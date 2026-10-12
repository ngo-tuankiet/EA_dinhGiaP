"""Chặn công bố khi có sự kiện trọng yếu mô hình chưa phản ánh (D46).

PNJ: vụ án P-Lab, HĐQT trình kế hoạch 2026 lỗ 6.271 tỷ và phát hành riêng lẻ ~107% số cp
(25/09/2026) → BCTC quý và giá mục tiêu CTCK đều lập trước biến cố, mô hình ra +133% "MUA".
"""

from datetime import date

from valuation.config import active_event_hold
from valuation.db.session import SessionLocalRead as SessionLocal
from valuation.engine.batch import value_ticker


def test_hold_active_from_since_date_until_lifted():
    holds = {
        "XYZ": {
            "since": "2026-09-25",
            "reason": "lỗ lớn chưa vào BCTC",
            "source": "CBTT",
        }
    }
    assert active_event_hold("XYZ", date(2026, 9, 24), holds) is None
    assert (
        active_event_hold("xyz", date(2026, 9, 25), holds)["reason"]
        == "lỗ lớn chưa vào BCTC"
    )
    assert active_event_hold("ABC", date(2026, 10, 1), holds) is None


def test_hold_requires_reason_and_source():
    # Chặn công bố là quyết định có trách nhiệm giải trình: thiếu lý do/nguồn → lỗi rõ ràng.
    import pytest

    with pytest.raises(ValueError):
        active_event_hold("XYZ", date(2026, 10, 1), {"XYZ": {"since": "2026-09-25"}})


def test_pnj_not_published_while_event_hold_active():
    db = SessionLocal()
    try:
        res = value_ticker(db, "PNJ")
    finally:
        db.close()
    assert res.get("fair_value") is None
    assert res["recommendation"] == "NOT_RATED"
    assert "MATERIAL_EVENT_HOLD" in res["flags"]
