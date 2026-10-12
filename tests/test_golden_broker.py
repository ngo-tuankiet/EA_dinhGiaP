"""Golden test tái lập báo cáo CTCK (tests/golden/broker_assumptions.yaml), sai số < 10%.

Chỉ tái lập các chân mà quy ước kỳ khớp mô hình: chân P/B thị trường, trọng số pha
trộn, chân P/E. RI/DCF đầy đủ của Shinhan dùng kỳ đầu 6 tháng và hệ số chiết khấu
riêng nên không so trực tiếp (xem DECISIONS D42).
"""
from pathlib import Path

import pytest
import yaml

from tests.helpers_bank import build_fake_bank
from valuation.engine.blend import blend_intrinsic_relative
from valuation.engine.models.bank_general import BankGeneralValuationModel
from valuation.engine.models.pe_relative import PERelativeValuationModel

G = yaml.safe_load((Path(__file__).parent / "golden" / "broker_assumptions.yaml").read_text(encoding="utf-8"))
TOL = 0.10


@pytest.mark.parametrize("ticker", ["VCB", "MBB"])
def test_bank_pb_leg_and_blend_match_broker(ticker):
    b = G[ticker]
    bank = build_fake_bank(equity_ty=float(b["bvps_12m"]), shares_tr=1000.0, coe=b["coe"], g=b["terminal_growth"])
    bank.assumptions.historical_pb_median = b["pb_target"]
    pb_leg = BankGeneralValuationModel(bank).calculate_market_pb_valuation()["fair_value_per_share"]
    assert pb_leg == pytest.approx(b["pb_leg"], rel=TOL)

    blended, _ = blend_intrinsic_relative(b["ri_leg"], pb_leg, b["weights"]["ri"], 1.0)
    assert blended == pytest.approx(b["target_price"], rel=TOL)


def test_hpg_pe_leg_matches_broker():
    b = G["HPG"]
    shares = 100e6
    ni_bn = b["eps_2026"] * shares / 1e9
    m = PERelativeValuationModel(
        "HPG", {"net_income_history": [ni_bn] * 3, "shares_outstanding": shares, "current_price": 1.0},
        {"target_pe": b["pe_target"], "norm_years": 3},
    )
    assert m.perform_valuation()["blended_fair_value_per_share"] == pytest.approx(b["pe_leg"], rel=TOL)
    blended, _ = blend_intrinsic_relative(b["pe_leg"], b["fcff_leg"], b["weights"]["pe"], 1.0)
    assert blended == pytest.approx(b["target_price"], rel=TOL)
