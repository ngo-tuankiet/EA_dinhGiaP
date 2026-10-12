# Báo cáo khắc phục dữ liệu VN100

Ngày hoàn tất kiểm kê nguồn: 01/09/2026, giờ Việt Nam.

## Phạm vi đã làm

- Tạo backup nhất quán trước khi thao tác; kiểm tra phục hồi và checksum.
- Tải đủ 900 bộ dữ liệu có cấu trúc cho 100/100 mã: BS, IS, CF quý/năm,
  ratios, stats và giao dịch khối ngoại. Cache nguồn trả phí được giữ nội bộ,
  không đưa vào Git.
- Bổ sung 2.000 phiên dòng tiền ngoại gần nhất theo cơ chế upsert idempotent;
  chạy lại không nhân đôi và không xóa OHLCV, turnover hoặc tự doanh đã có.
- Sửa xử lý TTM/FY, dữ liệu thiếu, số 0/lỗ thật, metadata, restatement, đơn vị,
  aliases, bảng cân đối và dòng tiền. Không tự cân đối hay tự tạo lợi nhuận.
- Tách taxonomy tồn kho gộp, dự phòng và tồn kho ròng; định giá ưu tiên tồn kho
  ròng. Tách quy ước dấu chi phí khỏi xung đột số liệu và cho phép sai số làm
  tròn tối đa 0,1%.
- Chặn giá mục tiêu, upside, khuyến nghị và xuất báo cáo đầu tư khi đầu vào trọng
  yếu thiếu hoặc xung đột. Giá trị chẩn đoán nội bộ không được coi là khuyến nghị.
- DeepSeek không được gọi khi tải trang/đổi tab; lượt xử lý này không gọi AI.

## Kết quả đối chiếu

| Chỉ tiêu | Kết quả |
|---|---:|
| Mã đã kiểm kê | 100/100 |
| Bộ dữ liệu nguồn có cache | 900/900 |
| Ô trùng khớp | 60.138 |
| Ô chênh trong ngưỡng làm tròn | 18 |
| Ô trùng độ lớn nhưng khác quy ước dấu | 251 |
| Xung đột còn lại | 472 |
| Xung đột trực tiếp ảnh hưởng định giá | 72 ô / 7 mã |
| Lỗi hợp đồng dữ liệu nguồn | 0 |
| Mã vượt cổng dữ liệu và được phép hiển thị giá trị hợp lý | 66/100 |
| Mã bị chặn do xung đột, thiếu đầu vào, kiểm tra kế toán hoặc model | 34/100 |

Bảy mã còn xung đột trọng yếu là `BVH`, `DPM`, `DSE`, `PVT`, `REE`, `SSI` và
`TCH`. Hệ thống giữ nguyên dữ liệu cũ, không tự chọn nguồn thắng và không phát
hành khuyến nghị cho các mã này trước khi có đối chiếu filing/thuyết minh.

Bảng xếp hạng nội bộ đã được tính lại lúc 09:06 ngày 01/09/2026, dùng phiên giá
28/08/2026 và BCTC đến quý II/2026. Có 66 mã có giá trị hợp lý để xếp hạng sơ bộ,
nhưng chưa mã nào vượt toàn bộ bộ lọc bằng chứng để thành danh sách chính thức.
Mỗi chiến lược hiện chỉ hiển thị 7 ứng viên nghiên cứu; không gọi các ứng viên
chờ kiểm chứng này là khuyến nghị mua.

`NO_MATCHING_KEY` chỉ có nghĩa taxonomy nguồn mới chưa tìm thấy đúng khóa tương
ứng trong kho cũ; không tự động kết luận dữ liệu bị thiếu. Nếu trường đó thực sự
cần cho mô hình, cổng kiểm tra đầu vào riêng vẫn chặn phát hành.

## Tệp kiểm tra

- `temp_reports/data_quality_20260901/VN100_chat_luong_du_lieu.csv`: trạng thái
  từng mã và lý do không được phát hành.
- `temp_reports/data_quality_20260901/Doi_chieu_nguon.csv`: từng ô khác biệt,
  nguồn cũ/mới, tỷ lệ lệch và cờ ảnh hưởng định giá.
- `data/source_quality_status.json`: trạng thái gọn để bản portable và UI dùng;
  không chứa số liệu nguồn trả phí.

## Giới hạn còn lại

- Không ghi đè hàng loạt 72 ô trọng yếu vì schema hiện tại chưa lưu song song
  version nguồn/phê duyệt. Làm vậy sẽ phá khả năng truy vết và rollback.
- Lợi suất TPCP 10 năm trong DB vẫn cần đối chiếu số chính xác từ tệp công bố HNX
  mới nhất; không suy đoán số từ tiêu đề thông báo.
- Các model chưa có golden test độc lập hoặc dữ liệu chuyên ngành vẫn mang trạng
  thái chưa xác minh dù ba báo cáo tài chính đã có đủ tệp.
