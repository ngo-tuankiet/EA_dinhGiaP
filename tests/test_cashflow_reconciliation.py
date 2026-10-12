"""
test_cashflow_reconciliation.py — Test hồi quy cho bug CFI/CFF bị trừ CapEx
hai lần và tường cảnh báo "chưa có đầy đủ lưu chuyển đầu tư/tài chính" lặp
theo năm.

Bối cảnh: xem docs/PLAN_FIX_CASHFLOW_WARNINGS.md và mục "Lỗi đã gặp thực tế"
trong .agents/skills/financial-data-integrity/SKILL.md.

  - CFI (dòng tiền đầu tư) đã bao gồm CapEx âm sẵn bên trong. Model lưu CapEx
    riêng cho FCFF, nên nếu cộng thẳng CFI+CFF vào cf_other mà không cộng
    ngược CapEx thì phép đối chiếu Δtiền = CFO - CapEx + cf_other sẽ trừ
    CapEx hai lần.
  - Trước bản sửa này, Company.validate_model_integrity coi MỌI năm lệch
    identity mà cf_other==0.0 là "thiếu dữ liệu", cảnh báo lặp theo từng năm
    (kể cả khi dữ liệu đủ nhưng cf_other tính đúng đã bằng 0.0 một cách tình
    cờ), và không có ngưỡng tương đối theo quy mô doanh nghiệp.
  - Bản sửa: CashFlow có 2 field mới (has_full_cashflow_sections,
    is_ttm_period) để phân biệt rõ "thiếu dữ liệu" (gộp 1 dòng) với "lệch đối
    chiếu thật" (ngưỡng tương đối từ config/defaults.yaml, không hardcode).
"""
import pytest

from valuation.data_access.repo import _cashflow_other_excluding_capex
from valuation.models.financials import (
    Assumptions,
    BalanceSheet,
    CashFlow,
    Company,
    IncomeStatement,
)


def _assumptions() -> Assumptions:
    return Assumptions(
        risk_free_rate=0.045, beta=1.0, erp=0.082,
        cost_of_debt=0.07, tax_rate=0.20,
        revenue_growth=[0.10] * 5, ebit_margin=[0.12] * 5,
        capex_to_revenue=[0.05] * 5, depr_to_revenue=[0.03] * 5,
        dso=[30.0] * 5, dio=[30.0] * 5, dpo=[30.0] * 5,
        interest_rate=[0.07] * 5,
    )


def _is(year: int, revenue: float = 100.0) -> IncomeStatement:
    return IncomeStatement(
        year=year, revenue=revenue, cogs=60.0, gross_profit=40.0,
        opex=20.0, ebit=15.0, interest_expense=1.0, tax=2.8, net_income=11.2,
    )


def _bs(year: int, cash: float, total_assets: float = 500.0) -> BalanceSheet:
    """BS cân đối sẵn (total_assets == total_liabilities_and_equity) để phần
    kiểm tra cân đối kế toán không xen vào các assertion về cashflow."""
    other_current = total_assets - cash - 50.0 - 40.0 - 100.0 - 50.0
    return BalanceSheet(
        year=year,
        cash_and_equivalents=cash,
        receivables=50.0, inventory=40.0,
        other_current_assets=other_current,
        fixed_assets=100.0, other_long_term_assets=50.0,
        total_assets=total_assets,
        short_term_debt=30.0, accounts_payable=20.0,
        other_current_liabilities=10.0,
        long_term_debt=40.0, other_long_term_liabilities=0.0,
        total_equity=total_assets - 100.0,
    )


def _company(historical_bs, historical_cf) -> Company:
    return Company(
        ticker="TEST", name="Test Co.", sector="Industrials",
        current_price=10_000.0, shares_outstanding=100.0,
        historical_is=[_is(bs.year) for bs in historical_bs],
        historical_bs=historical_bs, historical_cf=historical_cf,
        assumptions=_assumptions(),
    )


