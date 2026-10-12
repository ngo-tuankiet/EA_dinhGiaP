"""Một worker dùng chung cho nút bấm và lịch tuần; UI chỉ đọc kết quả đã lưu."""

from __future__ import annotations

import subprocess
import sys
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from valuation.analysis.investment_ranking import (
    load_ranking_config,
    rank_companies,
    score_metrics,
    select_candidates,
)
from valuation.services.ranking_store import (
    ROOT,
    STORE,
    exclusive_lock,
    latest_snapshot,
    publish,
    read_json,
    write_json,
)


def _sqlite_path_from_url(url: str) -> Path | None:
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return None
    database = parsed.database
    if not database or database == ":memory:":
        return None
    path = Path(database)
    return path if path.is_absolute() else ROOT / path


@contextmanager
def _batch_read_session_factory(*, refresh: bool, store: Path):
    from valuation.config import settings
    from valuation.db.session import SessionLocalRead

    source = _sqlite_path_from_url(settings.database_url_readonly)
    if refresh or source is None or not source.exists():
        yield SessionLocalRead
        return

    with TemporaryDirectory(prefix="vn100-ranking-db-") as temp_dir:
        target = Path(temp_dir) / source.name
        copy2(source, target)
        marker = store / "runtime" / "readonly_db_copy.json"
        write_json(
            marker,
            {
                "source": str(source),
                "target": str(target),
                "created_at": local_now().isoformat(),
                "reason": "batch_read_no_refresh",
            },
        )
        engine = create_engine(
            f"sqlite:///{target}",
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        try:
            yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
        finally:
            engine.dispose()


def local_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))


def week_key(now: datetime) -> str:
    schedule = load_ranking_config()["schedule"]
    weekday = schedule["weekday"]
    day = now.date() - timedelta(days=(now.weekday() - weekday) % 7)
    if now.weekday() == weekday and (now.hour, now.minute) < (
        schedule["hour"],
        schedule["minute"],
    ):
        day -= timedelta(days=7)
    return day.isoformat()


def next_run(now: datetime) -> datetime:
    schedule = load_ranking_config()["schedule"]
    candidate = now.replace(
        hour=schedule["hour"], minute=schedule["minute"], second=0, microsecond=0
    )
    candidate += timedelta(days=(schedule["weekday"] - now.weekday()) % 7)
    return candidate if candidate > now else candidate + timedelta(days=7)


def job_status(store: Path = STORE) -> dict:
    status = read_json(store / "status.json", {})
    if status.get("status") in ("QUEUED", "RUNNING"):
        try:
            with exclusive_lock(store / "worker.lock"):
                age = (
                    local_now() - datetime.fromisoformat(status["updated_at"])
                ).total_seconds()
                if status["status"] == "RUNNING" or age > 60:
                    return {
                        **status,
                        "status": "INTERRUPTED",
                        "message": "Đợt trước đã dừng; bản kết quả cũ vẫn được giữ. Có thể cập nhật lại.",
                    }
        except OSError:
            pass
    return status


def start_job(store: Path = STORE) -> bool:
    try:
        with exclusive_lock(store / "launch.lock"):
            if job_status(store).get("status") in ("QUEUED", "RUNNING"):
                return False
            write_json(
                store / "status.json",
                {
                    "status": "QUEUED",
                    "message": "Đang khởi động",
                    "updated_at": local_now().isoformat(),
                    "completed": 0,
                    "total": 100,
                },
            )
            try:
                subprocess.Popen(
                    [sys.executable, str(ROOT / "scripts/update_vn100_ranking.py")],
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,  # khởi động lại app không giết worker
                )
            except OSError:
                write_json(
                    store / "status.json",
                    {
                        "status": "FAILED",
                        "message": "Không khởi động được Python worker",
                        "updated_at": local_now().isoformat(),
                    },
                )
                raise
            return True
    except BlockingIOError:
        return False


