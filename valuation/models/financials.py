"""
Financial models — Các mô hình Pydantic v2 để validate dữ liệu tài chính cho doanh nghiệp phi tài chính.
"""
from typing import Any, List, Dict, Optional
from pydantic import BaseModel, Field, model_validator


def _proxy_cfg() -> dict:
    from valuation.config import load_defaults

    return load_defaults()["proxy_valuation"]


class GovernanceData(BaseModel):
    audit_issue: bool = Field(False, description="Có vấn đề ngoại trừ từ kiểm toán không")
    legal_issue: bool = Field(False, description="Có rủi ro pháp lý nghiêm trọng không")
    liquidity_issue: bool = Field(False, description="Có rủi ro thanh khoản không")
    analyst_owner: str = Field("System", description="Người phân tích")
    reviewer: str = Field("System", description="Người phê duyệt")
    version_tag: str = Field("v1.0", description="Phiên bản định giá")

class QualityMetrics(BaseModel):
    roe: float = Field(0.0, description="Return on Equity")
    roic: float = Field(0.0, description="Return on Invested Capital")
    debt_to_equity: float = Field(0.0, description="Tỷ lệ nợ trên vốn chủ sở hữu")
    net_debt_to_ebitda: float = Field(0.0, description="Tỷ lệ nợ ròng trên EBITDA")

class IncomeStatement(BaseModel):
    year: int
    revenue: float = Field(..., description="Doanh thu thuần (tỷ đồng)")
    cogs: float = Field(..., description="Giá vốn hàng bán (tỷ đồng)")
    gross_profit: float = Field(..., description="Lợi nhuận gộp (tỷ đồng)")
    opex: float = Field(..., description="Chi phí hoạt động (bán hàng + QLDN) (tỷ đồng)")
    ebit: float = Field(..., description="Lợi nhuận trước lãi vay và thuế (tỷ đồng)")
    interest_expense: float = Field(..., description="Chi phí lãi vay (tỷ đồng)")
    tax: float = Field(..., description="Chi phí thuế TNDN (tỷ đồng); âm = lợi ích thuế ròng (hoãn lại)")
    net_income: float = Field(..., description="Lợi nhuận sau thuế (tỷ đồng)")
    jv_income: float = Field(
        0.0, description="Lãi/lỗ từ công ty liên doanh, liên kết (tỷ đồng) — nằm ngoài EBIT"
    )
    pbt: float | None = Field(
        None, description="Tổng LN kế toán trước thuế báo cáo (mã 50, tỷ đồng); None = nguồn không có dòng"
    )

