"""
Test RNAV/SOTP proxy: from_pydantic chạy được, trả blended_fair_value_per_share
và GẮN CỜ VALUATION_PROXY (cảnh báo dữ liệu chỉ là ước lượng tổng quát).
"""
from valuation.models.financials import (
    Company, IncomeStatement, BalanceSheet, CashFlow, Assumptions,
)
from valuation.engine.models.rnav import RNAVValuationModel
from valuation.engine.models.sotp import SOTPValuationModel


def _company():
    is_ = IncomeStatement(year=2025, revenue=1000, cogs=700, gross_profit=300,
                          opex=100, ebit=200, interest_expense=10, tax=20, net_income=150)
    bs = BalanceSheet(year=2025, cash_and_equivalents=100, receivables=50, inventory=400,
                      other_current_assets=0, fixed_assets=300, other_long_term_assets=0,
                      total_assets=950, short_term_debt=100, accounts_payable=50,
                      other_current_liabilities=0, long_term_debt=200,
                      other_long_term_liabilities=0, total_equity=600)
    a = Assumptions(revenue_growth=[0.1]*5, ebit_margin=[0.2]*5, capex_to_revenue=[0.05]*5,
                    depr_to_revenue=[0.04]*5, dso=[30]*5, dio=[30]*5, dpo=[30]*5,
                    interest_rate=[0.06]*5, debt_repayment_rate=[0.2]*5, new_borrowing_rate=[0.05]*5)
    return Company(ticker="ZZTEST", name="Test", sector="BĐS", current_price=50000,
                   shares_outstanding=100, historical_is=[is_], historical_bs=[bs],
                   historical_cf=[CashFlow(year=2025, cfo=150, capex=50)], assumptions=a)


def test_rnav_proxy_blended_and_flag():
    m = RNAVValuationModel.from_pydantic(_company())
    res = m.perform_valuation()
    assert res["blended_fair_value_per_share"] > 0
    assert "VALUATION_PROXY" in res["flags"]
    assert "VALUATION_PROXY" in m.valuation_warnings


def test_sotp_proxy_blended_and_flag():
    m = SOTPValuationModel.from_pydantic(_company())
    res = m.perform_valuation()
    assert res["blended_fair_value_per_share"] > 0
    assert "VALUATION_PROXY" in res["flags"]
    assert "VALUATION_PROXY" in m.valuation_warnings


def test_proxy_greeks_path_returns_base_fv():
    """calculate_greeks (base) phải lấy được base_fair_value từ blended_fair_value_per_share."""
    m = RNAVValuationModel.from_pydantic(_company())
    g = m.calculate_greeks()
    assert g["base_fair_value"] > 0


def test_sotp_earnings_based_not_book(_=None):
    """SOTP v2: holding asset-light ROE cao → định giá theo LN, KHÔNG hụt về book×(1-discount)."""
    c = _company()
    # equity nhỏ (600 tỷ) nhưng LN cao (150 tỷ → ROE 25%): earnings-based phải vượt xa book.
    res = SOTPValuationModel.from_pydantic(c).perform_valuation()
    assert res["earnings_value_per_share"] > res["nav_per_share"]
    # FV phải bám earnings (không phải book×0.9 = ~5,400)
    assert res["blended_fair_value_per_share"] > res["nav_per_share"]


def test_rnav_revalues_investment_property():
    """RNAV v2: BĐS đầu tư (other_long_term_assets) cũng được đánh giá lại, không chỉ tồn kho."""
    base = _company()
    # Cùng công ty nhưng thêm BĐS đầu tư lớn → RNAV phải cao hơn.
    rich = _company()
    rich.historical_bs[-1].other_long_term_assets = 5000.0
    fv_base = RNAVValuationModel.from_pydantic(base).perform_valuation()["rnav_fvps"]
    fv_rich = RNAVValuationModel.from_pydantic(rich).perform_valuation()["rnav_fvps"]
    assert fv_rich > fv_base
