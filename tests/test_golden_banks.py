"""
Golden test tầng trích xuất + định giá ngân hàng BID / CTG / TCB qua ĐÚNG đường chạy thật
(build_company_data → valuate → BankGeneralValuationModel). Không hardcode fair value.

Khóa lại:
  1. shares ≈ vốn điều lệ thật / mệnh giá 10,000 (bắt lỗi dùng nhầm owners_equity → ~2.8x).
  2. LN / VCSH / cho vay khách hàng > 0 → keyword tiếng Anh match đúng.
  3. ROE kỳ gần nhất nằm trong vùng hợp lý cho bank VN (5%–30%).
  4. valuate() cho FV dương, không rơi vào nhánh chân định giá âm.
"""
import pytest

from valuation.data_access.repo import build_company_data
from valuation.db.session import SessionLocalRead
from valuation.engine.ttm_helper import get_shares_outstanding
from valuation.engine.valuate import valuate

# Shares xác minh từ vốn điều lệ thật; ±20% đủ chặt bắt lỗi proxy owners_equity (~180%).
GOLDEN_SHARES = {
    "BID": 7_280_065_200,
    "CTG": 7_766_944_600,
    "TCB": 7_086_240_400,
}


@pytest.fixture
def db():
    session = SessionLocalRead()
    yield session
    session.close()


@pytest.mark.parametrize("ticker", ["BID", "CTG", "TCB"])
class TestBankExtractionIntegrity:
    def test_shares_match_charter_capital(self, db, ticker):
        shares = get_shares_outstanding(db, ticker)
        golden = GOLDEN_SHARES[ticker]
        rel = abs(shares - golden) / golden
        assert rel < 0.20, f"{ticker}: shares={shares:,.0f} lệch {rel:.1%} so với {golden:,.0f}"

    def test_core_financials_populated_and_roe_sane(self, db, ticker):
        c = build_company_data(db, ticker)
        bs, is_ = c.historical_bs[-1], c.historical_is[-1]
        assert is_.net_income > 0 and bs.total_equity > 0 and bs.customer_loans > 0
        roe = is_.net_income / bs.total_equity
        assert 0.05 <= roe <= 0.30, f"{ticker}: ROE={roe:.1%} ngoài vùng hợp lý (5%–30%)"

    def test_valuation_runs_positive(self, db, ticker):
        res = valuate(build_company_data(db, ticker))
        assert res["blended_fair_value_per_share"] > 0
        assert "BANK_NEGATIVE_VALUATION_LEG" not in res["flags"]
