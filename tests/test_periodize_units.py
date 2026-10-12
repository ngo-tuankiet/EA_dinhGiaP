"""
Unit test for data_access periodize & units.
"""
import pytest
import pandas as pd
from valuation.data_access.units import to_billion_vnd, from_billion_vnd
from valuation.data_access.periodize import periodize_quarters_to_annual, is_stock_item

def test_units_conversion():
    assert to_billion_vnd(1_000_000_000) == 1.0
    assert to_billion_vnd(500_000_000) == 0.5
    assert to_billion_vnd(None) == 0.0
    
    assert from_billion_vnd(1.5) == 1_500_000_000.0
    assert from_billion_vnd(0.0) == 0.0
    assert from_billion_vnd(None) == 0.0

def test_is_stock_item():
    # Các khoản mục CĐKT (Stock)
    assert is_stock_item("Tổng tài sản") is True
    assert is_stock_item("Vốn chủ sở hữu") is True
    assert is_stock_item("Cho vay khách hàng") is True
    assert is_stock_item("total_assets") is True
    assert is_stock_item("owners_equity") is True
    
    # Các khoản mục KQKD/LCTT (Flow)
    assert is_stock_item("Doanh thu thuần") is False
    assert is_stock_item("Lợi nhuận sau thuế") is False
    assert is_stock_item("net_sales") is False
    assert is_stock_item("net_income") is False


@pytest.mark.parametrize(
    "line_item,statement,expected",
    [
        ("trade_accounts_payable", "BS", True),
        ("net_cash_inflows_outflows_from_operating_activities", "CF", False),
        ("purchases_of_fixed_assets_and_other_long_term_assets", "CF", False),
        ("cash_and_cash_equivalents", "BS", True),
    ],
)
def test_statement_type_overrides_keyword_heuristics(line_item, statement, expected):
    assert is_stock_item(line_item, statement=statement) is expected

def test_periodize_quarters_to_annual():
    # Tạo DataFrame giả lập dữ liệu quý
    data = [
        # Doanh thu thuần (Flow) - TTM phải bằng sum các quý = 1000
        {"fiscal_year": 2024, "fiscal_quarter": 1, "line_item": "Doanh thu thuần", "value": 200.0},
        {"fiscal_year": 2024, "fiscal_quarter": 2, "line_item": "Doanh thu thuần", "value": 250.0},
        {"fiscal_year": 2024, "fiscal_quarter": 3, "line_item": "Doanh thu thuần", "value": 300.0},
        {"fiscal_year": 2024, "fiscal_quarter": 4, "line_item": "Doanh thu thuần", "value": 250.0},
        
        # Vốn chủ sở hữu (Stock) - TTM phải bằng giá trị quý cuối cùng (Q4) = 520
        {"fiscal_year": 2024, "fiscal_quarter": 1, "line_item": "Vốn chủ sở hữu", "value": 500.0},
        {"fiscal_year": 2024, "fiscal_quarter": 2, "line_item": "Vốn chủ sở hữu", "value": 510.0},
        {"fiscal_year": 2024, "fiscal_quarter": 3, "line_item": "Vốn chủ sở hữu", "value": 515.0},
        {"fiscal_year": 2024, "fiscal_quarter": 4, "line_item": "Vốn chủ sở hữu", "value": 520.0},
    ]
    df = pd.DataFrame(data)
    
    # Chạy TTM
    result_ttm = periodize_quarters_to_annual(df, 2024, mode="TTM", latest_quarter=4)
    
    assert result_ttm["Doanh thu thuần"] == 1000.0
    assert result_ttm["Vốn chủ sở hữu"] == 520.0
    
    # Chạy FY
    result_fy = periodize_quarters_to_annual(df, 2024, mode="FY")
    assert result_fy["Doanh thu thuần"] == 1000.0
    assert result_fy["Vốn chủ sở hữu"] == 520.0


def test_ttm_uses_latest_bs_and_sums_cash_flow_items():
    data = []
    for quarter, payable, cfo, capex in [
        (1, 100.0, 10.0, -2.0),
        (2, 110.0, 20.0, -3.0),
        (3, 120.0, 30.0, -4.0),
        (4, 130.0, 40.0, -5.0),
    ]:
        data.extend(
            [
                {
                    "fiscal_year": 2024,
                    "fiscal_quarter": quarter,
                    "statement": "BS",
                    "line_item": "trade_accounts_payable",
                    "value": payable,
                },
                {
                    "fiscal_year": 2024,
                    "fiscal_quarter": quarter,
                    "statement": "CF",
                    "line_item": "net_cash_inflows_outflows_from_operating_activities",
                    "value": cfo,
                },
                {
                    "fiscal_year": 2024,
                    "fiscal_quarter": quarter,
                    "statement": "CF",
                    "line_item": "purchases_of_fixed_assets_and_other_long_term_assets",
                    "value": capex,
                },
            ]
        )

    result = periodize_quarters_to_annual(
        pd.DataFrame(data), 2024, mode="TTM", latest_quarter=4
    )

    assert result["trade_accounts_payable"] == 130.0
    assert result["net_cash_inflows_outflows_from_operating_activities"] == 100.0
    assert result["purchases_of_fixed_assets_and_other_long_term_assets"] == -14.0


def test_fy_q0_duplicate_line_item_prefers_balance_sheet_stock_value():
    """Regression PVT: minority_interests tồn tại ở cả IS và BS."""
    df = pd.DataFrame(
        [
            {
                "fiscal_year": 2025,
                "fiscal_quarter": 0,
                "statement": "IS",
                "line_item": "minority_interests",
                "value": 291_124_019_480.0,
            },
            {
                "fiscal_year": 2025,
                "fiscal_quarter": 0,
                "statement": "BS",
                "line_item": "minority_interests",
                "value": 2_817_176_678_989.0,
            },
        ]
    )

    result = periodize_quarters_to_annual(df, 2025, mode="FY")

    assert result["minority_interests"] == 2_817_176_678_989.0
