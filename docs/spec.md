# Hệ thống định giá tự động VN100 — Bản đặc tả kỹ thuật (Spec)

> Tài liệu này là spec nguồn để đưa cho Codex / Claude Code build từng phần.
> Kiến trúc: **n8n (điều phối) → Python service (tính toán) → PostgreSQL (lưu trữ) → Google Sheets + Discord + Google Drive (đầu ra)**.

---

## 1. Tổng quan kiến trúc

```
                    ┌─────────────────────────────────────────────┐
                    │                  n8n (orchestrator)          │
                    │  - Cron trigger (batch backfill)             │
                    │  - Webhook/poll trigger (BCTC mới)           │
                    │  - Manual trigger (nhập mã chạy theo ý muốn) │
                    └───────────────┬─────────────────────────────┘
                                    │ HTTP call
                                    ▼
        ┌────────────────────────────────────────────────────────┐
        │              Python service (FastAPI)                   │
        │  ingest → clean/QC → analyze → forecast → value         │
        └───────┬───────────────────────────────────┬────────────┘
                │ read/write                          │ read/write
                ▼                                     ▼
   ┌─────────────────────────┐          ┌──────────────────────────┐
   │   Nguồn dữ liệu          │          │   PostgreSQL (kho dữ liệu)│
   │  - vnstock API           │          │  - financials_quarterly  │
   │  - Filing UBCK/HOSE/HNX  │          │  - prices_daily          │
   │  - GSO / SBV (macro)     │          │  - macro / industry      │
   └─────────────────────────┘          │  - assumptions / outputs │
                                         └──────────────────────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              ▼                     ▼                      ▼
      ┌──────────────┐     ┌──────────────┐       ┌──────────────┐
      │ Google Sheets│     │   Discord    │       │ Google Drive │
      │ (model 2 chiều)│   │  (cảnh báo)  │       │ (lưu PDF/log)│
      └──────────────┘     └──────────────┘       └──────────────┘
```

**Nguyên tắc phân vai:**
- **n8n** chỉ điều phối: trigger, gọi API, định tuyến, gửi thông báo, xử lý lỗi/retry. KHÔNG tính toán nặng trong n8n.
- **Python service** làm toàn bộ ingest → QC → phân tích → dự phóng → định giá. Triển khai dạng API (FastAPI) để n8n gọi qua HTTP node.
- **PostgreSQL** là nguồn sự thật (single source of truth) cho lịch sử. vnstock chỉ là nguồn nạp, không phải nơi lưu.
- **Google Sheets** là giao diện điều chỉnh giả định 2 chiều (chi tiết mục 8).

---

## 2. Tầng dữ liệu

### 2.1 Nguồn dữ liệu
| Nguồn | Lấy gì | Cách lấy |
|---|---|---|
| vnstock API (đã mua) | Giá, BCTC (CĐKT, KQKD, LCTT), chỉ số, cổ đông, sự kiện | SDK/HTTP, nạp theo mã |
| HOSE / HNX / UBCK | Công bố thông tin, BCTC bản gốc, nghị quyết, thay đổi sở hữu | Poll RSS/trang CBTT hoặc scrape có lịch |
| GSO (Tổng cục Thống kê) | GDP, CPI, IIP, bán lẻ, FDI | Scrape/định kỳ |
| SBV (NHNN) | Lãi suất điều hành, tỷ giá, M2, tăng trưởng tín dụng | Scrape/định kỳ |
| TPCP 10 năm | Risk-free rate cho WACC | vnstock hoặc nguồn bond |

### 2.2 Phạm vi & thứ tự
- Universe: **VN100** (danh sách lấy động, refresh khi HOSE cập nhật rổ).
- **Phase 1 — backfill tuần tự:** chạy lần lượt từng mã VN100 để dựng đủ cơ sở dữ liệu lịch sử (tối thiểu 5 năm / 20 quý BCTC + giá daily). Có rate-limit + checkpoint để chạy lại từ mã lỗi.
- **Phase 2 — vận hành:** chạy khi (a) có BCTC mới, (b) bạn nhập mã thủ công.

