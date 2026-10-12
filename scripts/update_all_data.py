"""
Script cập nhật dữ liệu tài chính & giá mới nhất cho toàn bộ danh mục VN100,
sau đó tái tính toán định giá và xuất báo cáo (CSV + Google Sheets).
"""

import logging
import argparse

# Import DB và pipeline
from valuation.db.session import SessionLocalWrite, SessionLocalRead
from valuation.db.models import FinancialsQuarterly, PricesDaily
from valuation.ingest.pipeline import run_ingest
from sqlalchemy import distinct, func
from valuation.engine.batch import value_all
from valuation.models.macro_env import MacroEnvironment
from valuation.output.gsheets_exporter import (
    build_vn100_dataframe,
    export_vn100_valuations_to_gsheets,
    export_vn100_valuations_to_xlsx,
)
from valuation.config import PROJECT_ROOT, settings
from valuation.ingest.universe import get_vn100_symbols

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("ingest_update")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish-sheets",
        action="store_true",
        help="Chỉ publish sau khi file local đã vượt kiểm tra chất lượng.",
    )
    args = parser.parse_args()

    if settings.vnstock_api_key:
        from vnstock.core import setup_api_key

        setup_api_key(settings.vnstock_api_key)
    print("=" * 60)
    print("1. KHỞI CHẠY CẬP NHẬT DỮ LIỆU TÀI CHÍNH & GIÁ THỊ TRƯỜNG MỚI NHẤT")
    print("=" * 60)

    db_write = SessionLocalWrite()
    try:
        tickers = get_vn100_symbols()
        have_financials = {
            row[0] for row in db_write.query(distinct(FinancialsQuarterly.ticker)).all()
        }
        print(f"-> Tìm thấy {len(tickers)} mã cổ phiếu trong danh mục.")
    finally:
        db_write.close()

    success_count = 0
    partial_count = 0
    fail_count = 0

    for idx, ticker in enumerate(tickers, start=1):
        print(f"[{idx}/{len(tickers)}] Đang cập nhật {ticker}...", end=" ", flush=True)
        try:
            ingest_result = run_ingest(
                ticker,
                ["prices", "financials"],
                incremental=True,
                include_yearly=ticker not in have_financials,
                include_market_flows=False,
            )
            if ingest_result["status"] == "SUCCESS":
                print("OK")
                success_count += 1
            elif ingest_result["status"] == "PARTIAL":
                print(f"MỘT PHẦN: {ingest_result['errors']}")
                partial_count += 1
            else:
                print(f"LỖI: {ingest_result['errors']}")
                fail_count += 1
        except Exception as e:
            print(f"LỖI: {e}")
            fail_count += 1

    print("\n" + "=" * 60)
    print(
        "HOÀN THÀNH INGESTION: "
        f"{success_count} đầy đủ, {partial_count} một phần, {fail_count} thất bại."
    )
    print("=" * 60)

    print("\n2. TÁI TÍNH TOÁN ĐỊNH GIÁ TOÀN BỘ DANH MỤC VN100...")
    db_read = SessionLocalRead()
    try:
        normal_env = MacroEnvironment(inflation_rate=0.03, sbv_stance="Neutral")
        results = value_all(db_read, macro_env=normal_env)
        df = build_vn100_dataframe(results)

        # Xuất CSV
        out_csv = PROJECT_ROOT / "vn100_valuations.csv"
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        out_xlsx = PROJECT_ROOT / "vn100_valuations.xlsx"
        export_vn100_valuations_to_xlsx(results, db_read, out_xlsx)

        ok_val = sum(1 for r in results if "error" not in r)
        print(f"-> Đã tái định giá thành công {ok_val}/{len(results)} mã.")
        print(f"-> Đã lưu kết quả ra file: {out_csv}")
        print(f"-> Đã lưu workbook kiểm toán: {out_xlsx}")

        if args.publish_sheets:
            print("-> Đang đồng bộ kết quả đã kiểm tra lên Google Sheets...")
            res_gsheets = export_vn100_valuations_to_gsheets(
                results, sheet_name="VN100_Valuations"
            )
            print("-> Google Sheets status:", res_gsheets.get("status"))

        # Thống kê tổng hợp báo cáo
        max_price_date = db_read.query(func.max(PricesDaily.trade_date)).scalar()
        max_yr_q = (
            db_read.query(
                FinancialsQuarterly.fiscal_year,
                FinancialsQuarterly.fiscal_quarter,
            )
            .filter(
                FinancialsQuarterly.ticker.in_(tickers),
                FinancialsQuarterly.fiscal_quarter > 0,
            )
            .order_by(
                FinancialsQuarterly.fiscal_year.desc(),
                FinancialsQuarterly.fiscal_quarter.desc(),
            )
            .first()
        )

        print("\n" + "=" * 60)
        print("BÁO CÁO TỔNG HỢP SAU CẬP NHẬT:")
        print(f"- Ngày giá thị trường mới nhất trong DB: {max_price_date}")
        print(f"- Kỳ báo cáo tài chính mới nhất: Năm {max_yr_q[0]} Quý {max_yr_q[1]}")
        print(f"- Tổng số mã trong danh mục: {len(results)}")

        rec_counts = {}
        for r in results:
            rec = r.get("recommendation", "UNKNOWN")
            rec_counts[rec] = rec_counts.get(rec, 0) + 1

        print("- Phân bổ khuyến nghị định giá:")
        for rec, cnt in rec_counts.items():
            print(f"  + {rec}: {cnt} mã")
        print("=" * 60)

    finally:
        db_read.close()


if __name__ == "__main__":
    main()
