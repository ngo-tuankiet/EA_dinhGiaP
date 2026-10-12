# Chạy hệ thống VN100 từ Google Drive

## Cách mở

1. Mở thư mục dự án trên Google Drive/Google Drive Desktop.
2. Nhấp đúp file `Chay_Dinh_Gia_VN100.command`.
3. Trình duyệt sẽ mở `http://localhost:8502`.

## Dữ liệu portable

- DB đầy đủ để chạy app: `vn100_full.db`.
- DB này được dựng từ `vn100_backup.sql`, sau đó merge thêm dữ liệu mới hơn trong `vn100.db`.
- Launcher ép app đọc:
  - `DATABASE_URL_READONLY=sqlite:///.../vn100_full.db`
  - `DATABASE_URL_WRITE=sqlite:///.../vn100_full.db`

Nhờ vậy máy khác không cần PostgreSQL local để xem dữ liệu đã tải.

Mặc định app đọc giá gần nhất từ `vn100_full.db` để ai mở từ Drive cũng chạy
được, kể cả khi chưa đăng nhập vnstock hoặc bị giới hạn API. Nếu muốn bật giá
live, thêm dòng sau vào `.env`:

```bash
ENABLE_LIVE_PRICE=1
```

## Kiểm tra nhanh

Chạy trong thư mục dự án:

```bash
sqlite3 vn100_full.db "select count(*) from tickers where is_vn100=1;"
sqlite3 vn100_full.db "select count(distinct ticker) from financials_quarterly;"
sqlite3 vn100_full.db "select count(distinct ticker) from prices_daily;"
```

Kỳ vọng hiện tại:

- `tickers is_vn100`: 101
- `financials_quarterly`: 102 mã
- `prices_daily`: 102 mã
- routing/valuation output: 101/101 mã VN100
- consensus CTCK: 101/101 mã VN100 có ít nhất 1 dòng truy vết

## Lưu ý chất lượng dữ liệu

- Dữ liệu BCTC trong backup vẫn thiếu `published_at`, nên chưa đạt chuẩn backtest chống lookahead.
- Một số ngành như BĐS/holdings vẫn là `proxy` nếu chưa có cấu hình RNAV/SOTP chi tiết.
- Muốn tải dữ liệu mới từ vnstock/nguồn ngoài thì mỗi máy vẫn cần API key/quyền truy cập phù hợp.
- `vnstock_data` là package proprietary/optional. Thiếu package này thì app vẫn
  đọc dữ liệu đã lưu trong `vn100_full.db`, nhưng cập nhật dòng tiền nâng cao
  có thể dùng fallback rỗng.