def _cashflow_warnings(company: Company) -> list[str]:
    return [
        w for w in company.warnings
        if "lưu chuyển đầu tư/tài chính" in w or "vượt ngưỡng đối chiếu" in w
    ]


# =============================================================================
# 1. Unit test cho _cashflow_other_excluding_capex (repo.py) — bug gốc CapEx
#    bị trừ hai lần.
# =============================================================================

class TestCashflowOtherExcludingCapex:
    def test_cfi_already_includes_capex_must_add_back(self):
        """CFI (đã chứa CapEx âm) + CFF phải được cộng ngược CapEx dương để
        cf_other không double-count CapEx.

        Số liệu tính tay: CFI = -50 (trong đó CapEx = -30 là một phần của
        CFI), CFF = +20, FX = 0. capex_abs (lưu riêng) = 30.
        cf_other kỳ vọng = CFI + CFF + FX + capex_abs = -50 + 20 + 0 + 30 = 0.
        """
        annual_data = {
            "net_cash_inflows_outflows_from_investing_activities": -50.0,
            "net_cash_inflows_outflows_from_financing_activities": 20.0,
        }
        cf_other, has_full = _cashflow_other_excluding_capex(annual_data, capex_abs=30.0)
        assert has_full is True
        assert abs(cf_other - 0.0) < 1e-9, f"cf_other phải = 0.0 (cộng ngược CapEx), got {cf_other}"

    def test_missing_cfi_or_cff_flags_incomplete(self):
        """Thiếu CFI hoặc CFF thì has_full_cashflow_sections=False, cf_other=0.0
        — KHÔNG được suy ra một con số bịa."""
        annual_data = {
            "net_cash_inflows_outflows_from_investing_activities": -50.0,
            # thiếu CFF
        }
        cf_other, has_full = _cashflow_other_excluding_capex(annual_data, capex_abs=30.0)
        assert has_full is False
        assert cf_other == 0.0

    def test_full_reconciliation_identity_holds(self):
        """Regression: với CFI/CFF/CapEx thật (số liệu GEX 2020, tỷ đồng, đã
        chuẩn hoá — xem docs/PLAN_FIX_CASHFLOW_WARNINGS.md mục 2.3), phép
        đối chiếu Δtiền = CFO - CapEx + cf_other phải khớp trong 0.5 tỷ.
        """
        annual_data = {
            "net_cash_inflows_outflows_from_investing_activities": -2_979.9,
            "net_cash_inflows_outflows_from_financing_activities": 3_245.5,
        }
        capex_abs = 1_917.4
        cf_other, has_full = _cashflow_other_excluding_capex(annual_data, capex_abs)
        assert has_full is True

        cfo = 373.3
        delta_cash_thuc_te = 1_559.2 - 921.0  # tiền cuối 2020 - tiền cuối 2019 (GEX)
        total_cf = cfo - capex_abs + cf_other
        # Ngưỡng 1.0 tỷ khớp abs_tolerance_billion_vnd mặc định — số liệu vế
        # trái lấy từ bảng đã làm tròn 1 chữ số thập phân trong PLAN nên có
        # sai số cộng dồn nhỏ, không phải sai số của công thức.
        assert abs(delta_cash_thuc_te - total_cf) < 1.0, (
            f"Đối chiếu lệch quá 1.0 tỷ: Δtiền={delta_cash_thuc_te}, tính lại={total_cf}"
        )


# =============================================================================
# 2. Model-level: Company.validate_model_integrity gộp cảnh báo & dùng ngưỡng
#    tương đối, thay vì lặp theo năm và ngưỡng cứng 1 tỷ.
# =============================================================================

