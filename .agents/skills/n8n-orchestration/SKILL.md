---
name: n8n-orchestration
description: Khi thiết kế hoặc sửa workflow n8n, trigger, hoặc ranh giới giữa n8n và Python service, dùng skill này để giữ n8n chỉ làm điều phối và đảm bảo chạy lại an toàn.
---

# Skill: Điều phối bằng n8n

## Ranh giới (NGHIÊM)
- **n8n CHỈ điều phối:** trigger, gọi HTTP tới Python service, định tuyến, gửi Discord/Sheets, xử lý lỗi/retry, lập lịch.
- **Mọi tính toán** (ingest parse, QC, dự phóng, DCF, định giá) nằm trong **Python service (FastAPI)**. Tuyệt đối không viết logic tài chính trong Function node của n8n.
- n8n gọi Python qua HTTP node tới các endpoint nhỏ, idempotent: `/ingest`, `/qc`, `/analyze`, `/revalue`.

## Các workflow
- **WF-1 Backfill tuần tự (Phase 1):** lấy danh sách VN100 → loop từng mã → gọi `/ingest`→`/qc`→`/analyze` → cập nhật checkpoint. Có retry + báo Discord khi lỗi/khi xong.
- **WF-2 BCTC mới (Phase 2):** poll/webhook CBTT HOSE/HNX → phát hiện mã có BCTC mới → `/revalue` mã đó → cập nhật Sheet → Discord.
- **WF-3 Chạy theo yêu cầu:** nhận mã do người dùng nhập (form n8n / lệnh Discord) → validate mã → `/revalue` → trả Discord.
- **WF-4 Recompute từ Sheet:** Apps Script → webhook → Python đọc giả định đã sửa → tính lại → ghi Sheet + lưu version.
- **WF-5 Macro/ngành định kỳ:** cron tuần/tháng → ingest GSO/SBV/industry.

## Luật bắt buộc
1. **Idempotent:** mỗi lần gọi lại một bước không được tạo dữ liệu trùng hay gửi cảnh báo trùng. Dùng khóa idempotency (mã + kỳ + version).
2. **Checkpoint cho backfill:** lưu tiến độ; lỗi ở mã thứ N thì chạy lại từ mã N, không từ đầu.
3. **Retry có backoff** cho lỗi tạm thời (rate limit vnstock, mạng). Lỗi dữ liệu (sai/mâu thuẫn) thì KHÔNG retry mù — báo Discord.
4. **Rate limit:** tôn trọng giới hạn vnstock & trang CBTT; thêm delay giữa các mã.
5. **Validate input:** mã người dùng nhập phải khớp whitelist VN100 / regex mã hợp lệ trước khi gọi Python.
6. **Secret:** credential (vnstock, Google, Discord, DB) lưu trong credential store của n8n, KHÔNG nhúng trong node hay URL.
7. **Quan sát được:** mỗi workflow log được run-id, mã, kết quả; lỗi đẩy Discord với đủ ngữ cảnh (mã, bước, lý do) nhưng KHÔNG kèm secret.

## Tự host
- Nếu self-host n8n: đặt sau HTTPS, bật basic auth/owner account, không expose webhook công khai không xác thực (dùng header token cho webhook recompute).
