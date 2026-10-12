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
from valuation.db.models import FinancialsQuarterly, PricesDaily, Ticker
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
    return result


def _source_audit_flags(
    audit: dict | None, ticker: str, mapping_version: str
) -> list[str]:
    if not audit:
        return ["SOURCE_AUDIT_MISSING"]
    if audit.get("mapping_version") != mapping_version:
        return ["SOURCE_AUDIT_STALE"]
    row = next(
        (item for item in audit.get("rows", []) if item.get("ticker") == ticker), None
    )
    if not row:
        return ["SOURCE_AUDIT_MISSING"]
    flags = []
    if row.get("source_contract_errors", 0):
        flags.append(f"SOURCE_CONTRACT_ERROR:{row['source_contract_errors']}")
    if row.get("CRITICAL_CONFLICT", 0):
        flags.append(f"SOURCE_CONFLICT:{row['CRITICAL_CONFLICT']}")
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
        "tax": abs(tax),
        "net_income": ni,
    }


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
    cash: float, st_investments: float, receivables: float, inventory: float, other: float
) -> bool:
    """Phần dư "tài sản ngắn hạn khác" chiếm tỷ trọng bất thường → thường là dòng bị mất
    khi nạp (FPT từng mất ~31 nghìn tỷ tiền gửi: phần dư 53% tài sản ngắn hạn)."""
    total = cash + st_investments + receivables + inventory + other
    share = float((load_defaults().get("audit") or {}).get("unexplained_current_assets_share", 0.35))
    return total > 0 and other / total > share


def normalized_credit_cost(ttm: float, median: float, spike_multiple: float) -> tuple[float, bool]:
    """Chi phí tín dụng dự phóng = max(TTM, trung vị chu kỳ); TTM > spike_multiple × trung vị
    coi là trích lập đột biến một lần → giữ trung vị, trả cờ (D47)."""
    if median > 0 and ttm > spike_multiple * median:
        return median, True
    return max(ttm, median), False


def sales_to_capital(
    revenue: float, equity: float, debt: float, cash: float, st_investments: float, lt_investments: float
) -> float | None:
    """Doanh thu / vốn đầu tư vận hành (Damodaran). Vốn vận hành = VCSH + nợ vay − tiền −
    đầu tư ngắn hạn − đầu tư dài hạn (tài sản ngoài hoạt động). ≤ 0 → None; kẹp theo dải cấu hình."""
    capital = equity + debt - cash - st_investments - lt_investments
    if capital <= 0 or revenue <= 0:
        return None
    lo, hi = (load_defaults().get("dcf") or {}).get("sales_to_capital_band", [0.3, 5.0])
    return min(max(revenue / capital, lo), hi)


def growth_consistent_capex(
    growth: list[float], depr_ratio: float, nwc_ratio: float, s2c: float
) -> list[float]:
    """CapEx/DT từng năm sao cho tái đầu tư ròng = Δdoanh thu / (doanh thu trên vốn):
    CapEx = khấu hao + ΔDT × (1/s2c − vốn lưu động/DT) (vốn vận hành đã gồm vốn lưu động).
    Sàn = khấu hao: CapEx duy trì không thấp hơn hao mòn, kể cả năm doanh thu giảm."""
    return [
        max(depr_ratio, depr_ratio + g / (1 + g) * (1 / s2c - nwc_ratio)) for g in growth
    ]


def own_history_multiple(
    db: Session,
    ticker: str,
    denominators: Dict[int, float],
    shares_m: float,
    adjustments: Dict[int, float] | None = None,
    years: int = 5,
    kind: str | None = None,
) -> float | None:
    """Trung vị (vốn hóa cuối năm + điều chỉnh) / mẫu số các năm gần nhất của CHÍNH mã.

    P/B: mẫu số VCSH mẹ; P/E: LN mẹ > 0; EV/EBITDA: điều chỉnh = nợ ròng + CĐKKS −
    đầu tư dài hạn, mẫu số EBITDA > 0. Cần ≥ 3 năm quan sát HỢP LỆ.
    `kind` ("pe"/"ev_ebitda"): bỏ từng quan sát ngoài dải `relative_multiples` TRƯỚC khi
    lấy trung vị — năm LN đáy cho P/E 120x+ phản ánh mẫu số méo, không phải giá thị trường
    trả (CTD: trung vị 27,9x → áp lên LN phục hồi ra FV gấp 3 thị giá).
    Giá đã điều chỉnh quyền × số cp hiện tại = vốn hóa lịch sử khi các sự kiện là
    cổ tức CP/thưởng. ponytail: phát hành thêm có thu tiền (quyền mua, riêng lẻ)
    làm bội số năm cũ hơi cao; cần chuỗi số cp lịch sử + giá thô nếu muốn chính xác.
    """
    import datetime
    import statistics

    lo, hi = (
        (load_defaults().get("relative_multiples", {}) or {}).get(kind, [0.0, float("inf")])
        if kind
        else (float("-inf"), float("inf"))
    )
    vals = []
    for y in sorted(denominators)[-years:]:
        den = denominators[y]
        row = (
            db.query(PricesDaily.close)
            .filter(
                PricesDaily.ticker == ticker,
                PricesDaily.trade_date >= datetime.date(y, 12, 1),
                PricesDaily.trade_date <= datetime.date(y, 12, 31),
            )
            .order_by(PricesDaily.trade_date.desc())
            .first()
        )
        if row and row[0] and den > 0:
            mcap = float(row[0]) * shares_m / 1e3  # tỷ đồng
            multiple = (mcap + (adjustments or {}).get(y, 0.0)) / den
            if lo <= multiple <= hi:
                vals.append(multiple)
    return statistics.median(vals) if len(vals) >= 3 else None


