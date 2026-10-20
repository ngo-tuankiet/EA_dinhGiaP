from datetime import date

import valuation.services.assistant as a

CFG = {
    "daily_limit_per_user": 2,
    "quota_exempt_ids": [7],
    "max_calls": 3,
    "max_tickers": 5,
    "max_rows": 30,
    "max_sessions": 250,
    "data_chars": 12000,
    "plan_max_tokens": 400,
    "answer_max_tokens": 1000,
}
U = frozenset({"FPT", "MBB", "TCB", "HPG", "VNM", "AAA", "BBB", "CCC"})


def test_validate_filters_tools_tickers_and_clamps():
    plan = {
        "calls": [
            {"tool": "valuate", "args": {"tickers": ["mbb", "tcb", "XYZ"]}},
            {"tool": "run_sql", "args": {"q": "drop table"}},
            {"tool": "ranking", "args": {"sector": "Ngân hàng", "top": 999}},
            {"tool": "macro", "args": {}},
        ]
    }
    calls, notes = a.validate(plan, U, CFG)
    assert calls == [
        ("valuate", {"tickers": ["MBB", "TCB"]}),
        ("ranking", {"sector": "Ngân hàng", "top": 30, "include_excluded": False}),
    ]
    assert any("XYZ" in n for n in notes) and any("run_sql" in n for n in notes)
    assert any("3 việc" in n for n in notes)  # 4 công cụ → cắt còn 3 (macro bị cắt)


def test_validate_drops_calls_without_valid_ticker_and_bad_plan():
    calls, _ = a.validate(
        {
            "calls": [
                {"tool": "consensus", "args": {"ticker": "ZZZ"}},
                {"tool": "valuate", "args": {"tickers": []}},
            ]
        },
        U,
        CFG,
    )
    assert calls == []
    assert a.validate("not json", U, CFG)[0] == []
    calls, _ = a.validate(
        {"calls": [{"tool": "price_moves", "args": {"sessions": "abc", "top": 0}}]},
        U,
        CFG,
    )
    assert calls == [("price_moves", {"tickers": [], "sessions": 5, "top": 1})]


def test_take_quota_limit_reset_and_exempt(tmp_path):
    d1, d2 = date(2026, 10, 20), date(2026, 10, 21)
    assert a.take_quota(1, CFG, d1, tmp_path) == (True, 1)
    assert a.take_quota(1, CFG, d1, tmp_path) == (True, 0)
    assert a.take_quota(1, CFG, d1, tmp_path) == (False, 0)  # lượt thứ 3 > giới hạn 2
    assert a.take_quota(2, CFG, d1, tmp_path) == (True, 1)  # người khác đếm riêng
    assert a.take_quota(1, CFG, d2, tmp_path) == (True, 1)  # sang ngày mới reset
    assert a.take_quota(7, CFG, d1, tmp_path) == (True, None)  # miễn giới hạn


def test_moves_over_hand_calculated():
    days = [date(2026, 10, d) for d in (13, 14, 15, 16, 19, 20)]
    rows = [("AAA", d, c) for d, c in zip(days, [100, 101, 99, 104, 108, 110])]
    rows += [("BBB", days[-1], 50.0)]  # 1 phiên → không đủ
    m = a.moves_over(rows, 5)
    assert m == {
        "AAA": {
            "pct": 10.0,
            "from": "2026-10-13",
            "to": "2026-10-20",
            "close_from": 100,
            "close_to": 110,
        }
    }


def test_news_filter_by_ticker_and_query(monkeypatch):
    feed = {
        "checked_at": "2026-10-20T08:00:00+07:00",
        "items": [
            {
                "title": "HPG báo lãi quý 3 tăng",
                "url": "https://x/1",
                "published": "2026-10-19",
            },
            {
                "title": "NHNN giữ lãi suất điều hành",
                "url": "https://x/2",
                "published": "2026-10-18",
            },
            {"title": "Giá vàng giảm", "url": "https://x/3", "published": "2026-10-17"},
        ],
    }
    monkeypatch.setattr(
        "valuation.services.ranking_sources.fetch_news", lambda *_: feed
    )
    assert [i["url"] for i in a.tool_news(None, ["HPG"], 10)["items"]] == [
        "https://x/1"
    ]
    assert [i["url"] for i in a.tool_news("lãi suất", [], 10)["items"]] == [
        "https://x/2"
    ]
    assert len(a.tool_news(None, [], 2)["items"]) == 2


def test_ask_unsupported_skips_second_call(monkeypatch):
    monkeypatch.setattr(a, "_cfg", lambda: CFG)
    monkeypatch.setattr(a, "vn100", lambda: U)
    monkeypatch.setattr(
        a,
        "plan_request",
        lambda *_: {"calls": [], "unsupported": "không liên quan chứng khoán"},
    )
    called = []
    monkeypatch.setattr(a, "write_answer", lambda *x: called.append(x))
    res = a.ask("viết code cho tôi")
    assert "Chưa hỗ trợ" in res["answer"] and called == []


def test_ask_runs_tools_and_reports_tool_error(monkeypatch):
    monkeypatch.setattr(a, "_cfg", lambda: CFG)
    monkeypatch.setattr(a, "vn100", lambda: U)
    monkeypatch.setattr(
        a,
        "plan_request",
        lambda *_: {
            "calls": [
                {"tool": "macro"},
                {"tool": "consensus", "args": {"ticker": "VNM"}},
            ]
        },
    )

    def boom(ticker):
        raise ValueError("DB lỗi")

    monkeypatch.setitem(
        a.TOOLS,
        "macro",
        (lambda: {"lines": ["CPI VN (YoY): **5,08%**"], "dates": {}}, "", ""),
    )
    monkeypatch.setitem(a.TOOLS, "consensus", (boom, "", ""))
    seen = {}
    monkeypatch.setattr(
        a,
        "write_answer",
        lambda text, results, cfg: seen.setdefault("r", results) and "ok",
    )
    res = a.ask("CPI và khuyến nghị VNM")
    assert res["answer"] == "ok"
    assert (
        seen["r"][1]["error"] == "ValueError: DB lỗi"
    )  # lỗi công cụ hiện rõ, không nuốt
    assert "5,08%" in res["sources"] and "consensus**: lỗi" in res["sources"]
