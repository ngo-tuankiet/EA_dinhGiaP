"""Lưu luận điểm CÔNG KHAI của báo cáo CTCK + bóc tách tất định (D31).

`broker_24hmoney.fetch_report_summaries()` vốn đã tải đoạn tóm tắt luận điểm của
từng báo cáo, nhưng chỉ dùng tạm cho AI tổng hợp rồi VỨT ĐI. Nghĩa là mỗi lần
muốn tổng hợp lại phải cào lại toàn bộ, và không có cách nào đối chiếu xem CTCK
thực sự giả định gì.

Nguồn: CHỈ trang tóm tắt công khai (24hmoney) và tiêu đề (Simplize).
KHÔNG tải PDF báo cáo gốc — giữ quyết định bản quyền của dự án.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy.dialects.postgresql import insert

from valuation.db.models import ConsensusReportText
from valuation.db.session import SessionLocalWrite
from valuation.engine.consensus_extract import EXTRACT_VERSION, extract_thesis
from valuation.ingest.broker_names import normalize_broker

logger = logging.getLogger(__name__)


def capture_report_texts(ticker: str, timeout: float = 20.0) -> List[Dict[str, Any]]:
    """Gom luận điểm công khai từ mọi nguồn cho 1 mã. KHÔNG ghi DB."""
    out: List[Dict[str, Any]] = []

    # --- 24hmoney: đoạn tóm tắt luận điểm (nguồn giàu thông tin nhất) ---
    try:
        from valuation.ingest.scrapers.broker_24hmoney import fetch_report_summaries
        for r in fetch_report_summaries(ticker, timeout=timeout):
            canon, _ = normalize_broker(r["broker"])
            out.append({
                "ticker": ticker.upper(), "broker_canon": canon,
                "report_date": r["report_date"], "source_site": "24HMONEY",
                "detail_url": r.get("detail_url"), "title": r.get("title"),
                "summary_text": r.get("summary") or "",
            })
    except Exception as e:
        logger.warning("24hmoney text %s: %s", ticker, e)

    # --- Simplize: chỉ có tiêu đề, nhưng GIỮ CẢ báo cáo không có giá mục tiêu
    # (báo cáo ngành/chiến lược bị loại khỏi consensus_history vì median cần giá
    # mục tiêu, song ngôn ngữ phương pháp trong đó vẫn có giá trị).
    try:
        from valuation.ingest.scrapers.broker_simplize import fetch_reports
        for r in fetch_reports(ticker):
            canon, _ = normalize_broker(r["broker"])
            out.append({
                "ticker": ticker.upper(), "broker_canon": canon,
                "report_date": r["report_date"], "source_site": "SIMPLIZE",
                "detail_url": r.get("source_url"), "title": r.get("report_title"),
                "summary_text": r.get("report_title") or "",
            })
    except Exception as e:
        logger.warning("simplize text %s: %s", ticker, e)

    return out


def import_report_texts(ticker: str, timeout: float = 20.0) -> int:
    """Lấy + ghi luận điểm và kết quả bóc tách (idempotent theo khoá chính)."""
    rows = capture_report_texts(ticker, timeout=timeout)
    if not rows:
        return 0

    db = SessionLocalWrite()
    n = 0
    try:
        for r in rows:
            if not r.get("summary_text"):
                continue
            extracted = extract_thesis(r["summary_text"]).to_dict()
            stmt = insert(ConsensusReportText).values(
                **r, extracted=extracted, extract_version=EXTRACT_VERSION
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker", "broker_canon", "report_date", "source_site"],
                set_={
                    "detail_url": stmt.excluded.detail_url,
                    "title": stmt.excluded.title,
                    "summary_text": stmt.excluded.summary_text,
                    "extracted": stmt.excluded.extracted,
                    "extract_version": stmt.excluded.extract_version,
                },
            )
            db.execute(stmt)
            n += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return n


def coverage_report(db, ticker: str | None = None) -> Dict[str, Any]:
    """Đếm tỷ lệ bóc được từng trường — để báo cáo nói "6/11 CTCK nêu P/B"
    thay vì bịa một giá trị trung bình từ dữ liệu thiếu."""
    q = db.query(ConsensusReportText)
    if ticker:
        q = q.filter(ConsensusReportText.ticker == ticker.upper())
    rows = q.all()
    total = len(rows)
    fields = ("target_pb", "target_pe", "forecast_roe", "target_price",
              "forecast_net_income_ty", "forecast_growth", "wacc")
    counts = {f: 0 for f in fields}
    counts["methods"] = 0
    for r in rows:
        ex = r.extracted or {}
        for f in fields:
            if ex.get(f) is not None:
                counts[f] += 1
        if ex.get("methods"):
            counts["methods"] += 1
    return {"n_reports": total,
            "counts": counts,
            "rates": {k: (v / total if total else 0.0) for k, v in counts.items()}}
