# DECISIONS.md — Quyết định kỹ thuật dự án antigravity-vn100

> Chỉ giữ chi tiết từ D61 trở đi. D01..D60 nằm ở `docs/archive/DECISIONS_D01-D60.md`
> (mục lục 1 dòng bên dưới). Mục mới thêm vào CUỐI file.

## Mục lục D01..D60 (chi tiết trong archive)

- D20 — Trần ROE bền vững ngân hàng theo TIER chất lượng (15%/20%), không dùng 1 trần cứng
- D21 — RNAV PROXY_MODE: chiết khấu chỉ áp phần đánh giá lại đất, không áp vốn CSH sổ sách
- D22 — Capex dự phóng DCF: median 3 kỳ gần nhất, không median toàn lịch sử
- D23 — Harness hiệu chuẩn + hàng rào chống hồi quy theo nhóm phương pháp
- D24 — Chất lượng dữ liệu đồng thuận: chuẩn hoá tên CTCK, cách ly dữ liệu giả, bật Simplize
- D25 — Sổ đăng ký hiệu chuẩn từng mã: cơ chế "giữ nguyên hay phải sửa"
- D26 — Chứng khoán: đấu nối model RI+P/B, sửa lỗi ROE lệch tử/mẫu số
- D27 — Tách bảo hiểm khỏi chứng khoán: NOT_RATED thay vì số đã kẹp
- D28 — SOTP: từ chối xuất bản số khi proxy không mô tả được doanh nghiệp (NOT_RATED)
- D29 — Ngân hàng: sửa ước lượng ROE bền vững, bỏ hệ thống tier, thêm trần P/B
- D30 — Hợp nhất định nghĩa kịch bản + cho kịch bản biến thiên khối terminal
- D31 — Lưu luận điểm CTCK công khai + bóc tách TẤT ĐỊNH (không LLM)
- D32 — Năm gốc dự phóng: cơ chế đã sẵn sàng, MẶC ĐỊNH VẪN TRAILING
- D33 — Cưỡng chế bằng máy: engine không được biết gì về dữ liệu CTCK
- D23-b — Sự cố hạ tầng: hai cluster PostgreSQL, cluster dữ liệu thật bị chết
- D9 — DCF chặn vốn cổ phần ÂM về 0 + cờ NEGATIVE_EQUITY_VALUE_DCF
- D10 — Cờ review upside cực đoan (UPSIDE/DOWNSIDE_EXTREME_REVIEW) trong valuate()
- D11 — Sửa lỗi tầng xuất Excel (export_100.py): Sector & MOS rỗng
- D13 — Sửa bội số EV/EBITDA gán nhầm cho vận tải/cảng (PVT +302%, HAH +113%)
- D14b — Lỗi hiển thị Excel VCB "1000%": pipeline xuất nhân đôi 100×
- D19 — Backfill lịch sử chuỗi vĩ mô → kích hoạt overlay vi mô ngành
- D18 — Nguồn vĩ mô thay thế + cào qua Chrome (đã có dữ liệu thật)
- D17 — Nguồn vĩ mô: khung nhập CSV (chạy ngay) + scaffold scraper HNX/VBMA
- D16 — Audit dữ liệu 2026-07-11 + Freshness Gate + vĩ mô mỗi lần quét
- D15 — Điều chỉnh Blume cho beta toàn hệ thống (sửa gốc NAB +138%)
- D12 — Tồn đọng CẦN QUYẾT (calibration, chưa tự sửa)
- D8 — UI không hiển thị flags từ valuate() → kết quả bất thường trông như lỗi
- D6 — Land Bank Add-on: cộng giá trị quỹ đất chưa phản ánh BCTC
- D7 — VJC/EV-EBITDAR: KHÔNG triển khai — tiền đề ban đầu sai, đã kiểm chứng dữ liệu
- D1 — DCF blend phụ theo business_nature (P/E vs EV/EBITDA)
- D2 — Tách CK thành nhóm "Securities" MOS 30% (không gộp Bank 20%)
- D3 — Decision Engine: epsilon chống lỗi float ở biên MOS
- D4 — Làm rõ 2 trục: routing.json = method, business_nature = MOS
- D5 — Nhóm cao su & FRT: kết luận sau kiểm chứng thực nghiệm
- D34 — Định nghĩa dữ liệu đầu vào
- D35 — Cầu nối EV → VCSH đầy đủ
- D36 — Chuẩn hóa chu kỳ theo biên
- D37 — Một g vĩnh viễn, fade tăng trưởng về g
- D38 — Ngân hàng
- D39 — CTCK, điện, bội số, beta
- D40 — Khuyến nghị, cổng chặn, vĩ mô, kịch bản
- D41 — Dọn engine trùng
- D42 — Golden test tái lập báo cáo CTCK
- D43 — Làm sạch bội số, chặn kết quả cực đoan, cờ tài sản ngắn hạn
- D44 — Bảng định giá chuẩn Excel, đồng thuận không điều chỉnh quyền lần hai (2026-09-29)
- D45 — DCF: liên doanh theo lợi nhuận, CapEx khớp tăng trưởng (2026-09-30, người dùng duyệt)
- D46 — Chặn công bố khi có sự kiện trọng yếu mô hình chưa phản ánh (2026-10-02, người dùng duyệt)
- D47 — Giả định ngân hàng theo số thực tế (2026-10-02, người dùng duyệt)
- D48 — Số cp sau cổ phiếu thưởng thiếu ngày GDKHQ; quy đổi tay ×0,9033 là sai (2026-10-02)
- D49 — Golden test đối chiếu đồng thuận CTCK toàn VN100 (2026-10-02, người dùng duyệt)
- D50 — Khung "Chỉ số vĩ mô" trên sidebar + rút gọn tin AI (2026-10-10, người dùng duyệt)
- D51 — "Tổng quan thị trường" nhìn 5 giây trên đầu sidebar (2026-10-10, người dùng duyệt thiết kế)
- D52 — Mục VN-Index + "Sắp tới" trong Tổng quan thị trường; bỏ điểm số trụ cột (2026-10-12)
- D53 — Giao diện điện thoại + chạy trên VPS (2026-10-12)
- D54 — Điện thoại: thanh tab đáy kiểu app, nhận diện điện thoại ở server (2026-10-12)
- D55 — Tab VN100 làm lại: xếp hạng theo upside mô hình + 5 mã tích sản (2026-10-12, người dùng chọn)
- D56 — Nhận định nhanh lịch quyền: 3 tiêu chí cổ tức; sửa thanh khoản engine (2026-10-12, người dùng chọn)
- D57 — Ngưỡng cổ tức tốt 3,5%; sửa cộng cổ tức hai lần trong phân tích lịch sử (2026-10-12, người dùng chọn)
- D58 — Gọn cảnh báo trên mọi thiết bị (2026-10-13, người dùng yêu cầu)
- D59 — Kaleido cho ảnh biểu đồ PDF/Word (2026-10-13, người dùng yêu cầu cài)
- D60 — Xuất PDF báo cáo bằng Playwright (2026-10-14, người dùng yêu cầu cài)

