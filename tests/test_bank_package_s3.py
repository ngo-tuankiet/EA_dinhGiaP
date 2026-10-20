"""Gói ngân hàng s3 (19/10/2026): ROE terminal hội tụ về ROE ngành (λ, Damodaran), chi phí tín dụng
phai đối xứng TTM → trung vị, tăng trưởng tín dụng phai tuyến tính về GDP danh nghĩa dài hạn.

Không làm cổ tức theo VCSH/TS (NH F4): VCSH/TS là proxy sai cho CAR (NAB +86%), cần RWA.
"""

from types import SimpleNamespace as N

import pytest

from tests.helpers_bank import build_fake_bank
from valuation.config import load_defaults
from valuation.data_access import repo
from valuation.db.session import SessionLocalRead
from valuation.engine.models.bank_general import (
    BankGeneralValuationModel,
    converged_roe,
)
from valuation.engine.sensitivity import apply_scenario_adjustments
from valuation.forecast.base_year import revenue_growth_path


@pytest.fixture(scope="module")
def db():
    s = SessionLocalRead()
    yield s
    s.close()


# --- F5: hội tụ ROE terminal ----------------------------------------------------------------------


def test_converged_roe_hand_calc():
    # roe5 20,9%, ROE ngành 16,97%: λ=1 → 16,97%; λ=0,5 → 20,9 + 0,5·(16,97 − 20,9) = 18,935%.
    assert converged_roe(0.209, 0.1697, 1.0) == pytest.approx(0.1697)
    assert converged_roe(0.209, 0.1697, 0.5) == pytest.approx(0.18935)
    assert converged_roe(0.209, 0.1697, 0.0) == pytest.approx(0.209)
    assert converged_roe(0.209, None, 1.0) == pytest.approx(
        0.209
    )  # thiếu ROE ngành → giữ ROE riêng


def _bank(industry_roe, lam):
    c = build_fake_bank(sustainable_roe=0.209, coe=0.1192, g=0.04)
    c.assumptions.industry_roe = industry_roe
    c.assumptions.roe_convergence = lam
    return c


def test_terminal_roe_converges_and_drives_both_legs():
    m = BankGeneralValuationModel(_bank(0.1697, 1.0))
    assert m.terminal_roe == pytest.approx(0.1697)
    # fx2: ROE_T trên VCSH bình quân → VCSH đầu kỳ ở trạng thái dừng: 0,1697 × (1 + 0,04/2) = 0,173094.
    # P/B hợp lý = (0,173094 − 0,04)/(0,1192 − 0,04) = 1,68048 → × 1.000 tỷ / 100 triệu cp = 16.805đ.
    pb = m.calculate_pb_valuation()
    assert pb["target_pb"] == pytest.approx(1.68048, abs=1e-4)
    assert pb["fair_value_per_share"] == pytest.approx(16804.8, abs=1.0)
    # TV RI = (ROE_T·(1 + g/2) − COE)·B5/(COE − g), chiết khấu 5 năm.
    b5 = m.projections[-1]["total_equity"]
    ri = m.calculate_residual_income()
    assert ri["pv_terminal_ri"] == pytest.approx(
        (0.173094 - 0.1192) * b5 / 0.0792 / 1.1192**5
    )


def test_lambda_zero_reproduces_own_roe_with_cap():
    c = _bank(0.1697, 0.0)
    m = BankGeneralValuationModel(c)
    assert m.terminal_roe == pytest.approx(
        0.20
    )  # roe5 20,9% chạm trần 20% như trước s3
    assert any(w.startswith("BANK_TERMINAL_ROE_CAPPED") for w in c.warnings)


def test_bear_scenario_still_moves_terminal_when_fully_converged():
    base = _bank(0.1697, 1.0)
    bear = apply_scenario_adjustments(base, "Bear")
    # λ = 1: sốc −2pp chỉ trên ROE riêng sẽ mất tác dụng → phải sốc cả ROE ngành.
    assert bear.assumptions.industry_roe == pytest.approx(0.1497)
    assert BankGeneralValuationModel(bear).terminal_roe == pytest.approx(0.1497)
    assert (
        BankGeneralValuationModel(bear).calculate_pb_valuation()["fair_value_per_share"]
        < BankGeneralValuationModel(base).calculate_pb_valuation()[
            "fair_value_per_share"
        ]
    )


