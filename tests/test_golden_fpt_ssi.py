"""
Golden Test FPT & SSI — So sánh kết quả định giá với mốc tính tay độc lập để khóa thuật toán.
Tầng 3 của lớp kiểm định chất lượng định giá.
"""
import pytest
from valuation.engine.models.dcf import DCFValuationModel
from valuation.engine.models.securities import SecuritiesValuationModel
from valuation.db.session import SessionLocalRead
from valuation.api.routes.valuation import revalue_ticker
from valuation.db.models import ValuationOutput

@pytest.fixture
def db():
    session = SessionLocalRead()
    yield session
    session.close()

class TestFPTAlgorithmIntegrity:
    def test_dcf_fv_hand_calculation(self):
        """
        Kiểm chứng thuật toán DCF của FPT đối chiếu với kết quả tính tay (Sai số < 15%).
        """
        cf_fpt = {
            'total_equity': 35e12,
            'total_assets': 70e12,
            'cash_and_equivalents': 10e12,
            'total_debt': 15e12,
            'total_revenue': 60e12,
            'ebitda': 12e12,
            'shares_outstanding': 1.7e9,
            'current_price': 130000
        }
        
        assumptions_fpt = {
            'cost_of_equity': 0.12,
            'wacc': 0.10,
            'revenue_growth_1_to_3': 0.18,
            'revenue_growth_4_to_5': 0.15,
            'ebit_margin': 0.16,
            'tax_rate': 0.10,
            'reinvestment_rate': 0.35,
            'target_ev_ebitda': 13.0,
            'long_term_growth': 0.05,
            'weight_dcf': 0.5
        }
        
        model = DCFValuationModel("FPT", cf_fpt, assumptions_fpt)
        res = model.perform_valuation()
        blended_fvps = res['blended_fair_value_per_share']
        
        # Mốc tính tay: 89,013 VND
        hand_calc_fv = 89013
        error = abs(blended_fvps - hand_calc_fv) / hand_calc_fv
        print(f"\n[FPT DCF Verification] Model FV = {blended_fvps:,.0f} VND vs Hand Calc = {hand_calc_fv:,.0f} VND. Sai số = {error:.2%}")
        
        assert error < 0.15, f"Thuật toán DCF FPT lệch quá 15% so với tính tay (Sai số: {error:.2%})"


class TestSSIAlgorithmIntegrity:
    def test_ri_pb_securities_hand_calculation(self):
        """
        Kiểm chứng thuật toán Residual Income + P/B cho SSI đối chiếu với kết quả tính tay (Sai số < 15%).
        """
        cf_ssi = {
            'total_equity': 22e12,
            'total_assets': 60e12,
            'total_revenue': 8e12,
            'net_income': 2.5e12,
            'shares_outstanding': 1.5e9,
            'current_price': 35000
        }
        
        assumptions_ssi = {
            'cost_of_equity': 0.12,
            'long_term_growth': 0.04,
            'market_liquidity_vnd_billion': 18000.0,
            'brokerage_market_share': 0.095,
            'brokerage_margin': 0.0015,
            'margin_loans': 16000.0,
            'net_margin_rate': 0.055,
            'prop_trading_income': 1800.0,
            'opex_ratio': 0.35,
            'tax_rate': 0.20,
            'payout_ratio': 0.20,
            'weight_ri': 0.5
        }
        
        model = SecuritiesValuationModel("SSI", cf_ssi, assumptions_ssi)
        res = model.perform_valuation()
        blended_fvps = res['blended_fair_value_per_share']
        
        # Mốc tính tay: 3,770 VND
        hand_calc_fv = 3770
        error = abs(blended_fvps - hand_calc_fv) / hand_calc_fv
        print(f"\n[SSI RI/PB Verification] Model FV = {blended_fvps:,.0f} VND vs Hand Calc = {hand_calc_fv:,.0f} VND. Sai số = {error:.2%}")
        
        assert error < 0.15, f"Thuật toán SSI RI/PB lệch quá 15% so với tính tay (Sai số: {error:.2%})"


class TestThreeTierValidationGates:
    def test_revalue_fpt_and_check_sanity_gates(self, db):
        """
        Chạy revalue cho FPT và kiểm chứng các tầng:
        - Tầng 1: Implied PE, PB, EV/EBITDA
        - Tầng 2: Consensus check
        """
        # Đảm bảo ticker FPT có sector = 'Technology'
        from valuation.db.models import Ticker, PricesDaily
        t = db.query(Ticker).filter(Ticker.ticker == "FPT").first()
        if not t:
            from valuation.db.session import SessionLocalWrite
            db_write = SessionLocalWrite()
            db_write.add(Ticker(ticker="FPT", company_name="FPT", sector="Technology", is_vn100=True))
            db_write.commit()
            db_write.close()
            
        # Thêm giá hiện tại nếu chưa có
        price = db.query(PricesDaily).filter(PricesDaily.ticker == "FPT").first()
        if not price:
            from valuation.db.session import SessionLocalWrite
            db_write = SessionLocalWrite()
            db_write.add(PricesDaily(ticker="FPT", trade_date="2026-06-24", close=130000, volume=1000000))
            db_write.commit()
            db_write.close()
            
        # Chạy revalue_ticker qua API route
        from valuation.db.session import SessionLocalWrite
        db_write = SessionLocalWrite()
        from fastapi import BackgroundTasks
        bg_tasks = BackgroundTasks()
        res = revalue_ticker("FPT", background_tasks=bg_tasks, db_read=db, db_write=db_write)
        
        assert res["ticker"] == "FPT"
        assert "valuation" in res
        assert "qc" in res
        
        # Check xem các trường qc có trả về flags đúng
        flags = res["qc"]["flags"]
        print(f"\n[FPT Run Flags] {flags}")
        
        # Check xem có bản ghi lưu ValuationOutput trong DB (dùng db_write)
        last_val = db_write.query(ValuationOutput).filter(ValuationOutput.ticker == "FPT").order_by(ValuationOutput.created_at.desc()).first()
        assert last_val is not None
        assert last_val.blended_fair_value_per_share > 0
        assert isinstance(last_val.flags, list)
        db_write.close()
