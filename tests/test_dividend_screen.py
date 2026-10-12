"""Nhận định nhanh lịch quyền (D56): upside dương + cổ tức tiền tốt & đều + giá sau GDKHQ vượt VN-Index."""

from datetime import date, timedelta

import pytest

from valuation.analysis.corporate_actions import dividend_opinion, dividend_track_record

AS_OF = date(2026, 10, 12)
KW = {"min_yield_pct": 5.0, "min_events": 3, "min_hit_rate": 0.6, "post_sessions": 2}


def _days(start, n):
    return [start + timedelta(days=i) for i in range(n)]


def test_track_record_hand_calculated():
    # Cổ phiếu: 100 → 104 → 110 quanh GDKHQ 02/03/2026 (giá đã điều chỉnh cổ tức), VN-Index 100 → 101 → 102.
    # Cửa sổ 2 phiên từ phiên trước GDKHQ: cổ phiếu +10%, VN-Index +2% → vượt +8 điểm %.
    d = _days(date(2026, 3, 1), 3)
    rec = dividend_track_record(
        cash_events=[
            (d[1], 3000),
            (d[1], 3000),
            (date(2025, 3, 2), 2000),
            (date(2024, 3, 2), 2000),
        ],
        closes=list(zip(d, [100, 104, 110])) + [(AS_OF, 50000)],
        index_closes=list(zip(d, [100, 101, 102])),
        as_of=AS_OF,
        post_sessions=2,
        consistency_years=3,
    )
    # TTM chỉ tính lần 02/03/2026 (3.000 đ, bỏ bản trùng): 3.000 / 50.000 = 6%.
    assert rec["yield_pct"] == pytest.approx(6.0)
    # Năm 2023 không trả → 2/3 năm (2023, 2024, 2025 chỉ có 2024, 2025).
    assert rec["paid_years"] == 2
    # Chỉ GDKHQ 2026 có đủ giá quanh mốc → 1 lần, vượt VN-Index.
    assert rec["events"] == 1 and rec["hits"] == 1
    assert rec["median_excess_pct"] == pytest.approx(8.0)


def _rec(y=6.0, paid=3, ev=4, hits=3, med=1.5):
    return {
        "yield_pct": y,
        "paid_years": paid,
        "consistency_years": 3,
        "events": ev,
        "hits": hits,
        "median_excess_pct": med,
    }


def test_opinion_levels():
    full = dividend_opinion(
        upside_pct=20.0,
        data_note="",
        liquidity_low=False,
        record=_rec(),
        event_note="",
        **KW
    )
    assert full.startswith("ĐẠT 3/3")
    # Cổ tức 4% < 5% → thiếu tiêu chí 2.
    two = dividend_opinion(
        upside_pct=20.0,
        data_note="",
        liquidity_low=True,
        record=_rec(y=4.0),
        event_note="",
        **KW
    )
    assert (
        two.startswith("THEO DÕI — đạt 2/3, thiếu cổ tức tốt & đều")
        and "thanh khoản thấp" in two
    )
    # 2/4 lần vượt = 50% < 60% và trả không đều → chỉ đạt upside.
    one = dividend_opinion(
        upside_pct=5.0,
        data_note="",
        liquidity_low=False,
        record=_rec(paid=2, hits=2),
        event_note="",
        **KW
    )
    assert one.startswith("CHƯA ĐẠT — đạt 1/3")
    neg = dividend_opinion(
        upside_pct=-3.0,
        data_note="",
        liquidity_low=False,
        record=_rec(),
        event_note="",
        **KW
    )
    assert neg.startswith("CHƯA HẤP DẪN")
    bad = dividend_opinion(
        upside_pct=30.0,
        data_note="Lỗi dữ liệu: CORPORATE_ACTION_UNDATED",
        liquidity_low=False,
        record=_rec(),
        event_note="",
        **KW
    )
    assert bad.startswith("CHƯA ĐỦ CƠ SỞ — Lỗi dữ liệu")
