"""D62 — lỗi dữ liệu/code nhỏ + ROIC terminal (người dùng duyệt « làm tất cả » 15/10/2026)."""

import pytest

from valuation.data_access.repo import build_company_data
from valuation.db.session import SessionLocalRead
from valuation.engine.models.dcf import DCFValuationModel
from valuation.engine.valuate import _warning_codes, valuate


@pytest.fixture(scope="module")
def db():
    s = SessionLocalRead()
    yield s
    s.close()


def test_stub_year_without_cash_flow_is_dropped(db):
    # BAF 2018: chỉ có Q0, không có LCTT, nguồn ghi 0 → trước đây điền 0 vào lịch sử.
    c = build_company_data(db, "BAF", mode="TTM", fetch_live=False)
    assert 2018 not in [i.year for i in c.historical_is]
    assert "INCOMPLETE_YEAR_DROPPED:2018" in c.data_flags
    assert not any(str(w).startswith("Năm 2018") for w in c.warnings)


def test_convertible_bonds_counted_as_debt(db):
    # BAF Q2/2026: vay dài hạn 3.218,1 + trái phiếu chuyển đổi 513,1 = 3.731,2 tỷ (DTL 8,4 vẫn là nợ khác).
    bs = build_company_data(db, "BAF", mode="TTM", fetch_live=False).historical_bs[-1]
    assert bs.long_term_debt == pytest.approx(3731.2, abs=0.5)
    assert bs.other_long_term_liabilities == pytest.approx(8.4, abs=0.5)


def test_weight_dcf_follows_routing(db):
    # routing.json: VPL weight_primary 0,6 (trước đây cố định 0,5 cho mọi mã).
    assert build_company_data(db, "VPL", mode="TTM", fetch_live=False).assumptions.weight_dcf == 0.6


def test_free_text_warnings_do_not_become_flag_codes():
    from types import SimpleNamespace
    C = SimpleNamespace(warnings=["BANK_G_CLAMPED_BELOW_COE: g=5%", "Năm 2018: Bảng cân đối lệch", "Thiếu lưu chuyển: 2019"])

    assert _warning_codes(C) == ["BANK_G_CLAMPED_BELOW_COE"]
    assert len(C.warnings) == 3  # văn bản cảnh báo vẫn giữ để hiển thị


def test_fts_has_no_junk_year_flag(db):
    flags = valuate(build_company_data(db, "FTS", mode="TTM", fetch_live=False))["flags"]
    assert not any(str(f).startswith("Năm ") for f in flags)


def _model(roic=None):
    cf = {
        "total_equity": 5_000e9, "total_assets": 8_000e9, "cash_and_equivalents": 500e9,
        "total_debt": 1_000e9, "total_revenue": 5_000e9, "cogs": 3_500e9, "ebitda": 900e9,
        "shares_outstanding": 500e6, "current_price": 20_000.0,
    }
    ass = {
        "cost_of_equity": 0.13, "wacc": 0.12, "revenue_growth": [0.05] * 5, "ebit_margin": [0.12] * 5,
        "tax_rate": 0.20, "capex_to_revenue": [0.04] * 5, "depr_to_revenue": [0.03] * 5,
        "dso": [30.0] * 5, "dio": [30.0] * 5, "dpo": [30.0] * 5, "interest_rate": [0.08] * 5,
        "debt_repayment_rate": [0.1] * 5, "new_borrowing_rate": [0.05] * 5,
        "target_ev_ebitda": 6.0, "long_term_growth": 0.04, "weight_dcf": 0.5, "roic_terminal": roic,
    }
    return DCFValuationModel("TST", cf, ass)


def test_roic_terminal_override_hand_calculated():
    # TV = NOPAT₆·(1 − g/ROIC)/(WACC − g). ROIC = WACC (mặc định) vs ROIC 10%:
    # chênh EV = NOPAT₅·1,04·(0,04/0,10 − 0,04/0,12)/0,08 / 1,12⁵.
    base, low = _model(), _model(0.10)
    nopat5 = base.forecast_drivers()["terminal_nopat"]
    expected = nopat5 * 1.04 * (0.04 / 0.10 - 0.04 / 0.12) / 0.08 / 1.12**5
    diff = base.perform_valuation()["enterprise_value_dcf"] - low.perform_valuation()["enterprise_value_dcf"]
    assert diff == pytest.approx(expected, rel=1e-9)


def test_roic_terminal_below_growth_rejected():
    with pytest.raises(ValueError, match="INVALID_ROIC_TERMINAL"):
        _model(0.03).perform_valuation()
