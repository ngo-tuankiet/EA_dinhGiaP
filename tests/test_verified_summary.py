import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.data_access.repo import _match_value
from valuation.db.models import ConsensusSynthesis, Ticker
from valuation.db.session import Base
from valuation.models.financials import (
    Assumptions,
    BalanceSheet,
    CashFlow,
    Company,
    IncomeStatement,
)
from valuation.report.verified_summary import (
    _compact_payload,
    collect_consensus_context,
    collect_market_context,
    generate_verified_summary,
    generate_verified_summary_cached,
    legacy_verified_summary_session_keys,
    normalized_report_sections,
    persist_consensus_synthesis,
    report_markdown,
    run_deterministic_checks,
    verified_summary_session_key,
)


def _company(*, bad_gross_profit: bool = False) -> Company:
    return Company(
        ticker="AAA",
        name="Công ty kiểm thử",
        sector="Consumer",
        current_price=20_000,
        shares_outstanding=100,
        historical_is=[
            IncomeStatement(
                year=2025,
                revenue=1_000,
                cogs=700,
                gross_profit=450 if bad_gross_profit else 300,
                opex=100,
                ebit=200,
                interest_expense=20,
                tax=36,
                net_income=144,
            )
        ],
        historical_bs=[
            BalanceSheet(
                year=2025,
                cash_and_equivalents=100,
                receivables=100,
                inventory=100,
                other_current_assets=100,
                fixed_assets=500,
                other_long_term_assets=100,
                total_assets=1_000,
                short_term_debt=100,
                accounts_payable=100,
                other_current_liabilities=100,
                long_term_debt=100,
                other_long_term_liabilities=100,
                total_equity=500,
            )
        ],
        historical_cf=[CashFlow(year=2025, cfo=150, capex=-50)],
        assumptions=Assumptions(
            revenue_growth=[0.08] * 5,
            ebit_margin=[0.20] * 5,
            capex_to_revenue=[0.05] * 5,
            depr_to_revenue=[0.03] * 5,
            dso=[30] * 5,
            dio=[30] * 5,
            dpo=[30] * 5,
            interest_rate=[0.07] * 5,
        ),
    )


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = (
            '{"audit_status":"OK","audit_findings":[],"thesis":"Luận điểm",'
            '"overview":"Tổng quan","industry":"Ngành","risks":"Rủi ro",'
            '"market_view":"Giá và khối lượng đang cần theo dõi.",'
            '"consensus_synthesis":{"diem_chung":["Cùng khuyến nghị mua"],'
            '"diem_rieng":["Giá mục tiêu khác nhau"],'
            '"diem_mau_chot":["Theo dõi tăng trưởng"],'
            '"doi_chieu_noi_bo":"Mô hình nội bộ cao hơn đồng thuận."}}'
        )
        return SimpleNamespace(
            model=kwargs["model"],
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        )


def test_deterministic_checks_accept_balanced_financials():
    issues = run_deterministic_checks(_company(), blended_fv=25_000, upside=25.0)
    assert issues == []


def test_match_value_prefers_exact_line_item_over_legacy_prefix():
    data = {
        "minority_interests_before_2015": 0.0,
        "minority_interests": 2_011_756_720_004.0,
    }

    assert _match_value(data, ["minority_interests"]) == 2_011_756_720_004.0


def test_ai_payload_derives_quality_metrics_from_financials():
    payload = _compact_payload(
        _company(),
        blended_fv=25_000,
        current_price=20_000,
        upside=25.0,
        recommendation="BUY",
        deterministic_issues=[],
    )

    metrics = payload["quality_metrics"]
    assert metrics["roe"] == pytest.approx(144 / 500)
    assert metrics["roic"] == pytest.approx(160 / 600)
    assert metrics["debt_to_equity"] == pytest.approx(200 / 500)
    assert metrics["net_debt_to_ebitda"] == pytest.approx(100 / 200)


