import json
from valuation.db.session import SessionLocalWrite
from valuation.api.routes.valuation import revalue_ticker

def test_qc():
    db = SessionLocalWrite()
    
    # Check VCB (Bank)
    res_vcb = revalue_ticker("VCB", db_read=db, db_write=db)
    print("--- VCB (Ngân hàng) QC ---")
    print(json.dumps(res_vcb.get('qc', {}), indent=2))
    
    # Check HPG (Non-Bank)
    res_hpg = revalue_ticker("HPG", db_read=db, db_write=db)
    print("\n--- HPG (Phi Tài chính) QC ---")
    print(json.dumps(res_hpg.get('qc', {}), indent=2))
    
    # Ensure POOR_QUALITY flows into DB
    from valuation.db.models import ValuationOutput
    out_hpg = db.query(ValuationOutput).filter(ValuationOutput.ticker == "HPG").order_by(ValuationOutput.created_at.desc()).first()
    if out_hpg:
        print("\nHPG ValuationOutput flags in DB:", out_hpg.flags)
        
    db.close()

if __name__ == "__main__":
    test_qc()
