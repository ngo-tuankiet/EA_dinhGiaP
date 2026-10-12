# Kế hoạch giao diện tham khảo VPBank

## Phạm vi

- Tham khảo trực tiếp https://www.vpbank.com.vn/ca-nhan ngày 31/08/2026.
- Màu quan sát: xanh lá #00B74F, xanh dương #1D4289, chữ #2E3A5B.
- Trang mẫu dùng SVN-Gilroy, menu 16px, tiêu đề chính 52px/60px,
  tiêu đề phần 28-36px. Dùng Manrope có giấy phép OFL, hỗ trợ tiếng Việt,
  lưu trong dự án; không sao chép logo, ảnh hoặc font riêng của ngân hàng.
- Giữ bố cục làm việc của ứng dụng: chọn mã, tổng quan, năm tab phân tích.
  Đầu trang hai tầng gọn, nền trắng, khoảng thở rõ, số liệu dễ so sánh.
- Giữ nguyên dữ liệu, mô hình, kiểm chứng, nút gọi DeepSeek và xuất báo cáo.

## Các bước

- [x] Đọc trang mẫu, đo màu/chữ và kiểm tra code hiện tại.
- [x] Sửa theme.py, streamlit_app.py, corporate_actions.py và cấu hình theme.
- [x] Kiểm tra desktop/mobile, độ tương phản, tab, cảnh báo, không gọi AI.
- [x] Quét secret, kiểm tra diff và chuẩn bị bản phát hành lên main.

## Rủi ro và kiểm tra

- CSS phải theo testid hiện có của Streamlit, không làm mất thao tác/nội dung.
- Giữ đỏ/cam cho cảnh báo và xám cho chưa đủ cơ sở định giá.
- Font tải từ tệp nội bộ; hiệu ứng CSS ngắn và tôn trọng reduced-motion.
- Kiểm tra ảnh chụp màn hình, không tràn chữ; bảng rộng được cuộn riêng.
- Không đổi schema, ghi đè dữ liệu hoặc thêm dịch vụ ngoài.

## Thiết kế đã áp dụng

- Header hai tầng: dải xanh dương sang xanh lá và hàng nhận diện VN100.
- Tiêu đề trang 34px, tiêu đề phần 26px, tiêu đề phụ 20px, nội dung 15px.
  Điện thoại dùng tiêu đề 28px/23px/18px; không co chữ liên tục theo viewport.
- Manrope thường/đậm dạng WOFF2 được nhúng từ tệp cục bộ, cache một lần
  mỗi tiến trình. Giấy phép nằm trong valuation/views/assets/Manrope-LICENSE.txt.
- Nút thao tác bo tròn, nút sinh báo cáo nổi bật; giữ nguyên điều kiện gọi API.
- Tổng quan và thống kê là các dải thông tin, không dùng thẻ lồng nhau.
- Tên tab ngắn hơn; bảng rộng cuộn độc lập trên màn hình nhỏ.
- Giữ nguyên font và màu riêng của biểu đồ kỹ thuật khi người dùng đổi theme
  biểu đồ; không tác động tới dữ liệu hay công thức định giá.

## Kết quả kiểm tra

- 22 test hiện có của corporate_actions và report_render đều đạt.
- py_compile, black và ruff của các view đã sửa đều đạt.
- Trình duyệt desktop 1792px và mobile 390px: không tràn ngang toàn trang;
  tiêu đề và giá tự xuống dòng, giữ đầy đủ cảnh báo.
- Cả năm tab có nội dung, không có stException hay lỗi console.
- Nút sinh báo cáo dùng màu mới, không bấm gọi DeepSeek trong kiểm tra UI.
- Font Manrope được áp từ tệp cục bộ; không có yêu cầu tải font ngoài.
- Endpoint health trả về ok; quét secret trên các tệp thay đổi đạt.
