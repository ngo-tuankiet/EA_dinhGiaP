# Project Context — Hệ thống định giá VN100 (bản hiện hành)

> File này mô tả TRẠNG THÁI THỰC TẾ đang chạy, cập nhật lần cuối 2026-09-29
> (sau rà soát độc lập 2026-09-28 — quyết định D34–D42 trong `DECISIONS.md`).
> Bản trước của file này (dựa trên phân tích codebase cũ) có vài câu không còn
> đúng — đã thay bằng nội dung dưới đây.
> Nếu đây là lần đầu bạn vào repo, đọc `.agents/AGENT_HANDOFF.md` trước — file
> đó liệt kê thứ tự đọc và lỗi đã gặp; file này là phần "bối cảnh hiện hành"
> mà handoff trỏ tới.

## 1. Kiến trúc thực tế đang chạy (KHÔNG phải `docs/spec.md`)

- Ứng dụng là **Streamlit app** (`streamlit_app.py`), chạy local trên máy
  người dùng qua `Chay_Dinh_Gia_VN100.command` (macOS) hoặc
  `Chay_Dinh_Gia_VN100_Windows.bat` (Windows), cổng `8502`.
- KHÔNG có PostgreSQL, KHÔNG có n8n orchestrator, KHÔNG có FastAPI service nào
  chạy thật trong bản đang giao cho khách hàng. `docs/spec.md` mô tả **kiến
  trúc mục tiêu ban đầu** (n8n → FastAPI → Postgres → Sheets/Discord/Drive);
  một phần nhỏ (script n8n, Google Sheets exporter, Discord webhook) còn tồn
  tại trong `scripts/` và `valuation/output/` nhưng KHÔNG phải đường chạy
  chính của bản portable. Đọc `docs/spec.md` như tài liệu tham chiếu kiến trúc
  lý tưởng, không phải mô tả hệ thống đang chạy.
- Nguồn sự thật dữ liệu = **SQLite portable** (`vn100_full.db`), không phải
  PostgreSQL. Xem mục 3.
- Code tính toán nằm trong package `valuation/` (ingest, quality, analysis,
  forecast, engine/models định giá theo ngành, report, output, views
  Streamlit).
- `.agents/skills/n8n-orchestration/SKILL.md` và
  `.agents/skills/google-sheets-two-way/SKILL.md` mô tả kiến trúc **mục tiêu**
  (n8n + Sheets 2 chiều) — chỉ áp dụng nếu/khi bạn được yêu cầu build lại phần
  đó. Đừng giả định chúng đang chạy trong bản hiện hành.

## 2. Nơi chạy & cách khởi động

- Thư mục dự án trên máy đang phát triển (đồng bộ Google Drive):
  `.../DATA-G/Phi/1 Antigravity/chứng khoán định giá/antigravity-vn100`
- Chạy nhanh:
  ```bash
  python -m streamlit run streamlit_app.py --server.port 8502 --server.headless true
  ```
- Launcher tự tạo venv tại `~/.venv` (mac/linux) hoặc `%USERPROFILE%\.venv`
  (Windows), cài `requirements.txt`, giải nén DB portable nếu cần.
- Repo GitHub chính (bản portable cho khách tải):
  `https://github.com/tranphixdbt-alt/antigravity-vn100.git`, branch `main`.

## 3. Database portable (SQLite)

- `vn100_full.db`: SQLite đầy đủ, ~100MB, nguồn sự thật khi app chạy local.
  KHÔNG commit trực tiếp — GitHub chặn file đơn lẻ lớn và `.gitignore` đã
  chặn mọi `*.db`.
- `vn100_full.db.gz`: bản nén, **file dữ liệu DUY NHẤT được phép commit**. Khi
  người dùng tải repo, launcher tự giải nén thành `vn100_full.db` qua
  `scripts/ensure_portable_db.py`.
