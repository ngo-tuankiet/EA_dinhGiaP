"""Chu kỳ thép: zigzag, thời lượng pha, Kaplan–Meier — các ca tính tay."""

import pandas as pd
import pytest

from valuation.analysis.steel_cycle import (
    duration_stats,
    forward_return_by_state,
    km_survival,
    phases,
    prob_end_within,
    zigzag,
)


def test_zigzag_hand_case():
    # 100 → 130 (+30% ≥ 20%: xác nhận đáy ở kỳ 0, tại kỳ 2) → đỉnh 150 ở kỳ 3 → 115 (−23%: xác nhận
    # đỉnh tại kỳ 4) → 110 đáy ở kỳ 5 → 140 (+27%: xác nhận đáy tại kỳ 6).
    v = [100, 110, 130, 150, 115, 110, 140]
    turns, state = zigzag(v, 0.20)
    assert [(t.idx, t.kind, t.confirmed_idx) for t in turns] == [(0, "T", 2), (3, "P", 4), (5, "T", 6)]
    # Trạng thái thời gian thực: chưa biết gì tới kỳ 2, rồi up, down từ kỳ 4, up từ kỳ 6.
    assert state == [None, None, "up", "up", "down", "down", "up"]
    ph = phases(v, turns)
    assert [(p["type"], p["months"], round(p["change"], 3), p["censored"]) for p in ph] == [
        ("up", 3, 0.5, False),
        ("down", 2, round(110 / 150 - 1, 3), False),
        ("up", 1, round(140 / 110 - 1, 3), True),
    ]
    assert duration_stats(ph, "up") == {
        "n": 1, "median_months": 3, "mean_months": 3.0, "min_months": 3, "max_months": 3, "median_change": 0.5,
    }


def test_zigzag_small_moves_are_noise():
    turns, state = zigzag([100, 105, 98, 104, 99], 0.20)
    assert turns == [] and set(state) == {None}


def test_kaplan_meier_hand_case():
    # Thời lượng 2, 4, 4, 6 (kết thúc) + 5 (đang diễn ra, censored).
    # t=2: 5 pha có rủi ro, 1 kết thúc → S = 4/5 = 0,8
    # t=4: 4 có rủi ro, 2 kết thúc → S = 0,8 × 2/4 = 0,4
    # t=5: censored, không đổi S; t=6: 1 có rủi ro, 1 kết thúc → S = 0.
    d, c = [2, 4, 4, 6, 5], [False, False, False, False, True]
    assert km_survival(d, c) == [(2, pytest.approx(0.8), 5), (4, pytest.approx(0.4), 4), (6, pytest.approx(0.0), 1)]
    # Đã kéo dài 3 tháng: P(kết thúc trong 2 tháng) = 1 − S(5)/S(3) = 1 − 0,4/0,8 = 0,5; 4 pha từng sống ≥ 3.
    r = prob_end_within(d, c, age=3, horizon=2)
    assert r["prob"] == pytest.approx(0.5) and r["n_at_risk"] == 4


def test_forward_return_by_state_hand_case():
    idx = pd.date_range("2020-01-31", periods=4, freq="ME")
    px = pd.Series([100.0, 110.0, 121.0, 100.0], index=idx)
    st = pd.Series(["up", "up", "down", "down"], index=idx)
    r = forward_return_by_state(px, st, months=1)
    # up: +10%, +10% → trung bình 10%; down: 100/121 − 1 (kỳ cuối không có lợi suất tới).
    assert r["up"]["mean"] == pytest.approx(0.10) and r["up"]["hit_rate"] == 1.0
    assert r["down"]["n"] == 1 and r["down"]["mean"] == pytest.approx(100 / 121 - 1)


def test_event_returns_hand_case():
    from valuation.analysis.steel_cycle import event_returns

    idx = pd.period_range("2020-01", periods=4, freq="M")
    px = pd.Series([100.0, 120.0, 90.0, 99.0], index=idx)
    r = event_returns(px, [(pd.Period("2020-02", "M"), "T"), (pd.Period("2019-01", "M"), "P")], [1, 6])
    # Tháng 02: 120 → 90 sau 1 tháng = −25%; 6 tháng vượt dữ liệu → None; sự kiện trước dữ liệu bị bỏ.
    assert r == [{"date": "2020-02", "kind": "T", "r1": pytest.approx(-0.25), "r6": None}]
