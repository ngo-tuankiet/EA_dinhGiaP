"""
Test EVEBITDAValuationModel — đặc biệt case đòn bẩy cao (hàng không) khiến
net debt > EV, equity value âm bị clip về 0.

Regression: trước đây model trả fvps=0.0 (upside -100%) mà KHÔNG gắn cờ, khiến
người dùng hiểu nhầm công ty "vô giá trị" thay vì "net debt vượt EV theo
multiple hiện tại" (VD: VJC — nợ thuê tài chính máy bay vốn hóa rất lớn).
"""
import pytest

from valuation.engine.models.ev_ebitda import EVEBITDAValuationModel


def test_negative_equity_value_flags_and_clips_to_zero():
    """Net debt >> EV → fvps=0.0 VÀ phải gắn cờ NEGATIVE_EQUITY_VALUE_EV_EBITDA."""
    cf_dict = {
        'ebitda_history': [4000.0, 4200.0, 4400.0],  # tỷ đồng
        'total_debt': 70_000e9,        # đòn bẩy rất cao (giống VJC)
        'cash_and_equivalents': 7_000e9,
        'shares_outstanding': 600e6,
        'current_price': 139_000.0,
    }
    assumptions = {'target_ev_ebitda': 6.0, 'norm_years': 3}
    m = EVEBITDAValuationModel('TST', cf_dict, assumptions)
    res = m.perform_valuation()

    assert res['equity_value'] < 0, "fixture phải tái hiện equity value âm"
    assert res['blended_fair_value_per_share'] == 0.0
    assert "NEGATIVE_EQUITY_VALUE_EV_EBITDA" in res['flags']


def test_positive_equity_value_no_false_flag():
    """Trường hợp bình thường (equity value dương) KHÔNG được gắn cờ oan."""
    cf_dict = {
        'ebitda_history': [1000.0, 1100.0, 1200.0],
        'total_debt': 2_000e9,
        'cash_and_equivalents': 500e9,
        'shares_outstanding': 100e6,
        'current_price': 50_000.0,
    }
    assumptions = {'target_ev_ebitda': 7.0, 'norm_years': 3}
    m = EVEBITDAValuationModel('TST2', cf_dict, assumptions)
    res = m.perform_valuation()

    assert res['equity_value'] > 0
    assert res['blended_fair_value_per_share'] > 0
    assert "NEGATIVE_EQUITY_VALUE_EV_EBITDA" not in res['flags']


def test_hand_calc_ev_ebitda_normal_case():
    """Ca tính tay: EBITDA norm = mean(1000,1100,1200)=1100 tỷ; EV=1100*7=7700 tỷ;
    net_debt = 2000-500=1500 tỷ; equity=6200 tỷ; fvps=6200e9/100e6=62,000 VND."""
    cf_dict = {
        'ebitda_history': [1000.0, 1100.0, 1200.0],
        'total_debt': 2_000e9,
        'cash_and_equivalents': 500e9,
        'shares_outstanding': 100e6,
        'current_price': 50_000.0,
    }
    assumptions = {'target_ev_ebitda': 7.0, 'norm_years': 3}
    m = EVEBITDAValuationModel('TST3', cf_dict, assumptions)
    res = m.perform_valuation()

    assert res['normalized_ebitda'] == pytest.approx(1100e9)
    assert res['enterprise_value'] == pytest.approx(7700e9)
    assert res['equity_value'] == pytest.approx(6200e9)
    assert res['blended_fair_value_per_share'] == pytest.approx(62_000.0)
