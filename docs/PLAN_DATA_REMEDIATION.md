# Kế hoạch khắc phục dữ liệu và độ tin cậy định giá VN100

Ngày lập: 31/08/2026. Trạng thái: ĐÃ TRIỂN KHAI GIAI ĐOẠN AN TOÀN
(01/09/2026); các xung đột nguồn còn lại tiếp tục bị chặn, chưa ghi đè BCTC.

Kết quả triển khai và giới hạn còn lại nằm tại `docs/DATA_REMEDIATION_REPORT.md`.
Đây không phải chứng nhận mọi mã đều đủ điều kiện định giá hoặc khuyến nghị mua.

## 1. Kết quả kiểm tra

Nguồn nội bộ: `.vn100_ranking/history/20260831T222809-04d93372.json`, hoàn thành
22:36:25 ngày 31/08/2026, giờ Việt Nam; `vn100_full.db` là DB được cấu hình cho
cả đọc và ghi. Không suy rộng rằng PostgreSQL khác đã đồng bộ với bản này.

| Quan sát | Kết quả | Diễn giải đúng |
|---|---:|---|
| Mã có ít nhất một dòng cho từng báo cáo BS, IS, CF quý II/2026 | 100/100 | Có báo cáo trong kho, chưa chứng minh đủ mọi chỉ tiêu hoặc đúng nguồn |
| Dòng BCTC thuộc 100 mã | 468.752 | Khối lượng dữ liệu không đồng nghĩa chất lượng |
| Dòng có ngày công bố được lưu | 42 | Thiếu metadata nghiêm trọng, không có nghĩa doanh nghiệp chưa công bố |
| Mã được xếp hạng tạm / không xếp hạng | 51 / 49 | Không phải 49 báo cáo gốc đã được xác nhận sai |
| Mã có cảnh báo sai lệch EBIT | 25 | Cần tách lỗi định nghĩa, ánh xạ và sai số nguồn |
| Mã có cảnh báo sai lệch lợi nhuận gộp | 13 | Có nhiều CTCK, cần kiểm tra cấu trúc báo cáo riêng |
| Mã có cảnh báo sai lệch lợi nhuận trước thuế ngân hàng | 1 | Cần đối chiếu chỉ tiêu và kỳ báo cáo |
| Mã có giá trị hợp lý thiếu hoặc không dương | 6 | Có thể do kinh tế doanh nghiệp hoặc mô hình, không tự sửa thành dương |
| Mã mang cờ định giá thay thế VALUATION_PROXY | 20 | Cần dữ liệu chuyên ngành, không chỉ tải thêm ba BCTC |
| Mã có cảnh báo lãi suất đầu vào cũ | 100 | Điểm chung có thể ảnh hưởng cả rổ |
| Phiên giá kiểm tra, tối đa 20 phiên gần nhất mỗi mã đến 28/08 | 2.000 | Có khối lượng nhưng không có trường giá trị giao dịch và giá trị mua bán ròng ngoại |
| Ngân hàng có NPL/LLR được đưa vào snapshot | 0/18 | Thiếu ở đầu vào xếp hạng; chưa kết luận thuyết minh gốc không có |
| Mã có xác nhận quản trị và golden hợp lệ | 0 | Kho bằng chứng chưa điền, không phải mọi doanh nghiệp đều kém |

Các nhóm lỗi có thể trùng nhau, không cộng các hàng để tính số mã lỗi.
Toàn bộ 100 mã được ghi kỳ mới nhất Q2/2026 nhưng 98 mã bị gắn nhãn
"BCTC cũ hoặc chưa rõ ngày công bố". Nhãn hiện tại trộn hai vấn đề khác nhau.

Môi trường `/usr/local/bin/python3`: vnstock 4.0.4, vnai 2.4.9; requirements
yêu cầu tương ứng từ 4.0.6 và 2.5.7. Có cấu hình API key, nhưng không tìm thấy
module `vnstock_data` trong môi trường này. Chưa xác thực hạng tài trợ hoặc quyền
truy cập thực tế, không yêu cầu mua lại gói trước khi kiểm tra.

