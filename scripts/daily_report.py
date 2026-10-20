"""CLI báo cáo sáng lên Discord (launchd gọi thứ 2–6). Không gọi DeepSeek."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valuation.services.daily_report import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-refresh", action="store_true", help="Không cập nhật giá/vĩ mô, chỉ đọc DB"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ in ra màn hình: không gửi, không lưu lịch sử",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    msg = run(refresh=not args.no_refresh, save=not args.dry_run, send=not args.dry_run)
    print(msg["embed_title"], msg["embed_desc"], sep="\n")
    for f in msg["fields"]:
        print(f"\n{f['name']}\n{f['value']}")
    print(f"\n{msg['footer']}")


if __name__ == "__main__":
    main()
