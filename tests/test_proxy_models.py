"""
Test RNAV/SOTP proxy: from_pydantic chạy được, trả blended_fair_value_per_share
và GẮN CỜ VALUATION_PROXY (cảnh báo dữ liệu chỉ là ước lượng tổng quát).
"""
import pytest

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


def test_rnav_revalues_investment_property_not_residual_long_term_assets():
    """s6 F2: chỉ BĐS đầu tư thật (investment_property) được đánh giá lại; phần dư tài sản dài hạn
    (phải thu dài hạn, đầu tư liên kết, XDCB...) thì KHÔNG."""
    base = _company()
    residual = _company()
    residual.historical_bs[-1].other_long_term_assets = 5000.0
    ip = _company()
    ip.historical_bs[-1].investment_property = 5000.0
    fv = {k: RNAVValuationModel.from_pydantic(c).perform_valuation()["rnav_fvps"]
          for k, c in (("base", base), ("residual", residual), ("ip", ip))}
    assert fv["residual"] == fv["base"]
    assert fv["ip"] > fv["base"]


def test_rnav_proxy_hand_calc_after_tax():
    """Ca tay (chẩn đoán RNAV F2+F3b): VCSH mẹ 600 tỷ, 100 triệu cp, tồn kho 400, BĐS đầu tư 100,
    phần dư dài hạn 500 (gồm 400 phải thu dài hạn), premium 0,2, thuế 20%, chiết khấu 0,4.
    Thặng dư = (400 + 100) × 0,2 = 100; sau thuế 80; sau chiết khấu 48 → FV = 648 tỷ / 100tr = 6.480đ.
    (Code cũ: (400 + 500) × 0,2 × 0,6 = 108 → 7.080đ.)"""
    c = _company()
    c.historical_bs[-1].investment_property = 100.0
    c.historical_bs[-1].other_long_term_assets = 500.0
    c.assumptions.rnav_revaluation_premium = 0.2
    c.assumptions.rnav_discount = 0.4
    res = RNAVValuationModel.from_pydantic(c).perform_valuation()
    assert res["rnav_fvps"] == pytest.approx(6_480.0)
    assert res["nav_equity_before_discount"] == pytest.approx(680e9)  # 600 + 80 sau thuế, trước chiết khấu


def test_rnav_proxy_assumptions_come_from_config(monkeypatch):
    """s6 F3a: config proxy_valuation thực sự có tác dụng (trước đây mặc định Pydantic 0,2/0,4 che config 0,30)."""
    from valuation.config import load_defaults

    cfg = load_defaults()["proxy_valuation"]
    monkeypatch.setitem(cfg, "rnav_land_premium", 0.25)
    monkeypatch.setitem(cfg, "rnav_discount", 0.5)
    c = _company()  # Assumptions dựng SAU khi đổi config → nhận mặc định mới
    assert c.assumptions.rnav_revaluation_premium == 0.25
    # Thặng dư = 400 × 0,25 × 0,8 × 0,5 = 40 → (600 + 40) tỷ / 100tr = 6.400đ
    res = RNAVValuationModel.from_pydantic(c).perform_valuation()
    assert res["rnav_fvps"] == pytest.approx(6_400.0)


def test_repo_maps_investment_properties_line():
    """repo nạp dòng investment_properties vào BalanceSheet.investment_property (VHM: BĐS đầu tư ~15,9 nghìn tỷ,
    nhỏ hơn nhiều phần dư tài sản dài hạn ~410 nghìn tỷ mà proxy cũ đánh giá lại)."""
    from valuation.data_access.repo import build_company_data
    from valuation.db.session import SessionLocalRead

    db = SessionLocalRead()
    try:
        bs = build_company_data(db, "VHM", mode="TTM", fetch_live=False).historical_bs[-1]
    finally:
        db.close()
    assert 0 < bs.investment_property < 0.2 * bs.other_long_term_assets
