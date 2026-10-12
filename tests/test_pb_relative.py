"""
Test justified P/B (CK/bảo hiểm): P/B link ROE — (ROE−g)/(COE−g), median LN, kẹp,
cờ DATA_SUSPECT khi ROE phi lý (vd bảo hiểm LN bị map nhầm doanh thu phí).
"""
import pytest
from valuation.engine.models.pb_relative import PBRelativeValuationModel


def _pb(ni_hist, equity_ty=20000.0, shares=1000e6, coe=0.13, g=0.03):
    cf = {"total_equity": equity_ty * 1e9, "net_income_history": ni_hist,
          "shares_outstanding": shares, "current_price": 20000}
    a = {"cost_of_equity": coe, "long_term_growth": g, "norm_years": 3}
    return PBRelativeValuationModel("ZZPB", cf, a)


def test_pb_linked_to_roe():
    """ROE cao hơn → justified P/B cao hơn (P/B KHÔNG cố định)."""
    lo = _pb([1000.0, 1100.0, 1200.0]).perform_valuation()   # ROE ~6%
    hi = _pb([2400.0, 2600.0, 2800.0]).perform_valuation()   # ROE ~13%
    assert hi["justified_pb"] > lo["justified_pb"]
    assert hi["roe"] > lo["roe"]


def test_pb_formula():
    # ROE = median(2000)/20000 = 10%; PB = (0.10-0.03)/(0.13-0.03) = 0.7
    r = _pb([1800.0, 2000.0, 2200.0]).perform_valuation()
    assert r["roe"] == pytest.approx(0.10, rel=1e-9)
    assert r["justified_pb"] == pytest.approx(0.7, rel=1e-6)


def test_pb_flags_absurd_roe():
    # ROE 150% (LN bị map nhầm doanh thu) → cờ DATA_SUSPECT + P/B kẹp ở 4.0.
    r = _pb([30000.0, 30000.0, 30000.0]).perform_valuation()
    assert "DATA_SUSPECT_ROE" in r["flags"]
    assert r["justified_pb"] <= 4.0


def test_pb_uses_median_not_latest():
    r = _pb([1000.0, 1000.0, 5000.0]).perform_valuation()  # năm gần đột biến
    assert r["roe"] == pytest.approx(1000e9 / 20000e9, rel=1e-9)  # median 1000, không 5000


def test_bvh_insurance_ni_mapped_correctly():
    """Regression: NI bảo hiểm (BVH) phải map đúng line-item → ROE hợp lý (~10-15%),
    KHÔNG lấy nhầm doanh thu phí (trước đây ROE 118%, cờ DATA_SUSPECT)."""
    from valuation.db.session import SessionLocalRead
    from valuation.data_access.repo import build_company_data
    db = SessionLocalRead()
    try:
        c = build_company_data(db, "BVH", mode="TTM")
        m = PBRelativeValuationModel.from_pydantic(c)
        r = m.perform_valuation()
        assert 0.05 <= r["roe"] <= 0.20, f"ROE BVH={r['roe']:.1%} ngoài vùng hợp lý ngành BH"
        assert "DATA_SUSPECT_ROE" not in r["flags"]
    finally:
        db.close()
