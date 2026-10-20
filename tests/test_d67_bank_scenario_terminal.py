"""D67 (21/10/2026, phi chọn phương án b) — kịch bản Bull/Bear NH: ROE dài hạn tính lại từ driver đã sốc.

Phản biện r4 (major): Bull/Bear dồn toàn bộ sốc driver vào LN năm 5 (cơ chế delta r4a) trong khi RI terminal vẫn theo
ROE_T của Base → LN năm 5 → 6 nhảy bậc (VPB Bear lỗ năm 4–5 rồi ROE ~13% vĩnh viễn; CTG Bear LN6/LN5 +361%).
Sửa: roe5 kịch bản = roe5 Base + (roe5 driver đã sốc − roe5 driver Base), ROE_T kịch bản = hội tụ λ về ROE ngành
(KHÔNG sốc), driver gốc cũng sốc → năm 3–5 phai về ROE_T kịch bản, năm 5 = ROE_T, LN6 nối liền.

Test viết TRƯỚC khi sửa (tái hiện bước nhảy). Mỗi ca có phép tính tay trong comment.
"""

import pytest

from tests.helpers_bank import build_fake_bank
from valuation.config import load_defaults

_DRIVERS = ("credit_growth", "nim", "cir", "credit_cost")


def _hand_bank(sustainable_roe: float = 0.17):
    """NH tính tay: tín dụng không tăng, chi trả 100% → TS 10.000, cho vay 8.000, VCSH 1.000 không đổi.

    Base: NII 3,5% × 10.000 = 350; ngoài lãi 1% × 10.000 = 100; TOI 450; CIR 35% → chi phí 157,5; PPOP 292,5;
    dự phòng 1% × 8.000 = 80; LN = 212,5 × 0,8 = 170 → roe5 driver = 17% (= sustainable_roe như repo đặt).
    ROE ngành 18%, λ = 0,5 → ROE_T Base = 17,5%.
    """
    c = build_fake_bank(sustainable_roe=sustainable_roe, coe=0.12, g=0.02, payout=1.0)
    a = c.assumptions
    a.credit_growth = [0.0] * 5
    a.industry_roe, a.roe_convergence = 0.18, 0.5
    a.driver_base = {k: list(getattr(a, k)) for k in _DRIVERS}
    return c


def _ln6_ratio(c):
    """(LN6/LN5, g): LN6 = ROE_T đầu kỳ × VCSH5 (RI terminal), LN5 = LN năm cuối của dự phóng."""
    from valuation.engine.forecast_bank import forecast_bank_financials
    from valuation.engine.models.bank_general import BankGeneralValuationModel

    p = forecast_bank_financials(c)
    m = BankGeneralValuationModel(c.model_copy(deep=True), projections=p)
    return m.terminal_roe_begin * p[-1]["total_equity"] / p[-1]["net_income"], m.g


def test_bear_hand_case_roe5_and_terminal_from_shocked_drivers():
    from valuation.engine.forecast_bank import bank_terminal_roe
    from valuation.engine.sensitivity import apply_scenario_adjustments

    bear = apply_scenario_adjustments(_hand_bank(), "Bear")
    # Bear: NIM 3,15% → NII 315; TOI 415; CIR 38,5% → 159,775; PPOP 255,225; dự phòng 1,5% × 8.000 = 120;
    # LN = 135,225 × 0,8 = 108,18 → roe5 kịch bản 10,818% (không cộng −2 điểm % cố định).
    assert bear.assumptions.sustainable_roe == pytest.approx(0.10818)
    # ROE ngành KHÔNG sốc (D67) → ROE_T = 10,818% + 0,5 × (18% − 10,818%) = 14,409%.
    assert bear.assumptions.industry_roe == pytest.approx(0.18)
    assert bank_terminal_roe(bear)[0] == pytest.approx(0.14409)


