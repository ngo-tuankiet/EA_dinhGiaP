"""DCF phi tài chính (nâng cấp 19/10/2026, bước s4): thuế suất hiệu dụng theo LNTT báo cáo, nhánh P/E
trailing × LN TTM, XDCB dở dang (CIP) nhất quán hai chân, doanh thu trên vốn.

Số liệu tính tay; đơn vị đồng trừ khi ghi chú (repo: tỷ đồng).
"""

from types import SimpleNamespace as N

import pytest

from valuation.data_access import repo
from valuation.engine.models.dcf import DCFValuationModel
from valuation.models.financials import IncomeStatement

SHARES = 100e6


def _is(year: int, tax: float, pbt: float | None) -> IncomeStatement:
    return IncomeStatement(
        year=year, revenue=1.0, cogs=0.0, gross_profit=1.0, opex=0.0, ebit=1.0,
        interest_expense=0.0, tax=tax, net_income=1.0, pbt=pbt,
    )


# --- F1: thuế suất hiệu dụng = Σthuế / ΣLNTT báo cáo -------------------------------------------


def test_effective_tax_pooled_over_profitable_years_mwg():
    # MWG FY2023–2025 (tỷ): thuế 522 + 1.092 + 1.560 = 3.174; LNTT 690 + 4.826 + 8.633 = 14.149
    # → 22,43%. Trung bình đơn của từng năm (cũ) bị năm đáy 2023 (76%) kéo lên trần 25%.
    hist = [_is(2023, 522, 690), _is(2024, 1_092, 4_826), _is(2025, 1_560, 8_633)]
    assert repo.effective_tax_rate(hist) == pytest.approx(3_174 / 14_149)
    assert repo.effective_tax_rate(hist) == pytest.approx(0.2243, abs=1e-4)


def test_effective_tax_skips_loss_year_frt():
    # FRT: 2023 LNTT −294 bị bỏ; 3 năm có lãi gần nhất (88 + 119 + 235)/(486 + 527 + 1.219) = 19,80%.
    hist = [_is(2022, 120, 600), _is(2023, 20, -294), _is(2024, 88, 486), _is(2025, 119, 527),
            _is(2026, 235, 1_219)]
    assert repo.effective_tax_rate(hist) == pytest.approx(442 / 2_232)


def test_effective_tax_clamped_and_missing_pbt():
    # 40/100 = 40% → kẹp trần dải cấu hình 25%; 1/100 = 1% → sàn 5%.
    assert repo.effective_tax_rate([_is(2024, 40, 100), _is(2025, 40, 100)]) == pytest.approx(0.25)
    assert repo.effective_tax_rate([_is(2024, 1, 100), _is(2025, 1, 100)]) == pytest.approx(0.05)
    # < 2 năm có LNTT dương (thiếu dòng hoặc lỗ) → None: caller dùng cách cũ + cờ TAX_FALLBACK_EBIT.
    assert repo.effective_tax_rate([_is(2024, 10, None), _is(2025, 10, 50)]) is None


# --- XDCB dở dang: doanh thu trên vốn ---------------------------------------------------------


def test_sales_to_capital_excludes_cip_nkg():
    # NKG Q2/2026 (tỷ): vốn = 7.651 + 8.554 − 117 − 3.173 − 54 = 12.861; loại CIP 5.149 → 7.712.
    # 14.321 / 7.712 = 1,857 (Damodaran Steel 01/2026: 1,80); gồm CIP chỉ 1,114.
    assert repo.sales_to_capital(14_321, 7_651, 8_554, 117, 3_173, 54, cip=5_149) == pytest.approx(
        14_321 / 7_712
    )
    assert repo.sales_to_capital(14_321, 7_651, 8_554, 117, 3_173, 54) == pytest.approx(14_321 / 12_861)


# --- XDCB dở dang: cầu nối EV hoạt động hai chân ----------------------------------------------


