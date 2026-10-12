# Agent Handoff — đọc file này ĐẦU TIÊN

> Mục đích: agent mới vào phiên làm việc đọc file này để biết đọc gì trước,
> tránh lặp lại các lỗi đã sửa, và có checklist làm theo trước khi sửa code
> hoặc đẩy lên GitHub. Cập nhật file này khi phát hiện lỗi mới đáng ghi nhớ
> (xem mục 6).

## 1. Thứ tự đọc khi bắt đầu phiên làm việc mới

1. `AGENTS.md` — luật nền, KHÔNG NEGOTIABLE. Đọc trước tiên, luôn luôn.
2. File này (`.agents/AGENT_HANDOFF.md`) — bối cảnh vận hành + lỗi đã gặp.
3. `.agents/rules/project-context.md` — trạng thái hiện hành của hệ thống
   (kiến trúc thực tế, DB, DeepSeek, bảo mật, tài liệu liên quan).
4. `.agents/rules/security-principles.md` — nguyên tắc bảo mật/push ngắn gọn.
5. `docs/AGENT_OPERATING_MANUAL.md` — cách vận hành, module chính, bẫy đã gặp.
6. `README.md` — cách chạy app, dữ liệu đi kèm, lệnh push GitHub.
7. Skill liên quan tới việc bạn sắp làm (không cần đọc hết mọi lần):
   - Sửa/ingest dữ liệu tài chính → `.agents/skills/financial-data-integrity/SKILL.md`
   - Sửa/thêm model định giá → `.agents/skills/valuation-models/SKILL.md`
   - Đụng n8n/workflow điều phối → `.agents/skills/n8n-orchestration/SKILL.md`
     (LƯU Ý: kiến trúc mục tiêu, chưa chạy thật — xem mục 1 của
     `project-context.md`)
   - Đụng Google Sheets 2 chiều → `.agents/skills/google-sheets-two-way/SKILL.md`
     (cũng là kiến trúc mục tiêu, chưa chạy thật)
6. Chỉ khi cần tra cứu sâu:
   - `docs/spec.md` — kiến trúc lý tưởng ban đầu, KHÔNG phải hiện trạng.
   - `DECISIONS.md` — nhật ký quyết định kỹ thuật chi tiết (rất dài, dùng
     `grep` thay vì đọc hết).
   - `docs/DATA_REMEDIATION_REPORT.md` — mã nào dữ liệu đã kiểm chứng, mã nào
     còn bị chặn và vì sao.
   - `docs/DEEPSEEK_COST_CONTROL.md`, `docs/CORPORATE_ACTIONS.md` — trước khi
     đụng bất kỳ code nào gọi DeepSeek hoặc xử lý sự kiện doanh nghiệp.
   - `docs/GITHUB_UPDATE_WORKFLOW.md` — trước khi push.
   - `docs/SECURITY_AND_SECRETS.md` — trước khi commit/push hoặc xử lý key.

## 2. Lỗi đã gặp — đọc để không lặp lại

### 2.1 CFI/CFF bị trừ CapEx hai lần
- **Triệu chứng:** phép đối chiếu dòng tiền (`Δcash ≈ cfo - capex + cf_other`
  trong `valuation/models/financials.py::Company.validate_model_integrity`)
  luôn báo lệch, hoặc `cf_other` bị âm thầm set về 0.
- **Nguyên nhân gốc:** CFI (dòng tiền đầu tư) trong BCTC đã bao gồm sẵn CapEx
  âm như một dòng con. Model lại lưu CapEx riêng để tính FCFF. Cộng thẳng
  CFI+CFF vào `cf_other` mà không cộng ngược CapEx = trừ CapEx hai lần.
- **Cách xử lý đúng:** `_cashflow_other_excluding_capex()`
  (`valuation/data_access/repo.py`) cộng ngược `capex_abs` vào tổng
  CFI+CFF+FX. Khi không khớp được taxonomy CFI/CFF thì gắn cờ
  `MISSING_FINANCIAL_INPUT:{year}:cfi_cff`, KHÔNG default về 0 rồi im lặng.
- **Bài học tổng quát:** bất kỳ dòng "tổng hợp/khác" nào trong BCTC đều có khả
  năng đã chứa sẵn một dòng con đang được dùng riêng ở chỗ khác trong model.
  Trước khi cộng gộp, kiểm tra kỹ chồng lấn.

