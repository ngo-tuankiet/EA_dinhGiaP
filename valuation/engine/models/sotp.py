import statistics
from typing import Dict, Any
from .base import BaseValuationModel, input_number
from valuation.models.financials import Company
from valuation.config import load_defaults


class SOTPValuationModel(BaseValuationModel):
    """
    SOTP (Sum of the Parts) dành cho các Tập đoàn đa ngành.

    Phiên bản MỚI:
    - Nhất quán phân tách EV và Equity.
    - Tổng_EV = Sum(các mảng định giá theo EV)
    - Equity_từ_EV = Tổng_EV - Nợ vay ròng tập đoàn (trừ phần của công ty con đã định giá theo Equity).
    - Tổng_Equity = Equity_từ_EV + Sum(các mảng định giá theo Equity).
    - Trừ đi lợi ích CĐTS (trừ phần của công ty con đã định giá theo Equity) — xem segments_equity.

    Chế độ SOTP_HOLDINGS (config/sotp_holdings.yaml): phần sở hữu ở công ty con/liên kết niêm yết theo
    thị giá, phần còn lại theo VCSH mẹ hợp nhất (Damodaran, cross holdings):
        FV/cp = [VCSH mẹ + Σ(stake × vốn hóa − giá sổ phần sở hữu)] / số cp × (1 − chiết khấu holding)
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
            'sotp_segments': getattr(company.assumptions, 'sotp_segments', []),
            'sotp_holdings': getattr(company.assumptions, 'sotp_holdings', None),
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
        holdings_cfg = self.assumptions.get('sotp_holdings') or {}
        holdings = holdings_cfg.get('holdings') or []
        holdings_ok = bool(holdings) and not any(h.get('error') for h in holdings)
        breakdown = None
        ai_mode, missing = False, []
        if sotp_segments:
            total_equity_value, missing = self.segments_equity(sotp_segments, net_debt, minority_interest)
            ai_mode = not missing
        if ai_mode:
            # AI_SOTP_MODE
            sotp_ps = (total_equity_value / shares) * (1 - discount)

            flags = ["AI_SOTP_MODE"]
            if "VALUATION_PROXY" in self.valuation_warnings:
                self.valuation_warnings.remove("VALUATION_PROXY")
                
            earnings_ps = 0.0
            nav_ps = 0.0
        elif holdings_ok:
            sotp_ps, flags, breakdown = self._holdings_value(holdings_cfg, equity, shares, discount)
            if "VALUATION_PROXY" in self.valuation_warnings:
                self.valuation_warnings.remove("VALUATION_PROXY")
            earnings_ps = sotp_ps
            nav_ps = 0.0
        else:
            # PROXY_MODE: Phần vận hành (Earnings) + NAV
            flags = ["VALUATION_PROXY"]
            if holdings:
                # Có khai báo cổ phần nhưng không dựng được giá/VCSH một công ty con → không định giá nửa vời.
                flags.append("SOTP_HOLDINGS_INCOMPLETE")
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
            
        if missing:
            # Mảng AI nhập thiếu → không dùng AI_SOTP (không định giá nửa vời), báo rõ trường thiếu.
            flags.append("SOTP_SEGMENT_INPUT_MISSING: " + ", ".join(missing))
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
        is_proxy_mode = not ai_mode and not holdings_ok

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

        if holdings_ok and sotp_ps <= 0:
            not_rated = True  # phần chưa niêm yết âm sổ sách lớn hơn giá trị cổ phần niêm yết

        if not_rated:
            flags.append("NOT_RATED")

        return {
            "blended_fair_value_per_share": sotp_ps, # Dùng luôn làm target price
            "earnings_value_per_share": earnings_ps if not ai_mode else sotp_ps,
            "nav_per_share": nav_ps if not ai_mode else 0.0,
            "discount_applied": discount,
            "not_rated": not_rated,
            "flags": flags,
            "sotp_holdings_breakdown": breakdown,
        }

    @staticmethod
    def segments_equity(segments, net_debt: float, minority_interest: float):
        """(Giá trị VCSH mẹ AI_SOTP — đồng, [trường thiếu]).

        VCSH = Σ EV − (nợ ròng hợp nhất − Σ nợ ròng con) + Σ Equity − (CĐKKS hợp nhất − Σ CĐKKS con).
        Mảng EQUITY là phần sở hữu đã sau nợ của chính công ty đó (vd stake × vốn hóa). Nếu công ty đó được
        HỢP NHẤT thì nợ vay ròng (100%) và CĐKKS của nó đã nằm trong số hợp nhất → phải loại ra, nếu không
        bị trừ hai lần (CFA SOTP). Công ty liên kết (hop_nhat = False) không có trong nợ/CĐKKS hợp nhất.
        """
        def _yes_no(v):
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            return True if s in {"true", "1", "1.0", "có", "co"} else False if s in {"false", "0", "0.0", "không", "khong"} else None

        total_ev = total_eq = sub_net_debt = sub_minority = 0.0
        missing = []
        for i, seg in enumerate(segments, 1):
            name = seg.get('ten_mang') or f"#{i}"
            val = input_number(seg, 'gia_tri')
            if val is None:
                missing.append(f"{name}.gia_tri")
                continue
            mult = input_number(seg, 'multiple_ky_vong') or 0.0
            # multiple 0/trống → gia_tri là giá trị tuyệt đối (vd DCF mảng đã ra số tiền)
            value = val * 1e9 * (mult if mult > 0 else 1.0)
            if 'EV' in str(seg.get('loai_gia_tri', '')).upper():
                total_ev += value
                continue
            total_eq += value  # mặc định Equity nếu không ghi rõ EV
            consolidated = _yes_no(seg.get('hop_nhat'))
            if consolidated is None:
                missing.append(f"{name}.hop_nhat")
            elif consolidated:
                nd, mi = input_number(seg, 'no_vay_rong_ty'), input_number(seg, 'cdkks_ty')
                missing += [f"{name}.{k}" for k, v in (("no_vay_rong_ty", nd), ("cdkks_ty", mi)) if v is None]
                sub_net_debt += (nd or 0.0) * 1e9
                sub_minority += (mi or 0.0) * 1e9
        equity = total_ev - (net_debt - sub_net_debt) + total_eq - (minority_interest - sub_minority)
        return equity, missing

    @staticmethod
    def _holdings_value(cfg: dict[str, Any], parent_equity: float, shares: float, discount: float):
        """(FV/cp, cờ, phân rã tỷ đồng) của chế độ SOTP_HOLDINGS. `parent_equity` (đồng) là VCSH mẹ hợp
        nhất — đã chứa giá sổ phần sở hữu công ty con và mọi mảng chưa niêm yết (kể cả nợ ròng hợp nhất).
        Không trừ CĐKKS lần nữa: VCSH mẹ đã loại phần đó."""
        from datetime import date

        parts = {}
        for h in cfg["holdings"]:
            book = h["carrying_value_bn"] if h.get("carrying_value_bn") is not None else h["stake"] * h["book_equity_bn"]
            value = h["stake"] * h["market_cap_bn"]
            parts[h["ticker"]] = {"stake": h["stake"], "market_value_bn": value, "book_bn": book, "reval_bn": value - book}
        reval_bn = sum(p["reval_bn"] for p in parts.values())
        sotp_ps = (parent_equity + reval_bn * 1e9) / shares * (1 - discount)

        flags = ["SOTP_HOLDINGS_MODE", "SOTP_UNLISTED_AT_BOOK"]
        # Lỗi dữ liệu mức error của công ty con (vd chưa audit nguồn) → mã mẹ không công bố được.
        flags += [
            f"SOTP_SUBSIDIARY_DATA_ERROR:{h['ticker']}({','.join(h['data_errors'])})"
            for h in cfg["holdings"] if h.get("data_errors")
        ]
        try:
            reviewed_on = date.fromisoformat(str(cfg.get("as_of") or "")[:10])
        except ValueError:
            reviewed_on = None
        # Có người duyệt mà thiếu/hỏng ngày duyệt thì hạn TTL không tính được → coi như chưa duyệt.
        if not cfg.get("reviewed_by") or reviewed_on is None:
            flags.append("SOTP_HOLDINGS_UNVERIFIED")
        # shortcut: hạn rà soát so với ngày định giá (as_of backtest dùng bảng cổ phần hiện tại), đủ cho
        # hiệu chỉnh gần hiện tại; backtest xa cần lịch sử tỷ lệ sở hữu theo kỳ.
        age = (date.fromisoformat(cfg["valuation_date"]) - reviewed_on).days if reviewed_on else None
        if (age is not None and age > int(cfg["review_ttl_days"])) or any(h.get("price_stale") for h in cfg["holdings"]):
            flags.append("SOTP_HOLDINGS_STALE")
        breakdown = {"parent_equity_bn": parent_equity / 1e9, "reval_bn": reval_bn, "holdings": parts}
        return sotp_ps, flags, breakdown