def _dcf(cip: float = 0.0, secondary: str = "EV_EBITDA", ni_hist=None, target_pe: float = 10.0,
         cyclical: bool = False, revenue_history=None) -> DCFValuationModel:
    cf = {
        "total_equity": 5_000e9, "total_assets": 8_000e9, "cash_and_equivalents": 1_000e9,
        "total_debt": 500e9, "minority_interest": 0.0, "non_operating_assets": 0.0,
        "construction_in_progress": cip,
        "total_revenue": 4_000e9, "cogs": 2_800e9, "ebitda": 800e9,
        "shares_outstanding": SHARES, "current_price": 50_000.0,
        "net_income_history": ni_hist or [], "revenue_history": revenue_history or [],
    }
    ass = {
        "cost_of_equity": 0.12, "wacc": 0.11, "revenue_growth": [0.10] * 5,
        "ebit_margin": [0.15] * 5, "tax_rate": 0.20, "capex_to_revenue": [0.05] * 5,
        "depr_to_revenue": [0.04] * 5, "dso": [30.0] * 5, "dio": [30.0] * 5, "dpo": [30.0] * 5,
        "interest_rate": [0.08] * 5, "debt_repayment_rate": [0.2] * 5,
        "new_borrowing_rate": [0.05] * 5, "target_ev_ebitda": 8.0, "target_pe": target_pe,
        "long_term_growth": 0.04, "weight_dcf": 0.5, "secondary_multiple": secondary,
        "cyclical": cyclical,
    }
    return DCFValuationModel("TST", cf, ass)


def test_cip_added_at_book_to_both_legs():
    # CIP 300 tỷ / 100 triệu cp = 3.000đ cộng vào CẢ chân DCF lẫn chân EV/EBITDA (bội số đo trên EV
    # hoạt động đã loại CIP từng năm → phải cộng CIP hiện tại ở cầu nối).
    base, with_cip = _dcf().perform_valuation(), _dcf(cip=300e9).perform_valuation()
    assert with_cip["dcf_fvps"] - base["dcf_fvps"] == pytest.approx(3_000.0)
    assert with_cip["multiples_fvps"] - base["multiples_fvps"] == pytest.approx(3_000.0)
    assert with_cip["construction_in_progress"] == pytest.approx(300e9)


def test_operating_ev_multiple_round_trip_closes():
    # Vốn hóa 1.000, nợ ròng 500, CIP 300, EBITDA 100 (tỷ). Bội số EV hoạt động = (1.000 + 500 − 300)/100
    # = 12x (cũ 15x). Định giá lại với 12x: 1.200 − 500 + 300 = 1.000 = vốn hóa (vòng kiểm tra khép);
    # cách ngây thơ 15x + CIP ra 1.300 (đếm trùng 300).
    b = N(short_term_debt=500.0, long_term_debt=0.0, cash_and_equivalents=0.0,
          short_term_financial_investments=0.0, minority_interest=0.0, long_term_investments_net=0.0,
          construction_in_progress=300.0)
    i = N(year=2026, ebit=100.0, net_income=50.0)
    company = N(historical_is=[i], historical_bs=[b], historical_cf=[N(year=2026, depreciation=0.0)],
                current_price=10_000.0, shares_outstanding=100.0)  # 10.000đ × 100 triệu cp = 1.000 tỷ
    assert repo.operating_ev_bridge(b) == pytest.approx(200.0)
    multiple = repo.current_multiples(company)["ev_ebitda"]
    assert multiple == pytest.approx(12.0)
    m = _dcf(cip=300e9)
    m.current_financials.update(total_debt=500e9, cash_and_equivalents=0.0, ebitda=100e9)
    m.assumptions["target_ev_ebitda"] = multiple
    res = m.perform_valuation()
    assert res["multiples_fvps"] * SHARES == pytest.approx(1_000e9)


