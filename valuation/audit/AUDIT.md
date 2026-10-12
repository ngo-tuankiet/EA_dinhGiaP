# BÁO CÁO AUDIT CODEBASE & SCHEMA HỆ THỐNG ĐỊNH GIÁ

Tài liệu này ghi nhận hiện trạng cấu trúc mã nguồn (codebase), ranh giới giao diện (interface), schema cơ sở dữ liệu và các rủi ro phát hiện trong dự án định giá VN100 hiện tại trước khi thực hiện nâng cấp.

---

## 1. PHÂN TÍCH CODEBASE & INTERFACE HIỆN TẠI

Hệ thống định giá được tổ chức dưới dạng các lớp định giá chuyên biệt trong thư mục `valuation/engine/models/`.

### 1.1. Các Lớp Định Giá (Valuation Models)

#### 1.1.1. Lớp Cơ Bản `BaseValuationModel`
- **Đường dẫn:** `valuation/engine/models/base.py`
- **Mô tả:** Chứa thuộc tính dùng chung (`ticker`, `current_financials`, `assumptions`, `coe`, `wacc`, `g`) và logic tính độ nhạy (Greeks) thông qua phương pháp sai phân (bump-and-recalc).
- **Interface:**
  - `__init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any])`
  - `validators(self)`: Ràng buộc $g < WACC$ (nếu dùng WACC) và $g < COE$. Tự động clamp giảm $g$ xuống dưới ngưỡng $0.5\%$.
  - `forecast_drivers(self)`: Abstract method.
  - `perform_valuation(self)`: Abstract method.
  - `calculate_greeks(self)`: Tính toán đạo hàm $\frac{\partial FV}{\partial Driver}$ cho các drivers được cấu hình trong `assumptions['drivers']`.

#### 1.1.2. Lớp Định Giá Phi Tài Chính `DCFValuationModel`
- **Đường dẫn:** `valuation/engine/models/dcf.py`
- **Mô tả:** Định giá các doanh nghiệp phi tài chính (HPG, FPT, DGC...) bằng phương pháp FCFF (dựa trên tăng trưởng doanh thu, biên EBIT, tỷ lệ tái đầu tư, WACC) phối hợp EV/EBITDA với tỷ trọng mặc định 50/50.
- **Interface:**
  - `__init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any])`
  - `forecast_drivers(self)`: Dự phóng doanh thu, EBIT, NOPAT, Reinvestment và FCFF trong 5 năm.
  - `perform_valuation(self)` -> Trả về `Dict[str, Any]` gồm:
    - `blended_fair_value_per_share`: Giá trị hợp lý sau pha trộn.
    - `dcf_fvps`: Giá trị hợp lý từ FCFF.
    - `multiples_fvps`: Giá trị hợp lý từ EV/EBITDA.
    - `weight_dcf`, `enterprise_value_dcf`, `equity_value_dcf`.

#### 1.1.3. Lớp Định Giá Ngân Hàng `VCBValuationModel`
- **Đường dẫn:** `valuation/engine/models/bank_vcb.py`
- **Mô tả:** Định giá ngân hàng (VCB) bằng phương pháp Residual Income (RI) + P/B. Lớp này độc lập và không kế thừa `BaseValuationModel`.
- **Interface:**
  - `__init__(self, current_financials: dict, assumptions: dict)`
  - `forecast_drivers(self)` -> `pd.DataFrame`: Dự phóng cho vay, tổng tài sản, VCSH, thu nhập lãi thuần (NII), thu nhập ngoài lãi (Non-II), trích lập dự phòng (Credit Cost), LNST và cổ tức trong 5 năm.
  - `calculate_residual_income(self)` -> `dict`
  - `calculate_pb_valuation(self)` -> `dict`
  - `blend_valuation(self, weight_ri=0.5, weight_pb=0.5)` -> `dict`
  - `calculate_greeks(self)` -> `dict`
