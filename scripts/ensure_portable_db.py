from __future__ import annotations

import gzip
import shutil
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "vn100_full.db"
GZ_PATH = ROOT / "vn100_full.db.gz"


def ensure_portable_db() -> Path:
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        _validate_sqlite(DB_PATH)
        print(f"Đã có database portable: {DB_PATH}")
        return DB_PATH

    if not GZ_PATH.exists():
        raise FileNotFoundError(
            "Không tìm thấy vn100_full.db hoặc vn100_full.db.gz trong thư mục dự án."
        )

    print("Đang giải nén vn100_full.db.gz thành vn100_full.db...")
    tmp_path = DB_PATH.with_suffix(".db.tmp")
    try:
        with gzip.open(GZ_PATH, "rb") as source, tmp_path.open("wb") as target:
            shutil.copyfileobj(source, target)
        _validate_sqlite(tmp_path)
        tmp_path.replace(DB_PATH)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    print(f"Đã sẵn sàng database portable: {DB_PATH}")
    return DB_PATH


def _validate_sqlite(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"SQLite integrity_check thất bại: {result}")


if __name__ == "__main__":
    ensure_portable_db()
