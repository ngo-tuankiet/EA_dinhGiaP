"""Test điều chỉnh Blume cho beta — chống thiên lệch ước lượng (NAB beta 0.59)."""
import pytest
from valuation.engine.ttm_helper import _blume_adjust


def test_blume_formula():
    # 0.67*raw + 0.33*1.0
    assert _blume_adjust(1.0) == pytest.approx(1.0)          # beta 1.0 không đổi
    assert _blume_adjust(0.593) == pytest.approx(0.67*0.593 + 0.33)  # NAB
    assert _blume_adjust(1.5) == pytest.approx(0.67*1.5 + 0.33)


def test_blume_pulls_extremes_toward_one():
    """Beta cực thấp/cao bị kéo về gần 1; beta gần 1 gần như giữ nguyên."""
    assert _blume_adjust(0.5) > 0.5      # kéo lên
    assert _blume_adjust(1.4) < 1.4      # kéo xuống
    assert abs(_blume_adjust(1.05) - 1.05) < abs(_blume_adjust(0.5) - 0.5)


def test_blume_clamped_range():
    assert _blume_adjust(-2.0) >= 0.6
    assert _blume_adjust(5.0) <= 1.5
