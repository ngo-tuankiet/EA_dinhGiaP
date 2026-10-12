# KẾ HOẠCH TỔNG THỂ v2 — Hệ thống định giá VN100 "sống hằng ngày"

> Bản này **thay thế** roadmap cũ. Nó xây trên những gì đã có (data bank, model VCB, 2 thư viện prompt) và bổ sung tầng cốt lõi mới: **Two-Speed Valuation Engine** + **Daily Signal Layer** để định giá tự động mỗi ngày một cách có ý nghĩa.
> Đọc kèm: `@docs/spec.md`, `@AGENTS.md`, và các skill trong `@.agents/skills/`.

---

## PHẦN A — Tài sản hiện có (điểm xuất phát, KHÔNG làm lại)

| Tài sản | Vai trò trong hệ thống mới |
|---|---|
| **Model VCB (Excel):** driver-based forecast → Residual Income + P/B, blend 50/50 | Bản tham chiếu (golden reference) để máy hóa model ngân hàng. Mọi output Python phải khớp file này trước khi mở rộng. |
| **Dashboard phân tích VCB (Excel):** CAR, NPL, NPL coverage, CIR, COF, NIM, CASA, LDR, ROA/ROE, rủi ro thanh khoản/lãi suất | Bộ QC + chỉ số riêng ngành ngân hàng. Chuyển thành module `quality/bank_metrics.py`. |
| **Data bank (Excel):** `MaCK`, `BCTC` (VND tuyệt đối, wide), `Giá cổ phiếu` (daily) | Hạt giống kho dữ liệu → nạp thẳng vào Postgres, vừa tiết kiệm vừa có sẵn dữ liệu ngân hàng. |
| **Prompt "xây model chuyên sâu"** (driver-based, quy trình giả định→workbook→build) | Triết lý dự phóng bắt buộc của hệ thống: **driver-based, KHÔNG tăng trưởng cơ học**. Đưa vào skill. |
| **Bộ prompt end-to-end** (Macro Radar, Industry Indicator Dashboard, 5 forces, VRIO, value chain, consensus) | Khung phương pháp luận research → số hóa thành **Macro Radar Service** + **Consensus Tracker** + memo tự sinh. |

**Hai điều chỉnh về dữ liệu cần làm ngay:** (1) `BCTC` dạng wide một-dòng-mỗi-quý cần ánh xạ sang schema chuẩn (long) trong `spec.md`, hoặc giữ wide nhưng thêm bảng ánh xạ tên cột → `line_item`; (2) bổ sung cột `published_at` (ngày công bố thực tế) cho mỗi BCTC — bắt buộc để định giá point-in-time và backtest sau này.

---

## PHẦN B — Ý TƯỞNG CỐT LÕI: Two-Speed Valuation Engine

### B.1 Vấn đề với "định giá hằng ngày" ngây thơ
BCTC chỉ đổi theo quý. Chạy lại DCF/RI mỗi ngày với cùng dữ liệu → ra **cùng một con số fair value** → vô nghĩa và tốn tài nguyên. Cái thực sự thay đổi mỗi ngày là: **giá thị trường**, **dòng tiền/thanh khoản/khối ngoại**, **chỉ báo vĩ mô-ngành** (lãi suất, tỷ giá, lợi suất TPCP, giá HRC, tín dụng...), và **tin tức/sự kiện**.

### B.2 Hai nhịp đồng hồ
- **Nhịp CHẬM (Intrinsic Engine):** mô hình driver-based → fair value band (bull/base/bear). Chỉ chạy lại khi (a) có BCTC mới, (b) bạn sửa giả định, (c) sự kiện lớn. Đây chính là model VCB đã có, máy hóa.
- **Nhịp NHANH (Daily Signal Engine):** chạy mỗi ngày sau phiên, KHÔNG chạy lại mô hình đầy đủ, mà:
  1. Cập nhật **upside/downside & margin of safety** = (fair value band hiện hành) vs **giá đóng cửa hôm nay**.
  2. Cập nhật **Macro Radar** (chỉ báo vĩ mô-ngành theo tần suất), so ngưỡng cảnh báo.
  3. **Tái định giá nhanh bằng độ nhạy** (mục B.3) khi một driver vĩ mô-ngành dịch chuyển đáng kể.
  4. Sinh **bảng xếp hạng hành động hằng ngày** + cờ "cần review".
  5. Đẩy **bản tin Discord** + cập nhật Google Sheet dashboard.

### B.3 Kỹ thuật "greeks" cho định giá — điểm khiến nó thật sự hằng ngày
Khi Intrinsic Engine (nhịp chậm) chạy, ngoài fair value, nó **tính sẵn và lưu lại độ nhạy** của fair value theo từng driver then chốt (đạo hàm riêng / độ co giãn):

