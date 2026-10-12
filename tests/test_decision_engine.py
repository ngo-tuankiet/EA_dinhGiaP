"""
Test InvestmentDecisionMaker — Dynamic Margin of Safety + Hard Gates.

Kiểm chứng đúng bảng khuyến nghị trong tài liệu lõi định giá:
  Upside >= MOS(ngành) -> BUY
  Upside >= 0%         -> HOLD
  Upside >= -10%       -> TRIM
  Upside <  -10%       -> SELL
  (Hard gate: audit/legal/liquidity issue -> HARD REJECT, bất kể upside)
"""
import pytest

from valuation.models.financials import GovernanceData
from valuation.engine.decision_engine import InvestmentDecisionMaker


def _decide(nature, price, fv, governance=None):
    dm = InvestmentDecisionMaker(nature, price, fv, governance or GovernanceData())
    return dm.make_decision()


def test_mos_by_business_nature():
    """MOS đúng theo từng nhóm bản chất kinh doanh (tài liệu mục 2)."""
    cases = {
        "Compounder": 0.15,
        "Bank": 0.20,
        "Utility": 0.20,
        "Retail": 0.25,
        "Cyclical": 0.30,
        "Developer": 0.30,
        "Securities": 0.30,  # CTCK biến động mạnh theo thị trường
        "Unknown": 0.25,   # default
    }
    for nature, mos in cases.items():
        dm = InvestmentDecisionMaker(nature, 100.0, 100.0, GovernanceData())
        assert dm.get_target_mos() == pytest.approx(mos), f"{nature} MOS sai"


def test_hpg_cyclical_upside_below_mos_is_hold():
    """Ví dụ tài liệu: HPG (Cyclical, MOS 30%) upside +25% < 30% -> HOLD, KHÔNG BUY."""
    d = _decide("Cyclical", price=100.0, fv=125.0)  # upside +25%
    assert d["upside"] == pytest.approx(25.0)
    assert d["recommendation"] == "HOLD"


def test_buy_when_upside_clearly_above_mos():
    """Upside vượt rõ MOS -> BUY (Compounder 15%)."""
    d = _decide("Compounder", price=100.0, fv=120.0)  # +20%
    assert d["recommendation"] == "BUY"


def test_buy_at_exact_mos_boundary_float_safe():
    """Biên chính xác: Compounder fv=115 (upside +15% = MOS) -> BUY dù float 14.999..."""
    d = _decide("Compounder", price=100.0, fv=115.0)
    assert d["recommendation"] == "BUY"


def test_recommendation_bands():
    """Các mốc HOLD / TRIM / SELL theo đúng ngưỡng tài liệu."""
    assert _decide("Bank", 100.0, 105.0)["recommendation"] == "HOLD"   # +5% (0<=u<MOS)
    assert _decide("Bank", 100.0, 95.0)["recommendation"] == "TRIM"    # -5% (>= -10%)
    assert _decide("Bank", 100.0, 89.0)["recommendation"] == "SELL"    # -11% (< -10%)
    # Biên -10% đúng bằng ngưỡng vẫn là TRIM
    assert _decide("Bank", 100.0, 90.0)["recommendation"] == "TRIM"


def test_hard_gate_overrides_even_when_cheap():
    """Có vấn đề kiểm toán/pháp lý -> HARD REJECT dù định giá rất rẻ (upside cao)."""
    gov = GovernanceData(audit_issue=True)
    d = _decide("Compounder", price=100.0, fv=200.0, governance=gov)  # upside +100%
    assert d["recommendation"] == "HARD REJECT"
    assert d["hard_gates_violations"], "phải liệt kê vi phạm hard gate"


def test_zero_price_no_crash():
    """Giá = 0 (thiếu dữ liệu) không được crash; upside quy ước 0 -> HOLD."""
    d = _decide("Bank", price=0.0, fv=100.0)
    assert d["recommendation"] == "HOLD"
