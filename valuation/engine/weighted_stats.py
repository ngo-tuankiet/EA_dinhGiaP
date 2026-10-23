"""Thống kê trọng số thuần (không phụ thuộc dữ liệu đồng thuận CTCK).

Tách riêng khỏi valuation.calibration.consensus_view vì module đó đọc bảng
consensus_history (dữ liệu đồng thuận CTCK), còn engine định giá KHÔNG được
import dữ liệu đó (quyết định #2, tests/test_forward_base.py). Hai hàm ở đây
là toán thuần túy trên số đưa vào tham số, dùng được ở cả hai phía.
"""

from __future__ import annotations

from collections.abc import Sequence


def weighted_median(values: Sequence[float], weights: Sequence[float]) -> float | None:
    """Trung vị có trọng số: giá trị đầu tiên mà tổng trọng số tích luỹ đạt >= 50%.

    Khi mọi trọng số bằng nhau và n lẻ, kết quả trùng median thường. Với n chẵn,
    hàm này trả phần tử "vượt mốc 50%" (không nội suy) — chọn cách này để kết quả
    luôn là một giá mục tiêu CÓ THẬT của một CTCK, không phải số trung bình nhân tạo.
    """
    pairs = [(v, w) for v, w in zip(values, weights) if w > 0]
    if not pairs:
        return None
    pairs.sort(key=lambda p: p[0])
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    acc = 0.0
    for value, w in pairs:
        acc += w
        if acc >= total / 2.0:
            return float(value)
    return float(pairs[-1][0])


def recency_weight(age_days: int, half_life_days: float | None) -> float:
    """Trọng số suy giảm theo chu kỳ bán rã. `half_life_days=None` → tắt (1.0)."""
    if half_life_days is None or half_life_days <= 0:
        return 1.0
    return 0.5 ** (max(0, age_days) / float(half_life_days))
