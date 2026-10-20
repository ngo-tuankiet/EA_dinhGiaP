# Dữ liệu cổ tức, tăng vốn và quyền cổ đông

## Phạm vi

- Backfill toàn bộ VN100 trong 5 năm và giữ sự kiện đã công bố có ngày thực hiện
  trong 12 tháng tới.
- Nhóm sự kiện: cổ tức tiền mặt/cổ phiếu, cổ phiếu thưởng, quyền mua, ESOP,
  phát hành riêng lẻ, niêm yết bổ sung, chuyển đổi và các sự kiện vốn liên quan.
- `corporate_actions` giữ lịch sử theo khóa `(ticker, source_site,
  source_event_id)`. Bản ghi giống hệt không bị ghi lại; bản nguồn điều chỉnh được
  cập nhật kèm `content_hash` và `updated_at`.
- `corporate_action_sync` là checkpoint từng mã. Mã có trạng thái `OK` chỉ kiểm tra
  lại sau TTL 24 giờ; checkpoint `ERROR` được retry ngay.

## Nguồn và độ tin cậy

- `OFFICIAL`: VSDC/HOSE/HNX/UBCK hoặc IR doanh nghiệp đã có URL truy vết.
- `AGGREGATOR`: VCI qua `vnstock`, dùng để phát hiện và chuẩn hóa sự kiện trên
  diện rộng. Sự kiện chỉ có lớp này phải đối chiếu công bố chính thức trước quyết
  định đầu tư.
- Reader luôn lọc `announcement_date <= as_of_date` để chống lookahead. Sự kiện
  không có ngày công bố không được đưa vào phân tích tại một mốc lịch sử.

## Công thức cơ học

- Cổ tức tiền mặt: `Dividend yield = DPS / P`; giá tham chiếu lý thuyết
  `P_ex = max(P - DPS, 0)`.
- Cổ tức/cổ phiếu thưởng tỷ lệ `r`: `Shares_after = Shares * (1+r)` và
  `P_ex = P / (1+r)`. Đây là điều chỉnh cơ học, không tự tạo thêm giá trị.
- Quyền mua giá `K`, tỷ lệ `r`: `TERP = (P + r*K)/(1+r)`; giá trị quyền trên một
  cổ phiếu cũ `P - TERP`; vốn huy động `Shares*r*K`.
- Pha loãng EPS trước lợi nhuận mới: `1/(1+r)-1`. Nếu thiếu giá phát hành, mục
  đích vốn hoặc tỷ lệ, hệ thống trả `THIẾU DỮ LIỆU`, không tự đặt giả định.

## Cách đọc tác động giá

- Giao diện đặt các sự kiện **đã công bố trong 12 tháng tới** lên trước. Mỗi sự
  kiện giải thích bằng ví dụ người đang giữ 1.000 cổ phiếu: được nhận gì, phải nộp
  thêm bao nhiêu, tổng số cổ phiếu sau quyền và giá lý thuyết sau điều chỉnh.
- Cuối tab có lịch toàn VN100 cho 30 ngày tới. Lịch chọn mốc thực hiện gần nhất
  còn ở phía trước (GDKHQ, chốt quyền, thanh toán, đăng ký/mua hoặc niêm yết),
  nên vẫn hiển thị đợt cổ tức đã chốt quyền nhưng sắp đến ngày thanh toán.
- Bảng 30 ngày có cột `Nhận định nhanh`, kết hợp snapshot xếp hạng VN100 mới
  nhất với bản chất sự kiện. Cổ tức/quyền mua không được tự nâng một mã lỗi dữ
  liệu, chưa định giá được hoặc chưa qua bộ lọc thành khuyến nghị mua.
- Các mã chưa thể kết luận phải ghi đúng nguyên nhân: mô hình RNAV/SOTP còn là
  proxy, nguồn dữ liệu xung đột, kiểm tra BCTC không đạt hoặc chưa có định giá.
  Không gom mọi trường hợp vào một nhãn `Chưa đủ cơ sở` gây hiểu nhầm.
