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

### Báo cáo sáng & bot Discord

- `valuation/services/daily_report.py` tái dùng `market_data`/`ranking_table`/`accumulation_picks`
  (tab VN100) và `macro_panel.build_snapshot`; KHÔNG gọi DeepSeek. Cập nhật giá giữ
  `.data_update/worker.lock` để không ghi SQLite song song với "Quét VN100".
- `scripts/discord_bot.py` gọi thẳng `unified_report` (không cần FastAPI), chỉ nhận lệnh của
  mọi thành viên trong `DISCORD_CHANNEL_ID` (hoặc chỉ `DISCORD_OWNER_ID` nếu đặt), chỉ mã `is_vn100`; mã có
  `publication_allowed=False` không hiện FV và không gọi DeepSeek.
- Lịch chạy bằng launchd `vn.antigravity-vn100.discord-bot` / `.daily-report` (chỉ host chủ).

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
  ném exception. Mặc định `is_vn100=False`: mã mới không tự vào rổ (thành viên
  VN100 do `scripts/sync_vn100_universe.py` đặt). Route `/ingest` chỉ nhận mã
  thuộc VN100 ∪ công ty con trong `config/sotp_holdings.yaml`.
- Audit nguồn (`scripts/audit_vn100_data.py`) lưu tập kỳ đã đối chiếu
  (`audited_periods`) và dấu vân tay chỉ của các kỳ đó. Sau khi nạp BCTC kỳ mới,
  mã nhận `SOURCE_AUDIT_PARTIAL:<kỳ>` (cảnh báo, vẫn công bố); số của kỳ ĐÃ đối
  chiếu bị đổi → `SOURCE_AUDIT_STALE` (chặn). Quy trình sau mỗi mùa BCTC: làm mới
  cache nguồn `.vn100_ranking/sponsor/` rồi chạy lại audit để kỳ mới được đối chiếu.
  r3b: một kỳ chỉ vào `audited_periods` khi DB có ô trọng yếu khớp khóa nguồn (cache đi
  trước DB không còn làm STALE nhầm khi DB nạp kỳ đó); quá `audit.max_unaudited_periods`
  (2) kỳ chưa đối chiếu → `SOURCE_AUDIT_STALE:<các kỳ>` (chặn).
- **Quy trình audit sau mỗi mùa BCTC (D66)** — không ghi DB, chỉ ghi file audit/cache:
  1. Nạp giá/BCTC kỳ mới (Quét VN100 hoặc `scripts/update_all_data.py`); `weekly_updater` làm mới cả công ty
     con trong `config/sotp_holdings.yaml` (giá cũ → mã mẹ `SOTP_HOLDINGS_STALE`).
  2. `python scripts/collect_sponsor_data.py --financials` (không `--tickers` = VN100 ∪ công ty con SOTP).
     Cache `.vn100_ranking/sponsor/<MÃ>/` chỉ tải lại khi quá 7 ngày (`collect_sponsor_dataset(ttl_days=7)`),
     nên chạy khi nguồn đã có kỳ mới.
  3. `python scripts/audit_vn100_data.py` (đầy đủ): ghi `data/source_quality_status.json` +
     `.vn100_ranking/sponsor/source_audit.json`; đo ΔFV xung đột (F2c) trên bản sao DB trong bộ nhớ:
     ≤ `audit.source_conflict_fv_materiality_pct` (1%) → `SOURCE_CONFLICT_IMMATERIAL` (cảnh báo), còn lại
     `SOURCE_CONFLICT` (chặn). Chỉ chạy một nhóm mã: `--tickers` (gộp vào audit đã lưu).
  4. Kiểm còn mã nào `SOURCE_AUDIT_PARTIAL`/`STALE`/`SOURCE_CONFLICT`. Mùa Q4 + năm mà chưa audit lại thì
     số kỳ chưa đối chiếu vượt `audit.max_unaudited_periods` → STALE chặn hàng loạt.
  5. Đổi MÔ HÌNH (dữ liệu giữ nguyên) không làm audit cũ hết hạn, nhưng số ΔFV F2c trong status được đo bằng
     mô hình cũ → chạy lại audit, hoặc đo lại ΔFV các mã đang `SOURCE_CONFLICT*`.
- Client VNStock phải đưa `settings.vnstock_api_key` vào biến môi trường của
  tiến trình trước request đầu tiên. Không gọi `setup_api_key()` trong app vì
  hàm đó tạo thêm file chứa key trong thư mục HOME; `.env` vẫn là nơi lưu duy
  nhất của dự án.

## 12. Quy ước mô hình định giá (fx2, 20/10/2026)

