import pandas as pd
from typing import Dict, Any
# Note: we might not need router import if we pass sector directly

def _get_val(df: pd.DataFrame, keywords: list, period_filter: tuple = None, default=0.0):
    if df is None or df.empty:
        return 0.0
    
    if period_filter is not None:
        sub_df = df[(df['fiscal_year'] == period_filter[0]) & (df['fiscal_quarter'] == period_filter[1])]
    else:
        sub_df = df
        
    for kw in keywords:
        matches = sub_df[sub_df['line_item'].str.contains(kw, case=False, na=False)]
        if not matches.empty:
            return float(matches.iloc[0]['value'])
    return default

def calculate_altman_z_score(df: pd.DataFrame, curr_period: tuple, market_cap: float) -> float:
    total_assets = _get_val(df, ["Tổng tài sản", "total_assets"], curr_period)
    if total_assets <= 0: return 0.0
    
    current_assets = _get_val(df, ["Tài sản ngắn hạn", "current_assets"], curr_period)
    current_liabilities = _get_val(df, ["Nợ ngắn hạn", "current_liabilities"], curr_period)
    working_capital = current_assets - current_liabilities
    
    retained_earnings = _get_val(df, ["Lợi nhuận sau thuế chưa phân phối", "retained_earnings"], curr_period)
    
    pbt = _get_val(df, ["Lợi nhuận kế toán trước thuế", "net_accounting_profit_loss_before_tax"], curr_period)
    interest_expense = abs(_get_val(df, ["Chi phí lãi vay", "interest_expenses"], curr_period))
    ebit = pbt + interest_expense
    
    total_liabilities = _get_val(df, ["Nợ phải trả", "liabilities"], curr_period)
    sales = _get_val(df, ["Doanh thu thuần", "net_sales"], curr_period)
    
    T1 = working_capital / total_assets
    T2 = retained_earnings / total_assets
    T3 = ebit / total_assets
    T4 = market_cap / total_liabilities if total_liabilities > 0 else 0.0
    T5 = sales / total_assets
    
    z = 1.2 * T1 + 1.4 * T2 + 3.3 * T3 + 0.6 * T4 + 1.0 * T5
    return round(z, 2)

def calculate_beneish_m_score(df: pd.DataFrame, curr_period: tuple, prev_period: tuple) -> float:
    def get(kw, period): return _get_val(df, kw, period)
    
    sales_t = get(["Doanh thu thuần", "net_sales"], curr_period)
    sales_t1 = get(["Doanh thu thuần", "net_sales"], prev_period)
    if sales_t1 <= 0 or sales_t <= 0: return 0.0
    
    rec_t = get(["Phải thu ngắn hạn", "short_term_receivables"], curr_period)
    rec_t1 = get(["Phải thu ngắn hạn", "short_term_receivables"], prev_period)
    DSRI = (rec_t / sales_t) / (rec_t1 / sales_t1) if (sales_t1 > 0 and rec_t1 > 0) else 1.0
    
    gp_t = get(["Lợi nhuận gộp", "gross_profit"], curr_period)
    gp_t1 = get(["Lợi nhuận gộp", "gross_profit"], prev_period)
    gm_t = gp_t / sales_t if sales_t > 0 else 0
    gm_t1 = gp_t1 / sales_t1 if sales_t1 > 0 else 0
    GMI = gm_t1 / gm_t if gm_t > 0 else 1.0
    
    SGI = sales_t / sales_t1 if sales_t1 > 0 else 1.0
    
    ca_t = get(["Tài sản ngắn hạn", "current_assets"], curr_period)
    ca_t1 = get(["Tài sản ngắn hạn", "current_assets"], prev_period)
    ppe_t = get(["Tài sản cố định", "fixed_assets"], curr_period)
    ppe_t1 = get(["Tài sản cố định", "fixed_assets"], prev_period)
    ta_t = get(["Tổng tài sản", "total_assets"], curr_period)
    ta_t1 = get(["Tổng tài sản", "total_assets"], prev_period)
    
    aq_t = (ta_t - ca_t - ppe_t) / ta_t if ta_t > 0 else 0
    aq_t1 = (ta_t1 - ca_t1 - ppe_t1) / ta_t1 if ta_t1 > 0 else 0
    AQI = aq_t / aq_t1 if aq_t1 != 0.0 else 1.0
    
    depr_t = get(["Khấu hao", "depreciation_and_amortization"], curr_period)
    depr_t1 = get(["Khấu hao", "depreciation_and_amortization"], prev_period)
    depi_t = depr_t / (ppe_t + depr_t) if (ppe_t + depr_t) > 0 else 0
    depi_t1 = depr_t1 / (ppe_t1 + depr_t1) if (ppe_t1 + depr_t1) > 0 else 0
    DEPI = depi_t1 / depi_t if depi_t > 0 else 1.0
    
    m_score = -6.065 + 0.823 * DSRI + 0.906 * GMI + 0.593 * AQI + 0.717 * SGI + 0.107 * DEPI
    return round(m_score, 2)

