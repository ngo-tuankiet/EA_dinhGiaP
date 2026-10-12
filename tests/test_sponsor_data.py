"""Kiểm tra cache và dữ liệu giao dịch bằng số mẫu tính tay."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from valuation.ingest import sponsor_data as source


def market_fixture():
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(20)]
    window = {"start": days[0].isoformat(), "end": days[-1].isoformat()}
    stats = {
        **window,
        "rows": [
            {
                "average_match_value": 100,
                "total_value": 2500,
                "average_volume": 10,
                "total_volume": 200,
            }
        ],
    }
    flows = {
        **window,
        "rows": [{"time": day.isoformat(), "net_val": -5} for day in days],
    }
    return days, stats, flows


def test_market_metrics_use_actual_matching_value():
    days, stats, flows = market_fixture()
    result = source.sponsor_market_metrics(stats, flows, days)
    assert result == {"avg_traded_value": 100, "foreign_flow_ratio": -0.04}


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 0])
def test_market_metrics_reject_invalid_denominator(bad):
    days, stats, flows = market_fixture()
    stats["rows"][0]["total_value"] = bad
    assert source.sponsor_market_metrics(stats, flows, days) == {}


def test_market_metrics_reject_incomplete_window():
    days, stats, flows = market_fixture()
    flows["rows"].pop()
    assert source.sponsor_market_metrics(stats, flows, days) == {}
    assert source.sponsor_market_metrics(stats, flows, days[:-1]) == {}


def test_ambiguous_percent_unit_cannot_enter_bank_safety_score():
    payload = {
        "rows": [{"period": "2026-Q2", "id": "RT_BANK_NPL", "unit": "%", "value": 0.01}]
    }
    assert source.sponsor_risk_metrics(payload, "2026-Q2") == {}


def test_cache_avoids_repeated_api_calls_and_preserves_old_source(
    tmp_path, monkeypatch
):
    calls = []

    def fetch(*args):
        calls.append(args)
        return pd.DataFrame([{"value": len(calls)}])

    monkeypatch.setattr(source, "fetch_sponsor_dataset", fetch)
    args = ("ACB", "BS", date(2026, 1, 1), date(2026, 1, 20))
    now = datetime(2026, 1, 21, tzinfo=UTC)
    assert (
        source.collect_sponsor_dataset(*args, now, tmp_path)["status"] == "downloaded"
    )
    assert source.collect_sponsor_dataset(*args, now, tmp_path)["status"] == "cached"
    assert len(calls) == 1
    source.collect_sponsor_dataset(*args, now + timedelta(days=8), tmp_path)
    assert len(calls) == 2
    assert len(list((tmp_path / "ACB/history").glob("*.json"))) == 1


def test_cache_rejects_invalid_ticker(tmp_path):
    with pytest.raises(ValueError, match="Mã"):
        source.collect_sponsor_dataset(
            "../x",
            "BS",
            date(2026, 1, 1),
            date(2026, 1, 20),
            datetime(2026, 1, 21, tzinfo=UTC),
            tmp_path,
        )
