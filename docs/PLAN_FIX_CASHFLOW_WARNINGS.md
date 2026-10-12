# Kế hoạch: dứt điểm tường cảnh báo "chưa có đầy đủ lưu chuyển đầu tư/tài chính"

Ngày lập: 02/09/2026. Trạng thái: CHỜ DUYỆT (chưa sửa code).

## 1. Hiện tượng

Màn hình định giá (GEX và nhiều mã khác) hiển thị 8 hộp đỏ giống hệt nhau, mỗi
năm một hộp:

> Năm 2019…2026: chưa có đầy đủ lưu chuyển đầu tư/tài chính để đối chiếu biến
> động tiền; không tự tạo khoản bù.

Cùng nội dung đó cũng nằm trong báo cáo đã xuất:
`temp_reports/Report_Valuation_{GEX,CTD,CTS,PC1}.html`.

## 2. Nguyên nhân gốc (đã kiểm chứng, không suy đoán)

### 2.1 Nguồn phát cảnh báo

`valuation/models/financials.py::Company.validate_model_integrity` (dòng ~168-188):

```python
total_cf = curr_cf.cfo - curr_cf.capex + curr_cf.cf_other
if abs(delta_cash - total_cf) > 1.0 and curr_cf.cf_other == 0.0:
    warnings.append(f"Năm {curr_cf.year}: chưa có đầy đủ lưu chuyển đầu tư/tài chính …")
```

Cảnh báo chỉ bật khi `cf_other == 0.0`.

### 2.2 Vì sao `cf_other` luôn bằng 0

Bản **đã commit (HEAD)** của `valuation/data_access/repo.py` dựng `CashFlow(...)`
mà **không truyền `cf_other`** (git show HEAD: dòng 504-509), nên field này luôn
nhận default `0.0` trong `models/financials.py:71`. Hệ quả: mọi mã, mọi năm mà
biến động tiền không giải thích được chỉ bằng `CFO − CapEx` (tức gần như toàn
bộ, vì thiếu hẳn CFI/CFF) đều bật cảnh báo → tường cảnh báo lặp theo số năm.

Đây **không phải lỗi thiếu dữ liệu**. Đã đếm trên `vn100_full.db`: cả 82 mã
phi-ngân hàng trong VN100 đều có đủ `net_cash_inflows_outflows_from_investing_activities`
và `..._financing_activities` cho mọi năm lịch sử (có dòng Q0 cả năm hoặc đủ 4
quý). Năm 2026 chỉ có Q1–Q2 nên không đủ FY, nhưng năm gần nhất được tính theo
TTM (4 quý gần nhất) và vẫn khớp được.

### 2.3 Bản sửa đã có trong working tree (chưa commit)

`repo.py` hiện tại (mtime 02/09/2026 01:41) đã có
`_cashflow_other_excluding_capex()` và truyền `cf_other` vào `CashFlow`. Chạy lại
đúng pipeline (`periodize_quarters_to_annual` + `_match_value`) trên
`vn100_full.db` cho GEX:

| Năm | CFO | CFI | CFF | CapEx | Tiền cuối kỳ | cf_other | Khớp Δtiền? |
|---|---:|---:|---:|---:|---:|---:|:--|
| 2019 | 1.167,9 | −3.933,9 | 2.763,3 | −1.527,2 | 921,0 | 356,6 | ✔ (−2,7 vs −2,7) |
| 2020 | 373,3 | −2.979,9 | 3.245,5 | −1.917,4 | 1.559,2 | 2.182,4 | ✔ (638,2 vs 638,3) |
| 2021 | −2.513,8 | −5.776,7 | 11.640,1 | −7.977,3 | 4.906,1 | 13.837,9 | ✔ |
| 2022 | 7.917,2 | −3.132,6 | −6.532,8 | −4.086,5 | 3.156,3 | −5.580,6 | ✔ |
| 2023 | 4.425,9 | −6.923,9 | 2.650,0 | −5.327,0 | 3.312,7 | 1.057,6 | ✔ |
| 2024 | 2.509,2 | −966,6 | −786,9 | −3.835,1 | 4.074,2 | 2.087,4 | ✔ |
| 2025 | 546,2 | −5.016,7 | 9.049,0 | −5.837,2 | 8.659,5 | 9.876,4 | ✔ |
| 2026 (TTM) | 760,9 | −16.641,5 | 17.839,0 | −4.316,2 | 5.738,9 | 5.519,5 | ✘ xem 2.4 |

