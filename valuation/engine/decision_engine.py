from typing import Dict, Any, List, Optional
from valuation.config import load_defaults
from valuation.models.financials import GovernanceData

from valuation.models.macro_env import MacroEnvironment

# Nhãn hiển thị duy nhất cho mọi kênh (UI, PDF, Sheets, báo cáo).
REC_LABELS_VI = {
    "BUY": "MUA",
    "HOLD": "NẮM GIỮ",
    "TRIM": "GIẢM TỶ TRỌNG",
    "SELL": "BÁN",
    "HARD REJECT": "LOẠI (RỦI RO QUẢN TRỊ)",
    "NOT_RATED": "KHÔNG XẾP HẠNG",
}


def recommend(
    ticker: str,
    current_price: float,
    fair_value: float,
    governance: Optional[GovernanceData] = None,
    macro_env: Optional[MacroEnvironment] = None,
    not_rated: bool = False,
) -> Dict[str, Any]:
    """Nguồn khuyến nghị DUY NHẤT: biên an toàn theo bản chất ngành + cổng chặn."""
    from valuation.engine.sector_router import route

    plan = route(ticker) or {}
    return InvestmentDecisionMaker(
        business_nature=plan.get("business_nature", "Unknown"),
        current_price=current_price,
        fair_value=fair_value,
        governance=governance,
        macro_env=macro_env,
        not_rated=not_rated,
    ).make_decision()

class InvestmentDecisionMaker:
    """
    Quyết định hành động đầu tư dựa trên Hard Gates và Dynamic Margin of Safety (MOS).
    """

    def __init__(self, business_nature: str, current_price: float, fair_value: float, governance: GovernanceData, macro_env: MacroEnvironment = None, not_rated: bool = False):
        self.business_nature = business_nature
        self.current_price = current_price
        self.fair_value = fair_value
        self.governance = governance
        self.macro_env = macro_env
        # D28: mô hình tự nhận không đủ cơ sở định giá mã này (vd proxy SOTP lệch
        # phi lý so thị giá). Khi đó KHÔNG được phát khuyến nghị MUA/BÁN — đưa ra
        # khuyến nghị từ một con số mình không tin là điều tệ hơn cả im lặng.
        self.not_rated = not_rated

    def get_target_mos(self) -> float:
        """
        Xác định Margin of Safety an toàn tối thiểu theo loại hình doanh nghiệp.
        Và tự động nới rộng (+5%) nếu môi trường vĩ mô đang căng thẳng.
        """
        cfg = load_defaults().get("margin_of_safety") or {}
        by_nature = cfg.get("by_business_nature") or {}
        mos = float(by_nature.get(self.business_nature, cfg.get("default", 0.25)))
        # Nới rộng MOS nếu vĩ mô xấu
        if self.macro_env and self.macro_env.is_macro_stressed:
            mos += float(cfg.get("macro_stress_add", 0.05))
        return mos

    def evaluate_hard_gates(self) -> List[str]:
        """
        Kiểm tra rủi ro nghiêm trọng. Nếu có bất kỳ lỗi nào, mã sẽ bị Hard Reject.
        """
        violations = []
        if self.governance:
            if self.governance.audit_issue:
                violations.append("Vấn đề ngoại trừ từ kiểm toán")
            if self.governance.legal_issue:
                if self.business_nature == "Developer":
                    violations.append("Rủi ro pháp lý dự án BĐS đặc biệt nghiêm trọng")
                else:
                    violations.append("Rủi ro pháp lý nghiêm trọng")
            if self.governance.liquidity_issue:
                violations.append("Rủi ro thanh khoản")
        return violations

    def make_decision(self) -> Dict[str, Any]:
        """
        Ra quyết định đầu tư cuối cùng (Buy / Hold / Trim / Sell / Hard Reject).
        """
        hard_gates_violations = self.evaluate_hard_gates()
        upside = ((self.fair_value / self.current_price - 1.0) * 100.0) if self.current_price > 0 else 0.0
        target_mos = self.get_target_mos()
        # So sánh upside (%) với target_mos (ratio) → cần nhân target_mos × 100
        target_mos_pct = target_mos * 100.0

        # Epsilon chống lỗi làm tròn số thực ở biên: upside đúng bằng MOS (vd
        # 115/100-1 = 14.999...% do float) vẫn phải được coi là đạt ngưỡng BUY.
        _EPS = 1e-9
        if len(hard_gates_violations) > 0:
            recommendation = "HARD REJECT"
        elif self.not_rated:
            # Hard gates vẫn ưu tiên cao hơn (rủi ro quản trị là thông tin có
            # giá trị kể cả khi không định giá được).
            recommendation = "NOT_RATED"
        elif upside >= target_mos_pct - _EPS:
            recommendation = "BUY"
        elif upside >= -_EPS:
            recommendation = "HOLD"
        elif upside >= float((load_defaults().get("margin_of_safety") or {}).get("trim_floor", -0.10)) * 100.0 - _EPS:
            recommendation = "TRIM"
        else:
            recommendation = "SELL"

        return {
            "business_nature": self.business_nature,
            "target_mos": target_mos,
            "hard_gates_violations": hard_gates_violations,
            "upside": upside,
            "recommendation": recommendation
        }
