import pytest
import datetime
from sqlalchemy.orm import Session
from valuation.db.session import SessionLocalRead, SessionLocalWrite
from valuation.db.models import Ticker, ValuationOutput, ValuationSensitivity, DailySignal, PricesDaily, MacroRadar, MacroSeries
from valuation.engine.daily_signal import calculate_daily_signal

@pytest.fixture
def db_session():
    # Sử dụng transaction rollback để giữ DB sạch sau khi test
    session = SessionLocalWrite()
    yield session
    session.rollback()
    session.close()

def test_stale_fv_behavior_for_banks(db_session):
    """
    Test 1 (RED): Khi fv_fast lệch > 5% so với fv_base đối với sector ngân hàng (Banks/Ngân hàng),
    hệ thống phải dùng fv_base làm effective_fv, gắn cờ STALE_FV + PROVISIONAL.
    
    Trong code cũ: VCB có sector='Banks' không khớp với 'Ngân hàng', nên dùng threshold = 10%
    làm lệch 6% không bị coi là stale, dẫn tới trả fv_fast thay vì fv_base (Test FAIL).
    """
    ticker = "VCB_TEST"
    
    # 1. Setup ticker & price
    t = Ticker(ticker=ticker, company_name="VCB Test", sector="Banks", is_vn100=True)
    db_session.add(t)
    
    price = PricesDaily(
        ticker=ticker,
        trade_date=datetime.date.today(),
        close=92000,
        volume=1000000
    )
    db_session.add(price)
    
    # 2. Setup valuation output (base case)
    val_out = ValuationOutput(
        id=9999,
        ticker=ticker,
        blended_fair_value_per_share=100000,
        margin_of_safety=0.20,
        flags=[]
    )
    db_session.add(val_out)
    
    # 3. Setup Greeks (dFV_ddriver)
    # driver 'nim' có dFV_ddriver = 20,000,000 (cho bump 0.001)
    # bump 0.001 -> delta 0.001 -> impact = 0.001 * 20M = 20,000.
    # fv_fast = fv_base + impact = 100,000 + 20,000 = 120,000.
    # Deviation = 20% (vượt cả 5% và 10%). Ta muốn test lệch 6%:
    # dFV_ddriver = 6,000,000 -> bump 0.001 -> impact = 6,000.
    # Deviation = 6%.
    sens = ValuationSensitivity(
        ticker=ticker,
        assumption_version=9999,
        driver_code="nim",
        dFV_ddriver=6000000,
        base_driver_value=0.028
    )
    db_session.add(sens)
    
    # 4. Setup Macro Series & Radar
    # Đăng ký radar map indicator 'NIM_IND' -> driver 'nim'
    radar = MacroRadar(
        sector="Banks",
        indicator_code="NIM_IND",
        frequency="Q",
        mapped_driver="nim"
    )
    db_session.add(radar)
    
    # Đăng ký macro series để tính delta = latest - previous (code cũ)
    # Lệch delta = 0.001
    m1 = MacroSeries(indicator_code="NIM_IND", date=datetime.date.today(), value=0.029)
    m2 = MacroSeries(indicator_code="NIM_IND", date=datetime.date.today() - datetime.timedelta(days=1), value=0.028)
    db_session.add_all([m1, m2])
    
    db_session.flush()
    
    # 5. Chạy signal
    res = calculate_daily_signal(ticker, db=db_session)
    
    # Assert fv_fast = 106,000 (lệch 6%)
    assert res['fv_fast'] == 106000
    
    # Vì lệch 6% (> 5% stale threshold của bank), effective_fv phải là fv_base (100,000)
    # và flags phải có STALE_FV + PROVISIONAL
    assert "STALE_FV" in res['flags']
    assert "PROVISIONAL" in res['flags']
    assert res['effective_fv'] == 100000

