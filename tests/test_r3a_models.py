"""r3a_models (20/10/2026) — phản biện vòng 2 (journal wf_677a6cd6-b37): thuế biên trong WACC, thuế terminal
chỉnh được, plug phai ROE ngân hàng, quy đổi ROE bình quân ↔ đầu kỳ cho CK/BH, P/B pro-forma trước phát hành.

Mỗi ca có phép tính tay trong docstring/comment. Test viết TRƯỚC khi sửa (tái hiện lỗi).
"""

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.helpers_bank import build_fake_bank
from valuation.config import load_defaults
from valuation.data_access import repo


def _levered_company(tax_rate=0.05, terminal_tax_rate=None):
    """Vốn hóa 10.000đ × 100 tr cp = 1.000 tỷ = nợ vay 1.000 tỷ → D/(D+E) = 0,5; COE 12%, Rd 8%, rf 3% (sàn 6%)."""
    from tests.test_ai_rnav_sotp import create_dummy_company

    c = create_dummy_company()
    c.historical_bs[-1].short_term_debt = 500
    c.historical_bs[-1].long_term_debt = 500
    a = c.assumptions
    a.cost_of_equity, a.cost_of_debt, a.tax_rate = 0.12, 0.08, tax_rate
    if terminal_tax_rate is not None:
        a.terminal_tax_rate = terminal_tax_rate
    return c


# --- (1) WACC: lá chắn thuế nợ theo thuế BIÊN (cùng nguồn với NOPAT terminal) ---------------------------


def test_company_wacc_uses_marginal_tax_by_default(monkeypatch):
    from valuation.engine.wacc import company_wacc

    # 12% × 0,5 + 8% × (1 − 20%) × 0,5 = 6% + 3,2% = 9,2% (thuế hiệu dụng 5% không vào lá chắn thuế).
    # r4a: đặt chế độ bằng monkeypatch thay vì khoá giá trị config (đang chờ phi duyệt).
    monkeypatch.setitem(load_defaults()["dcf"], "wacc_tax_mode", "marginal")
    monkeypatch.setitem(load_defaults()["dcf"], "terminal_tax_mode", "marginal")
    assert company_wacc(_levered_company(tax_rate=0.05)) == pytest.approx(0.092)


def test_company_wacc_effective_mode_rollback(monkeypatch):
    from valuation.engine.wacc import company_wacc

    # 12% × 0,5 + 8% × (1 − 5%) × 0,5 = 6% + 3,8% = 9,8% (cách cũ).
    monkeypatch.setitem(load_defaults()["dcf"], "wacc_tax_mode", "effective")
    assert company_wacc(_levered_company(tax_rate=0.05)) == pytest.approx(0.098)


def test_company_wacc_follows_user_terminal_tax():
    from valuation.engine.wacc import company_wacc

    # Người dùng nhập thuế terminal 15% → lá chắn thuế cùng 15%: 6% + 8% × 0,85 × 0,5 = 9,4%.
    assert company_wacc(_levered_company(terminal_tax_rate=0.15)) == pytest.approx(
        0.094
    )


def test_wacc_tax_mode_rejects_unknown(monkeypatch):
    from valuation.engine.wacc import company_wacc

    monkeypatch.setitem(load_defaults()["dcf"], "wacc_tax_mode", "magic")
    with pytest.raises(ValueError, match="wacc_tax_mode"):
        company_wacc(_levered_company())


def test_report_wacc_breakdown_matches_model_wacc():
    """Bảng bóc tách WACC của báo cáo phải ra đúng WACC mô hình dùng (trước: tự tính lại với thuế hiệu dụng)."""
    from valuation.report.report_data import _pct, build_wacc_breakdown

    rows = {
        r["label"]: r["value"]
        for r in build_wacc_breakdown(_levered_company(tax_rate=0.05))
    }
    assert rows["WACC"] == _pct(0.092)  # cách cũ ra 9,8%


# --- (2) Thuế terminal người dùng chỉnh được ---------------------------------------------------------------


def test_assumptions_terminal_tax_default_none():
    from tests.test_ai_rnav_sotp import create_dummy_company

    assert create_dummy_company().assumptions.terminal_tax_rate is None


