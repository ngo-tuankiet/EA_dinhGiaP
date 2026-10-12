# Security Principles — đọc trước khi commit/push

- Không commit `.env`, API key, PAT GitHub, Google token, Discord webhook, n8n
  credential, DB password, service account JSON, private key hoặc database thô.
- File dữ liệu được phép commit cho bản portable là `vn100_full.db.gz`; không
  commit `vn100_full.db` hoặc bất kỳ `*.db`/`*.sqlite*`.
- Không dùng `git add .` hoặc `git add -A`. Add từng file/thư mục cụ thể sau khi
  đã xem `git status`.
- Nếu phát hiện secret thật trong file tracked hoặc đã push, báo người dùng để
  revoke/rotate key. Xoá khỏi file hiện tại chưa đủ nếu secret đã nằm trong lịch
  sử Git.
- Checklist đầy đủ nằm ở `docs/SECURITY_AND_SECRETS.md`.
