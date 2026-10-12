"""
Weekly Auto Updater Module — Tự động cập nhật BCTC, Giá & Báo cáo Định giá CTCK hàng tuần.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from valuation.db.models import FinancialsQuarterly, Ticker
from valuation.ingest.pipeline import run_ingest
from valuation.ingest.scrapers import broker_24hmoney, broker_simplize

logger = logging.getLogger("weekly_updater")

# Nguồn khuyến nghị CTCK, chạy tuần tự. Mỗi nguồn bọc try/except RIÊNG để một
# nguồn chết (đổi HTML, sập API) không làm mất nốt dữ liệu của nguồn kia.
# Simplize bổ sung ~12 CTCK mà 24hmoney không có (FPTS, MAS, BVSC, KIS,
# YUANTA, DSC...) — nhiều mã hiện chỉ có 1-3 CTCK nên median rất nhiễu.
_CONSENSUS_SOURCES = (
    ("24HMONEY", broker_24hmoney.import_broker_reports),
    ("SIMPLIZE", broker_simplize.import_reports),
)


def run_weekly_auto_update(
    db_read: Session,
    db_write: Session = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    max_tickers: int | None = None,
) -> dict[str, Any]:
    """
    Chạy cập nhật dữ liệu hàng tuần cho các mã VN100:
    1. Cập nhật Giá thị trường & Dòng tiền mới nhất.
    2. Cập nhật BCTC Quý/Năm mới nhất.
    3. Crawl Báo cáo & Khuyến nghị mới nhất của các CTCK vào consensus_history.
    """
    logger.info("--- BẮT ĐẦU CẬP NHẬT TỰ ĐỘNG HÀNG TUẦN ---")

    tickers_query = (
        db_read.query(Ticker.ticker)
        .filter(Ticker.is_vn100)
        .order_by(Ticker.ticker.asc())
        .all()
    )
    tickers = [t[0] for t in tickers_query]

    if max_tickers and max_tickers > 0:
        tickers = tickers[:max_tickers]

    total = len(tickers)
    success_count = 0
    partial_count = 0
    fail_count = 0
    have_financials = {
        row[0] for row in db_read.query(distinct(FinancialsQuarterly.ticker)).all()
    }
    consensus_counts: dict[str, int] = {name: 0 for name, _ in _CONSENSUS_SOURCES}
    consensus_errors: list[str] = []

    for idx, ticker in enumerate(tickers, start=1):
        status_msg = f"Đang cập nhật {ticker} ({idx}/{total})..."
        logger.info(status_msg)
        if progress_callback:
            progress_callback(idx, total, status_msg)

        try:
            # 1. Ingest Giá & BCTC
            ingest_result = run_ingest(
                ticker,
                data_types=["prices", "financials"],
                incremental=True,
                include_yearly=ticker not in have_financials,
            )

            # 2. Ingest Báo cáo định giá CTCK — từng nguồn độc lập
            for source_name, importer in _CONSENSUS_SOURCES:
                try:
                    recs = importer(ticker) or []
                    consensus_counts[source_name] += len(recs)
                except Exception as e_broker:
                    msg = f"{source_name}/{ticker}: {e_broker}"
                    logger.warning(f"Lỗi crawl báo cáo CTCK — {msg}")
                    consensus_errors.append(msg)

            if ingest_result["status"] == "SUCCESS":
                success_count += 1
            elif ingest_result["status"] == "PARTIAL":
                partial_count += 1
                logger.warning(
                    "Cập nhật một phần %s: %s",
                    ticker,
                    ingest_result["errors"],
                )
            else:
                fail_count += 1
            time.sleep(1.0)  # Giảm tải cho API server & web scrapers
        except Exception as e:
            logger.error(f"Lỗi cập nhật {ticker}: {e}")
            fail_count += 1

    # VNINDEX có is_vn100=0 nên vòng trên bỏ qua → chuỗi chỉ số từng đứng im (D51).
    vni = run_ingest("VNINDEX", data_types=["prices"], include_market_flows=False)
    if vni["prices"]["status"] != "UPDATED":
        logger.warning("Không cập nhật được VNINDEX: %s", vni["prices"])

    # Sự kiện cổ tức/quyền trước đây chỉ làm mới khi mở từng mã → 85/100 mã đứng ở 30/08 và lịch
    # quyền VN100 thiếu các đợt công bố mới. Theo TTL nên mã vừa kiểm tra không gọi lại nguồn.
    if db_write is not None:
        from valuation.ingest.corporate_actions import backfill_vn100_corporate_actions

        ca = backfill_vn100_corporate_actions(db_write)
        if ca.get("error"):
            logger.warning("Cập nhật sự kiện cổ tức/quyền lỗi %s mã: %s", ca["error"], ca)

    consensus_summary = ", ".join(f"{k}={v}" for k, v in consensus_counts.items())
    summary_msg = (
        f"Hoàn tất cập nhật hàng tuần: {success_count}/{total} mã đầy đủ, "
        f"{partial_count} mã một phần, {fail_count} mã thất bại. "
        f"Khuyến nghị CTCK thu được: {consensus_summary}."
    )
    logger.info(summary_msg)

    return {
        "status": "SUCCESS" if not partial_count and not fail_count else "PARTIAL",
        "total": total,
        "success_count": success_count,
        "partial_count": partial_count,
        "fail_count": fail_count,
        "consensus": {**consensus_counts, "errors": consensus_errors},
        "message": summary_msg,
    }
