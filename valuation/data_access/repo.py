"""
Repository module — Truy vấn dữ liệu tài chính từ PostgreSQL, chuẩn hóa đơn vị và kỳ báo cáo.
"""

import math
from typing import Any, Dict, List, Tuple, Union, overload

import pandas as pd
from sqlalchemy.orm import Session

from valuation.data_access.periodize import (
    periodize_quarters_to_annual,
)
from valuation.config import load_defaults
from valuation.data_access.units import to_billion_vnd
from valuation.db.models import CorporateAction, FinancialsQuarterly, PricesDaily, Ticker
from valuation.engine.ttm_helper import estimate_vcb_beta, get_latest_tpcp_10y, undated_split_flags
from valuation.models.financials import (
    Assumptions,
    BalanceSheet,
    CashFlow,
    Company,
    IncomeStatement,
)
from valuation.models.financials_bank import (
    AssumptionsBank,
    BalanceSheetBank,
    CompanyBank,
    IncomeStatementBank,
)

# Từ khóa matching cho Phi tài chính
NON_FIN_KEYWORDS = {
    "revenue": [
        "net_revenue_from_goods_and_services_rendered",
        "net_sales",
        "net_sales_from_insurance_business",
        "Doanh thu thuần",
        "Doanh thu hoạt động",
    ],
    "cogs": [
        "cost_of_goods_sold",
        "cost_of_sales",
        "cogs",
        "Giá vốn hàng bán",
        "Chi phí hoạt động tự doanh",
    ],
    "gross_profit": ["gross_profit", "Lợi nhuận gộp"],
    # OPEX tách 2 cấu phần để CỘNG (không dùng chung 1 key — xem build_company_data).
    "selling_expenses": ["selling_expenses", "Chi phí bán hàng"],
    "ga_expenses": [
        "general_and_admin_expenses",
        "general_and_administrative_expenses",
        "Chi phí quản lý doanh nghiệp",
        "Chi phí quản lý",
    ],
    "opex_total": ["operating_expenses", "operating_expense", "Chi phí hoạt động"],
    "operating_profit": [
        "operating_profit_loss",
        "Lợi nhuận từ hoạt động kinh doanh",
        "Lợi nhuận thuần từ hoạt động kinh doanh",
    ],
    "interest_expense": [
        "interest_expenses",
        "interests_expenses",
        "interest_expense",
        "Chi phí lãi vay",
    ],
    "tax": [
        "corporate_income_tax_expenses",
        "corporate_income_tax_for_the_year",
        "corporate_income_tax",
        "tax_rate_value",
        "Chi phí thuế TNDN hiện hành",
        "Thuế thu nhập doanh nghiệp",
    ],
    # Mã 50 — mẫu số thuế suất hiệu dụng (gồm thu nhập tài chính/liên doanh/khác cũng chịu thuế).
    "pbt": [
        "net_accounting_profit_loss_before_tax",
        "profit_before_tax",
        "Tổng lợi nhuận kế toán trước thuế",
    ],
    # net_profit_attributable... + profit_after_tax cho ngành bảo hiểm (BVH) — IS bảo
    # hiểm KHÔNG có net_profit_loss_after_tax; nếu thiếu, fallback ebit×0.8 lấy nhầm
    # doanh thu phí (ROE phi lý). Đặt SAU key chuẩn để DN thường vẫn match key đầu.
    # LN của cổ đông công ty mẹ đứng đầu: EPS/P/E/ROE/DDM phải loại phần CĐKKS
    # (CII, DXG, GEX, MSN có LN hợp nhất gấp 1,6-3 lần LN mẹ).
    "net_income": [
        "attributable_to_parent_company",
        "net_profit_loss_after_tax",
        "profit_after_tax",
        "net_profit_attributable_to_shareholders_of_the_group",
        "net_income",
        "Lợi nhuận sau thuế",
    ],
    "cash": ["cash_and_cash_equivalents", "Tiền và các khoản tương đương tiền"],
    "short_term_financial_investments": [
        "short_term_financial_investments",
        "short_term_investments",
        "Đầu tư tài chính ngắn hạn",
    ],
    "receivables": [
        "short_term_trade_receivables",
        "trade_accounts_receivable",
        "short_term_receivables",
        "Phải thu ngắn hạn của khách hàng",
        "Các khoản phải thu",
    ],
    "inventory": ["inventories_net", "inventories", "inventory", "Hàng tồn kho"],
    "fixed_assets": [
        "tangible_fixed_assets",
        "fixed_assets",
        "Tài sản cố định",
        "Tài sản cố định hữu hình",
    ],
    "total_assets": ["total_assets", "Tổng tài sản", "TỔNG TÀI SẢN"],
    "st_debt": [
        "short_term_borrowings",
        "short_term_debt",
        "Vay và nợ thuê tài chính ngắn hạn",
        "Vay ngắn hạn",
    ],
    "lt_debt": [
        "long_term_borrowings",
        "long_term_debt",
        "Vay và nợ thuê tài chính dài hạn",
        "Vay dài hạn",
    ],
    # Trái phiếu chuyển đổi: phần nợ trình bày tách khỏi vay dài hạn (BAF, CII, SBT). Phần quyền
    # chọn chuyển đổi (conversion_options_on_convertible_bonds) là vốn chủ → không cộng.
    "convertible_bonds": ["convertible_bonds", "Trái phiếu chuyển đổi"],
    "accounts_payable": [
        "short_term_trade_payables",
        "trade_accounts_payable",
        "accounts_payable",
        "Phải trả người bán ngắn hạn",
        "Phải trả người bán",
    ],
    "total_equity": [
        "owners_equity",
        "shareholders_equity",
        "capital_and_reserves",
        "Vốn chủ sở hữu",
    ],
    # Mã 250 (tổng): đã gồm liên kết, dài hạn khác, HTM dài hạn và dự phòng — dùng
    # dòng tổng để không cộng trùng các dòng con.
    "long_term_investments": ["long_term_investments", "Đầu tư tài chính dài hạn"],
    "investments_in_associates": [
        "investments_in_associates",
        "investments_in_joint_ventures_and_associates",
        "Đầu tư vào công ty liên doanh, liên kết",
    ],
    # Mã 242 khớp chính xác: KHÔNG dùng long_term_incomplete_assets (mã 240 = 241 + 242; 241 là
    # SXKD dở dang dài hạn — vốn vận hành, vd WIP BĐS) hay construction_in_progress_before_2015.
    "construction_in_progress": ["construction_in_progress", "Chi phí xây dựng cơ bản dở dang"],
    "investment_property": ["investment_properties", "Bất động sản đầu tư"],
    # Doanh thu chưa thực hiện (mã 318 ngắn hạn + 336 dài hạn): nợ vận hành, tiền khách trả trước.
    "deferred_revenue_st": ["short_term_unrealized_revenue", "Doanh thu chưa thực hiện ngắn hạn"],
    "deferred_revenue_lt": ["deferred_revenue", "Doanh thu chưa thực hiện dài hạn"],
    "jv_income": [
        "gain_loss_from_joint_ventures_from_2015",
        "gain_loss_from_joint_ventures",
        "shares_of_the_profit_of_associates_and_joint_ventures",
        "Lãi/lỗ trong công ty liên doanh, liên kết",
    ],
    "minority_interest": [
        "minority_interests",
        "minority_interest",
        "Lợi ích cổ đông không kiểm soát",
    ],
    "cfo": [
        "net_cash_inflows_outflows_from_operating_activities",
        "net_cash_flows_from_operating_activities",
        "cfo",
        "Lưu chuyển tiền thuần từ hoạt động kinh doanh",
    ],
    "cfi": [
        "net_cash_inflows_outflows_from_investing_activities",
        "net_cash_from_investing_activities",
        "Lưu chuyển tiền thuần từ hoạt động đầu tư",
    ],
    "cff": [
        "net_cash_inflows_outflows_from_financing_activities",
        "net_cash_from_financing_activities",
        "Lưu chuyển tiền thuần từ hoạt động tài chính",
    ],
    "fx_effect": [
        "effect_of_foreign_exchange_differences",
        "Ảnh hưởng của thay đổi tỷ giá hối đoái quy đổi ngoại tệ",
    ],
    "capex": [
        "purchases_of_fixed_assets_and_other_long_term_assets",
        "payments_for_purchase_of_fixed_assets",
        "capex",
        "Tiền chi để mua sắm, xây dựng TSCĐ",
    ],
    "dividends_paid": ["dividends_paid", "Cổ tức, lợi nhuận đã trả cho chủ sở hữu"],
    "depreciation": [
        "depreciation_and_amortization",
        "depreciation",
        "Khấu hao tài sản cố định",
        "Khấu hao TSCĐ và BĐSĐT",
    ],
}

# Từ khóa matching cho Ngân hàng.
# Ưu tiên key tiếng Anh (vnstock English line_item) ĐẶT TRƯỚC để match qua
# startswith trước; giữ key tiếng Việt phía sau để tương thích nguồn cũ.
BANK_KEYWORDS = {
    "net_interest_income": [
        "net_interest_income",
        "I. Thu nhập lãi thuần",
        "Thu nhập lãi thuần",
    ],
    "non_interest_income": ["non_interest_income"],  # Tính gián tiếp TOI - NII
    "total_operating_income": [
        "total_operating_income",
        "VIII. Tổng thu nhập hoạt động",
        "Tổng thu nhập hoạt động",
    ],
    "operating_expenses": [
        "general_and_admin_expenses",
        "IX. Chi phí hoạt động",
        "Chi phí hoạt động",
    ],
    "provision_expense": [
        "provision_for_credit_losses",
        "Chi phí dự phòng rủi ro tín dụng",
        "Chi phí dự phòng",
    ],
    "pretax_income": [
        "net_accounting_profit_loss_before_tax",
        "XI. Tổng lợi nhuận trước thuế",
        "Tổng lợi nhuận trước thuế",
    ],
    "net_income": [
        "attributable_to_parent_company",
        "net_profit_loss_after_tax",
        "XIV. Lợi nhuận sau thuế",
        "Lợi nhuận sau thuế",
    ],
    "customer_loans": [
        "loans_and_advances_to_customers_net",
        "loans_and_advances_to_customers",
        "1. Cho vay khách hàng",
    ],
    "customer_deposits": [
        "deposits_from_customers",
        "Tiền gửi của khách hàng",
        "Tiền gửi khách hàng",
    ],
    "total_assets": ["total_assets", "TỔNG TÀI SẢN", "Tổng tài sản"],
    "total_equity": ["owners_equity", "shareholders_equity", "Vốn chủ sở hữu"],
}


def _bounded_bank_credit_growth(
    raw_growth: float, config: Dict[str, Any]
) -> Tuple[float, bool]:
    floor = float(config.get("credit_growth_floor", 0.05))
    cap = float(config.get("credit_growth_cap", 0.25))
    if floor > cap:
        raise ValueError("credit_growth_floor không được lớn hơn credit_growth_cap")
    bounded = min(max(float(raw_growth), floor), cap)
    return bounded, bounded != float(raw_growth)


def _quarterly_revenues(db: Session, ticker: str) -> List[float]:
    """Doanh thu thuần theo TỪNG QUÝ, sắp xếp cũ -> mới (D32).

    Dùng cho động lượng năm gốc dự phóng. Dữ liệu quý vốn đã có sẵn trong DB
    nhưng `build_company_data` chỉ dùng nó để ráp thành năm — thông tin về xu
    hướng gần đây bị mất trong lúc gộp.
    """
    rows = (
        db.query(FinancialsQuarterly)
        .filter(
            FinancialsQuarterly.ticker == ticker, FinancialsQuarterly.statement == "IS"
        )
        .all()
    )
    by_period: Dict[tuple, Dict[str, float]] = {}
    for r in rows:
        if r.fiscal_quarter is None or r.fiscal_quarter == 0:
            continue  # bỏ dòng năm, chỉ lấy quý
        key = (r.fiscal_year, r.fiscal_quarter)
        by_period.setdefault(key, {})[r.line_item] = float(r.value or 0.0)

    out: List[float] = []
    for key in sorted(by_period):
        rev = _match_value(by_period[key], NON_FIN_KEYWORDS["revenue"])
        if rev and rev > 0:
            out.append(rev)
    return out


@overload
def _match_value(data: dict, keywords: List[str], fallback: float = 0.0) -> float: ...


@overload
def _match_value(data: dict, keywords: List[str], fallback: None) -> float | None: ...


def _match_value(
    data: dict, keywords: List[str], fallback: float | None = 0.0
) -> float | None:
    """Chỉ dùng alias chính xác; không bắt nhầm chỉ tiêu tổng/con hoặc legacy."""
    for kw in keywords:
        kw_lower = kw.lower()
        for k, v in data.items():
            if k.lower().strip() == kw_lower:
                if v is not None and pd.notna(v):
                    return float(v)
    return fallback


def _required_value(data: dict, aliases: list[str], field: str) -> float:
    value = _match_value(data, aliases, fallback=None)
    if value is None or not math.isfinite(value):
        raise ValueError(
            f"MISSING_FINANCIAL_INPUT: {field}; thiếu chỉ tiêu hoặc chưa đủ bốn quý"
        )
    return value


