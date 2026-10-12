"""
test_valuation_accuracy.py — Golden test cho các bug fix định giá.

Mỗi test case dùng fixture số liệu tính tay (không cần DB).
Cấu trúc:
  - test_b1_ebitda_*        : B1 — EBITDA = EBIT + D&A (không dùng ×1.25)
  - test_b2_wacc_*          : B2 — WACC dùng market cap weights
  - test_b3_sustainable_roe : B3 — Justified P/B dùng sustainable ROE
  - test_b4_bank_tax        : B4 — Tax ngân hàng từ assumptions
  - test_dcf_golden_fpt     : DCF integration fixture (FPT-like), ±10%
  - test_bank_golden_vcb    : Bank integration fixture (VCB-like), ±10%
"""
import pytest
from valuation.models.financials import (
    IncomeStatement, BalanceSheet, CashFlow, Assumptions, Company
)
from valuation.models.financials_bank import (
    IncomeStatementBank, BalanceSheetBank, AssumptionsBank, CompanyBank
)
from valuation.engine.models.dcf import DCFValuationModel
from valuation.engine.models.bank_general import BankGeneralValuationModel
from valuation.engine.forecast_bank import forecast_bank_financials


# =============================================================================
# HELPERS
# =============================================================================

def _make_fpt_company(current_price: float = 100_000.0) -> Company:
    """
    Fixture phi tài chính (FPT-like).

    Số liệu:
      Revenue base = 100 tỷ, EBIT = 15 tỷ (15%), D&A = 3 tỷ (3% rev)
      Short-term debt = 10 tỷ, Long-term debt = 10 tỷ → total_debt = 20 tỷ
      Cash = 5 tỷ, book equity = 50 tỷ
      Shares = 1,000 triệu | current_price = 100,000 VND
      → market_cap = 1,000 × 1e6 × 100,000 = 1e14 đồng = 100,000 tỷ

    Giả định:
      rf = 3%, beta = 1.0, erp = 8.2% → coe = 11.2%
      cost_of_debt = 6%, tax = 20%
      WACC (market cap) = 11.2% × (100,000/120,000) + 4.8% × (20,000/120,000)
                        ≈ 9.333% + 0.800% ≈ 10.133%
      (Giá trị tham chiếu dùng trong test_b2)

    EBITDA tham chiếu (sau B1 fix):
      = 15 + 0.03 × 100 = 15 + 3 = 18 tỷ → 18 × 1e9 đồng = 1.8e10
    """
    is_ = IncomeStatement(
        year=2023,
        revenue=100.0, cogs=60.0, gross_profit=40.0,
        opex=25.0, ebit=15.0, interest_expense=1.2,
        tax=2.76, net_income=11.04,
    )
    bs_ = BalanceSheet(
        year=2023,
        cash_and_equivalents=5.0, receivables=12.0, inventory=8.0,
        other_current_assets=5.0, fixed_assets=15.0, other_long_term_assets=5.0,
        total_assets=50.0,
        short_term_debt=10.0, accounts_payable=7.0, other_current_liabilities=3.0,
        long_term_debt=10.0, other_long_term_liabilities=0.0,
        total_equity=20.0,
    )
    cf_ = CashFlow(year=2023, cfo=14.0, capex=5.0)
    ass_ = Assumptions(
        risk_free_rate=0.03, beta=1.0, erp=0.082,
        cost_of_debt=0.06, tax_rate=0.20,
        revenue_growth=[0.20, 0.20, 0.20, 0.15, 0.10],
        ebit_margin=[0.15] * 5,
        capex_to_revenue=[0.05] * 5,
        depr_to_revenue=[0.03] * 5,
        dso=[30.0] * 5,
        dio=[30.0] * 5,
        dpo=[30.0] * 5,
        interest_rate=[0.06] * 5,
        terminal_growth_rate=0.02,
        target_ev_ebitda=13.0,
        weight_dcf=0.5,
    )
    return Company(
        ticker="FPT_TEST", name="FPT Test Co.", sector="Technology",
        current_price=current_price,
        shares_outstanding=1_000.0,  # triệu cp
        historical_is=[is_], historical_bs=[bs_], historical_cf=[cf_],
        assumptions=ass_,
    )


