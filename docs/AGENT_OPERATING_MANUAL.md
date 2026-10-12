# Agent Operating Manual — Antigravity VN100

> File này dành cho mọi agent mới vào repo. Mục tiêu là hiểu hệ thống đang chạy
> thật, sửa đúng chỗ, không lặp lại lỗi dữ liệu/định giá đã gặp.

## 1. Đọc theo thứ tự này

1. `AGENTS.md`: luật nền bắt buộc.
2. `.agents/AGENT_HANDOFF.md`: checklist và lỗi đã gặp.
3. `.agents/rules/project-context.md`: trạng thái hiện hành của dự án.
4. File này: cách vận hành/sửa hệ thống thực tế.
5. Skill liên quan đến việc đang làm:
   - Dữ liệu/BCTC/giá/macro: `.agents/skills/financial-data-integrity/SKILL.md`
   - Định giá/model/ranking: `.agents/skills/valuation-models/SKILL.md`
   - Google Sheets 2 chiều: `.agents/skills/google-sheets-two-way/SKILL.md`
   - n8n: `.agents/skills/n8n-orchestration/SKILL.md`

## 2. Hệ thống đang chạy thật

- App chính là Streamlit: `streamlit_app.py`, chạy local cổng `8502`.
- Package nghiệp vụ chính: `valuation/`.
- Database đang dùng là SQLite portable:
  - `vn100_full.db`: file chạy local, không commit.
  - `vn100_full.db.gz`: bản nén được phép commit để khách tải về chạy được.
- Launcher:
  - macOS: `Chay_Dinh_Gia_VN100.command`
  - Windows: `Chay_Dinh_Gia_VN100_Windows.bat`
- `docs/spec.md` mô tả kiến trúc mục tiêu ban đầu. Không mặc định coi FastAPI,
  PostgreSQL hoặc n8n là đường chạy thật nếu người dùng không yêu cầu rõ.

## 3. Lệnh chạy nhanh

```bash
python -m streamlit run streamlit_app.py --server.port 8502 --server.headless true
```

Nếu cần kiểm tra health:

```bash
python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8502/_stcore/health', timeout=5).read().decode())"
```

Khi đóng gói dữ liệu portable:

```bash
python scripts/ensure_portable_db.py
gzip -t vn100_full.db.gz
```

## 4. Luồng dữ liệu chính

- `valuation/data_access/repo.py`: đọc DB, map field BCTC vào model nội bộ.
- `valuation/models/financials.py`: cấu trúc `Company`, kiểm tra model
  integrity.
- `valuation/analysis/`: phân tích/ranking/tích sản.
- `valuation/forecast/` và `valuation/engine/`: dự phóng và định giá.
- `valuation/report/`: báo cáo, AI narrative, DOCX/HTML export.
- `valuation/views/`: UI Streamlit.

Nếu thấy cảnh báo dữ liệu, tìm nguyên nhân từ nguồn/map/taxonomy trước, không
ẩn cảnh báo để giá mục tiêu nhìn đẹp hơn.

## 5. Các lỗi dữ liệu đã gặp

- **CFI/CFF và CapEx:** CFI đã bao gồm CapEx âm. Khi model cũng lưu CapEx riêng,
  `cf_other` phải dùng `_cashflow_other_excluding_capex()` để tránh trừ CapEx hai
  lần. Xem `valuation/data_access/repo.py`.
- **Ticker lọt vào tích sản khi dữ liệu yếu:** ranking dài hạn không được chỉ dựa
  vào upside. Mã có cờ dữ liệu trọng yếu, thiếu BCTC quan trọng, đòn bẩy/cashflow
  không kiểm chứng được phải bị chặn hoặc hạ cấp rõ lý do.
- **Corporate actions bị lặp:** không nhồi toàn bộ lịch sử cổ tức/quyền mua vào
  AI summary. Phần sự kiện chi tiết có tab riêng; AI summary chỉ nhắc sự kiện khi
  nó ảnh hưởng luận điểm đầu tư.
- **Báo cáo AI cũ còn trong cache:** khi đổi cấu trúc prompt/section, phải tăng
  cache version trong `valuation/report/verified_summary.py` và xoá/normalize
  session keys cũ.

## 6. DeepSeek

