"""Định giá công ty chứng khoán: Residual Income + Justified P/B (D26).

BỐI CẢNH SỬA: trước D26, 7 mã CK (SSI VND VCI HCM VIX FTS BSI) đi qua
`PBRelativeValuationModel` — một perpetuity MỘT NHỊP dùng ROE trailing. Kết quả
lệch -76% so đồng thuận CTCK và 90% số mã có FV thấp hơn CHÍNH THỊ GIÁ (VCI
7.523đ vs thị giá 22.100đ). Model này đã tồn tại sẵn trong repo nhưng KHÔNG BAO
GIỜ được đấu nối (thiếu `from_pydantic`), và tầng driver cũ dựa trên các hằng số
thị phần môi giới bịa sẵn (market_liquidity=20000, market_share=0.10...) — không
lấy được từ DB, dùng là vi phạm luật vàng #1.

CÁCH LÀM MỚI — dự phóng ĐƯỜNG ROE thay vì dựng doanh thu:

  ROE hiện tại (cùng kỳ, median N kỳ gần nhất)
      -> fade tuyến tính về ROE MID-CYCLE CỦA CHÍNH CÔNG TY ĐÓ
         (median toàn lịch sử — gồm cả đỉnh 2021 lẫn đáy 2023-2024)
      -> giữ mức đó làm terminal ROE.

Cơ sở kinh tế của cú fade: CTCK Việt Nam vừa qua đợt tăng vốn lớn (VCSH VCI
3.643 -> 17.138 tỷ, gấp 4,7 lần). Vốn mới KHÔNG sinh lời ngay — nó được giải
ngân dần vào dư nợ margin trong 2-3 năm. Vì vậy ROE ngay sau tăng vốn là ước
lượng CHỆCH THẤP CÓ HỆ THỐNG của ROE forward. Đây là lý do kinh tế, không phải
thủ thuật để đẩy định giá lên.

Vì sao dùng ROE mid-cycle CỦA TỪNG CÔNG TY, không phải một số chung cho ngành:
lợi nhuận CTCK cực kỳ chu kỳ (2021 bùng nổ 19-35%, 2023-2024 về 5-13%). Lấy
median toàn chu kỳ của chính công ty đó là ước lượng mid-cycle trung thực, và
phân hoá được chất lượng giữa các nhà (SSI 12,2% vs BSI 8,9%) — điều mà một hằng
số ngành sẽ xoá mất.
"""
from typing import Any, Dict, List, Optional

import statistics

from valuation.config import load_defaults

from .base import BaseValuationModel

_DEFAULTS = {
    # Cửa sổ tính ROE "hiện tại" (số kỳ gần nhất).
    "norm_years_recent": 3,
    # Số năm để ROE fade từ mức hiện tại về mid-cycle (thời gian giải ngân vốn mới).
    "capital_deployment_years": 3,
    # Chặn hai đầu cho terminal ROE — chống dữ liệu rác, KHÔNG phải để tinh chỉnh
    # kết quả. Khoảng quan sát thực tế của 7 CTCK VN100: mid-cycle 8,9%-13,1%.
    "terminal_roe_floor": 0.05,
    "terminal_roe_cap": 0.20,
    "payout_ratio": 0.20,
    "weight_ri": 0.5,
    "forecast_years": 5,
}


def _cfg(section: str = "securities") -> Dict[str, Any]:
    return {**_DEFAULTS, **(load_defaults().get(section) or {})}


def roe_path_from_history(
    net_income: List[float],
    equity: List[float],
) -> List[float]:
    """ROE từng kỳ = LNST_t / VCSH BÌNH QUÂN CÙNG KỲ.

    Đây là chỗ sửa lỗi cốt lõi: công thức cũ lấy median(LNST 3 kỳ) chia cho VCSH
    MỚI NHẤT — tử số là lợi nhuận TRƯỚC tăng vốn, mẫu số là vốn SAU tăng vốn, nên
    ROE bị bóp méo xuống một cách máy móc với mọi công ty vừa phát hành thêm.
    """
    out: List[float] = []
    for i in range(1, min(len(net_income), len(equity))):
        avg_eq = (equity[i] + equity[i - 1]) / 2.0
        if avg_eq > 0:
            out.append(net_income[i] / avg_eq)
    # Chỉ có 1 kỳ: đành dùng VCSH cuối kỳ.
    if not out and net_income and equity and equity[-1] > 0:
        out.append(net_income[-1] / equity[-1])
    return out


