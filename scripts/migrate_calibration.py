"""Tạo bảng hiệu chuẩn: calibration_runs + calibration_observations (D23).

Chỉ CREATE TABLE IF NOT EXISTS — không đụng bảng có sẵn, không UPDATE/DELETE gì
(AGENTS.md luật vàng #6). An toàn chạy lại nhiều lần.

    python -m scripts.migrate_calibration            # dry-run: chỉ in ra sẽ làm gì
    python -m scripts.migrate_calibration --apply    # thực thi
"""
import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect

from valuation.db.models import CalibrationObservation, CalibrationRunRow  # noqa: F401
from valuation.db.session import Base, SessionLocalWrite

_TABLES = ("calibration_runs", "calibration_observations")


def main() -> int:
    ap = argparse.ArgumentParser(description="Tạo bảng hiệu chuẩn (D23)")
    ap.add_argument("--apply", action="store_true",
                    help="Thực thi thật. Không có cờ này = dry-run.")
    args = ap.parse_args()

    db = SessionLocalWrite()
    try:
        bind = db.get_bind()
        existing = set(inspect(bind).get_table_names())
        missing = [t for t in _TABLES if t not in existing]

        print("=" * 64)
        print("MIGRATION HIỆU CHUẨN (D23)")
        print("=" * 64)
        for t in _TABLES:
            print(f"  {t:<32} {'ĐÃ CÓ' if t in existing else 'SẼ TẠO'}")

        if not missing:
            print("\n-> Không có gì để tạo. Kết thúc.")
            return 0

        if not args.apply:
            print(f"\n[DRY-RUN] Sẽ tạo {len(missing)} bảng: {', '.join(missing)}")
            print("Chạy lại với --apply để thực thi.")
            return 0

        # create_all chỉ tạo bảng còn thiếu, không sửa bảng đã tồn tại.
        Base.metadata.create_all(
            bind=bind,
            tables=[Base.metadata.tables[t] for t in missing],
        )
        after = set(inspect(bind).get_table_names())
        for t in missing:
            print(f"  -> {t}: {'OK' if t in after else 'THẤT BẠI'}")
        print("\nHoàn tất.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
