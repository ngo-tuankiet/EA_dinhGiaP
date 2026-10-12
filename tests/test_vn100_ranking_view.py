"""Tab VN100 (D55): xếp hạng theo upside mô hình + 5 mã tích sản (lọc dữ liệu, ngưỡng, thanh khoản, ngành)."""

from datetime import date

import pandas as pd
import pytest

from valuation.views.vn100_ranking import accumulation_picks, ranking_table

CFG = {
    "blocking_flags": ["NOT_RATED", "UPSIDE_EXTREME_REVIEW"],
    "max_upside_pct": 100,
    "scales": {"min_traded_value_vnd": 10e9},
}
D = date(2026, 10, 9)
LIQ = 50e9  # 50 tỷ/phiên — đạt ngưỡng 10 tỷ


def _row(t, fv, sector, flags=()):
    return {
        "ticker": t,
        "fair_value": fv,
        "sector": sector,
        "flags": list(flags),
        "price": 1,
    }


def test_ranking_table_hand_calculated():
    # Upside = GTHL / giá − 1: AAA 15.000/10.000 = +50%; BBB 22.000/20.000 = +10%;
    # CCC 25.000/10.000 = +150% (> 100% → cần rà soát); DDD chưa định giá; EEE thanh khoản 5 tỷ.
    snap = {
        "rows": [
            _row("BBB", 22000, "X"),
            _row("AAA", 15000, "X"),
            _row("CCC", 25000, "Y"),
            _row("DDD", None, "Y"),
            _row("EEE", 12000, "Z"),
        ]
    }
    market = {
        "AAA": (10000, D, LIQ),
        "BBB": (20000, D, LIQ),
        "CCC": (10000, D, LIQ),
        "DDD": (5000, D, LIQ),
        "EEE": (10000, D, 5e9),
    }
    t = ranking_table(snap, market, CFG).set_index("Mã")
    assert t.loc["AAA", "Upside (%)"] == pytest.approx(50.0)
    assert t.loc["BBB", "Upside (%)"] == pytest.approx(10.0)
    assert list(t.index) == [
        "CCC",
        "AAA",
        "EEE",
        "BBB",
        "DDD",
    ]  # theo upside, chưa định giá cuối
    assert t.loc["CCC", "Hạng"] == 1 and pd.isna(t.loc["DDD", "Hạng"])
    assert t.loc["CCC", "Ghi chú"] == "Upside > 100%: cần rà soát"
    assert t.loc["EEE", "Ghi chú"] == "Thanh khoản < 10 tỷ/phiên"
    assert t.loc["DDD", "Ghi chú"] == "Chưa định giá được"
    assert t.loc["AAA", "Ghi chú"] == ""


def test_data_error_flags_excluded_including_undated_corporate_action():
    snap = {
        "rows": [
            _row("AAA", 15000, "X", ["CORPORATE_ACTION_UNDATED"]),
            _row("BBB", 15000, "X", ["NOT_RATED: lý do"]),
            _row(
                "CCC", 15000, "X", ["JV_VALUED_AT_PE"]
            ),  # cờ thông tin, không phải lỗi
        ]
    }
    market = {t: (10000, D, LIQ) for t in ("AAA", "BBB", "CCC")}
    t = ranking_table(snap, market, CFG).set_index("Mã")
    assert t.loc["AAA", "Ghi chú"] == "Lỗi dữ liệu: CORPORATE_ACTION_UNDATED"
    assert t.loc["BBB", "Ghi chú"] == "Lỗi dữ liệu: NOT_RATED"
    assert t.loc["CCC", "Ghi chú"] == ""


def test_accumulation_picks_top_upside_max_two_per_sector():
    # 4 mã ngành X (upside 60/50/40/30) + 2 mã ngành Y (20/10): tối đa 2/ngành →
    # X60, X50, Y20, Y10 (bỏ X40, X30); chỉ 4 mã qua lọc nên trả 4.
    snap = {
        "rows": [_row(f"X{u}", 10000 * (1 + u / 100), "X") for u in (60, 50, 40, 30)]
        + [_row(f"Y{u}", 10000 * (1 + u / 100), "Y") for u in (20, 10)]
    }
    market = {r["ticker"]: (10000, D, LIQ) for r in snap["rows"]}
    picks = accumulation_picks(ranking_table(snap, market, CFG), max_per_sector=2)
    assert list(picks["Mã"]) == ["X60", "X50", "Y20", "Y10"]
