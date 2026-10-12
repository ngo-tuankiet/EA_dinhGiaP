# BÁO CÁO TỔNG QUAN KIẾN TRÚC & MÔ HÌNH ĐỊNH GIÁ HỆ THỐNG ANTIGRAVITY VN100

**Kính gửi:** Ban Lãnh đạo / Cấp Quản lý
**Chủ đề:** Thuyết minh chi tiết cơ chế hoạt động, luồng dữ liệu và mô hình phân tích định giá tự động.

---

## 1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG (SYSTEM ARCHITECTURE)

Hệ thống được thiết kế theo kiến trúc Microservices & Data-driven, phân tách rõ ràng giữa tầng điều phối, tầng xử lý tính toán và tầng tương tác người dùng.

```mermaid
graph TD
    A[n8n Orchestrator] -->|Điều phối & Triggers| B(Python Service - Core Engine)
    
    subgraph Dữ Liệu Đầu Vào (Data Ingestion)
    D1[vnstock API / Market Data] --> B
    D2[UBCK / HOSE / HNX] --> B
    D3[Dữ liệu Vĩ mô GSO / SBV] --> B
    end
    
    B <-->|Đọc/Ghi Dữ Liệu| C[(PostgreSQL Data Warehouse)]
    
    subgraph Tương Tác & Báo Cáo
    B -->|Xuất/Cập nhật định giá| E[Google Sheets - Bảng điều khiển 2 chiều]
    B -->|Sinh báo cáo tự động| F[Google Drive - PDF/Log]
    B -->|Cảnh báo Real-time| G[Discord Bot - Alerts]
    end
    
    E -.->|Thay đổi giả định / Trigger Recompute| A
```

**Nguyên tắc cốt lõi:**
- **n8n:** Đóng vai trò nhạc trưởng (Orchestrator), điều phối các tiến trình chạy tự động (Cron jobs), nhận Webhook khi có Báo cáo tài chính (BCTC) mới, và xử lý cảnh báo.
- **Python Core Engine:** Đảm nhiệm toàn bộ các nghiệp vụ nặng: Làm sạch dữ liệu (Data Cleansing), Chấm điểm chất lượng (QC), Phân tích (Analysis), Dự phóng (Forecasting) và Định giá (Valuation).
- **PostgreSQL:** Kho dữ liệu trung tâm (Single Source of Truth), lưu trữ chuỗi thời gian của giá, BCTC chuẩn hóa, dữ liệu vĩ mô và lịch sử các kịch bản định giá.
- **Google Sheets:** Không chỉ để xem kết quả mà còn là "Mô hình 2 chiều" (Two-way Model), cho phép Chuyên viên Phân tích nhập các giả định mới và hệ thống sẽ tính toán lại (Recompute) tức thì.

---

## 2. LUỒNG XỬ LÝ DỮ LIỆU & KIỂM SOÁT CHẤT LƯỢNG (DATA PIPELINE & QC)

Dữ liệu nguyên bản thường có độ nhiễu cao. Trước khi đi vào định giá, hệ thống phải đi qua một bộ lọc chất lượng gắt gao.

1. **Chuẩn hóa (Normalization):** Ưu tiên sử dụng BCTC Hợp nhất, BCTC Đã kiểm toán. Các chỉ tiêu tài chính được quy về một chuẩn chung (Standardized Line Items). Xử lý các trường hợp hồi tố (Restatement).
2. **Hàng rào rủi ro (Guardrails & Scoring):**
   - **Altman Z-Score:** Đánh giá xác suất phá sản.
   - **Beneish M-Score:** Phát hiện khả năng thao túng lợi nhuận (Earnings Manipulation).
   - **Piotroski F-Score:** Đánh giá chất lượng sức khỏe tài chính (thang điểm 0-9).
   - **Chất lượng lợi nhuận (Earnings Quality):** Đánh giá Cash Conversion (dòng tiền HĐKD so với Lợi nhuận ròng).

---

## 3. MÔ HÌNH ĐỊNH GIÁ CHUYÊN SÂU (SECTOR-SPECIFIC VALUATION MODELS)

Không có một mô hình nào đúng cho mọi ngành. Hệ thống sử dụng **Sector Router** để tự động phân luồng từng mã cổ phiếu (VN100) vào mô hình định giá phù hợp nhất với bản chất kinh doanh.

### 3.1. Nhóm Tài chính (Ngân hàng & Chứng khoán)
*Mã đại diện: VCB, BID, TCB, SSI, VND...*
- **Ngân hàng:** Sử dụng mô hình **Residual Income (Thu nhập thặng dư)** và **Justified P/B**. Đặc biệt, hệ thống áp dụng cơ chế **ROE Fade** (Hạ dần tỷ suất lợi nhuận trên vốn chủ sở hữu về mức bền vững trong dài hạn, có giới hạn trần max 15%) để tránh định giá quá cao (Overvaluation) trong các chu kỳ bùng nổ tín dụng.
- **Chứng khoán:** Định giá theo P/B × ROE kết hợp P/E tương đối dựa trên thanh khoản thị trường và dư nợ Margin.

