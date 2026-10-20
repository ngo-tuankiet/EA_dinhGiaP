"""Nâng cấp định chế tài chính phi ngân hàng (bước s2, 19/10/2026).

F1  EVF (công ty tài chính, mẫu BCTC TCTD) → pipeline ngân hàng, RI 0,5 / P/B 0,5.
F3  Chân P/B thị trường: kỳ TTM ghép giá cuối quý (D62) cho CK/BH/NH; thiếu lịch sử → trung vị
    P/B hiện hành của nhóm routing.json.
F5  Beta ngành bottom-up dùng chung (sector_peer_beta) cho NH (D47) và CTCK; loại mã không có beta.
F6  Bảo hiểm: chân P/B lịch sử của chính mã, cửa sổ ROE = forecast.margin_window_years.
CK F6  Payout CK/BH từ cổ tức tiền thực trả + cờ nhất quán Gordon.
"""

import datetime
from types import SimpleNamespace as N

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.data_access import repo
from valuation.db.models import PricesDaily, Ticker
from valuation.db.session import Base, SessionLocalRead
from valuation.engine import ttm_helper
from valuation.engine.models.insurance import InsuranceValuationModel
from valuation.engine.models.securities import (
    SecuritiesValuationModel,
    cash_payout_ratio,
    gordon_payout_flags,
)
from valuation.models.financials_bank import CompanyBank


@pytest.fixture(scope="module")
def db():
    s = SessionLocalRead()
    yield s
    s.close()


# --- F1: nhận diện mẫu BCTC TCTD ----------------------------------------------------------------


def test_credit_institution_template_detects_nii_line():
    tctd = [N(statement="IS", line_item="net_interest_income", value=1.2e12)]
    nonfin = [
        N(statement="IS", line_item="net_sales", value=5e12),
        N(statement="BS", line_item="net_interest_income", value=1.0),
    ]
    assert repo.credit_institution_template(tctd) is True
    assert repo.credit_institution_template(nonfin) is False  # chỉ dòng KQKD mới tính
    assert (
        repo.credit_institution_template(
            [N(statement="IS", line_item="net_interest_income", value=None)]
        )
        is False
    )


def test_evf_valued_as_credit_institution(db):
    from valuation.engine.valuate import valuate

    c = repo.build_company_data(db, "EVF")
    assert isinstance(
        c, CompanyBank
    )  # trước đây: ValueError MISSING_FINANCIAL_INPUT: revenue
    assert c.assumptions.beta == pytest.approx(ttm_helper.sector_peer_beta(db, "NH"))
    v = valuate(c)
    # Chân P/B = P/B lịch sử × BVPS (tỷ → đồng/cp: ×1000 / triệu cp); pha 0,5/0,5 như NH.
    bvps = c.historical_bs[-1].parent_equity * 1000 / c.shares_outstanding
    assert v["relative_fv"] == pytest.approx(c.assumptions.historical_pb_median * bvps)
    assert v["weight_intrinsic"] == 0.5
    assert v["blended_fair_value_per_share"] == pytest.approx(
        0.5 * v["intrinsic_fv"] + 0.5 * v["relative_fv"]
    )


# --- F5: beta ngành bottom-up -------------------------------------------------------------------


def _prices_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Ticker(ticker="VNINDEX", company_name="VNINDEX", is_vn100=False))
    s.add(
        PricesDaily(
            ticker="VNINDEX", trade_date=datetime.date(2026, 10, 16), close=1700.0
        )
    )
    s.commit()
    return s


