import datetime
import logging
from valuation.db.session import SessionLocalWrite
from valuation.engine.daily_signal import calculate_batch_signals
from valuation.output.gsheets_exporter import export_daily_signals_to_gsheets

logging.basicConfig(level=logging.INFO)

def test():
    db = SessionLocalWrite()
    try:
        signals_res = calculate_batch_signals(
            tickers=["VCB", "HPG"], 
            trade_date=None,
            force_override=True,
            db=db
        )
        print("SIGNALS:", signals_res)
        
        effective_dates = [datetime.date.fromisoformat(s['trade_date']) for s in signals_res if 'trade_date' in s]
        export_date = max(effective_dates) if effective_dates else datetime.date.today()
        print("EXPORT DATE:", export_date)
        
        # Test query in same session
        from valuation.db.models import DailySignal
        found = db.query(DailySignal).filter(DailySignal.trade_date == export_date).count()
        print("FOUND IN DB COUNT BEFORE EXPORT:", found)
        
        sheets_res = export_daily_signals_to_gsheets(trade_date=export_date, db=db)
        print("SHEETS RES:", sheets_res)
    finally:
        db.close()

if __name__ == "__main__":
    test()
