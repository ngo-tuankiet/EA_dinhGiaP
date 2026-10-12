---
name: valuation-models
description: Khi build hoặc sửa bất kỳ phần định giá nào (DCF, multiples, DDM, residual income, RNAV, SOTP, WACC) hoặc khi chọn model cho một mã/ngành, dùng skill này để chọn đúng model theo ngành và áp đúng công thức, tránh các lỗi định giá kinh điển.
---

# Skill: Định giá theo ngành (VN100)

## Nguyên tắc
- Mỗi mã được map vào một **nhóm ngành** (cột `sector` trong bảng `tickers`); mỗi nhóm có bộ model riêng. KHÔNG dùng một model cho mọi mã.
- Kết quả cuối = blend có trọng số giữa **định giá tuyệt đối** (DCF/DDM/RI) và **tương đối** (multiples). Trọng số cấu hình được, không hardcode.
- Mỗi mã ra 3 kịch bản: bull / base / bear.

## Bảng map ngành → model
| Nhóm ngành | Model chính | Model phụ | CẤM dùng |
|---|---|---|---|
| Ngân hàng | Residual Income / Justified P/B theo ROE | DDM | EV/EBITDA, FCFF |
| Chứng khoán | P/B × ROE | P/E | EV/EBITDA |
| Bảo hiểm | P/B + Embedded Value | DDM | EV/EBITDA |
| Bất động sản (chủ đầu tư) | RNAV/NAV theo dự án | P/B | P/E thuần (LN dồn cục theo bàn giao) |
| Thép / vật liệu (cyclical) | DCF với earnings **mid-cycle chuẩn hóa** | EV/EBITDA | P/E ở đỉnh/đáy chu kỳ |
| Tiện ích/điện/nước | DDM | FCFF DCF | — |
| Bán lẻ / F&B / tiêu dùng | FCFF DCF | EV/EBITDA, P/E | — |
| KCN | RNAV (đất) + DCF | EV/EBITDA | — |
| Holdings/đa ngành | Sum-of-the-Parts (SOTP) | NAV | P/E hợp nhất gộp |
| Phi tài chính (mặc định) | FCFF DCF | EV/EBITDA, P/E | — |

## Luật chống lỗi (đọc kỹ — AI hay sai ở đây)
1. **Ngân hàng/tài chính KHÔNG có FCFF/EV/EBITDA có nghĩa** (nợ là nguyên liệu kinh doanh). Dùng Residual Income, DDM, hoặc justified P/B = (ROE − g)/(r − g).
2. **Công ty lỗ → P/E vô nghĩa.** Không tính P/E khi EPS ≤ 0; chuyển sang P/B, EV/Sales, hoặc DCF.
3. **Cyclical (thép, vận tải, hóa chất): cấm định giá theo earnings năm đỉnh.** Dùng biên lợi nhuận/ROE trung bình qua trọn chu kỳ (mid-cycle), nếu không sẽ định giá đỉnh thành "rẻ".
4. **Terminal value:** `g` (tăng trưởng vĩnh viễn) phải ≤ tăng trưởng GDP danh nghĩa dài hạn của VN. Cấm `g ≥ WACC` (ra giá vô cực/âm). Validate điều kiện này trong code.
5. **WACC cho VN:**
   - `Re = Rf + β × ERP_VN`. `Rf` = lợi suất TPCP 10 năm VN (lấy động, KHÔNG hardcode). `ERP_VN` gồm country risk premium — **CẤM dùng ERP Mỹ (~5%)**.
   - `β` hồi quy giá mã vs VN-Index; cân nhắc unlever/relever theo cấu trúc vốn. Chặn β vô lý (vd <0 hoặc >3 thì cảnh báo).
   - Cost of debt từ chi phí lãi vay thực tế, điều chỉnh thuế: `Kd × (1 − tax)`.
6. **Đơn vị & nhất quán:** target price ra **VND/cổ phiếu**. Kiểm tra số cổ phiếu lưu hành (pha loãng nếu có trái phiếu chuyển đổi/ESOP). EV phải trừ nợ ròng đúng, cộng/trừ lợi ích cổ đông thiểu số khi cần.
7. **Peer multiples:** dùng **median** ngành (không phải mean — tránh outlier). Loại peer lỗ/âm khỏi rổ P/E.
8. **SOTP/RNAV:** định giá từng mảng/dự án riêng rồi cộng, trừ nợ ròng cấp tập đoàn và chiết khấu holding nếu hợp lý.

## Bắt buộc khi code phần định giá
- Mỗi model là một hàm thuần (pure function) nhận giả định + dữ liệu, trả kết quả — dễ test.
- Mỗi model có **unit test với 1 ví dụ tính tay ra đúng** (vd DCF 5 năm với số tròn).
- Validate đầu vào: chặn `g ≥ WACC`, EPS ≤ 0 cho P/E, β vô lý, số cổ phiếu ≤ 0.
- Mọi giả định mặc định (ERP_VN, biên, tăng trưởng) để trong config, không rải trong code.
- Output kèm metadata: model nào, kịch bản nào, version giả định nào.

## Ranking VN100 và danh sách tích sản
- Không chọn mã dài hạn chỉ vì upside cao. Một mã phải qua thêm các lớp: toàn
  vẹn dữ liệu, chất lượng lợi nhuận/dòng tiền, đòn bẩy, thanh khoản, vị thế
  ngành, thương hiệu, rủi ro vĩ mô và mức an toàn định giá.
- Nếu không đủ 5-7 mã đạt chuẩn, báo thiếu mã và nêu lý do từng mã bị loại.
  Chỉ hạ tiêu chuẩn khi người dùng duyệt; khi hạ phải ghi rõ tiêu chuẩn nào bị
  hạ và rủi ro tăng thêm.
- Tách rõ hai khẩu vị: **thận trọng** (an toàn, bền, ít rủi ro dữ liệu) và
  **tăng trưởng** (upside/động lực cao hơn nhưng rủi ro lớn hơn). Không trộn hai
  danh sách vào một kết luận mơ hồ.
- DeepSeek trong ranking chỉ dùng để viết phản biện/lọc cuối cùng trên dữ liệu
  Python đã chấm điểm, không thay thế score engine và không tự tạo số liệu.
