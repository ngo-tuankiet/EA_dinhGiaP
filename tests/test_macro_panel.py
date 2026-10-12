"""Khung chỉ số vĩ mô sidebar (D50): FRED (lãi suất Fed, TPCP Mỹ 10Y) + nhận định nhanh theo quy tắc."""

from datetime import date

import pytest

from valuation.ingest.fred_fetcher import fetch_fred, parse_fred_csv
from valuation.views.macro_panel import MacroObs, quick_takes

CFG = {
    "stale_days": {"DAILY": 7, "MONTHLY": 45},
    "cpi_target": 0.045,
    "cpi_near_band": 0.005,
}


def test_parse_fred_csv_percent_to_decimal_and_skips_missing():
    text = "observation_date,DGS10\n2026-10-01,4.12\n2026-10-02,.\n2026-10-03,4.05\n"
    pts = parse_fred_csv(text, "DGS10", "UST_10Y")
    assert [(p.date, p.value) for p in pts] == [
        (date(2026, 10, 1), pytest.approx(0.0412)),
        (date(2026, 10, 3), pytest.approx(0.0405)),
    ]
    assert {p.source for p in pts} == {"fred.stlouisfed.org"}


def test_parse_fred_csv_rejects_unexpected_header():
    with pytest.raises(ValueError):
        parse_fred_csv("<html>blocked</html>", "DGS10", "UST_10Y")


def test_fetch_fred_only_calls_allowlisted_host():
    urls = []

    def fake_get(url):
        urls.append(url)
        sid = url.split("id=")[1].split("&")[0]
        return f"observation_date,{sid}\n2026-10-01,4.50\n"

    written = []
    n = fetch_fred(
        None,
        http_get=fake_get,
        writer=lambda pts, db: written.extend(pts) or len(pts),
        today=date(2026, 10, 10),
    )
    assert n == 3 and len(written) == 3
    assert all(
        u.startswith("https://fred.stlouisfed.org/graph/fredgraph.csv?id=")
        for u in urls
    )


def test_quick_takes_hand_calculated():
    # CPI 4,89% > mục tiêu 4,5%; TPCP VN 4,58% − CPI 4,89% = −0,31 điểm % (lãi suất thực âm);
    # TPCP VN 4,58% − Mỹ 4,10% = +0,48 điểm %; Fed 4,25% từ 4,50% → vừa hạ 0,25 điểm %.
    today = date(2026, 10, 10)
    snap = {
        "CPI_YOY": MacroObs(0.0489, date(2026, 9, 30), 0.0475, "MONTHLY"),
        "TPCP_10Y": MacroObs(0.0458, date(2026, 10, 9), 0.0458, "DAILY"),
        "UST_10Y": MacroObs(0.0410, date(2026, 10, 8), 0.0412, "DAILY"),
        "FED_FUNDS_UPPER": MacroObs(0.0425, date(2026, 9, 18), 0.0450, "EVENT"),
    }
    takes = quick_takes(snap, CFG, today)
    text = " | ".join(takes)
    assert "4,89%" in text and "vượt mục tiêu 4,5%" in text
    assert "−0,31 điểm %" in text
    assert "+0,48 điểm %" in text
    assert "hạ 0,25 điểm % về cận trên 4,25%" in text


def test_quick_takes_fed_hike_wording():
    snap = {"FED_FUNDS_UPPER": MacroObs(0.0400, date(2026, 10, 9), 0.0375, "EVENT")}
    (take,) = quick_takes(snap, {**CFG, "fed_lookback_days": 120}, date(2026, 10, 10))
    assert take == "Fed tăng 0,25 điểm % lên cận trên 4,00% trong 120 ngày qua."


def test_quick_takes_marks_stale_inputs():
    today = date(2026, 10, 10)
    snap = {
        "CPI_YOY": MacroObs(0.0469, date(2026, 6, 30), 0.056, "MONTHLY"),
        "TPCP_10Y": MacroObs(0.0458, date(2026, 10, 9), None, "DAILY"),
    }
    takes = quick_takes(snap, CFG, today)
    assert any("số liệu 30/06/2026" in t for t in takes)


def test_snapshot_skips_delta_across_data_gap():
    from valuation.db.models import MacroSeries
    from valuation.db.session import SessionLocalWrite
    from valuation.views.macro_panel import build_snapshot

    db = SessionLocalWrite()
    try:
        db.query(MacroSeries).filter(
            MacroSeries.indicator_code.in_(["USDVND", "FED_FUNDS_LOWER"])
        ).delete()
        db.add_all(
            [
                MacroSeries(
                    indicator_code="FED_FUNDS_LOWER",
                    date=date(2026, 10, 9),
                    value=0.0375,
                    source="t",
                ),
                MacroSeries(
                    indicator_code="USDVND",
                    date=date(2026, 7, 10),
                    value=26260,
                    source="t",
                ),
                MacroSeries(
                    indicator_code="USDVND",
                    date=date(2026, 10, 10),
                    value=25879,
                    source="t",
                ),
            ]
        )
        db.flush()
        snap = build_snapshot(db, CFG, {"USDVND": "DAILY"})
        assert snap["USDVND"].value == 25879 and snap["USDVND"].prev is None
        # Cận dưới Fed không có ô riêng nhưng phải có trong snapshot để hiện khoảng.
        assert snap["FED_FUNDS_LOWER"].value == pytest.approx(0.0375)
    finally:
        db.rollback()
        db.close()
