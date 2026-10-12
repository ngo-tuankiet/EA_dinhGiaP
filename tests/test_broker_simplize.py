"""Test parser Simplize (offline — không chạm mạng)."""
import datetime
from unittest.mock import patch

from valuation.ingest.scrapers import broker_simplize as sz

_SAMPLE = {"status": 200, "total": 3, "data": [
    {"source": "FPTS", "issueDate": "19/06/2026", "title": "MUA - định giá lần đầu",
     "attachedLink": "https://cdn.simplize.vn/report/FPT/a.pdf", "targetPrice": 94700.0, "recommend": "MUA"},
    {"source": "Vietcap", "issueDate": "10/06/2026", "title": "OUTPERFORM",
     "attachedLink": "https://cdn.simplize.vn/report/FPT/b.pdf", "targetPrice": 101600.0, "recommend": "KHẢ QUAN"},
    # báo cáo ngành không có giá mục tiêu -> phải bị bỏ
    {"source": "MBS", "issueDate": "01/06/2026", "title": "Báo cáo ngành CNTT",
     "attachedLink": "", "targetPrice": None, "recommend": None},
]}


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


def test_fetch_filters_and_parses():
    with patch.object(sz.httpx, "get", return_value=_Resp(_SAMPLE)):
        recs = sz.fetch_reports("FPT")
    assert len(recs) == 2  # bỏ báo cáo ngành không có giá mục tiêu
    brokers = {r["broker"] for r in recs}
    assert brokers == {"FPTS", "VIETCAP"}  # chuẩn hóa hoa
    fpts = next(r for r in recs if r["broker"] == "FPTS")
    assert fpts["target_price"] == 94700.0
    assert fpts["rating"] == "MUA"
    assert fpts["report_date"] == datetime.date(2026, 6, 19)
    assert fpts["source_url"].endswith(".pdf")


def test_fetch_dedup_same_broker_date():
    dup = {"data": _SAMPLE["data"] + [dict(_SAMPLE["data"][0])]}
    with patch.object(sz.httpx, "get", return_value=_Resp(dup)):
        recs = sz.fetch_reports("FPT")
    assert len(recs) == 2  # FPTS trùng ngày không tạo dòng mới


def test_fetch_empty_no_crash():
    with patch.object(sz.httpx, "get", return_value=_Resp({"data": []})):
        assert sz.fetch_reports("XYZ") == []


def test_parse_date_invalid():
    assert sz._parse_date("khong-hop-le") is None
    assert sz._parse_date("19/06/2026") == datetime.date(2026, 6, 19)
