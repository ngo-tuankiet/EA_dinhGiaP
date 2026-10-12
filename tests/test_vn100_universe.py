import json
from pathlib import Path

from valuation.engine import sector_router as sr


UNIVERSE_FILE = Path(__file__).parents[1] / "config" / "vn100_universe.json"


def test_current_universe_has_exactly_100_unique_symbols():
    snapshot = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    symbols = snapshot["symbols"]

    assert len(symbols) == 100
    assert len(set(symbols)) == 100
    assert symbols == sorted(symbols)
    assert snapshot["as_of"] == "2026-08-29"


def test_current_universe_is_fully_routed():
    symbols = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))["symbols"]
    missing = [symbol for symbol in symbols if sr.route(symbol) is None]

    assert missing == []


def test_departed_members_are_not_in_current_universe():
    symbols = set(json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))["symbols"])

    assert "HVN" not in symbols
    assert "TNH" not in symbols
    assert "BAF" in symbols
    assert "VCK" in symbols
