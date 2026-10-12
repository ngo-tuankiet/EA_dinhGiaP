"""
Test Report Data Builder (báo cáo 11 phần chuẩn quỹ) — fixture synthetic,
không phụ thuộc DB. Ca tính tay: vốn hóa, band khuyến nghị, ROE lịch sử.
"""
import pytest

from valuation.models.financials import (
    IncomeStatement, BalanceSheet, CashFlow, Company, Assumptions
)
from valuation.report.report_data import (
    build_appendix_financials,
    build_assumptions_table,
    build_cover,
    build_historical_analysis,
    build_wacc_breakdown,
    market_cap_billion_vnd,
)


def _make_company(price: float = 50_000.0) -> Company:
    """Công ty phi tài chính 2 năm lịch sử, số tròn để tính tay."""
    years = [2023, 2024]
    hist_is = [
        IncomeStatement(year=y, revenue=1000.0 * (1 + 0.1 * i), cogs=600.0,
                        gross_profit=400.0, opex=250.0, ebit=150.0,
                        interest_expense=10.0, tax=28.0, net_income=112.0)
        for i, y in enumerate(years)
    ]
    hist_bs = [
        BalanceSheet(year=y, cash_and_equivalents=100.0, receivables=80.0,
                     inventory=120.0, other_current_assets=50.0, fixed_assets=400.0,
                     other_long_term_assets=50.0, total_assets=800.0,
                     short_term_debt=100.0, accounts_payable=60.0,
                     other_current_liabilities=40.0, long_term_debt=100.0,
                     other_long_term_liabilities=0.0, total_equity=500.0)
        for y in years
    ]
    hist_cf = [CashFlow(year=y, cfo=150.0, capex=60.0, depreciation=40.0) for y in years]
    ass = Assumptions(
        risk_free_rate=0.045, beta=1.0, erp=0.082, cost_of_debt=0.075, tax_rate=0.20,
        revenue_growth=[0.10] * 5, ebit_margin=[0.15] * 5,
        capex_to_revenue=[0.06] * 5, depr_to_revenue=[0.04] * 5,
        dso=[30.0] * 5, dio=[30.0] * 5, dpo=[30.0] * 5, interest_rate=[0.075] * 5,
        terminal_growth_rate=0.02, target_ev_ebitda=8.0, weight_dcf=0.5,
    )
    return Company(ticker="TST", name="Test Corp", sector="Consumer",
                   current_price=price, shares_outstanding=100.0,  # 100 triệu cp
                   historical_is=hist_is, historical_bs=hist_bs,
                   historical_cf=hist_cf, assumptions=ass)


def test_market_cap_hand_calc():
    """Vốn hóa = 100 triệu cp × 50,000 VND = 5,000 tỷ đồng (tính tay)."""
    c = _make_company(price=50_000.0)
    assert market_cap_billion_vnd(c) == pytest.approx(5_000.0)


def test_cover_upside_and_recommendation():
    """Cùng một nguồn khuyến nghị với UI: upside 20% < MOS mặc định 25% → NẮM GIỮ;
    upside 30% ≥ 25% → MUA."""
    c = _make_company(price=50_000.0)
    cover = build_cover(c, blended_fv=60_000.0)
    assert cover["upside"] == pytest.approx(0.20)
    assert cover["recommendation"] == "NẮM GIỮ"
    assert build_cover(c, blended_fv=65_000.0)["recommendation"] == "MUA"
    assert cover["market_cap"] == pytest.approx(5_000.0)


def test_historical_roe_hand_calc():
    """ROE = 112 / 500 = 22.4% cho mọi năm fixture."""
    c = _make_company()
    hist = build_historical_analysis(c)
    roe_row = next(r for r in hist["rows"] if r["label"] == "ROE")
    assert all(v == "22.4%" for v in roe_row["values"])
    # Chart series đầy đủ cho biểu đồ
    cs = hist["chart_series"]
    assert cs["years"] == [2023, 2024]
    assert cs["revenue"] == [1000.0, 1100.0]


def test_wacc_breakdown_contains_full_capm_chain():
    """Bóc tách WACC phi tài chính phải đủ: rf, beta, ERP, Re, Rd, weights, WACC."""
    c = _make_company()
    rows = build_wacc_breakdown(c)
    labels = " | ".join(r["label"] for r in rows)
    for needle in ("rf", "Beta", "ERP", "Re", "Rd", "WACC"):
        assert needle in labels, f"thiếu {needle} trong WACC breakdown"
    # COE = 4.5% + 1.0 × 8.2% = 12.7% (tính tay)
    coe_row = next(r for r in rows if "Re (CAPM)" in r["label"])
    assert coe_row["value"] == "12.7%"


def test_ai_facts_pair_year_with_values_and_expose_latest():
    """AI phải nhận cặp năm↔giá trị (chống gán sai năm) + số liệu MỚI NHẤT.

    Regression: trước đây truyền years/revenue thành 2 mảng rời → AI ghép nhầm
    năm và né số mới (báo ROE 'duy trì >20%' dù năm cuối đã giảm).
    """
    from valuation.report.ai_narrative import _build_facts

    sections = {
        "cover": {"ticker": "TST", "sector": "Consumer", "current_price": 50_000.0,
                  "target_price": 60_000.0, "upside": 0.20, "recommendation": "MUA",
                  "market_cap": 5_000.0},
        "historical": {"chart_series": {
            "years": [2023, 2024, 2025],
            "revenue": [1000.0, 1100.0, 1200.0],
            "net_income": [100.0, 90.0, 80.0],
            "roe": [0.22, 0.18, 0.15],   # ROE GIẢM dần → phải lộ ra số mới nhất
        }},
        "scenarios": None, "consensus": None, "flags": [],
    }
    facts = _build_facts(sections)

    # Năm mới nhất và chỉ số mới nhất phải đúng (2025, ROE 15%)
    assert facts["latest_fiscal_year"] == 2025
    assert facts["latest_roe_pct"] == 15.0
    assert facts["latest_revenue"] == 1200
    assert "report_date" in facts

    # Bảng năm↔giá trị ghép đúng cặp
    fby = facts["financials_by_year"]
    assert len(fby) == 3
    assert fby[0] == {"year": 2023, "revenue": 1000, "net_income": 100, "roe_pct": 22.0}
    assert fby[-1] == {"year": 2025, "revenue": 1200, "net_income": 80, "roe_pct": 15.0}


def test_assumptions_and_appendix_structure():
    c = _make_company()
    ass = build_assumptions_table(c)
    assert len(ass["schedule_rows"]) >= 4
    assert all(len(r["values"]) == 5 for r in ass["schedule_rows"])

    app = build_appendix_financials(c)
    assert app["headers"] == ["2023", "2024"]
    assert len(app["income_statement"]) == 8
    assert len(app["cash_flow"]) == 3  # phi tài chính có LCTT