- **Quy tắc an toàn tài chính tích hợp:**
  - **Sanity Floor cho COE:** Nếu $COE < rf + 5\%$, bắn lỗi `ValueError("COE_TOO_LOW")`.
  - **Implied P/B Warning:** Nếu P/B ngầm định từ ROE vĩnh viễn nằm ngoài khoảng $[0.5, 4.0]$, bắn log warning `[IMPLIED_PB_WARNING]`.
  - **Double-count Detection:** Bắn warning nếu dùng $rf > 2.5\%$ và $erp > 8.5\%$ (gợi ý double-count rủi ro quốc gia).

#### 1.1.4. Lớp Định Giá Chứng Khoán `SecuritiesValuationModel`
- **Đường dẫn:** `valuation/engine/models/securities.py`
- **Mô tả:** Định giá công ty chứng khoán (SSI...) sử dụng Residual Income + P/B dựa trên thanh khoản thị trường, thị phần môi giới, dư nợ margin.
- **Interface tương tự** `DCFValuationModel` (kế thừa `BaseValuationModel`).

---

### 1.2. consensus_helper & ttm_helper

#### 1.2.1. consensus_helper
- **Đường dẫn:** `valuation/engine/consensus_helper.py`
- **Interface:** `get_consensus_stats(ticker: str, trade_date: datetime.date, db: Session) -> Dict[str, Any]`
- **Chức năng:** Lọc các khuyến nghị của broker trong vòng 180 ngày tính đến ngày `trade_date`, tính giá mục tiêu trung vị (median), trung bình (mean) và số lượng báo cáo.

#### 1.2.2. ttm_helper
- **Đường dẫn:** `valuation/engine/ttm_helper.py`
- **Mô tả:** Cầu nối dữ liệu thô từ database. Thực hiện quy đổi quý sang năm:
  - **Balance Sheet (Stock):** `get_latest_balance()` lấy số quý gần nhất của 4 quý gần nhất.
  - **Income Statement (Flow):** `get_ttm_value()` cộng dồn 4 quý gần nhất (TTM) hoặc tỷ lệ hóa nếu thiếu quý.
  - **Shares Outstanding:** `get_shares_outstanding()` tính số cổ phiếu lưu hành bằng cách chia Vốn chủ sở hữu/Vốn góp cho mệnh giá 10,000 VND (hoặc lấy direct volume).
  - **Ước lượng tham số động:** `estimate_vcb_beta()` tính beta động so với VNINDEX từ giá 2 năm; `get_latest_tpcp_10y()` lấy TPCP VN 10Y làm risk-free.

---

### 1.3. Điểm Gọi Hệ Thống (Entrypoints / Callers)

Các model định giá hiện tại được gọi thông qua API Route:
- **Đường dẫn:** `valuation/api/routes/valuation.py`
- **Hàm:** `revalue_ticker(ticker: str, background_tasks: BackgroundTasks, db_read: Session, db_write: Session)`
- **Luồng hoạt động:**
  1. Xác minh Ticker tồn tại trong bảng `tickers`.
  2. Lấy dữ liệu BCTC từ `financials_quarterly`.
  3. Lọc ticker:
     - Nếu thuộc nhóm `BANK_TICKERS`: Dùng dữ liệu từ `build_vcb_current_financials`, chạy model `VCBValuationModel`.
     - Nếu thuộc FPT, HPG, DGC, SSI: Dùng helper tương ứng và chạy `DCFValuationModel` hoặc `SecuritiesValuationModel`.
     - Nếu thuộc VHM, DIG: Chạy `RNAVValuationModel`.
     - Nếu MSN: Chạy `SOTPValuationModel`.
  4. Thực hiện chạy QC (`run_qc_checks`), so sánh giá trị ngầm định (PE, PB, EV/EBITDA) với benchmark và đối chiếu consensus.
  5. Lưu kết quả định giá vào `ValuationOutput` và Greeks vào `ValuationSensitivity`.
  6. Gửi background task cập nhật lên Google Sheets.

