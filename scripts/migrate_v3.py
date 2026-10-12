from valuation.db.session import SessionLocalWrite
import sqlalchemy as sa

def run_migration():
    db = SessionLocalWrite()
    try:
        # Check columns for daily_signal
        inspector = sa.inspect(db.bind)
        cols_signal = [c['name'] for c in inspector.get_columns('daily_signal')]
        if 'computed_at' not in cols_signal:
            print("Adding computed_at to daily_signal...")
            db.execute(sa.text("ALTER TABLE daily_signal ADD COLUMN computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP"))
            db.commit()
            print("Successfully added computed_at.")
        else:
            print("computed_at already exists in daily_signal.")

        # Check columns for valuation_outputs
        cols_val = [c['name'] for c in inspector.get_columns('valuation_outputs')]
        if 'macro_snapshot' not in cols_val:
            print("Adding macro_snapshot to valuation_outputs...")
            db.execute(sa.text("ALTER TABLE valuation_outputs ADD COLUMN macro_snapshot JSONB"))
            db.commit()
            print("Successfully added macro_snapshot.")
        else:
            print("macro_snapshot already exists in valuation_outputs.")
    except Exception as e:
        db.rollback()
        print("Migration failed:", e)
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
