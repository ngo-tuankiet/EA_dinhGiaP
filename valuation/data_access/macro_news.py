import os
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Bản tin vĩ mô được lưu ra file kèm timestamp để tồn tại QUA CÁC LẦN RESTART app
# (st.cache_data chỉ nằm trong RAM, mất khi restart → tốn token gọi lại AI mỗi lần).
_MACRO_CACHE_FILE = Path(__file__).resolve().parents[2] / ".macro_bulletin_cache.json"
# Đổi khi đổi prompt: tin không đổi vẫn phải viết lại theo định dạng mới (vd thêm dòng TAGS, D51).
_PROMPT_VERSION = "d51"
_TAGS_PREFIX = "TAGS:"
_MAX_TAGS = 8


def split_news_tags(text: str, allowed: set[str]) -> tuple[str, dict[str, list[str]] | None]:
    """Tách dòng TAGS (máy đọc) khỏi bản tin. Chỉ giữ mã/ngành trong whitelist — AI không được
    bịa mã, và nội dung tin (dữ liệu ngoài) không thể chèn chữ tùy ý vào giao diện."""
    body, sep, raw = text.partition(_TAGS_PREFIX)
    body = body.split("**🎲")[0].strip()  # bản lưu cũ còn mục 'dòng tiền/nhà cái' dài (D50)
    if not sep:
        return body, None
    try:
        data = json.loads(raw.strip().splitlines()[0].strip("` "))
    except (ValueError, IndexError) as exc:
        logger.warning("Dòng TAGS của bản tin không phải JSON hợp lệ: %s", exc)
        data = {}
    tags: dict[str, list[str]] = {}
    for key in ("tich_cuc", "tieu_cuc"):
        items = data.get(key, []) if isinstance(data, dict) else []
        clean = (x.strip() for x in items if isinstance(x, str))
        tags[key] = [x for x in dict.fromkeys(clean) if x in allowed][:_MAX_TAGS]
    return body, tags


def _allowed_tags() -> tuple[list[str], list[str]]:
    """(mã VN100, tên ngành) được phép xuất hiện trong dòng TAGS."""
    from valuation.db.models import Ticker
    from valuation.db.session import SessionLocalRead
    from valuation.views.market_overview import sector_map

    db = SessionLocalRead()
    try:
        tickers = sorted(t for (t,) in db.query(Ticker.ticker).filter(Ticker.is_vn100))
    finally:
        db.close()
    return tickers, sorted(set(sector_map().values()) - {"Chưa rõ"})


def latest_news_tags() -> dict[str, list[str]] | None:
    """Nhãn tin của bản tin đang lưu; None nếu bản lưu chưa có dòng TAGS (chưa làm mới)."""
    if not _MACRO_CACHE_FILE.exists():
        return None
    text = json.loads(_MACRO_CACHE_FILE.read_text(encoding="utf-8")).get("text") or ""
    if _TAGS_PREFIX not in text:
        return None
    tickers, sectors = _allowed_tags()
    return split_news_tags(text, set(tickers) | set(sectors))[1]


