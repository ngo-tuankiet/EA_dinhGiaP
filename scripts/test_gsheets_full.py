import datetime
from valuation.db.session import SessionLocalWrite
from valuation.engine.daily_signal import calculate_daily_signal
from valuation.output.gsheets_exporter import export_daily_signals_to_gsheets

def test():
    db = SessionLocalWrite()
    try:
        # Generate signal for VCB
        target_date = datetime.date(2026, 6, 20)
        print("Calculating signal for VCB...")
        sig_res = calculate_daily_signal("VCB", trade_date=target_date, force_override=True, db=db)
        print("Signal Result:", sig_res)
        
        # Export to sheets
        print("Exporting to Google Sheets...")
        res = export_daily_signals_to_gsheets(trade_date=target_date, db=db)
        print("Export Result:", res)
    finally:
        db.close()

if __name__ == "__main__":
    test()