## 2. Nguyên nhân cần sửa trước khi tải hàng loạt

| Vị trí | Phát hiện từ code | Biện pháp đề xuất |
|---|---|---|
| `valuation/ingest/normalizer.py` | Không giữ ngày công bố; gán mặc định hợp nhất, VND, chưa điều chỉnh | Hợp đồng dữ liệu riêng theo nguồn; giữ scope, đơn vị, ngày công bố thực, trạng thái bản điều chỉnh; thiếu thì ghi chưa xác minh |
| `valuation/data_access/repo.py` | Chuyển số thiếu thành 0; lợi nhuận bằng 0 có thể bị thay bằng ước tính sau thuế | Phân biệt thiếu, 0 thật, số báo cáo và số tính lại; không dùng lợi nhuận ước tính như số lịch sử |
| Cùng loader | Bỏ scope, nguồn, đơn vị trước khi ghép kỳ; tìm chỉ tiêu bằng từ khóa gần đúng | Chọn bản hợp nhất đúng kỳ/nguồn; bảng ánh xạ có version theo ngành; đối chiếu khi có nhiều ứng viên |
| Loader và `valuation/report/verified_summary.py` | Loader đổi cách lấy EBIT khi lợi nhuận lõi không dương nhưng bộ kiểm tra vẫn yêu cầu cùng một đẳng thức | Chuẩn hóa định nghĩa EBIT theo mô hình; lập bảng đối chiếu các khoản tạo chênh lệch; giữ nguyên lỗ thật |
| Bộ kiểm tra | Mọi công ty không phải ngân hàng dùng kiểm tra doanh thu/giá vốn kiểu phi tài chính | Quy tắc riêng cho CTCK, bảo hiểm; không hạ ngưỡng hoặc bỏ kiểm tra chỉ để hết cảnh báo |
| `valuation/ingest/pipeline.py` | BCTC trùng khóa dùng DO NOTHING | Tải lại không sửa bản cũ; cần quy trình bản điều chỉnh có bằng chứng, giữ lịch sử và khả năng rollback |
| `upsert_prices` trong cùng file | Cập nhật mọi cột ngoài khóa, dù payload chỉ có OHLCV | Test tái hiện trước; chỉ cập nhật các trường thuộc payload, tránh xóa giá trị giao dịch/dòng tiền đã có |
| `valuation/services/ranking_sources.py` | Đợt cập nhật hiện chỉ bổ sung OHLCV, không nạp turnover/flows | Bổ sung nguồn đúng trường và lịch riêng, không thay số thiếu bằng 0 |
| `valuation/data_access/investment_snapshot.py` | Thiếu ngày ở bất kỳ dòng lịch sử hoặc lỗi kế toán cũ có thể chặn mã | Tách chất lượng đầu vào thực sự dùng định giá hiện tại và khả năng kiểm thử lịch sử; vẫn chặn mọi lỗi trọng yếu đang được dùng |
| `config/investment_evidence.json` | Danh mục bằng chứng trống; NPL/LLR chỉ lấy từ đây | Nối dữ liệu xác minh chuyên ngành vào bộ chấm điểm; bằng chứng định tính có nguồn/ngày/người duyệt |

## 3. Triển khai theo thứ tự

### Giai đoạn 1: Ngăn phát hành sai và sửa lỗi xử lý

- Sao lưu DB nhất quán, cấu hình giả định, snapshot; lưu checksum và thử phục hồi
  trên bản sao. Chốt DB nguồn chuẩn, kiểm tra mọi luồng UI/CLI dùng đúng kho.
- Tạo ma trận 100 mã: trường cần thiết, kỳ, nguồn, đơn vị, ngày công bố, ngày tải,
  bản điều chỉnh, mức độ ảnh hưởng, người chịu trách nhiệm xác minh.
