"""CLI nhập CSV vĩ mô chính thống vào macro_series.

Ví dụ:
  # CSV WIDE (date,value) — CPI theo % từ GSO:
  ./venv/bin/python -m scripts.import_macro_csv cpi.csv --code CPI_YOY --percent

  # CSV LONG (date,indicator_code,value) — nhiều chỉ báo 1 file:
  ./venv/bin/python -m scripts.import_macro_csv macro.csv --source SBV --percent

  # TPCP 10Y export từ HNX/VBMA (đã là %):
  ./venv/bin/python -m scripts.import_macro_csv tpcp.csv --code TPCP_10Y --source HNX --percent
"""
import argparse

from valuation.db.session import SessionLocalWrite
from valuation.ingest.import_macro_csv import import_macro_csv


def main() -> None:
    ap = argparse.ArgumentParser(description="Nhập CSV vĩ mô chính thống vào macro_series")
    ap.add_argument("csv_path")
    ap.add_argument("--code", default=None, help="indicator_code cho CSV WIDE (date,value)")
    ap.add_argument("--source", default="manual_csv", help="Nguồn để truy vết (vd GSO/SBV/HNX/VBMA)")
    ap.add_argument("--percent", action="store_true", help="Cột value là % (vd 3.2 = 3.2%)")
    ap.add_argument("--decimal", action="store_true", help="Cột value đã là decimal (vd 0.032)")
    args = ap.parse_args()

    as_percent = True
    if args.decimal:
        as_percent = False
    elif args.percent:
        as_percent = True

    db = SessionLocalWrite()
    try:
        n = import_macro_csv(
            args.csv_path, db,
            indicator_code=args.code, source=args.source, as_percent=as_percent,
        )
        print(f"Đã ghi/cập nhật {n} điểm vĩ mô từ {args.csv_path} (nguồn={args.source}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
