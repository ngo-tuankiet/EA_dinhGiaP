"""Bước s5 (20/10/2026): SOTP theo cổ phần niêm yết (SOTP_HOLDINGS), đổi phương pháp PC1/HDG/VCG/SIP,
doanh thu chưa thực hiện trong vốn lưu động.

Số liệu tính tay; đơn vị tỷ đồng trừ khi ghi chú.
"""

import datetime
from types import SimpleNamespace as N

import pytest

from valuation.config import load_sotp_holdings, sotp_holdings_for
from valuation.engine.models.sotp import SOTPValuationModel


def _holding(ticker, stake, mc, bv=None, cv=None, **over):
    return {"ticker": ticker, "stake": stake, "market_cap_bn": mc, "book_equity_bn": bv,
            "carrying_value_bn": cv, "price_stale": False, "source": "https://x", **over}


def _cfg(holdings, reviewed_by="phi", as_of="2026-10-01", valuation_date="2026-10-20"):
    return {"as_of": as_of, "reviewed_by": reviewed_by, "review_ttl_days": 180,
            "valuation_date": valuation_date, "holdings": holdings}


def _model(cfg, parent_equity_bn=40_000.0, shares_m=1_520.5, price=70_000.0, discount=0.10):
    cf = {
        "total_equity": parent_equity_bn * 1e9, "cash_and_equivalents": 0.0, "total_debt": 0.0,
        "minority_interest": 0.0, "net_income_history": [1_000.0] * 3,
        "shares_outstanding": shares_m * 1e6, "current_price": price,
    }
    a = {"sotp_operating_pe": 11.0, "sotp_earnings_weight": 0.6, "sotp_holding_discount": discount,
         "sotp_segments": [], "sotp_holdings": cfg}
    return SOTPValuationModel("TSTH", cf, a)


MSN_LIKE = [_holding("MCHX", 0.66, 181_000.0, bv=18_700.0), _holding("TCBX", 0.198, 233_100.0, bv=189_000.0)]


# --- F1: công thức (tính tay) ---------------------------------------------------------------------


def test_holdings_value_hand_calc():
    # 0,66 × (181.000 − 18.700) = 107.118; 0,198 × (233.100 − 189.000) = 8.731,8
    # (40.000 + 107.118 + 8.731,8) / 1.520,5 tr cp × 1000 = 102.499,05đ; × (1 − 0,10) = 92.249,14đ
    m = _model(_cfg(MSN_LIKE))
    res = m.perform_valuation()
    assert res["blended_fair_value_per_share"] == pytest.approx(155_849.8 / 1_520.5 * 1_000 * 0.9, rel=1e-9)
    assert res["blended_fair_value_per_share"] == pytest.approx(92_249.14, abs=0.01)
    assert res["sotp_holdings_breakdown"]["reval_bn"] == pytest.approx(115_849.8)
    assert res["sotp_holdings_breakdown"]["holdings"]["MCHX"]["reval_bn"] == pytest.approx(107_118.0)


@pytest.mark.parametrize("discount,expected", [(0.0, 102_499.05), (0.15, 87_124.19)])
def test_holdings_discount_from_assumption(discount, expected):
    m = _model(_cfg(MSN_LIKE), discount=discount)
    assert m.perform_valuation()["blended_fair_value_per_share"] == pytest.approx(expected, abs=0.01)


def test_holdings_carrying_value_overrides_book_share():
    # Khoản đầu tư ghi giá gốc: 0,10 × 30.742 − 3.297 = −222,8 tỷ
    m = _model(_cfg([_holding("EIBX", 0.10, 30_742.0, bv=25_000.0, cv=3_297.0)]),
               parent_equity_bn=10_000.0, shares_m=1_000.0, discount=0.0)
    res = m.perform_valuation()
    assert res["sotp_holdings_breakdown"]["reval_bn"] == pytest.approx(-222.8)
    assert res["blended_fair_value_per_share"] == pytest.approx(9_777.2 / 1_000.0 * 1_000)


