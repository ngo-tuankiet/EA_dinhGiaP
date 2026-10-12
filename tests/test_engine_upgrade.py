"""
Unit test for Phase 1 Engine Upgrade — Kiểm chứng lõi tính toán theo Phụ lục C của Spec.
"""
import pytest
from valuation.models.financials import Company, IncomeStatement, BalanceSheet, CashFlow, Assumptions
from valuation.models.financials_bank import CompanyBank, IncomeStatementBank, BalanceSheetBank, AssumptionsBank
from valuation.engine.forecast import forecast_company_financials
from valuation.engine.forecast_bank import forecast_bank_financials
from valuation.engine.models.dcf import DCFValuationModel
from valuation.engine.models.bank_general import BankGeneralValuationModel
from valuation.engine.relative import calculate_relative_valuation
from valuation.engine.blend import blend_intrinsic_relative
from valuation.engine.sensitivity import calculate_sensitivity_matrix, run_scenario_analysis

def create_sample_manufacturing_company() -> Company:
    """
    Tạo đối tượng Company mẫu dựa trên Phụ lục C của Spec để làm dữ liệu kiểm thử.
    """
    historical_is = [
        IncomeStatement(
            year=2025,
            revenue=1000.0,
            cogs=850.0,
            gross_profit=150.0,
            opex=0.0,
            ebit=150.0,
            interest_expense=0.0,
            tax=30.0,
            net_income=120.0
        )
    ]
    
    historical_bs = [
        BalanceSheet(
            year=2025,
            cash_and_equivalents=100.0,
            receivables=20.0,
            inventory=10.0,
            other_current_assets=0.0,
            fixed_assets=470.0,
            other_long_term_assets=0.0,
            total_assets=600.0,
            short_term_debt=100.0,
            accounts_payable=20.0,
            other_current_liabilities=80.0,
            long_term_debt=200.0,
            other_long_term_liabilities=0.0,
            total_equity=200.0  # Cố ý đặt VCSH = 200 để cân với tổng tài sản 600
        )
    ]
    
    historical_cf = [
        CashFlow(
            year=2025,
            cfo=150.0,
            capex=60.0
        )
    ]
    
    assumptions = Assumptions(
        risk_free_rate=0.035,
        beta=1.1,
        erp=0.08,
        cost_of_debt=0.08,
        tax_rate=0.20,
        revenue_growth=[0.10, 0.10, 0.10, 0.10, 0.10],
        ebit_margin=[0.15, 0.15, 0.15, 0.15, 0.15],
        capex_to_revenue=[0.06, 0.06, 0.06, 0.06, 0.06],
        depr_to_revenue=[0.05, 0.05, 0.05, 0.05, 0.05],
        dso=[30.0] * 5,
        dio=[30.0] * 5,
        dpo=[30.0] * 5,
        interest_rate=[0.06] * 5,
        terminal_growth_rate=0.03,
        target_ev_ebitda=10.0,
        weight_dcf=0.5
    )
    
    return Company(
        ticker="SAMPLE",
        name="Sample Manufacturing Company",
        sector="Manufacturing",
        current_price=60.0,
        shares_outstanding=100.0,
        historical_is=historical_is,
        historical_bs=historical_bs,
        historical_cf=historical_cf,
        assumptions=assumptions
    )

def test_wacc_calculation():
    company = create_sample_manufacturing_company()
    model = DCFValuationModel.from_pydantic(company)
    
    # COE = rf + beta*erp = 3.5% + 1.1*8% = 12.3%
    # Rd_at = 8% * (1-20%) = 6.4%
    # Market-cap weights (Damodaran standard):
    #   E = shares(100M) * current_price(60 VND) = 6,000,000,000 đồng = 6 tỷ đồng
    #   D = (100+200) tỷ * 1e9 = 300 tỷ đồng
    #   we = 6 / 306 ≈ 1.96%,  wd = 300 / 306 ≈ 98.04%
    # WACC = 12.3%*0.0196 + 6.4%*0.9804 ≈ 6.52%
    assert abs(model.coe - 0.123) < 1e-5
    assert abs(model.wacc - 0.0652) < 1e-3

def test_financials_forecast():
    company = create_sample_manufacturing_company()
    projections = forecast_company_financials(company)
    
    # 2026 Revenue = 1000 * 1.1 = 1100
    # 2030 Revenue = 1000 * (1.1^5) = 1610.51
    assert abs(projections[0]["revenue"] - 1100.0) < 1e-2
    assert abs(projections[4]["revenue"] - 1610.51) < 1e-2
    
    # EBIT 2026 = 1100 * 0.15 = 165
    assert abs(projections[0]["ebit"] - 165.0) < 1e-2

