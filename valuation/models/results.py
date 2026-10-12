"""
Valuation results model — Định nghĩa cấu trúc kết quả đầu ra đồng bộ cho mọi mô hình định giá.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ValuationResult(BaseModel):
    ticker: str
    engine_type: str = Field(..., description="Loại engine định giá: 'dcf' hoặc 'bank'")
    base_year: int = Field(..., description="Năm cơ sở dùng để định giá")
    base_year_mode: str = Field(..., description="Chế độ năm cơ sở: 'TTM' hoặc 'FY'")
    
    # Kết quả chi tiết
    fair_value_intrinsic: float = Field(..., description="Giá trị hợp lý phương pháp nội tại (DCF hoặc RI) (VND)")
    fair_value_relative: float = Field(..., description="Giá trị hợp lý phương pháp so sánh (Multiples hoặc P/B) (VND)")
    blended_fair_value: float = Field(..., description="Giá trị hợp lý pha trộn (VND)")
    
    current_price: float = Field(..., description="Giá thị trường hiện tại (VND)")
    upside: float = Field(..., description="Tỷ lệ tăng trưởng kỳ vọng (%)")
    recommendation: str = Field(..., description="Khuyến nghị đầu tư: 'MUA', 'HOLD', 'BÁN'")
    
    # Tham số định giá chính
    coe: float = Field(..., description="Chi phí vốn cổ phần COE (%)")
    wacc: Optional[float] = Field(None, description="Chi phí sử dụng vốn bình quân WACC (%)")
    terminal_g: float = Field(..., description="Tăng trưởng vĩnh viễn g (%)")
    
    # Dự phóng chi tiết
    projections: List[Dict[str, Any]] = Field(..., description="Danh sách dự phóng 3 dòng BCTC 5 năm tiếp theo")
    
    # Phân tích kịch bản
    scenarios: Dict[str, float] = Field(..., description="Kết quả định giá blended theo kịch bản: Bull, Base, Bear")
    
    # Phân tích độ nhạy
    sensitivity_x: List[float] = Field(..., description="Trục X độ nhạy: WACC hoặc Re (%)")
    sensitivity_y: List[float] = Field(..., description="Trục Y độ nhạy: g (%)")
    sensitivity_matrix: List[List[float]] = Field(..., description="Ma trận độ nhạy 2 chiều của blended fair value")

    # Flag kiểm định
    flags: List[str] = Field(default_factory=list, description="Danh sách các cờ QC/Sanity check")
