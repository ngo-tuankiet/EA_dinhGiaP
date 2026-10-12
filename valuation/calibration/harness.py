"""Bộ điều phối chạy hiệu chuẩn toàn VN100 và lưu lịch sử.

Nguyên tắc thiết kế quan trọng: harness gọi `valuation.engine.batch.value_all` —
ĐÚNG lõi mà production/Streamlit/CLI dùng. Tuyệt đối không tạo đường định giá song
song, vì khi đó ta sẽ đo một thứ và giao cho người dùng một thứ khác.

Mỗi lần chạy lưu kèm `engine_config` (snapshot các key config ảnh hưởng định giá)
và `git_sha`, để câu hỏi "giữa hai lần chạy này thì cái gì đã đổi?" luôn trả lời
được (AGENTS.md luật vàng #5: mọi số đầu ra phải truy vết được về version giả định).
"""
from __future__ import annotations

import datetime
import logging
import subprocess
from dataclasses import dataclass, replace
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from valuation.calibration.consensus_view import (
    DEFAULT_WINDOW_DAYS,
    get_consensus_view,
)
from valuation.calibration.metrics import BAND_DEFAULT, Observation, aggregate, build_observation

logger = logging.getLogger(__name__)

# Các key trong config/defaults.yaml thực sự ảnh hưởng con số định giá.
# Snapshot lại để diff giữa 2 run giải thích được bằng thay đổi config.
_ENGINE_CONFIG_KEYS = (
    "coe_convention",
    "long_run_nominal_gdp_growth",
    "sector_ev_ebitda",
    "sector_pe",
    "sector_tax_rates",
    "proxy_valuation",
    "ddm",
    "bank_terminal",      # thêm ở GĐ5
    "securities",         # thêm ở GĐ3
    "relative_pb",        # thêm ở GĐ3
    "forecast",           # thêm ở GĐ7
)


@dataclass(frozen=True)
class CalibrationRun:
    label: str
    git_sha: Optional[str]
    as_of: datetime.date
    window_days: int
    dedup_mode: str
    weighting: str
    engine_config: dict[str, Any]
    observations: tuple[Observation, ...]
    aggregates: dict[str, Any]
    run_id: Optional[int] = None


def _git_sha() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _engine_config_snapshot() -> dict[str, Any]:
    from valuation.config import load_defaults
    d = load_defaults() or {}
    return {k: d[k] for k in _ENGINE_CONFIG_KEYS if k in d}


def _all_routed_tickers() -> list[str]:
    from valuation.engine.sector_router import _router
    return sorted(_router().routing_data.keys())


def run_calibration(
    db_read: Session,
    tickers: Optional[Sequence[str]] = None,
    as_of: Optional[datetime.date] = None,
    label: str = "",
    window_days: int = DEFAULT_WINDOW_DAYS,
    half_life_days: Optional[float] = None,
    band: float = BAND_DEFAULT,
    registry: Optional[dict] = None,
    macro_env=None,
    progress=None,
) -> CalibrationRun:
    """Định giá toàn bộ mã rồi đo lệch vs đồng thuận CTCK và vs thị giá.

    Args:
        registry: dict[ticker -> RegistryEntry] từ GĐ2. None → bỏ qua governance.
        progress: callable(idx, total, ticker) để hiển thị tiến độ CLI.
    """
    from valuation.engine.batch import value_ticker

    as_of = as_of or datetime.date.today()
    tickers = list(tickers) if tickers else _all_routed_tickers()
    total = len(tickers)

    observations: list[Observation] = []
    for idx, ticker in enumerate(tickers, start=1):
        if progress:
            progress(idx, total, ticker)
        try:
            valuation = value_ticker(db_read, ticker, macro_env=macro_env, as_of=as_of)
        except Exception as exc:  # 1 mã lỗi không phá cả lần chạy
            logger.warning("value_ticker(%s) lỗi: %s", ticker, exc)
            valuation = {"ticker": ticker, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}

        view = get_consensus_view(
            db_read, ticker, as_of=as_of,
            window_days=window_days, half_life_days=half_life_days,
        )
        obs = build_observation(ticker, valuation, view, band=_band_for(ticker, valuation, registry, band))
        obs = _apply_governance(obs, registry, as_of)
        observations.append(obs)

    return CalibrationRun(
        label=label or f"run-{as_of.isoformat()}",
        git_sha=_git_sha(),
        as_of=as_of,
        window_days=window_days,
        dedup_mode="latest_per_broker",
        weighting=("none" if not half_life_days else f"halflife_{half_life_days:g}d"),
        engine_config=_engine_config_snapshot(),
        observations=tuple(observations),
        aggregates=aggregate(observations),
    )


def _band_for(ticker: str, valuation: dict, registry: Optional[dict], default: float) -> float:
    """Band riêng cho mã/nhóm PP nếu registry quy định (GĐ2), không thì mặc định."""
    if not registry:
        return default
    try:
        from valuation.calibration.registry import band_for
        return band_for(ticker, valuation.get("method"), registry, default)
    except ImportError:
        return default


