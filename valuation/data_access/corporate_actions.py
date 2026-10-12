"""Đọc sự kiện doanh nghiệp theo thời điểm, không rò dữ liệu công bố tương lai."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from valuation.analysis.corporate_actions import (
    analyze_corporate_action,
    analyze_historical_price_impact,
    assess_corporate_action,
    dividend_track_record,
    explain_historical_price_impact,
    explain_upcoming_action,
)
from valuation.config import load_defaults
from valuation.db.models import (
    CorporateAction,
    CorporateActionSync,
    PricesDaily,
    Ticker,
)

_PRICE_IMPACT_TYPES = {
    "CASH_DIVIDEND",
    "STOCK_DIVIDEND",
    "BONUS_SHARE",
    "RIGHTS_ISSUE",
    "ESOP",
    "PRIVATE_PLACEMENT",
    "SHARE_ISSUE",
}
_VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

_ACTION_MILESTONES = (
    ("ex_right_date", "Ngày GDKHQ"),
    ("record_date", "Ngày chốt quyền"),
    ("payment_date", "Ngày thanh toán"),
    ("start_date", "Bắt đầu đăng ký/mua"),
    ("end_date", "Kết thúc đăng ký/mua"),
    ("listing_date", "Ngày niêm yết"),
)


@dataclass(frozen=True)
class UpcomingCorporateAction:
    """Một sự kiện VN100 cùng mốc thực hiện gần nhất còn ở phía trước."""

    action: CorporateAction
    company_name: str
    event_date: datetime.date
    date_role: str


def _today_vn() -> datetime.date:
    return datetime.datetime.now(_VN_TZ).date()


def _same_timezone(
    left: datetime.datetime, right: datetime.datetime
) -> tuple[datetime.datetime, datetime.datetime]:
    """SQLite có thể trả datetime naive; chuẩn hóa trước khi so sánh TTL."""
    if left.tzinfo is None and right.tzinfo is not None:
        left = left.replace(tzinfo=right.tzinfo)
    elif left.tzinfo is not None and right.tzinfo is None:
        right = right.replace(tzinfo=left.tzinfo)
    return left, right


def should_refresh_corporate_actions(
    db: Session,
    ticker: str,
    *,
    now: datetime.datetime | None = None,
    ttl_hours: int = 24,
    error_retry_minutes: int = 30,
) -> bool:
    now = now or datetime.datetime.now(_VN_TZ)
    sync = db.get(CorporateActionSync, (ticker.upper(), "VCI"))
    if sync is None or sync.last_checked_at is None:
        return True
    checked = sync.last_checked_at
    now, checked = _same_timezone(now, checked)
    if sync.status != "OK":
        return now - checked >= datetime.timedelta(minutes=error_retry_minutes)
    return now - checked >= datetime.timedelta(hours=ttl_hours)


def _event_anchor(row: CorporateAction) -> datetime.date | None:
    return (
        row.ex_right_date
        or row.record_date
        or row.payment_date
        or row.listing_date
        or row.announcement_date
    )


def load_corporate_actions(
    db: Session,
    ticker: str,
    *,
    as_of_date: datetime.date | None = None,
    history_years: int = 5,
    future_days: int = 365,
) -> list[CorporateAction]:
    """Chỉ dùng sự kiện đã được công bố tính đến `as_of_date`."""
    as_of = as_of_date or _today_vn()
    window_start = as_of - datetime.timedelta(days=history_years * 366)
    window_end = as_of + datetime.timedelta(days=future_days)
    rows = (
        db.query(CorporateAction)
        .filter(
            CorporateAction.ticker == ticker.upper(),
            CorporateAction.announcement_date.is_not(None),
            CorporateAction.announcement_date <= as_of,
        )
        .all()
    )
    rows = [
        row
        for row in rows
        if (anchor := _event_anchor(row)) and window_start <= anchor <= window_end
    ]
    source_rank = {"OFFICIAL": 0, "AGGREGATOR": 1}
    rows.sort(
        key=lambda row: (
            _event_anchor(row) or datetime.date.min,
            -source_rank.get(row.source_tier, 9),
        ),
        reverse=True,
    )
    return rows


def _next_action_milestone(
    row: CorporateAction,
    *,
    window_start: datetime.date,
    window_end: datetime.date,
) -> tuple[datetime.date, str] | None:
    candidates = [
        (event_date, role)
        for field, role in _ACTION_MILESTONES
        if (event_date := getattr(row, field)) is not None
        and window_start <= event_date <= window_end
    ]
    return min(candidates, key=lambda item: item[0]) if candidates else None


def load_upcoming_vn100_corporate_actions(
    db: Session,
    *,
    as_of_date: datetime.date | None = None,
    future_days: int = 30,
) -> list[UpcomingCorporateAction]:
    """Đọc sự kiện đã công bố có mốc thực hiện trong cửa sổ VN100 sắp tới.

    Một sự kiện vẫn được giữ nếu ngày GDKHQ đã qua nhưng ngày thanh toán,
    đăng ký mua hoặc niêm yết còn nằm trong cửa sổ. Ngày công bố tương lai bị
    loại để tránh lookahead.
    """
    as_of = as_of_date or _today_vn()
    window_end = as_of + datetime.timedelta(days=max(int(future_days), 0))
    rows = (
        db.query(CorporateAction, Ticker.company_name)
        .join(Ticker, Ticker.ticker == CorporateAction.ticker)
        .filter(
            Ticker.is_vn100.is_(True),
            CorporateAction.announcement_date.is_not(None),
            CorporateAction.announcement_date <= as_of,
        )
        .all()
    )
    upcoming: list[UpcomingCorporateAction] = []
    for action, company_name in rows:
        milestone = _next_action_milestone(
            action,
            window_start=as_of,
            window_end=window_end,
        )
        if milestone is None:
            continue
        event_date, date_role = milestone
        upcoming.append(
            UpcomingCorporateAction(
                action=action,
                company_name=company_name or action.ticker,
                event_date=event_date,
                date_role=date_role,
            )
        )
    source_rank = {"OFFICIAL": 0, "AGGREGATOR": 1}
    upcoming.sort(
        key=lambda item: (
            item.event_date,
            item.action.ticker,
            source_rank.get(item.action.source_tier, 9),
        )
    )
    return upcoming


def corporate_actions_context(
    db: Session,
    *,
    ticker: str,
    current_price_vnd: float,
    shares_outstanding: float,
    as_of_date: datetime.date | None = None,
) -> dict[str, Any]:
    cfg = (load_defaults().get("corporate_actions") or {}).copy()
    rows = load_corporate_actions(
        db,
        ticker,
        as_of_date=as_of_date,
        history_years=int(cfg.get("history_years", 5)),
        future_days=int(cfg.get("future_days", 365)),
    )
    max_events = int(cfg.get("max_events_ai", 12))
    as_of = as_of_date or _today_vn()
    price_rows = (
        db.query(PricesDaily.trade_date, PricesDaily.close)
        .filter(PricesDaily.ticker == ticker.upper())
        .order_by(PricesDaily.trade_date)
        .all()
    )
    prices = [
        {"date": row.trade_date, "close": float(row.close)}
        for row in price_rows
        if row.close is not None
    ]
    events: list[dict[str, Any]] = []
    for row in rows[:max_events]:
        analysis = analyze_corporate_action(
            event_type=row.event_type,
            current_price_vnd=current_price_vnd,
            shares_outstanding=shares_outstanding,
            exercise_ratio=(
                float(row.exercise_ratio) if row.exercise_ratio is not None else None
            ),
            cash_amount_vnd_per_share=(
                float(row.cash_amount_vnd_per_share)
                if row.cash_amount_vnd_per_share is not None
                else None
            ),
            issue_price_vnd=(
                float(row.issue_price_vnd) if row.issue_price_vnd is not None else None
            ),
        )
        assessment = assess_corporate_action(
            event_type=row.event_type,
            analysis=analysis,
            attractive_dividend_yield_pct=float(
                cfg.get("attractive_dividend_yield_pct", 5.0)
            ),
            dilution_warning_pct=float(cfg.get("dilution_warning_pct", 10.0)),
        )
        anchor = _event_anchor(row)
        time_status = "UPCOMING" if anchor and anchor > as_of else "HISTORICAL"
        historical_price_impact = None
        if anchor and anchor <= as_of and row.event_type in _PRICE_IMPACT_TYPES:
            historical_price_impact = analyze_historical_price_impact(
                prices=prices,
                event_date=anchor,
                event_type=row.event_type,
                exercise_ratio=(
                    float(row.exercise_ratio)
                    if row.exercise_ratio is not None
                    else None
                ),
                cash_amount_vnd_per_share=(
                    float(row.cash_amount_vnd_per_share)
                    if row.cash_amount_vnd_per_share is not None
                    else None
                ),
                issue_price_vnd=(
                    float(row.issue_price_vnd)
                    if row.issue_price_vnd is not None
                    else None
                ),
                short_sessions=int(cfg.get("price_impact_short_sessions", 5)),
                long_sessions=int(cfg.get("price_impact_long_sessions", 20)),
            )
        historical_explanation = None
        if historical_price_impact and historical_price_impact.get("available"):
            historical_explanation = explain_historical_price_impact(
                event_type=row.event_type,
                impact=historical_price_impact,
                reaction_materiality_pct=float(
                    cfg.get("reaction_materiality_pct", 2.0)
                ),
            )
        upcoming_explanation = None
        if time_status == "UPCOMING":
            upcoming_explanation = explain_upcoming_action(
                event_type=row.event_type,
                holding_shares=int(cfg.get("example_holding_shares", 1_000)),
                current_price_vnd=current_price_vnd,
                exercise_ratio=(
                    float(row.exercise_ratio)
                    if row.exercise_ratio is not None
                    else None
                ),
                cash_amount_vnd_per_share=(
                    float(row.cash_amount_vnd_per_share)
                    if row.cash_amount_vnd_per_share is not None
                    else None
                ),
                issue_price_vnd=(
                    float(row.issue_price_vnd)
                    if row.issue_price_vnd is not None
                    else None
                ),
                analysis=analysis,
            )
        events.append(
            {
                "event_type": row.event_type,
                "title": row.title,
                "announcement_date": (
                    row.announcement_date.isoformat() if row.announcement_date else None
                ),
                "effective_date": anchor.isoformat() if anchor else None,
                "time_status": time_status,
                "exercise_ratio": (
                    float(row.exercise_ratio)
                    if row.exercise_ratio is not None
                    else None
                ),
                "cash_amount_vnd_per_share": (
                    float(row.cash_amount_vnd_per_share)
                    if row.cash_amount_vnd_per_share is not None
                    else None
                ),
                "issue_price_vnd": (
                    float(row.issue_price_vnd)
                    if row.issue_price_vnd is not None
                    else None
                ),
                "shares_after": (
                    float(row.shares_after) if row.shares_after is not None else None
                ),
                "source_site": row.source_site,
                "source_tier": row.source_tier,
                "source_url": row.source_url,
                "analysis": analysis,
                "assessment": assessment,
                "historical_price_impact": historical_price_impact,
                "historical_explanation": historical_explanation,
                "upcoming_explanation": upcoming_explanation,
            }
        )
    sync = db.get(CorporateActionSync, (ticker.upper(), "VCI"))
    return {
        "available": bool(events),
        "as_of_date": as_of.isoformat(),
        "n_events": len(events),
        "events": events,
        "last_checked_at": (
            sync.last_checked_at.isoformat() if sync and sync.last_checked_at else None
        ),
        "source_warning": (
            "VCI là nguồn tổng hợp. Sự kiện chưa có nguồn OFFICIAL cần đối chiếu VSDC/HOSE/HNX/IR trước quyết định."
        ),
    }


def load_dividend_track_records(
    db: Session,
    tickers: list[str],
    *,
    as_of: datetime.date,
    history_years: int,
    post_sessions: int,
    consistency_years: int,
) -> dict[str, dict[str, Any]]:
    """{mã: dividend_track_record} cho các mã trong lịch quyền — một lượt đọc DB cho cả nhóm (D56)."""
    if not tickers:
        return {}
    start = as_of - datetime.timedelta(days=366 * history_years)
    cash: dict[str, list[tuple[datetime.date, float]]] = {}
    for t, ex, amount in (
        db.query(
            CorporateAction.ticker,
            CorporateAction.ex_right_date,
            CorporateAction.cash_amount_vnd_per_share,
        )
        .filter(
            CorporateAction.ticker.in_(tickers),
            CorporateAction.event_type == "CASH_DIVIDEND",
            CorporateAction.ex_right_date.is_not(None),
            CorporateAction.ex_right_date >= start,
            CorporateAction.ex_right_date <= as_of,
        )
        .all()
    ):
        if amount is not None:
            cash.setdefault(t, []).append((ex, float(amount)))
    closes: dict[str, list[tuple[datetime.date, float]]] = {}
    for t, day, close in (
        db.query(PricesDaily.ticker, PricesDaily.trade_date, PricesDaily.close)
        .filter(
            PricesDaily.ticker.in_([*tickers, "VNINDEX"]),
            PricesDaily.trade_date >= start - datetime.timedelta(days=10),
            PricesDaily.trade_date <= as_of,
        )
        .all()
    ):
        if close is not None:
            closes.setdefault(t, []).append((day, float(close)))
    return {
        t: dividend_track_record(
            cash_events=cash.get(t, []),
            closes=closes.get(t, []),
            index_closes=closes.get("VNINDEX", []),
            as_of=as_of,
            post_sessions=post_sessions,
            consistency_years=consistency_years,
        )
        for t in tickers
    }