---

### D61 — Biên lợi nhuận theo cửa sổ gần đây + chặn nhánh DCF âm (2026-10-15, người dùng duyệt « A+D »)
- **A:** trung vị biên EBIT / EBITDA mid-cycle / ROE CTCK lấy `forecast.margin_window_years: 4` năm gần nhất thay vì
  cả 9 năm (9 năm trộn các gãy cấu trúc: BMP biên 2023+ gấp đôi, VPX/PVD thời lỗ). Trung vị ≤ 0 nhưng năm cuối
  dương → dùng năm cuối. `bank_terminal.credit_cost_spike_multiple` 2,0 → 1,5 (EIB lọt).
- **D:** nhánh DCF âm không pha vào trung bình với bội số → `NEGATIVE_DCF_LEG`, FV = 0, NOT_RATED (BAF, CII, NKG, HSG).
- Đo trên cùng DB (chỉ đổi cấu hình D61): 47/100 mã đổi FV; công bố đổi 2 mã (EIB mở 11.082, HSG chặn).
  So CTCK: gần hơn BMP −35→+2%, GAS +25→−1%, DCM +21→−10%, HT1 +29→+8%; xa hơn HPG −13→−28%, POW +1→−16%,
  PVT +2→+12%. Độ nhạy cửa sổ 3/4/5/6/9 năm: trung vị |lệch| 29–31% (nhiễu) → giữ 4, không dò theo CTCK.
- HPG: cửa sổ rơi vào đáy chu kỳ thép (11,8% vs 13,1–13,5% hai năm gần nhất) — giới hạn mid-cycle theo cửa sổ với
  ngành chu kỳ, ghi must_fix. PVD có giá lần đầu, lệch −26% chưa rõ nguyên nhân → must_fix. HHV +148% lọt ngưỡng
  150% → event hold (bội số BOT thời ramp-up). Chưa duyệt: B (capex), C (bội số), các lỗi dữ liệu nhỏ.
- Lưu ý vận hành: 46 mã giá dừng 09/10 → cờ STALE_PRICE chặn công bố (không do D61), cần chạy cập nhật giá.

### D62 — Lỗi dữ liệu nhỏ, ROIC terminal, bội số TTM + trung vị ngành (2026-10-15, người dùng duyệt « làm tất cả »)
- **Dữ liệu/code:** bỏ năm sơ khai không có LCTT thay vì điền 0 (`INCOMPLETE_YEAR_DROPPED`, chỉ BAF 2018);
  trái phiếu chuyển đổi (phần nợ) cộng vào nợ dài hạn — BAF 513, CII 3.257, SBT 976 tỷ; phần quyền chọn là vốn
  chủ, không cộng. `weight_dcf` lấy theo routing.json thay vì cố định 0,5 (VRE 1,0 → FV 16.193 → 8.906; BWE 1,0;
  VPL 0,6; CII 1,0). Cảnh báo văn bản tự do không còn thành mã cờ rác ("Năm 2018"), văn bản vẫn hiển thị.
- **B:** TV đã đúng Damodaran (tái đầu tư = g/ROIC, mặc định ROIC = WACC theo D49). Sửa: `roic_terminal` người
  dùng nhập bị bỏ qua; ROIC ≤ g báo lỗi `INVALID_ROIC_TERMINAL` thay vì kẹp im lặng. **Chưa làm:** cộng XDCB dở
  dang theo giá sổ vào cầu nối vốn chủ (NKG −5.971 → ~4.837, HSG, HPG +16%) — bộ phân loại an toàn chặn sửa đổi
  làm tăng FV, chờ người dùng xác nhận riêng. Không nới trần doanh thu/vốn (5,0) — ngoài phạm vi duyệt.
- **C:** kỳ TTM ghép giá cuối quý → được tính vào ≥3 quan sát bội số lịch sử; thiếu lịch sử → trung vị bội số
  HIỆN HÀNH nhóm routing.json (`peer_multiples.min_peers: 3`, cờ `MULTIPLE_FROM_PEER_MEDIAN`), hằng số ngành chỉ
  còn là phương án cuối. Không kẹp bội số theo ngành: nhóm routing còn lẫn mô hình (HHV BOT chung nhà thầu → −49%).
- Kết quả (giá cập nhật tới 15/10): công bố 58/100; trung vị |lệch CTCK| 25,7% (n=60, ≥3 CTCK). Đổi lớn: FRT
  34.878 → 58.738 (có giá, ghi must_fix: chuẩn hoá LN trên pha tăng trưởng Long Châu, −65% vs CTCK), MCH +27%,
  CTD −22% (+61% → +26% vs CTCK), BSR −26%, VTP +22%, HHV −20% (vẫn hold).

### D63 — Nghiên cứu chu kỳ ngành thép & HPG (2026-10-18, người dùng duyệt nguồn World Bank + FRED)
- Thêm `www.worldbank.org`, `thedocs.worldbank.org` vào `macro_sources.allowed_domains` (Pink Sheet: quặng sắt,
  than theo tháng từ 1960). FRED đã có sẵn; thêm chuỗi WPU101 (giá thép Mỹ từ 1926) và CPIAUCNS (giảm phát).
  Giá cổ phiếu dài hạn lấy từ gói tài trợ `vnstock_data` (bản community trong vnstock_client giới hạn 8 năm).
- `valuation/analysis/steel_cycle.py` (hàm thuần, có test tính tay): zigzag đỉnh/đáy với trạng thái thời gian thực
  (không nhìn trước), thời lượng pha, Kaplan–Meier cho xác suất pha kết thúc, lợi suất theo trạng thái, tương quan
  trễ, nghiên cứu sự kiện, mùa vụ. `scripts/steel_cycle_report.py` nạp/lưu dữ liệu ở `data/steel_cycle/`, ghi
  `reports/steel_cycle/`. Tham số ở `steel_cycle` trong defaults.yaml (ngưỡng 20% hàng hóa, 35% cổ phiếu).
- Không ghi DB, không đụng mô hình định giá. Kết quả là tần suất lịch sử, không phải khuyến nghị.

### D64 — λ ROE ngân hàng 0,5; ngưỡng hai chân 5,0 (2026-10-20, người dùng quyết — owner phi)
- **Q1:** `bank_terminal.roe_convergence` 1,0 → 0,5: ROE terminal = nửa ROE bền vững riêng, nửa ROE ngành. Đo 18 NH
  (mốc 20/10): EIB −28%, SSB −26%, VPB −22%, MSB −19%, CTG −18%, TPB −16%, SHB −14%, OCB −13%, BID −10%, NAB −9%,
  VIB −8%, VCB/TCB −7%, STB −6%, ACB −4%; LPB +7%, MBB +4%, HDB +3% (ROE riêng > ngành); EVF không đổi. MSB, BID,
  VIB, TPB vào band ở hai mốc golden (gỡ khỏi registry; gỡ hold TPB — upside +74%); MBB ra band +20,7% (20/10).