- Dùng chung kết quả kiểm tra cho tab từng mã, bảng VN100 và file xuất. Mã lỗi
  trọng yếu vẫn hiện lý do nhưng không phát hành giá mục tiêu/khuyến nghị như đã xác minh.
- Viết test tái hiện số 0 thật, thiếu chỉ tiêu, sai scope/đơn vị, nhầm dòng chỉ tiêu,
  EBIT âm, BCTC CTCK, giá cập nhật làm mất flows trước khi sửa code.
- Sửa TTM: cộng đúng bốn quý độc lập đối với dòng thu nhập/lưu chuyển; tách số
  lũy kế; bảng cân đối dùng số cuối kỳ, không cộng bốn quý. Thiếu kỳ phải báo thiếu.
- Tách ngày kết thúc kỳ, ngày công bố và ngày tải. Không lấy ngày tải để giả làm
  ngày công bố. Với kiểm thử lịch sử, chỉ dùng thông tin đã công bố tại thời điểm đó.
- Không biến thiếu metadata thành khẳng định BCTC lỗi thời; không bỏ qua lỗi cũ
  nếu kỳ đó vẫn dùng tính tăng trưởng, lợi nhuận bình quân hoặc giả định.

### Giai đoạn 2: Khôi phục nguồn và bổ sung dữ liệu cần thiết

- Xác minh môi trường Python của app và worker; kiểm tra quyền của key đang có,
  dùng SDK đúng gói đã mua nếu được cấp quyền. Kiểm thử trên môi trường/bản sao
  trước khi đổi phiên bản đang phục vụ; không nâng cấp mù hoặc thêm dịch vụ trả phí.
- Dùng vnstock cho thu thập có cấu trúc; dùng BCTC, thuyết minh và công bố chính thức
  của doanh nghiệp/sở để đối chiếu. Mâu thuẫn phải đưa vào danh sách chờ duyệt,
  không chọn một nguồn im lặng. Báo cáo CTCK chỉ là tham khảo có ngày và giả định.
- Mục tiêu lịch sử: tối thiểu 5 năm/20 quý, đủ ba báo cáo và thuyết minh cần thiết;
  doanh nghiệp có lịch sử ngắn được ghi rõ, không dựng thêm năm giả.
- Điền chỉ tiêu theo mô hình, không yêu cầu mọi ngành có cùng bộ dữ liệu:

| Nhóm | Dữ liệu cần bổ sung hoặc xác minh |
|---|---|
| Toàn rổ | Tiền, nợ, vốn chủ sở hữu thuộc cổ đông mẹ, lợi nhuận thuộc cổ đông mẹ, lợi ích không kiểm soát, cổ phiếu lưu hành tại ngày định giá, số bình quân dùng cho EPS, thuế, khấu hao, CAPEX, vốn lưu động và CFO nếu mô hình cần |
| Ngân hàng | Nợ nhóm 3-5 và mẫu số phù hợp để tính NPL, dự phòng bao phủ nợ xấu LLR, NIM, CASA, CAR, tín dụng/tiền gửi; mỗi tỷ lệ có kỳ và định nghĩa |
| CTCK | Cho vay ký quỹ, nguồn vốn vay, tự doanh, lãi đã/chưa thực hiện, chi phí hoạt động, vốn chủ; không ép vào cấu trúc giá vốn của doanh nghiệp sản xuất |
| Dầu khí, vận tải, chu kỳ | Sản lượng/công suất, giá đầu vào, biên lợi nhuận qua chu kỳ, đội tàu/tài sản, hợp đồng và CAPEX; không kéo lợi nhuận một năm đột biến mãi về sau |
| Bất động sản | Dự án, tỷ lệ sở hữu, pháp lý, lượng đã bán/chưa bàn giao, chi phí còn lại, dòng tiền dự án và nợ để RNAV có cơ sở |
| Holding, đa ngành | Từng công ty con/mảng, tỷ lệ sở hữu, giá trị tài sản, nợ cấp holding, giao dịch nội bộ và lợi ích thiểu số để SOTP tránh tính hai lần |
| Bảo hiểm | Dự phòng nghiệp vụ, kết quả khai thác, danh mục đầu tư; chỉ dùng phương pháp có đủ dữ liệu công bố |
| Giá và sự kiện | Giá gốc/đã điều chỉnh có nhãn, giá trị giao dịch thực, khối lượng, flows nếu nguồn hỗ trợ, ngày giao dịch không hưởng quyền, tỷ lệ cổ tức/quyền mua, giá phát hành, ngày cổ phiếu bổ sung giao dịch |
| Vĩ mô | Lợi suất TPCP đúng kỳ hạn/ngày/loại chỉ tiêu; CPI, tăng trưởng, lãi suất và biến ngành cập nhật theo tần suất công bố |

