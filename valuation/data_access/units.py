"""
Units utility — Chuyển đổi và chuẩn hóa đơn vị tiền tệ.
"""
from typing import Union, List, Dict, Any

BILLION = 1_000_000_000.0

def to_billion_vnd(val: Union[float, int, None]) -> float:
    """Đổi VND thô (Đồng) sang Tỷ đồng (billion VND)."""
    if val is None:
        return 0.0
    return float(val) / BILLION

def from_billion_vnd(val: Union[float, int, None]) -> float:
    """Đổi Tỷ đồng (billion VND) sang VND thô (Đồng)."""
    if val is None:
        return 0.0
    return float(val) * BILLION

def clean_value(val: Any) -> float:
    """Lọc sạch giá trị số, trả về float, tránh None."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
