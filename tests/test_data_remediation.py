"""Kiểm thử lỗi dữ liệu trước khi sửa; số mẫu kiểm chứng được bằng tay."""

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.data_access.periodize import periodize_quarters_to_annual
from valuation.data_access.repo import _match_value
from valuation.db.models import PricesDaily
from valuation.db.session import Base
from valuation.ingest import pipeline
from valuation.ingest.normalizer import normalize_daily_prices, unpivot_financials


def financial_rows(values, statement="IS", item="net_income"):
    return pd.DataFrame(
        [
            {
                "fiscal_year": 2025,
                "fiscal_quarter": q,
                "statement": statement,
                "line_item": item,
                "value": v,
            }
            for q, v in values
        ]
    )


@pytest.mark.parametrize("mode", ["TTM", "FY"])
def test_missing_quarter_is_not_annualized(mode):
    result = periodize_quarters_to_annual(
        financial_rows([(1, 10), (2, 20), (4, 40)]), 2025, mode, 4
    )
    assert "net_income" not in result


def test_missing_value_is_not_zero_in_annual_report():
    result = periodize_quarters_to_annual(financial_rows([(0, None)]), 2025, "FY")
    assert "net_income" not in result


def test_each_item_needs_its_own_four_quarters():
    df = pd.concat(
        [
            financial_rows([(1, 1), (2, 2), (3, 3), (4, 4)], item="net_sales"),
            financial_rows([(1, 10), (2, 20), (4, 40)]),
        ]
    )
    result = periodize_quarters_to_annual(df, 2025, "TTM", 4)
    assert result["net_sales"] == 10
    assert "net_income" not in result


def test_latest_balance_sheet_cannot_borrow_previous_quarter():
    df = pd.concat(
        [
            financial_rows([(4, 500)], "BS", "total_assets"),
            financial_rows([(3, 20)], "BS", "cash"),
        ]
    )
    result = periodize_quarters_to_annual(df, 2025, "TTM", 4)
    assert result["total_assets"] == 500
    assert "cash" not in result


def test_partial_annual_statement_does_not_hide_complete_quarterly_item():
    df = pd.concat(
        [
            financial_rows([(0, 500)], "BS", "total_assets"),
            financial_rows([(1, 10), (2, 20), (3, -5), (4, -25)]),
        ]
    )
    result = periodize_quarters_to_annual(df, 2025, "FY")
    assert result["net_income"] == 0
    assert result["total_assets"] == 500


def test_exact_alias_wins_over_approximate_match_of_earlier_alias():
    values = {"net_income_before_2015": 999, "profit_after_tax": 10}
    assert _match_value(values, ["net_income", "profit_after_tax"]) == 10


def test_missing_alias_does_not_match_unrelated_item():
    assert (
        _match_value(
            {"minority_interests_before_2015": 99},
            ["minority_interests"],
            fallback=None,
        )
        is None
    )


def test_already_normalized_prices_are_not_multiplied_again():
    df = pd.DataFrame([{"close": 20000.0, "price_unit": "VND"}])
    assert normalize_daily_prices(df).iloc[0]["close"] == 20000


def test_price_refresh_preserves_turnover_and_flows(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pipeline, "SessionLocalWrite", factory)
    with factory() as db:
        db.add(
            PricesDaily(
                ticker="AAA",
                trade_date=date(2025, 1, 2),
                close=10000,
                value=2500000,
                foreign_net_val=-300000,
            )
        )
        db.commit()
    frame = pd.DataFrame([{"time": "2025-01-02", "close": 11000, "volume": 200}])
    pipeline.upsert_prices(frame, "AAA")
    pipeline.upsert_prices(frame, "AAA")
    with factory() as db:
        row = db.query(PricesDaily).one()
        assert float(row.close) == 11000
        assert float(row.value) == 2500000
        assert float(row.foreign_net_val) == -300000


def test_foreign_refresh_does_not_erase_existing_proprietary_flow(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pipeline, "SessionLocalWrite", factory)
    with factory() as db:
        db.add(
            PricesDaily(
                ticker="AAA",
                trade_date=date(2025, 1, 2),
                close=10000,
                proprietary_net_val=900000,
            )
        )
        db.commit()
    foreign = pd.DataFrame([{"time": "2025-01-02", "net_val": -300000}])
    pipeline.upsert_market_flows("AAA", foreign, pd.DataFrame())
    with factory() as db:
        row = db.query(PricesDaily).one()
        assert float(row.foreign_net_val) == -300000
        assert float(row.proprietary_net_val) == 900000