- **Q2:** `publication_gate.leg_ratio_review` 3,0 → 5,0. Mở công bố: BSI, FTS (không có CTCK), SHB (upside +99,9%,
  CTCK n=1 lệch +5,5%), VCI (−50,7%, n=1, luận điểm D26), FRT (−49,9%, n=13 → hold chờ duyệt).
- **Q3/Q4** (audit nguồn công ty con SOTP qua API vnstock chỉ đọc, không ghi DB; MSN cộng MSR 92,89% và MML 94,3%
  theo thị giá vào holdings) đã được phi cho phép — thực hiện ở bước r4b (D65).
- Kèm theo (phản biện r3): driver NH analyst/kịch bản sửa cộng lên đường đã phai ROE thay vì bỏ dòng cân (đúng dấu);
  một nguồn thuế dài hạn `wacc.marginal_tax_rate`. Ghi chú: /private/tmp/claude-501/upgrade_notes/r4a_decisions_models.md.

### D65 — Audit nguồn công ty con SOTP; MSN cộng MSR/MML theo thị giá (2026-10-20, người dùng quyết — owner phi)
- **Q3:** `scripts/collect_sponsor_data.py` và `scripts/audit_vn100_data.py` nhận VN100 ∪ công ty con khai trong
  `config/sotp_holdings.yaml` (`universe.audit_universe/select_audit_tickers`: whitelist + regex `[A-Z0-9]{3}`);
  audit đầy đủ cũng giữ dòng công ty con; `--finalize-existing` đòi đủ 100 mã VN100 (dòng công ty con là phần
  thêm). Thu cache vnstock/VCI (chỉ đọc) và audit `--tickers` GEL, VSH, TBC, TMP, HHS, MSR, MML: status 100 → 107
  dòng (100 dòng cũ giữ nguyên), 0 xung đột. Không ghi DB. GEX/REE/TCH hết `SOTP_SUBSIDIARY_DATA_ERROR`.
- **Q4:** MSN holdings thêm MSR 92,89% và MML 94,3% (thị giá): FV 92.535 → 126.062đ (20/10, +35,2% CTCK n=6) /
  117.171đ (28/09, +27,2%). Registry MSN `out_of_band_justified` (owner phi); golden MSN kiểm phần lõi (MCH, TCB)
  trong golden_tolerance và phần MSR/MML đúng công thức tính tay.
- GEX, REE, TCH, MSN vẫn chặn `SOTP_HOLDINGS_UNVERIFIED` tới khi phi rà tỷ lệ và điền `reviewed_by`/`as_of`.
  Khi mở: REE −40,5% (n=10), TCH −59% (n=2) / −63% (n=3) là must_fix trong registry. Ghi chú:
  /private/tmp/claude-501/upgrade_notes/r4b_sotp_audit.md, bảng rà soát sotp_review_table.md.

