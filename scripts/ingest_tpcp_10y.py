"""Ingest TPCP_10Y từ file investing.com (Vietnam 10-Year Bond Yield).

Format nguồn: "Date"(MM/DD/YYYY), "Price"(% lợi suất), ...
Chuẩn hóa: value = Price/100 (decimal_rate theo registry), ghi idempotent.

Chạy: ./venv/bin/python -m scripts.ingest_tpcp_10y <csv_path>
"""
import sys

import pandas as pd

from valuation.db.session import SessionLocalWrite
from valuation.ingest.macro_store import MacroPoint, upsert_macro_series


def main(csv_path: str) -> None:
    df = pd.read_csv(csv_path)
    points = [
        MacroPoint(
            indicator_code="TPCP_10Y",
            date=pd.to_datetime(row["Date"], format="%m/%d/%Y").date(),
            value=float(row["Price"]) / 100.0,  # % -> decimal_rate
            source="investing.com",
        )
        for _, row in df.iterrows()
    ]
    db = SessionLocalWrite()
    try:
        n = upsert_macro_series(points, db)
        print(f"TPCP_10Y: ghi/cập nhật {n} điểm.")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1])
