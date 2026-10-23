# Mô hình tổng hợp CTCK (BROKER_SYNTH)

> Code: `valuation/engine/models/broker_synth.py`. Test tính tay: `tests/test_broker_synth.py`.
> Config mẫu (fixture, KHÔNG phải mã thật): `tests/fixtures/broker_synth/XYZ.yaml`.
> Tham số: `config/defaults.yaml` → khóa `broker_synth` và `valuation_review`.

## Khi nào dùng

Chỉ dùng cho mã mà mô hình định giá riêng của hệ thống (DCF/RNAV/SOTP/PE/PB/EV_EBITDA...)
**chưa công bố được vì lý do dữ liệu/mô hình** (proxy lệch phi lý, vốn chủ/chân âm, CIP lấn át,
hai chân định giá vênh nhau, hold sự kiện trọng yếu...) — xem `broker_synth.trigger_flag_prefixes`
trong `config/defaults.yaml` — hoặc khi file cấu hình của mã ghi `use_broker_synth: true`.

Mã đang công bố bình thường bằng mô hình riêng **không** bị thay. Đây là điểm tựa khi hệ thống
bó tay, không phải đường tắt để bỏ qua mô hình riêng.

Khi được dùng, giá trị công bố là **trung vị có trọng số độ mới** của giá trị/cp tính lại từ các
báo cáo CTCK, theo đúng phương pháp mà CTCK đó dùng (không lấy thẳng giá mục tiêu CTCK in trong
báo cáo — xem "Vì sao không lấy thẳng giá mục tiêu" ở dưới). FV của mô hình riêng (nếu có) vẫn
được giữ lại trong `own_model_fv`/`own_model_flags` để so sánh, không bị xoá.

## Vì sao không lấy thẳng giá mục tiêu CTCK

Giá mục tiêu CTCK in trong báo cáo đã cố định tại một số cổ phiếu (SỐ CP CTCK DÙNG lúc viết báo
cáo) và một ngày cụ thể (ngày định giá hoặc 12 tháng tới). Nếu công ty có phát hành thêm/mua lại/
cổ phiếu thưởng sau ngày báo cáo, lấy thẳng giá mục tiêu rồi áp lên số cổ phiếu hiện tại dễ bị
**điều chỉnh quyền hai lần** (giá CTCK đã in có thể đã được broker tự điều chỉnh theo kế hoạch
phát hành, hoặc chưa — không biết chắc nếu chỉ nhìn con số cuối). Thay vào đó, pipeline:

1. Tính lại **giá trị vốn chủ tuyệt đối** (tỷ đồng) từ các cấu phần/bội số mà CTCK công bố, bằng
   đúng công thức chuẩn của phương pháp đó (§ "Công thức theo phương pháp").
2. Cộng/trừ các sự kiện vốn xảy ra **sau ngày báo cáo** (`capital_events_after_report`): + tiền
   thu phát hành, − cổ tức tiền đã trả.
3. Chia cho **số cổ phiếu hiện tại** (`company.shares_outstanding`, lấy từ DB — không phải số
   CTCK dùng lúc viết báo cáo).
4. Nếu báo cáo là giá mục tiêu **12 tháng tới** (`horizon: 12m_forward`), chiết giá trị đó về hôm
   nay bằng chi phí vốn chủ sở hữu (COE) của mã — xem Damodaran, *target price ≠ fair value hôm
   nay*: `value_hôm_nay = value_12m / (1 + COE)`. Tham số
   `broker_synth.discount_forward_to_today: true` (mặc định) bật bước này.

Việc tính lại cũng cho phép **kiểm nhất quán**: lấy giá trị vốn chủ tính lại chia cho đúng số cổ
phiếu mà CTCK đã dùng (`shares_used_mn`) phải ra xấp xỉ giá mục tiêu CTCK in trong báo cáo. Lệch
quá `broker_synth.recon_tolerance` (mặc định 10%) → cờ `BROKER_SYNTH_RECON_GAP:<broker>`, nghĩa là
số liệu trích từ báo cáo (cấu phần, bội số, dự phóng...) có thể bị ghi sai và cần đối chiếu lại
file PDF nguồn.

## Công thức theo phương pháp (khớp CFA/Damodaran)

Ký hiệu: `Σcomponents` = tổng giá trị các cấu phần (tỷ đồng, EV của từng mảng/dự án); `net_debt` =
nợ ròng; `minority` = lợi ích CĐTS; `other` = điều chỉnh khác (vd tiền mặt thừa, tài sản không hoạt
động); `discount` = chiết khấu holding/thanh khoản (%).

