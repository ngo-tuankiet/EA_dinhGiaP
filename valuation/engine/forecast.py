"""
Forecast module — Dự phóng 3 dòng BCTC 5 năm tiếp theo cho doanh nghiệp phi tài chính.
"""
from typing import List, Dict, Any
from valuation.models.financials import Company

def forecast_company_financials(company: Company) -> List[Dict[str, Any]]:
    """
    Dự phóng 5 năm tiếp theo của doanh nghiệp phi tài chính.
    Trả về danh sách 5 dict chứa các khoản mục dự phóng.
    """
    hist_is = company.historical_is
    hist_bs = company.historical_bs
    assumptions = company.assumptions

    # Lấy năm lịch sử gần nhất làm mốc gốc
    base_is = hist_is[-1]
    base_bs = hist_bs[-1]
    
    # NWC gốc từ DSO/DIO/DPO (tương thích với Assumptions.dso/dio/dpo)
    base_cogs = base_is.cogs
    cogs_ratio = base_cogs / base_is.revenue if base_is.revenue > 0 else 0.7
    dso0 = assumptions.dso[0]
    dio0 = assumptions.dio[0]
    dpo0 = assumptions.dpo[0]
    base_nwc = (
        base_is.revenue * (dso0 / 365)
        + base_is.revenue * cogs_ratio * (dio0 / 365)
        - base_is.revenue * cogs_ratio * (dpo0 / 365)
    )

    projections = []
    curr_rev = base_is.revenue
    curr_nwc = base_nwc
    base_year = base_is.year

    # Debt Schedule: khởi tạo tổng nợ đầu kỳ
    base_total_debt = base_bs.short_term_debt + base_bs.long_term_debt
    curr_debt = base_total_debt

    for i in range(5):
        year = base_year + (i + 1)
        growth = assumptions.revenue_growth[i]
        ebit_m = assumptions.ebit_margin[i]
        capex_m = assumptions.capex_to_revenue[i]
        depr_m = assumptions.depr_to_revenue[i]
        dso = assumptions.dso[i]
        dio = assumptions.dio[i]
        dpo = assumptions.dpo[i]

        # 1. Doanh thu & Chi phí
        rev = curr_rev * (1 + growth)
        ebit = rev * ebit_m
        nopat = ebit * (1 - assumptions.tax_rate)

        # 2. D&A, CapEx, NWC (DSO/DIO/DPO schedule)
        depr = rev * depr_m
        capex = rev * capex_m
        curr_cogs = rev * cogs_ratio
        nwc = (
            rev * (dso / 365)
            + curr_cogs * (dio / 365)
            - curr_cogs * (dpo / 365)
        )

        # 3. Biến động NWC & FCFF
        # LƯU Ý: FCFF = NOPAT + D&A - Capex - ΔNWC (Damodaran)
        # FCFF KHÔNG bị ảnh hưởng bởi Interest Expense
        delta_nwc = nwc - curr_nwc
        fcff = nopat + depr - abs(capex) - delta_nwc

        # 4. Debt Schedule
        # debt_repayment: trả nợ gốc = nợ đầu kỳ × tỷ lệ trả nợ
        # new_borrowing: vay mới = doanh thu dự phóng × tỷ lệ vay mới
        # ending_debt = beginning_debt + new_borrowing - debt_repayment
        # interest_expense = average_debt × lãi suất (Damodaran avg-debt convention)
        repayment_rate = assumptions.debt_repayment_rate[i]
        new_borrow_rate = assumptions.new_borrowing_rate[i]
        int_rate = assumptions.interest_rate[i]

        debt_repayment = curr_debt * repayment_rate
        new_borrowing = rev * new_borrow_rate
        end_debt = curr_debt + new_borrowing - debt_repayment
        avg_debt = (curr_debt + end_debt) / 2
        interest_expense = avg_debt * int_rate

        # 5. Net Income (FCFE path): EBIT - Interest Expense - Tax trên EBT
        # Net Income = (EBIT - Interest Expense) × (1 - tax_rate)
        ebt = ebit - interest_expense
        net_income = ebt * (1 - assumptions.tax_rate)

        proj_item = {
            "year": year,
            "revenue": rev,
            "growth": growth,
            "ebit": ebit,
            "ebit_margin": ebit_m,
            "nopat": nopat,
            "depreciation": depr,
            "capex": capex,
            "nwc": nwc,
            "delta_nwc": delta_nwc,
            "fcff": fcff,
            # Debt Schedule output
            "beginning_debt": curr_debt,
            "new_borrowing": new_borrowing,
            "debt_repayment": debt_repayment,
            "ending_debt": end_debt,
            "interest_expense": interest_expense,
            "net_income": net_income,
        }
        projections.append(proj_item)

        curr_rev = rev
        curr_nwc = nwc
        curr_debt = end_debt

    return projections