```
∂FV/∂r        (theo cost of equity / WACC — đổi theo lợi suất TPCP, lãi suất)
∂FV/∂g        (theo tăng trưởng dài hạn)
∂FV/∂NIM      (ngân hàng)
∂FV/∂credit_growth, ∂FV/∂credit_cost, ∂FV/∂CIR  (ngân hàng)
∂FV/∂ASP, ∂FV/∂spread  (thép/commodity)
∂FV/∂SSSG, ∂FV/∂biên gộp  (bán lẻ)
... theo driver tree của từng ngành
```

Nhịp nhanh hằng ngày tái định giá **xấp xỉ bậc nhất**, không chạy lại mô hình:

```
FV_today ≈ FV_base + Σ_i (∂FV/∂driver_i) × Δdriver_i
```

Ví dụ ngân hàng VCB: hôm nay lợi suất TPCP 10 năm tăng 20bps → `r` tăng → `FV_today = FV_base + (∂FV/∂r)×(+0.002)`. Bạn có **giá trị hợp lý cập nhật theo điều kiện thị trường mỗi ngày**, mà không cần BCTC mới. Khi độ dịch chuyển tích lũy của driver vượt ngưỡng (vd FV lệch >10% so với lần chạy chậm gần nhất) → hệ thống **tự gắn cờ "mô hình đã cũ, cần chạy lại đầy đủ"** và có thể tự kích hoạt nhịp chậm.

### B.4 Macro Radar trở thành "công dân hạng nhất"
Thể chế hóa ý tưởng Macro Radar của bạn thành một **service + config**: mỗi ngành có một bảng chỉ báo (`macro_radar.yaml`) gồm: chỉ báo | tần suất (ngày/tuần/tháng/quý) | nguồn | ngưỡng cảnh báo | **driver mô hình mà nó tác động tới**. Chính cột cuối là cầu nối: khi một chỉ báo cập nhật, hệ thống biết nó làm dịch chuyển driver nào → kích hoạt tái định giá nhanh (B.3).

### B.5 Daily Conviction Score (tổng hợp)
Mỗi mã mỗi ngày có một **điểm conviction** kết hợp: (1) margin of safety vs fair value, (2) trạng thái Macro Radar của ngành (thuận/nghịch), (3) cờ chất lượng (NPL/credit cost xấu đi, accruals...), (4) độ lệch với consensus CTCK, (5) tín hiệu dòng tiền (khối ngoại, thanh khoản). Điểm này xếp hạng toàn VN100 → bản tin "hôm nay chú ý mã nào".

---

## PHẦN C — Kiến trúc nâng cấp

```
                         ┌───────────────── n8n (orchestrator) ─────────────────┐
                         │ Cron EOD hằng ngày · Webhook filing/news · Manual mã  │
                         │ Cron macro (ngày/tuần) · Webhook recompute từ Sheet   │
                         └───────────────┬──────────────────────────────────────┘
                                         │ HTTP
        ┌────────────────────────────────┴─────────────────────────────────┐
        │                     Python service (FastAPI)                      │
        │                                                                   │
        │   NHỊP CHẬM (Intrinsic)          NHỊP NHANH (Daily Signal)         │
        │   ingest→QC→driver forecast      price update · macro radar        │
        │   →valuation→**sensitivity**     →fast re-price (greeks)           │
        │   →fair value band + greeks      →conviction score · flags         │
        └───────┬─────────────────────────────────┬─────────────────────────┘
                │                                  │
                ▼                                  ▼
   ┌────────────────────────┐        ┌──────────────────────────────────────┐
   │  Nguồn dữ liệu          │        │   PostgreSQL (kho + point-in-time)    │
   │  vnstock · filing HOSE  │        │   + bảng greeks, macro_radar,         │
   │  GSO/SBV · giá realtime │        │   consensus, daily_signal, snapshots  │
   └────────────────────────┘        └──────────────────────────────────────┘
                          │
        ┌─────────────────┼──────────────────────┐
        ▼                 ▼                       ▼
  Google Sheets      Discord (bản tin EOD     Google Drive
  (model 2 chiều)    + cảnh báo ngưỡng)        (memo PDF, snapshot)
```

---

## PHẦN D — Các tầng chi tiết

