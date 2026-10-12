"""Cầu nối EV → vốn CSH, vốn cổ đông mẹ, và không bịa số khi thiếu dữ liệu.

Số liệu tính tay; đơn vị đồng trừ khi ghi chú.
"""
import pytest

from valuation.engine.models.dcf import DCFValuationModel
from valuation.engine.models.ev_ebitda import EVEBITDAValuationModel
from valuation.data_access.repo import unexplained_current_assets
from valuation.models.financials import BalanceSheet

SHARES = 200e6


def _dcf(non_operating=0.0, revenue=4_000e9, growth=None):
    cf = {
        "total_equity": 5_000e9, "total_assets": 8_000e9,
        "cash_and_equivalents": 1_000e9, "total_debt": 500e9,
        "minority_interest": 0.0, "non_operating_assets": non_operating,
        "total_revenue": revenue, "cogs": 2_800e9, "ebitda": 800e9,
        "shares_outstanding": SHARES, "current_price": 50_000.0,
    }
    ass = {
        "cost_of_equity": 0.12, "wacc": 0.11,
        "revenue_growth": growth or [0.10] * 5,
        "ebit_margin": [0.15] * 5, "tax_rate": 0.20, "capex_to_revenue": [0.05] * 5,
        "depr_to_revenue": [0.04] * 5, "dso": [30.0] * 5, "dio": [30.0] * 5,
        "dpo": [30.0] * 5, "interest_rate": [0.08] * 5, "debt_repayment_rate": [0.2] * 5,
        "new_borrowing_rate": [0.05] * 5, "target_ev_ebitda": 8.0,
        "long_term_growth": 0.02, "weight_dcf": 0.5,
    }
    return DCFValuationModel("TST", cf, ass)


def test_dcf_bridge_adds_long_term_investments_to_both_legs():
    # +1.000 tỷ đầu tư liên kết/dài hạn → +1.000e9 / 200e6 = +5.000đ/cp ở mỗi chân.
    base = _dcf().perform_valuation()
    with_inv = _dcf(non_operating=1_000e9).perform_valuation()
    assert with_inv["dcf_fvps"] - base["dcf_fvps"] == pytest.approx(5_000.0)
    assert with_inv["multiples_fvps"] - base["multiples_fvps"] == pytest.approx(5_000.0)


def test_dcf_refuses_to_invent_revenue():
    # Trước đây doanh thu 0 bị thay bằng 100.000 tỷ đồng.
    with pytest.raises(ValueError, match="MISSING_FINANCIAL_INPUT"):
        _dcf(revenue=0.0).perform_valuation()


def test_dcf_uses_every_forecast_year():
    # Người dùng sửa tăng trưởng năm 2 → doanh thu năm 2 phải đổi (trước đây bị bỏ qua).
    flat = _dcf().forecast_drivers()["forecasts"]
    edited = _dcf(growth=[0.10, 0.30, 0.10, 0.10, 0.10]).forecast_drivers()["forecasts"]
    assert flat[0]["revenue"] == pytest.approx(edited[0]["revenue"])
    assert edited[1]["revenue"] == pytest.approx(4_000e9 * 1.10 * 1.30)
    assert flat[1]["revenue"] == pytest.approx(4_000e9 * 1.10 * 1.10)


def test_ev_ebitda_cyclical_midcycle_margin_and_bridge():
    # Biên EBITDA 10%, 15%, 20% → trung vị 15% × DT TTM 2.000 tỷ = 300 tỷ.
    # EV = 300 × 5 = 1.500 tỷ; nợ ròng 400 tỷ; +200 tỷ đầu tư dài hạn → VCSH 1.300 tỷ.
    # FV = 1.300e9 / 100e6 = 13.000đ.
    cf = {
        "ebitda_history": [100.0, 300.0, 400.0], "revenue_history": [1000.0, 2000.0, 2000.0],
        "total_debt": 500e9, "cash_and_equivalents": 100e9, "minority_interest": 0.0,
        "non_operating_assets": 200e9, "shares_outstanding": 100e6, "current_price": 10_000.0,
    }
    m = EVEBITDAValuationModel("TSTC", cf, {"target_ev_ebitda": 5.0, "norm_years": 5, "cyclical": True})
    r = m.perform_valuation()
    assert r["normalized_ebitda"] == pytest.approx(300e9)
    assert r["blended_fair_value_per_share"] == pytest.approx(13_000.0)


def test_parent_equity_excludes_minority_interest():
    # FPT FY2025: VCSH 43.748 tỷ gồm CĐKKS 7.265 tỷ → vốn cổ đông mẹ 36.483 tỷ.
    bs = BalanceSheet(
        year=2025, cash_and_equivalents=10_522, receivables=14_402, inventory=2_194,
        other_current_assets=31_019, fixed_assets=17_289, other_long_term_assets=12_716,
        total_assets=88_142, short_term_debt=19_170, accounts_payable=3_837,
        other_current_liabilities=18_518, long_term_debt=0, other_long_term_liabilities=2_869,
        total_equity=43_748, minority_interest=7_265, long_term_investments_net=4_738,
    )
    assert bs.parent_equity == pytest.approx(36_483)


def test_unexplained_current_assets_flags_missing_deposit_line():
    # FPT 2025 trước khi sửa: tiền 10.522, phải thu 14.402, tồn kho 2.194, ĐTNH 0,
    # phần dư 31.019 / 58.137 = 53% → nghi mất dòng (thực tế là 29.631 tỷ tiền gửi).
    assert unexplained_current_assets(10_522, 0, 14_402, 2_194, 31_019)
    # Sau khi sửa: ĐTNH 29.631, phần dư còn ~1.388 (2,4%) → không cờ.
    assert not unexplained_current_assets(10_522, 29_631, 14_402, 2_194, 1_388)
