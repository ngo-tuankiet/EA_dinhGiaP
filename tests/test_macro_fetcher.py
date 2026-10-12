"""Test macro_fetcher với price_fetcher giả (không gọi mạng).

Dùng symbol_map + registry test (code ZZ_TEST_*) để KHÔNG đụng dữ liệu thật.
"""
import datetime

import pytest

from valuation.db.models import MacroSeries
from valuation.db.session import SessionLocalWrite
from valuation.ingest.macro_fetcher import fetch_market_macro

# symbol giả -> code test
SYMBOL_MAP = {"FAKE_FX": "ZZ_TEST_FX", "FAKE_CMD": "ZZ_TEST_CMD"}
TEST_REGISTRY = {
    "ZZ_TEST_FX": {"unit": "vnd_per_usd", "source": "test"},
    "ZZ_TEST_CMD": {"unit": "usd", "source": "test"},
}
CODES = list(TEST_REGISTRY)
D = datetime.date(2025, 2, 10)


@pytest.fixture
def db():
    s = SessionLocalWrite()
    s.query(MacroSeries).filter(MacroSeries.indicator_code.like("ZZ_TEST_%")).delete(
        synchronize_session=False
    )
    s.commit()
    yield s
    s.query(MacroSeries).filter(MacroSeries.indicator_code.like("ZZ_TEST_%")).delete(
        synchronize_session=False
    )
    s.commit()
    s.close()


def _fake_fetcher(values):
    return lambda symbol: values.get(symbol)


def test_fetch_maps_symbols_to_codes(db):
    fetcher = _fake_fetcher({"FAKE_FX": (D, 26245.0), "FAKE_CMD": (D, 1156.0)})
    n = fetch_market_macro(
        db, price_fetcher=fetcher, symbol_map=SYMBOL_MAP, registry=TEST_REGISTRY
    )
    assert n == 2
    got = {
        r.indicator_code: float(r.value)
        for r in db.query(MacroSeries).filter(MacroSeries.indicator_code.in_(CODES))
    }
    assert got == {"ZZ_TEST_FX": 26245.0, "ZZ_TEST_CMD": 1156.0}


def test_fetch_is_idempotent(db):
    fetcher = _fake_fetcher({"FAKE_FX": (D, 26245.0)})
    fetch_market_macro(db, price_fetcher=fetcher, symbol_map=SYMBOL_MAP, registry=TEST_REGISTRY)
    fetch_market_macro(db, price_fetcher=fetcher, symbol_map=SYMBOL_MAP, registry=TEST_REGISTRY)
    assert (
        db.query(MacroSeries).filter(MacroSeries.indicator_code == "ZZ_TEST_FX").count()
        == 1
    )


def test_fetch_skips_missing_symbol(db):
    fetcher = _fake_fetcher({"FAKE_FX": (D, 26245.0), "FAKE_CMD": None})
    n = fetch_market_macro(
        db, price_fetcher=fetcher, symbol_map=SYMBOL_MAP, registry=TEST_REGISTRY
    )
    assert n == 1


def test_real_symbol_map_uses_registry_codes():
    """Map yfinance thật phải trỏ vào code có trong registry production."""
    from valuation.config import get_macro_series_registry
    from valuation.ingest.macro_fetcher import YF_SYMBOL_TO_CODE

    reg = get_macro_series_registry()
    for code in YF_SYMBOL_TO_CODE.values():
        assert code in reg
