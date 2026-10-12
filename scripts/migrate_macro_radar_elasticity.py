"""Migration: thêm cột elasticity (NUMERIC, default 1.0) cho bảng macro_radar.

Cần cho daily_signal: driver_delta = elasticity * macro_delta. Cột nullable với
mặc định 1.0 → an toàn, tương thích ngược (map 1:1 như cũ).

An toàn chạy lại nhiều lần (ADD COLUMN IF NOT EXISTS — Postgres 9.6+).

Chạy: ./venv/bin/python -m scripts.migrate_macro_radar_elasticity
"""
from sqlalchemy import text

from valuation.db.session import SessionLocalWrite


def main() -> None:
    db = SessionLocalWrite()
    try:
        db.execute(
            text(
                "ALTER TABLE macro_radar "
                "ADD COLUMN IF NOT EXISTS elasticity NUMERIC DEFAULT 1.0"
            )
        )
        db.commit()
        print("Đã đảm bảo cột macro_radar.elasticity (default 1.0).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
