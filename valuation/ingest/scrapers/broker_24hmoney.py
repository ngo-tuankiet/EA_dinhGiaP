"""
Thu thập khuyến nghị ĐA CÔNG TY CHỨNG KHOÁN từ 24hmoney.vn (nguồn tổng hợp công
khai — SSI, KBSV, BSC, MIRAE, ACBS, VCBS, MBS, VNDS...).

Ưu điểm: dữ liệu nằm trong HTML SSR → lấy bằng httpx (KHÔNG cần Chrome, nhanh,
tự động hoá được cho cả 100 mã). Mỗi mã cho 3–5 báo cáo CTCK gần nhất kèm giá
mục tiêu + khuyến nghị + ngày. Ghi vào consensus_history qua upsert (idempotent,
khoá ticker+broker+report_date).

NGUYÊN TẮC: chỉ lưu số liệu thật đọc được; không bịa. Nguồn ghi kèm để truy vết.
"""
from __future__ import annotations

import datetime
import html as _html
import re
from typing import Any, Dict, List

import httpx

from valuation.db.models import Consensus
from valuation.db.session import SessionLocalWrite
from valuation.db.upsert import dialect_insert

_ORIGIN = "https://24hmoney.vn"
_BASE = "https://24hmoney.vn/stock/"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# "Khuyến nghị MUA với giá mục tiêu 103,800 đồng/cổ phiếu Nguồn: KBSV-08/06/2026"
# Một số trang cũ ghi thiếu rating: "Khuyến nghị với giá mục tiêu ..."
_PATTERN = re.compile(
    r"Khuyến nghị(?:\s+(?P<rating>[^<]{1,30}?))?\s+với giá mục tiêu\s+"
    r"(?P<tp>[\d.,]+)\s*đồng.*?Nguồn:\s*(?P<broker>[A-Za-z0-9]+)-"
    r"(?P<date>\d{2}/\d{2}/\d{4})",
    re.IGNORECASE | re.DOTALL,
)


def _parse_tp(s: str) -> float:
    """'103,800' -> 103800.0 (bỏ dấu phân cách nghìn)."""
    return float(s.replace(".", "").replace(",", ""))


def fetch_broker_reports(ticker: str, timeout: float = 20.0) -> List[Dict[str, Any]]:
    """Lấy danh sách khuyến nghị CTCK cho 1 mã từ 24hmoney. KHÔNG ghi DB."""
    url = f"{_BASE}{ticker.upper()}"
    resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    seen = set()
    out: List[Dict[str, Any]] = []
    for m in _PATTERN.finditer(html):
        broker = m.group("broker").upper().strip()
        try:
            rep_date = datetime.datetime.strptime(m.group("date"), "%d/%m/%Y").date()
        except ValueError:
            continue
        tp = _parse_tp(m.group("tp"))
        # đơn vị: 24hmoney ghi bằng ĐỒNG (vd 103,800) — giữ nguyên VND
        rating_raw = m.group("rating")
        rating = re.sub(r"\s+", " ", rating_raw).strip().upper() if rating_raw else "KHÔNG RÕ"
        key = (broker, rep_date)
        if key in seen or tp <= 0:
            continue
        seen.add(key)
        out.append({
            "ticker": ticker.upper(), "broker": broker, "report_date": rep_date,
            "target_price": tp, "rating": rating,
            "source_url": url,
            "raw_quote": f"{broker} {rep_date}: {rating}, giá mục tiêu {tp:,.0f} VND (nguồn 24hmoney)",
        })
    return out


# ---------------------------------------------------------------------------
# GĐ2 — Bóc TÓM TẮT LUẬN ĐIỂM từng báo cáo (để AI tổng hợp điểm chung/riêng).
# Mỗi báo cáo trên trang mã có link chi tiết .../bao-cao-phan-tich/...rpIdN.html,
# trong đó có đoạn tóm tắt luận điểm (động lực, dự phóng, upside). Chỉ lưu nội
# bộ tham khảo — KHÔNG tải/phát tán PDF gốc có bản quyền.
# ---------------------------------------------------------------------------

