# Kiểm soát chi phí DeepSeek

## Báo cáo định giá

- Một lần sinh báo cáo tạo đồng thời kiểm chứng dữ liệu, luận điểm đầu tư, phần
  phản biện/rủi ro, kỹ thuật/dòng tiền/vị thế thị trường và tổng hợp CTCK trong
  tối đa một API call.
- Trước khi gọi API, hệ thống tạo dấu vân tay từ BCTC, giả định, thị giá, kết quả
  định giá, sự kiện và báo cáo CTCK. Cùng dấu vân tay thì dùng lại báo cáo đã lưu,
  kể cả sau khi khởi động lại ứng dụng.
- Thời điểm kiểm tra nguồn không làm cache mất hiệu lực. Khi dữ liệu thực chất
  thay đổi, dấu vân tay đổi và hệ thống tự gọi lại DeepSeek.
- Tùy chọn `Buộc DeepSeek viết lại dù dữ liệu không đổi` luôn tốn một API call và
  chỉ nên bật khi cần một cách diễn đạt mới.

## Các luồng khác

- Bản tin vĩ mô chỉ gọi DeepSeek khi nội dung RSS thay đổi. Cache hết giờ nhưng
  danh sách tin giống hệt thì chỉ gia hạn cache, không gọi model.
- Upload Google Sheets dùng lại luận điểm từ báo cáo đã kiểm chứng, không sinh
  thêm một AI Insight riêng trong giao diện.
- Kiểm tra sự kiện VCI chạy nền. Lỗi nguồn được chờ 30 phút trước khi thử lại để
  Streamlit rerun không tạo request lặp liên tục.
- Ranking VN100/tích sản chỉ gọi DeepSeek khi danh sách hoặc dữ liệu đầu vào đổi;
  không gọi lại chỉ vì người dùng mở tab. Một request nếu cần phải gom cả nhóm
  thận trọng và tăng trưởng.

## Nội dung không nên để AI lặp lại

- Không tạo section AI summary riêng tên "Cổ tức, tăng vốn và quyền cổ đông".
  Sự kiện doanh nghiệp đã có tab/bảng riêng; AI chỉ nhắc khi sự kiện tác động
  trực tiếp tới luận điểm, rủi ro hoặc định giá.
