"""Cập nhật tăng dần cho bảng tuần; không gọi AI và không ghi đè lịch sử."""

from __future__ import annotations

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

import httpx
import pandas as pd
from sqlalchemy import func

from valuation.data_access.investment_snapshot import previous_session_day
from valuation.services.ranking_store import read_json, write_json


def refresh_ticker(ticker: str, now: datetime, cfg: dict, store: Path) -> list[str]:
    from valuation.db.models import FinancialsQuarterly, PricesDaily
    from valuation.db.session import SessionLocalRead, SessionLocalWrite
    from valuation.db.upsert import dialect_insert
    from valuation.ingest.normalizer import normalize_daily_prices, unpivot_financials
    from valuation.ingest.pipeline import upsert_financials
    from valuation.ingest.vnstock_client import vnstock_client

    checkpoint_path = store / "source_checks" / f"{ticker}.json"
    checkpoint = read_json(checkpoint_path, {})
    errors = []
    cutoff = previous_session_day(now.date())
    with SessionLocalRead() as db:
        last = (
            db.query(func.max(PricesDaily.trade_date))
            .filter(
                PricesDaily.ticker == ticker,
                PricesDaily.close > 0,
                PricesDaily.trade_date <= cutoff,
            )
            .scalar()
        )
        ingested = (
            db.query(func.max(FinancialsQuarterly.ingested_at))
            .filter(
                FinancialsQuarterly.ticker == ticker,
            )
            .scalar()
        )
    if last is None or last < cutoff:
        try:
            start = (
                last + timedelta(days=1)
                if last
                else cutoff - timedelta(days=cfg["financial_max_age_days"])
            )
            frame = normalize_daily_prices(
                vnstock_client.get_historical_prices(ticker, start.isoformat())
            )
            records = []
            for _, price in frame.iterrows():
                day = pd.Timestamp(price["time"]).date()
                if day > cutoff or (last and day <= last):
                    continue
                ohlc = {
                    key: float(price[key]) for key in ("open", "high", "low", "close")
                }
                if not all(pd.notna(v) and v > 0 for v in ohlc.values()):
                    raise ValueError("Giá mới không hợp lệ")
                if ohlc["low"] > min(ohlc.values()) or ohlc["high"] < max(
                    ohlc.values()
                ):
                    raise ValueError("OHLC không nhất quán")
                records.append(
                    {
                        "ticker": ticker,
                        "trade_date": day,
                        **ohlc,
                        "volume": int(price["volume"]),
                        "price_unit": "VND",
                    }
                )
            if records:
                with SessionLocalWrite() as db:
                    stmt = dialect_insert(db, PricesDaily).values(records)
                    db.execute(
                        stmt.on_conflict_do_nothing(
                            index_elements=["ticker", "trade_date"]
                        )
                    )
                    db.commit()
            checkpoint["prices_checked"] = now.isoformat()
            checkpoint["prices_added"] = len(records)
        except (Exception, SystemExit) as exc:
            errors.append(f"{ticker}: tải giá thất bại ({type(exc).__name__})")
    # Chỉ kiểm tra BCTC sau TTL; không tải lại mọi lần nhấn nút.
    last_check = checkpoint.get("financials_checked") or (
        ingested.isoformat() if ingested else None
    )
    due = (
        not last_check
        or (now.date() - datetime.fromisoformat(last_check).date()).days
        >= cfg["financial_check_ttl_days"]
    )
    if due:
        ok = True
        for statement in ("BS", "IS", "CF"):
            try:
                frame = unpivot_financials(
                    vnstock_client.get_financials(ticker, statement, period="quarter"),
                    statement,
                )
                if frame.empty:
                    raise ValueError("Nguồn BCTC rỗng")
                # Upsert hiện có dùng DO NOTHING: giữ số cũ khi nguồn đổi số.
                upsert_financials(frame, ticker)
            except (Exception, SystemExit) as exc:
                errors.append(
                    f"{ticker}: tải {statement} thất bại ({type(exc).__name__})"
                )
                ok = False
        if ok:
            checkpoint["financials_checked"] = now.isoformat()
    write_json(checkpoint_path, checkpoint)
    return errors


def fetch_news(now: datetime, cfg: dict, store: Path) -> dict:
    path = store / "news.json"
    cached = read_json(path)
    if (
        cached
        and (now - datetime.fromisoformat(cached["checked_at"])).total_seconds()
        < cfg["news_ttl_hours"] * 3600
    ):
        return cached
    items: dict[str, dict] = {}
    errors = []
    for url in cfg["news_feeds"]:
        try:
            response = httpx.get(url, timeout=10, follow_redirects=True)
            response.raise_for_status()
            for item in ElementTree.fromstring(response.content).findall(".//item"):
                link, title, raw_date = (
                    item.findtext(k, "").strip() for k in ("link", "title", "pubDate")
                )
                if not link.startswith("https://") or not title or not raw_date:
                    continue
                published = parsedate_to_datetime(raw_date)
                if published.tzinfo is None or published > now:
                    continue
                if (
                    not 0
                    <= (now.date() - published.date()).days
                    <= cfg["news_max_age_days"]
                ):
                    continue
                items[link] = {
                    "title": title,
                    "url": link,
                    "published": published.isoformat(),
                }
        except (httpx.HTTPError, ElementTree.ParseError, ValueError, TypeError) as exc:
            errors.append(f"{url}: {type(exc).__name__}")
    data = {
        "checked_at": now.isoformat(),
        "items": sorted(items.values(), key=lambda x: x["published"], reverse=True)[
            : cfg["news_max_items"]
        ],
        "errors": errors,
    }
    # Lỗi nguồn không gán ngày mới cho bản tin cũ.
    if not items and cached:
        return {**cached, "errors": errors, "stale": True}
    write_json(path, data)
    return data
