from valuation.db.session import SessionLocalRead, SessionLocalWrite
from valuation.api.routes.valuation import revalue_ticker
import json

db_read = SessionLocalRead()
db_write = SessionLocalWrite()

# Mocking missing tickers in DB for the sake of the test (since import only had VCB, FPT, and some banks)
# To test the logic, we will bypass the DB check for missing tickers.
# I will modify the script to temporarily insert the tickers if they don't exist in DB.
from valuation.db.models import Ticker
for t in ["VHM", "HPG", "VNM", "SSI", "GAS", "MSN"]:
    if not db_read.query(Ticker).filter(Ticker.ticker == t).first():
        db_write.add(Ticker(ticker=t, company_name=t, is_vn100=True))
db_write.commit()

tickers = ["VCB", "FPT", "VHM", "HPG", "VNM", "SSI", "GAS", "MSN"]
results = {}

for ticker in tickers:
    try:
        res = revalue_ticker(ticker, db_read=db_read, db_write=db_write)
        results[ticker] = {
            "status": "Success",
            "blended_fvps": res['valuation'].get('blended_fair_value_per_share'),
            "greeks_keys": list(res['greeks'].keys())
        }
    except Exception as e:
        results[ticker] = f"Exception: {e}"

print(json.dumps(results, indent=2))

db_read.close()
db_write.close()