- Cổng `VALUATION_LEGS_DIVERGE` dùng chung (`guardrails.legs_diverge`, ngưỡng
  `publication_gate.leg_ratio_review`, khóa cũ `dcf.leg_ratio_review` vẫn đọc được): DCF vs bội số,
  RI vs P/B của CK/BH và NH khi cả hai trọng số > 0. Một chân ≤ 0 hoặc max/min > ngưỡng (5,0 — phi duyệt
  20/10/2026; trước 3,0) → chặn.
- Ngân hàng: MỘT định nghĩa ROE = LNST / VCSH bình quân (roe5, ROE ngành, trung vị lịch sử). RI terminal
  và P/B hợp lý dùng ROE_T·(1 + g/2) (VCSH đầu kỳ ở trạng thái dừng). Dự phóng 3 giai đoạn: năm
  3–5 ROE phai tuyến tính từ driver về ROE_T (`bank_terminal.roe_transition_years`), phần chênh nằm ở dòng
  `roe_fade_adjustment` (cấp LNTT); `forecast_bank_financials(..., fade_to_terminal=False)` = driver thuần.
- DCF: NOPAT terminal theo thuế suất biên `sector_tax_rates.default` (`dcf.terminal_tax_mode: marginal`);
  năm 1–5 giữ thuế hiệu dụng. Tỷ lệ ΔDR/ΔDT chỉ cho mã trong `dcf.deferred_revenue_operating_tickers`.
  CĐKKS > `dcf.minority_book_review` VCSH mẹ → cờ `MINORITY_AT_BOOK_MATERIAL` (không đổi FV).
- EV/EBITDA mã không chu kỳ: bội số trailing × EBITDA TTM; mã chu kỳ giữ EBITDA giữa chu kỳ.
- Kỳ Q4: TTM = FY đủ 4 quý, không bị loại khỏi cửa sổ năm đầy đủ (`CompanyBank.last_period_is_ttm`,
  `CashFlow.is_ttm_period`).
- RNAV AI: dòng tiền dự án (trước tài trợ) chiết khấu bằng WACC
  (`proxy_valuation.rnav_project_discount_rate`).
- Bội số lịch sử nhóm CK/BH loại quan sát trước đợt quyền mua/riêng lẻ (`relative_multiples.
  capital_raise_exclusion_groups`); NH/DCF chưa áp vì thiếu giá phát hành để pro-forma.
- r3a (20/10/2026): (1) lá chắn thuế nợ trong WACC dùng thuế biên (`dcf.wacc_tax_mode: marginal`,
  `wacc.wacc_tax_rate`), cùng nguồn với NOPAT terminal; báo cáo dùng `company_wacc`. (2) `Assumptions.
  terminal_tax_rate` (None = config) đi qua `DCFValuationModel.from_pydantic` và ô "Thuế terminal (vĩnh viễn)"
  trên tab giả định. (3) NH: cờ `BANK_ROE_FADE_PLUG:x%` (% LN năm 5 do dòng cân,
  `bank_terminal.fade_plug_flag_share`); cơ chế "năm theo driver" của r3a đã bỏ ở r4a (xem dưới). (4) CK/BH dùng `forecast_bank.ni_from_avg_roe` /
  `begin_roe_from_avg` (ROE bình quân ↔ đầu kỳ). (5) P/B CK/BH trước phát hành pro-forma vốn hóa / (VCSH + C),
  C = tiền thu LCTT đối chiếu Δ(vốn góp + thặng dư) (`repo.capital_raise_proceeds`,
  `relative_multiples.capital_raise_proforma`); không ước được → loại như fx2.
- r4a (20/10/2026, quyết định phi): ROE terminal NH λ = 0,5 (`bank_terminal.roe_convergence`); ngưỡng hai chân
  5,0. NH: dòng cân phai ROE tính từ driver GỐC (`AssumptionsBank.driver_base`, repo chụp lúc dựng; UI chụp nếu
  thiếu); driver analyst/kịch bản sửa cộng thẳng: LN = LN_phai(gốc) + (LN_driver_sửa − LN_driver_gốc) trên cùng
  trạng thái đầu kỳ — đúng dấu, không bỏ dòng cân (trước: bỏ dòng cân → FV giảm khi tăng NIM ở NH dòng cân dương).
  Hệ quả: kịch bản Bull/Bear NH (`sensitivity`) nay có tác dụng ở năm 3–5. fin_a: ràng buộc vốn
  (`min_equity_to_assets`) áp RIÊNG cho đường gốc và đường sửa theo cùng luật một bước (trước: đường gốc chỉ bị kẹp
  khi đường sửa chạm trần → LN nhảy bậc khi kéo tăng trưởng tín dụng qua trần); không sửa driver thì trùng từng số
  (19 TCTD), Bull/Bear đổi ≤ 0,4%. Thuế dài hạn một nguồn
  `wacc.marginal_tax_rate(terminal_tax_rate, tax_rate)`: thuế người dùng nhập, không thì thuế biên (mode
  `marginal`) hoặc thuế hiệu dụng (mode `effective`) — dùng cho NOPAT terminal (dcf) và lá chắn thuế nợ (WACC).

