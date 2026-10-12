from valuation.db.session import engine_read
from sqlalchemy import text

with engine_read.connect() as conn:
    res = conn.execute(text("SELECT DISTINCT sector FROM tickers;"))
    for row in res:
        print(row)
