"""
Test khung nhập CSV vĩ mô + scaffold scraper TPCP HNX/VBMA — đều OFFLINE
(không chạm mạng/DB thật; fetcher & registry injectable).
"""
import datetime

import pytest

from valuation.ingest.import_macro_csv import rows_to_points, _normalize_value
from valuation.ingest import tpcp_scraper

# Registry giả để test không đụng registry production.
_TEST_REG = {"CPI_YOY": {"unit": "decimal_rate"}, "POLICY_RATE": {"unit": "decimal_rate"},
             "TPCP_10Y": {"unit": "decimal_rate"}, "USDVND": {"unit": "vnd_per_usd"}}


# ---------------- CSV import ----------------

def test_percent_rate_normalized_to_decimal():
    """CPI 3.2 (%) → 0.032 (decimal_rate)."""
    assert _normalize_value("CPI_YOY", 3.2, as_percent=True) == pytest.approx(0.032)
    # Auto-detect: giá trị >1 coi như % dù không khai as_percent
    assert _normalize_value("CPI_YOY", 3.2, as_percent=False) == pytest.approx(0.032)


def test_decimal_rate_left_alone():
    """Giá trị đã là decimal (0.032) không bị chia nữa."""
    assert _normalize_value("CPI_YOY", 0.032, as_percent=True) == pytest.approx(0.032)


def test_price_series_not_divided():
    """USDVND (giá) không phải rate → giữ nguyên."""
    assert _normalize_value("USDVND", 25400.0, as_percent=True) == pytest.approx(25400.0)


def test_rows_to_points_rejects_unknown_code():
    rows = [{"date": "2026-06-30", "indicator_code": "FAKE_CODE", "value": 1.0}]
    with pytest.raises(ValueError):
        rows_to_points(rows, source="t", registry=_TEST_REG)


def test_rows_to_points_skips_nan_and_builds():
    import numpy as np
    rows = [
        {"date": "2026-06-30", "indicator_code": "CPI_YOY", "value": 3.2},
        {"date": "2026-06-30", "indicator_code": "POLICY_RATE", "value": np.nan},  # bỏ qua
    ]
    pts = rows_to_points(rows, source="GSO", as_percent=True, registry=_TEST_REG)
    assert len(pts) == 1
    assert pts[0].indicator_code == "CPI_YOY"
    assert pts[0].value == pytest.approx(0.032)
    assert pts[0].date == datetime.date(2026, 6, 30)


# ---------------- TPCP scraper (offline) ----------------

def test_scraper_domain_guard_blocks_unknown_host():
    """Fetch host ngoài allowlist bị chặn (chống SSRF)."""
    with pytest.raises(ValueError):
        tpcp_scraper.fetch_tpcp_10y(db=None, endpoint="https://evil.example.com/x")


def test_parse_hnx_yield_curve_extracts_10y():
    """Parser bóc đúng kỳ hạn 10Y, quy % → decimal."""
    payload = '{"data":[{"tenor":"5Y","yield":2.9},{"tenor":"10Y","yield":3.25,"date":"2026-06-30"}]}'
    parsed = tpcp_scraper.parse_hnx_yield_curve(payload, tenor_years=10)
    assert parsed is not None
    d, y = parsed
    assert y == pytest.approx(0.0325)
    assert d == datetime.date(2026, 6, 30)


def test_parse_hnx_returns_none_when_tenor_absent():
    payload = '{"data":[{"tenor":"5Y","yield":2.9}]}'
    assert tpcp_scraper.parse_hnx_yield_curve(payload, tenor_years=10) is None


def test_fetch_tpcp_offline_with_injected_fetcher(monkeypatch):
    """fetch_tpcp_10y dùng fetcher tách rời + endpoint hnx.vn (trong allowlist),
    KHÔNG chạm mạng; ghi qua upsert được mock."""
    calls = {}

    def fake_fetch(url):
        calls["url"] = url
        return '{"data":[{"tenor":"10Y","yield":3.4,"date":"2026-07-01"}]}'

    captured = {}
    def fake_upsert(points, db, registry=None):
        captured["points"] = list(points)
        return len(captured["points"])

    monkeypatch.setattr(tpcp_scraper, "upsert_macro_series", fake_upsert)
    n = tpcp_scraper.fetch_tpcp_10y(
        db=None, fetcher=fake_fetch,
        endpoint="https://hnx.vn/fake-yield-endpoint",
    )
    assert n == 1
    assert captured["points"][0].indicator_code == "TPCP_10Y"
    assert captured["points"][0].value == pytest.approx(0.034)
    assert "hnx.vn" in calls["url"]


def test_fetch_tpcp_no_endpoint_returns_zero():
    """Endpoint rỗng (chưa bật live) → trả 0, không lỗi."""
    assert tpcp_scraper.fetch_tpcp_10y(db=None, endpoint="") == 0
