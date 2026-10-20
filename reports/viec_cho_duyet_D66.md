# Việc chờ phi quyết sau đợt nâng cấp D66 (20/10/2026)

Chưa commit gì. DB chỉ được ghi ở s7 (18 mã công ty con, có sao lưu `backups/vn100_full.pre_s7_20261020.db`).

## 1. Mô hình
- **[major, phản biện r4] Kịch bản Bull/Bear NH có bước nhảy LN năm 5 → 6** (VPB Bear: lỗ năm 4–5 rồi ROE ~13% vĩnh
  viễn; CTG Bear LN6/LN5 +361%). Base không bị. Chọn: (a) gán `driver_base` = driver đã sốc trong
  `apply_scenario_adjustments`, hoặc (b) tính lại ROE bền vững của kịch bản từ driver đã sốc. Kèm cờ
  BANK_TERMINAL_JUMP và ngưỡng. Ảnh hưởng tab tích sản, báo cáo DOCX/HTML.
- SHB công bố với upside +99,9% (sát ngưỡng 100%), n=1; cổ tức CP 10% chưa có ngày GDKHQ.
- Cờ Gordon payout CK/BH (bắn 7/12 CK + BVH): giữ, hay chỉ cảnh báo khi ROE_T ≤ g như NH (D29).
- P/B CK: chọn P/B riêng post-money (VIX −15%) hay trung vị nhóm; TERP chính xác hay pro-forma xấp xỉ (SSI, HCM).
- RNAV: premium mặc định 0 (chỉ dùng khi analyst nhập có nguồn)? `rnav_discount` 0,40 áp cả chế độ AI?
- Thuế terminal 20% cho mọi mã: có cần bảng ưu đãi dài hạn theo mã (vd phần mềm 10%) có căn cứ pháp lý không.
- EVF: forecast_bank thiết kế cho NH, chưa rà sâu (huy động chủ yếu giấy tờ có giá/liên NH).

## 2. SOTP (`config/sotp_holdings.yaml`, bảng rà soát `sotp_review_table.md`)
- Điền `reviewed_by` + `as_of` cho VIC, MSN, GEX, REE, TCH sau khi rà. Điểm cần chốt: stake MSR 0,9289 hay 0,8787
  (sau Elmet, cùng mẫu số DB; 0,8284 nếu bán thêm 5,01%); MCH 66% vs pháp lý ~65,3–69,4%; MML chưa có tỷ lệ pháp
  lý; EIB 10% (GEX) thiếu `source_date`, chưa cập nhật sau tăng vốn; GEL chưa cộng 1,85% Phát điện Gelex; VHM 71,58%
  vs 71,07% (theinvestor).
- REE (−40,5%, n=10), TCH (−59%): duyệt mục registry rồi mới xoá hold đặt sẵn.
- MSN registry `out_of_band_justified` chỉ hơn band 0,2 điểm % → có thể thành OBSOLETE khi giá đổi.

## 3. Hold (`config/event_holds.yaml`) chờ duyệt gỡ
VCG (+41,5% CTCK), PC1 (+33,0%; dưới ngưỡng mới 40% nhưng gỡ cần phi), FRT (−49,9%, n=13), SIP (cần dữ liệu quỹ
đất), POW (chờ TTM đủ 4 quý), NAB (cần RWA/CAR), BVH (cần Embedded Value), VRE (TS dài hạn chưa phân loại).

## 4. Registry (owner "claude-de-xuat (cho phi duyet)")
- MBB +20,7% (λ 0,5 giữ nửa ROE riêng 19,6%), SSI/HCM (cơ chế P/B mới), REE, PC1, VCG, FRT và các mục cũ khác.
- EIB, OCB, EVF: registry `data_blocked` nhưng engine vẫn công bố → chặn theo registry hay giữ?

## 5. Ngưỡng do claude đề xuất (config, chưa duyệt)
`bank_terminal.fade_plug_flag_share` 0,10 (12/18 NH bị gắn), `audit.max_unaudited_periods` 2,
`audit.filing_precedence_max_rel_diff` 0,05 + `filing_source_domains`, `dcf.minority_book_review` 0,10,
`relative_multiples.capital_raise_min_ratio` 0,05 / `capital_raise_proceeds_tol` 0,10 /
`capital_raise_exclusion_groups` [CK, BH], `publication_gate.new_listing_hold_*` (0,40 / 3 CTCK / 100%).

## 6. Dữ liệu & vận hành
- PVT: tổng mục BCĐKT Q2/2026 chưa bổ sung (PDF pvtrans.com lỗi chứng chỉ TLS) — phi tự tải nếu cần.
- 13 đợt cổ tức CP/thưởng/quyền mua chưa có ĐKCC trên VSDC (TCB, BID, VCB, SHB, BCM, PC1, SJS, VSC, CMG, SBT, NKG,
  VND, PDR): khi có ngày GDKHQ, thêm `config/corporate_actions.yaml`. `issue_price_vnd` NULL cho mọi quyền mua.
- Sau mùa BCTC Q3: chạy collect + audit (manual §11); hiện KBC `SOURCE_AUDIT_PARTIAL:2026Q3`.
- `vn100_full.db` (10:02:47) và `vn100_full.db.gz` (10:03:21) ngày 20/10 bị tiến trình NGOÀI ghi sau r4c (không
  phải fin_a/fin_b; nghi lịch TPCP 10 năm thứ Ba 10:00 hoặc app/bot đang mở DB). Chưa kiểm nội dung; .gz nay
  khác HEAD — rà trước khi commit.
- Đồng thuận HDB trộn giá mục tiêu đã/chưa điều chỉnh (24hmoney vs Simplize).
- Commit: toàn bộ thay đổi s1–fin_b đang nằm trong working tree, chưa commit.