def test_terminal_tax_override_flows_through_from_pydantic():
    from valuation.engine.models.dcf import DCFValuationModel

    # DT 1.000 tỷ × 1,05^5 = 1.276,28; biên EBIT 20% → EBIT5 = 255,26 tỷ; thuế terminal 15% → NOPAT 216,97 tỷ.
    c = _levered_company(tax_rate=0.20, terminal_tax_rate=0.15)
    m = DCFValuationModel.from_pydantic(c)
    out = m.forecast_drivers()
    ebit5 = 1_000e9 * 1.05**5 * 0.20
    assert out["terminal_tax_rate"] == pytest.approx(0.15)
    assert out["terminal_nopat"] == pytest.approx(ebit5 * 0.85)
    # None → theo config (thuế biên 20%).
    out2 = DCFValuationModel.from_pydantic(
        _levered_company(tax_rate=0.20)
    ).forecast_drivers()
    assert out2["terminal_nopat"] == pytest.approx(ebit5 * 0.80)


def test_input_assumptions_has_terminal_tax_input():
    """UI: ô 'thuế terminal (vĩnh viễn)' riêng; ô thuế cũ ghi rõ là giai đoạn dự phóng."""
    from streamlit.testing.v1 import AppTest

    def _app():
        import streamlit as st

        from tests.test_ai_rnav_sotp import create_dummy_company
        from valuation.views.input_assumptions import render_input_assumptions

        if "c" not in st.session_state:
            st.session_state["c"] = create_dummy_company()
        render_input_assumptions(st.session_state["c"])

    at = AppTest.from_function(_app, default_timeout=60).run()
    assert not at.exception
    labels = {n.label: n for n in at.number_input}
    term = next(
        n for lbl, n in labels.items() if "thuế terminal (vĩnh viễn)" in lbl.lower()
    )
    old = next(n for lbl, n in labels.items() if lbl.startswith("Thuế suất TNDN"))
    assert "dự phóng" in (old.help or "").lower()
    assert term.value == pytest.approx(load_defaults()["sector_tax_rates"]["default"])
    term.set_value(0.15).run()
    assert at.session_state["c"].assumptions.terminal_tax_rate == pytest.approx(0.15)


# --- (3) Ngân hàng: cờ dòng cân phai ROE. r4a thay cơ chế "năm theo driver" (bỏ dòng cân → đảo dấu, phản biện
# r3) bằng cộng phần analyst sửa lên đường đã phai — test ở tests/test_r4a_decisions_models.py. ------------


def _bank(**over):
    c = build_fake_bank(sustainable_roe=0.16, coe=0.12, g=0.04)
    c.ticker = "SHB"  # routing có trọng số RI/P/B
    c.assumptions.industry_roe = 0.20
    c.assumptions.roe_convergence = 1.0
    for k, v in over.items():
        setattr(c.assumptions, k, v)
    return c


def test_bank_fade_plug_flag_reports_share_of_year5_income():
    from valuation.engine.forecast_bank import fade_plug_share, forecast_bank_financials
    from valuation.engine.valuate import valuate

    c = _bank()
    proj = forecast_bank_financials(c)
    share = fade_plug_share(proj, c.assumptions.tax_rate)
    # Phần LN năm 5 do dòng cân = điều chỉnh LNTT × (1 − thuế) / LN năm 5.
    assert share == pytest.approx(
        proj[4]["roe_fade_adjustment"] * 0.8 / proj[4]["net_income"]
    )
    thr = load_defaults()["bank_terminal"]["fade_plug_flag_share"]
    assert abs(share) >= thr
    res = valuate(c)
    flag = next(f for f in res["flags"] if f.startswith("BANK_ROE_FADE_PLUG:"))
    assert flag == f"BANK_ROE_FADE_PLUG:{share:.0%}"
    # Cờ cảnh báo, không chặn công bố. r4a: analyst sửa driver không bỏ dòng cân (test_r4a_decisions_models).
    from valuation.engine.flag_descriptions import FLAG_DESCRIPTIONS

    assert FLAG_DESCRIPTIONS["BANK_ROE_FADE_PLUG"]["level"] == "warning"