### D.1 Dữ liệu (mở rộng từ spec mục 3)
Bảng cũ giữ nguyên, **thêm**:
- `valuation_sensitivities` — lưu greeks cho mỗi mã/version: `(ticker, assumption_version, driver_code, dFV_ddriver, base_driver_value)`.
- `macro_radar` — `(sector, indicator_code, frequency, source, warn_low, warn_high, mapped_driver)`.
- `daily_signal` — `(ticker, trade_date, close, fair_value_fast, upside, margin_of_safety, conviction, flags)` (point-in-time, không ghi đè — mỗi ngày một dòng → thành track record).
- `consensus` — `(ticker, broker, report_date, target_price, rating, source)`.
- `bctc_published_at` — bổ sung ngày công bố cho mỗi BCTC.

### D.2 Dự phóng DRIVER-BASED theo ngành (bắt buộc — theo prompt của bạn)
**Tuyệt đối không** dự phóng cơ học "doanh thu +x%, chi phí = y% doanh thu". Mỗi ngành có **driver tree** riêng:
- **Ngân hàng** (đã có ở VCB, máy hóa): tăng trưởng tín dụng → quy mô sinh lời; YEA & COF → NIM → thu nhập lãi thuần; CASA; CIR → opex; credit cost & NPL → dự phòng; thuế → LNST; VCSH lăn theo lợi nhuận giữ lại → RI/PB.
- **Thép/commodity:** công suất × tỷ lệ vận hành → sản lượng; ASP & spread thép/nguyên liệu → biên gộp; capex/khấu hao; vốn lưu động; debt schedule → FCFF.
- **Bán lẻ:** số cửa hàng × doanh thu/cửa hàng × SSSG → doanh thu; biên gộp; chi phí thuê/nhân sự/logistics; vòng quay tồn kho → FCFF.
- **BĐS:** dòng tiền theo tiến độ bàn giao từng dự án → RNAV.
- (Các ngành khác theo bảng `valuation-models` skill.)

Cấu trúc workbook/giả định theo prompt "xây model chuyên sâu": Assumptions / Scenario Manager / các Build sheet / IS-BS-CF / FCFF-FCFE / Valuation / Sensitivity / Model Checks — phản chiếu thành các module Python tách bạch input/calc/output.

### D.3 Định giá (theo ngành — skill `valuation-models`)
Giữ nguyên bộ model theo ngành. **Bổ sung bước tính sensitivity (greeks)** sau mỗi lần định giá chậm: với mỗi driver then chốt, bump ±1 đơn vị nhỏ, đo thay đổi fair value, lưu `valuation_sensitivities`.

### D.4 Daily Signal Engine (mới)
Endpoint `POST /daily-signal` (n8n gọi EOD):
1. Lấy giá đóng cửa hôm nay toàn VN100.
2. Lấy chỉ báo Macro Radar có cập nhật hôm nay; tính Δdriver.
3. Fast re-price theo B.3 → `fair_value_fast`.
4. Tính upside, margin of safety, conviction score, flags.
5. Ghi `daily_signal` (1 dòng/mã/ngày).
6. Nếu |FV_fast − FV_base|/FV_base > ngưỡng → cờ "stale, cần chạy nhịp chậm" (có thể tự trigger).
7. Trả bảng xếp hạng + đẩy Discord + cập nhật Sheet.

### D.5 Macro Radar Service (mới)
- Ingest chỉ báo theo tần suất (cron ngày/tuần/tháng).
- So ngưỡng → trạng thái ngành (thuận/trung tính/nghịch).
- Ánh xạ chỉ báo → driver mô hình (cột `mapped_driver`) → cung cấp Δdriver cho Daily Signal Engine.

### D.6 Consensus Tracker (mới, từ prompt 8 & 12)
- Thu thập giá mục tiêu/khuyến nghị CTCK (scrape báo cáo/tổng hợp công khai).
- So fair value của bạn vs consensus → cờ "đồng thuận / lệch pha" (luận điểm khác thị trường = cơ hội hoặc rủi ro).

### D.7 Point-in-time & Track record
Mỗi ngày snapshot `daily_signal`; mỗi BCTC lưu `published_at`. Sau 6–12 tháng có dữ liệu để backtest **không bias**: dùng dữ liệu as-of từng ngày, đo hit-rate fair value theo ngành.

### D.8 Đầu ra
- **Google Sheets:** dashboard master (xếp hạng conviction hằng ngày) + tab chi tiết mỗi mã (model 2 chiều theo skill `google-sheets-two-way`).
- **Discord bản tin EOD** (gu như pptx mẫu của bạn: tóm tắt điều hành + chỉ số then chốt + ngưỡng cảnh báo + mã cần chú ý).
- **Drive:** memo PDF tự sinh + snapshot dữ liệu.

---

## PHẦN E — Lộ trình triển khai (đã chỉnh để tận dụng tài sản sẵn có)

