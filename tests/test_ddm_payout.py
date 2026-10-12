"""DDM dùng payout THỰC TẾ và cùng đường tăng trưởng/g với DCF; payout thấp → bỏ DDM."""
import pytest

from valuation.engine.models.ddm import DDMValuationModel


def _ddm(payout):
    cf = {"net_income_history": [80.0, 100.0, 120.0], "shares_outstanding": 100e6,
          "current_price": 10_000.0}
    a = {"cost_of_equity": 0.12, "risk_free_rate": 0.05, "payout_ratio": payout,
         "min_payout": 0.40, "growth_path": [0.10] * 5, "long_term_growth": 0.04}
    return DDMValuationModel("ZZD", cf, a)


def test_ddm_hand_calc():
    # EPS chuẩn hóa = median(80,100,120) = 100 tỷ / 100 triệu cp = 1.000đ; D0 = 500đ.
    # D1..D5 tăng 10%/năm, chiết khấu 12%; TV = D5×1,04/(0,12−0,04) → 8.309,22đ.
    assert _ddm(0.5).perform_valuation()["blended_fair_value_per_share"] == pytest.approx(8309.2209, abs=0.01)


def test_ddm_skipped_when_dividends_do_not_represent_fcfe():
    r = _ddm(0.14).perform_valuation()  # POW: payout ~14%
    assert r["blended_fair_value_per_share"] == 0.0
    assert "DDM_SKIPPED_LOW_PAYOUT" in r["flags"]