def test_normalizer_preserves_verified_source_metadata():
    frame = pd.DataFrame({"item_id": ["total_assets"], "2025-Q4": [2.0]})
    frame.attrs.update(
        source="issuer_filing",
        currency="VND",
        unit_multiplier=1e9,
        is_consolidated=False,
        is_restated=True,
        published_at="2026-02-01",
    )
    result = unpivot_financials(frame, "BS").iloc[0]
    assert float(result["value"]) == 2e9
    assert not bool(result["is_consolidated"])
    assert bool(result["is_restated"])
    assert str(result["published_at"]) == "2026-02-01"
    assert result["source"] == "issuer_filing"


def test_explicit_cumulative_flow_is_converted_to_quarters():
    frame = pd.DataFrame(
        {
            "item_id": ["net_income"],
            "2025-Q1": [10],
            "2025-Q2": [30],
            "2025-Q3": [25],
            "2025-Q4": [60],
        }
    )
    frame.attrs["period_basis"] = "cumulative"
    result = unpivot_financials(frame, "IS").sort_values("fiscal_quarter")
    assert result["value"].tolist() == [10, 20, -5, 35]


def test_cumulative_without_previous_quarter_is_rejected():
    frame = pd.DataFrame({"item_id": ["net_income"], "2025-Q2": [30]})
    frame.attrs["period_basis"] = "cumulative"
    with pytest.raises(ValueError, match="lũy kế"):
        unpivot_financials(frame, "IS")


def test_reported_zero_profit_and_negative_core_ebit_are_preserved():
    from valuation.data_access.repo import _nonfinancial_income_values

    values = _nonfinancial_income_values(
        {
            "net_sales": 100,
            "cost_of_sales": -110,
            "gross_profit": -10,
            "selling_expenses": -5,
            "general_and_admin_expenses": -10,
            "operating_profit_loss": 50,
            "net_profit_loss_after_tax": 0,
            "interest_expenses": -2,
            "corporate_income_tax_expenses": 0,
        }
    )
    assert values["net_income"] == 0
    assert values["ebit"] == -25
    assert values["opex"] == 15


def test_missing_profit_is_not_estimated_from_ebit():
    from valuation.data_access.repo import _nonfinancial_income_values

    with pytest.raises(ValueError, match="net_income"):
        _nonfinancial_income_values(
            {
                "net_sales": 100,
                "cost_of_sales": -60,
                "selling_expenses": -5,
                "general_and_admin_expenses": -10,
            }
        )


def test_validation_does_not_invent_cash_flow_balancing_entry():
    from test_verified_summary import _company

    from valuation.models.financials import Company

    company = _company()
    older = company.historical_bs[0].model_copy(
        update={"year": 2024, "cash_and_equivalents": 20}
    )
    company.historical_bs.insert(0, older)
    data = company.model_dump()
    data["historical_cf"][0]["cf_other"] = 0
    restored = Company.model_validate(data)
    assert restored.historical_cf[0].cf_other == 0


def test_cashflow_other_uses_reported_cfi_cff_without_double_counting_capex():
    from valuation.data_access.repo import _cashflow_other_excluding_capex

    data = {
        "net_cash_inflows_outflows_from_operating_activities": 1_000.0,
        "net_cash_inflows_outflows_from_investing_activities": -300.0,
        "net_cash_inflows_outflows_from_financing_activities": -100.0,
        "effect_of_foreign_exchange_differences": 5.0,
        "purchases_of_fixed_assets_and_other_long_term_assets": -200.0,
    }

    cf_other, has_full_sections = _cashflow_other_excluding_capex(
        data,
        capex_abs=200.0,
    )

    assert has_full_sections is True
    assert cf_other == -195.0
    assert 1_000.0 - 200.0 + cf_other == 605.0


def test_material_data_error_blocks_publication_without_hiding_diagnostic():
    from test_verified_summary import _company

    from valuation.engine.valuate import _apply_publication_gate

    result = {
        "blended_fair_value_per_share": 25000,
        "recommendation": "BUY",
        "flags": [],
        "decision": {"recommendation": "BUY"},
    }
    gated = _apply_publication_gate(_company(bad_gross_profit=True), result)
    assert not gated["publication_allowed"]
    assert gated["recommendation"] == "NOT_RATED"
    assert gated["decision"]["recommendation"] == "NOT_RATED"
    assert gated["blended_fair_value_per_share"] == 25000


def test_securities_checks_do_not_use_industrial_gross_profit_identity():
    from test_verified_summary import _company

    from valuation.report.verified_summary import run_deterministic_checks

    company = _company(bad_gross_profit=True)
    company.ticker = "SSI"
    company.sector = "Securities"
    checks = run_deterministic_checks(company, blended_fv=25000, upside=25)
    assert "GROSS_PROFIT_MISMATCH" not in {r["code"] for r in checks}
    assert "FINANCIAL_SECTOR_LAYOUT" in {r["code"] for r in checks}


