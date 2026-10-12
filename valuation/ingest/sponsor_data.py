"""Nguồn Golden có cache; chỉ tải khi worker được yêu cầu, không chạy lúc render."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from valuation.config import settings
from valuation.services.ranking_store import read_json, write_json


def fetch_sponsor_dataset(
    ticker: str, kind: str, start: date, end: date
) -> pd.DataFrame:
    os.environ["VNSTOCK_API_KEY"] = settings.vnstock_api_key
    from vnstock_data import Finance, Market

    if kind in {"foreign", "stats"}:
        market = Market().equity(ticker)
        method = market.foreign_flow if kind == "foreign" else market.session_stats
        return method(start=start.isoformat(), end=end.isoformat())
    period = "year" if kind.endswith("_FY") else "quarter"
    statement = kind.removesuffix("_FY")
    methods = {
        "BS": "balance_sheet",
        "IS": "income_statement",
        "CF": "cash_flow",
        "ratios": "ratio",
    }
    finance = Finance(source="VCI", symbol=ticker, period=period, get_all=True)
    return getattr(finance, methods[statement])(
        format="long", style="technical", lang="en", dropna=False, get_all=True
    )


def collect_sponsor_dataset(
    ticker: str,
    kind: str,
    start: date,
    end: date,
    now: datetime,
    root: Path,
    ttl_days: int = 7,
) -> dict:
    """Cache theo loại nguồn/cửa sổ; giữ bản nguồn cũ, không ghi đè BCTC trong DB."""
    if not re.fullmatch(r"[A-Z0-9]{3}", ticker):
        raise ValueError("Mã chứng khoán không hợp lệ")
    if kind not in {
        "foreign",
        "stats",
        "ratios",
        "BS",
        "IS",
        "CF",
        "BS_FY",
        "IS_FY",
        "CF_FY",
    }:
        raise ValueError("Loại dữ liệu không hợp lệ")
    if start > end or end >= now.date() or ttl_days < 1:
        raise ValueError("Cửa sổ dữ liệu hoặc thời hạn cache không hợp lệ")
    path = root / ticker / f"{kind}.json"
    cached = read_json(path)
    same_window = kind not in {"foreign", "stats"} or (
        cached
        and cached.get("start") == start.isoformat()
        and cached.get("end") == end.isoformat()
    )
    if (
        cached
        and same_window
        and 0
        <= (now.date() - date.fromisoformat(cached["checked_at"][:10])).days
        < ttl_days
    ):
        return {"status": "cached", "rows": len(cached["rows"])}
    frame = fetch_sponsor_dataset(ticker, kind, start, end)
    if frame is None or frame.empty:
        raise ValueError(f"Nguồn Golden trả rỗng: {ticker}/{kind}")
    payload = {
        "ticker": ticker,
        "kind": kind,
        "source": (
            "vnstock_data/VCI"
            if kind not in {"foreign", "stats"}
            else "vnstock_data/Market"
        ),
        "checked_at": now.isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "rows": json.loads(frame.to_json(orient="records", date_format="iso")),
        "attrs": frame.attrs,
    }
    if cached:
        write_json(
            root
            / ticker
            / "history"
            / f"{kind}-{cached['checked_at'].replace(':', '-')}.json",
            cached,
        )
    write_json(path, payload)
    return {"status": "downloaded", "rows": len(frame)}


def sponsor_risk_metrics(payload: dict | None, period: str) -> dict:
    """Chỉ nhận tỷ lệ cùng kỳ, đơn vị rõ; không tự xem đây là filing đã kiểm chứng."""
    if not payload or payload.get("ratio_convention") != "verified_decimal":
        return {}
    result = {}
    mapping = {"RT_BANK_NPL": "npl", "RT_BANK_NPL_COVERAGE": "llr"}
    for row in payload.get("rows", []):
        name = mapping.get(row.get("id"))
        value = row.get("value")
        if not name or row.get("period") != period or value is None:
            continue
        if row.get("unit") not in {"%", "lần", "ratio", "decimal"}:
            continue
        value = float(value)
        if math.isfinite(value) and value >= 0 and (name != "npl" or value <= 1):
            result[name] = value
    return result


def sponsor_market_metrics(
    stats: dict | None, foreign: dict | None, days: list[date]
) -> dict:
    """Giá trị khớp lệnh bình quân thật, không nhân giá đóng cửa với khối lượng."""
    if len(days) != 20 or len(set(days)) != 20 or not stats or not foreign:
        return {}
    start, end = min(days).isoformat(), max(days).isoformat()
    if any(p.get("start") != start or p.get("end") != end for p in (stats, foreign)):
        return {}
    rows = stats.get("rows", [])
    flow_rows = foreign.get("rows", [])
    dates = [str(r.get("time", ""))[:10] for r in flow_rows]
    if (
        len(rows) != 1
        or len(dates) != 20
        or set(dates) != {d.isoformat() for d in days}
    ):
        return {}
    avg = rows[0].get("average_match_value")
    total = rows[0].get("total_value")
    avg_volume, total_volume = rows[0].get("average_volume"), rows[0].get(
        "total_volume"
    )
    if any(
        v is None or not math.isfinite(float(v)) or float(v) <= 0
        for v in (avg, total, avg_volume, total_volume)
    ):
        return {}
    if abs(float(total_volume) / float(avg_volume) - 20) > 0.01:
        return {}
    net_values = [r.get("net_val") for r in flow_rows]
    if any(v is None or not math.isfinite(float(v)) for v in net_values):
        return {}
    return {
        "avg_traded_value": float(avg),
        "foreign_flow_ratio": sum(map(float, net_values)) / float(total),
    }
