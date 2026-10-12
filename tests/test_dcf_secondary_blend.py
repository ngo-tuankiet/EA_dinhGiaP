"""
Test DCF chọn phương pháp so sánh phụ theo business_nature (tài liệu lõi định giá):
  Compounder/Retail -> blend DCF + P/E
  Cyclical/Utility/Developer... -> blend DCF + EV/EBITDA

Trước đây MỌI mã DCF đều blend EV/EBITDA → méo cho retail biên mỏng (vd FRT).
"""
import pytest

from valuation.db.session import SessionLocalRead
from valuation.data_access.repo import build_company_data
from valuation.engine.models.dcf import DCFValuationModel
from valuation.engine.sector_router import route


@pytest.fixture
def db():
    s = SessionLocalRead()
    yield s
    s.close()


@pytest.mark.parametrize("ticker,expected_secondary", [
    ("FPT", "PE"),          # Compounder
    ("VNM", "PE"),          # Compounder (tiêu dùng)
    ("MWG", "PE"),          # Retail
    ("HPG", "EV_EBITDA"),   # Cyclical
    ("GAS", "EV_EBITDA"),   # Cyclical (dầu khí)
    ("POW", "EV_EBITDA"),   # Utility
])
def test_dcf_secondary_multiple_by_nature(db, ticker, expected_secondary):
    plan = route(ticker)
    # Chỉ chạy khi mã thực sự đi đường DCF (method=DCF) — nếu routing đổi thì skip.
    if not plan or plan.get("method") != "DCF":
        pytest.skip(f"{ticker} không route qua DCF (method={plan and plan.get('method')})")
    company = build_company_data(db, ticker, mode="TTM")
    res = DCFValuationModel.from_pydantic(company).perform_valuation()
    assert res["secondary_multiple"] == expected_secondary


def test_pe_branch_falls_back_to_dcf_when_earnings_negative(db):
    """LNST chuẩn hóa <= 0 ở nhánh P/E → multi_fvps fallback về dcf_fvps (không kéo về 0)."""
    company = build_company_data(db, "FPT", mode="TTM")  # Compounder → nhánh PE
    # Ép lịch sử LNST âm để kích hoạt fallback
    model = DCFValuationModel.from_pydantic(company)
    model.current_financials["net_income_history"] = [-1e12, -2e12, -1.5e12]
    res = model.perform_valuation()
    assert res["secondary_multiple"] == "PE"
    # multi_fvps phải bằng dcf_fvps (fallback), không phải 0
    assert res["multiples_fvps"] == pytest.approx(res["dcf_fvps"])