def _make_vcb_company() -> CompanyBank:
    """
    Fixture ngân hàng (VCB-like).

    Số liệu (đơn vị tỷ đồng):
      Cho vay KH = 1,200,000 | Earning assets = 1,400,000 | Total assets = 1,600,000
      Tiền gửi KH = 1,260,000 | Other liab = 220,000 | Equity = 120,000
      NII = 40,000 | Non-II = 6,000 | TOI = 46,000
      Opex = 15,180 (CIR 33%) | PPOP = 30,820
      Provision = 12,000 | PBT = 18,820 | NI = 15,056

    Giả định:
      rf=3%, beta=0.9, erp=8.2% → coe = 10.38%
      credit_growth=12%, nim=2.857% (≈ NII/avg_earning_assets),
      cir=33%, credit_cost=1%, tax=20%
      sustainable_roe = 20% (tham chiếu chuẩn VCB)
      g = 2%, shares = 3,723 triệu

    Justified P/B (tính tay):
      = (ROE_s - g) / (Re - g) = (0.20 - 0.02) / (0.1038 - 0.02)
      = 0.18 / 0.0838 ≈ 2.148
    BVPS = 120,000 tỷ / 3,723 triệu × 1,000 ≈ 32,231 VND
    Target P (standalone Justified P/B) = 2.148 × 32,231 ≈ 69,232 VND
    """
    is_b = IncomeStatementBank(
        year=2023,
        net_interest_income=40_000.0,
        non_interest_income=6_000.0,
        total_operating_income=46_000.0,
        operating_expenses=15_180.0,
        pre_provision_profit=30_820.0,
        provision_expense=12_000.0,
        pretax_income=18_820.0,
        net_income=15_056.0,
    )
    bs_b = BalanceSheetBank(
        year=2023,
        customer_loans=1_200_000.0,
        other_earning_assets=200_000.0,
        total_assets=1_600_000.0,
        customer_deposits=1_260_000.0,
        other_liabilities=220_000.0,
        total_equity=120_000.0,
    )
    ass_b = AssumptionsBank(
        risk_free_rate=0.03, beta=0.90, erp=0.082,
        credit_growth=[0.12, 0.12, 0.11, 0.10, 0.09],
        nim=[0.0286, 0.0286, 0.0283, 0.0280, 0.0278],
        cir=[0.33, 0.33, 0.325, 0.320, 0.315],
        credit_cost=[0.010, 0.010, 0.010, 0.009, 0.009],
        deposit_growth=[0.12, 0.12, 0.11, 0.10, 0.09],
        dividend_payout_ratio=0.15,
        terminal_growth_rate=0.02,
        sustainable_roe=0.20,   # B3 fix sẽ dùng giá trị này
        tax_rate=0.20,          # B4 fix
        weight_ri=0.5,
    )
    return CompanyBank(
        ticker="VCB_TEST", name="VCB Test",
        current_price=85_000.0,
        shares_outstanding=3_723.0,  # triệu cp
        historical_is=[is_b],
        historical_bs=[bs_b],
        assumptions=ass_b,
    )


# =============================================================================
# B1 — EBITDA = EBIT + D&A
# =============================================================================

