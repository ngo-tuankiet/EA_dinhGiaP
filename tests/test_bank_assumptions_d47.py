"""D47 — giả định ngân hàng theo số thực tế (người dùng duyệt 02/10/2026).

1. Beta: trung vị beta Blume của nhóm ngân hàng VN100 (beta ngành bottom-up, Damodaran) thay beta hồi
   quy riêng — ACB beta riêng 0,77 cho COE 10,9%, thấp nhất nhóm, nhiễu ước lượng.
2. Tỷ lệ chi trả tiền = max(thực trả 3 năm, cổ tức tiền đã GDKHQ 12 tháng gần nhất / LN TTM) — MBB 3 năm
   8,7% nhưng 1.000đ GDKHQ 09/07/2026 ≈ 27% LN (trả ở quý 3, ngoài cửa sổ TTM).
3. Chi phí tín dụng phai tuyến tính TTM → trung vị 3 năm tài chính (s3, thay max(TTM, trung vị));
   TTM > spike_multiple × trung vị coi là trích lập đột biến một lần (STB Q4/2025) → giữ trung vị + cờ.
4. Sàn VCSH/Tổng tài sản = min(hiện tại, trung vị lịch sử): không ép VPB giảm đòn bẩy (LN năm 1 −44%)
   nhưng không cho NH tăng đòn bẩy vượt hiện tại (bỏ hẳn sàn từng đẩy TCB +48%) → cờ khi dưới lịch sử.
"""

from datetime import date

import pytest

from valuation.data_access.repo import build_company_data, credit_cost_schedule
from valuation.db.session import SessionLocalRead
from valuation.engine.ttm_helper import (
    estimate_vcb_beta,
    recent_cash_payout,
    sector_peer_beta,
)


@pytest.fixture(scope="module")
def db():
    s = SessionLocalRead()
    yield s
    s.close()


def test_recent_cash_payout_adjusts_dps_for_later_stock_dividend():
    # MBB: 1.000đ GDKHQ 09/07/2026, sau đó cổ tức CP 15% GDKHQ 11/08/2026.
    # Tiền chi = 1.000 / 1,15 × 9.263 triệu cp hiện tại = 8.055 tỷ; LN TTM 30.078 tỷ → 26,78%.
    payout = recent_cash_payout(
        dps_events=[(date(2026, 7, 9), 1000.0)],
        split_events=[(date(2026, 8, 11), 0.15)],
        shares=9_263_000_000,
        ttm_net_income=30_078e9,
        as_of=date(2026, 9, 28),
    )
    assert payout == pytest.approx(0.2678, abs=1e-4)


def test_recent_cash_payout_ignores_events_older_than_12_months_or_after_as_of():
    assert (
        recent_cash_payout(
            [(date(2025, 9, 1), 1000.0), (date(2026, 10, 5), 500.0)],
            [],
            1e9,
            1e12,
            date(2026, 9, 28),
        )
        == 0.0
    )


def test_credit_cost_schedule_rules():
    # VPB: TTM 2,91% < trung vị 4,53% → phai lên; bước (4,53 − 2,91)/4 = 0,405pp (tính tay).
    cc, spike = credit_cost_schedule(0.0291, 0.0453, spike_multiple=1.5)
    assert cc == pytest.approx([0.0291, 0.03315, 0.0372, 0.04125, 0.0453])
    assert spike is False
    # ACB: TTM 0,56% > trung vị 0,40% (chưa tới 1,5×) → phai XUỐNG, đối xứng (luật max cũ giữ 0,56%).
    cc, spike = credit_cost_schedule(0.0056, 0.0040, spike_multiple=1.5)
    assert cc == pytest.approx([0.0056, 0.0052, 0.0048, 0.0044, 0.0040])
    assert spike is False
    # STB: TTM 2,86% > 1,5 × 0,81% → đột biến một lần, giữ trung vị phẳng + cờ.
    assert credit_cost_schedule(0.0286, 0.0081, spike_multiple=1.5) == ([0.0081] * 5, True)


def test_bank_beta_is_peer_median(db):
    peer = sector_peer_beta(db, "NH")
    for t in ("ACB", "VCB", "MBB"):
        assert build_company_data(db, t).assumptions.beta == pytest.approx(peer)
    assert estimate_vcb_beta(db, "ACB") < peer  # beta riêng của ACB thấp hơn ngành


def test_mbb_payout_reflects_new_cash_dividend(db):
    assert build_company_data(
        db, "MBB"
    ).assumptions.dividend_payout_ratio == pytest.approx(0.268, abs=0.01)


def test_equity_floor_is_current_level_when_below_history(db):
    c = build_company_data(db, "VPB")
    bs = c.historical_bs[-1]
    # VPB: E/A hiện tại 12,7% < trung vị 14,3% → sàn = mức hiện tại, không ép giảm đòn bẩy.
    assert c.assumptions.min_equity_to_assets == pytest.approx(
        bs.total_equity / bs.total_assets
    )
    assert "BANK_LEVERAGE_ABOVE_HISTORY" in c.data_flags


def test_stb_credit_cost_spike_flagged_not_used(db):
    c = build_company_data(db, "STB")
    assert c.assumptions.credit_cost[0] == pytest.approx(0.0081, abs=5e-4)
    assert "BANK_CREDIT_COST_SPIKE" in c.data_flags
