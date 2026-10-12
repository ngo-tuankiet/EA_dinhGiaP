"""Bổ sung nguồn Golden vào kho chờ đối chiếu; không sửa BCTC hoặc gọi AI."""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valuation.config import PROJECT_ROOT, settings
from valuation.db.models import PricesDaily
from valuation.db.session import SessionLocalRead
from valuation.ingest.sponsor_data import collect_sponsor_dataset
from valuation.ingest.universe import load_vn100_snapshot
from valuation.services.ranking_store import read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*")
    parser.add_argument("--financials", action="store_true")
    parser.add_argument("--workers", type=int, default=1, choices=(1, 2, 3))
    args = parser.parse_args()
    allowed = load_vn100_snapshot()["symbols"]
    tickers = args.tickers or allowed
    if set(tickers) - set(allowed):
        parser.error("Mã ngoài VN100")
    root = PROJECT_ROOT / ".vn100_ranking/sponsor"
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    previous = read_json(root / "collection_status.json", {})
    results = [
        row
        for row in previous.get("results", [])
        if row.get("ticker") not in set(tickers)
    ]
    logging.getLogger("vnstock_data").setLevel(logging.ERROR)

    def collect_ticker(ticker: str) -> list[dict]:
        collected = []
        with SessionLocalRead() as db:
            prices = (
                db.query(PricesDaily.trade_date)
                .filter(
                    PricesDaily.ticker == ticker,
                    PricesDaily.close > 0,
                    PricesDaily.trade_date < now.date(),
                )
                .order_by(PricesDaily.trade_date.desc())
                .limit(20)
                .all()
            )
        if len(prices) != 20:
            return [
                {
                    "ticker": ticker,
                    "status": "error",
                    "error": "Thiếu 20 phiên giá để chọn cửa sổ",
                }
            ]
        days = [p[0] for p in prices]
        kinds = ["stats", "foreign", "ratios"]
        if args.financials:
            kinds += ["BS", "IS", "CF", "BS_FY", "IS_FY", "CF_FY"]
        for kind in kinds:
            try:
                result = collect_sponsor_dataset(
                    ticker, kind, min(days), max(days), now, root
                )
            except (
                RuntimeError,
                ValueError,
                OSError,
                KeyError,
                TypeError,
                SystemExit,
            ) as exc:
                message = str(exc)
                if settings.vnstock_api_key:
                    message = message.replace(settings.vnstock_api_key, "[redacted]")
                result = {"status": "error", "error": message[:350]}
            collected.append({"ticker": ticker, "kind": kind, **result})
        return collected

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(collect_ticker, ticker): ticker for ticker in tickers}
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            collected = future.result()
            results.extend(collected)
            write_json(
                root / "collection_status.json",
                {
                    "started_at": now.isoformat(),
                    "completed_tickers": index,
                    "results": results,
                },
            )
            print(
                f"{index}/{len(tickers)} {ticker}: "
                + ", ".join(f"{r.get('kind', 'all')}={r['status']}" for r in collected),
                flush=True,
            )
    write_json(
        root / "collection_status.json",
        {
            "started_at": now.isoformat(),
            "completed_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
            "completed_tickers": len(tickers),
            "results": results,
        },
    )


if __name__ == "__main__":
    main()
