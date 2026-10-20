# Hệ thống định giá VN100

Ứng dụng Streamlit định giá cổ phiếu VN100, đọc dữ liệu tài chính/giá lịch sử từ database portable và chỉ gọi API ngoài khi người dùng chủ động cập nhật dữ liệu hoặc sinh báo cáo AI.

## Thư mục đang chạy trên máy này

```text
/Users/macos/Library/CloudStorage/GoogleDrive-tranphixdbt@gmail.com/.shortcut-targets-by-id/18agtU6fpR5TUOQ34MscdIETims-hoTsa/DATA-G/Phi/1 Antigravity/chứng khoán định giá/antigravity-vn100
```

## Cách chạy nhanh trên macOS

1. Cài Python 3.11+ nếu máy chưa có.
2. Tải repo về máy.
3. Nhấp đúp `Chay_Dinh_Gia_VN100.command`.
4. Mở `http://localhost:8502`.

Launcher sẽ tự tạo môi trường Python tại `~/.venv`, cài thư viện từ `requirements.txt`, giải nén `vn100_full.db.gz` thành `vn100_full.db` nếu cần, rồi chạy app.

## Cách chạy nhanh trên Windows

1. Cài Python 3.11+ nếu máy chưa có. Khi cài, tick `Add python.exe to PATH`.
2. Tải repo về máy và giải nén ZIP.
3. Nhấp đúp `Chay_Dinh_Gia_VN100_Windows.bat`.
4. Mở `http://localhost:8502`.

Launcher Windows sẽ tự tạo môi trường Python tại `%USERPROFILE%\.venv`, cài thư
viện từ `requirements.txt`, giải nén `vn100_full.db.gz` thành `vn100_full.db` nếu
cần, rồi chạy app.

Hướng dẫn gửi khách hàng: `docs/HUONG_DAN_GUI_KHACH_HANG.md`.

## Tài liệu cho agent/kỹ thuật viên

Nếu một agent hoặc kỹ thuật viên khác tiếp tục sửa dự án, đọc theo thứ tự:

1. `AGENTS.md`
2. `.agents/AGENT_HANDOFF.md`
3. `.agents/rules/project-context.md`
4. `.agents/rules/security-principles.md`
5. `docs/AGENT_OPERATING_MANUAL.md`
6. `docs/SECURITY_AND_SECRETS.md`

Hai file quan trọng nhất để tránh sửa sai là `docs/AGENT_OPERATING_MANUAL.md`
và `docs/SECURITY_AND_SECRETS.md`.

## Cách chạy bằng terminal

```bash
python3 -m venv ~/.venv
source ~/.venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python scripts/ensure_portable_db.py
export DATABASE_URL_READONLY="sqlite:///$PWD/vn100_full.db"
export DATABASE_URL_WRITE="sqlite:///$PWD/vn100_full.db"
python -m streamlit run streamlit_app.py --server.port 8502 --server.headless true
```

## Dữ liệu đi kèm

- `vn100_full.db.gz`: database portable đã nén để đưa lên GitHub.
- Khi chạy lần đầu, file này được giải nén thành `vn100_full.db`.
- `vn100_full.db` không commit trực tiếp vì file lớn hơn 100 MB, GitHub thường chặn file đơn lẻ quá lớn.

## Xếp hạng VN100 & tích sản

Tab mới tách hai chiến lược Thận trọng/Tăng trưởng, có lịch sử định giá và xuất Excel.
Nhận định DeepSeek dùng một yêu cầu cho cả hai nhóm khi nội dung thay đổi. Bản portable
hiển thị snapshot đã lưu mà không cần key. Lịch thứ Ba 09:30 chỉ được cài trên host
chủ dự án, không tự chạy trên máy khách. Hướng dẫn: [VN100 & tích sản](docs/VN100_TICH_SAN.md).

## API key

Repo không chứa key thật. Nếu muốn dùng dữ liệu live, Google Sheets/Drive, Discord hoặc DeepSeek, sao chép:

```bash
cp .env.example .env
```

Sau đó điền key trong `.env`.

Các key quan trọng:

- `VNSTOCK_API_KEY`: cập nhật dữ liệu mới từ vnstock.
- `DEEPSEEK_API_KEY`: sinh báo cáo AI khi bấm nút trong app.
- `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEET_MASTER_ID`, `GOOGLE_DRIVE_FOLDER_ID`: xuất Google.
- `DISCORD_WEBHOOK_URL`: gửi cảnh báo và báo cáo sáng.
- `DISCORD_BOT_TOKEN`, `DISCORD_OWNER_ID`, `DISCORD_CHANNEL_ID`: bot Discord nhận lệnh trong 1 kênh
  (để trống `DISCORD_OWNER_ID` = mọi thành viên kênh; điền ID = chỉ 1 người).

## Discord: báo cáo sáng và bot

Chỉ cài trên host chủ dự án (cần `pip install -r requirements-integrations.txt` trong `~/.venv`).

- **Báo cáo sáng** (`scripts/daily_report.py`, thứ 2–6 lúc 07:50 qua launchd): cập nhật giá VN100
  và vĩ mô, rồi gửi 5 mã cơ hội định giá (cùng bộ lọc tab VN100), thay đổi so với báo cáo trước
  và khung vĩ mô. Không gọi DeepSeek. Thử không gửi: `python scripts/daily_report.py --dry-run --no-refresh`.
  Lịch sử lưu ở `.daily_report/history/`; ngưỡng ở `config/defaults.yaml → daily_report`.
- **Bot / trợ lý** (`scripts/discord_bot.py`, launchd giữ chạy liên tục): chỉ phản hồi khi được **@bot**.
  `@bot FPT` định giá 1 mã; `@bot !baocao` báo cáo ngay; câu tự do (`@bot so sánh MBB với TCB`,
  `@bot top 10 ngân hàng`, `@bot tin về lãi suất`) → DeepSeek hiểu yêu cầu, Python lấy số, DeepSeek viết
  lời kèm bảng số gốc. Giới hạn lượt/người/ngày ở `config/defaults.yaml → assistant`. Mã chưa qua cổng kiểm chứng chỉ hiện lý do, không hiện FV.
  Cần bật *MESSAGE CONTENT INTENT* trong Discord Developer Portal. Bot offline khi máy ngủ.
- Bật/tắt: `launchctl bootstrap gui/$UID ~/Library/LaunchAgents/vn.antigravity-vn100.<discord-bot|daily-report>.plist`
  / `launchctl bootout gui/$UID/vn.antigravity-vn100.<…>`. Log ở `logs/discord_bot.log`, `logs/daily_report.log`.

## Đẩy lên GitHub

Repo chính của dự án:

```text
https://github.com/tranphixdbt-alt/antigravity-vn100.git
```

Khi cần cập nhật bản đang chạy lên GitHub, xem thêm
`docs/GITHUB_UPDATE_WORKFLOW.md`.

Lệnh push bản portable lên `main`:

```bash
git remote add origin https://github.com/tranphixdbt-alt/antigravity-vn100.git
git add README.md .env.example .gitignore Chay_Dinh_Gia_VN100.command scripts/ensure_portable_db.py vn100_full.db.gz
git add streamlit_app.py valuation tests config docs requirements.txt requirements-integrations.txt
git status
git commit -m "Đóng gói bản chạy portable VN100"
git push origin HEAD:main
```

Trước khi commit, luôn kiểm tra `git status` để chắc `.env`, `venv/`, `build/`, `dist/`, `backups/`, `logs/` và `*.db` không bị đưa lên.

## Kiểm tra nhanh dữ liệu portable

```bash
python scripts/ensure_portable_db.py
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
