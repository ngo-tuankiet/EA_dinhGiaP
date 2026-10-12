"""Test GĐ2 — bóc tóm tắt luận điểm đa-CTCK + AI tổng hợp (offline, không chạm mạng/LLM)."""
import datetime
import json
from unittest.mock import patch

from valuation.ingest.scrapers import broker_24hmoney as b24
from valuation.engine import consensus_synthesis as cs

# Trang mã: mỗi báo cáo là 1 <a ... class="title">Tiêu đề</a> + "Nguồn: BROKER-DATE".
_STOCK_HTML = """
<a href="/bao-cao-phan-tich/fpt-rpId5465.html" class="title" data-v>FPT: Khuyến nghị MUA với giá mục tiêu 103,800 đồng/cổ phiếu</a>
<p class="report-source">Nguồn: KBSV-08/06/2026</p>
<a href="/bao-cao-phan-tich/fpt-rpId5354.html" class="title" data-v>FPT: Khuyến nghị KHẢ QUAN với giá mục tiêu 90,600 đồng/cổ phiếu</a>
<p class="report-source">Nguồn: BSC-18/05/2026</p>
"""

_DETAIL_HTML = """
<html><body>
<h1>FPT</h1> Nguồn: KBSV Ngày phát hành: 08/06/2026 Số lượt tải về: 33
<button>Tải về</button>
KBSV duy trì khuyến nghị MUA với giá mục tiêu 103.800 đồng, upside 42,4%. Động lực chính từ CNTT nước ngoài.
<div>Báo cáo mã bạn đang theo dõi</div>
</body></html>
"""


def _mock_get(url, **kwargs):
    class _Resp:
        def __init__(self, text): self.text = text
        def raise_for_status(self): pass
    return _Resp(_STOCK_HTML if "/stock/" in url else _DETAIL_HTML)


def test_report_links_parses_broker_tp_rating():
    with patch.object(b24.httpx, "get", side_effect=_mock_get):
        links = b24.report_links("FPT")
    assert len(links) == 2
    kbsv = next(l for l in links if l["broker"] == "KBSV")
    assert kbsv["target_price"] == 103800.0
    assert kbsv["rating"] == "MUA"
    assert kbsv["report_date"] == datetime.date(2026, 6, 8)
    assert kbsv["detail_url"].endswith("rpId5465.html")
    bsc = next(l for l in links if l["broker"] == "BSC")
    assert bsc["rating"] == "KHẢ QUAN"
    assert bsc["target_price"] == 90600.0


def test_fetch_summaries_extracts_body():
    with patch.object(b24.httpx, "get", side_effect=_mock_get):
        sums = b24.fetch_report_summaries("FPT")
    assert len(sums) == 2
    assert all(s["summary"] for s in sums)
    kbsv = next(s for s in sums if s["broker"] == "KBSV")
    assert "khuyến nghị MUA" in kbsv["summary"]
    # cắt đúng: không dính phần "Báo cáo mã bạn đang theo dõi"
    assert "Báo cáo mã" not in kbsv["summary"]


def test_extract_body_empty_when_no_marker():
    assert b24._extract_body("<html>không có nội dung</html>") == ""


class _FakeChat:
    def __init__(self, payload): self._payload = payload
    @property
    def chat(self): return self
    @property
    def completions(self): return self
    def create(self, **kwargs):
        class _M: content = json.dumps(self._payload, ensure_ascii=False)
        class _C: message = _M()
        class _R: choices = [_C()]
        return _R()


def test_synthesize_normalizes_shape():
    payload = {
        "diem_chung": ["Đồng thuận MUA", "Động lực CNTT nước ngoài"],
        "diem_rieng": "Giá mục tiêu chênh lệch KBSV vs BSC",   # str -> list
        "diem_mau_chot": ["Mô hình phí theo đầu ra"],
        "doi_chieu_noi_bo": ["Nội bộ thấp hơn"],               # list -> str
    }
    summaries = [{"broker": "KBSV", "report_date": datetime.date(2026, 6, 8),
                  "summary": "abc", "target_price": 103800.0}]
    out = cs.synthesize_from_summaries("FPT", summaries, internal=None,
                                       client=_FakeChat(payload))
    assert isinstance(out["diem_rieng"], list) and len(out["diem_rieng"]) == 1
    assert isinstance(out["doi_chieu_noi_bo"], str)
    assert out["diem_chung"] == payload["diem_chung"]


def test_synthesize_empty_summaries_returns_empty():
    assert cs.synthesize_from_summaries("FPT", [], client=_FakeChat({})) == {}
