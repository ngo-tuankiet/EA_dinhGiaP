"""
Test guardrail terminal growth trong BaseValuationModel:
- Cap g <= rf (Damodaran): perpetuity không tăng nhanh hơn nền kinh tế.
- Ép spread tối thiểu WACC-g (hoặc COE-g) >= MIN_WACC_G_SPREAD để TV không phình.
"""
from valuation.engine.models.base import BaseValuationModel, MIN_WACC_G_SPREAD


def _make(assumptions, use_wacc=True):
    m = BaseValuationModel.__new__(BaseValuationModel)
    m.ticker = "ZZ_TEST"
    m.current_financials = {}
    m.assumptions = assumptions
    m.coe = assumptions.get("cost_of_equity", 0.13)
    m.wacc = assumptions.get("wacc", 0.11)
    m.g = assumptions.get("long_term_growth", 0.05)
    m.valuation_warnings = []
    m.use_wacc = use_wacc
    m.validators()
    return m


def test_no_clamp_when_safe():
    # g=4%, WACC=8%, rf=5% → spread 4% > 3%, g < rf → không clamp
    m = _make({"wacc": 0.08, "long_term_growth": 0.04, "risk_free_rate": 0.05})
    assert abs(m.g - 0.04) < 1e-9
    assert m.valuation_warnings == []


def test_cap_g_at_rf():
    # g=6% > rf=4.5% → clamp về rf
    m = _make({"wacc": 0.12, "long_term_growth": 0.06, "risk_free_rate": 0.045})
    assert abs(m.g - 0.045) < 1e-9
    assert any("CAPPED_AT_RF" in w for w in m.valuation_warnings)


def test_spread_floor_wacc():
    # g=5%, WACC=7% → spread 2% < 3% → ép g = 7% - 3% = 4%
    m = _make({"wacc": 0.07, "long_term_growth": 0.05})
    assert abs(m.g - (0.07 - MIN_WACC_G_SPREAD)) < 1e-9
    assert any("CLAMPED_SPREAD" in w for w in m.valuation_warnings)


def test_spread_floor_uses_coe_when_not_wacc():
    # Model không dùng WACC (vd RI/DDM) → spread tính theo COE
    m = _make({"cost_of_equity": 0.10, "long_term_growth": 0.09}, use_wacc=False)
    assert abs(m.g - (0.10 - MIN_WACC_G_SPREAD)) < 1e-9


def test_rf_cap_then_spread_floor_both_apply():
    # g=7% > rf=5%, sau cap còn 5%; WACC=7% → spread 2% <3% → ép xuống 4%
    m = _make({"wacc": 0.07, "long_term_growth": 0.07, "risk_free_rate": 0.05})
    assert abs(m.g - 0.04) < 1e-9
    assert len(m.valuation_warnings) == 2
