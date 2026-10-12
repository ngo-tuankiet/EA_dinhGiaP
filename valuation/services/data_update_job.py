"""Job nền "Quét VN100": cập nhật giá + BCTC + khuyến nghị CTCK, có tiến độ.

Cùng mẫu với job xếp hạng (investment_job): tiến trình Python riêng, trạng thái ghi
ra status.json sau MỖI mã, khóa OS chống chạy trùng. Trước đây nút chỉ bật một
thread daemon rồi hiện toast — không biết đang tới đâu, bấm lại là chạy trùng.

  python -m valuation.services.data_update_job   # worker (UI tự khởi chạy)
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from valuation.services.ranking_store import ROOT, exclusive_lock, read_json, write_json

STORE = ROOT / ".data_update"
_ACTIVE = ("QUEUED", "RUNNING")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def job_status(store: Path = STORE) -> dict:
    """Trạng thái hiện tại; RUNNING mà khóa worker đang trống = worker đã chết."""
    status = read_json(store / "status.json", {}) or {}
    if status.get("status") in _ACTIVE:
        try:
            with exclusive_lock(store / "worker.lock"):
                age = (datetime.now().astimezone() - datetime.fromisoformat(status["updated_at"])).total_seconds()
                if status["status"] == "RUNNING" or age > 60:
                    return {**status, "status": "INTERRUPTED",
                            "message": f"Đợt quét dừng giữa chừng ở {status.get('completed', 0)}/{status.get('total', '?')} mã. Có thể quét lại."}
        except BlockingIOError:
            pass  # worker đang giữ khóa → thực sự đang chạy
    return status


def start_job(store: Path = STORE) -> bool:
    """Khởi chạy worker; False nếu một đợt khác đang chạy."""
    try:
        with exclusive_lock(store / "launch.lock"):
            if job_status(store).get("status") in _ACTIVE:
                return False
            write_json(store / "status.json", {"status": "QUEUED", "message": "Đang khởi động",
                                               "completed": 0, "total": 0, "started_at": _now(), "updated_at": _now()})
            # Phiên riêng: tắt/khởi động lại app (Ctrl-C, đóng terminal) không giết đợt quét.
            subprocess.Popen([sys.executable, "-m", "valuation.services.data_update_job"], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True
    except BlockingIOError:
        return False


def main(store: Path = STORE) -> None:
    from valuation.db.session import SessionLocalRead, SessionLocalWrite
    from valuation.ingest.weekly_updater import run_weekly_auto_update

    with exclusive_lock(store / "worker.lock"):
        started = (read_json(store / "status.json", {}) or {}).get("started_at", _now())

        def progress(idx: int, total: int, msg: str) -> None:
            # idx là mã ĐANG xử lý → đã xong idx−1 mã.
            write_json(store / "status.json", {"status": "RUNNING", "message": msg, "completed": idx - 1,
                                               "total": total, "started_at": started, "updated_at": _now()})

        db_read, db_write = SessionLocalRead(), SessionLocalWrite()
        try:
            result = run_weekly_auto_update(db_read, db_write, progress_callback=progress)
            write_json(store / "status.json", {
                "status": "DONE", "message": result["message"], "completed": result["total"],
                "total": result["total"], "started_at": started, "updated_at": _now(), "finished_at": _now(),
                "success": result["success_count"], "partial": result["partial_count"], "failed": result["fail_count"],
            })
        except Exception as exc:  # báo lỗi lên UI thay vì chết im lặng
            last = read_json(store / "status.json", {}) or {}
            write_json(store / "status.json", {**last, "status": "FAILED", "updated_at": _now(),
                                               "message": f"Lỗi: {type(exc).__name__}: {str(exc)[:200]}"})
            raise
        finally:
            db_read.close()
            db_write.close()


if __name__ == "__main__":
    main()
