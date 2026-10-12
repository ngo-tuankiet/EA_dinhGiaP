from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import json

import pytest

from valuation.analysis.investment_ranking import load_ranking_config
from valuation.report.accumulation_review import (
    generate_review,
    review_payload,
    validate_review,
)


def snapshot() -> dict:
    profiles = {
        key: {"score": 70, "eligible": False, "rank_change": None}
        for key in ("defensive", "growth")
    }
    return {
        "rows": [{"ticker": "ACB", "sector": "NH", "profiles": profiles}],
        "selections": {key: {"qualified": [], "research": ["ACB"]} for key in profiles},
        "news": {"items": []},
    }


def content() -> str:
    pick = {
        "ticker": "ACB",
        "medium_term": "Cần kiểm tra dữ liệu trước khi tư vấn.",
        "long_term": "Theo dõi chất lượng kinh doanh nhiều năm.",
        "reasons": ["Chỉ là ứng viên"],
        "risks": ["Thiếu bằng chứng"],
        "invalid_if": "BCTC hoặc mô hình không đáng tin cậy.",
        "source_ids": ["DATA:ACB"],
    }
    return json.dumps(
        {
            "defensive": {
                "overview": "Chưa đủ cơ sở khuyến nghị mua.",
                "picks": [pick],
            },
            "growth": {"overview": "Cần kiểm chứng trước khi tư vấn.", "picks": [pick]},
            "counterargument": "Danh sách định lượng không bảo đảm an toàn hoặc sinh lời.",
        }
    )


class FakeClient:
    def __init__(self, *, failure=False, finish="stop"):
        self.chat = SimpleNamespace(completions=self)
        self.calls = 0
        self.failure = failure
        self.finish = finish

    def create(self, **kwargs):
        self.calls += 1
        if self.failure:
            raise TimeoutError("Không được log nội dung lỗi API chứa secret")
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason=self.finish,
                    message=SimpleNamespace(content=content()),
                )
            ],
            usage=None,
        )


@pytest.mark.parametrize(
    "failure,finish,status",
    [(False, "stop", "SUCCESS"), (True, "stop", "FAILED"), (False, "length", "FAILED")],
)
def test_one_call_even_on_error_or_truncation(tmp_path, failure, finish, status):
    cfg, data = load_ranking_config(), snapshot()
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    client = FakeClient(failure=failure, finish=finish)
    first = generate_review(data, cfg, tmp_path, now, client=client)
    data["rows"][0]["profiles"]["defensive"]["rank_change"] = 0
    second = generate_review(data, cfg, tmp_path, now, client=client)
    assert client.calls == 1
    assert first["status"] == second["status"] == status
    assert second["cache_hit"]
    assert "secret" not in json.dumps(second)


def test_real_input_change_invalidates_cache(tmp_path):
    cfg, data = load_ranking_config(), snapshot()
    client = FakeClient()
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    generate_review(data, cfg, tmp_path, now, client=client)
    data["rows"][0]["price"] = 20000
    generate_review(data, cfg, tmp_path, now, client=client)
    assert client.calls == 2


@pytest.mark.parametrize(
    "field,value",
    [("ticker", "FAKE"), ("source_ids", ["NEWS:FAKE"]), ("source_ids", [])],
)
def test_ai_cannot_add_ticker_or_source(field, value):
    cfg = load_ranking_config()
    result = json.loads(content())
    result["defensive"]["picks"][0][field] = value
    with pytest.raises(ValueError):
        validate_review(json.dumps(result), review_payload(snapshot(), cfg), cfg)


def test_no_truncate_or_bill_when_payload_too_big(tmp_path):
    cfg = deepcopy(load_ranking_config())
    cfg["ai_max_input_chars"] = 1
    client = FakeClient()
    result = generate_review(
        snapshot(),
        cfg,
        tmp_path,
        datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
        client=client,
    )
    assert client.calls == 0
    assert result["status"] == "SKIPPED"
