"""Số cổ phiếu phải phản ánh cổ tức CP/thưởng đã qua GDKHQ nhưng vốn điều lệ chưa ghi nhận.

Giá sau GDKHQ đã chia (1 + tỷ lệ); nếu số cp vẫn lấy từ vốn điều lệ cũ thì giá trị
hợp lý/cp bị thổi phồng đúng tỷ lệ đó (PVD thưởng 66,9% → +67%).
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.db.models import CorporateAction, FinancialsQuarterly, PricesDaily, Ticker
from valuation.db.session import Base
from valuation.engine.ttm_helper import get_shares_outstanding


def _db(capital_q2: float):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Ticker(ticker="ZZS", company_name="ZZS", is_vn100=True))
    for q, cap in ((1, 76_755e9), (2, capital_q2)):
        db.add(FinancialsQuarterly(
            ticker="ZZS", fiscal_year=2026, fiscal_quarter=q, is_consolidated=True,
            is_restated=False, statement="BS", line_item="charter_capital", value=cap,
            currency="VND", source="test",
        ))
    db.add(CorporateAction(
        ticker="ZZS", source_site="VCI", source_event_id="e1", event_type="STOCK_DIVIDEND",
        title="Cổ tức CP 10%", ex_right_date=date(2026, 5, 25), exercise_ratio=0.10,
        source_tier="AGGREGATOR", content_hash="h1",
    ))
    db.add(PricesDaily(ticker="ZZS", trade_date=date(2026, 9, 28), close=25_000))
    db.commit()
    return db


def test_stock_dividend_not_yet_in_charter_capital_is_applied():
    # Vốn Q1 = Q2 = 76.755 tỷ → 7.675,5 triệu cp × 1,10 = 8.443,05 triệu cp.
    shares = get_shares_outstanding(_db(76_755e9), "ZZS")
    assert shares == pytest.approx(7_675.5e6 * 1.10)


def test_stock_dividend_already_in_charter_capital_is_not_double_counted():
    shares = get_shares_outstanding(_db(84_430.5e9), "ZZS")
    assert shares == pytest.approx(8_443.05e6)