class SecuritiesValuationModel(BaseValuationModel):
    """RI + Justified P/B cho ngành chứng khoán."""

    def __init__(self, ticker: str, current_financials: Dict[str, Any],
                 assumptions: Dict[str, Any]):
        super().__init__(ticker, current_financials, assumptions)
        self.use_wacc = False

    # ------------------------------------------------------------------
    @classmethod
    def from_pydantic(cls, company) -> "SecuritiesValuationModel":
        cfg = _cfg("securities")
        bs = company.historical_bs[-1]
        a = company.assumptions
        coe = a.cost_of_equity if getattr(a, "cost_of_equity", None) else (
            a.risk_free_rate + a.beta * a.erp
        )
        cf = {
            "total_equity": bs.parent_equity * 1e9,                    # tỷ -> đồng
            "net_income_history": [x.net_income for x in company.historical_is],
            "equity_history": [x.parent_equity for x in company.historical_bs],
            "shares_outstanding": company.shares_outstanding * 1e6,   # triệu cp -> cp
            "current_price": company.current_price,
        }
        assumptions = {
            "historical_pb_median": getattr(a, "historical_pb_median", None),
            "cost_of_equity": coe,
            "risk_free_rate": a.risk_free_rate,
            "long_term_growth": a.terminal_growth_rate,
            **cfg,
        }
        return cls(company.ticker, cf, assumptions)

    # ------------------------------------------------------------------
    def forecast_drivers(self) -> Dict[str, Any]:
        """Dựng đường ROE 5 năm + VCSH cuộn chiếu theo tỷ lệ giữ lại.

        Hai đường vào:
        - MẶC ĐỊNH (production, qua `from_pydantic`): dựng ROE từ lịch sử BCTC.
        - LEGACY: khi analyst/API truyền tay bộ driver doanh thu môi giới
          (`market_liquidity_vnd_billion`, `brokerage_market_share`...). Giữ lại
          vì API `/valuation/detail` và golden test cũ dùng đường này. KHÔNG dùng
          ở batch/Streamlit: các hằng số đó không lấy được từ DB, tự điền vào là
          bịa số (luật vàng #1).
        """
        ni = self.current_financials.get("net_income_history") or []
        eq = self.current_financials.get("equity_history") or []
        if not ni or not eq:
            legacy = self._legacy_driver_forecast()
            if legacy is not None:
                return legacy
        n_years = int(self.assumptions.get("forecast_years", 5))
        n_recent = int(self.assumptions.get("norm_years_recent", 3))
        deploy_yrs = max(1, int(self.assumptions.get("capital_deployment_years", 3)))
        payout = float(self.assumptions.get("payout_ratio", 0.20))

        roes = roe_path_from_history(ni, eq)
        if not roes:
            return {"forecasts": [], "terminal_roe": None, "flags": ["NO_ROE_DATA"]}

        roe_now = statistics.median(roes[-n_recent:]) if len(roes) >= 1 else roes[-1]
        roe_mid = statistics.median(roes)  # mid-cycle của CHÍNH công ty này

        floor = float(self.assumptions.get("terminal_roe_floor", 0.05))
        cap = float(self.assumptions.get("terminal_roe_cap", 0.20))
        flags: List[str] = []
        terminal_roe = min(max(roe_mid, floor), cap)
        if terminal_roe != roe_mid:
            flags.append(
                f"SEC_TERMINAL_ROE_CLAMPED: mid-cycle {roe_mid:.1%} -> {terminal_roe:.1%}"
            )

        # Fade tuyến tính roe_now -> terminal_roe trong deploy_yrs năm, sau đó giữ.
        book = float(self.current_financials.get("total_equity", 0.0))
        forecasts: List[Dict[str, Any]] = []
        for year in range(1, n_years + 1):
            if year <= deploy_yrs:
                w = year / float(deploy_yrs)
                roe_y = roe_now + (terminal_roe - roe_now) * w
            else:
                roe_y = terminal_roe
            ni_y = book * roe_y
            forecasts.append({"year": year, "roe": roe_y,
                              "net_income": ni_y, "book_value_start": book})
            book += ni_y * (1.0 - payout)

        return {"forecasts": forecasts, "terminal_roe": terminal_roe,
                "roe_now": roe_now, "roe_midcycle": roe_mid, "flags": flags}

    # ------------------------------------------------------------------
    def _legacy_driver_forecast(self) -> Optional[Dict[str, Any]]:
        """Đường cũ: dựng lợi nhuận từ driver doanh thu môi giới do analyst nhập.

        Chỉ kích hoạt khi CÓ driver truyền vào — không có thì trả None để
        `forecast_drivers` báo thiếu dữ liệu, thay vì âm thầm dùng hằng số bịa.
        """
        a = self.assumptions
        if a.get("market_liquidity_vnd_billion") is None or a.get("brokerage_market_share") is None:
            return None

        liq = float(a["market_liquidity_vnd_billion"]) * 1e9
        share = float(a["brokerage_market_share"])
        brok_margin = float(a.get("brokerage_margin", 0.0015))
        margin_loans = float(a.get("margin_loans", 0.0)) * 1e9
        net_margin_rate = float(a.get("net_margin_rate", 0.0))
        prop = float(a.get("prop_trading_income", 0.0)) * 1e9
        opex_ratio = float(a.get("opex_ratio", 0.40))
        tax = float(a.get("tax_rate", 0.20))
        payout = float(a.get("payout_ratio", 0.20))

        total_rev = (liq * 250 * share * brok_margin) + (margin_loans * net_margin_rate) + prop
        net_income = total_rev * (1 - opex_ratio) * (1 - tax)

        book = float(self.current_financials.get("total_equity", 0.0))
        forecasts: List[Dict[str, Any]] = []
        for year in range(1, int(a.get("forecast_years", 5)) + 1):
            forecasts.append({"year": year, "net_income": net_income,
                              "book_value_start": book,
                              "roe": (net_income / book if book > 0 else 0.0)})
            book += net_income * (1 - payout)

        return {"forecasts": forecasts,
                "terminal_roe": (net_income / book if book > 0 else 0.0),
                "roe_now": None, "roe_midcycle": None,
                "flags": ["SEC_LEGACY_DRIVER_MODE"]}

    # ------------------------------------------------------------------
    def perform_valuation(self) -> Dict[str, Any]:
        shares = float(self.current_financials.get("shares_outstanding") or 0.0)
        book0 = float(self.current_financials.get("total_equity") or 0.0)
        price = self.current_financials.get("current_price")

        if shares <= 0 or book0 <= 0:
            return {"blended_fair_value_per_share": 0.0, "flags": ["NO_SEC_DATA"]}

        drv = self.forecast_drivers()
        forecasts = drv.get("forecasts") or []
        terminal_roe = drv.get("terminal_roe")
        flags: List[str] = list(drv.get("flags") or [])
        if not forecasts or terminal_roe is None:
            return {"blended_fair_value_per_share": 0.0, "flags": flags + ["NO_SEC_DATA"]}

        coe, g = self.coe, self.g

        # --- 1. Residual Income ---
        # RI_t = LNST_t - COE × VCSH đầu kỳ. Giá trị chỉ sinh ra khi ROE > COE.
        pv_ri = 0.0
        for f in forecasts:
            ri = f["net_income"] - f["book_value_start"] * coe
            pv_ri += ri / ((1.0 + coe) ** f["year"])

        terminal_book = forecasts[-1]["book_value_start"] + forecasts[-1]["net_income"] * (
            1.0 - float(self.assumptions.get("payout_ratio", 0.20))
        )
        ri_fvps = 0.0
        if coe > g:
            terminal_ri = (terminal_roe - coe) * terminal_book
            pv_tv = (terminal_ri / (coe - g)) / ((1.0 + coe) ** len(forecasts))
            ri_fvps = (book0 + pv_ri + pv_tv) / shares
        else:
            flags.append("COE_LE_G_RI_SKIPPED")

        # --- 2. Chân P/B: ưu tiên P/B THỊ TRƯỜNG lịch sử của chính công ty. P/B hợp lý
        # (ROE−g)/(COE−g) dùng cùng ROE/COE với RI nên không kiểm tra chéo được gì — và
        # khi ROE giữa chu kỳ < COE nó khẳng định mọi CTCK hủy giá trị vĩnh viễn.
        target_pb = (terminal_roe - g) / (coe - g) if coe > g else 1.0
        hist_pb = self.assumptions.get("historical_pb_median")
        if hist_pb and hist_pb > 0:
            pb_fvps = hist_pb * book0 / shares
        else:
            pb_fvps = target_pb * book0 / shares
            flags.append("SEC_NO_MARKET_PB_HISTORY")

        # --- 3. Pha trộn ---
        w_ri = float(self.assumptions.get("weight_ri", 0.5))
        blended = max(0.0, ri_fvps * w_ri + pb_fvps * (1.0 - w_ri))

        # --- 4. Guardrail: cờ, không kẹp ---
        from valuation.engine.guardrails import (
            check_fv_vs_price,
            check_implied_pb,
            market_pb,
        )
        mkt_pb = market_pb(price, book0, shares)
        flags += check_implied_pb(target_pb, mkt_pb, label="SEC_PB")
        flags += check_fv_vs_price(blended, price)
        if terminal_roe < coe:
            # Không phải lỗi — nhưng là tuyên bố mạnh, phải nói rõ.
            flags.append(
                f"SEC_ROE_BELOW_COE: ROE bền vững {terminal_roe:.1%} < COE {coe:.1%} "
                f"→ P/B hợp lý < 1 (mô hình cho rằng công ty chưa tạo thêm giá trị)"
            )

        return {
            "blended_fair_value_per_share": blended,
            "ri_fvps": ri_fvps,
            "pb_fvps": pb_fvps,
            "justified_pb": target_pb,
            "market_pb": mkt_pb,
            "terminal_roe": terminal_roe,
            "roe_now": drv.get("roe_now"),
            "roe_midcycle": drv.get("roe_midcycle"),
            "weight_ri": w_ri,
            "flags": flags,
        }
