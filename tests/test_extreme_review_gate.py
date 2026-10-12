"""Kết quả cực đoan (upside > +150% / downside < −60%) phải CHẶN phát hành cho tới khi
rà soát (AGENTS.md mục 8: báo, đừng giấu — nhưng cũng không phát hành số chưa rà soát).
Số chẩn đoán vẫn giữ trong kết quả."""
import pytest

from valuation.data_access.repo import build_company_data
from valuation.db.session import SessionLocalRead
from valuation.engine.valuate import _apply_publication_gate


@pytest.fixture
def fpt():
    db = SessionLocalRead()
    try:
        yield build_company_data(db, "FPT")
    finally:
        db.close()


@pytest.mark.parametrize("flag", ["UPSIDE_EXTREME_REVIEW", "DOWNSIDE_EXTREME_REVIEW"])
def test_extreme_review_flag_blocks_publication(fpt, flag):
    fv = fpt.current_price * 1.1  # FV hợp lệ để chỉ cờ rà soát quyết định
    res = _apply_publication_gate(fpt, {"blended_fair_value_per_share": fv, "flags": [flag], "recommendation": "BUY"})
    assert res["publication_allowed"] is False
    assert res["recommendation"] == "NOT_RATED"
    assert res["blended_fair_value_per_share"] == fv  # số chẩn đoán không bị xóa


def test_normal_result_still_published(fpt):
    res = _apply_publication_gate(fpt, {"blended_fair_value_per_share": fpt.current_price * 1.1, "flags": [], "recommendation": "HOLD"})
    assert res["publication_allowed"] is True
