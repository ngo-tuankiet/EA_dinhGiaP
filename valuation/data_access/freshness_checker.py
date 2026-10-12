"""Kiểm tra độ mới của giá, BCTC và báo cáo CTCK đã lưu trong DB."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from valuation.db.models import Consensus, FinancialsQuarterly, PricesDaily


@dataclass
class DataFreshnessStatus:
    is_stale: bool
    price_is_stale: bool
    consensus_is_stale: bool
    days_since_price: int
    days_since_consensus: int
    last_price_date: date | None
    last_consensus_date: date | None
    latest_financial_year: int | None
    latest_financial_quarter: int | None


def check_data_freshness(
    db: Session,
    threshold_days: int = 7,
    ticker: str | None = None,
) -> DataFreshnessStatus:
    """Trả trạng thái nguồn dữ liệu toàn DB hoặc của riêng một mã."""
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()

    price_query = db.query(func.max(PricesDaily.trade_date))
    consensus_query = db.query(func.max(Consensus.report_date))
    financial_query = db.query(
        FinancialsQuarterly.fiscal_year,
        FinancialsQuarterly.fiscal_quarter,
    ).filter(FinancialsQuarterly.fiscal_quarter > 0)
    if ticker:
        normalized_ticker = ticker.upper().strip()
        price_query = price_query.filter(PricesDaily.ticker == normalized_ticker)
        consensus_query = consensus_query.filter(
            Consensus.ticker == normalized_ticker,
            Consensus.is_synthetic.is_(False),
        )
        financial_query = financial_query.filter(
            FinancialsQuarterly.ticker == normalized_ticker
        )

    max_price_date = price_query.scalar()
    max_consensus_date = consensus_query.scalar()
    latest_fin = financial_query.order_by(
        FinancialsQuarterly.fiscal_year.desc(),
        FinancialsQuarterly.fiscal_quarter.desc(),
    ).first()

    days_price = (today - max_price_date).days if max_price_date else 999
    days_consensus = (today - max_consensus_date).days if max_consensus_date else 999
    price_is_stale = days_price >= threshold_days
    consensus_is_stale = days_consensus >= threshold_days

    return DataFreshnessStatus(
        is_stale=price_is_stale or consensus_is_stale,
        price_is_stale=price_is_stale,
        consensus_is_stale=consensus_is_stale,
        days_since_price=days_price,
        days_since_consensus=days_consensus,
        last_price_date=max_price_date,
        last_consensus_date=max_consensus_date,
        latest_financial_year=latest_fin[0] if latest_fin else None,
        latest_financial_quarter=latest_fin[1] if latest_fin else None,
    )


def _age_label(last_date: date | None, days_since: int) -> str:
    if last_date is None:
        return "chưa có dữ liệu"
    if days_since <= 0:
        return "hôm nay"
    return f"{days_since} ngày trước"


def describe_data_freshness(status: DataFreshnessStatus) -> tuple[str, str]:
    """Nêu đúng nguồn nào cũ và không đưa số giả 999 ngày lên giao diện."""
    if status.last_price_date is None and status.last_consensus_date is None:
        headline = "Chưa có giá và báo cáo CTCK"
    elif status.price_is_stale and status.consensus_is_stale:
        headline = "Giá và báo cáo CTCK cần cập nhật"
    elif status.price_is_stale:
        headline = "Giá cần cập nhật"
    elif status.consensus_is_stale:
        headline = "Báo cáo CTCK cần kiểm tra"
    else:
        headline = "Dữ liệu thị trường còn mới"

    details = (
        f"Giá: {_age_label(status.last_price_date, status.days_since_price)}; "
        "Báo cáo CTCK: "
        f"{_age_label(status.last_consensus_date, status.days_since_consensus)}."
    )
    return headline, details
