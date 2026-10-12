"""Pipeline ingest vĩ mô định kỳ (schedule EOD qua n8n/cron).

Lấy dữ liệu thị trường (FX, hàng hóa) qua yfinance, ghi idempotent vào
macro_series. TPCP_10Y / CPI / GDP đi qua đường CSV riêng
(`valuation.ingest.macro`).
"""
from valuation.db.session import SessionLocalWrite
from valuation.ingest.macro_fetcher import fetch_market_macro


def run_macro_ingestion_pipeline() -> int:
    """Chạy ingest macro thị trường. Trả về số series đã ghi/cập nhật."""
    print("Starting Macro Ingestion Pipeline...")
    db = SessionLocalWrite()
    try:
        n = fetch_market_macro(db)
        print(f"Macro market data: {n} series ghi/cập nhật (yfinance).")
        return n
    finally:
        db.close()


if __name__ == "__main__":
    run_macro_ingestion_pipeline()
