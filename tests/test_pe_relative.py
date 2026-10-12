"""
Test P/E relative (Phase 2): EPS CHUẨN HÓA median lịch sử × P/E mục tiêu ngành.
Guardrail: chống nhiễu lợi nhuận 1 năm; LN âm → không ra số rác.
"""
import pytest
from valuation.engine.models.pe_relative import PERelativeValuationModel


def _pe(ni_history, sector="Dệt may/TS", shares=200e6, price=50000):
    cf = {"net_income_history": ni_history, "shares_outstanding": shares, "current_price": price}
    a = {"target_pe": PERelativeValuationModel._target_pe(sector), "norm_years": 3}
    return PERelativeValuationModel("ZZPE", cf, a)


def test_pe_uses_median_not_latest():
    # LN [100, 120, 500] (500 là năm đột biến) → median 3 năm = 120, không lấy 500.
    m = _pe([100.0, 120.0, 500.0])
    r = m.perform_valuation()
    # eps = median(120)*1e9 / 200e6 = 600 VND; FV = 600 * 8 (dệt may) = 4800
    assert r["normalized_eps"] == pytest.approx(120e9 / 200e6, rel=1e-9)
    assert r["blended_fair_value_per_share"] == pytest.approx(120e9 / 200e6 * 8.0, rel=1e-9)


def test_pe_flags_cyclical_spike():
    m = _pe([100.0, 110.0, 300.0])  # năm gần vọt
    assert "EARNINGS_NORMALIZED_CYCLICAL" in m.perform_valuation()["flags"]


def test_pe_negative_earnings_no_garbage():
    m = _pe([-50.0, -30.0, -40.0])
    r = m.perform_valuation()
    assert r["blended_fair_value_per_share"] == 0.0
    assert "PE_DISABLED_TTM_LOSS" in r["flags"]


def test_pe_disabled_when_ttm_loss_even_if_median_positive():
    # Luật vàng #2: DN không chu kỳ đang lỗ TTM → không dùng P/E dù median dương.
    r = _pe([100.0, 120.0, -10.0]).perform_valuation()
    assert r["blended_fair_value_per_share"] == 0.0
    assert "PE_DISABLED_TTM_LOSS" in r["flags"]


def _pe_cyclical(ni, rev, shares=200e6):
    cf = {"net_income_history": ni, "revenue_history": rev,
          "shares_outstanding": shares, "current_price": 50000}
    return PERelativeValuationModel("ZZCY", cf, {"target_pe": 8.0, "norm_years": 5, "cyclical": True})


def test_pe_cyclical_uses_midcycle_margin_times_ttm_revenue():
    # Biên: -5%, 10%, 10% → trung vị 10% (GỒM năm lỗ) × DT TTM 2.000 tỷ = 200 tỷ.
    # EPS = 200e9 / 200e6 = 1.000đ; FV = 1.000 × 8 = 8.000đ.
    # (Cách cũ: median LN tuyệt đối = 100 tỷ → 4.000đ, định giá thấp DN đang lớn.)
    r = _pe_cyclical([-50.0, 100.0, 200.0], [1000.0, 1000.0, 2000.0]).perform_valuation()
    assert r["normalized_eps"] == pytest.approx(1000.0)
    assert r["blended_fair_value_per_share"] == pytest.approx(8000.0)


def test_pe_cyclical_ttm_loss_uses_midcycle_with_flag():
    # Biên 10%, 10%, -2% → trung vị 10% × DT TTM 1.000 tỷ = 100 tỷ → EPS 500 → FV 4.000.
    r = _pe_cyclical([100.0, 150.0, -20.0], [1000.0, 1500.0, 1000.0]).perform_valuation()
    assert r["blended_fair_value_per_share"] == pytest.approx(4000.0)
    assert "PE_ON_MIDCYCLE_EARNINGS_TTM_LOSS" in r["flags"]


def test_pe_sector_target():
    assert PERelativeValuationModel._target_pe("Dệt may/TS") == 8.0
    assert PERelativeValuationModel._target_pe("Xây dựng") == 9.0
    assert PERelativeValuationModel._target_pe("Dược") == 13.0
