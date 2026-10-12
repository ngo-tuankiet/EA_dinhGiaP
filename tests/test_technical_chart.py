from datetime import date

import pandas as pd
import pytest

from valuation.analysis.technical_chart import (
    add_technical_indicators,
    normalize_price_history,
    period_start_date,
    price_snapshot,
    resample_price_history,
)


def _daily_prices(periods: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=periods, freq="D")
    close = pd.Series([10.0 + (index * 0.1) for index in range(periods)])
    return pd.DataFrame(
        {
            "time": dates,
            "open": close - 0.05,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": [1_000 + index for index in range(periods)],
        }
    )


def test_period_start_date_has_indicator_buffer() -> None:
    assert period_start_date("3T", date(2026, 8, 30)) == "2026-05-02"
    with pytest.raises(ValueError, match="Khoảng thời gian"):
        period_start_date("10N", date(2026, 8, 30))


def test_normalize_price_history_sorts_deduplicates_and_drops_invalid_rows() -> None:
    frame = pd.DataFrame(
        {
            "time": ["2026-01-02", "2026-01-01", "2026-01-02", "bad"],
            "open": [10, 9, 11, 8],
            "high": [11, 10, 12, 9],
            "low": [9, 8, 10, 7],
            "close": [10.5, 9.5, 11.5, 8.5],
            "volume": [100, 90, 110, 80],
        }
    )

    result = normalize_price_history(frame)

    assert result["time"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-01", "2026-01-02"]
    assert result.iloc[-1]["close"] == pytest.approx(11.5)


def test_resample_weekly_uses_first_max_min_last_and_sum() -> None:
    frame = pd.DataFrame(
        {
            "time": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-09"]),
            "open": [10.0, 11.0, 12.0],
            "high": [11.0, 13.0, 12.5],
            "low": [9.5, 10.5, 11.5],
            "close": [10.5, 12.5, 12.0],
            "volume": [100, 200, 300],
        }
    )

    result = resample_price_history(frame, "Tuần")

    assert len(result) == 1
    assert result.iloc[0]["open"] == pytest.approx(10.0)
    assert result.iloc[0]["high"] == pytest.approx(13.0)
    assert result.iloc[0]["low"] == pytest.approx(9.5)
    assert result.iloc[0]["close"] == pytest.approx(12.0)
    assert result.iloc[0]["volume"] == pytest.approx(600)


def test_indicators_are_calculated_from_price_history() -> None:
    result = add_technical_indicators(_daily_prices())

    assert result.iloc[19]["MA20"] == pytest.approx(10.95)
    assert result.iloc[49]["MA50"] == pytest.approx(12.45)
    assert result.iloc[-1]["RSI14"] == pytest.approx(100.0)
    assert result.iloc[-1]["BB_UPPER"] > result.iloc[-1]["MA20"]
    assert result.iloc[-1]["BB_LOWER"] < result.iloc[-1]["MA20"]
    assert result.iloc[-1]["MACD"] > result.iloc[-1]["MACD_SIGNAL"]


def test_price_snapshot_uses_actual_period_and_last_20_sessions() -> None:
    frame = _daily_prices()
    snapshot = price_snapshot(frame)

    assert snapshot["latest_close"] == pytest.approx(15.9)
    assert snapshot["period_change_pct"] == pytest.approx(59.0)
    assert snapshot["period_high"] == pytest.approx(16.1)
    assert snapshot["period_low"] == pytest.approx(9.8)
    assert snapshot["average_volume_20"] == pytest.approx(1049.5)