def _balance_residuals(
    data: dict,
    *,
    cash: float,
    receivables: float,
    inventory: float,
    fixed: float,
    short_debt: float,
    payable: float,
    long_debt: float,
) -> dict[str, float | None]:
    """Phần còn lại của từng tổng mục báo cáo, không tự phân bổ 50/50."""
    groups = {
        "other_current_assets": (["current_assets"], cash + receivables + inventory),
        "other_long_term_assets": (["long_term_assets", "non_current_assets"], fixed),
        "other_current_liabilities": (["current_liabilities"], short_debt + payable),
        "other_long_term_liabilities": (
            ["long_term_liabilities", "non_current_liabilities"],
            long_debt,
        ),
    }
    result = {}
    for field, (aliases, known) in groups.items():
        subtotal = _match_value(data, aliases, fallback=None)
        result[field] = None if subtotal is None else subtotal - known
    total_liab = _match_value(data, ["liabilities", "total_liabilities"], fallback=None)
    current_liab = _match_value(data, ["current_liabilities"], fallback=None)
    if result["other_long_term_liabilities"] is None and total_liab is not None and current_liab is not None:
        # BCTC bảo hiểm (TT232/2012) không có tổng mục nợ dài hạn; dự phòng nghiệp vụ là mục riêng
        # → suy theo đẳng thức Tổng nợ − Nợ ngắn hạn − vay dài hạn (chỉ hiển thị; P/B không dùng).
        result["other_long_term_liabilities"] = total_liab - current_liab - long_debt
    return result


def _source_audit_flags(
    audit: dict | None, ticker: str, mapping_version: str, records: list | None = None
) -> list[str]:
    """Cờ audit nguồn. `records` (bản ghi DB hợp nhất VND của mã) → so dấu vân tay các kỳ ĐÃ đối
    chiếu: số đã đối chiếu đổi (hoặc audit cũ chưa lưu dấu/tập kỳ) → SOURCE_AUDIT_STALE (chặn);
    kỳ nạp sau audit, nguồn chưa đối chiếu → SOURCE_AUDIT_PARTIAL:<kỳ> (cảnh báo); quá
    audit.max_unaudited_periods kỳ như vậy → SOURCE_AUDIT_STALE:<các kỳ> (chặn)."""
    if not audit:
        return ["SOURCE_AUDIT_MISSING"]
    if audit.get("mapping_version") != mapping_version:
        return ["SOURCE_AUDIT_STALE"]
    row = next(
        (item for item in audit.get("rows", []) if item.get("ticker") == ticker), None
    )
    if not row:
        return ["SOURCE_AUDIT_MISSING"]
    flags: list[str] = []
    if records is not None:
        from valuation.ingest.taxonomy import critical_periods, source_fingerprint

        audited = {(int(y), int(q)) for y, q in row.get("audited_periods") or []}
        if not audited or not row.get("db_fingerprint") or "year_from" not in audit:
            return ["SOURCE_AUDIT_STALE"]
        year_from = int(audit["year_from"])
        if row["db_fingerprint"] != source_fingerprint(records, year_from, audited):
            return ["SOURCE_AUDIT_STALE"]
        pending = [
            f"{y}{'FY' if q == 0 else f'Q{q}'}"
            for y, q in sorted(critical_periods(records, year_from) - audited)
        ]
        if len(pending) > int(load_defaults()["audit"]["max_unaudited_periods"]):
            flags.append("SOURCE_AUDIT_STALE:" + ",".join(pending))
        else:
            flags.extend(f"SOURCE_AUDIT_PARTIAL:{p}" for p in pending)
    if row.get("source_contract_errors", 0):
        flags.append(f"SOURCE_CONTRACT_ERROR:{row['source_contract_errors']}")
    if row.get("FILING_PRECEDENCE", 0):
        # DB đang dùng filing chính thức đã soát xét (restated) khác vendor: thứ tự ưu tiên đúng, chỉ cảnh báo.
        flags.append(f"FILING_PRECEDENCE:{row['FILING_PRECEDENCE']}")
    if row.get("CRITICAL_CONFLICT", 0):
        # F2c: chỉ hạ mức khi ĐÃ ĐO được |ΔFV| ≤ ngưỡng trọng yếu; thiếu số đo → vẫn chặn.
        impact = row.get("critical_fv_impact_pct")
        threshold = float(load_defaults()["audit"]["source_conflict_fv_materiality_pct"])
        immaterial = impact is not None and float(impact) <= threshold
        flags.append(
            f"SOURCE_CONFLICT{'_IMMATERIAL' if immaterial else ''}:{row['CRITICAL_CONFLICT']}"
        )
    return flags


def _nonfinancial_income_values(
    data: dict, *, financial_sector: bool = False
) -> dict[str, float]:
    """Số lịch sử theo alias nguồn, không ước tính lợi nhuận để lấp số thiếu."""
    ni = _required_value(data, NON_FIN_KEYWORDS["net_income"], "net_income")
    rev = _required_value(data, NON_FIN_KEYWORDS["revenue"], "revenue")
    cogs = abs(_match_value(data, NON_FIN_KEYWORDS["cogs"]))
    gp = _match_value(data, NON_FIN_KEYWORDS["gross_profit"], fallback=None)
    selling = abs(_match_value(data, NON_FIN_KEYWORDS["selling_expenses"]))
    ga = _match_value(data, NON_FIN_KEYWORDS["ga_expenses"], fallback=None)
    if financial_sector:
        # CTCK dùng chi phí hoạt động để đối chiếu lợi nhuận gộp; không gọi đây
        # là giá vốn sản xuất. Mô hình P/B không sử dụng EBIT lõi này.
        cost = _match_value(data, NON_FIN_KEYWORDS["opex_total"], fallback=None)
        if cost is not None:
            cogs = abs(cost)
        gp = (
            gp
            if gp is not None
            else _match_value(data, ["gross_insurance_operating_profit"])
        )
    elif _match_value(data, NON_FIN_KEYWORDS["cogs"], fallback=None) is None:
        raise ValueError("MISSING_FINANCIAL_INPUT: cogs")
    if gp is None:
        gp = rev - cogs
    if ga is not None:
        opex = selling + abs(ga)
    else:
        opex = (
            abs(_required_value(data, NON_FIN_KEYWORDS["opex_total"], "opex"))
            if not financial_sector
            else selling
        )
    tax = _match_value(data, NON_FIN_KEYWORDS["tax"], fallback=None)
    if tax is None:
        current_tax = _match_value(data, ["business_income_tax_current"], fallback=None)
        deferred_tax = _match_value(
            data, ["business_income_tax_deferred"], fallback=None
        )
        if current_tax is None and deferred_tax is None:
            if not financial_sector:
                raise ValueError("MISSING_FINANCIAL_INPUT: tax")
            tax = 0.0
        else:
            tax = (current_tax or 0.0) + (deferred_tax or 0.0)
    return {
        "revenue": rev,
        "cogs": cogs,
        "gross_profit": gp,
        "opex": opex,
        "ebit": gp - opex,
        "interest_expense": abs(
            _match_value(data, NON_FIN_KEYWORDS["interest_expense"])
        ),
        # Nguồn (VCI) ghi thuế TNDN theo quy ước âm = chi phí: LNST = LNTT + số nguồn (đã kiểm 19 dòng
        # dương FY2021–2025: BAF, HAG, VPL, CII… đều là lợi ích thuế hoãn lại). Đổi dấu, KHÔNG abs —
        # abs biến lợi ích thuế thành chi phí (BAF 2023: +5,81 tỷ thành chi phí → thuế hiệu dụng 22,7%).
        "tax": -tax,
        "net_income": ni,
    }


def inconsistent_income_year(revenue: float, cogs: float, gross_profit: float) -> bool:
    """DT âm, hoặc |LN gộp − (DT − giá vốn)| vượt identity_tolerance_pct — cùng công thức và
    ngưỡng với kiểm tra GROSS_PROFIT_MISMATCH (verified_summary), trên đơn vị tỷ đồng."""
    from valuation.report.verified_summary import _config, _relative_diff_pct

    tolerance = float(_config()["identity_tolerance_pct"])
    gp, expected = to_billion_vnd(gross_profit), to_billion_vnd(revenue - cogs)
    return revenue < 0 or _relative_diff_pct(gp, expected) > tolerance


def inconsistent_year_droppable(
    year: int, *, latest_year: int, latest_quarter: int, window: int
) -> bool:
    """Năm vi phạm đẳng thức IS chỉ được bỏ khi nằm NGOÀI mọi cửa sổ mô hình: trước năm tài chính
    đầy đủ gần nhất − forecast.margin_window_years (TTM Q2/2026 → FY2025 − 4 = 2021). Năm trong cửa
    sổ (kể cả FY gần nhất) giữ lại để GROSS_PROFIT_MISMATCH nổi lên và chặn công bố."""
    latest_full_fy = latest_year if latest_quarter >= 4 else latest_year - 1
    return year < latest_full_fy - window


def _cashflow_other_excluding_capex(data: dict, capex_abs: float) -> tuple[float, bool]:
    """Phần dòng tiền ngoài CFO và CapEx, dùng để đối chiếu biến động tiền."""
    cfi = _match_value(data, NON_FIN_KEYWORDS["cfi"], fallback=None)
    cff = _match_value(data, NON_FIN_KEYWORDS["cff"], fallback=None)
    fx_effect = _match_value(data, NON_FIN_KEYWORDS["fx_effect"], fallback=0.0)
    has_full_sections = cfi is not None and cff is not None
    if not has_full_sections:
        return 0.0, False
    # CFI đã bao gồm CapEx âm. Model lưu CapEx riêng cho FCFF, nên cộng ngược
    # CapEx vào cf_other để phép check CFO - CapEx + cf_other không trừ hai lần.
    return (cfi or 0.0) + (cff or 0.0) + (fx_effect or 0.0) + capex_abs, True


def get_historical_years(db: Session, ticker: str) -> List[int]:
    """Lấy danh sách các năm có dữ liệu BCTC (bỏ qua năm rỗng)."""
    rows = (
        db.query(FinancialsQuarterly.fiscal_year)
        .filter(FinancialsQuarterly.ticker == ticker)
        .distinct()
        .order_by(FinancialsQuarterly.fiscal_year.asc())
        .all()
    )
    return [r[0] for r in rows if r[0] > 0]


def get_latest_price(db: Session, ticker: str, fetch_live: bool = True, as_of=None) -> float:
    """Lấy giá đóng cửa gần nhất của ticker (VND). Ưu tiên lấy giá live từ vnstock."""
    if fetch_live and as_of is None:
        try:
            from valuation.ingest.vnstock_client import vnstock_client

            live_price = vnstock_client.get_live_price(ticker)
            if live_price > 0:
                return live_price
        except Exception:
            pass

    q = db.query(PricesDaily).filter(PricesDaily.ticker == ticker)
    if as_of is not None:
        q = q.filter(PricesDaily.trade_date <= as_of)
    row = q.order_by(PricesDaily.trade_date.desc()).first()
    return float(row.close) if row and row.close is not None else 0.0


def _published_by(year: int, quarter: int, as_of, lag: Dict[str, Any]) -> bool:
    """Chống lookahead: kỳ BCTC chỉ được dùng khi hạn công bố luật định ≤ as_of."""
    import datetime

    from valuation.engine.ttm_helper import _quarter_end

    end = _quarter_end(year, 4 if quarter == 0 else quarter)
    days = int(lag.get("annual" if quarter == 0 else "quarterly", 90 if quarter == 0 else 30))
    return end + datetime.timedelta(days=days) <= as_of


def load_ticker_metadata(db: Session, ticker: str) -> Ticker:
    """Tải thông tin ngành và sàn giao dịch của ticker."""
    meta = db.query(Ticker).filter(Ticker.ticker == ticker).first()
    if not meta:
        try:
            import json
            import os

            routing_path = os.path.join(
                os.path.dirname(__file__), "..", "config", "routing.json"
            )
            if os.path.exists(routing_path):
                with open(routing_path, "r", encoding="utf-8") as f:
                    routing = json.load(f)
                info = routing.get(ticker, {})
                sector_raw = info.get("sector", "Khác")
                sector_map = {
                    "NH": "Banks",
                    "CK": "Securities",
                    "BH": "Insurance",
                    "BĐS": "Real Estate",
                    "KCN": "Industrial Real Estate",
                    "Thép": "Steel",
                    "Tiêu dùng": "Consumer",
                    "Bán lẻ": "Retail",
                    "Công nghệ": "Technology",
                    "Điện": "Utilities",
                    "Dầu khí": "Oil & Gas",
                    "Hóa chất": "Chemicals",
                }
                sector_name = sector_map.get(sector_raw, sector_raw)
                meta = Ticker(
                    ticker=ticker,
                    company_name=f"Công ty cổ phần {ticker}",
                    exchange="HOSE",
                    sector=sector_name,
                    industry=sector_name,
                )
                db.add(meta)
                db.commit()
                db.refresh(meta)
        except Exception:
            pass
    return meta


def unexplained_current_assets(
    current_assets: float,
    cash: float,
    st_investments: float,
    receivables_total: float,
    inventory: float,
    other_current: float,
) -> bool:
    """B01-DN: TSNH (100) = tiền (110) + ĐTNH (120) + TỔNG phải thu ngắn hạn (130) + tồn kho
    (140) + TSNH khác (150). Chênh bất thường → dòng bị mất khi nạp (FPT từng mất ~31 nghìn tỷ
    tiền gửi; tài sản sinh học TT99/2025 chưa có ID taxonomy). Tính theo phải thu KHÁCH HÀNG
    thì trả trước người bán/phải thu khác (vẫn thuộc 130) bị coi nhầm là "không giải thích"."""
    gap = float(load_defaults()["audit"]["unexplained_current_assets_gap"])
    explained = cash + st_investments + receivables_total + inventory + other_current
    return current_assets > 0 and abs(current_assets - explained) / current_assets > gap


def credit_cost_schedule(
    ttm: float, median: float, spike_multiple: float, years: int = 5
) -> tuple[list[float], bool]:
    """Chi phí tín dụng 5 năm phai tuyến tính từ TTM về trung vị chu kỳ (năm cuối = mức chuẩn hóa),
    đối xứng cả hai chiều — CFA L2 RI nhiều giai đoạn, lợi nhuận chuẩn hóa xuyên chu kỳ (Damodaran).
    Thay luật max(TTM, trung vị) của D47 vốn không bao giờ phản ánh chi phí đang giảm (VPB, CTG).
    TTM > spike_multiple × trung vị coi là trích lập đột biến một lần → giữ trung vị, trả cờ (D47)."""
    from valuation.forecast.base_year import revenue_growth_path

    if median > 0 and ttm > spike_multiple * median:
        return [median] * years, True
    return revenue_growth_path(ttm, median, years), False


