"""Test parser khuyến nghị đa-CTCK từ 24hmoney (offline — không chạm mạng)."""
import datetime
from unittest.mock import patch

import pytest

from valuation.ingest.scrapers import broker_24hmoney as b24

# HTML mẫu mô phỏng đúng cấu trúc SSR 24hmoney (nhiều CTCK).
_SAMPLE = """
<div>FPT: Khuyến nghị MUA với giá mục tiêu 103,800 đồng/cổ phiếu Nguồn: KBSV-08/06/2026 Tải về</div>
<div>FPT: Khuyến nghị KHẢ QUAN với giá mục tiêu 90,600 đồng/cổ phiếu Nguồn: BSC-18/05/2026 Tải về</div>
<div>FPT: Khuyến nghị TÍCH LŨY với giá mục tiêu 92,000 đồng/cổ phiếu Nguồn: MIRAE-22/04/2026 Tải về</div>
"""


def test_parse_extracts_all_brokers():
    class _Resp:
        text = _SAMPLE
        def raise_for_status(self): pass
    with patch.object(b24.httpx, "get", return_value=_Resp()):
        recs = b24.fetch_broker_reports("FPT")
    assert len(recs) == 3
    brokers = {r["broker"] for r in recs}
    assert brokers == {"KBSV", "BSC", "MIRAE"}


def test_parse_fields_correct():
    class _Resp:
        text = _SAMPLE
        def raise_for_status(self): pass
    with patch.object(b24.httpx, "get", return_value=_Resp()):
        recs = b24.fetch_broker_reports("FPT")
    kbsv = next(r for r in recs if r["broker"] == "KBSV")
    assert kbsv["target_price"] == 103800.0          # '103,800' -> 103800
    assert kbsv["rating"] == "MUA"
    assert kbsv["report_date"] == datetime.date(2026, 6, 8)
    assert kbsv["ticker"] == "FPT"
    assert "24hmoney" in kbsv["source_url"]


def test_parse_dedup_same_broker_date():
    dup = _SAMPLE + '<div>FPT: Khuyến nghị MUA với giá mục tiêu 103,800 đồng/cổ phiếu Nguồn: KBSV-08/06/2026</div>'
    class _Resp:
        text = dup
        def raise_for_status(self): pass
    with patch.object(b24.httpx, "get", return_value=_Resp()):
        recs = b24.fetch_broker_reports("FPT")
    assert len(recs) == 3  # KBSV lặp không tạo dòng mới


def test_parse_empty_html_no_crash():
    class _Resp:
        text = "<html>no reports here</html>"
        def raise_for_status(self): pass
    with patch.object(b24.httpx, "get", return_value=_Resp()):
        assert b24.fetch_broker_reports("XYZ") == []


def test_parse_tp_thousands_separator():
    assert b24._parse_tp("103,800") == 103800.0
    assert b24._parse_tp("1.234.500") == 1234500.0