def test_greek_error_returns_none():
    """
    Test 2 (RED): Khi một driver bị bump gây ra lỗi định giá,
    BaseValuationModel.calculate_greeks() phải bắt ngoại lệ và trả về None cho Greek đó (không làm crash).
    
    Trong code cũ: calculate_greeks() không bọc try-except và sẽ ném lỗi trực tiếp (Test FAIL).
    """
    from valuation.engine.models.base import BaseValuationModel
    
    class BrokenModel(BaseValuationModel):
        def forecast_drivers(self):
            return {}
        def perform_valuation(self):
            # Nếu driver rev_growth bị bump (khác 0.10), ném lỗi
            if self.assumptions.get("rev_growth") != 0.10:
                raise ValueError("Calculated failed on bump")
            return {"blended_fair_value_per_share": 100000.0}
            
    cf = {"shares_outstanding": 1e9}
    assumptions = {
        "rev_growth": 0.10,
        "drivers": {
            "rev_growth": {"bump": 0.01}
        }
    }
    
    model = BrokenModel("TEST", cf, assumptions)
    result = model.calculate_greeks()
    
    # Delta của rev_growth phải là None
    assert result['greeks']['delta_rev_growth'] is None

def test_sensitivity_failed_reduces_confidence(db_session):
    """
    Test 2.5 (GREEN): Khi dFV_ddriver là None (SENSITIVITY_FAILED),
    calculate_daily_signal phải gắn cờ SENSITIVITY_FAILED và trừ confidence 0.10.
    """
    ticker = "VCB_TEST_SENS"
    
    # 1. Setup ticker & price
    t = Ticker(ticker=ticker, company_name="VCB Test", sector="Banks", is_vn100=True)
    db_session.add(t)
    
    price = PricesDaily(
        ticker=ticker,
        trade_date=datetime.date.today(),
        close=92000,
        volume=1000000
    )
    db_session.add(price)
    
    # 2. Setup valuation output
    val_out = ValuationOutput(
        id=8888,
        ticker=ticker,
        blended_fair_value_per_share=100000,
        margin_of_safety=0.20,
        flags=[]
    )
    db_session.add(val_out)
    
    # 3. Setup Greeks có dFV_ddriver = None
    sens = ValuationSensitivity(
        ticker=ticker,
        assumption_version=8888,
        driver_code="nim",
        dFV_ddriver=None, # Lỗi
        base_driver_value=0.028
    )
    db_session.add(sens)
    
    # 4. Setup Macro
    radar = MacroRadar(
        sector="Banks",
        indicator_code="NIM_IND",
        frequency="Q",
        mapped_driver="nim"
    )
    db_session.add(radar)
    
    m1 = MacroSeries(indicator_code="NIM_IND", date=datetime.date.today(), value=0.029)
    m2 = MacroSeries(indicator_code="NIM_IND", date=datetime.date.today() - datetime.timedelta(days=1), value=0.028)
    db_session.add_all([m1, m2])
    
    db_session.flush()
    
    res = calculate_daily_signal(ticker, db=db_session)
    
    assert "SENSITIVITY_FAILED" in res['flags']
    # Confidence mặc định = 1.0. Bị phạt vì: SENSITIVITY_FAILED (-0.1), DATA_INCOMPLETE (-0.05) vì thiếu bull/bear, và STALE_FV (-0.20) do macro delta hoạt động mà mất Greek.
    # Tổng confidence = 1.0 - 0.35 = 0.65
    assert abs(res['confidence'] - 0.65) < 0.01

