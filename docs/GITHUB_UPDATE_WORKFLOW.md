# Quy trình cập nhật GitHub

Repo GitHub chính:

```text
https://github.com/tranphixdbt-alt/antigravity-vn100.git
```

Branch phát hành cho người dùng tải về:

```text
main
```

## Mục tiêu mỗi lần người dùng nói "update"

1. Kiểm tra app local đang chạy ổn.
2. Cập nhật dữ liệu portable nếu `vn100_full.db` thay đổi:

   ```bash
   gzip -c vn100_full.db > vn100_full.db.gz
   python scripts/ensure_portable_db.py
   gzip -t vn100_full.db.gz
   ```

3. Quét secret trước khi commit.
4. Commit toàn bộ code/config/docs/test/dữ liệu portable hợp lệ.
5. Push thẳng lên `main`:

   ```bash
   git push origin HEAD:main
   ```

## Không bao giờ commit

- `.env`
- key thật, token, webhook, service-account JSON
- `vn100_full.db`, `vn100.db`, `*.db`
- `venv/`, `build/`, `dist/`
- `backups/`, `logs/`
- shortcut Google Drive lồng trong repo

## File dữ liệu được phép commit

- `vn100_full.db.gz`

File này là database portable đã nén. Khi người khác tải repo về, launcher
`Chay_Dinh_Gia_VN100.command` sẽ tự giải nén thành `vn100_full.db` nếu cần.

## Launcher khách hàng

- macOS: `Chay_Dinh_Gia_VN100.command`
- Windows: `Chay_Dinh_Gia_VN100_Windows.bat`
- Hướng dẫn gửi khách hàng: `docs/HUONG_DAN_GUI_KHACH_HANG.md`

## Lưu ý quyền GitHub

Nếu push lỗi:

```text
Permission to tranphixdbt-alt/antigravity-vn100.git denied to Thomas-Tuan
```

nghĩa là máy đang đăng nhập Git bằng tài khoản `Thomas-Tuan` nhưng repo thuộc
`tranphixdbt-alt`. Cần đăng nhập lại Git bằng `tranphixdbt-alt` hoặc cấp quyền
write cho `Thomas-Tuan` trong repo.