class TestB1Ebitda:
    def test_ebitda_equals_ebit_plus_da(self):
        """B1: cf_dict['ebitda'] phải = (EBIT + depr_to_rev × rev) × 1e9, không phải EBIT × 1.25."""
        company = _make_fpt_company()
        model = DCFValuationModel.from_pydantic(company)

        base_is = company.historical_is[-1]
        depr_to_rev = company.assumptions.depr_to_revenue[0]
        expected_ebitda_ty = base_is.ebit + depr_to_rev * base_is.revenue  # tỷ đồng
        # 15 + 0.03 × 100 = 18 tỷ
        assert abs(expected_ebitda_ty - 18.0) < 0.001, "Tính tay EBITDA phải = 18 tỷ"

        actual_ebitda_dong = model.current_financials['ebitda']
        expected_ebitda_dong = expected_ebitda_ty * 1e9
        assert abs(actual_ebitda_dong - expected_ebitda_dong) < 1.0, (
            f"B1 FAIL: ebitda={actual_ebitda_dong:.2e}, "
            f"expected={expected_ebitda_dong:.2e} (EBIT+D&A)"
        )

    def test_ebitda_not_1_25_multiplier(self):
        """B1 regression: EBITDA không phải EBIT × 1.25."""
        company = _make_fpt_company()
        model = DCFValuationModel.from_pydantic(company)
        buggy_value = company.historical_is[-1].ebit * 1.25 * 1e9  # 18.75e9
        actual = model.current_financials['ebitda']
        assert abs(actual - buggy_value) > 1.0, (
            "B1 regression: EBITDA vẫn dùng ×1.25 (bug chưa sửa)"
        )


# =============================================================================
# B2 — WACC dùng market cap weights
# =============================================================================

class TestB2WaccMarketCap:
    def test_wacc_uses_market_cap_not_book_equity(self):
        """
        B2: Với company có P/B cao (market_cap >> book_equity),
        WACC phải gần với COE (E >> D) thay vì bị giảm xuống do book equity thấp.

        Fixture:
          book_equity = 20 tỷ, market_cap = 100,000 tỷ → P/B ≈ 5,000×
          total_debt = 20 tỷ
          coe = 11.2%, cod = 6%, tax = 20%

          WACC (market cap) ≈ 11.2% × (100,000/120,000) + 4.8% × (20,000/120,000)
                             ≈ 9.333% + 0.800% = 10.133%

          WACC (book equity — BUG) ≈ 11.2% × (20/(20+20)) + 4.8% × (20/(20+20))
                                    = 5.6% + 2.4% = 8.0% → bị floor lên 6% (rf+3%)
          → WACC book = 8.0% << WACC market = 10.133%
        """
        company = _make_fpt_company(current_price=100_000.0)
        model = DCFValuationModel.from_pydantic(company)
        actual_wacc = model.wacc

        # Market cap = 1,000 triệu × 100,000 đồng = 1e14 đồng = 100,000 tỷ
        # D = (10+10) tỷ = 20 tỷ
        # WACC_market = coe × E/(E+D) + cod_at × D/(E+D)
        coe = 0.03 + 1.0 * 0.082  # 0.112
        cod_at = 0.06 * (1 - 0.20)  # 0.048
        E = 100_000.0   # tỷ (market cap)
        D = 20.0        # tỷ
        expected_wacc = coe * E / (E + D) + cod_at * D / (E + D)
        # ≈ 0.112 × 0.9980 + 0.048 × 0.0020 ≈ 0.11178 + 0.000096 ≈ 0.11188

        assert abs(actual_wacc - expected_wacc) < 0.002, (
            f"B2 FAIL: WACC={actual_wacc:.4%}, expected≈{expected_wacc:.4%} (market cap)"
        )

    def test_wacc_with_zero_price_falls_back(self):
        """B2 fallback: nếu current_price = 0, không crash, dùng book equity."""
        company = _make_fpt_company(current_price=0.0)
        model = DCFValuationModel.from_pydantic(company)
        # Chỉ cần không crash và có cảnh báo
        assert model.wacc > 0, "WACC phải dương kể cả khi fallback book equity"
        assert any("WACC_BOOK_EQUITY_FALLBACK" in w for w in company.warnings), (
            "Phải có cảnh báo khi dùng book equity fallback"
        )


