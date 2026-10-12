"""
GĐ2 — AI tổng hợp đa-CTCK: điểm chung / điểm riêng / điểm mấu chốt cho mỗi mã.

Quy trình:
  1. Bóc tóm tắt luận điểm từng báo cáo CTCK (broker_24hmoney.fetch_report_summaries).
  2. Dựng quan điểm mô hình nội bộ VN100 (fair value + khuyến nghị).
  3. Gửi DeepSeek tổng hợp -> JSON (diem_chung/diem_rieng/diem_mau_chot/doi_chieu_noi_bo).
  4. Lưu bảng consensus_synthesis (idempotent theo ticker).

NGUYÊN TẮC: chỉ tổng hợp từ tóm tắt công khai; không phát tán PDF gốc; không bịa số.
"""
from __future__ import annotations

import json
import statistics
from typing import Any, Dict, List, Optional

from openai import OpenAI
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import func

from valuation.config import settings
from valuation.db.models import ConsensusSynthesis
from valuation.db.session import SessionLocalWrite
from valuation.ingest.scrapers.broker_24hmoney import fetch_report_summaries

# "deepseek-chat" — không dùng model suy luận "deepseek-v4-flash" vì tốn token
# "suy nghĩ" ngẫu nhiên, đôi khi cắt cụt JSON (xem valuation/analysis/ai_insight.py).
_MODEL = "deepseek-chat"
_KEYS = ("diem_chung", "diem_rieng", "diem_mau_chot", "doi_chieu_noi_bo")


def _internal_view(ticker: str, db) -> Optional[Dict[str, Any]]:
    """Quan điểm mô hình nội bộ VN100 cho 1 mã (fair value, upside, khuyến nghị)."""
    # import cục bộ: tránh kéo nặng khi chỉ test lớp tổng hợp
    from valuation.data_access.repo import build_company_data
    from valuation.engine.valuate import valuate
    try:
        c = build_company_data(db, ticker, "TTM")
        r = valuate(c)
        fv = r["blended_fair_value_per_share"]
        price = c.current_price
        return {
            "fair_value": round(float(fv)),
            "price": round(float(price)) if price else None,
            "upside_pct": round((fv / price - 1) * 100, 1) if price else None,
            "recommendation": r["recommendation"],
        }
    except Exception:
        return None


def _build_prompt(ticker: str, summaries: List[Dict[str, Any]],
                  internal: Optional[Dict[str, Any]]) -> str:
    blocks = "\n\n".join(
        f"### {s['broker']} ({s['report_date']})\n{s['summary']}" for s in summaries
    )
    if internal and internal.get("price"):
        iv = (f"MÔ HÌNH NỘI BỘ (VN100): fair value {internal['fair_value']:,} đ, "
              f"thị giá {internal['price']:,} đ, upside {internal['upside_pct']}%, "
              f"khuyến nghị {internal['recommendation']}.")
    else:
        iv = "MÔ HÌNH NỘI BỘ (VN100): không có dữ liệu định giá."
    return f"""Bạn là chuyên viên phân tích quỹ đầu tư. Dưới đây là {len(summaries)} báo cáo \
khuyến nghị của các công ty chứng khoán (CTCK) cho mã {ticker}, kèm quan điểm mô hình định giá nội bộ.

CÁC BÁO CÁO CTCK:
{blocks}

{iv}

Trả về DUY NHẤT một JSON tiếng Việt với đúng các khóa sau:
- "diem_chung": mảng 3-4 chuỗi — luận điểm CHUNG mà đa số CTCK đồng thuận.
- "diem_rieng": mảng 2-4 chuỗi — điểm KHÁC BIỆT giữa các CTCK (giá mục tiêu/giả định/rủi ro), nêu rõ CTCK nào.
- "diem_mau_chot": mảng 2-3 chuỗi — nhận định SÂU nhất (động lực chính, điều thị trường có thể bỏ sót).
- "doi_chieu_noi_bo": 1-2 câu (chuỗi) so sánh mô hình VN100 với đồng thuận CTCK (cao/thấp hơn và vì sao có thể khác).

Chỉ dùng thông tin có trong các báo cáo trên; không bịa số."""


def synthesize_from_summaries(ticker: str, summaries: List[Dict[str, Any]],
                              internal: Optional[Dict[str, Any]] = None,
                              client: Optional[OpenAI] = None) -> Dict[str, Any]:
    """Gọi DeepSeek tổng hợp từ danh sách tóm tắt cho sẵn (lớp thuần, dễ test)."""
    if not summaries:
        return {}
    if client is None:
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY chưa được cấu hình.")
        client = OpenAI(api_key=settings.deepseek_api_key,
                        base_url="https://api.deepseek.com/v1")
    resp = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": _build_prompt(ticker, summaries, internal)}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    data = json.loads(resp.choices[0].message.content)
    # chuẩn hóa: list cho 3 khóa mảng, str cho đối chiếu
    for k in ("diem_chung", "diem_rieng", "diem_mau_chot"):
        v = data.get(k)
        data[k] = v if isinstance(v, list) else ([v] if v else [])
    data["doi_chieu_noi_bo"] = str(data.get("doi_chieu_noi_bo") or "")
    return data


def synthesize_ticker(ticker: str, db=None, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    """Lấy tóm tắt + quan điểm nội bộ + DeepSeek tổng hợp cho 1 mã. KHÔNG ghi DB."""
    ticker = ticker.upper()
    summaries = fetch_report_summaries(ticker, timeout=timeout)
    if not summaries:
        return None
    close_db = False
    if db is None:
        from valuation.db.session import SessionLocalRead
        db = SessionLocalRead()
        close_db = True
    try:
        internal = _internal_view(ticker, db)
    finally:
        if close_db:
            db.close()
    synth = synthesize_from_summaries(ticker, summaries, internal)
    if not synth:
        return None
    tps = [s["target_price"] for s in summaries if s.get("target_price")]
    return {
        "ticker": ticker,
        "n_reports": len(summaries),
        "brokers": ", ".join(dict.fromkeys(s["broker"] for s in summaries)),
        "diem_chung": synth.get("diem_chung", []),
        "diem_rieng": synth.get("diem_rieng", []),
        "diem_mau_chot": synth.get("diem_mau_chot", []),
        "doi_chieu_noi_bo": synth.get("doi_chieu_noi_bo", ""),
        "internal_fv": internal["fair_value"] if internal else None,
        "consensus_median": round(statistics.median(tps)) if tps else None,
        "model": _MODEL,
    }


def import_synthesis(ticker: str, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    """Tổng hợp + ghi consensus_synthesis (upsert theo ticker)."""
    rec = synthesize_ticker(ticker, timeout=timeout)
    if not rec:
        return None
    db = SessionLocalWrite()
    try:
        stmt = insert(ConsensusSynthesis).values(**rec, generated_at=func.now())
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker"],
            set_={k: getattr(stmt.excluded, k) for k in (
                "n_reports", "brokers", "diem_chung", "diem_rieng", "diem_mau_chot",
                "doi_chieu_noi_bo", "internal_fv", "consensus_median", "model",
                "generated_at")},
        )
        db.execute(stmt)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return rec
