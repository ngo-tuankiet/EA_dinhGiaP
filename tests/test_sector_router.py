"""
Test sector_router — NGUỒN SỰ THẬT routing DUY NHẤT (routing.json từ Excel CTCK).
Khóa: ánh xạ primary→canonical, trạng thái phương pháp, và ValuationRouter (API cũ)
dùng chung một nguồn với route() (API mới) → không còn 2 router.
"""
import pytest
from valuation.engine import sector_router as sr
from valuation.engine.router import ValuationRouter as ReexportedRouter


@pytest.mark.parametrize("ticker,method,status", [
    ("VCB", "RI_PB", "IMPLEMENTED"),   # ngân hàng
    ("HPG", "DCF", "IMPLEMENTED"),     # thép (FCFF)
    ("VHM", "RNAV", "PARTIAL"),        # bất động sản — proxy
    ("VIC", "SOTP", "PARTIAL"),        # holding đa ngành thực thụ — vẫn proxy SOTP
    ("FPT", "DCF", "IMPLEMENTED"),     # Compounder — chuyển SOTP→DCF+P/E (routing 2026-07)
    ("BVH", "PB", "IMPLEMENTED"),      # bảo hiểm — justified P/B
    ("SSI", "PB", "IMPLEMENTED"),      # chứng khoán — justified P/B
    ("SSB", "RI_PB", "IMPLEMENTED"),   # ngân hàng
])
def test_known_routes(ticker, method, status):
    r = sr.route(ticker)
    assert r is not None, f"{ticker} thiếu trong routing.json"
    assert r["method"] == method
    assert r["status"] == status


def test_unknown_ticker_returns_none():
    assert sr.route("ZZZ_NOT_A_TICKER") is None


def test_is_supported_only_for_implemented():
    assert sr.is_supported("VCB") is True
    assert sr.is_supported("HPG") is True
    assert sr.is_supported("BVH") is True     # PB justified — implemented
    assert sr.is_supported("VHM") is False   # RNAV proxy (partial)
    assert sr.is_supported("VIC") is False    # SOTP proxy (partial)


def test_single_source_of_truth():
    """router.py re-export CHÍNH là ValuationRouter trong sector_router (1 nguồn)."""
    assert ReexportedRouter is sr.ValuationRouter
    # route() (mới) và get_routing() (cũ) đọc cùng routing.json
    rj = sr.ValuationRouter().get_routing("VCB")
    assert rj["primary"] == "RI"
    assert sr.route("VCB")["method"] == "RI_PB"


def test_routing_covers_full_vn100():
    data = sr._router().routing_data
    # Mọi primary phải ánh xạ được sang canonical đã khai báo status
    for t, c in data.items():
        method = sr._PRIMARY_TO_METHOD.get(c["primary"], "DCF")
        assert method in sr.METHOD_STATUS, f"{t}: method {method} chưa khai báo status"
