"""Định giá doanh nghiệp bảo hiểm: Justified P/B trên ROE chuẩn hoá dài kỳ (D27).

VÌ SAO TÁCH KHỎI CHỨNG KHOÁN: routing gộp BVH/BMI/MIG chung `primary: P/B` với
nhóm CK, nên trước D26 cả 10 mã đi qua cùng một `PBRelativeValuationModel`. Nhưng
kinh tế hai ngành khác hẳn:

- CTCK: lợi nhuận = phí môi giới + lãi margin + tự doanh → bám sát thanh khoản
  thị trường, chu kỳ NGẮN và biên độ RẤT rộng (ROE 5%-35% trong 8 năm).
- Bảo hiểm: lợi nhuận = kết quả nghiệp vụ + thu nhập đầu tư danh mục (chủ yếu
  trái phiếu/tiền gửi) → chi phối bởi chu kỳ LÃI SUẤT, dài hơn và êm hơn nhiều.
  Đo thực tế 3 mã VN100: ROE 7%-14%, mid-cycle 8,6%-12,6%.

Hệ quả thiết kế: ROE giữ phẳng ở mức chuẩn hoá (cửa sổ forecast.margin_window_years
như D61 — bản đầu dùng 5 kỳ riêng, trộn cả năm ROE đáy 2022), KHÔNG có cú "fade sau
tăng vốn" như CTCK vì bảo hiểm không có hiện tượng vốn mới chưa giải ngân ở quy mô đó.

Chân thứ hai là P/B THỊ TRƯỜNG lịch sử của chính mã (như NH/CK, D38/D39): P/B hợp lý
(ROE−g)/(COE−g) dùng cùng ROE/COE với RI nên không kiểm tra chéo được gì. Embedded
Value mảng nhân thọ chưa có dữ liệu → FV thiếu VIF, BVH giữ event hold.

KIỂM CHỨNG NGUỒN GỐC LỢI NHUẬN: docstring `pb_relative.py` từng cảnh báo lợi
nhuận bảo hiểm có thể bị map nhầm từ DOANH THU PHÍ. Model này kiểm tra ROE có
nằm trong khoảng hợp lý không; nếu không thì trả `NOT_RATED` kèm cờ
`NI_MAPPING_UNVERIFIED` — KHÔNG trả một con số đã bị kẹp về 0,3x rồi trình bày
như định giá bình thường.
"""
from typing import Any, Dict, List

import statistics

from valuation.config import load_defaults
from valuation.engine.forecast_bank import begin_roe_from_avg, ni_from_avg_roe

from .base import BaseValuationModel
from .securities import apply_data_payout, payout_flags, roe_path_from_history

_DEFAULTS = {
    # Ngoài khoảng này thì nghi lợi nhuận bị map nhầm (vd lấy nhầm doanh thu phí,
    # vốn lớn gấp nhiều lần lợi nhuận thật -> ROE vọt phi lý).
    "roe_sanity_min": 0.0,
    "roe_sanity_max": 0.30,
    "terminal_roe_floor": 0.04,
    "terminal_roe_cap": 0.16,
    "weight_ri": 0.5,
    "payout_ratio": 0.30,
    "payout_cap": 1.0,
    "payout_years": 3,
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
            "historical_pb_median": getattr(a, "historical_pb_median", None),
            "cost_of_equity": coe,
            "risk_free_rate": a.risk_free_rate,
            "long_term_growth": a.terminal_growth_rate,
            **cfg,
        }
        return cls(company.ticker, cf, apply_data_payout(assumptions, company))

    # ------------------------------------------------------------------
    def forecast_drivers(self) -> Dict[str, Any]:
        ni = self.current_financials.get("net_income_history") or []
        eq = self.current_financials.get("equity_history") or []
        roes = roe_path_from_history(ni, eq)
        if not roes:
            return {"roes": [], "terminal_roe": None, "flags": ["NO_ROE_DATA"]}

        # D61: cùng cửa sổ N năm gần nhất với ROE mid-cycle CTCK và biên EBIT phi tài chính.
        n = int((load_defaults().get("forecast") or {}).get("margin_window_years", 4))
        roe_norm = statistics.median(roes[-n:])

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
        # ROE chuẩn hoá đo trên VCSH BÌNH QUÂN → LN giải theo VCSH đầu kỳ, RI terminal/P/B hợp lý dùng ROE đầu
        # kỳ = ROE × (1 + g/2) — cùng quy đổi với NH/CTCK (forecast_bank).
        roe_b = begin_roe_from_avg(terminal_roe, g)
        pv_ri, book = 0.0, book0
        for year in range(1, n_years + 1):
            ni_y = ni_from_avg_roe(terminal_roe, book, payout)
            ri = ni_y - book * coe
            pv_ri += ri / ((1.0 + coe) ** year)
            book += ni_y - max(ni_y, 0.0) * payout  # lỗ không chia cổ tức

        ri_fvps = 0.0
        if coe > g:
            terminal_ri = (roe_b - coe) * book
            pv_tv = (terminal_ri / (coe - g)) / ((1.0 + coe) ** n_years)
            ri_fvps = (book0 + pv_ri + pv_tv) / shares
        else:
            flags.append("COE_LE_G_RI_SKIPPED")

        # --- Chân P/B: ưu tiên P/B THỊ TRƯỜNG lịch sử của chính mã (như securities.py) ---
        target_pb = (roe_b - g) / (coe - g) if coe > g else 1.0
        hist_pb = self.assumptions.get("historical_pb_median")
        if hist_pb and hist_pb > 0:
            pb_fvps = hist_pb * book0 / shares
        else:
            pb_fvps = target_pb * book0 / shares
            flags.append("INS_NO_MARKET_PB_HISTORY")

        w_ri = float(self.assumptions.get("weight_ri", 0.5))
        blended = max(0.0, ri_fvps * w_ri + pb_fvps * (1.0 - w_ri))

        from valuation.engine.guardrails import (
            check_fv_vs_price,
            check_implied_pb,
            legs_diverge,
            market_pb,
        )
        if 0.0 < w_ri < 1.0 and legs_diverge(ri_fvps, pb_fvps):
            # Như DCF: trung bình hai chân bất đồng (DSE RI 2.746 vs P/B 29.589) không phải giá trị hợp lý → chặn.
            flags.append("VALUATION_LEGS_DIVERGE")
        mkt_pb = market_pb(price, book0, shares)
        flags += check_implied_pb(target_pb, mkt_pb, label="INS_PB")
        flags += check_fv_vs_price(blended, price)
        flags += payout_flags("INS", self.assumptions, payout, roe_b, g)

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
