from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.data_access.freshness_checker import (
    check_data_freshness,
    describe_data_freshness,
)
from valuation.db.models import Consensus, PricesDaily, Ticker
from valuation.db.session import Base


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_freshness_is_scoped_to_selected_ticker():
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    db = _session()
    try:
        db.add_all(
            [
                Ticker(ticker="AAA", company_name="AAA", is_vn100=True),
                Ticker(ticker="BBB", company_name="BBB", is_vn100=True),
                PricesDaily(
                    ticker="AAA",
                    trade_date=today - timedelta(days=10),
                    close=10,
                ),
                PricesDaily(ticker="BBB", trade_date=today, close=20),
                Consensus(
                    ticker="AAA",
                    broker="TEST",
                    report_date=today,
                    target_price=12,
                ),
            ]
        )
        db.commit()

        status = check_data_freshness(db, threshold_days=7, ticker="AAA")

        assert status.last_price_date == today - timedelta(days=10)
        assert status.price_is_stale is True
        assert status.consensus_is_stale is False
        assert status.is_stale is True
    finally:
        db.close()


def test_freshness_message_names_only_the_stale_source():
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    db = _session()
    try:
        db.add_all(
            [
                Ticker(ticker="AAA", company_name="AAA", is_vn100=True),
                PricesDaily(ticker="AAA", trade_date=today, close=10),
                Consensus(
                    ticker="AAA",
                    broker="TEST",
                    report_date=today - timedelta(days=14),
                    target_price=12,
                ),
            ]
        )
        db.commit()

        status = check_data_freshness(db, threshold_days=7, ticker="AAA")
        headline, details = describe_data_freshness(status)

        assert headline == "Báo cáo CTCK cần kiểm tra"
        assert "Giá: hôm nay" in details
        assert "Báo cáo CTCK: 14 ngày trước" in details
        assert "0 ngày" not in headline
    finally:
        db.close()


def test_freshness_message_handles_missing_data_without_999_days():
    db = _session()
    try:
        db.add(Ticker(ticker="AAA", company_name="AAA", is_vn100=True))
        db.commit()

        status = check_data_freshness(db, ticker="AAA")
        headline, details = describe_data_freshness(status)

        assert headline == "Chưa có giá và báo cáo CTCK"
        assert "chưa có dữ liệu" in details
        assert "999" not in details
    finally:
        db.close()
