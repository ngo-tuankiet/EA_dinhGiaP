"""Lưu trữ chuỗi vĩ mô (macro_series) theo cơ chế idempotent.

Mọi scraper macro (SBV/GSO/commodity) PHẢI ghi DB qua hàm `upsert_macro_series`
ở đây, không tự `add_all`. Lý do:

- Luật vàng #6 (AGENTS.md): ghi DB idempotent — chạy lại pipeline 2 lần KHÔNG
  được nhân đôi dữ liệu. `MacroSeries` có unique constraint
  (indicator_code, date); ta dùng PostgreSQL ``ON CONFLICT DO UPDATE``.
- Luật vàng #5 (truy vết): chỉ nhận series_code nằm trong registry cấu hình,
  từ chối code lạ để tránh rác/typo làm hỏng mapping driver về sau.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from valuation.config import get_macro_series_registry
from valuation.db.models import MacroSeries
from valuation.db.upsert import dialect_insert


@dataclass(frozen=True)
class MacroPoint:
    """Một quan sát vĩ mô đã chuẩn hóa, sẵn sàng ghi DB."""

    indicator_code: str
    date: datetime.date
    value: float
    source: str


class UnknownIndicatorError(ValueError):
    """series_code không nằm trong registry cấu hình — từ chối ghi."""


def upsert_macro_series(
    points: Iterable[MacroPoint],
    db: Session,
    registry: dict | None = None,
) -> int:
    """Ghi/cập nhật các điểm vĩ mô một cách idempotent.

    Trả về số bản ghi đã ghi (insert + update). Gọi lại với cùng dữ liệu sẽ
    KHÔNG tạo dòng mới (chỉ cập nhật value/source nếu khác).

    Args:
        registry: tập series_code hợp lệ. Mặc định là registry production
            (config). Test truyền registry riêng để dùng code không đụng dữ
            liệu thật.

    Raises:
        UnknownIndicatorError: nếu có indicator_code ngoài registry.
    """
    if registry is None:
        registry = get_macro_series_registry()
    rows: list[dict] = []
    for p in points:
        if p.indicator_code not in registry:
            raise UnknownIndicatorError(
                f"indicator_code '{p.indicator_code}' không có trong "
                f"macro_series_registry. Thêm vào config/defaults.yaml trước."
            )
        rows.append(
            {
                "indicator_code": p.indicator_code,
                "date": p.date,
                "value": p.value,
                "source": p.source,
            }
        )

    if not rows:
        return 0

    stmt = dialect_insert(db, MacroSeries).values(rows)
    conflict_kwargs = (
        {"index_elements": ["indicator_code", "date"]}
        if db.get_bind().dialect.name == "sqlite"
        else {"constraint": "uq_macro_series_code_date"}
    )
    stmt = stmt.on_conflict_do_update(
        **conflict_kwargs,
        set_={"value": stmt.excluded.value, "source": stmt.excluded.source},
    )
    db.execute(stmt)
    db.commit()
    return len(rows)