# --- (4) CK/BH: quy đổi ROE bình quân ↔ đầu kỳ dùng chung với ngân hàng ----------------------------------


def test_avg_roe_helpers_hand_case():
    from valuation.engine.forecast_bank import begin_roe_from_avg, ni_from_avg_roe

    # B = 100, r = 12%, p = 20%: LN = 12 / (1 − 0,12 × 0,8 / 2) = 12 / 0,952 = 12,6050.
    assert ni_from_avg_roe(0.12, 100.0, 0.2) == pytest.approx(12 / 0.952)
    # Lỗ: không cổ tức → LN = r·B / (1 − r/2) = −5 / 1,025.
    assert ni_from_avg_roe(-0.05, 100.0, 0.2) == pytest.approx(-5 / 1.025)
    # Trạng thái dừng: ROE đầu kỳ = ROE bình quân × (1 + g/2) = 0,16 × 1,02.
    assert begin_roe_from_avg(0.16, 0.04) == pytest.approx(0.1632)


def _flat_model(cls):
    # VCSH 1.000 tỷ phẳng, LN 120 → ROE bình quân lịch sử 12% (roe_now = mid = terminal = 12%); 100 tr cp;
    # payout 20%, COE 15%, g 4%.
    from valuation.engine.models import insurance, securities

    cf = {
        "total_equity": 1_000e9,
        "net_income_history": [120.0] * 4,
        "equity_history": [1_000.0] * 4,
        "shares_outstanding": 100e6,
        "current_price": 10_000.0,
    }
    base = (
        securities._cfg()
        if cls is securities.SecuritiesValuationModel
        else insurance._cfg()
    )
    ass = {
        **base,
        "historical_pb_median": 1.0,
        "cost_of_equity": 0.15,
        "risk_free_rate": 0.05,  # g 4% ≤ rf → không bị kẹp TERMINAL_G_CAPPED_AT_RF
        "long_term_growth": 0.04,
        "payout_ratio": 0.20,
        "payout_from_data": True,
    }
    return cls("ZZZ", cf, ass)


def _hand_ri_fvps(r=0.12, p=0.2, coe=0.15, g=0.04, b0=1_000e9, shares=100e6, years=5):
    # LN_t = r·B_t / (1 − r(1 − p)/2) = 0,1260504·B_t; B_{t+1} = B_t + 0,8·LN_t; RI_t = LN_t − COE·B_t.
    k = r / (1 - r * (1 - p) / 2)
    b, pv = b0, 0.0
    for t in range(1, years + 1):
        pv += (k * b - coe * b) / (1 + coe) ** t
        b += k * b * (1 - p)
    # RI terminal = (ROE_T(1 + g/2) − COE) × B5 / (COE − g), chiết khấu 5 năm.
    pv_tv = (r * (1 + g / 2) - coe) * b / (coe - g) / (1 + coe) ** years
    return (b0 + pv + pv_tv) / shares


def test_securities_uses_avg_roe_conversion():
    from valuation.engine.models.securities import SecuritiesValuationModel

    m = _flat_model(SecuritiesValuationModel)
    f1 = m.forecast_drivers()["forecasts"][0]
    assert f1["net_income"] == pytest.approx(1_000e9 * 0.12 / 0.952)
    res = m.perform_valuation()
    assert res["ri_fvps"] == pytest.approx(_hand_ri_fvps())
    # P/B hợp lý dùng ROE đầu kỳ: (0,12 × 1,02 − 0,04)/(0,15 − 0,04) = 0,74909.
    assert res["justified_pb"] == pytest.approx((0.12 * 1.02 - 0.04) / 0.11)


def test_insurance_uses_avg_roe_conversion():
    from valuation.engine.models.insurance import InsuranceValuationModel

    res = _flat_model(InsuranceValuationModel).perform_valuation()
    assert res["ri_fvps"] == pytest.approx(_hand_ri_fvps())
    assert res["justified_pb"] == pytest.approx((0.12 * 1.02 - 0.04) / 0.11)