**Giai đoạn 0 — Hạ tầng + nạp data bank sẵn có.** Postgres + schema (gồm bảng mới D.1); **nạp thẳng `data bank` Excel** (MaCK/BCTC/Giá) vào DB; FastAPI skeleton; kết nối Google/Discord. *Mốc: dữ liệu ngân hàng đã có trong DB, /health 200.*

**Giai đoạn 1 — Máy hóa model VCB làm golden reference.** Dựng `quality/bank_metrics.py` (từ dashboard VCB) + driver forecast ngân hàng + RI + P/B + blend, **đối chiếu khớp file Excel VCB** (sai số nhỏ). Tính & lưu greeks cho VCB. *Mốc: `/revalue VCB` ra ~khớp Excel; có bảng sensitivity.*

**Giai đoạn 2 — Mở rộng định giá theo ngành + sensitivity.** Các model còn lại (DCF, multiples, DDM, RNAV, SOTP, mid-cycle) theo driver tree; mỗi model có greeks. Pilot phủ ngành: VCB, FPT, VHM, HPG, VNM, **SSI, GAS, MSN**. *Mốc: 8 pilot ra fair value band + greeks, unit test tính tay pass.*

**Giai đoạn 3 — Macro Radar Service + `macro_radar.yaml`.** Ingest chỉ báo theo tần suất, ánh xạ chỉ báo→driver. *Mốc: radar ngành ngân hàng & thép chạy, có Δdriver hằng ngày.*

**Giai đoạn 4 — DAILY SIGNAL ENGINE (trái tim của bản v2).** Fast re-price bằng greeks, conviction score, cờ stale, bảng xếp hạng, bản tin Discord EOD. *Mốc: chạy EOD cho pilot, Discord nhận bản tin, Sheet cập nhật, `daily_signal` ghi point-in-time.*

**Giai đoạn 5 — Google Sheets 2 chiều + Consensus + Memo PDF.** *Mốc: sửa giả định→giá đổi; consensus so sánh; memo PDF lên Drive.*

**Giai đoạn 6 — Scale toàn VN100 + n8n tự động hóa.** Backfill 100 mã (checkpoint/retry); WF EOD daily, WF filing, WF manual, WF recompute, WF macro. *Mốc: toàn VN100 có daily signal tự động + cảnh báo sự kiện.*

**Giai đoạn 7 — Backtest track record.** Sau khi tích đủ snapshot, đo hit-rate point-in-time theo ngành, hiệu chỉnh trọng số blend & conviction.

---

## PHẦN F — Cái gì chạy hằng ngày vs theo quý (rõ ràng)
| Tần suất | Chạy gì |
|---|---|
| **Mỗi ngày (EOD)** | Cập nhật giá → upside/MoS; Macro Radar (chỉ báo ngày); fast re-price (greeks); conviction; bản tin Discord; snapshot `daily_signal` |
| **Hằng tuần/tháng** | Macro Radar (chỉ báo tuần/tháng); cập nhật consensus |
| **Theo quý / sự kiện** | Nhịp chậm: ingest BCTC mới → QC → driver forecast → định giá đầy đủ → tính lại greeks; hoặc khi bạn sửa giả định / khi cờ "stale" bật |

---

## PHẦN G — Guardrail & sửa lỗi (giữ từ rà soát trước, bắt buộc)
1. **Ngân hàng/CK/bảo hiểm: KHÔNG dùng Altman Z / Beneish M / Piotroski F.** Dùng bộ riêng (đã có từ dashboard VCB): CAR, NPL, NPL coverage, LDR, credit cost, CIR.
2. **WACC không đếm rủi ro quốc gia 2 lần:** nếu `Rf = TPCP VN` thì KHÔNG cộng thêm country risk premium vào ERP. Chốt 1 quy ước, ghi rõ trong config.
3. **Dự phóng phải driver-based**, không tăng trưởng cơ học (theo chính prompt của bạn).
4. **Ingest VN-Index** (cho beta) + **published_at** cho mọi BCTC (point-in-time).
5. **Validator mọi output:** chặn `g ≥ WACC`, giá ≤ 0, chia 0, upside ngoài biên → cờ "cần review".
6. **QC gate:** Tổng tài sản = Nợ + VCSH trước khi nhận BCTC.
7. **Greeks là xấp xỉ bậc nhất** — chỉ dùng cho dịch chuyển nhỏ/trung bình; khi vượt ngưỡng phải chạy lại nhịp chậm (không tin tuyến tính khi driver nhảy mạnh).
8. **Idempotent, checkpoint, retry, không commit secret** (theo AGENTS.md).