def test_taxonomy_long_and_legacy_wide_produce_same_value():
    raw = pd.DataFrame(
        [{"id": "BS_TOTAL_ASSETS", "unit": "VNĐ", "period": "2025-Q4", "value": 200}]
    )
    result = unpivot_financials(raw, "BS").iloc[0]
    assert result["line_item"] == "total_assets"
    assert result["value"] == 200


def test_inventory_taxonomy_keeps_net_and_gross_concepts_separate():
    raw = pd.DataFrame(
        [
            {
                "id": "BS_INVENTORIES",
                "unit": "VNĐ",
                "period": "2025-Q4",
                "value": 90,
            },
            {
                "id": "BS_INVENTORIES_GROSS",
                "unit": "VNĐ",
                "period": "2025-Q4",
                "value": 100,
            },
        ]
    )
    result = unpivot_financials(raw, "BS").set_index("line_item")["value"]
    assert result["inventories_net"] == 90
    assert result["inventories"] == 100
    assert _match_value(result.to_dict(), ["inventories_net", "inventories"]) == 90


def test_source_comparison_accepts_expense_sign_convention_only():
    from valuation.ingest.taxonomy import classify_source_value

    assert (
        classify_source_value(100, -100, "corporate_income_tax_expenses")
        == "SIGN_CONVENTION_MATCH"
    )
    assert classify_source_value(100, -100, "total_assets") == "CRITICAL_CONFLICT"


def test_source_comparison_accepts_small_rounding_difference():
    from valuation.ingest.taxonomy import classify_source_value

    assert classify_source_value(100_000, 100_050, "total_assets") == "ROUNDING_MATCH"


def test_goodwill_amortization_cannot_replace_total_depreciation():
    raw = pd.DataFrame(
        [
            {
                "id": "CF_DEPRECIATION_AND_AMORTISATION",
                "unit": "VNĐ",
                "period": "2025-Q4",
                "value": 200,
            },
            {
                "id": "CF_DEPRECIATION_AMORTIZATION",
                "unit": "VNĐ",
                "period": "2025-Q4",
                "value": 5,
            },
        ]
    )
    result = unpivot_financials(raw, "CF")
    assert len(result) == 1
    assert result.iloc[0]["value"] == 200


def test_conflicting_duplicate_financial_rows_are_not_silently_dropped():
    raw = pd.DataFrame(
        {"item_id": ["total_assets", "total_assets"], "2025-Q4": [100, 200]}
    )
    with pytest.raises(ValueError, match="mâu thuẫn"):
        unpivot_financials(raw, "BS")


def test_balance_residuals_use_reported_subtotals_not_half_split():
    from valuation.data_access.repo import _balance_residuals

    result = _balance_residuals(
        {
            "current_assets": 100,
            "long_term_assets": 300,
            "current_liabilities": 80,
            "long_term_liabilities": 120,
        },
        cash=10,
        receivables=20,
        inventory=30,
        fixed=200,
        short_debt=20,
        payable=10,
        long_debt=100,
    )
    assert result == {
        "other_current_assets": 40,
        "other_long_term_assets": 100,
        "other_current_liabilities": 50,
        "other_long_term_liabilities": 20,
    }


def test_missing_balance_subtotal_is_not_invented():
    from valuation.data_access.repo import _balance_residuals

    result = _balance_residuals(
        {},
        cash=10,
        receivables=20,
        inventory=30,
        fixed=200,
        short_debt=20,
        payable=10,
        long_debt=100,
    )
    assert all(v is None for v in result.values())


def test_source_conflict_blocks_publication():
    from test_verified_summary import _company

    from valuation.engine.valuate import _apply_publication_gate

    company = _company()
    company.data_flags.append("SOURCE_CONFLICT:2")
    result = _apply_publication_gate(
        company,
        {
            "blended_fair_value_per_share": 25000,
            "recommendation": "BUY",
            "flags": [],
            "decision": {"recommendation": "BUY"},
        },
    )
    assert not result["publication_allowed"]
    assert result["recommendation"] == "NOT_RATED"


def test_missing_or_old_source_audit_is_explicitly_blocked():
    from valuation.data_access.repo import _source_audit_flags

    assert _source_audit_flags(None, "ACB", "v1") == ["SOURCE_AUDIT_MISSING"]
    assert _source_audit_flags({"mapping_version": "old", "rows": []}, "ACB", "v1") == [
        "SOURCE_AUDIT_STALE"
    ]


def test_only_critical_source_conflict_blocks_publication():
    from valuation.data_access.repo import _source_audit_flags

    audit = {
        "mapping_version": "v2",
        "rows": [
            {
                "ticker": "ACB",
                "CONFLICT": 4,
                "CRITICAL_CONFLICT": 0,
                "INFORMATIONAL_CONFLICT": 4,
            }
        ],
    }
    assert _source_audit_flags(audit, "ACB", "v2") == []