## 13. SOTP_HOLDINGS và cổng công bố (fx3, 20/10/2026)

- `repo.resolve_sotp_holdings` chạy `run_deterministic_checks` cho từng công ty con (FV giả = thị giá, chỉ giữ
  lỗi dữ liệu mức error, trừ `STALE_PRICE` đã đi đường `SOTP_HOLDINGS_STALE`). Có lỗi → mã mẹ mang
  `SOTP_SUBSIDIARY_DATA_ERROR:<MÃ CON>(<mã lỗi>)` (chặn). r4b (D65): `collect_sponsor_data.py` và
  `audit_vn100_data.py` nhận VN100 ∪ công ty con trong `config/sotp_holdings.yaml` (`universe.audit_universe`,
  whitelist + regex); chạy mặc định (không `--tickers`) gồm cả công ty con. Thêm công ty con mới vào yaml → chạy
  `collect_sponsor_data.py --tickers <MÃ> --financials` rồi `audit_vn100_data.py --tickers <MÃ>` trước khi mã mẹ
  công bố được.
- `config/sotp_holdings.yaml`: có `reviewed_by` thì bắt buộc `as_of` (YYYY-MM-DD), thiếu/sai → `ValueError` khi
  nạp; mô hình vẫn coi `as_of` hỏng là `SOTP_HOLDINGS_UNVERIFIED` (hạn rà soát không tính được).
- **Cách duyệt `config/sotp_holdings.yaml` (việc của người dùng; agent không tự điền `reviewed_by`):** rà từng
  holding — `stake` là lợi ích kinh tế hiệu quả (trực tiếp + gián tiếp), có `source` https và `source_date`;
  `carrying_value_bn` chỉ cho khoản ghi giá gốc; đọc `known_gaps`. Sửa nếu cần, rồi điền ở cấp mã mẹ
  `reviewed_by: <tên>` và `as_of: YYYY-MM-DD` (ngày đối chiếu xong). Quá `review_ttl_days` (180) so ngày định
  giá → `SOTP_HOLDINGS_STALE` (chặn) → rà lại và đổi `as_of`. Trước khi điền, nếu mã mẹ sẽ mở với lệch vượt ngưỡng
  hold (dưới) thì phải có hold hoặc mục registry đã duyệt (REE, TCH đã đặt hold sẵn). Mã holding không được
  đồng thời là holder; mã mới phải qua collect + audit như trên.
- Cổng `_apply_publication_gate` so theo mã cờ trước dấu `:` (cờ mang chi tiết vẫn chặn).
- `audit_vn100_data.py --tickers` GỘP vào audit đã lưu (giữ dòng/chênh lệch các mã khác, dùng lại `year_from`
  của audit đã lưu; mapping_version đổi → phải audit đầy đủ). Trước fx3 lệnh này ghi đè cả file. r3b: chưa
  có `source_audit.json` (máy mới/bản portable) thì gộp vào `data/source_quality_status.json`; không có cả
  hai → lỗi, yêu cầu audit đầy đủ.
- Mã cờ trong `valuate.PUBLICATION_BLOCKING_FLAGS` và tiền tố `verified_summary.DATA_FLAG_ERROR_PREFIXES`
  phải có level `error` trong `flag_descriptions` (test r3b).
- Golden (`tests/test_golden_consensus.py`) kiểm registry ở hai mốc 28/09 và 20/10/2026; mục registry chỉ
  lỗi thời khi không mốc nào còn ngoài band. Cùng lượt chạy kiểm mọi khóa `defaults.yaml` engine đọc đều có
  trong snapshot `harness._ENGINE_CONFIG_KEYS` (khóa mới phải thêm vào đó). fin_a: snapshot `engine_config` còn
  chụp `config_files_sha256` của `config/sotp_holdings.yaml` và `config/event_holds.yaml` (đổi FV/cổng công bố
  ngoài `defaults.yaml`, kể cả khi chưa commit).
- `config/event_holds.yaml` (D46): mỗi mã có `since` (YYYY-MM-DD), `reason`, `source`, `lift_when` → cờ
  `MATERIAL_EVENT_HOLD` (chặn; số chẩn đoán vẫn tính). So `since` với ngày chạy (`date.today()`), không theo
  `as_of` → mã đang hold không được golden đo ở mốc nào. Gỡ hold = xoá dòng khi điều kiện `lift_when` đạt và
  người dùng duyệt; ghi lý do gỡ ở comment file.
