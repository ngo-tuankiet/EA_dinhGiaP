"""
AI Narrative — sinh NHÁP văn bản cho báo cáo định giá (4 phần: luận điểm đầu
tư, tổng quan doanh nghiệp, bối cảnh ngành, rủi ro) từ số liệu thật qua
DeepSeek API.

LUẬT (SPEC PHẦN G): văn bản AI sinh là BẢN NHÁP — mọi đoạn trả ra đều gắn cờ
`ai_generated=True` và template phải hiển thị dấu "Nháp do AI tạo — cần
analyst review". Khi thiếu API key / lỗi mạng → fallback khung gợi ý để
analyst tự viết, KHÔNG chặn việc xuất báo cáo.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

AI_DRAFT_NOTICE = (
    "Nháp do AI tạo từ số liệu định giá — cần analyst review trước khi phát hành."
)

# Khung gợi ý khi chưa sinh báo cáo bằng nút DeepSeek duy nhất.
_FALLBACK = {
    "thesis": (
        "(Analyst tự viết 3–5 luận điểm. Gợi ý: định giá đang rẻ/đắt so với giá "
        "trị nội tại? Động lực tăng trưởng chính? Chất lượng tài sản/biên lợi "
        "nhuận? Yếu tố ngành hỗ trợ?)"
    ),
    "overview": (
        "(Analyst mô tả mô hình kinh doanh: mảng doanh thu chính, vị thế cạnh "
        "tranh, thị phần, chuỗi giá trị.)"
    ),
    "industry": (
        "(Analyst tóm tắt bối cảnh ngành: chu kỳ, cung–cầu, chính sách, driver "
        "vĩ mô liên quan.)"
    ),
    "market_view": (
        "(Analyst nhận định xu hướng giá, khối lượng, dòng tiền và vị thế "
        "cung-cầu; không quy kết thao túng khi chưa có bằng chứng.)"
    ),
    "risks": (
        "(Analyst liệt kê rủi ro: rủi ro ngành/chu kỳ, rủi ro thực thi, rủi ro "
        "giả định định giá — WACC, tăng trưởng terminal.)"
    ),
}


def _build_facts(sections: Dict[str, Any]) -> Dict[str, Any]:
    """Rút gọn số liệu định lượng làm context cho AI (không gửi thừa)."""
    cover = sections.get("cover", {})
    hist = sections.get("historical", {}).get("chart_series", {})
    scenarios = sections.get("scenarios") or {}
    consensus = sections.get("consensus") or {}
    years: List[int] = hist.get("years", [])
    revenue = hist.get("revenue", [])
    net_income = hist.get("net_income", [])
    roe = hist.get("roe", [])

    # GHÉP năm↔giá trị thành 1 bảng để AI KHÔNG gán sai năm (trước đây truyền 2
    # mảng rời → AI ghép nhầm & né số mới). Mỗi dòng là 1 năm đầy đủ chỉ số.
    financials_by_year = []
    for i, y in enumerate(years):
        financials_by_year.append(
            {
                "year": y,
                "revenue": round(revenue[i]) if i < len(revenue) else None,
                "net_income": round(net_income[i]) if i < len(net_income) else None,
                "roe_pct": (
                    round(roe[i] * 100, 1)
                    if i < len(roe) and roe[i] is not None
                    else None
                ),
            }
        )

    latest_year = years[-1] if years else None
    latest = financials_by_year[-1] if financials_by_year else {}

    return {
        "ticker": cover.get("ticker"),
        "sector": cover.get("sector"),
        # Mốc thời gian rõ ràng để AI dùng dữ liệu MỚI NHẤT, không lùi về quá khứ.
        "report_date": datetime.date.today().isoformat(),
        "latest_fiscal_year": latest_year,
        "latest_revenue": latest.get("revenue"),
        "latest_net_income": latest.get("net_income"),
        "latest_roe_pct": latest.get("roe_pct"),
        "current_price_vnd": cover.get("current_price"),
        "target_price_vnd": round(cover.get("target_price", 0)),
        "upside_pct": round(cover.get("upside", 0) * 100, 1),
        "recommendation": cover.get("recommendation"),
        "market_cap_billion_vnd": round(cover.get("market_cap", 0)),
        # Bảng năm↔chỉ số (nguồn sự thật duy nhất cho phần văn bản)
        "financials_by_year": financials_by_year,
        "scenarios": scenarios.get("rows"),
        "consensus_median": consensus.get("consensus_median"),
        "qc_flags": sections.get("flags", []),
    }


def generate_report_narratives(sections: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sinh nháp 5 phần văn bản. Trả về:
      {"thesis": str, "overview": str, "industry": str, "market_view": str, "risks": str,
       "ai_generated": bool}
    """
    from valuation.config import settings

    if not getattr(settings, "deepseek_api_key", None):
        return {**_FALLBACK, "ai_generated": False}

    facts = _build_facts(sections)
    prompt = f"""
Bạn là chuyên gia phân tích cổ phiếu cao cấp của quỹ đầu tư tại Việt Nam.
Viết 4 phần văn bản cho báo cáo định giá, bằng tiếng Việt, giọng chuẩn quỹ.

QUY TẮC BẮT BUỘC VỀ DỮ LIỆU:
- Chỉ dùng số liệu trong JSON dưới đây. TUYỆT ĐỐI KHÔNG dùng kiến thức/trí nhớ
  riêng của bạn về công ty này (số liệu bạn nhớ có thể đã CŨ và sai).
- Năm tài chính mới nhất là {facts.get('latest_fiscal_year')} (báo cáo lập ngày
  {facts.get('report_date')}). PHẢI ưu tiên số liệu năm mới nhất và nêu XU HƯỚNG
  GẦN ĐÂY (ví dụ ROE/biên đang tăng hay giảm ở các năm cuối), không chỉ mô tả
  giai đoạn đầu.
- Khi trích số theo năm, lấy ĐÚNG cặp năm↔giá trị trong "financials_by_year";
  không tự gán năm cho một con số.

Viết 5 phần:
1. "thesis": Luận điểm đầu tư — 3 đến 5 gạch đầu dòng, mỗi ý 1-2 câu, sắc bén,
   trong đó có ít nhất 1 ý về diễn biến/định giá MỚI NHẤT.
2. "overview": Tổng quan doanh nghiệp — 3-4 câu về quy mô & hiệu quả, dùng số
   liệu năm mới nhất ({facts.get('latest_fiscal_year')}) làm mốc chính.
3. "industry": Bối cảnh ngành {facts.get('sector')} tại Việt Nam — 3-4 câu, nêu
   driver chính; thận trọng, không bịa số liệu ngành không có trong data.
4. "market_view": Kỹ thuật, khối lượng, dòng tiền và vị thế cung-cầu; không
   khẳng định thao túng khi không có bằng chứng.
5. "risks": Rủi ro đầu tư — 3 đến 4 gạch đầu dòng, PHẢI gồm rủi ro giả định định
   giá (WACC/terminal growth) và giải thích các cờ QC nếu có; nêu rõ nếu chỉ số
   gần đây suy giảm.

Số liệu (nguồn sự thật DUY NHẤT): {json.dumps(facts, ensure_ascii=False)}

TRẢ VỀ JSON THUẦN đúng schema: {{"thesis": "...", "overview": "...",
"industry": "...", "market_view": "...", "risks": "..."}} — không markdown fence, không lời dẫn.
"""
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.deepseek_api_key, base_url="https://api.deepseek.com/v1"
        )
        response = client.chat.completions.create(
            # "deepseek-chat" — không dùng model suy luận "deepseek-v4-flash":
            # đo thực tế tiêu tốn 89-1065 "reasoning token" NGẪU NHIÊN cho cùng
            # 1 prompt, đôi khi ăn hết max_tokens trước khi kịp sinh JSON trả về
            # → content rỗng/cắt cụt → json.loads lỗi → exception bị nuốt → rơi
            # về fallback im lặng. Đây là nguyên nhân nút "Sinh nháp văn bản AI"
            # thỉnh thoảng không hoạt động mà không báo lỗi gì.
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior equity research analyst. Reply with pure JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        # Chịu lỗi nhẹ: gọt markdown fence nếu model vẫn trả kèm
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("{") : raw.rfind("}") + 1]
        data = json.loads(raw)
        out = {
            k: str(data.get(k) or _FALLBACK[k])
            for k in ("thesis", "overview", "industry", "market_view", "risks")
        }
        return {**out, "ai_generated": True}
    except Exception as e:
        logger.error(
            f"AI narrative thất bại ({type(e).__name__}: {e}) — dùng khung gợi ý."
        )
        return {**_FALLBACK, "ai_generated": False}