def test_baseline_macro_snapshot_prevents_double_counting(db_session):
    """
    Test 3 (RED): Đảm bảo delta vĩ mô được tính so với snapshot tại thời điểm định giá chậm,
    tránh dùng delta trôi nổi giữa 2 điểm gần nhất gây đếm kép.
    
    Setup:
      - Snapshot vĩ mô lúc định giá chậm: NIM_IND = 0.030.
      - 2 giá trị vĩ mô mới sau đó: 0.028 (hôm qua) và 0.035 (hôm nay).
      - Code cũ tính delta = 0.035 - 0.028 = 0.007.
      - Code mới tính delta = 0.035 - 0.030 = 0.005.
    """
    ticker = "VCB_TEST_DOUBLE"
    
    t = Ticker(ticker=ticker, company_name="VCB Test", sector="Banks", is_vn100=True)
    db_session.add(t)
    
    price = PricesDaily(
        ticker=ticker,
        trade_date=datetime.date.today(),
        close=92000,
        volume=1000000
    )
    db_session.add(price)
    
    # Định giá chậm có lưu snapshot vĩ mô
    val_out = ValuationOutput(
        id=7777,
        ticker=ticker,
        blended_fair_value_per_share=100000,
        margin_of_safety=0.20,
        flags=[],
        macro_snapshot={"NIM_IND": 0.030} # Snapshot vĩ mô
    )
    db_session.add(val_out)
    
    sens = ValuationSensitivity(
        ticker=ticker,
        assumption_version=7777,
        driver_code="nim",
        dFV_ddriver=10000000,
        base_driver_value=0.030
    )
    db_session.add(sens)
    
    radar = MacroRadar(
        sector="Banks",
        indicator_code="NIM_IND",
        frequency="Q",
        mapped_driver="nim"
    )
    db_session.add(radar)
    
    # 2 giá trị vĩ mô mới: 0.028 (trước) và 0.035 (nay)
    m1 = MacroSeries(indicator_code="NIM_IND", date=datetime.date.today(), value=0.035)
    m2 = MacroSeries(indicator_code="NIM_IND", date=datetime.date.today() - datetime.timedelta(days=1), value=0.028)
    db_session.add_all([m1, m2])
    
    db_session.flush()
    
    res = calculate_daily_signal(ticker, db=db_session)
    
    # Applied delta phải là 0.035 - 0.030 = 0.005
    # Nếu là code cũ, delta = 0.035 - 0.028 = 0.007
    assert len(res['applied_deltas']) == 1
    assert abs(res['applied_deltas'][0]['delta'] - 0.005) < 0.0001


def test_upside_validation_limits(db_session):
    """
    Test 4 (RED): Validator upside 2 phía:
    STALE khi upside > +300% (3.0) HOẶC < -90% (-0.9), hoặc fv_fast <= 0, hoặc giá <= 0/NaN.
    """
    ticker = "VCB_TEST_LIMITS"
    
    # Setup ticker & price
    t = Ticker(ticker=ticker, company_name="VCB Test", sector="Banks", is_vn100=True)
    db_session.add(t)
    
    price = PricesDaily(
        ticker=ticker,
        trade_date=datetime.date.today(),
        close=100000,
        volume=1000000
    )
    db_session.add(price)
    
    val_out = ValuationOutput(
        id=6666,
        ticker=ticker,
        blended_fair_value_per_share=100000,
        margin_of_safety=0.20,
        flags=[],
        macro_snapshot={"NIM_IND": 0.030}
    )
    db_session.add(val_out)
    
    sens = ValuationSensitivity(
        ticker=ticker,
        assumption_version=6666,
        driver_code="nim",
        dFV_ddriver=310000000, # bump 0.001 -> delta 310,000 -> fv_fast = 410,000 -> upside = 310% > 300%
        base_driver_value=0.030
    )
    db_session.add(sens)
    
    radar = MacroRadar(
        sector="Banks",
        indicator_code="NIM_IND",
        frequency="Q",
        mapped_driver="nim"
    )
    db_session.add(radar)
    
    m1 = MacroSeries(indicator_code="NIM_IND", date=datetime.date.today(), value=0.031)
    db_session.add(m1)
    db_session.flush()
    
    res = calculate_daily_signal(ticker, db=db_session)
    
    # 1. upside_fast > +300% -> STALE_FV + PROVISIONAL, dùng fv_base
    assert "STALE_FV" in res['flags']
    assert "PROVISIONAL" in res['flags']
    assert res['effective_fv'] == 100000
    
    # 2. upside_fast < -90% (fv_fast = 5000, price = 100,000 -> upside = -95% < -90%)
    sens.dFV_ddriver = 100000000
    m1.value = 0.02905 # delta = -0.00095 -> impact = -95,000 -> fv_fast = 5,000
    db_session.flush()
    
    res2 = calculate_daily_signal(ticker, db=db_session)
    assert "STALE_FV" in res2['flags']
    assert "PROVISIONAL" in res2['flags']
    assert res2['effective_fv'] == 100000
    
    # 3. fv_fast <= 0 (fv_fast = -10,000)
    m1.value = 0.0289 # delta = -0.0011 -> impact = -110,000 -> fv_fast = -10,000
    db_session.flush()
    
    res3 = calculate_daily_signal(ticker, db=db_session)
    assert "STALE_FV" in res3['flags']
    assert "PROVISIONAL" in res3['flags']
    assert res3['effective_fv'] == 100000
    
    # 4. Giá <= 0 hoặc NaN -> STALE_FV + PROVISIONAL
    price.close = 0
    m1.value = 0.030 # fv_fast = 100,000
    db_session.flush()
    
    res4 = calculate_daily_signal(ticker, db=db_session)
    assert "STALE_FV" in res4['flags']
    assert "PROVISIONAL" in res4['flags']
    assert res4['effective_fv'] == 100000
    
    import math
    price.close = float('nan')
    db_session.flush()
    
    res5 = calculate_daily_signal(ticker, db=db_session)
    assert "STALE_FV" in res5['flags']
    assert "PROVISIONAL" in res5['flags']
    assert res5['effective_fv'] == 100000


