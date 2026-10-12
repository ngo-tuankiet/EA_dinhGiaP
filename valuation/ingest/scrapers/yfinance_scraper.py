"""DEPRECATED — giữ để tương thích ngược.

Logic cũ dùng `add_all` không idempotent và series_code không khớp registry
(EXCHANGE_RATE/CRUDE_OIL). Đã thay bằng `valuation.ingest.macro_fetcher`
(idempotent UPSERT + validate registry). File này chỉ delegate.
"""
from sqlalchemy.orm import Session

from valuation.ingest.macro_fetcher import fetch_market_macro


def fetch_yfinance_macro(db: Session = None) -> int:
    """Đã thay thế bởi macro_fetcher.fetch_market_macro. Delegate."""
    from valuation.db.session import SessionLocalWrite

    close_db = False
    if db is None:
        db = SessionLocalWrite()
        close_db = True
    try:
        return fetch_market_macro(db)
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    fetch_yfinance_macro()
