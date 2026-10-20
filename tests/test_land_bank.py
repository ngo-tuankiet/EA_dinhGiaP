"""
Test Land Bank Add-on — cộng giá trị quỹ đất chưa phản ánh trong BCTC vào fair
value chính (DCF/EV_EBITDA/PE/...), độc lập với phương pháp.

Ca tính tay: 100ha × 10,000 m2/ha × 3,000,000 VND/m2 = 3,000 tỷ đồng; giá sổ 0; thuế TNDN 20%;
100% sở hữu; thu ngay năm hiện tại (t=0) → (3,000 − 0) × 0,8 = 2,400 tỷ đồng.
"""
import datetime

import pytest

from valuation.engine.land_bank import compute_land_bank_value_per_share
from valuation.models.financials import (
    Assumptions, BalanceSheet, CashFlow, Company, IncomeStatement
)


def _make_company(land_bank_projects=None, shares_million=100.0):
    ass = Assumptions(
        risk_free_rate=0.045, beta=1.0, erp=0.082, cost_of_debt=0.075, tax_rate=0.20,
        revenue_growth=[0.08] * 5, ebit_margin=[0.15] * 5,
        capex_to_revenue=[0.05] * 5, depr_to_revenue=[0.04] * 5,
        dso=[30.0] * 5, dio=[30.0] * 5, dpo=[30.0] * 5, interest_rate=[0.075] * 5,
        terminal_growth_rate=0.02, target_ev_ebitda=7.0, weight_dcf=0.5,
        land_bank_projects=land_bank_projects or [],
    )
    is_ = IncomeStatement(year=2025, revenue=1000.0, cogs=700.0, gross_profit=300.0,
                          opex=150.0, ebit=150.0, interest_expense=10.0, tax=28.0,
                          net_income=112.0)
    bs = BalanceSheet(year=2025, cash_and_equivalents=100.0, receivables=80.0,
                      inventory=120.0, other_current_assets=0.0, fixed_assets=400.0,
                      other_long_term_assets=0.0, total_assets=700.0,
                      short_term_debt=100.0, accounts_payable=60.0,
                      other_current_liabilities=0.0, long_term_debt=100.0,
                      other_long_term_liabilities=0.0, total_equity=440.0)
    cf = CashFlow(year=2025, cfo=100.0, capex=40.0, depreciation=40.0)
    return Company(ticker="TST", name="Test Corp", sector="Cao su/NN",
                   current_price=30_000.0, shares_outstanding=shares_million,
                   historical_is=[is_], historical_bs=[bs],
                   historical_cf=[cf], assumptions=ass)


def test_empty_land_bank_no_effect():
    """Mặc định rỗng -> add-on = 0, không ảnh hưởng gì (an toàn cho mã không có đất)."""
    c = _make_company(land_bank_projects=[])
    res = compute_land_bank_value_per_share(c)
    assert res["land_bank_npv"] == 0.0
    assert res["land_bank_value_per_share"] == 0.0
    assert res["flags"] == []


def test_hand_calc_single_project_no_discount():
    """100ha × 3,000,000 VND/m2, giá sổ 0, thuế 20%, 100% sở hữu, thu năm nay (t=0) = 2,400 tỷ đồng."""
    this_year = datetime.date.today().year
    c = _make_company(
        land_bank_projects=[{
            "ten": "Test KCN", "dien_tich_ha": 100, "gia_boi_thuong_vnd_m2": 3_000_000,
            "ty_le_so_huu": 100, "nam_thu_tien": this_year, "gia_tri_so_sach_ty": 0,
        }],
        shares_million=100.0,
    )
    res = compute_land_bank_value_per_share(c)
    assert res["land_bank_npv"] == pytest.approx(2_400_000_000_000.0)
    # per share = 2,400 tỷ / 100 triệu cp = 24,000 VND/cp
    assert res["land_bank_value_per_share"] == pytest.approx(24_000.0)
    assert res["flags"] == ["LAND_BANK_VALUE_ADDED"]


def test_book_value_and_tax_not_double_counted():
    """Ca tay chẩn đoán RNAV F8: 10 ha × 5,000,000 VND/m2 = 500 tỷ; giá sổ 100 tỷ (đã nằm trong VCSH);
    thuế 20%; 100% sở hữu; thu năm nay → (500 − 100) × 0,8 = 320 tỷ (code cũ: 500 tỷ)."""
    c = _make_company(land_bank_projects=[{
        "ten": "X", "dien_tich_ha": 10, "gia_boi_thuong_vnd_m2": 5_000_000,
        "ty_le_so_huu": 100, "nam_thu_tien": datetime.date.today().year, "gia_tri_so_sach_ty": 100,  # noqa: DTZ011
    }])
    assert compute_land_bank_value_per_share(c)["land_bank_npv"] == pytest.approx(320e9)


