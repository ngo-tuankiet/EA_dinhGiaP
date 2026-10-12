from sqlalchemy import text
from valuation.db.session import engine_write

def migrate():
    with engine_write.begin() as conn:
        conn.execute(text('ALTER TABLE valuation_outputs ADD COLUMN IF NOT EXISTS flags JSON;'))
        print("Added flags to valuation_outputs")
            
    with engine_write.begin() as conn:
        conn.execute(text('ALTER TABLE daily_signal ADD COLUMN IF NOT EXISTS flags JSON;'))
        print("Added flags to daily_signal")

if __name__ == "__main__":
    migrate()