---

## 3. Database schema (PostgreSQL)

```sql
-- Danh mục mã
CREATE TABLE tickers (
  ticker        TEXT PRIMARY KEY,
  company_name  TEXT,
  exchange      TEXT,
  sector        TEXT,          -- map sang nhóm định giá (mục 6)
  industry      TEXT,
  is_vn100      BOOLEAN,
  updated_at    TIMESTAMPTZ DEFAULT now()
);

-- BCTC theo quý (đã chuẩn hóa)
CREATE TABLE financials_quarterly (
  ticker        TEXT REFERENCES tickers(ticker),
  fiscal_year   INT,
  fiscal_quarter INT,          -- 1..4, 0 = cả năm
  is_consolidated BOOLEAN,     -- hợp nhất vs công ty mẹ
  is_restated   BOOLEAN,       -- bản điều chỉnh hồi tố
  statement     TEXT,          -- 'BS' | 'IS' | 'CF'
  line_item     TEXT,          -- mã chỉ tiêu chuẩn hóa
  value         NUMERIC,
  currency      TEXT DEFAULT 'VND',
  source        TEXT,          -- 'vnstock' | 'hose_filing'
  ingested_at   TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (ticker, fiscal_year, fiscal_quarter, statement, line_item, is_consolidated, is_restated)
);

-- Giá daily
CREATE TABLE prices_daily (
  ticker TEXT, trade_date DATE, open NUMERIC, high NUMERIC, low NUMERIC,
  close NUMERIC, adj_close NUMERIC, volume BIGINT, value NUMERIC,
  foreign_buy NUMERIC, foreign_sell NUMERIC,
  PRIMARY KEY (ticker, trade_date)
);

-- Dữ liệu vĩ mô & ngành
CREATE TABLE macro_series (
  series_code TEXT, period DATE, value NUMERIC, source TEXT,
  PRIMARY KEY (series_code, period)
);
CREATE TABLE industry_indicators (
  sector TEXT, indicator_code TEXT, period DATE, value NUMERIC,
  PRIMARY KEY (sector, indicator_code, period)
);

-- Giả định định giá (đồng bộ với Google Sheet)
CREATE TABLE valuation_assumptions (
  ticker TEXT, version INT, edited_by TEXT,  -- 'system' | 'user'
  rev_growth JSONB, margin JSONB, wacc NUMERIC, terminal_growth NUMERIC,
  target_multiple JSONB, scenario TEXT,      -- 'bull'|'base'|'bear'
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (ticker, version, scenario)
);

-- Kết quả định giá
CREATE TABLE valuation_outputs (
  ticker TEXT, assumption_version INT, model TEXT,
  scenario TEXT, target_price NUMERIC, current_price NUMERIC,
  upside_pct NUMERIC, rating TEXT, margin_of_safety NUMERIC,
  flags JSONB,                               -- Z/M/F score, red flags
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (ticker, assumption_version, model, scenario)
);
```

---

## 4. Tầng kiểm soát chất lượng (QC) — chạy trước khi định giá

- Chuẩn hóa: hợp nhất vs công ty mẹ (ưu tiên hợp nhất), năm tài chính lệch dương lịch, đơn vị tiền.
- Xử lý restatement: khi có bản hồi tố, đánh dấu `is_restated`, dùng bản mới nhất cho dự phóng nhưng giữ bản cũ để truy vết.
- Chỉ báo cảnh báo (lưu vào `flags`):
  - **Altman Z-score** — rủi ro phá sản (chọn biến thể phù hợp DN sản xuất / phi sản xuất).
  - **Beneish M-score** — khả năng thao túng lợi nhuận.
  - **Piotroski F-score** — chất lượng tài chính (0–9).
  - **Chất lượng lợi nhuận:** accruals ratio, tỷ lệ LN ròng / dòng tiền HĐKD (cash conversion).