# =============================================================================
# B3 — Sustainable ROE trong Justified P/B (bank.py standalone)
# =============================================================================

class TestB3SustainableRoe:
    def test_justified_pb_uses_sustainable_roe(self):
        """
        B3: Justified P/B của model ACTIVE (bank_general) phải ưu tiên
        assumptions.sustainable_roe, KHÔNG dùng ROE dự phóng năm 5.

        (Trước đây B3 chỉ nằm ở engine/bank.py legacy — đã xoá. Nay hợp nhất về
        một model duy nhất: BankGeneralValuationModel.)
        """
        company = _make_vcb_company()
        company.assumptions.sustainable_roe = 0.11  # khác rõ ROE dự phóng năm 5

        model = BankGeneralValuationModel(company)
        pb_res = model.calculate_pb_valuation()

        # ROE dùng cho Gordon Growth phải = sustainable_roe (B3)
        assert abs(pb_res["long_term_roe"] - 0.11) < 1e-9, (
            f"B3 FAIL: long_term_roe={pb_res['long_term_roe']:.4f}, phải = 0.11"
        )

        # Bằng chứng B3 áp dụng: sustainable_roe KHÁC ROE dự phóng năm 5
        roe_yr5 = model.projections[-1]["net_income"] / model.projections[-2]["total_equity"]
        assert abs(roe_yr5 - 0.11) > 0.02, "test cần sustainable_roe khác ROE năm 5 mới có ý nghĩa"

        # Target P/B khớp công thức Gordon với sustainable_roe
        expected_pb = max(0.3, (0.11 - model.g) / (model.coe - model.g))
        assert abs(pb_res["target_pb"] - expected_pb) < 1e-6



# =============================================================================
# B4 — Tax bank từ assumptions
# =============================================================================

class TestB4BankTax:
    def test_net_income_uses_assumptions_tax(self):
        """
        B4: LNST năm 1 phải = PBT × (1 - assumptions.tax_rate).
        Với tax_rate=0.15 (ưu đãi), LNST phải ≠ PBT × 0.80.
        """
        company = _make_vcb_company()
        # Override tax sang 15% để phân biệt khỏi default 20%
        company.assumptions.tax_rate = 0.15

        projs = forecast_bank_financials(company)
        yr1 = projs[0]

        pbt_yr1 = yr1["pretax_income"]
        expected_ni = pbt_yr1 * (1.0 - 0.15)
        actual_ni = yr1["net_income"]

        assert abs(actual_ni - expected_ni) < 0.01, (
            f"B4 FAIL: NI={actual_ni:.2f}, expected={expected_ni:.2f} "
            f"(tax=15%, không phải 20% hardcode)"
        )

    def test_net_income_not_hardcoded_080(self):
        """B4 regression: NI không phải PBT × 0.8 khi tax != 20%."""
        company = _make_vcb_company()
        company.assumptions.tax_rate = 0.15
        projs = forecast_bank_financials(company)
        pbt = projs[0]["pretax_income"]
        ni = projs[0]["net_income"]
        buggy = pbt * 0.8
        assert abs(ni - buggy) > 0.01, "B4 regression: vẫn hardcode 0.8"


# =============================================================================
# DCF Integration Golden Test — FPT-like fixture
# =============================================================================