def calculate_piotroski_f_score(df: pd.DataFrame, curr_period: tuple, prev_period: tuple) -> int:
    def get(kw, period): return _get_val(df, kw, period)
    f_score = 0
    
    ni_t = get(["Lợi nhuận sau thuế", "net_profit_loss_after_tax"], curr_period)
    ta_t = get(["Tổng tài sản", "total_assets"], curr_period)
    ta_t1 = get(["Tổng tài sản", "total_assets"], prev_period)
    
    if ta_t <= 0: return 5 
    
    if (ni_t / ta_t) > 0: f_score += 1
    
    cfo_t = get(["Lưu chuyển tiền thuần từ hoạt động kinh doanh", "net_cash_from_operating_activities"], curr_period)
    if cfo_t > 0: f_score += 1
    
    ni_t1 = get(["Lợi nhuận sau thuế", "net_profit_loss_after_tax"], prev_period)
    if (ni_t / ta_t) > (ni_t1 / ta_t1 if ta_t1 > 0 else 0): f_score += 1
    
    if cfo_t > ni_t: f_score += 1
    
    ltd_t = get(["Vay và nợ thuê tài chính dài hạn", "long_term_borrowings"], curr_period)
    ltd_t1 = get(["Vay và nợ thuê tài chính dài hạn", "long_term_borrowings"], prev_period)
    if (ltd_t / ta_t) < (ltd_t1 / ta_t1 if ta_t1 > 0 else 0): f_score += 1
    
    ca_t = get(["Tài sản ngắn hạn", "current_assets"], curr_period)
    cl_t = get(["Nợ ngắn hạn", "current_liabilities"], curr_period)
    ca_t1 = get(["Tài sản ngắn hạn", "current_assets"], prev_period)
    cl_t1 = get(["Nợ ngắn hạn", "current_liabilities"], prev_period)
    if (ca_t / cl_t if cl_t > 0 else 0) > (ca_t1 / cl_t1 if cl_t1 > 0 else 0): f_score += 1
    
    eq_t = get(["Vốn góp của chủ sở hữu", "share_capital"], curr_period)
    eq_t1 = get(["Vốn góp của chủ sở hữu", "share_capital"], prev_period)
    if eq_t <= eq_t1: f_score += 1
    
    gp_t = get(["Lợi nhuận gộp", "gross_profit"], curr_period)
    sales_t = get(["Doanh thu thuần", "net_sales"], curr_period)
    gp_t1 = get(["Lợi nhuận gộp", "gross_profit"], prev_period)
    sales_t1 = get(["Doanh thu thuần", "net_sales"], prev_period)
    if (gp_t / sales_t if sales_t > 0 else 0) > (gp_t1 / sales_t1 if sales_t1 > 0 else 0): f_score += 1
    
    if (sales_t / ta_t) > (sales_t1 / ta_t1 if ta_t1 > 0 else 0): f_score += 1
    
    return f_score

def run_qc_checks(ticker: str, sector_name: str, financials: pd.DataFrame, market_cap: float = 0.0) -> Dict[str, Any]:
    """
    Chạy các bài kiểm tra chất lượng (QC) cho một cổ phiếu.
    Không áp dụng cho Ngân hàng, Chứng khoán, Bảo hiểm.
    """
    bank_sectors = ['Ngân hàng', 'Banks']
    other_fin_sectors = ['Chứng khoán', 'Bảo hiểm', 'Financial Services', 'Insurance', 'Securities', 'Dịch vụ tài chính']
    
    # Danh sách các sector đã vượt qua cổng chất lượng (validated)
    VALIDATED_SECTORS = {'Ngân hàng', 'Banks', 'Chứng khoán', 'Securities', 'Thép', 'Steel', 'Công nghệ', 'Technology'}
    
    flags = []
    if not sector_name or sector_name not in VALIDATED_SECTORS:
        flags.append("SECTOR_UNVALIDATED")
        
    if sector_name and (sector_name in bank_sectors or sector_name in other_fin_sectors):
        flags.append("financial_sector_skipped_standard_qc")
        if sector_name in other_fin_sectors:
            flags.append("FINANCIAL_QC_MISSING")
            
        return {
            "altman_z_score": None,
            "beneish_m_score": None,
            "piotroski_f_score": None,
            "flags": flags
        }
    
    if financials is None or financials.empty:
        return {"altman_z_score": None, "beneish_m_score": None, "piotroski_f_score": None, "flags": ["DATA_INCOMPLETE"]}
        
    latest_year = financials['fiscal_year'].max()
    sub_df = financials[financials['fiscal_year'] == latest_year]
    
    if 0 in sub_df['fiscal_quarter'].values:
        curr_period = (latest_year, 0)
        prev_period = (latest_year - 1, 0)
    else:
        latest_q = sub_df['fiscal_quarter'].max()
        curr_period = (latest_year, latest_q)
        if latest_q > 1:
            prev_period = (latest_year, latest_q - 1)
        else:
            prev_period = (latest_year - 1, 4)
            
    z_score = calculate_altman_z_score(financials, curr_period, market_cap)
    m_score = calculate_beneish_m_score(financials, curr_period, prev_period)
    f_score = calculate_piotroski_f_score(financials, curr_period, prev_period)
    
    if z_score != 0.0 and z_score < 1.81:
        flags.append("z_score_distress")
    if m_score != 0.0 and m_score > -1.78:
        flags.append("m_score_manipulation_risk")
    if f_score <= 3:
        flags.append("f_score_poor_quality")
        
    if "z_score_distress" in flags or "m_score_manipulation_risk" in flags or "f_score_poor_quality" in flags:
        flags.append("POOR_QUALITY")
        
    return {
        "altman_z_score": z_score,
        "beneish_m_score": m_score,
        "piotroski_f_score": f_score,
        "flags": flags
    }