def test_sotp_discount_default_comes_from_config():
    from valuation.config import load_defaults
    from valuation.models.financials import Assumptions

    a = Assumptions(revenue_growth=[0.1] * 5, ebit_margin=[0.1] * 5, capex_to_revenue=[0.05] * 5,
                    depr_to_revenue=[0.04] * 5, dso=[30] * 5, dio=[30] * 5, dpo=[30] * 5,
                    interest_rate=[0.06] * 5)
    assert a.sotp_discount == load_defaults()["proxy_valuation"]["sotp_holding_discount"]


# --- F1: cờ và cổng công bố -----------------------------------------------------------------------


def test_holdings_mode_drops_proxy_and_flags_unverified():
    m = _model(_cfg(MSN_LIKE, reviewed_by=None, as_of=None))
    res = m.perform_valuation()
    assert "VALUATION_PROXY" not in res["flags"] and "VALUATION_PROXY" not in m.valuation_warnings
    assert {"SOTP_HOLDINGS_MODE", "SOTP_UNLISTED_AT_BOOK", "SOTP_HOLDINGS_UNVERIFIED"} <= set(res["flags"])
    assert "SOTP_HOLDINGS_STALE" not in res["flags"]
    assert not any(f.startswith("PROXY_IMPLAUSIBLE") for f in res["flags"])  # cổng proxy không áp


def test_holdings_reviewed_is_clean():
    res = _model(_cfg(MSN_LIKE)).perform_valuation()
    assert "SOTP_HOLDINGS_UNVERIFIED" not in res["flags"] and "SOTP_HOLDINGS_STALE" not in res["flags"]
    assert res["not_rated"] is False


def test_holdings_stale_review_or_price():
    # 2026-04-20 → 2026-10-20 = 183 ngày > 180
    assert "SOTP_HOLDINGS_STALE" in _model(_cfg(MSN_LIKE, as_of="2026-04-20")).perform_valuation()["flags"]
    assert "SOTP_HOLDINGS_STALE" not in _model(_cfg(MSN_LIKE, as_of="2026-04-23")).perform_valuation()["flags"]
    stale_px = [_holding("MCHX", 0.66, 181_000.0, bv=18_700.0, price_stale=True)]
    assert "SOTP_HOLDINGS_STALE" in _model(_cfg(stale_px)).perform_valuation()["flags"]


def test_unresolved_holding_falls_back_to_proxy():
    hs = [MSN_LIKE[0], {"ticker": "ZZZ", "stake": 0.2, "carrying_value_bn": None, "source": "https://x",
                        "error": "Không tìm thấy ticker ZZZ trong DB"}]
    res = _model(_cfg(hs)).perform_valuation()
    assert {"VALUATION_PROXY", "SOTP_HOLDINGS_INCOMPLETE"} <= set(res["flags"])
    assert "SOTP_HOLDINGS_MODE" not in res["flags"]


@pytest.mark.parametrize("flag,blocked", [
    ("SOTP_HOLDINGS_UNVERIFIED", True), ("SOTP_HOLDINGS_STALE", True), ("SOTP_HOLDINGS_MODE", False),
])
def test_publication_gate_blocks_unverified_or_stale(monkeypatch, flag, blocked):
    import valuation.config as cfg_mod
    import valuation.report.verified_summary as vs
    from valuation.engine.valuate import _apply_publication_gate

    monkeypatch.setattr(vs, "run_deterministic_checks", lambda *a, **k: [])
    monkeypatch.setattr(cfg_mod, "active_event_hold", lambda *a, **k: None)
    company = N(ticker="TSTH", current_price=70_000.0, assumptions=N(ai_inputs_verified=False))
    out = _apply_publication_gate(company, {"blended_fair_value_per_share": 92_000.0, "flags": [flag]})
    assert out["publication_allowed"] is (not blocked)


