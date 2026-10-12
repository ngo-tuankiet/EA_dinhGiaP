import pytest
import datetime
from unittest.mock import patch
from sqlalchemy.orm import Session

from valuation.db.session import SessionLocalWrite
from valuation.db.models import Consensus, Ticker, ValuationOutput, ValuationSensitivity, PricesDaily, DailySignal
from valuation.engine.consensus_helper import get_consensus_stats
from valuation.engine.daily_signal import calculate_daily_signal

@pytest.fixture
def db_session():
    session = SessionLocalWrite()
    
    # Clean up test records in correct order of dependency
    session.query(DailySignal).filter(DailySignal.ticker == "TEST_TCK").delete()
    session.query(Consensus).filter(Consensus.ticker == "TEST_TCK").delete()
    session.query(ValuationSensitivity).filter(ValuationSensitivity.ticker == "TEST_TCK").delete()
    session.query(ValuationOutput).filter(ValuationOutput.ticker == "TEST_TCK").delete()
    session.query(PricesDaily).filter(PricesDaily.ticker == "TEST_TCK").delete()
    session.query(Ticker).filter(Ticker.ticker == "TEST_TCK").delete()
    session.commit()
    
    # Add dummy ticker
    session.add(Ticker(ticker="TEST_TCK", company_name="Test Ticker", sector="Technology", is_vn100=True))
    session.commit()
    
    yield session
    
    # Clean up again after test
    session.query(DailySignal).filter(DailySignal.ticker == "TEST_TCK").delete()
    session.query(Consensus).filter(Consensus.ticker == "TEST_TCK").delete()
    session.query(ValuationSensitivity).filter(ValuationSensitivity.ticker == "TEST_TCK").delete()
    session.query(ValuationOutput).filter(ValuationOutput.ticker == "TEST_TCK").delete()
    session.query(PricesDaily).filter(PricesDaily.ticker == "TEST_TCK").delete()
    session.query(Ticker).filter(Ticker.ticker == "TEST_TCK").delete()
    session.commit()
    session.close()

def test_consensus_stats_lookahead_and_window(db_session: Session):
    """
    Test get_consensus_stats:
    - Phải lọc report_date <= trade_date (chống lookahead).
    - Phải lọc report_date >= trade_date - 180 ngày.
    - Tính đúng trung vị (median) và trung bình (mean).
    """
    trade_date = datetime.date(2026, 6, 20)
    
    # Thêm 4 báo cáo consensus:
    # 1. Hợp lệ: ngày 2026-06-15 (trong 180 ngày, trước trade_date)
    # 2. Hợp lệ: ngày 2026-05-20 (trong 180 ngày, trước trade_date)
    # 3. Lookahead (Vi phạm): ngày 2026-06-21 (sau trade_date)
    # 4. Stale (Vi phạm): ngày 2025-12-15 (quá 180 ngày trước trade_date)
    
    db_session.add_all([
        Consensus(ticker="TEST_TCK", broker="Broker A", report_date=datetime.date(2026, 6, 15), target_price=100000.0),
        Consensus(ticker="TEST_TCK", broker="Broker B", report_date=datetime.date(2026, 5, 20), target_price=120000.0),
        Consensus(ticker="TEST_TCK", broker="Broker C", report_date=datetime.date(2026, 6, 21), target_price=150000.0),
        Consensus(ticker="TEST_TCK", broker="Broker D", report_date=datetime.date(2025, 12, 15), target_price=80000.0)
    ])
    db_session.commit()
    
    stats = get_consensus_stats("TEST_TCK", trade_date, db_session)
    
    # Chỉ Broker A (100k) và Broker B (120k) được tính
    assert stats["count"] == 2
    # Trung vị của 100k và 120k là 110k
    assert stats["median"] == 110000.0
    # Trung bình là 110k
    assert stats["mean"] == 110000.0

def test_daily_signal_consensus_deviation_flag(db_session: Session):
    """
    Test cờ CONSENSUS_DEVIATION_HIGH và giảm confidence:
    - Nếu blended_fv lệch > 25% trung vị consensus, cờ phải bật.
    - Confidence phải bị trừ 0.10.
    """
    trade_date = datetime.date(2026, 6, 20)
    
    # Thêm giá daily
    db_session.add(PricesDaily(ticker="TEST_TCK", trade_date=trade_date, close=100000.0, volume=1000000))
    
    # Thêm Valuation Output (Blended FV = 150k)
    val_out = ValuationOutput(
        ticker="TEST_TCK", 
        blended_fair_value_per_share=150000.0,
        fair_value_bull=180000.0,
        fair_value_bear=120000.0,
        margin_of_safety=0.3
    )
    db_session.add(val_out)
    db_session.commit()
    
    # Thêm Valuation Sensitivity (Greeks) để không bị lỗi NO_BASELINE
    # Ta add 1 driver rỗng hoặc driver có dFV_ddriver = 0
    db_session.add(ValuationSensitivity(
        ticker="TEST_TCK",
        assumption_version=val_out.id,
        driver_code="interest_rate",
        dFV_ddriver=0.0,
        base_driver_value=0.06
    ))
    db_session.commit()
    
    # Thêm Consensus (Trung vị = 100k -> Lệch = (150 - 100)/100 = 50% > 25%)
    db_session.add(Consensus(ticker="TEST_TCK", broker="Broker A", report_date=datetime.date(2026, 6, 10), target_price=100000.0))
    db_session.commit()
    
    # Chạy Daily Signal
    # Mock get_macro_deltas để không bị lỗi trống
    with patch("valuation.engine.daily_signal.get_macro_deltas", return_value={}):
        res = calculate_daily_signal("TEST_TCK", trade_date=trade_date, db=db_session)
            
    assert "CONSENSUS_DEVIATION_HIGH" in res["flags"]
    # Kiểm tra xem confidence có bị trừ 0.10 do CONSENSUS_DEVIATION_HIGH hay không (1.0 - 0.10 = 0.90)
    assert "DATA_INCOMPLETE" not in res["flags"]
    assert res["confidence"] == 0.90