# --- (5) P/B trước phát hành: pro-forma cộng tiền thu C vào mẫu số khi ước được đáng tin -------------------


def _q_end(y, q):
    return datetime.date(y, 3 * q, 31 if q in (1, 4) else 30)


def _pf_db(prices, actions, quarters):
    """quarters: {(năm, quý): (vốn góp, thặng dư, tiền thu phát hành)} — tỷ đồng (ghi DB theo đồng)."""
    from valuation.db.models import (
        CorporateAction,
        FinancialsQuarterly,
        PricesDaily,
        Ticker,
    )
    from valuation.db.session import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Ticker(ticker="ZZM", company_name="ZZM", is_vn100=True))
    for d, px in prices.items():
        s.add(PricesDaily(ticker="ZZM", trade_date=d, close=px))
    for i, (etype, ex, ratio, listing) in enumerate(actions):
        s.add(
            CorporateAction(
                ticker="ZZM",
                source_site="T",
                source_event_id=str(i),
                event_type=etype,
                title=etype,
                ex_right_date=ex,
                exercise_ratio=ratio,
                listing_date=listing,
                source_tier="T",
                content_hash=str(i),
            )
        )
    for (y, q), vals in quarters.items():
        for stmt, item, v in zip(
            ("BS", "BS", "CF"),
            ("paid_in_capital", "capital_surplus", "proceeds_from_issue_of_shares"),
            vals,
        ):
            if v is None:
                continue
            s.add(
                FinancialsQuarterly(
                    ticker="ZZM",
                    fiscal_year=y,
                    fiscal_quarter=q,
                    is_consolidated=True,
                    is_restated=False,
                    statement=stmt,
                    line_item=item,
                    value=v * 1e9,
                    currency="VND",
                )
            )
    s.commit()
    return s


_D = datetime.date
# Giá 1.300đ × 100 tr cp = 130 tỷ (vốn hóa đã điều chỉnh × số cp hiện tại); VCSH 50 tỷ → P/B thô 2,6x.
_PRICES = {_D(2020, 12, 31): 1_300, _D(2021, 12, 31): 1_300, _D(2022, 12, 30): 1_300}
_EQ = {2020: 50.0, 2021: 50.0, 2022: 50.0}
_RIGHTS = [("RIGHTS_ISSUE", _D(2023, 1, 9), 0.25, _D(2023, 4, 29))]
_KW = {"as_of": _D(2026, 10, 20), "exclude_pre_issue": True}


def test_pre_issue_pb_proforma_hand_case():
    # Cửa sổ quý GDKHQ (Q1/2023) → quý hoàn tất (Q2/2023): tiền thu C = 30 tỷ (CF), xác nhận bằng Δ(vốn góp +
    # thặng dư) = (125 + 5) − (100 + 0) = 30.
    # P/B pro-forma = 130 / (50 + 30) = 1,625x thay vì 2,6x (thô) hay bỏ quan sát (fx2).
    s = _pf_db(
        _PRICES,
        _RIGHTS,
        {(2022, 4): (100, 0, 0), (2023, 1): (125, 5, 30), (2023, 2): (125, 5, 0)},
    )
    flags: list[str] = []
    assert repo.own_history_multiple(
        s, "ZZM", _EQ, 100.0, flags=flags, **_KW
    ) == pytest.approx(1.625)
    assert flags == ["MULTIPLE_PRE_ISSUE_PROFORMA:pb=3(C=30)"]


