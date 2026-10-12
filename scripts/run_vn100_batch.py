"""Định giá batch toàn VN100 hiện hành → CSV + XLSX, tùy chọn Google Sheets.

Chỉ định giá mã đã có dữ liệu trong DB; mã thiếu data → cột Cờ ghi lý do.
  ./venv/bin/python -m scripts.run_vn100_batch
"""
from valuation.db.session import SessionLocalRead
import argparse

from valuation.engine.batch import value_all
from valuation.ingest.universe import get_vn100_symbols
from valuation.output.gsheets_exporter import (
    build_vn100_dataframe,
    export_vn100_valuations_to_gsheets,
    export_vn100_valuations_to_xlsx,
)
from valuation.config import PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-sheets", action="store_true")
    args = parser.parse_args()

    db = SessionLocalRead()
    try:
        symbols = get_vn100_symbols()
        results = value_all(db, symbols)
        df = build_vn100_dataframe(results)

        out_csv = PROJECT_ROOT / "vn100_valuations.csv"
        out_xlsx = PROJECT_ROOT / "vn100_valuations.xlsx"
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        export_vn100_valuations_to_xlsx(results, db, out_xlsx)
        ok = sum(1 for r in results if "error" not in r)
        print(f"Đã định giá {ok}/{len(symbols)} mã → {out_csv}")
        print(f"Workbook kiểm toán → {out_xlsx}")

        if args.publish_sheets:
            res = export_vn100_valuations_to_gsheets(results)
            print("Google Sheets:", res.get("status"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