class BalanceSheet(BaseModel):
    year: int
    reported_total_liabilities: Optional[float] = Field(None, description="Tổng nợ phải trả từ BCTC, không phải số dư ép cân đối (tỷ đồng)")
    cash_and_equivalents: float = Field(..., description="Tiền và tương đương tiền (tỷ đồng)")
    short_term_financial_investments: float = Field(
        0.0, description="Đầu tư tài chính ngắn hạn có thể dùng trong cầu nối EV (tỷ đồng)"
    )
    receivables: float = Field(..., description="Phải thu khách hàng (tỷ đồng)")
    inventory: float = Field(..., description="Hàng tồn kho (tỷ đồng)")
    other_current_assets: float = Field(
        ..., description="Tài sản ngắn hạn − tiền − phải thu − tồn kho (tỷ đồng); GỒM cả đầu tư ngắn hạn"
    )
    fixed_assets: float = Field(..., description="Tài sản cố định ròng (tỷ đồng)")
    other_long_term_assets: float = Field(
        ..., description="Tài sản dài hạn − TSCĐ (tỷ đồng); GỒM cả long_term_investments_net"
    )
    total_assets: float = Field(..., description="Tổng tài sản (tỷ đồng)")
    short_term_debt: float = Field(..., description="Nợ vay ngắn hạn (tỷ đồng)")
    accounts_payable: float = Field(..., description="Phải trả người bán (tỷ đồng)")
    other_current_liabilities: float = Field(..., description="Nợ ngắn hạn khác (tỷ đồng)")
    long_term_debt: float = Field(..., description="Nợ vay dài hạn (tỷ đồng)")
    other_long_term_liabilities: float = Field(..., description="Nợ dài hạn khác (tỷ đồng)")
    total_equity: float = Field(..., description="Vốn chủ sở hữu (tỷ đồng)")
    minority_interest: float = Field(
        0.0, description="Lợi ích cổ đông không kiểm soát (tỷ đồng)"
    )
    long_term_investments_net: float = Field(
        0.0,
        description=(
            "Đầu tư tài chính dài hạn ròng (mã 250: liên kết, liên doanh, dài hạn khác, "
            "HTM dài hạn, trừ dự phòng) — tài sản ngoài hoạt động cho cầu nối EV (tỷ đồng)"
        ),
    )
    investments_in_associates: float = Field(
        0.0,
        description="Đầu tư vào liên doanh, liên kết theo sổ sách (tỷ đồng) — một phần của long_term_investments_net",
    )
    construction_in_progress: float = Field(
        0.0,
        description=(
            "Chi phí XDCB dở dang (mã 242, tỷ đồng) — một phần của other_long_term_assets; chưa tạo "
            "doanh thu/EBITDA nên định giá theo sổ sách ở cầu nối EV (NPV = 0), không thuộc vốn vận hành"
        ),
    )
    investment_property: float = Field(
        0.0,
        description=(
            "Bất động sản đầu tư ròng (dòng investment_properties, tỷ đồng) — một phần của "
            "other_long_term_assets; tài sản có giá thị trường khác giá sổ (cơ sở đánh giá lại RNAV)"
        ),
    )
    deferred_revenue: float = Field(
        0.0,
        description=(
            "Doanh thu chưa thực hiện ngắn + dài hạn (mã 318 + 336, tỷ đồng) — nợ vận hành (tiền thuê "
            "trả trước của KCN...), một phần của other_*_liabilities; Δ của nó là dòng tiền trong vốn lưu động"
        ),
    )

    @property
    def parent_equity(self) -> float:
        """VAS: vốn chủ sở hữu (mã 400) đã gồm lợi ích CĐKKS (mã 429)."""
        return self.total_equity - self.minority_interest

    @property
    def total_liabilities(self) -> float:
        if self.reported_total_liabilities is not None:
            return self.reported_total_liabilities
        return (self.short_term_debt + self.accounts_payable + self.other_current_liabilities +
                self.long_term_debt + self.other_long_term_liabilities)

    @property
    def total_liabilities_and_equity(self) -> float:
        return self.total_liabilities + self.total_equity

class CashFlow(BaseModel):
    year: int
    cfo: float = Field(..., description="Dòng tiền từ hoạt động kinh doanh (tỷ đồng)")
    capex: float = Field(..., description="Chi phí đầu tư tài sản cố định (tỷ đồng)")
    depreciation: float = Field(0.0, description="Khấu hao & phân bổ (D&A) trong kỳ (tỷ đồng)")
    dividends_paid: float = Field(0.0, description="Cổ tức, lợi nhuận đã trả (trị tuyệt đối, tỷ đồng)")
    cf_other: float = Field(0.0, description="Dòng tiền đầu tư/tài chính khác (tỷ đồng), đã cộng ngược CapEx — xem repo.py::_cashflow_other_excluding_capex")
    has_full_cashflow_sections: bool = Field(
        True,
        description=(
            "CFI và CFF khớp được taxonomy nguồn hay không. False nghĩa là "
            "cf_other=0.0 vì THIẾU dữ liệu, không phải vì thực sự bằng 0 — "
            "dùng để phân biệt 'thiếu dữ liệu' với 'lệch đối chiếu thật' "
            "trong Company.validate_model_integrity."
        ),
    )
    is_ttm_period: bool = Field(
        False,
        description=(
            "Kỳ TTM (4 quý gần nhất, cho năm gần nhất khi mode=TTM). Δtiền đo "
            "giữa 2 mốc bảng cân đối có thể không cùng độ dài kỳ với dòng tiền "
            "cộng dồn 4 quý (vd BS mới nhất chỉ cách BS trước 2 quý) — không "
            "đối chiếu chặt danh mục này để tránh báo sai do thiết kế."
        ),
    )

