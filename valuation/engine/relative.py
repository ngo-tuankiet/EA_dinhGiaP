"""
Relative Valuation module — Định giá so sánh multiples (EV/EBITDA cho phi tài chính hoặc P/B cho ngân hàng).
"""
from typing import Union
from valuation.models.financials import Company
from valuation.models.financials_bank import CompanyBank

def calculate_relative_valuation(company: Union[Company, CompanyBank], target_multiple: float = None) -> float:
    """
    Tính giá trị hợp lý mỗi cổ phiếu theo phương pháp so sánh multiples (VND).
    """
    shares = company.shares_outstanding
    if shares <= 0:
        return 0.0

    if isinstance(company, Company):
        # Phi tài chính: EV/EBITDA
        hist_is = company.historical_is
        hist_bs = company.historical_bs
        assumptions = company.assumptions
        
        base_is = hist_is[-1]
        base_bs = hist_bs[-1]
        
        # EBITDA = EBIT + D&A, ước lượng D&A từ depr_to_revenue assumption
        depr_est = assumptions.depr_to_revenue[0] * base_is.revenue
        ebitda_base = base_is.ebit + depr_est
        
        ev_ebitda_mult = target_multiple if target_multiple is not None else assumptions.target_ev_ebitda
        ev = ebitda_base * ev_ebitda_mult
        
        # Net Debt = Total Debt - Cash & equivalents
        net_debt = base_bs.short_term_debt + base_bs.long_term_debt - base_bs.cash_and_equivalents
        equity_val = ev - net_debt
        
        fvps = (equity_val / shares) * 1000.0
        return max(0.0, fvps)
        
    else:
        # Ngân hàng: P/B so sánh (gọi Justified P/B)
        # Thực tế, Justified P/B được tính trong bank_general.py
        # Ở đây ta trả về giá trị P/B của base case
        # (Sẽ được handle tích hợp qua engine định giá tổng hợp)
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        model = BankGeneralValuationModel(company)
        pb_res = model.calculate_pb_valuation()
        return pb_res["fair_value_per_share"]
