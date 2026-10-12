"""CLI dùng chung với nút VN100; mặc định có kiểm tra nguồn và một lượt AI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valuation.services.investment_job import run_job


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-refresh", action="store_true", help="Chỉ dùng nguồn đã lưu"
    )
    parser.add_argument("--no-ai", action="store_true", help="Không gọi DeepSeek")
    parser.add_argument(
        "--scheduled", action="store_true", help="Chống lặp lịch cùng tuần"
    )
    parser.add_argument(
        "--export-portable",
        action="store_true",
        help="Chỉ xuất bản snapshot hiện có để đóng gói, không chạy nguồn/AI",
    )
    args = parser.parse_args()
    if args.export_portable:
        from valuation.services.ranking_store import (
            PORTABLE,
            latest_snapshot,
            write_json,
        )

        snapshot = latest_snapshot()
        if not snapshot:
            parser.error("Chưa có snapshot để đóng gói")
        write_json(PORTABLE, snapshot)
        print(
            f"Đã xuất snapshot {snapshot['run_id']} vào {PORTABLE.name}; không gọi API"
        )
        return

    def emit_progress(state: dict) -> None:
        print(json.dumps(state, ensure_ascii=False), flush=True)

    result = run_job(
        refresh=not args.no_refresh,
        use_ai=not args.no_ai,
        scheduled=args.scheduled,
        progress_sink=emit_progress,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