Đơn vị: tỷ đồng. `cf_other ≠ 0` ở mọi năm → **cảnh báo hiện tại không còn điều
kiện để bật**.

Kết luận: màn hình người dùng đang chạy **code cũ** (tiến trình Streamlit khởi
động trước lúc sửa, Python giữ module đã import trong `sys.modules`) và/hoặc đọc
lại artifact đã cache (`temp_reports/*.html`, `.deepseek_report_cache/`,
`st.session_state`). Bước đầu tiên là khởi động lại app và xoá cache, chưa cần
sửa dòng code nào.

### 2.4 Bốn khiếm khuyết còn lại của chính phép kiểm tra

| # | Khiếm khuyết | Hệ quả |
|---|---|---|
| a | Điều kiện bật là `cf_other == 0.0` — dùng "bằng 0" làm dấu hiệu thiếu dữ liệu | Sau khi sửa, **mọi lệch đối chiếu thật đều im lặng**. Kiểm tra trở thành vô dụng thay vì ồn ào. |
| b | Ngưỡng cứng `1.0` tỷ đồng cho mọi doanh nghiệp | Với GEX (tài sản hàng chục nghìn tỷ) 1 tỷ là nhiễu làm tròn; với DN nhỏ lại quá lỏng. Vi phạm luật "no magic number" trong AGENTS.md. |
| c | Năm TTM trộn hai độ dài kỳ: Δtiền lấy giữa hai mốc bảng cân đối cách nhau 2 quý (Q4/2025 → Q2/2026) nhưng dòng tiền cộng 4 quý | GEX 2026: Δtiền −2.920,6 vs dòng tiền +1.964,2, lệch ~4.885 tỷ **do thiết kế**. Bất kỳ kiểm tra chặt nào cũng sẽ báo sai ở năm gần nhất. |
| d | Mỗi năm một dòng, `streamlit_app.py:276-279` render từng dòng bằng `st.error` | 8 hộp đỏ giống hệt nhau cho cùng một nguyên nhân. |

### 2.5 Cảnh báo này đang chặn xếp hạng

Chuỗi văn bản cảnh báo được dùng làm **lý do chặn cứng**:

- `valuation/analysis/investment_ranking.py:MATERIAL_MODEL_WARNING_PHRASES`
- `valuation/views/vn100_ranking.py::_hard_reason`

Và cờ `MISSING_FINANCIAL_INPUT:{năm}:cfi_cff` (bản sửa mới thêm) bị
`valuation/report/verified_summary.py::run_deterministic_checks` xếp severity
`error` → `publication_allowed=False` → NOT_RATED. Nghĩa là **thiếu CFI/CFF của
một năm cũ (vd 2018) đủ để chặn phát hành cả mã**, kể cả khi năm định giá đủ dữ
liệu. Cần phân loại lại theo mức trọng yếu.

### 2.6 Sau khi sửa còn bao nhiêu cảnh báo thật?

Đối chiếu FY toàn bộ 82 mã phi-ngân hàng bằng công thức đã sửa
(`Δtiền ≈ CFO − CapEx + cf_other`):

- 555 ticker-năm đối chiếu được.
- **13 ticker-năm (2,3%) lệch > 1 tỷ**, thuộc 8 mã.
- Lệch lớn nhất: `VCK 2025` (327.660 tỷ — gần như chắc chắn sai đơn vị hoặc sai
  dòng "tiền"), `HSG 2023` (322), `FTS 2021` (110), `VND 2019/2023` (105/98),
  `CTS 2023` (32), `FRT 2020` (17,5), `SSI` (1,5–3,5).

Tức là thay vì ~700 cảnh báo nhiễu, một phép kiểm tra đúng sẽ chỉ nêu ~13 trường
hợp — và đó đều là số liệu đáng đi kiểm tra thật.

## 3. Kế hoạch nâng cấp

### Giai đoạn 0 — Xác nhận, chưa sửa code (15 phút)

- [ ] Tắt hẳn tiến trình Streamlit đang chạy, xoá `temp_reports/*.html` và
      `.deepseek_report_cache/` liên quan GEX, khởi động lại app.
