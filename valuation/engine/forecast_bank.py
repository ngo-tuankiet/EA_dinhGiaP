"""
Forecast bank module — Dự phóng 3 dòng BCTC 5 năm tiếp theo cho Ngân hàng.
"""
from typing import List, Dict, Any
from valuation.models.financials_bank import CompanyBank

def forecast_bank_financials(company: CompanyBank) -> List[Dict[str, Any]]:
    """
    Dự phóng 5 năm tiếp theo cho Ngân hàng dựa trên các giả định NIM, Tăng trưởng tín dụng, CIR, Credit Cost.
    """
    hist_is = company.historical_is
    hist_bs = company.historical_bs
    assumptions = company.assumptions

    base_is = hist_is[-1]
    base_bs = hist_bs[-1]

    # Tính tỷ lệ Non-II / Tài sản bình quân lịch sử
    hist_non_ii = base_is.non_interest_income
    hist_assets = base_bs.total_assets
    non_ii_to_assets = hist_non_ii / hist_assets if hist_assets > 0 else 0.005

    projections = []
    
    curr_loans = base_bs.customer_loans
    curr_assets = base_bs.total_assets
    curr_earning_assets = base_bs.earning_assets
    curr_equity = base_bs.total_equity
    curr_deposits = base_bs.customer_deposits
    base_year = base_is.year

    min_eq = getattr(assumptions, "min_equity_to_assets", None)
    tax_rate = getattr(assumptions, 'tax_rate', 0.20)

    def _year(cg: float, dg: float, i: int) -> Dict[str, float]:
        next_loans = curr_loans * (1 + cg)
        next_earning_assets = curr_earning_assets * (1 + cg)
        next_assets = curr_assets * (1 + cg)
        avg_earning_assets = (curr_earning_assets + next_earning_assets) / 2
        avg_assets = (curr_assets + next_assets) / 2
        nii = assumptions.nim[i] * avg_earning_assets
        non_ii = non_ii_to_assets * avg_assets
        toi = nii + non_ii
        opex = assumptions.cir[i] * toi
        ppop = toi - opex
        provision = assumptions.credit_cost[i] * (curr_loans + next_loans) / 2
        pbt = ppop - provision
        ni = pbt * (1.0 - tax_rate)  # lỗ vẫn là lỗ, không kẹp về 0
        div = max(ni, 0.0) * assumptions.dividend_payout_ratio
        return dict(
            next_loans=next_loans, next_deposits=curr_deposits * (1 + dg),
            next_earning_assets=next_earning_assets, next_assets=next_assets,
            nii=nii, non_ii=non_ii, toi=toi, opex=opex, ppop=ppop, provision=provision,
            pbt=pbt, ni=ni, div=div, next_equity=curr_equity + ni - div,
        )

    for i in range(5):
        year = base_year + (i + 1)
        cg = assumptions.credit_growth[i]
        dg = assumptions.deposit_growth[i] if hasattr(assumptions, "deposit_growth") and assumptions.deposit_growth else cg
        y = _year(cg, dg, i)
        # Ràng buộc vốn: không để VCSH/Tổng tài sản xuống dưới mức lịch sử của chính NH —
        # tăng trưởng tài sản bị giới hạn bởi vốn tích lũy (thay cho kiểm tra CAR).
        if min_eq and y["next_equity"] < min_eq * y["next_assets"]:
            cg = y["next_equity"] / min_eq / curr_assets - 1
            y = _year(cg, min(dg, cg), i)
        next_loans, next_deposits = y["next_loans"], y["next_deposits"]
        next_earning_assets, next_assets = y["next_earning_assets"], y["next_assets"]
        nii, non_ii, toi, opex, ppop = y["nii"], y["non_ii"], y["toi"], y["opex"], y["ppop"]
        provision, pbt, ni, div = y["provision"], y["pbt"], y["ni"], y["div"]
        next_equity = y["next_equity"]

        next_other_earning_assets = max(0.0, next_assets - next_loans)
        next_other_liabilities = max(0.0, next_assets - next_deposits - next_equity)

        proj_item = {
            "year": year,
            "customer_loans": next_loans,
            "other_earning_assets": next_other_earning_assets,
            "earning_assets": next_earning_assets,
            "total_assets": next_assets,
            "customer_deposits": next_deposits,
            "other_liabilities": next_other_liabilities,
            "net_interest_income": nii,
            "non_interest_income": non_ii,
            "total_operating_income": toi,
            "operating_expenses": opex,
            "pre_provision_profit": ppop,
            "provision_expense": provision,
            "pretax_income": pbt,
            "net_income": ni,
            "dividends": div,
            "total_equity": next_equity
        }
        projections.append(proj_item)

        # Cập nhật cho vòng lặp tiếp theo
        curr_loans = next_loans
        curr_earning_assets = next_earning_assets
        curr_assets = next_assets
        curr_equity = next_equity
        curr_deposits = next_deposits

    return projections