- Không coi `giá đóng cửa x khối lượng` là giá trị khớp lệnh chính xác; nếu có dùng
  làm ước tính riêng phải gắn nhãn, không lặng lẽ cho qua tiêu chí thanh khoản thật.
- Giá đã điều chỉnh không được cộng thêm cổ tức/cổ phiếu thưởng lần nữa khi tính
  hiệu quả đầu tư. Các sự kiện cùng ngày cần tổng hợp; mốc so sánh 5/20 phiên ghi rõ.
- Dữ liệu không được công bố: ghi "chưa có nguồn", giữ mô hình thay thế ở trạng thái
  nghiên cứu, không dùng AI điền số hoặc đảm bảo mọi mã đều đủ điều kiện định giá.

### Giai đoạn 3: Đối chiếu mẫu rồi mở rộng VN100

- Đề xuất tám mã thử kỹ thuật: ACB, MBB, PVT, BSR, FPT, SSI, VHM, REE. Bao phủ
  ngân hàng, vận tải/dầu khí, chu kỳ, tăng trưởng, CTCK, RNAV, SOTP; không phải danh
  sách đề xuất đầu tư. Nếu thiếu công bố, thay mẫu hoặc giữ trạng thái thiếu rõ ràng.
- Đối chiếu từng đầu vào trọng yếu với đúng BCTC/thuyết minh, ghi URL/tệp/trang/kỳ,
  giá trị trước/sau, lý do, người duyệt; chênh lệch chỉ do làm tròn có ngưỡng riêng.
- Golden test định giá với Excel độc lập hoặc tài liệu ngoài có dữ liệu/giả định
  tương ứng. Sai số mặc định dưới 10% khi so cùng ngày, đơn vị, số cổ phiếu và giả
  định; không ép mọi kết quả giống giá thị trường hoặc giá mục tiêu CTCK bất kỳ.
- Xuất so sánh trước/sau cho giá mục tiêu, mô hình, giả định, các chỉ tiêu và nguyên
  nhân thay đổi. Chỉ sau khi mẫu đạt mới chạy từng lô VN100 có checkpoint và log lỗi.
- Đề xuất quy trình dữ liệu: bản nguồn bất biến -> bản chuẩn hóa có version ->
  kiểm tra -> phê duyệt bản điều chỉnh -> định giá. Mọi đổi schema/migration và
  sửa lịch sử phải trình duyệt riêng trước khi thực hiện; không ghi đè hàng loạt.

### Giai đoạn 4: Duy trì chất lượng và kiểm soát chi phí

- Giá cập nhật sau phiên đã đóng; BCTC và công bố kiểm tra chỉ mục/tệp mới theo
  nguồn, ETag/Last-Modified khi có, checksum và cache để tránh tải lại nội dung cũ.
- Kiểm tra lại kỳ gần đây để phát hiện restatement, không chỉ tìm quý mới. TTL
  không chứng minh dữ liệu mới nhất; khi nguồn lỗi phải giữ cả mốc cũ và cảnh báo.
- Tái sử dụng dữ liệu đã xác minh, nhưng xét lại khi nguồn/số liệu/giả định thay đổi.
  Điểm quản trị và lợi thế kinh doanh cần bằng chứng có ngày, không suy ra từ tên.
