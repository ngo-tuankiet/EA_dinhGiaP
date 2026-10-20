"""r4a_decisions_models (20/10/2026) — quyết định người dùng (phi) Q1/Q2 + phản biện vòng 3
(journal wf_47ae6de9-8db): driver ngân hàng analyst sửa cộng lên đường đã phai (không bỏ dòng cân), một nguồn
thuế dài hạn cho NOPAT terminal và lá chắn thuế nợ.

Mỗi ca có phép tính tay trong comment. Test viết TRƯỚC khi sửa (tái hiện lỗi).
"""

import pytest

from tests.helpers_bank import build_fake_bank
from valuation.config import load_defaults

_DRIVERS = ("credit_growth", "nim", "cir", "credit_cost")


# --- Q1: ROE terminal NH = ROE riêng + λ·(ROE ngành − ROE riêng) ------------------------------------------


def test_bank_terminal_roe_half_convergence_hand_case():
    from valuation.engine.forecast_bank import bank_terminal_roe

    # λ = 0,5 (phi duyệt 20/10/2026): ROE bền vững 16%, ROE ngành 20% → 16% + 0,5 × 4% = 18% (trước trần 20%).
    c = build_fake_bank(sustainable_roe=0.16)
    c.assumptions.industry_roe, c.assumptions.roe_convergence = 0.20, 0.5
    assert bank_terminal_roe(c) == pytest.approx((0.18, 0.18))


# --- (3) Driver analyst sửa cộng lên đường đã phai: LN = LN_phai(gốc) + (LN_drv_sửa − LN_drv_gốc) ----------


def _bank(edit_nim: dict[int, float] | None = None, with_base: bool = True):
    """NH giả: ROE driver ~16% < ROE_T 20% (λ = 1) → dòng cân năm 3–5 DƯƠNG và lớn (kiểu EIB/SSB)."""
    c = build_fake_bank(sustainable_roe=0.16, coe=0.12, g=0.04)
    c.ticker = "SHB"  # routing có trọng số RI/P/B
    a = c.assumptions
    a.industry_roe, a.roe_convergence = 0.20, 1.0
    if with_base:
        a.driver_base = {k: list(getattr(a, k)) for k in _DRIVERS}
    for i, v in (edit_nim or {}).items():
        a.nim[i] = v
    return c


def test_bank_unedited_drivers_identical_to_plain_fade():
    from valuation.engine.forecast_bank import forecast_bank_financials

    # Không sửa gì: có/không có ảnh chụp driver gốc → dự phóng giống hệt (từng số).
    assert forecast_bank_financials(_bank()) == forecast_bank_financials(
        _bank(with_base=False)
    )


def test_bank_nim_edit_year4_adds_driver_delta_on_faded_path():
    from valuation.engine.forecast_bank import forecast_bank_financials

    base = forecast_bank_financials(_bank())
    edited = forecast_bank_financials(_bank(edit_nim={3: 0.040}))
    assert base[:3] == edited[:3]  # năm 1–3 không đổi
    # Năm 4 cùng trạng thái đầu kỳ: TS sinh lời 10.000 × 1,12^3 = 14.049,28 → 1,12^4 = 15.735,19; bình quân
    # 14.892,24 tỷ. NIM +0,5 điểm % → TOI +74,461; × (1 − CIR 35%) × (1 − thuế 20%) = +38,72 tỷ LN.
    avg_ea = 10_000.0 * (1.12**3 + 1.12**4) / 2
    assert edited[3]["net_income"] - base[3]["net_income"] == pytest.approx(
        0.005 * avg_ea * 0.65 * 0.8
    )
    assert edited[3]["net_income"] - base[3]["net_income"] == pytest.approx(
        38.72, abs=0.01
    )
    # Dòng cân tính từ driver GỐC trên cùng trạng thái → giữ nguyên năm 4; bảng IS vẫn khớp.
    assert edited[3]["roe_fade_adjustment"] == pytest.approx(
        base[3]["roe_fade_adjustment"]
    )
    y4 = edited[3]
    assert y4["net_income"] == pytest.approx(
        (
            y4["pre_provision_profit"]
            - y4["provision_expense"]
            + y4["roe_fade_adjustment"]
        )
        * 0.8
    )
    # Năm 5: VCSH đầu kỳ lớn hơn → LN đã phai về ROE_T lớn hơn (đúng dấu, không nhảy bậc).
    assert edited[4]["net_income"] > base[4]["net_income"]


def test_bank_nim_edit_raises_fv_on_large_positive_plug_bank():
    """Phản biện r3: trước sửa, sửa NIM năm 4 (UI tự đánh dấu → bỏ dòng cân) làm FV GIẢM ở NH dòng cân dương."""
    from valuation.engine.valuate import valuate

    fv_base = valuate(_bank())["blended_fair_value_per_share"]
    fv_up = valuate(_bank(edit_nim={3: 0.040}))["blended_fair_value_per_share"]
    assert fv_up > fv_base
    fv_dn = valuate(_bank(edit_nim={3: 0.030}))["blended_fair_value_per_share"]
    assert fv_dn < fv_base