- `DATABASE_URL_READONLY` / `DATABASE_URL_WRITE` trỏ vào file SQLite portable
  theo mặc định; chỉ cần API key/PostgreSQL thật nếu chủ động bật
  `ENABLE_LIVE_PRICE=1` hoặc chạy ingest live.
- Kỳ vọng dữ liệu tại thời điểm viết file này (kiểm tra lại số mới nhất trong
  `README.md` mục "Kiểm tra nhanh dữ liệu portable"): `tickers is_vn100`=101,
  `financials_quarterly`/`prices_daily` phủ 102 mã, routing/valuation output
  101/101 VN100.
- **Trạng thái xác minh dữ liệu (01/09/2026,** `docs/DATA_REMEDIATION_REPORT.md`
  **):** chỉ 66/100 mã vượt cổng kiểm tra để hiển thị giá trị hợp lý; 34/100
  mã bị chặn do xung đột/thiếu input. 7 mã còn xung đột trọng yếu chưa giải
  quyết: `BVH, DPM, DSE, PVT, REE, SSI, TCH`. Đừng coi mọi mã trong DB là "đã
  kiểm chứng" — kiểm tra `data/source_quality_status.json` trước khi dùng số
  cho kết luận đầu tư.

## 4. DeepSeek — luật bất di bất dịch

- DeepSeek **CHỈ được gọi khi người dùng bấm nút** "Kiểm chứng dữ liệu & sinh
  báo cáo" ở tab BCTC. Mở tab, đổi tab, refresh, load trang: KHÔNG được gọi
  DeepSeek. Nếu bạn thêm code mới gọi DeepSeek ở đường load dữ liệu/render —
  đó là lỗi, dừng lại và báo trước khi tiếp tục.
- Một lần bấm = tối đa **một API call**, sinh đồng thời cả 4 phần narrative
  (kiểm chứng, luận điểm, sự kiện doanh nghiệp, tổng hợp CTCK) trong cùng JSON.
- Cache theo **fingerprint** (`verified_summary_fingerprint` trong
  `valuation/report/verified_summary.py`) hash từ BCTC + giả định + giá + kết
  quả định giá + sự kiện + báo cáo CTCK. Cùng fingerprint → dùng lại cache đã
  lưu kể cả sau khi restart app. Đổi fingerprint (dữ liệu thực đổi) → gọi lại.
  Có tuỳ chọn "buộc viết lại" nhưng luôn tốn 1 call, chỉ bật khi cần văn phong
  mới.
- DeepSeek chỉ được **phản biện dữ liệu Python đã cung cấp**, không tự sửa DB,
  không bịa số/nguồn. Khi thiếu filing gốc trong payload, chỉ được ghi "nghi
  vấn", không khẳng định đã đối chiếu nguồn chính thức.
- Chi tiết đầy đủ: `docs/DEEPSEEK_COST_CONTROL.md`, `docs/CORPORATE_ACTIONS.md`.

## 5. Corporate actions (cổ tức, quyền mua, ESOP...)

- Bảng `corporate_actions` dedupe theo `(ticker, source_site, source_event_id)`
  — không insert trùng bản ghi giống hệt; bản nguồn điều chỉnh cập nhật kèm
  `content_hash`/`updated_at`.
- Prompt gửi DeepSeek giới hạn tối đa 12 sự kiện (`max_events_ai` trong
  `valuation/data_access/corporate_actions.py`), tóm tắt gọn — không nhồi toàn
  bộ lịch sử corporate action vào một request.
- Công thức cơ học (cổ tức, cổ phiếu thưởng, quyền mua TERP...) đã chuẩn hoá
  trong `docs/CORPORATE_ACTIONS.md` — đọc trước khi sửa code liên quan, đừng
  suy luận lại công thức từ đầu.

## 6. Dữ liệu tài chính — bẫy đã gặp (đọc thêm skill `financial-data-integrity`)

