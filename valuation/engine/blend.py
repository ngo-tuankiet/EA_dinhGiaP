"""Pha trộn giá trị nội tại và so sánh. Khuyến nghị do decision_engine.recommend quyết định."""
import math
from typing import Tuple


def blend_intrinsic_relative(
    intrinsic_fv: float,
    relative_fv: float,
    weight_intrinsic: float,
    current_price: float,
) -> Tuple[float, float]:
    """Trả (blended_fair_value, upside %). Chân NaN/âm → ValueError, không pha âm thầm."""
    for leg in (intrinsic_fv, relative_fv):
        if leg is None or not math.isfinite(leg) or leg < 0:
            raise ValueError(f"INVALID_VALUATION_LEG: {leg}")
    blended_fv = intrinsic_fv * weight_intrinsic + relative_fv * (1.0 - weight_intrinsic)
    upside = (blended_fv / current_price - 1.0) * 100.0 if current_price > 0 else 0.0
    return blended_fv, upside