---

## 2. PHÂN TÍCH SCHEMA CƠ SỞ DỮ LIỆU (POSTGRESQL ONLY)

Hệ thống sử dụng cơ sở dữ liệu PostgreSQL thực tế với các bảng chính:

| Tên bảng | Mục đích | Các cột quan trọng & Kiểu dữ liệu | Quy ước đơn vị dữ liệu |
|---|---|---|---|
| `tickers` | Danh mục cổ phiếu | `ticker` (PK), `company_name`, `sector`, `industry`, `is_vn100` | Ticker VN100 |
| `financials_quarterly` | BCTC theo quý (nguồn) | `ticker`, `fiscal_year`, `fiscal_quarter`, `statement`, `line_item`, `value` (Numeric), `currency` | **Đồng (VND thô)**. Ví dụ: VCSH = `220494731000000.0` đồng |
| `prices_daily` | Giá đóng cửa hàng ngày | `ticker`, `trade_date`, `close` (Numeric), `volume`, `price_unit` | **Đồng (VND thô)**. Ví dụ: close = `7476.25` |
| `valuation_outputs` | Lưu kết quả chạy định giá | `id` (PK), `ticker`, `blended_fair_value_per_share` (Numeric), `fair_value_bull`, `fair_value_bear`, `flags` (JSON), `macro_snapshot` (JSON) | Đồng (VND thô) |
| `valuation_sensitivities` | Lưu độ nhạy assumptions | `ticker`, `assumption_version` (FK), `driver_code`, `dFV_ddriver` (Numeric) | Đạo hàm tuyệt đối |
| `consensus_history` | Khuyến nghị của CTCK | `ticker`, `broker`, `report_date`, `target_price` (Numeric) | Đồng (VND thô) |
| `macro_series` | Chỉ số vĩ mô | `indicator_code` (TPCP_10Y...), `date`, `value` (Numeric) | Tỷ lệ thô (ví dụ: `0.032` = 3.2%) |

### Quy ước đơn vị tiền tệ thô (VND):
- **BCTC Value:** Đơn vị là Đồng thô (VND). Các số lớn đạt mức $10^{12} - 10^{15}$ VND.
- **Prices Close:** Đơn vị là Đồng thô (VND). Ví dụ `7476.25` VND (cần chú ý xem giá đã điều chỉnh chưa).
- **Consensus Target Price:** Đơn vị là Đồng thô (VND).

---

## 3. PHÁT HIỆN LỖI LƯỚI AN TOÀN (TEST FAILURES)

Khi thực hiện chạy regression tests (`task-4070`), có 2/10 test cases bị **FAILED**:
1. `TestDGCSanityGates.test_revalue_dgc_and_check_sanity_gates`
2. `TestThreeTierValidationGates.test_revalue_fpt_and_check_sanity_gates`

### Nguyên nhân lỗi:
API Route `revalue_ticker` được khai báo trong `valuation/api/routes/valuation.py` có tham số bắt buộc thứ hai là `background_tasks: BackgroundTasks`. Tuy nhiên, trong mã nguồn test (`test_golden_dgc.py` và `test_golden_fpt_ssi.py`), hàm này đang được gọi trực tiếp bằng:
```python
res = revalue_ticker("DGC", db_read=db, db_write=db_write)
```
Thiếu đối số `background_tasks`, dẫn đến lỗi `TypeError: revalue_ticker() missing 1 required positional argument: 'background_tasks'`.

### Giải pháp khắc phục (trong Phase 0):
Cần sửa đổi cách gọi hàm trong các file test để truyền mock `BackgroundTasks()` hoặc một class mock tương ứng, đảm bảo lưới an toàn regression test luôn **PASS xanh** trước khi thực hiện bất kỳ thay đổi cấu trúc nào khác.
