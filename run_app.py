import os
import sys

# Kiểm tra bản quyền trước khi load bất kỳ thứ gì khác
try:
    from valuation.security.trial_manager import check_trial_status
    check_trial_status()
except ImportError as e:
    print(f"Lỗi khởi động module bảo mật: {e}")
    sys.exit(1)

import streamlit.web.bootstrap

def main():
    # Khi build bằng PyInstaller, __file__ trỏ về file thực thi, nhưng
    # các file assets được nhét vào thư mục tạm sys._MEIPASS
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    app_path = os.path.join(base_dir, "streamlit_app.py")
    
    # Thiết lập biến môi trường để Streamlit tự động mở trình duyệt và vô hiệu hóa các thông báo không cần thiết
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "false"
    os.environ["STREAMLIT_SERVER_PORT"] = "8501"
    
    print("🚀 Đang khởi động hệ thống định giá VN100...")
    
    # Chạy streamlit app
    streamlit.web.bootstrap.run(
        app_path,
        command_line="",
        args=[],
        flag_options={}
    )

if __name__ == "__main__":
    main()
