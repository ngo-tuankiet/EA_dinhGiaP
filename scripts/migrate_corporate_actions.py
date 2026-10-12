"""Tạo hai bảng sự kiện doanh nghiệp; chỉ CREATE, không sửa/xóa lịch sử."""
from __future__ import annotations

import argparse

from sqlalchemy import inspect

from valuation.db.models import CorporateAction, CorporateActionSync  # noqa: F401
from valuation.db.session import Base, SessionLocalWrite


_TABLES = ("corporate_actions", "corporate_action_sync")


def main() -> int:
    parser = argparse.ArgumentParser(description="Tạo bảng corporate actions")
    parser.add_argument("--apply", action="store_true", help="Thực thi tạo bảng")
    args = parser.parse_args()
    db = SessionLocalWrite()
    try:
        bind = db.get_bind()
        existing = set(inspect(bind).get_table_names())
        missing = [name for name in _TABLES if name not in existing]
        for name in _TABLES:
            print(f"{name}: {'ĐÃ CÓ' if name in existing else 'SẼ TẠO'}")
        if not missing or not args.apply:
            return 0
        Base.metadata.create_all(
            bind=bind,
            tables=[Base.metadata.tables[name] for name in missing],
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
