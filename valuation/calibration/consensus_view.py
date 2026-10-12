"""Nguồn đọc đồng thuận CTCK DUY NHẤT cho toàn hệ thống.

Trước file này có HAI đường đọc consensus cho cùng một mã, ra hai con số khác nhau
trên cùng một màn hình:
  - `consensus_helper.get_consensus_stats` — KHÔNG dedup: một CTCK ra 3 báo cáo
    trong 180 ngày được tính 3 phiếu vào median.
  - `report_data.build_consensus_comparison` — CÓ dedup (giữ báo cáo mới nhất mỗi
    CTCK) cho bảng chi tiết.
KPI "Median CTCK" và bảng bên dưới nó vì thế lệch nhau. Module này là nguồn chung
để cả hai cùng gọi.

Nguyên tắc:
- `count` là SỐ CTCK (sau dedup), không phải số báo cáo — "5 CTCK theo dõi" mới là
  thông tin nhà đầu tư cần, "5 báo cáo" có thể chỉ là 1 CTCK viết 5 lần.
- Chống lookahead (AGENTS.md luật vàng #3): chỉ lấy `report_date <= as_of`.
- Loại dòng `is_synthetic` (dữ liệu seed để test, xem GĐ1) khỏi mọi thống kê.
"""
from __future__ import annotations

import datetime
import statistics
from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from valuation.db.models import Consensus


def _quality_cfg() -> dict:
    """Đọc config/consensus_quality.yaml (D24). Thiếu file → dùng mặc định an toàn."""
    import yaml
    from valuation.config import PROJECT_ROOT
    path = PROJECT_ROOT / "config" / "consensus_quality.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_CFG = _quality_cfg()

# Cửa sổ mặc định: 180 ngày ~ 2 quý, đủ để gom báo cáo quanh 1-2 mùa BCTC mà
# không kéo theo luận điểm đã lỗi thời.
DEFAULT_WINDOW_DAYS = int(_CFG.get("window_days", 180))
# Báo cáo cũ hơn mốc này thì `ConsensusView.stale = True` (cảnh báo, không loại).
DEFAULT_STALE_AFTER_DAYS = int(_CFG.get("stale_after_days", 120))
# Chu kỳ bán rã trọng số độ mới; None = tắt weighting.
DEFAULT_HALF_LIFE_DAYS = _CFG.get("half_life_days", 90)
# Dưới ngưỡng này thì "đồng thuận" thực chất chỉ là ý kiến của 1 CTCK.
MIN_BROKERS_FOR_MEDIAN = int(_CFG.get("min_brokers_for_median", 2))


@dataclass(frozen=True)
class BrokerQuote:
    """Một khuyến nghị đã chuẩn hoá của một CTCK."""

    broker: str            # tên chuẩn hoá (broker_canon nếu có, không thì broker gốc)
    broker_raw: str        # tên gốc trong DB — giữ để truy vết
    source_site: Optional[str]
    report_date: datetime.date
    target_price: float
    rating: Optional[str]
    age_days: int
    weight: float          # trọng số theo độ mới; 1.0 khi tắt weighting


@dataclass(frozen=True)
class ConsensusView:
    """Ảnh chụp đồng thuận CTCK của 1 mã tại 1 thời điểm."""

    ticker: str
    as_of: datetime.date
    window_days: int
    quotes: tuple[BrokerQuote, ...]     # đã dedup: 1 dòng mới nhất mỗi CTCK
    median: Optional[float]
    weighted_median: Optional[float]
    mean: Optional[float]
    count: int                          # SỐ CTCK, không phải số báo cáo
    n_reports_raw: int                  # số báo cáo thô trước dedup
    min: Optional[float]
    max: Optional[float]
    newest_age_days: Optional[int]
    stale: bool

    @property
    def has_data(self) -> bool:
        return self.count > 0

    @property
    def thin(self) -> bool:
        """Quá ít CTCK để gọi là 'đồng thuận' — median chỉ là ý kiến đơn lẻ.

        Dùng để báo cáo ghi rõ "chỉ 1 CTCK theo dõi" thay vì trình bày như quan
        điểm thị trường, và để governance nới tay với mã mỏng dữ liệu.
        """
        return 0 < self.count < MIN_BROKERS_FOR_MEDIAN


def weighted_median(values: Sequence[float], weights: Sequence[float]) -> Optional[float]:
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