- Chỉ gọi khi người dùng bấm nút sinh báo cáo/kiểm chứng.
- Mỗi lần bấm tối đa một API call cho toàn bộ narrative liên quan.
- Mở app, đổi mã, đổi tab, refresh Streamlit không được gọi DeepSeek.
- Ranking VN100/tích sản chỉ gọi DeepSeek khi dữ liệu hoặc danh sách thay đổi;
  nếu snapshot chưa đổi thì dùng cache.
- DeepSeek không sửa DB. Nó chỉ nêu nghi vấn/cảnh báo dựa trên dữ liệu Python
  đưa vào.

## 7. Báo cáo AI hiện hành

AI summary trong tab BCTC chỉ nên có các phần:

- Luận điểm đầu tư
- Tổng quan doanh nghiệp
- Bối cảnh ngành
- Kỹ thuật, dòng tiền và vị thế thị trường
- Rủi ro và điểm cần theo dõi

Không tạo section riêng tên "Cổ tức, tăng vốn và quyền cổ đông" trong summary
AI vì phần đó đã có tab dữ liệu chi tiết riêng.

## 8. VN100 ranking và tích sản

- Có hai nhóm khuyến nghị: thận trọng và tăng trưởng.
- Không hạ tiêu chuẩn để đủ 5-7 mã nếu dữ liệu không đạt. Nếu người dùng cho
  phép hạ tiêu chuẩn, phải ghi rõ tiêu chuẩn nào được hạ và rủi ro tăng thêm.
- Cần hiển thị lý do không đạt: thiếu dữ liệu, model integrity, định giá không
  đủ MOS, thanh khoản, chất lượng lợi nhuận, rủi ro ngành/vĩ mô, dòng tiền, nợ.
- Lịch cập nhật mong muốn: thứ Ba 09:30 cho ranking/tích sản; TPCP 10 năm thứ
  Ba 10:00 nếu automation được cài trên host chủ dự án.

## 9. Khi sửa UI

- Tone thương hiệu hiện đang hướng tới xanh tài chính, gần cảm giác VPBank:
  tin cậy, rõ ràng, ít màu rối.
- Không dùng text giải thích dài dòng trong UI nếu có thể trình bày bằng tiêu
  đề, thẻ số liệu, bảng, tooltip và trạng thái ngắn.
- UI Streamlit phải nhẹ: tránh animation nặng, tránh gọi API trong render.

## 10. Trước khi báo xong

- Với code Python: chạy test liên quan, `ruff check`, `black --check` nếu khả thi.
- Với dữ liệu: in sample hoặc kiểm tra vài ticker đại diện, nhất là mã từng lỗi.
- Với GitHub: đọc `docs/SECURITY_AND_SECRETS.md` và
  `docs/GITHUB_UPDATE_WORKFLOW.md` trước khi commit/push.

## 11. Cập nhật dữ liệu trong ứng dụng

- `Tải mới <MÃ>` gọi API cho đúng mã đang mở: giá, BCTC quý và nguồn báo cáo
  CTCK. BCTC năm chỉ tải khi mã chưa có lịch sử, nhằm giảm thời gian và lượt gọi.
- `Nạp lại mô hình đã lưu` chỉ đọc DB trên máy, tuyệt đối không gọi API.
- Trạng thái độ mới phải tính theo từng mã và tách rõ giá với báo cáo CTCK.
  Không được dùng ngày mới nhất toàn VN100 để kết luận cho mã đang mở, và không
  hiển thị kiểu "dữ liệu cũ 0 ngày" khi thực tế chỉ báo cáo CTCK đã cũ.
- Mở app không tự quét toàn bộ VN100. Quét 100 mã chỉ chạy khi bấm nút hoặc qua
  lịch trên máy chủ dự án, tránh mỗi máy khách tạo hàng trăm lượt API.
- `run_ingest()` trả `SUCCESS`, `PARTIAL` hoặc `FAILED`. Mọi UI/script gọi hàm
  này phải đọc trạng thái trả về; không được coi là thành công chỉ vì hàm không
  ném exception.
- Client VNStock phải đưa `settings.vnstock_api_key` vào biến môi trường của
  tiến trình trước request đầu tiên. Không gọi `setup_api_key()` trong app vì
  hàm đó tạo thêm file chứa key trong thư mục HOME; `.env` vẫn là nơi lưu duy
  nhất của dự án.
