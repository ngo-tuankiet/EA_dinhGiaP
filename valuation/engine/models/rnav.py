import datetime
from typing import Dict, Any
from .base import BaseValuationModel
from valuation.models.financials import Company
from valuation.config import load_defaults


class RNAVValuationModel(BaseValuationModel):
    """
    RNAV (Revalued Net Asset Value) cho Bất động sản.

    Phiên bản MỚI: 
    Nếu có rnav_projects (AI bóc tách), sử dụng mô hình DCF để chiết khấu dòng tiền từng dự án.
    Nếu không có, fallback về định giá lại HÀNG TỒN KHO & BĐS ĐẦU TƯ (PROXY).
    """

    def __init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any]):
        super().__init__(ticker, current_financials, assumptions)
        self.valuation_warnings.append("VALUATION_PROXY")

    @classmethod
    def from_pydantic(cls, company: Company) -> "RNAVValuationModel":
        bs = company.historical_bs[-1]
        cfg = load_defaults().get("proxy_valuation", {})
        cf_dict = {
            'total_equity': bs.parent_equity * 1e9,
            'cash_and_equivalents': bs.cash_and_equivalents * 1e9,
            'total_debt': (bs.short_term_debt + bs.long_term_debt) * 1e9,
            'minority_interest': getattr(bs, 'minority_interest', 0.0) * 1e9,
            'inventory': bs.inventory * 1e9,
            'investment_property': bs.other_long_term_assets * 1e9,
            'shares_outstanding': company.shares_outstanding * 1e6,
            'current_price': company.current_price,
        }
        
        # WACC: Có thể lấy từ WACC tổng của cty, tạm dùng chi phí vốn cổ phần hoặc rnav_wacc
        wacc_default = getattr(company.assumptions, 'cost_of_equity', 0.11)
        if wacc_default is None:
            wacc_default = 0.11
            
        assumptions = {
            'rnav_land_premium': getattr(company.assumptions, 'rnav_revaluation_premium', cfg.get('rnav_land_premium', 0.30)),
            'rnav_discount': getattr(company.assumptions, 'rnav_discount', 0.45), # analyst nhập
            'rnav_wacc': getattr(company.assumptions, 'rnav_wacc', wacc_default), # analyst nhập
            'rnav_projects': getattr(company.assumptions, 'rnav_projects', [])
        }
        return cls(company.ticker, cf_dict, assumptions)

    def perform_valuation(self) -> Dict[str, Any]:
        shares = self.current_financials.get('shares_outstanding', 1)
        equity = self.current_financials.get('total_equity', 0)
        cash = self.current_financials.get('cash_and_equivalents', 0)
        total_debt = self.current_financials.get('total_debt', 0)
        minority_interest = self.current_financials.get('minority_interest', 0)
        
        inventory = self.current_financials.get('inventory', 0)
        inv_property = self.current_financials.get('investment_property', 0)

        rnav_projects = self.assumptions.get('rnav_projects', [])
        wacc = self.assumptions.get('rnav_wacc', 0.11)
        rnav_discount = self.assumptions.get('rnav_discount', 0.45)
        current_year = datetime.datetime.now().year
        
        flags = []

        if rnav_projects and len(rnav_projects) > 0:
            # AI_RNAV_MODE (DCF Dự án)
            sum_npv = 0.0
            for proj in rnav_projects:
                # Diện tích sàn (m2)
                nsa = proj.get('dien_tich_san_thuong_pham_m2')
                if nsa is None or str(nsa).lower() == 'null':
                    # Thử lấy ha đất x hệ số
                    he_so = proj.get('he_so_su_dung_dat', 1.0)
                    area_ha = proj.get('area_ha', 0) # Fallback if any
                    nsa = float(area_ha) * 10000 * float(he_so or 1.0)
                else:
                    nsa = float(nsa)
                
                # Giá bán (VND/m2)
                gia_ban = float(proj.get('gia_ban_tren_m2', 0) or 0)
                
                # Chi phí / Biên LN
                bien_ln = proj.get('bien_ln_rong', None)
                if bien_ln is not None and str(bien_ln).lower() != 'null':
                    loi_nhuan_m2 = gia_ban * (float(bien_ln) / 100.0)
                else:
                    chi_phi = float(proj.get('chi_phi_tren_m2', 0) or 0)
                    loi_nhuan_m2 = gia_ban - chi_phi
                    
                # Doanh thu / Dòng tiền ròng dự án
                ty_le_so_huu = float(proj.get('ty_le_so_huu', 100) or 100) / 100.0
                ty_le_da_ban = float(proj.get('ty_le_da_ban', 100) or 100) / 100.0
                
                # Tổng CF (để chiết khấu)
                total_project_cf = nsa * loi_nhuan_m2 * ty_le_so_huu * ty_le_da_ban
                
                # Phân bổ DCF (mở bán -> bàn giao)
                nam_mo_ban = int(float(proj.get('nam_mo_ban', current_year) or current_year))
                nam_ban_giao = int(float(proj.get('nam_ban_giao', current_year) or current_year))
                
                # Tránh năm quá khứ
                start_year = max(current_year, nam_mo_ban)
                end_year = max(start_year, nam_ban_giao)
                duration = end_year - start_year + 1
                
                cf_per_year = total_project_cf / duration
                
                npv_project = 0.0
                for y in range(start_year, end_year + 1):
                    t = y - current_year + 1 # năm 1, 2, 3...
                    npv_project += cf_per_year / ((1 + wacc) ** t)
                
                sum_npv += npv_project

            # NAV VCSH (Trừ nợ ròng)
            # NAV = NPV_Dự_án + Tiền mặt - Nợ_vay - CĐTS
            nav_equity = sum_npv + cash - total_debt - minority_interest
            
            nav_sau_chiet_khau = nav_equity * (1 - rnav_discount)
            rnav_fvps = (nav_sau_chiet_khau / shares) if shares > 0 else 0
            
            flags = ["AI_RNAV_MODE"]
            if "VALUATION_PROXY" in self.valuation_warnings:
                self.valuation_warnings.remove("VALUATION_PROXY")
                
        else:
            # PROXY_MODE
            # Chiết khấu (rnav_discount) chỉ áp cho PHẦN ĐÁNH GIÁ LẠI (premium
            # đất/BĐS đầu tư — số liệu ước lượng, có rủi ro/thanh khoản khi
            # hiện thực hoá), KHÔNG áp cho vốn CSH sổ sách (đã kiểm toán, chắc
            # chắn). Bản trước chiết khấu cả NAV gộp (equity + premium) —
            # với công ty quỹ đất lâu năm (đất ghi giá gốc từ nhiều năm trước,
            # premium/equity lớn), điều này có thể kéo FV xuống DƯỚI CẢ giá trị
            # sổ sách — phi lý cho công ty có tài sản lõi bị định giá thấp
            # trên sổ sách. Điều tra 2026-07, xem DECISIONS.md.
            premium = self.assumptions.get('rnav_land_premium', 0.30)
            revaluation_surplus = (inventory + inv_property) * premium
            surplus_sau_chiet_khau = revaluation_surplus * (1 - rnav_discount)
            nav_equity = equity + surplus_sau_chiet_khau
            rnav_fvps = (nav_equity / shares) if shares > 0 else 0
            flags = ["VALUATION_PROXY"]

        return {
            "blended_fair_value_per_share": rnav_fvps, # Use this directly for target price
            "rnav_fvps": rnav_fvps,
            "nav_equity_before_discount": nav_equity,
            "discount_applied": rnav_discount,
            "flags": flags,
        }
