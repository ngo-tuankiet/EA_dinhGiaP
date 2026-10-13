"""Ảnh biểu đồ tĩnh cho PDF/Word: Plotly ≥6 bỏ tham số write_image(engine=...) → mọi ảnh từng lỗi (D59)."""

import pytest

pytest.importorskip("kaleido")

from valuation.report.charts import generate_football_field_chart  # noqa: E402


def test_football_field_png_is_written(tmp_path):
    out = tmp_path / "football.png"
    generate_football_field_chart(100_000, 80_000, 110_000, 90_000, str(out))
    assert out.exists() and out.stat().st_size > 1_000
