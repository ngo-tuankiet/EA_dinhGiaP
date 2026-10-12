"""
Golden test ngành BẢO HIỂM (mô phỏng BVH) — dùng fixture tự chứa ZZ_TEST_BVH.

Mục tiêu: khoá lại hành vi map line-item của `build_company_data` cho doanh nghiệp
bảo hiểm, chống hồi quy lỗi cũ:
  - IS bảo hiểm KHÔNG có `net_profit_loss_after_tax`. Nếu net_income không match,
    code fallback `ebit×0.8` → lấy nhầm DOANH THU PHÍ (~40.9k tỷ) → ROE ~120% phi lý,
    justified P/B kẹp 4.0 + cờ DATA_SUSPECT_ROE.
  - Sau fix: net_income phải map đúng dòng `profit_after_tax` (~2.95k tỷ) → ROE ~11%.

Quy ước (memory: tests chạy DB thật): fixture dùng mã ZZ_TEST_* và CHỈ xoá đúng
dữ liệu mình tạo trong teardown, không đụng dữ liệu production.
"""
import pytest
from valuation.db.session import SessionLocalRead, SessionLocalWrite
from valuation.db.models import Ticker, FinancialsQuarterly
from valuation.data_access.repo import build_company_data
from valuation.engine.models.pb_relative import PBRelativeValuationModel

TICKER = "ZZ_TEST_BVH"
YEAR = 2025

# Giá trị năm (VND) phỏng theo BCTC BVH thật (đơn vị raw VND).
ANNUAL_REVENUE_PREMIUM = 40_948_251_401_814   # net_sales_from_insurance_business (BẪY: KHÔNG phải LN)
ANNUAL_PROFIT_AFTER_TAX = 2_952_000_000_000   # profit_after_tax (LNST đúng)
ANNUAL_PROFIT_BEFORE_TAX = 3_554_431_272_129  # net_profit_loss_before_tax
EQUITY = 26_296_000_000_000                   # owners_equity (stock)
TOTAL_ASSETS = 291_805_652_090_226            # total_assets (stock)
COMMON_SHARES = 7_423_227_640_000             # vốn điều lệ → shares = /10_000


def _seed():
    """Tạo ticker + 4 quý FY2025 cho ZZ_TEST_BVH (idempotent)."""
    db = SessionLocalWrite()
    try:
        _purge(db)
        db.merge(Ticker(
            ticker=TICKER, company_name="ZZ Test Insurance", exchange="HOSE",
            sector="Insurance", is_vn100=False,
        ))
        db.commit()  # commit ticker trước để thoả FK của financials_quarterly
        # Flow items (IS): chia đều 4 quý → TTM sum = giá trị năm.
        flow = {
            "net_sales_from_insurance_business": ANNUAL_REVENUE_PREMIUM,
            "profit_after_tax": ANNUAL_PROFIT_AFTER_TAX,
            "net_profit_loss_before_tax": ANNUAL_PROFIT_BEFORE_TAX,
        }
        # Stock items (BS): mỗi quý giữ nguyên, periodize lấy quý mới nhất.
        stock = {
            "owners_equity": EQUITY,
            "total_assets": TOTAL_ASSETS,
            "common_shares": COMMON_SHARES,
        }
        for q in (1, 2, 3, 4):
            for item, annual in flow.items():
                db.add(FinancialsQuarterly(
                    ticker=TICKER, fiscal_year=YEAR, fiscal_quarter=q,
                    is_consolidated=True, is_restated=False, statement="IS",
                    line_item=item, value=annual / 4.0, currency="VND", source="ZZ_TEST",
                ))
            for item, val in stock.items():
                db.add(FinancialsQuarterly(
                    ticker=TICKER, fiscal_year=YEAR, fiscal_quarter=q,
                    is_consolidated=True, is_restated=False, statement="BS",
                    line_item=item, value=val, currency="VND", source="ZZ_TEST",
                ))
        db.commit()
    finally:
        db.close()


def _purge(db):
    db.query(FinancialsQuarterly).filter(FinancialsQuarterly.ticker == TICKER).delete()
    db.query(Ticker).filter(Ticker.ticker == TICKER).delete()
    db.commit()


@pytest.fixture
def insurance_fixture():
    _seed()
    yield
    db = SessionLocalWrite()
    try:
        _purge(db)
    finally:
        db.close()


class TestInsuranceNetIncomeMapping:
    def test_net_income_maps_to_profit_after_tax_not_premium(self, insurance_fixture):
        """net_income phải bám profit_after_tax (~2.95k tỷ), KHÔNG phải doanh thu phí (~40.9k tỷ)."""
        db = SessionLocalRead()
        try:
            c = build_company_data(db, TICKER, mode="TTM")
        finally:
            db.close()

        ni = c.historical_is[-1].net_income          # tỷ
        revenue = c.historical_is[-1].revenue        # tỷ

        # NI ≈ profit_after_tax (sai số < 5%), KHÔNG bị kéo lên gần doanh thu phí.
        assert ni == pytest.approx(ANNUAL_PROFIT_AFTER_TAX / 1e9, rel=0.05), (
            f"net_income={ni:,.0f} tỷ lệch profit_after_tax — có thể đang lấy nhầm dòng khác"
        )
        # Bẫy hồi quy: NI tuyệt đối KHÔNG được xấp xỉ doanh thu phí.
        assert ni < 0.2 * revenue, (
            f"net_income={ni:,.0f} tỷ quá gần revenue={revenue:,.0f} tỷ → lại map nhầm doanh thu phí"
        )

    def test_roe_in_sane_insurance_band(self, insurance_fixture):
        """ROE bảo hiểm phải ~10-15%, không phình lên >40% như lỗi cũ."""
        db = SessionLocalRead()
        try:
            c = build_company_data(db, TICKER, mode="TTM")
        finally:
            db.close()

        ni = c.historical_is[-1].net_income
        eq = c.historical_bs[-1].total_equity
        roe = ni / eq
        print(f"\n[ZZ_TEST_BVH] NI={ni:,.0f} tỷ | Equity={eq:,.0f} tỷ | ROE={roe:.1%}")
        assert 0.05 <= roe <= 0.20, f"ROE={roe:.1%} ngoài vùng hợp lý ngành bảo hiểm"

    def test_pb_relative_no_data_suspect_flag(self, insurance_fixture):
        """Qua PBRelativeValuationModel: ROE hợp lý, P/B không kẹp 4.0, hết cờ DATA_SUSPECT_ROE."""
        db = SessionLocalRead()
        try:
            c = build_company_data(db, TICKER, mode="TTM")
        finally:
            db.close()

        r = PBRelativeValuationModel.from_pydantic(c).perform_valuation()
        print(f"\n[ZZ_TEST_BVH PB] ROE={r['roe']:.1%} | justified_pb={r['justified_pb']:.2f} | flags={r['flags']}")
        assert "DATA_SUSPECT_ROE" not in r["flags"]
        assert 0.05 <= r["roe"] <= 0.20
        assert r["justified_pb"] < 4.0, "P/B vẫn kẹp trần 4.0 → ROE có thể vẫn phi lý"
