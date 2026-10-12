"""Nâng cấp chất lượng dữ liệu đồng thuận CTCK (D24).

CHỈ cộng thêm cột + backfill giá trị dẫn xuất — KHÔNG sửa cột `broker` (nằm
trong PRIMARY KEY, sửa tại chỗ là vi phạm luật vàng #6), KHÔNG xoá dòng nào.
Mọi thay đổi đảo ngược được bằng `UPDATE consensus_history SET <cột> = NULL`.

    python -m scripts.migrate_consensus_quality           # dry-run: in báo cáo
    python -m scripts.migrate_consensus_quality --apply   # thực thi

Backfill:
  - source_site  : suy từ host của source_url
  - broker_canon : normalize_broker() — in ra danh sách sẽ GỘP để review trước
  - is_synthetic : đánh dấu dòng seed test (URL trỏ thẳng web CTCK, không phải
                   24hmoney/Simplize) — in ra để xác nhận trước khi apply
"""
import argparse
import os
import sys
from collections import defaultdict
from urllib.parse import urlparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect, text

from valuation.db.session import SessionLocalWrite
from valuation.ingest.broker_names import normalize_broker

_NEW_COLUMNS = {
    "broker_canon": "TEXT",
    "source_site": "TEXT",
    "is_synthetic": "BOOLEAN NOT NULL DEFAULT FALSE",
    "report_title": "TEXT",
    "currency_unit": "TEXT DEFAULT 'VND'",
}

# Dòng seed giả trong scratch/run_consensus_collector.py trỏ thẳng web CTCK.
# Dòng cào thật LUÔN mang host 24hmoney.vn / simplize.vn / cdn.simplize.vn.
_SYNTHETIC_PREDICATE = r"source_url ~ '://(www\.)?(ssi|hsc|mbs|vci|vndirect)\.com\.vn'"


def _site_from_url(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if "24hmoney" in host:
        return "24HMONEY"
    if "simplize" in host:
        return "SIMPLIZE"
    if host.startswith("vnstock") or url.startswith("vnstock:"):
        return "VNSTOCK"
    return "UNKNOWN" if host else "UNKNOWN"


def main() -> int:
    ap = argparse.ArgumentParser(description="Nâng cấp chất lượng consensus (D24)")
    ap.add_argument("--apply", action="store_true", help="Thực thi thật (mặc định dry-run)")
    args = ap.parse_args()

    db = SessionLocalWrite()
    try:
        bind = db.get_bind()
        existing = {c["name"] for c in inspect(bind).get_columns("consensus_history")}
        missing = {k: v for k, v in _NEW_COLUMNS.items() if k not in existing}

        print("=" * 70)
        print("MIGRATION CHẤT LƯỢNG CONSENSUS (D24)")
        print("=" * 70)
        for col in _NEW_COLUMNS:
            print(f"  {col:<16} {'ĐÃ CÓ' if col in existing else 'SẼ THÊM'}")

        rows = db.execute(text(
            "SELECT ticker, broker, report_date, source_url FROM consensus_history"
        )).fetchall()
        print(f"\n  Tổng số dòng: {len(rows)}")

        # --- Báo cáo GỘP tên CTCK ---
        groups: dict[str, set] = defaultdict(set)
        unmatched: set[str] = set()
        for _, broker, _, _ in rows:
            canon, ok = normalize_broker(broker)
            groups[canon].add(broker)
            if not ok:
                unmatched.add(broker)

        merges = {c: v for c, v in groups.items() if len(v) > 1}
        print(f"\n  --- Sẽ GỘP {len(merges)} nhóm tên CTCK ---")
        for canon, raws in sorted(merges.items()):
            print(f"    {canon:<12} <- {', '.join(sorted(raws))}")
        if not merges:
            print("    (không có nhóm nào cần gộp trong dữ liệu hiện tại)")
        print(f"\n  --- {len(unmatched)} tên CHƯA map (giữ nguyên, không gộp bừa) ---")
        print(f"    {', '.join(sorted(unmatched)) if unmatched else '(không có)'}")

        # --- Báo cáo source_site ---
        sites: dict[str, int] = defaultdict(int)
        for _, _, _, url in rows:
            sites[_site_from_url(url)] += 1
        print("\n  --- Phân bổ nguồn ---")
        for site, n in sorted(sites.items(), key=lambda kv: -kv[1]):
            print(f"    {site:<12} {n}")

        # --- Báo cáo dòng nghi là seed giả ---
        syn = db.execute(text(
            f"SELECT ticker, broker, report_date, source_url FROM consensus_history "
            f"WHERE {_SYNTHETIC_PREDICATE}"
        )).fetchall()
        print(f"\n  --- {len(syn)} dòng sẽ đánh dấu is_synthetic=TRUE ---")
        for t, b, d, u in syn:
            print(f"    {t:<6} {b:<14} {d}  {u}")
        if not syn:
            print("    (không có — DB này chưa từng chạy scratch seed)")

        if not args.apply:
            print("\n[DRY-RUN] Chưa thay đổi gì. Xem lại báo cáo trên rồi chạy --apply.")
            return 0

        # ---------------- THỰC THI ----------------
        for col, ddl in missing.items():
            db.execute(text(f"ALTER TABLE consensus_history ADD COLUMN IF NOT EXISTS {col} {ddl};"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_consensus_ticker_date "
            "ON consensus_history (ticker, report_date DESC);"
        ))
        db.commit()
        print(f"\n  -> Đã thêm {len(missing)} cột + index.")

        # Backfill từng dòng theo khoá chính (an toàn, không đụng dòng khác).
        n_upd = 0
        for ticker, broker, report_date, url in rows:
            canon, _ = normalize_broker(broker)
            db.execute(
                text("UPDATE consensus_history SET broker_canon = :c, source_site = :s "
                     "WHERE ticker = :t AND broker = :b AND report_date = :d"),
                {"c": canon, "s": _site_from_url(url), "t": ticker,
                 "b": broker, "d": report_date},
            )
            n_upd += 1
        db.commit()
        print(f"  -> Backfill broker_canon + source_site cho {n_upd} dòng.")

        res = db.execute(text(
            f"UPDATE consensus_history SET is_synthetic = TRUE WHERE {_SYNTHETIC_PREDICATE}"
        ))
        db.commit()
        print(f"  -> Đánh dấu {res.rowcount} dòng is_synthetic.")
        print("\nHoàn tất.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
