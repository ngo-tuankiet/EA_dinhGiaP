"""
Thu thập khuyến nghị ĐA CÔNG TY CHỨNG KHOÁN từ Simplize (api2.simplize.vn).

Ưu điểm: API JSON công khai (không cần đăng nhập/Chrome), phủ nhiều CTCK KHÁC với
24hmoney (FPTS, MAS, VPBS, BVSC, YUANTA, DSC, SHINHAN, KIS, SSV, VDS, KAFI,
VCSC...), mỗi báo cáo kèm giá mục tiêu + khuyến nghị + link PDF tải trực tiếp
(attachedLink, host trên CDN Simplize). Ghi vào consensus_history qua upsert
(khoá ticker+broker+report_date).

NGUYÊN TẮC: chỉ lưu số liệu thật; PDF chỉ tải về lưu NỘI BỘ tham khảo, không
phát tán lại. Nguồn (link) ghi kèm để truy vết.
"""
from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from valuation.db.models import Consensus
from valuation.db.session import SessionLocalWrite
from valuation.db.upsert import dialect_insert

_API = "https://api2.simplize.vn/api/company/analysis-report/list"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _parse_date(s: str) -> Optional[datetime.date]:
    try:
        return datetime.datetime.strptime(s.strip(), "%d/%m/%Y").date()
    except (ValueError, AttributeError):
        return None


def fetch_reports(ticker: str, size: int = 30, timeout: float = 20.0) -> List[Dict[str, Any]]:
    """Lấy danh sách báo cáo CTCK cho 1 mã từ Simplize (có giá mục tiêu). KHÔNG ghi DB."""
    resp = httpx.get(_API, params={"ticker": ticker.upper(), "page": 0, "size": size},
                     headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    data = (resp.json() or {}).get("data") or []

    seen = set()
    out: List[Dict[str, Any]] = []
    for rec in data:
        tp = rec.get("targetPrice")
        broker = (rec.get("source") or "").strip().upper()
        rep_date = _parse_date(rec.get("issueDate") or "")
        if not tp or tp <= 0 or not broker or rep_date is None:
            continue  # bỏ báo cáo ngành/chiến lược không có giá mục tiêu
        key = (broker, rep_date)
        if key in seen:
            continue
        seen.add(key)
        rating = re.sub(r"\s+", " ", (rec.get("recommend") or "").strip()).upper() or None
        title = (rec.get("title") or "").strip()
        out.append({
            "ticker": ticker.upper(), "broker": broker, "report_date": rep_date,
            "target_price": float(tp), "rating": rating,
            "source_url": rec.get("attachedLink") or "",
            # D24: tiêu đề báo cáo lưu vào cột riêng để truy vấn được, thay vì
            # chỉ nhét trong chuỗi raw_quote.
            "report_title": title or None,
            "raw_quote": f"{broker} {rep_date}: {rating}, giá mục tiêu {float(tp):,.0f} VND "
                         f"— {title} (nguồn Simplize)",
        })
    return out


def import_reports(ticker: str, size: int = 30) -> List[Dict[str, Any]]:
    """Lấy + ghi khuyến nghị CTCK cho 1 mã vào consensus_history (idempotent)."""
    recs = fetch_reports(ticker, size=size)
    if not recs:
        return []
    from valuation.ingest.broker_names import normalize_broker

    db = SessionLocalWrite()
    try:
        for rec in recs:
            # D24: `broker` giữ nguyên tên thô của Simplize (bảo toàn xuất xứ);
            # việc gộp cùng-một-CTCK-khác-tên (VCSC vs VIETCAP) làm ở tầng đọc
            # qua `broker_canon`, xem calibration/consensus_view.py.
            canon, _ = normalize_broker(rec["broker"])
            row = {**rec, "broker_canon": canon, "source_site": "SIMPLIZE",
                   "currency_unit": "VND", "is_synthetic": False}
            stmt = dialect_insert(db, Consensus).values(row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker", "broker", "report_date"],
                set_={
                    "target_price": stmt.excluded.target_price,
                    "rating": stmt.excluded.rating,
                    "source_url": stmt.excluded.source_url,
                    "raw_quote": stmt.excluded.raw_quote,
                    "report_title": stmt.excluded.report_title,
                    "broker_canon": stmt.excluded.broker_canon,
                    "source_site": stmt.excluded.source_site,
                },
            )
            db.execute(stmt)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return recs


def download_reports(ticker: str, dest_dir: str, limit: int = 5,
                     size: int = 30, timeout: float = 60.0) -> List[str]:
    """Tải PDF báo cáo (attachedLink) về thư mục nội bộ để tham khảo. Trả list đường dẫn.

    Chỉ tải file .pdf công khai trên CDN Simplize; lưu nội bộ, không phát tán lại.
    """
    os.makedirs(dest_dir, exist_ok=True)
    saved: List[str] = []
    for rec in fetch_reports(ticker, size=size)[:limit]:
        url = rec.get("source_url") or ""
        if not url.lower().endswith(".pdf"):
            continue
        fname = f"{ticker.upper()}_{rec['broker']}_{rec['report_date']}.pdf"
        path = os.path.join(dest_dir, fname)
        if os.path.exists(path):
            saved.append(path)
            continue
        try:
            r = httpx.get(url, headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
            saved.append(path)
        except Exception:
            continue
    return saved