def test_financial_qc_missing_reduces_confidence(db_session):
    """
    Test 5 (RED): Với mã chứng khoán/bảo hiểm (không phải ngân hàng),
    QC result phải gắn FINANCIAL_QC_MISSING, và daily signal phải giảm confidence đi 0.15.
    """
    from valuation.quality.scores import run_qc_checks
    
    ticker = "SSI_TEST"
    
    # 1. Test run_qc_checks trực tiếp
    import pandas as pd
    df_empty = pd.DataFrame()
    qc_res = run_qc_checks(ticker, "Securities", df_empty)
    assert "FINANCIAL_QC_MISSING" in qc_res['flags']
    
    # 2. Test daily signal confidence reduction
    t = Ticker(ticker=ticker, company_name="SSI Test", sector="Securities", is_vn100=True)
    db_session.add(t)
    
    price = PricesDaily(
        ticker=ticker,
        trade_date=datetime.date.today(),
        close=35000,
        volume=1000000
    )
    db_session.add(price)
    
    val_out = ValuationOutput(
        id=5555,
        ticker=ticker,
        blended_fair_value_per_share=40000,
        margin_of_safety=0.30,
        flags=["FINANCIAL_QC_MISSING"] # flag lưu từ QC
    )
    db_session.add(val_out)
    
    sens = ValuationSensitivity(
        ticker=ticker,
        assumption_version=5555,
        driver_code="brokerage_market_share",
        dFV_ddriver=1000000,
        base_driver_value=0.10
    )
    db_session.add(sens)
    
    db_session.flush()
    
    res = calculate_daily_signal(ticker, db=db_session)
    
    # Assert cờ FINANCIAL_QC_MISSING được truyền vào signal
    assert "FINANCIAL_QC_MISSING" in res['flags']
    
    # Confidence: 1.0 - 0.05 (DATA_INCOMPLETE do thiếu bull/bear) - 0.15 (FINANCIAL_QC_MISSING) = 0.80
    assert abs(res['confidence'] - 0.80) < 0.01


