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


def test_is_authorized_channel_members_or_owner_lock():
    assert bot.is_authorized(999, False, CHANNEL, None, CHANNEL)  # không khóa owner: ai trong kênh cũng được
    assert not bot.is_authorized(999, True, CHANNEL, None, CHANNEL)  # bot khác bị bỏ qua
    assert not bot.is_authorized(999, False, 333, None, CHANNEL)  # sai kênh
    assert not bot.is_authorized(999, False, CHANNEL, None, None)  # thiếu kênh = từ chối
    assert bot.is_authorized(OWNER, False, CHANNEL, OWNER, CHANNEL)
    assert not bot.is_authorized(999, False, CHANNEL, OWNER, CHANNEL)  # có khóa owner


def _message(content, author=OWNER, channel=CHANNEL):
    temp = SimpleNamespace(delete=AsyncMock())
    ch = SimpleNamespace(id=channel, send=AsyncMock(return_value=temp))
    return SimpleNamespace(
        content=content, author=SimpleNamespace(id=author, bot=False), channel=ch
    )


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_ID", OWNER)
    monkeypatch.setattr(bot, "CHANNEL_ID", CHANNEL)
    monkeypatch.setattr(bot, "VN100", {"FPT", "PNJ"})
    monkeypatch.setattr(bot.client._connection, "user", SimpleNamespace(id=1))
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


def test_ignores_other_user_channel_and_non_vn100(wired, monkeypatch):
    fetch = MagicMock(return_value=_report(True))
    monkeypatch.setattr(bot, "fetch_report", fetch)
    for msg in (
        _message("FPT", author=999),
        _message("FPT", channel=333),
        _message("haha"),
        _message("ABC"),
    ):
        asyncio.run(bot.on_message(msg))
        msg.channel.send.assert_not_called()
    fetch.assert_not_called()


def test_blocked_ticker_hides_fv_and_skips_deepseek(wired, monkeypatch):
    monkeypatch.setattr(bot, "fetch_report", MagicMock(return_value=_report(False)))
    msg = _message("PNJ")
    asyncio.run(bot.on_message(msg))
    wired.assert_not_called()
    embed = msg.channel.send.await_args_list[-1].kwargs["embed"]
    assert "chưa đủ điều kiện" in embed.title and "150" not in embed.description


def test_allowed_ticker_calls_deepseek_once(wired, monkeypatch):
    monkeypatch.setattr(bot, "fetch_report", MagicMock(return_value=_report(True)))
    msg = _message("fpt")
    asyncio.run(bot.on_message(msg))
    wired.assert_called_once()
    assert "150" in msg.channel.send.await_args_list[-1].kwargs["embed"].description
