"""Fetcher dữ liệu vĩ mô thị trường (FX, hàng hóa) qua yfinance.

vnstock 4.x KHÔNG có module macro/bond, nên dữ liệu thị trường (tỷ giá, giá
hàng hóa) lấy qua yfinance; còn TPCP_10Y / CPI / GDP (không có API miễn phí
tin cậy) đi qua đường CSV (`valuation.ingest.macro_csv`).

Mọi ghi DB đi qua `upsert_macro_series` (idempotent + validate registry). Hàm
fetch được tách rời (dependency injection qua `price_fetcher`) để test không
cần mạng.
"""
from __future__ import annotations

import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from valuation.ingest.macro_store import MacroPoint, upsert_macro_series

# yfinance symbol -> series_code chuẩn trong registry.
YF_SYMBOL_TO_CODE: dict[str, str] = {
    "VND=X": "USDVND",     # Tỷ giá USD/VND
    "HRC=F": "STEEL_HRC",  # HRC futures (USD/tấn)
    "CL=F": "CRUDE_OIL",   # Dầu WTI (USD/thùng)
}

# (date, close) của quan sát mới nhất cho một symbol.
PricePoint = tuple[datetime.date, float]
# Hàm lấy giá: symbol -> PricePoint | None (None nếu không có dữ liệu).
PriceFetcher = Callable[[str], Optional[PricePoint]]


def _yfinance_latest_close(symbol: str) -> Optional[PricePoint]:
    """Lấy (ngày, giá đóng cửa) gần nhất từ yfinance. None nếu rỗng."""
    import yfinance as yf

    hist = yf.Ticker(symbol).history(period="5d")
    if hist.empty:
        return None
    latest = hist.iloc[-1]
    return latest.name.date(), float(latest["Close"])


def fetch_market_macro(
    db: Session,
    price_fetcher: PriceFetcher = _yfinance_latest_close,
    symbol_map: Optional[dict[str, str]] = None,
    registry: Optional[dict] = None,
) -> int:
    """Lấy FX + hàng hóa, ghi idempotent vào macro_series.

    Trả về số series đã ghi. `price_fetcher` injectable để test offline;
    `registry` override để test dùng code không đụng dữ liệu thật.
    Symbol không có dữ liệu (fetcher trả None) được bỏ qua, không raise.
    """
    symbol_map = symbol_map or YF_SYMBOL_TO_CODE
    points: list[MacroPoint] = []
    for symbol, code in symbol_map.items():
        pp = price_fetcher(symbol)
        if pp is None:
            continue
        trade_date, value = pp
        points.append(MacroPoint(code, trade_date, value, source="yfinance"))

    if not points:
        return 0
    return upsert_macro_series(points, db, registry=registry)
