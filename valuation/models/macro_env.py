from dataclasses import dataclass
from typing import Optional

@dataclass
class MacroEnvironment:
    """
    Thông số vĩ mô đầu vào để điều chỉnh các giả định định giá (WACC, Terminal Growth, MOS).
    """
    inflation_rate: float = 0.04 # Mặc định 4%
    sbv_stance: str = "Neutral" # "Easing", "Neutral", "Tightening"
    risk_free_rate: Optional[float] = None # Lấy mặc định từ config nếu None
    country_risk_premium: Optional[float] = None # CRP mặc định
    
    @property
    def is_macro_stressed(self) -> bool:
        """
        Xác định xem môi trường vĩ mô có đang căng thẳng (đòi hỏi nới rộng MOS) hay không.
        - Lạm phát trên 5%
        - SBV thắt chặt (Tightening)
        """
        return self.inflation_rate > 0.05 or self.sbv_stance == "Tightening"
    
    def get_adjusted_crp(self, base_crp: float) -> float:
        """
        Điều chỉnh Country Risk Premium (CRP) nếu vĩ mô căng thẳng.
        Tăng CRP lên 2 điểm phần trăm (2%) nếu vĩ mô căng thẳng.
        """
        crp = self.country_risk_premium if self.country_risk_premium is not None else base_crp
        if self.is_macro_stressed:
            return crp + 0.02
        return crp

    @classmethod
    def from_db(cls, db) -> "MacroEnvironment":
        """Tự dựng môi trường vĩ mô TỪ DỮ LIỆU THẬT trong macro_series (mỗi lần quét).

        - inflation_rate: CPI_YOY mới nhất (nếu có; thiếu → giữ mặc định 4%).
        - risk_free_rate: TPCP_10Y mới nhất (nếu có).
        - sbv_stance: suy từ 2 quan sát POLICY_RATE gần nhất — tăng → Tightening,
          giảm → Easing, không đủ dữ liệu/không đổi → Neutral.

        KHÔNG bịa số: chỉ số nào thiếu trong DB thì dùng giá trị trung tính, và
        cờ STALE_MACRO_RF (freshness gate) sẽ cảnh báo riêng nếu rf quá cũ.
        """
        from valuation.db.models import MacroSeries

        def _latest(code: str, n: int = 1):
            rows = (
                db.query(MacroSeries.date, MacroSeries.value)
                .filter(MacroSeries.indicator_code == code)
                .order_by(MacroSeries.date.desc())
                .limit(n)
                .all()
            )
            return [(d, float(v)) for d, v in rows if v is not None]

        env = cls()

        cpi = _latest("CPI_YOY")
        if cpi:
            env.inflation_rate = cpi[0][1]

        rf = _latest("TPCP_10Y")
        if rf:
            env.risk_free_rate = rf[0][1]

        policy = _latest("POLICY_RATE", n=2)
        if len(policy) == 2:
            latest, prev = policy[0][1], policy[1][1]
            if latest > prev + 1e-9:
                env.sbv_stance = "Tightening"
            elif latest < prev - 1e-9:
                env.sbv_stance = "Easing"

        return env
