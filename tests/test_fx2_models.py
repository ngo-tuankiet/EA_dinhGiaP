"""fx2_models (20/10/2026) — sửa 10 phát hiện mô hình định giá của vòng phản biện (journal wf_8d44f5a2-ff9).

Mỗi ca có phép tính tay trong docstring/comment. Test viết TRƯỚC khi sửa (tái hiện lỗi).
"""

import datetime
from types import SimpleNamespace as N

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.helpers_bank import build_fake_bank
from valuation.config import load_defaults
from valuation.data_access import repo
from valuation.db.session import SessionLocalRead

Q4_AS_OF = datetime.date(
    2026, 4, 15
)  # Q4/2025 đã công bố (hạn 30 ngày), Q1/2026 chưa → kỳ cuối = FY2025


@pytest.fixture(scope="module")
def db():
    s = SessionLocalRead()
    yield s
    s.close()


# --- (1) VALUATION_LEGS_DIVERGE dùng chung cho CK/BH/NH -------------------------------------------


def test_legs_diverge_shared_module_dse_hand_case():
    from valuation.engine.guardrails import legs_diverge

    # Ngưỡng ĐỌC từ config (publication_gate.leg_ratio_review; phi đặt 5,0 ngày 20/10/2026) rồi sinh ca biên.
    thr = float(load_defaults()["publication_gate"]["leg_ratio_review"])
    # Đúng bằng ngưỡng → chưa vênh (so sánh >).
    assert not legs_diverge(1_000, 1_000 * thr)
    assert legs_diverge(1_000, 1_000 * thr * 1.01)
    assert legs_diverge(1_000 * thr * 1.01, 1_000)  # đối xứng
    # DSE: RI 2.746 vs P/B lịch sử 29.589 → 10,78x — vênh với mọi ngưỡng ≤ 10,78.
    assert legs_diverge(2_746, 29_589) == (29_589 / 2_746 > thr)
    assert legs_diverge(
        0.0, 5_000
    )  # một chân 0 (vd RI bỏ qua vì COE ≤ g) mà chân kia dương
    assert not legs_diverge(-1.0, -2.0)  # cả hai chân âm: đã có cờ chân âm riêng


def test_legs_diverge_config_backward_compatible(monkeypatch):
    """Config cũ chỉ có dcf.leg_ratio_review vẫn đọc được (giữ tương thích)."""
    from valuation.engine.guardrails import legs_diverge

    cfg = load_defaults()
    monkeypatch.delitem(cfg["publication_gate"], "leg_ratio_review")
    monkeypatch.setitem(cfg["dcf"], "leg_ratio_review", 12.0)
    assert not legs_diverge(2_746, 29_589)  # 10,78 < 12


def _sec_model(cls, hist_pb: float, roe: float = 0.12):
    # VCSH 1.000 tỷ phẳng, LN = ROE × 1.000; 100 triệu cp → BVPS 10.000đ; chân P/B = hist_pb × 10.000đ.
    cf = {
        "total_equity": 1_000e9,
        "net_income_history": [1_000 * roe] * 4,
        "equity_history": [1_000.0] * 4,
        "shares_outstanding": 100e6,
        "current_price": 10_000.0,
    }
    ass = {
        "historical_pb_median": hist_pb,
        "cost_of_equity": 0.15,
        "risk_free_rate": 0.03,
        "long_term_growth": 0.04,
        "payout_from_data": True,
    }
    from valuation.engine.models import insurance, securities

    base = (
        securities._cfg()
        if cls is securities.SecuritiesValuationModel
        else insurance._cfg()
    )
    return cls("ZZZ", cf, {**base, **ass})


@pytest.mark.parametrize("kind", ["securities", "insurance"])
def test_ri_pb_models_flag_divergent_legs(kind):
    from valuation.engine.models.insurance import InsuranceValuationModel
    from valuation.engine.models.securities import SecuritiesValuationModel

    cls = SecuritiesValuationModel if kind == "securities" else InsuranceValuationModel
    wide = _sec_model(cls, hist_pb=4.0).perform_valuation()  # chân P/B 40.000đ
    ratio = max(wide["ri_fvps"], wide["pb_fvps"]) / min(
        wide["ri_fvps"], wide["pb_fvps"]
    )
    thr = load_defaults()["publication_gate"]["leg_ratio_review"]
    assert ratio > thr
    assert "VALUATION_LEGS_DIVERGE" in wide["flags"]
    near = _sec_model(
        cls, hist_pb=1.0
    ).perform_valuation()  # chân P/B 10.000đ, RI cùng cỡ
    ratio = max(near["ri_fvps"], near["pb_fvps"]) / min(
        near["ri_fvps"], near["pb_fvps"]
    )
    assert ratio < thr
    assert "VALUATION_LEGS_DIVERGE" not in near["flags"]


