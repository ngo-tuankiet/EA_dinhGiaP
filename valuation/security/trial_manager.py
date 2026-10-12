import os
import sys
import json
import base64
import time
from datetime import datetime, timedelta

LICENSE_FILE_NAME = ".vn100_license.dat"
TRIAL_DAYS = 14

def _get_license_path():
    """Lưu trữ file license ở thư mục người dùng (cấp OS) để tránh bị xóa cùng app"""
    home = os.path.expanduser("~")
    return os.path.join(home, LICENSE_FILE_NAME)

def _read_license():
    path = _get_license_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            encoded_data = f.read()
        decoded_bytes = base64.b64decode(encoded_data.encode("utf-8"))
        decoded_str = decoded_bytes.decode("utf-8")
        return json.loads(decoded_str)
    except Exception:
        # Nếu file bị lỗi / bị sửa tay làm sai định dạng -> khóa luôn
        return {"tampered": True}

def _write_license(data):
    path = _get_license_path()
    json_str = json.dumps(data)
    encoded_bytes = base64.b64encode(json_str.encode("utf-8"))
    with open(path, "w") as f:
        f.write(encoded_bytes.decode("utf-8"))

def check_trial_status():
    """Kiểm tra thời hạn 14 ngày. Nếu quá hạn hoặc gian lận thì khóa app."""
    import tkinter as tk
    from tkinter import messagebox
    
    def show_alert_and_exit(msg):
        root = tk.Tk()
        root.withdraw() # Ẩn cửa sổ chính
        messagebox.showerror("VN100 Valuation - Thông báo", msg)
        root.destroy()
        sys.exit(1)

    lic_data = _read_license()
    now_ts = int(time.time())
    
    if lic_data is None:
        # Lần chạy đầu tiên
        lic_data = {
            "first_run_ts": now_ts,
            "last_check_ts": now_ts
        }
        _write_license(lic_data)
        return True # Cho phép chạy
        
    if lic_data.get("tampered"):
        show_alert_and_exit("Phát hiện dữ liệu bản quyền bị can thiệp trái phép. Ứng dụng đã bị khóa.")
        
    first_run_ts = lic_data.get("first_run_ts", 0)
    last_check_ts = lic_data.get("last_check_ts", 0)
    
    # Kiểm tra gian lận lùi thời gian máy tính (thời gian hiện tại nhỏ hơn thời gian check lần cuối)
    if now_ts < last_check_ts:
        show_alert_and_exit("Phát hiện thời gian hệ thống không hợp lệ (Time Tampering). Ứng dụng bị khóa.")
        
    # Tính toán thời gian đã qua
    first_run_date = datetime.fromtimestamp(first_run_ts)
    now_date = datetime.fromtimestamp(now_ts)
    days_passed = (now_date - first_run_date).days
    
    if days_passed > TRIAL_DAYS:
        show_alert_and_exit("Bản dùng thử 14 ngày của bạn đã hết hạn. Vui lòng liên hệ nhà phát triển để mua bản quyền.")
        
    # Cập nhật thời gian check lần cuối
    lic_data["last_check_ts"] = now_ts
    _write_license(lic_data)
    
    print(f"[Licensing] Bản dùng thử: Còn {TRIAL_DAYS - days_passed} ngày.")
    return True