def test_bull_hand_case():
    from valuation.engine.forecast_bank import bank_terminal_roe
    from valuation.engine.sensitivity import apply_scenario_adjustments

    bull = apply_scenario_adjustments(_hand_bank(), "Bull")
    # Bull: NIM 3,85% → NII 385; TOI 485; CIR 31,5% → 152,775; PPOP 332,225; dự phòng 0,9% × 8.000 = 72;
    # LN = 260,225 × 0,8 = 208,18 → roe5 20,818%; ROE_T = 20,818% + 0,5 × (18% − 20,818%) = 19,409% (< trần 20%).
    assert bull.assumptions.sustainable_roe == pytest.approx(0.20818)
    assert bank_terminal_roe(bull)[0] == pytest.approx(0.19409)


def test_bear_year3_to_5_fade_to_scenario_terminal_no_jump():
    """Tái hiện phản biện r4: trước sửa LN5 Bear = 155 + (108,18 − 170) = 93,18 trong khi LN6 = 15,5% × 1,0075 × 1.000
    = 156,2 → LN6/LN5 = 1,676. Sau sửa: năm 3–5 phai 10,818% → 14,409% (trọng số 1/3, 2/3, 1).
    """
    from valuation.engine.forecast_bank import forecast_bank_financials
    from valuation.engine.sensitivity import apply_scenario_adjustments

    bear = apply_scenario_adjustments(_hand_bank(), "Bear")
    p = forecast_bank_financials(bear)
    ni = [y["net_income"] for y in p]
    # Chi trả 100% → VCSH bình quân = 1.000 → LN = ROE × 1.000.
    assert ni[:2] == pytest.approx([108.18, 108.18])
    assert ni[2:] == pytest.approx([120.15, 132.12, 144.09], abs=0.01)
    # LN6 = 14,409% × (1 + 1,5%/2) × 1.000 = 145,17; g Bear = 2% − 0,5% → LN6/LN5 = 1,0075, lệch 1 + g −0,75 điểm %.
    ratio, g = _ln6_ratio(bear)
    assert ratio == pytest.approx(1.0075)
    assert (
        abs(ratio - (1 + g))
        <= load_defaults()["bank_terminal"]["terminal_jump_flag_tolerance"]
    )


def test_analyst_sustainable_roe_override_shifted_by_driver_delta():
    """Analyst nhập ROE bền vững 15% (≠ roe5 driver 17%): kịch bản giữ mức của analyst, chỉ dịch phần sốc driver
    15% + (10,818% − 17%) = 8,818% — Bear − Base chỉ do sốc kịch bản."""
    from valuation.engine.sensitivity import apply_scenario_adjustments

    assert apply_scenario_adjustments(
        _hand_bank(0.15), "Bear"
    ).assumptions.sustainable_roe == pytest.approx(0.08818)


def test_negative_scenario_roe5_kept_not_replaced_by_ttm():
    """VPB Bear (20/10): roe5 kịch bản −4,5%. ROE riêng ≤ 0 phải được dùng: −2% + 0,5 × (18% + 2%) = 8%. Trước D67
    ≤ 0 bị thay bằng ROE TTM 17% → ROE_T 17,5%, tức Bear còn cao hơn ROE_T Base (đảo dấu sốc).
    """
    from valuation.engine.forecast_bank import bank_terminal_roe

    c = _hand_bank()
    c.assumptions.sustainable_roe = -0.02
    assert bank_terminal_roe(c) == pytest.approx((0.08, 0.08))


def test_base_scenario_untouched():
    from valuation.engine.forecast_bank import forecast_bank_financials
    from valuation.engine.sensitivity import apply_scenario_adjustments

    c = _hand_bank()
    base = apply_scenario_adjustments(c, "Base")
    assert base.assumptions == c.assumptions
    assert forecast_bank_financials(base) == forecast_bank_financials(c)


# --- Cờ BANK_TERMINAL_JUMP: |LN6/LN5 − (1 + g)| > bank_terminal.terminal_jump_flag_tolerance --------------------


