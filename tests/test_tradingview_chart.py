import pandas as pd

from valuation.views import tradingview_chart


def _price_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": ["2026-09-01"],
            "open": [20.0],
            "high": [21.0],
            "low": [19.5],
            "close": [20.5],
            "volume": [1_000_000],
        }
    )


def test_price_history_reads_stored_prices_without_network(monkeypatch) -> None:
    # Hiển thị biểu đồ không được gọi vnstock (nguồn chậm từng treo cả trang).
    stored = _price_frame()
    stored.attrs["data_source"] = "CSDL giá nội bộ"
    monkeypatch.setattr(tradingview_chart, "_load_stored_price_history", lambda ticker, start_date: stored)
    tradingview_chart._load_price_history.clear()

    result = tradingview_chart._load_price_history("ACB", "2026-01-01")

    assert result.attrs["data_source"] == "CSDL giá nội bộ"
    assert not hasattr(tradingview_chart, "vnstock_client")
    assert result.iloc[0]["close"] == 20.5