- [ ] Mở GEX, xác nhận tường cảnh báo biến mất. Nếu vẫn còn → dừng, báo lại;
      giả thuyết mục 2.3 sai và phải điều tra tiếp trước khi làm Giai đoạn 2.
- [ ] Chạy thêm CTD, CTS, PC1 (4 mã đã có báo cáo cũ dính lỗi) để xác nhận.

### Giai đoạn 1 — Khoá lại bằng test hồi quy (trước khi sửa tiếp)

- [ ] `tests/test_cashflow_reconciliation.py`:
  - đủ CFI/CFF → `company.warnings` không chứa cụm "lưu chuyển đầu tư/tài chính";
  - thiếu CFI/CFF ở 3 năm → đúng **một** dòng cảnh báo gộp, không phải ba;
  - fixture GEX-like tính tay: `Δtiền = CFO − CapEx + cf_other` khớp trong 0,1 tỷ;
  - test chống hồi quy CapEx trừ hai lần (`cf_other` phải cộng ngược `capex_abs`).
- [ ] Test phải FAIL trên code HEAD và PASS trên working tree hiện tại.

### Giai đoạn 2 — Sửa bản thân phép kiểm tra (`valuation/models/financials.py`)

Tách một cảnh báo mơ hồ thành hai loại rõ ràng:

- [ ] **Loại A — thiếu dữ liệu**: `cf_other` không dựng được (CFI hoặc CFF không
      match taxonomy). Gộp tất cả các năm vào **một** dòng:
      `Thiếu lưu chuyển đầu tư/tài chính: 2019, 2020, 2021 (3 năm) — không tự tạo khoản bù.`
      Nguồn sự thật là cờ `MISSING_FINANCIAL_INPUT:{năm}:cfi_cff` do repo gắn,
      **không** suy ra từ `cf_other == 0.0` nữa.
- [ ] **Loại B — lệch đối chiếu**: dữ liệu đủ nhưng identity không khớp. Dòng
      riêng, nêu số liệu cụ thể:
      `Năm 2025: Δtiền 4.585,3 vs CFO−CapEx+khác 4.585,4 (lệch 0,1 tỷ; 0,00% tài sản).`
      Chỉ hiện khi vượt ngưỡng.
- [ ] **Ngưỡng tương đối, đặt trong `config/defaults.yaml`** (không hardcode):
      `cash_reconciliation_tolerance: {abs_billion_vnd: 1.0, pct_total_assets: 0.5, pct_delta_cash: 2.0}`
      → bật cảnh báo khi lệch vượt **cả** ngưỡng tuyệt đối lẫn ngưỡng tương đối.
- [ ] **Sửa lệch kỳ ở năm TTM (khiếm khuyết 2.4c):** hoặc (i) bỏ qua năm TTM
      trong phép đối chiếu và ghi rõ lý do, hoặc (ii) so Δtiền đúng cửa sổ 4 quý
      (tiền cuối Q2/2026 vs tiền cuối Q2/2025). Ưu tiên (ii) nếu BS quý có đủ;
      nếu không, làm (i). **Không** để nguyên trạng trộn 2 quý với 4 quý.

### Giai đoạn 3 — Hiển thị (`streamlit_app.py`, `valuation/report/template.html`)

- [ ] Gom cảnh báo trùng nội dung trước khi render; hiện tiêu đề đếm số:
      `⚠️ Cảnh báo toàn vẹn mô hình (3)` trong một `st.expander` thu gọn mặc định.
- [ ] Phân biệt màu theo mức: thiếu dữ liệu (vàng) vs lệch trọng yếu (đỏ). Hiện
      tại mọi thứ đều `st.error` đỏ nên người đọc không phân biệt được mức độ.
- [ ] `template.html`: nhóm `flag-chip` trùng nội dung, hiển thị `×N` thay vì lặp.

### Giai đoạn 4 — Phân loại lại severity của cổng phát hành

- [ ] `valuation/report/verified_summary.py::run_deterministic_checks`:
      `MISSING_FINANCIAL_INPUT:{năm}:cfi_cff` chỉ là `error` khi **năm đó thuộc
      cửa sổ dùng để định giá** (năm gần nhất/TTM và năm liền trước). Năm cũ hơn
      → `warning`, không chặn phát hành.