class Assumptions(BaseModel):
    # Chi phí vốn (COE)
    risk_free_rate: float = Field(0.03, description="Lợi suất phi rủi ro")
    beta: float = Field(1.0, description="Hệ số Beta")
    erp: float = Field(0.045, description="Mature-market ERP (VND-base: rf=TPCP_VN đã chứa CRP)")
    cost_of_equity: Optional[float] = Field(None, description="Chi phí vốn cổ phần (nếu tự nhập)")
    wacc_override: Optional[float] = Field(None, description="WACC ghi đè trực tiếp (ma trận độ nhạy)")
    historical_pb_median: Optional[float] = Field(
        None, description="P/B trung vị các cuối năm gần nhất của chính mã (chân thị trường CTCK/bảo hiểm)"
    )
    
    # Cơ cấu vốn & Nợ
    cost_of_debt: float = Field(0.06, description="Chi phí nợ vay trước thuế")
    tax_rate: float = Field(0.20, description="Thuế suất TNDN hiệu dụng — giai đoạn dự phóng năm 1–5")
    terminal_tax_rate: float | None = Field(
        None,
        description="Thuế suất biên vĩnh viễn cho NOPAT terminal và lá chắn thuế nợ trong WACC; "
        "None = theo config (dcf.terminal_tax_mode / sector_tax_rates.default)",
    )
    debt_ratio: Optional[float] = Field(None, description="Tỷ lệ nợ/tổng nguồn vốn (nếu cố định)")

    # Giả định dự phóng (5 năm tiếp theo)
    revenue_growth: List[float] = Field(..., description="Tốc độ tăng trưởng doanh thu 5 năm")
    ebit_margin: List[float] = Field(..., description="Biên EBIT 5 năm")
    mid_cycle_ebit_margin: Optional[float] = Field(None, description="Biên EBIT mid-cycle cho terminal (ngành cyclical); None nếu không cyclical")
    capex_to_revenue: List[float] = Field(..., description="CapEx/Doanh thu 5 năm")
    depr_to_revenue: List[float] = Field(..., description="Khấu hao/Doanh thu 5 năm")
    
    # Working Capital Schedule (3 vòng quay)
    dso: List[float] = Field(..., description="Days Sales Outstanding (Số ngày phải thu)")
    dio: List[float] = Field(..., description="Days Inventory Outstanding (Số ngày tồn kho)")
    dpo: List[float] = Field(..., description="Days Payable Outstanding (Số ngày phải trả)")
    deferred_revenue_to_revenue: float = Field(
        0.0, description="ΔDoanh thu chưa thực hiện / ΔDT (tỷ lệ biên, cửa sổ margin_window_years) — nợ vận hành trừ khỏi NWC"
    )

    # Debt Schedule
    interest_rate: List[float] = Field(..., description="Lãi suất vay trung bình (%)")
    debt_repayment_rate: List[float] = Field(
        default_factory=lambda: [0.20] * 5,
        description="Tỷ lệ trả nợ gốc hàng năm (% trên tổng nợ đầu kỳ)"
    )
    new_borrowing_rate: List[float] = Field(
        default_factory=lambda: [0.05] * 5,
        description="Tỷ lệ vay mới hàng năm (% trên doanh thu dự phóng)"
    )
    
    # Giả định vĩnh viễn
    terminal_growth_rate: float = Field(0.02, description="Tăng trưởng vĩnh viễn g")
    roic_terminal: Optional[float] = Field(None, description="ROIC vĩnh viễn")
    
    # Định giá so sánh & Pha trộn
    target_ev_ebitda: float = Field(8.0, description="EV/EBITDA mục tiêu")
    target_pe: Optional[float] = Field(
        None, description="P/E mục tiêu = trung vị lịch sử của chính mã; None → hằng số ngành"
    )
    sales_to_capital: Optional[float] = Field(
        None,
        description="Doanh thu / vốn đầu tư vận hành dùng dựng CapEx mặc định (D45); None → CapEx/DT lịch sử",
    )
    weight_dcf: float = Field(0.5, description="Trọng số DCF")
    
    # RNAV & SOTP
    # Một nguồn sự thật: mặc định đọc config proxy_valuation (trước đây số Pydantic che config).
    rnav_revaluation_premium: float = Field(
        default_factory=lambda: float(_proxy_cfg()["rnav_land_premium"]),
        description="Premium đánh giá lại tồn kho + BĐS đầu tư so giá sổ (proxy RNAV) — mặc định config",
    )
    rnav_wacc: float | None = Field(
        None, description="Suất chiết khấu dòng tiền dự án RNAV; None → mặc định config (WACC: dòng tiền chưa trừ nợ)"
    )
    rnav_discount: float = Field(
        default_factory=lambda: float(_proxy_cfg()["rnav_discount"]),
        description="Chiết khấu áp lên PHẦN ĐÁNH GIÁ LẠI (không áp lên VCSH sổ sách) — mặc định config",
    )
    sotp_discount: float = Field(
        default_factory=lambda: float(_proxy_cfg()["sotp_holding_discount"]),
        description="Tỷ lệ chiết khấu holding (SOTP) — mặc định từ config proxy_valuation.sotp_holding_discount",
    )
    sotp_holdings: dict[str, Any] | None = Field(
        None,
        description=(
            "Cổ phần niêm yết đã định giá theo thị giá (config/sotp_holdings.yaml, repo.resolve_sotp_holdings); "
            "None → không khai báo"
        ),
    )
    rnav_projects: Optional[List[Dict]] = Field(default_factory=list, description="Danh sách dự án BĐS do AI bóc tách")
    sotp_segments: Optional[List[Dict]] = Field(default_factory=list, description="Danh sách mảng kinh doanh SOTP do AI bóc tách")
    ai_inputs_verified: bool = Field(
        False, description="Analyst đã đối chiếu dự án/mảng AI bóc tách với nguồn chính thức"
    )

    # Land Bank Add-on — giá trị quỹ đất (cao su, KCN, nông nghiệp...) CHƯA phản
    # ánh trong BCTC (đất ghi nhận theo giá gốc, không phải giá thị trường/đền
    # bù). Cộng thêm vào fair value CHÍNH (bất kể phương pháp DCF/EV_EBITDA/PE)
    # — KHÔNG thay method. Mặc định RỖNG: analyst phải tự nhập diện tích/giá
    # đền bù từ báo cáo thật (AGENTS.md — không bịa số liệu).
    # Mỗi dict: {ten, dien_tich_ha, gia_boi_thuong_vnd_m2, ty_le_so_huu, nam_thu_tien}
    land_bank_projects: Optional[List[Dict]] = Field(
        default_factory=list,
        description="Quỹ đất chưa phản ánh trong BCTC (ha, giá đền bù/m2, tỷ lệ sở hữu, năm dự kiến thu tiền)"
    )

