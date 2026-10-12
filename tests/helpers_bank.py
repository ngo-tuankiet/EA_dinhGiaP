"""Helper dựng CompanyBank tối giản cho test terminal (D29).

Tách khỏi file test để nhiều test dùng chung; mọi con số ở đây là fixture giả
đơn giản (VCSH 1.000 tỷ, 100 triệu cp) để trị số kỳ vọng tính tay được.
"""
from valuation.models.financials import GovernanceData
from valuation.models.financials_bank import (
    AssumptionsBank,
    BalanceSheetBank,
    CompanyBank,
    IncomeStatementBank,
)


def build_fake_bank(
    sustainable_roe: float = 0.16,
    coe: float | None = 0.12,
    g: float = 0.02,
    payout: float = 0.25,
    equity_ty: float = 1000.0,
    shares_tr: float = 100.0,
    price: float = 10000.0,
) -> CompanyBank:
    """Ngân hàng giả: VCSH 1.000 tỷ, 100 triệu cp -> BVPS 10.000đ."""
    bs = BalanceSheetBank(
        year=2026, customer_loans=8000.0, other_earning_assets=2000.0,
        total_assets=10000.0, customer_deposits=8500.0,
        other_liabilities=500.0, total_equity=equity_ty,
    )
    _ni = equity_ty * sustainable_roe
    is_ = IncomeStatementBank(
        year=2026, net_interest_income=500.0, non_interest_income=100.0,
        total_operating_income=600.0, operating_expenses=250.0,
        pre_provision_profit=350.0, provision_expense=50.0,
        pretax_income=_ni / 0.8, net_income=_ni,
    )
    a = AssumptionsBank(
        risk_free_rate=0.045, beta=1.0, erp=0.075, cost_of_equity=coe,
        credit_growth=[0.12] * 5, nim=[0.035] * 5, cir=[0.35] * 5,
        credit_cost=[0.01] * 5,
        dividend_payout_ratio=payout, terminal_growth_rate=g,
        sustainable_roe=sustainable_roe,
    )
    return CompanyBank(
        ticker="TESTBANK", name="Ngân hàng Test", sector="Banks",
        current_price=price, shares_outstanding=shares_tr,
        historical_bs=[bs], historical_is=[is_],
        assumptions=a, governance=GovernanceData(),
    )