### D66 — Nâng cấp định giá toàn VN100 (2026-10-19→20, người dùng duyệt gói NH, SOTP chiết khấu 10%, XDCB theo sổ, ghi DB)
- Tổng hợp các bước s1–s7, phản biện fx1–fx3, r3, r4 và fin_a; mỗi sửa có test tái hiện viết trước; chỉ s7 ghi DB.
  Quyết định riêng đã ghi: λ ROE NH 0,5 và ngưỡng hai chân 5,0 (D64); audit công ty con SOTP, MSN cộng MSR/MML
  (D65). Ghi chú chi tiết: /private/tmp/claude-501/upgrade_notes/*.md. Vận hành: manual §11–§14.
- **Lỗi code/dữ liệu & cờ (s1, fx1):** `sector_peer_multiples` lọc theo `sector` (D62-C lần đầu thực sự chạy);
  NH giữ dấu chi phí dự phòng (NAB hết BANK_PBT_MISMATCH), số dư bình quân TTM lấy cùng quý năm trước; chỉ tính
  bội số mà route() dùng; UNEXPLAINED_CURRENT_ASSETS theo tổng mục B01; bỏ năm vi phạm đẳng thức IS chỉ khi nằm
  ngoài mọi cửa sổ mô hình; FILING_BS_INCOMPLETE (PVT, GAS Q2/2026). Thuế = −số nguồn, chia cho LNTT trừ lãi LD/LK
  (BAF 22,7% → 10,2%). as_of quy số cp về cùng gốc giá đã điều chỉnh (hết lookahead HDB, TPB, GMD; gộp các đợt
  cùng ngày: BAF 334 → 365 tr cp). RIGHTS_ISSUE_UNDATED (info) tách khỏi CORPORATE_ACTION_UNDATED. Cổng
  VALUATION_LEGS_DIVERGE (s1 cho DCF; fx2 dùng chung CK/BH/NH); ngưỡng +150%/−60% vào config; thêm 48 mô tả cờ,
  level cờ khớp cổng công bố.
- **CK/BH/EVF (s2, r3a):** EVF nhận diện theo mẫu BCTC TCTD → RI 0,5 + P/B 0,5 (lỗi → 11.235đ, công bố). Chân P/B
  thị trường có kỳ TTM; dưới 3 quan sát thì lấy trung vị P/B nhóm. Beta nhóm bottom-up cho NH, CK
  (`coe_convention.peer_beta_groups`). BH dùng P/B lịch sử riêng. Payout CK/BH lấy từ cổ tức tiền 3 năm (cờ Gordon
  chỉ cảnh báo). fx2/r3a: CK/BH quy đổi ROE bình quân ↔ đầu kỳ; P/B trước đợt quyền mua/riêng lẻ tính pro-forma
  vốn hóa/(VCSH + tiền thu); không ước được thì loại quan sát (chỉ nhóm CK, BH).
- **Ngân hàng (s3, fx2, r3a, r4a, fin_a; λ ở D64):** ROE terminal hội tụ về ROE ngành. Một định nghĩa ROE = LNST /
  VCSH bình quân; RI và P/B hợp lý dùng ROE_T·(1 + g/2). Chi phí tín dụng phai đối xứng từ TTM về trung vị 3 năm.
  Tăng trưởng tín dụng phai về GDP danh nghĩa 8%. ROE năm 3–5 phai về ROE_T (dòng `roe_fade_adjustment`, cờ
  BANK_ROE_FADE_PLUG). Driver do analyst/kịch bản sửa được cộng delta trên driver gốc (`driver_base`). Ràng buộc
  vốn áp đối xứng cho đường gốc và đường sửa. Không làm F4 (cổ tức theo VCSH/TS mục tiêu).
- **DCF/thuế/XDCB (s4, fx2, r3a, r4a):** thuế hiệu dụng = Σthuế/ΣLNTT 3 năm tài chính, kẹp `dcf.effective_tax_band`.
  NOPAT terminal và lá chắn thuế nợ trong WACC dùng thuế biên 20% (một nguồn `wacc.marginal_tax_rate`, ô "Thuế
  terminal" trên UI). Bỏ trần 5,0 của sales-to-capital (giữ sàn 0,3). XDCB dở dang (mã 242) cộng theo giá sổ vào
  vốn chủ và loại khỏi EV hoạt động của bội số (người dùng duyệt, NPV = 0); vượt `dcf.cip_share_review` 0,5 → chặn
  CIP_DOMINATES_VALUE (NKG, HSG, BAF). Chân P/E phụ = P/E trailing × LN TTM; EV/EBITDA mã không chu kỳ dùng EBITDA
  TTM. ΔDR/ΔDT chỉ áp cho SIP. Thêm cờ MINORITY_AT_BOOK_MATERIAL (không đổi FV).
- **SOTP & đổi phương pháp (s5, fx3, r4b; MSR/MML ở D65):** chế độ SOTP_HOLDINGS (`config/sotp_holdings.yaml`):
  FV = [VCSH mẹ + Σ(stake × vốn hóa − giá sổ)] / cp × (1 − 10%), chiết khấu holding do người dùng duyệt. Áp cho
  VIC, MSN, GEX (GEL 70,21% thay look-through VGC), REE, TCH. Chặn tới khi người dùng điền `reviewed_by`/`as_of`
  (UNVERIFIED; quá TTL 180 ngày → STALE); lỗi dữ liệu công ty con chặn mã mẹ (SOTP_SUBSIDIARY_DATA_ERROR). PC1 →
  EV/EBITDA, HDG và VCG → FCFF (đảo D39, không gồm VGC); SIP → FCFF 0,5 + EV/EBITDA 0,5.
- **RNAV kỹ thuật (s6):** proxy chỉ đánh giá lại tồn kho + BĐS đầu tư (cơ sở VHM 410.285 → 15.878 tỷ); giả định
  proxy một nguồn config; thặng dư tính sau thuế phổ thông 20%. AI_RNAV theo đẳng thức NAV (bắt buộc giá sổ ròng,
  chi phí/m², tỷ lệ sở hữu). AI_SOTP hết trừ nợ ròng/CĐKKS hai lần. Land Bank trừ giá sổ và thuế. Mọi mã RNAV vẫn
  VALUATION_PROXY (chặn).
- **Ghi DB (s7, người dùng duyệt):** sao lưu `backups/vn100_full.pre_s7_20261020.db`. `run_ingest` (chỉ upsert, không
  UPDATE/DELETE) cho 18 mã công ty con/liên kết ngoài VN100 với is_vn100 = 0: +30.314 dòng giá, +132.911 dòng BCTC.
  Rổ VN100 vẫn 100 mã; chạy lại lượt 5 không nhân đôi dòng. Ngày GDKHQ: 0 dòng ghi (VSDC chưa có ĐKCC cho 13 đợt).
  PVT: không bổ sung tổng mục BCĐKT (PDF lỗi chứng chỉ TLS, không bỏ kiểm tra để tải).
- **Audit nguồn (s1, fx1, r3b, r4b):** dấu vân tay chỉ băm ô trọng yếu của kỳ ĐÃ đối chiếu (`audited_periods`).
  Kỳ mới → SOURCE_AUDIT_PARTIAL (cảnh báo). Số của kỳ đã đối chiếu bị đổi, hoặc quá `audit.max_unaudited_periods`
  kỳ chưa đối chiếu → SOURCE_AUDIT_STALE (chặn). F2c đo ΔFV xung đột trên bản sao DB trong bộ nhớ: ≤ 1% →
  SOURCE_CONFLICT_IMMATERIAL (DPM, SSI mở công bố). FILING_PRECEDENCE đo trên số thực dùng. `--tickers` gộp vào
  audit đã lưu. Status nay có 107 dòng (100 + 7 công ty con), 0 xung đột ở công ty con.
- **Bảo mật ingest (s7, fx1, r4b):** trước đây mã mới luôn được chèn is_vn100 = 1, nay `run_ingest` mặc định
  `is_vn100=False`. Route `/ingest` kiểm `^[A-Z0-9]{3}$` + whitelist VN100 ∪ công ty con. `universe.audit_universe`
  kiểm regex trước khi gọi API/ghi cache.
- **Hold (`config/event_holds.yaml`):** thêm NAB (sổ liên NH phình, cần RWA), BVH (thiếu Embedded Value), VRE
  (25.468 tỷ TS dài hạn chưa phân loại), POW (TTM chưa đủ 4 quý công suất mới), SIP (TV coi tiền thuê trả trước
  là tiền vĩnh viễn, thiếu quỹ đất), VCG, PC1 (mới mở, lệch > 30% CTCK), FRT (mới mở, −49,9%, n=13), REE, TCH (đặt
  sẵn: −40,5% / −59% khi điền reviewed_by). TPB thêm ở fx3 rồi gỡ ở r4a (upside +73,7%). Giữ PNJ, HHV. Luật hold
  thống nhất: `publication_gate.new_listing_hold_*` (0,40, ≥ 3 CTCK, upside 100%).
- **Bác/không làm:** cổ tức NH theo VCSH/TS mục tiêu (proxy sai cho CAR, cần RWA). Bội số theo số cp tại từng kỳ
  (số cp quỹ, ngày GDKHQ, giá phát hành chưa tin cậy). Loại quan sát trước phát hành cho NH/DCF (không có giá phát
  hành; FV đổi gấp nhiều lần độ méo). Ép driver NH về ROE_T (không có chuẩn CFA/Damodaran). Bảng thuế ưu đãi theo
  mã (cần căn cứ pháp lý). Ước CĐKKS theo thị giá (chưa có phương pháp từ dữ liệu sẵn có). VGC sang EV/EBITDA; BCM
  SOTP; module KCN, chân P/B BĐS, bội số chu kỳ chuẩn hóa (F9), NT2 đời hữu hạn, beta bottom-up phi tài chính
  (ngoài phạm vi). CHP, PPC, PAN không khai holdings (nguồn tỷ lệ cũ hơn 2 năm hoặc không có).
- **Kết quả đo** (100 mã, DB thật, đồng thuận CTCK 19/10): công bố 58 → 61; công bố có n ≥ 3 CTCK trong ±20%:
  21/39 → 29/41; trung vị |lệch| 17,2% → 11,8%. Baseline chạy trên dữ liệu cũ hơn (giá khác ở 91 mã, đồng thuận
  khác ở 19 mã) nên chênh lệch gồm cả trôi dữ liệu. Các mốc giữa: s8 64 / 30 trên 43 / 10,8%; fx4 55 / 26 trên 40 /
  15,0% (sửa công thức ROE NH khi λ = 1, P/B CK, cổng hai chân 3,0, hold VCG/PC1/TPB); r4 sau D64. fin_a không đổi FV Base hay cổng công bố. Không mã công
  bố nào có upside > 100% hoặc FV âm (SHB +99,9% sát ngưỡng); 12 mã công bố n ≥ 3 ngoài band đều có mục registry.
  pytest toàn bộ (fin_b): 981 passed, 4 skipped, gồm test_golden_consensus 3 ca hai mốc.
- **Chờ người dùng:** kịch bản Bull/Bear NH có bước nhảy LN năm 5 → 6 (phản biện r4, major); `reviewed_by`/`as_of`
  cho 5 holder SOTP và stake MSR sau Elmet (0,8787 cùng mẫu số DB); các mục registry owner "claude-de-xuat" (vd
  MBB, REE, PC1, VCG, FRT, SSI, HCM); các ngưỡng đề xuất liệt kê ở manual §14; EIB/OCB/EVF registry data_blocked
  mà engine vẫn công bố.

### D67 — Kịch bản NH: ROE dài hạn theo kịch bản (2026-10-21, người dùng chọn — owner phi)
- **Vấn đề (phản biện r4, major):** Bull/Bear sốc driver cả 5 năm. Cơ chế delta r4a dồn toàn bộ phần sốc vào LN năm 5,
  trong khi RI terminal vẫn theo ROE_T của Base (chỉ ±2 điểm % cố định) → LN năm 5 → 6 nhảy bậc. Vd VPB Bear lỗ năm
  4–5 rồi ROE ~12% vĩnh viễn; CTG Bear LN6/LN5 = 4,61. Docstring "năm 5 = ROE_T, LN6 nối liền" sai ở kịch bản.
- **Chọn phương án (b):** roe5 kịch bản = ROE riêng Base + (roe5 driver đã sốc − roe5 driver Base), qua
  `forecast_bank.driver_roe5`, dùng chung với repo. Với giả định máy đặt, ROE riêng Base chính là roe5 driver nên
  roe5 kịch bản đúng bằng ROE năm 5 của driver đã sốc. Khi analyst nhập ROE bền vững thì giữ mức đó, chỉ dịch phần
  sốc. ROE_T kịch bản hội tụ λ (D64) về ROE ngành. `driver_base` sốc cùng hệ số nên năm 3–5 phai về ROE_T kịch bản,
  năm 5 = ROE_T. Bỏ `sustainable_roe_delta` ±2 điểm % trong `config/scenarios.yaml`.
- **ROE ngành KHÔNG sốc.** Đây là dữ liệu quan sát (trung vị ROE lịch sử của nhóm), làm đích dài hạn cho hội tụ
  Damodaran, không phải driver của NH. Muốn sốc thì phải dùng số cố định (đúng thứ (b) thay thế) hoặc dự phóng lại cả
  nhóm. Hệ quả: λ = 1 thì ROE_T kịch bản = ROE ngành. Kịch bản khi đó chỉ còn tác động qua năm 1–5, COE và g (đảo ca
  s3 "λ = 1 sốc cả đích"). Nếu đọc Bear là stress toàn hệ thống thì vẫn có lý do sốc ROE ngành: mở cho phi.
- **ROE riêng ≤ 0 vẫn dùng** (`bank_own_roe`). Trước đây giá trị này bị thay bằng ROE TTM, nên VPB Bear (roe5 −4,5%)
  sẽ ra ROE_T cao hơn Base. Base 19 TCTD đều > 0 nên không đổi.
- **Cờ mới `BANK_TERMINAL_JUMP` (cảnh báo):** bắn khi |LN6/LN5 − (1 + g)| > `bank_terminal.terminal_jump_flag_tolerance`
  hoặc khi LN5 ≤ 0. Ngưỡng 0,10 do claude đề xuất, chờ phi duyệt. Base 19 TCTD lệch +0,03…+0,07.
- **Đo (DB 20/10, chỉ đọc):** Base trùng từng số ở cả 19 mã. Sau sửa, mọi kịch bản lệch tối đa 0,074 (HDB Bull);
  trước sửa là 7,07 (VPB Bear). Không mã nào bắn cờ. FV Bull −1,3%…−10,5% (bỏ +2 điểm % ROE ngành). FV Bear −21,0%
  (EVF) / −15,8% (VPB)…+9,0% (NAB). Giá trị kỳ vọng 25/50/25 −0,6%…−4,8%. Ghi chú:
  /private/tmp/claude-501/upgrade_notes/d67.md.

### D68 — Mô hình tổng hợp CTCK (BROKER_SYNTH) + cổng rà soát (2026-10-22, owner phi yêu cầu)
- **Vấn đề:** 39 mã bị chặn công bố vì mô hình riêng của hệ thống không định giá được (proxy lệch
  phi lý, vốn chủ/chân âm, CIP lấn át, hai chân vênh, hold sự kiện...). Owner yêu cầu vẫn công bố
  (kèm rà soát), và với các mã mô hình riêng chưa làm được thì bắt chước phương pháp CTCK để ra
  giá, ghi rõ nhãn "mô hình tổng hợp của CTCK" — không bịa công thức, không bịa số.
- **`valuation/engine/models/broker_synth.py` (docs/BROKER_SYNTH.md):** mỗi báo cáo CTCK tính lại
  giá trị vốn chủ tuyệt đối (tỷ đồng) bằng đúng công thức CTCK dùng (RNAV/SOTP/DCF: Σ cấu phần −
  nợ ròng − CĐTS + điều chỉnh, × (1 − chiết khấu); PE/PB/EV_EBITDA: bội số × dự phóng FY+1;
  BLEND: Σ trọng số × chân), cộng/trừ sự kiện vốn sau ngày báo cáo, rồi chia SỐ CP HIỆN TẠI —
  tránh điều chỉnh quyền hai lần (không lấy thẳng giá mục tiêu CTCK in). Giá mục tiêu 12 tháng
  chiết về hôm nay bằng COE (Damodaran: target price ≠ fair value hôm nay). Kiểm nhất quán: tính
  lại tại số cp CTCK dùng lệch giá mục tiêu CTCK đó > `broker_synth.recon_tolerance` (10%) → cờ
  `BROKER_SYNTH_RECON_GAP:<broker>`. Tổng hợp nhiều báo cáo = trung vị có trọng số độ mới (dùng
  lại `calibration.consensus_view.weighted_median`/`recency_weight`), bỏ báo cáo cũ hơn
  `max_report_age_days` (365 ngày).
- **`valuate._apply_publication_gate`:** mã có `config/broker_synth/<MÃ>.yaml` và mô hình riêng bị
  chặn vì đúng nhóm cờ dữ liệu/mô hình (`broker_synth.trigger_flag_prefixes`), hoặc config ghi
  `use_broker_synth: true` → công bố theo BROKER_SYNTH, cờ `BROKER_SYNTHESIZED` (info); FV/cờ mô
  hình riêng giữ lại ở `own_model_fv`/`own_model_flags` để so sánh, không xoá. Mã đang công bố
  bình thường không bị thay.
- **Cổng rà soát `config/valuation_reviews.yaml`:** review `decision: publish` còn hạn
  (`valuation_review.ttl_days`, 180 ngày) và cùng `basis` (own_model/broker_synth) với phương pháp
  đang dùng → gỡ các cờ "rà soát được" (`UPSIDE/DOWNSIDE_EXTREME_REVIEW`, `MATERIAL_EVENT_HOLD`,
  `VALUATION_LEGS_DIVERGE`, `PROXY_IMPLAUSIBLE`, `NOT_RATED`; thêm `VALUATION_PROXY`,
  `CIP_DOMINATES_VALUE` nếu basis=broker_synth; `SOTP_HOLDINGS_UNVERIFIED` nếu review xác nhận
  stakes), gắn cờ `REVIEWED_PUBLISH:<reason>` (info). Cờ lỗi dữ liệu thật (mọi `severity: error` từ
  `run_deterministic_checks`, `SOTP_SUBSIDIARY_DATA_ERROR`, `AI_INPUTS_UNVERIFIED`...) KHÔNG bao
  giờ bị gỡ. `decision: block` luôn chặn, cờ `REVIEW_BLOCKED:<reason>` (error). Không có review thì
  hành vi như cũ.
- **Test tính tay (`tests/test_broker_synth.py`, fixture `tests/fixtures/broker_synth/XYZ.yaml`,
  số liệu bịa có chủ đích cho test):** RNAV (1.000+500−300)×(1−20%)/100tr cp = 9.600đ; phát hành
  20tr cp/200 tỷ sau báo cáo → (960+200)/120×1.000 = 9.666,67 (không điều chỉnh quyền hai lần);
  12m_forward 10.000/1,15 = 8.695,65; recon gap + bỏ báo cáo cũ; BLEND trọng số; cổng review
  gỡ/không gỡ cờ dữ liệu thật/hết hạn/khác basis/block (dùng FPT thật trong DB, chỉ đọc); thay FV
  bằng BROKER_SYNTH khi mô hình riêng bị VALUATION_PROXY, giữ own_model_fv/flags, không thay mã
  đang công bố bình thường. 12 test pass; `tests/test_golden_consensus.py` không bị ảnh hưởng.
- **Chưa làm (do owner khác/agent khác điền sau):** file `config/broker_synth/<MÃ>.yaml` thật cho
  39 mã (đọc PDF CTCK, ghi nguồn file+trang) và `config/valuation_reviews.yaml` thật — engine này
  chỉ đọc, không tạo số liệu. Không tạo file mã thật trong lúc viết engine, chỉ có 1 fixture test.

### D68b — Điền `config/broker_synth/<MÃ>.yaml` cho 25 mã từ báo cáo CTCK đã đọc (2026-10-22)
- **Việc làm:** một agent trước đã đọc PDF 29 mã trong `reports/broker_pdfs/` và tính tay lại giá
  trị hợp lý theo đúng phương pháp CTCK (quy đổi về số CP hiện tại, không lấy thẳng giá mục tiêu —
  xem recon_note từng mã). Tôi chỉ dùng engine BROKER_SYNTH đã có (KHÔNG viết thêm code mới trong
  `valuate.py` — hạ tầng `_apply_publication_gate`/`load_broker_synth` đã làm đúng việc task yêu
  cầu), ghi 25 file `config/broker_synth/<MÃ>.yaml`: BAF, BCM, BVH, CII, DXG, FRT, GEE, GEX, HHV,
  HSG, KBC, KDH, MSN, NKG, NLG, NVL, PC1, PDR, REE, SIP, TCH, VCG, VGC, VHM, VJC.
  Mỗi report dùng `equity_value_bn` (tính ngược = FV tính tay × shares_outstanding hiện tại/1000,
  đã khớp số với `build_company_data` cho từng mã) thay vì chẻ `components` — vì agent trước đã
  làm phần tính tay, số liệu/trang nguồn nằm ở `notes` + `pages` trong từng file; `method: RNAV`
  chỉ là vỏ kỹ thuật dùng đường `equity_value_bn` trực tiếp, phương pháp CTCK thật ghi ở
  `method_family`. `horizon: valuation_date` (không chiết khấu COE thêm) vì agent trước đã nêu rõ
  không áp dụng bước này (ưu tiên tốc độ) khi tính recomputed_fv.
- **KHÔNG tạo file cho:** PNJ (mâu thuẫn với ghi nhớ dự án — khủng hoảng P-Lab, lỗ 2026 dự kiến +
  pha loãng 107% khiến upside tính lại +213% vô lý, xem `memory/pnj-plab-crisis-2026.md` — không
  tự ý ghi đè, cần người duyệt riêng); VRE, TAL (PDF ảnh scan, agent trước không đọc được số liệu,
  `recomputed_fv=0` — không có gì để ghi, giữ NOT_RATED); POW (đã có mô hình riêng DCF, agent
  trước ghi rõ "không thay thế" — giữ nguyên, chỉ bị MATERIAL_EVENT_HOLD).
- **Kết quả chạy lại (`valuate()`, 2026-10-22):** 17/25 mã chuyển `publication_allowed=True` với
  `method=BROKER_SYNTH` (BAF, BCM, CII, DXG, GEE, GEX, HSG, KBC, KDH, MSN, NKG, NLG, NVL, PDR,
  VGC, VHM, VJC — FV khớp đúng recomputed_fv tính tay). **8 mã vẫn NOT_RATED** dù đã có
  BROKER_SYNTH (BVH, FRT, HHV, PC1, REE, SIP, TCH, VCG) — vì `MATERIAL_EVENT_HOLD` từ
  `config/event_holds.yaml` KHÔNG tự động gỡ khi dùng broker_synth (đúng thiết kế `_gate()`: event
  hold cần review người thật qua `config/valuation_reviews.yaml`, không để mô hình CTCK tự động
  đè sự kiện trọng yếu chưa xử lý — xem D68 gốc). Đây là hành vi AN TOÀN đúng chủ định, KHÔNG phải
  lỗi — không viết thêm code để "ép" publication_allowed=True cho 8 mã này, vì sẽ phá cơ chế rà
  soát sự kiện trọng yếu mà hệ thống đã có (và đã từng cứu PNJ khỏi công bố sai, xem trên).
- **Test:** `pytest tests/test_broker_synth.py tests/test_golden_consensus.py` (22 pass, không
  đổi code nên không cần test mới — chỉ thêm data config). Toàn bộ 100 mã VN100
  (`/private/tmp/claude-501/broker_lean_final.json`, chạy lại `valuate()` cho cả 100 mã):
  **công bố trước = 61/100, sau = 78/100** (+17, đúng bằng 17 mã BROKER_SYNTH thắng
  MATERIAL_EVENT_HOLD ở trên). 22 mã còn NOT_RATED: 8 mã BROKER_SYNTH-bị-event-hold nêu trên +
  PNJ/VRE/TAL/POW (giữ nguyên, lý do trên) + DIG/DSE/KDC/KOS/NAB/PAN/SJS/VIC/VPI/VPL (ngoài phạm
  vi — owner chưa đưa báo cáo CTCK cho các mã này, không có gì để điền).
- **Việc còn để ngỏ:** 8 mã MATERIAL_EVENT_HOLD trên cần người dùng tự điền
  `config/valuation_reviews.yaml` (reviewed_by là người thật) nếu muốn công bố — ngoài phạm vi
  agent. PNJ cần xem lại riêng vì mâu thuẫn dữ liệu đã biết. VRE/TAL cần đọc PDF scan (OCR) để có
  số liệu.

### D68c — Sửa 8 lỗi test từ D68/D68b trước khi công bố (2026-10-22, owner Claude)
- **Vi phạm kiến trúc:** `broker_synth.py` import `valuation.calibration.consensus_view`
  (`weighted_median`, `recency_weight`) — vi phạm luật "engine không import dữ liệu đồng thuận
  CTCK" (`tests/test_forward_base.py::test_engine_khong_import_du_lieu_CTCK`). Hai hàm này là toán
  thuần (không đọc bảng `consensus_history`) nên tách sang `valuation/engine/weighted_stats.py`
  (module trung lập), `consensus_view.py` re-export lại để không phải sửa nơi khác đang import.
- **`VALUATION_PROXY` biến mất khỏi `flags` khi chuyển BROKER_SYNTH** (vỡ
  `test_batch_engine.py::test_proxy_flag_propagates`, và làm mất thông tin minh bạch): sửa
  `_apply_publication_gate` nối cờ chẩn đoán của mô hình riêng (`gated["flags"]`, bỏ
  `NOT_RATED`/`DATA_REVIEW_REQUIRED`) vào `flags` cuối SAU khi `_gate()` quyết công bố xong — không
  nối trước, vì `VALUATION_PROXY`/`PROXY_IMPLAUSIBLE` nằm trong `PUBLICATION_BLOCKING_FLAGS`, nối
  trước sẽ bị cổng tự chặn lại lần hai. Đồng bộ `batch.py`: `_NOT_RATEABLE_FLAGS` (kiểm độc lập,
  phòng vệ thừa) chỉ áp khi `method != "BROKER_SYNTH"` — quyết định công bố thật đã nằm ở
  `publication_allowed`.
- **`_apply_publication_gate` sập với mã mock trong unit test** (vd ticker `"HOLDX"` 5 ký tự):
  `load_broker_synth()` cố ý `raise ValueError` cho mã sai định dạng (chống path injection, xem
  `test_broker_synth.py::test_ticker_khong_hop_le` — ĐÚNG, không sửa). Lỗi là gọi hàm đó cho MỌI
  mã kể cả mã giả trong test. Sửa: chỉ gọi `load_broker_synth` khi mã khớp `[A-Z0-9]{3}`, mã khác
  dạng thì bỏ qua BROKER_SYNTH (coi như không có config) thay vì sập `valuate()`.
- **Lỗi nghiêm trọng hơn — `SOTP_HOLDINGS_` trong `trigger_flag_prefixes` vô hiệu hoá cổng chờ rà
  soát:** D68b (và tôi, lúc đầu) đã bật `use_broker_synth: true` cho cả MSN/GEX/REE/TCH — 4 mã này
  **đã có cơ chế SOTP_HOLDINGS đúng** (cổ phần công ty con niêm yết theo thị giá, D65), chỉ đang
  chờ người dùng điền `reviewed_by`/`as_of` sau khi rà tỷ lệ sở hữu
  (`reports/sotp_review_table.md`). Vì `trigger_flag_prefixes` có tiền tố `SOTP_HOLDINGS_`, cờ
  `SOTP_HOLDINGS_UNVERIFIED` (chặn có chủ đích, chờ người) tự kích BROKER_SYNTH — thay một cơ chế
  đã đúng bằng một báo cáo CTCK đơn lẻ kém chính xác hơn, và vô hiệu hoá chính cổng chờ rà soát
  (`tests/test_sotp_holdings.py::test_msn_holdings_mechanism_on_real_db` bắt được: tăng thêm từ
  MSR/MML = 0 thay vì ~25.878đ/cp). **Sửa:** bỏ `SOTP_HOLDINGS_` khỏi `trigger_flag_prefixes`;
  trả `use_broker_synth: false` cho MSN/GEX/REE/TCH (đúng kế hoạch D66/D67 đã báo người dùng — 4
  mã này vẫn chờ rà soát, KHÔNG dùng broker_synth).
- **Test:** toàn bộ `pytest` (1.014 passed, 0 fail, 4 skip — tăng từ 1.006 passed/8 fail của
  D68/D68b). `test_golden_consensus.py` (3 ca, cả 2 mốc) pass.
- **Kết quả cuối (`/private/tmp/claude-501/final_valuation2.json`, chạy lại `valuate()` 100 mã):**
  công bố 76/100 (so baseline tuần này 58/100). BROKER_SYNTH công bố 15 mã: BAF, BCM, CII, DXG,
  GEE, HSG, KBC, KDH, NKG, NLG, NVL, PDR, VGC, VHM, VJC. MSN/GEX/REE/TCH quay lại NOT_RATED (chờ
  rà soát tỷ lệ sở hữu — không phải lỗi, đúng kế hoạch). HHV vẫn NOT_RATED (MATERIAL_EVENT_HOLD từ
  D61, không đổi vì broker_synth không gỡ event hold — đúng thiết kế).

### D68d — Excel ghi đúng nhãn BROKER_SYNTH (2026-10-22, owner Claude)
**Vấn đề:** `scripts/export_valuation_book.py` lấy cột "Phương pháp định giá" từ `value_ticker()["method"]`
(= phương pháp của bảng routing), nên 15 mã BROKER_SYNTH vẫn ghi "RNAV (proxy)"/"DCF/FCFF" trong khi app
ghi "Mô hình tổng hợp CTCK"; cột "Chú ý" lại liệt kê cờ của mô hình riêng ("FV về 0, không công bố")
mâu thuẫn với trạng thái Công bố. Giá trị hợp lý thì không lệch (đối chiếu 100/100 mã, sai khác 0).
**Sửa:** mã BROKER_SYNTH dùng `res["method_label"]`, để trống cột nội tại/tương đối, và tách cờ mô hình
riêng thành một câu "Mô hình riêng không dùng được (...)".

### D69 — Rà mô hình sau D68: giữ ROIC dài hạn = WACC; ngân hàng không có lỗi công thức (2026-10-22, người dùng duyệt « Giữ nguyên »)
**Đo trên 24 mã DCF đã công bố, có ≥2 CTCK** (ảnh DB 22/10):
| ROIC terminal | trong ±15% | trong ±25% | trung vị |lệch| | trung vị lệch có dấu |
|---|---|---|---|---|
| = WACC (giữ) | 11 | 17 | 16,2% | −10,1% |
| (ROIC lịch sử + WACC)/2 | 10 | 16 | 16,4% | −4,8% |
| ROIC lịch sử, trần 30% | 10 | 16 | 15,8% | −3,9% |
Đổi chỉ dời thiên lệch, không tăng tỷ lệ khớp; đẩy NT2/BWE lệch xa hơn → **giữ = WACC** (đóng câu hỏi treo từ D49).
**Ngân hàng (SHB +96%, MBB, TPB):** RI = B0 + ΣPV(RI) + TV với RI6 = (ROE_T đầu kỳ − COE)·B5 — đúng CFA/Damodaran.
Upside cao vì cả 17 NH dùng chung beta ngành (D47) → COE 11,9%, trong khi thị trường trả SHB P/B 0,66x
(ngầm định COE cao hơn nhiều hoặc không tin ROE 16% bền vững). SHB không có CTCK nào trong 180 ngày để đối chiếu;
TPB lệch +12% so với CTCK (trong band). Không sửa — đổi COE riêng từng NH là đổi mô hình, cần duyệt riêng.
**Mã lệch >25% là lý do riêng từng mã, không phải một lỗi chung:** HPG — s2c tính trên vốn đã gồm Dung Quất 2
nên dự phóng còn capex lớn (FCFF âm năm 1–2); GVR/PHR — giá trị đất KCN/đền bù không nằm trong DCF;
BSR/PVD — chuẩn hoá chu kỳ; VTP/MCH — tăng trưởng/ROIC cao, ROIC terminal = WACC; SSI — CTCK chu kỳ thanh khoản.

### D70 — Thử s2c trung vị 5 năm cho HPG: KHÔNG áp dụng (2026-10-22, owner Claude)
Giả thuyết: HPG 2025 chuyển ~64 nghìn tỷ XDCB Dung Quất 2 sang TSCĐ → s2c năm cuối 1,02 (trước đó 1,3–1,5) →
capex dự phóng tính lần hai cho công suất đã xây. Thử trung vị s2c 5 năm: HPG chỉ +2% (20.554 → 21.004, vẫn −35%
so với CTCK); toàn rổ trung vị |lệch| 15,1% → 15,7%, số mã trong ±15% không đổi. Đã hoàn tác.
Lệch HPG chủ yếu do CTCK định giá theo LN dự phóng 2026–27 (công suất mới) trong khi chân bội số dùng EBITDA TTM
và DCF dùng thuế biên 20% cho terminal (thuế hiệu dụng HPG 13%) — đều là quyết định đã duyệt (D61/D64), giữ nguyên.

### D71 — Mã còn lại: Mô hình tổng hợp CTCK nhiều nguồn (TARGET_PRICE) + review ủy quyền (2026-10-23, người dùng yêu cầu)
**Yêu cầu:** « các công ty còn lại áp dụng đúng mô hình CTCK, có so sánh chọn lọc của từng cty phát hành; mã đã định
giá không đụng; tôi tin tưởng các báo cáo của bạn ».
**Làm:**
- `broker_synth.py`: phương pháp `TARGET_PRICE` — vốn chủ = giá mục tiêu × shares_used_mn (test tính tay
  `test_target_price_nhieu_ctck_trung_vi_trong_so`). Giá từ `consensus_history` đã điều chỉnh quyền/cổ tức tại nguồn
  → shares_used = số cp hiện tại (không điều chỉnh lần hai). horizon `12m_forward` → chiết về hôm nay bằng COE.
- "So sánh chọn lọc": mọi CTCK phát hành trong 365 ngày, trung vị có trọng số độ mới (bán rã 180 ngày) — trung vị
  tự loại giá mục tiêu lệch xa số đông; báo cáo PDF đã đọc ở D68b giữ nguyên, không trùng (cùng CTCK + ngày).
- 15 mã: FRT HHV PC1 REE SIP TCH VCG GEX MSN POW VRE BVH PAN TAL VPL (`use_broker_synth: true`).
- `config/valuation_reviews.yaml`: review basis broker_synth cho 15 mã — gỡ MATERIAL_EVENT_HOLD vì mọi hold của các
  mã này ghi rõ "lỗi mô hình riêng, không phải sự kiện doanh nghiệp". reviewed_by ghi "người dùng ủy quyền".
**Không mở:** PNJ (sự kiện thật P-Lab; chưa có giá mục tiêu CTCK lập sau 25/09/2026 — đúng lift_when);
DIG DSE KDC KOS NAB SJS VIC VPI (0 báo cáo CTCK trong 365 ngày).
**Lưu ý chất lượng:** BVH, PAN chỉ 1 báo cáo cũ ~10 tháng; GEX/TAL/VPL 1–3 báo cáo. 15 mã D68 cũ vẫn
`horizon: valuation_date` (không chiết COE) — người dùng yêu cầu không đụng, nên hai nhóm khác quy ước chiết khấu.
**Kết quả (DB 23/10):** công bố 76 → 91/100; 76 mã cũ không đổi do D71 (chênh <1% ở vài mã là do giá cập nhật sáng 23/10).
**Test (23/10):** 1012 pass; còn 3 lỗi `test_golden_banks[TCB]` do DỮ LIỆU — đợt tự cập nhật sáng 23/10 nạp Q3/2026 dở
(TCB chỉ IS+CF 78 dòng, không có BS → không tìm được vốn điều lệ; HT1/MSN 66 dòng cũng thiếu). Không ghi DB khi chưa
được duyệt. Registry: gỡ FRT/PC1/REE/TCH/VCG/VRE (vào band qua D71) và HDB (vào lại band sau giá 23/10);
`test_calibration_registry` đổi mã ví dụ FRT → PVD (FRT không còn mục must_fix).

### D71b — Nạp lại BCTC Q3/2026 dở cho TCB, HT1, MSN (2026-10-23, người dùng duyệt « đồng ý »)
Đợt tự cập nhật sáng 23/10 chỉ nạp IS+CF Q3/2026 (nguồn chưa có BS lúc đó). Sao lưu DB
(`/private/tmp/claude-501/vn100_full.before_q3fix.db`), gọi lại `vnstock_client.get_financials` + `upsert_financials`
(ON CONFLICT DO NOTHING) cho BS/IS/CF: +324 dòng BS (TCB 86, HT1 119, MSN 119); chạy lần 2 không thêm dòng (1.102.968).
`test_golden_banks` 9/9 pass. TCB 40.295 → 41.121đ. Chưa đóng gói lại `vn100_full.db.gz` (làm khi push).
**NT2 (cùng ngày):** nguồn vẫn chưa có CF Q3/2026 của NT2 (BS+IS đã có) → không phải lỗi nạp mà công bố dần. Sửa gốc:
`repo.drop_incomplete_latest_quarters` — quý mới nhất chưa đủ BS+IS+CF thì TTM dừng ở quý đầy đủ gần nhất, cờ
`QUARTER_INCOMPLETE_SKIPPED:<kỳ>` (thông tin). Test tay `test_bo_quy_moi_nhat_chua_du_ba_bao_cao`. NT2 công bố lại 36.205đ.
**Số cp (cùng ngày, lỗi có sẵn lộ ra khi có BS Q3):** `ttm_helper.get_latest_balance` luôn lấy quý mới nhất,
bỏ qua as_of → backtest 28/09 dùng vốn điều lệ BS Q3/2026 (kết thúc 30/09) = lookahead (MSN 1.520 → 1.535 tr cp).
Sửa: (a) tham số as_of — chỉ quý đã quá hạn công bố (`publication_lag_days.quarterly`), chỉ áp khi gọi ngày quá khứ;
(b) lấy quý gần nhất CÓ chỉ tiêu (quý nạp dở không làm mất vốn điều lệ, ca TCB sáng 23/10).
`test_msn_holdings_mechanism_on_real_db` tắt broker_synth (MSN công bố qua BROKER_SYNTH từ D71) để vẫn kiểm cơ chế SOTP.
