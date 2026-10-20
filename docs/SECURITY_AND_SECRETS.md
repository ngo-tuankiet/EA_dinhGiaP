# Security And Secrets — Antigravity VN100

> File này là checklist bảo mật riêng cho dự án. Nếu mâu thuẫn với yêu cầu tiện
> lợi, chọn bảo mật trước.

## 1. Không bao giờ commit

- `.env`, `*.env`, `.env.*` nếu chứa giá trị thật.
- `VNSTOCK_API_KEY`, `DEEPSEEK_API_KEY`, GitHub PAT, Google token, Discord
  webhook, n8n credential, DB password.
- `*service-account*.json`, `credentials.json`, `token.json`, `*.pem`, `*.key`.
- `vn100_full.db`, `*.db`, `*.sqlite*`, backup SQL, file dump thô.
- `venv/`, `.venv/`, `build/`, `dist/`, `logs/`, `backups/`, `secrets/`.

## 2. Được phép commit

- `.env.example` với giá trị rỗng/mẫu, không có key thật.
- `vn100_full.db.gz` nếu đã kiểm tra không chứa secret và cần để bản portable
  chạy được.
- Tài liệu hướng dẫn khách hàng không chứa mật khẩu/API key.

## 3. Quy tắc `.env`

- Người dùng tự tạo `.env` từ `.env.example`.
- App đọc secret qua biến môi trường hoặc `.env`, không hardcode.
- Nếu người dùng lỡ dán key vào chat hoặc terminal, không đưa key đó vào file
  tracked. Nếu key đã push lên GitHub, phải rotate/revoke key.

## 4. GitHub PAT

- PAT chỉ dùng để xác thực push, không lưu trong repo.
- Không ghi PAT vào remote URL dạng `https://TOKEN@github.com/...`.
- Nếu cần lưu credential, dùng Git Credential Manager/keychain của hệ điều hành.
- Khi user nhập PAT vào terminal, PAT là mật khẩu cho GitHub, không phải một lệnh
  shell độc lập.

## 5. Checklist trước commit

```bash
git status --short
```

Đảm bảo không có file cấm trong danh sách staged/untracked sẽ add.

Quét nhanh từ khóa trên file đã sửa:

```bash
rg -n "API_KEY|SECRET|TOKEN|WEBHOOK|PASSWORD|github_pat_|ghp_|gho_|AIza|BEGIN PRIVATE KEY" .
```

Nếu dùng `rg` toàn repo thấy kết quả trong `.env.example` hoặc docs hướng dẫn
không chứa key thật thì được. Nếu thấy chuỗi secret thật, dừng và xoá/rotate.

## 6. Cách add file an toàn

Không dùng:

```bash
git add .
git add -A
```

Ưu tiên add rõ từng file hoặc thư mục đã kiểm tra:

```bash
git add README.md docs .agents AGENTS.md
git add streamlit_app.py valuation tests config scripts
git add vn100_full.db.gz
```

Sau khi add, chạy:

```bash
git status --short
git diff --cached --name-only
```

## 7. Dữ liệu và báo cáo có bản quyền

- Có thể lưu nội bộ metadata/tóm tắt báo cáo CTCK để phân tích, nhưng không phát
  tán lại nguyên văn báo cáo có bản quyền lên repo public.
- Nếu đưa dữ liệu vào `vn100_full.db.gz`, chỉ dùng dữ liệu được phép chia sẻ
  trong phạm vi bản portable của dự án.

## 8. Kết nối ngoài

- Google API: cấp scope tối thiểu cho Sheets/Drive cần dùng.
- Discord: chỉ dùng webhook gửi thông báo, không dùng bot token nếu không cần.
- DB ghi: tách read-only và write account nếu sau này chuyển sang PostgreSQL.
- Không tự nhập mật khẩu, giải CAPTCHA, tạo tài khoản hoặc vượt rào truy cập.
- Mã chứng khoán từ ngoài (D66): route `/ingest` chỉ nhận `^[A-Z0-9]{3}$` thuộc VN100 ∪ công ty con trong
  `config/sotp_holdings.yaml` (mã lạ → 422 trước khi chạm DB/API); `universe.audit_universe` kiểm cùng regex
  trước khi mã đi vào lời gọi API và đường dẫn cache. `run_ingest()` mặc định `is_vn100=False` để mã mới không
  tự vào rổ VN100.
- Không tải tài liệu khi chứng chỉ TLS lỗi (không tắt kiểm tra chứng chỉ để lấy cho được).
