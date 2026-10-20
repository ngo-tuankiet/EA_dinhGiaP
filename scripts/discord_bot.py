"""Bot Discord chiều Discord → Python: định giá 1 mã VN100 và lệnh !baocao.

Chỉ nhận lệnh trong DISCORD_CHANNEL_ID (.env); mọi thành viên kênh dùng được, trừ khi đặt
DISCORD_OWNER_ID để khóa về 1 người. Gọi thẳng engine định giá
(không cần FastAPI). Chạy nền bằng launchd: ~/Library/LaunchAgents/vn.antigravity-vn100.discord-bot.plist
"""
import asyncio
import datetime
import logging
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import certifi
import discord
from fastapi import HTTPException

from valuation.config import settings
from valuation.engine.flag_descriptions import describe_flags
from valuation.output.ai_insight import call_deepseek_sync

# Đảm bảo chứng chỉ SSL sử dụng Certifi bundle để tránh lỗi trên macOS
os.environ["SSL_CERT_FILE"] = certifi.where()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Khởi tạo Discord client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Đọc token và cấu hình từ Settings
DISCORD_TOKEN = settings.discord_bot_token or os.getenv("DISCORD_BOT_TOKEN")


def _id(raw: str) -> int | None:
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


OWNER_ID = _id(settings.discord_owner_id)
CHANNEL_ID = _id(settings.discord_channel_id)
VN100: set[str] = set()  # nạp từ DB lúc khởi động; mã ngoài rổ bị bỏ qua


def is_authorized(
    author_id: int, author_is_bot: bool, channel_id: int, owner_id: int | None, allowed_channel: int | None
) -> bool:
    """Đúng kênh, không phải bot; nếu đặt owner_id thì chỉ người đó. Thiếu kênh = từ chối hết."""
    if author_is_bot or allowed_channel is None or channel_id != allowed_channel:
        return False
    return owner_id is None or author_id == owner_id


def load_universe() -> set[str]:
    from valuation.db.models import Ticker
    from valuation.db.session import SessionLocalRead

    db = SessionLocalRead()
    try:
        return {t for (t,) in db.query(Ticker.ticker).filter(Ticker.is_vn100)}
    finally:
        db.close()


def fetch_report(ticker: str) -> dict:
    """Cùng engine thống nhất với Streamlit/batch, gọi trực tiếp thay vì qua FastAPI."""
    from valuation.api.routes.valuation import unified_report
    from valuation.db.session import SessionLocalRead

    db = SessionLocalRead()
    try:
        return unified_report(ticker, db)
    finally:
        db.close()

_FLAG_ICON = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}


