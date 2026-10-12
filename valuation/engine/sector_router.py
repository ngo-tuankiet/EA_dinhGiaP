"""
Sector router — NGUỒN SỰ THẬT DUY NHẤT cho định tuyến phương pháp định giá VN100.

Dữ liệu: valuation/config/routing.json (sinh từ VN100_Phuong_phap_dinh_gia_chi_tiet.xlsx
qua generate_routing.py, đã đối chiếu báo cáo SSI/Vietcap/HSC). Đây là file routing
DUY NHẤT — module router.py cũ giờ chỉ re-export ValuationRouter từ đây.

Hai tầng API trên cùng một nguồn:
  - ValuationRouter().get_routing(ticker)  → dict thô {primary, secondary, weights...}
    (giữ nguyên cho sensitivity.py, views — consumer cũ).
  - route(ticker) / is_supported(ticker)   → API canonical {method, engine, status...}
    (cho route gate + báo cáo trạng thái phủ phương pháp).

HAI TRỤC ĐỘC LẬP (đọc kỹ để tránh lẫn):
  1. `method` (PHƯƠNG PHÁP định giá) — quyết định bởi `primary` trong routing.json.
     Đây là NGUỒN DUY NHẤT chọn mô hình chạy (RI_PB/DCF/PE/PB/EV_EBITDA/RNAV/SOTP).
  2. `business_nature` (BẢN CHẤT kinh doanh) — suy từ sector, CHỈ dùng để đặt
     Margin of Safety trong decision_engine (và chọn nhánh blend phụ của DCF:
     P/E cho Compounder/Retail vs EV/EBITDA cho phần còn lại).
  → business_nature KHÔNG tự chọn method. Khi đổi ngành 1 mã trong routing.json,
    nhớ kiểm tra CẢ `primary` (method) cho khớp bản chất mới.
"""
from __future__ import annotations
import json
import os
from functools import lru_cache
from typing import Tuple, Dict, Any, Optional

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "routing.json"
)

# primary (routing.json, từ Excel) → mã canonical của engine.
_PRIMARY_TO_METHOD = {
    "RI": "RI_PB",
    "FCFF": "DCF",
    "RNAV": "RNAV",
    "SOTP": "SOTP",
    "P/B": "PB",
    "P/E": "PE",
    "EV/EBITDA": "EV_EBITDA",
}

# Trạng thái hỗ trợ từng phương pháp canonical:
#   IMPLEMENTED     — model chạy trên dữ liệu thật.
#   PARTIAL         — có model nhưng dùng PROXY (gắn cờ VALUATION_PROXY).
#   NOT_IMPLEMENTED — chưa có model; route gắn cờ, không định giá.
METHOD_STATUS: Dict[str, str] = {
    "RI_PB": "IMPLEMENTED",   # bank_general.BankGeneralValuationModel (RI + P/B thị trường)
    "DCF":   "IMPLEMENTED",   # dcf.DCFValuationModel (build_company_data); gồm cả FCFF+EV/EBITDA
    "RNAV":  "PARTIAL",       # rnav.RNAVValuationModel.from_pydantic — proxy
    "SOTP":  "PARTIAL",       # sotp.SOTPValuationModel.from_pydantic — proxy
    "PB":    "IMPLEMENTED",   # pb_relative.PBRelativeValuationModel (justified P/B từ ROE)
    "EV_EBITDA": "IMPLEMENTED",  # ev_ebitda.EVEBITDAValuationModel (EBITDA chuẩn hóa 3 năm)
    "PE":    "IMPLEMENTED",       # pe_relative.PERelativeValuationModel (EPS chuẩn hóa median)
}

METHOD_ENGINE: Dict[str, str] = {
    "RI_PB": "bank", "DCF": "dcf", "RNAV": "rnav",
    "SOTP": "sotp", "PB": "securities", "EV_EBITDA": "ev_ebitda", "PE": "pe",
}


class ValuationRouter:
    """Đọc routing.json, trả routing thô cho từng mã (API cũ — giữ nguyên hợp đồng)."""

    def __init__(self, config_path: str = None):
        self.config_path = config_path or _CONFIG_PATH
        self.routing_data = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def get_routing(self, ticker: str) -> Dict[str, Any]:
        ticker = ticker.upper()
        if ticker in self.routing_data:
            return self.routing_data[ticker]
        return {
            "sector": "Unknown", "primary": "FCFF", "secondary": None,
            "weight_primary": 1.0, "weight_secondary": 0.0,
            "raw_primary": "Default FCFF", "raw_secondary": "", "raw_weights": "",
        }


