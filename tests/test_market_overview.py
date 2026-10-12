"""Tổng quan thị trường (D51): 4 trụ cột −1/0/+1, ngành/mã có lực, nhãn tin AI qua whitelist."""

from datetime import date

import pandas as pd
import pytest

from valuation.data_access.macro_news import split_news_tags
from valuation.views.macro_panel import MacroObs
from valuation.views.market_overview import (
    Pillar,
    foreign_pillar,
    leaders,
    macro_pillar,
    overall,
    trend_pillar,
    valuation_pillar,
)

CFG = {
    "min_coverage": 0.5,
    "spread_comfort": 0.01,
    "ma_short": 3,
    "ma_long": 5,
    "breadth_high": 0.6,
    "breadth_low": 0.4,
    "return_sessions": 2,
    "flow_band_bn": 2000,
    "upside_high": 0.15,
    "upside_low": 0.0,
    "overall_threshold": 2,
    "sector_min_members": 2,
}
MCFG = {"cpi_target": 0.045, "cpi_near_band": 0.005}
DAYS = pd.date_range("2026-10-01", periods=6, freq="B")


def test_macro_pillar_current_snapshot_is_negative():
    # CPI 5,08% > 4,5% → −1; TPCP VN 4,58% − Mỹ 5,22% = −0,64 điểm % → −1;
    # Fed 3,75% → 4,00% → −1; SBV chỉ 1 quan sát → giữ (0). Tổng −3 → −1.
    snap = {
        "CPI_YOY": MacroObs(0.0508, date(2026, 9, 30), 0.0489, "MONTHLY"),
        "TPCP_10Y": MacroObs(0.0458, date(2026, 10, 6), 0.0458, "DAILY"),
        "UST_10Y": MacroObs(0.0522, date(2026, 10, 8), 0.0528, "DAILY"),
        "FED_FUNDS_UPPER": MacroObs(0.04, date(2026, 10, 9), 0.0375, "EVENT"),
        "POLICY_RATE": MacroObs(0.045, date(2026, 6, 30), None, "EVENT"),
    }
    p = macro_pillar(snap, MCFG, CFG)
    assert p.score == -1
    assert p.summary == "CPI vượt mục tiêu, TPCP VN < Mỹ, Fed tăng lãi suất"
    assert any("−0,64 điểm %" in d for d in p.details)


def test_trend_pillar_hand_calculated():
    # VN-Index 100,100,100,100,110 (×1000): MA3 = 103,33, MA5 = 102 → trên cả hai (+2).
    # Độ rộng: A, B trên MA3, C dưới → 2/3 = 67% ≥ 60% (+1). Tổng +3 → +1.
    vni = pd.Series([100e3, 100e3, 100e3, 100e3, 110e3], index=DAYS[:5])
    closes = pd.DataFrame(
        {"A": [10, 10, 12], "B": [5, 5, 6], "C": [8, 8, 7]}, index=DAYS[:3]
    )
    p = trend_pillar(vni, closes, CFG)
    assert p.score == 1
    assert "67% mã trên MA3" in p.summary
    assert p.details[0] == "VN-Index 110,00 điểm (07/10/2026)"


def test_foreign_pillar_band():
    # 2 phiên cuối, 2 mã: (−600 −500) + (−700 −400) tỷ = −2.200 tỷ < −2.000 → −1.
    flows = pd.DataFrame(
        {"A": [9e12, -600e9, -500e9], "B": [9e12, -700e9, -400e9]}, index=DAYS[:3]
    )
    p = foreign_pillar(flows, universe=2, cfg=CFG)
    assert p.score == -1 and p.summary == "bán ròng 2.200 tỷ/2 phiên"
    # Chỉ 1/4 mã có dữ liệu (< 50%) → không chấm.
    assert foreign_pillar(flows[["A"]], universe=4, cfg=CFG).score is None


def test_valuation_pillar_median():
    # Trung vị của −5%, 10%, 20% = 10% → giữa 0% và 15% → trung tính.
    p = valuation_pillar([-0.05, 0.10, 0.20], "nguồn", CFG)
    assert p.score == 0 and p.summary == "upside trung vị +10,0%"
    assert valuation_pillar([0.2, 0.3, 0.16], "nguồn", CFG).score == 1
    assert valuation_pillar([], "nguồn", CFG).score is None


def test_overall_ignores_missing_pillars():
    ps = [
        Pillar("a", -1, ""),
        Pillar("b", -1, ""),
        Pillar("c", 0, ""),
        Pillar("d", None, ""),
    ]
    assert overall(ps, CFG) == ("Khó khăn", -2, 3)
    ps2 = [
        Pillar("a", -1, ""),
        Pillar("b", 1, ""),
        Pillar("c", 0, ""),
        Pillar("d", 0, ""),
    ]
    assert overall(ps2, CFG)[0] == "Trung tính"