- Giữ lịch xếp hạng thứ Ba 09:30 giờ Việt Nam; dùng phiên giá đã hoàn tất và ghi
  mốc giá, BCTC, vĩ mô, kiểm chứng riêng. Chưa thay đổi automation trong đề xuất này.
- Python tính số và kiểm tra; DeepSeek chỉ giải thích, phản biện và tổng hợp bằng
  chứng. Không được sửa DB, tự tạo số thiếu hoặc tự xác nhận một mô hình đã đúng.
- Với một lượt cập nhật VN100 đã được yêu cầu, tối đa một yêu cầu AI chung cho
  hai chiến lược; cache theo dữ liệu/giả định/prompt/model, không gọi lại khi chỉ
  đổi tab hoặc mở giao diện. Giữ yêu cầu chỉ sinh báo cáo theo nút hoặc lịch đã duyệt.
- Không hứa chất lượng không đổi khi cắt nguồn. Tiết kiệm bằng chống lặp, tải tăng
  dần và kiểm tra bằng code; không cắt dữ liệu trọng yếu để giảm token.

## 4. Phạm vi file và nghiệm thu

File dự kiến: `valuation/ingest/vnstock_client.py`, `normalizer.py`, `pipeline.py`,
`valuation/data_access/repo.py` và module periodization liên quan,
`valuation/data_access/investment_snapshot.py`, `valuation/services/ranking_sources.py`,
`valuation/report/verified_summary.py`, cấu hình mapping/evidence/quality và các
view/export đọc kết quả kiểm tra. Thêm tests cho từng lỗi; không đổi model hoặc
schema trong bước đầu nếu chưa có đề xuất và phê duyệt tương ứng.

- [x] 100 mã có ma trận đầu vào, lỗi, nguồn và thời điểm, kể cả mã chưa đủ điều kiện.
- [x] Không còn thay số lịch sử thiếu/0 thật bằng ước tính không gắn nhãn trong loader đã sửa.
- [ ] Mọi số trọng yếu được xuất truy về nguồn và version giả định; lỗi đang ảnh
  hưởng định giá chặn phát hành, không chỉ thêm chú thích nhỏ sau khuyến nghị mua.
- [ ] Kiểm tra riêng từng ngành; thiếu dữ liệu khác doanh nghiệp kinh doanh kém.
- [ ] Mẫu đã có unit test tính tay và golden đối chiếu, báo cáo trước/sau được duyệt.
- [x] Chạy lại ingest hai lần không nhân bản, không làm mất flows/giá, không phá
  bản lịch sử; phục hồi được backup, thử trên bản sao trước.
- [x] Lint/type/test theo phạm vi sửa đạt; UI và Excel dùng chung trạng thái chất lượng.
- [x] Mở tab không gọi AI, đầu vào không đổi dùng cache, thất bại hiện rõ nguồn lỗi.
- [x] Không có API key, dữ liệu đăng nhập hoặc thư viện/tài liệu bị hạn chế tái phân
  phối trong Git; kiểm tra quyền trước khi phát hành gói dữ liệu cho khách hàng.

Mục tiêu là 100% mã được kiểm kê minh bạch, không phải 100% mã được gắn BUY hoặc
đủ điều kiện tích sản. Số liệu đúng vẫn có thể cho giá trị thấp, âm hoặc rủi ro cao.

## 5. Tài liệu nguồn bên ngoài đã tra cứu

- [Vnstock: so sánh vnstock và vnstock_data](https://vnstocks.com/docs/vnstock-data/gioi-thieu-vnstock-data):
  phân biệt bản miễn phí và tài trợ, giới hạn kỳ lịch sử, khả năng thuyết minh và
  cơ chế xác thực. Đây là cơ sở kiểm tra gói đang có, không chứng minh key đã hợp lệ.
- [HNX: thống kê giao dịch trái phiếu](https://www.hnx.vn/vi-vn/trai-phieu/thong-ke-giao-dich.html):
  nguồn đề xuất đối chiếu dữ liệu lợi suất. Chưa tải hoặc thay thế lãi suất trong DB.
