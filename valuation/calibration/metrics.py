"""Chỉ số hiệu chuẩn: lệch từng mã + tổng hợp theo nhóm phương pháp/ngành.

Hai họ chỉ số, cố tình tách biệt:

1. **Lệch vs đồng thuận CTCK** (`dev_vs_consensus`) — thước đo chính, nhưng phụ
   thuộc CTCK có phủ mã đó không và CTCK có đúng không.
2. **Lệch vs THỊ GIÁ** (`dev_vs_price`) — thước đo sanity ĐỘC LẬP với CTCK. Một
   FV thấp hơn chính thị giá 40%+ gần như luôn là lỗi mô hình, bất kể CTCK nghĩ gì.
   Chính chỉ số này tóm được VIC (-92%), HCM (-73%), EIB (-72%) — những mã mà nếu
   chỉ nhìn lệch-vs-CTCK sẽ dễ bị bỏ qua thành "quan điểm thận trọng".

Không có magic number: mọi ngưỡng truyền vào từ config (AGENTS.md luật vàng #5).
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

# Band mặc định khi registry không quy định riêng. ±20% = quyết định #1 của user.
BAND_DEFAULT = 0.20
# FV thấp hơn thị giá quá mức này ⇒ nghi lỗi mô hình, đếm riêng để canh hồi quy.
BELOW_PRICE_ALARM = 0.40

# Trạng thái band
IN_BAND = "IN_BAND"
OUT_HIGH = "OUT_HIGH"
OUT_LOW = "OUT_LOW"
NO_CONSENSUS = "NO_CONSENSUS"
ERROR = "ERROR"


@dataclass(frozen=True)
class Observation:
    """Kết quả đo của 1 mã trong 1 lần chạy hiệu chuẩn."""

    ticker: str
    method: Optional[str] = None
    sector_group: Optional[str] = None
    business_nature: Optional[str] = None

    fair_value: Optional[float] = None
    market_price: Optional[float] = None

    consensus_median: Optional[float] = None
    consensus_weighted: Optional[float] = None
    n_brokers: int = 0
    consensus_min: Optional[float] = None
    consensus_max: Optional[float] = None
    consensus_age_days: Optional[int] = None

    dev_vs_consensus: Optional[float] = None
    dev_vs_price: Optional[float] = None

    band: float = BAND_DEFAULT
    band_status: str = NO_CONSENSUS
    governance_status: str = "OK"
    registry_status: Optional[str] = None
    registry_thesis: Optional[str] = None

    flags: list[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def below_price_alarm(self) -> bool:
        return self.dev_vs_price is not None and self.dev_vs_price <= -BELOW_PRICE_ALARM


def classify_band(dev: Optional[float], band: float) -> str:
    """Phân loại độ lệch so với band. Đúng bằng biên (±band) vẫn tính IN_BAND."""
    if dev is None:
        return NO_CONSENSUS
    if dev > band:
        return OUT_HIGH
    if dev < -band:
        return OUT_LOW
    return IN_BAND


def _safe_ratio(value: Optional[float], base: Optional[float]) -> Optional[float]:
    if value is None or base is None or base == 0:
        return None
    return (value - base) / base


def build_observation(
    ticker: str,
    valuation: dict[str, Any],
    view,
    band: float = BAND_DEFAULT,
) -> Observation:
    """Ghép 1 kết quả `batch.value_ticker` với 1 `ConsensusView` thành Observation."""
    err = valuation.get("error")
    fv = valuation.get("fair_value")
    price = valuation.get("price")
    fv = float(fv) if fv else None
    price = float(price) if price else None

    median = view.median if view is not None else None
    dev_consensus = _safe_ratio(fv, median)
    dev_price = _safe_ratio(fv, price)

    if err:
        band_status = ERROR
    else:
        band_status = classify_band(dev_consensus, band)

    return Observation(
        ticker=ticker,
        method=valuation.get("method"),
        sector_group=valuation.get("group"),
        business_nature=valuation.get("business_nature"),
        fair_value=fv,
        market_price=price,
        consensus_median=median,
        consensus_weighted=(view.weighted_median if view is not None else None),
        n_brokers=(view.count if view is not None else 0),
        consensus_min=(view.min if view is not None else None),
        consensus_max=(view.max if view is not None else None),
        consensus_age_days=(view.newest_age_days if view is not None else None),
        dev_vs_consensus=dev_consensus,
        dev_vs_price=dev_price,
        band=band,
        band_status=band_status,
        flags=list(valuation.get("flags") or []),
        error=err,
    )


def _group_stats(obs: Sequence[Observation]) -> dict[str, Any]:
    """Thống kê cho một nhóm quan sát bất kỳ (toàn cục hoặc theo method/ngành)."""
    devs = [o.dev_vs_consensus for o in obs if o.dev_vs_consensus is not None]
    devs_price = [o.dev_vs_price for o in obs if o.dev_vs_price is not None]
    banded = [o for o in obs if o.band_status in (IN_BAND, OUT_HIGH, OUT_LOW)]

    out: dict[str, Any] = {
        "n": len(obs),
        "n_with_consensus": len(devs),
        "n_errors": sum(1 for o in obs if o.error),
        "median_dev": statistics.median(devs) if devs else None,
        "median_abs_dev": statistics.median([abs(d) for d in devs]) if devs else None,
        "mean_dev": (sum(devs) / len(devs)) if devs else None,
        "share_in_band": (
            sum(1 for o in banded if o.band_status == IN_BAND) / len(banded)
            if banded else None
        ),
        "n_in_band": sum(1 for o in obs if o.band_status == IN_BAND),
        "n_out_high": sum(1 for o in obs if o.band_status == OUT_HIGH),
        "n_out_low": sum(1 for o in obs if o.band_status == OUT_LOW),
        "median_dev_vs_price": statistics.median(devs_price) if devs_price else None,
        "n_below_price": sum(1 for d in devs_price if d < 0),
        "n_below_price_40": sum(1 for d in devs_price if d <= -BELOW_PRICE_ALARM),
    }
    if len(devs) >= 4:
        qs = statistics.quantiles(devs, n=4)
        out["p25_dev"], out["p75_dev"] = qs[0], qs[2]
    else:
        out["p25_dev"] = out["p75_dev"] = None
    return out


def aggregate(obs: Sequence[Observation]) -> dict[str, Any]:
    """Tổng hợp: toàn cục + theo nhóm phương pháp + theo ngành.

    `by_method` là chiều quan trọng nhất — sự cố tháng 7/2026 là một nhóm phương
    pháp (RI_PB) dịch 35pp trong khi tổng thể trông có vẻ khá hơn.
    """
    by_method: dict[str, list[Observation]] = defaultdict(list)
    by_sector: dict[str, list[Observation]] = defaultdict(list)
    for o in obs:
        by_method[o.method or "UNKNOWN"].append(o)
        by_sector[o.sector_group or "UNKNOWN"].append(o)

    return {
        "overall": _group_stats(obs),
        "by_method": {k: _group_stats(v) for k, v in sorted(by_method.items())},
        "by_sector": {k: _group_stats(v) for k, v in sorted(by_sector.items())},
    }
