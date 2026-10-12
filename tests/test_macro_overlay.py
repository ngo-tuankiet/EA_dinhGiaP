"""Test Macro Bridge overlay (forecast/drivers.py)."""
import datetime

import pytest

from valuation.db.models import MacroSeries
from valuation.db.session import SessionLocalWrite
from valuation.forecast.drivers import (
    MacroContext,
    classify_sector,
    overlay_revenue_growth,
)


def test_classify_sector():
    assert classify_sector("Banks") == "banks"
    assert classify_sector("Ngân hàng TMCP") == "banks"
    assert classify_sector("Tài nguyên Cơ bản (thép)") == "steel"
    assert classify_sector("Bán lẻ") == "retail"
    assert classify_sector("Công nghệ thông tin") == "technology"
    assert classify_sector(None) == "default"
    assert classify_sector("Ngành lạ") == "default"


def test_overlay_noop_when_no_delta():
    """Không có biến động macro -> driver giữ nguyên (an toàn bật/tắt)."""
    ctx = MacroContext(deltas={"GDP_YOY": 0.0})
    base = [0.10, 0.09, 0.08]
    assert overlay_revenue_growth(base, "steel", ctx) == base


def test_overlay_revenue_growth_steel_cyclical():
    """Thép beta=2.0: GDP +1% -> revenue growth +2% mỗi năm."""
    ctx = MacroContext(deltas={"GDP_YOY": 0.01})
    base = [0.10, 0.09, 0.08]
    out = overlay_revenue_growth(base, "Thép HPG", ctx)
    assert out == pytest.approx([0.12, 0.11, 0.10])


def test_overlay_revenue_growth_utilities_defensive():
    """Tiện ích beta=0.5: ít nhạy hơn."""
    ctx = MacroContext(deltas={"GDP_YOY": 0.02})
    out = overlay_revenue_growth([0.05], "Điện POW", ctx)
    assert out == pytest.approx([0.05 + 0.5 * 0.02])


def test_overlay_revenue_growth_banks_excluded():
    """Ngân hàng không dùng GDP overlay cho doanh thu (beta=0)."""
    ctx = MacroContext(deltas={"GDP_YOY": 0.05})
    base = [0.15, 0.14]
    assert overlay_revenue_growth(base, "Banks", ctx) == base


def test_macro_context_from_db():
    """delta = now - baseline, đọc từ macro_series thật (code ZZ_TEST)."""
    s = SessionLocalWrite()
    s.query(MacroSeries).filter(MacroSeries.indicator_code == "ZZ_TEST_GDP").delete(
        synchronize_session=False
    )
    s.commit()
    try:
        s.add_all(
            [
                MacroSeries(
                    indicator_code="ZZ_TEST_GDP",
                    date=datetime.date(2025, 1, 1),
                    value=0.06,
                    source="test",
                ),
                MacroSeries(
                    indicator_code="ZZ_TEST_GDP",
                    date=datetime.date(2025, 6, 1),
                    value=0.065,
                    source="test",
                ),
            ]
        )
        s.commit()
        ctx = MacroContext.from_db(
            s, baseline_date=datetime.date(2025, 1, 31), codes=["ZZ_TEST_GDP"]
        )
        assert ctx.delta("ZZ_TEST_GDP") == pytest.approx(0.005)
    finally:
        s.query(MacroSeries).filter(
            MacroSeries.indicator_code == "ZZ_TEST_GDP"
        ).delete(synchronize_session=False)
        s.commit()
        s.close()


def test_macro_context_from_db_momentum():
    """delta = mới nhất - giá trị ~1 năm trước (momentum 12 tháng)."""
    s = SessionLocalWrite()
    s.query(MacroSeries).filter(MacroSeries.indicator_code == "ZZ_TEST_GDP").delete(
        synchronize_session=False
    )
    s.commit()
    try:
        s.add_all(
            [
                MacroSeries(  # ~1.5 năm trước -> là baseline (<= now - 365d)
                    indicator_code="ZZ_TEST_GDP",
                    date=datetime.date(2024, 6, 1),
                    value=0.0755,
                    source="test",
                ),
                MacroSeries(  # trong vòng 1 năm -> KHÔNG được chọn làm baseline
                    indicator_code="ZZ_TEST_GDP",
                    date=datetime.date(2025, 9, 1),
                    value=0.0823,
                    source="test",
                ),
                MacroSeries(  # mới nhất = now
                    indicator_code="ZZ_TEST_GDP",
                    date=datetime.date(2025, 12, 31),
                    value=0.0846,
                    source="test",
                ),
            ]
        )
        s.commit()
        ctx = MacroContext.from_db_momentum(s, codes=["ZZ_TEST_GDP"], lookback_days=365)
        # now=0.0846 (2025-12-31), baseline = bản ghi <= 2024-12-31 = 0.0755
        assert ctx.delta("ZZ_TEST_GDP") == pytest.approx(0.0091)
    finally:
        s.query(MacroSeries).filter(
            MacroSeries.indicator_code == "ZZ_TEST_GDP"
        ).delete(synchronize_session=False)
        s.commit()
        s.close()
