# Kế hoạch tab Xếp hạng VN100 & tích sản

Trạng thái: ĐÃ DUYỆT triển khai hai chiến lược; lịch thứ Ba 09:30 giờ Việt Nam.
Host tạm dùng máy Mac hiện tại; không cam kết chạy khi máy tắt/ngủ.
Lưu snapshot dạng tệp có version ở giai đoạn này để không đổi schema DB.
Hai nhóm Thận trọng và Tăng trưởng hiển thị riêng, mỗi nhóm tối đa 7 mã;
không coi các mã nằm ở cả hai nhóm là hai khoản đa dạng hóa độc lập.
Ngày lập: 31/08/2026.

## 1. Mục tiêu và phạm vi

- Thêm tab thứ năm: "VN100 & tích sản", cùng tone và font với giao diện hiện tại.
- Xếp hạng cơ hội đầu tư trong rổ VN100; lựa chọn 5-7 ứng viên nắm giữ trung,
  dài hạn dựa trên định giá, chất lượng, sức khỏe tài chính và bằng chứng kinh doanh.
- Không coi upside là xác suất sinh lời, điểm số là xác suất an toàn, hoặc cổ phiếu
  đầu ngành đương nhiên đáng mua ở mọi mức giá. Không cam kết bảo toàn vốn/lợi nhuận.
- Mốc đề xuất để duyệt: trung hạn 12-24 tháng, tích sản chính 3-5 năm.
- Không tự mua/bán, không tích hợp tài khoản giao dịch và không phân bổ tiền thật.
- Màn hình VN100 độc lập với mã đang chọn; chưa chọn mã vẫn xem được toàn rổ.

## 2. Cơ sở có sẵn và phần cần bổ sung

- valuation/engine/batch.py đã định giá từng mã qua cùng lõi valuate với giao diện.
- valuation/ingest/weekly_updater.py đã có ingest tăng dần và thu thập CTCK, nhưng
  không phải lịch tự chạy vào thứ Ba; một số bước báo thành công dù có mã lỗi.
- streamlit_app.py chỉ kiểm tra độ cũ khi mở, không tự quét VN100 khi khởi động.
- valuation/report/verified_summary.py có kiểm tra xác định bằng Python và cache
  theo dấu vân tay nội dung; tái sử dụng cơ chế, không dùng báo cáo một mã cho cả rổ.
- Chưa thấy kho bằng chứng có cấu trúc cho thương hiệu, thị phần, lợi thế cạnh tranh
  và lịch sử danh sách tích sản. Không suy ra những mục này từ tên doanh nghiệp.
- Một số cờ quản trị mặc định false/chỉ số mặc định 0; cần phân biệt thiếu dữ liệu
  với đã kiểm tra và không phát hiện vấn đề, không cho điểm an toàn từ giá trị mặc định.

## 3. Bố cục màn hình

### Đầu tab

- Thời điểm hoàn thành định giá, phiên giá sử dụng, kỳ BCTC, thời điểm kiểm tra tin,
  thời điểm tạo nhận định AI, lịch chạy tiếp theo, số mã đạt/thiếu/lỗi.
- Một nút chính: "Định giá VN100 & cập nhật tích sản".
- Lần cập nhật chạy nền, có tiến độ và lỗi theo mã; bản thành công trước vẫn xem được.
- Xem lịch sử các tuần và xuất bảng Excel/CSV kèm thời điểm và nguồn.

### Bảng toàn VN100

- Hạng, thay đổi hạng, mã/tên/ngành, thị giá, giá hợp lý Base, chênh lệch %, biên an toàn,
  điểm định giá, điểm tổng hợp, mức rủi ro, chất lượng dữ liệu, cập nhật gần nhất.
- Mặc định điểm cơ hội tổng hợp giảm dần; có cách sắp theo định giá/biên an toàn.
- Mã không đủ điều kiện vẫn hiện trong bảng với lý do "Chưa đủ dữ liệu/Không xếp hạng",
  không biến lỗi hoặc thiếu dữ liệu thành điểm thấp giả tạo.
- Mỗi mã mở phân tích hiện có và hiển thị giả định của chính bản xếp hạng để đối chiếu.
- Lọc ngành, trạng thái và độ mới; bảng rộng cuộn riêng, không tải lại khi đổi bộ lọc.

### Danh sách tích sản

