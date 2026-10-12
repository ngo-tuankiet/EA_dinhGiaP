from valuation.db.session import engine_read
from sqlalchemy import text

with engine_read.connect() as conn:
    res = conn.execute(text("SELECT ticker, sector FROM tickers WHERE ticker IN ('VCB', 'HPG');"))
    for row in res:
        print(row)