def build_ticker_report_prompt(ticker, price, fv, upside, method_label, flag_infos,
                               recommendation=None, business_nature=None, target_mos=None,
                               intrinsic_fv=None, relative_fv=None) -> str:
    flags_text = "Không có cảnh báo đáng chú ý."
    if flag_infos:
        flags_text = " ".join(f"[{f['level'].upper()}] {f['message']}" for f in flag_infos)

    # So sánh 2 phương pháp: nội tại (DCF) vs so sánh (multiples). Chênh lệch lớn => rủi ro phương pháp.
    method_divergence = ""
    if intrinsic_fv and relative_fv and relative_fv > 0:
        gap = abs(intrinsic_fv - relative_fv) / relative_fv
        if gap > 0.20:
            method_divergence = (
                f"- Lưu ý: hai phương pháp cho kết quả lệch nhau khá lớn "
                f"(giá trị nội tại {intrinsic_fv:,.0f} VND vs giá trị so sánh {relative_fv:,.0f} VND) "
                f"→ độ chắc chắn của định giá thấp hơn, phụ thuộc nhiều vào giả định.\n"
            )
        else:
            method_divergence = (
                f"- Hai phương pháp (nội tại {intrinsic_fv:,.0f} VND và so sánh {relative_fv:,.0f} VND) "
                f"cho kết quả khá đồng thuận → củng cố độ tin cậy của định giá.\n"
            )

    nature_line = ""
    if business_nature:
        nature_map = {
            "Cyclical": "doanh nghiệp CHU KỲ (lợi nhuận biến động mạnh theo chu kỳ ngành/giá hàng hóa)",
            "Stable": "doanh nghiệp ỔN ĐỊNH (dòng tiền/lợi nhuận tương đối đều)",
            "Growth": "doanh nghiệp TĂNG TRƯỞNG (kỳ vọng mở rộng nhanh)",
        }
        nature_line = f"- Bản chất kinh doanh: {nature_map.get(business_nature, business_nature)}\n"

    mos_line = ""
    if target_mos is not None:
        mos_line = f"- Biên an toàn mục tiêu hệ thống áp cho nhóm này: {target_mos*100:.0f}%\n"

    rec_line = f"- Khuyến nghị của hệ thống định giá: {recommendation}\n" if recommendation else ""

    # Chỉ viết mục cảnh báo khi THỰC SỰ có cờ (warning/error). Không có cờ => bỏ hẳn, không viết dòng "không có cảnh báo".
    meaningful_flags = [f for f in (flag_infos or []) if f.get("level") in ("warning", "error")]
    if meaningful_flags:
        flags_text = " ".join(f"[{f['level'].upper()}] {f['message']}" for f in meaningful_flags)
        flags_section_instruction = (
            "\n**🔎 Điểm cần soi kỹ** — Nêu ngắn gọn (2-3 câu) đúng ý nghĩa các cảnh báo đã cung cấp và "
            "ảnh hưởng tới độ tin cậy định giá. Dùng đúng mô tả, KHÔNG tự suy thành 'lỗi dữ liệu'/'lỗi mô hình' nếu mô tả không nói vậy.\n"
        )
        flags_data_line = f"- Cảnh báo chất lượng (đã diễn giải sẵn): {flags_text}\n"
    else:
        flags_section_instruction = ""  # KHÔNG viết mục chất lượng khi sạch cờ
        flags_data_line = ""

    return (
        "Bạn là Giám đốc phân tích của một quỹ đầu tư Việt Nam, viết nhận định cho nhà đầu tư bận rộn. "
        "Văn phong TRỰC DIỆN, sắc bén, đi thẳng vào kết luận — cắt bỏ mọi câu đệm sáo rỗng kiểu "
        "'nhà đầu tư cần hiểu rằng', 'điều này có nghĩa là', 'tuy nhiên cần lưu ý', 'không đồng nghĩa với việc'. "
        "Mỗi câu phải mang một thông tin mới, không diễn giải vòng vo.\n\n"
        "ĐỘ DÀI: 340-440 từ (không dưới 320 từ), đủ sâu để có sức thuyết phục nhưng không lan man. "
        "Tiếng Việt. Được phép dùng KIẾN THỨC NGÀNH định tính (sản phẩm chính, động lực cung–cầu) để tăng chiều sâu, "
        "NHƯNG TUYỆT ĐỐI KHÔNG nêu con số cụ thể (giá hàng hóa, ngưỡng USD/tấn, %, mốc giá) mà dữ liệu không cung cấp — "
        "chỉ nói định tính (ví dụ 'giá phốt pho giảm sâu' thay vì 'dưới 2,300 USD/tấn'). "
        "Chỉ được dùng đúng các con số có trong phần DỮ LIỆU bên dưới.\n"
        "KHÔNG lặp lại các con số giá/FV/upside ở đầu (đã hiển thị riêng cho người đọc).\n"
        "Mỗi mục phải có LẬP LUẬN cụ thể (vì sao), không chỉ nêu kết luận suông.\n\n"
        "Định dạng BẮT BUỘC — dùng đúng các tiêu đề in đậm sau (mỗi mục 1 đoạn 3-5 câu có lý lẽ, KHÔNG đánh số):\n"
        "**💎 Cơ hội & Biên an toàn** — Upside đang cho biên an toàn thế nào so với ngưỡng mục tiêu của hệ thống? Định giá này hấp dẫn ở mức nào?\n"
        f"{flags_section_instruction}"
        "**⚠️ Rủi ro chính** — Điểm yếu lớn nhất: bản chất kinh doanh (chu kỳ?), độ lệch giữa 2 phương pháp định giá, đặc thù ngành. Nói thẳng cái gì có thể phá vỡ luận điểm.\n"
        "**📌 Khuyến nghị** — Hành động cụ thể (bám khuyến nghị hệ thống nếu hợp lý), và ĐIỀU KIỆN cụ thể nào khiến phải đổi quan điểm.\n\n"
        f"DỮ LIỆU (từ engine định giá thống nhất):\n"
        f"- Mã: {ticker}\n"
        f"- Phương pháp: {method_label}\n"
        f"- Upside so với thị giá: {upside:+.1f}%\n"
        f"{rec_line}{nature_line}{mos_line}{method_divergence}{flags_data_line}"
    )

@client.event
async def on_ready():
    logger.info(f"Bot đã đăng nhập thành công dưới tên: {client.user}")


