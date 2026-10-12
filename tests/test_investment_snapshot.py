from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest

from valuation.analysis.investment_ranking import load_ranking_config
from valuation.data_access.investment_snapshot import (
    financial_metrics,
    previous_session_day,
    verified_evidence,
)
from valuation.services import investment_job
from valuation.services.investment_job import next_run, week_key


def test_annual_metrics_exclude_overlapping_ttm():
    company = NS(
        historical_is=[
            NS(year=2023, revenue=100, net_income=10),
            NS(year=2024, revenue=110, net_income=20),
            NS(year=2025, revenue=121, net_income=30),
            NS(year=2026, revenue=500, net_income=200),
        ],
        historical_bs=[
            NS(year=2024, total_equity=100, parent_equity=100, short_term_debt=10, long_term_debt=10),
            NS(year=2025, total_equity=200, parent_equity=200, short_term_debt=20, long_term_debt=40),
        ],
        historical_cf=[NS(year=2025, cfo=36)],
    )
    metrics = financial_metrics(company, date(2026, 8, 31))
    assert metrics["roe"] == pytest.approx(30 / 150)
    assert metrics["revenue_cagr"] == pytest.approx(0.10)
    assert metrics["debt_to_equity"] == pytest.approx(0.30)
    assert metrics["cash_conversion"] == pytest.approx(1.20)
    assert metrics["metric_period"] == "FY2025"


def test_no_default_governance_or_stale_evidence():
    cfg = load_ranking_config()
    assert not verified_evidence({}, date(2026, 8, 31), "hash", cfg)
    valid = {
        "reviewed_on": "2026-08-30",
        "reviewer": "Analyst",
        "sources": [{"url": "https://example.com/report", "title": "BCTC"}],
        "golden": {
            "input_hash": "hash",
            "relative_error": 0.09,
            "reference_url": "https://example.com/model",
        },
    }
    assert verified_evidence(valid, date(2026, 8, 31), "hash", cfg)["golden_verified"]
    assert not verified_evidence(valid, date(2026, 8, 31), "other", cfg)[
        "golden_verified"
    ]
    assert not verified_evidence(valid, date(2028, 8, 31), "hash", cfg)


def test_schedule_and_intraday_cutoff():
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    monday = datetime(2026, 8, 31, 10, tzinfo=tz)
    tuesday = datetime(2026, 9, 1, 9, 30, tzinfo=tz)
    assert next_run(monday) == tuesday
    assert next_run(tuesday).day == 8
    assert week_key(monday) == "2026-08-25"
    assert week_key(tuesday) == "2026-09-01"
    assert previous_session_day(monday.date()) == date(2026, 8, 28)
    assert previous_session_day(tuesday.date()) == date(2026, 8, 31)


def test_run_job_emits_progress_without_api(monkeypatch, tmp_path):
    cfg = load_ranking_config()
    cfg["schedule"] = {"weekday": 1, "hour": 9, "minute": 30}

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def query(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

    def fake_rank(rows, cfg):
        for row in rows:
            row["mos"] = 0.30
            row["upside_pct"] = 42.0
            row["profiles"] = {
                key: {
                    "score": 80.0,
                    "eligible": True,
                    "rank": 1,
                    "reasons": [],
                    "components": {},
                    "coverage": 100,
                }
                for key in cfg["profiles"]
            }
        return rows

    monkeypatch.setattr(investment_job, "load_ranking_config", lambda: cfg)
    monkeypatch.setattr(investment_job, "score_metrics", lambda rows, cfg: None)
    monkeypatch.setattr(investment_job, "rank_companies", fake_rank)
    monkeypatch.setattr(
        investment_job,
        "select_candidates",
        lambda rows, profile, cfg, *, eligible_only: ["AAA"] if eligible_only else [],
    )

    @contextmanager
    def fake_read_session_factory(*, refresh, store):
        yield DummySession

    monkeypatch.setattr(
        investment_job, "_batch_read_session_factory", fake_read_session_factory
    )

    import valuation.db.session as db_session
    from valuation.data_access import investment_snapshot
    from valuation.ingest import universe

    monkeypatch.setattr(db_session, "SessionLocalRead", DummySession)
    monkeypatch.setattr(
        universe,
        "load_vn100_snapshot",
        lambda: {"symbols": ["AAA"], "as_of": "2026-09-01"},
    )
    monkeypatch.setattr(investment_snapshot, "fingerprint", lambda value: "fp")
    monkeypatch.setattr(
        investment_snapshot,
        "build_ranking_row",
        lambda db, ticker, as_of, cfg, evidence: {
            "ticker": ticker,
            "name": ticker,
            "sector": "Kiểm thử",
            "price": 10.0,
            "fair_value": 13.0,
            "flags": [],
            "blockers": [],
            "checks": [],
        },
    )

    progress = []
    result = investment_job.run_job(
        refresh=False,
        use_ai=False,
        store=tmp_path,
        progress_sink=progress.append,
    )

    assert result["status"] == "COMPLETED"
    assert progress
    assert any("Đọc thành phần VN100" in item["message"] for item in progress)
    assert progress[-1]["status"] == "COMPLETED"