- Lọc thanh khoản: ADTV 3 tháng < ngưỡng → gắn cờ "thanh khoản thấp", vẫn định giá nhưng cảnh báo.

---

## 5. Tầng phân tích tài chính
- Common-size (BS, IS), phân tích xu hướng nhiều quý.
- Bộ chỉ số: thanh khoản, đòn bẩy, hiệu quả, sinh lời; phân rã **DuPont** (ROE = biên LN × vòng quay TS × đòn bẩy).
- So sánh peer trong cùng nhóm ngành (median ngành làm tham chiếu).

---

## 6. Tầng định giá theo ngành (cốt lõi)

Mỗi mã VN100 được map vào một nhóm; mỗi nhóm dùng bộ model riêng. Kết quả cuối = blend có trọng số giữa **định giá tuyệt đối** và **định giá tương đối**.

| Nhóm ngành (VN100 điển hình) | Model chính | Model phụ | Industry indicators theo dõi |
|---|---|---|---|
| Ngân hàng (VCB, BID, CTG, TCB, MBB, ACB, VPB, STB, HDB...) | Residual Income / Justified P/B theo ROE | DDM | NIM, CASA, NPL, LLR coverage, CAR, credit cost, tăng trưởng tín dụng |
| Chứng khoán (SSI, VND, HCM, VCI...) | P/B × ROE | P/E | Thanh khoản TT, dư nợ margin, phí GD |
| Bảo hiểm (BVH, BMI...) | P/B + Embedded Value | DDM | Lãi suất, tỷ lệ bồi thường |
| Bất động sản (VHM, VIC, VRE, NVL, KDH, DXG, PDR...) | **RNAV/NAV theo dự án** | P/B | Tỷ lệ hấp thụ, nguồn cung, giá đất, lãi suất vay mua nhà |
| Thép / vật liệu (HPG, HSG, NKG...) | DCF với **earnings chuẩn hóa mid-cycle** | EV/EBITDA | Giá HRC, giá quặng/than, BĐS & xây dựng |
| Tiện ích/điện/nước (GAS, POW, REE, NT2...) | DDM | DCF (FCFF) | Phụ tải, giá CGM, thủy văn, giá khí |
| Bán lẻ (MWG, FRT, PNJ...) | DCF (FCFF) | EV/EBITDA, P/E | SSSG, số cửa hàng, sức mua bán lẻ |
| F&B / tiêu dùng (VNM, MSN, SAB...) | DCF (FCFF) | EV/EBITDA | Giá nguyên liệu, thu nhập khả dụng |
| Công nghiệp/KCN (BCM, KBC, IDC, GVR...) | RNAV (đất KCN) + DCF | EV/EBITDA | FDI, lấp đầy KCN, giá thuê |
| Holdings/đa ngành (MSN, GEX...) | **Sum-of-the-Parts (SOTP)** | NAV | Theo từng mảng con |
| Phi tài chính thông thường (mặc định) | **FCFF DCF** | EV/EBITDA, P/E | Theo ngành |

**Discount rate (WACC) cho thị trường VN:**
- Cost of equity (CAPM): `Re = Rf + β × ERP_VN`
  - `Rf` = lợi suất TPCP 10 năm VN (lấy động).
  - `β` ước lượng hồi quy từ giá mã vs VN-Index (có thể unlever/relever theo cấu trúc vốn).
  - `ERP_VN` = equity risk premium Việt Nam (cộng country risk premium — KHÔNG dùng ERP Mỹ).
- Cost of debt từ chi phí lãi vay thực tế / cấu trúc nợ; điều chỉnh thuế.

**Đầu ra mỗi mã:** target price theo 3 kịch bản (bull/base/bear), upside/downside vs giá hiện tại, margin of safety, rating (Mua/Nắm giữ/Bán theo ngưỡng upside cấu hình được).

---

