# VN100 & tích sản

## Cách sử dụng

1. Mở tab **VN100 & tích sản**. Không cần định giá từng mã trước.
2. Chọn **Tích sản thận trọng** hoặc **Tích sản tăng trưởng**. Hai bộ trọng số khác nhau.
3. Đọc thời điểm hoàn thành, phiên giá, kỳ BCTC và các điều kiện chưa đạt.
4. Xem danh sách qua bộ lọc, rồi mở từng ứng viên để đọc góc nhìn 12-24 tháng,
   3-5 năm, kịch bản giá, rủi ro, điều kiện bỏ luận điểm và nguồn.
5. Bảng toàn VN100 cho phép lọc ngành và sắp theo điểm, chênh lệch hoặc biên an toàn.
6. **Xuất Excel hai chiến lược** tạo bảng và nhận định AI kèm trạng thái/nguồn.
7. **Định giá VN100 & cập nhật tích sản** chạy nền, kiểm tra dữ liệu và tạo nhận định.
   Có thể mất vài phút khi phải tải nguồn. Mở tab/đổi bộ lọc không chạy cập nhật.

"Chờ kiểm chứng" không phải khuyến nghị mua. Giá hợp lý không phải giá chắc chắn đạt
được, điểm số không phải xác suất sinh lời. Không có cam kết bảo toàn vốn. Hai nhóm
có thể trùng mã; không coi chúng là hai danh mục đa dạng hóa độc lập.

## Lịch và chi phí

- Lịch cài trên máy Mac của chủ dự án bằng Codex: thứ Ba 09:30 giờ Việt Nam.
- Máy và Codex cần hoạt động. Không cam kết chạy đúng giờ khi máy ngủ/tắt.
- Máy khách tải GitHub không tự có lịch này. Không để mọi khách hàng cùng chạy lịch
  với một API key dùng chung. CLI chạy được trên Mac/Windows, lịch phải cài theo host.
- Dùng giá đóng cửa trước ngày chạy; lúc 09:30 không dùng giá phiên còn đang giao dịch.
- Một yêu cầu DeepSeek cho **cả hai** chiến lược, chọn model từ cấu hình hiện có.
- Mỗi chiến lược tối đa 7 mã, tối đa 2 mã/ngành. Python ưu tiên phân tán ngành trước
  khi gửi AI. Không ép đủ số lượng khi dữ liệu hoặc định giá không đạt.
- Hồ sơ nguồn được rút gọn cho shortlist và tối đa 40 tiêu đề RSS. Điều này không
  tương đương việc đọc toàn văn mọi báo cáo của 100 mã.
- Cùng đầu vào/model/prompt dùng cache; lỗi/timeout cũng được ghi để không tự gọi lại.
  Bản lỗi không được thay bằng nội dung AI cũ gắn ngày mới. Đầu vào vượt ngân sách
  hoặc đầu ra không đạt schema: giữ bảng Python, báo AI chưa hoàn thành.
- Giới hạn một yêu cầu áp dụng cho job VN100 này. Nút sinh báo cáo từng mã và nút
  làm mới bản tin vĩ mô là tác vụ riêng do người dùng chủ động bấm.

## Dữ liệu và công thức

- Lõi `build_company_data` + `valuate` hiện có; Base/Bear/Bull dùng bản sao độc lập.
- Phiên giá và giả định trong snapshot có thể khác hồ sơ đang chỉnh thủ công ở tab định giá.
- Biên an toàn = `1 - giá / giá hợp lý`. Chênh lệch = `giá hợp lý / giá - 1`.
- Ví dụ tính tay: giá 75, giá hợp lý 100 => biên an toàn 25%, chênh lệch 33,33%.
- Điểm = tổng `điểm thành phần × trọng số / 100`. Thiếu chỉ tiêu không chia lại trọng
  số để nâng điểm. Phải đọc kèm độ phủ; điểm thiếu nguồn chỉ là mức sàng lọc sơ bộ.
