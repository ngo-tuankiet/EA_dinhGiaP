"""Nguồn sự thật duy nhất cho Cost of Equity (COE) — convention VND-base.

QUYẾT ĐỊNH CHỐT (xem golden rule trong config/defaults.yaml):
    rf  = TPCP VN 10Y (lấy động từ macro_series) — lãi suất phi rủi ro danh
          nghĩa bằng VND (đã gồm lạm phát kỳ vọng VN).
    erp = mature-market ERP + Country Risk Premium VN (erp_mature + crp_vn).
    COE = rf + beta * (erp_mature + crp_vn)

Lý do cộng CRP (chuẩn Damodaran cho thị trường mới nổi):
    CRP là phần bù RỦI RO VỐN CỔ PHẦN mà nhà đầu tư đòi hỏi khi nắm giữ cổ
    phiếu tại thị trường mới nổi — TÁCH BIỆT với rủi ro vỡ nợ nằm trong lợi
    suất trái phiếu chính phủ. Dùng rf_VN mà bỏ CRP sẽ under-price rủi ro cổ
    phiếu VN → WACC quá thấp → định giá lạc quan hệ thống (upside ảo).

File này là chỗ duy nhất quyết định ERP để mọi nơi (repo, route, ttm_helper)
dùng chung.
"""
from __future__ import annotations

from valuation.config import load_defaults
from valuation.models.macro_env import MacroEnvironment

# Equity premium tối thiểu hợp lệ (beta*erp). Dùng cho sanity floor.
# Với convention VND-base (erp = mature+CRP ~8.2%, beta 0.5-1.5) premium ~4-12%.
MIN_EQUITY_PREMIUM = 0.03


def get_erp(macro_env: MacroEnvironment | None = None) -> float:
    """ERP cho COE VND-base = mature-market ERP + Country Risk Premium VN.

    CRP tách biệt với rủi ro vỡ nợ trong lợi suất TPCP nên phải cộng để phản
    ánh đúng rủi ro vốn cổ phần của thị trường VN (chuẩn Damodaran).
    """
    coe_conv = load_defaults().get("coe_convention", {})
    erp_mature = float(coe_conv.get("erp_mature", 0.045))
    crp_vn = float(coe_conv.get("crp_vn", 0.037))
    
    if macro_env is not None:
        crp_vn = macro_env.get_adjusted_crp(crp_vn)
        
    return erp_mature + crp_vn


def terminal_growth(rf: float | None = None) -> float:
    """g vĩnh viễn duy nhất = min(config, rf, GDP danh nghĩa dài hạn)."""
    cfg = load_defaults()
    g = float(cfg.get("coe_convention", {}).get("terminal_growth", 0.04))
    caps = [float(cfg.get("long_run_nominal_gdp_growth", 0.08))]
    if rf is not None and rf > 0:
        caps.append(rf)
    return min([g] + caps)


def compute_coe(rf: float, beta: float, erp: float | None = None, macro_env: MacroEnvironment | None = None) -> float:
    """COE = rf + beta * erp. erp mặc định = mature ERP (VND-base)."""
    if erp is None:
        erp = get_erp(macro_env)
    return rf + beta * erp