## 7. Overlay vĩ mô & ngành
- **Top-down:** GDP, CPI, lãi suất, tỷ giá, tăng trưởng tín dụng, M2 → điều chỉnh giả định tăng trưởng & WACC.
- **Vòng đời ngành & vị thế cạnh tranh:** chấm điểm định tính (có thể bán tự động) đưa vào memo.
- Industry indicators đẩy thẳng vào driver dự phóng (vd: giá HRC → biên LN thép; tín dụng → tăng trưởng cho vay ngân hàng).

---

## 8. Cơ chế Google Sheet 2 chiều (tính năng bạn yêu cầu)

Mục tiêu: hệ thống ra giá tự động, nhưng bạn sửa kỳ vọng trong Sheet → giá đổi theo, và sửa được cả 2 chiều.

**Thiết kế lai (khuyến nghị):**
- **Tab dữ liệu (read-only):** Python ghi xuống BCTC chuẩn hóa, chỉ số, flags QC, giá hiện tại. Bạn không sửa tab này.
- **Tab giả định (editable):** Python ghi *base case* (tăng trưởng DT, biên LN, WACC, terminal growth, target multiple). Bạn sửa trực tiếp các ô này.
- **Tab kết quả:**
  - Với model **đơn giản** (multiples, DDM): dựng **công thức sống ngay trong Sheet** → bạn sửa giả định là target price đổi *tức thì*, minh bạch, không cần gọi lại Python.
  - Với model **phức tạp** (DCF nhiều giai đoạn, SOTP, RNAV): để Python tính. Có **nút "Recompute"** (Google Apps Script gọi webhook n8n → Python đọc giả định đã sửa → tính lại → ghi target price mới về Sheet).
- **Đồng bộ về DB:** mỗi lần bạn sửa giả định và recompute, lưu một `version` mới vào `valuation_assumptions` (đánh dấu `edited_by='user'`) để truy vết và backtest.

**Luồng:** Python ghi base case → bạn chỉnh ô kỳ vọng → (model đơn giản đổi ngay / model phức tạp bấm Recompute) → target price + upside cập nhật → ghi version về DB.

---

## 9. Đầu ra: Sheets + Discord + Drive
- **Google Sheets:** model động (mục 8) — 1 master dashboard liệt kê toàn VN100 (target price, upside, rating, flags) + sheet chi tiết từng mã.
- **Discord:** cảnh báo khi (a) có BCTC mới đã định giá xong, (b) upside vượt ngưỡng (vd > 20%), (c) flag rủi ro (Z-score/M-score xấu), (d) job lỗi.
- **Google Drive:** lưu báo cáo PDF (investment memo tự sinh: luận điểm, định giá, catalyst, rủi ro) + log + bản snapshot dữ liệu theo kỳ.

---

## 10. Thiết kế workflow n8n

**WF-1 — Backfill tuần tự (chạy 1 lần, Phase 1):**
`Manual/Cron trigger → lấy danh sách VN100 → Loop từng mã → HTTP gọi Python /ingest → /qc → /analyze → ghi DB → cập nhật checkpoint → (lỗi: retry + báo Discord) → khi xong báo Discord`

**WF-2 — Sự kiện BCTC mới (Phase 2):**
`Poll/Webhook CBTT HOSE/HNX → phát hiện mã có BCTC mới → HTTP /ingest+revalue mã đó → ghi DB + cập nhật Sheet → Discord alert`

**WF-3 — Chạy theo yêu cầu (nhập mã thủ công):**
`Form/Webhook nhận mã (vd qua lệnh Discord hoặc form n8n) → HTTP /revalue → cập nhật Sheet → trả kết quả về Discord`

**WF-4 — Recompute từ Google Sheet:**
`Apps Script (nút Recompute) → Webhook n8n → Python đọc giả định → tính lại → ghi Sheet + lưu version DB`

**WF-5 — Cập nhật vĩ mô/ngành (định kỳ):**
`Cron (hàng tuần/tháng) → ingest GSO/SBV/industry → ghi DB`