- 5-7 mã đạt điều kiện; nếu chỉ có ít hơn thì hiển thị ít hơn và nêu lý do.
- Đề xuất đa dạng ít nhất 3 ngành, tối đa 2 mã/ngành; không hạ chuẩn để lấp đủ danh sách.
- Ba trạng thái rõ: "Có thể cân nhắc mua từng phần", "Doanh nghiệp tốt, chờ giá",
  "Chưa phù hợp tích sản". Top tích sản không lấy mã tốt nhưng giá đắt để lấp chỗ.
- Mỗi mã: lý do chọn, bằng chứng đầu ngành/thương hiệu, sức khỏe tài chính, chất lượng
  lợi nhuận, định giá và vùng giá xem xét mua theo biên an toàn có cấu hình.
- Luận điểm trung hạn và dài hạn riêng; kịch bản tốt/cơ sở/xấu, yếu tố thúc đẩy,
  rủi ro mất vốn, phản biện mạnh nhất, điều kiện làm luận điểm không còn đúng.
- Ghi rõ cổ tức tiền mặt, pha loãng/quyền mua nếu có nguồn; không coi cổ tức cổ phiếu
  tự tạo lợi nhuận và không cộng trùng vào lợi suất đã điều chỉnh.
- So với tuần trước: giữ nguyên, thêm mới, loại khỏi danh sách và lý do.
  Rớt hạng nhẹ không tự thành khuyến nghị bán, tránh đổi danh sách vô cớ mỗi tuần.

## 4. Phương pháp tuyển chọn để duyệt

### Bước A: kiểm soát bắt buộc

- Đơn vị, hợp nhất, TTM, số cổ phiếu/pha loãng, điều chỉnh quyền, thời điểm công bố.
- Độ mới của giá/BCTC/vĩ mô và bằng chứng doanh nghiệp được kiểm tra riêng.
- Mô hình đúng ngành, ba kịch bản, đối chiếu batch và UI cùng giả định/phiên giá.
- Kết quả NOT_RATED, proxy vô lý, thiếu nguồn trọng yếu, cờ rủi ro nghiêm trọng hoặc
  mô hình chưa được kiểm chứng phù hợp: không được đưa vào nhóm tích sản.
- Thiếu dữ liệu không được coi là không có rủi ro. Hiển thị mức độ bao phủ thông tin.

### Bước B: chấm điểm minh bạch bằng Python

Trọng số khởi tạo cho hai chiến lược, chưa được chứng minh tối ưu; lưu cấu hình có version.

| Nhóm tiêu chí | Thận trọng | Tăng trưởng |
|---|---:|---:|
| Định giá hấp dẫn | 30% | 25% |
| Chất lượng kinh doanh | 20% | 30% |
| Sức khỏe tài chính | 25% | 10% |
| Lợi thế cạnh tranh | 15% | 20% |
| Vĩ mô và tin doanh nghiệp | 5% | 10% |
| Dòng tiền giao dịch | 5% | 5% |

Quản trị và đối chiếu golden là điều kiện bắt buộc, không được bù bằng điểm cao.
Biên an toàn tối thiểu: Thận trọng 25%, Tăng trưởng 15%.

- Chuẩn hóa chỉ tiêu theo ngành, không so trực tiếp ROE/PB các ngành khác nhau.
- Doanh nghiệp thường: xem CFO, lợi nhuận, ROIC và nợ; ngân hàng: dùng các thước đo
  phù hợp như NPL, LLR, CAR, CASA, NIM khi có dữ liệu, không áp FCFF/net debt chung.
- Dòng tiền hoạt động kinh doanh khác dòng tiền mua bán cổ phiếu. Khối lượng tăng
  không phải bằng chứng chắc chắn về "tiền thông minh" hay hoạt động mua gom.
- Chỉ tiêu thiếu trọng yếu chặn đề xuất; thiếu thứ yếu làm giảm độ tin cậy theo
  quy tắc cố định, không tự bỏ trọng số rồi vô tình nâng điểm doanh nghiệp thiếu dữ liệu.
- Mỗi điểm có thành phần, dữ liệu nguồn, ngày và quy tắc để truy vết.

## 5. Thu thập thông tin và DeepSeek

- Nguồn chính: BCTC/công bố chính thức của doanh nghiệp, sở giao dịch; vnstock và
  dữ liệu CTCK đang có là nguồn bổ sung. Tin phải lưu URL, ngày công bố, ngày thu thập.