def _apply_governance(obs: Observation, registry: Optional[dict], today: datetime.date) -> Observation:
    """Gắn governance_status vào quan sát (GĐ2). Không có registry → giữ 'OK'."""
    if not registry:
        return obs
    try:
        from valuation.calibration.registry import govern
    except ImportError:
        return obs
    status, entry = govern(obs.ticker, obs.band_status, registry, today)
    return replace(
        obs,
        governance_status=status,
        registry_status=(entry.status if entry else None),
        registry_thesis=(entry.thesis if entry else None),
    )


# --------------------------------------------------------------------------
# Lưu / đọc lịch sử
# --------------------------------------------------------------------------

def persist_run(db_write: Session, run: CalibrationRun) -> int:
    """Ghi 1 lần chạy vào DB. Idempotent theo `label` (AGENTS.md luật vàng #6):
    chạy lại cùng label sẽ GHI ĐÈ, không nhân đôi dữ liệu."""
    from sqlalchemy import delete
    from valuation.db.models import CalibrationObservation, CalibrationRunRow

    overall = run.aggregates.get("overall", {})
    existing = (
        db_write.query(CalibrationRunRow)
        .filter(CalibrationRunRow.label == run.label)
        .one_or_none()
    )
    if existing is not None:
        db_write.execute(
            delete(CalibrationObservation).where(CalibrationObservation.run_id == existing.id)
        )
        row = existing
    else:
        row = CalibrationRunRow(label=run.label)
        db_write.add(row)

    row.git_sha = run.git_sha
    row.as_of = run.as_of
    row.window_days = run.window_days
    row.dedup_mode = run.dedup_mode
    row.weighting = run.weighting
    row.engine_config = run.engine_config
    row.n_tickers = len(run.observations)
    row.n_valued = sum(1 for o in run.observations if o.fair_value)
    row.n_with_consensus = overall.get("n_with_consensus")
    row.median_dev_vs_consensus = overall.get("median_dev")
    row.median_abs_dev_vs_consensus = overall.get("median_abs_dev")
    row.share_in_band = overall.get("share_in_band")
    row.median_dev_vs_price = overall.get("median_dev_vs_price")
    row.n_below_price = overall.get("n_below_price")
    row.n_below_price_40 = overall.get("n_below_price_40")
    row.aggregates = run.aggregates
    db_write.flush()

    for o in run.observations:
        db_write.add(CalibrationObservation(
            run_id=row.id, ticker=o.ticker, method=o.method,
            sector_group=o.sector_group, business_nature=o.business_nature,
            fair_value=o.fair_value, market_price=o.market_price,
            consensus_median=o.consensus_median, consensus_weighted=o.consensus_weighted,
            n_brokers=o.n_brokers, consensus_min=o.consensus_min,
            consensus_max=o.consensus_max, consensus_age_days=o.consensus_age_days,
            dev_vs_consensus=o.dev_vs_consensus, dev_vs_price=o.dev_vs_price,
            band=o.band, band_status=o.band_status,
            governance_status=o.governance_status, registry_status=o.registry_status,
            registry_thesis=o.registry_thesis,
            flags=list(o.flags or []), error=o.error,
        ))
    db_write.commit()
    return int(row.id)


def load_run(
    db_read: Session,
    run_id: Optional[int] = None,
    label: Optional[str] = None,
) -> Optional[CalibrationRun]:
    """Đọc lại 1 lần chạy đã lưu (theo id hoặc label; không truyền gì → mới nhất)."""
    from valuation.db.models import CalibrationObservation, CalibrationRunRow

    q = db_read.query(CalibrationRunRow)
    if run_id is not None:
        q = q.filter(CalibrationRunRow.id == run_id)
    elif label is not None:
        q = q.filter(CalibrationRunRow.label == label)
    row = q.order_by(CalibrationRunRow.id.desc()).first()
    if row is None:
        return None

    obs_rows = (
        db_read.query(CalibrationObservation)
        .filter(CalibrationObservation.run_id == row.id)
        .all()
    )
    observations = tuple(
        Observation(
            ticker=r.ticker, method=r.method, sector_group=r.sector_group,
            business_nature=r.business_nature,
            fair_value=_f(r.fair_value), market_price=_f(r.market_price),
            consensus_median=_f(r.consensus_median),
            consensus_weighted=_f(r.consensus_weighted),
            n_brokers=r.n_brokers or 0,
            consensus_min=_f(r.consensus_min), consensus_max=_f(r.consensus_max),
            consensus_age_days=r.consensus_age_days,
            dev_vs_consensus=_f(r.dev_vs_consensus), dev_vs_price=_f(r.dev_vs_price),
            band=_f(r.band) or BAND_DEFAULT, band_status=r.band_status,
            governance_status=r.governance_status or "OK",
            registry_status=r.registry_status, registry_thesis=r.registry_thesis,
            flags=list(r.flags or []), error=r.error,
        )
        for r in obs_rows
    )
    return CalibrationRun(
        label=row.label, git_sha=row.git_sha, as_of=row.as_of,
        window_days=row.window_days or DEFAULT_WINDOW_DAYS,
        dedup_mode=row.dedup_mode or "latest_per_broker",
        weighting=row.weighting or "none",
        engine_config=row.engine_config or {},
        observations=observations,
        aggregates=row.aggregates or aggregate(observations),
        run_id=int(row.id),
    )


def _f(x) -> Optional[float]:
    return None if x is None else float(x)
