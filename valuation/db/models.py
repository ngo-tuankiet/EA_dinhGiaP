from sqlalchemy import Column, String, Boolean, Integer, Numeric, Date, BigInteger, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
import datetime
from valuation.db.session import Base

class Ticker(Base):
    __tablename__ = "tickers"
    
    ticker = Column(String, primary_key=True)
    company_name = Column(String)
    exchange = Column(String)
    sector = Column(String)
    industry = Column(String)
    is_vn100 = Column(Boolean)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

class FinancialsQuarterly(Base):
    __tablename__ = "financials_quarterly"
    
    ticker = Column(String, ForeignKey("tickers.ticker"), primary_key=True)
    fiscal_year = Column(Integer, primary_key=True)
    fiscal_quarter = Column(Integer, primary_key=True)
    is_consolidated = Column(Boolean, primary_key=True)
    is_restated = Column(Boolean, primary_key=True)
    statement = Column(String, primary_key=True)
    line_item = Column(String, primary_key=True)
    value = Column(Numeric)
    currency = Column(String, default="VND")
    source = Column(String)
    published_at = Column(Date, nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())

class PricesDaily(Base):
    __tablename__ = "prices_daily"
    
    ticker = Column(String, primary_key=True)
    trade_date = Column(Date, primary_key=True)
    open = Column(Numeric)
    high = Column(Numeric)
    low = Column(Numeric)
    close = Column(Numeric)
    adj_close = Column(Numeric, nullable=True)
    volume = Column(BigInteger)
    value = Column(Numeric, nullable=True)
    
    # Dòng tiền khối ngoại
    foreign_buy = Column(Numeric, nullable=True)
    foreign_sell = Column(Numeric, nullable=True)
    foreign_buy_vol = Column(Numeric, nullable=True)
    foreign_buy_val = Column(Numeric, nullable=True)
    foreign_sell_vol = Column(Numeric, nullable=True)
    foreign_sell_val = Column(Numeric, nullable=True)
    foreign_net_vol = Column(Numeric, nullable=True)
    foreign_net_val = Column(Numeric, nullable=True)
    
    # Dòng tiền tự doanh
    proprietary_buy_vol = Column(Numeric, nullable=True)
    proprietary_buy_val = Column(Numeric, nullable=True)
    proprietary_sell_vol = Column(Numeric, nullable=True)
    proprietary_sell_val = Column(Numeric, nullable=True)
    proprietary_net_vol = Column(Numeric, nullable=True)
    proprietary_net_val = Column(Numeric, nullable=True)
    
    price_unit = Column(String, default="VND")

class BackfillStatus(Base):
    __tablename__ = "backfill_status"
    
    ticker = Column(String, primary_key=True)
    last_financial_period = Column(String)
    last_price_date = Column(Date)
    status = Column(String)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CorporateAction(Base):
    """Sự kiện vốn/quyền cổ đông có truy vết và giữ nguyên lịch sử nguồn."""

    __tablename__ = "corporate_actions"

    ticker = Column(String, ForeignKey("tickers.ticker"), primary_key=True)
    source_site = Column(String, primary_key=True)
    source_event_id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False)
    event_code = Column(String, nullable=True)
    title = Column(String, nullable=False)
    announcement_date = Column(Date, nullable=True)
    ex_right_date = Column(Date, nullable=True)
    record_date = Column(Date, nullable=True)
    payment_date = Column(Date, nullable=True)
    listing_date = Column(Date, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    exercise_ratio = Column(Numeric, nullable=True)
    cash_amount_vnd_per_share = Column(Numeric, nullable=True)
    issue_price_vnd = Column(Numeric, nullable=True)
    shares_issued = Column(Numeric, nullable=True)
    shares_after = Column(Numeric, nullable=True)
    source_url = Column(String, nullable=True)
    source_tier = Column(String, nullable=False, default="AGGREGATOR")
    raw_payload = Column(JSON, nullable=True)
    content_hash = Column(String(64), nullable=False)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class CorporateActionSync(Base):
    """Checkpoint giúp chỉ kiểm tra nguồn khi dữ liệu của mã đã quá TTL."""

    __tablename__ = "corporate_action_sync"

    ticker = Column(String, ForeignKey("tickers.ticker"), primary_key=True)
    source_site = Column(String, primary_key=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    latest_announcement_date = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="PENDING")
    rows_seen = Column(Integer, nullable=False, default=0)
    last_error = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ValuationOutput(Base):
    __tablename__ = "valuation_outputs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, ForeignKey("tickers.ticker"))
    blended_fair_value_per_share = Column(Numeric)
    fair_value_bull = Column(Numeric, nullable=True)
    fair_value_bear = Column(Numeric, nullable=True)
    margin_of_safety = Column(Numeric, nullable=True)
    flags = Column(JSON, nullable=True)
    macro_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ValuationSensitivity(Base):
    __tablename__ = "valuation_sensitivities"
    
    ticker = Column(String, ForeignKey("tickers.ticker"), primary_key=True)
    assumption_version = Column(Integer, ForeignKey("valuation_outputs.id"), primary_key=True)
    driver_code = Column(String, primary_key=True)
    dFV_ddriver = Column(Numeric)
    base_driver_value = Column(Numeric)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class MacroSeries(Base):
    __tablename__ = 'macro_series'
    id = Column(Integer, primary_key=True, index=True)
    indicator_code = Column(String(50), index=True)
    date = Column(Date, index=True)
    value = Column(Numeric)
    source = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.utcnow, server_default=func.now())

    # Idempotent ingest: một (indicator_code, date) chỉ tồn tại một bản ghi.
    # Bắt buộc cho UPSERT (Luật vàng #6 — ghi DB idempotent, chạy lại không nhân đôi).
    __table_args__ = (
        UniqueConstraint('indicator_code', 'date', name='uq_macro_series_code_date'),
    )