- **CFI/CFF chồng CapEx:** dòng CFI (dòng tiền đầu tư) đã bao gồm CapEx âm bên
  trong. Nếu cộng CFI+CFF thẳng vào `cf_other` mà không cộng ngược CapEx lại,
  phép đối chiếu `Δcash ≈ cfo - capex + cf_other` sẽ trừ CapEx hai lần. Xem
  `valuation/data_access/repo.py::_cashflow_other_excluding_capex` và mục "Lỗi
  đã gặp thực tế" trong `.agents/skills/financial-data-integrity/SKILL.md`.
- Đơn vị VND, hợp nhất vs công ty mẹ, restatement, lookahead/survivorship
  bias: xem skill `financial-data-integrity` — không lặp lại ở đây.

### Bẫy mới phát hiện khi rà soát 2026-09-28 (đã sửa — đừng tái phạm)

- **LN cổ đông mẹ, không phải LN hợp nhất:** `net_income` ưu tiên
  `attributable_to_parent_company` (CII/DXG/GEX/MSN lệch 1,6–3 lần). BVPS/P/B/ROE dùng
  `BalanceSheet.parent_equity` (VCSH mã 400 đã GỒM CĐKKS mã 429).
- **item_id trùng trong nguồn vnstock:** `short_term_investments`,
  `held_to_maturity_investment` xuất hiện 2 lần; bản nạp cũ để dòng 0 đè dòng thật
  (FPT/MWG mất ~30 nghìn tỷ tiền gửi). Normalizer hiện giữ dòng đầu; dữ liệu cũ sửa bằng
  `scripts/repair_duplicate_bs_items.py` (dry-run mặc định, `--apply` sau khi backup).
- **Cầu nối EV:** cộng `long_term_investments_net` (mã 250) — EBIT không gồm lãi liên kết.
- **Số cp:** cổ tức CP/thưởng đã qua GDKHQ mà vốn điều lệ chưa ghi nhận → nhân (1+tỷ lệ)
  (`ttm_helper._unreflected_split_factor`).
- **Giá:** vnstock trả giá điều chỉnh hồi tố; tải incremental tự phát hiện và tải lại
  toàn bộ mã khi đoạn chồng lấn lệch (`pipeline._overlap_was_readjusted`).
- **Không gọi mạng khi render UI:** biểu đồ giá chỉ đọc DB (trước đây gọi vnstock mỗi lần
  mở trang → treo nhiều phút khi nguồn chậm, mọi nút phải xếp hàng chờ).
- **Thư viện `vnai` có bug** (`vnai/beam/quota.py::verify` — `import threading` cục bộ →
  `UnboundLocalError` khi chạm nhánh hạn mức). Lỗi của thư viện, không phải code dự án;
  ingest bắt được theo từng mã, cứ chạy lại.

### Phương pháp hiện hành (sau D34–D42)

- Một nguồn khuyến nghị: `decision_engine.recommend` + `REC_LABELS_VI` (MOS theo bản chất
  ngành trong `config/defaults.yaml: margin_of_safety`).
- g vĩnh viễn duy nhất `coe_convention.terminal_growth` (4%, trần min(rf, GDP danh nghĩa)).
- Chu kỳ: biên giữa chu kỳ × doanh thu TTM (`models/base.midcycle_level`).
- Ngân hàng: ROE bền vững = ROE năm 5 của dự phóng chuẩn hóa; chân relative = P/B lịch
  sử 5 năm của chính NH. CTCK: chân P/B lịch sử tương tự.
- Bội số P/E, EV/EBITDA = trung vị lịch sử của chính mã (hằng số ngành chỉ dự phòng).
- Job "Quét VN100" chạy tiến trình riêng (`valuation/services/data_update_job.py`), tiến
  độ ở `.data_update/status.json`, UI hiển thị thanh tiến độ.

## 7. Bảo mật — nhắc lại điều quan trọng nhất

