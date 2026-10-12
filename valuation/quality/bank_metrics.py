import pandas as pd

def _get_val(df: pd.DataFrame, keywords: list, period_filter=None, default=0.0):
    """
    Helper to get the value for a specific line item using keyword matching.
    """
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

class BankMetricsCalculator:
    def __init__(self, financials_df: pd.DataFrame):
        """
        financials_df must be in long format:
        columns: ticker, fiscal_year, fiscal_quarter, statement, line_item, value
        """
        self.df = financials_df

    def calculate_metrics(self, year: int, quarter: int) -> dict:
        """
        Calculate key metrics for a specific period (year, quarter).
        """
        curr = (year, quarter)
        
        # Determine previous period (TTM or QoQ depending on metric)
        if quarter == 0: # Annual data
            prev = (year - 1, 0)
        else:
            prev = (year, quarter - 1) if quarter > 1 else (year - 1, 4)
            
        # Balances
        total_assets = _get_val(self.df, ["Tổng tài sản", "TỔNG TÀI SẢN"], curr)
        total_equity = _get_val(self.df, ["Vốn chủ sở hữu", "VỐN CHỦ SỞ HỮU"], curr)
        customer_loans = _get_val(self.df, ["Cho vay khách hàng", "CHO VAY KHÁCH HÀNG"], curr)
        customer_deposits = _get_val(self.df, ["Tiền gửi của khách hàng", "TIỀN GỬI CỦA KHÁCH HÀNG", "Tiền gửi theo loại hình"], curr)
        
        npl = _get_val(self.df, ["Nợ nhóm 3", "Nợ nhóm 4", "Nợ nhóm 5", "Nợ xấu"], curr) # This might require aggregation if split
        npl_3 = _get_val(self.df, ["Nợ dưới tiêu chuẩn"], curr)
        npl_4 = _get_val(self.df, ["Nợ nghi ngờ"], curr)
        npl_5 = _get_val(self.df, ["Nợ có khả năng mất vốn"], curr)
        total_npl = npl_3 + npl_4 + npl_5
        if total_npl == 0.0: total_npl = npl # fallback
        
        llp = _get_val(self.df, ["Dự phòng rủi ro cho vay khách hàng", "Dự phòng rủi ro"], curr)
        # NPL and LLP usually negative or absolute in DB?
        llp = abs(llp)

        # Income Statement (Annualized or Quarterly)
        # Assuming values in DB are quarterly if quarter != 0, else annual.
        net_interest_income = _get_val(self.df, ["Thu nhập lãi thuần", "Lãi/lỗ thuần từ hoạt động dịch vụ"], curr) # Thu nhập lãi thuần
        net_interest_income = _get_val(self.df, ["Thu nhập lãi thuần"], curr, default=_get_val(self.df, ["Thu nhập lãi và các khoản", "Chi phí lãi và các"], curr)) 
        
        # Actually in VN bctc it's: Thu nhập lãi và các khoản tương tự - Chi phí lãi
        interest_income = _get_val(self.df, ["Thu nhập lãi và các khoản tương tự"], curr)
        interest_expense = abs(_get_val(self.df, ["Chi phí lãi và các khoản chi phí tương tự", "Chi phí lãi"], curr))
        nii = interest_income - interest_expense
        if nii == 0: nii = net_interest_income
        
        operating_expense = abs(_get_val(self.df, ["Chi phí hoạt động"], curr))
        total_operating_income = _get_val(self.df, ["Tổng thu nhập hoạt động", "Thu nhập hoạt động thuần"], curr)
        if total_operating_income == 0:
            total_operating_income = nii + _get_val(self.df, ["Lãi/lỗ thuần từ hoạt động dịch vụ", "Lãi/lỗ thuần từ hoạt động kinh doanh"], curr)
            
        provision_expense = abs(_get_val(self.df, ["Chi phí dự phòng", "Dự phòng rủi ro tín dụng"], curr))
        net_income = _get_val(self.df, ["Lợi nhuận sau thuế"], curr)
        
        # Calculate derived metrics
        ldr = (customer_loans / customer_deposits) if customer_deposits > 0 else 0
        npl_ratio = (total_npl / customer_loans) if customer_loans > 0 else 0
        npl_coverage = (llp / total_npl) if total_npl > 0 else 0
        
        # Annualized metrics (assuming quarterly data implies * 4 for simple annualization)
        annual_factor = 4 if quarter != 0 else 1
        
        roa = (net_income * annual_factor / total_assets) if total_assets > 0 else 0
        roe = (net_income * annual_factor / total_equity) if total_equity > 0 else 0
        
        nim = (nii * annual_factor / total_assets) if total_assets > 0 else 0 # Approx based on total assets instead of avg earning assets
        cir = (operating_expense / total_operating_income) if total_operating_income > 0 else 0
        
        return {
            "LDR": round(ldr, 4),
            "NPL_Ratio": round(npl_ratio, 4),
            "NPL_Coverage": round(npl_coverage, 4),
            "NIM": round(nim, 4),
            "CIR": round(cir, 4),
            "ROA": round(roa, 4),
            "ROE": round(roe, 4)
        }
