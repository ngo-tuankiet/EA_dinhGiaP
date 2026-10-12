import logging
import datetime
import httpx
from sqlalchemy.orm import Session
from discord_webhook import DiscordWebhook, DiscordEmbed
from valuation.db.models import DailySignal
from valuation.db.session import SessionLocalRead
from valuation.config import settings

logger = logging.getLogger(__name__)


def _color_to_int(color) -> int:
    """Chuẩn hóa màu (chuỗi hex '00FF00' hoặc int) → int cho Discord REST API."""
    if isinstance(color, int):
        return color
    try:
        return int(str(color).lstrip("#"), 16)
    except (ValueError, TypeError):
        return 0x5865F2


def _post_via_bot(channel_id, content, embed_title, embed_desc, color, fields, footer) -> bool:
    """Gửi tin nhắn vào đúng channel_id (kể cả DM) qua bot token. Trả True nếu thành công."""
    if not settings.discord_bot_token:
        return False
    payload = {"content": content or ""}
    if embed_title:
        embed = {"title": embed_title, "description": embed_desc or "", "color": _color_to_int(color)}
        if fields:
            embed["fields"] = [
                {"name": f["name"], "value": f["value"][:1024], "inline": f.get("inline", False)}
                for f in fields
            ]
        if footer:
            embed["footer"] = {"text": footer}
        payload["embeds"] = [embed]
    try:
        r = httpx.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {settings.discord_bot_token}"},
            json=payload,
            timeout=30.0,
        )
        if r.status_code in (200, 201):
            return True
        logger.error(f"Bot post to channel {channel_id} failed {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"Bot post exception for channel {channel_id}: {e}")
        return False


def notify_discord(
    content: str = None,
    embed_title: str = None,
    embed_desc: str = None,
    color: str = "5865F2",
    fields: list = None,
    footer: str = None,
    channel_id=None,
):
    """Gửi thông báo lên Discord.

    - Nếu có ``channel_id``: gửi thẳng vào kênh đó qua bot token (đúng nơi user gõ lệnh,
      kể cả DM). Nếu lỗi thì fallback về webhook.
    - Nếu không có ``channel_id``: gửi qua webhook cố định (dùng cho n8n/scheduled).

    fields: list các dict {"name": str, "value": str, "inline": bool} (tối đa ~25, mỗi value <= 1024 ký tự).
    """
    if channel_id and _post_via_bot(channel_id, content, embed_title, embed_desc, color, fields, footer):
        return

    if not settings.discord_webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL is not set. Skipping Discord notification.")
        return
    webhook = DiscordWebhook(url=settings.discord_webhook_url, content=content or "")
    if embed_title:
        embed = DiscordEmbed(title=embed_title, description=embed_desc or "", color=color)
        for f in (fields or []):
            embed.add_embed_field(name=f["name"], value=f["value"][:1024], inline=f.get("inline", False))
        if footer:
            embed.set_footer(text=footer)
        webhook.add_embed(embed)
    webhook.execute()


def send_daily_alerts(trade_date: datetime.date = None, db: Session = None):
    """
    Quét bảng DailySignal lấy tín hiệu của ngày giao dịch và gửi cảnh báo lên Discord.
    - Cảnh báo STALE_FV
    - Tín hiệu Mua mạnh (Conviction Score > 75)
    """
    if not settings.discord_webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL is not set. Skipping Discord alerts.")
        return {"status": "skipped", "reason": "No webhook URL"}
        
    close_db = False
    if db is None:
        db = SessionLocalRead()
        close_db = True
        
    if trade_date is None:
        trade_date = datetime.date.today()
        
    try:
        signals = db.query(DailySignal).filter(DailySignal.trade_date == trade_date).all()
        
        strong_buys = []
        stale_flags = []
        
        for sig in signals:
            flags = sig.flags or []
            if "STALE_FV" in flags:
                stale_flags.append(sig)
                
            if sig.conviction_score and float(sig.conviction_score) > 75:
                strong_buys.append(sig)
                
        if not strong_buys and not stale_flags:
            logger.info("No actionable signals to alert today.")
            return {"status": "success", "alerts_sent": 0}
            
        webhook = DiscordWebhook(url=settings.discord_webhook_url)
        
        if strong_buys:
            embed = DiscordEmbed(
                title="🚀 CHỈ BÁO MUA MẠNH (STRONG BUY)", 
                description=f"Ngày giao dịch: {trade_date}",
                color="00FF00"
            )
            for b in strong_buys:
                fv_fast = b.fair_value_fast if b.fair_value_fast else "N/A"
                upside = round(float(b.upside) * 100, 1) if b.upside else "N/A"
                score = round(float(b.conviction_score), 1)
                
                embed.add_embed_field(
                    name=b.ticker,
                    value=f"**Điểm Conviction:** {score}/100\n**Upside:** {upside}%\n**Thị giá:** {b.close_price}\n**FV Điều chỉnh:** {fv_fast}",
                    inline=False
                )
            webhook.add_embed(embed)
            
        if stale_flags:
            embed = DiscordEmbed(
                title="⚠️ CẢNH BÁO STALE FV (Cần chạy lại Intrinsic Model)", 
                description="Vĩ mô biến động quá 10%, Base FV cũ đã bị vỡ.",
                color="FF0000"
            )
            for s in stale_flags:
                embed.add_embed_field(
                    name=s.ticker,
                    value=f"Cờ: {', '.join(s.flags)}\nĐiểm hiện tại bị phạt về: {round(float(s.conviction_score or 0), 1)}",
                    inline=False
                )
            webhook.add_embed(embed)
            
        response = webhook.execute()
        
        logger.info(f"Discord alerts sent successfully. Status code: {response.status_code}")
        return {"status": "success", "alerts_sent": len(strong_buys) + len(stale_flags)}
        
    except Exception as e:
        logger.error(f"Failed to send Discord alert: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        if close_db:
            db.close()
