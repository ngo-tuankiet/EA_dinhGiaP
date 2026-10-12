"""Hồ sơ xếp hạng chỉ đọc DB; không sửa giả định hoặc BCTC đã lưu."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from valuation.analysis.investment_ranking import finite
from valuation.config import PROJECT_ROOT
from valuation.data_access.repo import build_company_data
from valuation.db.models import FinancialsQuarterly, PricesDaily, Ticker
from valuation.engine.sector_router import route
from valuation.engine.sensitivity import apply_scenario_adjustments
from valuation.engine.valuate import valuate
from valuation.models.financials_bank import CompanyBank
from valuation.models.macro_env import MacroEnvironment
from valuation.report.verified_summary import run_deterministic_checks
from valuation.ingest.sponsor_data import sponsor_market_metrics
from valuation.services.ranking_store import read_json


def fingerprint(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, default=str
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def traded_values(prices: list[Any]) -> list[float]:
    """GTGD từng phiên. Cột `value` trống (vnstock không trả) → ước lượng giá đóng cửa × khối lượng.

    Trước đây chỉ đọc `value` → không mã nào đủ 20 phiên → mọi mã "thanh khoản không đạt" (D56).
    """
    out = []
    for x in prices:
        if x.value is not None and x.value > 0:
            out.append(float(x.value))
        elif x.close and x.volume:
            out.append(float(x.close) * float(x.volume))
    return out


def previous_session_day(today: date) -> date:
    """Chỉ dùng phiên đã kết thúc trước ngày chạy, tránh giá dở phiên lúc 09:30."""
    day = today - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def verified_evidence(raw: dict, as_of: date, input_hash: str, cfg: dict) -> dict:
    """Hồ sơ do analyst duyệt phải có ngày, nguồn và gắn đúng đầu vào định giá."""
    try:
        reviewed = date.fromisoformat(raw["reviewed_on"])
        sources = raw["sources"]
        valid = (
            0 <= (as_of - reviewed).days <= cfg["evidence_max_age_days"]
            and bool(raw.get("reviewer"))
            and bool(sources)
            and all(
                urlparse(s["url"]).scheme == "https" and s.get("title") for s in sources
            )
        )
    except (KeyError, TypeError, ValueError):
        return {}
    if not valid:
        return {}
    if any(
        not finite(value) or not 0 <= value <= 100
        for value in raw.get("scores", {}).values()
    ):
        return {}
    result = dict(raw)
    golden = raw.get("golden", {})
    result["golden_verified"] = (
        golden.get("input_hash") == input_hash
        and finite(golden.get("relative_error"))
        and 0 <= golden["relative_error"] < cfg["golden_tolerance"]
        and bool(golden.get("reference_url"))
    )
    return result


def financial_metrics(company: Any, as_of: date) -> dict:
    """Dùng FY đã hoàn thành cho tăng trưởng; không ghép TTM với FY chồng kỳ."""
    bank = isinstance(company, CompanyBank)
    annual = sorted(
        [x for x in company.historical_is if x.year < as_of.year], key=lambda x: x.year
    )
    balances = {x.year: x for x in company.historical_bs if x.year < as_of.year}
    cashflows = {
        x.year: x for x in getattr(company, "historical_cf", []) if x.year < as_of.year
    }
    result: dict[str, Any] = {"history_years": len(annual)}
    if not annual:
        return result
    latest = annual[-1]
    balance, previous = balances.get(latest.year), balances.get(latest.year - 1)
    revenue_key = "total_operating_income" if bank else "revenue"
    first = annual[max(0, len(annual) - 4)]
    start, end = getattr(first, revenue_key), getattr(latest, revenue_key)
    years = latest.year - first.year
    if start > 0 and end > 0 and years > 0:
        result["revenue_cagr"] = (end / start) ** (1 / years) - 1
    if balance and previous and min(balance.parent_equity, previous.parent_equity) > 0:
        result["roe"] = latest.net_income / (
            (balance.parent_equity + previous.parent_equity) / 2
        )
    if not bank and balance and balance.total_equity > 0:
        debt = balance.short_term_debt + balance.long_term_debt
        # Giá trị 0 có thể là mặc định của mapper, không suy ra doanh nghiệp không nợ.
        result["debt_to_equity"] = debt / balance.total_equity if debt > 0 else None
        cf = cashflows.get(latest.year)
        if cf and cf.cfo != 0 and latest.net_income > 0:
            result["cash_conversion"] = cf.cfo / latest.net_income
    result["metric_period"] = f"FY{latest.year}"
    return result


def build_ranking_row(
    db: Session, ticker: str, as_of: date, cfg: dict, evidence: dict
) -> dict:
    meta = db.get(Ticker, ticker)
    routing = route(ticker) or {}
    row: dict[str, Any] = {
        "ticker": ticker,
        "name": meta.company_name if meta else ticker,
        "sector": routing.get("group") or (meta.sector if meta else "Chưa rõ"),
        "method": routing.get("method", "Chưa rõ"),
        "flags": [],
        "blockers": [],
    }
    if not meta or not routing:
        row["error"] = "Thiếu metadata hoặc phương pháp đúng ngành"
        return row
    prices = (
        db.query(PricesDaily)
        .filter(
            PricesDaily.ticker == ticker,
            PricesDaily.trade_date <= previous_session_day(as_of),
            PricesDaily.close > 0,
        )
        .order_by(PricesDaily.trade_date.desc())
        .limit(20)
        .all()
    )
    if not prices or prices[0].price_unit != "VND":
        row["error"] = "Thiếu giá đóng cửa đúng đơn vị VND"
        return row
    price = float(prices[0].close)
    if not finite(price) or price <= 0:
        row["error"] = "Giá đóng cửa không phải số hữu hạn dương"
        return row
    row.update(
        price=price,
        price_date=prices[0].trade_date.isoformat(),
        price_source="prices_daily / vnstock",
        price_cutoff=previous_session_day(as_of).isoformat(),
    )
    if (as_of - prices[0].trade_date).days > cfg["price_max_age_days"]:
        row["blockers"].append("Giá đã cũ")
    rows = (
        db.query(FinancialsQuarterly).filter(FinancialsQuarterly.ticker == ticker).all()
    )
    if any(x.published_at and x.published_at > as_of for x in rows):
        row["error"] = "BCTC có ngày công bố tương lai; cần kiểm tra nguồn"
        return row
    known_dates = [x.published_at for x in rows if x.published_at]
    period = max(((x.fiscal_year, x.fiscal_quarter) for x in rows), default=(0, 0))
    row["financial_period"] = f"{period[0]} Q{period[1]}"
    row["financial_published"] = max(known_dates).isoformat() if known_dates else None
    row["financial_sources"] = sorted({x.source for x in rows if x.source})
    row["publication_coverage_pct"] = (
        round(100 * len(known_dates) / len(rows), 1) if rows else 0
    )
    current_dates = [x.published_at for x in rows if x.published_at and (x.fiscal_year, x.fiscal_quarter) == period]
    if not current_dates:
        row["blockers"].append("Kỳ BCTC mới nhất chưa có ngày công bố được lưu; chưa xác minh độ mới")
    elif (as_of - max(current_dates)).days > cfg["financial_max_age_days"]:
        row["blockers"].append("Ngày công bố kỳ BCTC mới nhất đã quá hạn kiểm tra")
    if len(known_dates) != len(rows):
        row["blockers"].append("Chưa đủ ngày công bố để kiểm chứng toàn bộ lịch sử")
    if any(not x.is_consolidated or x.currency != "VND" for x in rows):
        row["blockers"].append(
            "Dữ liệu lẫn phạm vi hợp nhất/đơn vị; cần analyst kiểm tra"
        )

    company = build_company_data(db, ticker, mode="TTM", fetch_live=False)
    company.current_price = price
    row["is_bank"] = isinstance(company, CompanyBank)
    row["assumptions"] = company.assumptions.model_dump(mode="json")
    macro = MacroEnvironment.from_db(db)
    row["input_hash"] = fingerprint(
        {"company": company.model_dump(mode="json"), "macro": vars(macro)}
    )
    result = valuate(company.model_copy(deep=True), macro_env=macro)
    row["flags"] = sorted(
        set(result.get("flags", []) + list(getattr(company, "data_flags", []) or []))
    )
    fv = float(result["blended_fair_value_per_share"])
    checks = run_deterministic_checks(
        company, blended_fv=fv, upside=(fv / price - 1) * 100
    )
    row["checks"] = checks
    row["blockers"].extend(x["message"] for x in checks if x["severity"] == "error")
    row["blockers"].extend(result.get("decision", {}).get("hard_gates_violations", []))
    row["fair_value"] = fv if finite(fv) and fv > 0 else None
    row["scenarios"] = {"Base": row["fair_value"]}
    for scenario in ("Bear", "Bull"):
        value = valuate(apply_scenario_adjustments(company, scenario), macro_env=macro)[
            "blended_fair_value_per_share"
        ]
        row["scenarios"][scenario] = (
            float(value) if finite(value) and value > 0 else None
        )
    metrics = financial_metrics(company, as_of)
    if metrics["history_years"] < cfg["min_history_years"]:
        row["blockers"].append("Chưa đủ lịch sử kinh doanh nhiều năm")
    values = traded_values(prices)
    row["liquidity_ok"] = (
        len(values) == len(prices) == 20
        and sum(values) / len(values) >= cfg["scales"]["min_traded_value_vnd"]
    )
    metrics["avg_traded_value"] = sum(values) / len(values) if values else None
    if len(values) == len(prices) == 20 and all(
        x.foreign_net_val is not None for x in prices
    ):
        metrics["flow_ratio"] = sum(float(x.foreign_net_val) for x in prices) / sum(
            values
        )
    if len(values) != 20 or metrics.get("flow_ratio") is None:
        cache = PROJECT_ROOT / ".vn100_ranking/sponsor" / ticker
        stats, foreign = read_json(cache / "stats.json"), read_json(cache / "foreign.json")
        # Nguồn tải sau ngày định giá không được đưa vào kiểm thử lịch sử.
        usable = all(p and p.get("checked_at", "9999")[:10] <= as_of.isoformat() for p in (stats, foreign))
        supplement = sponsor_market_metrics(stats, foreign, [x.trade_date for x in prices]) if usable else {}
        if supplement:
            if len(values) != 20:
                metrics["avg_traded_value"] = supplement["avg_traded_value"]
                row["liquidity_ok"] = supplement["avg_traded_value"] >= cfg["scales"]["min_traded_value_vnd"]
            if metrics.get("flow_ratio") is None:
                metrics["flow_ratio"] = supplement["foreign_flow_ratio"]
            row["market_metrics_source"] = "vnstock_data/Market"
            row["market_metrics_checked_at"] = stats["checked_at"]
    validated = verified_evidence(evidence, as_of, row["input_hash"], cfg)
    row["evidence"] = validated
    row["governance_verified"] = validated.get("governance_clear") is True
    row["golden_verified"] = validated.get("golden_verified", False)
    # Chỉ số ngân hàng lấy từ hồ sơ có nguồn, không lấy số 0 mặc định của model.
    for key in ("npl", "llr"):
        metrics[key] = validated.get("metrics", {}).get(key)
    row["metrics"] = metrics
    row["components"] = {
        key: validated.get("scores", {}).get(key) for key in ("moat", "context")
    }
    return row
