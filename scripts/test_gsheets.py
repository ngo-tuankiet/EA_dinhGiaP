import datetime
from valuation.db.session import SessionLocalWrite
from valuation.output.gsheets_exporter import export_daily_signals_to_gsheets

def test():
    db = SessionLocalWrite()
    try:
        # Instead of today, let's just test with a date that might have signals, or today
        res = export_daily_signals_to_gsheets(trade_date=datetime.date.today(), db=db)
        print("Export result:", res)
    finally:
        db.close()

if __name__ == "__main__":
    test()
