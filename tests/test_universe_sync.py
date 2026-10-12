from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.db.models import Ticker
from valuation.db.session import Base
from valuation.ingest.universe import sync_vn100_membership


def test_sync_vn100_membership_is_idempotent_and_preserves_departed_ticker():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all(
        [
            Ticker(ticker="ACB", company_name="ACB", is_vn100=False),
            Ticker(ticker="HVN", company_name="HVN", is_vn100=True),
        ]
    )
    session.commit()
    metadata = {
        "BAF": {
            "company_name": "BAF",
            "exchange": "HOSE",
            "sector": "Agriculture",
            "industry": "Food & Beverage",
        }
    }

    first = sync_vn100_membership(session, ["ACB", "BAF"], metadata)
    second = sync_vn100_membership(session, ["ACB", "BAF"], metadata)

    assert first == {"members": 2, "added": 1, "changed": 2}
    assert second == {"members": 2, "added": 0, "changed": 0}
    assert session.query(Ticker).count() == 3
    assert session.get(Ticker, "ACB").is_vn100 is True
    assert session.get(Ticker, "BAF").is_vn100 is True
    assert session.get(Ticker, "HVN").is_vn100 is False
    session.close()
