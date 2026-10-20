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


def marginal_tax_rate(terminal_tax_rate: float | None, tax_rate: float) -> float:
    """Thuế dài hạn — NGUỒN DUY NHẤT cho NOPAT terminal (dcf.forecast_drivers) và lá chắn thuế nợ trong WACC:
    thuế terminal người dùng nhập nếu có; không thì sector_tax_rates.default khi dcf.terminal_tax_mode =
    marginal (Damodaran: ưu đãi có thời hạn không kéo dài vĩnh viễn), còn lại ('effective', mã có ưu đãi dài
    hạn theo luật) là thuế hiệu dụng tax_rate."""
    from valuation.config import load_defaults

    if terminal_tax_rate is not None:
        return float(terminal_tax_rate)
    cfg = load_defaults()
    if cfg["dcf"]["terminal_tax_mode"] == "marginal":
        return float(cfg["sector_tax_rates"]["default"])
    return float(tax_rate)


def wacc_tax_rate(assumptions) -> float:
    """Thuế cho lá chắn thuế nợ, theo dcf.wacc_tax_mode: 'marginal' (Damodaran: Rd·(1 − thuế BIÊN) vì lãi vay
    giảm thuế ở mức biên — cùng thuế với NOPAT terminal) | 'effective' (thuế hiệu dụng, cách cũ để quay lui)."""
    from valuation.config import load_defaults

    mode = load_defaults()["dcf"]["wacc_tax_mode"]
    if mode == "marginal":
        return marginal_tax_rate(getattr(assumptions, "terminal_tax_rate", None), assumptions.tax_rate)
    if mode == "effective":
        return assumptions.tax_rate
    raise ValueError(f"dcf.wacc_tax_mode không hợp lệ: {mode!r} (marginal|effective)")


def company_wacc(company) -> float:
    """WACC hiện hành của Company (Damodaran, trọng số thị trường): E = vốn hóa (thiếu giá → VCSH sổ sách gồm
    CĐKKS), D = nợ vay kỳ cuối, Rd = cost_of_debt hoặc rf + spread, thuế = wacc_tax_rate, sàn rf + spread;
    wacc_override thắng. Dùng chung DCF (FCFF), RNAV (dòng tiền dự án chưa trừ nợ) và báo cáo."""
    a = company.assumptions
    if a.wacc_override is not None:
        return a.wacc_override
    bs = company.historical_bs[-1]
    rf = a.risk_free_rate
    coe = a.cost_of_equity or (rf + a.beta * a.erp)
    cod = a.cost_of_debt if a.cost_of_debt is not None else cost_of_debt_from_rf(rf)
    mcap = company.shares_outstanding * 1e6 * company.current_price
    equity = mcap if mcap > 0 else bs.total_equity * 1e9
    debt = (bs.short_term_debt + bs.long_term_debt) * 1e9
    return compute_wacc(coe, cod, equity, debt, wacc_tax_rate(a), floor=rf + DEFAULT_DEBT_SPREAD)
