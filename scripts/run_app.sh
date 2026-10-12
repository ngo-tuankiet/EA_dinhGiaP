#!/bin/sh
# Chạy app VN100 — luôn chỉ MỘT bản: tắt mọi bản streamlit_app.py đang chạy (mọi cổng, mọi thư mục)
# rồi mở bản mới ở cổng 8506 từ đúng thư mục dự án này.
cd "$(dirname "$0")/.." || exit 1
pkill -f "streamlit run streamlit_app.py" 2>/dev/null && sleep 2
exec /Users/macos/.venv/bin/python -m streamlit run streamlit_app.py --server.port 8506 --server.headless true
