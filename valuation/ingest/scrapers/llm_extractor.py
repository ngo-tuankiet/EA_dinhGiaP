import json
from typing import Dict, Any
from openai import OpenAI
from valuation.config import settings

def extract_macro_from_text(text: str, indicator_name: str) -> Dict[str, Any]:
    """
    Sử dụng LLM (DeepSeek) để trích xuất số liệu vĩ mô từ một đoạn văn bản thô.
    """
    if not settings.deepseek_api_key:
        print("Warning: DEEPSEEK_API_KEY is not set. Cannot run LLM extractor.")
        return {}

    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com/v1"
    )

    prompt = f"""
    Bạn là một chuyên gia dữ liệu tài chính.
    Đọc đoạn văn bản dưới đây và trích xuất giá trị mới nhất của chỉ báo: "{indicator_name}".
    Chỉ trả về ĐÚNG MỘT JSON object hợp lệ, không kèm giải thích hay text nào khác.
    Format JSON bắt buộc:
    {{
        "value": <float, ví dụ 0.05 đại diện cho 5%>,
        "date": <string, định dạng YYYY-MM-DD nếu có, hoặc để null nếu không xác định được>
    }}
    Nếu không tìm thấy thông tin, trả về: {{"value": null, "date": null}}
    
    --- VĂN BẢN ---
    {text}
    """

    try:
        response = client.chat.completions.create(
            # "deepseek-chat" — không dùng model suy luận "deepseek-v4-flash" vì
            # tốn token "suy nghĩ" ngẫu nhiên, đôi khi cắt cụt JSON trước khi kịp
            # trả lời (xem valuation/analysis/ai_insight.py).
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a helpful financial data extraction assistant. Always respond in pure JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        return data
        
    except Exception as e:
        print(f"Error extracting data with LLM: {e}")
        return {}

if __name__ == "__main__":
    sample_text = "Ngân hàng Nhà nước cho biết tăng trưởng tín dụng tính đến cuối tháng 5/2024 đã đạt 5.4%, cao hơn so với mức 3.2% của cùng kỳ năm ngoái."
    print("Testing LLM Extractor with sample text...")
    result = extract_macro_from_text(sample_text, "Tăng trưởng tín dụng từ đầu năm")
    print(f"Extraction result: {result}")