def test_past_trade_date_skip_upsert(db_session):
    """
    Test 6 (RED): CHỈ upsert khi trade_date == hôm nay;
    ghi đè ngày quá khứ phải có force_override=True.
    Đồng thời cập nhật computed_at khi ghi đè hoặc insert.
    """
    ticker = "VCB_TEST_PIT"
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    
    t = Ticker(ticker=ticker, company_name="VCB Test", sector="Banks", is_vn100=True)
    db_session.add(t)
    
    # 1. Setup PricesDaily cho ngày hôm qua
    price = PricesDaily(
        ticker=ticker,
        trade_date=yesterday,
        close=95000,
        volume=1000000
    )
    db_session.add(price)
    
    val_out = ValuationOutput(
        id=4444,
        ticker=ticker,
        blended_fair_value_per_share=100000,
        margin_of_safety=0.20,
        flags=[]
    )
    db_session.add(val_out)
    
    sens = ValuationSensitivity(
        ticker=ticker,
        assumption_version=4444,
        driver_code="nim",
        dFV_ddriver=10000000,
        base_driver_value=0.028
    )
    db_session.add(sens)
    db_session.flush() # Flush trước các dependency để tránh lỗi FK khi insert sig_old
    
    # 2. Tạo sẵn 1 bản ghi DailySignal ngày hôm qua trong DB với conviction_score = 99.0
    ten_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10)
    sig_old = DailySignal(
        ticker=ticker,
        trade_date=yesterday,
        close_price=95000,
        fair_value_fast=100000,
        upside=0.05,
        margin_of_safety=0.20,
        conviction_score=99.0, # Giá trị cũ muốn bảo vệ
        flags=["OLD_RUN"],
        computed_at=ten_days_ago
    )
    db_session.add(sig_old)
    db_session.flush()
    
    # 3. Chạy calculate_daily_signal cho ngày hôm qua (yesterday) với force_override=False
    res1 = calculate_daily_signal(ticker, trade_date=yesterday, force_override=False, db=db_session)
    
    # Phải trả về kết quả với upserted = False
    assert res1["upserted"] is False
    
    # Query DB kiểm tra bản ghi ngày hôm qua không đổi
    db_session.expire(sig_old)
    sig_db = db_session.query(DailySignal).filter_by(ticker=ticker, trade_date=yesterday).one()
    assert sig_db.conviction_score == 99.0
    assert "OLD_RUN" in sig_db.flags
    
    # 4. Chạy với force_override=True
    res2 = calculate_daily_signal(ticker, trade_date=yesterday, force_override=True, db=db_session)
    
    # Phải trả về kết quả với upserted = True
    assert res2["upserted"] is True
    
    # Query DB kiểm tra bản ghi ngày hôm qua đã bị thay đổi và computed_at được cập nhật
    db_session.expire(sig_db)
    sig_db2 = db_session.query(DailySignal).filter_by(ticker=ticker, trade_date=yesterday).one()
    assert sig_db2.conviction_score != 99.0
    assert sig_db2.computed_at is not None
    computed_ts = sig_db2.computed_at if sig_db2.computed_at.tzinfo else sig_db2.computed_at.replace(tzinfo=datetime.timezone.utc)
    assert computed_ts > ten_days_ago


