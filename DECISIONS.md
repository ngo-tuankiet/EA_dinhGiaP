# DECISIONS.md — Quyết định kỹ thuật dự án antigravity-vn100

> Ghi lại theo yêu cầu AGENTS.md. Mỗi mục: quyết định, lý do, file/dòng liên quan.

---

## Sprint: Điều tra lệch định giá vs đồng thuận đa-CTCK (2026-07)

**Bối cảnh:** sau khi nạp consensus đa nguồn (24hmoney + Simplize, 64 CTCK,
2.925 dòng), đối chiếu cho thấy mô hình nội bộ thấp hơn đồng thuận CTCK median
-37% (66/81 mã), lệch nặng nhất ở ngân hàng top-tier, công ty quỹ đất lâu năm,
và cổ phiếu chu kỳ vừa qua đỉnh capex. Điều tra tìm ra 3 nguyên nhân gốc — đều
là 1 tham số cố định áp đặt đồng loạt, xoá mất phân hoá chất lượng mà thị
trường/CTCK định giá.

### D20 — Trần ROE bền vững ngân hàng theo TIER chất lượng (15%/20%), không dùng 1 trần cứng

**Quyết định:** `BankGeneralValuationModel.__init__` — ngân hàng có
`sustainable_roe` lịch sử (median nhiều năm) > `ELITE_ROE_THRESHOLD=0.18` được
trần `ELITE_ROE_CAP=0.20`; còn lại giữ trần cũ `STANDARD_ROE_CAP=0.15`.

**Lý do:** trần cứng 15% cho MỌI ngân hàng (thêm ở commit `e36eb41`, sửa lỗi
"upside phi lý" — sprint 2026-07 đầu dự án) xoá sạch phần bù chất lượng: 11/17
ngân hàng VN100 (VCB 19.6%, ACB 20.9%, MBB 19.9%, HDB 20.9%, VIB 21.5%...) có
ROE bền vững lịch sử > trần, bị ép về ĐÚNG mức ngân hàng trung bình (BID
14.8%, CTG 15.5%) — dù thị trường trả P/B cao hơn hẳn cho nhóm tốt (VCB P/B
thị trường ~2.16x vs ACB ~1.17x, model cũ chỉ phân hoá ~5%). Vì
`Target P/B = (ROE-g)/(COE-g)` cực nhạy ROE, đây là nguyên nhân chính khiến
VCB/ACB/MBB/HDB bị định giá thấp hơn đồng thuận CTCK có hệ thống.

Đối chiếu golden test `TestBankGoldenVcb` (fixture `sustainable_roe=0.20`):
tài liệu hand-calc gốc kỳ vọng P/B≈2.148, FVPS≈69,232 VND — code cũ (trần 15%)
cho ra 1.55/50,002 (lệch 28%, không ai phát hiện vì test đã bị viết lại thành
circular-check thuần công thức, không so với hand-calc). Sau fix: khớp đúng
2.148/69,232 — test đã bổ sung assertion số cứng.

**Tác động thực nghiệm (build_company_data thật, TTM):**
VCB upside -24.8%→+0.8% (SELL→HOLD), ACB +30.8%→+77.2%, MBB→+90.8%,
HDB→+44.9% (đều BUY). BID/CTG gần như không đổi (không thuộc tier elite).

**Files:** `valuation/engine/models/bank_general.py` (dòng ~46-62).
**Test:** `tests/test_valuation_accuracy.py::TestBankGoldenVcb` (assertion mới
đối chiếu trực tiếp hand-calc, không còn circular).

---

### D21 — RNAV PROXY_MODE: chiết khấu chỉ áp phần đánh giá lại đất, không áp vốn CSH sổ sách

**Quyết định:** `RNAVValuationModel.perform_valuation()` nhánh PROXY_MODE —
`rnav_discount` chỉ nhân vào `revaluation_surplus` (phần premium đất/BĐS đầu
tư), KHÔNG nhân vào `total_equity` (đã kiểm toán). Công thức mới:
`nav_equity = equity + revaluation_surplus × (1 - discount)`
(trước: `nav_equity = (equity + revaluation_surplus) × (1 - discount)`).

**Lý do:** `rnav_land_premium=0.20`/`rnav_discount=0.40` là default Pydantic
đồng loạt cho MỌI công ty BĐS/KCN (comment gốc "# analyst nhập" — thiết kế để
chuyên viên tự override, nhưng quét batch 100 mã không ai chỉnh). Với công ty
quỹ đất lâu năm (BCM: đất KCN Bình Dương ghi giá gốc hàng chục năm trước,
inventory+BĐS đầu tư/cp 39,480đ >> equity/cp 21,718đ), công thức cũ chiết khấu
40% lên CẢ vốn CSH đã kiểm toán → FV (17,768đ) THẤP HƠN CẢ giá trị sổ sách
(21,718đ) — phi lý cho công ty có tài sản lõi bị định giá thấp trên sổ sách.

**Tác động thực nghiệm:** BCM FV 17,768→26,455đ (thoát vùng dưới sổ sách, vẫn
SELL vì thị giá 48,700đ quá cao so với NAV thận trọng). KBC 23,158→34,609đ
(SELL→HOLD). PHR/GVR ít đổi hơn (premium/equity nhỏ hơn BCM/KBC).

**Chưa sửa (để dành quyết định sau nếu cần):** magnitude premium 20%/discount
40% vẫn giữ nguyên — không tăng premium riêng cho nhóm đất lâu năm (BCM/GVR),
vì cần nghiên cứu tuổi quỹ đất/giá KCN hiện tại vs giá gốc mới định lượng đúng
được. Đây vẫn là proxy thận trọng, không phải NAV chi tiết theo dự án.

**Files:** `valuation/engine/models/rnav.py` (nhánh PROXY_MODE, dòng ~127-142).
**Test:** `tests/test_proxy_models.py`, `tests/test_ai_rnav_sotp.py` (không đổi
số, chỉ qualitative — vẫn pass).

---

### D22 — Capex dự phóng DCF: median 3 kỳ gần nhất, không median toàn lịch sử

**Quyết định:** `build_company_data` (repo.py) — `capex_to_rev` ưu tiên
median của 3 kỳ TÀI CHÍNH GẦN NHẤT (`historical_cf[-3:]`/`historical_is[-3:]`,
kỳ cuối là TTM), fallback về median toàn lịch sử nếu <3 kỳ có dữ liệu hợp lệ.
Cùng cửa sổ với `effective_tax` (đã dùng `historical_is[-3:]` từ trước).

**Lý do:** median toàn lịch sử (có thể 9 kỳ) trộn lẫn giai đoạn xây
dựng/mở rộng công suất (capex/DT cao) với giai đoạn thu hoạch hiện tại (capex/
DT thấp) rồi chiếu CỐ ĐỊNH cho cả 5 năm tới. VD HPG: capex/DT lịch sử dao động
3.2%-49.4% (giai đoạn xây Dung Quất 2), median toàn lịch sử = 14.6% — trong
khi kỳ TTM gần nhất chỉ 3.2% (đúng như tất cả báo cáo CTCK: "Dung Quất 2 đã
hoàn thành, giai đoạn gặt hái bắt đầu"). Model cũ vẫn giả định capex nặng như
thời xây dựng → FCFF bị bóp nghẹt (capex ăn ~86% NOPAT năm 1 dự phóng).

**Lưu ý trung thực:** với HPG cụ thể, 3 kỳ gần nhất VẪN còn 2 năm cao điểm
(25.6%, 16.5%, 3.2% → median 16.5% — cao hơn cả median-9 cũ 14.6%), nên fix
này KHÔNG cải thiện nhiều cho riêng HPG (FV giảm nhẹ 15,923→14,762). Logic vẫn
đúng hướng và có lợi hơn cho các mã khác đã hoàn tất capex-cycle sớm hơn (dữ
liệu 3 kỳ gần nhất phản ánh đúng giai đoạn hiện tại thay vì trộn lẫn quá khứ).

**Files:** `valuation/data_access/repo.py` (dòng ~436-448).
**Test:** full suite 233 passed, 3 skipped — không có golden test riêng cho
capex window (áp dụng chung cho mọi mã phi tài chính, không đổi hành vi cho
DN capex ổn định qua các kỳ).

---

## Sprint: Hiệu chuẩn định giá vs đồng thuận CTCK (2026-08)

**Bối cảnh:** đo lại toàn bộ VN100 cho thấy mô hình lệch median **-21.5%** so
đồng thuận CTCK, nhưng phân hoá rất mạnh theo nhóm phương pháp: PB **-76.1%**,
SOTP **-58.1%**, PE -29.1%, DCF -26.1%, RNAV -17.1%, còn RI_PB (ngân hàng)
**+10.7%** — tức sprint D20 (2026-07) đã sửa QUÁ TAY nhóm ngân hàng. Nghiêm
trọng hơn: **52/97 mã có FV thấp hơn CHÍNH THỊ GIÁ**, 28 mã thấp hơn >40%
(VIC -91.9%, HCM -73.2%, EIB -71.9%). Lệch so với thị giá là dấu hiệu lỗi mô
hình độc lập với việc CTCK đúng hay sai.

### D23 — Harness hiệu chuẩn + hàng rào chống hồi quy theo nhóm phương pháp

**Quyết định:** thêm package `valuation/calibration/` đo lệch mô hình vs đồng
thuận CTCK và vs thị giá cho toàn VN100, lưu lịch sử vào 2 bảng
(`calibration_runs` unique theo `label` ⇒ idempotent, `calibration_observations`),
kèm CLI `scripts/run_calibration.py` có `--baseline-label --fail-on-regression`.

**Lý do — bài học D20:** sprint 2026-07 sửa undervaluation ngân hàng làm nhóm
RI_PB nhảy từ ~-25% sang +10.7% (dịch 35 điểm phần trăm, xuyên qua band ra phía
bên kia) mà KHÔNG AI PHÁT HIỆN, vì các chỉ số tổng thể khi đó "trông tốt lên"
(|lệch| median giảm). Không có cơ chế đo giữa hai lần chạy thì mọi thay đổi mô
hình đều là sửa mù.

**5 rule khiến verdict = FAIL** (ngưỡng ở `DEFAULT_RULES`, không hardcode rải rác):
1. `NEW_ERRORS` — sinh mã lỗi mới.
2. `BAND_NET_LOSS` — đẩy ra khỏi band nhiều hơn kéo vào.
3. `OVERALL_REGRESSION` — |lệch| median toàn cục xấu đi > 1pp.
4. **`METHOD_SHIFT`** — nhóm PP có n≥3 dịch lệch median *có dấu* > 15pp. **Đây
   chính là rule bắt được sự cố D20.**
5. `NEW_BELOW_PRICE_ALARM` — mã mới rơi xuống dưới thị giá > 40%.

**Sửa kèm — hai nguồn đọc consensus mâu thuẫn:** trước đây
`consensus_helper.get_consensus_stats` KHÔNG dedup theo CTCK (1 CTCK ra 3 báo
cáo = 3 phiếu vào median) trong khi `report_data.build_consensus_comparison` CÓ
dedup → KPI "Median CTCK" và bảng ngay dưới nó hiện hai con số khác nhau. Nay cả
hai uỷ quyền cho `calibration/consensus_view.py::get_consensus_view` — nguồn đọc
DUY NHẤT, có dedup theo CTCK, chống lookahead (`report_date <= as_of`), tuỳ chọn
trọng số theo độ mới, và loại dòng `is_synthetic`. `count` nay là SỐ CTCK chứ
không phải số báo cáo.

**Baseline chốt (label `baseline-2026-08-11`, git bbdf0b7, 100 mã, 0 lỗi):**

| Nhóm PP | n | Lệch median | \|Lệch\| median | Trong band | FV<giá 40% |
|---|---|---|---|---|---|
| DCF | 36 | -26.1% | 40.5% | 30.6% | 10 |
| RI_PB | 15 | **+10.7%** | 26.7% | 40.0% | 3 |
| RNAV | 9 | -17.1% | 17.1% | 55.6% | 1 |
| PE | 5 | -29.1% | 29.1% | 0.0% | 3 |
| EV_EBITDA | 4 | -9.4% | 10.4% | 75.0% | 2 |
| PB | 3 | **-76.1%** | 76.1% | 0.0% | 7 |
| SOTP | 3 | **-58.1%** | 58.1% | 0.0% | 2 |
| **TOÀN BỘ** | **75** | **-21.5%** | **31.5%** | **33.3%** | **28** |

**Ranh giới kiến trúc:** engine KHÔNG được import package này. Dữ liệu CTCK chỉ
để ĐO, không bao giờ là input định giá (sẽ cưỡng chế bằng
`tests/test_import_boundaries.py` ở GĐ7).

**Files:** `valuation/calibration/{__init__,consensus_view,metrics,harness,compare}.py`,
`valuation/db/models.py` (+`CalibrationRunRow`, `CalibrationObservation`),
`scripts/{migrate_calibration,run_calibration}.py`,
`valuation/engine/consensus_helper.py` (rút thành wrapper),
`valuation/report/report_data.py` (bỏ vòng dedup riêng).

**Test:** 278 passed, 3 skipped (trước sprint: 233 + 3). Trong đó
`tests/test_calibration_compare.py::TestSuCoNganHangThang7` tái hiện đúng sự cố
D20 và assert hàng rào FAIL — test này là bộ nhớ thể chế, nếu ai nới lỏng
`max_method_shift` thì nó đỏ ngay. Kèm test chứng minh chỉ số tổng thể KHÔNG báo
động trong kịch bản đó (lý do bắt buộc phải có rule theo nhóm PP).

**Cổng nghiệm thu đã qua:** harness tái lập ĐÚNG từng con số baseline đo độc lập
trước đó (-21.5% / DCF -26.1% / RI_PB +10.7% / PB -76.1% / SOTP -58.1%), và chạy
lại 2 lần cho kết quả tất định (100 mã UNCHANGED, verdict PASS).

### D24 — Chất lượng dữ liệu đồng thuận: chuẩn hoá tên CTCK, cách ly dữ liệu giả, bật Simplize

**Quyết định:** làm sạch MẪU SỐ trước khi động vào mô hình — mọi kết luận "lệch
bao nhiêu so với CTCK" đều vô nghĩa nếu bản thân đồng thuận sai.

**1. Chuẩn hoá tên CTCK** — `config/broker_aliases.yaml` +
`valuation/ingest/broker_names.py::normalize_broker()`. Bảng alias dựng từ dữ
liệu THẬT quan sát được ngày 2026-08-11 (24hmoney: 31 mã CTCK; Simplize: 30 mã),
KHÔNG suy đoán. Các cặp trùng đã xác minh: `VIETCAP/VCSC`, `MIRAE/MAS`,
`SSV/SHINHAN`, `YSVN/YUANTA`, `VDSC/VDS`, `AGR/AGRISECO`, `SBSC/SBBS`,
`VIETINBANKSC/CTS`. Tên chưa xác minh (`VPX`, `ELDIAN`) **giữ nguyên, không gộp
bừa** (`unmatched_policy: keep_raw`) — gộp nhầm hai công ty làm sai median mà
không ai nhìn thấy.

**Bẫy đã chặn bằng test:** `HCM` vừa là MÃ CỔ PHIẾU VN100 vừa là tên gọi tắt của
CTCK HSC. Alias list CỐ Ý bỏ `HCM`;
`tests/test_broker_names.py::test_HCM_khong_duoc_map_sang_HSC` đỏ ngay nếu ai
thêm vào. Cũng bóc hậu tố `"VCI (Nguyen Van A)"` → `VCI` (lỗi từ
`consensus_collector.py` ghép tên chuyên viên vào tên CTCK, khiến một nhà bị tách
thành nhiều "CTCK").

**2. Migration CỘNG THÊM, đảo ngược được** (`scripts/migrate_consensus_quality.py`,
dry-run mặc định, in báo cáo gộp/dòng-giả trước khi `--apply`): thêm
`broker_canon`, `source_site`, `is_synthetic`, `report_title`, `currency_unit`.
**KHÔNG sửa cột `broker`** — nó nằm trong PRIMARY KEY, sửa tại chỗ vi phạm luật
vàng #6 và xoá mất xuất xứ. Tên chuẩn ghi vào cột riêng; gộp làm ở tầng ĐỌC.
Kết quả: 268 dòng nguyên vẹn, 268 có `broker_canon`, 6 dòng đổi tên chuẩn
(`VIETINBANKSC`→CTS, `YSVN`→YUANTA), 0 dòng giả.

**3. Cách ly dữ liệu bịa** — `scratch/run_consensus_collector.py:11-33` chứa 9
dòng khuyến nghị **gõ tay** (SSI Research/HSC/MBS cho FPT, HPG, SSI) ghi vào
`consensus_history` y hệt dữ liệu cào thật, không cách nào phân biệt. DB hiện tại
may mắn chưa từng chạy nó (kiểm tra: 0 dòng khớp predicate). Nay: bắt buộc cờ
`--i-know-this-is-fake`, và mọi dòng ghi kèm `is_synthetic=True` để
`consensus_view` tự loại khỏi thống kê.

**4. Trọng số theo độ mới** — `config/consensus_quality.yaml`
(`half_life_days: 90`, `stale_after_days: 120`, `min_brokers_for_median: 2`).
`ConsensusView` trả **CẢ HAI** `median` và `weighted_median`, harness ghi cả hai
vào `calibration_observations` để A/B bằng số liệu thực nghiệm — **chưa chốt dùng
cái nào làm chuẩn**, sẽ quyết khi có dữ liệu so sánh. Thêm cờ `thin`
(< 2 CTCK) hiển thị cảnh báo trên tab: một mã chỉ 1 CTCK theo dõi thì "đồng
thuận" chỉ là ý kiến đơn lẻ, không phải quan điểm thị trường (vd NVL: 1 CTCK,
lệch +116%).