# --- F2: file config/sotp_holdings.yaml -----------------------------------------------------------


def test_config_file_valid_with_sources():
    cfg = load_sotp_holdings()
    assert set(cfg["holders"]) == {"VIC", "MSN", "GEX", "REE", "TCH"}
    for holder in cfg["holders"]:
        entry = sotp_holdings_for(holder)
        assert entry["review_ttl_days"] == 180
        for h in entry["holdings"]:
            assert str(h["source"]).startswith("https://") and 0 < h["stake"] <= 1
    # Trạng thái duyệt (reviewed_by/as_of) do người dùng điền → không khoá trong test (fin_a); hành vi cổng kiểm ở
    # test_holdings_mode_drops_proxy_and_flags_unverified / test_holdings_reviewed_is_clean và test r4b.


def test_gex_holds_gel_directly_not_vgc_look_through():
    # GEL có giá từ 20/10/2026: 624,9 / 890 tr cp = 70,21% (>79% × 790/890 = 70,12% là cận dưới).
    # VGC là công ty con của GEL → không được khai cả hai (đếm trùng).
    held = {h["ticker"]: h["stake"] for h in sotp_holdings_for("GEX")["holdings"]}
    assert "VGC" not in held
    assert held["GEL"] == pytest.approx(624.9 / 890, abs=1e-4)
    assert held["GEL"] >= 0.79 * 790 / 890


@pytest.mark.parametrize("holding,msg", [
    ({"ticker": "AAA", "stake": 0.5}, "source"),
    ({"ticker": "AAA", "stake": 1.2, "source": "https://x"}, "stake"),
    ({"ticker": "BBB", "stake": 0.5, "source": "https://x"}, "đệ quy"),
])
def test_config_validation_errors(holding, msg):
    cfg = {"review_ttl_days": 180, "holders": {"HOLD": {"holdings": [holding]}, "BBB": {"holdings": [
        {"ticker": "CCC", "stake": 0.5, "source": "https://x"}]}}}
    with pytest.raises(ValueError, match=msg):
        sotp_holdings_for("HOLD", cfg)


def test_undeclared_ticker_returns_none():
    assert sotp_holdings_for("PAN") is None


# --- Doanh thu chưa thực hiện trong vốn lưu động --------------------------------------------------


def test_marginal_deferred_revenue_ratio_sip_hand_calc():
    from valuation.data_access.repo import marginal_deferred_revenue_ratio

    # SIP (tỷ): DR 2022 11.037 → TTM Q2/2026 14.023; DT 6.035 → 9.092; cửa sổ 4 khoảng (5 điểm)
    # (14.023 − 11.037) / (9.092 − 6.035) = 2.986 / 3.057 = 0,97677
    dr = [10_471, 11_037, 11_273, 12_106, 13_375, 14_023]
    rev = [5_578, 6_035, 6_677, 7_801, 8_596, 9_092]
    bs = [N(deferred_revenue=x) for x in dr]
    is_ = [N(revenue=x) for x in rev]
    assert marginal_deferred_revenue_ratio(bs, is_, 4) == pytest.approx(2_986 / 3_057)
    assert marginal_deferred_revenue_ratio(bs, is_, 4) == pytest.approx(0.97677, abs=1e-5)
    # DT không tăng trên cửa sổ → 0 (hành vi cũ)
    assert marginal_deferred_revenue_ratio(bs, [N(revenue=100)] * 6, 4) == 0.0


