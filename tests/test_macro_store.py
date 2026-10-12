"""Test idempotency & validate cho macro_store.

QUAN TRỌNG: test chạy trên DB thật nên TUYỆT ĐỐI không dùng series_code
production (sẽ xóa nhầm dữ liệu thật). Dùng code test ``ZZ_TEST_*`` + registry
override; chỉ dọn đúng các code này.
"""
import datetime

import pytest

from valuation.db.models import MacroSeries
from valuation.db.session import SessionLocalWrite
from valuation.ingest.macro_store import (
    MacroPoint,
    UnknownIndicatorError,
    upsert_macro_series,
)

TEST_CODE = "ZZ_TEST_RATE"
TEST_REGISTRY = {TEST_CODE: {"unit": "decimal_rate", "source": "test"}}
D = datetime.date(2025, 1, 15)


def _upsert(points, db):
    return upsert_macro_series(points, db, registry=TEST_REGISTRY)


@pytest.fixture
def db():
    session = SessionLocalWrite()
    session.query(MacroSeries).filter(
        MacroSeries.indicator_code.like("ZZ_TEST_%")
    ).delete(synchronize_session=False)
    session.commit()
    yield session
    session.query(MacroSeries).filter(
        MacroSeries.indicator_code.like("ZZ_TEST_%")
    ).delete(synchronize_session=False)
    session.commit()
    session.close()


def _count(db) -> int:
    return db.query(MacroSeries).filter(MacroSeries.indicator_code == TEST_CODE).count()


def test_upsert_is_idempotent(db):
    """Chạy 2 lần cùng dữ liệu KHÔNG nhân đôi (Luật vàng #6)."""
    points = [MacroPoint(TEST_CODE, D, 0.032, "test")]
    _upsert(points, db)
    _upsert(points, db)
    assert _count(db) == 1


def test_upsert_updates_value_on_conflict(db):
    """Cùng (code, date) nhưng value mới → cập nhật, không thêm dòng."""
    _upsert([MacroPoint(TEST_CODE, D, 0.030, "test")], db)
    _upsert([MacroPoint(TEST_CODE, D, 0.035, "test2")], db)
    assert _count(db) == 1
    row = (
        db.query(MacroSeries)
        .filter(MacroSeries.indicator_code == TEST_CODE, MacroSeries.date == D)
        .one()
    )
    assert float(row.value) == pytest.approx(0.035)
    assert row.source == "test2"


def test_distinct_dates_create_distinct_rows(db):
    _upsert(
        [
            MacroPoint(TEST_CODE, D, 0.030, "test"),
            MacroPoint(TEST_CODE, datetime.date(2025, 1, 16), 0.031, "test"),
        ],
        db,
    )
    assert _count(db) == 2


def test_reject_unknown_indicator(db):
    """series_code ngoài registry bị từ chối (Luật vàng #5)."""
    with pytest.raises(UnknownIndicatorError):
        _upsert([MacroPoint("ZZ_TEST_UNKNOWN_XYZ", D, 1.0, "x")], db)


def test_real_registry_has_core_series():
    """Registry production phải có các series lõi cho WACC/driver."""
    from valuation.config import get_macro_series_registry

    reg = get_macro_series_registry()
    for code in ("TPCP_10Y", "USDVND", "STEEL_HRC", "CRUDE_OIL"):
        assert code in reg


def test_empty_input_noop(db):
    assert _upsert([], db) == 0