def parse_ticker_from_message(content: str, bot_id: int) -> str | None:
    """Phân tích tin nhắn để trích xuất mã cổ phiếu bằng nhiều cú pháp khác nhau"""
    content_strip = content.strip()
    if not content_strip:
        return None

    # 1. Hỗ trợ tiền tố truyền thống !revalue <ticker>
    if content_strip.startswith("!revalue"):
        parts = content_strip.split()
        if len(parts) >= 2:
            return parts[1].upper().strip()

    # Danh sách các từ cần bỏ qua để tránh nhận diện nhầm khi chat
    ignored_words = {
        "cho", "toi", "con", "mua", "ban", "giu", "xem", "chay", "lenh", 
        "bot", "vua", "vao", "may", "chu", "dinh", "gia", "check", "ma", 
        "code", "link", "them", "xoa", "sua", "gium", "giup", "dep"
    }

    # 2. Hỗ trợ mention bot (ví dụ: @dinh gia chung khoan chạy fpt, @bot VCB...)
    mention_pattern = f"<@!?{bot_id}>"
    if re.search(mention_pattern, content_strip):
        clean = re.sub(mention_pattern, "", content_strip).lower().strip()
        # Tìm các từ có 3-4 chữ cái
        candidates = re.findall(r"\b[a-zA-Z]{3,4}\b", clean)
        for cand in candidates:
            if cand not in ignored_words:
                return cand.upper()

    # 3. Hỗ trợ từ khóa tiếng Việt/tiếng Anh (ví dụ: "định giá fpt", "dinh gia vcb", "check ctg")
    content_lower = content_strip.lower()
    keywords = ["định giá", "dinh gia", "revalue", "check", "định giá mã", "dinh gia ma"]
    for kw in keywords:
        if kw in content_lower:
            # Ưu tiên tìm từ đứng ngay sau từ khóa
            match = re.search(rf"{kw}\s+(\b[a-zA-Z]{3,4}\b)", content_lower)
            if match:
                return match.group(1).upper()
            
            # Nếu không tìm thấy ngay sau, quét toàn bộ tin nhắn loại trừ các từ bỏ qua
            candidates = re.findall(r"\b[a-zA-Z]{3,4}\b", content_lower)
            for cand in candidates:
                if cand not in ignored_words:
                    return cand.upper()

    # 4. Hỗ trợ gõ trực tiếp mã cổ phiếu (ví dụ: gõ "FPT" hoặc "fpt" hoặc "VCB" trong kênh)
    # Chỉ áp dụng nếu tin nhắn chỉ chứa duy nhất 1 từ dài từ 3 đến 4 chữ cái và không nằm trong từ bỏ qua
    if re.match(r"^[a-zA-Z]{3,4}$", content_strip):
        cand = content_strip.lower()
        if cand not in ignored_words:
            return cand.upper()

    return None

def _flags_block(flag_infos: list) -> str:
    if not flag_infos:
        return "✅ Không có cảnh báo — dữ liệu đạt chuẩn kiểm tra."
    lines = [f"{_FLAG_ICON.get(f['level'], '•')} {f['message']}" for f in flag_infos[:4]]
    if len(flag_infos) > 4:
        lines.append(f"... và {len(flag_infos) - 4} cảnh báo khác")
    return "\n".join(lines)


def _footer() -> str:
    now = datetime.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    return f"Hệ thống định giá tự động VN100 | {now:%d/%m/%Y %H:%M}"


async def handle_report_command(message):
    """!baocao — dựng báo cáo sáng ngay từ dữ liệu đang có (không cập nhật giá, không ghi lịch sử)."""
    from valuation.services.daily_report import run

    temp_msg = await message.channel.send("⏳ Đang dựng báo cáo từ dữ liệu hiện có...")
    try:
        await asyncio.to_thread(run, refresh=False, save=False, channel_id=message.channel.id)
    except Exception as e:  # noqa: BLE001 — báo lỗi ngay trong kênh thay vì chết im lặng
        logger.error(f"Error building daily report: {e}")
        await message.channel.send(f"❌ Không dựng được báo cáo: {type(e).__name__}: {e}")
    finally:
        await temp_msg.delete()


