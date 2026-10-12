"""Định giá doanh nghiệp bảo hiểm: Justified P/B trên ROE chuẩn hoá dài kỳ (D27).

VÌ SAO TÁCH KHỎI CHỨNG KHOÁN: routing gộp BVH/BMI/MIG chung `primary: P/B` với
nhóm CK, nên trước D26 cả 10 mã đi qua cùng một `PBRelativeValuationModel`. Nhưng
kinh tế hai ngành khác hẳn:

- CTCK: lợi nhuận = phí môi giới + lãi margin + tự doanh → bám sát thanh khoản
  thị trường, chu kỳ NGẮN và biên độ RẤT rộng (ROE 5%-35% trong 8 năm).
- Bảo hiểm: lợi nhuận = kết quả nghiệp vụ + thu nhập đầu tư danh mục (chủ yếu
  trái phiếu/tiền gửi) → chi phối bởi chu kỳ LÃI SUẤT, dài hơn và êm hơn nhiều.
  Đo thực tế 3 mã VN100: ROE 7%-14%, mid-cycle 8,6%-12,6%.

Hệ quả thiết kế: cửa sổ chuẩn hoá ROE DÀI HƠN (mặc định 5 kỳ thay vì 3) vì chu
kỳ lãi suất dài hơn chu kỳ thanh khoản; và KHÔNG có cú "fade sau tăng vốn" như
CTCK vì bảo hiểm không có hiện tượng vốn mới chưa giải ngân ở quy mô đó.

KIỂM CHỨNG NGUỒN GỐC LỢI NHUẬN: docstring `pb_relative.py` từng cảnh báo lợi
nhuận bảo hiểm có thể bị map nhầm từ DOANH THU PHÍ. Model này kiểm tra ROE có
nằm trong khoảng hợp lý không; nếu không thì trả `NOT_RATED` kèm cờ
`NI_MAPPING_UNVERIFIED` — KHÔNG trả một con số đã bị kẹp về 0,3x rồi trình bày
như định giá bình thường.
"""
from typing import Any, Dict, List

import statistics

from valuation.config import load_defaults

from .base import BaseValuationModel
from .securities import roe_path_from_history

_DEFAULTS = {
    # Chu kỳ lãi suất dài hơn chu kỳ thanh khoản -> cửa sổ chuẩn hoá dài hơn.
    "norm_years": 5,
    # Ngoài khoảng này thì nghi lợi nhuận bị map nhầm (vd lấy nhầm doanh thu phí,
    # vốn lớn gấp nhiều lần lợi nhuận thật -> ROE vọt phi lý).
    "roe_sanity_min": 0.0,
    "roe_sanity_max": 0.30,
    "terminal_roe_floor": 0.04,
    "terminal_roe_cap": 0.16,
    "weight_ri": 0.5,
    "payout_ratio": 0.30,
    "forecast_years": 5,
}


def _cfg() -> Dict[str, Any]:
    return {**_DEFAULTS, **(load_defaults().get("insurance") or {})}


