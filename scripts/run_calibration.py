"""Chạy hiệu chuẩn định giá VN100 vs đồng thuận CTCK (D23).

Quy trình chuẩn khi sửa mô hình:

    # 1. Chụp baseline TRƯỚC khi sửa
    python -m scripts.run_calibration --label baseline-2026-08-10

    # 2. Sửa mô hình ...

    # 3. Đo lại và bắt buộc không được hồi quy
    python -m scripts.run_calibration --label after-D26-pb \\
        --baseline-label baseline-2026-08-10 --fail-on-regression --markdown diff.md

    # 4. Dán nội dung diff.md vào DECISIONS.md (AGENTS.md yêu cầu ghi D-entry)

Exit code 1 khi `--fail-on-regression` và verdict = FAIL → dùng được trong CI/hook.
"""
import argparse
import csv
import datetime
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from valuation.calibration.compare import FAIL, compare_runs, render_diff_markdown
from valuation.calibration.harness import load_run, persist_run, run_calibration
from valuation.db.session import SessionLocalRead, SessionLocalWrite


def _pct(x) -> str:
    return "—" if x is None else f"{x:+.1%}"


def _print_summary(run) -> None:
    agg = run.aggregates
    o = agg.get("overall", {})
    print("\n" + "=" * 78)
    print(f"HIỆU CHUẨN — {run.label}  (as_of={run.as_of}, git={(run.git_sha or '?')[:8]})")
    print("=" * 78)
    print(f"  Số mã                     : {o.get('n')}  (định giá được: {run_valued(run)})")
    print(f"  Có đồng thuận CTCK        : {o.get('n_with_consensus')}")
    print(f"  Lệch median vs CTCK       : {_pct(o.get('median_dev'))}")
    print(f"  |Lệch| median             : {_pct(o.get('median_abs_dev'))}")
    print(f"  Tỷ lệ trong band          : {_pct(o.get('share_in_band'))}")
    print(f"  Lệch median vs THỊ GIÁ    : {_pct(o.get('median_dev_vs_price'))}")
    print(f"  Số mã FV < thị giá        : {o.get('n_below_price')}"
          f"  (trong đó thấp hơn >40%: {o.get('n_below_price_40')})")
    print(f"  Số mã lỗi                 : {o.get('n_errors')}")

    print(f"\n  {'NHÓM PP':<12}{'n':>4}{'lệch median':>14}{'|lệch| med':>13}"
          f"{'trong band':>13}{'FV<giá 40%':>13}")
    print("  " + "-" * 69)
    for method, s in sorted(agg.get("by_method", {}).items(),
                            key=lambda kv: -(kv[1].get("n") or 0)):
        print(f"  {method:<12}{s.get('n_with_consensus') or 0:>4}"
              f"{_pct(s.get('median_dev')):>14}{_pct(s.get('median_abs_dev')):>13}"
              f"{_pct(s.get('share_in_band')):>13}{s.get('n_below_price_40') or 0:>13}")

    gov = {}
    for ob in run.observations:
        gov[ob.governance_status] = gov.get(ob.governance_status, 0) + 1
    if set(gov) - {"OK"}:
        print("\n  Governance:", ", ".join(f"{k}={v}" for k, v in sorted(gov.items())))


def run_valued(run) -> int:
    return sum(1 for o in run.observations if o.fair_value)


def _write_csv(run, path: str) -> None:
    cols = ["ticker", "method", "sector_group", "fair_value", "market_price",
            "consensus_median", "n_brokers", "dev_vs_consensus", "dev_vs_price",
            "band", "band_status", "governance_status", "flags", "error"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for o in sorted(run.observations, key=lambda x: (x.dev_vs_consensus is None,
                                                         x.dev_vs_consensus or 0)):
            w.writerow([
                o.ticker, o.method, o.sector_group, o.fair_value, o.market_price,
                o.consensus_median, o.n_brokers, o.dev_vs_consensus, o.dev_vs_price,
                o.band, o.band_status, o.governance_status,
                "|".join(o.flags or []), o.error or "",
            ])
    print(f"\n-> Đã ghi CSV: {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Hiệu chuẩn định giá VN100 vs CTCK")
    ap.add_argument("--label", default="", help="Tên lần chạy (bắt buộc khi lưu DB)")
    ap.add_argument("--tickers", default="", help="Danh sách mã, phân tách bằng dấu phẩy")
    ap.add_argument("--as-of", default="", help="Mốc thời gian YYYY-MM-DD (chống lookahead)")
    ap.add_argument("--window-days", type=int, default=180)
    ap.add_argument("--half-life-days", default="none",
                    help="Chu kỳ bán rã trọng số độ mới, hoặc 'none'")
    ap.add_argument("--band", type=float, default=0.20)
    ap.add_argument("--baseline-label", default="", help="So sánh với lần chạy này")
    ap.add_argument("--fail-on-regression", action="store_true",
                    help="Exit 1 nếu verdict = FAIL")
    ap.add_argument("--csv", default="", help="Xuất bảng per-ticker ra CSV")
    ap.add_argument("--markdown", default="", help="Xuất bảng diff markdown cho DECISIONS.md")
    ap.add_argument("--no-persist", action="store_true", help="Không ghi DB")
    args = ap.parse_args()

    as_of = datetime.date.fromisoformat(args.as_of) if args.as_of else None
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None
    half_life = None if args.half_life_days.lower() in ("none", "", "0") else float(args.half_life_days)

    try:
        from valuation.calibration.registry import load_registry
        registry = load_registry()
    except Exception:
        registry = None

    db_read = SessionLocalRead()
    try:
        def progress(idx, total, ticker):
            print(f"\r  [{idx}/{total}] {ticker:<8}", end="", flush=True)

        run = run_calibration(
            db_read, tickers=tickers, as_of=as_of, label=args.label,
            window_days=args.window_days, half_life_days=half_life,
            band=args.band, registry=registry, progress=progress,
        )
        print()
        _print_summary(run)

        if args.csv:
            _write_csv(run, args.csv)

        if not args.no_persist and args.label:
            db_write = SessionLocalWrite()
            try:
                run_id = persist_run(db_write, run)
                print(f"\n-> Đã lưu DB: calibration_runs.id={run_id} (label='{run.label}')")
            finally:
                db_write.close()
        elif not args.label:
            print("\n-> Không có --label nên KHÔNG lưu DB.")

        if args.baseline_label:
            baseline = load_run(db_read, label=args.baseline_label)
            if baseline is None:
                print(f"\n!! Không tìm thấy baseline '{args.baseline_label}' — bỏ qua so sánh.")
                return 0
            diff = compare_runs(baseline, run)
            md = render_diff_markdown(diff)
            print("\n" + "=" * 78)
            print(md)
            if args.markdown:
                with open(args.markdown, "w", encoding="utf-8") as f:
                    f.write(md + "\n")
                print(f"\n-> Đã ghi markdown: {args.markdown}")
            if args.fail_on_regression and diff.verdict == FAIL:
                print("\n🚨 HỒI QUY — từ chối thay đổi này.")
                return 1
        return 0
    finally:
        db_read.close()


if __name__ == "__main__":
    raise SystemExit(main())