@client.event
async def on_message(message):
    # Tránh trường hợp bot tự trả lời chính mình
    if message.author == client.user:
        return
    if not is_authorized(message.author.id, message.author.bot, message.channel.id, OWNER_ID, CHANNEL_ID):
        return

    if message.content.strip().startswith("!baocao"):
        await handle_report_command(message)
        return

    # Phân tích xem tin nhắn có chứa mã cổ phiếu không; chỉ nhận mã thuộc VN100 (chống spam/injection)
    ticker = parse_ticker_from_message(message.content, client.user.id)
    if ticker not in VN100:
        return

    temp_msg = await message.channel.send(f"⏳ Đang thực hiện định giá và phân tích AI cho cổ phiếu **{ticker}**...")

    try:
        try:
            res = await asyncio.to_thread(fetch_report, ticker)
        except HTTPException as e:
            await temp_msg.delete()
            await message.channel.send(f"❌ Lỗi khi định giá {ticker} (Mã lỗi: {e.status_code}) — {e.detail}")
            return

        curr_price = res.get("current_price", 0.0) or 0.0
        blended_fv = res.get("fair_value", 0.0) or 0.0
        intrinsic_fv = res.get("intrinsic_fv")
        relative_fv = res.get("relative_fv")
        method_label = res.get("method", "N/A")
        recommendation = res.get("recommendation")
        business_nature = res.get("business_nature")
        target_mos = res.get("target_mos")
        qc_flags = res.get("flags", [])
        upside = (res.get("upside") or 0.0) * 100

        flag_infos = describe_flags(qc_flags)

        if not res.get("publication_allowed", True):
            # Cổng kiểm chứng chặn (giống Streamlit): không công bố FV/upside, không tốn lời gọi DeepSeek.
            embed = discord.Embed(
                title=f"⛔ {ticker}: chưa đủ điều kiện công bố giá trị hợp lý",
                description=(
                    f"**💵 Giá thị trường:** {curr_price:,.0f} VND\n\n"
                    "Dữ liệu đầu vào hoặc kết quả mô hình chưa qua cổng kiểm chứng, nên hệ thống "
                    "không công bố giá trị hợp lý, upside và nhận định AI cho mã này.\n\n"
                    f"**🚦 Lý do:**\n{_flags_block(flag_infos)}"
                ),
                color=0x95A5A6,
            )
            embed.set_footer(text=_footer())
            await temp_msg.delete()
            await message.channel.send(embed=embed)
            return

        # Gọi DeepSeek lấy nhận định (chạy trong thread riêng vì call_deepseek_sync là hàm đồng bộ)
        prompt = build_ticker_report_prompt(
            ticker, curr_price, blended_fv, upside, method_label, flag_infos,
            recommendation=recommendation, business_nature=business_nature,
            target_mos=target_mos, intrinsic_fv=intrinsic_fv, relative_fv=relative_fv,
        )
        ai_report = await asyncio.to_thread(call_deepseek_sync, prompt, 1300, 0.4)

        # Số liệu chuẩn — hiển thị trước, súc tích
        fv_line = f"**🎯 Giá trị hợp lý:** {blended_fv:,.0f} VND"
        if intrinsic_fv and relative_fv:
            fv_line += f"\n   ↳ Nội tại (DCF) {intrinsic_fv:,.0f} · So sánh (bội số) {relative_fv:,.0f}"

        rec_line = f"\n**🏁 Khuyến nghị hệ thống:** {recommendation}" if recommendation else ""

        header = (
            f"**💵 Giá thị trường:** {curr_price:,.0f} VND\n"
            f"{fv_line}\n"
            f"**📈 Upside:** {upside:+.1f}%\n"
            f"**🧮 Phương pháp:** {method_label}{rec_line}\n\n"
            f"**🚦 Cảnh báo chất lượng:**\n{_flags_block(flag_infos)}\n\n"
            f"**💡 Nhận định:**\n{ai_report}"
        )
        # Giới hạn description embed 4096 ký tự
        if len(header) > 4000:
            header = header[:3990] + "…"

        color = 0x00FF00 if upside > 0 else 0xFF0000
        embed = discord.Embed(
            title=f"📊 Báo cáo định giá: {ticker}",
            description=header,
            color=color
        )
        embed.set_footer(text=_footer())

        await temp_msg.delete()
        await message.channel.send(embed=embed)

    except Exception as e:
        logger.error(f"Error processing command for {ticker}: {e}")
        await temp_msg.delete()
        await message.channel.send(f"❌ Có lỗi xảy ra trong quá trình xử lý lệnh: {e!s}")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("Vui lòng cấu hình DISCORD_BOT_TOKEN trong file .env hoặc biến môi trường.")
        sys.exit(1)
    if CHANNEL_ID is None:
        logger.error("Cần DISCORD_CHANNEL_ID (dạng số) trong .env — bot chỉ nhận lệnh trong 1 kênh.")
        sys.exit(1)
    VN100.update(load_universe())
    logger.info(f"Đã nạp {len(VN100)} mã VN100; kênh {CHANNEL_ID}; người dùng: {OWNER_ID or 'mọi thành viên'}")
    client.run(DISCORD_TOKEN, log_handler=None)