def test_dcf_delta_deferred_revenue_enters_fcff():
    from valuation.engine.models.dcf import DCFValuationModel

    def fcff1(dr):
        cf = {"total_equity": 5_000e9, "total_assets": 8_000e9, "cash_and_equivalents": 1_000e9,
              "total_debt": 500e9, "minority_interest": 0.0, "non_operating_assets": 0.0,
              "total_revenue": 1_000e9, "cogs": 700e9, "ebitda": 200e9, "shares_outstanding": 100e6,
              "current_price": 50_000.0, "net_income_history": [], "revenue_history": []}
        ass = {"cost_of_equity": 0.12, "wacc": 0.11, "revenue_growth": [0.10] * 5, "ebit_margin": [0.15] * 5,
               "tax_rate": 0.20, "capex_to_revenue": [0.05] * 5, "depr_to_revenue": [0.04] * 5,
               "dso": [0.0] * 5, "dio": [0.0] * 5, "dpo": [0.0] * 5, "interest_rate": [0.08] * 5,
               "debt_repayment_rate": [0.2] * 5, "new_borrowing_rate": [0.0] * 5, "target_ev_ebitda": 8.0,
               "long_term_growth": 0.04, "weight_dcf": 1.0, "deferred_revenue_to_revenue": dr}
        return DCFValuationModel("TST", cf, ass).forecast_drivers()["forecasts"][0]

    # Năm 1: DT 1.000 → 1.100; NOPAT = 165 × 0,8 = 132; khấu hao 44; capex 55; ΔNWC = −0,98 × 100 = −98
    # FCFF = 132 + 44 − 55 + 98 = 219 tỷ (không DR: 121 tỷ)
    assert fcff1(0.0)["fcff"] == pytest.approx(121e9)
    assert fcff1(0.98)["delta_nwc"] == pytest.approx(-98e9)
    assert fcff1(0.98)["fcff"] == pytest.approx(219e9)


def test_growth_consistent_capex_offsets_deferred_revenue_when_s2c_known():
    from valuation.data_access.repo import growth_consistent_capex

    # Tái đầu tư ròng = ΔDT/s2c bất kể DR (vốn vận hành phía nguồn vốn đã trừ DR): g 10%, s2c 2,
    # NWC/DT 0,10 → capex/DT = 0,04 + 0,1/1,1 × (0,5 − 0,10); thêm DR 0,3 → capex tăng đúng 0,3 × ΔDT/DT.
    base = growth_consistent_capex([0.10], 0.04, 0.10, 2.0)[0]
    with_dr = growth_consistent_capex([0.10], 0.04, 0.10 - 0.3, 2.0)[0]
    assert with_dr - base == pytest.approx(0.3 * 0.10 / 1.10)


# --- F4 + RNAV F1: định tuyến ---------------------------------------------------------------------


@pytest.mark.parametrize("ticker,method", [
    ("PC1", "EV_EBITDA"), ("HDG", "DCF"), ("VCG", "DCF"), ("SIP", "DCF"),
    ("VGC", "SOTP"), ("GEE", "SOTP"), ("PAN", "SOTP"), ("TCH", "SOTP"), ("REE", "SOTP"),
])
def test_routing_after_s5(ticker, method):
    from valuation.engine.sector_router import route

    assert route(ticker)["method"] == method


def test_sip_event_hold_active():
    from valuation.config import active_event_hold

    assert active_event_hold("SIP", datetime.date(2026, 10, 20)) is not None


# --- Test CƠ CHẾ (không phải golden) trên DB thật: MSN ở mốc cố định 28/09/2026 ---------------------

# Số tính tay ĐỘC LẬP từ dòng thô DB (prices_daily, financials_quarterly hợp nhất Q2/2026), không qua engine; tỷ đồng.
# MSR: đóng cửa 28/09 52.600đ × (vốn cổ phần 10.998.295.200.000đ / 10.000 = 1.099,82952 tr cp) = 57.851,03;
#      VCSH Q2/2026 14.384,01 (lợi ích CĐ không kiểm soát 0) → chênh 43.467,02.
# MML: 26.100đ × (3.403.168.580.000 / 10.000 = 340,316858 tr cp) = 8.882,27; VCSH 5.538,77 − CĐKKS 200,47
#      = 5.338,30 → chênh 3.543,97.
# MSN: 15.204.920.000.000 / 10.000 = 1.520,492 tr cp.
_MSN_HAND_0928 = {"MSR": (57_851.03, 14_384.01), "MML": (8_882.27, 5_338.30)}
_MSN_SHARES_M_0928 = 1_520.492