def test_missing_book_value_excluded_and_flagged():
    """Thiếu giá sổ (ô trống) → không coi là 0 (cộng trùng), bỏ dòng đó và gắn cờ chặn công bố."""
    this_year = datetime.date.today().year  # noqa: DTZ011
    c = _make_company(land_bank_projects=[
        {"ten": "A", "dien_tich_ha": 10, "gia_boi_thuong_vnd_m2": 5_000_000,
         "ty_le_so_huu": 100, "nam_thu_tien": this_year, "gia_tri_so_sach_ty": 100},
        {"ten": "B", "dien_tich_ha": 50, "gia_boi_thuong_vnd_m2": 5_000_000,
         "ty_le_so_huu": 100, "nam_thu_tien": this_year, "gia_tri_so_sach_ty": float("nan")},
    ])
    res = compute_land_bank_value_per_share(c)
    assert res["land_bank_npv"] == pytest.approx(320e9)
    assert res["flags"] == ["LAND_BANK_VALUE_ADDED", "LAND_BANK_INPUT_MISSING"]


def test_ownership_ratio_and_discounting_applied():
    """Sở hữu 50% và thu tiền sau 2 năm -> giá trị giảm đúng theo tỷ lệ + chiết khấu COE."""
    this_year = datetime.date.today().year
    c = _make_company(
        land_bank_projects=[{
            "ten": "Test", "dien_tich_ha": 100, "gia_boi_thuong_vnd_m2": 3_000_000,
            "ty_le_so_huu": 50, "nam_thu_tien": this_year + 2, "gia_tri_so_sach_ty": 0,
        }],
    )
    res = compute_land_bank_value_per_share(c)
    coe = c.assumptions.risk_free_rate + c.assumptions.beta * c.assumptions.erp
    expected_npv = (100 * 10_000 * 3_000_000 * 0.8 * 0.5) / ((1 + coe) ** 2)
    assert res["land_bank_npv"] == pytest.approx(expected_npv)


def test_multiple_projects_summed():
    """Nhiều dự án cộng dồn đúng (sau thuế 20%)."""
    this_year = datetime.date.today().year
    c = _make_company(land_bank_projects=[
        {"ten": "A", "dien_tich_ha": 50, "gia_boi_thuong_vnd_m2": 2_000_000,
         "ty_le_so_huu": 100, "nam_thu_tien": this_year, "gia_tri_so_sach_ty": 0},
        {"ten": "B", "dien_tich_ha": 30, "gia_boi_thuong_vnd_m2": 5_000_000,
         "ty_le_so_huu": 100, "nam_thu_tien": this_year, "gia_tri_so_sach_ty": 0},
    ])
    res = compute_land_bank_value_per_share(c)
    expected = ((50 * 10_000 * 2_000_000) + (30 * 10_000 * 5_000_000)) * 0.8
    assert res["land_bank_npv"] == pytest.approx(expected)


def _patch_valuate(monkeypatch):
    """Giả lập route + dispatch để cô lập test khỏi DB thật."""
    from valuation.engine import valuate as valuate_mod

    monkeypatch.setattr(valuate_mod, "_route_fn", lambda t: {
        "method": "DCF", "group": "Cao su/NN", "business_nature": "Cyclical",
        "weight_primary": 1.0,
    })

    class _FakeRouter:
        def get_routing(self, ticker):
            return {"weight_primary": 1.0}

    monkeypatch.setattr(valuate_mod, "ValuationRouter", _FakeRouter, raising=False)

    def _fake_dispatch(company, method, group, macro_env=None):
        return object(), {"blended_fair_value_per_share": 20_000.0, "flags": []}

    import valuation.engine.batch as batch_mod
    monkeypatch.setattr(batch_mod, "_dispatch_nonfin", _fake_dispatch)
    return valuate_mod


def test_valuate_adds_land_bank_to_any_method(monkeypatch):
    """Add-on cộng vào blended_fair_value_per_share bất kể phương pháp chính."""
    valuate_mod = _patch_valuate(monkeypatch)
    company = _make_company(land_bank_projects=[{
        "ten": "X", "dien_tich_ha": 10, "gia_boi_thuong_vnd_m2": 1_000_000,
        "ty_le_so_huu": 100, "nam_thu_tien": datetime.date.today().year, "gia_tri_so_sach_ty": 0,
    }])
    result = valuate_mod.valuate(company)
    land_val = compute_land_bank_value_per_share(company)["land_bank_value_per_share"]
    assert result["blended_fair_value_per_share"] == pytest.approx(20_000.0 + land_val)
    assert "LAND_BANK_VALUE_ADDED" in result["flags"]


def test_valuate_blocks_when_land_bank_input_missing(monkeypatch):
    """Cờ LAND_BANK_INPUT_MISSING chặn công bố (fail-closed)."""
    valuate_mod = _patch_valuate(monkeypatch)
    company = _make_company(land_bank_projects=[{
        "ten": "X", "dien_tich_ha": 10, "gia_boi_thuong_vnd_m2": 1_000_000,
        "ty_le_so_huu": 100, "nam_thu_tien": datetime.date.today().year,  # noqa: DTZ011
    }])
    result = valuate_mod.valuate(company)
    assert result["publication_allowed"] is False
    assert "LAND_BANK_INPUT_MISSING" in result["flags"]
