"""Chụp định giá toàn VN100 + so trung vị giá mục tiêu CTCK → reports/audit/<label>.csv.

Chỉ đọc DB. Dùng để so trước/sau khi sửa mô hình, KHÔNG dùng để tinh chỉnh.
  DATABASE_URL_READONLY=sqlite:////path/copy.db python -m scripts.audit_vn100_snapshot baseline
"""
import csv
import statistics
import sys
from collections import defaultdict

from sqlalchemy import text

from valuation.config import PROJECT_ROOT, load_defaults
from valuation.db.session import SessionLocalRead
from valuation.engine.batch import value_all
from valuation.ingest.universe import get_vn100_symbols

CONSENSUS_SINCE = "2026-03-01"


def consensus_medians(db) -> dict:
    rows = db.execute(
        text(
            "select ticker, target_price from consensus_history "
            "where report_date >= :d and is_synthetic = 0 and target_price > 0"
        ),
        {"d": CONSENSUS_SINCE},
    ).fetchall()
    by = defaultdict(list)
    for t, tp in rows:
        by[t].append(float(tp))
    return {t: (statistics.median(v), len(v)) for t, v in by.items()}


def main(label: str) -> None:
    db = SessionLocalRead()
    try:
        results = value_all(db, get_vn100_symbols())
        cons = consensus_medians(db)
    finally:
        db.close()

    out_dir = PROJECT_ROOT / "reports" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{label}.csv"
    cols = ["ticker", "method", "group", "price", "fair_value", "upside",
            "consensus_median", "n_reports", "dev_vs_consensus", "recommendation", "error", "flags"]
    band = float((load_defaults().get("audit") or {}).get("consensus_review_band", 0.25))
    review = []
    dev, ups, zero_or_none = [], [], 0
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in results:
            fv = r.get("fair_value")
            med, n = cons.get(r["ticker"], (None, 0))
            d = (fv / med - 1) if (fv and med) else None
            if not fv:
                zero_or_none += 1
            if d is not None:
                dev.append(d)
                if abs(d) > band:
                    review.append((r["ticker"], r.get("method"), fv, med, n, d))
            if r.get("upside") is not None:
                ups.append(r["upside"])
            w.writerow({
                "ticker": r["ticker"], "method": r.get("method"), "group": r.get("group"),
                "price": r.get("price"), "fair_value": fv, "upside": r.get("upside"),
                "consensus_median": med, "n_reports": n, "dev_vs_consensus": d,
                "recommendation": r.get("recommendation"), "error": r.get("error"),
                "flags": "|".join(r.get("flags") or []),
            })

    def share(xs, lo):
        return f"{sum(abs(x) <= lo for x in xs)}/{len(xs)}"

    print(f"→ {out}")
    print(f"mã: {len(results)} | không có FV (NOT_RATED/lỗi): {zero_or_none}")
    print(f"vs trung vị CTCK: ±10% {share(dev, .10)} | ±20% {share(dev, .20)} | "
          f">50% {sum(abs(x) > .5 for x in dev)}/{len(dev)}")
    print(f"upside vs giá: |u|≤20% {share(ups, .20)} | ≥+50% {sum(u >= .5 for u in ups)} | "
          f"≤−50% {sum(u <= -.5 for u in ups)}")
    # Danh sách soát xét: lệch > band so với trung vị CTCK phải có giải thích, KHÔNG ép khớp.
    rv = out_dir / f"{label}_consensus_review.csv"
    with open(rv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "method", "fair_value", "consensus_median", "n_reports", "dev", "giai_thich"])
        for t, m, fv, med, n, d in sorted(review, key=lambda x: -abs(x[5])):
            w.writerow([t, m, round(fv), round(med), n, round(d, 3), ""])
    print(f"cần giải thích (lệch > ±{band:.0%} so với CTCK): {len(review)} mã → {rv}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "snapshot")