- ROE dùng lợi nhuận FY / vốn chủ bình quân đầu-cuối FY; CAGR không ghép FY với TTM.
  ROE/tăng trưởng so cùng nhóm ngành khi đủ mẫu, nếu không dùng thang cố định công khai.
- Ngân hàng không dùng nợ/vốn hay CFO như doanh nghiệp thường; cần NPL/LLR có nguồn.
- Thanh khoản yêu cầu đủ 20 phiên giá trị giao dịch. Thiếu không ước đoán từ giá đóng cửa.
- Quản trị mặc định false không phải bằng chứng đã kiểm tra. Golden phải gắn dấu
  vân tay bộ đầu vào và nguồn đối chiếu, sai số dưới ngưỡng 10% theo cấu hình.
- Mã có lỗi đối chiếu BCTC, định giá proxy hoặc không đủ cơ sở: không có hạng/giá mục tiêu
  công bố ở bảng này; số thô chỉ giữ nội bộ để chẩn đoán.
- Dữ liệu giá mới chỉ INSERT; BCTC dùng DO NOTHING khi trùng khóa. Không sửa số cũ.
  Restatement/mâu thuẫn nguồn cần quy trình analyst riêng, không giao cho AI sửa.

## Hồ sơ analyst

`config/investment_evidence.json` lưu các hồ sơ đã duyệt, khóa theo ticker VN100.
Các trường: `reviewed_on` (YYYY-MM-DD), `reviewer`, `sources` (title/url HTTPS),
`governance_clear`, `scores` (moat/context, 0-100), `metrics` (npl/llr dạng tỷ lệ),
`golden` (input_hash/reference_url/relative_error). Dấu vân tay lấy từ chi tiết mã.
Chỉ điền từ tài liệu thật và kết quả kiểm chứng; không điền để vượt cờ chặn.
File ban đầu rỗng vì chưa có hồ sơ được xác minh. DeepSeek không có quyền sửa file này.

## Lưu trữ và CLI

DB PostgreSQL/SQLite vẫn là nguồn sự thật. `.vn100_ranking/` chứa snapshot dẫn xuất,
checkpoint theo mã, trạng thái nguồn và cache AI, không đổi schema hoặc xóa lịch sử.
Khóa OS ngăn hai tiến trình dùng cùng thư mục chạy đồng thời, tự nhả khi worker chết.
Khóa này không thay thế khóa phân tán cho nhiều máy chạy trên thư mục Google Drive
được đồng bộ riêng; chỉ cấu hình một host lịch chính.

```bash
python scripts/update_vn100_ranking.py
python scripts/update_vn100_ranking.py --scheduled
python scripts/update_vn100_ranking.py --no-refresh --no-ai
python scripts/update_vn100_ranking.py --export-portable
```

Lệnh cuối chỉ xuất `data/vn100_ranking_latest.json`, không gọi API. Bản tải GitHub
xem được snapshot đó dù chưa có key; dữ liệu DB đi kèm có kỳ cập nhật riêng.
Không phát tán toàn văn báo cáo có bản quyền hoặc `.env` khi đóng gói.

## Kiểm chứng ngày 31/08/2026

- Chạy toàn bộ 100 mã, 51 mã được tính điểm sơ bộ, 49 mã không xếp hạng.
- Chưa có mã qua đủ bộ lọc tích sản do thiếu hồ sơ/golden/thanh khoản và TPCP_10Y cũ.
- DeepSeek trả 5 ứng viên nghiên cứu mỗi nhóm trong một yêu cầu: 15.137 token vào,
  4.598 token ra. Không coi các ứng viên này là khuyến nghị mua đã duyệt.
- Gọi lại cùng nội dung dùng cache, kiểm tra số lời gọi mới bằng 0.
- Chưa có golden cho mọi mã; không tuyên bố bộ định giá hiện tại đã được xác nhận toàn rổ.
