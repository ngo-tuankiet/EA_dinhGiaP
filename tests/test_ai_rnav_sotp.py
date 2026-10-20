import datetime

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

def _project(**over):
    """Dự án (phần chưa ghi nhận): 100.000 m2 × (10tr − 5tr)/m2 → LN trước thuế R − C = 500 tỷ; giá sổ ròng
    200 tỷ; sở hữu 100%; thu/chi trong năm hiện tại (năm 1)."""
    this_year = datetime.date.today().year  # noqa: DTZ011 — cùng mốc năm với model
    p = {
        "ten_du_an": "A",
        "dien_tich_san_thuong_pham_m2": 100_000,
        "gia_ban_tren_m2": 10_000_000,
        "chi_phi_tren_m2": 5_000_000,
        "ty_le_so_huu": 100,
        "gia_tri_so_sach_rong_ty": 200,
        "nam_mo_ban": this_year,
        "nam_ban_giao": this_year,
    }
    p.update(over)
    return p


@pytest.mark.parametrize("discount, expected_fvps", [(0.0, 13_454.545), (0.40, 12_072.727)])
def test_rnav_math(discount, expected_fvps):
    """Ca tay chẩn đoán RNAV F5 (đẳng thức NAV): VCSH mẹ 1.000 tỷ. Tiền còn thu − chi phí còn lại = 1.000 − 300,
    giá sổ ròng 200, thuế 20% × (1.000 − 300 − 200) = 100 → dòng tiền năm 1 = 600; WACC 10% → PV 545,45.
    NAV = 1.000 + (545,45 − 200) = 1.345,45 tỷ → 13.454,5đ/cp (100tr cp). Chiết khấu 40% chỉ áp lên phần đánh
    giá lại: (1.000 + 345,45 × 0,6) / 100tr = 12.072,7đ. Tiền 1.000/nợ 500 KHÔNG cộng/trừ lần nữa (đã trong VCSH);
    code cũ ra 1.409,09 tỷ (bỏ mọi tài sản ròng khác, không thuế, chỉ đếm phần đã bán)."""
    comp = create_dummy_company(rnav_projects=[_project()])
    comp.assumptions.rnav_discount = discount
    res = RNAVValuationModel.from_pydantic(comp).perform_valuation()
    assert res["nav_equity_before_discount"] / 1e9 == pytest.approx(1_345.4545, abs=0.01)
    assert res["rnav_fvps"] == pytest.approx(expected_fvps, abs=0.01)
    assert "AI_RNAV_MODE" in res["flags"]


def test_rnav_ownership_and_unsold_units():
    """Sở hữu 60% nhân cả PV lẫn giá sổ; ty_le_da_ban không còn cắt bớt giá trị (căn chưa bán vẫn sẽ thu tiền)."""
    comp = create_dummy_company(rnav_projects=[_project(ty_le_so_huu=60, ty_le_da_ban=30)])
    comp.assumptions.rnav_discount = 0.0
    res = RNAVValuationModel.from_pydantic(comp).perform_valuation()
    assert res["nav_equity_before_discount"] / 1e9 == pytest.approx(1_000 + 0.6 * 345.4545, abs=0.01)


def test_rnav_wacc_coe_rollback(monkeypatch):
    """Config proxy_valuation.rnav_project_discount_rate = coe (cách s6): rnav_wacc None → COE = rf + β × ERP =
    0,03 + 1,0 × 0,045 = 7,5%: PV = 600 / 1,075 = 558,14. Mặc định fx2 là WACC (test_fx2_models)."""
    from valuation.config import load_defaults

    monkeypatch.setitem(load_defaults()["proxy_valuation"], "rnav_project_discount_rate", "coe")
    comp = create_dummy_company(rnav_projects=[_project()])
    comp.assumptions.rnav_wacc = None
    comp.assumptions.rnav_discount = 0.0
    res = RNAVValuationModel.from_pydantic(comp).perform_valuation()
    assert res["nav_equity_before_discount"] / 1e9 == pytest.approx(1_000 + 600 / 1.075 - 200, abs=0.01)


@pytest.mark.parametrize("drop", ["ty_le_so_huu", "gia_tri_so_sach_rong_ty", "chi_phi_tren_m2"])
def test_rnav_missing_project_input_falls_back_to_proxy(drop):
    """Thiếu sở hữu/giá sổ/chi phí (không suy từ biên LN mơ hồ) → không định giá nửa vời: giữ proxy (bị chặn)
    và báo rõ trường thiếu; không mặc định sở hữu 100%."""
    proj = _project(bien_ln_rong=20)
    proj[drop] = float("nan")  # ô trống của st.data_editor
    comp = create_dummy_company(rnav_projects=[proj])
    res = RNAVValuationModel.from_pydantic(comp).perform_valuation()
    assert "VALUATION_PROXY" in res["flags"]
    assert "AI_RNAV_MODE" not in res["flags"]
    assert any(f.startswith("RNAV_PROJECT_INPUT_MISSING") and f"A.{drop}" in f for f in res["flags"])


def _segments(equity_seg):
    return [
        {"loai_gia_tri": "EV", "gia_tri": 2, "multiple_ky_vong": 1000},  # EV = 2.000 tỷ
        {"loai_gia_tri": "Equity", "gia_tri": 500, "multiple_ky_vong": 1, **equity_seg},  # 500 tỷ
    ]


def test_sotp_math():
    """Mảng Equity là công ty LIÊN KẾT (không hợp nhất): VCSH = 2.000 − (−500) + 500 = 3.000 tỷ;
    chiết khấu 20% → 2.400 tỷ / 100tr cp = 24.000đ."""
    comp = create_dummy_company(sotp_segments=_segments({"hop_nhat": False}))
    res = SOTPValuationModel.from_pydantic(comp).perform_valuation()
    assert res["blended_fair_value_per_share"] == pytest.approx(24_000.0)
    assert "AI_SOTP_MODE" in res["flags"]


def test_sotp_consolidated_equity_segment_not_double_deducted():
    """Mảng Equity là công ty con HỢP NHẤT (stake × vốn hóa, đã sau nợ của nó): nợ vay ròng 300 và CĐKKS 80 của
    nó đã nằm trong số hợp nhất (nợ ròng −500, CĐKKS 100) → loại ra:
    2.000 − (−500 − 300) + 500 − (100 − 80) = 3.280 tỷ × 0,8 = 2.624 tỷ → 26.240đ (code cũ: 23.200đ)."""
    comp = create_dummy_company(
        sotp_segments=_segments({"hop_nhat": True, "no_vay_rong_ty": 300, "cdkks_ty": 80})
    )
    comp.historical_bs[-1].minority_interest = 100
    res = SOTPValuationModel.from_pydantic(comp).perform_valuation()
    assert res["blended_fair_value_per_share"] == pytest.approx(26_240.0)


@pytest.mark.parametrize("seg", [{}, {"hop_nhat": True, "cdkks_ty": 80}])
def test_sotp_equity_segment_missing_consolidation_input(seg):
    """Không khai hop_nhat, hoặc hợp nhất mà thiếu nợ ròng/CĐKKS của công ty con → không dùng AI_SOTP."""
    comp = create_dummy_company(sotp_segments=_segments(seg))
    res = SOTPValuationModel.from_pydantic(comp).perform_valuation()
    assert "AI_SOTP_MODE" not in res["flags"]
    assert any(f.startswith("SOTP_SEGMENT_INPUT_MISSING") for f in res["flags"])
