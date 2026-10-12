from fastapi import FastAPI
from valuation.db.session import SessionLocalRead
from sqlalchemy import text
from valuation.api.routes import ingest, valuation, signals, orchestration

app = FastAPI(title="VN100 Valuation API", version="0.1.0")

app.include_router(ingest.router, prefix="/ingest")
app.include_router(valuation.router, prefix="/revalue")
app.include_router(signals.router, prefix="/signals")
app.include_router(orchestration.router, prefix="/orchestration")

@app.get("/health")
def health_check():
    db = SessionLocalRead()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}
    finally:
        db.close()