def test_bank_valuate_flags_divergent_legs():
    from valuation.engine.valuate import valuate

    # Ticker SHB để routing cho trọng số 0,5/0,5. VCSH 1.000 tỷ, 100 tr cp; P/B lịch sử 12x → chân P/B 120.000đ,
    # RI ~ 18 nghìn → ~6,6x, vượt ngưỡng publication_gate.leg_ratio_review (5,0 từ r4a; trước 8x với ngưỡng 3,0).
    c = build_fake_bank(sustainable_roe=0.16, coe=0.12, g=0.04)
    c.ticker = "SHB"
    c.assumptions.historical_pb_median = 12.0
    res = valuate(c)
    assert (
        res["relative_fv"] / res["intrinsic_fv"]
        > load_defaults()["publication_gate"]["leg_ratio_review"]
    )
    assert "VALUATION_LEGS_DIVERGE" in res["flags"]
    assert res["publication_allowed"] is False
    c2 = build_fake_bank(sustainable_roe=0.16, coe=0.12, g=0.04)
    c2.ticker = "SHB"
    c2.assumptions.historical_pb_median = 1.5
    assert "VALUATION_LEGS_DIVERGE" not in valuate(c2)["flags"]


# --- (2) NH: ROE fade năm 3–5 về ROE terminal; một định nghĩa ROE (VCSH bình quân) -------------------


def _bank(industry_roe=0.1697, lam=1.0, payout=0.25):
    c = build_fake_bank(sustainable_roe=0.209, coe=0.1192, g=0.04, payout=payout)
    c.assumptions.industry_roe = industry_roe
    c.assumptions.roe_convergence = lam
    return c


def _avg_roe(proj, b_prev, i):
    b0 = b_prev if i == 0 else proj[i - 1]["total_equity"]
    return proj[i]["net_income"] / ((b0 + proj[i]["total_equity"]) / 2)


def test_bank_roe_fades_to_terminal_in_years_3_to_5():
    from valuation.engine.forecast_bank import forecast_bank_financials

    c = _bank()
    b0 = c.historical_bs[-1].total_equity
    drv = forecast_bank_financials(c, fade_to_terminal=False)
    fad = forecast_bank_financials(c)
    # Năm 1–2 giữ nguyên driver.
    for i in (0, 1):
        assert fad[i]["net_income"] == pytest.approx(drv[i]["net_income"])
    # Năm 3, w = 1/3: r = r_drv + (0,1697 − r_drv)/3 trên VCSH bình quân; NI = r·B2 / (1 − r(1 − p)/2).
    b2, p = drv[1]["total_equity"], 0.25
    ni_d = drv[2]["net_income"]
    r_drv = ni_d / (b2 + ni_d * (1 - p) / 2)
    r3 = r_drv + (0.1697 - r_drv) / 3
    assert fad[2]["net_income"] == pytest.approx(r3 * b2 / (1 - r3 * (1 - p) / 2))
    assert _avg_roe(fad, b0, 2) == pytest.approx(r3)
    # Năm 5 (w = 1): ROE bình quân = ROE terminal → năm 6 (ROE_T trên VCSH bình quân) nối liền năm 5.
    assert _avg_roe(fad, b0, 4) == pytest.approx(0.1697)
    # Dòng điều chỉnh minh bạch ở cấp LNTT: LNTT = PPOP − dự phòng + điều chỉnh, LNST = LNTT × (1 − t).
    y3 = fad[2]
    assert y3["pretax_income"] == pytest.approx(
        y3["pre_provision_profit"] - y3["provision_expense"] + y3["roe_fade_adjustment"]
    )
    assert y3["net_income"] == pytest.approx(
        y3["pretax_income"] * (1 - c.assumptions.tax_rate)
    )