- **RNAV / SOTP** (`method: RNAV` hoặc `SOTP`):
  `equity = (Σcomponents − net_debt − minority + other) × (1 − discount%)`.
  Nếu CTCK công bố thẳng vốn chủ hợp lý mà không chẻ cấu phần, dùng `equity_value_bn` thay cho
  `components`.
- **DCF** (`method: DCF`): giống RNAV/SOTP — `components` ở đây là EV (giá trị hiện tại dòng tiền
  + giá trị cuối kỳ), trừ nợ ròng/CĐTS cộng điều chỉnh, rồi chiết khấu nếu CTCK có áp.
- **PE** (`method: PE`): `equity = target_multiple × NPAT_FY+1` (lấy `forecast.npat_bn`; nếu CTCK
  chỉ cho EPS thì `equity = target_multiple × forecast.eps × shares_used_mn / 1000`).
- **PB** (`method: PB`): tương tự PE nhưng trên vốn chủ sổ sách (`forecast.equity_bn` hoặc
  `forecast.bvps`).
- **EV/EBITDA** (`method: EV_EBITDA`): `equity = target_multiple × EBITDA_FY+1 − net_debt −
  minority + other` (EV/EBITDA ra EV, phải cầu nối về vốn chủ — KHÔNG dùng trực tiếp cho ngân
  hàng/bảo hiểm, xem skill `valuation-models`).
- **BLEND** (`method: BLEND`): báo cáo CTCK tự trộn nhiều phương pháp. `legs[]` là danh sách các
  chân (mỗi chân có cấu trúc như trên), `weight` mỗi chân, tổng `weight` phải = 1 (sai → lỗi, không
  tự chuẩn hoá âm thầm). `equity = Σ weight_i × equity_leg_i`.

## Tổng hợp nhiều báo cáo

- Bỏ báo cáo cũ hơn `broker_synth.max_report_age_days` (mặc định 365 ngày) hoặc ngày trong tương
  lai (chống lookahead).
- Mỗi báo cáo còn lại có trọng số theo độ mới: `recency_weight(age_days, half_life)` (dùng lại
  `valuation.calibration.consensus_view.recency_weight`, cùng cơ chế với đồng thuận CTCK).
- Giá trị tổng hợp = `weighted_median` (trung vị có trọng số) của giá trị/cp từng báo cáo — chống
  một báo cáo outlier kéo lệch trung bình.
- Không còn báo cáo nào sau khi lọc tuổi → lỗi rõ ràng (không âm thầm trả 0 hay NaN).

## Lược đồ `config/broker_synth/<MÃ>.yaml`

Agent điền file này cho một mã KHÔNG tự viết công thức — chỉ chép lại số liệu CTCK đã công bố
theo đúng cấu trúc dưới, kèm nguồn (file + trang) để truy vết. Không bịa số, không suy diễn số
CTCK không công bố.

