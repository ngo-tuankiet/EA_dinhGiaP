from valuation.db.session import engine_write
from sqlalchemy import text

with engine_write.connect() as conn:
    res = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'valuation_outputs';"))
    for row in res:
        print(row)
