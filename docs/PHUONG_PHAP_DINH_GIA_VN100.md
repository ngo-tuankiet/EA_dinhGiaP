# Phương pháp định giá hiện tại — VN100

> **Nguồn dữ liệu:** trích xuất trực tiếp từ `valuation/config/routing.json` và
> logic runtime thực tế trong `valuation/engine/sector_router.py`,
> `valuation/engine/models/dcf.py`, `valuation/engine/models/bank_general.py`
> của hệ thống antigravity-vn100 tại thời điểm xuất báo cáo.
> **Không có số liệu suy đoán/bịa** — mọi giá trị trong bảng đều đọc thẳng từ
> cấu hình và mã nguồn đang chạy.

**Ngày xuất báo cáo:** 2026-07-02
**Tổng số mã trong hệ thống:** 101 (không tính VNINDEX — là chỉ số, không phải cổ phiếu)

---

## 1. Tổng quan phương pháp đang dùng

| Phương pháp | Số mã | Mô tả | Trạng thái triển khai |
|---|---|---|---|
| **RI_PB** | 17 | Thu nhập thặng dư (Residual Income) + So sánh P/B | ✅ Đầy đủ (không proxy) |
| **DCF** | 30 | DCF/FCFF + So sánh EV/EBITDA | ✅ Đầy đủ (không proxy) |
| **PE** | 6 | So sánh P/E (EPS chuẩn hóa trung vị 3 năm) | ✅ Đầy đủ (không proxy) |
| **PB** | 10 | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) |
| **EV_EBITDA** | 6 | So sánh EV/EBITDA (EBITDA chuẩn hóa bình quân 3 năm) | ✅ Đầy đủ (không proxy) |
| **RNAV** | 14 | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) |
| **SOTP** | 17 | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) |
| *(không có cấu hình)* | 1 | Mã chưa được thêm vào routing.json | ❌ |

**Đã đối chiếu với báo cáo CTCK thật (verified=true):** 13/101 mã.

---

## 2. Cách đọc bảng & lưu ý quan trọng

- **RI_PB (Ngân hàng):** blend Residual Income + P/B theo đúng trọng số ghi trong
  `routing.json` (trọng số này lấy từ đối chiếu báo cáo định giá thật của SSI/Vietcap/HSC).
- **DCF (phi tài chính):** hệ thống LUÔN blend cố định 50% DCF/FCFF + 50% so sánh
  EV/EBITDA ngay trong code (`valuation/engine/models/dcf.py`), **không đổi theo
  cấu hình** dù `routing.json` có ghi trọng số/phương pháp phụ khác.
- **PE / PB / EV_EBITDA / RNAV / SOTP:** hệ thống chạy **đúng 1 phương pháp duy nhất**
  cho các mã này — không blend thêm phương pháp phụ nào khác, bất kể `routing.json`
  có ghi phương pháp tham khảo phụ (secondary) hay không.
- **⚠️ Proxy (RNAV/SOTP):** ước lượng từ giá trị sổ sách (không phải mô hình định giá
  dự án/mảng kinh doanh chi tiết như CTCK chuyên nghiệp). Kết quả gắn cờ
  `VALUATION_PROXY` — độ tin cậy thấp hơn nhóm IMPLEMENTED.
- **Cột "Đối chiếu CTCK":** "✔️ Có" nghĩa là phương pháp/trọng số đã được kiểm tra khớp
  với báo cáo định giá thật của công ty chứng khoán; "Chưa" là chưa đối chiếu
  (không có nghĩa là sai, chỉ là chưa xác minh chéo).

---

## 3. Bảng chi tiết theo từng mã (101 mã, sắp xếp theo mã CK)

