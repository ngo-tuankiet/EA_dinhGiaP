---
name: financial-data-integrity
description: Khi ingest, chuẩn hóa, lưu hoặc đọc dữ liệu tài chính (BCTC, giá, macro) từ vnstock/filing/GSO/SBV, hoặc khi backfill và backtest, dùng skill này để giữ dữ liệu toàn vẹn và tránh các lỗi dữ liệu khiến định giá sai.
---

# Skill: Toàn vẹn dữ liệu tài chính

## Chuẩn hóa khi ingest (bắt buộc)
1. **Đơn vị tiền:** BCTC VN thường tính bằng VND, hay ghi theo triệu/tỷ tùy nguồn. **Luôn quy về VND tuyệt đối** khi lưu DB; ghi rõ đơn vị gốc trong metadata. Sai đơn vị = định giá lệch 1.000–1.000.000 lần. Validate độ lớn hợp lý.
2. **Hợp nhất vs công ty mẹ:** mặc định dùng **BCTC hợp nhất** cho định giá. Đánh dấu `is_consolidated`. **CẤM trộn** chỉ tiêu hợp nhất với công ty mẹ trong cùng phép tính.
3. **Năm tài chính lệch:** nhiều DN VN không theo năm dương lịch. Lưu đúng `fiscal_year`/`fiscal_quarter` theo niên độ của DN, không ép theo lịch dương.
4. **Restatement (điều chỉnh hồi tố):** khi có bản mới cho cùng kỳ, lưu thành bản mới (`is_restated=true`), GIỮ bản cũ. Dùng bản mới nhất cho dự phóng, nhưng giữ lịch sử để truy vết và backtest.
5. **TTM:** khi cần lợi nhuận 4 quý gần nhất, cộng đúng 4 quý liên tiếp; cẩn thận double-count với báo cáo bán niên/cả năm.

## Kiểm soát chất lượng (chạy TRƯỚC khi định giá)
- Tính & lưu vào `flags`: **Altman Z-score** (chọn đúng biến thể SX/phi SX), **Beneish M-score**, **Piotroski F-score**, accruals ratio, cash conversion (LN ròng / dòng tiền HĐKD).
- Phát hiện bất thường: dòng tiền âm kéo dài, LN tăng nhưng dòng tiền giảm, khoản phải thu phình bất thường → gắn cờ, KHÔNG tự ý "làm mượt".
- Thanh khoản: ADTV 3 tháng dưới ngưỡng → cờ "thanh khoản thấp", vẫn định giá nhưng cảnh báo.
- Khi dùng dữ liệu cho khuyến nghị/tích sản, kiểm tra `data/source_quality_status.json`
  nếu có. Mã có xung đột trọng yếu hoặc thiếu input không được nâng lên danh
  sách tốt chỉ vì upside cao.

## Chống bias (cực kỳ quan trọng cho backfill & backtest)
1. **Lookahead bias:** khi backtest hoặc tính chỉ số tại thời điểm T, chỉ dùng dữ liệu **đã công bố tính đến T**. BCTC quý chỉ "có hiệu lực" sau ngày công bố thực tế, KHÔNG phải ngày kết thúc quý. Lưu `published_at` và lọc theo nó.
2. **Survivorship bias:** rổ VN100 thay đổi theo thời gian. Khi phân tích lịch sử, dùng thành phần rổ **tại thời điểm đó**, đừng áp rổ hiện tại ngược về quá khứ.
3. **Restatement bias:** backtest phải dùng số liệu *as-reported tại thời điểm đó*, không dùng số đã hồi tố sau này.

## Khi mâu thuẫn nguồn (vnstock vs filing)
- Ưu tiên **filing gốc đã kiểm toán** > vnstock > số chưa kiểm toán.
- Nếu lệch đáng kể → gắn cờ và báo, KHÔNG tự chọn im lặng.
- DeepSeek/AI chỉ được ghi nhận nghi vấn dữ liệu; không được tự sửa DB hoặc bịa
  nguồn thay cho filing gốc.

## Luật ghi DB
- Mọi insert/update **idempotent** (dùng UPSERT theo khóa chính). Chạy lại backfill không được nhân đôi dữ liệu.
- Backfill phải có **checkpoint** (lưu mã đã xong) + **retry** + rate-limit, để chạy lại từ mã lỗi mà không làm lại từ đầu.
- Không DELETE dữ liệu lịch sử; muốn sửa thì thêm version mới.
- Mọi bản ghi lưu `source` và `ingested_at`.

## Lỗi đã gặp thực tế (đọc trước khi đụng cashflow)

### CFI/CFF bị trừ CapEx hai lần
- CFI (dòng tiền đầu tư) trong BCTC VN **đã bao gồm sẵn CapEx âm** như một dòng
  con. Model lại lưu CapEx riêng để tính FCFF. Nếu cộng thẳng CFI+CFF vào
  `cf_other` mà không cộng ngược CapEx lại, phép đối chiếu
  `Δcash ≈ cfo - capex + cf_other` (trong `Company.validate_model_integrity`,
  `valuation/models/financials.py`) sẽ **trừ CapEx hai lần** — hoặc tệ hơn, bị
  "vá" bằng cách âm thầm set `cf_other=0.0`.
- Sửa đúng: `_cashflow_other_excluding_capex()`
  (`valuation/data_access/repo.py`) cộng ngược `capex_abs` vào tổng
  CFI+CFF+FX trước khi so khớp. Khi không khớp được taxonomy CFI/CFF, gắn cờ
  `MISSING_FINANCIAL_INPUT:{year}:cfi_cff` — **không** default về 0 rồi im
  lặng bỏ qua.
- Bài học chung: bất kỳ dòng tổng hợp nào (CFI, CFF, "cf_other", "khác") đều có
  khả năng **chồng lấn** với một field đã tách riêng (CapEx, cổ tức, nợ vay).
  Trước khi cộng gộp, luôn kiểm tra dòng tổng có chứa sẵn dòng con đang dùng
  riêng hay không.

## Test bắt buộc
- Test chuẩn hóa đơn vị (tỷ → VND), test UPSERT idempotent (chạy 2 lần, đếm dòng không đổi), test lọc theo `published_at` (không rò dữ liệu tương lai).