**5. Bật Simplize vào production** — `weekly_updater.py` chuyển thành vòng lặp
`_CONSENSUS_SOURCES`, mỗi nguồn try/except RIÊNG (một nguồn chết không kéo theo
nguồn kia) + đếm riêng từng nguồn trong kết quả trả về. Nút "Tải mới {ticker}" ở
sidebar dùng CHUNG hằng số này để không bao giờ lệch nguồn với nút quét VN100.
Simplize vốn đã hoạt động và có test, nhưng **chưa từng được gọi ở production**.

**Kết quả nạp thực tế (101/101 mã, 0 lỗi, 2.064 báo cáo):**

| | Trước | Sau |
|---|---|---|
| Số dòng consensus | 268 | 2.265 |
| Số CTCK phân biệt | 28 | 34 |
| Mã có đồng thuận 180 ngày | 75 | 80 |
| ACB | 3 CTCK | **14 CTCK** (17 báo cáo → dedup 14) |
| POW | 1 CTCK | 12 CTCK |
| GAS | 2 CTCK | 10 CTCK |

**Hàng rào hồi quy BÁO ĐỘNG — và vì sao vẫn chấp nhận:**
`baseline-2026-08-11` → `baseline-dedup` cho verdict **FAIL**
(`BAND_NET_LOSS` 5 rời/3 vào band; `OVERALL_REGRESSION` |lệch| median
31.5%→33.0%). **Đây là thay đổi DỮ LIỆU, không phải mô hình** — engine không đổi
một dòng. Đã kiểm chứng từng mã dịch chuyển đều do mẫu CTCK tăng mạnh: DCM 4→15
CTCK, VHM 0→5, POW 1→12. Con số lệch "xấu đi" thực chất là phép đo TRUNG THỰC
HƠN, vì trước đó median dựa trên 1-3 CTCK rất nhiễu. Quyết định: nhận
`baseline-dedup` làm mốc tham chiếu mới cho GĐ3 trở đi.

**Phát hiện kèm theo:** dữ liệu tốt hơn làm lỗi overshoot ngân hàng (D20) **lộ
rõ hơn**: ACB +34.1%→+44.3%, MBB +63.3%→+93.0%, OCB +44.0%→+55.1%. Củng cố ưu
tiên cho GĐ5.

**Files:** `config/{broker_aliases,consensus_quality}.yaml`,
`valuation/ingest/broker_names.py`, `scripts/migrate_consensus_quality.py`,
`valuation/ingest/scrapers/{broker_24hmoney,broker_simplize}.py`,
`valuation/ingest/weekly_updater.py`, `valuation/views/{select_ticker,consensus_compare}.py`,
`valuation/db/models.py`, `valuation/calibration/consensus_view.py`,
`scratch/run_consensus_collector.py`.

**Test:** 302 passed, 3 skipped (D23: 278). Thêm `tests/test_broker_names.py`
(20 ca, gồm bẫy HCM≠HSC và tính bất biến normalize∘normalize = normalize cần cho
backfill idempotent) và mở rộng `tests/test_consensus_view.py` (gộp theo
`broker_canon`, loại `is_synthetic`).

---

### D25 — Sổ đăng ký hiệu chuẩn từng mã: cơ chế "giữ nguyên hay phải sửa"

**Quyết định:** `config/calibration_registry.yaml` (git-tracked, sửa qua commit
được review) + `valuation/calibration/registry.py::govern()` phân loại MỖI mã
VN100 thành một trong các trạng thái quản trị, thay vì để "lệch bao nhiêu" là
một con số trôi nổi không ai chịu trách nhiệm.

**Lý do:** quyết định #1 của người dùng — mô hình ĐƯỢC PHÉP lệch khỏi đồng thuận
CTCK (CTCK cũng sai, cũng có thiên lệch lạc quan cố hữu của môi giới bán lẻ),
nhưng mỗi lần lệch phải GIẢI TRÌNH ĐƯỢC bằng luận điểm cụ thể có bằng chứng.
Lệch mà không giải trình được ⇒ coi là lỗi giả định và phải sửa. Trước D25 không
có chỗ nào ghi lại "vì sao mã này được phép lệch", nên mọi lệch đều trông giống
nhau và không ai phân biệt được "cố ý" với "đang hỏng".

**Bảng chân trị `govern()`:**

| Đo được | Registry | Kết luận |
|---|---|---|
| IN_BAND | không có | `OK` |
| IN_BAND | còn entry cũ | `OBSOLETE_ENTRY` (nhắc dọn registry) |
| OUT_* | không có | **`MISSING_JUSTIFICATION`** — phải xử lý |
| OUT_* | justified, còn hạn | `OK_JUSTIFIED` — giữ nguyên mô hình |
| OUT_* | justified, hết hạn | `STALE_JUSTIFICATION` — rà lại |
| OUT_* | must_fix | `KNOWN_DEFECT` — backlog sửa |
| bất kỳ | data_blocked | `DATA_BLOCKED` — không đủ dữ liệu để phán xét |
| NO_CONSENSUS / ERROR | — | `OK` (không đo được thì không phán xét) |

**Luận điểm CÓ HẠN** (`review_ttl_days: 180`): "đã giải thích một lần năm 2026"
không cấp quyền miễn nhiễm vĩnh viễn — bối cảnh doanh nghiệp đổi thì phải rà lại.

**Band theo phương pháp:** SOTP 0,35 / RNAV 0,30 / còn lại 0,20. Nới cho nhóm
proxy là có chủ ý: chúng dựa trên giá trị sổ sách/quỹ đất nên sai số bản chất lớn
hơn DCF; ép vào ±20% chỉ tạo ra hàng loạt "vi phạm" giả.

**Hiện trạng khởi tạo (label `gov-clean`, 100 mã):**
`OK=46, MISSING_JUSTIFICATION=38, KNOWN_DEFECT=14, OK_JUSTIFIED=1 (HPG),
DATA_BLOCKED=1 (NVL)`. 38 mã chưa giải trình chủ yếu thuộc nhóm DCF — nguyên nhân
chung là thiên lệch quá khứ, sẽ xử lý một thể ở GĐ7 chứ không phải lỗi riêng từng mã.

**Cơ chế tự dọn đã chứng minh hoạt động:** REE ban đầu khai `must_fix`, nhưng với
band SOTP 0,35 thì -27,6% nằm TRONG band → harness báo `OBSOLETE_ENTRY` → đã gỡ
khỏi registry. Registry chỉ theo dõi mã NGOÀI band, không theo dõi chất lượng
phương pháp (SOTP vẫn sẽ sửa ở GĐ4 cho cả nhóm).

**Hiển thị ra người dùng** (`views/consensus_compare.py::_render_calibration`) —
thay cảnh báo cứng ">25%" trước đây bằng kết luận có ngữ cảnh. Ví dụ ACB nay
hiện: *"Mô hình lệch +44,3% (ngoài ngưỡng ±20%) — đây là LỖI ĐÃ BIẾT của phương
pháp định giá cho mã này, đang trong hàng đợi sửa. **Đừng dùng con số định giá
này để ra quyết định.** Tham chiếu: D20"*. Còn HPG hiện luận điểm capex Dung Quất
2 kèm bằng chứng. Người đọc phân biệt được "lệch vì ta tin mình đúng" với "lệch
vì đang hỏng" — trước đây hai thứ này trông y hệt nhau.

**Files:** `config/calibration_registry.yaml`, `valuation/calibration/registry.py`,
`valuation/report/report_data.py` (`_calibration_note`),
`valuation/views/consensus_compare.py` (`_render_calibration`).

**Test:** 324 passed, 3 skipped (D24: 302). `tests/test_calibration_registry.py`
(22 ca) gồm: bảng chân trị đầy đủ; **xác thực chống giải trình rỗng** (status
`justified` mà thiếu thesis/evidence/reviewed_on đều raise `RegistryError`); mọi
mã khai báo phải tồn tại trong `routing.json` (gõ nhầm mã sẽ tạo entry không bao
giờ khớp — im lặng vô dụng); và **test ratchet** `MAX_MISSING=40` chặn số mã chưa
giải trình tăng lên, hạ dần sau mỗi giai đoạn.

---

### D26 — Chứng khoán: đấu nối model RI+P/B, sửa lỗi ROE lệch tử/mẫu số

**Bối cảnh:** 7 mã CK (SSI VND VCI HCM VIX FTS BSI) lệch **-76%** so đồng thuận,
**90% số mã có FV thấp hơn CHÍNH THỊ GIÁ** (VCI 7.523đ vs 22.100đ). Không thể
giải thích bằng "thận trọng" — đó là lỗi phương pháp.

**Ba lỗi thật đã sửa:**

**1. ROE lệch tử/mẫu số** (`pb_relative.py:50-51` cũ) — `median(LNST 3 kỳ) / VCSH
MỚI NHẤT`: tử số là lợi nhuận TRƯỚC tăng vốn, mẫu số là vốn SAU tăng vốn. Với
VCI (VCSH 3.643 → 17.138 tỷ, gấp 4,7 lần) điều này bóp ROE xuống một cách máy
móc. Nay tính ROE TỪNG KỲ trên VCSH BÌNH QUÂN CÙNG KỲ rồi mới lấy median
(`roe_path_from_history`). Hand-calc: LNST [100,120,130] / VCSH [1000,1000,2000]
→ cũ 6,0% vs mới 10,33%. Sửa này dùng chung cho MỌI consumer của `pb_relative`.

**2. Perpetuity một nhịp** — model cũ không có giai đoạn dự phóng nào, áp thẳng
ROE trailing vào công thức vĩnh viễn. Nay dùng `SecuritiesValuationModel` (RI +
Justified P/B, dự phóng 5 năm) — **model này ĐÃ TỒN TẠI SẴN trong repo nhưng chưa
bao giờ được đấu nối** vì thiếu `from_pydantic`; `sector_router.METHOD_ENGINE["PB"]
= "securities"` đã khai báo sai sự thật suốt thời gian đó.

