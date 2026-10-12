"""Thu thập và ghi idempotent sự kiện vốn/quyền cổ đông."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session
from vnstock import Company as VnstockCompany

from valuation.config import load_defaults
from valuation.db.models import CorporateAction, CorporateActionSync, Ticker


def _value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _date(value: Any) -> datetime.date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return datetime.datetime.fromtimestamp(float(value) / 1000.0).date()
    text = str(value).strip()[:10]
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _event_type(code: str, title: str, cash_amount: float | None) -> str:
    code = str(code or "").upper()
    lowered = title.lower()
    if "mua lại" in lowered or "cổ phiếu quỹ" in lowered:
        return "SHARE_BUYBACK"
    if "chuyển đổi" in lowered:
        return "CONVERTIBLE"
    if code == "DIV":
        return (
            "CASH_DIVIDEND"
            if cash_amount is not None or "tiền mặt" in lowered
            else "DIVIDEND_OTHER"
        )
    if code == "AIS":
        return "ADDITIONAL_LISTING"
    if code == "MA":
        return "MERGER"
    if code == "ISS":
        if "quyền mua" in lowered or "cổ đông hiện hữu" in lowered:
            return "RIGHTS_ISSUE"
        if "cbc nv" in lowered or "cbcnv" in lowered or "esop" in lowered:
            return "ESOP"
        if "riêng lẻ" in lowered:
            return "PRIVATE_PLACEMENT"
        if "thưởng" in lowered:
            return "BONUS_SHARE"
        if "cổ tức" in lowered:
            return "STOCK_DIVIDEND"
        return "SHARE_ISSUE"
    return "OTHER_CAPITAL_ACTION"


def _shares_from_title(title: str) -> float | None:
    match = re.search(r"([0-9][0-9.,]*)\s*cổ phiếu", title.lower())
    if not match:
        return None
    digits = re.sub(r"[^0-9]", "", match.group(1))
    return float(digits) if digits else None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def _with_hash(values: dict[str, Any]) -> dict[str, Any]:
    hashable = {
        key: (_json_safe(value) if not isinstance(value, dict) else value)
        for key, value in values.items()
        if key != "content_hash"
    }
    encoded = json.dumps(hashable, ensure_ascii=False, sort_keys=True, default=str)
    values["content_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return values


def normalize_vci_event(row: dict[str, Any], *, ticker: str) -> dict[str, Any]:
    """Chuẩn hóa một bản ghi VCI, giữ nguyên VND/cổ phiếu và payload nguồn."""
    title = str(
        _value(row, "eventTitleVi", "event_title_vi", "eventNameVi")
        or "Sự kiện doanh nghiệp"
    )
    code = str(_value(row, "eventCode", "event_code") or "")
    cash_amount = _number(_value(row, "valuePerShare", "value_per_share"))
    source_event_id = str(_value(row, "id") or "").strip()
    if not source_event_id:
        identity = f"{ticker}|{code}|{title}|{_value(row, 'publicDate', 'public_date')}"
        source_event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    raw_payload = {str(key): _json_safe(value) for key, value in row.items()}
    values: dict[str, Any] = {
        "ticker": ticker.upper(),
        "source_site": "VCI",
        "source_event_id": source_event_id,
        "event_type": _event_type(code, title, cash_amount),
        "event_code": code or None,
        "title": title,
        "announcement_date": _date(_value(row, "publicDate", "public_date")),
        "ex_right_date": _date(_value(row, "exrightDate", "exright_date")),
        "record_date": _date(_value(row, "recordDate", "record_date")),
        "payment_date": _date(_value(row, "payoutDate", "payout_date")),
        "listing_date": _date(_value(row, "listingDate", "listing_date")),
        "start_date": _date(_value(row, "startDate", "start_date")),
        "end_date": _date(_value(row, "endDate", "end_date")),
        "exercise_ratio": _number(_value(row, "exerciseRatio", "exercise_ratio")),
        "cash_amount_vnd_per_share": cash_amount,
        "issue_price_vnd": _number(_value(row, "issuePrice", "issue_price")),
        "shares_issued": _shares_from_title(title),
        "shares_after": None,
        "source_url": None,
        "source_tier": "AGGREGATOR",
        "raw_payload": raw_payload,
    }
    return _with_hash(values)


def load_official_config_events() -> list[dict[str, Any]]:
    """Nạp các mốc VSDC đã đối chiếu thủ công trong config hiện có."""
    path = Path(__file__).resolve().parents[2] / "config" / "corporate_actions.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    events: list[dict[str, Any]] = []
    for item in data.get("shares_outstanding_events") or []:
        ticker = str(item.get("ticker") or "").upper()
        effective_date = _date(item.get("effective_date"))
        shares_after = _number(item.get("shares_outstanding"))
        if not ticker or effective_date is None or shares_after is None:
            continue
        values = {
            "ticker": ticker,
            "source_site": "VSDC",
            "source_event_id": f"shares-{ticker}-{effective_date.isoformat()}-{int(shares_after)}",
            "event_type": "ADDITIONAL_LISTING",
            "event_code": "AIS",
            "title": str(item.get("note") or "VSDC xác nhận thay đổi số cổ phiếu"),
            "announcement_date": effective_date,
            "ex_right_date": None,
            "record_date": None,
            "payment_date": None,
            "listing_date": effective_date,
            "start_date": None,
            "end_date": None,
            "exercise_ratio": None,
            "cash_amount_vnd_per_share": None,
            "issue_price_vnd": None,
            "shares_issued": None,
            "shares_after": shares_after,
            "source_url": item.get("source_url"),
            "source_tier": "OFFICIAL",
            "raw_payload": {str(key): _json_safe(value) for key, value in item.items()},
        }
        events.append(_with_hash(values))
    return events


def upsert_corporate_actions(
    db: Session, events: Iterable[dict[str, Any]]
) -> dict[str, int]:
    """Chỉ ghi bản ghi mới/thay đổi; dữ liệu giống hệt không bị rewrite."""
    rows = list(events)
    result = {"inserted": 0, "updated": 0, "unchanged": 0}
    if not rows:
        return result

    tickers = {str(row["ticker"]).upper() for row in rows}
    existing = {
        (row.ticker, row.source_site, row.source_event_id): row
        for row in db.query(CorporateAction)
        .filter(CorporateAction.ticker.in_(tickers))
        .all()
    }
    now = datetime.datetime.now()
    try:
        for values in rows:
            key = (values["ticker"], values["source_site"], values["source_event_id"])
            current = existing.get(key)
            if current is None:
                db.add(CorporateAction(**values))
                result["inserted"] += 1
                continue
            if current.content_hash == values["content_hash"]:
                result["unchanged"] += 1
                continue
            for field, value in values.items():
                setattr(current, field, value)
            current.updated_at = now
            result["updated"] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def fetch_vci_corporate_actions(
    ticker: str,
    *,
    start_date: datetime.date,
    end_date: datetime.date,
    page_size: int,
) -> list[dict[str, Any]]:
    """Một request/mã, chỉ lấy nhóm cổ tức/phát hành/niêm yết liên quan vốn."""
    # Import vnstock ở module load trên luồng chính. Import lười đồng thời từ
    # worker Streamlit từng gây _ModuleLock deadlock và làm checkpoint đứng ERROR.
    company = VnstockCompany(source="VCI", symbol=ticker.upper())
    return list(
        company.provider._fetch_events(
            event_codes="DIV,ISS,AIS,MA,OTHE",
            from_date=start_date.strftime("%Y%m%d"),
            to_date=end_date.strftime("%Y%m%d"),
            page=0,
            size=page_size,
        )
        or []
    )


def refresh_corporate_actions(
    db: Session,
    ticker: str,
    *,
    force: bool = False,
    now: datetime.datetime | None = None,
    fetcher: Callable[..., list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Kiểm tra tăng dần một mã theo TTL; không ghi lại event không đổi."""
    from valuation.data_access.corporate_actions import should_refresh_corporate_actions

    cfg = (load_defaults().get("corporate_actions") or {}).copy()
    now = now or datetime.datetime.now()
    ttl_hours = int(cfg.get("refresh_ttl_hours", 24))
    error_retry_minutes = int(cfg.get("error_retry_minutes", 30))
    if not force and not should_refresh_corporate_actions(
        db,
        ticker,
        now=now,
        ttl_hours=ttl_hours,
        error_retry_minutes=error_retry_minutes,
    ):
        return {"status": "FRESH", "checked": False, "inserted": 0, "updated": 0}

    history_years = int(cfg.get("history_years", 5))
    future_days = int(cfg.get("future_days", 365))
    page_size = int(cfg.get("page_size", 200))
    today = now.date()
    start_date = today - datetime.timedelta(days=history_years * 366)
    end_date = today + datetime.timedelta(days=future_days)
    fetcher = fetcher or fetch_vci_corporate_actions
    ticker = ticker.upper()

    sync = db.get(CorporateActionSync, (ticker, "VCI"))
    if sync is None:
        sync = CorporateActionSync(ticker=ticker, source_site="VCI")
        db.add(sync)
    sync.last_checked_at = now

    try:
        raw_rows = fetcher(
            ticker,
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
        )
        normalized = [normalize_vci_event(row, ticker=ticker) for row in raw_rows]
        normalized = [
            row
            for row in normalized
            if row["announcement_date"] is not None
            and start_date <= row["announcement_date"] <= today
        ]
        result = upsert_corporate_actions(db, normalized)
        sync = db.get(CorporateActionSync, (ticker, "VCI")) or sync
        sync.last_checked_at = now
        sync.last_success_at = now
        sync.latest_announcement_date = max(
            (row["announcement_date"] for row in normalized), default=None
        )
        sync.status = "OK"
        sync.rows_seen = len(normalized)
        sync.last_error = None
        db.commit()
        return {"status": "OK", "checked": True, "seen": len(normalized), **result}
    except BaseException as exc:
        db.rollback()
        sync = db.get(CorporateActionSync, (ticker, "VCI"))
        if sync is None:
            sync = CorporateActionSync(ticker=ticker, source_site="VCI")
            db.add(sync)
        sync.last_checked_at = now
        sync.status = "ERROR"
        sync.last_error = str(exc)[:1000]
        db.commit()
        return {"status": "ERROR", "checked": True, "error": str(exc)}