def test_sector_peer_beta_hand_case(monkeypatch):
    # Beta thô 12 CTCK (chẩn đoán 19/10); VCK/TCX/VPX mới niêm yết (< 52 tuần) → None, bị loại.
    raw = {
        "SSI": 1.308,
        "VND": 1.219,
        "VCI": 1.048,
        "HCM": 1.126,
        "VIX": 1.5,
        "FTS": 1.237,
        "BSI": 1.18,
        "CTS": 1.36,
        "DSE": 0.674,
        "VCK": None,
        "TCX": None,
        "VPX": None,
    }
    monkeypatch.setattr(ttm_helper, "_beta_from_db", lambda db, t: raw.get(t))
    ttm_helper._PEER_BETA_CACHE.clear()
    # Blume 0,67b + 0,33: [1,206; 1,147; 1,032; 1,084; 1,335; 1,159; 1,121; 1,241; 0,782] → trung vị
    # = 0,67 × 1,219 + 0,33 = 1,14673 (VND). Nếu đưa beta_default 1,0 của 3 mã None vào: 1,121.
    assert ttm_helper.sector_peer_beta(_prices_db(), "CK") == pytest.approx(
        0.67 * 1.219 + 0.33
    )
    ttm_helper._PEER_BETA_CACHE.clear()


def test_sector_peer_beta_no_data_falls_back_and_rejects_unlever(monkeypatch):
    monkeypatch.setattr(ttm_helper, "_beta_from_db", lambda db, t: None)
    ttm_helper._PEER_BETA_CACHE.clear()
    assert ttm_helper.sector_peer_beta(_prices_db(), "CK") == pytest.approx(
        1.0
    )  # beta_default
    ttm_helper._PEER_BETA_CACHE.clear()
    with pytest.raises(ValueError):
        ttm_helper.sector_peer_beta(_prices_db(), "CK", unlever=True)


def test_securities_use_sector_beta(db):
    beta = ttm_helper.sector_peer_beta(db, "CK")
    for t in ("SSI", "VCK"):  # VCK chưa đủ 52 tuần: trước đây beta_default 1,0
        assert repo.build_company_data(db, t).assumptions.beta == pytest.approx(beta)


# --- F3: chân P/B thị trường --------------------------------------------------------------------


def test_current_pb_hand_case():
    # 20.000đ × 100 triệu cp / 1e3 = 2.000 tỷ; VCSH mẹ 1.000 tỷ → 2,0x.
    c = N(
        current_price=20_000,
        shares_outstanding=100.0,
        historical_bs=[N(parent_equity=1000.0)],
    )
    assert repo.current_pb(c) == pytest.approx(2.0)
    assert (
        repo.current_pb(
            N(
                current_price=1,
                shares_outstanding=1,
                historical_bs=[N(parent_equity=0.0)],
            )
        )
        is None
    )


def test_pb_peer_fallback_only_when_history_missing(monkeypatch):
    monkeypatch.setattr(repo, "own_history_multiple", lambda *a, **k: None)
    monkeypatch.setattr(
        repo,
        "sector_peer_multiples",
        lambda *a, **k: {"pb": 1.4234, "pe": None, "ev_ebitda": None},
    )
    flags: list = []
    assert repo.pb_history_or_peer(
        None, "TCX", [], 100.0, None, "CK", None, True, flags
    ) == pytest.approx(1.4234)
    assert flags == ["MULTIPLE_FROM_PEER_MEDIAN:pb=1.42x"]
    flags = []
    assert (
        repo.pb_history_or_peer(None, "TCX", [], 100.0, None, "CK", None, False, flags)
        is None
    )
    assert flags == []