def test_active_greek_error_triggers_stale(db_session):
    """
    Test Nhóm B.2 (RED): Khi một driver có macro_delta != 0 nhưng dFV_ddriver là None,
    hệ thống phải gắn SENSITIVITY_FAILED và đẩy STALE_FV + PROVISIONAL.
    """
    ticker = "VCB_TEST_ACTIVE_GREEK"
    
    t = Ticker(ticker=ticker, company_name="VCB Test", sector="Banks", is_vn100=True)
    db_session.add(t)
    
    price = PricesDaily(
        ticker=ticker,
        trade_date=datetime.date.today(),
        close=92000,
        volume=1000000
    )
    db_session.add(price)
    
    val_out = ValuationOutput(
        id=3333,
        ticker=ticker,
        blended_fair_value_per_share=100000,
        margin_of_safety=0.20,
        flags=[],
        macro_snapshot={"NIM_IND": 0.028}
    )
    db_session.add(val_out)
    
    sens = ValuationSensitivity(
        ticker=ticker,
        assumption_version=3333,
        driver_code="nim",
        dFV_ddriver=None,
        base_driver_value=0.028
    )
    db_session.add(sens)
    
    radar = MacroRadar(
        sector="Banks",
        indicator_code="NIM_IND",
        frequency="Q",
        mapped_driver="nim"
    )
    db_session.add(radar)
    
    m1 = MacroSeries(indicator_code="NIM_IND", date=datetime.date.today(), value=0.029)
    db_session.add(m1)
    db_session.flush()
    
    res = calculate_daily_signal(ticker, db=db_session)
    
    assert "SENSITIVITY_FAILED" in res['flags']
    assert "STALE_FV" in res['flags']
    assert "PROVISIONAL" in res['flags']
    assert res['effective_fv'] == 100000
    assert abs(res['confidence'] - 0.65) < 0.01


def test_worst_case_confidence_floor(db_session):
    """
    Test Nhóm B.3: Xác nhận confidence chạm sàn 0.5 đúng và không bị âm khi hội tụ tất cả penalty:
    - FINANCIAL_QC_MISSING (-0.15)
    - STALE_FV (-0.20)
    - SENSITIVITY_FAILED (-0.10)
    - WIDE_SPREAD (-0.10)
    - LOW_LIQUIDITY (-0.10)
    Tổng cộng penalty = -0.65 -> confidence lý thuyết = 0.35 -> chạm sàn = 0.5.
    """
    ticker = "SSI_TEST_WORST"
    
    t = Ticker(ticker=ticker, company_name="SSI Worst Test", sector="Securities", is_vn100=True)
    db_session.add(t)
    
    # Volume 100,000 < 500,000 (LOW_LIQUIDITY -> -0.10)
    price = PricesDaily(
        ticker=ticker,
        trade_date=datetime.date.today(),
        close=35000,
        volume=100000
    )
    db_session.add(price)
    
    # Có bull/bear nhưng spread rộng: (150k - 50k) / 100k = 1.0 > 0.60 (WIDE_SPREAD -> -0.10)
    val_out = ValuationOutput(
        id=2222,
        ticker=ticker,
        blended_fair_value_per_share=100000,
        fair_value_bull=150000,
        fair_value_bear=50000,
        margin_of_safety=0.30,
        flags=["FINANCIAL_QC_MISSING"], # FINANCIAL_QC_MISSING -> -0.15
        macro_snapshot={"NIM_IND": 0.028}
    )
    db_session.add(val_out)
    
    # dFV_ddriver = None + macro delta != 0 (SENSITIVITY_FAILED + STALE_FV -> -0.10 - 0.20)
    sens = ValuationSensitivity(
        ticker=ticker,
        assumption_version=2222,
        driver_code="nim",
        dFV_ddriver=None,
        base_driver_value=0.028
    )
    db_session.add(sens)
    
    radar = MacroRadar(
        sector="Securities",
        indicator_code="NIM_IND",
        frequency="Q",
        mapped_driver="nim"
    )
    db_session.add(radar)
    
    m1 = MacroSeries(indicator_code="NIM_IND", date=datetime.date.today(), value=0.029)
    db_session.add(m1)
    db_session.flush()
    
    res = calculate_daily_signal(ticker, db=db_session)
    
    # Assert flags
    assert "FINANCIAL_QC_MISSING" in res['flags']
    assert "STALE_FV" in res['flags']
    assert "SENSITIVITY_FAILED" in res['flags']
    assert "WIDE_SPREAD" in res['flags']
    assert "LOW_LIQUIDITY" in res['flags']
    
    # Confidence lý thuyết: 1.0 - 0.15 - 0.20 - 0.10 - 0.10 - 0.10 = 0.35 -> floor = 0.50
    assert res['confidence'] == 0.50






