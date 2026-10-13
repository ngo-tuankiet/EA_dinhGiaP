# Chạy app VN100 trên VPS và mở bằng điện thoại

Mục tiêu: mở `https://vn100.<tên-miền>` trên điện thoại, có mật khẩu, app hiển thị gọn ở màn hẹp
(CSS điện thoại trong `valuation/views/assets/workspace.css`, kiểm tra trên Streamlit 1.55.0 — D53).

> **Không gửi link khi chưa làm bước 5 (mật khẩu).** App không có đăng nhập riêng: ai có link đều bấm được
> nút gọi DeepSeek (tốn tiền API), quét dữ liệu vnstock và ghi DB.

## 1. Máy chủ

- Ubuntu 24.04 (có sẵn Python 3.12; dự án cần Python ≥ 3.11), 2 GB RAM trở lên.
- Một tên miền trỏ bản ghi A về IP của VPS (để có HTTPS; điện thoại chặn nhiều thứ trên http thường).
- Tạo user thường, không chạy app bằng root:

```bash
sudo adduser vn100
```

## 2. Lấy code và cài thư viện

```bash
sudo -iu vn100
git clone https://github.com/ngo-tuankiet/EA_dinhGiaP.git app
cd app
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

- `requirements.txt` ghim `streamlit==1.55.0`: CSS điện thoại dựa vào tên phần tử nội bộ của bản này. Nâng
  Streamlit thì phải kiểm tra lại giao diện điện thoại.
- `kaleido` (Plotly xuất ảnh biểu đồ cho PDF/Word) cần Chrome. VPS thường chưa có → tải bản riêng cho kaleido:
  `.venv/bin/kaleido_get_chrome` (một lần). Thiếu Chrome thì app vẫn chạy, chỉ PDF/Word không kèm biểu đồ.
- `vnii` / `vnstock_data` là gói tài trợ vnstock. Nếu `pip install` báo không tìm thấy, cài theo hướng dẫn gói
  tài trợ của vnstock rồi chạy lại lệnh trên. App vẫn mở được với dữ liệu có sẵn; chỉ nút cập nhật dữ liệu cần gói này.

## 3. Secret (.env)

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

Điền `DEEPSEEK_API_KEY`, `VNSTOCK_API_KEY` (và các key khác nếu dùng). Đặt DB bằng **đường dẫn tuyệt đối**:

```
DATABASE_URL_READONLY=sqlite:////home/vn100/app/vn100_full.db
DATABASE_URL_WRITE=sqlite:////home/vn100/app/vn100_full.db
```

Không commit `.env` (đã nằm trong `.gitignore`). Nên đặt hạn mức chi tiêu thấp trên tài khoản DeepSeek.

## 4. Dữ liệu — giải nén TRƯỚC khi chạy app lần đầu

```bash
.venv/bin/python scripts/ensure_portable_db.py
```

App cũng tự giải nén khi khởi động nếu chưa có `vn100_full.db` (D53). Bản code cũ hơn thì không: lỡ chạy app
trước sẽ tạo `vn100_full.db` rỗng và script tưởng đã có DB. Cách sửa: dừng app, `rm vn100_full.db`, chạy lại lệnh trên.

## 5. Chạy nền bằng systemd (tự bật lại khi VPS khởi động lại)

Không dùng `scripts/run_app.sh` trên VPS (script đó dành cho máy Mac). Tạo `/etc/systemd/system/vn100.service`:

```ini
[Unit]
Description=VN100 Streamlit
After=network.target

[Service]
User=vn100
WorkingDirectory=/home/vn100/app
ExecStartPre=/home/vn100/app/.venv/bin/python scripts/ensure_portable_db.py
ExecStart=/home/vn100/app/.venv/bin/python -m streamlit run streamlit_app.py
Environment=STREAMLIT_SERVER_ADDRESS=127.0.0.1
Environment=STREAMLIT_SERVER_PORT=8502
Environment=STREAMLIT_SERVER_HEADLESS=true
Environment=STREAMLIT_SERVER_DISCONNECTED_SESSION_TTL=1800
Environment=STREAMLIT_CLIENT_SHOW_ERROR_DETAILS=none
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

- `ADDRESS=127.0.0.1`: Streamlit chỉ nghe trong máy, ra ngoài phải đi qua Caddy (có mật khẩu). Biến môi trường
  ghi đè `address = "0.0.0.0"` trong `.streamlit/config.toml` (file đó giữ nguyên cho máy Mac).
- `DISCONNECTED_SESSION_TTL=1800`: điện thoại khóa màn hình tới 30 phút vẫn giữ giả định đang chỉnh.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vn100
sudo systemctl status vn100
```

## 6. HTTPS + mật khẩu bằng Caddy

```bash
sudo apt install -y caddy
caddy hash-password
```

Nhập mật khẩu, copy chuỗi hash. Sửa `/etc/caddy/Caddyfile`:

```
vn100.<tên-miền> {
    basic_auth {
        phi <chuỗi-hash-vừa-tạo>
    }
    reverse_proxy 127.0.0.1:8502
}
```

```bash
sudo systemctl reload caddy
```

Caddy tự lấy chứng chỉ HTTPS và tự chuyển tiếp websocket (Streamlit cần websocket).

Nếu dùng nginx thay Caddy, bắt buộc có trong `location /`: `proxy_http_version 1.1;`,
`proxy_set_header Upgrade $http_upgrade;`, `proxy_set_header Connection "upgrade";`,
`proxy_read_timeout 86400;` — thiếu các dòng này điện thoại sẽ treo ở "Connecting…".

## 7. Tường lửa

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Không mở cổng 8502/8506 ra ngoài.

## 8. Kiểm tra trên điện thoại

Mở `https://vn100.<tên-miền>`, nhập user `phi` + mật khẩu. Đúng khi:
- Góc trên trái có nút **« Chọn mã · Vĩ mô »** — bấm vào mở chọn mã, hồ sơ doanh nghiệp, tổng quan thị trường.
- 5 tab hiện đủ (xếp nhiều hàng), không phải kéo ngang cả trang.
- Vuốt trên biểu đồ thì trang cuộn (trên màn cảm ứng biểu đồ là ảnh tĩnh, không có tooltip — cố ý).
- Bảng xếp hạng/CTCK kéo ngang được, cột Mã/CTCK đứng yên.

## 9. Cập nhật code sau này

```bash
cd /home/vn100/app
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart vn100
```

Lịch "Quét VN100" hàng tuần chỉ nên chạy ở **một** nơi (Mac hoặc VPS) — chạy cả hai thì tốn phí API gấp đôi và
hai DB lệch nhau.