class InsuranceValuationModel(BaseValuationModel):
    """Justified P/B + Residual Income cho doanh nghiệp bảo hiểm."""

    def __init__(self, ticker: str, current_financials: Dict[str, Any],
                 assumptions: Dict[str, Any]):
        super().__init__(ticker, current_financials, assumptions)
        self.use_wacc = False

    @classmethod
    def from_pydantic(cls, company) -> "InsuranceValuationModel":
        cfg = _cfg()
        bs = company.historical_bs[-1]
        a = company.assumptions
        coe = a.cost_of_equity if getattr(a, "cost_of_equity", None) else (
            a.risk_free_rate + a.beta * a.erp
        )
        cf = {
            "total_equity": bs.parent_equity * 1e9,
            "net_income_history": [x.net_income for x in company.historical_is],
            "equity_history": [x.parent_equity for x in company.historical_bs],
            "shares_outstanding": company.shares_outstanding * 1e6,
            "current_price": company.current_price,
        }
        assumptions = {
            "cost_of_equity": coe,
            "risk_free_rate": a.risk_free_rate,
            "long_term_growth": a.terminal_growth_rate,
            **cfg,
        }
        return cls(company.ticker, cf, assumptions)

    # ------------------------------------------------------------------
    def forecast_drivers(self) -> Dict[str, Any]:
        ni = self.current_financials.get("net_income_history") or []
        eq = self.current_financials.get("equity_history") or []
        roes = roe_path_from_history(ni, eq)
        if not roes:
            return {"roes": [], "terminal_roe": None, "flags": ["NO_ROE_DATA"]}

        n = int(self.assumptions.get("norm_years", 5))
        roe_norm = statistics.median(roes[-n:]) if len(roes) >= 1 else roes[-1]

        flags: List[str] = []
        lo = float(self.assumptions.get("roe_sanity_min", 0.0))
        hi = float(self.assumptions.get("roe_sanity_max", 0.30))
        if not (lo <= roe_norm <= hi):
            # Không kẹp rồi đi tiếp — từ chối định giá và nói rõ vì sao.
            flags.append(
                f"NI_MAPPING_UNVERIFIED: ROE chuẩn hoá {roe_norm:.1%} nằm ngoài khoảng "
                f"hợp lý [{lo:.0%}, {hi:.0%}] — nghi lợi nhuận bị map nhầm "
                f"(vd lấy nhầm doanh thu phí thay vì LNST)"
            )
            return {"roes": roes, "roe_norm": roe_norm, "terminal_roe": None, "flags": flags}

        floor = float(self.assumptions.get("terminal_roe_floor", 0.04))
        cap = float(self.assumptions.get("terminal_roe_cap", 0.16))
        terminal_roe = min(max(roe_norm, floor), cap)
        if terminal_roe != roe_norm:
            flags.append(f"INS_TERMINAL_ROE_CLAMPED: {roe_norm:.1%} -> {terminal_roe:.1%}")
        return {"roes": roes, "roe_norm": roe_norm,
                "terminal_roe": terminal_roe, "flags": flags}

    # ------------------------------------------------------------------
    def perform_valuation(self) -> Dict[str, Any]:
        shares = float(self.current_financials.get("shares_outstanding") or 0.0)
        book0 = float(self.current_financials.get("total_equity") or 0.0)
        price = self.current_financials.get("current_price")

        if shares <= 0 or book0 <= 0:
            return {"blended_fair_value_per_share": 0.0, "flags": ["NO_INS_DATA"],
                    "not_rated": True}

        drv = self.forecast_drivers()
        flags: List[str] = list(drv.get("flags") or [])
        terminal_roe = drv.get("terminal_roe")
        if terminal_roe is None:
            # Thà một khoảng trống được ghi nhận còn hơn một con số sai tự tin.
            return {"blended_fair_value_per_share": 0.0, "flags": flags,
                    "not_rated": True, "roe_norm": drv.get("roe_norm")}

        coe, g = self.coe, self.g
        payout = float(self.assumptions.get("payout_ratio", 0.30))
        n_years = int(self.assumptions.get("forecast_years", 5))

        # --- Residual Income: ROE giữ ở mức chuẩn hoá (bảo hiểm ít biến động) ---
        pv_ri, book = 0.0, book0
        for year in range(1, n_years + 1):
            ni_y = book * terminal_roe
            ri = ni_y - book * coe
            pv_ri += ri / ((1.0 + coe) ** year)
            book += ni_y * (1.0 - payout)

        ri_fvps = 0.0
        if coe > g:
            terminal_ri = (terminal_roe - coe) * book
            pv_tv = (terminal_ri / (coe - g)) / ((1.0 + coe) ** n_years)
            ri_fvps = (book0 + pv_ri + pv_tv) / shares
        else:
            flags.append("COE_LE_G_RI_SKIPPED")

        # --- Justified P/B ---
        target_pb = (terminal_roe - g) / (coe - g) if coe > g else 1.0
        pb_fvps = target_pb * book0 / shares

        w_ri = float(self.assumptions.get("weight_ri", 0.5))
        blended = max(0.0, ri_fvps * w_ri + pb_fvps * (1.0 - w_ri))

        from valuation.engine.guardrails import (
            check_fv_vs_price,
            check_implied_pb,
            market_pb,
        )
        mkt_pb = market_pb(price, book0, shares)
        flags += check_implied_pb(target_pb, mkt_pb, label="INS_PB")
        flags += check_fv_vs_price(blended, price)

        return {
            "blended_fair_value_per_share": blended,
            "ri_fvps": ri_fvps,
            "pb_fvps": pb_fvps,
            "justified_pb": target_pb,
            "market_pb": mkt_pb,
            "terminal_roe": terminal_roe,
            "roe_norm": drv.get("roe_norm"),
            "weight_ri": w_ri,
            "flags": flags,
        }
