from valuation.engine.daily_signal import calculate_batch_signals, calculate_daily_signal
from valuation.db.session import SessionLocalWrite
from valuation.db.models import PricesDaily, ValuationOutput, ValuationSensitivity, Ticker, DailySignal
import datetime
import json

def setup_mock_data(db):
    # Create Tickers
    for t in ["VCB", "HPG", "MISSING_BASE"]:
        obj = db.query(Ticker).filter_by(ticker=t).first()
        if not obj:
            db.add(Ticker(ticker=t, sector="Ngân hàng" if t=="VCB" else "Tài nguyên Cơ bản"))

    # Insert prices for past date (simulating history)
    past_date = datetime.date(2026, 6, 20)
    for t, p in [("VCB", 95000), ("HPG", 30000), ("MISSING_BASE", 15000)]:
        obj = db.query(PricesDaily).filter_by(ticker=t, trade_date=past_date).first()
        if not obj:
            db.add(PricesDaily(ticker=t, trade_date=past_date, close=p, volume=1_000_000))
        
    # Base Valuation for VCB
    v_vcb = db.query(ValuationOutput).filter_by(ticker="VCB").first()
    if not v_vcb:
        v_vcb = ValuationOutput(ticker="VCB", blended_fair_value_per_share=105000, margin_of_safety=0.2)
        db.add(v_vcb)
        db.commit() 
        
    s = db.query(ValuationSensitivity).filter_by(ticker="VCB").first()
    if not s:
        db.add_all([
            ValuationSensitivity(ticker="VCB", assumption_version=v_vcb.id, driver_code="risk_free_rate", dFV_ddriver=-500000),
        ])
        
    # Base Valuation for HPG (With STALE condition and Wide Spread)
    v_hpg = db.query(ValuationOutput).filter_by(ticker="HPG").first()
    if not v_hpg:
        # Close is 30,000. Base FV = 45,000 (Upside = 50%). Required MoS = 30%.
        # Spread is > 60% (e.g. 55000 - 15000 = 40000 -> 40k/45k = 88%)
        v_hpg = ValuationOutput(ticker="HPG", blended_fair_value_per_share=45000, margin_of_safety=0.3, fair_value_bull=55000, fair_value_bear=15000)
        db.add(v_hpg)
        db.commit()
        db.add(ValuationSensitivity(ticker="HPG", assumption_version=v_hpg.id, driver_code="wacc", dFV_ddriver=-1000000))

    db.commit()
    return past_date

def test_batch_signal():
    db = SessionLocalWrite()
    past_date = setup_mock_data(db)
    
    print("\n--- Test 1: Batch Run (History without force override) ---")
    results = calculate_batch_signals(["VCB", "HPG", "MISSING_BASE"], trade_date=past_date, force_override=False, db=db)
    print(json.dumps(results, indent=2))
    for t in ["VCB", "HPG"]:
        assert results[t]["upserted"] == False, "Should not upsert historical data without override"
        
    print("\n--- Test 2: Idempotency (Upsert with Override) ---")
    calculate_daily_signal("VCB", trade_date=past_date, force_override=True, db=db)
    calculate_daily_signal("VCB", trade_date=past_date, force_override=True, db=db)
    count = db.query(DailySignal).filter_by(ticker="VCB").count()
    print(f"VCB DailySignal records count (should be 1): {count}")
    
    print("\n--- Test 3: Golden Hand-calc Check for HPG ---")
    # HPG Price = 30000
    # Base FV = 45000, MoS = 30%
    # Upside = 15000/30000 = 50%
    # Excess = 50% - 30% = 20%
    # Attractiveness = (20/25) * 100 = 80
    # Confidence: 
    # Spread = (55000 - 15000) / 45000 = 40000/45000 = 88% (>60%) -> Wide Spread penalty (-0.1)
    # Total Confidence = 1.0 - 0.1 = 0.9
    # Conviction = 80 * 0.9 = 72
    res = calculate_daily_signal("HPG", trade_date=past_date, force_override=True, db=db)
    assert "WIDE_SPREAD" in res["flags"], "Expected WIDE_SPREAD flag"
    assert abs(res["conviction_score"] - 72.0) < 0.1, f"Expected 72, got {res['conviction_score']}"
    print("Golden check passed! HPG Conviction is 72.")
    
    db.close()

if __name__ == "__main__":
    test_batch_signal()
