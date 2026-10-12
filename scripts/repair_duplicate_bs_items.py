"""Sửa dòng BCTC bị ghi đè do nguồn trả item_id TRÙNG (vd FPT short_term_investments=0).

vnstock trả hai dòng cùng item_id (Đầu tư ngắn hạn 29.631 tỷ và một dòng 0). Bản nạp
cũ để dòng sau đè dòng trước; normalizer hiện tại đã giữ dòng đầu + gắn hậu tố cho
dòng sau, nhưng upsert BCTC là do_nothing nên tải lại không sửa được số cũ.

Mặc định DRY-RUN: chỉ ghi reports/audit/bs_duplicate_repair_<ngày_giờ>.csv (cũ → mới).
--apply mới ghi DB — backup trước (sqlite3 vn100_full.db ".backup backups/...").
  python -m scripts.repair_duplicate_bs_items [--apply] [TICKER ...]
"""
import argparse
import csv
import datetime
import shutil
import tempfile

import pathlib

import pandas as pd

from valuation.config import PROJECT_ROOT
from valuation.db.models import FinancialsQuarterly, Ticker
from valuation.db.session import SessionLocalWrite
from valuation.ingest.normalizer import unpivot_financials
from valuation.ingest.vnstock_client import vnstock_client

_KEY = ("fiscal_year", "fiscal_quarter", "is_consolidated", "is_restated", "statement", "line_item")


def source_rows(ticker: str) -> pd.DataFrame:
    """Các dòng BS mà item_id bị trùng trong nguồn, đã chuẩn hóa như khi ingest."""
    parts = []
    for period in ("quarter", "year"):
        df = vnstock_client.get_financials(ticker, "BS", period)
        if df.empty or "item_id" not in df:
            continue
        dup_ids = set(df.loc[df["item_id"].duplicated(keep=False), "item_id"])
        if not dup_ids:
            continue
        norm = unpivot_financials(df, "BS")
        parts.append(norm[norm["line_item"].map(lambda li: li.split("__")[0] in dup_ids)])
    return pd.concat(parts) if parts else pd.DataFrame()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("tickers", nargs="*")
    args = ap.parse_args()

    db = SessionLocalWrite()
    tickers = args.tickers or [
        t for (t,) in db.query(Ticker.ticker).filter(Ticker.is_vn100.is_(True), Ticker.sector != "Banks")
    ]
    out = PROJECT_ROOT / "reports" / "audit" / f"bs_duplicate_repair_{datetime.datetime.now():%Y%m%d_%H%M}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Ghi ra file tạm cục bộ: ghi thẳng vào thư mục Google Drive từng timeout giữa chừng.
    tmp = pathlib.Path(tempfile.gettempdir()) / out.name
    changes = 0
    try:
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ticker", *_KEY, "old_value", "new_value", "action"])
            for t in tickers:
                try:
                    rows = source_rows(t)
                except Exception as e:  # một mã lỗi nguồn không chặn mã khác
                    w.writerow([t, *[""] * len(_KEY), "", "", f"FETCH_ERROR {type(e).__name__}"])
                    continue
                for _, r in rows.iterrows():
                    key = {k: r[k] for k in _KEY}
                    key["is_consolidated"], key["is_restated"] = bool(key["is_consolidated"]), bool(key["is_restated"])
                    new = float(r["value"])
                    row = db.query(FinancialsQuarterly).filter_by(ticker=t, **key).one_or_none()
                    old = None if row is None or row.value is None else float(row.value)
                    if old is not None and abs(old - new) <= max(1.0, abs(new) * 1e-9):
                        continue
                    action = "INSERT" if row is None else "UPDATE"
                    w.writerow([t, *key.values(), old, new, action])
                    changes += 1
                    if args.apply:
                        if row is None:
                            db.add(FinancialsQuarterly(
                                ticker=t, value=new, currency="VND",
                                source=r.get("source", "vnstock"), **key,
                            ))
                        else:
                            row.value = new
                if args.apply:
                    db.commit()
    finally:
        db.close()
        shutil.copyfile(tmp, out)
    print(f"{'ĐÃ GHI' if args.apply else 'DRY-RUN'}: {changes} thay đổi → {out}")


if __name__ == "__main__":
    main()
