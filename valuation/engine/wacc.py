"""Nguồn sự thật duy nhất cho công thức WACC.

Trước đây công thức WACC bị sao chép ở ≥5 nơi (models/dcf.py, engine/dcf.py,
sensitivity.py, route valuation.py, view input_assumptions.py) → khó bảo trì,
dễ lệch nhau. Module này gom về một hàm thuần.

    WACC = COE * E/(E+D) + Rd*(1-tax) * D/(E+D)

LƯU Ý về trọng số (chưa thống nhất toàn hệ thống — việc dọn tiếp):
- `models/dcf.py` dùng E = market cap (giá trị thị trường vốn CSH) — chuẩn
  Damodaran cho WACC hiện hành.
- route/view dùng E = book equity (giá trị sổ sách).
- `engine/dcf.py` dùng trọng số mục tiêu cố định (we, wd).
Hàm này KHÔNG quyết định E/D là gì — caller truyền vào. Nhờ vậy refactor không
làm đổi số (golden test giữ nguyên); việc thống nhất chọn loại trọng số là
quyết định tài chính riêng, làm sau.
"""
from __future__ import annotations

from typing import Optional

DEFAULT_DEBT_SPREAD = 0.03  # Rd = rf + spread khi không có chi phí nợ thực tế


def cost_of_debt_from_rf(rf: float, spread: float = DEFAULT_DEBT_SPREAD) -> float:
    """Chi phí nợ trước thuế = rf + spread (dùng khi thiếu Rd thực tế)."""
    return rf + spread


def compute_wacc(
    coe: float,
    cost_of_debt: float,
    equity_value: float,
    debt_value: float,
    tax_rate: float,
    floor: Optional[float] = None,
) -> float:
    """WACC theo trọng số giá trị (equity_value, debt_value) caller cung cấp.

    - Nếu equity_value + debt_value <= 0: trả về coe (không có cấu trúc vốn).
    - `floor`: ngưỡng sàn (vd rf + spread) để chặn WACC quá thấp; None = bỏ qua.
    """
    total = equity_value + debt_value
    if total <= 0:
        wacc = coe
    else:
        we = equity_value / total
        wd = debt_value / total
        wacc = coe * we + cost_of_debt * (1.0 - tax_rate) * wd
    if floor is not None:
        wacc = max(wacc, floor)
    return wacc
