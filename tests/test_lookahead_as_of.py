"""Chống lookahead: định giá tại ngày quá khứ chỉ thấy BCTC đã tới hạn công bố và giá ≤ ngày đó."""
import datetime

from valuation.data_access.repo import _published_by, build_company_data, get_latest_price
from valuation.db.models import PricesDaily
from valuation.db.session import SessionLocalRead

LAG = {"quarterly": 30, "annual": 90}


def test_publication_deadlines():
    # Q4/2025 hạn 30/01/2026; BCTC năm 2025 hạn 31/03/2026; Q1/2026 hạn 30/04/2026.
    assert _published_by(2025, 4, datetime.date(2026, 1, 30), LAG)
    assert not _published_by(2025, 0, datetime.date(2026, 3, 30), LAG)
    assert _published_by(2025, 0, datetime.date(2026, 3, 31), LAG)
    assert not _published_by(2026, 1, datetime.date(2026, 4, 29), LAG)


def test_build_company_data_as_of_hides_future_statements_and_prices():
    as_of = datetime.date(2026, 3, 1)
    db = SessionLocalRead()
    try:
        c = build_company_data(db, "FPT", mode="TTM", as_of=as_of)
        last_close = (
            db.query(PricesDaily.close)
            .filter(PricesDaily.ticker == "FPT", PricesDaily.trade_date <= as_of)
            .order_by(PricesDaily.trade_date.desc())
            .first()[0]
        )
        assert c.historical_is[-1].year == 2025  # không có kỳ 2026 nào
        assert c.current_price == float(last_close)
        assert get_latest_price(db, "FPT", fetch_live=False, as_of=as_of) == float(last_close)
    finally:
        db.close()
