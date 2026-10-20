"""Bot Discord = trợ lý chứng khoán. CHỈ phản hồi khi được @bot trong DISCORD_CHANNEL_ID (.env).

  @bot !baocao        → báo cáo sáng (không gọi DeepSeek, không trừ lượt)
  @bot FPT            → báo cáo định giá chi tiết 1 mã (1 lượt DeepSeek)
  @bot <câu tự do>    → valuation/services/assistant.py: DeepSeek hiểu yêu cầu → Python lấy số → DeepSeek viết lời

Mọi thành viên kênh dùng được (quota/ngày ở config assistant), trừ khi đặt DISCORD_OWNER_ID để
khóa về 1 người. Gọi thẳng engine định giá (không cần FastAPI). Chạy nền bằng launchd: ~/Library/LaunchAgents/vn.antigravity-vn100.discord-bot.plist
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
from valuation.services.assistant import fetch_report, vn100

# Đảm bảo chứng chỉ SSL sử dụng Certifi bundle để tránh lỗi trên macOS
os.environ["SSL_CERT_FILE"] = certifi.where()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Khởi tạo Discord client
intents = discord.Intents.default()
intents.message_content = True
# Tắt @everyone/@here/@role trong mọi tin bot gửi: chữ do AI viết không thể ping cả server.
client = discord.Client(intents=intents, allowed_mentions=discord.AllowedMentions.none())

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


HELP = (
    "Gọi mình bằng **@bot** + yêu cầu, ví dụ:\n"
    "• `@bot FPT` — định giá chi tiết 1 mã\n"
    "• `@bot so sánh MBB với TCB` · `@bot top 10 ngân hàng upside cao`\n"
    "• `@bot HPG 20 phiên qua tăng bao nhiêu` · `@bot mã nào giảm mạnh nhất tuần này`\n"
    "• `@bot lãi suất Fed, CPI hiện tại` · `@bot CTCK khuyến nghị gì cho VNM`\n"
    "• `@bot tin tức về lãi suất` · `@bot !baocao`"
)


async def take_quota(message) -> tuple[bool, int | None]:
    """Trừ 1 lượt trước khi gọi DeepSeek; hết lượt thì báo và dừng."""
    from valuation.services.assistant import _cfg, _today
    from valuation.services.assistant import take_quota as _take

    ok, remaining = await asyncio.to_thread(_take, message.author.id, _cfg(), _today())
    if not ok:
        await message.channel.send("⛔ Bạn đã dùng hết lượt hỏi hôm nay. Mai quay lại nhé.")
    return ok, remaining


async def handle_ask(message, text: str, remaining: int | None):
    """Câu hỏi tự do → trợ lý (tối đa 2 lượt DeepSeek), kèm bảng số gốc Python để đối chiếu."""
    from valuation.services.assistant import ask

    temp_msg = await message.channel.send("⏳ Đang hiểu yêu cầu và lấy dữ liệu...")
    try:
        res = await asyncio.to_thread(ask, text)
    except Exception as e:  # noqa: BLE001 — báo lỗi ngay trong kênh thay vì chết im lặng
        logger.error(f"Assistant error: {e}")
        await message.channel.send(f"❌ Không xử lý được yêu cầu: {type(e).__name__}: {e}")
        return
    finally:
        await temp_msg.delete()
    quota = "Không giới hạn lượt" if remaining is None else f"Còn {remaining} lượt hôm nay"
    answer = discord.Embed(title="🤖 Trợ lý chứng khoán", description=res["answer"][:4000], color=0x5865F2)
    if res["notes"]:
        answer.add_field(name="Ghi chú", value="; ".join(res["notes"])[:1024])
    answer.set_footer(text=f"{quota} · Không phải khuyến nghị đầu tư | {_footer()}")
    await message.channel.send(embed=answer)
    if res["sources"]:  # tin riêng: tổng 2 embed có thể vượt 6000 ký tự/tin
        await message.channel.send(embed=discord.Embed(
            title="📎 Số liệu gốc (Python lấy từ DB, không qua AI)", description=res["sources"], color=0x95A5A6))


@client.event
async def on_message(message):
    # Tránh trường hợp bot tự trả lời chính mình
    if message.author == client.user:
        return
    if not is_authorized(message.author.id, message.author.bot, message.channel.id, OWNER_ID, CHANNEL_ID):
        return

    if client.user not in message.mentions:
        return  # chỉ phản hồi khi được @bot — không đọc chat thường trong kênh

    text = re.sub(r"<@[!&]?\d+>", "", message.content).strip()
    if text.startswith("!baocao"):
        await handle_report_command(message)
        return
    if not text:
        await message.channel.send(HELP)
        return

    ok, remaining = await take_quota(message)
    if not ok:
        return
    ticker = text.upper()
    if ticker not in VN100:  # không phải đúng 1 mã → trợ lý hiểu câu tự do
        await handle_ask(message, text, remaining)
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
    VN100.update(vn100())
    logger.info(f"Đã nạp {len(VN100)} mã VN100; kênh {CHANNEL_ID}; người dùng: {OWNER_ID or 'mọi thành viên'}")
    client.run(DISCORD_TOKEN, log_handler=None)