def test_bank_fade_plug_flag_kept_after_driver_edit():
    """Cờ BANK_ROE_FADE_PLUG không biến mất âm thầm khi analyst sửa driver năm 5 (dòng cân vẫn còn)."""
    from valuation.engine.valuate import valuate

    flags = valuate(_bank(edit_nim={4: 0.040}))["flags"]
    assert any(f.startswith("BANK_ROE_FADE_PLUG:") for f in flags)


def test_input_assumptions_bank_snapshots_driver_base_without_year_marking():
    """UI NH: không còn chọn 'năm LN theo driver'; ảnh chụp driver gốc được giữ để tính phần analyst sửa."""
    from streamlit.testing.v1 import AppTest

    def _app():
        import streamlit as st

        from tests.helpers_bank import build_fake_bank
        from valuation.views.input_assumptions import render_input_assumptions

        if "c" not in st.session_state:
            c = build_fake_bank(sustainable_roe=0.16, coe=0.12, g=0.04)
            c.assumptions.industry_roe, c.assumptions.roe_convergence = 0.20, 1.0
            st.session_state["c"] = c
        render_input_assumptions(st.session_state["c"])

    at = AppTest.from_function(_app, default_timeout=60).run()
    assert not at.exception
    assert not any(m.label.startswith("Năm LN theo driver") for m in at.multiselect)
    assert any("do dòng cân phai ROE" in c.value for c in at.caption)
    a = at.session_state["c"].assumptions
    assert set(a.driver_base) == set(_DRIVERS)
    for k in _DRIVERS:  # bảng UI quy đổi %, nên so xấp xỉ
        assert a.driver_base[k] == pytest.approx(getattr(a, k))


def test_repo_snapshots_bank_driver_base():
    """Đường thật: repo chụp driver máy đặt ngay khi dựng giả định NH (kịch bản/analyst sửa sau đó mới là 'sửa')."""
    from valuation.data_access import repo
    from valuation.db.session import SessionLocalRead

    with SessionLocalRead() as db:
        a = repo.build_company_data(db, "VCB").assumptions
    assert a.driver_base == {k: list(getattr(a, k)) for k in _DRIVERS}


# --- (4) Một nguồn thuế dài hạn: NOPAT terminal và lá chắn thuế nợ ----------------------------------------


def _levered(tax_rate=0.10, terminal_tax_rate=None):
    from tests.test_r3a_models import _levered_company

    return _levered_company(tax_rate=tax_rate, terminal_tax_rate=terminal_tax_rate)


@pytest.mark.parametrize(
    ("mode", "user", "expected"),
    [
        ("marginal", None, 0.20),  # sector_tax_rates.default
        ("effective", None, 0.10),  # thuế hiệu dụng của mã (ưu đãi dài hạn theo luật)
        ("marginal", 0.15, 0.15),  # người dùng nhập thắng
        ("effective", 0.15, 0.15),
    ],
)
def test_marginal_tax_rate_follows_terminal_tax_mode(monkeypatch, mode, user, expected):
    from valuation.engine.wacc import marginal_tax_rate

    monkeypatch.setitem(load_defaults()["dcf"], "terminal_tax_mode", mode)
    assert marginal_tax_rate(user, 0.10) == pytest.approx(expected)


def test_effective_terminal_mode_same_tax_for_nopat_and_debt_shield(monkeypatch):
    from valuation.engine.models.dcf import DCFValuationModel
    from valuation.engine.wacc import company_wacc, wacc_tax_rate

    monkeypatch.setitem(load_defaults()["dcf"], "terminal_tax_mode", "effective")
    monkeypatch.setitem(load_defaults()["dcf"], "wacc_tax_mode", "marginal")
    c = _levered(tax_rate=0.10)
    # Lá chắn thuế = thuế hiệu dụng 10%: 12% × 0,5 + 8% × 0,9 × 0,5 = 6% + 3,6% = 9,6% (trước sửa vẫn 20% → 9,2%).
    assert wacc_tax_rate(c.assumptions) == pytest.approx(0.10)
    assert company_wacc(c) == pytest.approx(0.096)
    # NOPAT terminal cùng thuế: EBIT5 = 1.000 tỷ × 1,05^5 × 20% → × (1 − 10%).
    out = DCFValuationModel.from_pydantic(c).forecast_drivers()
    assert out["terminal_tax_rate"] == pytest.approx(0.10)
    assert out["terminal_nopat"] == pytest.approx(1_000e9 * 1.05**5 * 0.20 * 0.90)