def test_bank_terminal_ri_and_pb_use_average_roe_steady_state():
    from valuation.engine.models.bank_general import BankGeneralValuationModel

    m = BankGeneralValuationModel(_bank())
    assert m.terminal_roe == pytest.approx(0.1697)
    # Trạng thái dừng VCSH tăng g: VCSH bình quân năm 6 = B5(1 + g/2) → LN6 = ROE_T·B5·(1 + g/2).
    # ROE trên VCSH đầu kỳ = 0,1697 × 1,02 = 0,173094; P/B hợp lý = (0,173094 − 0,04)/(0,1192 − 0,04) = 1,68048.
    pb = m.calculate_pb_valuation()
    assert pb["target_pb"] == pytest.approx(1.68048, abs=1e-5)
    assert pb["fair_value_per_share"] == pytest.approx(16_804.8, abs=1.0)
    b5 = m.projections[-1]["total_equity"]
    ri = m.calculate_residual_income()
    assert ri["pv_terminal_ri"] == pytest.approx(
        (0.173094 - 0.1192) * b5 / 0.0792 / 1.1192**5
    )


def test_bank_industry_roe_on_average_equity(monkeypatch):
    """ROE ngành cùng định nghĩa roe5: LNST / VCSH bình quân (cuối năm trước, cuối năm). Kỳ cuối TTM chưa trọn
    năm bị loại; kỳ cuối là FY đủ 4 quý (Q4) thì giữ (mục 7)."""

    def peer(years, equity, ni, ttm):
        return N(
            historical_is=[N(year=y, net_income=v) for y, v in zip(years, ni)],
            historical_bs=[N(year=y, total_equity=e) for y, e in zip(years, equity)],
            last_period_is_ttm=ttm,
        )

    # A: VCSH 100 → 120 → 140 → 160, LN 22 / 26 / 30: ROE bình quân 22/110 = 0,20; 26/130 = 0,20; 30/150 = 0,20;
    #    kỳ cuối TTM (LN 99) bị loại → 0,20.
    # B: VCSH 100 → 100 → 100, LN 10 / 12 → 0,10; 0,12, kỳ cuối là FY (Q4) → giữ → trung vị 0,11.
    # C: VCSH 200 → 300 → 300, LN 25 / 45: 25/250 = 0,10; 45/300 = 0,15 → 0,125 (TTM 0,9 bị loại).
    peers = {
        "A": peer(
            [2022, 2023, 2024, 2025, 2026],
            [100, 120, 140, 160, 170],
            [0, 22, 26, 30, 99],
            True,
        ),
        "B": peer([2023, 2024, 2025], [100, 100, 100], [0, 10, 12], False),
        "C": peer(
            [2023, 2024, 2025, 2026], [200, 300, 300, 310], [0, 25, 45, 279], True
        ),
    }
    routing = {t: {"sector": "NH"} for t in peers}
    monkeypatch.setattr(
        "valuation.engine.sector_router._router", lambda: N(routing_data=routing)
    )
    monkeypatch.setattr(repo, "build_company_data", lambda db, p, **k: peers[p])
    monkeypatch.setattr(repo, "CompanyBank", N)
    monkeypatch.setattr(repo, "current_pb", lambda p: 1.0)
    repo._PEER_CACHE.clear()
    try:
        assert repo.bank_industry_roe(None, "NH") == pytest.approx(
            0.125
        )  # trung vị(0,20; 0,11; 0,125)
    finally:
        repo._PEER_CACHE.clear()


# --- (3) DCF: thuế suất biên cho NOPAT terminal -------------------------------------------------------


def _dcf(tax=0.10, **ass_over):
    from valuation.engine.models.dcf import DCFValuationModel

    cf = {
        "total_equity": 5_000e9,
        "total_assets": 8_000e9,
        "cash_and_equivalents": 1_000e9,
        "total_debt": 500e9,
        "minority_interest": 0.0,
        "non_operating_assets": 0.0,
        "total_revenue": 4_000e9,
        "cogs": 2_800e9,
        "ebitda": 800e9,
        "shares_outstanding": 100e6,
        "current_price": 50_000.0,
    }
    ass = {
        "cost_of_equity": 0.12,
        "wacc": 0.11,
        "revenue_growth": [0.10] * 5,
        "ebit_margin": [0.15] * 5,
        "tax_rate": tax,
        "capex_to_revenue": [0.05] * 5,
        "depr_to_revenue": [0.04] * 5,
        "dso": [30.0] * 5,
        "dio": [30.0] * 5,
        "dpo": [30.0] * 5,
        "target_ev_ebitda": 8.0,
        "long_term_growth": 0.04,
        "weight_dcf": 0.5,
        **ass_over,
    }
    return DCFValuationModel("TST", cf, ass)