class MacroRadar(Base):
    __tablename__ = "macro_radar"
    
    sector = Column(String, primary_key=True)
    indicator_code = Column(String, primary_key=True)
    frequency = Column(String)
    source = Column(String)
    warn_low = Column(Numeric)
    warn_high = Column(Numeric)
    mapped_driver = Column(String)
    # Độ nhạy driver theo biến vĩ mô: driver_delta = elasticity * (macro_now - baseline).
    # Mặc định 1.0 (map trực tiếp 1:1, vd TPCP_10Y→wacc). Cho GDP→revenue beta khác 1
    # theo ngành (thép 2.0, tech 1.2). Nguồn: config/elasticities.yaml.
    elasticity = Column(Numeric, default=1.0)

class DailySignal(Base):
    __tablename__ = "daily_signal"
    
    ticker = Column(String, ForeignKey("tickers.ticker"), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    close_price = Column(Numeric)
    fair_value_fast = Column(Numeric)
    upside = Column(Numeric)
    margin_of_safety = Column(Numeric)
    conviction_score = Column(Numeric)
    flags = Column(JSON)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Consensus(Base):
    __tablename__ = "consensus_history"

    ticker = Column(String, ForeignKey("tickers.ticker"), primary_key=True)
    broker = Column(String, primary_key=True)
    report_date = Column(Date, primary_key=True)
    target_price = Column(Numeric)
    rating = Column(String)
    source_url = Column(String)
    raw_quote = Column(String)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- D24: chất lượng dữ liệu đồng thuận ---
    # `broker` nằm trong PRIMARY KEY nên KHÔNG được sửa tại chỗ (luật vàng #6).
    # Tên chuẩn hoá ghi vào cột riêng; mọi reader dùng COALESCE(broker_canon, broker).
    broker_canon = Column(String, nullable=True)
    source_site = Column(String, nullable=True)   # 24HMONEY | SIMPLIZE | VNSTOCK | UNKNOWN
    # Dòng seed để test (scratch/run_consensus_collector.py) — phải loại khỏi
    # mọi thống kê, nếu không sẽ lẫn với dữ liệu cào thật mà không phân biệt được.
    is_synthetic = Column(Boolean, nullable=False, server_default="false", default=False)
    report_title = Column(String, nullable=True)
    currency_unit = Column(String, nullable=True, server_default="VND", default="VND")

class ConsensusSynthesis(Base):
    """Bản AI tổng hợp điểm chung/riêng/mấu chốt từ nhiều báo cáo CTCK cho 1 mã.

    Sinh bởi valuation/engine/consensus_synthesis.py (DeepSeek) dựa trên các
    tóm tắt luận điểm bóc từ 24hmoney + quan điểm mô hình nội bộ VN100.
    """
    __tablename__ = "consensus_synthesis"

    ticker = Column(String, ForeignKey("tickers.ticker"), primary_key=True)
    n_reports = Column(Integer)          # số báo cáo CTCK dùng để tổng hợp
    brokers = Column(String)             # danh sách CTCK, phân tách bằng dấu phẩy
    diem_chung = Column(JSON)            # list[str] — luận điểm đồng thuận
    diem_rieng = Column(JSON)            # list[str] — điểm khác biệt giữa các CTCK
    diem_mau_chot = Column(JSON)         # list[str] — nhận định sâu/điều dễ bỏ sót
    doi_chieu_noi_bo = Column(String)    # so sánh mô hình VN100 vs đồng thuận
    internal_fv = Column(Numeric)        # fair value mô hình nội bộ (VND/cp)
    consensus_median = Column(Numeric)   # median giá mục tiêu CTCK (VND/cp)
    model = Column(String)               # model LLM dùng (truy vết)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class ValuationRun(Base):
    __tablename__ = "valuation_runs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, ForeignKey("tickers.ticker"), nullable=False)
    analyst = Column(String, default="Analyst")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    engine = Column(String)  # 'dcf' hoặc 'bank'
    method = Column(String)  # 'FCFF + EV/EBITDA' hoặc 'Justified P/B'
    scenario = Column(String)  # 'Base', 'Bull', 'Bear'
    assumptions_json = Column(JSON)  # Lưu JSONB giả định định giá
    base_year_mode = Column(String)  # 'TTM' hoặc 'FY'
    wacc = Column(Numeric, nullable=True)
    terminal_g = Column(Numeric)
    target_price = Column(Numeric)
    current_price = Column(Numeric)
    upside = Column(Numeric)
    recommendation = Column(String)
    report_path = Column(String, nullable=True)
    notes = Column(String, nullable=True)



class CalibrationRunRow(Base):
    """Một lần chạy hiệu chuẩn toàn VN100 (DECISIONS.md D23).

    Lưu lịch sử để trả lời được "thay đổi vừa rồi làm tốt lên hay xấu đi?" — thứ
    sprint 2026-07 không có, nên bank overshoot từ -25% sang +10.7% mà không ai biết.
    `label` UNIQUE ⇒ chạy lại cùng label là ghi đè, không nhân đôi.
    """
    __tablename__ = "calibration_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String, nullable=False, unique=True)
    git_sha = Column(String)
    as_of = Column(Date, nullable=False)
    window_days = Column(Integer, default=180)
    dedup_mode = Column(String)          # 'latest_per_broker'
    weighting = Column(String)           # 'none' | 'halflife_90d'
    engine_config = Column(JSON)         # snapshot config ảnh hưởng định giá

    n_tickers = Column(Integer)
    n_valued = Column(Integer)
    n_with_consensus = Column(Integer)
    median_dev_vs_consensus = Column(Numeric)
    median_abs_dev_vs_consensus = Column(Numeric)
    share_in_band = Column(Numeric)
    median_dev_vs_price = Column(Numeric)
    n_below_price = Column(Integer)
    n_below_price_40 = Column(Integer)
    aggregates = Column(JSON)            # per-method / per-sector đầy đủ

    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CalibrationObservation(Base):
    """Kết quả đo của 1 mã trong 1 lần chạy hiệu chuẩn."""
    __tablename__ = "calibration_observations"

    run_id = Column(Integer, ForeignKey("calibration_runs.id", ondelete="CASCADE"), primary_key=True)
    ticker = Column(String, primary_key=True)
    method = Column(String)
    sector_group = Column(String)
    business_nature = Column(String)

    fair_value = Column(Numeric)
    market_price = Column(Numeric)
    consensus_median = Column(Numeric)
    consensus_weighted = Column(Numeric)
    n_brokers = Column(Integer)
    consensus_min = Column(Numeric)
    consensus_max = Column(Numeric)
    consensus_age_days = Column(Integer)

    dev_vs_consensus = Column(Numeric)   # (FV - median CTCK)/median
    dev_vs_price = Column(Numeric)       # (FV - thị giá)/thị giá — sanity độc lập CTCK
    band = Column(Numeric)
    band_status = Column(String)         # IN_BAND | OUT_HIGH | OUT_LOW | NO_CONSENSUS | ERROR
    governance_status = Column(String)   # OK | MISSING_JUSTIFICATION | KNOWN_DEFECT | ...
    registry_status = Column(String)
    registry_thesis = Column(String)

    flags = Column(JSON)
    error = Column(String)


class ConsensusReportText(Base):
    """Luận điểm CÔNG KHAI của báo cáo CTCK + kết quả bóc tách (D31).

    Tách khỏi `consensus_history` vì khác cardinality và khác nhịp refresh; giữ
    bảng số liệu đồng thuận sạch, không lẫn văn bản dài.

    NGUỒN: chỉ trang tóm tắt công khai trên 24hmoney và tiêu đề Simplize.
    KHÔNG tải PDF báo cáo gốc — giữ nguyên quyết định bản quyền của dự án
    (broker_24hmoney.py:74-78, AGENTS.md mục 5).
    """
    __tablename__ = "consensus_report_text"

    ticker = Column(String, primary_key=True)
    broker_canon = Column(String, primary_key=True)
    report_date = Column(Date, primary_key=True)
    source_site = Column(String, primary_key=True)   # 24HMONEY | SIMPLIZE

    detail_url = Column(String)
    title = Column(String)
    summary_text = Column(String)
    lang = Column(String, default="vi")

    extracted = Column(JSON)          # kết quả bóc tách tất định (regex)
    extract_version = Column(String)  # đổi version -> biết cần bóc lại
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