### 3.2. Nhóm Bất Động Sản & Khu Công Nghiệp
*Mã đại diện: VHM, KDH, NLG, BCM, KBC...*
- Mô hình cốt lõi: **RNAV (Revalued Net Asset Value - Giá trị tài sản ròng đánh giá lại)** kết hợp theo dự án (Land Bank) hoặc quỹ đất KCN. 
- Yếu tố dự phóng: Tỷ lệ lấp đầy, giá thuê (với KCN) và tỷ lệ hấp thụ, tiến độ bàn giao, lãi suất vay mua nhà (với BĐS dân cư).

### 3.3. Nhóm Sản Xuất Chu Kỳ (Thép, Vật liệu xây dựng)
*Mã đại diện: HPG, HSG...*
- Sử dụng **DCF (Discounted Cash Flow)** nhưng với cơ chế **Mid-cycle Earnings** (Lợi nhuận chuẩn hóa giữa chu kỳ). Việc này giúp tránh "bẫy giá trị" (Value Trap) khi định giá ở đỉnh hoặc đáy chu kỳ hàng hóa (giá HRC, giá quặng sắt).

### 3.4. Nhóm Tập đoàn đa ngành (Holdings)
*Mã đại diện: MSN, GEX, VIC...*
- Sử dụng mô hình **SOTP (Sum-of-the-Parts - Tổng các bộ phận)**. Định giá riêng rẽ từng mảng kinh doanh cốt lõi (Bán lẻ, Tiêu dùng, Tài chính, Khoáng sản) sau đó chiết khấu tập đoàn (Holding Discount) để ra giá trị hợp lý.

### 3.5. Nhóm Phi tài chính cơ bản (Bán lẻ, F&B, Tiện ích)
*Mã đại diện: MWG, VNM, GAS...*
- Sử dụng **FCFF DCF (Free Cash Flow to Firm)** nhiều giai đoạn kết hợp định giá tương đối **EV/EBITDA** và **P/E**.

---

## 4. THAM SỐ VĨ MÔ & TRỌNG SỐ ĐỊNH GIÁ (MACRO INPUTS & WEIGHTINGS)

### 4.1. Chi phí vốn & Tỷ suất chiết khấu (WACC & COE)
Mô hình định giá tuân thủ chuẩn mực của Aswath Damodaran:
- **Cost of Equity (COE):** Áp dụng CAPM `Re = Rf + β × ERP_VN`.
  - **Rf (Risk-free rate):** Lấy theo Lợi suất Trái phiếu Chính phủ VN 10 năm.
  - **Beta (β):** Blume Beta (Hồi quy giá so với VN-Index và điều chỉnh mượt).
  - **ERP_VN:** Phần bù rủi ro vốn cổ phần đã bao gồm Phần bù rủi ro quốc gia (Country Risk Premium) của Việt Nam.

### 4.2. Khung Macro Overlay (Yếu tố Vĩ mô)
Dữ liệu vĩ mô (GDP, CPI, Lãi suất điều hành SBV, Tăng trưởng tín dụng, Tỷ giá) được cập nhật liên tục để làm "Overlay". Các chỉ báo này sẽ tác động trực tiếp vào các biến số:
- Điều chỉnh Premium/Discount cho WACC.
- Điều chỉnh dự phóng tăng trưởng doanh thu (Revenue Growth) theo sức mua bán lẻ hoặc lạm phát.

### 4.3. Phương pháp Blend (Trọng số kết quả)
Hệ thống không dựa vào một con số duy nhất. Giá trị hợp lý cuối cùng (Blended Fair Value) là sự kết hợp có trọng số giữa:
- **Định giá tuyệt đối (Absolute Valuation):** DCF, RNAV, Residual Income (Trọng số thường chiếm 60% - 70%).
- **Định giá tương đối (Relative Valuation):** P/E, P/B, EV/EBITDA mục tiêu so sánh với Peer Group và Lịch sử (Trọng số 30% - 40%).

---

## 5. TỔNG KẾT
Antigravity VN100 không chỉ là một công cụ xuất báo cáo tự động, mà là một **Hệ sinh thái Phân tích Đầu tư (Investment Analysis Ecosystem)** toàn diện:
1. Tính khách quan, loại bỏ cảm tính (Data-driven).
2. Chuẩn mực khắt khe về tài chính (Damodaran WACC, ROE Fade, SOTP).
3. Linh hoạt điều chỉnh (Tương tác 2 chiều trên Google Sheets).
4. Phản ứng theo thời gian thực (Cảnh báo Discord khi có BCTC mới).

Điều này giúp Ban điều hành và đội ngũ Đầu tư luôn nắm bắt được "Intrinsic Value" (Giá trị nội tại) của thị trường một cách sát sao và khoa học nhất.
