"""
Integration test for DB & Streamlit flows.
"""
import pytest
from valuation.db.session import SessionLocalRead, SessionLocalWrite
from valuation.data_access.repo import build_company_data
from valuation.engine.models.bank_general import BankGeneralValuationModel
from valuation.engine.models.dcf import DCFValuationModel
from valuation.db.models import ValuationRun

@pytest.fixture
def db_read():
    session = SessionLocalRead()
    yield session
    session.close()

@pytest.fixture
def db_write():
    session = SessionLocalWrite()
    yield session
    session.close()

def test_integration_load_vcb(db_read):
    """Kiểm tra load VCB từ database và định giá Justified P/B."""
    company = build_company_data(db_read, "VCB", mode="TTM")
    assert company.ticker == "VCB"
    assert len(company.historical_is) > 0
    assert len(company.historical_bs) > 0
    assert company.current_price > 0
    
    model = BankGeneralValuationModel(company)
    res = model.perform_valuation()
    assert res["blended_fair_value_per_share"] > 0

def test_integration_load_hpg(db_read):
    """Kiểm tra load HPG từ database và định giá DCF."""
    company = build_company_data(db_read, "HPG", mode="TTM")
    assert company.ticker == "HPG"
    assert len(company.historical_is) > 0
    assert len(company.historical_bs) > 0
    assert company.current_price > 0
    
    model = DCFValuationModel.from_pydantic(company)
    res = model.perform_valuation()
    assert res["blended_fair_value_per_share"] > 0

def test_integration_save_and_cleanup_run(db_read, db_write):
    """Kiểm tra ghi kịch bản định giá vào valuation_runs và sau đó cleanup để tránh rác DB."""
    # 1. Ghi thử 1 kịch bản định giá giả lập cho VCB
    run_record = ValuationRun(
        ticker="VCB",
        analyst="Integration Test Bot",
        engine="bank",
        method="Justified P/B",
        scenario="Base",
        assumptions_json={"test_key": "test_val"},
        base_year_mode="TTM",
        wacc=None,
        terminal_g=0.02,
        target_price=65000.0,
        current_price=92000.0,
        upside=-29.3,
        recommendation="BÁN",
        notes="Ghi thử nghiệm từ integration test."
    )
    
    db_write.add(run_record)
    db_write.commit()
    db_write.refresh(run_record)
    
    assert run_record.id is not None
    assert run_record.ticker == "VCB"
    
    # 2. Truy vấn lại để xác nhận ghi thành công
    queried = db_write.query(ValuationRun).filter(ValuationRun.id == run_record.id).first()
    assert queried is not None
    assert queried.analyst == "Integration Test Bot"
    assert queried.assumptions_json == {"test_key": "test_val"}
    
    # 3. Cleanup: Xóa bản ghi test để bảo vệ DB sạch sẽ
    db_write.delete(run_record)
    db_write.commit()
    
    # 4. Xác nhận đã xóa thành công
    deleted = db_write.query(ValuationRun).filter(ValuationRun.id == run_record.id).first()
    assert deleted is None
