from valuation.db.session import SessionLocalWrite
from valuation.db.models import DailySignal

def test():
    db = SessionLocalWrite()
    try:
        signals = db.query(DailySignal).filter(DailySignal.trade_date == "2026-06-20").all()
        print(f"Found {len(signals)} signals for 2026-06-20")
        for s in signals:
            print(s.ticker, s.close_price, s.conviction_score)
    finally:
        db.close()

if __name__ == "__main__":
    test()
