import statistics
from typing import Dict, Any
from .base import BaseValuationModel
from valuation.models.financials import Company
from valuation.config import load_defaults


class SOTPValuationModel(BaseValuationModel):
    """
    SOTP (Sum of the Parts) dành cho các Tập đoàn đa ngành.

    Phiên bản MỚI:
    - Nhất quán phân tách EV và Equity.
    - Tổng_EV = Sum(các mảng định giá theo EV)
    - Equity_từ_EV = Tổng_EV - Nợ vay ròng tập đoàn.
    - Tổng_Equity = Equity_từ_EV + Sum(các mảng định giá theo Equity).
    - Trừ đi lợi ích CĐTS.
    """

    def __init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any]):
        super().__init__(ticker, current_financials, assumptions)
        self.valuation_warnings.append("VALUATION_PROXY")

    @classmethod
    def from_pydantic(cls, company: Company) -> "SOTPValuationModel":
        bs = company.historical_bs[-1]
        cfg = load_defaults().get("proxy_valuation", {})
        cf_dict = {
            'total_equity': bs.parent_equity * 1e9,
            'cash_and_equivalents': bs.cash_and_equivalents * 1e9,
            'total_debt': (bs.short_term_debt + bs.long_term_debt) * 1e9,
            'minority_interest': getattr(bs, 'minority_interest', 0.0) * 1e9,
            'net_income_history': [is_.net_income for is_ in company.historical_is],  # tỷ
            'shares_outstanding': company.shares_outstanding * 1e6,
            'current_price': company.current_price,
        }
        
        assumptions = {
            'sotp_operating_pe': cfg.get('sotp_operating_pe', 11.0),
            'sotp_earnings_weight': cfg.get('sotp_earnings_weight', 0.6),
            'sotp_holding_discount': getattr(company.assumptions, 'sotp_discount', cfg.get('sotp_holding_discount', 0.10)),
            'sotp_segments': getattr(company.assumptions, 'sotp_segments', [])
        }
        return cls(company.ticker, cf_dict, assumptions)

    def perform_valuation(self) -> Dict[str, Any]:
        shares = self.current_financials.get('shares_outstanding', 1)
        equity = self.current_financials.get('total_equity', 0)
        cash = self.current_financials.get('cash_and_equivalents', 0)
        total_debt = self.current_financials.get('total_debt', 0)
        minority_interest = self.current_financials.get('minority_interest', 0)
        net_debt = total_debt - cash
        
        hist = [x for x in self.current_financials.get('net_income_history', []) if x is not None]

        operating_pe = self.assumptions.get('sotp_operating_pe', 11.0)
        w_earn = self.assumptions.get('sotp_earnings_weight', 0.6)
        discount = self.assumptions.get('sotp_holding_discount', 0.10)
        sotp_segments = self.assumptions.get('sotp_segments', [])

        if shares <= 0:
            return {"blended_fair_value_per_share": 0.0, "flags": ["NO_SOTP_DATA"]}

        flags = []
        if sotp_segments and len(sotp_segments) > 0:
            # AI_SOTP_MODE
            total_ev_segments = 0.0
            total_equity_segments = 0.0
            
            for seg in sotp_segments:
                # Get value in VND
                try:
                    val_billion = float(seg.get('gia_tri', 0) or 0)
                except ValueError:
                    val_billion = 0.0
                
                val = val_billion * 1e9
                
                try:
                    mult = float(seg.get('multiple_ky_vong', 0) or 0)
                except ValueError:
                    mult = 0.0
                
                if mult > 0:
                    segment_value = val * mult
                else:
                    # Fallback to absolute value if mult is 0/null (e.g., DCF already outputs absolute value)
                    segment_value = val
                
                loai_gia_tri = str(seg.get('loai_gia_tri', '')).upper()
                
                if 'EV' in loai_gia_tri:
                    total_ev_segments += segment_value
                else:
                    # Mặc định coi là Equity nếu không rõ hoặc là Equity
                    total_equity_segments += segment_value
            
            # Tính Equity từ EV
            equity_from_ev = total_ev_segments - net_debt
            
            # Tổng VCSH (trừ CĐTS)
            total_equity_value = equity_from_ev + total_equity_segments - minority_interest
            
            # Giá mục tiêu
            sotp_ps = (total_equity_value / shares) * (1 - discount)
            
            flags = ["AI_SOTP_MODE"]
            if "VALUATION_PROXY" in self.valuation_warnings:
                self.valuation_warnings.remove("VALUATION_PROXY")
                
            earnings_ps = 0.0
            nav_ps = 0.0
        else:
            # PROXY_MODE: Phần vận hành (Earnings) + NAV
            flags = ["VALUATION_PROXY"]
            norm_ni = 0.0
            if hist:
                window = hist[-3:] if len(hist) >= 3 else hist
                norm_ni = statistics.median(window) * 1e9
            operating_value = max(0.0, norm_ni) * operating_pe
            earnings_ps = operating_value / shares

            nav_ps = equity / shares if equity > 0 else 0.0

            if earnings_ps <= 0:
                w_earn = 0.0
                flags.append("SOTP_NAV_FALLBACK")

            sotp_ps = (w_earn * earnings_ps + (1 - w_earn) * nav_ps) * (1 - discount)
            
        sotp_ps = max(0.0, sotp_ps)

        # ------------------------------------------------------------------
        # D28 — CỔNG CHẶN: proxy không được phép xuất bản số tự tin.
        #
        # Khiếm khuyết thật của SOTP cũ không phải "kém chính xác" mà là ĐƯA RA
        # MỘT CON SỐ ĐẦY TỰ TIN từ một proxy vô nghĩa: VIC ra 16.911đ trong khi
        # thị giá 208.500đ (-92%). Giá trị VIC nằm ở cổ phần công ty con niêm yết
        # và quỹ đất ghi giá gốc — công thức (0,6 × LNST×11 + 0,4 × VCSH sổ sách)
        # không mô tả được gì cả.
        #
        # Thà một khoảng trống ĐƯỢC GHI NHẬN còn hơn một con số sai đầy tự tin.
        # ------------------------------------------------------------------
        price = self.current_financials.get("current_price")
        not_rated = False
        cfg = load_defaults().get("proxy_valuation", {})
        max_div = float(cfg.get("proxy_max_divergence", 0.50))
        is_proxy_mode = not (sotp_segments and len(sotp_segments) > 0)

        if is_proxy_mode and price and price > 0 and sotp_ps > 0:
            div = abs(sotp_ps - price) / price
            if div > max_div:
                not_rated = True
                flags.append(
                    f"PROXY_IMPLAUSIBLE: proxy SOTP lệch {((sotp_ps - price) / price):+.0%} "
                    f"so thị giá (ngưỡng ±{max_div:.0%}) — proxy sổ sách/lợi nhuận không "
                    f"mô tả được cấu trúc tập đoàn này. Cần khai báo cổ phần công ty con "
                    f"trong config/sotp_holdings.yaml."
                )
        if is_proxy_mode and price and price > 0 and sotp_ps <= 0:
            not_rated = True
            flags.append("PROXY_IMPLAUSIBLE: proxy SOTP ra giá trị <= 0")

        if not_rated:
            flags.append("NOT_RATED")

        return {
            "blended_fair_value_per_share": sotp_ps, # Dùng luôn làm target price
            "earnings_value_per_share": earnings_ps if not (sotp_segments and len(sotp_segments) > 0) else sotp_ps,
            "nav_per_share": nav_ps if not (sotp_segments and len(sotp_segments) > 0) else 0.0,
            "discount_applied": discount,
            "not_rated": not_rated,
            "flags": flags,
        }