# Ghép: <a href="/bao-cao-phan-tich/...rpId123.html" ... class="title" ...>Tiêu đề</a>
#        ... Nguồn: BROKER-DD/MM/YYYY
_LINK_PATTERN = re.compile(
    r'href="(?P<href>/bao-cao-phan-tich/[^"]*rpId\d+\.html)"[^>]*class="title"[^>]*>'
    r'(?P<title>[^<]+)</a>.*?Nguồn:\s*(?P<broker>[A-Za-z0-9]+)-(?P<date>\d{2}/\d{2}/\d{4})',
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(html: str) -> str:
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", _html.unescape(html)).strip()


def report_links(ticker: str, timeout: float = 20.0) -> List[Dict[str, Any]]:
    """Danh sách link báo cáo chi tiết + broker/ngày cho 1 mã. KHÔNG chạm DB."""
    url = f"{_BASE}{ticker.upper()}"
    resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    out: List[Dict[str, Any]] = []
    seen = set()
    for m in _LINK_PATTERN.finditer(resp.text):
        broker = m.group("broker").upper().strip()
        try:
            rep_date = datetime.datetime.strptime(m.group("date"), "%d/%m/%Y").date()
        except ValueError:
            continue
        key = (broker, rep_date)
        if key in seen:
            continue
        seen.add(key)
        title = _html.unescape(m.group("title").strip())
        # tiêu đề: "FPT: Khuyến nghị MUA với giá mục tiêu 103,800 đồng/cổ phiếu"
        tm = re.search(
            r"Khuyến nghị\s+(?P<rating>.+?)\s+với giá mục tiêu\s+(?P<tp>[\d.,]+)",
            title, re.IGNORECASE)
        rating = re.sub(r"\s+", " ", tm.group("rating")).strip().upper() if tm else None
        tp = _parse_tp(tm.group("tp")) if tm else None
        out.append({
            "ticker": ticker.upper(), "broker": broker, "report_date": rep_date,
            "detail_url": _ORIGIN + m.group("href"),
            "title": title, "rating": rating, "target_price": tp,
        })
    return out


def _extract_body(detail_html: str) -> str:
    """Lấy đoạn tóm tắt luận điểm (giữa 'Tải về' và mục 'Báo cáo mã ...')."""
    txt = _strip_tags(detail_html)
    m = re.search(r"Tải về\s+(.*?)\s+(?:Báo cáo mã bạn đang theo dõi|Xem tất cả|$)", txt)
    return m.group(1).strip() if m else ""


def fetch_report_summaries(ticker: str, timeout: float = 20.0) -> List[Dict[str, Any]]:
    """Lấy tóm tắt luận điểm từng CTCK cho 1 mã (fetch từng trang chi tiết)."""
    out: List[Dict[str, Any]] = []
    for rep in report_links(ticker, timeout=timeout):
        try:
            resp = httpx.get(rep["detail_url"], headers={"User-Agent": _UA},
                             timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            summary = _extract_body(resp.text)
        except Exception:
            summary = ""
        if summary:
            rep = {**rep, "summary": summary}
            out.append(rep)
    return out


def import_broker_reports(ticker: str) -> List[Dict[str, Any]]:
    """Lấy + ghi khuyến nghị CTCK cho 1 mã vào consensus_history (idempotent)."""
    recs = fetch_broker_reports(ticker)
    if not recs:
        return []
    from valuation.ingest.broker_names import normalize_broker

    db = SessionLocalWrite()
    try:
        for rec in recs:
            # D24: ghi kèm tên chuẩn hoá + nguồn để dedup đồng thuận đúng theo
            # CTCK. `broker` gốc giữ nguyên (nằm trong PK, không sửa tại chỗ).
            canon, _ = normalize_broker(rec["broker"])
            row = {**rec, "broker_canon": canon, "source_site": "24HMONEY",
                   "currency_unit": "VND", "is_synthetic": False}
            stmt = dialect_insert(db, Consensus).values(row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker", "broker", "report_date"],
                set_={
                    "target_price": stmt.excluded.target_price,
                    "rating": stmt.excluded.rating,
                    "source_url": stmt.excluded.source_url,
                    "raw_quote": stmt.excluded.raw_quote,
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
