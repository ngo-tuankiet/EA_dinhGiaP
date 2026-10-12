import pytest
from valuation.engine.models.rnav import RNAVValuationModel
from valuation.engine.models.sotp import SOTPValuationModel
from valuation.models.financials import Company, Assumptions, BalanceSheet, IncomeStatement

def create_dummy_company(rnav_projects=None, sotp_segments=None) -> Company:
    bs = BalanceSheet(
        year=2023,
        cash_and_equivalents=1000, # 1,000 tỷ
        receivables=0,
        inventory=500,
        other_current_assets=0,
        fixed_assets=0,
        other_long_term_assets=0,
        total_assets=1500,
        short_term_debt=200,       # Tổng nợ 500
        accounts_payable=0,
        other_current_liabilities=0,
        long_term_debt=300,
        other_long_term_liabilities=0,
        total_equity=1000
    )
    # Nợ ròng = 500 - 1000 = -500 (tiền mặt ròng = 500)
    
    is_stmt = IncomeStatement(
        year=2023, revenue=1000, cogs=500, gross_profit=500,
        opex=100, ebit=400, interest_expense=50, tax=70, net_income=280
    )
    
    assumptions = Assumptions(
        risk_free_rate=0.03, beta=1.0, erp=0.045, cost_of_debt=0.06, tax_rate=0.2,
        revenue_growth=[0.05]*5, ebit_margin=[0.2]*5, capex_to_revenue=[0.05]*5,
        depr_to_revenue=[0.05]*5, dso=[30]*5, dio=[30]*5, dpo=[30]*5,
        interest_rate=[0.08]*5,
        rnav_projects=rnav_projects or [],
        sotp_segments=sotp_segments or [],
        rnav_discount=0.40,
        sotp_discount=0.20,
        rnav_wacc=0.10
    )
    
    return Company(
        ticker="DUMMY",
        name="Dummy",
        sector="Real Estate",
        current_price=10000,
        shares_outstanding=100, # 100 triệu cổ phiếu
        historical_is=[is_stmt],
        historical_bs=[bs],
        historical_cf=[],
        assumptions=assumptions
    )

def test_rnav_math():
    projects = [
        {
            "dien_tich_san_thuong_pham_m2": 100000, # 100k m2
            "gia_ban_tren_m2": 50000000, # 50tr/m2
            "bien_ln_rong": 20, # 20%
            "ty_le_so_huu": 100,
            "ty_le_da_ban": 100,
            "nam_mo_ban": 2024,
            "nam_ban_giao": 2024 # Thu 1 lần trong 1 năm
        }
    ]
    # Tổng lợi nhuận dự án = 100k * 50tr * 20% = 1,000 tỷ. 
    # Chiết khấu 1 năm với wacc 10% = 1000 / 1.1 = 909.09 tỷ
    
    comp = create_dummy_company(rnav_projects=projects)
    model = RNAVValuationModel.from_pydantic(comp)
    res = model.perform_valuation()
    
    nav_equity = res["nav_equity_before_discount"]
    assert abs(nav_equity / 1e9 - 1409.09) < 1.0 
    
    # Chiết khấu 40%
    # NAV sau chiết khấu = 1409.09 tỷ * 0.6 = 845.45 tỷ
    # rnav_fvps = 845.45 / 100tr = 8454.5 VND
    assert abs(res["rnav_fvps"] - 8454.5) < 5.0
    assert "AI_RNAV_MODE" in res["flags"]

def test_sotp_math():
    segments = [
        {
            "loai_gia_tri": "EV",
            "gia_tri": 2, # 2 tỷ
            "multiple_ky_vong": 1000 # EV = 2000 tỷ
        },
        {
            "loai_gia_tri": "Equity",
            "gia_tri": 500, # 500 tỷ
            "multiple_ky_vong": 1 # Equity = 500 tỷ
        }
    ]
    
    comp = create_dummy_company(sotp_segments=segments)
    model = SOTPValuationModel.from_pydantic(comp)
    res = model.perform_valuation()
    
    # Total EV segments = 2000 tỷ
    # Nợ ròng = -500 (tiền lớn hơn nợ)
    # Equity từ EV = 2000 - (-500) = 2500 tỷ
    # Total Equity Value = 2500 + 500 (từ equity segment) = 3000 tỷ
    
    # Discount = 20%
    # => Sau discount = 3000 * 0.8 = 2400 tỷ
    # FVPS = 2400 tỷ / 100tr cổ = 24000 VND
    
    assert abs(res["blended_fair_value_per_share"] - 24000.0) < 5.0
    assert "AI_SOTP_MODE" in res["flags"]