```yaml
ticker: FPT                      # Phải khớp tên file <MÃ>.yaml
method_family: RNAV              # Ghi chú phương pháp chủ đạo các CTCK dùng cho mã này (tham khảo)
use_broker_synth: false          # true = LUÔN công bố bằng BROKER_SYNTH dù mô hình riêng chạy được
                                  # (chỉ đặt true khi phi yêu cầu rõ — mặc định false, chỉ bật tự
                                  # động khi mô hình riêng bị cờ lỗi dữ liệu/mô hình chặn)

reports:                         # Mỗi báo cáo CTCK đã đọc = 1 phần tử
  - broker: SSI                  # Tên CTCK (viết tắt quen dùng, khớp config/broker_aliases.yaml)
    date: "2026-06-30"           # Ngày ra báo cáo (ISO, KHÔNG phải ngày tải file)
    file: reports/broker_pdfs/FPT/ssi_20260630.pdf   # Đường dẫn tương đối (thư mục đã gitignore)
    url: ""                      # Hoặc URL nguồn công khai nếu có, để trống nếu chỉ có file
    target_price: 145000         # đồng/cp — giá mục tiêu CTCK in trong báo cáo (để kiểm nhất quán)
    method: RNAV                 # RNAV | SOTP | DCF | PE | PB | EV_EBITDA | BLEND
    weights: null                # Chỉ dùng khi method=BLEND ở cấp "legs" bên dưới, để null ở đây
    horizon: valuation_date       # 'valuation_date' (giá hôm báo cáo) | '12m_forward' (giá mục tiêu 12 tháng)
    components:                   # Bắt buộc với RNAV/SOTP/DCF (bỏ nếu dùng equity_value_bn thẳng)
      - name: Mảng Viễn thông
        value_bn: 12000           # tỷ đồng — giá trị EV cấu phần theo CTCK
        basis: DCF mảng viễn thông
        page: 14                 # Trang trong file PDF — BẮT BUỘC để truy vết
      - name: Mảng Công nghệ
        value_bn: 8000
        basis: P/E mảng so sánh
        page: 16
    equity_value_bn: null         # Dùng khi CTCK chỉ công bố thẳng vốn chủ (không chẻ cấu phần)
    net_debt_bn: 1500             # tỷ đồng, lấy đúng số CTCK dùng (trang nào, ghi trong notes)
    minority_bn: 300
    other_adjustments_bn: 0
    discount_pct: 0               # % chiết khấu holding/thanh khoản CTCK áp (0 nếu không áp)
    shares_used_mn: 785           # triệu cp — SỐ CP CTCK DÙNG để ra giá mục tiêu (không phải số hiện tại)
    forecast:                     # Chỉ cần field tương ứng method (PE/PB/EV_EBITDA)
      eps: null
      bvps: null
      npat_bn: null
      ebitda_bn: null
    target_multiple: null         # Bội số mục tiêu CTCK dùng (PE/PB/EV_EBITDA)
    pages: [14, 16]               # Toàn bộ trang liên quan tới số liệu trích (cho audit nhanh)

  - broker: VCSC
    date: "2026-05-15"
    file: reports/broker_pdfs/FPT/vcsc_20260515.pdf
    target_price: 150000
    method: BLEND
    horizon: 12m_forward
    legs:                         # Chỉ dùng khi method=BLEND; mỗi leg có cấu trúc như 1 báo cáo đơn
      - method: PE
        weight: 0.6
        shares_used_mn: 785
        forecast: {eps: 9500}
        target_multiple: 16
      - method: EV_EBITDA
        weight: 0.4
        shares_used_mn: 785
        forecast: {ebitda_bn: 9000}
        target_multiple: 9
        net_debt_bn: 1500
    pages: [3, 4]

capital_events_after_report:      # Sự kiện vốn xảy ra SAU ngày báo cáo mới nhất tới hôm nay
  - date: "2026-08-01"
    type: rights                  # rights | esop | bonus_shares | cash_dividend | buyback...
    shares_added_mn: 50
    proceeds_bn: 2500             # Tiền thu được (0 nếu là cổ phiếu thưởng không thu tiền)
    cash_dividend_bn: 0           # > 0 nếu là đợt chia cổ tức tiền (trừ khỏi vốn chủ)
    source: "Nghị quyết ĐHCĐ 2026, công bố 2026-07-20"

synthesis:
  weighting: recency_median       # Hiện chỉ hỗ trợ 1 kiểu — ghi rõ cho minh bạch, không đổi code

reviewed_by: ""                   # Tên analyst đã rà soát file config này (KHÔNG phải cổng rà soát
reviewed_on: ""                   # định giá ở config/valuation_reviews.yaml — hai việc khác nhau)
notes: ""                         # Ghi chú tự do: vd lý do loại báo cáo nào, bất thường đã thấy
```

### Quy tắc điền

- **Không chép nguyên văn đoạn văn** từ báo cáo CTCK (bản quyền) — chỉ chép SỐ LIỆU vào các field
  số (`value_bn`, `target_price`, `forecast.*`, `target_multiple`...). `basis`/`notes` tóm tắt bằng
  lời của mình.
- **Mọi số phải có `page`** (hoặc `pages`) để ai đó mở lại PDF kiểm tra được.
- `shares_used_mn` là số cổ phiếu CTCK dùng lúc viết báo cáo — không tự suy ra, lấy đúng số CTCK
  ghi (thường ở phần giả định/phụ lục).
- Không tạo file `config/broker_synth/<MÃ>.yaml` cho mã thật trong lúc viết code/test — chỉ dùng
  fixture ở `tests/fixtures/broker_synth/`. File mã thật do agent đọc báo cáo điền, không phải
  agent viết engine.

## Cổng rà soát (`config/valuation_reviews.yaml`)

File riêng, KHÔNG phải `broker_synth/<MÃ>.yaml` ở trên — ghi quyết định rà soát của analyst (owner
phi) với một kết quả định giá cụ thể, không phải dữ liệu đầu vào.