def test_leaders_relative_strength_and_flows():
    # Lợi suất 2 phiên: A +20%, B +10%, C 0%, D −10% → trung vị 5%.
    # A: trên MA3, vượt trung vị, ngoại mua → có lực. B: vượt trung vị nhưng ngoại bán → không.
    closes = pd.DataFrame(
        {
            "A": [10, 10, 12],
            "B": [10, 10, 11],
            "C": [10, 10, 10],
            "D": [10, 10, 9],
        },
        index=DAYS[:3],
    )
    flows = pd.DataFrame({"A": [0, 5e9, 5e9], "B": [0, -1e9, -1e9]}, index=DAYS[:3])
    sectors = {"A": "Thép", "B": "Thép", "C": "NH", "D": "NH"}
    tk, sec = leaders(closes, flows, sectors, CFG)
    assert tk[tk.support]["Mã"].tolist() == ["A"]
    assert tk.set_index("Mã").loc["A", "rel"] == pytest.approx(0.15)
    # Thép: trung vị tương đối (15% + 5%)/2 = +10%, ngoại +10 − 2 = +8 tỷ → mạnh.
    # NH: (−5% − 15%)/2 = −10%, không có dữ liệu ngoại (0) → không xếp yếu.
    assert sec.loc["Thép", "state"] == 1 and sec.loc["NH", "state"] == 0


def test_split_news_tags_whitelist_blocks_invented_tickers():
    text = (
        "**🇻🇳 Việt Nam**\n- Tin A\n"
        'TAGS: {"tich_cuc": ["HPG", "XYZ", "Thép", "<script>"], "tieu_cuc": ["BĐS", "HPG"]}'
    )
    body, tags = split_news_tags(text, {"HPG", "VCB", "Thép", "BĐS"})
    assert "TAGS" not in body and body.endswith("Tin A")
    assert tags == {"tich_cuc": ["HPG", "Thép"], "tieu_cuc": ["BĐS", "HPG"]}
    assert split_news_tags("Bản cũ", set()) == ("Bản cũ", None)
    assert split_news_tags("x TAGS: không phải json", set())[1] == {
        "tich_cuc": [],
        "tieu_cuc": [],
    }


VCFG = {
    **CFG,
    "ma_trend": [3, 5, 10],
    "change_sessions": [1],
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "level_window": 60,
}


def test_rsi_wilder_extremes():
    from valuation.views.market_overview import rsi_wilder

    assert rsi_wilder(pd.Series(range(1, 40), dtype=float), 14) == 100.0
    zigzag = pd.Series([100.0 + (i % 2) for i in range(200)])  # lãi = lỗ → ~50
    assert rsi_wilder(zigzag, 14) == pytest.approx(50, abs=5)
    assert rsi_wilder(pd.Series([1.0, 2.0]), 14) is None


def test_index_view_and_outlook_hand_calculated():
    from valuation.views.market_overview import headline, index_view, outlook

    # 59 phiên 100 điểm rồi 90: MA3 = (100+100+90)/3 = 96,67; MA5 = 98; MA10 = 99; đỉnh 60 phiên 100.
    # Giá 90 dưới mọi MA → ↓ cả 3 khung; kháng cự gần nhất = MA3; 90 là đáy → không có hỗ trợ.
    vni = pd.Series(
        [100e3] * 59 + [90e3], index=pd.date_range("2026-07-01", periods=60, freq="B")
    )
    v = index_view(vni, VCFG)
    assert v.last == 90 and v.changes == [(1, pytest.approx(-0.10))]
    assert [s for _, s in v.trends] == [-1, -1, -1]
    assert (
        v.resistance == (pytest.approx(96.6667, rel=1e-4), "MA3") and v.support is None
    )
    assert v.rsi == 0.0  # chỉ có phiên giảm

    pillars = [
        Pillar("Vĩ mô & chính sách", -1, ""),
        Pillar("Khối ngoại", -1, ""),
        Pillar("Định giá", 1, ""),
    ]
    lines = outlook(v, "Khó khăn", pillars, VCFG)
    assert (
        lines[0]
        == "Nghiêng thận trọng: vĩ mô, khối ngoại bất lợi — nhịp hồi dễ bị bán."
    )
    assert lines[1].startswith("RSI 0: quá bán")
    assert (
        lines[2]
        == "▲ Vượt 97 (MA3) → xu hướng ngắn hạn cải thiện, cần khối ngoại mua ròng để xác nhận."
    )
    assert lines[3] == "▼ Đang ở đáy 60 phiên — chưa có hỗ trợ gần."
    assert (
        headline("Khó khăn", pillars)
        == "**KHÓ KHĂN** — thuận: định giá · bất lợi: vĩ mô, khối ngoại"
    )