@pytest.mark.parametrize("ticker", ["MBB", "SSI", "BVH"])
def test_financial_pb_history_includes_ttm_period(db, monkeypatch, ticker):
    calls = []
    real = repo.own_history_multiple

    def spy(
        db_,
        t,
        denominators,
        shares_m,
        adjustments=None,
        years=5,
        kind=None,
        period_end=None,
        **kw,
    ):
        if kind is None and t == ticker:
            calls.append(period_end)
        return real(
            db_, t, denominators, shares_m, adjustments, years, kind, period_end, **kw
        )

    monkeypatch.setattr(repo, "own_history_multiple", spy)
    c = repo.build_company_data(db, ticker, mode="TTM")
    # Lần gọi đầu là của chính mã; NH còn dựng lại chính mã làm peer khi tính ROE ngành (cache _PEER_CACHE lạnh
    # khi chạy riêng test) → cùng period_end. Trước fx2 `(period_end,) = calls` hỏng khi chạy riêng MBB.
    period_end = calls[0]
    assert all(c == period_end for c in calls)
    latest = c.historical_bs[-1].year
    assert list(period_end) == [latest]
    end = period_end[latest]
    assert (
        end.month in (3, 6, 9, 12) and (end + datetime.timedelta(days=1)).day == 1
    )  # ngày cuối quý


# --- CK F6: payout từ dữ liệu + Gordon ----------------------------------------------------------


def _hist(ni, div, ttm_last=True):
    years = list(range(2022, 2022 + len(ni)))
    is_ = [N(year=y, net_income=v) for y, v in zip(years, ni)]
    cf = [
        N(year=y, dividends_paid=d, is_ttm_period=(ttm_last and i == len(years) - 1))
        for i, (y, d) in enumerate(zip(years, div))
    ]
    return is_, cf


def test_cash_payout_ratio_hand_case():
    # SSI: (1.497 + 1.506 + 2.075) / (2.293 + 2.704 + 4.106) = 5.078 / 9.103 = 0,55784; kỳ TTM bị bỏ.
    is_, cf = _hist(
        [1500.0, 2293.0, 2704.0, 4106.0, 5000.0], [0.0, 1497.0, 1506.0, 2075.0, 9999.0]
    )
    assert cash_payout_ratio(is_, cf, cap=1.0, years=3) == pytest.approx(5078 / 9103)
    # DSE 2024: chia 330 tỷ trên LN 182 tỷ (trước IPO) → kẹp trần 1,0.
    is_, cf = _hist([182.0], [330.0], ttm_last=False)
    assert cash_payout_ratio(is_, cf, cap=1.0, years=3) == pytest.approx(1.0)
    is_, cf = _hist([-50.0, 20.0, 10.0], [0.0, 0.0, 0.0], ttm_last=False)
    assert cash_payout_ratio(is_, cf, cap=1.0, years=3) is None  # Σ LNST ≤ 0


def test_gordon_payout_flag():
    # ROE 12%, g 4% → payout* = 1 − 0,04/0,12 = 0,6667; tol 0,30.
    assert gordon_payout_flags("SEC", 0.20, 0.12, 0.04)[0].startswith(
        "SEC_PAYOUT_INCONSISTENT"
    )
    assert gordon_payout_flags("SEC", 0.60, 0.12, 0.04) == []
    assert gordon_payout_flags("SEC", 0.20, 0.0, 0.04) == []


def _fin_company(ni, eq, div, hist_pb=None):
    is_, cf = _hist(ni, div)
    return N(
        ticker="TST",
        historical_is=is_,
        historical_cf=cf,
        historical_bs=[N(year=i.year, parent_equity=e) for i, e in zip(is_, eq)],
        shares_outstanding=100.0,  # triệu cp
        current_price=10_000.0,
        assumptions=N(
            cost_of_equity=0.13,
            risk_free_rate=0.05,
            beta=1.0,
            erp=0.08,
            terminal_growth_rate=0.04,
            historical_pb_median=hist_pb,
        ),
    )


def test_securities_payout_from_data_drives_book_roll():
    # ROE phẳng 12%, payout 3 năm đầy đủ = 201/360 = 0,55833.
    c = _fin_company([120.0] * 5, [1000.0] * 5, [0.0, 67.0, 67.0, 67.0, 0.0])
    m = SecuritiesValuationModel.from_pydantic(c)
    assert m.assumptions["payout_ratio"] == pytest.approx(201 / 360)
    f = m.forecast_drivers()["forecasts"]
    # Năm 1 (r3a: ROE 12% trên VCSH BÌNH QUÂN, forecast_bank.ni_from_avg_roe): LN = 120 / (1 − 0,12 × 0,44167 / 2)
    # = 120 / 0,9735 = 123,267 tỷ → VCSH năm 2 = 1.000 + 123,267 × (1 − 0,55833) = 1.054,443 tỷ.
    assert f[1]["book_value_start"] == pytest.approx(1054.4427e9, rel=1e-6)


