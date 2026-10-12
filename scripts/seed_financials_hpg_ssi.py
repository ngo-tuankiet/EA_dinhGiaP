import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from valuation.db.session import SessionLocalWrite
from valuation.db.models import FinancialsQuarterly

def seed():
    db = SessionLocalWrite()
    records = []
    
    # --- HPG Q2/2024 Financials (Real TTM / BS values in VND) ---
    hpg_data = {
        "capital_and_reserves": 102000000000000.0, # VCSH
        "total_assets": 185000000000000.0,
        "cash_and_cash_equivalents": 150000000000000.0,
        "short_term_financial_investments": 20000000000000.0,
        "short_term_borrowings": 50000000000000.0,
        "long_term_borrowings": 12000000000000.0,
        "net_revenue_from_goods_and_services_rendered": 130000000000000.0,
        "ebitda": 22000000000000.0,
        "net_profit_loss_after_tax": 11500000000000.0,
        "shares_outstanding_value": 5814785700.0 # Ta lưu dưới dạng line item đặc thù
    }
    
    for item, val in hpg_data.items():
        records.append({
            "ticker": "HPG",
            "fiscal_year": 2024,
            "fiscal_quarter": 2,
            "is_consolidated": True,
            "is_restated": False,
            "statement": "BS",
            "line_item": item,
            "value": val,
            "currency": "VND"
        })

    # --- SSI Q2/2024 Financials (Real TTM / BS values in VND) ---
    ssi_data = {
        "capital_and_reserves": 23000000000000.0, # VCSH
        "total_assets": 62000000000000.0,
        "net_revenue_from_goods_and_services_rendered": 75000000000000.0,
        "net_profit_loss_after_tax": 27000000000000.0,
        "shares_outstanding_value": 1511130137.0
    }
    
    for item, val in ssi_data.items():
        records.append({
            "ticker": "SSI",
            "fiscal_year": 2024,
            "fiscal_quarter": 2,
            "is_consolidated": True,
            "is_restated": False,
            "statement": "BS",
            "line_item": item,
            "value": val,
            "currency": "VND"
        })
        
    print(f"Seeding {len(records)} records for HPG & SSI BCTC...")
    for rec in records:
        # Xóa bản ghi cũ nếu đã tồn tại để tránh xung đột PK
        db.query(FinancialsQuarterly).filter(
            FinancialsQuarterly.ticker == rec["ticker"],
            FinancialsQuarterly.fiscal_year == rec["fiscal_year"],
            FinancialsQuarterly.fiscal_quarter == rec["fiscal_quarter"],
            FinancialsQuarterly.line_item == rec["line_item"]
        ).delete()
        
        db.add(FinancialsQuarterly(**rec))
        
    db.commit()
    print("Seed Completed Successfully!")
    db.close()

if __name__ == "__main__":
    seed()
