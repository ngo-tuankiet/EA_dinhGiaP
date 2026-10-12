"""Snapshot bất biến, ghi nguyên tử và khóa liên tiến trình trên Mac/Windows."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".vn100_ranking"
PORTABLE = ROOT / "data/vn100_ranking_latest.json"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
                default=str,
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    """OS tự nhả khóa khi tiến trình chết; không xóa tệp khóa đang có người đợi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise BlockingIOError("Worker khác đang giữ khóa") from exc
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def latest_snapshot(store: Path = STORE) -> dict | None:
    pointer = read_json(store / "latest.json")
    if pointer:
        name = Path(pointer["filename"]).name
        return read_json(store / "history" / name)
    return read_json(PORTABLE)


def publish(snapshot: dict, store: Path = STORE) -> None:
    name = f"{snapshot['run_id']}.json"
    target = store / "history" / name
    if target.exists():
        raise FileExistsError("Không ghi đè snapshot lịch sử")
    write_json(target, snapshot)
    write_json(store / "latest.json", {"filename": name})
