from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.analysis.investment_ranking import load_ranking_config
from valuation.db.models import FinancialsQuarterly, PricesDaily, Ticker
from valuation.db.session import Base
from valuation.services.ranking_sources import refresh_ticker


def test_refresh_only_inserts_new_closed_session_and_is_idempotent(
    tmp_path, monkeypatch
):
    from valuation.db import session
    from valuation.ingest.vnstock_client import vnstock_client

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(session, "SessionLocalRead", factory)
    monkeypatch.setattr(session, "SessionLocalWrite", factory)
    now = datetime(2026, 9, 1, 9, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    with factory() as db:
        db.add(Ticker(ticker="ACB"))
        db.add(
            PricesDaily(
                ticker="ACB",
                trade_date=date(2026, 8, 28),
                close=20000,
                foreign_net_val=123,
                price_unit="VND",
            )
        )
        db.add(
            FinancialsQuarterly(
                ticker="ACB",
                fiscal_year=2026,
                fiscal_quarter=2,
                is_consolidated=True,
                is_restated=False,
                statement="IS",
                line_item="revenue",
                value=100,
                ingested_at=now.replace(tzinfo=None),
            )
        )
        db.commit()
    calls = []

    def prices(ticker, start):
        calls.append(start)
        return pd.DataFrame(
            [
                {
                    "time": day,
                    "open": 21,
                    "high": 23,
                    "low": 20,
                    "close": 22,
                    "volume": 1000,
                }
                for day in ["2026-08-28", "2026-08-31", "2026-09-01"]
            ]
        )

    monkeypatch.setattr(vnstock_client, "get_historical_prices", prices)
    cfg = load_ranking_config()
    assert refresh_ticker("ACB", now, cfg, tmp_path) == []
    assert refresh_ticker("ACB", now, cfg, tmp_path) == []
    assert len(calls) == 1
    with factory() as db:
        rows = db.query(PricesDaily).order_by(PricesDaily.trade_date).all()
        assert len(rows) == 2
        assert rows[0].close == 20000
        assert rows[0].foreign_net_val == 123
        assert rows[1].close == 22000
        assert rows[1].trade_date == date(2026, 8, 31)