def test_ai_payload_explains_engine_flags():
    company = _company()
    company.data_flags = ["STALE_PRICE"]

    payload = _compact_payload(
        company,
        blended_fv=25_000,
        current_price=20_000,
        upside=25.0,
        recommendation="BUY",
        deterministic_issues=run_deterministic_checks(
            company, blended_fv=25_000, upside=25.0
        ),
    )

    assert payload["flag_explanations"][0]["code"] == "STALE_PRICE"
    assert "Giá thị trường" in payload["flag_explanations"][0]["message"]


def test_deterministic_checks_detect_income_statement_error():
    issues = run_deterministic_checks(
        _company(bad_gross_profit=True), blended_fv=25_000, upside=25.0
    )
    assert {item["code"] for item in issues} >= {
        "GROSS_PROFIT_MISMATCH",
        "EBIT_MISMATCH",
    }


def test_generate_verified_summary_uses_exactly_one_non_thinking_call():
    completions = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = generate_verified_summary(
        company=_company(),
        blended_fv=25_000,
        current_price=20_000,
        upside=25.0,
        recommendation="BUY",
        client=client,
    )

    assert result["ai_generated"] is True
    assert result["status"] == "OK"
    assert len(completions.calls) == 1
    assert completions.calls[0]["model"] == "deepseek-v4-flash"
    assert completions.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_identical_inputs_reuse_disk_cache_without_second_api_call(tmp_path):
    completions = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    arguments = {
        "company": _company(),
        "blended_fv": 25_000,
        "current_price": 20_000,
        "upside": 25.0,
        "recommendation": "BUY",
        "client": client,
        "cache_dir": tmp_path,
    }

    first = generate_verified_summary_cached(**arguments)
    second = generate_verified_summary_cached(**arguments)

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert len(completions.calls) == 1


def test_changed_financial_input_invalidates_ai_cache(tmp_path):
    completions = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    first_company = _company()
    second_company = _company()
    second_company.historical_is[-1].revenue = 1_001

    for company in (first_company, second_company):
        generate_verified_summary_cached(
            company=company,
            blended_fv=25_000,
            current_price=20_000,
            upside=25.0,
            recommendation="BUY",
            client=client,
            cache_dir=tmp_path,
        )

    assert len(completions.calls) == 2


def test_force_regeneration_bypasses_identical_input_cache(tmp_path):
    completions = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    arguments = {
        "company": _company(),
        "blended_fv": 25_000,
        "current_price": 20_000,
        "upside": 25.0,
        "recommendation": "BUY",
        "client": client,
        "cache_dir": tmp_path,
    }

    generate_verified_summary_cached(**arguments)
    forced = generate_verified_summary_cached(**arguments, force=True)

    assert forced["cache_hit"] is False
    assert len(completions.calls) == 2


def test_source_check_timestamp_does_not_invalidate_ai_cache(tmp_path):
    completions = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    base = {
        "available": True,
        "events": [{"event_type": "CASH_DIVIDEND", "effective_date": "2026-09-01"}],
    }
    for checked_at in ("2026-08-30T08:00:00", "2026-08-30T09:00:00"):
        generate_verified_summary_cached(
            company=_company(),
            blended_fv=25_000,
            current_price=20_000,
            upside=25.0,
            recommendation="BUY",
            corporate_actions_context={**base, "last_checked_at": checked_at},
            client=client,
            cache_dir=tmp_path,
        )

    assert len(completions.calls) == 1


def test_one_call_generates_report_and_consensus_together():
    completions = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    context = collect_consensus_context(
        ticker="AAA",
        blended_fv=25_000,
        current_price=20_000,
        fetcher=lambda ticker, timeout: [
            {
                "broker": "SSI",
                "report_date": "2026-08-01",
                "target_price": 24_000,
                "rating": "MUA",
                "summary": "Doanh thu tăng và biên lợi nhuận cải thiện.",
            }
        ],
    )

    result = generate_verified_summary(
        company=_company(),
        blended_fv=25_000,
        current_price=20_000,
        upside=25.0,
        recommendation="BUY",
        consensus_context=context,
        client=client,
    )

    assert len(completions.calls) == 1
    assert result["report_sections"]["thesis"] == "Luận điểm"
    assert result["consensus_synthesis"]["diem_chung"] == ["Cùng khuyến nghị mua"]
    prompt = completions.calls[0]["messages"][1]["content"]
    assert '"consensus_ctck"' in prompt
    assert "Doanh thu tăng và biên lợi nhuận cải thiện" in prompt