def backfill_vn100_corporate_actions(
    db: Session,
    *,
    force: bool = False,
    fetcher: Callable[..., list[dict[str, Any]]] | None = None,
    progress: Callable[[int, int, str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Backfill có checkpoint theo mã; lỗi một mã không làm mất tiến độ mã khác."""
    cfg = (load_defaults().get("corporate_actions") or {}).copy()
    interval = float(cfg.get("request_interval_sec", 1.1))
    tickers = [
        row[0]
        for row in db.query(Ticker.ticker)
        .filter(Ticker.is_vn100.is_(True))
        .order_by(Ticker.ticker)
        .all()
    ]
    summary: dict[str, Any] = {
        "tickers": len(tickers),
        "ok": 0,
        "fresh": 0,
        "error": 0,
        "inserted": 0,
        "updated": 0,
        "details": [],
    }
    official = [
        row for row in load_official_config_events() if row["ticker"] in set(tickers)
    ]
    official_result = upsert_corporate_actions(db, official)
    summary["official"] = official_result

    for index, ticker in enumerate(tickers):
        result = refresh_corporate_actions(db, ticker, force=force, fetcher=fetcher)
        status = str(result.get("status") or "ERROR").lower()
        if status == "ok":
            summary["ok"] += 1
        elif status == "fresh":
            summary["fresh"] += 1
        else:
            summary["error"] += 1
        summary["inserted"] += int(result.get("inserted") or 0)
        summary["updated"] += int(result.get("updated") or 0)
        summary["details"].append({"ticker": ticker, **result})
        if progress is not None:
            progress(index + 1, len(tickers), ticker, result)
        if index < len(tickers) - 1 and result.get("checked"):
            time.sleep(interval)
    return summary