| STT | Mã CK | Tên công ty | Ngành | Phương pháp áp dụng | Trạng thái | Đối chiếu CTCK |
|---|---|---|---|---|---|---|
| 1 | **ACB** | Ngân hàng Thương mại Cổ phần Á Châu | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 2 | **AGG** | Công ty Cổ phần Đầu tư và Phát triển Bất động sản An Gia | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 3 | **ANV** | Công ty Cổ phần Nam Việt | Dệt may/TS | So sánh P/E (EPS chuẩn hóa trung vị 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 4 | **BCM** | Tập đoàn Đầu tư và Phát triển Công nghiệp Becamex - CTCP | KCN (Khu công nghiệp) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | ✔️ Có |
| 5 | **BID** | Ngân hàng Thương mại Cổ phần Đầu tư và Phát triển Việt Nam | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 6 | **BMI** | Tổng Công ty Cổ phần Bảo Minh | BH (Bảo hiểm) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 7 | **BMP** | Công ty Cổ phần Nhựa Bình Minh | Thép | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 8 | **BSI** | Công ty Cổ phần Chứng khoán BIDV | CK (Chứng khoán) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 9 | **BSR** | Công ty Cổ phần - Tổng Công ty Lọc Hoá dầu Việt Nam | Dầu khí | So sánh EV/EBITDA (EBITDA chuẩn hóa bình quân 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 10 | **BVH** | Tập đoàn Bảo Việt | BH (Bảo hiểm) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 11 | **CMG** | Công ty Cổ phần Tập đoàn Công nghệ CMC | Công nghệ | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 12 | **CTD** | Công ty Cổ phần Xây dựng Coteccons | Xây dựng | So sánh P/E (EPS chuẩn hóa trung vị 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 13 | **CTG** | Ngân hàng Thương mại Cổ phần Công thương Việt Nam | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 14 | **CTR** | Tổng Công ty Cổ phần Công trình Viettel | Công nghệ | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 15 | **DBD** | Công ty Cổ phần Dược - Trang thiết bị y tế Bình Định (BIDIPHAR) | Dược | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 16 | **DCM** | Công ty Cổ phần - Tổng Công ty Phân bón Dầu Khí Cà Mau | Hóa chất | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 17 | **DGC** | Hoá chất Đức Giang | Hóa chất | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 18 | **DGW** | Công ty Cổ phần Thế Giới Số | Bán lẻ | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 19 | **DHG** | Công ty Cổ phần Dược Hậu Giang | Dược | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 20 | **DIG** | Tổng Công ty Cổ phần Đầu tư Phát triển Xây dựng | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 21 | **DPM** | Tổng Công ty Phân bón và Hóa chất Dầu khí - Công ty Cổ phần | Hóa chất | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 22 | **DPR** | Công ty Cổ phần Cao su Đồng Phú | Cao su/NN | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 23 | **DXG** | Công ty Cổ phần Bluemarq Group | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 24 | **EIB** | Ngân hàng Thương mại Cổ phần Xuất nhập khẩu Việt Nam | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 25 | **FPT** | FPT Corporation | Công nghệ | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | ✔️ Có |
| 26 | **FRT** | Công ty Cổ phần Bán lẻ Kỹ thuật số FPT | Bán lẻ | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 27 | **FTS** | Công ty Cổ phần Chứng khoán FPT | CK (Chứng khoán) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 28 | **GAS** | Tổng Công ty Khí Việt Nam - Công ty Cổ phần | Dầu khí | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 29 | **GEG** | Công ty Cổ phần Điện Gia Lai | Điện | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 30 | **GEX** | Công ty Cổ phần Tập đoàn Gelex | Điện | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 31 | **GIL** | Công ty Cổ phần Sản xuất Kinh doanh Xuất nhập khẩu Bình Thạnh | Dệt may/TS | So sánh P/E (EPS chuẩn hóa trung vị 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 32 | **GMD** | Công ty Cổ phần Tập đoàn Gemadept | Cảng | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 33 | **GVR** | Tập đoàn Công nghiệp Cao su Việt Nam - Công ty Cổ phần | Cao su/NN | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | ✔️ Có |
| 34 | **HAG** | Công ty Cổ phần Hoàng Anh Gia Lai | Cao su/NN | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 35 | **HAH** | Công ty Cổ phần Vận tải và Xếp dỡ Hải An | Cảng | So sánh EV/EBITDA (EBITDA chuẩn hóa bình quân 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 36 | **HCM** | Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh | CK (Chứng khoán) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 37 | **HDB** | Ngân hàng Thương mại Cổ phần Phát Triển Thành phố Hồ Chí Minh | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 38 | **HDC** | Công ty Cổ phần Phát triển Nhà Bà Rịa Vũng Tàu | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 39 | **HDG** | Công ty Cổ phần Tập đoàn Hà Đô | Điện | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 40 | **HHV** | Công ty Cổ phần Đầu tư Hạ tầng Giao thông Đèo Cả | Xây dựng | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 41 | **HPG** | Hoa Phat Group | Thép | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | ✔️ Có |
| 42 | **HSG** | Công ty Cổ phần Tập đoàn Hoa Sen | Thép | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 43 | **HT1** | Công ty Cổ phần Xi măng VICEM Hà Tiên | Thép | So sánh EV/EBITDA (EBITDA chuẩn hóa bình quân 3 năm) | ✅ Đầy đủ (không proxy) | ✔️ Có |
| 44 | **HVN** | Tổng Công ty Hàng không Việt Nam - CTCP | Hàng không | So sánh EV/EBITDA (EBITDA chuẩn hóa bình quân 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 45 | **IMP** | Công ty Cổ phần Dược phẩm Imexpharm | Dược | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 46 | **KBC** | Tổng Công ty Phát triển Đô thị Kinh Bắc - CTCP | KCN (Khu công nghiệp) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 47 | **KDC** | Công ty Cổ phần Tập đoàn KIDO | Tiêu dùng | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 48 | **KDH** | Công ty Cổ phần Đầu tư và Kinh doanh nhà Khang Điền | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 49 | **LPB** | Ngân hàng Thương mại Cổ phần Lộc Phát Việt Nam | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 50 | **MBB** | Ngân hàng Thương mại Cổ phần Quân đội | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 51 | **MCH** | Công ty Cổ phần Hàng Tiêu Dùng MaSan | Tiêu dùng | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 52 | **MIG** | Tổng Công ty Cổ phần Bảo hiểm Quân đội | BH (Bảo hiểm) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 53 | **MSB** | Ngân hàng Thương mại Cổ phần Hàng Hải Việt Nam | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 54 | **MSH** | Công ty Cổ phần May Sông Hồng | Dệt may/TS | So sánh P/E (EPS chuẩn hóa trung vị 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 55 | **MSN** | Công ty Cổ phần Tập đoàn Masan | Đa ngành | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | ✔️ Có |
| 56 | **MWG** | Công ty Cổ phần Đầu tư Thế Giới Di Động | Bán lẻ | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | ✔️ Có |
| 57 | **NAB** | Ngân hàng Thương mại Cổ phần Nam Á | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 58 | **NKG** | Công ty Cổ phần Thép Nam Kim | Thép | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 59 | **NLG** | Công ty Cổ phần Đầu tư Nam Long | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 60 | **NT2** | Công ty Cổ phần Điện lực Dầu khí Nhơn Trạch 2 | Điện | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 61 | **NTL** | Công ty Cổ phần Phát triển Đô thị Từ Liêm | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 62 | **NVL** | Công ty Cổ phần Tập đoàn Đầu tư Địa ốc No Va | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 63 | **OCB** | Ngân hàng Thương mại Cổ phần Phương Đông | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 64 | **PC1** | Công ty Cổ phần Tập đoàn PC1 | Điện | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 65 | **PDR** | Công ty Cổ phần Phát triển Bất động sản Phát Đạt | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 66 | **PHR** | Công ty Cổ phần Cao su Phước Hòa | Cao su/NN | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 67 | **PLX** | Tập đoàn Xăng dầu Việt Nam | Dầu khí | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 68 | **PNJ** | Công ty Cổ phần Vàng bạc Đá quý Phú Nhuận | Bán lẻ | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 69 | **POW** | Tổng Công ty Điện lực Dầu khí Việt Nam - CTCP | Điện | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 70 | **PVD** | Tổng Công ty Cổ phần Khoan và Dịch vụ khoan Dầu khí | Dầu khí | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | ✔️ Có |
| 71 | **PVT** | Tổng Công ty Cổ phần Vận tải Dầu khí | Dầu khí | So sánh EV/EBITDA (EBITDA chuẩn hóa bình quân 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 72 | **REE** | Công ty Cổ phần Cơ điện Lạnh | Đa ngành | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 73 | **SAB** | Tổng Công ty Cổ phần Bia - Rượu - Nước Giải khát Sài Gòn | Tiêu dùng | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 74 | **SBT** | Công ty Cổ phần Thành Thành Công - Biên Hòa | Tiêu dùng | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 75 | **SHB** | Ngân hàng Thương mại Cổ phần Sài Gòn – Hà Nội | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 76 | **SIP** | Công ty Cổ phần Đầu tư Sài Gòn VRG | KCN (Khu công nghiệp) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 77 | **SSB** | Ngân hàng Thương mại Cổ phần Đông Nam Á | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 78 | **SSI** | Công ty Cổ phần Chứng khoán SSI | CK (Chứng khoán) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 79 | **STB** | Ngân hàng Thương mại Cổ phần Sài Gòn Tài Lộc | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 80 | **STK** | Công ty Cổ phần Sợi Thế Kỷ | Dệt may/TS | So sánh P/E (EPS chuẩn hóa trung vị 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 81 | **SZC** | Công ty Cổ phần Sonadezi Châu Đức | KCN (Khu công nghiệp) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 82 | **TCB** | Ngân hàng Thương mại Cổ phần Kỹ thương Việt Nam | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | ✔️ Có |
| 83 | **TCH** | Công ty Cổ phần Đầu tư Dịch vụ Tài chính Hoàng Huy | Đa ngành | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 84 | **TNH** | Công ty Cổ phần Tập đoàn Bệnh viện TNH | Dược | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 85 | **TPB** | Ngân hàng Thương mại Cổ phần Tiên Phong | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 86 | **VCB** | Vietcombank | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | ✔️ Có |
| 87 | **VCG** | Tổng Công ty Cổ phần Xuất nhập khẩu và Xây dựng Việt Nam | Xây dựng | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 88 | **VCI** | Công ty Cổ phần Chứng khoán Vietcap | CK (Chứng khoán) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 89 | **VGC** | Tổng Công ty Viglacera - Công ty Cổ phần | KCN (Khu công nghiệp) | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | Chưa |
| 90 | **VHC** | Công ty Cổ phần Vĩnh Hoàn | Dệt may/TS | So sánh P/E (EPS chuẩn hóa trung vị 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 91 | **VHM** | Công ty Cổ phần Vinhomes | BĐS (Bất động sản) | RNAV — Revalued Net Asset Value (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | ✔️ Có |
| 92 | **VIB** | Ngân hàng Thương mại Cổ phần Quốc tế Việt Nam | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 93 | **VIC** | Tập đoàn Vingroup - Công ty CP | Đa ngành | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | ✔️ Có |
| 94 | **VIX** | Công ty Cổ phần Chứng khoán VIX | CK (Chứng khoán) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 95 | **VJC** | Công ty Cổ phần Hàng không Vietjet | Hàng không | So sánh EV/EBITDA (EBITDA chuẩn hóa bình quân 3 năm) | ✅ Đầy đủ (không proxy) | Chưa |
| 96 | **VND** | Công ty Cổ phần Chứng khoán VNDIRECT | CK (Chứng khoán) | So sánh P/B (Justified P/B theo ROE) | ✅ Đầy đủ (không proxy) | Chưa |
| 97 | **VNM** | Công ty Cổ phần Sữa Việt Nam | Tiêu dùng | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 98 | **VPB** | Ngân hàng Thương mại Cổ phần Việt Nam Thịnh Vượng | NH (Ngân hàng) | Thu nhập thặng dư (Residual Income) + So sánh P/B — blend 50% RI + 50% P/B (trọng số theo báo cáo CTCK đối chiếu) | ✅ Đầy đủ (không proxy) | Chưa |
| 99 | **VRE** | Công ty Cổ phần Vincom Retail | BĐS (Bất động sản) | SOTP — Sum-of-the-Parts (proxy) | ⚠️ Proxy (ước lượng từ giá trị sổ sách, gắn cờ VALUATION_PROXY) | ✔️ Có |
| 100 | **VSC** | Công ty Cổ phần Container Việt Nam | Cảng | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |
| 101 | **VTP** | Tổng Công ty Cổ phần Bưu chính Viettel | Công nghệ | DCF/FCFF + So sánh EV/EBITDA — blend cố định 50% DCF + 50% EV/EBITDA (code, không đổi theo cấu hình) | ✅ Đầy đủ (không proxy) | Chưa |

---

## 4. Mã thiếu cấu hình định tuyến

Không còn mã VN100 nào thiếu cấu hình định tuyến trong `valuation/config/routing.json`.

---

*File này được sinh tự động bằng script đọc trực tiếp cấu hình và mã nguồn hệ thống —
không có giá trị nào được nhập tay hoặc suy đoán.*
