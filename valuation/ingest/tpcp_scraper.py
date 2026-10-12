"""
Scraper lợi suất TPCP 10 năm từ nguồn CHÍNH THỐNG (HNX / VBMA).

TRẠNG THÁI: scaffold sẵn sàng — parser + domain-guard + fetcher tách rời đã
test offline. Chưa bật scrape LIVE vì cần XÁC NHẬN endpoint AJAX thật của HNX/
VBMA (trang dùng ASP.NET, endpoint JSON không public rõ ràng; môi trường dev
hiện không verify được SSL hnx.vn). Khi có endpoint xác nhận:
  1. Điền `macro_sources.tpcp_10y_endpoint` trong config/defaults.yaml.
  2. Chỉnh `parse_hnx_yield_curve` cho khớp schema thật (đã có test khung).
  3. Bật gọi `fetch_tpcp_10y(db)` trong pipeline quét.

NGUYÊN TẮC BẢO MẬT (AGENTS.md mục 5):
- Chỉ fetch domain nằm trong `macro_sources.allowed_domains` (hnx.vn/vbma.org.vn
  đã thêm). `_assert_allowed_host` chặn mọi host lạ (chống SSRF).
- Fetcher injectable → test KHÔNG chạm mạng.
Ghi DB idempotent qua upsert_macro_series.
"""
from __future__ import annotations

import datetime
from typing import Callable, List, Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from valuation.config import get_macro_allowed_domains, load_defaults
from valuation.ingest.macro_store import MacroPoint, upsert_macro_series

# fetcher: url -> nội dung thô (JSON text / HTML). Injectable để test offline.
Fetcher = Callable[[str], str]


def _assert_allowed_host(url: str) -> None:
    """Chặn fetch tới domain ngoài allowlist (chống gọi endpoint lạ/SSRF)."""
    host = (urlparse(url).hostname or "").lower()
    allowed = {d.lower() for d in get_macro_allowed_domains()}
    if host not in allowed:
        raise ValueError(
            f"Host '{host}' KHÔNG nằm trong macro_sources.allowed_domains "
            f"({sorted(allowed)}). Từ chối fetch (bảo mật AGENTS.md #5)."
        )


def _httpx_fetch(url: str) -> str:
    """Fetcher thật qua httpx (chỉ gọi sau khi đã _assert_allowed_host)."""
    import httpx
    cfg = load_defaults().get("macro_sources", {})
    headers = {"User-Agent": cfg.get("user_agent", "antigravity-vn100-macro/1.0")}
    timeout = float(cfg.get("request_timeout_sec", 15))
    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def parse_hnx_yield_curve(payload: str, tenor_years: int = 10) -> Optional[tuple[datetime.date, float]]:
    """Bóc (ngày, lợi suất decimal) cho kỳ hạn `tenor_years` từ JSON HNX.

    HNX đường cong lợi suất trả list điểm, mỗi điểm có kỳ hạn + lợi suất (%).
    Parser linh hoạt theo nhiều tên trường thường gặp; trả None nếu không thấy
    kỳ hạn yêu cầu. (Schema chính xác cần xác nhận endpoint thật — test khung
    dùng sample đại diện.)
    """
    import json

    data = json.loads(payload)
    # Chấp nhận cả {"data": [...]} lẫn list trực tiếp.
    rows = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return None

    _TENOR_KEYS = ("tenor", "term", "KyHan", "kyhan", "maturity")
    _YIELD_KEYS = ("yield", "LaiSuat", "laisuat", "value", "rate")
    _DATE_KEYS = ("date", "Ngay", "ngay", "TradingDate", "tradeDate")

    def _get(d, keys):
        for k in keys:
            if k in d:
                return d[k]
        return None

    for row in rows:
        if not isinstance(row, dict):
            continue
        tenor = _get(row, _TENOR_KEYS)
        # tenor có thể "10Y", "10", 10, "10 năm"
        tenor_num = None
        if tenor is not None:
            s = "".join(ch for ch in str(tenor) if ch.isdigit())
            tenor_num = int(s) if s else None
        if tenor_num != tenor_years:
            continue
        y = _get(row, _YIELD_KEYS)
        if y is None:
            continue
        yv = float(y)
        if abs(yv) > 1.0:  # nhập dạng % → decimal_rate
            yv /= 100.0
        d = _get(row, _DATE_KEYS)
        obs_date = (
            __import__("pandas").to_datetime(d).date() if d else datetime.date.today()
        )
        return obs_date, yv
    return None


def fetch_tpcp_10y(
    db: Session,
    fetcher: Fetcher = _httpx_fetch,
    endpoint: Optional[str] = None,
    registry: Optional[dict] = None,
) -> int:
    """Lấy TPCP_10Y từ HNX/VBMA và ghi idempotent. Trả số điểm ghi (0 nếu chưa
    cấu hình endpoint hoặc không parse được).

    endpoint: mặc định đọc `macro_sources.tpcp_10y_endpoint` từ config. Rỗng →
    trả 0 (chưa bật live; dùng CSV import thay thế).
    """
    ep = endpoint or load_defaults().get("macro_sources", {}).get("tpcp_10y_endpoint", "")
    if not ep:
        return 0
    _assert_allowed_host(ep)
    payload = fetcher(ep)
    parsed = parse_hnx_yield_curve(payload, tenor_years=10)
    if parsed is None:
        return 0
    obs_date, value = parsed
    host = (urlparse(ep).hostname or "hnx.vn").replace("www.", "")
    points: List[MacroPoint] = [MacroPoint("TPCP_10Y", obs_date, value, source=host)]
    return upsert_macro_series(points, db, registry=registry)
