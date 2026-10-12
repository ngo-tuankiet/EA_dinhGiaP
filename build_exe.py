import os
import sys
import subprocess

def main():
    print("Bắt đầu đóng gói ứng dụng VN100 Valuation...")
    
    # Đảm bảo PyInstaller đã được cài đặt
    try:
        import PyInstaller
    except ImportError:
        print("Đang cài đặt PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        
    # Thư mục gốc dự án
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Lệnh chạy PyInstaller
    # --name: tên file exe
    # --onefile: gom tất cả vào 1 file duy nhất (dễ chia sẻ)
    # --add-data: thêm các file/thư mục cần thiết vào exe
    # --hidden-import: một số thư viện PyInstaller không tự nhận diện được (đặc biệt là streamlit)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "-y",
        "--name=VN100_Valuation",
        "--onefile",
        "--windowed", # Ẩn console đen
        "--add-data=streamlit_app.py:.",
        "--add-data=valuation/config/routing.json:valuation/config",
        "--add-data=.env:.",
        "--hidden-import=streamlit",
        "--hidden-import=sqlalchemy",
        "--hidden-import=psycopg2",
        "--hidden-import=pandas",
        "--hidden-import=dotenv",
        "--hidden-import=pydantic",
        "--hidden-import=ingest_all",
        "run_app.py"
    ]
    
    # Các package của Streamlit có rất nhiều file tĩnh (frontend), cần được include
    import streamlit
    st_path = os.path.dirname(streamlit.__file__)
    command.append(f"--add-data={st_path}:streamlit")
    
    print("Đang chạy lệnh:", " ".join(command))
    
    # Chạy build
    env = os.environ.copy()
    result = subprocess.run(command, env=env, cwd=base_dir)
    
    if result.returncode == 0:
        print("\n✅ Đóng gói THÀNH CÔNG!")
        print(f"File thực thi nằm trong thư mục: {os.path.join(base_dir, 'dist')}")
    else:
        print("\n❌ Đóng gói THẤT BẠI. Vui lòng kiểm tra log ở trên.")

if __name__ == "__main__":
    main()
