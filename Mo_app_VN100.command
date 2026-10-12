#!/bin/sh
# Bấm đúp file này trong Finder để mở app VN100 (luôn chỉ 1 bản, cổng 8506).
cd "$(dirname "$0")" || exit 1
(sleep 6 && open "http://localhost:8506") &
exec sh scripts/run_app.sh
