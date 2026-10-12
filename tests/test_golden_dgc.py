import pytest
import datetime
from valuation.engine.models.dcf import DCFValuationModel
from valuation.db.session import SessionLocalRead, SessionLocalWrite
from valuation.db.models import ValuationOutput, Ticker, PricesDaily
from valuation.api.routes.valuation import revalue_ticker

@pytest.fixture
def db():
    session = SessionLocalRead()
    yield session
    session.close()

class TestDGCAlgorithmIntegrity:
    def test_dcf_fv_hand_calculation(self):
        """
        Kiểm chứng thuật toán DCF của DGC đối chiếu với kết quả tính tay (Sai số < 15%).
        """
        cf_dgc = {
            'total_equity': 12e12,
            'total_assets': 16e12,
            'cash_and_equivalents': 6e12,
            'total_debt': 1e12,
            'total_revenue': 10e12,
            'ebitda': 2.8e12,
            'shares_outstanding': 379e6,
            'current_price': 50000
        }
        
        assumptions_dgc = {
            'cost_of_equity': 0.12,
            'wacc': 0.11,
            'revenue_growth_1_to_3': 0.15,
            'revenue_growth_4_to_5': 0.10,
            'ebit_margin': 0.22,
            'tax_rate': 0.20,
            'reinvestment_rate': 0.35,
            'target_ev_ebitda': 8.0,
            'long_term_growth': 0.04,
            'weight_dcf': 0.5
        }
        
        model = DCFValuationModel("DGC", cf_dgc, assumptions_dgc)
        res = model.perform_valuation()
        blended_fvps = res['blended_fair_value_per_share']
        
        # Mốc tính tay: 74,892 VND
        hand_calc_fv = 74892
        error = abs(blended_fvps - hand_calc_fv) / hand_calc_fv
        print(f"\n[DGC DCF Verification] Model FV = {blended_fvps:,.0f} VND vs Hand Calc = {hand_calc_fv:,.0f} VND. Sai số = {error:.2%}")
        
        assert error < 0.15, f"Thuật toán DCF DGC lệch quá 15% so với tính tay (Sai số: {error:.2%})"

class TestDGCSanityGates:
    def test_revalue_dgc_and_check_sanity_gates(self, db):
        """
        Chạy revalue cho DGC và kiểm chứng các sanity check.
        """
        # Đảm bảo ticker DGC có sector = 'Chemicals'
        t = db.query(Ticker).filter(Ticker.ticker == "DGC").first()
        if not t:
            db_write = SessionLocalWrite()
            db_write.add(Ticker(ticker="DGC", company_name="Hoá chất Đức Giang", sector="Chemicals", is_vn100=True))
            db_write.commit()
            db_write.close()
            
        # Đảm bảo có giá đóng cửa
        price = db.query(PricesDaily).filter(PricesDaily.ticker == "DGC").first()
        if not price:
            db_write = SessionLocalWrite()
            db_write.add(PricesDaily(ticker="DGC", trade_date=datetime.date.today(), close=50400, volume=1000000))
            db_write.commit()
            db_write.close()
            
        # Chạy revalue_ticker
        db_write = SessionLocalWrite()
        from fastapi import BackgroundTasks
        bg_tasks = BackgroundTasks()
        res = revalue_ticker("DGC", background_tasks=bg_tasks, db_read=db, db_write=db_write)
        
        assert res["ticker"] == "DGC"
        assert "valuation" in res
        assert "qc" in res
        
        flags = res["qc"]["flags"]
        print(f"\n[DGC Run Flags] {flags}")
        
        # Check xem có lưu ValuationOutput trong DB
        last_val = db_write.query(ValuationOutput).filter(ValuationOutput.ticker == "DGC").order_by(ValuationOutput.created_at.desc()).first()
        assert last_val is not None
        assert last_val.blended_fair_value_per_share > 0
        assert isinstance(last_val.flags, list)
        
        db_write.close()