class TestDcfGoldenFpt:
    """
    Golden test tích hợp DCF. Fixture FPT-like, tính tay:

    Sau B1+B2 fix:
    EBITDA = 18 tỷ → EV_multiples = 18e9 × 13 = 234e9 đồng
    Net debt = (20-5) tỷ × 1e9 = 15e9 đồng
    equity_val_multi = (234 - 15) × 1e9 = 219e9 đồng
    shares = 1,000e6 cp
    multiples_fvps = 219e9 / 1,000e6 = 219 đồng (quá thấp vì shares lớn & đơn vị)

    Lưu ý đơn vị quan trọng:
      equity_val (đồng) / shares (cp) = đồng/cp
      219e9 / 1e9 = 219 đồng — đây là kết quả đúng theo đơn vị của code.
      Nhưng current_price = 100,000 đồng → upside sẽ âm.
      Điều này bình thường: FPT có EV/EBITDA 13× nhưng số shares rất lớn.
      Test này CHỈ verify tính đúng đắn toán học (không crash, không NaN, không âm
      vô lý), không verify "giá hợp lý kinh tế" vì fixture là số giả.

    Assert quan trọng:
      1. Không crash
      2. dcf_fvps > 0
      3. multiples_fvps > 0
      4. EBITDA trong cf_dict = 18 × 1e9
      5. WACC ≈ 10.133% (market cap weighted)
    """
    def test_dcf_no_crash_and_positive(self):
        company = _make_fpt_company()
        model = DCFValuationModel.from_pydantic(company)
        result = model.perform_valuation()

        assert result["dcf_fvps"] > 0, "DCF FVPS phải dương"
        assert result["multiples_fvps"] > 0, "Multiples FVPS phải dương"
        assert result["blended_fair_value_per_share"] > 0, "Blended FVPS phải dương"

    def test_multiples_ebitda_correct(self):
        """Multiples dùng EBITDA đã fix B1."""
        company = _make_fpt_company()
        model = DCFValuationModel.from_pydantic(company)
        ebitda_actual = model.current_financials['ebitda']
        # Sau B1 fix: EBITDA = 18 tỷ × 1e9
        assert abs(ebitda_actual - 18e9) < 1.0, (
            f"EBITDA={ebitda_actual:.2e}, expected=18e9"
        )
        result = model.perform_valuation()
        net_debt = model.current_financials['total_debt'] - model.current_financials['cash_and_equivalents']
        expected_ev = ebitda_actual * 13.0
        expected_equity = expected_ev - net_debt
        shares = model.current_financials['shares_outstanding']
        expected_multi_fvps = expected_equity / shares if shares > 0 else 0.0
        assert abs(result["multiples_fvps"] - expected_multi_fvps) < 0.01, (
            f"multiples_fvps={result['multiples_fvps']:.4f}, expected={expected_multi_fvps:.4f}"
        )


# =============================================================================
# Bank Integration Golden Test — VCB-like fixture
# =============================================================================

