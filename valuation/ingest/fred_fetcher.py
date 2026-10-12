"""Lấy lãi suất Fed và TPCP Mỹ 10Y từ FRED (Fed St. Louis) — CSV công khai, không cần API key (D50).

Chỉ gọi khi người dùng bấm "Cập nhật vĩ mô"; domain phải nằm trong macro_sources.allowed_domains.
Ghi DB qua upsert_macro_series (idempotent, truy vết nguồn). FRED trả % → lưu decimal_rate.
"""

from __future__ import annotations

import datetime
import urllib.parse
from collections.abc import Callable
from zoneinfo import ZoneInfo

from valuation.config import get_macro_allowed_domains, load_defaults
from valuation.ingest.macro_store import MacroPoint, upsert_macro_series

SOURCE = "fred.stlouisfed.org"
_BASE = f"https://{SOURCE}/graph/fredgraph.csv"
# Mã FRED → series_code trong macro_series_registry.
FRED_SERIES: dict[str, str] = {
    "DFEDTARU": "FED_FUNDS_UPPER",
    "DFEDTARL": "FED_FUNDS_LOWER",
    "DGS10": "UST_10Y",
}


def parse_fred_csv(text: str, fred_id: str, code: str) -> list[MacroPoint]:
    """CSV 'observation_date,<ID>' → MacroPoint (bỏ ô trống '.'). Header lạ → lỗi rõ ràng."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines or lines[0].split(",")[-1].strip() != fred_id:
        raise ValueError(
            f"FRED {fred_id}: phản hồi không phải CSV mong đợi ({lines[:1]})"
        )
    points = []
    for ln in lines[1:]:
        day, _, raw = ln.partition(",")
        if raw in ("", "."):
            continue
        points.append(
            MacroPoint(
                code, datetime.date.fromisoformat(day), float(raw) / 100.0, SOURCE
            )
        )
    return points


def _http_get(url: str) -> str:
    import httpx

    cfg = load_defaults().get("macro_sources", {}) or {}
    resp = httpx.get(
        url,
        timeout=float(cfg.get("request_timeout_sec", 15)),
        headers={"User-Agent": cfg.get("user_agent", "antigravity-vn100-macro/1.0")},
        follow_redirects=False,
    )
    resp.raise_for_status()
    return resp.text


def fetch_fred(
    db,
    http_get: Callable[[str], str] = _http_get,
    writer: Callable = upsert_macro_series,
    today: datetime.date | None = None,
) -> int:
    """Lấy các chuỗi FRED_SERIES trong `fred_history_days` gần nhất, ghi DB. Trả số điểm đã ghi."""
    if SOURCE not in get_macro_allowed_domains():
        raise PermissionError(f"{SOURCE} chưa nằm trong macro_sources.allowed_domains")
    days = int(
        (load_defaults().get("macro_dashboard") or {}).get("fred_history_days", 60)
    )
    start = (
        today or datetime.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    ) - datetime.timedelta(days=days)
    points: list[MacroPoint] = []
    for fred_id, code in FRED_SERIES.items():
        url = f"{_BASE}?" + urllib.parse.urlencode(
            {"id": fred_id, "cosd": start.isoformat()}
        )
        points.extend(parse_fred_csv(http_get(url), fred_id, code))
    return writer(points, db) if points else 0
