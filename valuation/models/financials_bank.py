"""
Financial bank models — Các mô hình Pydantic v2 validate dữ liệu tài chính cho nhóm Ngân hàng/Tài chính.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from valuation.models.financials import GovernanceData

class BankQualityMetrics(BaseModel):
    roe: float = Field(0.0, description="Return on Equity")
    roa: float = Field(0.0, description="Return on Assets")
    npl_ratio: float = Field(0.0, description="Tỷ lệ nợ xấu (NPL)")
    llrc: float = Field(0.0, description="Tỷ lệ bao phủ nợ xấu (LLRC)")

class IncomeStatementBank(BaseModel):
    year: int
    net_interest_income: float = Field(..., description="Thu nhập lãi thuần (tỷ đồng)")
    non_interest_income: float = Field(..., description="Thu nhập ngoài lãi (tỷ đồng)")
    total_operating_income: float = Field(..., description="Tổng thu nhập hoạt động TOI (tỷ đồng)")
    operating_expenses: float = Field(..., description="Chi phí hoạt động (tỷ đồng)")
    pre_provision_profit: float = Field(..., description="Lợi nhuận trước trích lập dự phòng PPOP (tỷ đồng)")
    provision_expense: float = Field(..., description="Chi phí dự phòng rủi ro tín dụng (tỷ đồng)")
    pretax_income: float = Field(..., description="Lợi nhuận trước thuế LNTT (tỷ đồng)")
    net_income: float = Field(..., description="Lợi nhuận sau thuế LNST (tỷ đồng)")

class BalanceSheetBank(BaseModel):
    year: int
    customer_loans: float = Field(..., description="Cho vay khách hàng (tỷ đồng)")
    other_earning_assets: float = Field(..., description="Tài sản sinh lời khác (tỷ đồng)")
    total_assets: float = Field(..., description="Tổng tài sản (tỷ đồng)")
    customer_deposits: float = Field(..., description="Tiền gửi của khách hàng (tỷ đồng)")
    other_liabilities: float = Field(..., description="Nợ phải trả khác (tỷ đồng)")
    total_equity: float = Field(..., description="Vốn chủ sở hữu (tỷ đồng)")

    @property
    def parent_equity(self) -> float:
        # ponytail: chưa tách CĐKKS cho ngân hàng (thường < 2% vốn); tách khi có mã NH có CĐKKS lớn
        return self.total_equity

    @property
    def earning_assets(self) -> float:
        return self.customer_loans + self.other_earning_assets

    @property
    def total_liabilities_and_equity(self) -> float:
        return self.customer_deposits + self.other_liabilities + self.total_equity

class AssumptionsBank(BaseModel):
    # Chi phí vốn cổ phần (COE)
    risk_free_rate: float = Field(0.03, description="Lợi suất phi rủi ro")
    beta: float = Field(1.0, description="Hệ số Beta")
    erp: float = Field(0.045, description="Mature-market ERP (VND-base: rf=TPCP_VN đã chứa CRP)")
    cost_of_equity: Optional[float] = Field(None, description="Chi phí vốn cổ phần Re (nếu tự nhập)")
    
    # Dự phóng hoạt động ngân hàng (5 năm)
    credit_growth: List[float] = Field(..., description="Tốc độ tăng trưởng tín dụng 5 năm")
    nim: List[float] = Field(..., description="Biên lãi thuần (NIM) 5 năm")
    cir: List[float] = Field(..., description="Tỷ lệ Chi phí / Thu nhập TOI (CIR) 5 năm")
    credit_cost: List[float] = Field(..., description="Chi phí dự phòng / Dư nợ bình quân (Credit Cost) 5 năm")
    deposit_growth: List[float] = Field(default_factory=lambda: [0.12, 0.12, 0.12, 0.12, 0.12], description="Tốc độ tăng trưởng tiền gửi 5 năm")
    
    # Thuế TNDN (dùng trong forecast_bank để tính NI = PBT × (1 - tax_rate))
    tax_rate: float = Field(0.20, description="Thuế suất TNDN hiệu dụng")

    # Phân phối lợi nhuận
    dividend_payout_ratio: float = Field(0.15, description="Tỷ lệ chi trả cổ tức")

    # Giả định vĩnh viễn
    terminal_growth_rate: float = Field(0.02, description="Tăng trưởng vĩnh viễn g")
    sustainable_roe: Optional[float] = Field(None, description="ROE bền vững dài hạn")
    industry_roe: float | None = Field(
        None, description="ROE trung bình ngành — đích hội tụ của ROE terminal (None = không hội tụ)"
    )
    roe_convergence: float = Field(
        0.0, description="λ: ROE terminal = ROE bền vững + λ·(ROE ngành − ROE bền vững); 0 = không hội tụ"
    )
    min_equity_to_assets: Optional[float] = Field(
        None, description="Sàn VCSH/Tổng tài sản (trung vị 3 năm của chính NH) — ràng buộc vốn cho dự phóng"
    )
    historical_pb_median: Optional[float] = Field(
        None, description="P/B trung vị các cuối năm gần nhất của chính mã — chân so sánh thị trường"
    )

    # Ảnh chụp driver LN máy đặt (credit_growth/nim/cir/credit_cost) lúc dựng giả định: dòng cân phai ROE tính
    # từ driver gốc, phần analyst/kịch bản sửa cộng thẳng vào LN (forecast_bank, r4a). None = driver hiện tại.
    driver_base: dict[str, list[float]] | None = Field(
        None, description="Driver LN gốc (máy đặt) — phần chênh do analyst sửa cộng lên đường đã phai ROE"
    )

    # Trọng số định giá
    weight_ri: float = Field(0.5, description="Trọng số Residual Income")

class CompanyBank(BaseModel):
    ticker: str
    name: str
    sector: str = "Banks"
    current_price: float = Field(..., description="Giá thị trường hiện tại (VND)")
    shares_outstanding: float = Field(..., description="Số lượng cổ phiếu lưu hành (triệu cổ phiếu)")
    
    historical_is: List[IncomeStatementBank]
    historical_bs: List[BalanceSheetBank]
    assumptions: AssumptionsBank
    
    governance: Optional[GovernanceData] = Field(default_factory=GovernanceData)
    quality_metrics: Optional[BankQualityMetrics] = Field(default_factory=BankQualityMetrics)

    warnings: List[str] = Field(default_factory=list)
    # Cờ độ tươi dữ liệu (STALE_PRICE/STALE_MACRO_RF...) do freshness gate gắn.
    data_flags: List[str] = Field(default_factory=list)
    last_period_is_ttm: bool = Field(
        False,
        description="Kỳ cuối là TTM chưa trọn năm tài chính (mode TTM, quý cuối < 4) — chồng quý năm trước, "
        "loại khỏi cửa sổ năm tài chính đầy đủ (ROE ngành). Quý cuối = 4 thì kỳ cuối là FY đủ 4 quý.",
    )

    @model_validator(mode="after")
    def validate_bank_balance_sheet(self) -> 'CompanyBank':
        warnings = []
        for bs in self.historical_bs:
            # Kiểm tra cân đối kế toán: Tổng tài sản vs Tổng nguồn vốn
            diff = abs(bs.total_assets - bs.total_liabilities_and_equity)
            if diff > 0.05:  # Lệch quá 50 triệu VND (0.05 tỷ)
                warnings.append(
                    f"Năm {bs.year}: BCTC Ngân hàng không cân đối! "
                    f"Tổng tài sản ({bs.total_assets:.3f}) lệch so với Tổng nguồn vốn ({bs.total_liabilities_and_equity:.3f}) "
                    f"một khoảng {diff:.3f} tỷ đồng."
                )
        self.warnings.extend(warnings)
        return self
