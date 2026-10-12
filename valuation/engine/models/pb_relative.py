from typing import Dict, Any
import statistics
from .base import BaseValuationModel
from valuation.models.financials import Company


def _pb_bounds() -> tuple[float, float]:
    """Sàn/trần P/B mục tiêu — đưa vào config, không hardcode (luật vàng #5)."""
    from valuation.config import load_defaults
    cfg = load_defaults().get("relative_pb") or {}
    return (float(cfg.get("floor", 0.3)), float(cfg.get("ceiling", 4.0)))


class PBRelativeValuationModel(BaseValuationModel):
    """
    Justified P/B cho định chế tài chính phi-ngân-hàng (chứng khoán, bảo hiểm).

    GUARDRAIL (reviewer): P/B PHẢI link ROE — justified P/B = (ROE − g)/(COE − g),
    KHÔNG dùng P/B cố định. ROE = LN chuẩn hóa (median) / vốn CSH.
    Sanity: ROE phi lý (>40% hoặc <0) hoặc vốn CSH<=0 → cờ DATA_SUSPECT; P/B kẹp [0.3, 4.0].
    """

    def __init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any]):
        super().__init__(ticker, current_financials, assumptions)
        self.use_wacc = False

    @classmethod
    def from_pydantic(cls, company: Company) -> "PBRelativeValuationModel":
        bs = company.historical_bs[-1]
        a = company.assumptions
        cf_dict = {
            "total_equity": bs.parent_equity * 1e9,            # đồng
            "net_income_history": [is_.net_income for is_ in company.historical_is],  # tỷ
            # D26: cần chuỗi VCSH để tính ROE CÙNG KỲ (xem `perform_valuation`).
            "equity_history": [b.parent_equity for b in company.historical_bs],  # tỷ
            "shares_outstanding": company.shares_outstanding * 1e6,
            "current_price": company.current_price,
        }
        coe = (a.cost_of_equity if a.cost_of_equity else a.risk_free_rate + a.beta * a.erp)
        assumptions = {
            "cost_of_equity": coe,
            "long_term_growth": a.terminal_growth_rate,
            "norm_years": 3,
        }
        return cls(company.ticker, cf_dict, assumptions)

    def perform_valuation(self) -> Dict[str, Any]:
        equity = self.current_financials.get("total_equity", 0.0)
        hist = [x for x in self.current_financials.get("net_income_history", []) if x is not None]
        shares = self.current_financials.get("shares_outstanding", 1.0)
        g = self.g
        coe = self.coe

        if equity <= 0 or not hist or shares <= 0:
            return {"blended_fair_value_per_share": 0.0, "flags": ["NO_PB_DATA"]}

        n = int(self.assumptions.get("norm_years", 3))
        flags = []

        # D26 — SỬA LỖI LỆCH TỬ/MẪU SỐ:
        # Công thức cũ `median(LNST 3 kỳ) / VCSH MỚI NHẤT` lấy tử số là lợi nhuận
        # TRƯỚC tăng vốn chia cho vốn SAU tăng vốn → ROE bị bóp xuống một cách máy
        # móc với mọi doanh nghiệp vừa phát hành thêm. Nay tính ROE TỪNG KỲ trên
        # VCSH bình quân cùng kỳ rồi mới lấy median.
        eq_hist = self.current_financials.get("equity_history") or []
        if eq_hist:
            from valuation.engine.models.securities import roe_path_from_history
            roe_path = roe_path_from_history(hist, eq_hist)
            roe = statistics.median(roe_path[-n:]) if roe_path else 0.0
        else:
            # Không có chuỗi VCSH (API cũ truyền tay) → giữ cách cũ, có cờ truy vết.
            roe = (statistics.median(hist[-n:] if len(hist) >= n else hist) * 1e9) / equity
            flags.append("PB_ROE_TRAILING_FALLBACK")

        # ROE phi lý → dữ liệu khả nghi (vd bảo hiểm: LN bị map nhầm doanh thu phí).
        if roe > 0.40 or roe < 0:
            flags.append("DATA_SUSPECT_ROE")

        if coe <= g:
            justified_pb = 1.0
        else:
            justified_pb = (roe - g) / (coe - g)

        # Kẹp chống số rác — nhưng PHẢI LÊN TIẾNG. Trước đây việc kẹp im lặng
        # biến mọi kết quả phi lý thành 0,3x rồi trình bày như định giá bình thường,
        # che mất đúng tín hiệu cần thấy.
        pb_raw = justified_pb
        floor, ceiling = _pb_bounds()
        justified_pb = max(floor, min(justified_pb, ceiling))
        if pb_raw < floor:
            flags.append(f"PB_CLAMPED_LOW: P/B lý thuyết {pb_raw:.2f}x -> {floor:.2f}x")
        elif pb_raw > ceiling:
            flags.append(f"PB_CLAMPED_HIGH: P/B lý thuyết {pb_raw:.2f}x -> {ceiling:.2f}x")

        bvps = equity / shares
        fvps = max(0.0, justified_pb * bvps)

        from valuation.engine.guardrails import check_fv_vs_price, check_implied_pb, market_pb
        mkt_pb = market_pb(self.current_financials.get("current_price"), equity, shares)
        flags += check_implied_pb(justified_pb, mkt_pb)
        flags += check_fv_vs_price(fvps, self.current_financials.get("current_price"))

        return {
            "blended_fair_value_per_share": fvps,
            "justified_pb": justified_pb,
            "market_pb": mkt_pb,
            "roe": roe,
            "book_value_per_share": bvps,
            "flags": flags,
        }
