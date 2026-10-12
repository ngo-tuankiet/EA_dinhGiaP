from typing import Dict, Any
import statistics
from .base import BaseValuationModel
from valuation.models.financials import Company
from valuation.config import load_defaults


class DDMValuationModel(BaseValuationModel):
    """
    Dividend Discount Model (DDM) — cross-check cho điện.

    Cổ tức năm t = EPS chuẩn hóa (median LN mẹ 3 kỳ) × payout THỰC TẾ × Π(1+g_t),
    g_t = đường tăng trưởng doanh thu của DCF; sau năm 5 dùng g vĩnh viễn chung,
    chiết khấu theo COE. Payout < ngưỡng → cổ tức không đại diện FCFE → không định giá.
    """

    def __init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any]):
        super().__init__(ticker, current_financials, assumptions)
        self.use_wacc = False

    @staticmethod
    def historical_payout(company: Company, years: int) -> float | None:
        paid = {cf.year: cf.dividends_paid for cf in company.historical_cf}
        pairs = [(paid.get(is_.year, 0.0), is_.net_income) for is_ in company.historical_is[-years:]]
        ni = sum(n for _, n in pairs if n > 0)
        if ni <= 0:
            return None
        return min(sum(d for d, _ in pairs) / ni, 1.0)

    @classmethod
    def from_pydantic(cls, company: Company) -> "DDMValuationModel":
        a = company.assumptions
        cfg = load_defaults().get("ddm", {})
        coe = (a.cost_of_equity if a.cost_of_equity else a.risk_free_rate + a.beta * a.erp)
        cf_dict = {
            "net_income_history": [is_.net_income for is_ in company.historical_is],  # tỷ
            "shares_outstanding": company.shares_outstanding * 1e6,
            "current_price": company.current_price,
        }
        assumptions = {
            "cost_of_equity": coe,
            "risk_free_rate": a.risk_free_rate,
            "payout_ratio": cls.historical_payout(company, int(cfg.get("payout_years", 4))),
            "min_payout": float(cfg.get("min_payout", 0.40)),
            "growth_path": list(a.revenue_growth),
            "long_term_growth": a.terminal_growth_rate,
        }
        return cls(company.ticker, cf_dict, assumptions)

    def perform_valuation(self) -> Dict[str, Any]:
        hist = [x for x in self.current_financials.get("net_income_history", []) if x is not None]
        shares = self.current_financials.get("shares_outstanding")
        payout = self.assumptions.get("payout_ratio")
        if not hist or not shares or shares <= 0:
            return {"blended_fair_value_per_share": 0.0, "flags": ["NO_DDM_DATA"]}
        if payout is None or payout < self.assumptions.get("min_payout", 0.40):
            return {"blended_fair_value_per_share": 0.0, "payout_ratio": payout,
                    "flags": ["DDM_SKIPPED_LOW_PAYOUT"]}

        window = hist[-3:] if len(hist) >= 3 else hist
        norm_ni = statistics.median(window) * 1e9
        if norm_ni <= 0:
            return {"blended_fair_value_per_share": 0.0, "flags": ["NEGATIVE_EARNINGS"]}

        coe, g_term = self.coe, self.g  # g đã qua guardrail g ≤ rf, COE − g ≥ spread
        eps0 = norm_ni / shares
        pv, d_t = 0.0, eps0 * payout
        path = self.assumptions.get("growth_path") or [g_term] * 5
        for t, g_t in enumerate(path[:5], start=1):
            d_t *= 1 + g_t
            pv += d_t / (1 + coe) ** t
        pv += d_t * (1 + g_term) / (coe - g_term) / (1 + coe) ** 5

        return {
            "blended_fair_value_per_share": max(0.0, pv),
            "normalized_eps": eps0,
            "payout_ratio": payout,
            "implied_div_yield": (eps0 * payout) / self.current_financials["current_price"]
            if self.current_financials.get("current_price") else None,
            "flags": [],
        }