def test_pre_issue_pb_unreliable_proceeds_falls_back_to_exclusion():
    # Thiếu dòng tiền thu (CF) một quý trong cửa sổ → không ước được C → giữ cách fx2 (loại quan sát) + cờ.
    s = _pf_db(
        _PRICES,
        _RIGHTS,
        {(2022, 4): (100, 0, 0), (2023, 1): (125, 5, None), (2023, 2): (125, 5, 0)},
    )
    flags: list[str] = []
    assert repo.own_history_multiple(s, "ZZM", _EQ, 100.0, flags=flags, **_KW) is None
    assert flags == ["MULTIPLE_PRE_ISSUE_EXCLUDED:pb=3<2023-04-29"]
    # Vốn góp + thặng dư tăng ít hơn tiền thu quá dung sai → dòng tiền không phải vốn cổ phần → không tin.
    tol = load_defaults()["relative_multiples"]["capital_raise_proceeds_tol"]
    s2 = _pf_db(
        _PRICES,
        _RIGHTS,
        {
            (2022, 4): (100, 0, 0),
            (2023, 1): (100 + 30 * (1 - tol) - 1, 0, 30),
            (2023, 2): (100 + 30 * (1 - tol) - 1, 0, 0),
        },
    )
    assert repo.own_history_multiple(s2, "ZZM", _EQ, 100.0, **_KW) is None


def test_pre_issue_pb_proforma_toggle_rollback(monkeypatch):
    monkeypatch.setitem(
        load_defaults()["relative_multiples"], "capital_raise_proforma", False
    )
    s = _pf_db(
        _PRICES,
        _RIGHTS,
        {(2022, 4): (100, 0, 0), (2023, 1): (125, 5, 30), (2023, 2): (125, 5, 0)},
    )
    assert (
        repo.own_history_multiple(s, "ZZM", _EQ, 100.0, **_KW) is None
    )  # cách fx2: loại cả 3


def test_pre_issue_pb_proceeds_booked_before_period_end_kept_unadjusted():
    # Quyền mua GDKHQ 10/10/2022, niêm yết 15/02/2023, tiền thu ghi Q4/2022: VCSH 31/12/2022 đã gồm C → quan sát
    # 2022 sạch (giữ nguyên 2,6x); 2020, 2021 pro-forma 1,625x → trung vị 1,625.
    s = _pf_db(
        _PRICES,
        [("RIGHTS_ISSUE", _D(2022, 10, 10), 0.25, _D(2023, 2, 15))],
        {(2022, 3): (100, 0, 0), (2022, 4): (125, 5, 30), (2023, 1): (125, 5, 0)},
    )
    flags: list[str] = []
    assert repo.own_history_multiple(
        s, "ZZM", _EQ, 100.0, flags=flags, **_KW
    ) == pytest.approx(1.625)
    assert flags == ["MULTIPLE_PRE_ISSUE_PROFORMA:pb=2(C=30)"]


def test_pre_issue_pb_ignores_unpublished_quarters():
    # as_of 15/04/2023: Q1/2023 chưa tới hạn công bố (30 ngày) → chưa ước được C → loại (không lookahead).
    s = _pf_db(
        _PRICES,
        _RIGHTS,
        {(2022, 4): (100, 0, 0), (2023, 1): (125, 5, 30), (2023, 2): (125, 5, 0)},
    )
    kw = {"as_of": _D(2023, 4, 15), "exclude_pre_issue": True}
    assert repo.own_history_multiple(s, "ZZM", _EQ, 100.0, **kw) is None


def test_pre_issue_pb_proforma_rejected_when_implied_premoney_implausible():
    """Pro-forma dựa trên đẳng thức vốn hóa điều chỉnh = vốn hóa cũ + C (một đợt, giá không đổi giữa cuối kỳ và đợt).
    Vốn hóa cũ ngụ ý = 130 − 120 = 10 tỷ → P/B cũ ngụ ý 10/50 = 0,2x < sàn relative_multiples.pb (0,3x): đẳng thức
    không đứng (giá tăng mạnh/nhiều đợt — VIX FY2022: 8.902 − 17.578 < 0) → không pro-forma, loại như fx2.
    """
    s = _pf_db(
        _PRICES,
        _RIGHTS,
        {(2022, 4): (100, 0, 0), (2023, 1): (220, 0, 120), (2023, 2): (220, 0, 0)},
    )
    flags: list[str] = []
    assert repo.own_history_multiple(s, "ZZM", _EQ, 100.0, flags=flags, **_KW) is None
    assert flags == ["MULTIPLE_PRE_ISSUE_EXCLUDED:pb=3<2023-04-29"]
    assert 10 / 50 < load_defaults()["relative_multiples"]["pb"][0]