### 2.2 Corporate actions không được lặp/nhồi vào AI
- Bảng `corporate_actions` dedupe theo khóa
  `(ticker, source_site, source_event_id)` — không insert lại bản ghi giống
  hệt.
- Prompt gửi DeepSeek giới hạn tối đa 12 sự kiện (`max_events_ai`) và tóm tắt
  gọn — không đẩy toàn bộ lịch sử sự kiện vào một request (tốn token, dễ khiến
  AI lặp lại narrative cho cùng sự kiện).
- Fingerprint cache (`verified_summary_fingerprint`) tính luôn trên
  `corporate_actions_context`, nên chỉ khi sự kiện mới xuất hiện mới kích hoạt
  gọi lại DeepSeek — không phải mỗi lần render tab là gọi lại.
- Nếu bạn thêm sự kiện/nguồn corporate action mới: đảm bảo đi qua đúng khóa
  dedupe trên, đừng insert trực tiếp bỏ qua kiểm tra trùng.

### 2.3 DeepSeek chỉ được gọi khi bấm nút
- Đường load dữ liệu, đổi tab, refresh Streamlit rerun: **tuyệt đối không**
  được gọi DeepSeek. Chỉ nút "Kiểm chứng dữ liệu & sinh báo cáo" ở tab BCTC
  mới được gọi, tối đa 1 API call/lần bấm.
- Nếu đang debug và thấy DeepSeek bị gọi ngoài luồng nút bấm (vd trong
  `st.rerun()`, trong hàm render, trong background worker chạy theo
  interval) — đó là bug nghiêm trọng về chi phí, dừng lại và báo trước khi
  tiếp tục.
- Worker kiểm tra sự kiện VCI chạy nền: lỗi nguồn phải chờ 30 phút trước khi
  retry, để Streamlit rerun không tạo request lặp liên tục.

### 2.4 Không commit `.env` / secret
- `.env` đã nằm trong `.gitignore` cùng `*.env`, `secrets/`,
  `*service-account*.json`, `*.pem`, `*.key`. Đừng bao giờ dùng `git add -A`
  hay `git add .` — luôn add từng file/thư mục cụ thể (xem `README.md` mục
  "Đẩy lên GitHub" để có danh sách mẫu).
- File dữ liệu DUY NHẤT được phép commit là `vn100_full.db.gz` (đã nén, không
  chứa secret). `vn100_full.db`, `vn100.db`, `*.db`, `*.sqlite*`,
  `vn100_backup.sql` đều bị `.gitignore` chặn — đừng cố `git add -f` chúng.

### 2.5 AI summary cũ còn trong cache/session
- Khi sửa prompt hoặc cấu trúc section của báo cáo AI, phải tăng cache version
  trong `valuation/report/verified_summary.py` và normalize/xoá session keys cũ.
- Section "Cổ tức, tăng vốn và quyền cổ đông" không còn thuộc AI summary chính.
  Nếu người dùng vẫn thấy, kiểm tra cache/session trước khi kết luận prompt chưa
  đổi. Tab dữ liệu chi tiết về cổ tức/quyền mua có thể vẫn tồn tại riêng.

### 2.6 Ingest không được báo thành công giả
- `valuation/ingest/pipeline.py::run_ingest()` trả trạng thái có cấu trúc cho
  giá và từng BS/IS/CF. Một phần lỗi phải là `PARTIAL`, tất cả lỗi là `FAILED`.
- VCI có thể trả `published_at=NaT`; phải đổi thành Python `None` trước khi ghi
  SQLite. Một số bảng ngân hàng cũ trùng `item_id` cho các nhãn khác nhau; chỉ
  tách khóa khi có nhãn nguồn để truy vết, không tự cộng hoặc đoán dòng.
- Freshness trên sidebar phải lọc theo mã đang mở. Cờ cũ có thể đến từ báo cáo
  CTCK dù giá vừa cập nhật; luôn nêu riêng từng nguồn, không báo "cũ 0 ngày".
- Nút `Nạp lại mô hình đã lưu` không tải Internet. Nút gọi API là
  `Tải mới <MÃ>`; mở app không tự quét 100 mã để tránh rate limit và chi phí.
