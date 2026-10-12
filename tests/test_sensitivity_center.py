"""Ô trung tâm ma trận độ nhạy (WACC gốc, g gốc) phải bằng giá trị hợp lý mô hình.

Regression: trục "WACC" từng bị gán vào COE, DCF pha lại với nợ → WACC thực thấp
hơn nhãn trục, ô giữa lệch khỏi con số hiển thị trên UI.
"""
import pytest

from valuation.data_access.repo import build_company_data
from valuation.db.session import SessionLocalRead
from valuation.engine.batch import _dispatch_nonfin
from valuation.engine.models.dcf import DCFValuationModel
from valuation.engine.sector_router import route
from valuation.engine.sensitivity import calculate_sensitivity_matrix


@pytest.mark.parametrize("ticker", ["FPT", "GMD"])
def test_sensitivity_center_equals_fair_value(ticker):
    db = SessionLocalRead()
    try:
        company = build_company_data(db, ticker, mode="TTM", fetch_live=False)
    finally:
        db.close()
    plan = route(ticker)
    _, res = _dispatch_nonfin(company, plan["method"], plan["group"])
    base_wacc = DCFValuationModel.from_pydantic(company).wacc
    _, _, matrix = calculate_sensitivity_matrix(
        company, base_wacc, company.assumptions.terminal_growth_rate
    )
    assert matrix[2][2] == pytest.approx(res["blended_fair_value_per_share"], abs=1.0)
    # Trục WACC phải thực sự làm đổi giá trị (WACC cao hơn → FV thấp hơn).
    assert matrix[2][0] > matrix[2][2] > matrix[2][4]