- [ ] Giữ nguyên nguyên tắc: thiếu đầu vào trọng yếu của chính năm định giá vẫn
      chặn. Không nới lỏng để "cho ra số".

### Giai đoạn 5 — Xếp hạng VN100

- [ ] Rà `MATERIAL_MODEL_WARNING_PHRASES` và `_hard_reason`: chỉ chặn khi thiếu
      dữ liệu năm định giá, không chặn vì một năm lịch sử xa.
- [ ] Chạy lại `scripts/update_vn100_ranking.py`, ghi lại **trước/sau**: số mã
      vượt cổng dữ liệu (hiện 66/100 theo `docs/DATA_REMEDIATION_REPORT.md`) và
      số mã bị chặn vì lý do cashflow.
- [ ] Nếu số mã được xếp hạng tăng, kiểm tra tay 3 mã mới vào danh sách trước khi
      tin — không mặc định coi việc bỏ chặn là đúng.

### Giai đoạn 6 — Xử lý 13 ca lệch thật

- [ ] `VCK 2025` (lệch 327.660 tỷ): gần như chắc là sai đơn vị hoặc lấy nhầm
      dòng "tiền". Kiểm tra taxonomy + số nguồn trước khi kết luận.
- [ ] `HSG 2023`, `FTS 2021`, `VND 2019/2023`, `CTS 2023`, `FRT 2020`, `SSI`:
      đối chiếu thuyết minh BCTC. Mã chứng khoán (FTS/VND/CTS/SSI) có cấu trúc
      lưu chuyển tiền khác DN sản xuất — có thể cần taxonomy riêng thay vì coi là
      lỗi dữ liệu.
- [ ] Ca nào chưa kết luận được thì giữ cảnh báo, **không** nới ngưỡng để cho nó
      biến mất.

### Giai đoạn 7 — Dọn dẹp và ghi nhớ

- [ ] Xoá `temp_reports/*.html` cũ chứa cảnh báo sai, xuất lại báo cáo mẫu.
- [ ] Thêm mục vào `DECISIONS.md` (ngày, quyết định, lý do, files).
- [ ] Cập nhật `.agents/AGENT_HANDOFF.md` mục 2.1 với kết luận cuối.
- [ ] Chạy checklist bảo mật + `pytest`/`ruff`/`mypy` trước khi commit.

## 4. Tiêu chí nghiệm thu

1. GEX, CTD, CTS, PC1: không còn cảnh báo lặp theo năm trên UI và trong PDF/Word.
2. Khi thiếu CFI/CFF thật, hệ thống hiện **một** dòng gộp nêu rõ các năm thiếu.
3. Khi dữ liệu đủ nhưng lệch vượt ngưỡng tương đối, hệ thống hiện dòng riêng kèm
   con số — không im lặng như hiện nay.
4. Toàn VN100: số cảnh báo cashflow ≤ 15 ticker-năm (so với ~700 hiện tại), và
   mỗi cảnh báo còn lại truy được về một sai lệch số liệu cụ thể.
5. Không mã nào bị NOT_RATED chỉ vì thiếu CFI/CFF của một năm ngoài cửa sổ định giá.
6. `pytest` xanh, trong đó có test hồi quy CapEx-trừ-hai-lần.

## 5. Không làm trong kế hoạch này

- Không tự cân đối, không tự tạo khoản bù để identity khớp.
- Không nới ngưỡng chỉ để cảnh báo biến mất.
- Không đổi taxonomy nguồn hàng loạt; 13 ca lệch xử lý từng ca có đối chiếu.
- Không đụng đường DeepSeek (mọi thay đổi ở đây là tính toán/hiển thị, không phát
  sinh API call).

## 6. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Bỏ chặn sai → phát hành khuyến nghị trên dữ liệu hỏng | Giai đoạn 4 chỉ nới cho năm ngoài cửa sổ định giá; năm định giá vẫn chặn |
| Ngưỡng tương đối che mất lệch thật ở DN lớn | Dùng đồng thời ngưỡng tuyệt đối và tương đối, ghi log số lệch kể cả khi không cảnh báo |
| Sửa `financials.py` phá test/UI khác | Giai đoạn 1 viết test trước; `validate_model_integrity` còn phục vụ check cân đối BS |
