"""Dựng BẢN NHÁP danh sách cổ phần công ty con cho SOTP, từ vnstock (D28).

VÌ SAO CẦN: proxy SOTP hiện tại vô nghĩa với tập đoàn đa ngành (VIC lệch -92% so
thị giá) nên đã bị chặn thành NOT_RATED. Để định giá được thật sự, cần biết tập
đoàn nắm bao nhiêu % ở công ty con nào — dữ liệu này KHÔNG có trong DB.

Script này KHÔNG tự động hoá giả định (AGENTS.md §7). Nó chỉ:
  1. Kéo `subsidiaries()` + `affiliate()` từ vnstock (dữ liệu công bố).
  2. Đánh dấu công ty con nào ĐÃ NIÊM YẾT (định giá được theo vốn hoá thị trường).
  3. Ước lượng ĐỘ PHỦ so với vốn chủ sở hữu hợp nhất.
  4. In ra YAML nháp để chuyên viên ĐỐI CHIẾU BCTN rồi mới đưa vào
     `config/sotp_holdings.yaml`.

Cảnh báo đã biết: vnstock KHÔNG đầy đủ. Ví dụ VIC — thiếu hẳn Vinhomes (VHM),
tài sản lớn nhất — nên độ phủ tính ra rất thấp và mã vẫn phải NOT_RATED cho đến
khi chuyên viên bổ sung tay. Đừng dùng đầu ra của script này như sự thật cuối cùng.

    python -m scripts.draft_sotp_holdings VIC MSN REE TCH
"""
import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from valuation.data_access.repo import get_latest_price, get_shares_outstanding_repo
from valuation.db.models import Ticker
from valuation.db.session import SessionLocalRead


def _listed_tickers(db) -> set:
    return {t[0] for t in db.query(Ticker.ticker).all()}


def _market_cap_ty(db, ticker: str):
    """Vốn hoá (tỷ đồng) = thị giá (đ) × số cp (triệu) / 1000."""
    price = get_latest_price(db, ticker, fetch_live=False)
    shares = get_shares_outstanding_repo(db, ticker)
    if not price or not shares:
        return None
    return price * shares / 1000.0


def draft_for(db, ticker: str) -> dict:
    from vnstock.api.company import Company

    known = _listed_tickers(db)
    c = Company(source="VCI", symbol=ticker)
    rows = []

    try:
        subs = c.subsidiaries()
        for _, r in subs.iterrows():
            code = str(r.get("sub_organ_code") or "").strip()
            rows.append({
                "name": str(r.get("organ_name") or "").strip(),
                "code": code,
                "stake": float(r.get("ownership_percent") or 0.0),
                "listed_ticker": code if code in known else None,
                "source": "vnstock.subsidiaries",
            })
    except Exception as e:
        print(f"  !! subsidiaries({ticker}) lỗi: {str(e)[:70]}")

    try:
        aff = c.affiliate()
        for _, r in aff.iterrows():
            tk = str(r.get("right_ticker") or "").strip()
            rows.append({
                "name": str(r.get("right_organ_name_vi") or "").strip(),
                "code": str(r.get("right_organ_code") or "").strip(),
                "stake": float(r.get("owned_percentage") or 0.0),
                "listed_ticker": tk if tk in known else None,
                "source": "vnstock.affiliate",
            })
    except Exception as e:
        print(f"  !! affiliate({ticker}) lỗi: {str(e)[:70]}")

    # Gộp trùng theo code. ƯU TIÊN bản có mã niêm yết: cùng một công ty con xuất
    # hiện ở CẢ `subsidiaries` (chỉ có mã nội bộ, vd VRJSC) lẫn `affiliate` (có
    # `right_ticker` = VRE). Nếu chỉ so tỷ lệ thì bản không có mã có thể thắng và
    # ta mất khả năng định giá theo vốn hoá — đúng lỗi đã gặp với VIC/VRE.
    def _better(new: dict, old: dict) -> bool:
        if bool(new["listed_ticker"]) != bool(old["listed_ticker"]):
            return bool(new["listed_ticker"])
        return new["stake"] > old["stake"]

    best: dict = {}
    for r in rows:
        k = r["code"] or r["name"]
        if not k:
            continue
        if k not in best or _better(r, best[k]):
            best[k] = r
    return {"ticker": ticker, "rows": sorted(best.values(), key=lambda x: -x["stake"])}


def main() -> int:
    ap = argparse.ArgumentParser(description="Dựng nháp cổ phần SOTP từ vnstock")
    ap.add_argument("tickers", nargs="*", default=["VIC", "MSN", "REE", "TCH"])
    ap.add_argument("--min-stake", type=float, default=0.05,
                    help="Bỏ qua cổ phần nhỏ hơn ngưỡng này (mặc định 5%%)")
    args = ap.parse_args()

    db = SessionLocalRead()
    try:
        for tk in args.tickers:
            print(f"\n{'=' * 68}\n{tk}\n{'=' * 68}")
            d = draft_for(db, tk)
            listed = [r for r in d["rows"] if r["listed_ticker"] and r["stake"] >= args.min_stake]
            unlisted = [r for r in d["rows"]
                        if not r["listed_ticker"] and r["stake"] >= args.min_stake]

            covered_ty = 0.0
            print("  --- Công ty con ĐÃ NIÊM YẾT (định giá được theo vốn hoá) ---")
            if not listed:
                print("    (không tìm thấy)")
            for r in listed:
                mc = _market_cap_ty(db, r["listed_ticker"])
                val = (mc * r["stake"]) if mc else None
                if val:
                    covered_ty += val
                print(f"    {r['listed_ticker']:<6} {r['stake']:>7.2%}  "
                      f"vốn hoá={mc:,.0f} tỷ  phần sở hữu={val:,.0f} tỷ" if mc else
                      f"    {r['listed_ticker']:<6} {r['stake']:>7.2%}  (chưa có giá)")

            print(f"  --- Chưa niêm yết (>= {args.min_stake:.0%}), cần chuyên viên định giá tay ---")
            for r in unlisted[:10]:
                print(f"    {r['code'][:18]:<18} {r['stake']:>7.2%}  {r['name'][:44]}")
            if len(unlisted) > 10:
                print(f"    ... và {len(unlisted) - 10} đơn vị nữa")

            mc_parent = _market_cap_ty(db, tk)
            if mc_parent:
                print(f"\n  Vốn hoá {tk}: {mc_parent:,.0f} tỷ | "
                      f"Phần niêm yết định giá được: {covered_ty:,.0f} tỷ "
                      f"({covered_ty / mc_parent:.0%})")
                if covered_ty / mc_parent < 0.60:
                    print("  ⚠️  ĐỘ PHỦ THẤP — vnstock thiếu dữ liệu (vd VIC thiếu VHM). "
                          "Mã sẽ vẫn NOT_RATED cho tới khi bổ sung tay từ BCTN.")
        print("\nĐây là BẢN NHÁP. Đối chiếu BCTN rồi mới đưa vào config/sotp_holdings.yaml.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