def run_job(
    *,
    refresh: bool = True,
    use_ai: bool = True,
    scheduled: bool = False,
    store: Path = STORE,
    progress_sink: Callable[[dict], None] | None = None,
) -> dict:
    try:
        with exclusive_lock(store / "worker.lock"):
            return _run_locked(
                refresh=refresh,
                use_ai=use_ai,
                scheduled=scheduled,
                store=store,
                progress_sink=progress_sink,
            )
    except BlockingIOError:
        return {"status": "BUSY", "message": "Đã có một đợt cập nhật đang chạy"}


def _run_locked(
    *,
    refresh: bool,
    use_ai: bool,
    scheduled: bool,
    store: Path,
    progress_sink: Callable[[dict], None] | None = None,
) -> dict:
    from valuation.config import PROJECT_ROOT
    from valuation.data_access.investment_snapshot import build_ranking_row, fingerprint
    from valuation.db.models import MacroSeries
    from valuation.ingest.universe import load_vn100_snapshot
    from valuation.report.accumulation_review import generate_review
    from valuation.services.ranking_sources import fetch_news, refresh_ticker

    cfg, now = load_ranking_config(), local_now()
    schedule_path = store / "schedule.json"
    schedule_key = f"{week_key(now)}:{fingerprint(cfg)}"
    if scheduled and read_json(schedule_path, {}).get("key") == schedule_key:
        return {"status": "UNCHANGED", "message": "Lịch tuần này đã thực hiện"}
    run_id = now.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    state = {"run_id": run_id, "status": "RUNNING", "completed": 0, "total": 100}

    def progress(message: str) -> None:
        state.update(message=message, updated_at=local_now().isoformat())
        write_json(store / "status.json", state)
        if progress_sink is not None:
            progress_sink(dict(state))

    progress("Đọc thành phần VN100 và kiểm tra nguồn")
    try:
        universe = load_vn100_snapshot()
        evidence = read_json(
            PROJECT_ROOT / "config/investment_evidence.json", {"companies": {}}
        )["companies"]
        old = latest_snapshot(store) or {}
        rows, source_errors = [], []
        with _batch_read_session_factory(refresh=refresh, store=store) as ReadSession:
            for index, ticker in enumerate(universe["symbols"]):
                progress(
                    f"{ticker}: {'kiểm tra dữ liệu và ' if refresh else ''}định giá ba kịch bản"
                )
                ticker_errors = (
                    refresh_ticker(ticker, now, cfg, store) if refresh else []
                )
                source_errors.extend(ticker_errors)
                try:
                    with ReadSession() as db:
                        row = build_ranking_row(
                            db, ticker, now.date(), cfg, evidence.get(ticker, {})
                        )
                except (
                    SQLAlchemyError,
                    RuntimeError,
                    ValueError,
                    TypeError,
                    ArithmeticError,
                    OSError,
                    KeyError,
                    IndexError,
                    AttributeError,
                    SystemExit,
                ) as exc:
                    from valuation.config import settings

                    detail = str(exc)
                    for secret in (settings.vnstock_api_key, settings.deepseek_api_key):
                        if secret:
                            detail = detail.replace(secret, "[redacted]")
                    row = {
                        "ticker": ticker,
                        "name": ticker,
                        "sector": "Chưa rõ",
                        "error": f"Không tạo được hồ sơ ({type(exc).__name__}): {detail[:350]}",
                        "flags": [],
                    }
                row.setdefault("blockers", []).extend(ticker_errors)
                universe_age = (
                    now.date() - datetime.fromisoformat(universe["as_of"]).date()
                ).days
                if not 0 <= universe_age <= cfg["universe_max_age_days"]:
                    row["blockers"].append("Cần xác nhận lại thành phần rổ VN100")
                rows.append(row)
                state["completed"] = index + 1
                write_json(store / "checkpoints" / run_id / f"{ticker}.json", row)
            with ReadSession() as db:
                macro_rows = (
                    db.query(MacroSeries)
                    .filter(MacroSeries.date <= now.date())
                    .order_by(MacroSeries.date.desc())
                    .all()
                )
        score_metrics(rows, cfg)
        rows = rank_companies(rows, cfg)
        if not any(r["profiles"]["defensive"]["score"] is not None for r in rows):
            raise ValueError(
                "Không có mã nào đủ dữ liệu tính điểm; giữ nguyên snapshot cũ"
            )
        previous = (
            old.get("previous_selections", {})
            if old.get("week") == week_key(now)
            else old.get("selections", {})
        )
        if (
            old.get("week") != week_key(now)
            and old.get("ai", {}).get("status") == "SUCCESS"
        ):
            previous = {}
            old_by_ticker = {row["ticker"]: row for row in old["rows"]}
            for key in cfg["profiles"]:
                picks = [item["ticker"] for item in old["ai"]["review"][key]["picks"]]
                accepted = [
                    ticker
                    for ticker in picks
                    if old_by_ticker[ticker]["profiles"][key]["eligible"]
                ]
                previous[key] = {
                    "qualified": accepted,
                    "research": [ticker for ticker in picks if ticker not in accepted],
                }
        selections = {
            key: {
                "qualified": select_candidates(rows, key, cfg, eligible_only=True),
                "research": select_candidates(rows, key, cfg, eligible_only=False),
            }
            for key in cfg["profiles"]
        }
        old_rows = {row["ticker"]: row for row in old.get("rows", [])}
        for row in rows:
            for key in cfg["profiles"]:
                old_rank = (
                    old_rows.get(row["ticker"], {})
                    .get("profiles", {})
                    .get(key, {})
                    .get("rank")
                )
                rank = row["profiles"][key]["rank"]
                row["profiles"][key]["rank_change"] = (
                    old_rank - rank if old_rank and rank else None
                )
        progress("Kiểm tra bản tin và hồ sơ nguồn")
        news = (
            fetch_news(now, cfg, store)
            if refresh
            else read_json(
                store / "news.json",
                {"items": [], "errors": ["Đợt này chỉ tính bằng dữ liệu đã lưu"]},
            )
        )
        macro = {}
        for item in macro_rows:
            if item.indicator_code not in macro:
                macro[item.indicator_code] = {
                    "value": float(item.value) if item.value is not None else None,
                    "date": str(item.date),
                    "source": item.source,
                }
        snapshot = {
            "run_id": run_id,
            "started_at": now.isoformat(),
            "week": week_key(now),
            "config": cfg,
            "universe": universe,
            "rows": rows,
            "macro": macro,
            "selections": selections,
            "previous_selections": previous,
            "news": news,
            "source_errors": source_errors,
            "source_refresh": refresh,
        }
        progress("Phản biện hai chiến lược qua DeepSeek (tối đa một yêu cầu)")
        snapshot["ai"] = (
            generate_review(snapshot, cfg, store, now)
            if use_ai
            else {"status": "SKIPPED", "message": "Đợt kiểm thử không gọi AI"}
        )
        snapshot["completed_at"] = local_now().isoformat()
        snapshot["data_status"] = (
            "NEEDS_REVIEW"
            if any(
                r.get("error") or not r["profiles"]["defensive"]["eligible"]
                for r in rows
            )
            else "COMPLETE"
        )
        publish(snapshot, store)
        if scheduled:
            write_json(schedule_path, {"key": schedule_key, "run_id": run_id})
        state["status"] = "COMPLETED"
        progress(
            f"Đã tính {len(rows)} mã. AI: {snapshot['ai']['status']}. Cần đọc các điều kiện chưa đạt trước khi tư vấn."
        )
        return state
    except (
        SQLAlchemyError,
        RuntimeError,
        ValueError,
        TypeError,
        ArithmeticError,
        OSError,
        KeyError,
        IndexError,
        AttributeError,
        SystemExit,
    ) as exc:
        state["status"] = "FAILED"
        progress(
            f"Đợt cập nhật chưa hoàn thành ({type(exc).__name__}). Bản thành công trước vẫn được giữ."
        )
        raise