def test_terminal_nopat_uses_marginal_tax_by_default(monkeypatch):
    # Năm 5: DT = 4.000 × 1,1^5 = 6.442,04 tỷ; EBIT = 15% → 966,31 tỷ. Thuế hiệu dụng 10% (ưu đãi có thời hạn)
    # cho năm 1–5; terminal dùng thuế phổ thông sector_tax_rates.default 20%: 966,31 × 0,8 = 773,04 tỷ.
    monkeypatch.setitem(load_defaults()["dcf"], "terminal_tax_mode", "marginal")
    out = _dcf(tax=0.10).forecast_drivers()
    ebit5 = 4_000e9 * 1.1**5 * 0.15
    assert out["forecasts"][-1]["nopat"] == pytest.approx(ebit5 * 0.90)
    assert out["terminal_nopat"] == pytest.approx(ebit5 * 0.80)
    assert out["terminal_tax_rate"] == pytest.approx(0.20)


def test_terminal_tax_effective_mode_rollback(monkeypatch):
    monkeypatch.setitem(load_defaults()["dcf"], "terminal_tax_mode", "effective")
    out = _dcf(tax=0.10).forecast_drivers()
    assert out["terminal_nopat"] == pytest.approx(out["forecasts"][-1]["nopat"])


def test_terminal_tax_marginal_applies_to_midcycle_branch():
    # Biên giữa chu kỳ 10% × DT năm 5 × (1 − 20%).
    out = _dcf(tax=0.10, mid_cycle_ebit_margin=0.10).forecast_drivers()
    assert out["terminal_nopat"] == pytest.approx(4_000e9 * 1.1**5 * 0.10 * 0.80)


# --- (4) EV/EBITDA mã không chu kỳ: bội số trailing × EBITDA TTM ----------------------------------------


def _ev_model(cyclical: bool):
    from valuation.engine.models.ev_ebitda import EVEBITDAValuationModel

    cf = {
        "ebitda_history": [2_404.0, 2_939.0, 2_942.0],  # tỷ, kỳ cuối = TTM (PC1)
        "revenue_history": [10_000.0, 11_000.0, 12_000.0],
        "total_debt": 0.0,
        "cash_and_equivalents": 0.0,
        "minority_interest": 0.0,
        "non_operating_assets": 0.0,
        "shares_outstanding": 100e6,
        "current_price": 10_000.0,
    }
    return EVEBITDAValuationModel(
        "ZZZ", cf, {"target_ev_ebitda": 6.65, "norm_years": 3, "cyclical": cyclical}
    )


def test_ev_ebitda_noncyclical_applies_trailing_multiple_to_ttm():
    # 2.942 tỷ × 6,65 / 100 tr cp = 195.643đ (cũ: trung bình chồng kỳ 2.761,67 → 183.651đ).
    res = _ev_model(cyclical=False).perform_valuation()
    assert res["normalized_ebitda"] == pytest.approx(2_942e9)
    assert res["blended_fair_value_per_share"] == pytest.approx(2_942e9 * 6.65 / 100e6)


def test_ev_ebitda_cyclical_still_midcycle():
    # Biên EBITDA [24,04%; 26,72%; 24,52%] → trung vị 24,52% × DT TTM 12.000 = 2.942 (trùng TTM ở ca này);
    # đổi DT TTM để tách: giữ nguyên nhánh giữa chu kỳ.
    m = _ev_model(cyclical=True)
    m.current_financials["revenue_history"] = [10_000.0, 11_000.0, 14_000.0]
    res = m.perform_valuation()
    margins = sorted([2_404 / 10_000, 2_939 / 11_000, 2_942 / 14_000])
    assert res["normalized_ebitda"] == pytest.approx(margins[1] * 14_000 * 1e9)


# --- (5) Tỷ lệ biên ΔDR/ΔDT chỉ cho mã khai báo (KCN cho thuê) -------------------------------------------


def test_deferred_revenue_ratio_only_for_declared_tickers(db):
    assert "SIP" in load_defaults()["dcf"]["deferred_revenue_operating_tickers"]
    # PHR: DR là tiền đền bù/thuê đất trả trước, không gắn doanh thu cao su → 0 (trước sửa −0,419).
    assert (
        repo.build_company_data(db, "PHR").assumptions.deferred_revenue_to_revenue
        == 0.0
    )
    assert (
        repo.build_company_data(db, "SIP").assumptions.deferred_revenue_to_revenue > 0.5
    )


# --- (6) Nhánh P/E chu kỳ trong chân P/E phụ của DCF: không còn code chết -----------------------------