def test_msn_holdings_mechanism_on_real_db():
    """Test CƠ CHẾ SOTP_HOLDINGS của MSN ở mốc 28/09/2026 — KHÔNG phải golden (fin_a, phản biện r4).

    FV đầy đủ MSN lệch CTCK có chủ ý (quyết định Q4 của phi, r4b: MSR/MML cộng theo thị giá) và do
    tests/test_golden_consensus.py + config/calibration_registry.yaml (mục MSN) quản. Ở đây chỉ kiểm:
    - phần lõi MCH + TCB (như s5) vẫn khớp đồng thuận trong golden_tolerance (đối chiếu cơ chế, không phải số
      công bố);
    - vốn hóa / VCSH mẹ MSR, MML engine lấy khớp số tính tay độc lập ở trên, và phần FV tăng thêm khớp
      Σ stake × chênh tay × 1e9 / cp tay × (1 − chiết khấu). Stake là quyết định đang chờ phi rà
      (sotp_review_table) nên đọc từ config, không khoá trị số. Với stake hiện hành 0,9289 / 0,943:
      40.376,52 + 3.341,96 = 43.718,48 tỷ → 43.718,48 / 1.520,492 × 0,9 = 25.877,6đ/cp.
    """
    import copy

    import yaml

    from valuation.config import PROJECT_ROOT, load_defaults
    from valuation.data_access.repo import build_company_data
    from valuation.db.session import SessionLocalRead
    from valuation.engine.consensus_helper import get_consensus_stats
    from valuation.engine.valuate import valuate

    as_of = datetime.date(2026, 9, 28)
    tol = yaml.safe_load((PROJECT_ROOT / "config" / "investment_ranking.yaml").read_text())["golden_tolerance"]
    db = SessionLocalRead()
    try:
        company = build_company_data(db, "MSN", mode="TTM", fetch_live=False, as_of=as_of)
        cons = get_consensus_stats("MSN", as_of, db) or {}
    except ValueError as exc:
        pytest.skip(f"Thiếu dữ liệu MSN trong DB: {exc}")
    finally:
        db.close()
    if (cons.get("count") or 0) < 3:
        pytest.skip("Đồng thuận MSN < 3 CTCK ở mốc cố định")
    res = valuate(company)
    assert "SOTP_HOLDINGS_MODE" in res["flags"]
    held = {h["ticker"]: h for h in company.assumptions.sotp_holdings["holdings"]}
    assert company.shares_outstanding == pytest.approx(_MSN_SHARES_M_0928)
    for t, (mc, bv) in _MSN_HAND_0928.items():
        assert not held[t].get("error")
        assert held[t]["market_cap_bn"] == pytest.approx(mc, abs=0.01)
        assert held[t]["book_equity_bn"] == pytest.approx(bv, abs=0.01)
    core = copy.deepcopy(company)
    core.assumptions.sotp_holdings["holdings"] = [
        h for h in core.assumptions.sotp_holdings["holdings"] if h["ticker"] not in _MSN_HAND_0928
    ]
    core_fv = valuate(core)["blended_fair_value_per_share"]
    assert abs(core_fv / cons["median"] - 1) < tol
    discount = load_defaults()["proxy_valuation"]["sotp_holding_discount"]
    increment = (
        sum(held[t]["stake"] * (mc - bv) for t, (mc, bv) in _MSN_HAND_0928.items())
        * 1e9
        / (_MSN_SHARES_M_0928 * 1e6)
        * (1 - discount)
    )
    assert res["blended_fair_value_per_share"] - core_fv == pytest.approx(increment, rel=1e-5)
