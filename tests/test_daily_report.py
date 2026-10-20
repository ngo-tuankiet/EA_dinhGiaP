from datetime import date

from valuation.services.daily_report import (
    build_message,
    changes,
    previous_report,
    session_moves,
)
from valuation.services.ranking_store import write_json

CFG = {
    "top_n": 5,
    "price_move_pct": 5,
    "snapshot_stale_days": 14,
    "price_stale_days": 4,
    "max_lines": 10,
}


def _state(
    picks, notes, moves, price_date="2026-10-19", completed="2026-10-13T09:50:00+07:00"
):
    return {
        "date": "2026-10-20",
        "price_date": price_date,
        "snapshot": {"run_id": "R1", "completed_at": completed},
        "max_per_sector": 2,
        "picks": [
            {
                "ticker": t,
                "price": 100.0,
                "fair_value": 150.0,
                "upside": 50.0,
                "sector": "X",
            }
            for t in picks
        ],
        "notes": notes,
        "moves": moves,
        "macro_lines": [],
    }


def test_session_moves_hand_calculated():
    d1, d2, d0 = date(2026, 10, 16), date(2026, 10, 19), date(2026, 10, 15)
    rows = [
        ("AAA", d2, 105.0),
        ("AAA", d1, 100.0),  # +5,00% (thứ tự lộn xộn vẫn đúng)
        ("BBB", d1, 50.0),
        ("BBB", d2, 46.5),  # 46,5/50 − 1 = −7,00%
        ("CCC", d0, 10.0),
        ("CCC", d1, 11.0),  # không giao dịch phiên 19/10 → bỏ
        ("DDD", d2, 20.0),  # chỉ 1 phiên → bỏ
    ]
    assert session_moves(rows, d2) == {"AAA": 5.0, "BBB": -7.0}


def test_changes_entered_left_notes_movers():
    prev = _state(
        ["A", "B", "C"], {"A": "", "B": "", "C": ""}, {}, price_date="2026-10-16"
    )
    cur = _state(
        ["B", "C", "D"],
        {"A": "", "B": "", "C": "Lỗi dữ liệu: NOT_RATED"},
        {"A": 6.2, "B": -5.0, "C": 4.99},
    )
    chg = changes(prev, cur, 5)
    assert chg["entered"] == ["D"] and chg["left"] == ["A"]
    assert chg["notes"] == [("C", "", "Lỗi dữ liệu: NOT_RATED")]
    assert chg["movers"] == [("A", 6.2), ("B", -5.0)]  # |−5,0| ≥ 5 tính; 4,99 không


def test_changes_no_new_session_hides_movers_and_first_report():
    prev = _state(["A"], {"A": ""}, {"A": 9.0})
    cur = _state(["A"], {"A": ""}, {"A": 9.0})
    chg = changes(prev, cur, 5)
    assert chg["new_session"] is False and chg["movers"] == []
    assert changes(None, cur, 5) is None


def test_build_message_format_and_stale_warnings():
    state = _state(["FPT"], {"FPT": ""}, {}, completed="2026-09-29T09:00:00+07:00")
    state["picks"] = [
        {
            "ticker": "FPT",
            "price": 57100.0,
            "fair_value": 87848.0,
            "upside": 53.85,
            "sector": "Công nghệ",
        }
    ]
    msg = build_message(
        state,
        None,
        {
            "skipped": None,
            "price_errors": ["XYZ: FAILED"],
            "macro_errors": [],
            "price_total": 102,
        },
        CFG,
        date(2026, 10, 20),
    )
    picks, diff, _ = (f["value"] for f in msg["fields"])
    assert picks == "**FPT** 57.100 → FV 87.848 (+53,9%) · Công nghệ"
    assert diff == "Chưa có báo cáo trước để so sánh."
    assert "21 ngày trước" in msg["embed_desc"]  # 29/09 → 20/10 > 14 ngày
    assert "1/102 mã không cập nhật được giá: XYZ" in msg["embed_desc"]
    assert "R1" in msg["footer"]


def test_previous_report_skips_today(tmp_path):
    for day in ("2026-10-16", "2026-10-19", "2026-10-20"):
        write_json(tmp_path / "history" / f"{day}.json", {"date": day})
    assert previous_report(date(2026, 10, 20), tmp_path) == {"date": "2026-10-19"}
    assert previous_report(date(2026, 10, 16), tmp_path) is None
