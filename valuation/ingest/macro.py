"""Ingest dữ liệu vĩ mô từ CSV (TPCP_10Y, CPI, GDP... — nguồn không có API).

CSV format: indicator_code, date, value, source
Ghi qua `upsert_macro_series` → idempotent + validate registry (Luật vàng #5, #6).
"""
import datetime

import pandas as pd
from sqlalchemy.orm import Session

from valuation.db.session import SessionLocalWrite
from valuation.ingest.macro_store import MacroPoint, upsert_macro_series


def ingest_macro_csv(file_path: str, db: Session = None) -> int:
    """Ingest macro từ CSV. Trả về số bản ghi đã ghi/cập nhật.

    Không nuốt lỗi: series_code lạ / CSV sai định dạng sẽ raise rõ ràng.
    """
    close_db = False
    if db is None:
        db = SessionLocalWrite()
        close_db = True

    try:
        df = pd.read_csv(file_path)
        points = [
            MacroPoint(
                indicator_code=str(row["indicator_code"]),
                date=pd.to_datetime(row["date"]).date(),
                value=float(row["value"]),
                source=str(row.get("source", "CSV")),
            )
            for _, row in df.iterrows()
        ]
        n = upsert_macro_series(points, db)
        print(f"Ingested/updated {n} macro records from {file_path}")
        return n
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        ingest_macro_csv(sys.argv[1])
    else:
        print("Usage: python -m valuation.ingest.macro <path_to_csv>")
