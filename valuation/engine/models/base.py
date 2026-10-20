from typing import Dict, Any
import copy
import math

# Spread tối thiểu giữa WACC và terminal growth g.
# Khi discount rate thấp (VND-base COE ~8%), g 4-5% làm spread mỏng → terminal
# value phình bất thường. Ép spread tối thiểu để TV ổn định (Gordon sanity check).
MIN_WACC_G_SPREAD = 0.03


def midcycle_level(values, revenues, window=None):
    """Mức lợi nhuận giữa chu kỳ = trung vị biên (GỒM năm lỗ) × doanh thu kỳ cuối.

    Chuẩn hóa theo BIÊN chứ không theo giá trị tuyệt đối: trung bình tuyệt đối nhiều
    năm danh nghĩa định giá thấp DN đang lớn lên và định giá cao DN đang thu hẹp.
    Trả None khi không có cặp (giá trị, doanh thu>0) nào.
    """
    import statistics
    pairs = [(v, r) for v, r in zip(values, revenues) if v is not None and r and r > 0]
    if not pairs:
        return None
    if window:
        pairs = pairs[-int(window):]  # D61: chỉ N năm gần nhất (tránh trộn mô hình kinh doanh cũ)
    return statistics.median(v / r for v, r in pairs) * pairs[-1][1]


def input_number(row: dict[str, Any], key: str) -> float | None:
    """Số analyst nhập (bảng st.data_editor/AI bóc tách); None khi trống, NaN, 'null' hoặc không phải số
    — để model báo THIẾU thay vì âm thầm coi là 0/100%."""
    try:
        v = float(row.get(key))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


class BaseValuationModel:
    """
    Base class cho tất cả các mô hình định giá.
    Chứa logic dùng chung:
    - Lưu trữ dữ liệu tài chính và assumptions.
    - Logic tính Greeks (Sensitivity).
    - Validation cơ bản (g >= WACC, chia 0).
    """
    def __init__(self, ticker: str, current_financials: Dict[str, Any], assumptions: Dict[str, Any]):
        self.ticker = ticker
        self.current_financials = current_financials
        self.assumptions = assumptions
        
        # Biến được khai báo ở model cụ thể
        self.coe = assumptions.get('cost_of_equity', 0.13)
        self.wacc = assumptions.get('wacc', 0.11)
        self.g = assumptions.get('long_term_growth', 0.05)
        self.valuation_warnings = []

        self.validators()

    def validators(self):
        """
        Guardrail terminal growth g:
        1. Damodaran cap: g không vượt risk-free rate (rf proxy tăng trưởng kinh tế
           danh nghĩa dài hạn — một perpetuity không thể tăng nhanh hơn nền kinh tế).
        2. Spread tối thiểu WACC−g (và COE−g) ≥ MIN_WACC_G_SPREAD để TV không phình.
        """
        rf = self.assumptions.get('risk_free_rate')
        if rf is not None and self.g > rf:
            self.valuation_warnings.append(
                f"TERMINAL_G_CAPPED_AT_RF: g={self.g:.4f} > rf={rf:.4f} → clamp về rf"
            )
            self.g = rf

        uses_wacc = getattr(self, 'use_wacc', False)
        discount = self.wacc if uses_wacc else self.coe
        if self.g > discount - MIN_WACC_G_SPREAD:
            new_g = discount - MIN_WACC_G_SPREAD
            self.valuation_warnings.append(
                f"TERMINAL_G_CLAMPED_SPREAD: g={self.g:.4f} → {new_g:.4f} "
                f"(ép spread {'WACC' if uses_wacc else 'COE'}−g ≥ {MIN_WACC_G_SPREAD:.2f})"
            )
            self.g = new_g

    def forecast_drivers(self):
        """Phải được override bởi model con. Trả về dataframe hoặc dict forecast."""
        raise NotImplementedError

    def perform_valuation(self) -> Dict[str, Any]:
        """Phải được override bởi model con. Trả về kết quả định giá."""
        raise NotImplementedError

    def calculate_greeks(self) -> Dict[str, float]:
        """
        Tính đạo hàm bậc nhất (greeks) của fair value theo từng driver.
        Mô hình con cần define self.assumptions['drivers'] = {'nim': {'bump': 0.001}, ...}
        """
        base_valuation = self.perform_valuation()
        base_fv = base_valuation.get('blended_fair_value_per_share', 0.0)
        
        greeks = {}
        drivers = self.assumptions.get('drivers', {})
        
        for driver_name, config in drivers.items():
            bump_val = config.get('bump', 0.01)
            original_val = self.assumptions.get(driver_name)
            
            if original_val is None:
                continue
                
            # Tạo bản sao mô hình với giả định mới
            bumped_assumptions = copy.deepcopy(self.assumptions)
            bumped_assumptions[driver_name] = original_val + bump_val
            
            # Khởi tạo instance mới cùng type với class hiện tại
            model_class = type(self)
            try:
                bumped_model = model_class(self.ticker, self.current_financials, bumped_assumptions)
                bumped_valuation = bumped_model.perform_valuation()
                bumped_fv = bumped_valuation.get('blended_fair_value_per_share', 0.0)
                
                # Tính đạo hàm: dFV / dDriver
                if bump_val != 0:
                    delta = (bumped_fv - base_fv) / bump_val
                else:
                    delta = 0.0
            except Exception:
                delta = None
                
            greeks[f"delta_{driver_name}"] = delta
            
        return {
            "base_fair_value": base_fv,
            "greeks": greeks
        }
