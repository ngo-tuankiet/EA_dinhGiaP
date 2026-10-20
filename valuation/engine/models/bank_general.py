"""
Bank General Model — Mô hình định giá ngân hàng tổng quát (Residual Income + Justified P/B).
Kế thừa tinh hoa từ VCB model và mở rộng cho tất cả các ngân hàng thương mại thuộc VN100.
"""
from typing import Dict, Any, List
from valuation.config import load_defaults
from valuation.models.financials_bank import CompanyBank
from valuation.engine.forecast_bank import (  # noqa: F401 — converged_roe giữ đường import cũ
    bank_terminal_roe,
    begin_roe_from_avg,
    converged_roe,
    forecast_bank_financials,
)


class BankGeneralValuationModel:
    """
    Mô hình định giá Ngân hàng dựa trên Pydantic CompanyBank.
    """
    def __init__(self, company: CompanyBank, projections: List[Dict[str, Any]] = None):
        self.company = company
        self.assumptions = company.assumptions
        self.base_bs = company.historical_bs[-1]
        self.base_is = company.historical_is[-1]
        
        # Chi phí vốn cổ phần
        self.rf = self.assumptions.risk_free_rate
        self.beta = self.assumptions.beta
        self.erp = self.assumptions.erp
        self.g = self.assumptions.terminal_growth_rate
        
        if self.assumptions.cost_of_equity is not None:
            self.coe = self.assumptions.cost_of_equity
        else:
            self.coe = self.rf + self.beta * self.erp
            
        # Ràng buộc g < coe
        if self.g >= self.coe:
            self.company.warnings.append(
                f"BANK_G_CLAMPED_BELOW_COE: g={self.g:.2%} >= COE={self.coe:.2%} → {self.coe - 0.005:.2%}"
            )
            self.g = self.coe - 0.005

        # Sanity Floor Check cho COE (VND-base: equity premium >= MIN_EQUITY_PREMIUM)
        from valuation.engine.coe import MIN_EQUITY_PREMIUM
        if self.coe < self.rf + MIN_EQUITY_PREMIUM:
            self.company.warnings.append(
                f"COE_TOO_LOW: Chi phí vốn cổ phần COE={self.coe:.2%} quá thấp "
                f"(thấp hơn rf={self.rf:.2%} + {MIN_EQUITY_PREMIUM:.1%}). Kiểm tra lại Beta ({self.beta}) hoặc ERP ({self.erp:.2%})."
            )

        # Dự phóng
        self.projections = projections if projections is not None else forecast_bank_financials(self.company)

        # B3: Fade ROE dài hạn (terminal_roe) về mức bền vững, TRẦN THEO TIER
        # chất lượng (không dùng 1 trần cứng cho mọi ngân hàng).
        #
        # Trần cứng 15% cho MỌI ngân hàng (bản trước) xoá sạch phần bù chất
        # lượng: ngân hàng top-tier (VCB/ACB/MBB/HDB/VIB, ROE lịch sử bền vững
        # >18% nhiều năm liền) bị ép về ĐÚNG mức ngân hàng trung bình (BID/CTG
        # ~15%), trong khi thị trường trả P/B cao hơn hẳn cho nhóm top-tier
        # (VD: VCB P/B thị trường ~2.16x vs ACB ~1.17x — model cũ chỉ phân
        # hoá được ~5%). Hệ quả: undervaluation hệ thống đúng nhóm ngân hàng
        # tốt nhất — điều tra 2026-07, xem DECISIONS.md.
        #
        # Quy tắc mới: ngân hàng có sustainable_roe lịch sử > ELITE_ROE_THRESHOLD
        # (đã bền vững nhiều năm, không phải đột biến 1 kỳ) được trần cao hơn
        # (ELITE_ROE_CAP). Ngân hàng còn lại giữ trần cũ (STANDARD_ROE_CAP) —
        # vẫn chống "upside ảo" cho ngân hàng trung bình/yếu.
        # D29 — BỎ HỆ THỐNG TIER, DÙNG MỘT TRẦN DUY NHẤT.
        #
        # Hệ thống tier của D20 (ngưỡng 18% -> trần 20%, dưới -> trần 15%) tạo một
        # VÁCH ĐỨNG phi kinh tế: ngân hàng ROE 17,9% bị ép về 15%, ngân hàng 18,1%
        # được giữ 20% — chênh 0,2pp đầu vào tạo ra chênh 5pp đầu ra, tức ~40% giá
        # trị. Tier đó sinh ra để CHỮA TRIỆU CHỨNG của một ước lượng tồi (trung
        # bình toàn lịch sử, gồm cả đỉnh chu kỳ). D29 sửa thẳng ước lượng
        # (median cửa sổ gần nhất, xem repo.py) nên tier trở thành thừa và có hại.
        ROE_CAP = float((load_defaults().get("bank_terminal", {}) or {}).get("terminal_roe_cap", 0.20))
        # ROE terminal trên VCSH BÌNH QUÂN (cùng định nghĩa roe5 và ROE ngành — config bank_terminal).
        self.terminal_roe, raw_roe = bank_terminal_roe(self.company)
        # RI terminal và P/B hợp lý cần ROE trên VCSH ĐẦU kỳ: trạng thái dừng VCSH tăng g → VCSH bình quân năm
        # 6 = B5·(1 + g/2), nên LN6 / B5 = ROE_T·(1 + g/2) (đẳng thức, không phải giả định mới).
        self.terminal_roe_begin = begin_roe_from_avg(self.terminal_roe, self.g)
        if raw_roe > ROE_CAP:
            self.company.warnings.append(
                f"BANK_TERMINAL_ROE_CAPPED: ROE bền vững {raw_roe:.1%} vượt trần "
                f"{ROE_CAP:.0%} — một ngân hàng không thể duy trì vĩnh viễn mức sinh "
                f"lời này dưới áp lực cạnh tranh và tích luỹ vốn."
            )

        # Kiểm tra NHẤT QUÁN GORDON: công thức Target P/B = (ROE-g)/(COE-g) chỉ
        # đúng khi tỷ lệ chi trả cổ tức ở trạng thái dừng thoả g = ROE × (1-payout),
        # tức payout* = 1 - g/ROE. Nếu payout dùng trong giai đoạn dự phóng lệch
        # quá xa payout* thì hai khối đang mô tả hai thế giới khác nhau.
        self._check_terminal_consistency()
        self._check_terminal_jump()

    def _check_terminal_jump(self) -> None:
        """D67: LN6 của RI terminal (ROE_T đầu kỳ × VCSH5) phải nối liền LN5 dự phóng: |LN6/LN5 − (1 + g)| quá ngưỡng
        (hoặc LN5 ≤ 0) → cờ cảnh báo BANK_TERMINAL_JUMP. Bắt tái phát lỗi phản biện r4 (kịch bản dồn sốc vào năm 5)
        và ca analyst sửa driver năm 4–5 làm năm 5 lệch xa ROE_T."""
        tol = float(load_defaults()["bank_terminal"]["terminal_jump_flag_tolerance"])
        ni5 = self.projections[-1]["net_income"]
        ni6 = self.terminal_roe_begin * self.projections[-1]["total_equity"]
        if ni5 <= 0:
            self.company.warnings.append(
                f"BANK_TERMINAL_JUMP: LN năm 5 = {ni5:,.0f} tỷ ≤ 0 trong khi RI terminal giả định LN6 = {ni6:,.0f} tỷ")
        elif abs(ni6 / ni5 - (1 + self.g)) > tol:
            self.company.warnings.append(
                f"BANK_TERMINAL_JUMP: LN6/LN5 = {ni6 / ni5:.2f} lệch 1 + g = {1 + self.g:.3f} quá {tol:.0%}")

    def _check_terminal_consistency(self) -> None:
        """Cảnh báo khi trạng thái dừng KHÔNG THỂ TỒN TẠI về mặt toán học.

        Gordon: ở trạng thái dừng, g = ROE × (1 − payout) ⇒ payout* = 1 − g/ROE.

        LƯU Ý CÓ CHỦ Ý — chỉ cảnh báo ca payout* <= 0 (tức ROE <= g): khi đó ngân
        hàng phải PHÁT HÀNH THÊM VỐN vĩnh viễn để tăng trưởng bằng g trong khi sinh
        lời thấp hơn g, một trạng thái dừng không tồn tại.

        Bản đầu của D29 cảnh báo mỗi khi payout* lệch payout dự phóng quá 30pp —
        và nó bắn ở 15/17 ngân hàng, tức thành NHIỄU chứ không phải tín hiệu.
        Nghĩ lại: chênh lệch đó là BẢN CHẤT của mọi mô hình 2 giai đoạn (giai đoạn
        đầu giữ lại lợi nhuận để tăng trưởng, trạng thái dừng chi trả gần hết) —
        Damodaran nói rõ phải điều chỉnh payout cho khớp g và ROE ở giai đoạn dừng.
        Cảnh báo cái bình thường sẽ làm người đọc bỏ qua cả cảnh báo thật.
        """
        if self.terminal_roe <= 0:
            return
        implied_payout = 1.0 - (self.g / self.terminal_roe_begin)
        if implied_payout <= 0:
            self.company.warnings.append(
                f"TERMINAL_IMPOSSIBLE: ROE bền vững {self.terminal_roe:.1%} <= tăng "
                f"trưởng vĩnh viễn g {self.g:.1%}. Trạng thái dừng này đòi ngân hàng "
                f"phát hành thêm vốn vĩnh viễn — không tồn tại. Rà lại ROE hoặc g."
            )

    def calculate_residual_income(self) -> Dict[str, float]:
        """Tính giá trị hợp lý theo phương pháp Residual Income (Excess Return)."""
        pv_ri = 0.0
        beg_equity = self.base_bs.total_equity
        ri_list = []
        
        for i, proj in enumerate(self.projections):
            # RI = LNST - (VCSH đầu kỳ * COE)
            ri = proj["net_income"] - (beg_equity * self.coe)
            ri_list.append(ri)
            
            # Chiết khấu về PV
            pv_ri += ri / ((1 + self.coe) ** (i + 1))
            beg_equity = proj["total_equity"]
            
        # Terminal Value cho RI (fade về terminal_roe bền vững)
        eq_terminal_begin = self.projections[-1]["total_equity"]
        sustainable_ri = (self.terminal_roe_begin - self.coe) * eq_terminal_begin
        terminal_ri = sustainable_ri / (self.coe - self.g)
        pv_terminal_ri = terminal_ri / ((1 + self.coe) ** len(self.projections))
        
        total_ri_equity_value = self.base_bs.total_equity + pv_ri + pv_terminal_ri
        
        # Đổi sang VND mỗi cổ phiếu (VCSH tỷ đồng, shares triệu cp -> tỷ/triệu = nghìn đồng, nhân 1000 ra đồng)
        ri_fvps = (total_ri_equity_value / self.company.shares_outstanding) * 1000.0 if self.company.shares_outstanding > 0 else 0.0
        
        return {
            "pv_ri": pv_ri,
            "pv_terminal_ri": pv_terminal_ri,
            "equity_value": total_ri_equity_value,
            "fair_value_per_share": ri_fvps
        }

    def calculate_pb_valuation(self) -> Dict[str, float]:
        """Tính giá trị hợp lý theo phương pháp Justified P/B.

        B3: ưu tiên sustainable ROE (ROE bền vững dài hạn) cho Gordon Growth.
        ROE dự phóng năm 5 có thể còn phản ánh trạng thái siêu lợi nhuận nhất
        thời (ngân hàng VN ROE ~20% hiện tại, cạnh tranh + tích lũy vốn nén dần).
        Chỉ fallback về ROE năm 5 khi assumptions không cung cấp sustainable_roe.
        """
        # Gordon P0/B0 = (ROE − g)/(COE − g) với ROE = LN năm tới / VCSH hiện tại (đầu kỳ).
        long_term_roe = self.terminal_roe_begin
        
        # Target P/B = (ROE - g) / (Re - g)
        if self.coe <= self.g:
            target_pb = 1.0
        else:
            target_pb = (long_term_roe - self.g) / (self.coe - self.g)
            
        # D29 — có SÀN thì phải có TRẦN. Trước đây chỉ `max(0.3, ...)`, không có
        # giới hạn trên: ACB ra 1,82x trong khi thị trường trả 1,17x mà không có
        # gì chặn lại. Ngưỡng lấy từ config (luật vàng #5).
        _cfg = load_defaults().get("bank_terminal", {}) or {}
        pb_floor = float(_cfg.get("target_pb_floor", 0.3))
        pb_ceiling = float(_cfg.get("target_pb_ceiling", 3.0))
        raw_pb = target_pb
        target_pb = max(pb_floor, min(target_pb, pb_ceiling))
        if raw_pb < pb_floor:
            self.company.warnings.append(
                f"BANK_PB_CLAMPED_LOW: P/B lý thuyết {raw_pb:.2f}x -> sàn {pb_floor:.2f}x")
        elif raw_pb > pb_ceiling:
            self.company.warnings.append(
                f"BANK_PB_CLAMPED_HIGH: P/B lý thuyết {raw_pb:.2f}x -> trần {pb_ceiling:.2f}x")

        total_pb_equity_value = target_pb * self.base_bs.total_equity
        pb_fvps = (total_pb_equity_value / self.company.shares_outstanding) * 1000.0 if self.company.shares_outstanding > 0 else 0.0

        # So P/B mục tiêu với P/B THỊ TRƯỜNG — phép thử độc lập với đồng thuận CTCK.
        # Không ép khớp thị trường, nhưng lệch xa thì phải có luận điểm.
        from valuation.engine.guardrails import check_implied_pb, market_pb
        _mkt_pb = market_pb(
            self.company.current_price,
            self.base_bs.total_equity * 1e9,
            self.company.shares_outstanding * 1e6,
        )
        for _f in check_implied_pb(target_pb, _mkt_pb, label="BANK_PB"):
            self.company.warnings.append(_f)

        # Implied P/B sanity check warning
        if target_pb > 4.0 or target_pb < 0.5:
            self.company.warnings.append(
                f"IMPLIED_PB_WARNING: P/B ngầm định Justified P/B = {target_pb:.2f}x "
                f"nằm ngoài khoảng hợp lý [0.5, 4.0]. ROE={long_term_roe:.2%}, COE={self.coe:.2%}, g={self.g:.2%}."
            )

        return {
            "long_term_roe": self.terminal_roe,  # VCSH bình quân (định nghĩa chung bank_terminal)
            "long_term_roe_begin": long_term_roe,  # VCSH đầu kỳ — dùng trong (ROE − g)/(COE − g)
            "target_pb": target_pb,
            "equity_value": total_pb_equity_value,
            "fair_value_per_share": pb_fvps
        }

    def calculate_market_pb_valuation(self) -> Dict[str, float] | None:
        """Chân so sánh THỊ TRƯỜNG: P/B trung vị 5 cuối năm của chính NH × BVPS hiện tại.

        P/B hợp lý (ROE−g)/(COE−g) dùng cùng ROE/COE/g với RI nên không kiểm tra
        chéo được gì; chân này neo vào mức thị trường thực sự trả cho chính NH.
        """
        pb = getattr(self.assumptions, "historical_pb_median", None)
        if not pb or pb <= 0 or self.company.shares_outstanding <= 0:
            return None
        return {
            "market_pb": pb,
            "fair_value_per_share": pb * self.base_bs.parent_equity / self.company.shares_outstanding * 1000.0,
        }

    def perform_valuation(self) -> Dict[str, Any]:
        """Pha trộn kết quả định giá."""
        ri_res = self.calculate_residual_income()
        pb_res = self.calculate_pb_valuation()
        
        weight_ri = self.assumptions.weight_ri
        weight_pb = 1.0 - weight_ri
        
        blended_fvps = (ri_res["fair_value_per_share"] * weight_ri) + (pb_res["fair_value_per_share"] * weight_pb)
        
        return {
            "blended_fair_value_per_share": blended_fvps,
            "ri_fvps": ri_res["fair_value_per_share"],
            "pb_fvps": pb_res["fair_value_per_share"],
            "weight_ri": weight_ri,
            "coe": self.coe,
            "terminal_g": self.g,
            "projections": self.projections
        }
