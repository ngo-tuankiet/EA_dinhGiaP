"""Migration: thêm UNIQUE(indicator_code, date) cho bảng macro_series.

Cần cho UPSERT idempotent (Luật vàng #6). An toàn chạy lại nhiều lần:
- ADD CONSTRAINT IF NOT EXISTS (Postgres 9.6+ không hỗ trợ IF NOT EXISTS cho
  ADD CONSTRAINT, nên ta kiểm tra catalog trước).
- Bảng hiện trống (đã xác minh) nên không cần dedup; nếu sau này có dữ liệu
  trùng, script sẽ báo lỗi rõ ràng thay vì âm thầm bỏ qua.

Chạy: ./venv/bin/python -m scripts.migrate_macro_unique
"""
from sqlalchemy import text

from valuation.db.session import SessionLocalWrite

CONSTRAINT = "uq_macro_series_code_date"


def main() -> None:
    db = SessionLocalWrite()
    try:
        exists = db.execute(
            text(
                "SELECT 1 FROM pg_constraint WHERE conname = :name"
            ),
            {"name": CONSTRAINT},
        ).first()
        if exists:
            print(f"Constraint {CONSTRAINT} đã tồn tại — bỏ qua.")
            return

        dupes = db.execute(
            text(
                "SELECT indicator_code, date, COUNT(*) c FROM macro_series "
                "GROUP BY indicator_code, date HAVING COUNT(*) > 1"
            )
        ).fetchall()
        if dupes:
            raise RuntimeError(
                f"Có {len(dupes)} cặp (indicator_code, date) trùng trong "
                "macro_series. Dọn dữ liệu trước khi thêm constraint."
            )

        db.execute(
            text(
                f"ALTER TABLE macro_series ADD CONSTRAINT {CONSTRAINT} "
                "UNIQUE (indicator_code, date)"
            )
        )
        db.commit()
        print(f"Đã thêm constraint {CONSTRAINT}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
