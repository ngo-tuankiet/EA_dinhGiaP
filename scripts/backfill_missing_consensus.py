"""Backfill consensus CTCK cho VN100 bằng nguồn công khai.

Ghi idempotent vào consensus_history; không tải/lưu PDF báo cáo để tránh phát
tán lại tài liệu có bản quyền. Nguồn và raw_quote vẫn được lưu để truy vết.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from valuation.db.models import Consensus, Ticker
from valuation.db.session import SessionLocalRead
from valuation.ingest.scrapers import broker_24hmoney, broker_simplize


SOURCES = (
    ("SIMPLIZE", broker_simplize.import_reports),
    ("24HMONEY", broker_24hmoney.import_broker_reports),
)


def _vn100_tickers(only_missing: bool) -> list[str]:
    db = SessionLocalRead()
    try:
        q = db.query(Ticker.ticker).filter(Ticker.is_vn100.is_(True))
        if only_missing:
            have = {
                row[0]
                for row in db.query(Consensus.ticker)
                .filter(Consensus.is_synthetic.is_(False))
                .distinct()
                .all()
            }
            return sorted(t[0] for t in q.all() if t[0] not in have)
        return sorted(t[0] for t in q.all())
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill consensus CTCK cho VN100")
    parser.add_argument("--only-missing", action="store_true", help="Chỉ chạy mã chưa có consensus thật")
    parser.add_argument("--tickers", nargs="*", help="Danh sách mã cụ thể, bỏ qua selector tự động")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số mã chạy, 0 = không giới hạn")
    parser.add_argument("--sleep", type=float, default=0.7, help="Nghỉ giữa các mã để giảm tải nguồn")
    args = parser.parse_args()

    tickers = [t.upper() for t in args.tickers] if args.tickers else _vn100_tickers(args.only_missing)
    if args.limit > 0:
        tickers = tickers[: args.limit]

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"consensus_backfill_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    total = len(tickers)
    rows: list[dict[str, object]] = []
    print(f"Backfill consensus: {total} mã -> {log_path}")

    for idx, ticker in enumerate(tickers, start=1):
        source_counts: dict[str, int] = {}
        source_errors: dict[str, str] = {}
        print(f"[{idx}/{total}] {ticker}", flush=True)
        for source_name, importer in SOURCES:
            try:
                recs = importer(ticker) or []
                source_counts[source_name] = len(recs)
                print(f"  - {source_name}: {len(recs)}")
            except Exception as exc:
                source_counts[source_name] = 0
                source_errors[source_name] = f"{type(exc).__name__}: {str(exc)[:200]}"
                print(f"  - {source_name}: ERR {source_errors[source_name]}")

        rows.append(
            {
                "ticker": ticker,
                "simplize": source_counts.get("SIMPLIZE", 0),
                "24hmoney": source_counts.get("24HMONEY", 0),
                "errors": " | ".join(f"{k}: {v}" for k, v in source_errors.items()),
            }
        )
        if args.sleep > 0 and idx < total:
            time.sleep(args.sleep)

    with log_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker", "simplize", "24hmoney", "errors"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. Log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
