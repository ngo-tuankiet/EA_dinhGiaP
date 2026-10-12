"""Snapshot thành phần VN100 dùng cho ingest và định giá batch."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from valuation.config import PROJECT_ROOT
from valuation.db.models import Ticker


UNIVERSE_FILE = PROJECT_ROOT / "config" / "vn100_universe.json"


def load_vn100_snapshot(path: Path = UNIVERSE_FILE) -> dict[str, Any]:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    symbols = snapshot.get("symbols", [])
    if len(symbols) != 100 or len(set(symbols)) != 100:
        raise ValueError("Snapshot VN100 phải có đúng 100 mã duy nhất")
    if symbols != sorted(symbols):
        raise ValueError("Snapshot VN100 phải được sắp xếp để diff có thể kiểm toán")
    return snapshot


def get_vn100_symbols() -> list[str]:
    return list(load_vn100_snapshot()["symbols"])


def sync_vn100_membership(
    db: Session,
    symbols: list[str],
    metadata_by_symbol: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Đồng bộ cờ thành phần rổ, không xóa lịch sử của mã đã rời VN100."""
    normalized = sorted({symbol.strip().upper() for symbol in symbols})
    if len(normalized) != len(symbols):
        raise ValueError("Danh sách VN100 chứa mã trùng hoặc không chuẩn hóa")

    existing = {row.ticker: row for row in db.query(Ticker).all()}
    missing_metadata = [
        symbol
        for symbol in normalized
        if symbol not in existing and symbol not in metadata_by_symbol
    ]
    if missing_metadata:
        raise ValueError(f"Thiếu metadata cho mã mới: {', '.join(missing_metadata)}")

    now = datetime.now()
    added = 0
    changed = 0
    for ticker in existing.values():
        should_be_member = ticker.ticker in normalized
        if bool(ticker.is_vn100) != should_be_member:
            ticker.is_vn100 = should_be_member
            ticker.updated_at = now
            changed += 1

    for symbol in normalized:
        if symbol in existing:
            continue
        metadata = metadata_by_symbol[symbol]
        db.add(
            Ticker(
                ticker=symbol,
                company_name=str(metadata.get("company_name") or symbol),
                exchange=str(metadata.get("exchange") or "HOSE"),
                sector=str(metadata.get("sector") or ""),
                industry=str(metadata.get("industry") or ""),
                is_vn100=True,
                updated_at=now,
            )
        )
        added += 1

    db.commit()
    return {"members": len(normalized), "added": added, "changed": changed}