def test_cip_dominates_value_flag_and_gate(monkeypatch):
    import valuation.config as cfg_mod
    import valuation.report.verified_summary as vs
    from valuation.engine.valuate import _apply_publication_gate

    # Vốn chủ DCF trước CIP = X; CIP lớn tới mức chiếm > dcf.cip_share_review (0,5) vốn chủ sau cộng.
    m0 = _dcf()
    eq0 = m0.perform_valuation()["dcf_fvps"] * SHARES
    cip = 2 * eq0  # sau cộng: 3·eq0, tỷ trọng CIP 2/3 > 0,5
    m = _dcf(cip=cip)
    m.perform_valuation()
    assert "CIP_DOMINATES_VALUE" in m.valuation_warnings
    small = _dcf(cip=0.5 * eq0)  # 0,5/1,5 = 1/3 < 0,5
    small.perform_valuation()
    assert "CIP_DOMINATES_VALUE" not in small.valuation_warnings

    # Cô lập cổng: company giả không có BCTC sẽ luôn bị chặn bởi MISSING_IS/MISSING_BS (fx1) → tắt kiểm
    # tra dữ liệu và hold sự kiện; ca đối chứng không cờ phải được công bố.
    monkeypatch.setattr(vs, "run_deterministic_checks", lambda *a, **k: [])
    monkeypatch.setattr(cfg_mod, "active_event_hold", lambda *a, **k: None)
    company = N(ticker="ZZZ", current_price=10.0, shares_outstanding=1.0, historical_is=[],
                historical_bs=[], data_flags=[], sector="", warnings=[],
                assumptions=N(ai_inputs_verified=False))
    control = _apply_publication_gate(company, {"blended_fair_value_per_share": 11.0, "flags": []})
    assert control["publication_allowed"] is True
    res = _apply_publication_gate(company, {"blended_fair_value_per_share": 11.0,
                                            "flags": ["CIP_DOMINATES_VALUE"]})
    assert res["publication_allowed"] is False and res["recommendation"] == "NOT_RATED"


# --- F3: nhánh P/E phụ = P/E trailing × LN trailing ---------------------------------------------


def test_pe_leg_uses_ttm_earnings_frt():
    # LN [318; 795; 1.137] tỷ, P/E 20,8x, 179 triệu cp: TTM → 1.137e9 × 20,8 / 179e6 = 132.121đ;
    # trung vị 3 năm (cũ) → 795e9 × 20,8 / 179e6 = 92.380đ.
    ni = [318e9, 795e9, 1_137e9]
    m = _dcf(secondary="PE", ni_hist=ni, target_pe=20.8)
    m.current_financials["shares_outstanding"] = 179e6
    res = m.perform_valuation()
    assert res["multiples_fvps"] == pytest.approx(1_137e9 * 20.8 / 179e6)
    assert res["multiples_fvps"] == pytest.approx(132_121, abs=1)
    assert "PE_LEG_TTM" in m.valuation_warnings


def test_pe_leg_median3_rollback(monkeypatch):
    from valuation.config import load_defaults

    monkeypatch.setitem(load_defaults()["dcf"], "pe_leg_earnings", "MEDIAN3")
    m = _dcf(secondary="PE", ni_hist=[318e9, 795e9, 1_137e9], target_pe=20.8)
    m.current_financials["shares_outstanding"] = 179e6
    assert m.perform_valuation()["multiples_fvps"] == pytest.approx(92_380, abs=1)


def test_pe_leg_cyclical_is_rejected_not_dead_code():
    # fx2: routing không bao giờ cho mã chu kỳ dùng chân P/E phụ (dcf_secondary_multiple chỉ trả PE cho
    # Compounder/Retail) → bỏ nhánh LN giữa chu kỳ (code chết), báo lỗi rõ nếu routing đổi.
    m = _dcf(secondary="PE", ni_hist=[10e9, 2e9, 6e9, 8e9], revenue_history=[100e9, 100e9, 100e9, 200e9],
             cyclical=True)
    with pytest.raises(ValueError, match="PE_LEG_CYCLICAL_UNSUPPORTED"):
        m.perform_valuation()
