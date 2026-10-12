from valuation.db.session import SessionLocalWrite
from valuation.api.routes.orchestration import run_daily_pipeline, RunDailyRequest

def test():
    db = SessionLocalWrite()
    try:
        request = RunDailyRequest(
            tickers=["VCB", "HPG"],
            force_override=True
        )
        result = run_daily_pipeline(request=request, db=db)
        print("Kết quả Pipeline:")
        print(result)
    finally:
        db.close()

if __name__ == "__main__":
    test()
