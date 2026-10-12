"""
Phase 1 — 3 guardrails tài chính:
  G1: P/B chứng khoán PHẢI link ROE/thị phần (justified P/B = f(ROE), ROE = f(share)).
  G2: EV/EBITDA hàng không/xi măng dùng EBITDA CHUẨN HÓA 3 năm (chống nhiễu chu kỳ).
  G3: DCF cyclical ép terminal margin về MID-CYCLE (không ngoại suy biên đỉnh).
"""
import pytest
from valuation.engine.models.securities import SecuritiesValuationModel
from valuation.engine.models.ev_ebitda import EVEBITDAValuationModel
from valuation.engine.models.dcf import DCFValuationModel


# ---------- G1: P/B chứng khoán link ROE/thị phần ----------
def _sec(share):
    cf = {"total_equity": 20000e9, "shares_outstanding": 1500e6}
    a = {
        "cost_of_equity": 0.13, "long_term_growth": 0.03,
        "market_liquidity_vnd_billion": 20000.0, "brokerage_market_share": share,
        "brokerage_margin": 0.0015, "margin_loans": 15000.0, "net_margin_rate": 0.05,
        "prop_trading_income": 2000.0, "opex_ratio": 0.40, "tax_rate": 0.20,
        "payout_ratio": 0.20, "weight_ri": 0.5,
    }
    return SecuritiesValuationModel("ZZSEC", cf, a)


def test_g1_pb_rises_with_market_share():
    """Thị phần môi giới ↑ → ROE ↑ → justified P/B ↑ (P/B KHÔNG cố định)."""
    lo = _sec(0.06).perform_valuation()
    hi = _sec(0.14).perform_valuation()
    assert hi["pb_fvps"] > lo["pb_fvps"], "P/B không phản ứng theo thị phần → mất link ROE"
    assert hi["blended_fair_value_per_share"] > lo["blended_fair_value_per_share"]


# ---------- G2: EV/EBITDA chuẩn hóa 3 năm ----------
def _ev(ebitda_history):
    cf = {"ebitda_history": ebitda_history, "total_debt": 0.0,
          "cash_and_equivalents": 0.0, "shares_outstanding": 1000e6, "current_price": 20000}
    a = {"target_ev_ebitda": 6.0, "norm_years": 3}
    return EVEBITDAValuationModel("ZZEV", cf, a)


def test_g2_uses_3yr_average_not_latest():
    # EBITDA có năm lỗ (-2) rồi phục hồi; chuẩn hóa = mean 3 năm gần, KHÔNG lấy 1 năm.
    m = _ev([-2.0, 10.0, 12.0, 14.0])  # tỷ đồng
    res = m.perform_valuation()
    assert res["years_averaged"] == 3
    assert res["normalized_ebitda"] == pytest.approx((10 + 12 + 14) / 3 * 1e9, rel=1e-9)


def test_g2_flags_cyclical_spike():
    # Năm gần nhất vọt mạnh khỏi mức chuẩn hóa → cờ EBITDA_NORMALIZED_CYCLICAL.
    m = _ev([8.0, 9.0, 25.0])
    assert "EBITDA_NORMALIZED_CYCLICAL" in m.perform_valuation()["flags"]


# ---------- G3: DCF cyclical terminal margin về mid-cycle ----------
def _dcf(ebit_margin, mid_cycle):
    cf = {"total_revenue": 100000e9, "cogs": 70000e9, "total_debt": 0.0,
          "cash_and_equivalents": 0.0, "shares_outstanding": 1000e6, "current_price": 30000}
    a = {"cost_of_equity": 0.12, "wacc": 0.10, "revenue_growth_1_to_3": 0.10,
         "revenue_growth_4_to_5": 0.08, "ebit_margin": ebit_margin,
         "mid_cycle_ebit_margin": mid_cycle, "tax_rate": 0.20, "capex_to_revenue": 0.05,
         "depr_to_revenue": 0.04, "dso": 30., "dio": 30., "dpo": 30., "interest_rate": 0.06,
         "debt_repayment_rate": 0.2, "new_borrowing_rate": 0.05, "long_term_growth": 0.03,
         "target_ev_ebitda": 6.0, "weight_dcf": 1.0}
    return DCFValuationModel("ZZCYC", cf, a)


def test_g3_terminal_uses_midcycle_margin():
    # Biên dự phóng 25% (đỉnh) nhưng mid-cycle 12% → terminal NOPAT theo 12%, FV thấp hơn.
    peak = _dcf(0.25, None)            # cũ: ngoại suy đỉnh
    guarded = _dcf(0.25, 0.12)         # G3: terminal về mid-cycle
    fv_peak = peak.perform_valuation()["dcf_fvps"]
    fv_guard = guarded.perform_valuation()["dcf_fvps"]
    assert fv_guard < fv_peak, "Terminal vẫn ngoại suy biên đỉnh → guardrail không hoạt động"
    assert any("CYCLICAL_TERMINAL_MIDCYCLE" in w for w in guarded.valuation_warnings)


def test_g3_no_effect_when_not_cyclical():
    # mid_cycle=None (không cyclical) → không đổi terminal, không warning.
    m = _dcf(0.15, None)
    m.perform_valuation()
    assert not any("CYCLICAL_TERMINAL_MIDCYCLE" in w for w in m.valuation_warnings)
