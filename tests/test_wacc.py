"""Test hàm WACC chung (engine/wacc.py)."""
import pytest

from valuation.engine.wacc import (
    DEFAULT_DEBT_SPREAD,
    compute_wacc,
    cost_of_debt_from_rf,
)


def test_market_weight_formula_manual():
    """Tính tay: coe=12%, cod=8%, tax=20%, E=200, D=300.
    we=0.4, wd=0.6 -> 0.12*0.4 + 0.08*0.8*0.6 = 0.048 + 0.0384 = 0.0864."""
    assert compute_wacc(0.12, 0.08, 200, 300, 0.20) == pytest.approx(0.0864)


def test_target_weight_equivalence():
    """Truyền trọng số (we, wd sum=1) cho kết quả = we*re + wd*rd*(1-t)."""
    re, rd, we, wd, tax = 0.123, 0.08, 0.4, 0.6, 0.20
    expected = we * re + wd * rd * (1 - tax)
    assert compute_wacc(re, rd, we, wd, tax) == pytest.approx(expected)


def test_no_capital_structure_returns_coe():
    assert compute_wacc(0.10, 0.08, 0.0, 0.0, 0.20) == 0.10


def test_floor_applied():
    # WACC tính ra thấp -> bị nâng lên floor
    assert compute_wacc(0.05, 0.05, 100, 0, 0.20, floor=0.08) == 0.08


def test_floor_not_applied_when_above():
    assert compute_wacc(0.15, 0.08, 100, 0, 0.20, floor=0.08) == pytest.approx(0.15)


def test_cost_of_debt_from_rf():
    assert cost_of_debt_from_rf(0.045) == pytest.approx(0.045 + DEFAULT_DEBT_SPREAD)
    assert cost_of_debt_from_rf(0.045, spread=0.02) == pytest.approx(0.065)
