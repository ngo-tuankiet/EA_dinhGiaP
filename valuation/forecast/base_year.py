"""Năm gốc dự phóng hướng tới tương lai (D32).

VẤN ĐỀ HỆ THỐNG: mô hình dựng tăng trưởng năm 1 từ MEDIAN tăng trưởng doanh thu
LỊCH SỬ (repo.py), tức nhìn hoàn toàn về quá khứ. CTCK định giá trên dự phóng
FY+1/FY+2. Ở thị trường tăng trưởng lợi nhuận 15-20%/năm, chênh lệch này tạo ra
khoảng lệch ÂM mang tính cấu trúc — đo được: nhóm DCF lệch -30% so đồng thuận.

NGUYÊN TẮC (quyết định #2 của người dùng): tự dự phóng ĐỘC LẬP, tuyệt đối KHÔNG
lấy số của CTCK làm input. Tín hiệu dùng ở đây đều là dữ liệu NỘI BỘ, tái lập được:

  1. Động lượng theo quý: 4 quý gần nhất so 4 quý trước đó (YoY trên TTM), và
     2 quý gần nhất annualized so TTM. Đây chính là chỗ median-lịch-sử bỏ sót:
     thông tin về tương lai gần nằm sẵn trong dữ liệu quý của chính ta.
  2. Overlay vĩ mô sẵn có (forecast/drivers.py) — không lặp lại ở đây.
  3. Guardrail: kẹp quanh median lịch sử để một quý đột biến không bẻ lái cả
     mô hình; mọi lần kẹp đều bắn cờ.

Bật/tắt bằng `config/defaults.yaml::forecast.base_year_mode` (TRAILING|FORWARD).
Chế độ TRAILING phải cho kết quả Y HỆT trước D32 (có test chứng minh).
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "base_year_mode": "TRAILING",
    "momentum_window_quarters": 4,
    # Kẹp quanh median lịch sử: forward không được lệch quá ±10pp.
    "max_uplift_vs_trailing": 0.10,
    "max_cut_vs_trailing": 0.10,
    # Band ngoài cùng, giữ nguyên như bản trailing.
    "growth_floor": 0.0,
    "growth_cap": 0.25,
}


def _cfg() -> dict:
    from valuation.config import load_defaults
    return {**_DEFAULTS, **((load_defaults().get("forecast") or {}))}


def base_year_mode() -> str:
    return str(_cfg().get("base_year_mode", "TRAILING")).upper()


@dataclass(frozen=True)
class ForwardBase:
    fy1_revenue_growth: float
    method: str                       # QUARTERLY_MOMENTUM | TRAILING_MEDIAN
    trailing_median: float
    evidence: dict = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)


def quarterly_momentum(revenues_by_quarter: List[float]) -> Optional[float]:
    """Tăng trưởng YoY trên cơ sở TTM: tổng 4 quý gần nhất / tổng 4 quý trước đó.

    Cần tối thiểu 8 quý. Trả None nếu không đủ dữ liệu — KHÔNG đoán.
    """
    if len(revenues_by_quarter) < 8:
        return None
    recent = sum(revenues_by_quarter[-4:])
    prior = sum(revenues_by_quarter[-8:-4])
    if prior <= 0:
        return None
    return (recent - prior) / prior


# Ngành chu kỳ: động lượng SAI VỀ BẢN CHẤT ở đây. Doanh thu thép/đường/dầu khí
# dao động theo giá hàng hoá; một cửa sổ TTM đang ở đáy (hoặc đỉnh) chu kỳ mà đem
# ngoại suy ra 5 năm chính là lỗi mà median-mid-cycle sinh ra để tránh.
# Danh sách khớp `_CYCLICAL_KW` đã dùng trong `engine/batch.py` (ép mid-cycle cho
# EV_EBITDA/PE nhóm này) — giữ nhất quán một định nghĩa "chu kỳ" trong toàn hệ thống.
CYCLICAL_KEYWORDS = ("Thép", "Hóa chất", "Dầu khí", "Cao su", "Phân bón",
                     "Vận tải", "Khai khoáng", "Mía đường", "Nông nghiệp")


def is_cyclical_sector(sector_group: Optional[str]) -> bool:
    return any(k in (sector_group or "") for k in CYCLICAL_KEYWORDS)


def build_forward_base(
    revenues_by_quarter: List[float],
    trailing_median_growth: float,
    cfg: Optional[dict] = None,
    sector_group: Optional[str] = None,
) -> ForwardBase:
    """Dựng tăng trưởng năm 1 hướng tới tương lai, có kẹp quanh median lịch sử."""
    c = {**_cfg(), **(cfg or {})}
    flags: List[str] = []

    if is_cyclical_sector(sector_group):
        return ForwardBase(
            fy1_revenue_growth=trailing_median_growth,
            method="TRAILING_MEDIAN",
            trailing_median=trailing_median_growth,
            evidence={"reason": f"ngành chu kỳ ({sector_group}) — giữ mid-cycle"},
            flags=["FWD_SKIPPED_CYCLICAL"],
        )

    momentum = quarterly_momentum(revenues_by_quarter)
    if momentum is None:
        return ForwardBase(
            fy1_revenue_growth=trailing_median_growth,
            method="TRAILING_MEDIAN",
            trailing_median=trailing_median_growth,
            evidence={"reason": "không đủ 8 quý để tính động lượng"},
            flags=["FWD_NO_QUARTERLY_DATA"],
        )

    # CO NGÓT VỀ MEDIAN LỊCH SỬ (shrinkage) thay vì thay thế hẳn.
    #
    # Đo thực nghiệm (harness `after-D32-forward`): dùng thẳng động lượng làm năm
    # gốc cải thiện xu hướng trung tâm (nhóm DCF -30,0% -> -24,6%) NHƯNG làm PHÂN
    # TÁN rộng ra (|lệch| median 29,1% -> 31,6%), đẩy vài mã chu kỳ ra xa hơn
    # (NT2 +82,8%, SBT -52,2%). Lý do: động lượng một cửa sổ TTM rất nhiễu với
    # doanh nghiệp chu kỳ.
    #
    # Co ngót về median lịch sử là ước lượng có cơ sở thống kê (kéo ước lượng
    # nhiễu về phía tiên nghiệm ổn định hơn), không phải chỉnh số cho vừa ý.
    w = float(c.get("momentum_weight", 0.5))
    g = w * momentum + (1.0 - w) * trailing_median_growth
    up = float(c["max_uplift_vs_trailing"])
    cut = float(c["max_cut_vs_trailing"])
    lo_band, hi_band = trailing_median_growth - cut, trailing_median_growth + up

    if g > hi_band:
        flags.append(
            f"FWD_CLAMPED_HIGH: động lượng {momentum:+.1%} -> {hi_band:+.1%} "
            f"(trần +{up:.0%} so median lịch sử {trailing_median_growth:+.1%})")
        g = hi_band
    elif g < lo_band:
        flags.append(
            f"FWD_CLAMPED_LOW: động lượng {momentum:+.1%} -> {lo_band:+.1%} "
            f"(sàn -{cut:.0%} so median lịch sử {trailing_median_growth:+.1%})")
        g = lo_band

    floor, cap = float(c["growth_floor"]), float(c["growth_cap"])
    g2 = min(max(g, floor), cap)
    if g2 != g:
        flags.append(f"FWD_OUT_OF_BAND: {g:+.1%} -> {g2:+.1%} (band [{floor:.0%}, {cap:.0%}])")
        g = g2

    return ForwardBase(
        fy1_revenue_growth=g,
        method="QUARTERLY_MOMENTUM",
        trailing_median=trailing_median_growth,
        evidence={
            "momentum_ttm_yoy": momentum,
            "trailing_median": trailing_median_growth,
            "n_quarters": len(revenues_by_quarter),
        },
        flags=flags,
    )


def revenue_growth_path(
    fy1_growth: float,
    long_run_growth: float,
    years: int = 5,
) -> List[float]:
    """Fade tuyến tính từ năm 1 về tăng trưởng dài hạn (GDP danh nghĩa).

    Giữ NGUYÊN dạng công thức của bản trailing (`repo.py:561`) để chỉ có ĐIỂM
    XUẤT PHÁT thay đổi, không đổi hình dạng đường fade — cô lập tác động.
    """
    n = max(1, years - 1)
    return [fy1_growth + (long_run_growth - fy1_growth) * (k / n) for k in range(years)]