```yaml
reviews:
  FPT:
    reviewed_by: phi
    reviewed_on: "2026-10-20"      # ISO date — hết hạn sau valuation_review.ttl_days (mặc định 180)
    decision: publish              # publish | block
    basis: own_model                # own_model | broker_synth — PHẢI khớp phương pháp đang công bố
    deviation_vs_consensus: 0.18    # Tham khảo, không bắt buộc logic — ghi lại % lệch lúc rà soát
    reason: "Lệch CTCK do giả định tăng trưởng mảng Viễn thông, đã kiểm tra lại driver"
    stakes_verified: false          # true nếu review xác nhận % sở hữu SOTP đúng (gỡ thêm cờ SOTP_HOLDINGS_UNVERIFIED)
    notes: ""
```

Thiếu bất kỳ field bắt buộc (`reviewed_by`, `reviewed_on`, `decision`, `basis`, `reason`) hoặc giá
trị `decision`/`basis` sai → lỗi rõ ràng (không âm thầm bỏ qua).

### Cờ được review gỡ khi `decision: publish` còn hạn và cùng `basis`

- Luôn gỡ được (không phân biệt basis): các cờ trong `valuation_review.reviewable_flags` —
  `UPSIDE_EXTREME_REVIEW`, `DOWNSIDE_EXTREME_REVIEW`, `MATERIAL_EVENT_HOLD`,
  `VALUATION_LEGS_DIVERGE`, `PROXY_IMPLAUSIBLE`, `NOT_RATED`.
- Chỉ gỡ khi `basis: broker_synth` (`valuation_review.reviewable_if_broker_synth`):
  `VALUATION_PROXY`, `CIP_DOMINATES_VALUE`.
- Chỉ gỡ khi `stakes_verified: true` (`valuation_review.reviewable_if_stakes_verified`):
  `SOTP_HOLDINGS_UNVERIFIED`.
- Cờ gỡ được thì gắn thêm `REVIEWED_PUBLISH:<reason>` (level info, hiển thị *"Đã rà soát:
  <reason>"* trên UI).

### Cờ KHÔNG BAO GIỜ bị review gỡ (lỗi dữ liệu thật)

Mọi cờ có `severity: error` từ `run_deterministic_checks` (vd đẳng thức BS/IS sai, giá cổ phiếu
lỗi thời, xung đột nguồn dữ liệu), cộng `SOURCE_AUDIT_STALE`, `SOTP_SUBSIDIARY_DATA_ERROR`,
`MISSING_FINANCIAL_INPUT`, `AI_INPUTS_UNVERIFIED` — vì đây là lỗi dữ liệu/quy trình, không phải
khác biệt quan điểm định giá. Review không có hiệu lực với các cờ này.

`decision: block` luôn chặn công bố, gắn cờ `REVIEW_BLOCKED:<reason>` (level error), bất kể cờ mô
hình là gì.

## Cờ mới (`valuation/engine/flag_descriptions.py`)

| Cờ | Level | Ý nghĩa |
|---|---|---|
| `BROKER_SYNTHESIZED` | info | Giá trị công bố = Mô hình tổng hợp CTCK, không phải mô hình riêng. |
| `BROKER_SYNTH_RECON_GAP:<broker>` | warning | Tính lại tại số cp CTCK dùng lệch giá mục tiêu CTCK đó > ngưỡng — soát lại số liệu trích. |
| `REVIEWED_PUBLISH:<reason>` | info | Đã rà soát, cho phép công bố — lý do sau dấu `:`. |
| `REVIEW_BLOCKED:<reason>` | error | Rà soát phát hiện lỗi thật, chặn công bố — lý do sau dấu `:`. |

## Kết quả trả về (`valuate_broker_synth`)

```python
{
    "blended_fair_value_per_share": float,   # đồng/cp — trung vị có trọng số độ mới
    "method": "BROKER_SYNTH",
    "method_label": "Mô hình tổng hợp CTCK (n báo cáo: CTCK_A 2026-09-01, ...)",
    "reports": [...],                         # Chi tiết từng báo cáo: equity_value_bn, recon_gap,
                                               # capital_adjustment_bn, fair_value_per_share...
    "cost_of_equity": float,
    "shares_now_mn": float,
    "flags": [...],                           # BROKER_SYNTH_RECON_GAP:<broker> nếu có
}
```

`valuate()` (`valuation/engine/valuate.py`, hàm `_apply_publication_gate`) gói kết quả này vào
cùng cấu trúc output như mọi mô hình khác (`own_model_fv`/`own_model_flags` giữ lại kết quả mô
hình riêng để so sánh) rồi chạy qua cổng công bố `_gate` như thường.
