from datetime import date

import pandas as pd
import pytest

from valuation.data_access.periodize import periodize_quarters_to_annual
from valuation.data_access.repo import NON_FIN_KEYWORDS, _match_value
from valuation.engine.models.ev_ebitda import EVEBITDAValuationModel
from valuation.engine.ttm_helper import resolve_shares_override


def test_restated_balance_sheet_row_wins_same_period() -> None:
    rows = pd.DataFrame(
        [
            {
                "fiscal_year": 2026,
                "fiscal_quarter": 2,
                "statement": "BS",
                "line_item": "short_term_financial_investments",
                "value": 0.0,
                "is_restated": False,
                "published_at": None,
            },
            {
                "fiscal_year": 2026,
                "fiscal_quarter": 2,
                "statement": "BS",
                "line_item": "short_term_financial_investments",
                "value": 4_422_226_341_994.0,
                "is_restated": True,
                "published_at": date(2026, 8, 28),
            },
        ]
    )

    result = periodize_quarters_to_annual(
        rows, target_year=2026, mode="TTM", latest_quarter=2
    )

    assert result["short_term_financial_investments"] == pytest.approx(
        4_422_226_341_994.0
    )


def test_share_override_only_applies_after_effective_date() -> None:
    events = [
        {
            "ticker": "ACB",
            "effective_date": "2026-06-29",
            "shares_outstanding": 5_804_421_957,
        }
    ]

    assert resolve_shares_override("ACB", date(2026, 6, 28), events) is None
    assert resolve_shares_override("ACB", date(2026, 6, 29), events) == 5_804_421_957


def test_ev_to_equity_subtracts_minority_interest() -> None:
    financials = {
        "ebitda_history": [1_000.0],
        "total_debt": 200.0 * 1e9,
        "cash_and_equivalents": 100.0 * 1e9,
        "minority_interest": 50.0 * 1e9,
        "shares_outstanding": 10.0 * 1e6,
        "current_price": 10_000.0,
    }
    model = EVEBITDAValuationModel(
        "TEST", financials, {"target_ev_ebitda": 5.0, "norm_years": 1}
    )

    result = model.perform_valuation()

    # EV 5.000 tỷ - nợ ròng 100 tỷ - NCI 50 tỷ = 4.850 tỷ; 10 triệu cp.
    assert result["equity_value"] == pytest.approx(4_850.0 * 1e9)
    assert result["blended_fair_value_per_share"] == pytest.approx(485_000.0)


def test_cost_of_sales_alias_is_mapped_as_cogs() -> None:
    assert _match_value(
        {"cost_of_sales": -8_151_357_902_595.0}, NON_FIN_KEYWORDS["cogs"]
    ) == pytest.approx(-8_151_357_902_595.0)


def test_cyclical_valuation_does_not_mutate_company() -> None:
    from valuation.data_access.repo import build_company_data
    from valuation.db.session import SessionLocalRead
    from valuation.engine.valuate import valuate

    with SessionLocalRead() as db:
        company = build_company_data(db, "PVT", mode="TTM", fetch_live=False)
    ebit_before = company.historical_is[-1].ebit

    valuate(company)

    assert company.historical_is[-1].ebit == pytest.approx(ebit_before)
