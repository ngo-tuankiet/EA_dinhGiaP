# Gộp tab định giá và dự phóng

- [x] Kiểm tra thứ tự render và trạng thái của hai phần hiện tại.
- [x] Gộp thành tab "Định giá & dự phóng"; đặt giả định trong expander ở đầu tab.
- [x] Kiểm tra bốn tab, mở/thu gọn giả định và giữ đủ biểu đồ, báo cáo, kịch bản.
- [x] Quét secret và chuẩn bị commit đồng bộ main.

Phạm vi: chỉ sửa bố cục trong streamlit_app.py. Giữ nguyên hai hàm render,
widget key, thứ tự áp dụng giả định trước kết quả và các điều kiện gọi API.
Không sửa công thức, dữ liệu hoặc schema. Kết quả vẫn render sau CTCK và cổ tức
để không chặn việc hiển thị các tab tham chiếu bởi phần chuẩn bị xuất báo cáo.

Kiểm tra: py_compile và git diff --check đạt; health trả về ok.
Trong phiên trình duyệt kiểm tra ACB, Beta 0.90 sang 0.91 cập nhật kết quả
phương pháp chính từ 32.992,3 về 32.697,5 VND. Đã nạp lại phiên từ dữ liệu gốc
để giữ nguyên độ chính xác của giả định và kiểm tra kết quả trở lại giá trị
ban đầu. Đây là kiểm tra tương tác, không xác nhận tính
đúng của dữ liệu nguồn hay công thức. Không lưu DB, xuất báo cáo hoặc gọi AI.