def test_dcf_pe_leg_rejects_cyclical():
    m = _dcf(tax=0.20, secondary_multiple="PE", target_pe=10.0, cyclical=True)
    m.current_financials["net_income_history"] = [10e9, 2e9, 6e9, 8e9]
    with pytest.raises(ValueError, match="PE_LEG_CYCLICAL"):
        m.perform_valuation()


# --- (7) Kỳ Q4: TTM = năm tài chính đầy đủ, không bị loại -------------------------------------------------


def test_q4_as_of_full_year_not_marked_ttm(db):
    sec = repo.build_company_data(db, "SSI", as_of=Q4_AS_OF)
    assert sec.historical_cf[-1].year == 2025
    assert (
        sec.historical_cf[-1].is_ttm_period is False
    )  # Q4 → kỳ cuối là FY2025 đủ 4 quý
    bank = repo.build_company_data(db, "VCB", as_of=Q4_AS_OF)
    assert bank.historical_is[-1].year == 2025 and bank.last_period_is_ttm is False
    assert (
        repo.build_company_data(db, "VCB").last_period_is_ttm is True
    )  # hôm nay: TTM đến Q2/2026


def test_q4_payout_window_includes_latest_fy(db):
    from valuation.engine.models.securities import cash_payout_ratio

    sec = repo.build_company_data(db, "SSI", as_of=Q4_AS_OF)
    ni = {i.year: i.net_income for i in sec.historical_is}
    cfs = [cf for cf in sec.historical_cf if cf.year in (2023, 2024, 2025)]
    expected = sum(cf.dividends_paid for cf in cfs) / sum(ni[cf.year] for cf in cfs)
    assert cash_payout_ratio(
        sec.historical_is, sec.historical_cf, 1.0, 3
    ) == pytest.approx(expected)


# --- (8) RNAV AI: dòng tiền dự án chưa trừ nợ chiết khấu bằng WACC --------------------------------------


def test_rnav_project_cash_flows_default_to_wacc():
    from tests.test_ai_rnav_sotp import _project, create_dummy_company
    from valuation.engine.models.rnav import RNAVValuationModel

    # Vốn hóa 10.000đ × 100 tr = 1.000 tỷ; nợ 500 tỷ; COE = 3% + 1,0 × 4,5% = 7,5%; Rd 6% × (1 − 20%) = 4,8%.
    # WACC = 7,5% × 1.000/1.500 + 4,8% × 500/1.500 = 6,6% (> sàn rf + 3% = 6%). PV = 600 / 1,066 = 562,85 tỷ.
    assert load_defaults()["proxy_valuation"]["rnav_project_discount_rate"] == "wacc"
    comp = create_dummy_company(rnav_projects=[_project()])
    comp.assumptions.rnav_wacc = None
    comp.assumptions.rnav_discount = 0.0
    res = RNAVValuationModel.from_pydantic(comp).perform_valuation()
    assert res["nav_equity_before_discount"] / 1e9 == pytest.approx(
        1_000 + 600 / 1.066 - 200, abs=0.01
    )


# --- (9) Bội số lịch sử: loại quan sát trước đợt phát hành có thu tiền ----------------------------------


def _hist_db(prices, actions):
    from valuation.db.models import CorporateAction, PricesDaily, Ticker
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
    s.commit()
    return s


def test_own_history_drops_observations_before_rights_issue_completion():
    d = datetime.date
    prices = {
        d(2022, 12, 30): 20_000,
        d(2023, 12, 29): 22_000,
        d(2024, 12, 31): 24_000,
        d(2025, 12, 31): 26_000,
    }
    # 100 tr cp hiện tại; VCSH (tỷ) 1.000 mỗi năm → P/B quan sát 2,0 / 2,2 / 2,4 / 2,6.
    eq = {2022: 1_000.0, 2023: 1_000.0, 2024: 1_000.0, 2025: 1_000.0}
    # Quyền mua 25% GDKHQ 09/01/2024, niêm yết (hoàn tất, tiền vào VCSH) 29/04/2024 → loại 2022, 2023.
    s = _hist_db(prices, [("RIGHTS_ISSUE", d(2024, 1, 9), 0.25, d(2024, 4, 29))])
    flags: list[str] = []
    kw = {"as_of": d(2026, 10, 20), "exclude_pre_issue": True}
    assert (
        repo.own_history_multiple(s, "ZZM", eq, 100.0, flags=flags, **kw) is None
    )  # còn 2 < 3
    assert flags == ["MULTIPLE_PRE_ISSUE_EXCLUDED:pb=2<2024-04-29"]
    # Không có đợt phát hành: trung vị(2,0; 2,2; 2,4; 2,6) = 2,3.
    s2 = _hist_db(prices, [])
    assert repo.own_history_multiple(s2, "ZZM", eq, 100.0, **kw) == pytest.approx(2.3)
    # Nhóm ngoài capital_raise_exclusion_groups (mặc định): giữ nguyên lịch sử.
    assert repo.own_history_multiple(
        s, "ZZM", eq, 100.0, as_of=d(2026, 10, 20)
    ) == pytest.approx(2.3)


