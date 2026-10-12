"""Gọi DeepSeek Chat API để sinh nhận định tiếng Việt cho báo cáo Discord.

Dùng httpx đồng bộ (không phải AsyncClient) để hàm này gọi được cả từ
background task đồng bộ (FastAPI BackgroundTasks) lẫn từ code async (Discord
bot, qua asyncio.to_thread) mà không cần quản lý 2 event loop khác nhau.
"""
import logging
import httpx
from valuation.config import settings

logger = logging.getLogger(__name__)

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def call_deepseek_sync(prompt: str, max_tokens: int = 1200, temperature: float = 0.3) -> str:
    if not settings.deepseek_api_key:
        return "⚠️ Không tìm thấy DEEPSEEK_API_KEY trong cấu hình. Không thể tạo nhận định AI."

    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        # "deepseek-chat" — không dùng model suy luận "deepseek-v4-flash" vì tốn
        # token "suy nghĩ" ngẫu nhiên, đôi khi cắt cụt nội dung (xem
        # valuation/analysis/ai_insight.py).
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(DEEPSEEK_URL, headers=headers, json=payload)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            logger.error(f"DeepSeek API error {response.status_code}: {response.text}")
            return f"⚠️ Lỗi khi gọi DeepSeek API (Mã lỗi: {response.status_code})."
    except Exception as e:
        logger.error(f"DeepSeek exception: {e}")
        return f"⚠️ Lỗi kết nối tới DeepSeek: {str(e)}"
