import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from valuation.db.session import SessionLocalWrite, Base
# Import rõ ràng để SQLAlchemy metadata ghi nhận các models
from valuation.db.models import Ticker, FinancialsQuarterly, PricesDaily, BackfillStatus, ValuationOutput, ValuationSensitivity, MacroRadar, MacroSeries, DailySignal, Consensus

def run_migration():
    db = SessionLocalWrite()
    try:
        print("Creating table consensus_history if not exist using metadata...")
        Base.metadata.create_all(bind=db.bind)
        print("Consensus history table migration completed successfully!")
    except Exception as e:
        db.rollback()
        print("Consensus migration failed:", e)
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
