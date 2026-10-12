"""Backfill sự kiện vốn/quyền cho VN100 với checkpoint theo từng mã."""
from __future__ import annotations

import argparse
import json

from valuation.db.session import SessionLocalWrite
from valuation.ingest.corporate_actions import backfill_vn100_corporate_actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill corporate actions VN100")
    parser.add_argument("--apply", action="store_true", help="Cho phép gọi nguồn và ghi DB")
    parser.add_argument("--force", action="store_true", help="Bỏ qua TTL checkpoint")
    args = parser.parse_args()
    if not args.apply:
        print("DRY-RUN: dùng --apply để backfill; --force chỉ dùng khi cần kiểm tra lại toàn bộ.")
        return 0
    db = SessionLocalWrite()
    try:
        def _progress(done, total, ticker, result):
            print(
                f"[{done:03d}/{total:03d}] {ticker}: {result.get('status')} "
                f"+{result.get('inserted', 0)} ~{result.get('updated', 0)}",
                flush=True,
            )

        summary = backfill_vn100_corporate_actions(
            db,
            force=args.force,
            progress=_progress,
        )
        print(json.dumps(summary, ensure_ascii=False, default=str))
        return 1 if summary["error"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
