from pathlib import Path

import pytest

from valuation.services.ranking_store import exclusive_lock, latest_snapshot, publish


def test_os_lock_prevents_duplicate_worker(tmp_path: Path) -> None:
    with exclusive_lock(tmp_path / "job.lock"):
        with pytest.raises(OSError):
            with exclusive_lock(tmp_path / "job.lock"):
                pytest.fail("Không được chạy hai worker cùng lúc")
    with exclusive_lock(tmp_path / "job.lock"):
        pass


def test_snapshot_immutable_and_latest_atomic(tmp_path: Path) -> None:
    publish({"run_id": "one", "rows": [1]}, tmp_path)
    with pytest.raises(FileExistsError):
        publish({"run_id": "one", "rows": [2]}, tmp_path)
    assert latest_snapshot(tmp_path)["rows"] == [1]
    publish({"run_id": "two", "rows": [3]}, tmp_path)
    assert latest_snapshot(tmp_path)["rows"] == [3]
    assert (tmp_path / "history/one.json").exists()