def effective_tax_rate(history: list[IncomeStatement], years: int = 3) -> float | None:
    """Σthuế (có dấu: lợi ích thuế âm) / Σ(LNTT − lãi/lỗ liên doanh, liên kết) của `years` năm có thu
    nhập chịu thuế dương gần nhất (Damodaran, Investment Valuation ch.10: effective tax = taxes /
    taxable income). Lãi LD/LK ghi theo phương pháp vốn chủ là phần LỢI NHUẬN SAU THUẾ của bên nhận
    đầu tư, cổ tức nhận về không chịu thuế TNDN lần nữa → loại khỏi mẫu số (để trong mẫu số làm loãng
    thuế suất áp lên EBIT, trong khi liên doanh đã định giá riêng). Gộp Σ/Σ để năm đáy không kéo lệch
    (MWG 2023: 76%); mẫu số EBIT − lãi vay cũ bỏ sót thu nhập tài chính chịu thuế nên chạm trần 25%.
    < 2 năm đủ điều kiện → None (caller fallback). Kẹp dcf.effective_tax_band."""
    rows = [
        i for i in history if i.pbt is not None and i.pbt - i.jv_income > 0
    ][-years:]
    if len(rows) < 2:
        return None
    lo, hi = load_defaults()["dcf"]["effective_tax_band"]
    taxable = sum((i.pbt or 0.0) - i.jv_income for i in rows)
    return min(max(sum(i.tax for i in rows) / taxable, lo), hi)


def sales_to_capital(
    revenue: float,
    equity: float,
    debt: float,
    cash: float,
    st_investments: float,
    lt_investments: float,
    cip: float = 0.0,
) -> float | None:
    """Doanh thu / vốn đầu tư vận hành (Damodaran). Vốn vận hành = VCSH + nợ vay − tiền −
    đầu tư ngắn hạn − đầu tư dài hạn (tài sản ngoài hoạt động) − XDCB dở dang (chưa tạo doanh thu,
    định giá riêng ở cầu nối). ≤ 0 → None; kẹp sàn dải cấu hình, trần None = không kẹp trên."""
    capital = equity + debt - cash - st_investments - lt_investments - cip
    if capital <= 0 or revenue <= 0:
        return None
    lo, hi = load_defaults()["dcf"]["sales_to_capital_band"]
    ratio = max(revenue / capital, lo)
    return ratio if hi is None else min(ratio, hi)


def marginal_deferred_revenue_ratio(
    historical_bs: list[BalanceSheet], historical_is: list[IncomeStatement], window: int
) -> float:
    """ΔDoanh thu chưa thực hiện / ΔDT trên `window` khoảng gần nhất — nợ vận hành trong NWC (Damodaran).
    Tỷ lệ BIÊN thay vì bình quân (Damodaran: marginal working capital khi tỷ lệ đang trôi): SIP DR/DT giảm
    1,88 → 1,54 (2021→TTM) vì DT điện tăng nhanh hơn tiền thuê đất; tỷ lệ bình quân 1,61 cho ΔDR dự phóng
    gấp ~2 lịch sử, tỷ lệ biên 0,98 khớp lịch sử. DT không tăng trên cửa sổ → 0 (= hành vi cũ)."""
    pts = list(zip(historical_bs, historical_is))[-(window + 1):]
    d_rev = pts[-1][1].revenue - pts[0][1].revenue if len(pts) >= 2 else 0.0
    return (pts[-1][0].deferred_revenue - pts[0][0].deferred_revenue) / d_rev if d_rev > 0 else 0.0


def growth_consistent_capex(
    growth: list[float], depr_ratio: float, nwc_ratio: float, s2c: float
) -> list[float]:
    """CapEx/DT từng năm sao cho tái đầu tư ròng = Δdoanh thu / (doanh thu trên vốn):
    CapEx = khấu hao + ΔDT × (1/s2c − vốn lưu động/DT) (vốn vận hành đã gồm vốn lưu động).
    Sàn = khấu hao: CapEx duy trì không thấp hơn hao mòn, kể cả năm doanh thu giảm."""
    return [
        max(depr_ratio, depr_ratio + g / (1 + g) * (1 / s2c - nwc_ratio)) for g in growth
    ]


def capital_raise_cutoff(db: Session, ticker: str, ref_date) -> Any:
    """Ngày hoàn tất muộn nhất của đợt phát hành CÓ THU TIỀN (quyền mua: ngày niêm yết, thiếu thì GDKHQ; riêng lẻ:
    ex_right_date) có GDKHQ ≤ ref_date và tỷ lệ ≥ relative_multiples.capital_raise_min_ratio (tỷ lệ 0/thiếu = chưa
    rõ → coi là trọng yếu). Quan sát cuối kỳ trước ngày này: giá × số cp hiện tại gồm tiền/cp mới mà VCSH/LN chưa
    có → bội số phình. None = không có đợt nào.
    shortcut: as_of quá khứ không quy đợt quyền mua GDKHQ trong (as_of, ngày giá cuối] (giá đã điều chỉnh lùi, số
    cp chưa tăng → bội số thấp đi) — cần chuỗi giá thô nếu backtest xa."""
    return max((done for _ex, done in _capital_raise_events(db, ticker, ref_date)), default=None)


def _capital_raise_events(db: Session, ticker: str, ref_date) -> list[tuple[Any, Any]]:
    """(GDKHQ, ngày hoàn tất) các đợt phát hành có thu tiền trọng yếu — bộ lọc chung của capital_raise_cutoff."""
    min_ratio = float(load_defaults()["relative_multiples"]["capital_raise_min_ratio"])
    rows = (
        db.query(
            CorporateAction.event_type, CorporateAction.ex_right_date,
            CorporateAction.listing_date, CorporateAction.exercise_ratio,
        )
        .filter(
            CorporateAction.ticker == ticker,
            CorporateAction.event_type.in_(("RIGHTS_ISSUE", "PRIVATE_PLACEMENT")),
            CorporateAction.ex_right_date.isnot(None),
            CorporateAction.ex_right_date <= ref_date,
        )
        .all()
    )
    return [
        (ex, listing if etype == "RIGHTS_ISSUE" and listing else ex)
        for etype, ex, listing, ratio in rows
        if not ratio or float(ratio) >= min_ratio
    ]