---

## 11. Cấu trúc Python service (gợi ý module)

```
valuation/
├── api/                 # FastAPI endpoints: /ingest /qc /analyze /forecast /revalue
├── ingest/
│   ├── vnstock_client.py
│   ├── filings_hose.py
│   └── macro_gso_sbv.py
├── quality/
│   ├── normalize.py     # hợp nhất, năm TC lệch, đơn vị
│   ├── scores.py        # Altman Z, Beneish M, Piotroski F
│   └── earnings_quality.py
├── analysis/
│   ├── ratios.py
│   └── dupont.py
├── forecast/
│   ├── drivers.py       # gắn industry indicator vào driver
│   └── scenarios.py     # bull/base/bear
├── valuation/
│   ├── wacc.py
│   ├── dcf.py           # FCFF/FCFE
│   ├── multiples.py
│   ├── ddm.py
│   ├── bank_ri.py       # residual income / justified P/B
│   ├── rnav.py          # bất động sản
│   ├── sotp.py
│   └── router.py        # map sector → model
├── output/
│   ├── gsheets.py       # ghi/đọc 2 chiều
│   ├── discord.py
│   └── memo_pdf.py      # sinh investment memo
└── db/
    └── models.py        # ORM/queries
```

---

## 12. Backtesting & governance
- Lưu mọi dự phóng theo `version` để sau này so target price cũ vs giá thực tế → đo độ chính xác model theo ngành.
- Định kỳ review giả định mặc định (vd ERP_VN, ngưỡng rating).
- Audit trail: ai sửa giả định gì, khi nào (`edited_by`, `created_at`).

---

## 13. Lộ trình triển khai theo giai đoạn

**Giai đoạn 0 — Hạ tầng (1):** dựng PostgreSQL + schema, FastAPI skeleton, kết nối vnstock, n8n (self-host), Google API (Sheets/Drive), Discord webhook.

**Giai đoạn 1 — Ingest + QC + Backfill VN100:** nạp giá + BCTC 5 năm toàn VN100 (WF-1), chuẩn hóa, scores. *Mốc: DB đầy đủ cho 100 mã.*

**Giai đoạn 2 — Định giá lõi (model phổ biến trước):** DCF + multiples cho nhóm phi tài chính + ngân hàng (chiếm tỷ trọng lớn VN100). Master dashboard Sheet.

**Giai đoạn 3 — Sheet 2 chiều + Recompute:** giả định editable, công thức sống cho model đơn giản, nút Recompute cho DCF/RNAV/SOTP.

**Giai đoạn 4 — Model ngành đặc thù:** RNAV (BĐS), SOTP (holdings), mid-cycle (thép), EV (bảo hiểm).

**Giai đoạn 5 — Vĩ mô/ngành overlay + memo PDF + backtest.**

**Giai đoạn 6 — Vận hành sự kiện:** WF-2 (BCTC mới), WF-3 (chạy theo mã), WF-5 (macro định kỳ), cảnh báo Discord.

---

## 14. Rủi ro & lưu ý
- **Đừng tự động hóa 100% giả định DCF** — base case máy đặt chỉ là điểm khởi đầu; quyết định cuối cần bạn chỉnh kỳ vọng (đúng như thiết kế Sheet 2 chiều).
- **Cyclical** (thép, vận tải): định giá theo earnings đỉnh chu kỳ là bẫy → dùng mid-cycle.
- **Chất lượng filing**: BCTC quý chưa kiểm toán; ưu tiên bản kiểm toán/hợp nhất khi có.
- **Rate limit vnstock & CBTT**: backfill phải có checkpoint + retry để chạy lại từ mã lỗi.
- **n8n không tính nặng**: mọi DCF/Monte Carlo để Python; n8n chỉ điều phối.
- **Bảo mật**: khóa API, credential Google/Discord lưu trong secret store của n8n, không hardcode.