def test_pre_issue_exclusion_scoped_to_ck_bh():
    """Đo fx2: áp cho NH/DCF đổi FV ngược chiều méo (SHB +34%, GMD −25%) vì thiếu giá phát hành để pro-forma."""
    groups = load_defaults()["relative_multiples"]["capital_raise_exclusion_groups"]
    assert set(groups) == {"CK", "BH"}


def test_own_history_ignores_small_or_future_issues():
    d = datetime.date
    prices = {
        d(2022, 12, 30): 20_000,
        d(2023, 12, 29): 22_000,
        d(2024, 12, 31): 24_000,
        d(2025, 12, 31): 26_000,
    }
    eq = {2022: 1_000.0, 2023: 1_000.0, 2024: 1_000.0, 2025: 1_000.0}
    min_ratio = load_defaults()["relative_multiples"]["capital_raise_min_ratio"]
    s = _hist_db(
        prices,
        [
            (
                "PRIVATE_PLACEMENT",
                d(2025, 3, 1),
                min_ratio / 2,
                None,
            ),  # dưới ngưỡng trọng yếu
            (
                "RIGHTS_ISSUE",
                d(2027, 1, 9),
                0.5,
                None,
            ),  # GDKHQ sau as_of: giá/số cp chưa phản ánh
        ],
    )
    assert repo.own_history_multiple(
        s, "ZZM", eq, 100.0, as_of=d(2026, 10, 20), exclude_pre_issue=True
    ) == pytest.approx(2.3)


def test_dse_pb_leg_drops_pre_rights_observations(db):
    """DSE quyền mua 25% GDKHQ 09/01/2026, niêm yết 29/04/2026. fx2: FY2024 2,52x, FY2025 2,33x bị loại → trung vị
    nhóm. r3a: pro-forma với tiền thu C = 1.284,6 tỷ (LCTT Q1/2026 = Δ vốn góp + thặng dư): FY2024 10.175/(4.030 +
    1.285) = 1,91x, FY2025 10.021/(4.302 + 1.285) = 1,79x → đủ 3 quan sát (cùng TTM), không còn rơi về trung vị
    nhóm; hai chân RI/P/B vẫn vênh > 3x → chặn công bố."""
    c = repo.build_company_data(db, "DSE")
    assert "MULTIPLE_PRE_ISSUE_PROFORMA:pb=2(C=1285)" in c.data_flags
    assert not any(f.startswith(("MULTIPLE_PRE_ISSUE_EXCLUDED", "MULTIPLE_FROM_PEER_MEDIAN")) for f in c.data_flags)
    assert c.assumptions.historical_pb_median == pytest.approx(1.794, abs=0.01)
    from valuation.engine.valuate import valuate

    res = valuate(c)
    assert (
        "VALUATION_LEGS_DIVERGE" in res["flags"] and res["publication_allowed"] is False
    )


# --- (10) CĐKKS theo giá sổ: cờ khi trọng yếu (không đổi FV) ------------------------------------------


def test_minority_at_book_material_flag_without_changing_fv():
    thr = load_defaults()["dcf"]["minority_book_review"]
    # VCSH (gồm CĐKKS) 5.000 tỷ. CĐKKS 1.000 → VCSH mẹ 4.000, tỷ lệ 25%.
    big = _dcf(tax=0.20)
    big.current_financials["minority_interest"] = 1_000e9
    res = big.perform_valuation()
    assert 1_000 / 4_000 > thr and "MINORITY_AT_BOOK_MATERIAL" in big.valuation_warnings
    small = _dcf(tax=0.20)
    small.current_financials["minority_interest"] = 0.04 * 5_000e9
    res_small = small.perform_valuation()
    assert "MINORITY_AT_BOOK_MATERIAL" not in small.valuation_warnings
    # FV không đổi theo cờ: chênh FV đúng bằng chênh CĐKKS sổ sách / cp ở cả hai chân.
    diff = (1_000e9 - 200e9) / 100e6
    assert res_small["dcf_fvps"] - res["dcf_fvps"] == pytest.approx(diff)
