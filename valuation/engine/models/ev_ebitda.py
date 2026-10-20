from typing import Dict, Any
import statistics
from .base import BaseValuationModel, midcycle_level
from valuation.config import load_defaults
from valuation.models.financials import Company


class EVEBITDAValuationModel(BaseValuationModel):
    """
    Định giá EV/EBITDA chủ đạo cho ngành lợi nhuận biến động mạnh (hàng không, xi măng).

    GUARDRAIL G2: ngành chu kỳ dùng EBITDA CHUẨN HÓA giữa chu kỳ (chống nhiễu đỉnh/đáy, vd hàng không);
    mã không chu kỳ dùng EBITDA TTM cùng định nghĩa với bội số trailing (fx2).
    """

    def __init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any]):
        super().__init__(ticker, current_financials, assumptions)
        self.use_wacc = False  # không chiết khấu dòng tiền; định giá bội số

    @classmethod
    def from_pydantic(cls, company: Company) -> "EVEBITDAValuationModel":
        bs = company.historical_bs[-1]
        depr_to_rev = company.assumptions.depr_to_revenue[0]

        # EBITDA từng năm = EBIT + D&A THẬT từ LCTT; chỉ ước lượng khi kỳ đó thiếu D&A.
        depr_by_year = {cf.year: cf.depreciation for cf in company.historical_cf}
        ebitda_hist = [
            is_.ebit + (depr_by_year.get(is_.year) or depr_to_rev * is_.revenue)
            for is_ in company.historical_is
            if is_.revenue and is_.revenue > 0
        ]

        from valuation.engine.sector_router import route as _route_fn
        plan = _route_fn(company.ticker) or {}
        business_nature = plan.get("business_nature", "Unknown")
        # Chỉ lấy trung bình chu kỳ (3-5 năm) cho các ngành chu kỳ (Cyclical/Developer)
        is_mid_cycle = business_nature in ["Cyclical", "Developer"]

        cf_dict = {
            'ebitda_history': ebitda_hist,            # tỷ đồng
            'revenue_history': [
                is_.revenue for is_ in company.historical_is if is_.revenue and is_.revenue > 0
            ],
            'total_debt': (bs.short_term_debt + bs.long_term_debt) * 1e9,
            'cash_and_equivalents': (
                bs.cash_and_equivalents + bs.short_term_financial_investments
            ) * 1e9,
            'minority_interest': bs.minority_interest * 1e9,
            # Bội số đo trên EV hoạt động (repo loại XDCB dở dang từng năm) → cộng CIP hiện tại theo sổ sách.
            'non_operating_assets': (bs.long_term_investments_net + bs.construction_in_progress) * 1e9,
            'shares_outstanding': company.shares_outstanding * 1e6,
            'current_price': company.current_price,
        }
        assumptions = {
            'target_ev_ebitda': company.assumptions.target_ev_ebitda,
            'norm_years': 5 if is_mid_cycle else 3,
            'cyclical': business_nature == "Cyclical",
        }
        return cls(company.ticker, cf_dict, assumptions)

    def perform_valuation(self) -> Dict[str, Any]:
        hist = self.current_financials.get('ebitda_history', []) or []
        n = int(self.assumptions.get('norm_years', 3))
        target = self.assumptions.get('target_ev_ebitda', 7.0) or 7.0

        if not hist:
            return {"blended_fair_value_per_share": 0.0, "flags": ["NO_EBITDA_DATA"]}

        # EBITDA chuẩn hóa: ngành chu kỳ = biên giữa chu kỳ × doanh thu TTM (D36; thiếu dữ liệu → trung bình n
        # kỳ). Còn lại = EBITDA TTM: bội số mục tiêu là EV/EBITDA TRAILING (EV cuối kỳ / EBITDA cùng kỳ, gồm TTM)
        # → tử/mẫu cùng định nghĩa (như chân P/E s4). Trung bình [FY−1, FY, TTM] chồng 2 quý và lệch định nghĩa.
        window = hist[-n:] if len(hist) >= n else hist
        if self.assumptions.get('cyclical'):
            mid = midcycle_level(
                hist,
                self.current_financials.get('revenue_history') or [],
                window=int((load_defaults().get("forecast") or {}).get("margin_window_years", 4)),
            )
            norm_ebitda = (mid if mid is not None else statistics.mean(window)) * 1e9
        else:
            window = hist[-1:]
            norm_ebitda = hist[-1] * 1e9

        ev = norm_ebitda * target
        net_debt = self.current_financials.get('total_debt', 0.0) - self.current_financials.get('cash_and_equivalents', 0.0)
        minority_interest = self.current_financials.get('minority_interest', 0.0)
        non_operating = self.current_financials.get('non_operating_assets', 0.0)
        equity_value = ev - net_debt - minority_interest + non_operating
        shares = self.current_financials.get('shares_outstanding')
        if not shares or shares <= 0:
            raise ValueError("MISSING_FINANCIAL_INPUT: shares_outstanding")
        fvps = equity_value / shares

        flags = []
        # Cờ minh bạch: nếu net debt > EV, equity value âm bị clip về 0 — đây
        # KHÔNG có nghĩa công ty vô giá trị. Thường gặp ở DN đòn bẩy cao (hàng
        # không: nợ thuê tài chính máy bay vốn hóa rất lớn theo chuẩn kế toán,
        # không được EV/EBITDA thường — không phải EBITDAR — bù đắp tương ứng).
        # Không tự đổi method/multiple ở đây (quyết định tài chính cần duyệt).
        if fvps < 0:
            flags.append("NEGATIVE_EQUITY_VALUE_EV_EBITDA")
        fvps = max(0.0, fvps)

        # Cảnh báo nếu EBITDA năm gần nhất lệch mạnh khỏi mức chuẩn hóa (chu kỳ/nhiễu).
        latest = window[-1] * 1e9
        if norm_ebitda > 0 and abs(latest - norm_ebitda) / norm_ebitda > 0.30:
            flags.append("EBITDA_NORMALIZED_CYCLICAL")

        return {
            "blended_fair_value_per_share": fvps,
            "normalized_ebitda": norm_ebitda,
            "enterprise_value": ev,
            "equity_value": equity_value,
            "target_ev_ebitda": target,
            "years_averaged": len(window),
            "flags": flags,
        }