def capital_raise_proceeds(db: Session, ticker: str, ref_date, as_of=None) -> list[tuple[Any, dict[Any, float] | None]]:
    """Mỗi đợt của _capital_raise_events: (ngày hoàn tất, {cuối quý: tiền thu C, tỷ đồng}) hoặc None khi không ước
    được C đáng tin. C = "Tiền thu từ phát hành cổ phiếu, nhận vốn góp" (LCTT quý, proceeds_from_issue_of_shares) các
    quý từ quý GDKHQ tới quý hoàn tất; ĐÁNG TIN khi đủ số liệu mọi quý, C > 0 và Δ(vốn góp + thặng dư) cùng cửa sổ ≥
    (1 − relative_multiples.capital_raise_proceeds_tol) × C (tiền thu thật sự vào vốn cổ phần; Δ lớn hơn C cho phép vì
    cổ phiếu thưởng từ LN chưa phân phối không thu tiền — VIX Q3/2024). as_of: chỉ dùng quý đã tới hạn công bố."""
    import datetime

    from valuation.engine.ttm_helper import _quarter_end

    events = _capital_raise_events(db, ticker, ref_date)
    if not events:
        return []
    cfg = load_defaults()
    tol = float(cfg["relative_multiples"]["capital_raise_proceeds_tol"])
    lag = cfg.get("publication_lag_days", {}) or {}
    as_of_d = as_of.date() if isinstance(as_of, datetime.datetime) else as_of
    rows = (
        db.query(
            FinancialsQuarterly.fiscal_year, FinancialsQuarterly.fiscal_quarter, FinancialsQuarterly.line_item,
            FinancialsQuarterly.is_restated, FinancialsQuarterly.value,
        )
        .filter(
            FinancialsQuarterly.ticker == ticker,
            FinancialsQuarterly.is_consolidated.is_(True),
            FinancialsQuarterly.fiscal_quarter.between(1, 4),
            FinancialsQuarterly.line_item.in_(("paid_in_capital", "capital_surplus", "proceeds_from_issue_of_shares")),
        )
        .order_by(FinancialsQuarterly.is_restated)  # bản điều chỉnh hồi tố (True) ghi đè bản gốc
        .all()
    )
    val = {
        (y, q, item): to_billion_vnd(float(v))
        for y, q, item, _r, v in rows
        if v is not None and (as_of_d is None or _published_by(y, q, as_of_d, lag))
    }

    def _cap(y: int, q: int) -> float | None:
        pic = val.get((y, q, "paid_in_capital"))
        return None if pic is None else pic + val.get((y, q, "capital_surplus"), 0.0)

    out: list[tuple[Any, dict[Any, float] | None]] = []
    for ex, done in events:
        q0, q1 = (ex.year, (ex.month - 1) // 3 + 1), (done.year, (done.month - 1) // 3 + 1)
        window = [(y, q) for y in range(q0[0], q1[0] + 1) for q in range(1, 5) if q0 <= (y, q) <= q1]
        prev = (q0[0] - 1, 4) if q0[1] == 1 else (q0[0], q0[1] - 1)
        cash = [val.get((y, q, "proceeds_from_issue_of_shares")) for y, q in window]
        cap0, cap1 = _cap(*prev), (_cap(*window[-1]) if window else None)
        total = sum(c for c in cash if c is not None)
        reliable = (
            bool(window) and None not in cash and cap0 is not None and cap1 is not None
            and total > 0 and cap1 - cap0 >= (1 - tol) * total
        )
        out.append((done, {_quarter_end(y, q): c for (y, q), c in zip(window, cash) if c} if reliable else None))
    return out


def own_history_multiple(
    db: Session,
    ticker: str,
    denominators: Dict[int, float],
    shares_m: float,
    adjustments: Dict[int, float] | None = None,
    years: int = 5,
    kind: str | None = None,
    period_end: Dict[int, Any] | None = None,  # năm → ngày cuối kỳ (datetime.date)
    as_of=None,
    flags: list[str] | None = None,
    exclude_pre_issue: bool = False,
) -> float | None:
    """Trung vị (vốn hóa cuối năm + điều chỉnh) / mẫu số các năm gần nhất của CHÍNH mã.

    P/B: mẫu số VCSH mẹ; P/E: LN mẹ > 0; EV/EBITDA: điều chỉnh = nợ ròng + CĐKKS −
    đầu tư dài hạn, mẫu số EBITDA > 0. Cần ≥ 3 năm quan sát HỢP LỆ.
    `kind` ("pe"/"ev_ebitda"): bỏ từng quan sát ngoài dải `relative_multiples` TRƯỚC khi
    lấy trung vị — năm LN đáy cho P/E 120x+ phản ánh mẫu số méo, không phải giá thị trường
    trả (CTD: trung vị 27,9x → áp lên LN phục hồi ra FV gấp 3 thị giá).
    Giá đã điều chỉnh quyền × số cp hiện tại = vốn hóa lịch sử khi các sự kiện là
    cổ tức CP/thưởng. Phát hành có thu tiền (quyền mua, riêng lẻ) làm bội số năm trước đợt phình →
    exclude_pre_issue=True (nhóm relative_multiples.capital_raise_exclusion_groups): quan sát cuối kỳ trước ngày hoàn
    tất của đợt nào đó — P/B pro-forma = vốn hóa / (VCSH_y + C) với C = tiền thu các quý SAU cuối kỳ y
    (capital_raise_proceeds, relative_multiples.capital_raise_proforma; cờ MULTIPLE_PRE_ISSUE_PROFORMA, C = mức cộng
    vào quan sát cũ nhất); bội số khác, C không ước được đáng tin hoặc P/B cũ ngụ ý (vốn hóa − C)/VCSH dưới sàn
    relative_multiples.pb → loại (fx2; cờ MULTIPLE_PRE_ISSUE_EXCLUDED).
    """
    import datetime
    import statistics

    ref = as_of.date() if isinstance(as_of, datetime.datetime) else (as_of or datetime.date.today())
    cutoff = capital_raise_cutoff(db, ticker, ref) if exclude_pre_issue else None
    proforma = (
        cutoff is not None
        and kind in (None, "pb")
        and bool(load_defaults()["relative_multiples"]["capital_raise_proforma"])
    )
    raises = capital_raise_proceeds(db, ticker, ref, as_of) if proforma else []
    pb_floor = float(load_defaults()["relative_multiples"]["pb"][0])
    dropped = proformed = 0
    c_max = 0.0

    lo, hi = (
        (load_defaults().get("relative_multiples", {}) or {}).get(kind, [0.0, float("inf")])
        if kind
        else (float("-inf"), float("inf"))
    )
    vals = []
    for y in sorted(denominators)[-years:]:
        den = denominators[y]
        # D62: kỳ TTM chưa có giá 31/12 → ghép giá cuối quý báo cáo gần nhất (trước đây bỏ phí 1/5 suất).
        end = (period_end or {}).get(y, datetime.date(y, 12, 31))
        add = 0.0
        if cutoff is not None and end < cutoff:
            hit = [qs for done, qs in raises if done > end]  # đợt hoàn tất sau cuối kỳ y
            if not proforma or None in hit:
                dropped += 1
                continue
            # Hợp các quý của mọi đợt (không cộng trùng); tiền đã ghi trước cuối kỳ y nằm sẵn trong VCSH_y.
            quarters = {qe: c for qs in hit if qs for qe, c in qs.items()}
            add = sum(c for qe, c in quarters.items() if qe > end)
        row = (
            db.query(PricesDaily.close)
            .filter(
                PricesDaily.ticker == ticker,
                PricesDaily.trade_date >= end.replace(day=1),
                PricesDaily.trade_date <= end,
            )
            .order_by(PricesDaily.trade_date.desc())
            .first()
        )
        if row and row[0] and den > 0:
            mcap = float(row[0]) * shares_m / 1e3  # tỷ đồng
            # Pro-forma dựa trên vốn hóa điều chỉnh = vốn hóa cũ + C (một đợt, giá không đổi tới đợt). P/B cũ ngụ ý
            # (vốn hóa − C)/VCSH dưới sàn relative_multiples.pb → đẳng thức không đứng (giá tăng mạnh, nhiều đợt:
            # VIX FY2022 8.902 − 17.578 < 0) → loại như fx2 thay vì một P/B pro-forma vô lý.
            if add > 0 and (mcap - add) / den < pb_floor:
                dropped += 1
                continue
            multiple = (mcap + (adjustments or {}).get(y, 0.0)) / (den + add)
            if lo <= multiple <= hi:
                vals.append(multiple)
                if add > 0:
                    proformed += 1
                    c_max = max(c_max, add)
    if proformed and flags is not None:
        flags.append(f"MULTIPLE_PRE_ISSUE_PROFORMA:{kind or 'pb'}={proformed}(C={c_max:.0f})")
    if dropped and flags is not None:
        flags.append(f"MULTIPLE_PRE_ISSUE_EXCLUDED:{kind or 'pb'}={dropped}<{cutoff}")
    return statistics.median(vals) if len(vals) >= 3 else None


def operating_ev_bridge(b: BalanceSheet) -> float:
    """EV hoạt động − vốn hóa = nợ vay − tiền − ĐTNH + CĐKKS − ĐTDH − XDCB dở dang (tỷ đồng). MỘT định nghĩa
    cho bội số EV/EBITDA lịch sử và hiện hành; cầu nối định giá cộng lại ĐTDH + CIP (tài sản không tạo EBITDA
    tách khỏi EV — Damodaran/CFA: tử, mẫu bội số cùng định nghĩa; áp bội số hiện hành ra đúng vốn hóa)."""
    return (
        b.short_term_debt + b.long_term_debt - b.cash_and_equivalents - b.short_term_financial_investments
        + b.minority_interest - b.long_term_investments_net - b.construction_in_progress
    )


def current_multiples(company: Company) -> Dict[str, float | None]:
    """EV/EBITDA, P/E hiện hành: thị giá × số cp hiện tại trên kỳ cuối (TTM) của chính mã."""
    i, b = company.historical_is[-1], company.historical_bs[-1]
    dep = next((cf.depreciation for cf in company.historical_cf if cf.year == i.year), 0.0)
    mcap = company.current_price * company.shares_outstanding / 1e3  # tỷ đồng
    ebitda = i.ebit + dep
    return {
        "ev_ebitda": (mcap + operating_ev_bridge(b)) / ebitda if ebitda > 0 else None,
        "pe": mcap / i.net_income if i.net_income > 0 else None,
    }


def multiples_used(plan: dict[str, Any], jv_valued: bool = False) -> tuple[bool, bool]:
    """(EV/EBITDA, P/E) mà phương pháp route() thực sự đưa vào FV. DCF: bội số phụ theo bản
    chất kinh doanh chỉ khi trọng số DCF < 1; P/E còn dùng định giá liên doanh có lãi (D45)."""
    from valuation.engine.sector_router import dcf_secondary_multiple

    method = plan.get("method")
    secondary = dcf_secondary_multiple(plan.get("business_nature"))
    blended = method == "DCF" and float(plan.get("weight", 0.5)) < 1
    uses_ev = method == "EV_EBITDA" or (blended and secondary == "EV_EBITDA")
    uses_pe = method == "PE" or (blended and secondary == "PE") or (method == "DCF" and jv_valued)
    return uses_ev, uses_pe


def peer_median_multiple(values: List[float | None], kind: str, min_peers: int) -> float | None:
    """Trung vị nhóm so sánh, bỏ bội số âm/vô nghĩa (ngoài dải relative_multiples) — CFA/Damodaran comparables."""
    import statistics

    lo, hi = load_defaults()["relative_multiples"][kind]
    vals = [v for v in values if v is not None and lo <= v <= hi]
    return statistics.median(vals) if len(vals) >= min_peers else None


_PEER_CACHE: Dict[tuple, Dict[str, float | None]] = {}


def sector_peer_multiples(db: Session, ticker: str, group: str | None, as_of=None) -> Dict[str, float | None]:
    """Trung vị bội số HIỆN HÀNH của các mã cùng nhóm routing.json (trừ chính mã) — D62."""
    min_peers = int((load_defaults().get("peer_multiples") or {}).get("min_peers", 3))
    obs = _group_peer_obs(db, group, as_of, exclude=ticker)
    return {
        k: peer_median_multiple([o.get(k) for o in obs], k, min_peers) for k in ("ev_ebitda", "pe", "pb")
    }


def resolve_sotp_holdings(db: Session, ticker: str, as_of=None) -> dict[str, Any] | None:
    """Gắn vốn hóa và VCSH mẹ (tỷ đồng, cùng as_of) cho từng cổ phần niêm yết khai báo trong
    config/sotp_holdings.yaml (chế độ SOTP_HOLDINGS). Mã không khai báo → None.
    Công ty con không dựng được dữ liệu → ghi `error` (sotp.py gắn SOTP_HOLDINGS_INCOMPLETE, quay về proxy).
    `data_errors`: mã lỗi mức error của chính công ty con (kiểm tra xác định như cổng công bố của nó) —
    vốn hóa/VCSH của nó đi thẳng vào FV mã mẹ nên lỗi đó phải chặn mã mẹ (SOTP_SUBSIDIARY_DATA_ERROR)."""
    import datetime

    from valuation.config import sotp_holdings_for
    from valuation.report.verified_summary import run_deterministic_checks

    entry = sotp_holdings_for(ticker)
    if entry is None:
        return None
    holdings = []
    for h in entry["holdings"]:
        sub_t = str(h["ticker"]).upper()
        cv = h.get("carrying_value_bn")
        row: dict[str, Any] = {
            "ticker": sub_t,
            "stake": float(h["stake"]),
            "carrying_value_bn": float(cv) if cv is not None else None,
            "source": h["source"],
        }
        try:
            sub = build_company_data(db, sub_t, mode="TTM", fetch_live=False, as_of=as_of, peer_lookup=False)
        except ValueError as exc:
            row["error"] = str(exc)[:160]
        else:
            if sub.current_price > 0 and sub.shares_outstanding > 0:
                # Công ty con không được định giá (chỉ lấy thị giá) → FV giả = thị giá để bỏ qua kiểm tra FV/upside,
                # chỉ giữ lỗi dữ liệu. Giá cũ đã có đường riêng (price_stale → SOTP_HOLDINGS_STALE).
                checks = run_deterministic_checks(sub, blended_fv=sub.current_price, upside=0.0)
                row.update(
                    market_cap_bn=sub.current_price * sub.shares_outstanding / 1e3,
                    book_equity_bn=sub.historical_bs[-1].parent_equity,
                    price_stale="STALE_PRICE" in (sub.data_flags or []),
                    data_errors=sorted(
                        {c["code"] for c in checks if c["severity"] == "error" and c["code"] != "STALE_PRICE"}
                    ),
                )
            else:
                row["error"] = "NO_PRICE_OR_SHARES"
        holdings.append(row)
    return {
        "as_of": str(entry["as_of"])[:10] if entry.get("as_of") else None,
        "reviewed_by": entry.get("reviewed_by") or None,
        "review_ttl_days": entry["review_ttl_days"],
        "valuation_date": (as_of or datetime.datetime.now().astimezone().date()).isoformat()[:10],
        "holdings": holdings,
    }


def _group_peer_obs(db: Session, group: str | None, as_of, exclude: str | None = None) -> list[dict]:
    """Chỉ tiêu HIỆN HÀNH (bội số; NH thêm ROE năm tài chính) của các mã cùng nhóm routing.json."""
    import datetime
    import statistics

    from valuation.engine.sector_router import _router

    window = int((load_defaults().get("bank_terminal") or {}).get("roe_window", 3))
    obs = []
    for p, data in _router().routing_data.items():
        # routing.json lưu nhóm ở khóa "sector" (route() map group = sector); khóa "group" không tồn tại.
        if p == exclude or not group or data.get("sector") != group:
            continue
        # shortcut: cache theo ngày trong tiến trình; giá trong ngày cập nhật được ở lần chạy hôm sau.
        key = (p, as_of, datetime.date.today())
        if key not in _PEER_CACHE:
            try:
                peer = build_company_data(db, p, as_of=as_of, peer_lookup=False)
            except ValueError:
                continue  # peer thiếu dữ liệu → bỏ khỏi mẫu, không chặn mã đang định giá
            if isinstance(peer, CompanyBank):
                # ROE năm tài chính ĐẦY ĐỦ trên VCSH bình quân (cùng định nghĩa roe5). Chỉ bỏ kỳ cuối khi là TTM
                # chưa trọn năm (chồng quý năm trước); kỳ cuối Q4 = FY đủ 4 quý thì giữ.
                n = len(peer.historical_is) - (1 if peer.last_period_is_ttm else 0)
                fy = average_equity_roes(peer.historical_is[:n], peer.historical_bs[:n])[-window:]
                _PEER_CACHE[key] = {"pb": current_pb(peer), "roe_fy": statistics.median(fy) if fy else None}
            else:
                _PEER_CACHE[key] = (
                    {**current_multiples(peer), "pb": current_pb(peer)} if isinstance(peer, Company) else {}
                )
        obs.append(_PEER_CACHE[key])
    return obs


def average_equity_roes(incomes: list, balances: list) -> list[float]:
    """ROE từng năm = LNST / VCSH BÌNH QUÂN (cuối năm trước, cuối năm) cho các cặp năm liền kề — định nghĩa ROE
    duy nhất của gói NH (bank_terminal): roe5, ROE ngành, trung vị lịch sử đối chiếu."""
    return [
        i.net_income / ((b0.total_equity + b.total_equity) / 2)
        for b0, i, b in zip(balances, incomes[1:], balances[1:])
        if b.year - b0.year == 1 and b0.total_equity + b.total_equity > 0
    ]


def bank_industry_roe(db: Session, group: str | None, as_of=None) -> float | None:
    """ROE trung bình ngành = trung vị (các NH cùng nhóm, gồm chính mã) của trung vị ROE `roe_window`
    năm tài chính đầy đủ (VCSH bình quân) — đích hội tụ ROE terminal (Damodaran). Cắt theo as_of: không lookahead.
    Nhóm dưới peer_multiples.min_peers mã (EVF một mình nhóm 'Tài chính') → None: không có trung bình
    ngành đáng tin, không hội tụ."""
    import statistics

    min_peers = int((load_defaults().get("peer_multiples") or {}).get("min_peers", 3))
    roes = [o["roe_fy"] for o in _group_peer_obs(db, group, as_of) if o.get("roe_fy") is not None]
    return statistics.median(roes) if len(roes) >= min_peers else None


def pb_history_or_peer(
    db: Session,
    ticker: str,
    balances: list,
    shares_m: float,
    period_end: dict[int, Any] | None,
    group: str | None,
    as_of,
    peer_lookup: bool,
    flags: list[str],
) -> float | None:
    """Chân P/B thị trường cho định chế tài chính: trung vị P/B của chính mã (gồm kỳ TTM ghép giá
    cuối quý, D62); thiếu < 3 quan sát → trung vị P/B HIỆN HÀNH của nhóm routing.json + cờ."""
    pb = own_history_multiple(
        db, ticker, {b.year: b.parent_equity for b in balances}, shares_m, period_end=period_end,
        as_of=as_of, flags=flags,
        exclude_pre_issue=group in (load_defaults()["relative_multiples"]["capital_raise_exclusion_groups"] or []),
    )
    if pb is None and peer_lookup:
        pb = sector_peer_multiples(db, ticker, group, as_of)["pb"]
        if pb is not None:
            flags.append(f"MULTIPLE_FROM_PEER_MEDIAN:pb={pb:.2f}x")
    return pb


# Tổng mục bắt buộc của một bộ BS (mẫu B01-DN mã 100/200/300/310/330).
_BS_SUBTOTALS = frozenset(
    {"current_assets", "long_term_assets", "liabilities", "current_liabilities", "long_term_liabilities"}
)


def drop_incomplete_filing_bs(df: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    """BS restated (filing) của một kỳ thiếu tổng mục → bỏ cả bộ BS restated kỳ đó, dùng nguyên
    BS vendor (nếu có). Ưu tiên restated theo TỪNG chỉ tiêu sẽ trộn hai nguồn trong một báo cáo:
    PVT Q2/2026 vốn chủ theo filing, nợ theo vendor → tổng tài sản lệch tổng nguồn vốn 150,9 tỷ.
    IS/CF filing giữ nguyên. Trả (df đã lọc, các kỳ (năm, quý) bị bỏ)."""
    if df.empty:
        return df, []
    bs = df["statement"] == "BS"
    restated = df["is_restated"].fillna(False).astype(bool)
    dropped: list[tuple[int, int]] = []
    mask = pd.Series(False, index=df.index)
    for (y, q), grp in df[bs & restated].groupby(["fiscal_year", "fiscal_quarter"]):
        period = (df["fiscal_year"] == y) & (df["fiscal_quarter"] == q) & bs
        if not _BS_SUBTOTALS <= set(grp["line_item"]) and (period & ~restated).any():
            mask |= period & restated
            dropped.append((int(y), int(q)))
    return df[~mask], dropped


def drop_incomplete_latest_quarters(records: list) -> tuple[list, list[tuple[int, int]]]:
    """Quý mới nhất chưa đủ cả BS, IS và CF (nguồn công bố dần: NT2 Q3/2026 có BS+IS, CF chưa ra) → bỏ các quý
    sau quý đầy đủ gần nhất, TTM tính tới quý đầy đủ đó. Trộn kỳ (BS quý mới, CF quý cũ) làm vỡ TTM và chặn oan
    cả mã. Chỉ xét quý (fiscal_quarter > 0). Trả (records đã lọc, các kỳ (năm, quý) bị bỏ)."""
    stmts: dict[tuple[int, int], set] = {}
    for r in records:
        if r.fiscal_quarter > 0:
            stmts.setdefault((r.fiscal_year, r.fiscal_quarter), set()).add(r.statement)
    complete = [k for k, v in stmts.items() if {"BS", "IS", "CF"} <= v]
    if not complete:
        return records, []
    last = max(complete)
    dropped = sorted(k for k in stmts if k > last)
    if not dropped:
        return records, []
    return [r for r in records if r.fiscal_quarter == 0 or (r.fiscal_year, r.fiscal_quarter) <= last], dropped


def credit_institution_template(records) -> bool:
    """BCTC theo mẫu tổ chức tín dụng (TT49/2014: có dòng 'thu nhập lãi thuần' trên KQKD) →
    định giá trên vốn chủ như ngân hàng (RI + P/B). Mẫu BCTC quyết định chỉ tiêu nào tồn tại:
    công ty tài chính (EVF) không có doanh thu/EBIT nên nhánh phi tài chính không chạy được."""
    return any(
        r.statement == "IS" and r.line_item == "net_interest_income" and r.value is not None
        for r in records
    )


def current_pb(company: Company | CompanyBank) -> float | None:
    """P/B hiện hành: thị giá × số cp hiện tại / VCSH mẹ kỳ cuối (TTM)."""
    equity = company.historical_bs[-1].parent_equity
    return company.current_price * company.shares_outstanding / 1e3 / equity if equity > 0 else None


def get_shares_outstanding_repo(db: Session, ticker: str, as_of=None) -> float:
    """Lấy số lượng cổ phiếu lưu hành (đổi sang triệu cổ phiếu)."""
    from valuation.engine.ttm_helper import get_shares_outstanding

    # as_of quá khứ: số cp quy về cùng gốc với giá prices_daily đã điều chỉnh lùi (chống lookahead lệch gốc).
    shares = get_shares_outstanding(db, ticker, as_of_date=as_of, price_basis=as_of is not None)
    if shares <= 0:
        raise ValueError(f"Số lượng cổ phiếu không hợp lệ cho {ticker}: {shares}")
    # ttm_helper trả về số cp thô (ví dụ: 8,355,675,094).
    return shares / 1e6


def build_company_data(
    db: Session,
    ticker: str,
    mode: str = "TTM",
    fetch_live: bool = False,
    as_of=None,
    peer_lookup: bool = True,
) -> Union[Company, CompanyBank]:
    """
    Truy vấn dữ liệu tài chính lịch sử, quy đổi kỳ báo cáo và đơn vị,
    trả về đối tượng Pydantic Company (phi tài chính) hoặc CompanyBank (ngân hàng).
    """
    meta = load_ticker_metadata(db, ticker)
    if not meta:
        raise ValueError(f"Không tìm thấy ticker {ticker} trong DB")

    # ponytail: as_of mới cắt BCTC/giá/số cp; rf, beta, freshness vẫn lấy mới nhất —
    # đủ cho hiệu chỉnh gần hiện tại, cần cắt nốt nếu backtest xa.
    current_price = get_latest_price(db, ticker, fetch_live=fetch_live, as_of=as_of)
    shares = get_shares_outstanding_repo(db, ticker, as_of=as_of)

    # 1. Truy vấn toàn bộ dữ liệu quý của ticker
    records = (
        db.query(FinancialsQuarterly)
        .filter(
            FinancialsQuarterly.ticker == ticker,
            FinancialsQuarterly.is_consolidated.is_(True),
            FinancialsQuarterly.currency == "VND",
        )
        .all()
    )
    all_records = records  # audit nguồn đối chiếu dữ liệu HIỆN TẠI, trước khi cắt theo as_of
    # Nhóm NH hoặc TCTD phi ngân hàng (EVF, sector DB 'Financial Services') nhận theo mẫu BCTC.
    is_bank = meta.sector == "Banks" or credit_institution_template(all_records)
    if as_of is not None:
        _lag = load_defaults().get("publication_lag_days", {}) or {}
        records = [r for r in records if _published_by(r.fiscal_year, r.fiscal_quarter, as_of, _lag)]
    records, _q_dropped = drop_incomplete_latest_quarters(records)
    fin_data = [
        {
            "fiscal_year": r.fiscal_year,
            "fiscal_quarter": r.fiscal_quarter,
            "line_item": r.line_item,
            "statement": r.statement,
            "is_restated": r.is_restated,
            "published_at": r.published_at,
            "value": float(r.value) if r.value is not None else None,
        }
        for r in records
    ]
    df_fin, _bs_dropped = drop_incomplete_filing_bs(pd.DataFrame(fin_data))

    # Lấy danh sách các năm
    years = sorted({r.fiscal_year for r in records})
    if not years:
        raise ValueError(f"Không có dữ liệu tài chính cho {ticker}")

    # Xác định năm lớn nhất và quý lớn nhất
    latest_yr = max(years)
    sub_latest = df_fin[
        (df_fin["fiscal_year"] == latest_yr) & (df_fin["fiscal_quarter"] > 0)
    ]
    latest_q = sub_latest["fiscal_quarter"].max() if not sub_latest.empty else 4
    # Kỳ cuối là TTM CHƯA trọn năm tài chính (chồng quý năm trước) → loại khỏi cửa sổ năm đầy đủ. Quý cuối = 4
    # thì TTM chính là FY đủ 4 quý: giữ (trước fx2 mất trọn một năm từ lúc có BCTC Q4 tới khi có Q1).
    ttm_partial = mode == "TTM" and int(latest_q) < 4

    historical_is = []
    historical_bs = []
    historical_cf = []
    extraction_flags = [f"FILING_BS_INCOMPLETE:{y}Q{q}" for y, q in _bs_dropped]
    extraction_flags += [f"QUARTER_INCOMPLETE_SKIPPED:{y}Q{q}" for y, q in _q_dropped]
    bank_div_paid: Dict[int, float] = {}
    _cip_wip: dict[int, tuple[float, float]] = {}  # năm → (XDCB mã 242, SXKD dở dang dài hạn mã 241)
    from valuation.engine.sector_router import route

    sector_plan = route(ticker) or {}
    financial_sector = sector_plan.get("group") in {
        "CK",
        "BH",
        "Chứng khoán",
        "Bảo hiểm",
    } or meta.sector in {"Insurance", "Securities", "Financial Services"}
    try:
        from valuation.config import PROJECT_ROOT
        from valuation.ingest.taxonomy import taxonomy_mapping
        from valuation.services.ranking_store import read_json

        audit = read_json(PROJECT_ROOT / "data/source_quality_status.json", {})
        extraction_flags.extend(
            _source_audit_flags(audit, ticker, taxonomy_mapping()["version"], all_records)
        )
    except (OSError, ValueError, TypeError):
        extraction_flags.append("SOURCE_AUDIT_MISSING")

    # 2. Quy đổi dữ liệu quý -> năm cho từng năm lịch sử
    for y in years:
        # Nếu là năm gần nhất và mode == TTM, chạy periodize theo TTM
        # Nếu là năm cũ, luôn chạy theo FY (đầy đủ cả năm)
        if y == latest_yr and mode == "TTM":
            annual_data = periodize_quarters_to_annual(
                df_fin, y, mode="TTM", latest_quarter=latest_q
            )
        else:
            annual_data = periodize_quarters_to_annual(df_fin, y, mode="FY")

        if not annual_data:
            continue
        # Năm sơ khai (vd BAF 2018: chỉ có Q0, không có LCTT, nguồn ghi 0 cho chỉ tiêu không báo cáo)
        # → bỏ năm, không điền 0 làm bẩn trung vị/tăng trưởng. Năm gần nhất giữ để cờ thiếu dữ liệu nổi lên.
        if (
            not is_bank
            and not financial_sector
            and y != latest_yr
            and _match_value(annual_data, NON_FIN_KEYWORDS["cfo"], fallback=None) is None
        ):
            extraction_flags.append(f"INCOMPLETE_YEAR_DROPPED:{y}")
            continue

        keywords = BANK_KEYWORDS if is_bank else NON_FIN_KEYWORDS
        for field in ("net_income", "total_assets", "total_equity"):
            try:
                _required_value(annual_data, keywords[field], field)
            except ValueError as exc:
                raise ValueError(f"{ticker} {y}: {exc}") from exc

        if is_bank:
            # Match dữ liệu bank
            nii = _required_value(
                annual_data, BANK_KEYWORDS["net_interest_income"], "net_interest_income"
            )
            toi = _required_value(
                annual_data,
                BANK_KEYWORDS["total_operating_income"],
                "total_operating_income",
            )
            opex = abs(
                _required_value(
                    annual_data,
                    BANK_KEYWORDS["operating_expenses"],
                    "operating_expenses",
                )
            )
            # Nguồn ghi chi phí dự phòng mang dấu âm; năm hoàn nhập ròng là số dương → đổi dấu,
            # KHÔNG abs (abs biến hoàn nhập thành chi phí: NAB 2018 LNTT lệch 27%). TT49/2014.
            prov = -_required_value(
                annual_data, BANK_KEYWORDS["provision_expense"], "provision_expense"
            )
            ni = _required_value(annual_data, BANK_KEYWORDS["net_income"], "net_income")
            bank_div_paid[y] = abs(_match_value(annual_data, ["dividends_paid"]))

            loans = _required_value(
                annual_data, BANK_KEYWORDS["customer_loans"], "customer_loans"
            )
            deposits = _required_value(
                annual_data, BANK_KEYWORDS["customer_deposits"], "customer_deposits"
            )
            assets = _required_value(
                annual_data, BANK_KEYWORDS["total_assets"], "total_assets"
            )
            equity = _required_value(
                annual_data, BANK_KEYWORDS["total_equity"], "total_equity"
            )

            # Tính toán gián tiếp nếu thiếu trường
            non_interest_income = toi - nii
            ppop = toi - opex
            # Số 0 có thể là số báo cáo thật, không thay bằng lợi nhuận ước tính.
            pbt = _required_value(
                annual_data, BANK_KEYWORDS["pretax_income"], "pretax_income"
            )

            other_earning_assets = max(0.0, assets - loans)
            other_liabilities = max(0.0, assets - deposits - equity)

            # Quy đổi sang Tỷ đồng (chia 10^9)
            historical_is.append(
                IncomeStatementBank(
                    year=y,
                    net_interest_income=to_billion_vnd(nii),
                    non_interest_income=to_billion_vnd(non_interest_income),
                    total_operating_income=to_billion_vnd(toi),
                    operating_expenses=to_billion_vnd(opex),
                    pre_provision_profit=to_billion_vnd(ppop),
                    provision_expense=to_billion_vnd(prov),
                    pretax_income=to_billion_vnd(pbt),
                    net_income=to_billion_vnd(ni),
                )
            )

            historical_bs.append(
                BalanceSheetBank(
                    year=y,
                    customer_loans=to_billion_vnd(loans),
                    other_earning_assets=to_billion_vnd(other_earning_assets),
                    total_assets=to_billion_vnd(assets),
                    customer_deposits=to_billion_vnd(deposits),
                    other_liabilities=to_billion_vnd(other_liabilities),
                    total_equity=to_billion_vnd(equity),
                )
            )
        else:
            income = _nonfinancial_income_values(
                annual_data, financial_sector=financial_sector
            )
            rev, cogs, gp, opex, ebit, int_exp, tax, ni = (
                income[k]
                for k in (
                    "revenue",
                    "cogs",
                    "gross_profit",
                    "opex",
                    "ebit",
                    "interest_expense",
                    "tax",
                    "net_income",
                )
            )
            # Năm CŨ vi phạm đẳng thức LN gộp = DT − giá vốn hoặc DT âm (VPI 2018 vendor: giá vốn
            # cộng thay vì trừ) là rác dữ liệu → bỏ năm như D62, không để bẩn trung vị/tăng trưởng.
            # Chỉ năm ngoài mọi cửa sổ mô hình; năm trong cửa sổ giữ để GROSS_PROFIT_MISMATCH chặn.
            if (
                not financial_sector
                and inconsistent_year_droppable(
                    int(y),
                    latest_year=int(latest_yr),
                    latest_quarter=int(latest_q),
                    window=int((load_defaults().get("forecast") or {})["margin_window_years"]),
                )
                and inconsistent_income_year(rev, cogs, gp)
            ):
                extraction_flags.append(f"INCONSISTENT_YEAR_DROPPED:{y}")
                continue
            if not financial_sector:
                for field in (
                    "cash",
                    "st_debt",
                    "lt_debt",
                    "receivables",
                    "inventory",
                    "accounts_payable",
                    "cfo",
                    "cfi",
                    "cff",
                    "capex",
                    "depreciation",
                ):
                    if (
                        _match_value(
                            annual_data, NON_FIN_KEYWORDS[field], fallback=None
                        )
                        is None
                    ):
                        extraction_flags.append(f"MISSING_FINANCIAL_INPUT:{y}:{field}")
            elif _match_value(
                annual_data, NON_FIN_KEYWORDS["tax"], fallback=None
            ) is None and all(
                _match_value(annual_data, [item], fallback=None) is None
                for item in (
                    "business_income_tax_current",
                    "business_income_tax_deferred",
                )
            ):
                extraction_flags.append(f"MISSING_DISPLAY_INPUT:{y}:tax")

            cash = _match_value(annual_data, NON_FIN_KEYWORDS["cash"])
            short_term_financial_investments = _match_value(
                annual_data, NON_FIN_KEYWORDS["short_term_financial_investments"]
            )
            rec = _match_value(annual_data, NON_FIN_KEYWORDS["receivables"])
            inv = _match_value(annual_data, NON_FIN_KEYWORDS["inventory"])
            fixed = _match_value(annual_data, NON_FIN_KEYWORDS["fixed_assets"])
            assets = _match_value(annual_data, NON_FIN_KEYWORDS["total_assets"])
            st_debt = _match_value(annual_data, NON_FIN_KEYWORDS["st_debt"])
            lt_debt = _match_value(annual_data, NON_FIN_KEYWORDS["lt_debt"]) + _match_value(
                annual_data, NON_FIN_KEYWORDS["convertible_bonds"]
            )
            pay = _match_value(annual_data, NON_FIN_KEYWORDS["accounts_payable"])
            equity = _match_value(annual_data, NON_FIN_KEYWORDS["total_equity"])
            minority_interest = _match_value(
                annual_data, NON_FIN_KEYWORDS["minority_interest"]
            )

            residuals = _balance_residuals(
                annual_data,
                cash=cash,
                receivables=rec,
                inventory=inv,
                fixed=fixed,
                short_debt=st_debt,
                payable=pay,
                long_debt=lt_debt,
            )
            for field, value in residuals.items():
                if value is None:
                    prefix = (
                        "MISSING_DISPLAY_INPUT"
                        if financial_sector
                        else "MISSING_FINANCIAL_INPUT"
                    )
                    extraction_flags.append(f"{prefix}:{y}:{field}")
            other_curr_assets = residuals["other_current_assets"] or 0.0
            if (
                y == latest_yr
                and not financial_sector
                and unexplained_current_assets(
                    _match_value(annual_data, ["current_assets"]),
                    cash,
                    short_term_financial_investments,
                    _match_value(annual_data, ["accounts_receivable", "short_term_receivables"], fallback=rec),
                    inv,
                    _match_value(annual_data, ["other_current_assets"]),
                )
            ):
                extraction_flags.append(f"UNEXPLAINED_CURRENT_ASSETS:{y}")
            other_lt_assets = residuals["other_long_term_assets"] or 0.0
            other_curr_liab = residuals["other_current_liabilities"] or 0.0
            other_lt_liab = residuals["other_long_term_liabilities"] or 0.0

            # Giữ nguyên vốn chủ sở hữu báo cáo. Nếu các cấu phần không khớp,
            # Pydantic sẽ phát cảnh báo cân đối; không được che lỗi bằng cách dựng
            # lại equity từ phần dư vì equity là đầu vào trực tiếp của định giá.

            cfo = _match_value(annual_data, NON_FIN_KEYWORDS["cfo"])
            capex = abs(
                _match_value(annual_data, NON_FIN_KEYWORDS["capex"])
            )  # lấy trị tuyệt đối
            cf_other, has_full_cashflow_sections = _cashflow_other_excluding_capex(
                annual_data,
                capex,
            )
            if not has_full_cashflow_sections and not financial_sector:
                extraction_flags.append(f"MISSING_FINANCIAL_INPUT:{y}:cfi_cff")
            dep_amort = abs(
                _match_value(annual_data, NON_FIN_KEYWORDS["depreciation"])
            )  # D&A thật từ CF

            # Quy đổi sang Tỷ đồng
            historical_is.append(
                IncomeStatement(
                    year=y,
                    revenue=to_billion_vnd(rev),
                    cogs=to_billion_vnd(cogs),
                    gross_profit=to_billion_vnd(gp),
                    opex=to_billion_vnd(opex),
                    ebit=to_billion_vnd(ebit),
                    interest_expense=to_billion_vnd(int_exp),
                    tax=to_billion_vnd(tax),
                    net_income=to_billion_vnd(ni),
                    jv_income=to_billion_vnd(
                        _match_value(annual_data, NON_FIN_KEYWORDS["jv_income"])
                    ),
                    pbt=(
                        to_billion_vnd(_pbt_raw)
                        if (_pbt_raw := _match_value(annual_data, NON_FIN_KEYWORDS["pbt"], fallback=None))
                        is not None
                        else None
                    ),
                )
            )
            cip = _match_value(annual_data, NON_FIN_KEYWORDS["construction_in_progress"])
            if not financial_sector:
                _cip_wip[y] = (cip, _match_value(annual_data, ["long_term_cost_of_work_in_progress"]))

            historical_bs.append(
                BalanceSheet(
                    year=y,
                    cash_and_equivalents=to_billion_vnd(cash),
                    short_term_financial_investments=to_billion_vnd(
                        short_term_financial_investments
                    ),
                    receivables=to_billion_vnd(rec),
                    inventory=to_billion_vnd(inv),
                    other_current_assets=to_billion_vnd(other_curr_assets),
                    fixed_assets=to_billion_vnd(fixed),
                    other_long_term_assets=to_billion_vnd(other_lt_assets),
                    total_assets=to_billion_vnd(assets),
                    short_term_debt=to_billion_vnd(st_debt),
                    accounts_payable=to_billion_vnd(pay),
                    other_current_liabilities=to_billion_vnd(other_curr_liab),
                    long_term_debt=to_billion_vnd(lt_debt),
                    other_long_term_liabilities=to_billion_vnd(other_lt_liab),
                    total_equity=to_billion_vnd(equity),
                    minority_interest=to_billion_vnd(minority_interest),
                    long_term_investments_net=to_billion_vnd(
                        _match_value(annual_data, NON_FIN_KEYWORDS["long_term_investments"])
                    ),
                    investments_in_associates=to_billion_vnd(
                        _match_value(annual_data, NON_FIN_KEYWORDS["investments_in_associates"])
                    ),
                    construction_in_progress=to_billion_vnd(cip),
                    investment_property=to_billion_vnd(
                        _match_value(annual_data, NON_FIN_KEYWORDS["investment_property"])
                    ),
                    deferred_revenue=to_billion_vnd(
                        _match_value(annual_data, NON_FIN_KEYWORDS["deferred_revenue_st"])
                        + _match_value(annual_data, NON_FIN_KEYWORDS["deferred_revenue_lt"])
                    ),
                    reported_total_liabilities=(
                        to_billion_vnd(value)
                        if (
                            value := _match_value(
                                annual_data,
                                ["liabilities", "total_liabilities"],
                                fallback=None,
                            )
                        )
                        is not None
                        else None
                    ),
                )
            )

            historical_cf.append(
                CashFlow(
                    year=y,
                    cfo=to_billion_vnd(cfo),
                    capex=to_billion_vnd(capex),
                    depreciation=to_billion_vnd(dep_amort),
                    dividends_paid=to_billion_vnd(
                        abs(_match_value(annual_data, NON_FIN_KEYWORDS["dividends_paid"]))
                    ),
                    cf_other=to_billion_vnd(cf_other),
                    has_full_cashflow_sections=has_full_cashflow_sections,
                    is_ttm_period=(ttm_partial and y == latest_yr),
                )
            )

    # XDCB bị nguồn xếp nhầm sang mã 241: HAG FY2023 có 242 = 0, 241 = 4.825 tỷ trong khi các kỳ khác
    # 242 > 0, 241 = 0. Giữ số nguồn (không tự phân loại lại), cảnh báo trong cửa sổ 5 năm của bội số.
    if any(c > 0 and w == 0 for c, w in _cip_wip.values()):
        extraction_flags += [
            f"CIP_LINE_MISSING:{y}" for y in sorted(_cip_wip)[-5:] if _cip_wip[y][0] == 0 < _cip_wip[y][1]
        ]

    # 3. Tính toán giả định base case động
    rf_dynamic = get_latest_tpcp_10y(db)
    beta_dynamic = estimate_vcb_beta(db, ticker)
    # D47 (+CTCK): beta ngành bottom-up cho nhóm trong coe_convention.peer_beta_groups thay beta hồi
    # quy riêng. TCTD phi ngân hàng (EVF, nhóm routing chỉ 1 mã) dùng beta nhóm NH — xấp xỉ.
    _beta_group = "NH" if is_bank else sector_plan.get("group")
    if _beta_group and _beta_group in (load_defaults().get("coe_convention", {}).get("peer_beta_groups") or []):
        from valuation.engine.ttm_helper import sector_peer_beta

        beta_dynamic = sector_peer_beta(db, _beta_group)

    # Macro overlay context: độ lệch vĩ mô theo momentum 12 tháng (giá trị mới
    # nhất vs ~1 năm trước). Robust khi dữ liệu vĩ mô trễ/sớm hơn năm tài chính.
    # Khi chưa có dữ liệu GDP/tín dụng, delta=0 → overlay no-op (an toàn).
    from valuation.forecast.drivers import (
        MacroContext,
        overlay_revenue_growth,
    )

    _macro_ctx = MacroContext.from_db_momentum(db)
    _sector_for_overlay = meta.sector


    config_defaults = load_defaults()
    # VND-base: erp = mature ERP + CRP VN (CRP là rủi ro vốn cổ phần TT mới nổi,
    # tách biệt rủi ro vỡ nợ trong TPCP — chuẩn Damodaran).
    from valuation.engine.coe import get_erp, terminal_growth

    erp_vn = get_erp()

    if is_bank:
        # Tính toán NIM, CIR, Credit Cost trung bình lịch sử làm base case
        # (dùng 4 quý gần nhất của ttm_helper)
        from valuation.engine.ttm_helper import (
            compute_historical_cir,
            compute_historical_credit_cost,
            compute_historical_credit_growth,
            compute_historical_nim,
        )

        nim_val = compute_historical_nim(db, ticker) or 0.03
        cir_val = compute_historical_cir(db, ticker) or 0.35
        cg_raw = compute_historical_credit_growth(db, ticker) or 0.12
        cc_val = compute_historical_credit_cost(db, ticker) or 0.01
        _bank_forecast_cfg = config_defaults.get("bank_forecast", {}) or {}
        cg_val, credit_growth_capped = _bounded_bank_credit_growth(
            cg_raw, _bank_forecast_cfg
        )

        # Giai đoạn chuyển tiếp (Damodaran 3 giai đoạn): phai tuyến tính từ YoY hiện tại về GDP danh
        # nghĩa dài hạn ở năm 5. Lịch cũ 25/24/23/23/22% rơi thẳng xuống g 4% ở terminal; mã tăng
        # chậm thì lịch cũ nhảy 5% → 8% ở năm 5 (max(cg − 3%, 8%)).
        from valuation.forecast.base_year import revenue_growth_path

        credit_growth = revenue_growth_path(
            cg_val, float(config_defaults["long_run_nominal_gdp_growth"]), years=5
        )
        # KHÔNG cộng tăng trưởng tín dụng hệ thống: YoY của chính NH đã phản ánh chu kỳ
        # tín dụng toàn ngành → cộng thêm là đếm trùng (MBB ~25%/năm × 5 năm).
        bounded_schedule = []
        for growth in credit_growth:
            bounded, was_capped = _bounded_bank_credit_growth(
                growth, _bank_forecast_cfg
            )
            bounded_schedule.append(bounded)
            credit_growth_capped = credit_growth_capped or was_capped
        credit_growth = bounded_schedule
        import statistics as _stats

        # Giữ NIM/CIR ở mức hiện tại (không lộ trình "luôn cải thiện" tự đặt). Chi phí
        # tín dụng năm 5 = trung vị chu kỳ (cùng cửa sổ ROE): nhìn xuyên đột biến trích lập một
        # lần (STB/EIB Q4/2025) nhưng vẫn phản ánh mức trích lập thấp kéo dài.
        annual_cc = [
            historical_is[i].provision_expense
            / ((historical_bs[i - 1].customer_loans + historical_bs[i].customer_loans) / 2)
            for i in range(1, len(historical_bs))
            if historical_bs[i - 1].customer_loans + historical_bs[i].customer_loans > 0
        ]
        _cc_window = int((config_defaults.get("bank_terminal", {}) or {}).get("credit_cost_window", 3))
        _bank_cfg_cc = config_defaults.get("bank_terminal", {}) or {}
        _fy_cc = annual_cc[:-1] if ttm_partial else annual_cc
        cc_median = _stats.median(_fy_cc[-_cc_window:]) if _fy_cc else cc_val
        cc_ttm = annual_cc[-1] if annual_cc else cc_median
        if mode == "TTM" and annual_cc:
            # Dự phòng TTM chia dư nợ bình quân ĐÚNG cửa sổ: đầu kỳ = cùng quý năm trước, không phải
            # cuối năm tài chính trước (Ngân hàng F2). Thiếu số dư đó → giữ mẫu số cũ.
            _loans_open = _match_value(
                periodize_quarters_to_annual(df_fin, latest_yr - 1, mode="TTM", latest_quarter=latest_q),
                BANK_KEYWORDS["customer_loans"], fallback=None,
            )
            if _loans_open:
                cc_ttm = historical_is[-1].provision_expense / (
                    (to_billion_vnd(_loans_open) + historical_bs[-1].customer_loans) / 2
                )
        # Phai TTM → trung vị chuẩn hóa (đối xứng), trừ khi TTM là đột biến một lần (D47).
        credit_cost, cc_spike = credit_cost_schedule(
            cc_ttm if (mode == "TTM" and annual_cc) else cc_median, cc_median,
            float(_bank_cfg_cc.get("credit_cost_spike_multiple", 2.0)),
        )
        nim = [nim_val] * 5
        cir = [cir_val] * 5
        eq_to_assets = [
            b.total_equity / b.total_assets for b in historical_bs if b.total_assets > 0
        ]
        # D47: sàn VCSH/TS = min(hiện tại, trung vị 3 kỳ). Sàn = trung vị ép NH đang đòn bẩy cao hơn
        # lịch sử phải giảm đòn bẩy ngay (VPB LN năm 1 −44%); bỏ hẳn sàn lại cho NH mỏng vốn tăng
        # tài sản 25%/năm không cần vốn (TCB +48%, trái ràng buộc CAR). Đòn bẩy cao hơn lịch sử → cờ.
        _ea_med = _stats.median(eq_to_assets[-3:]) if eq_to_assets else None
        min_equity_to_assets = min(eq_to_assets[-1], _ea_med) if eq_to_assets else None
        leverage_above_history = bool(eq_to_assets) and eq_to_assets[-1] < _ea_med - 1e-9
        _ni = [is_.net_income for is_ in historical_is[-3:]]
        _paid = [bank_div_paid.get(is_.year, 0.0) / 1e9 for is_ in historical_is[-3:]]
        payout = (
            min(max(sum(_paid) / sum(_ni), 0.0), float(_bank_forecast_cfg.get("payout_cap", 0.5)))
            if sum(_ni) > 0
            else float(_bank_forecast_cfg.get("payout_fallback", 0.2))
        )
        # D47: cổ tức tiền đã GDKHQ 12 tháng gần nhất phản ánh chính sách mới (MBB 1.000đ 07/2026
        # nằm ngoài cửa sổ TTM) → lấy mức cao hơn của thực trả 3 năm và mức vừa công bố.
        from valuation.engine.ttm_helper import declared_cash_payout

        _last_px = db.query(PricesDaily.trade_date).filter(PricesDaily.ticker == ticker)
        if as_of is not None:
            _last_px = _last_px.filter(PricesDaily.trade_date <= as_of)
        _last_px = _last_px.order_by(PricesDaily.trade_date.desc()).first()
        if _last_px and historical_is[-1].net_income > 0:
            _declared = declared_cash_payout(
                db, ticker, shares * 1e6, historical_is[-1].net_income * 1e9, _last_px[0]
            )
            payout = min(max(payout, _declared), float(_bank_forecast_cfg.get("payout_cap", 0.5)))

        # ROE bền vững — D29: MEDIAN cửa sổ gần nhất, KHÔNG phải trung bình toàn lịch sử.
        #
        # Cách cũ `sum(roes)/len(roes)` trộn đỉnh chu kỳ 2018-2021 vào ước lượng
        # "bền vững": ACB ra 20,8% trong khi ROE thực tế đang phai rõ rệt
        # 23%→20%→17%→16%. Vì Target P/B = (ROE-g)/(COE-g) CỰC nhạy với ROE, sai
        # số này đẩy thẳng vào định giá — là nguyên nhân gốc của overshoot D20.
        #
        # Median (không phải trung bình) để một quý đột biến không kéo lệch ước lượng.
        _bank_cfg = config_defaults.get("bank_terminal", {}) or {}
        _roe_window = int(_bank_cfg.get("roe_window", 3))
        avg_roe = float(_bank_cfg.get("roe_fallback", 0.15))
        if historical_bs and historical_is:
            # Cùng định nghĩa roe5/ROE ngành: VCSH bình quân, năm tài chính đầy đủ (bỏ TTM chưa trọn năm).
            _n_fy = len(historical_is) - (1 if ttm_partial else 0)
            roes = average_equity_roes(historical_is[:_n_fy], historical_bs[:_n_fy])
            if roes:
                import statistics as _stats

                avg_roe = _stats.median(roes[-_roe_window:])

        from valuation.engine.ttm_helper import _quarter_end

        # D62 cho P/B ngân hàng: kỳ TTM ghép giá cuối quý báo cáo (trước đây bỏ 1/5 quan sát).
        bank_pb_hist = pb_history_or_peer(
            db, ticker, historical_bs, shares,
            {int(latest_yr): _quarter_end(int(latest_yr), int(latest_q))} if mode == "TTM" else None,
            sector_plan.get("group"), as_of, peer_lookup, extraction_flags,
        )
        assumptions_bank = AssumptionsBank(
            risk_free_rate=rf_dynamic,
            beta=beta_dynamic,
            erp=erp_vn,
            credit_growth=credit_growth,
            nim=nim,
            cir=cir,
            credit_cost=credit_cost,
            # Ảnh chụp driver máy đặt: phần analyst/kịch bản sửa sau đó cộng lên đường phai ROE (forecast_bank).
            driver_base={"credit_growth": list(credit_growth), "nim": list(nim), "cir": list(cir),
                         "credit_cost": list(credit_cost)},
            dividend_payout_ratio=payout,
            terminal_growth_rate=terminal_growth(rf_dynamic),
            sustainable_roe=avg_roe,
            # Đích hội tụ ROE terminal theo nhóm routing.json. KHÔNG mượn nhóm NH cho TCTD phi ngân
            # hàng như beta: ROE là chỉ tiêu mô hình kinh doanh (EVF ROE 3 năm 6% so với NH 17%).
            # peer_lookup=False (đang dựng peer) → không hội tụ, tránh đệ quy.
            industry_roe=bank_industry_roe(db, sector_plan.get("group"), as_of) if peer_lookup else None,
            roe_convergence=float(_bank_cfg["roe_convergence"]),
            min_equity_to_assets=min_equity_to_assets,
            historical_pb_median=bank_pb_hist,
        )

        from valuation.data_access.freshness import data_freshness_flags

        data_flags = data_freshness_flags(db, ticker)
        data_flags.extend(undated_split_flags(db, ticker, as_of))
        data_flags.extend(extraction_flags)
        if credit_growth_capped:
            data_flags.append("CREDIT_GROWTH_CAPPED")
        if cc_spike:
            data_flags.append("BANK_CREDIT_COST_SPIKE")
        if leverage_above_history:
            data_flags.append("BANK_LEVERAGE_ABOVE_HISTORY")
        company_bank = CompanyBank(
            ticker=ticker,
            name=meta.company_name,
            current_price=current_price,
            shares_outstanding=shares,
            historical_is=historical_is,
            historical_bs=historical_bs,
            assumptions=assumptions_bank,
            data_flags=data_flags,
            last_period_is_ttm=ttm_partial,
        )
        # ROE bền vững = ROE năm 5 của chính dự phóng chuẩn hóa (không phải trung vị
        # lịch sử: cửa sổ ngắn bị một quý trích lập đột biến kéo sập, cửa sổ dài giữ
        # lại ROE cao đã phai). Trung vị lịch sử chỉ để đối chiếu.
        from valuation.engine.forecast_bank import driver_roe5

        roe5 = driver_roe5(company_bank)  # driver thuần, trước hội tụ (cùng hàm kịch bản D67 dùng)
        if roe5 is not None:
            if abs(roe5 - avg_roe) > float(_bank_cfg.get("roe_history_tolerance", 0.05)):
                data_flags.append("BANK_ROE_FORECAST_VS_HISTORY")
            company_bank.assumptions.sustainable_roe = roe5
        return company_bank
    else:
        # Phi tài chính: dùng MEDIAN (không phải mean) cho growth & margin.
        # Median robust với năm bùng nổ/sập → chính là biên/tăng trưởng MID-CYCLE,
        # đặc biệt quan trọng cho ngành cyclical (thép/hóa chất/dầu khí) tránh
        # extrapolate đỉnh chu kỳ ra vĩnh viễn (chống overvaluation hệ thống).
        import statistics

        med_growth = 0.10
        med_ebit_m = 0.15
        if len(historical_is) >= 2:
            growths = [
                (historical_is[i].revenue - historical_is[i - 1].revenue)
                / historical_is[i - 1].revenue
                for i in range(1, len(historical_is))
                if historical_is[i - 1].revenue > 0
            ]
            if growths:
                med_growth = statistics.median(growths)
            _win = int((config_defaults.get("forecast") or {}).get("margin_window_years", 4))
            ebits = [
                historical_is[i].ebit / historical_is[i].revenue
                for i in range(len(historical_is))
                if historical_is[i].revenue > 0
            ][-_win:]
            if ebits:
                med_ebit_m = statistics.median(ebits)
                # D61: trung vị ≤ 0 nhưng kỳ gần nhất có lãi (vd VPL sau COVID) → dùng biên kỳ gần nhất
                # thay vì ép về 0 (NOPAT = 0 vĩnh viễn).
                if med_ebit_m <= 0 < ebits[-1]:
                    med_ebit_m = ebits[-1]
        _fc = config_defaults.get("forecast", {}) or {}
        med_growth = min(
            max(med_growth, float(_fc.get("growth_floor", -0.10))),
            float(_fc.get("growth_cap", 0.25)),
        )
        med_ebit_m = max(med_ebit_m, 0.0)

        # Mức đầu tư CapEx, khấu hao và NWC.
        # capex_to_rev, depr_to_rev lấy TỪ DỮ LIỆU THẬT (median, robust ngoại lệ).
        # KHÔNG hardcode depr = 4%: mức đó bơm "tiền ảo" vào FCFF cho các DN nhẹ
        # tài sản (vd PNJ D&A thực ~0.2%, PLX ~0.7%) → overvaluation hệ thống.
        capex_to_rev = 0.05
        depr_to_rev = 0.04  # fallback chỉ dùng khi thiếu dữ liệu D&A

        if historical_cf and historical_is:
            # Ưu tiên capex 3 KỲ GẦN NHẤT (không median toàn lịch sử) — công ty
            # vừa qua đỉnh đầu tư (VD: HPG hậu Dung Quất 2, capex/DT lịch sử
            # 3%-49%) sẽ bị chiếu nhầm capex thời xây dựng cho cả 5 năm tới nếu
            # trộn lẫn với giai đoạn cũ. 3 kỳ = cùng cửa sổ với effective_tax
            # bên dưới, đủ mượt để không bị lệch bởi 1 kỳ TTM nhiễu.
            # Điều tra 2026-07, xem DECISIONS.md.
            recent_cf, recent_is = historical_cf[-3:], historical_is[-3:]
            capexs_recent = [
                cf.capex / is_rec.revenue
                for cf, is_rec in zip(recent_cf, recent_is)
                if is_rec.revenue > 0
            ]
            if capexs_recent:
                capex_to_rev = statistics.median(capexs_recent)
            else:
                capexs_all = [
                    cf.capex / is_rec.revenue
                    for cf, is_rec in zip(historical_cf, historical_is)
                    if is_rec.revenue > 0
                ]
                if capexs_all:
                    capex_to_rev = statistics.median(capexs_all)

            deprs = [
                cf.depreciation / is_rec.revenue
                for cf, is_rec in zip(historical_cf, historical_is)
                if is_rec.revenue > 0 and cf.depreciation > 0
            ]
            if deprs:
                depr_to_rev = statistics.median(deprs)

            dsos, dios, dpos = [], [], []
            for bs, is_rec in zip(historical_bs, historical_is):
                if is_rec.revenue > 0:
                    dsos.append((bs.receivables / is_rec.revenue) * 365)
                if is_rec.cogs > 0:
                    dios.append((bs.inventory / is_rec.cogs) * 365)
                    dpos.append((bs.accounts_payable / is_rec.cogs) * 365)

            dso_avg = sum(dsos) / len(dsos) if dsos else 30.0
            dio_avg = sum(dios) / len(dios) if dios else 30.0
            dpo_avg = sum(dpos) / len(dpos) if dpos else 30.0
            # Chỉ mã khai báo DR là nợ vận hành gắn doanh thu (KCN cho thuê — SIP); mã khác 0 (PHR: đền bù đất).
            dr_ratio = (
                marginal_deferred_revenue_ratio(
                    historical_bs, historical_is,
                    int((config_defaults.get("forecast") or {}).get("margin_window_years", 4)),
                )
                if ticker in (config_defaults["dcf"].get("deferred_revenue_operating_tickers") or [])
                else 0.0
            )

        # --- B5 FIX: Đọc tax_rate và ev_ebitda từ config theo sector ---
        # (không hardcode per-ticker, vi phạm AGENTS.md no-magic-numbers)
        sector_str = (meta.sector or "").lower()

        # GUARDRAIL CYCLICAL (G3): ngành chu kỳ → terminal margin ép về mid-cycle.
        _CYCLICAL_KW = (
            "steel",
            "metal",
            "chemical",
            "oil",
            "gas",
            "petroleum",
            "fuel",
            "resource",
            "shipping",
            "rubber",
            "fertil",
        )
        is_cyclical = any(k in sector_str for k in _CYCLICAL_KW)
        mid_cycle_margin = med_ebit_m if is_cyclical else None

        # 1. Effective tax rate = Σthuế/ΣLNTT báo cáo của 3 năm tài chính ĐẦY ĐỦ có lãi gần nhất
        # (bỏ kỳ TTM: chồng quý với năm trước). Thiếu dòng LNTT → cách cũ (EBIT − lãi vay) + cờ.
        _tax_lo, _tax_hi = config_defaults["dcf"]["effective_tax_band"]
        _tax_from_pbt = effective_tax_rate(
            historical_is[:-1] if ttm_partial else historical_is
        )
        _tax_rates_hist = []
        if _tax_from_pbt is None:
            if not financial_sector:  # CTCK/BH: mô hình P/B, RI không dùng thuế suất này
                extraction_flags.append("TAX_FALLBACK_EBIT")
            for _is in historical_is[-3:]:
                _pbt = _is.ebit - _is.interest_expense
                if _pbt > 0 and _is.tax > 0:
                    _tax_rates_hist.append(_is.tax / _pbt)
        if _tax_from_pbt is not None:
            effective_tax = _tax_from_pbt
        elif len(_tax_rates_hist) >= 2:
            effective_tax = min(
                max(sum(_tax_rates_hist) / len(_tax_rates_hist), _tax_lo), _tax_hi
            )
        else:
            _sector_tax_map = config_defaults.get("sector_tax_rates", {})
            if any(k in sector_str for k in ["tech", "information", "software"]):
                effective_tax = _sector_tax_map.get("technology", 0.20)
            elif any(k in sector_str for k in ["industrial", "zone"]):
                effective_tax = _sector_tax_map.get("industrial_zone", 0.20)
            elif any(k in sector_str for k in ["agri", "food"]):
                effective_tax = _sector_tax_map.get("agriculture", 0.20)
            else:
                effective_tax = _sector_tax_map.get("default", 0.20)

        # 2. EV/EBITDA target: ƯU TIÊN nhóm từ routing.json (nguồn sự thật ngành
        # — D14), fallback keyword trên DB sector. Tránh lỗi ngành DB rộng
        # "Industrial Goods & Services" (gồm vận tải/cảng như PVT/HAH) bị khớp
        # nhầm 'industrial' → industrial_zone (12x) → định giá phóng đại.
        _ev_map = config_defaults.get("sector_ev_ebitda", {})
        _GROUP_EV_KEY = {
            "Thép": "steel",
            "Dầu khí": "oil_gas",
            "Hàng không": "aviation",
            "Cảng": "transport",
            "Vận tải": "transport",
            "Hàng hải": "transport",
            "Điện": "utilities",
            "Nước": "utilities",
            "Tiện ích": "utilities",
            "Công nghệ": "technology",
            "Bán lẻ": "retail",
            "Tiêu dùng": "consumer",
            "Dược": "consumer",
            "KCN": "industrial_zone",
            "BĐS": "real_estate",
            "Cao su/NN": "agriculture",
        }
        _ev_ebitda_from_group = None
        try:
            from valuation.engine.sector_router import route as _route_lookup

            _grp = (_route_lookup(ticker) or {}).get("group")
            _key = _GROUP_EV_KEY.get(_grp)
            if _key and _ev_map.get(_key) is not None:
                _ev_ebitda_from_group = _ev_map.get(_key)
        except Exception:
            _ev_ebitda_from_group = None

        _depr = {cf.year: cf.depreciation for cf in historical_cf}
        from valuation.engine.ttm_helper import _quarter_end

        _ttm_end = {int(latest_yr): _quarter_end(int(latest_yr), int(latest_q))} if mode == "TTM" else None
        # Chỉ tính/gắn cờ bội số mà phương pháp route() thực sự đọc (RNAV/SOTP/PB không đọc
        # target_ev_ebitda/target_pe; EV/EBITDA, P/E vô nghĩa với CTCK/bảo hiểm — CFA).
        _pre_issue_ex = sector_plan.get("group") in (
            config_defaults["relative_multiples"]["capital_raise_exclusion_groups"] or []
        )
        uses_ev, uses_pe = multiples_used(
            sector_plan,
            jv_valued=historical_is[-1].jv_income > 0
            and min(historical_bs[-1].investments_in_associates, historical_bs[-1].long_term_investments_net) > 0,
        )
        ev_hist = (
            own_history_multiple(
                db, ticker,
                {i.year: i.ebit + _depr.get(i.year, 0.0) for i in historical_is},
                shares,
                # EV HOẠT ĐỘNG (loại XDCB dở dang từng năm): không loại thì bội số 2024 của HPG chứa 63.656 tỷ
                # Dung Quất 2 chưa có EBITDA, cộng CIP hiện tại ở cầu nối thành đếm trùng.
                adjustments={b.year: operating_ev_bridge(b) for b in historical_bs},
                kind="ev_ebitda",
                period_end=_ttm_end,
                as_of=as_of,
                flags=extraction_flags,
                exclude_pre_issue=_pre_issue_ex,
            )
            if uses_ev
            else None
        )
        pe_hist = (
            own_history_multiple(
                db, ticker, {i.year: i.net_income for i in historical_is}, shares, kind="pe",
                period_end=_ttm_end, as_of=as_of, flags=extraction_flags, exclude_pre_issue=_pre_issue_ex,
            )
            if uses_pe
            else None
        )
        # D62: thiếu lịch sử → trung vị bội số hiện hành của nhóm ngành thay vì hằng số cấu hình.
        if peer_lookup and ((uses_ev and ev_hist is None) or (uses_pe and pe_hist is None)):
            _peer = sector_peer_multiples(db, ticker, sector_plan.get("group"), as_of)
            if uses_ev and ev_hist is None and _peer["ev_ebitda"] is not None:
                ev_hist = _peer["ev_ebitda"]
                extraction_flags.append(f"MULTIPLE_FROM_PEER_MEDIAN:ev_ebitda={ev_hist:.1f}x")
            if uses_pe and pe_hist is None and _peer["pe"] is not None:
                pe_hist = _peer["pe"]
                extraction_flags.append(f"MULTIPLE_FROM_PEER_MEDIAN:pe={pe_hist:.1f}x")
        if (uses_ev and ev_hist is None) or (uses_pe and pe_hist is None):
            extraction_flags.append("MULTIPLE_FROM_SECTOR_CONSTANT")

        if ev_hist is not None:
            ev_ebitda_target = ev_hist
        elif _ev_ebitda_from_group is not None:
            ev_ebitda_target = _ev_ebitda_from_group
        elif any(k in sector_str for k in ["tech", "information", "software"]):
            ev_ebitda_target = _ev_map.get("technology", 7.0)
        elif any(k in sector_str for k in ["real", "estate", "property"]):
            ev_ebitda_target = _ev_map.get("real_estate", 7.0)
        elif any(k in sector_str for k in ["steel", "metal", "material"]):
            ev_ebitda_target = _ev_map.get("steel", 7.0)
        elif any(k in sector_str for k in ["consumer", "food", "beverage"]):
            ev_ebitda_target = _ev_map.get("consumer", 7.0)
        elif any(k in sector_str for k in ["retail", "wholesale"]):
            ev_ebitda_target = _ev_map.get("retail", 7.0)
        elif any(k in sector_str for k in ["oil", "petroleum", "fuel"]):
            # Phân phối/lọc dầu (PLX, BSR): biên mỏng, commodity → multiple thấp.
            # PHẢI đứng trước nhánh utilities vì "oil & gas" chứa 'gas'.
            ev_ebitda_target = _ev_map.get("oil_gas", 6.0)
        elif any(k in sector_str for k in ["travel", "airline", "aviation", "leisure"]):
            ev_ebitda_target = _ev_map.get("aviation", 6.0)
        elif any(k in sector_str for k in ["util", "electric", "power", "gas"]):
            ev_ebitda_target = _ev_map.get("utilities", 7.0)
        elif any(k in sector_str for k in ["industrial", "zone"]):
            ev_ebitda_target = _ev_map.get("industrial_zone", 7.0)
        else:
            ev_ebitda_target = _ev_map.get("default", 7.0)
        if ev_ebitda_target is None:
            ev_ebitda_target = 7.0

        # Revenue growth FADE từ median lịch sử (năm 1) về ĐÚNG g vĩnh viễn (năm 5):
        # neo cũ 8% rồi rơi xuống g ở năm 6 là vách đứng tự mâu thuẫn.
        g_lt = terminal_growth(rf_dynamic)

        # D32 — NĂM GỐC DỰ PHÓNG (sau cờ, mặc định TRAILING = y hệt hành vi cũ).
        # Mô hình vốn dựng năm 1 từ median tăng trưởng LỊCH SỬ, tức nhìn hoàn toàn
        # về quá khứ, trong khi CTCK định giá trên dự phóng FY+1 — nguồn gốc khoảng
        # lệch âm cấu trúc của nhóm DCF (-30%).
        _fwd_flags: List[str] = []
        _fy1_growth = med_growth
        from valuation.forecast.base_year import (
            base_year_mode,
            build_forward_base,
            revenue_growth_path,
        )

        if base_year_mode() == "FORWARD":
            _q_rev = _quarterly_revenues(db, ticker)
            _fwd = build_forward_base(
                _q_rev, med_growth, sector_group=_sector_for_overlay
            )
            _fy1_growth = _fwd.fy1_revenue_growth
            _fwd_flags = list(_fwd.flags)
            if _fwd.method == "QUARTERLY_MOMENTUM":
                _fwd_flags.append(
                    f"FWD_BASE_YEAR: năm 1 {med_growth:+.1%} (median lịch sử) -> "
                    f"{_fy1_growth:+.1%} (động lượng 4 quý)"
                )
        revenue_growth = revenue_growth_path(_fy1_growth, g_lt, years=5)
        revenue_growth = overlay_revenue_growth(
            revenue_growth, _sector_for_overlay, _macro_ctx
        )

        # Ước lượng debt_repayment_rate và new_borrowing_rate từ lịch sử
        debt_repay_default = 0.20
        new_borrow_default = 0.05
        if len(historical_bs) >= 2 and len(historical_is) >= 2:
            _repay_rates = []
            _borrow_rates = []
            for j in range(1, len(historical_bs)):
                prev_total_debt = (
                    historical_bs[j - 1].short_term_debt
                    + historical_bs[j - 1].long_term_debt
                )
                curr_total_debt = (
                    historical_bs[j].short_term_debt + historical_bs[j].long_term_debt
                )
                curr_rev = historical_is[j].revenue
                if prev_total_debt > 0:
                    # Nếu nợ giảm → có trả nợ ròng
                    net_change = curr_total_debt - prev_total_debt
                    if net_change < 0:
                        _repay_rates.append(abs(net_change) / prev_total_debt)
                    else:
                        _repay_rates.append(debt_repay_default)
                if curr_rev > 0:
                    net_change = curr_total_debt - prev_total_debt
                    if net_change > 0:
                        _borrow_rates.append(net_change / curr_rev)
                    else:
                        _borrow_rates.append(new_borrow_default)
            if _repay_rates:
                debt_repay_default = min(
                    max(sum(_repay_rates) / len(_repay_rates), 0.05), 0.50
                )
            if _borrow_rates:
                new_borrow_default = min(
                    max(sum(_borrow_rates) / len(_borrow_rates), 0.0), 0.20
                )

        # D45 — CapEx/DT lịch sử giữ phẳng 5 năm trong khi tăng trưởng fade về g là mâu
        # thuẫn (GMD 28% suốt kỳ = vẫn đầu tư như pha mở rộng mà không tăng trưởng).
        # Dựng CapEx từ doanh thu trên vốn của chính DN; không tính được → giữ lịch sử.
        _bs0, _is0 = historical_bs[-1], historical_is[-1]
        s2c = sales_to_capital(
            _is0.revenue,
            _bs0.total_equity,
            _bs0.short_term_debt + _bs0.long_term_debt,
            _bs0.cash_and_equivalents,
            _bs0.short_term_financial_investments,
            _bs0.long_term_investments_net,
            cip=_bs0.construction_in_progress,
        )
        if s2c is not None:
            _cogs_ratio = _is0.cogs / _is0.revenue if _is0.revenue > 0 else 0.0
            # Vốn vận hành của s2c (phía nguồn vốn) đã trừ doanh thu chưa thực hiện → NWC ở đây cũng trừ,
            # để tái đầu tư ròng vẫn đúng ΔDT/s2c (không đếm trùng tiền trả trước).
            _nwc_ratio = dso_avg / 365 + _cogs_ratio * (dio_avg - dpo_avg) / 365 - dr_ratio
            capex_schedule = growth_consistent_capex(revenue_growth, depr_to_rev, _nwc_ratio, s2c)
        else:
            capex_schedule = [capex_to_rev] * 5

        assumptions = Assumptions(
            risk_free_rate=rf_dynamic,
            beta=beta_dynamic,
            erp=erp_vn,
            cost_of_debt=rf_dynamic + 0.03,
            tax_rate=effective_tax,
            revenue_growth=revenue_growth,
            ebit_margin=[med_ebit_m] * 5,
            mid_cycle_ebit_margin=mid_cycle_margin,
            capex_to_revenue=capex_schedule,
            sales_to_capital=s2c,
            depr_to_revenue=[depr_to_rev] * 5,
            dso=[dso_avg] * 5,
            dio=[dio_avg] * 5,
            dpo=[dpo_avg] * 5,
            deferred_revenue_to_revenue=dr_ratio,
            interest_rate=[rf_dynamic + 0.03] * 5,
            debt_repayment_rate=[debt_repay_default] * 5,
            new_borrowing_rate=[new_borrow_default] * 5,
            terminal_growth_rate=terminal_growth(rf_dynamic),
            historical_pb_median=(
                pb_history_or_peer(
                    db, ticker, historical_bs, shares, _ttm_end,
                    sector_plan.get("group"), as_of, peer_lookup, extraction_flags,
                )
                if financial_sector
                else None
            ),
            target_ev_ebitda=ev_ebitda_target,
            target_pe=pe_hist,
            weight_dcf=sector_plan.get("weight", 0.5),  # trọng số DCF theo routing.json
            # Chỉ mã định tuyến SOTP mới đọc holdings; peer_lookup=False (đang dựng peer/công ty con) → bỏ qua.
            sotp_holdings=(
                resolve_sotp_holdings(db, ticker, as_of)
                if peer_lookup and sector_plan.get("method") == "SOTP"
                else None
            ),
        )

        from valuation.data_access.freshness import data_freshness_flags

        return Company(
            ticker=ticker,
            name=meta.company_name,
            sector=meta.sector or "Unknown",
            current_price=current_price,
            shares_outstanding=shares,
            historical_is=historical_is,
            historical_bs=historical_bs,
            historical_cf=historical_cf,
            assumptions=assumptions,
            data_flags=data_freshness_flags(db, ticker) + extraction_flags
            + undated_split_flags(db, ticker, as_of),
        )


def compute_midcycle_ebit_margin(db: Session, ticker: str) -> float | None:
    """
    Biên EBIT MID-CYCLE = median của (EBIT/Doanh thu) qua các năm lịch sử.
    Dùng cho guardrail G3: terminal margin ngành cyclical ép về mức này, không
    ngoại suy biên đỉnh. Trả None nếu không đủ dữ liệu.
    """
    import statistics

    try:
        company = build_company_data(db, ticker, mode="FY")
    except Exception:
        return None
    if not isinstance(company, Company):
        return None
    margins = [
        is_.ebit / is_.revenue
        for is_ in company.historical_is
        if is_.revenue and is_.revenue > 0
    ]
    return statistics.median(margins) if margins else None