- Mã MỚI mở công bố (vừa hết cờ chặn) mà lệch CTCK > `publication_gate.new_listing_hold_dev` (0,40, cần ≥
  `new_listing_hold_min_brokers` = 3 CTCK) hoặc upside > `new_listing_hold_upside_pct` (100%), với mục registry
  chưa được người dùng duyệt → hold trong `config/event_holds.yaml`, `lift_when` là người dùng duyệt (fin_a thống
  nhất ngưỡng; trước đó fx3 ghi 30%, r4a ghi 40%). Mã còn bị chặn bởi cờ chờ người dùng mà sẽ mở vượt ngưỡng
  (REE, TCH: `SOTP_HOLDINGS_UNVERIFIED`) được đặt hold sẵn để luật tự thực thi lúc mở. Thêm/gỡ hold thì sửa dòng
  dưới (test `test_fin_a_round4_minor` đối chiếu với file). Danh sách hold hiện hành: VCG, PC1, FRT, POW, SIP,
  NAB, BVH, VRE, PNJ, HHV, REE, TCH.
- Mọi cờ mới phải có mô tả trong `valuation/engine/flag_descriptions.py`; `describe_flags` tra theo mã trước `:`.

## 14. Cờ mới của đợt nâng cấp D66 (19–20/10/2026)

Mô tả đầy đủ ở `valuation/engine/flag_descriptions.py`; level dưới đây đọc từ file đó.

- **Chặn công bố:** `VALUATION_LEGS_DIVERGE` (một chân ≤ 0 hoặc max/min > `publication_gate.leg_ratio_review`),
  `CIP_DOMINATES_VALUE` (XDCB dở dang > `dcf.cip_share_review` vốn chủ DCF), `SOTP_HOLDINGS_UNVERIFIED`,
  `SOTP_HOLDINGS_STALE`, `SOTP_SUBSIDIARY_DATA_ERROR`, `LAND_BANK_INPUT_MISSING`, `SOURCE_AUDIT_STALE`,
  `SOURCE_CONFLICT` (ΔFV > 1% hoặc không đo được), cùng `MATERIAL_EVENT_HOLD` cho các hold mới.
- **Cảnh báo (không chặn):** `SOURCE_AUDIT_PARTIAL`, `SOURCE_CONFLICT_IMMATERIAL`, `FILING_PRECEDENCE`,
  `FILING_BS_INCOMPLETE`, `UNEXPLAINED_CURRENT_ASSETS`, `CIP_LINE_MISSING`, `MULTIPLE_FROM_PEER_MEDIAN`,
  `SEC_/INS_PAYOUT_FALLBACK`, `SEC_/INS_PAYOUT_INCONSISTENT`, `INS_NO_MARKET_PB_HISTORY`, `TAX_FALLBACK_EBIT`,
  `BANK_ROE_FADE_PLUG`, `MINORITY_AT_BOOK_MATERIAL`, `RNAV_PROJECT_INPUT_MISSING`, `SOTP_SEGMENT_INPUT_MISSING`,
  `SOTP_HOLDINGS_INCOMPLETE` (quay về proxy nên `VALUATION_PROXY` vẫn chặn).
- **Thông tin:** `INCONSISTENT_YEAR_DROPPED`, `MULTIPLE_PRE_ISSUE_EXCLUDED`, `MULTIPLE_PRE_ISSUE_PROFORMA`,
  `PE_LEG_TTM`, `SOTP_HOLDINGS_MODE`, `SOTP_UNLISTED_AT_BOOK`, `RIGHTS_ISSUE_UNDATED` (tách khỏi
  `CORPORATE_ACTION_UNDATED`, không tính là "Lỗi dữ liệu" ở bảng xếp hạng).
- **Lỗi cấu hình (raise, không phải cờ):** `PE_LEG_CYCLICAL_UNSUPPORTED` (mã chu kỳ + P/E phụ), stake/holder
  sai trong `sotp_holdings.yaml`, `reviewed_by` thiếu `as_of`, khóa lạ của `dcf.wacc_tax_mode`.
- Ngưỡng do claude đề xuất, CHƯA được người dùng duyệt (đổi số không cần sửa code): `bank_terminal.
  fade_plug_flag_share` 0,10, `audit.max_unaudited_periods` 2, `audit.filing_precedence_max_rel_diff` 0,05 +
  `audit.filing_source_domains`, `dcf.minority_book_review` 0,10, `relative_multiples.capital_raise_min_ratio`
  0,05 / `capital_raise_proceeds_tol` 0,10 / `capital_raise_exclusion_groups`, `publication_gate.
  new_listing_hold_*`.
