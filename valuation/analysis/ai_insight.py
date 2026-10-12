import logging
from openai import OpenAI
from valuation.config import settings

logger = logging.getLogger(__name__)

def generate_ai_insight(ticker: str, sector: str, close_price: float, fair_value: float, upside: float, flags: list, roe: float, pe: float, pb: float, consensus_target: float) -> str:
    """
    Sử dụng DeepSeek API để phân tích nhanh cơ hội/rủi ro đầu tư và viết nhận định đầu tư ngắn gọn (AI Insight).
    """
    if not settings.deepseek_api_key:
        return "Chưa cấu hình DEEPSEEK_API_KEY trong file .env"

    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com/v1"
    )

    # Format số liệu hiển thị trong prompt
    price_str = f"{close_price:,.0f} VND" if close_price else "N/A"
    fv_str = f"{fair_value:,.0f} VND" if fair_value else "N/A"
    upside_str = f"{upside*100:.1f}%" if upside is not None else "N/A"
    roe_str = f"{roe*100:.1f}%" if roe is not None else "N/A"
    pe_str = f"{pe:.2f}x" if pe is not None else "N/A"
    pb_str = f"{pb:.2f}x" if pb is not None else "N/A"
    consensus_str = f"{consensus_target:,.0f} VND" if consensus_target else "N/A"
    flags_str = ", ".join(flags) if flags else "OK"

    prompt = f"""
    Bạn là một chuyên gia phân tích đầu tư cao cấp chuyên về thị trường chứng khoán Việt Nam.
    Hãy viết nhận định đầu tư vô cùng ngắn gọn (tối đa 2-3 câu, khoảng 100 từ, bằng tiếng Việt) cho cổ phiếu {ticker} thuộc ngành {sector} dựa trên các thông số sau:
    - Thị giá hiện tại: {price_str}
    - Giá trị hợp lý định giá (FV Nhịp nhanh): {fv_str}
    - Mức Upside dự phóng: {upside_str}
    - Định giá của các công ty chứng khoán (Consensus): {consensus_str}
    - Chỉ số tài chính: P/E: {pe_str}, P/B: {pb_str}, ROE: {roe_str}
    - Các cờ cảnh báo rủi ro (QC Flags): {flags_str}

    Yêu cầu nhận định:
    1. Trực diện, sắc bén về mặt tài chính (ví dụ: định giá rẻ/đắt, chất lượng tài chính thế nào dựa trên cờ cảnh báo, có nên đầu tư không).
    2. Không dông dài, không mở bài/kết bài sáo rỗng.
    3. Giọng văn chuyên nghiệp chuẩn quỹ đầu tư.
    """

    try:
        response = client.chat.completions.create(
            # "deepseek-v4-flash" là model suy luận (reasoning) — tiêu tốn số
            # token "suy nghĩ" NGẪU NHIÊN (đo thực tế: 89-1065 token/lần gọi cho
            # cùng 1 prompt) trước khi sinh nội dung. Với max_tokens cố định, đôi
            # khi ăn hết ngân sách vào suy luận → nội dung bị cắt/rỗng → JSON lỗi
            # → exception bị nuốt → fallback im lặng, người dùng thấy "nút không
            # chạy". "deepseek-chat" không suy luận (reasoning_tokens=0), ổn định.
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a professional equity research analyst. Keep your responses extremely concise, structured, and sharp in Vietnamese."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        insight = response.choices[0].message.content.strip()
        # Loại bỏ các dấu xuống dòng để tránh làm hỏng cấu trúc dòng của Google Sheets
        insight = insight.replace("\n", " ").replace("\r", "")
        return insight
    except Exception as e:
        logger.error(f"Error generating AI insight for {ticker}: {e}")
        return f"Lỗi gọi DeepSeek API: {str(e)}"