- **Không bao giờ commit `.env`** hay bất kỳ file chứa key thật. `.env` đã nằm
  trong `.gitignore`. Trước mỗi commit: `git status` để chắc `.env`, `venv/`,
  `build/`, `dist/`, `backups/`, `logs/`, `*.db`, `secrets/`, `*.pem`, `*.key`
  không xuất hiện trong danh sách staged.
- File DUY NHẤT chứa dữ liệu được phép commit là `vn100_full.db.gz` (đã nén,
  không chứa secret, chỉ chứa dữ liệu thị trường công khai).
- Checklist bảo mật đầy đủ + checklist trước khi sửa code/push GitHub: xem
  `.agents/AGENT_HANDOFF.md`, `.agents/rules/security-principles.md` và
  `docs/SECURITY_AND_SECRETS.md`.

## 8. Báo cáo AI & UI hiện hành

- AI summary đã bỏ section riêng "Cổ tức, tăng vốn và quyền cổ đông". Nội dung
  sự kiện doanh nghiệp chỉ được nhắc trong luận điểm/rủi ro nếu thật sự ảnh
  hưởng quyết định đầu tư. Tab dữ liệu cổ tức/quyền mua riêng vẫn có thể tồn tại.
- Các section summary mong muốn: luận điểm đầu tư, tổng quan doanh nghiệp, bối
  cảnh ngành, kỹ thuật/dòng tiền/vị thế thị trường, rủi ro cần theo dõi.
- UI đang được chỉnh theo tone xanh tài chính, hướng tới cảm giác tin cậy và dễ
  hiểu cho người dùng phổ thông. Tránh các đoạn giải thích dài trùng lặp; ưu
  tiên bảng, badge, diễn giải ngắn và tooltip.

## 9. Trạng thái test/tooling (kiểm tra lại, đừng tin số cũ)

Bản ghi trước đây (giữ lại để tham khảo lịch sử, nhưng phải tự chạy lại trước
khi tin và trước khi báo cáo cho người dùng):
- `pytest`: từng PASS 9/9 (bao gồm test skip API) tại thời điểm review cũ.
- `mypy`/`ruff`: từng PASS với vài cảnh báo nhỏ (thiếu `Optional`, style E701).
- Golden test VCB: từng lệch pha lớn vì dùng số liệu giả lập/hardcode thay vì
  số liệu Excel gốc — cần dữ liệu BCTC thật trong DB để so khớp hoàn toàn.

Trước khi báo cáo trạng thái test, **chạy lại** `pytest`, `mypy .`,
`ruff check .` — đừng copy số cũ trong file này hoặc trong git log.

## 10. Tài liệu liên quan (đọc theo nhu cầu, không cần đọc hết)

| Chủ đề | File |
|---|---|
| Kiến trúc mục tiêu ban đầu (tham chiếu, không phải hiện trạng) | `docs/spec.md` |
| Manual vận hành cho agent | `docs/AGENT_OPERATING_MANUAL.md` |
| Bảo mật và secret | `docs/SECURITY_AND_SECRETS.md` |
| Cách chạy, dữ liệu đi kèm, lệnh push GitHub | `README.md` |
| Quy trình cập nhật GitHub chi tiết | `docs/GITHUB_UPDATE_WORKFLOW.md` |
| Kiểm soát chi phí DeepSeek | `docs/DEEPSEEK_COST_CONTROL.md` |
| Cổ tức/quyền cổ đông | `docs/CORPORATE_ACTIONS.md` |
| Báo cáo khắc phục dữ liệu (mã nào bị chặn, vì sao) | `docs/DATA_REMEDIATION_REPORT.md` |
| Nhật ký quyết định kỹ thuật chi tiết (rất dài, tra cứu khi cần) | `DECISIONS.md` |
| Luật nền bắt buộc đọc trước khi code | `AGENTS.md` |
| Thứ tự đọc + lỗi đã gặp + checklist | `.agents/AGENT_HANDOFF.md` |
| Nguyên tắc bảo mật ngắn gọn | `.agents/rules/security-principles.md` |
