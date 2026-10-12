from valuation.db.session import SessionLocalWrite, SessionLocalRead
from sqlalchemy import text

def test_write_connection():
    db = SessionLocalWrite()
    try:
        # Simple test
        result = db.execute(text("SELECT 1")).scalar()
        assert result == 1
    finally:
        db.close()

def test_read_connection():
    db = SessionLocalRead()
    try:
        # Simple test
        result = db.execute(text("SELECT 1")).scalar()
        assert result == 1
    finally:
        db.close()
