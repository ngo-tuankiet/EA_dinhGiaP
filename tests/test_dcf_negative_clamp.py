"""
Test DCF chặn giá trị vốn cổ phần ÂM về 0 + gắn cờ NEGATIVE_EQUITY_VALUE_DCF.

Regression: NKG (thép, biên mỏng, nợ lớn) từng ra blended FV = -6,510 VND
(giá cổ phiếu âm — vô lý). DCF không chặn số âm như EV/EBITDA đã làm (C9).
"""
import pytest

from valuation.engine.models.dcf import DCFValuationModel


def _dcf_with_huge_net_debt():
    """cf/assumptions khiến net debt >> EV → equity value âm."""
    cf_dict = {
        "total_equity": 1_000e9, "total_assets": 10_000e9,
        "cash_and_equivalents": 100e9, "total_debt": 9_000e9,  # nợ khổng lồ
        "total_revenue": 5_000e9, "cogs": 4_800e9, "ebitda": 150e9,
        "shares_outstanding": 500e6, "current_price": 12_000.0,
    }
    ass = {
        "cost_of_equity": 0.13, "wacc": 0.12,
        "revenue_growth_1_to_3": 0.02, "revenue_growth_4_to_5": 0.02,
        "ebit_margin": 0.02,  # biên siêu mỏng như thép
        "tax_rate": 0.20, "capex_to_revenue": 0.03, "depr_to_revenue": 0.03,
        "dso": 30.0, "dio": 30.0, "dpo": 30.0, "interest_rate": 0.10,
        "debt_repayment_rate": 0.10, "new_borrowing_rate": 0.05,
        "target_ev_ebitda": 5.0, "long_term_growth": 0.02, "weight_dcf": 0.5,
    }
    return DCFValuationModel("TST_STEEL", cf_dict, ass)


def test_negative_equity_clamped_to_zero_and_flagged():
    m = _dcf_with_huge_net_debt()
    res = m.perform_valuation()
    assert res["blended_fair_value_per_share"] == 0.0, "giá âm phải bị chặn về 0"
    assert "NEGATIVE_EQUITY_VALUE_DCF" in m.valuation_warnings


def test_normal_case_not_flagged():
    """DN lành mạnh (nợ thấp) không bị chặn/gắn cờ oan."""
    cf_dict = {
        "total_equity": 5_000e9, "total_assets": 8_000e9,
        "cash_and_equivalents": 1_000e9, "total_debt": 500e9,
        "total_revenue": 4_000e9, "cogs": 2_800e9, "ebitda": 800e9,
        "shares_outstanding": 200e6, "current_price": 50_000.0,
    }
    ass = {
        "cost_of_equity": 0.12, "wacc": 0.11,
        "revenue_growth_1_to_3": 0.10, "revenue_growth_4_to_5": 0.08,
        "ebit_margin": 0.15, "tax_rate": 0.20, "capex_to_revenue": 0.05,
        "depr_to_revenue": 0.04, "dso": 30.0, "dio": 30.0, "dpo": 30.0,
        "interest_rate": 0.08, "debt_repayment_rate": 0.20,
        "new_borrowing_rate": 0.05, "target_ev_ebitda": 8.0,
        "long_term_growth": 0.02, "weight_dcf": 0.5,
    }
    m = DCFValuationModel("TST_HEALTHY", cf_dict, ass)
    res = m.perform_valuation()
    assert res["blended_fair_value_per_share"] > 0
    assert "NEGATIVE_EQUITY_VALUE_DCF" not in m.valuation_warnings


def test_review_flags_thresholds():
    from valuation.engine.valuate import _review_flags
    assert _review_flags(302.8) == ["UPSIDE_EXTREME_REVIEW"]
    assert _review_flags(-99.9) == ["DOWNSIDE_EXTREME_REVIEW"]
    assert _review_flags(50.0) == []      # trong vùng bình thường
    assert _review_flags(-30.0) == []
    assert _review_flags(None) == []