def test_one_call_uses_corporate_actions_only_as_input_context():
    completions = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    event_context = {
        "available": True,
        "events": [
            {
                "event_type": "RIGHTS_ISSUE",
                "title": "Quyền mua 20%",
                "source_site": "VCI",
                "source_tier": "AGGREGATOR",
                "analysis": {
                    "eps_dilution_pct_before_new_profit": -16.67,
                    "data_warning": "Thiếu giá phát hành.",
                },
            }
        ],
    }

    result = generate_verified_summary(
        company=_company(),
        blended_fv=25_000,
        current_price=20_000,
        upside=25.0,
        recommendation="BUY",
        corporate_actions_context=event_context,
        client=client,
    )

    assert len(completions.calls) == 1
    assert "market_view" in result["report_sections"]
    assert "corporate_actions" not in result["report_sections"]
    prompt = completions.calls[0]["messages"][1]["content"]
    assert '"corporate_actions"' in prompt
    assert "Thiếu giá phát hành" in prompt
    assert "không tạo phần" in prompt
    assert "kỹ thuật/khối lượng" in prompt
    assert "không khẳng định thao túng" in prompt


def test_market_context_is_included_in_single_prompt():
    completions = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    market_context = {
        "available": True,
        "technical": {"available": True, "rsi14": 55, "volume_vs_20d_avg": 1.4},
        "sector_peers": {"available": True, "sector": "Consumer", "peers": []},
        "macro": {"available": True, "items": [{"code": "TPCP_10Y", "value": 0.046}]},
    }

    generate_verified_summary(
        company=_company(),
        blended_fv=25_000,
        current_price=20_000,
        upside=25.0,
        recommendation="BUY",
        market_context=market_context,
        client=client,
    )

    prompt = completions.calls[0]["messages"][1]["content"]
    assert '"market_context"' in prompt
    assert '"rsi14": 55' in prompt
    assert '"TPCP_10Y"' in prompt


def test_collect_market_context_without_db_is_explicit():
    context = collect_market_context(ticker="aaa", sector="Consumer", db=None)

    assert context["available"] is False
    assert context["ticker"] == "AAA"
    assert "Không có kết nối DB" in context["reason"]


def test_consensus_context_excludes_stale_and_future_reports():
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date()
    context = collect_consensus_context(
        ticker="AAA",
        blended_fv=25_000,
        current_price=20_000,
        fetcher=lambda ticker, timeout: [
            {
                "broker": "SSI",
                "report_date": today - datetime.timedelta(days=30),
                "target_price": 24_000,
                "summary": "Báo cáo hợp lệ.",
            },
            {
                "broker": "MBS",
                "report_date": today - datetime.timedelta(days=181),
                "target_price": 23_000,
                "summary": "Báo cáo đã cũ.",
            },
            {
                "broker": "VCBS",
                "report_date": today + datetime.timedelta(days=1),
                "target_price": 26_000,
                "summary": "Báo cáo tương lai.",
            },
        ],
    )

    assert context["n_reports"] == 1
    assert context["brokers"] == ["SSI"]


