"""Kiểm tra tính tay và rào chắn của hai chiến lược tích sản."""

from copy import deepcopy

import pytest

from valuation.analysis.investment_ranking import (
    load_ranking_config,
    rank_companies,
    select_candidates,
)


@pytest.fixture
def row():
    return {
        "ticker": "ACB",
        "sector": "NH",
        "price": 75,
        "fair_value": 100,
        "components": dict.fromkeys(
            ["quality", "safety", "moat", "context", "flow"], 80
        ),
        "flags": [],
        "blockers": [],
        "governance_verified": True,
        "golden_verified": True,
        "liquidity_ok": True,
    }


def test_mos_and_weighted_score_by_hand(row):
    result = rank_companies([row], load_ranking_config())[0]
    assert result["mos"] == pytest.approx(0.25)
    assert result["upside_pct"] == pytest.approx(100 / 75 * 100 - 100)
    # Định giá 100 điểm, 70% còn lại 80 điểm: 30 + 56 = 86.
    assert result["profiles"]["defensive"]["score"] == pytest.approx(86)
    assert result["profiles"]["defensive"]["eligible"] is True


def test_missing_evidence_never_passes_or_inflates_score(row):
    baseline = rank_companies([row], load_ranking_config())[0]
    row["components"]["moat"] = None
    row["governance_verified"] = False
    actual = rank_companies([row], load_ranking_config())[0]
    assert (
        actual["profiles"]["defensive"]["score"]
        < baseline["profiles"]["defensive"]["score"]
    )
    assert not actual["profiles"]["defensive"]["eligible"]


@pytest.mark.parametrize("flag", ["NOT_RATED", "STALE_MACRO_RF", "VALUATION_PROXY"])
def test_flags_block_picks_even_with_high_scores(row, flag):
    row["flags"] = [flag]
    actual = rank_companies([row], load_ranking_config())[0]
    assert not actual["profiles"]["growth"]["eligible"]


def test_invalid_values_are_not_ranked(row):
    for bad in [0, -1, float("nan"), float("inf"), None]:
        item = deepcopy(row)
        item["price"] = bad
        result = rank_companies([item], load_ranking_config())[0]
        assert result["profiles"]["defensive"]["rank"] is None


def test_two_profiles_and_no_mutation(row):
    before = deepcopy(row)
    result = rank_companies([row], load_ranking_config())[0]
    assert row == before
    assert (
        result["profiles"]["growth"]["score"]
        != result["profiles"]["defensive"]["score"]
    )


def test_no_golden_cannot_be_recommended(row):
    row["golden_verified"] = False
    result = rank_companies([row], load_ranking_config())[0]
    assert not result["profiles"]["defensive"]["eligible"]


def test_material_cashflow_warning_blocks_accumulation(row):
    row["checks"] = [
        {
            "severity": "warning",
            "message": "Năm 2025: chưa có đầy đủ lưu chuyển đầu tư/tài chính để đối chiếu biến động tiền; không tự tạo khoản bù.",
        }
    ]
    result = rank_companies([row], load_ranking_config())[0]
    assert not result["profiles"]["defensive"]["eligible"]
    assert any(
        "lưu chuyển đầu tư/tài chính" in reason
        for reason in result["profiles"]["defensive"]["reasons"]
    )


def test_diversification_and_no_forced_quota(row):
    cfg = load_ranking_config()
    rows = [
        dict(deepcopy(row), ticker=f"T{i}", sector=f"Ngành {i // 4}") for i in range(12)
    ]
    ranked = rank_companies(rows, cfg)
    chosen = select_candidates(ranked, "defensive", cfg, eligible_only=True)
    assert len(chosen) == 6
    for sector in {r["sector"] for r in rows}:
        assert sum(r["ticker"] in chosen and r["sector"] == sector for r in rows) == 2
    for item in rows:
        item["governance_verified"] = False
    assert not select_candidates(
        rank_companies(rows, cfg), "defensive", cfg, eligible_only=True
    )


def test_research_candidates_still_exclude_hard_blockers(row):
    cfg = load_ranking_config()
    soft = deepcopy(row)
    soft["ticker"] = "SOFT"
    soft["governance_verified"] = False
    hard = deepcopy(row)
    hard["ticker"] = "HARD"
    hard["flags"] = ["STALE_PRICE"]

    ranked = rank_companies([soft, hard], cfg)
    research = select_candidates(ranked, "defensive", cfg, eligible_only=False)

    assert "SOFT" in research
    assert "HARD" not in research


def test_identity_error_and_prefixed_proxy_are_not_ranked(row):
    row["checks"] = [{"severity": "error", "message": "BCTC không khớp"}]
    actual = rank_companies([row], load_ranking_config())[0]
    assert actual["profiles"]["defensive"]["rank"] is None
    assert actual["fair_value"] is None
    row["checks"] = []
    row["flags"] = ["PROXY_IMPLAUSIBLE: sai lệch trên ngưỡng"]
    actual = rank_companies([row], load_ranking_config())[0]
    assert actual["profiles"]["growth"]["rank"] is None