def test_terminal_jump_flag_fires_on_year5_driver_edit():
    """Analyst sửa chi phí tín dụng năm 5 lên 2% ở Base: LN5 = 175 + (−80 × 0,8) = 111; LN6 = 17,5% × 1,01 × 1.000
    = 176,75 → LN6/LN5 = 1,592, lệch 1 + g 0,572 > 0,10 → cờ cảnh báo (không chặn)."""
    from valuation.engine.flag_descriptions import FLAG_DESCRIPTIONS
    from valuation.engine.models.bank_general import BankGeneralValuationModel

    clean = _hand_bank()
    BankGeneralValuationModel(clean)
    assert not any(w.startswith("BANK_TERMINAL_JUMP") for w in clean.warnings)

    edited = _hand_bank()
    edited.assumptions.credit_cost[4] = 0.02
    m = BankGeneralValuationModel(edited)
    assert m.projections[-1]["net_income"] == pytest.approx(111.0)
    assert any(w.startswith("BANK_TERMINAL_JUMP") for w in edited.warnings)
    assert FLAG_DESCRIPTIONS["BANK_TERMINAL_JUMP"]["level"] == "warning"


def test_terminal_jump_flag_on_non_positive_year5_income():
    """LN5 ≤ 0 (chi phí tín dụng năm 5 = 4%: LN5 = 175 − 240 × 0,8 = −17) → tỷ số vô nghĩa, vẫn phải gắn cờ."""
    from valuation.engine.models.bank_general import BankGeneralValuationModel

    c = _hand_bank()
    c.assumptions.credit_cost[4] = 0.04
    m = BankGeneralValuationModel(c)
    assert m.projections[-1]["net_income"] == pytest.approx(-17.0)
    assert any(w.startswith("BANK_TERMINAL_JUMP") for w in c.warnings)


# --- Đường thật (DB chỉ đọc): hai mã phản biện r4 nêu --------------------------------------------------------


@pytest.mark.parametrize("ticker", ["VPB", "CTG"])
def test_real_banks_bull_bear_no_terminal_jump(ticker):
    from valuation.data_access import repo
    from valuation.db.session import SessionLocalRead
    from valuation.engine.sensitivity import apply_scenario_adjustments
    from valuation.engine.valuate import valuate

    tol = load_defaults()["bank_terminal"]["terminal_jump_flag_tolerance"]
    with SessionLocalRead() as db:
        c = repo.build_company_data(db, ticker)
    for s in ("Bull", "Base", "Bear"):
        sc = apply_scenario_adjustments(c, s)
        ratio, g = _ln6_ratio(sc)
        assert (
            abs(ratio - (1 + g)) <= tol
        ), f"{ticker} {s}: LN6/LN5 = {ratio:.3f}, 1 + g = {1 + g:.3f}"
        assert not any(
            f.startswith("BANK_TERMINAL_JUMP") for f in valuate(sc)["flags"]
        ), f"{ticker} {s}"


def test_report_scenarios_surface_roe5_undefined(monkeypatch):
    # D67: lỗi BANK_SCENARIO_ROE5_UNDEFINED phải hiện thành ghi chú trong báo cáo, không bị nuốt thành None.
    import valuation.engine.sensitivity as sens
    from valuation.report.report_data import build_scenarios

    def boom(_company):
        raise ValueError("BANK_SCENARIO_ROE5_UNDEFINED:ZZZ:Bear — VCSH bình quân năm 5 ≤ 0")

    monkeypatch.setattr(sens, "run_scenario_analysis", boom)

    class C:
        current_price = 10_000.0

    out = build_scenarios(C())
    assert out == {"rows": [], "applicable": False, "note": "BANK_SCENARIO_ROE5_UNDEFINED:ZZZ:Bear — VCSH bình quân năm 5 ≤ 0"}
