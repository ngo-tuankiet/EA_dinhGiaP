from typing import Dict, Any
import statistics
from .base import BaseValuationModel, midcycle_level
from valuation.models.financials import Company
from valuation.config import load_defaults


class PERelativeValuationModel(BaseValuationModel):
    """
    Định giá P/E so sánh cho ngành biên mỏng/chu kỳ xuất khẩu (dệt may, thủy sản,
    xây dựng) — nơi CTCK dùng P/E chủ đạo.

    GUARDRAIL: EPS CHUẨN HÓA = median lợi nhuận lịch sử / số cp (chống nhiễu lợi
    nhuận một năm bất thường), nhất quán với triết lý mid-cycle của EV/EBITDA & DCF.
    """

    def __init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any]):
        super().__init__(ticker, current_financials, assumptions)
        self.use_wacc = False

    @staticmethod
    def _target_pe(sector: str) -> float:
        cfg = load_defaults().get("sector_pe", {})
        s = (sector or "").lower()
        if any(k in s for k in ["dệt", "thủy", "may", "textile", "seafood", "fish"]):
            return cfg.get("textile_seafood", 8.0)
        if any(k in s for k in ["xây", "construction", "building"]):
            return cfg.get("construction", 9.0)
        if any(k in s for k in ["dược", "pharma", "health"]):
            return cfg.get("pharma", 13.0)
        if any(k in s for k in ["consumer", "tiêu dùng", "food", "beverage"]):
            return cfg.get("consumer", 14.0)
        if any(k in s for k in ["tech", "công nghệ", "software"]):
            return cfg.get("technology", 15.0)
        return cfg.get("default", 10.0)

    @classmethod
    def from_pydantic(cls, company: Company, sector: str = None) -> "PERelativeValuationModel":
        # Ưu tiên `sector` (nhóm ngành Excel từ router) cho chọn P/E mục tiêu, vì DB
        # sector (vnstock) lệch nhóm phân tích (vd VHC DB='Food & Beverage' nhưng Excel
        # ='Dệt may/TS' thủy sản). Fallback DB sector nếu không truyền.
        ni_hist = [is_.net_income for is_ in company.historical_is]  # tỷ đồng
        from valuation.engine.sector_router import route as _route_fn
        plan = _route_fn(company.ticker) or {}
        business_nature = plan.get("business_nature", "Unknown")
        is_mid_cycle = business_nature in ["Cyclical", "Developer"]

        cf_dict = {
            "net_income_history": ni_hist,
            "revenue_history": [is_.revenue for is_ in company.historical_is],
            "shares_outstanding": company.shares_outstanding * 1e6,
            "current_price": company.current_price,
        }
        assumptions = {
            "target_pe": company.assumptions.target_pe or cls._target_pe(sector or company.sector),
            "norm_years": 5 if is_mid_cycle else 3,
            "cyclical": business_nature == "Cyclical",
        }
        return cls(company.ticker, cf_dict, assumptions)

    def perform_valuation(self) -> Dict[str, Any]:
        hist = [x for x in self.current_financials.get("net_income_history", []) if x is not None]
        target_pe = self.assumptions.get("target_pe", 10.0) or 10.0
        shares = self.current_financials.get("shares_outstanding")
        if not shares or shares <= 0:
            raise ValueError("MISSING_FINANCIAL_INPUT: shares_outstanding")

        if not hist:
            return {"blended_fair_value_per_share": 0.0, "flags": ["NO_EARNINGS_DATA"]}

        n = int(self.assumptions.get("norm_years", 3))
        window = hist[-n:] if len(hist) >= n else hist
        flags = []
        cyclical = bool(self.assumptions.get("cyclical"))
        if cyclical:
            mid = midcycle_level(hist, self.current_financials.get("revenue_history") or [])
            norm_ni = (mid if mid is not None else statistics.median(window)) * 1e9
            if hist[-1] <= 0:
                flags.append("PE_ON_MIDCYCLE_EARNINGS_TTM_LOSS")
        elif hist[-1] <= 0:
            # Luật vàng #2: không dùng P/E cho DN đang lỗ (không phải ngành chu kỳ).
            return {"blended_fair_value_per_share": 0.0, "flags": ["PE_DISABLED_TTM_LOSS"]}
        else:
            norm_ni = statistics.median(window) * 1e9  # tỷ → đồng

        if norm_ni <= 0:
            # LN âm/0 → P/E vô nghĩa; trả 0 + cờ thay vì số rác.
            return {"blended_fair_value_per_share": 0.0, "flags": ["NEGATIVE_NORMALIZED_EARNINGS"]}

        eps = norm_ni / shares
        fvps = max(0.0, eps * target_pe)

        latest = window[-1] * 1e9
        if abs(latest - norm_ni) / norm_ni > 0.30:
            flags.append("EARNINGS_NORMALIZED_CYCLICAL")

        return {
            "blended_fair_value_per_share": fvps,
            "normalized_eps": eps,
            "target_pe": target_pe,
            "years_averaged": len(window),
            "flags": flags,
        }
