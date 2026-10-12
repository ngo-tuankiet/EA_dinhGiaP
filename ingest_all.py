import os
import sys
import time
import json
import logging

sys.path.append(os.getcwd())
from valuation.ingest.pipeline import run_ingest
from valuation.db.models import FinancialsQuarterly
from valuation.db.session import SessionLocalRead

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_ingest_all():
    print("--- Bắt đầu tải dữ liệu mới cho danh mục VN100 ---")
    with open("valuation/config/routing.json", "r", encoding="utf-8") as f:
        routing_data = json.load(f)

    tickers = list(routing_data.keys())
    db = SessionLocalRead()
    try:
        have_financials = {
            row[0] for row in db.query(FinancialsQuarterly.ticker).distinct().all()
        }
    finally:
        db.close()

    success_count = 0
    partial_count = 0
    fail_count = 0

    for i, ticker in enumerate(tickers):
        print(f"[{i+1}/{len(tickers)}] Đang cập nhật dữ liệu cho {ticker}...")
        try:
            result = run_ingest(
                ticker,
                data_types=["prices", "financials"],
                incremental=True,
                include_yearly=ticker not in have_financials,
                include_market_flows=False,
            )
            if result["status"] == "SUCCESS":
                success_count += 1
            elif result["status"] == "PARTIAL":
                partial_count += 1
                logger.warning("%s chỉ cập nhật một phần: %s", ticker, result["errors"])
            else:
                fail_count += 1
                logger.error("%s không cập nhật được: %s", ticker, result["errors"])
            time.sleep(1.5)  # Tránh rate limit của API vnstock
        except Exception as e:
            logger.error(f"Lỗi cập nhật {ticker}: {e}")
            fail_count += 1

    print(
        "--- Hoàn tất tải dữ liệu. "
        f"Đầy đủ: {success_count}, một phần: {partial_count}, "
        f"thất bại: {fail_count}/{len(tickers)} ---"
    )


if __name__ == "__main__":
    run_ingest_all()
