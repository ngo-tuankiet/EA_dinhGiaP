"""Macro Bridge — neo driver dự phóng vào biến vĩ mô (overlay top-down).

Base case driver lấy từ lịch sử doanh nghiệp (repo.py). Module này ĐIỀU CHỈNH
driver quanh base theo độ lệch vĩ mô:

    adjusted = base + elasticity * (macro_now - macro_baseline)

Đặc tính an toàn: nếu không có dữ liệu macro (delta = 0) hoặc elasticity = 0,
overlay là no-op → driver giữ nguyên base. Nhờ vậy bật/tắt overlay không phá
hành vi cũ.

Hệ số elasticity đọc từ config/elasticities.yaml (tunable, có nguồn).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from valuation.config import load_elasticities
from valuation.db.models import MacroSeries

# Map sector string (tự do, tiếng Việt/Anh) -> khóa chuẩn trong elasticities.yaml
_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "banks": ["bank", "ngân hàng"],
    "steel": ["steel", "thép", "metal", "material", "tài nguyên"],
    "retail": ["retail", "bán lẻ", "wholesale"],
    "technology": ["tech", "information", "software", "công nghệ"],
    "utilities": ["util", "electric", "power", "gas", "điện", "nước", "tiện ích"],
    "real_estate": ["real", "estate", "property", "bất động sản"],
    "consumer": ["consumer", "food", "beverage", "tiêu dùng", "thực phẩm"],
}


def classify_sector(sector_str: Optional[str]) -> str:
    """Đưa chuỗi ngành tự do về khóa chuẩn; mặc định 'default'."""
    if not sector_str:
        return "default"
    s = sector_str.lower()
    for key, kws in _SECTOR_KEYWORDS.items():
        if any(kw in s for kw in kws):
            return key
    return "default"


@dataclass(frozen=True)
class MacroContext:
    """Độ lệch vĩ mô (now - baseline) theo series_code."""

    deltas: dict[str, float]

    def delta(self, code: str) -> float:
        return self.deltas.get(code, 0.0)

    @classmethod
    def from_db(
        cls,
        db: Session,
        baseline_date: datetime.date,
        codes: Optional[list[str]] = None,
    ) -> "MacroContext":
        """Dựng context: delta = (giá trị mới nhất) - (giá trị tại baseline_date).

        Với mỗi code: 'now' = bản ghi gần nhất; 'baseline' = bản ghi gần nhất
        KHÔNG muộn hơn baseline_date. Thiếu một trong hai → delta = 0 (no-op).
        """
        codes = codes or ["GDP_YOY", "CREDIT_GROWTH", "STEEL_HRC", "CPI_YOY"]
        deltas: dict[str, float] = {}
        for code in codes:
            now_row = (
                db.query(MacroSeries)
                .filter(MacroSeries.indicator_code == code)
                .order_by(desc(MacroSeries.date))
                .first()
            )
            base_row = (
                db.query(MacroSeries)
                .filter(
                    MacroSeries.indicator_code == code,
                    MacroSeries.date <= baseline_date,
                )
                .order_by(desc(MacroSeries.date))
                .first()
            )
            if now_row and base_row and now_row.value is not None and base_row.value is not None:
                deltas[code] = float(now_row.value) - float(base_row.value)
            else:
                deltas[code] = 0.0
        return cls(deltas=deltas)

    @classmethod
    def from_db_momentum(
        cls,
        db: Session,
        codes: Optional[list[str]] = None,
        lookback_days: int = 365,
    ) -> "MacroContext":
        """Dựng context theo momentum: delta = (mới nhất) - (~lookback_days trước).

        Robust khi dữ liệu vĩ mô trễ/sớm hơn năm tài chính: luôn so giá trị mới
        nhất với giá trị một năm trước đó. Thiếu một trong hai mốc → delta = 0
        (giữ tính an toàn no-op).
        """
        codes = codes or ["GDP_YOY", "CREDIT_GROWTH", "STEEL_HRC", "CPI_YOY"]
        deltas: dict[str, float] = {}
        for code in codes:
            now_row = (
                db.query(MacroSeries)
                .filter(MacroSeries.indicator_code == code)
                .order_by(desc(MacroSeries.date))
                .first()
            )
            if not now_row or now_row.value is None:
                deltas[code] = 0.0
                continue
            cutoff = now_row.date - datetime.timedelta(days=lookback_days)
            base_row = (
                db.query(MacroSeries)
                .filter(
                    MacroSeries.indicator_code == code,
                    MacroSeries.date <= cutoff,
                )
                .order_by(desc(MacroSeries.date))
                .first()
            )
            if base_row and base_row.value is not None:
                deltas[code] = float(now_row.value) - float(base_row.value)
            else:
                deltas[code] = 0.0
        return cls(deltas=deltas)


def _elasticity(group: str, sector_key: str) -> float:
    """Lấy hệ số elasticity theo nhóm config + ngành; fallback 'default' rồi 0."""
    cfg = load_elasticities().get("macro_overlay", {})
    if not cfg.get("enabled", True):
        return 0.0
    table = cfg.get(group, {})
    if sector_key in table:
        return float(table[sector_key])
    return float(table.get("default", 0.0))


def overlay_revenue_growth(
    base_growth: list[float], sector_str: Optional[str], ctx: MacroContext
) -> list[float]:
    """Điều chỉnh revenue_growth theo độ lệch GDP_YOY."""
    sector_key = classify_sector(sector_str)
    beta = _elasticity("revenue_growth_to_gdp", sector_key)
    adj = beta * ctx.delta("GDP_YOY")
    if adj == 0.0:
        return list(base_growth)
    return [g + adj for g in base_growth]