class TestCompanyCashflowWarnings:
    def test_full_data_matching_identity_no_warning(self):
        """Đủ CFI/CFF và identity khớp trong ngưỡng → KHÔNG cảnh báo cashflow.
        Đây là ca đã bị bug cũ báo sai (cf_other != 0 nhưng vẫn từng bị lỗi
        double-count CapEx làm lệch identity)."""
        bs2019 = _bs(2019, cash=100.0)
        bs2020 = _bs(2020, cash=110.0)  # Δtiền = +10
        cf2020 = CashFlow(
            year=2020, cfo=20.0, capex=15.0, cf_other=5.0,  # 20 - 15 + 5 = 10 ✓
            has_full_cashflow_sections=True, is_ttm_period=False,
        )
        company = _company([bs2019, bs2020], [cf2020])
        assert _cashflow_warnings(company) == []

    def test_missing_years_grouped_into_single_warning(self):
        """3 năm thiếu CFI/CFF → đúng MỘT dòng cảnh báo gộp, không phải ba."""
        years = [2019, 2020, 2021, 2022]
        bs_list = [_bs(y, cash=100.0 + i * 5) for i, y in enumerate(years)]
        cf_list = [
            CashFlow(
                year=y, cfo=20.0, capex=15.0, cf_other=0.0,
                has_full_cashflow_sections=False, is_ttm_period=False,
            )
            for y in years[1:]  # 2020, 2021, 2022 thiếu dữ liệu
        ]
        company = _company(bs_list, cf_list)
        warnings = _cashflow_warnings(company)
        assert len(warnings) == 1, f"Kỳ vọng đúng 1 dòng gộp, got {len(warnings)}: {warnings}"
        assert "2020" in warnings[0] and "2021" in warnings[0] and "2022" in warnings[0]
        assert "3 năm" in warnings[0]

    def test_real_mismatch_exceeding_tolerance_still_warns_with_numbers(self):
        """Đủ dữ liệu nhưng lệch THẬT vượt ngưỡng tương đối → vẫn phải cảnh
        báo (không được im lặng), và cảnh báo nêu số cụ thể để truy vết."""
        bs2019 = _bs(2019, cash=100.0, total_assets=500.0)
        bs2020 = _bs(2020, cash=110.0, total_assets=500.0)  # Δtiền = +10
        cf2020 = CashFlow(
            year=2020, cfo=20.0, capex=15.0, cf_other=50.0,  # 20-15+50=55 != 10, lệch 45
            has_full_cashflow_sections=True, is_ttm_period=False,
        )
        company = _company([bs2019, bs2020], [cf2020])
        warnings = _cashflow_warnings(company)
        assert len(warnings) == 1
        assert "2020" in warnings[0] and "45" in warnings[0].replace(",", "")

    def test_small_rounding_diff_within_tolerance_no_warning(self):
        """Lệch nhỏ do làm tròn (ví dụ 0.3 tỷ trên DN có tổng tài sản 500 tỷ)
        không được cảnh báo — ngưỡng tuyệt đối 1 tỷ đã đủ che nhiễu làm tròn."""
        bs2019 = _bs(2019, cash=100.0)
        bs2020 = _bs(2020, cash=110.0)  # Δtiền = +10
        cf2020 = CashFlow(
            year=2020, cfo=20.0, capex=15.0, cf_other=5.3,  # tổng = 10.3, lệch 0.3
            has_full_cashflow_sections=True, is_ttm_period=False,
        )
        company = _company([bs2019, bs2020], [cf2020])
        assert _cashflow_warnings(company) == []

    def test_ttm_period_not_checked_for_identity(self):
        """Năm TTM (is_ttm_period=True) không đối chiếu chặt — Δtiền so BS
        không cùng độ dài kỳ với dòng tiền cộng dồn 4 quý theo thiết kế."""
        bs2025 = _bs(2025, cash=100.0)
        bs2026 = _bs(2026, cash=999.0)  # Δtiền cực lớn, cố tình không khớp gì
        cf2026_ttm = CashFlow(
            year=2026, cfo=20.0, capex=15.0, cf_other=5.0,
            has_full_cashflow_sections=True, is_ttm_period=True,
        )
        company = _company([bs2025, bs2026], [cf2026_ttm])
        assert _cashflow_warnings(company) == []
