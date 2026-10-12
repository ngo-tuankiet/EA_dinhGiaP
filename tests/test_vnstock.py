import pytest
from valuation.ingest.vnstock_client import vnstock_client

@pytest.mark.skip(reason="Live API call, run manually")
def test_get_company_overview():
    df = vnstock_client.get_company_overview("VCB")
    assert df is not None
    assert not df.empty
    assert "symbol" in df.columns
    assert df.iloc[0]["symbol"] == "VCB"

@pytest.mark.skip(reason="Live API call, run manually")
def test_get_financials():
    df = vnstock_client.get_financials("FPT", "IS")
    assert df is not None
    assert not df.empty
    assert "item_id" in df.columns

@pytest.mark.skip(reason="Live API call, run manually")
def test_get_historical_prices():
    df = vnstock_client.get_historical_prices("VCB", "2024-01-01")
    assert df is not None
    assert not df.empty
    assert "close" in df.columns
