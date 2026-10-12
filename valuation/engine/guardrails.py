"""Cờ cảnh báo cho kết quả định giá bất thường (D26).

Triết lý: đây là CỜ, KHÔNG PHẢI CLAMP. Mô hình có quyền bất đồng với thị trường —
đó chính là lý do ta định giá độc lập. Nhưng một con số thấp hơn thị giá 92%
(VIC) hay ngụ ý P/B 0,5x cho một công ty thị trường trả 1,5x thì KHÔNG ĐƯỢC PHÉP
rời engine trong im lặng: hoặc ta có luận điểm giải thích, hoặc đó là lỗi.

Kẹp giá trị lại sẽ giấu mất tín hiệu (đó chính là sai lầm của
`pb_relative.py: max(0.3, min(pb, 4.0))` — bóp mọi kết quả rác về 0,3x rồi trình
bày như một định giá bình thường).
"""
from __future__ import annotations

from typing import List, Optional

from valuation.config import load_defaults

_DEFAULTS = {
    # FV thấp hơn thị giá quá mức này ⇒ nghi lỗi mô hình (không phải "thận trọng").
    "fv_below_price_alarm": 0.40,
    # FV cao hơn thị giá quá mức này ⇒ nghi giả định tăng trưởng phi thực tế.
    "fv_above_price_alarm": 1.00,
    # P/B mục tiêu so với P/B thị trường: lệch quá tỷ lệ này thì phải giải thích.
    "pb_vs_market_max_ratio": 2.0,
    "pb_vs_market_min_ratio": 0.5,
}


def _cfg() -> dict:
    return {**_DEFAULTS, **(load_defaults().get("guardrails") or {})}


def check_fv_vs_price(fv: Optional[float], price: Optional[float]) -> List[str]:
    """So giá trị hợp lý với thị giá — phép thử ĐỘC LẬP với đồng thuận CTCK.

    Hữu ích ngay cả với mã không CTCK nào theo dõi.
    """
    flags: List[str] = []
    if not fv or not price or price <= 0 or fv <= 0:
        return flags
    cfg = _cfg()
    dev = (fv - price) / price
    if dev <= -float(cfg["fv_below_price_alarm"]):
        flags.append(f"FV_FAR_BELOW_PRICE: FV thấp hơn thị giá {abs(dev):.0%}")
    elif dev >= float(cfg["fv_above_price_alarm"]):
        flags.append(f"FV_FAR_ABOVE_PRICE: FV cao hơn thị giá {dev:.0%}")
    return flags


def check_implied_pb(
    justified_pb: Optional[float],
    market_pb: Optional[float],
    label: str = "PB",
) -> List[str]:
    """So P/B mục tiêu của mô hình với P/B thị trường đang trả.

    Không phải để bắt mô hình khớp thị trường, mà để buộc phải có luận điểm khi
    lệch xa: thị trường trả 1,5x mà mô hình nói 0,5x là một tuyên bố mạnh
    ("công ty này huỷ hoại giá trị"), cần nói rõ chứ không nói thầm.
    """
    flags: List[str] = []
    if not justified_pb or not market_pb or market_pb <= 0:
        return flags
    cfg = _cfg()
    ratio = justified_pb / market_pb
    if ratio >= float(cfg["pb_vs_market_max_ratio"]):
        flags.append(
            f"{label}_FAR_ABOVE_MARKET: P/B mục tiêu {justified_pb:.2f}x "
            f"= {ratio:.1f}× P/B thị trường {market_pb:.2f}x"
        )
    elif ratio <= float(cfg["pb_vs_market_min_ratio"]):
        flags.append(
            f"{label}_FAR_BELOW_MARKET: P/B mục tiêu {justified_pb:.2f}x "
            f"chỉ bằng {ratio:.0%} P/B thị trường {market_pb:.2f}x"
        )
    return flags


def market_pb(price: Optional[float], equity_vnd: Optional[float],
              shares: Optional[float]) -> Optional[float]:
    """P/B thị trường = thị giá / (VCSH / số cp). Đơn vị phải cùng hệ (VND, cp)."""
    if not price or not equity_vnd or not shares or shares <= 0 or equity_vnd <= 0:
        return None
    bvps = equity_vnd / shares
    return price / bvps if bvps > 0 else None
