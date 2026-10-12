"""
Test DDM (điện): multi-stage Gordon, EPS chuẩn hóa median, guardrail spread COE−g,
LN âm → không ra số rác.
"""
import pytest
from valuation.engine.models.ddm import DDMValuationModel


def _ddm(ni_hist, shares=1000e6, coe=0.12, payout=0.5, g_near=0.05, g_term=0.03):
    cf = {"net_income_history": ni_hist, "shares_outstanding": shares, "current_price": 15000}
    a = {"cost_of_equity": coe, "payout_ratio": payout, "near_growth": g_near, "long_term_growth": g_term}
    return DDMValuationModel("ZZDDM", cf, a)


def test_ddm_positive_and_uses_median():
    # LN [1000,1100,3000] (năm gần đột biến) → median 1100, không 3000.
    m = _ddm([1000.0, 1100.0, 3000.0])
    r = m.perform_valuation()
    assert r["normalized_eps"] == pytest.approx(1100e9 / 1000e6, rel=1e-9)
    assert r["blended_fair_value_per_share"] > 0


def test_ddm_higher_payout_higher_value():
    lo = _ddm([1000.0, 1000.0, 1000.0], payout=0.3).perform_valuation()
    hi = _ddm([1000.0, 1000.0, 1000.0], payout=0.7).perform_valuation()
    assert hi["blended_fair_value_per_share"] > lo["blended_fair_value_per_share"]


def test_ddm_negative_earnings_no_garbage():
    r = _ddm([-100.0, -50.0, -80.0]).perform_valuation()
    assert r["blended_fair_value_per_share"] == 0.0
    assert "NEGATIVE_EARNINGS" in r["flags"]


def test_ddm_handles_g_above_coe():
    # g_term >= coe → tự kẹp, không chia 0/âm.
    r = _ddm([1000.0, 1000.0, 1000.0], coe=0.10, g_term=0.12).perform_valuation()
    assert r["blended_fair_value_per_share"] > 0
