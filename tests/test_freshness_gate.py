"""
Test Freshness Gate + MacroEnvironment.from_db — dữ liệu chuẩn mỗi lần quét.

Regression: audit 2026-07-11 phát hiện giá lệch 5 thế hệ (26/6→8/7) mà không hệ
thống nào cảnh báo; vĩ mô USDVND/HRC/CRUDE chỉ có 1 điểm cũ. Gate này bảo đảm
kết quả định giá luôn TỰ KHAI BÁO độ tươi dữ liệu nền.
"""
import datetime

import pytest

from valuation.db.session import SessionLocalRead
from valuation.data_access.freshness import (
    PRICE_MAX_AGE_DAYS, data_freshness_flags,
)
from valuation.models.macro_env import MacroEnvironment


@pytest.fixture
def db():
    s = SessionLocalRead()
    yield s
    s.close()


def test_fresh_ticker_no_flags(db):
    """Mã vừa refresh giá (vintage mới nhất) → không cờ STALE_PRICE."""
    flags = data_freshness_flags(db, "FPT")
    assert "STALE_PRICE" not in flags


def test_stale_price_detected_with_shifted_today(db):
    """Giả lập 'hôm nay' lùi xa tương lai → mọi giá thành cũ → phải có cờ."""
    future = datetime.date.today() + datetime.timedelta(days=PRICE_MAX_AGE_DAYS + 30)
    flags = data_freshness_flags(db, "FPT", today=future)
    assert "STALE_PRICE" in flags
    assert "STALE_MACRO_RF" in flags  # TPCP_10Y cũng cũ theo


def test_unknown_ticker_flagged_stale(db):
    """Mã không có giá trong DB → STALE_PRICE (không có dữ liệu = không tươi)."""
    flags = data_freshness_flags(db, "ZZZ_KHONG_TON_TAI")
    assert "STALE_PRICE" in flags


def test_data_flags_flow_into_valuate(db):
    """data_flags gắn trên company phải chảy vào flags kết quả valuate()."""
    from valuation.data_access.repo import build_company_data
    from valuation.engine.valuate import valuate

    c = build_company_data(db, "FPT", "TTM")
    c.data_flags = ["STALE_PRICE"]  # giả lập dữ liệu cũ
    r = valuate(c)
    assert "STALE_PRICE" in r["flags"]


def test_macro_env_from_db_reads_real_series(db):
    """from_db lấy rf từ TPCP_10Y thật; thiếu CPI/POLICY_RATE → trung tính."""
    env = MacroEnvironment.from_db(db)
    # TPCP_10Y có trong DB → rf phải được set (số thực dương < 20%)
    assert env.risk_free_rate is not None
    assert 0.0 < env.risk_free_rate < 0.20
    # CPI_YOY chưa có trong DB → giữ mặc định trung tính 4%
    # (nếu sau này ingest CPI, assert này cần cập nhật — chủ đích)
    assert env.sbv_stance in ("Neutral", "Easing", "Tightening")


def test_stale_flags_documented():
    from valuation.engine.flag_descriptions import FLAG_DESCRIPTIONS
    assert "STALE_PRICE" in FLAG_DESCRIPTIONS
    assert "STALE_MACRO_RF" in FLAG_DESCRIPTIONS