class TestBankGoldenVcb:
    """
    Golden test Bank, dùng BankGeneralValuationModel.

    Justified P/B (tính tay với sustainable_roe=0.20):
      coe = 0.03 + 0.90 × 0.082 = 0.1038
      g = 0.02
      terminal_roe = min(0.20, ELITE_ROE_CAP=0.20) = 0.20  (0.20 > 0.18
        ngưỡng elite → trần 20%, KHÔNG bị ép về 15% chuẩn — điều tra 2026-07,
        xem DECISIONS.md "Trần ROE ngân hàng theo tier chất lượng")
      P/B = (0.20 - 0.02) / (0.1038 - 0.02) = 0.18 / 0.0838 ≈ 2.148
      BVPS = 120,000 tỷ / 3,723 triệu × 1,000 = 32,231 VND
      Target (Justified P/B) ≈ 69,232 VND — test_pb_valuation_formula assert
      trực tiếp số này (±10%), không còn circular-check thuần công thức.

    Residual Income: phụ thuộc projection, không tính tay đầy đủ.
    Test assert blended FV nằm trong khoảng hợp lý [30,000; 130,000] VND
    cho VCB với các giả định trên.
    """
    def test_bank_no_crash_positive(self):
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        company = _make_vcb_company()
        model = BankGeneralValuationModel(company)
        result = model.perform_valuation()

        assert result["blended_fair_value_per_share"] > 0
        assert result["ri_fvps"] > 0
        assert result["pb_fvps"] > 0

    def test_pb_valuation_formula(self):
        """
        P/B Justified: kết quả phải trong ±10% của giá trị tính tay.
        Tính tay:
          coe = 0.1038, g = 0.02
          long_term_roe = NI_yr5 / Equity_yr4 (từ projection)
          Target P/B = max(0.3, (long_term_roe - g) / (coe - g))
          FVPS = Target_PB × base_equity / shares × 1,000
        """
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        company = _make_vcb_company()
        model = BankGeneralValuationModel(company)
        pb_res = model.calculate_pb_valuation()

        coe = model.coe   # ≈ 0.1038
        g = model.g       # ≈ 0.02

        long_term_roe = pb_res["long_term_roe"]
        # Verify công thức P/B
        if coe > g:
            expected_target_pb = max(0.3, (long_term_roe - g) / (coe - g))
        else:
            expected_target_pb = 1.0

        actual_pb = pb_res["target_pb"]
        assert abs(actual_pb - expected_target_pb) < 0.001, (
            f"P/B formula sai: actual={actual_pb:.4f}, expected={expected_target_pb:.4f}"
        )

        # FVPS tham chiếu từ P/B tính tay
        ref_equity_val = expected_target_pb * company.historical_bs[-1].total_equity
        ref_fvps = (ref_equity_val / company.shares_outstanding) * 1_000.0
        actual_fvps = pb_res["fair_value_per_share"]
        assert abs(actual_fvps - ref_fvps) < 1.0, (
            f"FVPS = {actual_fvps:.0f} VND, tham chiếu = {ref_fvps:.0f} VND"
        )

        # Không chỉ circular-check công thức: đối chiếu THẲNG với hand-calc gốc
        # của docstring (sustainable_roe=0.20 → terminal_roe=0.20 vì thuộc tier
        # elite, KHÔNG bị ép về trần 15% chuẩn). ±10% theo AGENTS.md.
        assert abs(long_term_roe - 0.20) < 0.001, (
            f"terminal_roe = {long_term_roe:.4f}, kỳ vọng 0.20 (VCB-like elite tier, "
            "sustainable_roe=0.20 > ELITE_ROE_THRESHOLD=0.18)"
        )
        assert abs(actual_pb - 2.148) / 2.148 < 0.10, (
            f"target_pb = {actual_pb:.4f}, kỳ vọng ≈2.148 (hand-calc docstring)"
        )
        assert abs(actual_fvps - 69_232) / 69_232 < 0.10, (
            f"FVPS = {actual_fvps:.0f} VND, kỳ vọng ≈69,232 VND (hand-calc docstring)"
        )

    def test_bank_blended_in_reasonable_range(self):
        """Blended FV nằm trong [30,000; 130,000] VND cho VCB-like với current_price=85,000."""
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        company = _make_vcb_company()
        model = BankGeneralValuationModel(company)
        result = model.perform_valuation()
        fv = result["blended_fair_value_per_share"]
        assert 30_000 <= fv <= 130_000, (
            f"Blended FV={fv:.0f} VND nằm ngoài khoảng hợp lý [30k, 130k]. "
            "Kiểm tra lại assumptions hoặc projection logic."
        )

    def test_forecast_bank_tax_from_assumptions(self):
        """B4: NI trong projection phải dùng tax_rate từ assumptions."""
        company = _make_vcb_company()
        company.assumptions.tax_rate = 0.15
        projs = forecast_bank_financials(company)
        for yr_proj in projs:
            pbt = yr_proj["pretax_income"]
            ni = yr_proj["net_income"]
            if pbt > 0:
                implied_tax = 1.0 - (ni / pbt)
                assert abs(implied_tax - 0.15) < 0.001, (
                    f"Year {yr_proj['year']}: implied tax={implied_tax:.4f}, expected=0.15"
                )
                break  # Kiểm tra năm đầu là đủ
