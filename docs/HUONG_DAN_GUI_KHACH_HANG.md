# Hướng dẫn cài đặt và sử dụng VN100 Valuation

Tài liệu này dùng để gửi cho khách hàng/người dùng cuối. Người dùng không cần
biết lập trình, chỉ cần tải về và chạy đúng file theo hệ điều hành.

## 1. Link tải

Mở link:

```text
https://github.com/tranphixdbt-alt/antigravity-vn100
```

Bấm:

```text
Code -> Download ZIP
```

Sau khi tải xong, giải nén file ZIP ra một thư mục dễ tìm, ví dụ Desktop hoặc
Documents.

## 2. Yêu cầu máy tính

- Windows 10/11 hoặc macOS.
- Có kết nối internet trong lần chạy đầu để cài thư viện Python.
- Cài Python 3.11+.

Nếu máy chưa có Python:

- Windows: tải tại `https://www.python.org/downloads/windows/`.
- Khi cài trên Windows, nhớ tick `Add python.exe to PATH`.
- macOS: cài Python từ `https://www.python.org/downloads/macos/`.

## 3. Chạy trên Windows

Mở thư mục đã giải nén, nhấp đúp file:

```text
Chay_Dinh_Gia_VN100_Windows.bat
```

Lần chạy đầu có thể mất vài phút vì hệ thống cần:

- tạo môi trường Python riêng tại `C:\Users\<ten-user>\.venv`;
- cài các thư viện cần thiết;
- giải nén dữ liệu `vn100_full.db.gz` thành `vn100_full.db`;
- mở giao diện tại `http://localhost:8502`.

Nếu trình duyệt không tự mở, mở Chrome/Edge và nhập:

```text
http://localhost:8502
```

Để tắt ứng dụng, đóng cửa sổ terminal đang chạy hoặc bấm `Ctrl+C`.

## 4. Chạy trên macOS

Mở thư mục đã giải nén, nhấp đúp file:

```text
Chay_Dinh_Gia_VN100.command
```

Nếu macOS chặn vì file tải từ internet:

1. Bấm phải chuột vào file.
2. Chọn `Open`.
3. Bấm `Open` thêm một lần nếu macOS hỏi xác nhận.

Sau đó mở:

```text
http://localhost:8502
```

## 5. Dữ liệu có sẵn

Bản tải về đã có dữ liệu portable trong file:

```text
vn100_full.db.gz
```

Khi chạy lần đầu, hệ thống tự giải nén thành:

```text
vn100_full.db
```

Vì vậy người dùng có thể mở app và xem dữ liệu đã lưu sẵn mà chưa cần nhập API
key.

## 6. Khi nào cần API key?

Không cần API key nếu chỉ xem dữ liệu đã có sẵn.

Cần API key nếu muốn dùng các chức năng sau:

- cập nhật dữ liệu mới từ vnstock;
- sinh báo cáo AI bằng DeepSeek;
- xuất Google Sheets/Google Drive;
- gửi cảnh báo Discord.

Khi cần dùng API, sao chép file:

```text
.env.example
```

thành:

```text
.env
```

rồi điền key riêng của người dùng vào `.env`.

Không gửi file `.env` cho người khác nếu trong đó có key thật.

## 7. Lỗi thường gặp trên Windows

### Không tìm thấy Python

Thông báo thường gặp:

```text
Khong tim thay Python
```

Cách xử lý:

1. Cài Python 3.11+.
2. Khi cài, tick `Add python.exe to PATH`.
3. Đóng cửa sổ đang chạy.
4. Mở lại `Chay_Dinh_Gia_VN100_Windows.bat`.

### Windows SmartScreen chặn file

Nếu Windows hiện cảnh báo:

```text
Windows protected your PC
```

Bấm:

```text
More info -> Run anyway
```

### Cài thư viện lâu hoặc lỗi mạng

Lần đầu chạy cần internet để cài thư viện. Nếu mạng yếu, đóng cửa sổ và chạy lại
file `.bat`; hệ thống sẽ tiếp tục dùng môi trường đã tạo.

### Cổng 8502 đang bị chiếm

Nếu app báo port/cổng đang được dùng, hãy đóng cửa sổ terminal cũ đang chạy app,
rồi mở lại launcher.

## 8. Cách sử dụng cơ bản

1. Mở app tại `http://localhost:8502`.
2. Chọn mã cổ phiếu ở thanh bên trái.
3. Kiểm tra báo cáo tài chính, giả định và kết quả định giá.
4. Xem biểu đồ kỹ thuật trong tab kết quả định giá.
5. Chỉ bấm `Sinh báo cáo qua DeepSeek` khi thật sự cần báo cáo AI để tiết kiệm
   chi phí API.

Kết quả từ hệ thống là công cụ hỗ trợ phân tích, không phải khuyến nghị đầu tư
bắt buộc mua/bán.