- `.env` có key chưa đủ nếu client không đưa key vào môi trường tiến trình.
  Không dùng `setup_api_key()` trong app vì vnai sẽ ghi thêm key ra
  `~/.vnstock/api_key.json`; gán `VNSTOCK_API_KEY` trong bộ nhớ trước request.

## 3. Checklist bảo mật (chạy trước MỌI commit)

- [ ] `git status` — không thấy `.env`, `venv/`, `build/`, `dist/`,
      `backups/`, `logs/`, `secrets/`, bất kỳ `*.db`/`*.sqlite*`, hay
      `*service-account*.json` trong danh sách sẽ commit.
- [ ] Không có API key/token/webhook hardcode trong code Python/YAML/JSON vừa
      sửa (grep nhanh trên file đã đổi, tìm các pattern kiểu tiền tố key hoặc
      từ khóa "webhook"/"secret"/"token").
- [ ] Không log secret ra console/Discord/Drive trong code vừa thêm.
- [ ] Nếu đã lỡ dán key thật vào file để test — xoá và thay bằng biến môi
      trường trước khi commit, không chỉ "revert lại là xong" (key có thể đã
      dính vào lịch sử git, cần rotate key nếu đã push).
- [ ] MCP/kết nối Postgres (nếu dùng tới) chỉ dùng account read-only cho luồng
      phân tích; account có quyền ghi giới hạn đúng bảng cần thiết.

## 4. Checklist trước khi sửa code

- [ ] Đã đọc `AGENTS.md` mục 3 (Luật vàng) và mục 8 (khi nào phải dừng hỏi).
- [ ] Đã xác định đúng file/module đang sửa nằm ở đường chạy THẬT (Streamlit +
      SQLite), không phải nhánh kiến trúc mục tiêu chưa dùng
      (n8n/FastAPI/Sheets 2 chiều) — trừ khi nhiệm vụ rõ ràng là build phần
      đó.
- [ ] Với thay đổi liên quan công thức tài chính: đối chiếu với skill
      `valuation-models` hoặc `financial-data-integrity`, không tự đoán công
      thức.
- [ ] Với thay đổi ảnh hưởng dòng tiền/BCTC: đọc mục 2.1 ở trên trước khi đụng
      `repo.py`/`financials.py`.
- [ ] Có kế hoạch test: unit test mới, hoặc test tái hiện bug TRƯỚC khi sửa
      (theo AGENTS.md mục 4.6).
- [ ] Không đổi schema DB hoặc tích hợp ngoài (Google/Discord/n8n) mà chưa xin
      duyệt.

## 5. Checklist trước khi push GitHub

1. App local chạy ổn (`streamlit run streamlit_app.py`, không lỗi crash).
2. Nếu `vn100_full.db` đổi: chạy lại
   ```bash
   gzip -c vn100_full.db > vn100_full.db.gz
   python scripts/ensure_portable_db.py
   gzip -t vn100_full.db.gz
   ```
3. Chạy checklist bảo mật ở mục 3.
4. `pytest`, `ruff check .`, `mypy .` — sạch hoặc chỉ còn cảnh báo đã biết.
5. Commit theo từng file/thư mục cụ thể (không `git add -A`/`git add .`),
   message tiếng Việt mô tả *cái gì + tại sao*.
6. `git push origin HEAD:main`.
7. Nếu lỗi quyền kiểu `Permission denied to <user khác>`: xem
   `docs/GITHUB_UPDATE_WORKFLOW.md` mục "Lưu ý quyền GitHub" — có thể do đăng
   nhập git sai account trên máy.

## 6. Cập nhật file này khi nào

Thêm mục mới vào phần 2 (Lỗi đã gặp) mỗi khi bạn:
- Tìm ra nguyên nhân gốc một bug từng khiến định giá/dữ liệu sai và tốn thời
  gian để phát hiện.
- Phát hiện một giả định ngầm (implicit assumption) trong code dễ khiến agent
  sau hiểu nhầm.
- Sửa xong một lỗi bảo mật/rò rỉ secret.

Không cần xin phép để thêm — nhưng đừng xoá mục cũ trừ khi nó không còn đúng
(trong trường hợp đó, sửa lại nội dung thay vì xoá, và ghi rõ ngày sửa).