def test_persist_consensus_synthesis_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Ticker(ticker="AAA", company_name="Công ty kiểm thử"))
    db.commit()
    context = {
        "available": True,
        "n_reports": 2,
        "brokers": ["SSI", "MBS"],
        "internal_target_vnd": 25_000,
        "consensus_median_vnd": 23_500,
    }
    result = {
        "ai_generated": True,
        "model": "deepseek-v4-flash",
        "consensus_synthesis": {
            "diem_chung": ["Tăng trưởng"],
            "diem_rieng": ["Khác giá mục tiêu"],
            "diem_mau_chot": ["Biên lợi nhuận"],
            "doi_chieu_noi_bo": "Mô hình cao hơn đồng thuận.",
        },
    }

    assert persist_consensus_synthesis(
        result=result, context=context, ticker="AAA", db=db
    )
    result["consensus_synthesis"]["diem_chung"] = ["Tăng trưởng cập nhật"]
    assert persist_consensus_synthesis(
        result=result, context=context, ticker="AAA", db=db
    )

    rows = db.query(ConsensusSynthesis).all()
    assert len(rows) == 1
    assert rows[0].diem_chung == ["Tăng trưởng cập nhật"]
    db.close()


def test_error_escalates_single_call_to_pro_model():
    completions = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = generate_verified_summary(
        company=_company(bad_gross_profit=True),
        blended_fv=25_000,
        current_price=20_000,
        upside=25.0,
        recommendation="BUY",
        client=client,
    )

    assert result["status"] == "ERROR"
    assert len(completions.calls) == 1
    assert completions.calls[0]["model"] == "deepseek-v4-pro"


def test_session_key_is_stable_per_ticker():
    assert verified_summary_session_key("acb") == "verified_ai_summary_v8_ACB"
    assert "verified_ai_summary_v7_ACB" in legacy_verified_summary_session_keys("acb")


def test_normalized_report_sections_drops_legacy_corporate_actions():
    sections = normalized_report_sections(
        {
            "report_sections": {
                "thesis": "Luận điểm",
                "overview": "Tổng quan",
                "industry": "Ngành",
                "corporate_actions": "Cổ tức, tăng vốn và quyền cổ đông: nội dung cũ",
                "risks": "Rủi ro",
            }
        }
    )

    assert "corporate_actions" not in sections
    assert "Cổ tức, tăng vốn và quyền cổ đông" not in "\n".join(sections.values())
    assert "kỹ thuật" in sections["market_view"]


def test_report_markdown_does_not_repeat_corporate_action_section():
    markdown = report_markdown(
        {
            "report_sections": {
                "thesis": "Luận điểm",
                "overview": "Tổng quan",
                "industry": "Ngành",
                "market_view": "Kỹ thuật và dòng tiền",
                "risks": "Rủi ro",
            }
        }
    )

    assert "Kỹ thuật, dòng tiền và vị thế thị trường" in markdown
    assert "Cổ tức, tăng vốn và quyền cổ đông" not in markdown


def test_deepseek_auth_error_is_reported_not_crashing_page():
    """Khóa DeepSeek bị từ chối (401) từng làm sập cả trang Streamlit (uncaught AuthenticationError).
    Phải trả lỗi rõ ràng cho UI hiển thị, không lộ khóa, giữ kết quả kiểm tra Python."""
    import httpx
    import openai

    def _raise(**_kwargs):
        response = httpx.Response(401, request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"))
        raise openai.AuthenticationError("Your api key: ****f675 is invalid", response=response, body=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_raise)))
    result = generate_verified_summary(
        company=_company(),
        blended_fv=25_000,
        current_price=20_000,
        upside=25.0,
        recommendation="BUY",
        client=client,
    )
    assert result["ai_generated"] is False
    assert "401" in result["error"] and "DEEPSEEK_API_KEY" in result["error"]
    assert "f675" not in result["error"]
    assert result["status"] in {"OK", "WARNING", "ERROR"}


def test_parse_first_json_object_ignores_trailing_extra_data():
    import json as _json

    import pytest as _pytest

    from valuation.report.verified_summary import parse_first_json_object

    assert parse_first_json_object('{"a": 1}\n{"a": 2} thêm chữ') == {"a": 1}
    assert parse_first_json_object('  {"a": 1}  ') == {"a": 1}
    with _pytest.raises(_json.JSONDecodeError):
        parse_first_json_object('{"a": ')
    with _pytest.raises(ValueError):
        parse_first_json_object("[1, 2]")
