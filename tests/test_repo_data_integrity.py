import pytest

from valuation.data_access import repo
from valuation.engine import ttm_helper


def test_missing_shares_raises_instead_of_using_silent_fallback(monkeypatch):
    def _missing_shares(_db, ticker, as_of_date=None, price_basis=False):
        raise ValueError(f"missing shares for {ticker}")

    monkeypatch.setattr(ttm_helper, "get_shares_outstanding", _missing_shares)

    with pytest.raises(ValueError, match="missing shares for TEST"):
        repo.get_shares_outstanding_repo(object(), "TEST")


@pytest.mark.parametrize(
    "raw,expected,was_capped",
    [
        (0.431, 0.25, True),
        (0.18, 0.18, False),
        (-0.10, 0.05, True),
    ],
)
def test_bank_credit_growth_guardrail(raw, expected, was_capped):
    bounded, capped = repo._bounded_bank_credit_growth(
        raw, {"credit_growth_floor": 0.05, "credit_growth_cap": 0.25}
    )

    assert bounded == pytest.approx(expected)
    assert capped is was_capped
