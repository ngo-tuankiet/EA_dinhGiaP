import datetime
from typing import Dict, Any
from .base import BaseValuationModel, input_number
from valuation.models.financials import Company
from valuation.config import load_defaults


def default_project_rate(company: Company) -> float:
    """Suất chiết khấu mặc định cho dòng tiền dự án RNAV theo config proxy_valuation.rnav_project_discount_rate:
    'wacc' (mặc định) — dòng tiền dự án là dòng tiền TRƯỚC tài trợ (nợ vay dự án nằm trong VCSH mẹ hợp nhất) nên
    đi cặp WACC (Damodaran); 'coe' — cách cũ s6."""
    a = company.assumptions
    if load_defaults()["proxy_valuation"]["rnav_project_discount_rate"] == "coe":
        return a.cost_of_equity or (a.risk_free_rate + a.beta * a.erp)
    from valuation.engine.wacc import company_wacc

    return company_wacc(company)


class RNAVValuationModel(BaseValuationModel):
    """
    RNAV (Revalued Net Asset Value) cho Bất động sản — đẳng thức NAV điều chỉnh (CFA asset-based;
    Damodaran, BĐS đang phát triển định giá theo DCF dự án cộng tài sản ròng ngoài dự án):

        NAV = VCSH mẹ + phần đánh giá lại sau thuế × (1 − rnav_discount)

    VCSH mẹ đã chứa MỌI tài sản ròng ngoài dự án (tiền, phải thu, đầu tư, nợ vay, tiền khách trả trước,
    CĐKKS đã loại). Chiết khấu chỉ áp lên phần đánh giá lại (ước lượng), không áp lên VCSH sổ sách
    (đã kiểm toán) — xem DECISIONS.md (điều tra 2026-07).

    - AI_RNAV_MODE (rnav_projects đủ đầu vào): đánh giá lại = Σ sở hữu × [PV(dòng tiền dự án còn lại sau
      thuế) − giá sổ ròng dự án].
    - PROXY (không có/thiếu đầu vào dự án): đánh giá lại = (tồn kho + BĐS đầu tư) × premium × (1 − thuế).
    """

    def __init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any]):
        super().__init__(ticker, current_financials, assumptions)
        self.valuation_warnings.append("VALUATION_PROXY")

    @classmethod
    def from_pydantic(cls, company: Company) -> "RNAVValuationModel":
        bs = company.historical_bs[-1]
        a = company.assumptions
        cf_dict = {
            'total_equity': bs.parent_equity * 1e9,
            'inventory': bs.inventory * 1e9,
            'investment_property': bs.investment_property * 1e9,
            'shares_outstanding': company.shares_outstanding * 1e6,
            'current_price': company.current_price,
        }
        assumptions = {
            'rnav_land_premium': a.rnav_revaluation_premium,
            'rnav_discount': a.rnav_discount,
            'rnav_wacc': a.rnav_wacc if a.rnav_wacc is not None else default_project_rate(company),
            # Thuế phổ thông, không dùng thuế hiệu dụng: thu nhập chuyển nhượng BĐS không hưởng ưu đãi, và
            # thuế hiệu dụng bị méo bởi lãi LDLK sau thuế (BCM 8,9%) hoặc chi phí không khấu trừ (kẹp 25%).
            'tax_rate': float(load_defaults()["sector_tax_rates"]["default"]),
            'rnav_projects': a.rnav_projects or [],
        }
        return cls(company.ticker, cf_dict, assumptions)

    @staticmethod
    def project_revaluation(projects, wacc: float, tax: float, current_year: int):
        """(Σ sở hữu × [PV(dòng tiền còn lại sau thuế) − giá sổ ròng] — đồng, [trường thiếu]).

        Mỗi dự án (phần CHƯA ghi nhận doanh thu): R = diện tích × giá bán, C = diện tích × chi phí toàn bộ,
        B = giá sổ ròng (tồn kho/XDCB/BĐS đầu tư của dự án − tiền khách đã trả trước). Tiền còn thu − chi phí
        còn lại = (R − C) + B và thuế = t × (R − C), nên dòng tiền còn lại = (R − C)(1 − t) + B, chia đều từ
        năm mở bán tới năm bàn giao (cuối năm, năm hiện tại = năm 1). Không nhân tỷ lệ đã bán: căn chưa bán
        vẫn là giá trị sẽ thu.
        """
        total, missing = 0.0, []
        for i, p in enumerate(projects, 1):
            name = p.get('ten_du_an') or f"#{i}"
            nsa = input_number(p, 'dien_tich_san_thuong_pham_m2')
            area, far = input_number(p, 'area_ha'), input_number(p, 'he_so_su_dung_dat')
            if nsa is None and area is not None and far is not None:
                nsa = area * 10_000 * far
            raw = {
                'dien_tich_san_thuong_pham_m2': nsa,
                'gia_ban_tren_m2': input_number(p, 'gia_ban_tren_m2'),
                # Không suy chi phí từ bien_ln_rong: không rõ biên trước hay sau thuế (luật vàng #1).
                'chi_phi_tren_m2': input_number(p, 'chi_phi_tren_m2'),
                'ty_le_so_huu': input_number(p, 'ty_le_so_huu'),  # bắt buộc, không mặc định 100%
                'gia_tri_so_sach_rong_ty': input_number(p, 'gia_tri_so_sach_rong_ty'),
            }
            lack = [k for k, v in raw.items() if v is None]
            if lack:
                missing += [f"{name}.{k}" for k in lack]
                continue
            vals = {k: float(v or 0.0) for k, v in raw.items()}  # đã đủ, chỉ để thu hẹp kiểu
            book = vals['gia_tri_so_sach_rong_ty'] * 1e9
            cf_total = vals['dien_tich_san_thuong_pham_m2'] * (vals['gia_ban_tren_m2'] - vals['chi_phi_tren_m2']) * (1 - tax) + book
            start = max(current_year, int(input_number(p, 'nam_mo_ban') or current_year))
            end = max(start, int(input_number(p, 'nam_ban_giao') or current_year))
            n = end - start + 1
            pv = sum(cf_total / n / (1 + wacc) ** (y - current_year + 1) for y in range(start, end + 1))
            total += vals['ty_le_so_huu'] / 100.0 * (pv - book)
        return total, missing

    def perform_valuation(self) -> Dict[str, Any]:
        shares = self.current_financials.get('shares_outstanding', 1)
        equity = self.current_financials.get('total_equity', 0)
        inventory = self.current_financials.get('inventory', 0)
        inv_property = self.current_financials.get('investment_property', 0)

        rnav_projects = self.assumptions.get('rnav_projects') or []
        rnav_discount = self.assumptions['rnav_discount']
        tax = self.assumptions['tax_rate']

        current_year = datetime.datetime.now().year
        flags = []
        missing = []
        if rnav_projects:
            reval, missing = self.project_revaluation(rnav_projects, self.assumptions['rnav_wacc'], tax, current_year)
        if rnav_projects and not missing:
            flags = ["AI_RNAV_MODE"]
            if "VALUATION_PROXY" in self.valuation_warnings:
                self.valuation_warnings.remove("VALUATION_PROXY")
        else:
            # PROXY: chỉ đánh giá lại tài sản có giá thị trường khác giá sổ (CFA adjusted book value) — tồn
            # kho BĐS và BĐS đầu tư; KHÔNG cộng thặng dư lên phải thu/đầu tư tài chính/XDCB.
            reval = (inventory + inv_property) * self.assumptions['rnav_land_premium'] * (1 - tax)
            flags = ["VALUATION_PROXY"]
            if missing:
                # Dự án nhập thiếu → không định giá nửa vời; vẫn bị chặn công bố qua VALUATION_PROXY.
                flags.append("RNAV_PROJECT_INPUT_MISSING: " + ", ".join(missing))
        nav_equity = equity + reval
        rnav_fvps = (equity + reval * (1 - rnav_discount)) / shares if shares > 0 else 0

        return {
            "blended_fair_value_per_share": rnav_fvps, # Use this directly for target price
            "rnav_fvps": rnav_fvps,
            "nav_equity_before_discount": nav_equity,
            "revaluation_after_tax": reval,
            "discount_applied": rnav_discount,
            "flags": flags,
        }