def test_bank_industry_roe_median_of_fy_medians(monkeypatch):
    def fake(fy_roes, ttm_roe):
        # VCSH phẳng 100 → ROE bình quân (fx2) = LN/100; năm đầu không có VCSH đầu kỳ nên không có ROE.
        roes = [0.0] + fy_roes + [ttm_roe]  # kỳ cuối = TTM chưa trọn năm, phải bị loại
        return N(
            historical_is=[N(year=2020 + k, net_income=r * 100) for k, r in enumerate(roes)],
            historical_bs=[N(year=2020 + k, total_equity=100.0) for k in range(len(roes))],
            last_period_is_ttm=True,
        )

    peers = {
        "A": fake(
            [0.30, 0.10, 0.20, 0.15], 0.50
        ),  # 3 năm gần nhất → trung vị 0,15 (0,30 ngoài cửa sổ)
        "B": fake([0.18, 0.16, 0.17], 0.01),  # 0,17
        "C": fake([0.12, 0.08, 0.10], 0.40),  # 0,10
        "D": fake([0.05, 0.05, 0.05], 0.05),  # nhóm khác
    }
    routing = {
        "A": {"sector": "NH"},
        "B": {"sector": "NH"},
        "C": {"sector": "NH"},
        "D": {"sector": "Z"},
    }
    monkeypatch.setattr(
        "valuation.engine.sector_router._router", lambda: N(routing_data=routing)
    )
    monkeypatch.setattr(repo, "build_company_data", lambda db, p, **k: peers[p])
    monkeypatch.setattr(repo, "CompanyBank", N)
    monkeypatch.setattr(repo, "current_pb", lambda p: 1.0)
    repo._PEER_CACHE.clear()
    try:
        assert repo.bank_industry_roe(None, "NH") == pytest.approx(
            0.15
        )  # trung vị(0,15; 0,17; 0,10)
        assert (
            repo.bank_industry_roe(None, "Z") is None
        )  # 1 mã < min_peers 3 → không hội tụ
    finally:
        repo._PEER_CACHE.clear()


# --- Đường thật (DB) -------------------------------------------------------------------------------


def test_repo_sets_industry_roe_for_banks_not_evf(db):
    c = repo.build_company_data(db, "VCB")
    assert c.assumptions.industry_roe == pytest.approx(repo.bank_industry_roe(db, "NH"))
    assert (
        c.assumptions.roe_convergence
        == load_defaults()["bank_terminal"]["roe_convergence"]
    )
    # EVF một mình nhóm 'Tài chính': không mượn ROE ngân hàng.
    assert repo.build_company_data(db, "EVF").assumptions.industry_roe is None


def test_credit_growth_fades_linearly_to_long_run_gdp(db):
    g_lt = load_defaults()["long_run_nominal_gdp_growth"]
    hdb = repo.build_company_data(db, "HDB").assumptions.credit_growth
    assert hdb[0] == pytest.approx(0.25)  # YoY > trần 25%
    # Tính tay: 25% → 8%, bước 4,25pp: 25 / 20,75 / 16,5 / 12,25 / 8%.
    assert hdb == pytest.approx([0.25, 0.2075, 0.165, 0.1225, 0.08])
    assert hdb == pytest.approx(revenue_growth_path(0.25, g_lt, years=5))
    eib = repo.build_company_data(db, "EIB").assumptions.credit_growth
    # Tăng chậm (sàn 5%) → tăng dần lên 8%, không nhảy 5% → 8% ở năm 5 như lịch cũ.
    assert eib == pytest.approx(revenue_growth_path(eib[0], g_lt, years=5))
    assert eib[-1] == pytest.approx(g_lt)