**3. Tầng driver bịa số** — model cũ dựng lợi nhuận từ `market_liquidity=20000`,
`brokerage_market_share=0.10`... là các hằng số KHÔNG lấy được từ DB (luật vàng
#1). Nay thiết kế lại: dự phóng **ĐƯỜNG ROE** — ROE hiện tại fade tuyến tính về
**ROE mid-cycle của CHÍNH công ty đó** (median toàn lịch sử) trong
`capital_deployment_years` năm. Cơ sở kinh tế: vốn mới huy động chưa sinh lời
ngay, giải ngân dần vào dư nợ margin 2-3 năm, nên ROE ngay sau tăng vốn là ước
lượng chệch thấp có hệ thống. Dùng mid-cycle CỦA TỪNG CÔNG TY (không phải một
hằng số ngành) để giữ được phân hoá chất lượng: SSI 12,2% vs BSI 8,9%.
Đường driver cũ vẫn giữ cho API/analyst nhập tay (cờ `SEC_LEGACY_DRIVER_MODE`).

**Guardrail mới** (`valuation/engine/guardrails.py`) — là **CỜ, KHÔNG PHẢI CLAMP**.
Kẹp im lặng chính là sai lầm cũ: `max(0.3, min(pb, 4.0))` biến mọi kết quả rác
thành 0,3x rồi trình bày như định giá bình thường. Nay `PB_CLAMPED_LOW/HIGH`,
`FV_FAR_BELOW_PRICE`, `SEC_PB_FAR_BELOW_MARKET`, `SEC_ROE_BELOW_COE` đều lên tiếng.

**Kết quả (label `after-D26-pb` vs `gov-clean`, verdict PASS):**

| Mã | FV cũ | FV mới | Lệch vs CTCK cũ → mới |
|---|---|---|---|
| VCI | 7.523 | 11.237 | -75,9% → **-64,0%** |
| HCM | 6.967 | 10.029 | -69,6% → **-56,2%** |
| SSI | 10.975 | 13.520 | -71,2% → **-64,5%** |

Nhóm PB: -71,2% → **-64,0%**. `n_below_price_40`: 28 → 27. **Chỉ 3 mã PB dịch
chuyển, 97 mã còn lại UNCHANGED** — xác nhận thay đổi chỉ nằm ở dispatch, không rò rỉ.

**Phần lệch CÒN LẠI đã phân rã được — và đây là bất đồng quan điểm, không phải lỗi:**

| Mã | P/B mô hình | P/B thị trường | P/B theo CTCK | ROE mà CTCK ngụ ý |
|---|---|---|---|---|
| SSI | 0,83x | 1,54x | 2,34x | **30,0%** |
| VCI | 0,75x | 1,48x | 2,09x | **26,2%** |
| HCM | 0,74x | 1,91x | 1,69x | **21,9%** |

CTCK đang định giá theo ROE 22-30%, **cao hơn cả đỉnh chu kỳ 2021** (SSI 22%,
VCI 27%) — tức kịch bản nâng hạng thị trường mới nổi. Mô hình dùng mid-cycle
8,9%-13,1% và không đưa kịch bản chưa xảy ra vào. Đã ghi
`out_of_band_justified` cho SSI/VCI/HCM.

**CÂU HỎI MỞ, chưa xử lý (ghi lại để không bị quên, không dùng làm lý do bào chữa):**
COE nhóm CK 13,4%-15,2% có dấu hiệu hơi cao. `coe.py` lấy rf theo **TPCP VND**
(4,54%) rồi cộng NGUYÊN phần bù rủi ro dựng theo **khung USD của Damodaran**
(mature 4,5% + CRP VN 3,7% = 8,2%) — có khả năng tính TRÙNG rủi ro quốc gia, vì
lợi suất TPCP VND đã hàm chứa rủi ro nội địa. Đáng ngờ thêm: TPCP VN 10Y 4,54%
chỉ cao hơn UST 10Y ~24bp, quá hẹp so với CDS Việt Nam. Chú thích trong
`config/defaults.yaml` cũng ghi `rf: 0.043 # UST 10Y` trong khi code dùng TPCP
VND — tức khung lý thuyết và code đang không khớp nhau.
**KHÔNG sửa trong GĐ3** vì COE ảnh hưởng TOÀN BỘ 97 mã; sửa lẻ trong phạm vi
nhóm CK đúng là kiểu thay đổi đã gây ra sự cố D20. Cần một giai đoạn riêng, đo
bằng harness.

**Files:** `valuation/engine/models/securities.py` (viết lại tầng driver +
`from_pydantic`), `valuation/engine/models/pb_relative.py` (ROE cùng kỳ + cờ kẹp),
`valuation/engine/guardrails.py` (mới), `valuation/engine/batch.py` (dispatch),
`config/defaults.yaml` (`securities`, `relative_pb`, `guardrails`).

**Test:** 347 passed, 3 skipped (D25: 324). `tests/test_securities_insurance.py`
(23 ca) gồm golden test tính tay (P/B = (0,12-0,02)/(0,15-0,02) = 0,769231; VCSH
cuộn chiếu 1.000 → 1.096 tỷ) và **test hồi quy riêng cho bug tử/mẫu số**. Golden
test SSI cũ (`test_golden_fpt_ssi.py`) vẫn xanh nhờ giữ đường legacy.

### D27 — Tách bảo hiểm khỏi chứng khoán: NOT_RATED thay vì số đã kẹp

**Quyết định:** `valuation/engine/models/insurance.py` (mới) cho BVH/BMI/MIG,
tách khỏi nhánh chứng khoán trong `_dispatch_nonfin` theo `sector` của routing
(`BH` vs `CK`).

**Lý do:** routing gộp cả 10 mã chung `primary: P/B` nên trước đây dùng chung một
model, nhưng kinh tế khác hẳn. CTCK: lợi nhuận bám thanh khoản thị trường, chu kỳ
NGẮN, biên độ RẤT rộng (ROE 5%-35% trong 8 năm). Bảo hiểm: lợi nhuận = kết quả
nghiệp vụ + thu nhập đầu tư danh mục trái phiếu → bám chu kỳ LÃI SUẤT, dài và êm
hơn (đo thực tế: ROE 7%-14%, mid-cycle 8,6%-12,6%). Hệ quả: cửa sổ chuẩn hoá ROE
**5 kỳ** thay vì 3, và KHÔNG có cú fade "hậu tăng vốn" như CTCK.

**Từ chối định giá thay vì kẹp số:** `pb_relative.py` từng tự thú trong docstring
rằng lợi nhuận bảo hiểm có thể bị map nhầm từ DOANH THU PHÍ, nhưng vẫn kẹp P/B về
[0,3; 4,0] rồi trả ra một con số trông bình thường. Nay ROE chuẩn hoá nằm ngoài
[0%, 30%] → trả `NOT_RATED` + cờ `NI_MAPPING_UNVERIFIED`. **Thà một khoảng trống
được ghi nhận còn hơn một con số sai đầy tự tin.**
Kiểm chứng thực tế: cả 3 mã đều có ROE 7-14% → dữ liệu SẠCH, không bị map nhầm.
Cảnh báo trong docstring cũ không thành hiện thực với bộ dữ liệu này — nhưng cơ
chế vẫn cần thiết để không im lặng nếu sau này có.

**Files:** `valuation/engine/models/insurance.py`, `valuation/engine/batch.py`,
`config/defaults.yaml` (`insurance`).

---

### D28 — SOTP: từ chối xuất bản số khi proxy không mô tả được doanh nghiệp (NOT_RATED)

**Quyết định:** `SOTPValuationModel` gắn cờ `PROXY_IMPLAUSIBLE` + `NOT_RATED` khi
PROXY_MODE cho ra kết quả lệch quá `proxy_valuation.proxy_max_divergence` (0,50)
so THỊ GIÁ. `InvestmentDecisionMaker` nhận thêm `not_rated` → trả khuyến nghị
`NOT_RATED` thay vì BUY/SELL. Giao diện KHÔNG hiển thị giá mục tiêu và upside cho
mã NOT_RATED.

**Lý do:** khiếm khuyết thật của SOTP không phải "kém chính xác" mà là **đưa ra
một con số đầy tự tin từ một proxy vô nghĩa**. VIC ra 16.911đ trong khi thị giá
208.500đ (-92%) và hệ thống vẫn phát khuyến nghị bán như bình thường. Công thức
`(0,6 × LNST×11 + 0,4 × VCSH sổ sách) × 0,9` không mô tả được tập đoàn mà giá trị
nằm ở cổ phần công ty con niêm yết và quỹ đất ghi giá gốc. Nhãn `PARTIAL` /
`VALUATION_PROXY` cũ bị đọc thành "hơi kém chính xác một chút", không ai hiểu là
"con số này vô nghĩa".

**Vì sao KHÔNG dựng SOTP theo cổ phần công ty con ngay (đã thử, đã đo):**
`vnstock` CÓ API `subsidiaries()`/`affiliate()` với tỷ lệ sở hữu thật, đã viết
`scripts/draft_sotp_holdings.py` để kéo về. Nhưng đo độ phủ so vốn hoá công ty mẹ
thì quá mỏng:

| Mã | Công ty con niêm yết tìm được | Độ phủ |
|---|---|---|
| VIC | VRE 18,37% | **1%** — thiếu hẳn VHM, tài sản lớn nhất |
| MSN | TCB 14,84% | 32% |
| TCH | HHS 58,31% (chưa có giá trong DB) | 0% |
| REE | — | 0% |

Dựng SOTP từ dữ liệu phủ 1% sẽ chỉ tạo ra **một con số sai kiểu khác**. Bịa tỷ lệ
sở hữu còn tệ hơn (luật vàng #1). Nên: chặn lại bằng NOT_RATED, và giao công cụ
để chuyên viên bổ sung từ BCTN — `scripts/draft_sotp_holdings.py` in sẵn danh
sách công ty con + độ phủ để đối chiếu (AGENTS.md §7: không tự động hoá hoàn toàn
giả định).

**Kết quả:** VIC `SELL @ 16.911đ (-92%)` → **`NOT_RATED`, không công bố giá mục
tiêu**. MSN (-48%), REE (-6%), TCH (-31%) dưới ngưỡng nên vẫn định giá bình
thường — cố ý KHÔNG siết ngưỡng để bắt cho bằng được MSN, vì như vậy là chỉnh
tham số theo kết quả mong muốn.

**Chi tiết giao diện có chủ ý:** NOT_RATED tô XÁM trung tính, không tô đỏ — "chưa
đủ cơ sở định giá" khác hoàn toàn "khuyến nghị bán", tô đỏ sẽ bị hiểu thành tín
hiệu tiêu cực. Và **không hiển thị giá mục tiêu/upside**: hiện ra con số rồi dán
nhãn "không đáng tin" là tự mâu thuẫn — người đọc sẽ nhớ con số chứ không nhớ nhãn.

**Bug sửa kèm trong `draft_sotp_holdings.py`:** cùng một công ty con xuất hiện ở
cả `subsidiaries()` (chỉ có mã nội bộ `VRJSC`) lẫn `affiliate()` (có
`right_ticker='VRE'`); logic gộp ban đầu chỉ so tỷ lệ nên giữ nhầm bản KHÔNG có
mã niêm yết → mất khả năng định giá theo vốn hoá. Nay ưu tiên bản nhận diện được
mã niêm yết.

**Files:** `valuation/engine/models/sotp.py`, `valuation/engine/decision_engine.py`
(tham số `not_rated`), `valuation/engine/valuate.py` (truyền cờ), `streamlit_app.py`
(banner trung tính + ẩn giá mục tiêu), `config/defaults.yaml`
(`proxy_valuation.proxy_max_divergence`), `scripts/draft_sotp_holdings.py` (mới).

**Test:** 356 passed, 3 skipped (D27: 347). `tests/test_sotp_gate.py` (9 ca) gồm
ca tái hiện VIC, ca chứng minh KHÔNG chặn bừa khi proxy hợp lý (tính tay 8.946đ),
ca hard-gate vẫn ưu tiên cao hơn NOT_RATED, và test tích hợp end-to-end trên VIC thật.

**Hiệu chuẩn:** `after-D28-sotp` vs `after-D26-gov` = PASS, 100 mã UNCHANGED. Các
chỉ số lệch không đổi vì VIC không có đồng thuận CTCK để đo — cải thiện ở đây là
**chất lượng quyết định**, không phải con số lệch.

---

### D29 — Ngân hàng: sửa ước lượng ROE bền vững, bỏ hệ thống tier, thêm trần P/B
### (BỔ CHÍNH D20 — đọc kèm)

**Bối cảnh:** D20 (2026-07) sửa undervaluation ngân hàng nhưng **quá tay**. Sau
khi GĐ1 làm giàu dữ liệu CTCK, mức overshoot lộ rõ hơn: ACB +44,3%, MBB +93,0%,
OCB +55,1%, VIB +42,4%.

**Nguyên nhân gốc — ước lượng, không phải trần.** `repo.py` lấy
`sustainable_roe = TRUNG BÌNH ROE TOÀN LỊCH SỬ`, trộn đỉnh chu kỳ 2018-2021 vào
ước lượng "bền vững". ACB ra 20,8% trong khi ROE thực tế đang phai rõ rệt
23%→20%→17%→16%. Vì `Target P/B = (ROE−g)/(COE−g)` cực nhạy với ROE, sai số này
đi thẳng vào định giá. **Hệ thống tier của D20 chỉ là thuốc giảm đau cho một ước
lượng tồi.**

**Bốn sửa đổi:**

1. **`sustainable_roe` = MEDIAN cửa sổ 3 kỳ gần nhất** (`repo.py`), không phải
   trung bình toàn lịch sử. Median (không phải trung bình) để một quý đột biến
   không kéo lệch. Cửa sổ vào `config/defaults.yaml::bank_terminal.roe_window`.

2. **BỎ HỆ THỐNG TIER.** D20 dùng ngưỡng 18% → trần 20%, dưới → trần 15%. Đó là
   một **vách đứng phi kinh tế**: ngân hàng ROE 17,9% bị ép về 15%, ngân hàng
   18,1% giữ 20% — chênh 0,2pp đầu vào tạo chênh 5pp đầu ra, tức ~40% giá trị.
   Sửa thẳng ước lượng thì tier thành thừa và có hại. Nay MỘT trần duy nhất 20%.

3. **Thêm TRẦN cho target P/B.** Trước D29 chỉ có `max(0.3, ...)` — có sàn mà
   không có trần, nên ACB ra 1,82x trong khi thị trường trả 1,17x mà không gì
   chặn. Thêm trần 3,0x + so sánh tương đối với P/B thị trường
   (`BANK_PB_FAR_ABOVE/BELOW_MARKET`).

4. **Bỏ magic number** — `ELITE_ROE_THRESHOLD/CAP`, `STANDARD_ROE_CAP` từ literal
   trong `bank_general.py` vào `config/defaults.yaml::bank_terminal`, để harness
   snapshot được vào `engine_config` và quét được.

**Kết quả (label `after-D30-scenario` vs `after-D28-sotp`, verdict WARN — không
vi phạm rule cứng nào):**

| Mã | Trước | Sau | |
|---|---|---|---|
| ACB | +44,3% | **+18,1%** | ✅ vào band |
| VIB | +42,4% | **+8,8%** | ✅ vào band |
| OCB | +55,1% | **+19,7%** | ✅ vào band |
| BID | -21,4% | **-5,7%** | ✅ vào band |
| CTG | -17,0% | +9,7% | cải thiện |
| MBB | +93,0% | +89,3% | vẫn ngoài band |
| VCB | -16,9% | -30,5% | ❌ rời band |
| SHB | +10,7% | +23,8% | ❌ rời band |

Toàn cục: |lệch| median **33,0% → 29,1%**; tỷ lệ trong band **32,5% → 35,0%**;
số mã FV thấp hơn thị giá >40%: 28 → 26. P/B mô hình so P/B thị trường nay tập
trung ở 0,9-1,3x (trước có ca 1,82x/1,17x = 1,56).

**Trung thực về hạn chế:** VCB và SHB RỜI band. VCB là ngân hàng chất lượng cao
nhất, median-3 (16,8%) thấp hơn trung bình lịch sử (19,8%) nên bị định giá thấp
hơn — đúng vấn đề mà D20 từng sửa, nay tái xuất hiện ở dạng nhẹ hơn. Đây là đánh
đổi có ý thức: 4 mã vào band, 2 mã ra. Đã ghi vào registry để theo dõi.

**MBB là ca chưa giải thích được:** ROE 19,6% RẤT ổn định 6 kỳ liền
(21/23/22/20/19/20%) nên median không kéo xuống được, trong khi thị trường chỉ
trả P/B 1,25x. Không rõ vì sao thị trường định giá thấp một ngân hàng ROE ~20%.
Ghi `must_fix` kèm luận điểm "cần điều tra riêng" — KHÔNG chỉnh tham số để ép
khớp, vì như vậy là fit theo kết quả mong muốn.

**Sửa lại chính mình trong lúc làm:** bản đầu của D29 thêm cờ
`TERMINAL_INCONSISTENT` khi payout ngụ ý bởi Gordon (1−g/ROE) lệch payout dự
phóng quá 30pp. Đo thực tế: **bắn ở 15/17 ngân hàng** → thành NHIỄU. Nghĩ lại thì
chênh lệch đó là BẢN CHẤT của mọi mô hình 2 giai đoạn (Damodaran nói rõ phải điều
chỉnh payout ở trạng thái dừng cho khớp g và ROE), không phải lỗi. Đã thu hẹp
thành `TERMINAL_IMPOSSIBLE`, chỉ bắn khi ROE ≤ g — trạng thái dừng toán học không
tồn tại. Cảnh báo cái bình thường sẽ làm người đọc bỏ qua cả cảnh báo thật.

**Files:** `valuation/data_access/repo.py` (~378-395),
`valuation/engine/models/bank_general.py`, `config/defaults.yaml` (`bank_terminal`).

### D30 — Hợp nhất định nghĩa kịch bản + cho kịch bản biến thiên khối terminal

**Hai khiếm khuyết trong cùng một file `sensitivity.py`:**

1. **Hai bản sao logic kịch bản với NGƯỠNG KHÁC NHAU.**
   `apply_scenario_adjustments` (bank Bull cap credit growth 0,40; Bear floor
   −0,05) vs `run_scenario_analysis` (cap 0,30; floor +0,02). Cùng một mã, cùng
   một kịch bản, hai kết quả khác nhau tuỳ đường gọi — không ai phát hiện vì
   không có test đối chiếu hai đường.

2. **Cả hai đều KHÔNG đụng tới COE, g, hay ROE bền vững** — chỉ nhiễu credit
   growth/NIM. Trong khi giá trị terminal chứa gần hết bất định. Hệ quả: dải
   Bull-Bear của ACB chỉ **±6%**, tạo **cảm giác an toàn giả**.

**Sửa:** `run_scenario_analysis` uỷ quyền 100% cho `apply_scenario_adjustments`;
định nghĩa kịch bản chuyển sang `config/scenarios.yaml` (nguồn duy nhất), bổ sung
`coe_delta`, `terminal_g_delta`, `sustainable_roe_delta`.

**Kết quả — dải kịch bản phản ánh đúng bất định:**

| Mã | Dải Bull-Bear trước | sau |
|---|---|---|
| ACB | ±6% | **±42%** |
| MBB | — | ±32% |
| VCB | — | ±42% |
| FPT | — | ±24% |
| HPG | — | ±33% |

**Files:** `valuation/engine/sensitivity.py`, `config/scenarios.yaml` (mới).

**Test (D29+D30):** 369 passed, 3 skipped (D28: 356).
`tests/test_bank_terminal_d29.py` (13 ca) + `tests/helpers_bank.py`, gồm: chứng
minh trung bình-toàn-lịch-sử thổi phồng ROE (tính tay trên chuỗi ACB thật);
**test chặn vách đứng** (ROE 17,9% vs 18,1% phải cho terminal ROE gần nhau);
trần/sàn P/B; `TERMINAL_IMPOSSIBLE` chỉ bắn khi ROE ≤ g; **test đối chiếu hai
đường gọi kịch bản ra cùng số** (chính thứ đáng lẽ đã bắt được bug D30); và test
dải Bull-Bear phải > 20%. Golden test VCB của D20 (P/B≈2,148) **vẫn xanh** vì
fixture truyền `sustainable_roe` tường minh — đã kiểm chứng riêng.

---

### D31 — Lưu luận điểm CTCK công khai + bóc tách TẤT ĐỊNH (không LLM)

**Quyết định:** bảng `consensus_report_text` + `valuation/ingest/scrapers/consensus_text.py`
(thu thập) + `valuation/engine/consensus_extract.py` (bóc tách bằng regex).

**Lý do:** `broker_24hmoney.fetch_report_summaries()` vốn ĐÃ tải đoạn tóm tắt luận
điểm của từng báo cáo, nhưng chỉ dùng tạm cho AI tổng hợp rồi **vứt đi**. Mỗi lần
muốn tổng hợp lại phải cào lại toàn bộ, và không có cách nào đối chiếu CTCK thực
sự giả định gì.

**Vì sao regex chứ không LLM:** kết quả phải TÁI LẬP (cùng đoạn văn luôn cho cùng
kết quả — có test khẳng định) và AUDIT ĐƯỢC (`matched_spans` giữ nguyên văn để
truy con số ra từ chữ nào). LLM không đảm bảo cả hai, lại tốn token cho việc regex
làm đủ tốt.

**Bẫy đã phát hiện và xử lý:** tóm tắt CTCK thường nêu CẢ kết quả quý vừa công bố
LẪN dự phóng cả năm trong hai câu liền nhau. Ví dụ thật (NHSV/ACB): *"...Q2/2026
với lợi nhuận sau thuế đạt **4.292** tỷ đồng (-12,1% YoY). Dự phóng cả năm 2026
LNST đạt **17.207** tỷ đồng (+10,1% YoY)"*. Lấy khớp regex ĐẦU TIÊN ra 4.292 — sai
hoàn toàn về ý nghĩa. Đã thêm `_first_forecast()` ưu tiên câu mang từ khoá dự
phóng; câu không rõ thì đánh dấu `[KHÔNG RÕ: dự phóng hay đã công bố]`.

**Tỷ lệ bóc tách ĐO THỰC TẾ** (283 bản ghi 24hmoney có luận điểm; 2.059 bản ghi
Simplize chỉ có tiêu đề nên không tính vào mẫu số):

| Trường | Tỷ lệ đo được | Dự đoán trong kế hoạch |
|---|---|---|
| Giá mục tiêu | **56%** | — |
| LNST dự phóng | **43%** | — |
| Phương pháp định giá | **39%** | 30-50% ✓ |
| Upside | 31% | — |
| Tăng trưởng dự phóng | 26% | 40-60% (thực tế thấp hơn) |
| P/E mục tiêu | 19% | 15-25% ✓ |
| P/B mục tiêu | 18% | 15-25% ✓ |
| ROE dự phóng | 7% | — |
| WACC | **0%** (1/283) | <5% ✓ |

**77% bản ghi bóc được ít nhất 1 trường.** Tăng trưởng thấp hơn dự đoán vì đã siết
điều kiện phải có ngữ cảnh dự phóng (nếu không sẽ bắt nhầm YoY của quý). **WACC
coi như không dùng được** (1/283) — giữ trường nhưng không đưa vào thống kê nào.

**Quy tắc vàng của module:** thiếu dữ liệu trả `None`, TUYỆT ĐỐI không trả 0 —
một `target_pe = 0` sẽ lặng lẽ kéo mọi thống kê xuống. Báo cáo hiển thị dạng đếm
("6/11 CTCK nêu P/B") thay vì bịa giá trị trung bình từ dữ liệu thiếu.

**Nguồn:** CHỈ trang tóm tắt công khai 24hmoney + tiêu đề Simplize. **Không tải
PDF** — giữ nguyên quyết định bản quyền của dự án. Giữ cả báo cáo ngành/chiến lược
không có giá mục tiêu (bị loại khỏi `consensus_history` vì median cần giá mục tiêu,
nhưng ngôn ngữ phương pháp trong đó vẫn có giá trị).

**Nạp thực tế:** 101/101 mã, **2.347 bản ghi**.

**Files:** `valuation/db/models.py` (`ConsensusReportText`),
`valuation/ingest/scrapers/consensus_text.py`, `valuation/engine/consensus_extract.py`.
**Test:** `tests/test_consensus_extract.py` (19 ca) — fixture là văn bản THẬT từ
24hmoney, không phải câu tự bịa.

### D32 — Năm gốc dự phóng: cơ chế đã sẵn sàng, MẶC ĐỊNH VẪN TRAILING

**Quyết định:** thêm `valuation/forecast/base_year.py` + cờ
`config/defaults.yaml::forecast.base_year_mode`. **Mặc định `TRAILING`** — tức
hành vi y hệt trước D32 (đã kiểm chứng: 100 mã UNCHANGED).

**Vấn đề nhắm tới:** mô hình dựng tăng trưởng năm 1 từ median tăng trưởng LỊCH SỬ,
nhìn hoàn toàn về quá khứ, trong khi CTCK định giá trên dự phóng FY+1 — nguồn gốc
khoảng lệch âm cấu trúc của nhóm DCF (-30%).

**Đo thực nghiệm 3 phương án (harness, baseline `gd5-final`):**

| Phương án | Nhóm DCF | \|Lệch\| median | Trong band | FV<giá 40% | Verdict |
|---|---|---|---|---|---|
| (a) Động lượng thuần | -30,0% → **-24,6%** | 29,1% → **31,6%** ❌ | 38,8% | 26 → 27 ❌ | **FAIL** |
| (b) Co ngót 50/50 | -30,0% → **-24,0%** | 29,1% → 29,1% ✓ | 37,5% | 26 → 27 ❌ | **FAIL** |
| (c) (b) + bỏ qua ngành chu kỳ | như (b) | như (b) | như (b) | 26 → 27 ❌ | **FAIL** |

**KẾT LUẬN TRUNG THỰC: chưa bật.** Tiêu chí chấp nhận đã đặt TRƯỚC khi đo (trong
kế hoạch): *"chỉ chấp nhận khi lệch median toàn cục về gần 0 VÀ `n_below_price_40`
KHÔNG tăng VÀ không nhóm PP nào dịch quá ngưỡng"*. Cả 3 phương án đều làm
`n_below_price_40` tăng 26→27, nên **không đạt**.

**Tôi đã dừng đúng lúc.** Mã gây vi phạm là SBT — doanh thu 4 quý gần nhất giảm
thật (-5,6% YoY) nên mô hình hạ định giá. Tôi đã thử thêm SBT vào danh sách ngành
chu kỳ, nhưng `sector` của SBT là "Food & Beverage" chứ không phải "Mía đường" —
và **thêm từ khoá cho tới khi hàng rào chuyển xanh chính là chỉnh cho vừa kết
quả**, đúng thứ hàng rào sinh ra để ngăn. Nên dừng, giữ TRAILING, ghi lại số đo.

**Cải tiến giữ lại trong cơ chế (dùng được ngay khi bật):**
- **Co ngót về median lịch sử** (`momentum_weight: 0.5`) thay vì thay thế hẳn —
  ước lượng có cơ sở thống kê, kéo ước lượng nhiễu về phía tiên nghiệm ổn định.
  Đo được: giữ nguyên |lệch| median trong khi vẫn cải thiện nhóm DCF 6pp.
- **Bỏ qua ngành chu kỳ** — với thép/dầu khí/hoá chất, động lượng SAI VỀ BẢN CHẤT
  (một cửa sổ TTM ở đáy chu kỳ đem ngoại suy 5 năm). Dùng chung định nghĩa "chu kỳ"
  với `engine/batch.py`.
- Kẹp ±10pp quanh median lịch sử, mọi lần kẹp bắn cờ.

**Việc cần làm tiếp (giao lại):** phân loại chu kỳ hiện dựa trên chuỗi ngành của
routing, chưa đủ mịn (SBT mía đường bị xếp Food & Beverage). Cần bảng phân loại
chu kỳ riêng trước khi bật FORWARD.

**Files:** `valuation/forecast/base_year.py`, `valuation/data_access/repo.py`
(`_quarterly_revenues` + nhánh cờ), `config/defaults.yaml` (`forecast`).

### D33 — Cưỡng chế bằng máy: engine không được biết gì về dữ liệu CTCK

**Quyết định:** `tests/test_forward_base.py::TestRanhGioiKienTruc` quét AST toàn
bộ `engine/models/`, `repo.py`, `forecast*.py`, `valuation/forecast/` và
**assert không module nào import** `consensus_*` hay `calibration`.

**Lý do:** quyết định #2 của người dùng — dữ liệu CTCK chỉ để ĐO, không bao giờ là
input định giá. Đây là cách biến lời hứa thành **thuộc tính kiểm chứng được**: nếu
ai đó (kể cả vô tình, kể cả với ý tốt "cho khớp CTCK hơn") import consensus vào
engine, test đỏ ngay. Không trông chờ vào kỷ luật của người viết code.

**Test:** 406 passed, 3 skipped (D30: 369).

---

### D23-b — Sự cố hạ tầng: hai cluster PostgreSQL, cluster dữ liệu thật bị chết

**Hiện tượng:** sáng 2026-08-11 toàn bộ định giá lỗi
`column prices_daily.foreign_buy_vol does not exist`; DB chỉ còn 37 mã, giá đến
25/06, `macro_series` 9 dòng.

**Nguyên nhân gốc:** máy có 2 cluster — `postgresql@16` (dữ liệu thật, 358M) và
`postgresql@15` (cũ, 199M). Sau reboot, @16 tắt không sạch để lại
`postmaster.pid` ghi PID 803; PID này bị **MongoDB tái sử dụng**, nên PostgreSQL
tưởng "có postmaster khác đang chạy trên cùng data directory" và **từ chối khởi
động, lặp lại mỗi 10 giây**. Trong lúc đó @15 chiếm cổng 5432 → app trỏ vào
cluster gần rỗng. (@15 chưa từng chạy `alter_db.py` nên thiếu 12 cột market-flow
— đó là lỗi hiển thị ra ngoài.)

**Xử lý:** dừng @15 (`launchctl bootout`), đổi tên file khoá cũ thành
`postmaster.pid.stale-backup-<timestamp>` (sao lưu chứ không xoá; đã xác minh PID
803 là `mongod` chứ không phải postgres nên không có nguy cơ hai postmaster cùng
ghi), khởi động lại @16. Dữ liệu nguyên vẹn 100%: 101 mã VN100, 174.295 dòng giá
đến 10/08, 700.866 dòng BCTC, TPCP_10Y đến 10/08.

**Rủi ro còn lại:** plist `homebrew.mxcl.postgresql@15` vẫn nằm trong
`~/Library/LaunchAgents` → sẽ tự khởi động lại ở lần đăng nhập sau và có thể
giành cổng 5432 trước @16. Cần vô hiệu hoá vĩnh viễn nếu không dùng @15.

---

## Sprint: Kiểm tra file Excel xuất VN100 — sửa lỗi export + engine (2026-07)

### D9 — DCF chặn vốn cổ phần ÂM về 0 + cờ NEGATIVE_EQUITY_VALUE_DCF

**Quyết định:** `DCFValuationModel.perform_valuation()` chặn `blended_fvps` về 0
khi < 0 và gắn cờ `NEGATIVE_EQUITY_VALUE_DCF` (nhất quán với EV/EBITDA — C9).

**Lý do:** file Excel người dùng xuất có NKG blended = -6,510 VND (giá cổ phiếu
ÂM — vô lý). Nguyên nhân: NKG thép biên mỏng (~2%) + nợ ròng ~6,371 tỷ > EV từ
DCF → equity value âm; DCF (khác EV/EBITDA) chưa có chặn. Giá không thể âm.

**Files:** `valuation/engine/models/dcf.py`.
**Test:** `tests/test_dcf_negative_clamp.py`.

### D10 — Cờ review upside cực đoan (UPSIDE/DOWNSIDE_EXTREME_REVIEW) trong valuate()

**Quyết định:** `valuate()` gắn cờ khi upside > +150% (UPSIDE_EXTREME_REVIEW)
hoặc < −60% (DOWNSIDE_EXTREME_REVIEW), áp cho CẢ 2 nhánh (bank + phi tài chính;
trước đây nhánh bank trả `flags: []` cứng — cũng vá luôn).

**Lý do:** PVT +302.8%, TNH −99.9%, VIC −93% lọt qua không cờ nào → người dùng
không biết mã nào cần soi lại. Cờ này KHÔNG đổi khuyến nghị, chỉ buộc rà giả định.

**Files:** `valuation/engine/valuate.py` (`_review_flags`), `flag_descriptions.py`.

### D11 — Sửa lỗi tầng xuất Excel (export_100.py): Sector & MOS rỗng

**Quyết định:** sửa `export_100.py`:
- `Sector`: lấy `r.get('group')` (route() trả sector dưới key `group`, KHÔNG
  phải `sector` → trước đây rỗng 100/100 mã). Thêm cột `Business Nature`.
- `MOS Target (%)`: lấy `res['decision']['target_mos']` (KHÔNG phải
  `res['mos_target']` không tồn tại → trước đây 0 cho 100/100 mã).
- `Upside (%)`: bỏ `*100` thừa (valuate đã trả sẵn theo %).

**Lý do:** file Excel xuất ra có cột Sector rỗng toàn bộ và MOS = 0 toàn bộ —
lỗi lấy sai tên key ở tầng xuất, KHÔNG phải lỗi engine (khuyến nghị vẫn đúng vì
Decision Engine dùng target_mos nội bộ chính xác).

### D13 — Sửa bội số EV/EBITDA gán nhầm cho vận tải/cảng (PVT +302%, HAH +113%)

**Quyết định:** EV/EBITDA target ưu tiên lấy theo NHÓM từ routing.json (D14 —
nguồn sự thật ngành) qua map `_GROUP_EV_KEY`, fallback keyword DB sector. Thêm
`sector_ev_ebitda.transport: 6.5` cho vận tải/cảng biển.

**Lý do:** PVT (vận tải dầu khí) & HAH (vận tải container) có ngành DB rộng
"Industrial Goods & Services" → keyword 'industrial' khớp nhầm nhóm KCN
(industrial_zone = 12x). Tàu biển thâm dụng vốn đúng ra ~6x. Sau sửa: PVT dùng
oil_gas 6x (upside +302.8% → +70.1%), HAH dùng transport 6.5x (+112.6% → +9.2%).

**Files:** `valuation/data_access/repo.py` (map nhóm→ev_key, ưu tiên routing
group), `config/defaults.yaml` (thêm transport: 6.5).

### D14b — Lỗi hiển thị Excel VCB "1000%": pipeline xuất nhân đôi 100×

**Quyết định:** `export_100.py` bỏ `*100` ở cột Upside (valuate đã trả sẵn %),
sửa Sector→`group`, MOS→`decision.target_mos`. File `VN100_Valuation_Pro.xlsx`
tạo lại bằng script 1 bước dùng định dạng `0.0"%"` (số % thô + hậu tố %, KHÔNG
nhân 100).

**Lý do:** người dùng thấy VCB > 1000%. Nguyên nhân: pipeline cũ 2 bước
(export_100 nhân `upside*100` → format_excel chia /100 rồi định dạng '0.00%' lại
nhân ×100 khi hiển thị) → phóng đại ~100 lần (upside thật -18.5% hiện thành
~-1850%, hoặc +10% → +1000%). Sau sửa: VCB hiển thị đúng -18.5%; không mã nào
|upside| > 500%.

**Files:** `export_100.py`; file Desktop tạo lại.

### D19 — Backfill lịch sử chuỗi vĩ mô → kích hoạt overlay vi mô ngành

**Quyết định:** backfill lịch sử các chuỗi mà `MacroContext.from_db_momentum`
tiêu thụ (GDP_YOY, CREDIT_GROWTH, STEEL_HRC, CPI_YOY) để tính được momentum
(nay vs ~1 năm trước) — trước đây STEEL_HRC/CPI chỉ 1 điểm nên momentum = 0
(overlay no-op).

**Đã nạp (dữ liệu thật):**
- CRUDE_OIL, STEEL_HRC, USDVND: 32 điểm/chuỗi (tháng, 3 năm) qua yfinance history.
- CPI_YOY: 13 điểm (tháng, 2025-06→2026-06) qua Highcharts tradingeconomics
  (đọc `Highcharts.charts[0].series[0].data` qua Chrome). Chuẩn hóa cuối tháng.

**Kết quả momentum (xác nhận overlay hoạt động):** GDP +0.69pp, tín dụng
+2.79pp, thép HRC **+333 USD/tấn** (trước = 0), CPI +1.12pp. Overlay
revenue_growth (theo GDP) & credit_growth (theo tín dụng) chạy trên số thật.

**Tồn đọng (cần QUYẾT — không tự đặt hệ số):** elasticity biên-thép-theo-HRC
trong `config/elasticities.yaml` vẫn = 0.0 (disabled). DỮ LIỆU đã sẵn (HRC 32
điểm), nhưng HỆ SỐ co giãn là phán đoán tài chính — cần người dùng chốt mức
(vd margin thép +Xpp cho mỗi 100 USD/tấn HRC) trước khi bật.

### D18 — Nguồn vĩ mô thay thế + cào qua Chrome (đã có dữ liệu thật)

**Quyết định:** thay vì HNX/VBMA (khó cào, endpoint không rõ), dùng nguồn dễ
bóc tách hơn, cào qua Chrome MCP (người dùng cấp toàn quyền dùng Chrome):
- **worldgovernmentbonds.com** → đường cong lợi suất TPCP VN đầy đủ (1Y–30Y).
- **tradingeconomics.com/vietnam/indicators** → CPI, lãi suất điều hành, GDP,
  bán lẻ.
Cả 2 render bằng JS (httpx chỉ thấy khung, không có số) → phải chạy JS trong
Chrome. Thêm 2 domain vào allowlist.

**Dữ liệu THẬT đã nạp (2026-07-11):**
- TPCP_10Y = 4.537% @ 10/7 (worldgovernmentbonds) — thay điểm cũ 4.521% @ 26/6.
- CPI_YOY = 4.69%, POLICY_RATE = 4.5%, GDP_YOY = 8.39%, RETAIL_SALES_YOY = 14.8%
  @ Jun/26 (tradingeconomics). → MacroEnvironment.from_db giờ chạy trên số thật
  (lạm phát 4.69%, sát ngưỡng stress 5%).

**KHÔNG bịa:** M2 chỉ có dạng số tuyệt đối (VND Billion), không phải %YoY → CHƯA
ingest M2_YOY (tránh suy diễn sai); CREDIT_GROWTH chờ nguồn SBV. Ghi rõ trong
`scripts/refresh_macro_chrome.md`.

**Quy trình lặp lại:** `scripts/refresh_macro_chrome.md` ghi URL + JS trích số +
lệnh ghi DB. Dữ liệu đổi chậm → refresh tuần/tháng, không cần mỗi lần quét.

**Tồn đọng:** backfill LỊCH SỬ (nhiều năm) các chuỗi này để tính baseline
elasticity overlay vi mô — hiện mới có điểm mới nhất. worldgovernmentbonds/
tradingeconomics có trang lịch sử; cần thêm bước cào chuỗi thời gian.

### D17 — Nguồn vĩ mô: khung nhập CSV (chạy ngay) + scaffold scraper HNX/VBMA

**Bối cảnh:** người dùng chỉ định chuyển TPCP_10Y sang cào HNX/VBMA (chính
thống, miễn phí); CPI/M2/POLICY_RATE thì xây khung nhập để họ tải số liệu chính
thức; backfill lịch sử làm sau (mục 3 sau mục 1-2).

**Đã làm — Khung nhập CSV (mục 1, chạy ngay, không cần mạng):**
`valuation/ingest/import_macro_csv.py` + `scripts/import_macro_csv.py`. Hỗ trợ
CSV WIDE (date,value + --code) và LONG (date,indicator_code,value). Auto-detect
đơn vị: rate dạng % (|v|>1) → chia 100 thành decimal_rate; giá giữ nguyên. Ghi
idempotent qua upsert_macro_series (validate registry, từ chối code lạ). Phủ
CPI_YOY/M2_YOY/POLICY_RATE/RETAIL_SALES_YOY **và** TPCP_10Y (export HNX/VBMA→CSV).

**Đã làm — Scaffold scraper (mục 2):** `valuation/ingest/tpcp_scraper.py`.
Thêm hnx.vn/vbma.org.vn vào `macro_sources.allowed_domains`; domain-guard
`_assert_allowed_host` chặn host ngoài allowlist (chống SSRF, AGENTS.md #5);
fetcher injectable (test offline không chạm mạng); parser `parse_hnx_yield_curve`
linh hoạt tên trường + quy % → decimal; endpoint để trong config
(`tpcp_10y_endpoint`, mặc định RỖNG = chưa bật live).

**CHƯA bật scrape LIVE — lý do (trung thực):** endpoint AJAX thật của HNX
không public/không tra được qua search; trang ASP.NET; môi trường dev không
verify SSL hnx.vn (WebFetch fail "unable to verify first certificate"). Không
hardcode endpoint đoán mò rồi tuyên bố chạy được (vi phạm AGENTS.md #4 "tự kiểm
chứng"). **Cách bật:** xác nhận endpoint bằng DevTools trình duyệt → điền
config → chỉnh parser cho khớp schema thật (đã có test khung) → gọi
`fetch_tpcp_10y` trong pipeline. Trong lúc chờ: dùng CSV import (đường tin cậy).

**Test:** `tests/test_macro_ingest_sources.py` (10 test — chuẩn hóa đơn vị,
từ chối code lạ, domain-guard chặn host lạ, parser bóc 10Y, fetch offline).

### D16 — Audit dữ liệu 2026-07-11 + Freshness Gate + vĩ mô mỗi lần quét

**Phát hiện audit:**
1. 🔴 Giá lệch 5 "thế hệ" (mã cũ nhất 26/6, mới nhất 8/7, chênh 12 ngày) →
   upside giữa các mã KHÔNG so sánh được. Nguyên nhân: các đợt ingest rời rạc.
2. 🔴 DGC thủng giá 15 phiên (1/6→19/6, di chứng bug C8 chưa vá hết vì nằm
   ngoài cửa sổ backfill), REE 1 dòng NULL.
3. 🔴 Vĩ mô mỏng: USDVND/STEEL_HRC/CRUDE_OIL chỉ 1 điểm (26/6); CPI_YOY,
   M2_YOY, POLICY_RATE, RETAIL_SALES_YOY hoàn toàn trống; TPCP_10Y dừng 26/6.
4. 🟡 Lãng phí API: mỗi lần ingest kéo FULL giá từ 2020 (~1,700 dòng/mã).

**Đã sửa:**
- **Ingest incremental** (`pipeline.py::_incremental_price_start`): kéo giá từ
  max(trade_date)−5 ngày (đệm vá NULL, upsert idempotent); mã trống → full
  backfill 2020. Tham số `incremental=False` để ép full khi nghi lịch sử hỏng.
  → refresh 102 mã hết vài phút thay vì hàng chục phút, tiết kiệm ~99% dữ liệu kéo.
- **Đồng bộ giá 1 vintage**: refresh 102/102 mã về 2026-07-10; DGC/REE full
  backfill vá lỗ lịch sử. (REE còn 1 dòng 28/6 chỉ có flow không giá — ngày
  không giao dịch, vô hại, không xóa theo Luật vàng #6.)
- **Freshness Gate** (`data_access/freshness.py`): build_company_data gắn
  `data_flags` (STALE_PRICE >5 ngày, STALE_MACRO_RF >30 ngày) → valuate() trộn
  vào flags → UI/Excel tự khai báo độ tươi. Model Company/CompanyBank thêm
  field `data_flags`.
- **Vĩ mô cập nhật mỗi lần quét**: `MacroEnvironment.from_db(db)` tự dựng từ
  macro_series (CPI_YOY→inflation, TPCP_10Y→rf, POLICY_RATE 2 điểm gần nhất→
  sbv_stance); thiếu series → giá trị trung tính, KHÔNG bịa. Streamlit dùng
  from_db mặc định (analyst chỉnh tay vẫn ưu tiên); export_100.py gọi
  fetch_market_macro (3 call yfinance, idempotent) trước mỗi batch scan.

**Nguồn dữ liệu (uy tín, tiết kiệm):** giá/BCTC = vnstock API (trả phí, đã có);
FX/hàng hóa = yfinance (3 symbol); TPCP_10Y = investing.com CSV; GDP/tín dụng =
GSO/SBV qua CSV. CPI/M2/POLICY_RATE chưa có nguồn tự động — cần bổ sung CSV
GSO/SBV (tồn đọng, xem D17-plan).

**Test:** `tests/test_freshness_gate.py` (6 test). Excel regen: 100 mã cùng
vintage 10/7, 0 cờ STALE.

### D15 — Điều chỉnh Blume cho beta toàn hệ thống (sửa gốc NAB +138%)

**Quyết định (người dùng chốt phương án 1):** mọi beta ước lượng đi qua
`_blume_adjust(raw) = 0.67·raw + 0.33·1.0`, chặn dải [0.6, 1.5]. Áp tại
`estimate_vcb_beta` (cả nhánh DB lẫn live) — một điểm, mọi consumer dùng chung.

**Lý do:** NAB (Nam A Bank) upside +138% do beta thô = 0.593 — thấp nhất nhóm
ngân hàng, phi thực tế cho bank nhỏ. Beta hồi quy bị thiên lệch xuống cho mã
thanh khoản mỏng/mới niêm yết (NAB lên sàn 10/2020). Beta thấp → COE 9.4% quá
thấp → phồng RI & P/B. Điều chỉnh Blume là chuẩn ngành (Bloomberg, Value Line)
sửa sai số ước lượng + hồi quy beta về 1.0.

**Tác động:** NAB 0.593→0.727 (upside +138%→+103%); VCB 0.774→0.849; TCB
1.112→1.075 (beta cao gần như không đổi). Kéo các beta cực đoan về hợp lý, cải
thiện độ chính xác COE cho CẢ 100 mã. Lưu ý: NAB vẫn +103% vì thực sự rẻ (0.92x
book, ROE 16-18%) — phần upside này là thật, không phải lỗi.

**Files:** `valuation/engine/ttm_helper.py` (`_blume_adjust`).
**Test:** `tests/test_blume_beta.py`.

### D12 — Tồn đọng CẦN QUYẾT (calibration, chưa tự sửa)

Rà 100 mã phát hiện phân bố lệch mạnh về SELL (57/100) và 20 mã cờ REVIEW. Ba
nhóm nguyên nhân method-mismatch cần người dùng quyết hướng xử lý:
1. **TNH** (bệnh viện): capex/doanh thu = 72.5% (năm xây viện, một lần) bị ngoại
   suy 5 năm → FCFF âm vĩnh viễn → DCF sập ~0. Cần cap/fade capex như đã làm với
   D&A, HOẶC đổi sang P/E cho y tế.
2. **Nhóm cao su PHR/GVR/DPR**: DCF bỏ sót giá trị quỹ đất → cần nhập Land Bank
   Add-on (D6) hoặc quay lại RNAV.
3. **PVT/HAH/PNJ/NT2 (+100-302%)**: bội số EV/EBITDA hoặc growth có thể quá cao
   cho nhóm này — cần hiệu chỉnh bội số mục tiêu theo dữ liệu ngành thực tế.

---

## Sprint: Hiển thị flags trên UI — vá lỗ hổng minh bạch (2026-07)

### D8 — UI không hiển thị flags từ valuate() → kết quả bất thường trông như lỗi

**Bối cảnh phát hiện:** người dùng chụp màn hình VJC hiện "SELL · Giá MT 0 VND ·
Upside -100%" và hỏi "kiểm tra xem lỗi gì". Đây chính là kết quả ĐÚNG đã biết
từ D7 (equity value âm do đòn bẩy tài chính cao), engine đã gắn cờ
`NEGATIVE_EQUITY_VALUE_EV_EBITDA` — nhưng rà code phát hiện **UI không bao giờ
đọc `_res["flags"]`** ở cả 2 nơi hiển thị chính (`streamlit_app.py` banner đầu
trang, `views/results.py` card "KHUYẾN NGHỊ ĐẦU TƯ"). UI chỉ hiển thị
`company.warnings` (model integrity) và `hard_gates_violations` (Decision
Engine), bỏ sót hoàn toàn cờ định giá của engine → người dùng thấy số bất
thường mà không có lời giải thích, hiểu nhầm là bug.

**Quyết định:** thêm `valuation/engine/flag_descriptions.py` — dịch mọi mã cờ
đang tồn tại trong engine (17 cờ: NEGATIVE_EQUITY_VALUE_EV_EBITDA,
VALUATION_PROXY, LAND_BANK_VALUE_ADDED, DDM_BLEND, SOTP_NAV_FALLBACK,
EBITDA/EARNINGS_NORMALIZED_CYCLICAL, COE_TOO_LOW, IMPLIED_PB_WARNING...) sang
câu giải thích tiếng Việt + mức độ (error/warning/info). Wire vào cả 2 nơi
hiển thị: `streamlit_app.py` (ngay dưới Hard Gates) và `views/results.py`
(ngay dưới card khuyến nghị).

**Lý do:** đây là lỗi thiếu minh bạch, không phải lỗi tính toán — engine đã
đúng và đã gắn cờ đúng từ trước (C9, D7), chỉ là UI không hiển thị. Sửa 1 lần
ở lớp hiển thị dùng chung, áp dụng cho MỌI mã có cờ (không riêng VJC).

**Files:** `valuation/engine/flag_descriptions.py` (mới), `streamlit_app.py`,
`valuation/views/results.py`.
**Test:** `tests/test_flag_descriptions.py` (5 test: cờ đã biết, danh sách
rỗng, cờ lạ có fallback, mọi mô tả có level hợp lệ, các cờ then chốt phải
được document — không rơi vào fallback chung chung).

---

## Sprint: Land Bank Add-on + kết luận VJC EV/EBITDAR (2026-07)

### D6 — Land Bank Add-on: cộng giá trị quỹ đất chưa phản ánh BCTC

**Quyết định:** thêm `Assumptions.land_bank_projects` (mặc định RỖNG) + module
`valuation/engine/land_bank.py::compute_land_bank_value_per_share()`. Cộng
thêm vào `blended_fair_value_per_share` ở `valuate.py` cho MỌI phương pháp phi
tài chính (DCF/EV_EBITDA/PE/RNAV/SOTP) — không ép đổi method. Gắn cờ
`LAND_BANK_VALUE_ADDED` khi có dữ liệu. UI nhập liệu dạng bảng (giống mẫu
rnav_projects/sotp_segments) trong `input_assumptions.py` mục 5, luôn hiện cho
mã phi tài chính.

**Công thức:** mỗi dự án `NPV = diện_tích_ha × 10,000 × giá_đền_bù_VND/m2 ×
tỷ_lệ_sở_hữu / (1+COE)^(năm_thu_tiền − năm_hiện_tại)`. Chiết khấu bằng COE
(CAPM) của chính công ty.

**Lý do:** DN nông nghiệp/cao su/KCN (PHR, DPR, GVR, SIP, SZC...) ghi nhận đất
theo giá gốc trên BCTC — DCF trên dòng tiền cao su/nông nghiệp thuần không bắt
được khoản thu nhập đền bù/chuyển đổi đất một lần. Kiểm chứng: PHR baseline
24,320đ → +100ha giả lập @3tr/m2 → 46,460đ (đúng khớp tính tay 22,140đ/cp).

**KHÔNG bịa số liệu:** mặc định rỗng, add-on = 0 cho mọi mã chưa nhập —
analyst BẮT BUỘC tự nhập diện tích/giá đền bù/năm thu tiền từ báo cáo thật.

**Files:** `valuation/models/financials.py` (field mới), `valuation/engine/land_bank.py`
(mới), `valuation/engine/valuate.py` (wire cộng vào phi tài chính),
`valuation/views/input_assumptions.py` (UI mục 5).
**Test:** `tests/test_land_bank.py` (5 test: rỗng không ảnh hưởng, tính tay
không chiết khấu, sở hữu+chiết khấu, nhiều dự án cộng dồn, wire vào valuate()
qua mock cô lập DB).

---

### D7 — VJC/EV-EBITDAR: KHÔNG triển khai — tiền đề ban đầu sai, đã kiểm chứng dữ liệu

**Quyết định:** KHÔNG xây EV/EBITDAR cho VJC. Giữ nguyên EV/EBITDA hiện tại +
cờ `NEGATIVE_EQUITY_VALUE_EV_EBITDA` (đã có từ C9).

**Lý do (phát hiện khi điều tra trước khi code):** đề xuất ban đầu giả định nợ
VJC là "operating lease chưa vốn hóa" (off-balance-sheet) nên cần cộng ngược
EBITDAR. Kiểm tra dữ liệu thực tế cho thấy **giả định này sai**: VJC có dòng
`finance_lease_assets` + `finance_lease_principal_payments` trên BCTC — nợ
thuê máy bay ĐÃ được vốn hóa (capitalized) vào `total_debt` theo đúng chuẩn kế
toán hiện hành. Hơn nữa, `finance_lease_assets` chỉ ~5,517 tỷ trong khi
`total_debt` là ~68,999 tỷ — phần lớn nợ là vay thông thường, không phải thuê
máy bay. Loại trừ riêng nợ thuê tài chính khỏi net debt cũng không đủ xóa
khoảng cách âm (~35,000 tỷ). Xây EV/EBITDAR ở đây sẽ là **bịa công thức** trên
dữ liệu không hỗ trợ tiền đề — vi phạm AGENTS.md luật vàng #1.

**Kết luận đúng:** VJC thực sự có đòn bẩy tài chính rất cao so với EBITDA
chuẩn hóa; multiple EV/EBITDA 6.0x không đủ bù đắp → equity value âm là kết
quả HỢP LỆ của phương pháp so sánh bội số với đòn bẩy này, không phải lỗi
tính toán. Cờ cảnh báo (đã làm ở C9) là xử lý đúng — minh bạch thay vì che giấu
bằng một công thức không có dữ liệu hỗ trợ.

---

## Sprint: Rà soát nâng cấp Decision Engine + Business Nature (2026-07)

Bối cảnh: người dùng thêm `decision_engine.py` (Dynamic MOS + Hard Gates),
`business_nature` trong router, và chuyển 13 mã SOTP→FCFF trong routing.json.
Rà soát phát hiện & xử lý 5 điểm:

### D1 — DCF blend phụ theo business_nature (P/E vs EV/EBITDA)

**Quyết định:** `dcf.py.perform_valuation` chọn bội số so sánh phụ theo
business_nature: Compounder/Retail → **P/E** (EPS chuẩn hóa median × target_pe);
còn lại → **EV/EBITDA** (như cũ). LNST chuẩn hóa ≤ 0 ở nhánh P/E → fallback về
dcf_fvps (không kéo blend về 0).

**Lý do:** Tài liệu lõi định giá quy định Compounder/Retail dùng DCF+P/E, nhưng
code cũ blend EV/EBITDA cho MỌI mã DCF → méo nặng cho retail biên mỏng
(FRT −82.7%→−63.1%; VNM −1.5%→+4.5%). Nhóm Cyclical/Utility giữ nguyên EV/EBITDA
(kiểm chứng HPG/DGC/PLX/GAS/POW không đổi).

**Files:** `valuation/engine/models/dcf.py` (from_pydantic + perform_valuation).
**Test:** `tests/test_dcf_secondary_blend.py` (chọn đúng bội số theo nature +
fallback khi LNST âm).

### D2 — Tách CK thành nhóm "Securities" MOS 30% (không gộp Bank 20%)

**Quyết định:** Chứng khoán → business_nature `Securities`, MOS 30% (như nhóm
chu kỳ). Bảo hiểm giữ `Bank` (MOS 20%). Phương pháp CK vẫn là P/B (không đổi).

**Lý do:** LNST công ty chứng khoán biến động rất mạnh theo chu kỳ thị trường —
đòi hỏi biên an toàn cao hơn ngân hàng.

**Files:** `sector_router.py` (_SECTOR_TO_NATURE), `decision_engine.py`
(get_target_mos). **Test:** `tests/test_decision_engine.py`.

### D3 — Decision Engine: epsilon chống lỗi float ở biên MOS

**Quyết định:** so sánh ngưỡng dùng epsilon 1e-9 (`upside >= mos - 1e-9`...).

**Lý do:** upside đúng bằng MOS (vd 115/100−1 = 14.999...% do float) bị rớt
xuống HOLD thay vì BUY. **Files:** `decision_engine.py`.

### D4 — Làm rõ 2 trục: routing.json = method, business_nature = MOS

**Quyết định:** ghi rõ trong docstring `sector_router.py`: `primary` (routing.json)
là nguồn DUY NHẤT chọn phương pháp; `business_nature` chỉ đặt MOS + chọn nhánh
blend phụ của DCF. Đổi ngành 1 mã phải kiểm tra cả `primary`.

### D5 — Nhóm cao su & FRT: kết luận sau kiểm chứng thực nghiệm

**Quyết định:** GVR/DPR giữ DCF (kiểm chứng: DCF ≈ SOTP ≈ PE, ~−55%/~0% — DCF
không méo). FRT/PHR được cải thiện qua D1 (FRT nhờ nhánh P/E). PHR vẫn thấp do
thu nhập đền bù đất bất thường — cần dữ liệu quỹ đất (RNAV chi tiết) mới định giá
đúng, KHÔNG ép đổi method để "làm đẹp số" (giới hạn dữ liệu, không phải lỗi code).

**Lý do:** nghi ngờ ban đầu "cao su cần SOTP" chỉ đúng một phần — kiểm chứng số
thật cho thấy chỉ PHR lệch, và lệch do bản chất land-bank không model nào bắt
được nếu thiếu dữ liệu đất.

---

## Sprint: Ingest mã thiếu dữ liệu + sửa bug ghi đè giá (2026-07)

### C7 — Ingest 39 mã thiếu dữ liệu tài chính (CTD + 38 mã khác)

**Quyết định:** Chạy `run_ingest(ticker, ["prices","financials"])` cho 39 mã có
metadata trong bảng `tickers` nhưng 0 dòng ở `financials_quarterly`/`prices_daily`
(CTD, VIC, VHM, MSN, GVR, PVD, KBC, HSG...). Kết quả: 39/39 thành công, phủ
100% (101/101 mã, không tính VNINDEX).

**Lý do:** người dùng báo lỗi "Không có dữ liệu tài chính cho CTD" — điều tra
cho thấy đây không phải bug mà là dữ liệu thật sự chưa được nạp. Ghi upsert
idempotent (ON CONFLICT DO UPDATE), an toàn chạy lại nhiều lần.

**Files:** không đổi code, chỉ ghi dữ liệu qua `valuation/ingest/pipeline.py`.

---

### C8 — Fix bug NGHIÊM TRỌNG: upsert_market_flows() ghi đè OHLCV thành NULL

**Quyết định:** `upsert_market_flows()` trước đây dùng
`update_dict = {c.name: c for c in stmt.excluded if c.name not in ['ticker','trade_date']}`
— lấy TOÀN BỘ cột bảng `PricesDaily` để UPDATE, kể cả open/high/low/close/volume.
Vì record market-flow không chứa các cột này, SQLAlchemy coi là NULL trong
`excluded` row → ON CONFLICT DO UPDATE **ghi đè giá thật đã có bằng NULL**.
Đã sửa: chỉ update đúng `_MARKET_FLOW_COLUMNS` (foreign_*/proprietary_*), không
đụng OHLCV. Đồng thời chuẩn hóa mọi record trong batch insert có ĐỦ cùng bộ
cột (trước đây record thiếu cột không đồng nhất giữa các ngày → lỗi
"INSERT value ... explicitly rendered as boundparameter" khi build multi-row
INSERT).

**Lý do:** vi phạm trực tiếp Luật vàng #6 AGENTS.md ("không phá dữ liệu lịch
sử"). Phát hiện khi điều tra VIC upside -92.9% bất thường: giá 23 ngày gần
nhất (19/6→1/7) bị NULL, chỉ còn giá hôm nay (2/7) sống sót vì dữ liệu khối
ngoại/tự doanh của hôm nay chưa được publish (nên chưa kịp ghi đè).

**Phạm vi:** 7 mã bị ảnh hưởng — VIC, VHM, MSN, GVR, VJC, SSI (23 ngày mỗi mã),
REE (5 ngày). Đã backfill lại toàn bộ từ nguồn vnstock gốc (dữ liệu gốc không
mất, chỉ bị ghi đè trong DB) — xác nhận 0 ngày NULL sau khi backfill.

**Files:** `valuation/ingest/pipeline.py` (`upsert_market_flows`,
`_MARKET_FLOW_COLUMNS`). `valuation/data_access/repo.py::get_latest_price`
(người dùng tự thêm `and row.close is not None` — phòng thủ bổ sung, giữ
nguyên: nếu ngày mới nhất có close NULL, fallback về giá gần nhất có dữ liệu
thay vì crash/trả 0).

---

### C9 — EV/EBITDA: gắn cờ khi equity value âm bị clip về 0

**Quyết định:** `EVEBITDAValuationModel.perform_valuation()` gắn cờ
`NEGATIVE_EQUITY_VALUE_EV_EBITDA` khi `net_debt > EV` (equity value âm, trước
đây âm thầm clip về 0 → hiển thị "upside -100%" gây hiểu lầm công ty vô giá
trị). KHÔNG tự đổi method/multiple (VD: EV/EBITDAR cho hàng không thay vì
EV/EBITDA thường) — đây là quyết định tài chính cần duyệt riêng.

**Lý do:** phát hiện ở VJC (Vietjet) — nợ thuê tài chính máy bay vốn hóa theo
chuẩn kế toán rất lớn so với EV theo multiple 6.0x, khiến equity value âm
35,354 tỷ. Rà toàn bộ 6 mã dùng EV/EBITDA (BSR, HAH, HT1, HVN, PVT, VJC) —
chỉ VJC bị ảnh hưởng, không phải lỗi hệ thống.

**Files:** `valuation/engine/models/ev_ebitda.py`.
**Test:** `tests/test_ev_ebitda.py` (3 test: case đòn bẩy cao có cờ, case bình
thường không cờ oan, ca tính tay EV/EBITDA chuẩn).

---

## Sprint: Sửa gốc upside phi lý (2026-07)

### C1 — COE VND-base CỘNG Country Risk Premium (đảo convention cũ)

**Quyết định:** ERP dùng cho COE = `erp_mature + crp_vn` (≈ 4.5% + 3.7% = 8.2%).
COE = rf_VN + beta × (erp_mature + crp_vn). Đảo lại "golden rule" cũ (chỉ dùng
erp_mature, bỏ CRP vì cho rằng rf_VN đã chứa rủi ro quốc gia).

**Lý do:** CRP là phần bù RỦI RO VỐN CỔ PHẦN của thị trường mới nổi (chuẩn
Damodaran), TÁCH BIỆT với rủi ro vỡ nợ nằm trong lợi suất TPCP. Bỏ CRP làm COE
chỉ ~8-9% → WACC ~8%, mẫu số (WACC−g) ~6% → fair value phình khổng lồ (upside
100-210% cho cả DCF phi TC lẫn RI/PB ngân hàng). Đã được người dùng chốt.

**Tác động:** COE ~8.5%→~11.5%. PLX +114%→−25%, VNM +36%→−2%, banks +200%→~90%.

**Files:** `valuation/engine/coe.py` (get_erp), `config/defaults.yaml` (golden
rule + erp_total là ERP đang dùng), `ttm_helper.py`, `bank_vcb.py`.
**Test:** `tests/test_coe_convention.py` (viết lại theo convention mới),
`tests/test_golden_vcb.py` (recalibrate band 42k-80k theo COE ~10.9%).

---

### C2 — depr_to_revenue lấy từ D&A THẬT, bỏ hardcode 4%

**Quyết định:** `depr_to_revenue = median(D&A/doanh thu lịch sử)` lấy từ line
item `depreciation_and_amortization` (CF). Chỉ fallback 4% khi thiếu dữ liệu.
Thêm field `CashFlow.depreciation`.

**Lý do:** Hardcode 4% cho MỌI mã (magic number, vi phạm AGENTS.md #5) trong khi
capex lấy theo từng công ty → với DN nhẹ tài sản (PNJ D&A thực ~0.2%, PLX ~0.7%)
FCFF bị cộng thêm ~3.8% doanh thu "tiền ảo" mỗi năm → overvaluation.

**Files:** `valuation/data_access/repo.py` (NON_FIN_KEYWORDS + derive),
`valuation/models/financials.py` (CashFlow.depreciation).
**Test:** `tests/test_nonfin_calibration.py::test_depr_derived_from_real_da_not_hardcoded`.

---

### C3 — OPEX = chi phí bán hàng + QLDN (cộng cả 2)

**Quyết định:** `opex = selling_expenses + general_and_admin_expenses` (fallback
`operating_expenses` gộp nếu không tách được).

**Lý do:** `_match_value` chỉ trả 1 dòng khớp đầu tiên → chỉ bắt selling, bỏ sót
G&A → EBIT bị thổi ~2pp margin cho mọi mã phi TC (PNJ 11%→8.6% sau sửa, khớp
operating_profit báo cáo).

**Files:** `valuation/data_access/repo.py` (build_company_data non-fin branch).
**Test:** `tests/test_nonfin_calibration.py::test_opex_includes_selling_and_ga`.

---

### C4 — Engine readonly chạy AUTOCOMMIT (sửa flaky test tận gốc)

**Quyết định:** `engine_read` dùng `isolation_level="AUTOCOMMIT"`.

**Lý do:** Luồng phân tích chỉ đọc, không cần transaction. Trước đây một query lỗi
để lại transaction "aborted", connection trả về pool ở trạng thái hỏng → poison
query test sau (flaky ngẫu nhiên do pytest-randomly, "UndefinedColumn" giả).

**Files:** `valuation/db/session.py`.

---

### C5 — Trả tech debt engine: một nguồn định giá duy nhất

**Quyết định:**
- **DCF/sensitivity:** đã hợp nhất từ trước (`run_valuation_engine` delegate sang
  `_dispatch_nonfin`, WACC tập trung ở `engine/wacc.py`). Xác nhận không còn
  code trùng dựng cf_dict/WACC — mục action item của B75 coi như đóng.
- **Bank:** XÓA `engine/bank.py` (legacy, chạy trên API Company cũ đã lỗi thời:
  `income`/`balance`/`equity_risk_premium`/`forecast_years` — không tồn tại trên
  model hiện tại; chỉ còn 1 test dùng). Nguyên tắc B3 (Justified P/B dùng
  sustainable ROE) được đưa vào model ACTIVE `bank_general.py`.

**Lý do:** B87 để lại 2 implementation ngân hàng, B3 chỉ áp cho bản legacy chết.
Nay chỉ còn `BankGeneralValuationModel` là nguồn sự thật, honor B3.

**Files:** xoá `valuation/engine/bank.py`; `valuation/engine/models/bank_general.py`
(calculate_pb_valuation ưu tiên sustainable_roe).
**Test:** `tests/test_valuation_accuracy.py::TestB3SustainableRoe` viết lại trên
bank_general; bỏ import legacy.

---

### C6 — Báo cáo định giá 11 phần chuẩn quỹ (SPEC PHẦN B)

**Quyết định:** nâng báo cáo PDF/Word từ 5 phần lên đủ 11 phần chuẩn CTCK/quỹ:
cover (thêm vốn hóa + band khuyến nghị 5 mức MUA/KHẢ QUAN/NẮM GIỮ/KÉM KHẢ
QUAN/BÁN đọc từ `config/defaults.yaml → rating_bands`), luận điểm đầu tư, tóm
tắt định giá, tổng quan DN, bối cảnh ngành, phân tích tài chính lịch sử (+2
biểu đồ mới), bảng giả định, chi tiết định giá (bóc tách WACC + đối chiếu
consensus), kịch bản Bull/Base/Bear + heatmap, rủi ro (+QC flags), phụ lục BCTC.

**Kiến trúc:** tách data khỏi GUI theo spec —
- `valuation/report/report_data.py`: builder thuần gom dữ liệu 11 phần, test độc lập.
- `valuation/report/ai_narrative.py`: DeepSeek sinh NHÁP 4 phần văn bản từ số
  liệu thật, luôn gắn `ai_generated` để template in dấu "Nháp do AI tạo — cần
  analyst review" (PHẦN G); fallback khung gợi ý khi thiếu key/lỗi mạng —
  không chặn xuất báo cáo. Trên UI: nút bấm sinh 1 lần/mã, cache session.
- Kịch bản Bull/Bear với phương pháp proxy (RNAV/SOTP) không co giãn theo
  growth/margin → builder gắn `applicable=False`, báo cáo in ghi chú thay bảng.

**Files:** `valuation/report/{report_data,ai_narrative}.py` (mới),
`template.html` + `build_docx.py` (viết lại 11 phần), `charts.py` (+2 chart),
`views/results.py` (wire), `config/defaults.yaml` (rating_bands).
**Test:** `tests/test_report_data.py` (6, có ca tính tay vốn hóa/ROE/COE),
`tests/test_report_render.py` (5, golden render ACB+FPT đủ 11 section, Word
build được, dấu AI chỉ hiện khi ai_generated). PDF mẫu:
`temp_reports/Bao_cao_chuan_quy_ACB.pdf` (6 trang, đủ 11 phần, verify pypdf).

---

## Sprint: Nâng cấp độ chính xác định giá (2026-06)

### B1 — EBITDA = EBIT + D&A (không dùng magic multiplier)

**Quyết định:** EBITDA được tính là `EBIT + D&A_est`, trong đó `D&A_est = depr_to_revenue[0] × revenue`.

**Lý do:** Code cũ dùng `EBIT × 1.25` — con số ma thuật không có cơ sở tài chính. Theo định nghĩa chuẩn: EBITDA = EBIT + Depreciation & Amortization.

**Files:** `valuation/engine/models/dcf.py:27-28`, `valuation/engine/sensitivity.py:79-80`

---

### B2 — WACC dùng market-cap weights, không dùng book equity

**Quyết định:** `E = shares_outstanding × current_price` (market cap). Fallback về book equity chỉ khi `current_price = 0`, kèm warning vào `company.warnings`.

**Lý do:** CFA/Damodaran chuẩn: WACC weights phải theo giá trị thị trường. Book equity gây bias nặng cho các công ty tăng trưởng cao (VD: FPT có market cap >> book equity).

**Files:** `valuation/engine/models/dcf.py:51-68`, `valuation/engine/sensitivity.py:104-110`

---

### B3 — Justified P/B dùng sustainable ROE, không dùng ROE năm gốc

**Quyết định:** `bank.py` ưu tiên `assumptions.sustainable_roe` nếu được cung cấp. Chỉ fallback về ROE lịch sử nếu `sustainable_roe` là None hoặc <= 0.

**Lý do:** ROE năm gốc có thể bị distort bởi các yếu tố nhất thời (dự phòng lớn, hoàn nhập, lãi/lỗ bất thường). Justified P/B theo Gordon Growth cần ROE dài hạn bền vững.

**Files:** `valuation/engine/bank.py` (hàm calculate_bank_parameters), `valuation/models/financials_bank.py:57` (field sustainable_roe)

---

### B4 — Tax rate ngân hàng lấy từ assumptions.tax_rate, không hardcode 0.20

**Quyết định:** `forecast_bank.py` đọc `tax_rate = getattr(assumptions, 'tax_rate', 0.20)`.

**Lý do:** Hardcode 0.20 cho mọi ngân hàng là không chính xác — một số ngân hàng có ưu đãi thuế (vùng kinh tế đặc biệt, dự án xã hội hóa). Cho phép cấu hình per-company.

**Files:** `valuation/engine/forecast_bank.py:~65`, `valuation/models/financials_bank.py:50` (field tax_rate)

---

### B5 — Effective tax rate và EV/EBITDA target lấy từ config, không hardcode

**Quyết định:**
- Tax rate: tính median từ 3 năm lịch sử (PBT > 0 và tax > 0). Fallback: `config/defaults.yaml → sector_tax_rates`.
- EV/EBITDA target: `config/defaults.yaml → sector_ev_ebitda`, match keyword trên `sector_str`.
- Giới hạn: `effective_tax` trong [0.05, 0.25] để tránh outlier.

**Lý do:** Hardcode tax/multiple theo ngành vào Python code vi phạm nguyên tắc "no magic numbers". Config yaml dễ update mà không cần sửa code.

**Files:** `valuation/data_access/repo.py` (hàm build_company_from_db), `config/defaults.yaml` (blocks sector_tax_rates, sector_ev_ebitda)

---

### Golden Test — Fixture tính tay FPT-like & VCB-like

**Quyết định:** Golden test dùng fixture synthetic (không pull DB) với số tính tay verify ±10% per AGENTS.md.

- **FPT-like:** revenue=100 ty, ebit=15 ty, depr_to_rev=3%, price=100,000 VND, shares=1,000M → EBITDA=18 ty
- **VCB-like:** equity=120,000 ty, shares=3,723M, sustainable_roe=20%, g=3%, Re=12% → BVPS=32,235 VND, Justified P/B≈1.94, FV≈62,536 VND

**Lý do:** Fixture độc lập với DB, chạy nhanh, không phụ thuộc network. Số tính tay cho phép detect regression ngay lập tức.

**Files:** `tests/test_valuation_accuracy.py` (13 tests, tất cả PASSED)

---

### Kiến trúc — Hai engine path độc lập cần sync

**Quyết định:** `engine/models/dcf.py` (DCFValuationModel.from_pydantic) và `engine/sensitivity.py` (run_valuation_engine) đều build cf_dict độc lập. Cả hai phải được cập nhật đồng thời khi sửa B1/B2.

**Lý do:** Phát hiện trong sprint này: sensitivity.py có code duplicate của dcf.py. Đây là tech debt — cần refactor về 1 điểm duy nhất trong tương lai, nhưng chưa làm ngay để tránh phá interface.

**Action item (future):** Extract `_build_cf_dict(company)` và `_compute_wacc(company, cf_dict)` thành utility functions dùng chung.

---

### Kiến trúc — legacy bank.py vs bank_general.py

**Quyết định:** `engine/bank.py` (legacy dict API) và `engine/models/bank_general.py` (Pydantic) là hai implementation riêng. B3 chỉ applied vào `bank.py`. `bank_general.py` dùng ROE dự phóng năm 5 — chấp nhận được vì projection model sẽ converge về sustainable ROE.

**Lý do:** Không touch `bank_general.py` để tránh phá Streamlit UI đang dùng nó. Tech debt cần xử lý sau.

---

## 2026-08-30 — DeepSeek chỉ chạy từ nút kiểm chứng và sinh báo cáo

**Quyết định:** Tab BCTC có một nút duy nhất `Kiểm chứng dữ liệu & sinh báo
cáo qua DeepSeek`. Một lần bấm thực hiện tối đa một API call. Python chạy các
identity check, kiểm tra trường bắt buộc, growth/upside bất thường trước; sau đó
chọn `deepseek-v4-flash` cho ca thường hoặc `deepseek-v4-pro` khi có lỗi/cờ
trọng yếu. Cả hai chạy non-thinking để JSON ổn định và tiết kiệm token.

**Ranh giới:** DeepSeek chỉ phản biện dữ liệu đang có và sinh bản nháp; không tự
sửa hoặc ghi DB. Khi không có filing gốc trong payload, AI chỉ được ghi `nghi
vấn`, không được khẳng định đã đối chiếu nguồn chính thức hay bịa số thay thế.

**Tái sử dụng:** Kết quả được cache theo ticker trong Streamlit session. Tab kết
quả/PDF chỉ đọc lại bốn phần narrative đã cache, không gọi DeepSeek lần hai.

**Files:** `valuation/report/verified_summary.py`,
`valuation/views/input_financials.py`, `valuation/views/results.py`,
`config/defaults.yaml`, `tests/test_verified_summary.py`.

### Mở rộng một nút cho toàn bộ nội dung AI

**Quyết định:** Nút duy nhất ở tab BCTC sinh đồng thời bốn phần narrative dùng
cho màn hình/PDF và phần tổng hợp đa-CTCK trong cùng một JSON. Bản tổng hợp CTCK
được upsert theo ticker vào bảng `consensus_synthesis`; tab So sánh CTCK chỉ đọc,
không còn nút gọi DeepSeek riêng.

**Giới hạn chi phí:** Mỗi lần bấm vẫn tối đa một API call. Ngữ cảnh CTCK giới hạn
8 báo cáo và 1.200 ký tự tóm tắt mỗi báo cáo. Nếu không tải được tóm tắt công
khai, hệ thống dùng dữ liệu mục tiêu/khuyến nghị đã lưu và hiển thị cảnh báo,
không bịa luận điểm định tính.

## 2026-09-28 — Rà soát độc lập & sửa mô hình (D34–D41)

Bối cảnh: rà soát độc lập cho thấy 43/101 mã lệch giá > ±50% và chỉ 11% mã nằm
trong ±10% trung vị giá mục tiêu CTCK; thiên lệch có hệ thống theo ngành. Báo cáo
đầy đủ: kế hoạch rà soát ngày 2026-09-28. Baseline trước sửa:
`reports/audit/baseline_20260928.csv`.

### D34 — Định nghĩa dữ liệu đầu vào
- LN cho EPS/P/E/ROE/DDM = `attributable_to_parent_company` (LN cổ đông mẹ);
  vốn cho BVPS/P/B/ROE = `BalanceSheet.parent_equity` = VCSH − CĐKKS (VAS: mã 400
  đã gồm mã 429).
- Số cp: nhân (1 + tỷ lệ) cho cổ tức CP/thưởng đã qua GDKHQ mà vốn điều lệ trên
  BCTC gần nhất chưa ghi nhận (`ttm_helper._unreflected_split_factor`). Quyền mua/
  ESOP/riêng lẻ chờ BCTC vì kèm tiền mới.
- Giá: tải incremental phát hiện điều chỉnh hồi tố ở đoạn chồng lấn → tải lại toàn
  bộ lịch sử mã đó (nguyên nhân chuỗi gãy 03/07/2026).
- `build_company_data(as_of)` chỉ dùng kỳ đã tới hạn công bố (TT 96/2020) — chống
  lookahead khi hiệu chỉnh.

### D35 — Cầu nối EV → VCSH đầy đủ
VCSH = EV − nợ vay + tiền + đầu tư ngắn hạn − CĐKKS + **đầu tư tài chính dài hạn
ròng (mã 250)**. EBIT không gồm lãi liên kết nên phải cộng tài sản này ở cầu nối
(trước đây mất trắng: KDC ~53% VCSH, GMD ~31%). Dùng dòng tổng 250 để không cộng trùng
các dòng con. Không bịa doanh thu/số cp khi thiếu (trước: 100.000 tỷ, 1.000 cp).

### D36 — Chuẩn hóa chu kỳ theo biên
Mức giữa chu kỳ = trung vị biên (GỒM năm lỗ) × doanh thu TTM
(`models/base.midcycle_level`), áp trong P/E, EV/EBITDA và chân phụ DCF cho mã
`business_nature = Cyclical`. Bỏ hack ghi đè `ebit`/`depreciation` trong batch (đếm
D&A hai lần, chỉ lấy năm lãi). EBITDA dùng D&A thật từ LCTT.

### D37 — Một g vĩnh viễn, fade tăng trưởng về g
`coe_convention.terminal_growth` = 4,0% danh nghĩa VND, trần min(rf, GDP danh nghĩa
dài hạn), dùng chung DCF/DDM/RI. Doanh thu fade từ trung vị lịch sử về đúng g ở năm
5 (bỏ neo 8% rồi rơi xuống 2%). g cũ 2% < lạm phát = tăng trưởng thực âm vĩnh viễn.

### D38 — Ngân hàng
Bỏ cộng trùng tăng trưởng tín dụng hệ thống; ràng buộc VCSH/Tổng TS ≥ trung vị 3 năm
của chính NH; NIM/CIR giữ mức TTM (bỏ lộ trình luôn cải thiện); chi phí tín dụng =
trung vị 3 năm tài chính đầy đủ (loại TTM chồng kỳ); payout từ cổ tức thực trả.
ROE bền vững = ROE năm 5 của dự phóng chuẩn hóa (trung vị lịch sử chỉ để gắn cờ
`BANK_ROE_FORECAST_VS_HISTORY`). Chân "relative" = P/B trung vị 5 cuối năm của chính
NH (trước là P/B hợp lý cùng ROE/COE/g với RI — không kiểm tra chéo được gì).

### D39 — CTCK, điện, bội số, beta
- CTCK: chân P/B = P/B lịch sử 5 năm của chính công ty (thay P/B hợp lý khi
  ROE giữa chu kỳ < COE khẳng định mọi CTCK hủy giá trị).
- DDM điện: payout thực tế 4 năm; bỏ DDM nếu payout < 40% (cổ tức không đại diện
  FCFE); cùng đường tăng trưởng và g với DCF.
- Routing theo `raw_primary` của chính routing.json: GEX, HDG, PC1, VCG, VGC → SOTP
  (thiếu dữ liệu mảng → NOT_RATED minh bạch); BMP, HT1 → "Vật liệu xây dựng".
- P/E, EV/EBITDA mục tiêu = trung vị 5 cuối năm của chính mã (dải hợp lệ trong
  `relative_multiples`); hằng số ngành chỉ dự phòng + cờ `MULTIPLE_FROM_SECTOR_CONSTANT`.
- Beta: lợi suất tuần 3 năm trên giá đã điều chỉnh, Blume; thiếu dữ liệu → beta
  mặc định config. Bỏ gọi vnstock live trong lúc định giá.

### D40 — Khuyến nghị, cổng chặn, vĩ mô, kịch bản
- Một nguồn khuyến nghị: `decision_engine.recommend` (MOS theo bản chất ngành trong
  config + cổng chặn), nhãn `REC_LABELS_VI`; UI/PDF/Sheets/báo cáo dùng chung.
- Batch tôn trọng `publication_allowed`; `STALE_PRICE` là lỗi chặn; số AI bóc tách
  (RNAV/SOTP) cần analyst xác nhận đối chiếu mới phát hành.
- Bỏ công tắc +2% ERP khi CPI > 5% (vách đứng, ghi đè object caller); vĩ mô chỉ nới MOS.
- Kịch bản: sốc cộng cho tăng trưởng, sốc biên tới cả biên giữa chu kỳ, Bear stress
  chi phí tín dụng ×1,5, trọng số 25/50/25 → giá trị kỳ vọng.
- Ma trận độ nhạy: trục WACC đi thẳng vào WACC (`Assumptions.wacc_override`).

### D41 — Dọn engine trùng
Xóa `engine/dcf.py` (không caller); route API `/revalue` gọi `valuate()` thay vì dựng
input hardcode riêng (681 → 135 dòng). `overlay_credit_growth` bị xóa (D38).

### D42 — Golden test tái lập báo cáo CTCK
Giả định trích từ 18 báo cáo PDF thật (lưu nội bộ `reports/broker_pdfs/`, gitignore) vào
`tests/golden/broker_assumptions.yaml`. `tests/test_golden_broker.py` tái lập các chân có cùng
quy ước với mô hình (P/B thị trường, trọng số pha trộn VCB/MBB, P/E HPG) với sai số < 10%.
RI/DCF đầy đủ của Shinhan không so trực tiếp: kỳ đầu 6 tháng và hệ số chiết khấu riêng
(HPG: hệ số năm 1 = 0,80 với WACC 11,62%) — so thẳng sẽ đo quy ước, không đo thuật toán.

## 2026-09-29 — Hoàn tất các mục rà soát còn dở (D43)

### D43 — Làm sạch bội số, chặn kết quả cực đoan, cờ tài sản ngắn hạn
- **Bội số lịch sử:** `own_history_multiple(kind=...)` bỏ từng quan sát ngoài dải
  `relative_multiples` TRƯỚC khi lấy trung vị. CTD: năm lãi đáy cho P/E 120x kéo trung vị
  lên 27,9x → áp lên LN phục hồi ra FV gấp 3 thị giá; sau sửa 18,9x.
- **Kết quả cực đoan** (`UPSIDE_EXTREME_REVIEW` > +150%, `DOWNSIDE_EXTREME_REVIEW` < −60%)
  chặn phát hành (NOT_RATED) nhưng giữ số chẩn đoán — mục G2 của rà soát. Vd HHV (BOT, nợ
  gấp 3,5 lần vốn hóa): DCF vĩnh viễn cho dự án có thời hạn thu phí ra +296%; cần lịch hết
  hạn nhượng quyền từng dự án để định giá đúng, không tự đặt.
- **Cờ `UNEXPLAINED_CURRENT_ASSETS`:** phần dư tài sản ngắn hạn (đã trừ ĐTNH) > 35% → nghi
  mất dòng khi nạp. Đã khớp đúng nhóm mã còn chờ sửa item_id trùng.
- `other_current_assets`/`other_long_term_assets` là phần dư GỒM cả ĐTNH/đầu tư dài hạn
  (chỉ dùng hiển thị, cộng đúng về tổng tài sản) — đã ghi rõ trong model.
- Gỡ `VCBValuationModel` (không còn chạy ở app/batch/API); test ngân hàng chạy qua đường thật.
- `scripts/audit_vn100_snapshot.py` xuất thêm danh sách mã lệch > ±25% so với trung vị CTCK
  (`<label>_consensus_review.csv`) để analyst ghi giải thích — không ép khớp.
- **NT2:** PPA hiện tại tới 2032 rồi ký lại (BSC 15/06/2026) → KHÔNG cắt dòng tiền ở 2032;
  chưa có năm hết vòng đời nhà máy đáng tin → giữ DCF + DDM, ghi nhận rủi ro ký lại PPA.

### D44 — Bảng định giá chuẩn Excel, đồng thuận không điều chỉnh quyền lần hai (2026-09-29)
- `scripts/export_valuation_book.py` → `reports/vn100_dinh_gia_chuan_<ngày>.xlsx` (8 sheet). GTHL lấy
  từ `batch.value_ticker` (cùng lõi Streamlit); upside/khuyến nghị/lệch CTCK/bội số là công thức Excel.
  Đã đối chiếu: khuyến nghị công thức khớp engine 100/100 mã, số CTCK khớp `consensus_view` 100/100.
  Ghi chú analyst theo mã ở `config/analyst_notes.yaml` (chỉ sự kiện đã kiểm chứng, không là đầu vào).
- **Không chia giá mục tiêu CTCK theo cổ tức CP/thưởng:** tại 44 ngày GDKHQ 2026 giá VCI không có
  khoảng trống (kể cả VHM 100%) và giá mục tiêu Simplize/24hMoney trước/sau GDKHQ cùng mặt bằng →
  cả hai nguồn đã điều chỉnh quyền; chia thêm là điều chỉnh hai lần. PNJ lệch là do giá sập 07/2026.
- **Chờ duyệt (chưa sửa):** dự phóng ngân hàng dùng chi phí tín dụng trung vị 3 năm tài chính và
  ràng buộc E/A tối thiểu = trung vị lịch sử. VPB: CP tín dụng 4,53% vs TTM ~2,75% và E/A 12,7% < 14,3%
  → LNST năm 1 thấp hơn TTM 44%, GTHL thấp hơn trung vị CTCK 57%. File Excel ghi rõ ở cột lưu ý.
- Log `repair_duplicate_bs_items` đặt tên theo giờ (lượt 10:35 từng ghi đè log lượt 10:04 cùng ngày);
  trạng thái "đã sửa" trong bảng lấy từ DB (dòng BS tách hậu tố `__`), không từ log.
- `.gitignore`: `reports/broker_pdfs/` (bản text trích báo cáo CTCK trước đây chưa bị chặn) và `reports/*.xlsx`.

### D45 — DCF: liên doanh theo lợi nhuận, CapEx khớp tăng trưởng (2026-09-30, người dùng duyệt)
- **Lỗi:** GMD 56.864 so với trung vị CTCK 86.750. Chân DCF (43.245) cộng liên doanh theo
  sổ sách (4.811 tỷ) dù lãi liên doanh TTM 1.382 tỷ (≈3,5x lợi nhuận), và giữ CapEx/DT lịch sử
  28% phẳng 5 năm trong khi tăng trưởng fade 15% → 4,7%.
- **Sửa (Damodaran):** (1) cầu nối chân DCF thay sổ sách liên doanh bằng lãi liên doanh TTM ×
  P/E lịch sử của chính công ty mẹ (`target_pe`); lỗ hoặc không tách được sổ sách → giữ sổ sách;
  chân EV/EBITDA không đổi (bội số lịch sử đã chứa giá thị trường của liên doanh). Cờ
  `JV_VALUED_AT_PE`. (2) CapEx/DT mặc định = khấu hao + g/(1+g) × (1/doanh thu trên vốn − vốn
  lưu động/DT), sàn = khấu hao; doanh thu trên vốn = DT TTM / (VCSH + nợ vay − tiền − ĐTNH −
  ĐTDH), kẹp `dcf.sales_to_capital_band` [0,3; 5]. Vốn vận hành ≤ 0 → giữ CapEx lịch sử.
  Người dùng vẫn sửa CapEx/DT trên giao diện như cũ.
- **Kết quả toàn VN100:** GMD 56.864 → 77.458 (≈ giá, NẮM GIỮ); VSC +35%, CMG +35%, HSG +89%,
  FPT +6%, HPG +7%. Giảm: SBT −14%, PLX −10%, DCM −9%, NT2 −9%, MWG −8% — mô hình cũ ngoại suy
  CapEx < khấu hao (vừa tăng trưởng vừa rút vốn) hoặc hệ số doanh thu/vốn thô vô lý (PLX 26 do
  tiền mặt lớn). Lệch trung vị so với CTCK −18,0% → −14,7%. Test: tests/test_dcf_jv_reinvestment.py.
- **Lưu ý:** FPT định giá phần FPT Telecom theo P/E của FPT (~16x) — có thể cao hơn P/E thị
  trường của FPT Telecom; xem là cận trên. Chưa dùng giá thị trường của liên doanh niêm yết.

### D46 — Chặn công bố khi có sự kiện trọng yếu mô hình chưa phản ánh (2026-10-02, người dùng duyệt)
- `config/event_holds.yaml` (bắt buộc `reason` + `source`, có `since`) → cờ `MATERIAL_EVENT_HOLD` trong
  cổng phát hành của `valuate()`: không khuyến nghị, không xếp hạng, số chẩn đoán vẫn giữ.
- **PNJ** (từ 25/09/2026): vụ án P-Lab, kế hoạch 2026 lỗ 6.271 tỷ, phát hành riêng lẻ ~107% số cp — BCTC
  và giá mục tiêu CTCK đều lập trước biến cố nên mô hình ra "MUA +133%". Nguồn báo chí 30/09, chưa đối
  chiếu tài liệu ĐHĐCĐ gốc. Gỡ khi có BCTC phản ánh dự phòng và số cp mới.
- Giới hạn: so `since` với ngày chạy (không theo `as_of` backtest) → chỉ chặn thừa, không lookahead có lợi.

### D47 — Giả định ngân hàng theo số thực tế (2026-10-02, người dùng duyệt)
- **Beta:** trung vị beta Blume nhóm NH VN100 (beta ngành bottom-up, Damodaran) thay beta hồi quy riêng
  (`ttm_helper.bank_peer_beta`, hiện 0,898). ACB 0,77 → 0,90 (COE 10,9% → 11,9%).
- **Chi trả tiền:** max(thực trả 3 năm, cổ tức tiền đã GDKHQ 12 tháng / LN TTM). MBB 8,7% → 26,8%
  (1.000đ GDKHQ 09/07/2026 trả ở quý 3, ngoài cửa sổ TTM). DPS chia cho các đợt cổ tức CP sau đó.
- **Chi phí tín dụng:** max(TTM, trung vị 3 năm tài chính); TTM > `bank_terminal.credit_cost_spike_multiple`
  (2,0) × trung vị coi là trích lập đột biến một lần → giữ trung vị + cờ `BANK_CREDIT_COST_SPIKE` (STB).
- **Ràng buộc vốn:** sàn VCSH/TS = min(hiện tại, trung vị 3 kỳ) thay cho trung vị. Phương án đã duyệt "bỏ
  hẳn ràng buộc" bị loại sau khi chạy thử: NH mỏng vốn tăng tài sản 25%/năm không cần vốn (TCB +48%,
  TPB +34%), trái ràng buộc CAR. Sàn mới không ép VPB giảm đòn bẩy (lỗi gốc) nhưng không cho tăng đòn
  bẩy vượt hiện tại. Đòn bẩy cao hơn lịch sử → cờ `BANK_LEVERAGE_ABOVE_HISTORY`.
- **Kết quả nhóm NH:** trung vị |lệch| so với CTCK 18,3% → 16,0%; ACB +16% → −3%; BID −7% → +1%;
  TPB −9% → 0%; TCB −27% → −17%; CTG −33% → −24%. EIB: ROE dài hạn 2,2% < g → TERMINAL_IMPOSSIBLE,
  không xếp hạng (trước 11.065, −57% so với CTCK). Test: `tests/test_bank_assumptions_d47.py`.

### D48 — Số cp sau cổ phiếu thưởng thiếu ngày GDKHQ; quy đổi tay ×0,9033 là sai (2026-10-02)
- `config/corporate_actions.yaml`: FPT (thưởng 10%, 21/09), PHR (80%, 11/09), VPB (26,04%, 24/09) = số VSDC
  trước sự kiện × (1+tỷ lệ), TẠM TÍNH; GMD 432.892.509 (ESOP, VSDC 11/08) và 649.338.763 từ 07/10;
  HDB 6.506.859.219 từ 09/10. Override chỉ hiệu lực từ ngày GDKHQ (chống lookahead).
- **Phát hiện:** giá VCI đã điều chỉnh quyền nên P/E/EV-EBITDA lịch sử × chỉ tiêu/cp BẤT BIẾN theo số cp
  (sai số số cp cũ triệt tiêu trong nhánh bội số); chỉ nhánh DCF bị phóng đại. Quy đổi tay cả GTHL
  ×0,9033 (bảng/slide 30/09) là điều chỉnh quá tay: FPT đúng 87.805 (không phải ≈82.900), PHR 28.030
  (không phải ≈20.000). Phần liên doanh FPT Telecom tăng nhẹ vì P/E lịch sử nay đúng.
- Cờ mới `CORPORATE_ACTION_UNDATED`: cổ tức CP/thưởng công bố trong 180 ngày, thiếu GDKHQ, chưa có
  override → nhắc analyst thêm số cp VSDC. Test: `tests/test_shares_override_2026q3.py`.

### D49 — Golden test đối chiếu đồng thuận CTCK toàn VN100 (2026-10-02, người dùng duyệt)
- `tests/test_golden_consensus.py` chạy harness hiệu chuẩn trên ảnh DB 28/09/2026:
  (1) mọi mã lệch ngoài band (±20%; SOTP/RNAV rộng hơn) phải có mục trong `calibration_registry.yaml`
  còn hạn — không lệch im lặng, không mục lỗi thời; (2) `verified=true` trong routing.json chỉ khi
  ≥3 CTCK và |lệch| ≤ `golden_tolerance` 10% (luật vàng #8).
- Registry: thêm 19 mã (16 must_fix có luận điểm, 3 data_blocked vì < 3 CTCK), gỡ HPG/TPB đã vào band.
  9 mã DCF thấp hơn CTCK 27–58% chung một nguyên nhân chờ duyệt: ROIC dài hạn = WACC. Owner
  "claude-de-xuat (cho phi duyet)" — người dùng cần rà và nhận.
- `verified`: gỡ 12 mã không có bằng chứng (VCB −10,7%, TCB −17%, HPG −14,5%, MWG −27%, GVR −34%,
  HT1 +22%, VRE −55%; VHM/VIC/BCM/MSN/PVD không đo được). Còn FPT (−4,8%).
- `pytest.ini` `testpaths = tests`: các script test cũ ở gốc/scripts làm `pytest` không tham số lỗi.

### D50 — Khung "Chỉ số vĩ mô" trên sidebar + rút gọn tin AI (2026-10-10, người dùng duyệt)
- `valuation/views/macro_panel.py`: 7 ô (Fed cận dưới–cận trên, lãi suất SBV, TPCP Mỹ/VN 10N, CPI VN YoY,
  USD/VND, dầu WTI) đọc `macro_series`, không gọi mạng khi render; ô quá hạn `macro_dashboard.stale_days`
  hiện "⚠️ cũ". Delta chỉ so với kỳ trước khi khoảng cách ≤ 2× ngưỡng cũ (tránh khoảng trống dữ liệu
  hiện như thay đổi một kỳ).
- "Nhận định nhanh" theo quy tắc cố định, không AI: CPI so mục tiêu 4,5% (`cpi_target`); lãi suất thực
  = TPCP VN 10N − CPI; chênh lệch TPCP VN − Mỹ 10N; Fed đổi lãi suất trong `fed_lookback_days`.
  Không phải khuyến nghị đầu tư.
- Nguồn mới: FRED CSV công khai (`fred.stlouisfed.org`: DFEDTARU/DFEDTARL/DGS10, % → decimal) qua
  `valuation/ingest/fred_fetcher.py`; thêm `nso.gov.vn` vào allowlist. Chỉ gọi khi bấm "Cập nhật vĩ mô".
- Dữ liệu ghi 10/10 (backup `backups/vn100_full_before_macro_20261010_1850.db`): FRED 162 điểm;
  CPI_YOY 7–9/2026 = 4,45% / 4,89% / 5,08% đối chiếu PDF NSO (báo chí có bản ghi nhầm 5,8%).
- Nguyên nhân gốc tỷ giá/dầu đứng ở 10/07: `yfinance` (khai báo trong requirements-integrations.txt)
  chưa cài trong `~/.venv` → đã cài.
- Hệ quả: CPI 5,08% > 5% → `MacroEnvironment.is_macro_stressed` = True → MOS giao diện +5 điểm %
  (thiết kế sẵn có; batch/Excel không đổi).
- Tin AI: prompt 3 mục (VN ≤2, Thế giới ≤2, Tác động 1–2 ý, ≤20 từ/ý), đưa số khung vĩ mô vào prompt để
  không mâu thuẫn, max_tokens 1500 → 600. Test: `tests/test_macro_panel.py`.

### D51 — "Tổng quan thị trường" nhìn 5 giây trên đầu sidebar (2026-10-10, người dùng duyệt thiết kế)
- `valuation/views/market_overview.py`: đèn tổng Thuận lợi / Trung tính / Khó khăn = tổng 4 trụ cột
  −1/0/+1 (≥ +2 / ≤ −2): **Vĩ mô & chính sách** (CPI so mục tiêu, TPCP VN − Mỹ, hướng Fed/SBV),
  **Xu hướng & độ rộng** (VN-Index so MA50/MA200, % mã VN100 trên MA50 của chính nó),
  **Khối ngoại** (mua/bán ròng VN100 20 phiên, vùng trung tính ±2.000 tỷ), **Định giá** (upside trung vị
  theo đợt định giá VN100 mới nhất ÷ giá đóng cửa mới nhất). Ngưỡng ở `market_overview` — HEURISTIC,
  người dùng chỉnh được. Chấm điều kiện hiện tại, không dự báo giá, không khuyến nghị.
- Ngành/mã (người dùng chọn: chỉ theo giá + dòng tiền, không ánh xạ vĩ mô → ngành): đà 20 phiên so
  TRUNG VỊ VN100 (cùng ngày dữ liệu, không lệch khi VN-Index chậm hơn giá cp); "mã có lực" = trên MA50
  + vượt trung vị + khối ngoại mua ròng; ngành mạnh/yếu khi đà tương đối và khối ngoại cùng chiều.
- Ngày chỉ vài mã được cập nhật lẻ (< 50% VN100) bị cắt khỏi tính toán.
- Tin AI: cùng lần gọi DeepSeek trả thêm dòng `TAGS:` JSON (mã/ngành được tin nhắc tích cực/tiêu cực);
  chỉ giữ mục thuộc whitelist mã VN100 + tên ngành (chống AI bịa / nội dung tin chèn chữ vào UI). Hash
  cache gồm `_PROMPT_VERSION` để tin không đổi vẫn được viết lại theo định dạng mới.
- Nguyên nhân gốc VN-Index đứng ở 28/09: VNINDEX có `is_vn100=0` nên "Quét VN100" bỏ qua. Đã thêm
  vào `weekly_updater` và nút "Cập nhật vĩ mô". Ghi 10/10: +9 phiên (đến 09/10, 1.735,09 điểm); chạy
  lại không nhân đôi. Backup `backups/vn100_full_before_vnindex_20261010.db`. Hệ quả: beta tính từ
  VNINDEX đổi nhẹ (FPT 87.993 → 87.848). Test: `tests/test_market_overview.py`.

### D52 — Mục VN-Index + "Sắp tới" trong Tổng quan thị trường; bỏ điểm số trụ cột (2026-10-12)
- Đèn tổng thôi hiện "điểm −3/4" (người dùng thấy khó hiểu) → "KHÓ KHĂN — bất lợi: vĩ mô, xu hướng,
  khối ngoại · thuận: …". Cách chấm nhãn không đổi (D51).
- 📊 VN-Index: thay đổi 5/20 phiên; xu hướng ngắn/trung/dài hạn = giá trên/dưới MA20/50/200; RSI 14
  (Wilder, alpha 1/n); kháng cự/hỗ trợ = mức gần nhất trên/dưới giá trong {MA20/50/200, đỉnh/đáy 60 phiên}.
- 🔭 Sắp tới: KỊCH BẢN CÓ ĐIỀU KIỆN (vượt kháng cự / thủng hỗ trợ, RSI quá mua/quá bán, nghiêng theo
  nhãn tổng) — không dự báo giá, không khuyến nghị. Ngưỡng: `market_overview` (ma_trend, rsi_*, level_window).

### D53 — Giao diện điện thoại + chạy trên VPS (2026-10-12)
- Kiểm tra bằng workflow 9 agent (6 rà code theo màn hình, 1 trình duyệt 375px, 1 VPS, 1 tổng hợp) → 86 phát hiện.
- CSS (`workspace.css`, chỉ trong media query → desktop không đổi): ≤768px nút mở sidebar thành "Chọn mã · Vĩ mô"
  44px + header sidebar dính; ≤640px tab xuống dòng (2/5 tab từng nằm ngoài màn hình), header gọn (thông tin mã lên từ
  y=313 về 159), cặp chỉ số vĩ mô giữ 2 cột trong sidebar; màn cảm ứng (`hover:none` + `pointer:coarse`) tắt kéo
  Plotly để vuốt cuộn được trang (đổi lại chart tĩnh, không tooltip khi chạm). Bỏ selector chết `[data-testid="column"]`.
- Python: legend 6 chart xuống dưới vùng vẽ (chart "Cấu trúc tài sản" từng chỉ còn 64px vùng vẽ ở 375px) — thay
  đổi desktop duy nhất; thẻ khuyến nghị flex-wrap + `clamp()`; ghim cột Hạng/Mã/CTCK trong bảng; bỏ chữ "sidebar/👈".
- `requirements.txt` ghim `streamlit==1.55.0`, `plotly==7.0.0` (CSS dựa vào data-testid nội bộ).
- VPS: `docs/DEPLOY_VPS.md` — systemd nghe 127.0.0.1, Caddy HTTPS + basic_auth (app không có đăng nhập; link công
  khai = ai cũng bấm được nút DeepSeek/quét dữ liệu), giải nén DB trước lần chạy đầu.

### D54 — Điện thoại: thanh tab đáy kiểu app, nhận diện điện thoại ở server (2026-10-12)
- ≤640px: 5 tab cấp trang thành thanh điều hướng cố định ở đáy, icon + tên ngắn (BCTC · Định giá · CTCK ·
  Cổ tức · VN100); chỉ chọn tab con trực tiếp của khối nội dung (tab lồng không đổi). Bấm tab → cuộn về đầu
  nội dung tab (`st.html(..., unsafe_allow_javascript=True)`, chỉ gửi cho điện thoại).
- `valuation/views/device.py`: `is_phone()` = "Mobi" trong User-Agent (MDN; iPad/tablet Android = desktop);
  `phone_collapsible(label)` (điện thoại: expander đóng; desktop: container không khung → như cũ);
  `render_alerts` (điện thoại: 2 cảnh báo nặng nhất, còn lại gom vào "Cảnh báo khác (N)" — không xoá cảnh báo).

### D55 — Tab VN100 làm lại: xếp hạng theo upside mô hình + 5 mã tích sản (2026-10-12, người dùng chọn)
- Bảng toàn VN100: hạng theo upside = giá trị hợp lý (đợt định giá VN100 mới nhất) ÷ giá đóng cửa mới nhất − 1;
  mã chưa định giá được ở cuối (không có hạng). Bỏ hai chiến lược, AI, thẻ chi tiết, lịch sử… (rườm rà).
- 5 mã tích sản (người dùng chọn "Top 5 upside có lọc chất lượng"): loại cờ trong `blocking_flags` +
  CORPORATE_ACTION_UNDATED/MATERIAL_EVENT_HOLD (số cp/sự kiện chưa tin được), upside > `max_upside_pct` (rà soát),
  GTGD TB 20 phiên < `scales.min_traded_value_vnd`; tối đa `max_per_sector` mã/ngành. Đợt 06/10 + giá 09/10:
  DBC, NT2, MBB, FPT, DCM. Sàng lọc theo mô hình, không phải khuyến nghị.
- Lỗi gốc phát hiện: cột `prices_daily.value` luôn trống (vnstock không trả) → engine xếp hạng cũ
  (`investment_snapshot.py:210`) đánh "thanh khoản không đạt" cho MỌI mã. Tab mới ước lượng GTGD = giá đóng cửa ×
  khối lượng (gần đúng, không phải VWAP). Engine chưa sửa — chờ duyệt.
- Mở tab Cổ tức / VN100 → CSS ẩn khối định giá phía trên thanh tab (`st.container(key="valuation_head")`).
- (D54 bổ sung) Điện thoại thu gọn: bảng KQKD/CĐKT/kiểm tra cân đối, báo cáo AI nháp, quan điểm & kịch bản,
  phương pháp & khoảng giá, biểu đồ kỹ thuật, waterfall, heatmap độ nhạy, dự phóng 5 năm, consensus chi tiết,
  lưu/xuất báo cáo, giá mục tiêu từng CTCK, luận điểm CTCK, lịch quyền VN100; khung chỉ số vĩ mô sidebar; tin vĩ mô
  đóng sẵn. Luôn hiện: thẻ khuyến nghị, nút DeepSeek, biểu đồ tổng quan, bảng kịch bản, KPI CTCK + kết luận hiệu
  chuẩn, sự kiện quyền sắp tới, bảng xếp hạng + 5 mã tích sản. Cảnh báo info/success không bao giờ chiếm ô hiện ngay.

### D56 — Nhận định nhanh lịch quyền: 3 tiêu chí cổ tức; sửa thanh khoản engine (2026-10-12, người dùng chọn)
- Thay bộ lọc tích sản nghiêm (100/100 mã rớt vì chưa có hồ sơ quản trị, golden test, thanh khoản lỗi, độ phủ)
  bằng 3 tiêu chí người dùng chọn: (1) upside mô hình > 0 và không lỗi dữ liệu (dùng chung tab VN100);
  (2) cổ tức TIỀN MẶT 12 tháng ≥ `attractive_dividend_yield_pct` (5%) và trả đều `dividend_consistency_years`
  (3) năm gần nhất; (3) giá `price_impact_long_sessions` (20) phiên sau GDKHQ vượt VN-Index ở ≥
  `dividend_min_hit_rate` (60%) số lần, tối thiểu `dividend_min_events` (3). Nhãn: ĐẠT 3/3 / THEO DÕI (2/3) /
  CHƯA ĐẠT / CHƯA HẤP DẪN (upside ≤ 0) / CHƯA ĐỦ CƠ SỞ. Không bao giờ "MUA".
- Phản biện đã đưa vào: chỉ tính cổ tức tiền (cổ tức CP/thưởng không tạo giá trị); yêu cầu trả đều (tránh bẫy
  cổ tức một lần); so với VN-Index (tách "cả thị trường tăng"); mẫu tối thiểu 3 lần; ghi chú thuế 5% và việc giá
  giảm tương ứng cổ tức ngày GDKHQ.
- Phát hiện: giá DB đã điều chỉnh cổ tức tiền (254 lần chia: ngày GDKHQ trung vị −0,24% so với lý thuyết −2,9%)
  → tiêu chí (3) đo trên giá điều chỉnh = tổng lợi nhuận. Hệ quả: `analyze_historical_price_impact` (phân tích
  chuyên sâu) đang CỘNG cổ tức lần nữa vào "tổng tài sản" cho cổ tức tiền — chưa sửa, chờ duyệt.
- Engine xếp hạng: `traded_values()` — GTGD = `value` hoặc giá đóng cửa × khối lượng (cột value luôn trống);
  có hiệu lực từ lần "Định giá lại VN100" tới. Đợt 12/10, ngưỡng 5%: 11 mã VN100 đạt tiêu chí (2), 26 mã đạt (3);
  17 sự kiện trong 90 ngày tới chưa sự kiện nào đạt 2/3.
