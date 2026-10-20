import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")

_spec = importlib.util.spec_from_file_location(
    "discord_bot", Path(__file__).resolve().parents[1] / "scripts/discord_bot.py"
)
bot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bot)

OWNER, CHANNEL = 111, 222
BOT_USER = SimpleNamespace(id=1)


def test_is_authorized_channel_members_or_owner_lock():
    assert bot.is_authorized(
        999, False, CHANNEL, None, CHANNEL
    )  # không khóa owner: ai trong kênh cũng được
    assert not bot.is_authorized(
        999, True, CHANNEL, None, CHANNEL
    )  # bot khác bị bỏ qua
    assert not bot.is_authorized(999, False, 333, None, CHANNEL)  # sai kênh
    assert not bot.is_authorized(
        999, False, CHANNEL, None, None
    )  # thiếu kênh = từ chối
    assert bot.is_authorized(OWNER, False, CHANNEL, OWNER, CHANNEL)
    assert not bot.is_authorized(999, False, CHANNEL, OWNER, CHANNEL)  # có khóa owner


def _message(content, author=OWNER, channel=CHANNEL, mention=True):
    temp = SimpleNamespace(delete=AsyncMock())
    ch = SimpleNamespace(id=channel, send=AsyncMock(return_value=temp))
    return SimpleNamespace(
        content=("<@1> " if mention else "") + content,
        mentions=[BOT_USER] if mention else [],
        author=SimpleNamespace(id=author, bot=False),
        channel=ch,
    )


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_ID", None)
    monkeypatch.setattr(bot, "CHANNEL_ID", CHANNEL)
    monkeypatch.setattr(bot, "VN100", {"FPT", "PNJ"})
    monkeypatch.setattr(bot.client._connection, "user", BOT_USER)
    monkeypatch.setattr(bot, "take_quota", AsyncMock(return_value=(True, 19)))
    deepseek = MagicMock(return_value="nhận định")
    monkeypatch.setattr(bot, "call_deepseek_sync", deepseek)
    return deepseek


def _report(allowed):
    return {
        "current_price": 100.0,
        "fair_value": 150.0,
        "upside": 0.5,
        "flags": [],
        "publication_allowed": allowed,
    }


def test_ignores_without_mention_or_wrong_channel(wired, monkeypatch):
    fetch = MagicMock(return_value=_report(True))
    monkeypatch.setattr(bot, "fetch_report", fetch)
    for msg in (_message("FPT", mention=False), _message("FPT", channel=333)):
        asyncio.run(bot.on_message(msg))
        msg.channel.send.assert_not_called()
    fetch.assert_not_called()
    bot.take_quota.assert_not_called()  # không @ thì không tốn lượt


def test_blocked_ticker_hides_fv_and_skips_deepseek(wired, monkeypatch):
    monkeypatch.setattr(bot, "fetch_report", MagicMock(return_value=_report(False)))
    msg = _message("PNJ")
    asyncio.run(bot.on_message(msg))
    wired.assert_not_called()
    embed = msg.channel.send.await_args_list[-1].kwargs["embed"]
    assert "chưa đủ điều kiện" in embed.title and "150" not in embed.description


def test_mention_single_ticker_uses_fast_path(wired, monkeypatch):
    monkeypatch.setattr(bot, "fetch_report", MagicMock(return_value=_report(True)))
    ask = MagicMock()
    monkeypatch.setattr("valuation.services.assistant.ask", ask)
    msg = _message("fpt")
    asyncio.run(bot.on_message(msg))
    wired.assert_called_once()
    ask.assert_not_called()
    assert "150" in msg.channel.send.await_args_list[-1].kwargs["embed"].description


def test_free_text_goes_to_assistant_with_sources(wired, monkeypatch):
    ask = MagicMock(
        return_value={
            "answer": "MBB rẻ hơn",
            "sources": "**MBB** ...",
            "calls": [],
            "notes": [],
        }
    )
    monkeypatch.setattr("valuation.services.assistant.ask", ask)
    msg = _message("so sánh MBB với TCB")
    asyncio.run(bot.on_message(msg))
    ask.assert_called_once_with("so sánh MBB với TCB")
    embeds = [
        c.kwargs["embed"]
        for c in msg.channel.send.await_args_list
        if "embed" in c.kwargs
    ]
    assert (
        embeds[0].description == "MBB rẻ hơn" and "Còn 19 lượt" in embeds[0].footer.text
    )
    assert "Số liệu gốc" in embeds[1].title


def test_out_of_quota_stops_before_deepseek(wired, monkeypatch):
    monkeypatch.setattr(bot, "take_quota", AsyncMock(return_value=(False, 0)))
    fetch = MagicMock()
    monkeypatch.setattr(bot, "fetch_report", fetch)
    asyncio.run(bot.on_message(_message("FPT")))
    fetch.assert_not_called()
    wired.assert_not_called()


def test_client_disables_mass_mentions():
    am = bot.client.allowed_mentions
    assert not am.everyone and not am.roles and not am.users