- Lần đầu dựng hồ sơ cho toàn VN100 trong phạm vi nguồn truy cập được; các lần sau
  chỉ lấy BCTC/tin mới, chống trùng theo nội dung và URL. Hồ sơ thiếu được công bố rõ.
- Lợi thế cạnh tranh/thương hiệu là hồ sơ dài hạn cập nhật khi có thông tin mới,
  không tải lại toàn bộ báo cáo thường niên mỗi tuần. Tin tức không tự sửa số BCTC.
- Dùng Python lọc ứng viên định lượng trước, đề xuất gửi DeepSeek 15-20 mã đạt chuẩn
  tốt nhất cùng bối cảnh vĩ mô và danh sách tuần trước, trong ngân sách token cố định.
- DeepSeek đánh giá bằng chứng, phản biện, đề xuất 5-7 mã và lý do loại ứng viên;
  Python kiểm tra đầu ra, mã hợp lệ, nguồn, giới hạn ngành và các điều kiện bắt buộc.
- AI không bịa nguồn, sửa số liệu gốc, tính thay engine hoặc vượt cờ chặn.
- Nhận định định tính và dữ kiện tách riêng. Tin tiêu cực chưa kiểm chứng gắn nhãn
  cần kiểm tra; thiếu bằng chứng không tự cho điểm đầu ngành/thương hiệu cao.
- Tối đa MỘT yêu cầu API sinh nhận định cho một đợt có dữ liệu thay đổi; dùng model
  đã cấu hình ở mức phù hợp. Không tự nâng model hoặc gọi nối tiếp để sửa JSON.
- Không kích hoạt các lời gọi AI ẩn từ bộ thu thập báo cáo hoặc bản tin vĩ mô trong job này.
- Nội dung/nguồn/giả định/cấu hình/prompt/model không đổi thì dùng cache, không gọi API.
  Không đưa thời điểm kiểm tra đơn thuần vào khóa cache. Dữ liệu giá có thay đổi là
  thay đổi thực; không gọi báo cáo cũ là đã được AI đánh giá lại theo giá mới.
- Khi lỗi, hết tiền hoặc JSON không đạt: bảng Python có thể cập nhật, nhưng AI mới
  mang trạng thái thất bại/chưa có. Bản cũ hiển thị riêng với ngày cũ; không gắn nhãn mới.
- Ghi model, token, cache hit; chỉ ước tính chi phí nếu có bảng giá cấu hình được kiểm chứng.
- Việc rút gọn nguồn có đánh đổi; không hứa một lần gọi luôn bằng chất lượng đọc toàn bộ
  báo cáo 100 mã. Kiểm tra mẫu trước khi chốt giới hạn nội dung.

## 6. Lịch và hiệu năng

- Đã duyệt thứ Ba 09:30, Asia/Ho_Chi_Minh; dùng giá phiên đã kết thúc trước ngày chạy.
- Dùng cùng một job cho lịch và nút bấm; khóa chống chạy trùng giữa phiên trình duyệt,
  nút thủ công và lịch tuần. Có checkpoint, giới hạn tốc độ, thử lại dữ liệu từng mã.
- Khóa lịch theo tuần và version cấu hình; chỉ công bố snapshot mới sau khi kiểm tra.
- Nghỉ lễ: dùng phiên gần nhất và hiển thị ngày; máy tắt/lỡ lịch: chạy bù một đợt
  sau khi hoạt động lại, không dồn chạy tất cả tuần đã bỏ lỡ.
- Mở tab chỉ đọc snapshot, không tự gọi DeepSeek. Chỉ worker/lịch được duyệt hoặc
  nút cập nhật mới được khởi chạy cập nhật.
- Scheduler giai đoạn này: Codex heartbeat trên máy Mac hiện tại, gọi CLI Python;
  không thay stack hay dựng n8n mới. Không cần mở tab Streamlit nhưng máy/Codex phải
  hoạt động. Không cam kết đúng giờ hay chạy bù khi máy tắt/ngủ; có nút cập nhật bù.
- Bản tải về máy khách mặc định chỉ đọc snapshot; không tự kích hoạt lịch cho mọi
  máy dùng chung API key, tránh mỗi khách hàng phát sinh một đợt tính phí hàng tuần.

## 7. Lưu trữ và triển khai