@lru_cache(maxsize=1)
def _router() -> ValuationRouter:
    return ValuationRouter()


def route(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Kế hoạch định giá canonical cho 1 mã, hoặc None nếu ngoài bảng VN100.
    {ticker, method, engine, status, group, weight, verified, raw_main}
    """
    data = _router().routing_data.get(ticker.upper())
    if not data:
        return None
    method = _PRIMARY_TO_METHOD.get(data.get("primary", "FCFF"), "DCF")
    
    # Suy luận Business Nature từ sector code trong routing.json
    group = data.get("sector", "")
    _SECTOR_TO_NATURE = {
        # Tài chính
        "NH": "Bank",
        "Ngân hàng": "Bank",
        # Chứng khoán: lợi nhuận biến động mạnh theo thị trường → nhóm riêng,
        # MOS cao hơn ngân hàng (xem decision_engine.get_target_mos).
        "CK": "Securities",
        "Chứng khoán": "Securities",
        "BH": "Bank",           # Bảo hiểm → ổn định hơn CK, giữ MOS như ngân hàng
        "Bảo hiểm": "Bank",
        # Compounder (tăng trưởng ổn định, biên cao)
        "Công nghệ": "Compounder",
        "CNTT & viễn thông": "Compounder",
        "Tiêu dùng": "Compounder",
        "Dược": "Compounder",
        "Đa ngành": "Compounder",
        # Cyclical (chu kỳ kinh tế)
        "Thép": "Cyclical",
        "Vật liệu xây dựng": "Cyclical",
        "Dầu khí": "Cyclical",
        "Phân bón": "Cyclical",
        "Hóa chất": "Cyclical",
        "Hàng không": "Cyclical",
        "Xây dựng": "Cyclical",
        "Vận tải": "Cyclical",
        "Hàng hải": "Cyclical",
        "Dệt may/TS": "Cyclical",
        "Cao su/NN": "Cyclical",
        "Cảng": "Cyclical",
        # Bán lẻ
        "Bán lẻ": "Retail",
        # Utility (tiện ích / hạ tầng ổn định)
        "Điện": "Utility",
        "Nước": "Utility",
        "Tiện ích": "Utility",
        # Developer (BĐS phát triển)
        "BĐS": "Developer",
        "BĐS phát triển": "Developer",
        "Bất động sản": "Developer",
        "KCN": "Developer",     # Khu CN → BĐS hạ tầng
    }
    business_nature = _SECTOR_TO_NATURE.get(group, "Unknown")
    
    # Overrides cứng cho mã đặc thù (business nature khác sector chung)
    _TICKER_OVERRIDES = {
        "FPT": "Compounder",
        "HPG": "Cyclical",
        "MWG": "Retail",
        "NT2": "Utility",
        "KDH": "Developer",
    }
    business_nature = _TICKER_OVERRIDES.get(ticker.upper(), business_nature)
        
    return {
        "ticker": ticker.upper(),
        "method": method,
        "engine": METHOD_ENGINE.get(method, "dcf"),
        "status": METHOD_STATUS.get(method, "NOT_IMPLEMENTED"),
        "group": group,
        "weight": data.get("weight_primary", 1.0),
        "verified": bool(data.get("verified")),
        "raw_main": data.get("raw_primary"),
        "business_nature": business_nature,
        "primary_method": data.get("primary"),
        "secondary_method_1": data.get("secondary"),
        "secondary_method_2": None
    }


def is_supported(ticker: str) -> bool:
    """True nếu phương pháp của mã đã IMPLEMENTED (định giá vững, không proxy)."""
    r = route(ticker)
    return bool(r and r["status"] == "IMPLEMENTED")


def get_valuation_route(db, ticker: str) -> Tuple[str, str]:
    """Shim cũ: trả (engine_type, method_canonical)."""
    r = route(ticker)
    if r:
        return r["engine"], r["method"]
    return "dcf", "DCF"
