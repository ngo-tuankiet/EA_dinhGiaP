"""
Freshness gate — kiểm tra ĐỘ TƯƠI dữ liệu trước khi định giá.

Bối cảnh: audit 2026-07-11 phát hiện giá trong DB lệch 5 "thế hệ" (mã cũ nhất
26/6, mới nhất 8/7) → upside giữa các mã KHÔNG so sánh được với nhau; đồng thời
TPCP_10Y (rf động) đứng ở 26/6. Người dùng yêu cầu "dữ liệu chuẩn mỗi lần quét"
— gate này bảo đảm mọi kết quả định giá tự khai báo dữ liệu nền có tươi không.

Không tính toán tài chính — chỉ đo tuổi dữ liệu và trả cờ:
  STALE_PRICE     — giá đóng cửa mới nhất của mã cũ hơn ngưỡng (mặc định 5 ngày lịch)
  STALE_MACRO_RF  — TPCP_10Y (lãi suất phi rủi ro động) cũ hơn 30 ngày
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

# Ngưỡng tuổi (ngày lịch). 5 ngày lịch ~ 3 phiên giao dịch + cuối tuần.
PRICE_MAX_AGE_DAYS = 5
MACRO_RF_MAX_AGE_DAYS = 30


def _latest_price_date(db: Session, ticker: str) -> Optional[datetime.date]:
    from valuation.db.models import PricesDaily
    row = (
        db.query(PricesDaily.trade_date)
        .filter(PricesDaily.ticker == ticker, PricesDaily.close.isnot(None))
        .order_by(PricesDaily.trade_date.desc())
        .first()
    )
    return row[0] if row else None


def _latest_macro_date(db: Session, indicator_code: str) -> Optional[datetime.date]:
    from valuation.db.models import MacroSeries
    row = (
        db.query(MacroSeries.date)
        .filter(MacroSeries.indicator_code == indicator_code)
        .order_by(MacroSeries.date.desc())
        .first()
    )
    return row[0] if row else None


def data_freshness_flags(
    db: Session,
    ticker: str,
    today: Optional[datetime.date] = None,
) -> List[str]:
    """Trả danh sách cờ tuổi dữ liệu cho 1 mã (rỗng nếu mọi thứ đủ tươi)."""
    today = today or datetime.date.today()
    flags: List[str] = []

    price_date = _latest_price_date(db, ticker)
    if price_date is None or (today - price_date).days > PRICE_MAX_AGE_DAYS:
        flags.append("STALE_PRICE")

    rf_date = _latest_macro_date(db, "TPCP_10Y")
    if rf_date is None or (today - rf_date).days > MACRO_RF_MAX_AGE_DAYS:
        flags.append("STALE_MACRO_RF")

    return flags