def get_shares_outstanding_repo(db: Session, ticker: str, as_of=None) -> float:
    """Lấy số lượng cổ phiếu lưu hành (đổi sang triệu cổ phiếu)."""
    from valuation.engine.ttm_helper import get_shares_outstanding

    shares = get_shares_outstanding(db, ticker, as_of_date=as_of)
    if shares <= 0:
        raise ValueError(f"Số lượng cổ phiếu không hợp lệ cho {ticker}: {shares}")
    # ttm_helper trả về số cp thô (ví dụ: 8,355,675,094).
    return shares / 1e6


def build_company_data(
    db: Session, ticker: str, mode: str = "TTM", fetch_live: bool = False, as_of=None
) -> Union[Company, CompanyBank]:
    """
    Truy vấn dữ liệu tài chính lịch sử, quy đổi kỳ báo cáo và đơn vị,
    trả về đối tượng Pydantic Company (phi tài chính) hoặc CompanyBank (ngân hàng).
    """
    meta = load_ticker_metadata(db, ticker)
    if not meta:
        raise ValueError(f"Không tìm thấy ticker {ticker} trong DB")

    is_bank = meta.sector == "Banks"
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
    if as_of is not None:
        _lag = load_defaults().get("publication_lag_days", {}) or {}
        records = [r for r in records if _published_by(r.fiscal_year, r.fiscal_quarter, as_of, _lag)]
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
    df_fin = pd.DataFrame(fin_data)

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

    historical_is = []
    historical_bs = []
    historical_cf = []
    extraction_flags = []
    bank_div_paid: Dict[int, float] = {}
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
            _source_audit_flags(audit, ticker, taxonomy_mapping()["version"])
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
            prov = abs(
                _required_value(
                    annual_data, BANK_KEYWORDS["provision_expense"], "provision_expense"
                )
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
            lt_debt = _match_value(annual_data, NON_FIN_KEYWORDS["lt_debt"])
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
                    cash, short_term_financial_investments, rec, inv,
                    # phần dư "khác" đã GỒM ĐTNH → trừ ra để chỉ còn phần không giải thích được
                    other_curr_assets - short_term_financial_investments,
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
                )
            )

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
                    is_ttm_period=(mode == "TTM" and y == latest_yr),
                )
            )

    # 3. Tính toán giả định base case động
    rf_dynamic = get_latest_tpcp_10y(db)
    beta_dynamic = estimate_vcb_beta(db, ticker)
    if is_bank:
        # D47: beta ngành ngân hàng (trung vị Blume nhóm NH VN100) thay beta hồi quy riêng.
        from valuation.engine.ttm_helper import bank_peer_beta

        beta_dynamic = bank_peer_beta(db)

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

        # Declining schedules
        credit_growth = [
            cg_val,
            cg_val - 0.01,
            cg_val - 0.02,
            cg_val - 0.02,
            max(cg_val - 0.03, 0.08),
        ]
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
        # tín dụng = trung vị chu kỳ (cùng cửa sổ ROE): nhìn xuyên đột biến trích lập một
        # lần (STB/EIB Q4/2025) nhưng vẫn phản ánh mức trích lập thấp kéo dài.
        annual_cc = [
            historical_is[i].provision_expense
            / ((historical_bs[i - 1].customer_loans + historical_bs[i].customer_loans) / 2)
            for i in range(1, len(historical_bs))
            if historical_bs[i - 1].customer_loans + historical_bs[i].customer_loans > 0
        ]
        _cc_window = int((config_defaults.get("bank_terminal", {}) or {}).get("credit_cost_window", 3))
        _bank_cfg_cc = config_defaults.get("bank_terminal", {}) or {}
        _fy_cc = annual_cc[:-1] if mode == "TTM" else annual_cc
        cc_median = _stats.median(_fy_cc[-_cc_window:]) if _fy_cc else cc_val
        # D47: TTM nếu cao hơn trung vị (trích lập đang tăng), trừ khi đột biến một lần.
        cc_norm, cc_spike = normalized_credit_cost(
            annual_cc[-1] if (mode == "TTM" and annual_cc) else cc_median, cc_median,
            float(_bank_cfg_cc.get("credit_cost_spike_multiple", 2.0)),
        )
        nim = [nim_val] * 5
        cir = [cir_val] * 5
        credit_cost = [cc_norm] * 5
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
            roes = [
                historical_is[i].net_income / historical_bs[i].total_equity
                for i in range(len(historical_bs))
                if historical_bs[i].total_equity > 0
            ]
            if roes:
                import statistics as _stats

                avg_roe = _stats.median(roes[-_roe_window:])

        assumptions_bank = AssumptionsBank(
            risk_free_rate=rf_dynamic,
            beta=beta_dynamic,
            erp=erp_vn,
            credit_growth=credit_growth,
            nim=nim,
            cir=cir,
            credit_cost=credit_cost,
            dividend_payout_ratio=payout,
            terminal_growth_rate=terminal_growth(rf_dynamic),
            sustainable_roe=avg_roe,
            min_equity_to_assets=min_equity_to_assets,
            historical_pb_median=own_history_multiple(
                db, ticker, {b.year: b.parent_equity for b in historical_bs}, shares
            ),
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
        )
        # ROE bền vững = ROE năm 5 của chính dự phóng chuẩn hóa (không phải trung vị
        # lịch sử: cửa sổ ngắn bị một quý trích lập đột biến kéo sập, cửa sổ dài giữ
        # lại ROE cao đã phai). Trung vị lịch sử chỉ để đối chiếu.
        from valuation.engine.forecast_bank import forecast_bank_financials

        _proj = forecast_bank_financials(company_bank)
        _eq_avg = (_proj[-2]["total_equity"] + _proj[-1]["total_equity"]) / 2
        if _eq_avg > 0:
            roe5 = _proj[-1]["net_income"] / _eq_avg
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
            ebits = [
                historical_is[i].ebit / historical_is[i].revenue
                for i in range(len(historical_is))
                if historical_is[i].revenue > 0
            ]
            if ebits:
                med_ebit_m = statistics.median(ebits)
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

        # 1. Effective tax rate: ưu tiên tính từ lịch sử >= 3 năm
        _tax_rates_hist = []
        for _is in historical_is[-3:]:
            _pbt = _is.ebit - _is.interest_expense
            if _pbt > 0 and _is.tax > 0:
                _tax_rates_hist.append(_is.tax / _pbt)
        if len(_tax_rates_hist) >= 2:
            effective_tax = min(
                max(sum(_tax_rates_hist) / len(_tax_rates_hist), 0.05), 0.25
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
        ev_hist = (
            own_history_multiple(
                db, ticker,
                {i.year: i.ebit + _depr.get(i.year, 0.0) for i in historical_is},
                shares,
                adjustments={
                    b.year: b.short_term_debt + b.long_term_debt - b.cash_and_equivalents
                    - b.short_term_financial_investments + b.minority_interest
                    - b.long_term_investments_net
                    for b in historical_bs
                },
                kind="ev_ebitda",
            )
        )
        pe_hist = own_history_multiple(
            db, ticker, {i.year: i.net_income for i in historical_is}, shares, kind="pe"
        )
        if ev_hist is None or pe_hist is None:
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
        )
        if s2c is not None:
            _cogs_ratio = _is0.cogs / _is0.revenue if _is0.revenue > 0 else 0.0
            _nwc_ratio = dso_avg / 365 + _cogs_ratio * (dio_avg - dpo_avg) / 365
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
            interest_rate=[rf_dynamic + 0.03] * 5,
            debt_repayment_rate=[debt_repay_default] * 5,
            new_borrowing_rate=[new_borrow_default] * 5,
            terminal_growth_rate=terminal_growth(rf_dynamic),
            historical_pb_median=(
                own_history_multiple(
                    db, ticker, {b.year: b.parent_equity for b in historical_bs}, shares
                )
                if financial_sector
                else None
            ),
            target_ev_ebitda=ev_ebitda_target,
            target_pe=pe_hist,
            weight_dcf=0.5,
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