- Phân tích tác động giá trong quá khứ mặc định ẩn. Chuỗi giá và event study chỉ
  được đọc/tính khi người dùng bật công tắc xem chi tiết, giúp tab tải nhẹ hơn.
- Hệ thống không dự đoán sự kiện chưa công bố. Nếu thiếu tỷ lệ, giá phát hành hoặc
  mục đích vốn thì nêu thiếu dữ liệu thay vì tự điền giả định.
- Với sự kiện quá khứ, hệ thống dùng giá đóng cửa gần nhất trước ngày sự kiện và
  phiên đầu tiên từ ngày sự kiện trở đi. Kết quả tách thành: biến động giá thô,
  điều chỉnh cơ học, phản ứng so với giá lý thuyết và diễn biến sau 5/20 phiên.
- Cổ tức tiền mặt được cộng lại khi đo thay đổi tài sản cổ đông; cổ tức cổ phiếu
  và cổ phiếu thưởng được điều chỉnh theo số cổ phiếu mới. Nhờ vậy, mức giảm giá
  do tách quyền không bị gọi nhầm là thị trường phản ứng tiêu cực.
- Đây là event study mô tả, không phải kiểm định quan hệ nhân quả. Tin doanh
  nghiệp, biến động ngành và thị trường cùng thời điểm vẫn có thể chi phối giá.

## Số cổ phiếu khi dữ liệu thiếu ngày GDKHQ (D48)

- Nguồn sự kiện quyền (VCI) đôi khi có cổ tức CP/thưởng nhưng thiếu ngày GDKHQ. Engine bỏ qua
  các dòng này → giữ số cp cũ trong khi giá đã điều chỉnh quyền → giá trị/cp nhánh DCF bị phóng đại.
- Cách xử lý: thêm số cp sau sự kiện vào `config/corporate_actions.yaml` (`effective_date` = ngày
  GDKHQ, `source_url` VSDC). Khi VSDC chưa công bố số chính thức, dùng số đăng ký trước sự kiện ×
  (1 + tỷ lệ) và ghi "tạm tính" trong `note`; thay bằng số chính thức khi có.
- Cờ `CORPORATE_ACTION_UNDATED` nhắc khi một sự kiện như vậy (công bố trong 180 ngày) chưa có override.
- Quyền mua thiếu ngày GDKHQ mang cờ riêng `RIGHTS_ISSUE_UNDATED` (mức thông tin): quyền mua không vào hệ
  số chia (đi kèm tiền, chờ BCTC) nên không làm sai số cp; bảng xếp hạng không coi là lỗi dữ liệu (fx1).
- Định giá theo `as_of` quá khứ (golden/registry): giá `prices_daily` đã điều chỉnh lùi theo các đợt cổ tức
  CP/thưởng tới ngày giá cuối, nên `repo.get_shares_outstanding_repo` quy số cp tại `as_of` về cùng gốc giá
  (× (1 + Σ tỷ lệ cùng ngày) các đợt có GDKHQ trong (as_of, ngày giá cuối]). Quyền mua chưa quy đổi (TERP).
- KHÔNG quy đổi tay cả giá trị hợp lý theo tỷ lệ chia: nhánh bội số (P/E, EV/EBITDA lịch sử tính trên
  giá đã điều chỉnh) bất biến theo số cp; chỉ nhánh DCF thay đổi.

## DeepSeek và chi phí

- Mở tab hoặc refresh dữ liệu không gọi DeepSeek.
- Phân tích sự kiện được gộp vào đúng một API call khi người dùng bấm nút kiểm
  chứng và sinh báo cáo. Cùng response được tái sử dụng cho UI, PDF và Word.
- DeepSeek chỉ phản biện dữ liệu/công thức Python đã cung cấp; không được tự sửa
  DB hoặc bịa giá phát hành, mục đích sử dụng vốn hay nguồn chính thức.
