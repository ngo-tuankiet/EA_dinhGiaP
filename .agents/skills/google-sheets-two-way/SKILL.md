---
name: google-sheets-two-way
description: Khi build hoặc sửa phần Google Sheets cho phép người dùng chỉnh giả định và xem giá mục tiêu đổi theo (model 2 chiều), dùng skill này để chọn đúng cơ chế và đồng bộ version.
---

# Skill: Google Sheets model 2 chiều

## Mục tiêu
Hệ thống ra giá tự động (base case), nhưng người dùng sửa kỳ vọng trong Sheet → giá mục tiêu đổi theo. Sửa được 2 chiều, có truy vết version.

## Kiến trúc LAI (bắt buộc dùng cách này)
- **Tab dữ liệu (read-only):** Python ghi BCTC chuẩn hóa, chỉ số, flags QC, giá hiện tại. Người dùng không sửa.
- **Tab giả định (editable):** Python ghi base case (tăng trưởng DT, biên LN, WACC, terminal growth, target multiple). Người dùng sửa các ô này.
- **Tab kết quả:**
  - **Model đơn giản** (multiples, DDM, justified P/B): dựng **công thức sống ngay trong Sheet** → sửa giả định là giá đổi tức thì, minh bạch, không cần gọi lại Python.
  - **Model phức tạp** (DCF nhiều giai đoạn, RNAV, SOTP): **Python tính**, không nhồi vào công thức Sheet. Có nút **"Recompute"** (Apps Script → webhook n8n → Python đọc giả định đã sửa → tính lại → ghi giá mới về Sheet).

## CẤM
- CẤM dựng DCF nhiều giai đoạn / RNAV / SOTP bằng công thức Google Sheet thuần — khó bảo trì, dễ sai, không test được.
- CẤM để Python ghi đè ô giả định của người dùng khi recompute (chỉ ghi ô kết quả). Giữ nguyên thứ người dùng đã chỉnh.

## Đồng bộ & truy vết
- Mỗi lần người dùng chỉnh giả định + recompute → lưu một **version mới** vào `valuation_assumptions` với `edited_by='user'`; base case của máy là `edited_by='system'`.
- Kết quả ghi vào `valuation_outputs` kèm `assumption_version` tương ứng → luôn truy ngược được giá này tính từ giả định nào.
- Master dashboard: 1 sheet liệt kê toàn VN100 (target price, upside, rating, flags) + link tới sheet chi tiết từng mã.

## Kỹ thuật
- Dùng Google service account (scope tối thiểu Sheets/Drive). Không nhúng credential trong Apps Script công khai.
- Ghi Sheets theo batch để tránh rate limit; retry có backoff.
- Webhook recompute phải có token xác thực; validate mã trước khi tính.
- Format số: giá VND/cổ phiếu, %, có nhãn đơn vị rõ ràng để người dùng không hiểu nhầm.