def get_macro_bulletin_cached(force: bool = False) -> str:
    """Đọc thường không gọi mạng/AI; chỉ nút làm mới kiểm tra tin thay đổi."""
    now = time.time()
    data = {}
    if _MACRO_CACHE_FILE.exists():
        try:
            data = json.loads(_MACRO_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Không đọc được cache bản tin vĩ mô: {e}")

    if not force:
        return data.get("text") or "Chưa có bản tin vĩ mô được lưu."

    news_text = fetch_rss_news()
    if not news_text:
        if data.get("text"):
            return data["text"]
        return "⚠️ Không thể lấy được bản tin Vĩ mô lúc này. Vui lòng thử lại sau."
    source_hash = hashlib.sha256((_PROMPT_VERSION + news_text).encode("utf-8")).hexdigest()
    if data.get("text") and data.get("source_hash") == source_hash:
        data["checked_at"] = now
        try:
            _MACRO_CACHE_FILE.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Không gia hạn được cache bản tin vĩ mô: {e}")
        return data["text"]

    text = generate_macro_bulletin(news_text=news_text)

    # Chỉ lưu khi tạo thành công (không lưu thông báo lỗi để lần sau còn thử lại)
    if text and not text.startswith("⚠️"):
        try:
            _MACRO_CACHE_FILE.write_text(
                json.dumps(
                    {"ts": now, "text": text, "source_hash": source_hash},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Không ghi được cache bản tin vĩ mô: {e}")
    return text


def get_macro_cache_age_hours() -> float | None:
    """Tuổi (giờ) của bản tin đang lưu; None nếu chưa có."""
    if not _MACRO_CACHE_FILE.exists():
        return None
    try:
        data = json.loads(_MACRO_CACHE_FILE.read_text(encoding="utf-8"))
        return (time.time() - float(data.get("ts", 0))) / 3600.0
    except Exception:
        return None

def fetch_rss_news():
    urls = [
        "https://cafef.vn/vi-mo-dau-tu.rss",
        "https://cafef.vn/tai-chinh-quoc-te.rss"
    ]
    news_items = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "xml")
                items = soup.find_all("item")
                # Lấy 10 tin mới nhất mỗi nguồn
                for item in items[:10]:
                    title = item.find("title").text if item.find("title") else ""
                    description = item.find("description").text if item.find("description") else ""
                    
                    # Clean CDATA and HTML from description if any
                    desc_soup = BeautifulSoup(description, "html.parser")
                    clean_desc = desc_soup.get_text(separator=" ").strip()
                    
                    if title:
                        news_items.append(f"Tiêu đề: {title}\nNội dung tóm tắt: {clean_desc}")
        except Exception as e:
            logger.error(f"Error fetching RSS {url}: {e}")
            
    return "\n\n".join(news_items)

def get_openai_client() -> OpenAI | None:
    """Trả client AI; None nếu chưa cấu hình API key.

    Trả None thay vì để OpenAI(api_key=None) ném OpenAIError: bản tin vĩ mô chỉ là
    tính năng phụ, thiếu key thì tắt riêng nó, KHÔNG được kéo sập cả app định giá.
    """
    from valuation.config import settings
    api_key = settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY") # fallback
    if not api_key:
        return None
    if api_key.startswith("sk-"):
        # if using deepseek
        return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    return OpenAI(api_key=api_key)

def _panel_numbers_text() -> str:
    """Số liệu của khung 'Chỉ số vĩ mô' (macro_series) để bản tin AI không nói trái số liệu."""
    try:
        from valuation.config import get_macro_series_registry, load_defaults
        from valuation.db.session import SessionLocalRead
        from valuation.views.macro_panel import PANEL, _fmt_value, build_snapshot

        db = SessionLocalRead()
        try:
            freqs = {k: v.get("frequency", "DAILY") for k, v in get_macro_series_registry().items()}
            snap = build_snapshot(db, load_defaults().get("macro_dashboard") or {}, freqs)
        finally:
            db.close()
        return "\n".join(
            f"- {label}: {_fmt_value(snap[code], kind)[0]} ({snap[code].date:%d/%m/%Y})"
            for code, label, kind in PANEL if code in snap
        ) or "- (chưa có)"
    # Bản tin vẫn chạy khi DB vĩ mô lỗi — ghi warning rõ thay vì im lặng.
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không đọc được số liệu vĩ mô cho bản tin: %s", exc)
        return "- (không đọc được số liệu bảng)"


def _tag_lists_text() -> str:
    try:
        tickers, sectors = _allowed_tags()
    # Bản tin vẫn chạy khi DB lỗi — ghi warning; không có danh sách thì AI trả [].
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không đọc được danh sách mã/ngành cho dòng TAGS: %s", exc)
        return "- (không có danh sách — để [])"
    return f"- Mã VN100: {', '.join(tickers)}\n- Ngành: {', '.join(sectors)}"


def generate_macro_bulletin(news_text: str | None = None) -> str:
    # Kiểm tra key TRƯỚC khi tải RSS để khỏi tốn request mạng vô ích.
    client = get_openai_client()
    if client is None:
        return (
            "⚠️ Chưa cấu hình API key cho AI (`DEEPSEEK_API_KEY` hoặc `OPENAI_API_KEY` "
            "trong `.env`). Bản tin vĩ mô tạm nghỉ — các chức năng định giá khác vẫn "
            "chạy bình thường."
        )

    news_text = news_text or fetch_rss_news()
    if not news_text:
        return "⚠️ Không thể lấy được bản tin Vĩ mô lúc này. Vui lòng thử lại sau."

    prompt = f"""Bạn là chuyên gia vĩ mô cho nhà đầu tư chứng khoán Việt Nam.
Tin tức 24h qua:

{news_text}

Số liệu chính thức đang hiển thị trên bảng chỉ số (ưu tiên, KHÔNG được nói trái các số này):
{_panel_numbers_text()}

Viết BẢN TIN VĨ MÔ cực ngắn (đọc trong 15 giây), Markdown, đúng 3 phần, tiêu đề chỉ in đậm:

**🇻🇳 Việt Nam**
- tối đa 2 gạch

**🌍 Thế giới**
- tối đa 2 gạch (Fed, lợi suất Mỹ, USD, dầu, địa chính trị)

**💡 Tác động thị trường**
- 1–2 gạch: nhóm ngành hưởng lợi / chịu áp lực và vì sao

Quy tắc: mỗi gạch ≤ 20 từ, có con số nếu tin có; bỏ tin không ảnh hưởng thị trường chứng khoán;
không nhắc lại số liệu đã có trên bảng trừ khi có diễn biến mới; không bịa; không khuyên mua/bán.

Dòng CUỐI CÙNG (máy đọc, người dùng không thấy), đúng một dòng JSON:
TAGS: {{"tich_cuc": [...], "tieu_cuc": [...]}}
Chỉ ghi mã hoặc ngành được TIN Ở TRÊN nhắc trực tiếp là có lợi / bất lợi; không có thì để [].
Chỉ dùng đúng tên trong 2 danh sách sau:
{_tag_lists_text()}
"""

    try:
        response = client.chat.completions.create(
            # "deepseek-chat" (không phải "deepseek-v4-flash" — model suy luận,
            # tốn token "suy nghĩ" ngẫu nhiên, đôi khi cắt cụt nội dung trước khi
            # kịp trả lời; xem valuation/analysis/ai_insight.py).
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a top-tier macroeconomic analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=700,  # +100 cho dòng TAGS (D51)
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Lỗi AI macro_news: {e}")
        return f"⚠️ Lỗi khi gọi AI tổng hợp tin tức: {e}"
