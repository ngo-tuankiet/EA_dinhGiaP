import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from valuation.db.session import Base
from valuation.db.models import MacroRadar, MacroSeries

engine = create_engine("postgresql://macos@localhost:5432/vn100")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables if not exist
Base.metadata.create_all(bind=engine)

def seed_macro_radar():
    db = SessionLocal()
    # Clear old records
    db.query(MacroRadar).delete()
    
    configs = [
        MacroRadar(
            sector="ALL",
            indicator_code="TPCP_10Y",
            frequency="DAILY",
            source="SBV/BOND",
            warn_low=0.02, # < 2% maybe very loose monetary policy
            warn_high=0.06, # > 6% tight
            mapped_driver="risk_free_rate" # Mapping TPCP_10Y to risk_free_rate (or wacc)
        ),
        MacroRadar(
            sector="Ngân hàng",
            indicator_code="CREDIT_GROWTH",
            frequency="MONTHLY",
            source="SBV",
            warn_low=0.05,
            warn_high=0.15,
            mapped_driver="credit_growth"
        ),
        MacroRadar(
            sector="Tài nguyên Cơ bản",
            indicator_code="STEEL_HRC",
            frequency="WEEKLY",
            source="LME/SHFE",
            warn_low=3000,
            warn_high=6000,
            mapped_driver="gross_margin" # Changed to gross margin or similar
        )
    ]
    db.add_all(configs)
    db.commit()
    print("Seeded MacroRadar configs.")
    db.close()

def seed_mock_macro_series():
    db = SessionLocal()
    db.query(MacroSeries).delete()
    
    today = datetime.date.today()
    last_week = today - datetime.timedelta(days=7)
    last_month = today - datetime.timedelta(days=30)
    
    series = [
        # TPCP_10Y increased from 0.03 to 0.032
        MacroSeries(indicator_code="TPCP_10Y", date=last_week, value=0.03, source="BOND"),
        MacroSeries(indicator_code="TPCP_10Y", date=today, value=0.032, source="BOND"),
        
        # CREDIT_GROWTH decreased from 0.14 to 0.12
        MacroSeries(indicator_code="CREDIT_GROWTH", date=last_month, value=0.14, source="SBV"),
        MacroSeries(indicator_code="CREDIT_GROWTH", date=today, value=0.12, source="SBV"),
        
        # STEEL_HRC dropped from 4000 to 3800
        MacroSeries(indicator_code="STEEL_HRC", date=last_week, value=4000, source="SHFE"),
        MacroSeries(indicator_code="STEEL_HRC", date=today, value=3800, source="SHFE"),
    ]
    db.add_all(series)
    db.commit()
    print("Seeded MacroSeries mock data.")
    db.close()

if __name__ == "__main__":
    seed_macro_radar()
    seed_mock_macro_series()