def test_securities_payout_fallback_flag_when_no_full_year():
    c = _fin_company([120.0], [1000.0], [10.0])  # chỉ một kỳ và là TTM
    m = SecuritiesValuationModel.from_pydantic(c)
    assert m.assumptions["payout_from_data"] is False
    assert m.assumptions["payout_ratio"] == pytest.approx(
        0.20
    )  # securities.payout_ratio
    assert any(
        f.startswith("SEC_PAYOUT_FALLBACK") for f in m.perform_valuation()["flags"]
    )


# --- F6: bảo hiểm --------------------------------------------------------------------------------


def test_insurance_roe_window_is_margin_window():
    # VCSH phẳng 1.000 → ROE = LN/1.000: 7,8% 9,0% 10,0% 12,4% 13,4%. Cửa sổ 4 năm (D61):
    # trung vị(9,0; 10,0; 12,4; 13,4) = 11,2% (cửa sổ 5 kỳ cũ: 10,0%).
    c = _fin_company([0.0, 78.0, 90.0, 100.0, 124.0, 134.0], [1000.0] * 6, [0.0] * 6)
    assert InsuranceValuationModel.from_pydantic(c).forecast_drivers()[
        "roe_norm"
    ] == pytest.approx(0.112)


def test_insurance_market_pb_leg_hand_case():
    # ROE bình quân = COE = 13%, payout 0 (không cổ tức). r3a: LN = 0,13·B / (1 − 0,13/2) = 0,139037·B (ROE trên VCSH
    # đầu kỳ) → RI_t = 0,009037·B_t; B: 1.000 → 1.139,04 → 1.297,41 → 1.477,79 → 1.683,26 → B5 cuối = 1.917,30.
    # PV RI = 7,998 + 8,062 + 8,126 + 8,191 + 8,257 = 40,633; TV = (0,13 × 1,02 − 0,13) × 1.917,30 / 0,09 = 55,389
    # → PV 30,063. Chân RI = (1.000 + 40,633 + 30,063) tỷ / 100 tr cp = 10.706,96đ (cũ: 10.000đ).
    # Chân P/B = 1,5 × 10.000 = 15.000đ. FV = 0,5 × 10.706,96 + 0,5 × 15.000 = 12.853,48đ.
    c = _fin_company([130.0] * 6, [1000.0] * 6, [0.0] * 6, hist_pb=1.5)
    res = InsuranceValuationModel.from_pydantic(c).perform_valuation()
    assert res["ri_fvps"] == pytest.approx(10_706.96, abs=0.05)
    assert res["pb_fvps"] == pytest.approx(15_000.0)
    assert res["blended_fair_value_per_share"] == pytest.approx(12_853.48, abs=0.05)
    assert "INS_NO_MARKET_PB_HISTORY" not in res["flags"]


def test_insurance_without_pb_history_uses_justified_pb_and_flags():
    c = _fin_company([130.0] * 6, [1000.0] * 6, [0.0] * 6)
    res = InsuranceValuationModel.from_pydantic(c).perform_valuation()
    # P/B hợp lý (ROE đầu kỳ = 0,13 × (1 + 0,04/2) = 0,1326) = (0,1326 − 0,04)/(0,13 − 0,04) = 1,02889 → 10.288,89đ.
    assert res["pb_fvps"] == pytest.approx(10_288.89, abs=0.01)
    assert "INS_NO_MARKET_PB_HISTORY" in res["flags"]