def recency_weight(age_days: int, half_life_days: Optional[float]) -> float:
    """Trọng số suy giảm theo chu kỳ bán rã. `half_life_days=None` → tắt (1.0)."""
    if half_life_days is None or half_life_days <= 0:
        return 1.0
    return 0.5 ** (max(0, age_days) / float(half_life_days))


def _has_column(db: Session, name: str) -> bool:
    """Cột GĐ1 (broker_canon/source_site/is_synthetic) có thể chưa migrate.

    Đọc từ metadata của engine thay vì giả định, để GĐ0 chạy được trên DB chưa
    nâng cấp và tự dùng cột mới ngay khi GĐ1 apply — không cần sửa code.
    """
    try:
        cols = {c["name"] for c in inspect(db.get_bind()).get_columns("consensus_history")}
    except Exception:
        return False
    return name in cols


def get_consensus_view(
    db: Session,
    ticker: str,
    as_of: Optional[datetime.date] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    dedup: bool = True,
    half_life_days: Optional[float] = None,
    include_synthetic: bool = False,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> ConsensusView:
    """Đọc đồng thuận CTCK cho 1 mã, đã dedup theo CTCK và chống lookahead.

    Args:
        as_of: mốc thời gian; chỉ nhận báo cáo <= mốc này. Mặc định hôm nay.
        dedup: True → mỗi CTCK chỉ tính 1 phiếu (báo cáo mới nhất).
        half_life_days: chu kỳ bán rã cho trọng số độ mới. None → không weighting.
        include_synthetic: True → gồm cả dòng seed test (chỉ dùng khi debug).
    """
    as_of = as_of or datetime.date.today()
    start = as_of - datetime.timedelta(days=window_days)

    q = db.query(Consensus).filter(
        Consensus.ticker == ticker,
        Consensus.report_date >= start,
        Consensus.report_date <= as_of,
        Consensus.target_price.isnot(None),
    )
    if not include_synthetic and _has_column(db, "is_synthetic"):
        q = q.filter(Consensus.is_synthetic.isnot(True))

    records = [r for r in q.all() if r.target_price is not None and float(r.target_price) > 0]
    n_reports_raw = len(records)

    has_canon = _has_column(db, "broker_canon")
    has_site = _has_column(db, "source_site")

    def _canon(rec) -> str:
        if has_canon:
            val = getattr(rec, "broker_canon", None)
            if val:
                return str(val)
        return str(rec.broker)

    # Mới nhất trước; khi trùng ngày thì giá mục tiêu cao hơn thắng để kết quả
    # ổn định (deterministic) giữa các lần chạy, không phụ thuộc thứ tự DB trả về.
    records.sort(key=lambda r: (r.report_date, float(r.target_price)), reverse=True)

    seen: set[str] = set()
    quotes: list[BrokerQuote] = []
    for rec in records:
        canon = _canon(rec)
        if dedup and canon in seen:
            continue
        seen.add(canon)
        age = (as_of - rec.report_date).days
        quotes.append(
            BrokerQuote(
                broker=canon,
                broker_raw=str(rec.broker),
                source_site=(getattr(rec, "source_site", None) if has_site else None),
                report_date=rec.report_date,
                target_price=float(rec.target_price),
                rating=rec.rating,
                age_days=age,
                weight=recency_weight(age, half_life_days),
            )
        )

    quotes.sort(key=lambda q_: q_.target_price, reverse=True)
    prices = [q_.target_price for q_ in quotes]

    if not prices:
        return ConsensusView(
            ticker=ticker, as_of=as_of, window_days=window_days, quotes=(),
            median=None, weighted_median=None, mean=None, count=0,
            n_reports_raw=n_reports_raw, min=None, max=None,
            newest_age_days=None, stale=True,
        )

    newest_age = min(q_.age_days for q_ in quotes)
    return ConsensusView(
        ticker=ticker,
        as_of=as_of,
        window_days=window_days,
        quotes=tuple(quotes),
        median=statistics.median(prices),
        weighted_median=weighted_median(prices, [q_.weight for q_ in quotes]),
        mean=sum(prices) / len(prices),
        count=len(quotes),
        n_reports_raw=n_reports_raw,
        min=min(prices),
        max=max(prices),
        newest_age_days=newest_age,
        stale=newest_age > stale_after_days,
    )
