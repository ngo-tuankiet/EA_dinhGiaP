#!/bin/bash
# Script tự động khởi chạy Hệ thống Định giá VN100 (Nhấp đúp là chạy)
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "============================================================"
echo "   📈 HỆ THỐNG ĐỊNH GIÁ CỔ PHIẾU TỰ ĐỘNG VN100 (STANDALONE)   "
echo "============================================================"
echo "-> Đang kiểm tra môi trường và khởi động hệ thống..."

PYTHON_CMD="${PYTHON:-python3}"
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    echo "Không tìm thấy python3. Vui lòng cài Python 3.11+ rồi chạy lại."
    read -p "Nhấn Enter để thoát..."
    exit 1
fi

VENV_DIR="$HOME/.venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "-> Đang tạo môi trường Python dùng chung tại $VENV_DIR..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

python - <<'PY'
import importlib.util
import subprocess
import sys

required = ["streamlit", "sqlalchemy", "pandas", "pydantic_settings", "dotenv"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print("-> Đang cài/cập nhật thư viện cần thiết...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "pip"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
PY

python scripts/ensure_portable_db.py

export DATABASE_URL_READONLY="sqlite:///$DIR/vn100_full.db"
export DATABASE_URL_WRITE="sqlite:///$DIR/vn100_full.db"
export STREAMLIT_SERVER_FILE_WATCHER_TYPE="none"
export STREAMLIT_BROWSER_GATHER_USAGE_STATS="false"

# Tự động mở trình duyệt web sau 2 giây
(sleep 2 && open "http://localhost:8502") &

# Khởi chạy ứng dụng Streamlit
python -m streamlit run streamlit_app.py --server.port 8502 --server.headless true --server.fileWatcherType none