class Company(BaseModel):
    ticker: str
    name: str
    sector: str
    current_price: float = Field(..., description="Giá thị trường hiện tại (VND)")
    shares_outstanding: float = Field(..., description="Số lượng cổ phiếu lưu hành (triệu cổ phiếu)")
    
    historical_is: List[IncomeStatement]
    historical_bs: List[BalanceSheet]
    historical_cf: List[CashFlow]
    assumptions: Assumptions
    
    governance: Optional[GovernanceData] = Field(default_factory=GovernanceData)
    quality_metrics: Optional[QualityMetrics] = Field(default_factory=QualityMetrics)

    warnings: List[str] = Field(default_factory=list)
    # Cờ độ tươi dữ liệu (STALE_PRICE/STALE_MACRO_RF...) do freshness gate gắn
    # khi build từ DB — valuate() sẽ trộn vào flags kết quả.
    data_flags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_model_integrity(self) -> 'Company':
        warnings = []
        for bs in self.historical_bs:
            # Kiểm tra cân đối kế toán: Tổng tài sản vs Tổng nguồn vốn
            diff = abs(bs.total_assets - bs.total_liabilities_and_equity)
            if diff > 0.01:  # Lệch quá 10 triệu VND (0.01 tỷ)
                warnings.append(
                    f"Năm {bs.year}: Bảng cân đối kế toán không cân đối! "
                    f"Tổng tài sản ({bs.total_assets:.3f}) lệch so với Tổng nguồn vốn ({bs.total_liabilities_and_equity:.3f}) "
                    f"một khoảng {diff:.3f} tỷ đồng."
                )
                
        # Cash Flow Check — đối chiếu Δtiền = CFO - CapEx + cf_other.
        # Tách 2 loại thay vì gộp chung như trước (xem
        # docs/PLAN_FIX_CASHFLOW_WARNINGS.md và skill financial-data-integrity
        # mục "Lỗi đã gặp thực tế"):
        #   (A) THIẾU dữ liệu CFI/CFF (has_full_cashflow_sections=False) → gộp
        #       tất cả năm thiếu vào MỘT dòng, không lặp theo năm.
        #   (B) ĐỦ dữ liệu nhưng lệch đối chiếu vượt ngưỡng tương đối → dòng
        #       riêng nêu số cụ thể. Ngưỡng lấy từ config, không hardcode.
        #   Năm TTM (is_ttm_period=True) không đối chiếu chặt vì Δtiền so BS
        #   không cùng độ dài kỳ với dòng tiền cộng dồn 4 quý.
        from valuation.config import get_cash_reconciliation_tolerance

        tol = get_cash_reconciliation_tolerance()
        abs_tol = float(tol["abs_tolerance_billion_vnd"])
        pct_assets_tol = float(tol["pct_total_assets_tolerance"]) / 100.0
        pct_delta_tol = float(tol["pct_delta_cash_tolerance"]) / 100.0

        missing_years: List[int] = []
        for i in range(1, len(self.historical_bs)):
            prev_bs = self.historical_bs[i-1]
            curr_bs = self.historical_bs[i]
            
            cf_match = [cf for cf in self.historical_cf if cf.year == curr_bs.year]
            if not cf_match:
                continue
            curr_cf = cf_match[0]

            if not curr_cf.has_full_cashflow_sections:
                missing_years.append(curr_cf.year)
                continue
            if curr_cf.is_ttm_period:
                continue

            delta_cash = curr_bs.cash_and_equivalents - prev_bs.cash_and_equivalents
            total_cf = curr_cf.cfo - curr_cf.capex + curr_cf.cf_other
            diff_cash = abs(delta_cash - total_cf)

            threshold = max(
                abs_tol,
                pct_assets_tol * curr_bs.total_assets,
                pct_delta_tol * abs(delta_cash),
            )
            if diff_cash > threshold:
                warnings.append(
                    f"Năm {curr_cf.year}: Δtiền {delta_cash:,.1f} tỷ vs "
                    f"CFO-CapEx+khác {total_cf:,.1f} tỷ (lệch {diff_cash:,.1f} "
                    "tỷ đồng, vượt ngưỡng đối chiếu) — cần kiểm tra lại nguồn."
                )

        if missing_years:
            years_str = ", ".join(str(y) for y in missing_years)
            warnings.append(
                f"Thiếu lưu chuyển đầu tư/tài chính: {years_str} "
                f"({len(missing_years)} năm) — không tự tạo khoản bù."
            )

        self.warnings = list(dict.fromkeys(self.warnings + warnings))
        return self