- Snapshot bất biến từng lần chạy: thành phần VN100 tại thời điểm chạy, giá/nguồn,
  định giá/giả định/model version, điểm thành phần, lựa chọn AI, lỗi và trạng thái job.
- Giai đoạn này giữ nguyên schema PostgreSQL/SQLite. Snapshot đầu ra lưu tệp có version
  tại `.vn100_ranking/`, chỉ là sản phẩm dẫn xuất, không thay DB nguồn sự thật.
- Lần lỗi không xóa lịch sử hay ghi đè snapshot thành công; portable chứa bản công
  bố đã làm sạch, không kèm secret hoặc phát tán toàn văn báo cáo có bản quyền.
- Module dự kiến: valuation/analysis/investment_ranking.py,
  valuation/report/accumulation_review.py, valuation/views/vn100_ranking.py,
  dịch vụ job trong valuation/services/, CLI scripts/update_vn100_ranking.py.
- Tích hợp có phạm vi: streamlit_app.py, config chấm điểm, batch engine hiện có,
  data_access, schema/migration sau duyệt và scheduler được lựa chọn.

## 8. Các đợt thực hiện và nghiệm thu

1. Kiểm kê dữ liệu và xây quy tắc điểm/điều kiện chặn; mẫu tính tay và dữ liệu có nguồn.
2. Bảng toàn VN100 và snapshot; kiểm tra batch/UI cùng dữ liệu cho kết quả trùng nhau.
3. Hồ sơ doanh nghiệp/tin tức và DeepSeek chọn lọc; kiểm chứng từng mã trong danh sách.
4. Nút chạy nền, cache và lịch; thử chạy lại, lỗi API, nguồn chậm, máy bỏ lỡ lịch.
5. Kiểm tra giao diện desktop/mobile, xuất Excel, portable rồi mới phát hành GitHub.

- Golden test cho các mô hình được dùng để đề xuất, đối chiếu số với nguồn ngoài
  và ngưỡng của dự án; thiếu golden không tuyên bố mô hình đã được xác nhận.
- Test không xếp hạng dữ liệu lỗi, không coi mặc định 0/false là đã kiểm chứng,
  điểm có thể tính tay, thiếu dữ liệu không nâng điểm, không ép đủ 5-7 mã.
- Test cùng bộ dữ liệu/cấu hình cho cùng kết quả; cùng giờ chốt giá cho toàn rổ,
  version giả định nhất quán, không trộn dữ liệu tương lai hoặc thành phần rổ lịch sử.
- Test click liên tục/nhiều người dùng/lịch đồng thời chỉ tạo một job và tối đa một
  yêu cầu AI cho cùng nội dung; báo cáo lỗi/truncated không được công bố như hoàn chỉnh.
- Test reset hoặc mở lại tab không gọi AI; AI lỗi không gây mất bảng xếp hạng cũ.
- Tích sản không đảo danh sách chỉ vì điểm dao động nhỏ; lưu lý do mọi lần thay đổi.
- Điểm số cần kiểm định độ nhạy trước phát hành. Đánh giá lợi suất thực tế về sau
  phải theo các snapshot đã có, không hồi tố sửa để làm đẹp thành tích.

## 9. Đã chốt và giới hạn bản đầu

- Người dùng duyệt 3-5 năm, kèm 12-24 tháng; triển khai cả hai chiến lược riêng biệt.
- Lịch thứ Ba 09:30, một lượt DeepSeek cho cả hai chiến lược khi nội dung thay đổi.
- Bộ kiểm tra đầu tiên chạy đủ 100 mã; 51 mã đủ cơ sở tính điểm sơ bộ, 49 mã không
  được xếp hạng do lỗi BCTC/mô hình/định giá proxy. Chưa mã nào đủ điều kiện tích sản.
- DeepSeek phản biện thành công 5 ứng viên mỗi chiến lược, vẫn gắn nhãn cần kiểm chứng.
- Hồ sơ thương hiệu/quản trị/golden cần analyst bổ sung có nguồn; không tự tạo chứng nhận.
- Tin hiện lấy tiêu đề, URL và ngày qua RSS; không tuyên bố đã đọc toàn văn BCTC/
  báo cáo thường niên/tin của cả 100 doanh nghiệp. Macro dùng DB và cảnh báo độ cũ,
  không tự sửa chuỗi vĩ mô trong phạm vi này. Xem `VN100_TICH_SAN.md` để vận hành.
