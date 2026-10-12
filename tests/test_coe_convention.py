"""Test convention COE VND-base — ERP gồm Country Risk Premium (Damodaran)."""
import pytest

from valuation.config import load_defaults
from valuation.engine.coe import MIN_EQUITY_PREMIUM, compute_coe, get_erp


def test_erp_includes_country_risk_premium():
    """ERP dùng cho COE = mature + CRP (erp_total), KHÔNG phải mature-only.

    CRP là phần bù rủi ro vốn cổ phần của TT mới nổi, tách biệt với rủi ro vỡ
    nợ trong lợi suất TPCP → phải cộng để không under-price rủi ro cổ phiếu VN.
    """
    conv = load_defaults().get("coe_convention", {})
    assert get_erp() == pytest.approx(conv["erp_mature"] + conv["crp_vn"])
    assert get_erp() == pytest.approx(conv["erp_total"])
    assert get_erp() != pytest.approx(conv["erp_mature"])


def test_compute_coe_formula():
    rf, beta = 0.04521, 0.77
    erp = get_erp()
    assert compute_coe(rf, beta) == pytest.approx(rf + beta * erp)


def test_coe_reflects_country_risk():
    """COE đúng phải CAO hơn cách bỏ CRP (mature-only) đúng bằng beta * crp_vn."""
    rf, beta = 0.04521, 0.77
    conv = load_defaults().get("coe_convention", {})
    mature_only = rf + beta * conv["erp_mature"]
    correct = compute_coe(rf, beta)
    assert correct > mature_only
    assert (correct - mature_only) == pytest.approx(beta * conv["crp_vn"])


def test_floor_allows_vnd_base_coe():
    """Floor phải cho phép COE VND-base hợp lệ (beta=0.77) đi qua."""
    rf, beta = 0.04521, 0.77
    coe = compute_coe(rf, beta)
    assert coe >= rf + MIN_EQUITY_PREMIUM  # không bị COE_TOO_LOW