def test_fcff_forecast():
    company = create_sample_manufacturing_company()
    projections = forecast_company_financials(company)
    
    # 2026: NOPAT = 165 * 0.8 = 132, D&A = 1100*0.05 = 55, CapEx = 1100*0.06 = 66
    # NWC dùng DSO/DIO/DPO = 30 days; cogs_ratio = 850/1000 = 0.85
    # base_nwc(2025) = 1000*(30/365) + 850*(30/365) - 850*(30/365) = 1000*30/365 ≈ 82.19
    # nwc(2026) = 1100*(30/365) ≈ 90.41; delta_nwc ≈ 8.22
    # FCFF = 132 + 55 - 66 - 8.22 ≈ 112.78
    assert abs(projections[0]["fcff"] - 112.78) < 0.1

def test_dcf_valuation():
    company = create_sample_manufacturing_company()
    model = DCFValuationModel.from_pydantic(company)
    res = model.perform_valuation()
    
    assert res["dcf_fvps"] > 0
    assert res["blended_fair_value_per_share"] > 0

def test_relative_valuation():
    company = create_sample_manufacturing_company()
    rel_fv = calculate_relative_valuation(company)
    
    # EBITDA = EBIT + D&A = 150 + (depr_to_revenue[0]=0.05 × revenue=1000) = 150+50 = 200
    # EV = 200 * 10 = 2000
    # Net Debt = 300 (debt) - 100 (cash) = 200
    # Equity = 2000 - 200 = 1800
    # Shares = 100
    # FVPS = 1800 / 100 * 1000 = 18000 VND
    assert abs(rel_fv - 18000.0) < 1.0

def test_blended_and_recommendation():
    blended, upside = blend_intrinsic_relative(
        intrinsic_fv=17780.0,
        relative_fv=13200.0,
        weight_intrinsic=0.5,
        current_price=60000.0
    )
    # Blended = (17780 + 13200) / 2 = 15490 VND
    assert abs(blended - 15490.0) < 1e-2
    # Upside = (15490 - 60000) / 60000 = -74.18%
    assert abs(upside - (-74.18)) < 1e-1
    from valuation.engine.decision_engine import recommend
    assert recommend("FPT", 60000.0, blended)["recommendation"] == "SELL"


def test_blend_rejects_nan_or_negative_leg():
    import math
    for bad in (math.nan, -1.0, None):
        with pytest.raises(ValueError, match="INVALID_VALUATION_LEG"):
            blend_intrinsic_relative(bad, 13200.0, 0.5, 60000.0)

def test_bank_valuation_pb_roe():
    # Tạo CompanyBank mẫu
    historical_is = [
        IncomeStatementBank(
            year=2025,
            net_interest_income=50.0,
            non_interest_income=10.0,
            total_operating_income=60.0,
            operating_expenses=20.0,
            pre_provision_profit=40.0,
            provision_expense=10.0,
            pretax_income=30.0,
            net_income=24.0
        )
    ]
    
    historical_bs = [
        BalanceSheetBank(
            year=2025,
            customer_loans=800.0,
            other_earning_assets=200.0,
            total_assets=1000.0,
            customer_deposits=800.0,
            other_liabilities=50.0,
            total_equity=150.0
        )
    ]
    
    assumptions = AssumptionsBank(
        risk_free_rate=0.035,
        beta=1.1,
        erp=0.08,
        credit_growth=[0.12, 0.12, 0.12, 0.12, 0.12],
        nim=[0.03, 0.03, 0.03, 0.03, 0.03],
        cir=[0.35, 0.35, 0.35, 0.35, 0.35],
        credit_cost=[0.01, 0.01, 0.01, 0.01, 0.01],
        dividend_payout_ratio=0.15,
        terminal_growth_rate=0.02,
        sustainable_roe=0.18
    )
    
    bank = CompanyBank(
        ticker="VCB",
        name="Vietcombank",
        current_price=92000.0,
        shares_outstanding=100.0,
        historical_is=historical_is,
        historical_bs=historical_bs,
        assumptions=assumptions
    )
    
    model = BankGeneralValuationModel(bank)
    res = model.perform_valuation()
    
    assert res["ri_fvps"] > 0
    assert res["pb_fvps"] > 0
    assert res["blended_fair_value_per_share"] > 0

def test_sensitivity_and_scenarios():
    company = create_sample_manufacturing_company()
    
    # Test sensitivity
    x_vals, y_vals, matrix = calculate_sensitivity_matrix(company, base_x_val=0.0876, base_y_val=0.03)
    assert len(x_vals) == 5
    assert len(y_vals) == 5
    assert len(matrix) == 5
    
    # Test scenarios
    scenarios = run_scenario_analysis(company)
    assert "Base" in scenarios
    assert "Bull" in scenarios
    assert "Bear" in scenarios
    assert scenarios["Bull"] >= scenarios["Base"]
    assert scenarios["Bear"] <= scenarios["Base"]
