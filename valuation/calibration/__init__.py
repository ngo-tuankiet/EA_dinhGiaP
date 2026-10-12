"""Hiệu chuẩn định giá — đo lệch mô hình vs đồng thuận CTCK và vs thị giá.

Package này KHÔNG định giá. Nó gọi `valuation.engine.batch.value_all` (đúng lõi
production) rồi đo kết quả, để mọi thay đổi mô hình đều có bằng chứng số trước/sau.

Lý do tồn tại (DECISIONS.md D23): sprint 2026-07 sửa undervaluation ngân hàng đã
overshoot từ -25% sang +10.7% mà không ai phát hiện, vì không có cơ chế đo lệch
theo nhóm phương pháp giữa hai lần chạy.

Ranh giới quan trọng: engine KHÔNG được import package này (xem
tests/test_import_boundaries.py). Dữ liệu CTCK chỉ dùng để ĐO, không bao giờ là
input định giá.
"""
