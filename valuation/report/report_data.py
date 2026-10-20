"""
Report Data Builder — gom toàn bộ số liệu cho báo cáo định giá 11 phần chuẩn
CTCK/quỹ đầu tư (SPEC PHẦN B). Module THUẦN dữ liệu: không phụ thuộc Streamlit,
chạy và test độc lập được.

Khuôn 11 phần:
 1. Cover (khuyến nghị, giá MT, upside, vốn hóa)      → build_cover
 2. Luận điểm đầu tư                                   → ai_narrative (module riêng)
 3. Bảng tóm tắt định giá                              → build_valuation_summary
 4. Tổng quan doanh nghiệp                             → ai_narrative
 5. Bối cảnh ngành                                     → ai_narrative
 6. Phân tích tài chính lịch sử                        → build_historical_analysis
 7. Giả định dự phóng                                  → build_assumptions_table
 8. Chi tiết định giá (WACC breakdown, consensus)      → build_wacc_breakdown, build_consensus_comparison
 9. Độ nhạy & kịch bản Bull/Base/Bear                  → build_scenarios
10. Rủi ro đầu tư                                      → ai_narrative + flags
11. Phụ lục BCTC đầy đủ                                → build_appendix_financials
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from valuation.engine.decision_engine import REC_LABELS_VI, recommend
from valuation.models.financials import Company
from valuation.models.financials_bank import CompanyBank

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers chung
# ---------------------------------------------------------------------------

def _fmt(v: Optional[float], pattern: str = "{:,.1f}") -> str:
    """Format số cho bảng báo cáo; None/thiếu dữ liệu → 'N/A'."""
    if v is None:
        return "N/A"
    try:
        return pattern.format(v)
    except (ValueError, TypeError):
        return "N/A"


def _pct(v: Optional[float]) -> str:
    return _fmt(v, "{:.1%}")


def market_cap_billion_vnd(company: Union[Company, CompanyBank]) -> float:
    """Vốn hóa (tỷ đồng) = shares (triệu cp) × giá (VND) / 1e3."""
    return company.shares_outstanding * company.current_price / 1e3


# ---------------------------------------------------------------------------
# Phần 1 — Cover
# ---------------------------------------------------------------------------

def build_cover(company: Union[Company, CompanyBank], blended_fv: float) -> Dict[str, Any]:
    price = company.current_price
    upside = (blended_fv - price) / price if price else 0.0
    return {
        "ticker": company.ticker,
        "name": company.name,
        "sector": company.sector,
        "current_price": price,
        "target_price": blended_fv,
        "upside": upside,
        "recommendation": REC_LABELS_VI[
            recommend(company.ticker, price, blended_fv, governance=company.governance)["recommendation"]
        ],
        "market_cap": market_cap_billion_vnd(company),
        "shares_outstanding": company.shares_outstanding,
    }


# ---------------------------------------------------------------------------
# Phần 6 — Phân tích tài chính lịch sử (bảng + dữ liệu vẽ biểu đồ)
# ---------------------------------------------------------------------------

def build_historical_analysis(company: Union[Company, CompanyBank]) -> Dict[str, Any]:
    """Bảng chỉ số lịch sử theo năm + series cho biểu đồ (DT/LNST, ROE, biên)."""
    is_bank = isinstance(company, CompanyBank)
    years = [r.year for r in company.historical_is]

    if is_bank:
        toi = [r.total_operating_income for r in company.historical_is]
        nii = [r.net_interest_income for r in company.historical_is]
        ni = [r.net_income for r in company.historical_is]
        equity = [b.total_equity for b in company.historical_bs]
        assets = [b.total_assets for b in company.historical_bs]
        loans = [b.customer_loans for b in company.historical_bs]

        roe = [n / e if e > 0 else None for n, e in zip(ni, equity)]
        roa = [n / a if a > 0 else None for n, a in zip(ni, assets)]
        cir = [
            r.operating_expenses / r.total_operating_income if r.total_operating_income > 0 else None
            for r in company.historical_is
        ]
        loan_growth = [None] + [
            (loans[i] - loans[i - 1]) / loans[i - 1] if loans[i - 1] > 0 else None
            for i in range(1, len(loans))
        ]

        rows = [
            {"label": "Tổng thu nhập hoạt động (TOI)", "values": [_fmt(v) for v in toi]},
            {"label": "Thu nhập lãi thuần (NII)", "values": [_fmt(v) for v in nii]},
            {"label": "Lợi nhuận sau thuế", "values": [_fmt(v) for v in ni]},
            {"label": "Dư nợ cho vay KH", "values": [_fmt(v) for v in loans]},
            {"label": "Tăng trưởng tín dụng", "values": [_pct(v) for v in loan_growth]},
            {"label": "Vốn chủ sở hữu", "values": [_fmt(v) for v in equity]},
            {"label": "ROE", "values": [_pct(v) for v in roe]},
            {"label": "ROA", "values": [_pct(v) for v in roa]},
            {"label": "CIR", "values": [_pct(v) for v in cir]},
        ]
        chart_series = {
            "years": years,
            "revenue": toi,           # với bank dùng TOI làm "doanh thu"
            "net_income": ni,
            "roe": roe,
            "margin": cir,            # với bank vẽ CIR thay biên EBIT
            "margin_label": "CIR",
            "revenue_label": "Tổng thu nhập hoạt động",
        }
    else:
        rev = [r.revenue for r in company.historical_is]
        ni = [r.net_income for r in company.historical_is]
        ebit = [r.ebit for r in company.historical_is]
        equity = [b.total_equity for b in company.historical_bs]
        debt = [b.short_term_debt + b.long_term_debt for b in company.historical_bs]

        growth = [None] + [
            (rev[i] - rev[i - 1]) / rev[i - 1] if rev[i - 1] > 0 else None
            for i in range(1, len(rev))
        ]
        ebit_margin = [e / r if r > 0 else None for e, r in zip(ebit, rev)]
        net_margin = [n / r if r > 0 else None for n, r in zip(ni, rev)]
        roe = [n / e if e > 0 else None for n, e in zip(ni, equity)]
        de_ratio = [d / e if e > 0 else None for d, e in zip(debt, equity)]

        rows = [
            {"label": "Doanh thu thuần", "values": [_fmt(v) for v in rev]},
            {"label": "Tăng trưởng doanh thu", "values": [_pct(v) for v in growth]},
            {"label": "EBIT", "values": [_fmt(v) for v in ebit]},
            {"label": "Biên EBIT", "values": [_pct(v) for v in ebit_margin]},
            {"label": "Lợi nhuận sau thuế", "values": [_fmt(v) for v in ni]},
            {"label": "Biên LN ròng", "values": [_pct(v) for v in net_margin]},
            {"label": "ROE", "values": [_pct(v) for v in roe]},
            {"label": "Nợ vay / VCSH", "values": [_fmt(v, "{:.2f}x") for v in de_ratio]},
        ]
        chart_series = {
            "years": years,
            "revenue": rev,
            "net_income": ni,
            "roe": roe,
            "margin": ebit_margin,
            "margin_label": "Biên EBIT",
            "revenue_label": "Doanh thu thuần",
        }

    return {"headers": [str(y) for y in years], "rows": rows, "chart_series": chart_series}


# ---------------------------------------------------------------------------
# Phần 7 — Bảng giả định dự phóng
# ---------------------------------------------------------------------------

def build_assumptions_table(company: Union[Company, CompanyBank]) -> Dict[str, Any]:
    """Bảng giả định: schedule 5 năm (schedule_rows) + tham số đơn (single_rows)."""
    a = company.assumptions
    if isinstance(company, CompanyBank):
        rows = [
            {"label": "Tăng trưởng tín dụng", "values": [_pct(v) for v in a.credit_growth]},
            {"label": "NIM", "values": [_pct(v) for v in a.nim]},
            {"label": "CIR", "values": [_pct(v) for v in a.cir]},
            {"label": "Chi phí tín dụng", "values": [_pct(v) for v in a.credit_cost]},
            {"label": "Tỷ lệ chi trả cổ tức", "values": [_pct(a.dividend_payout_ratio)] * 5},
            {"label": "Thuế suất hiệu dụng", "values": [_pct(a.tax_rate)] * 5},
        ]
        from valuation.engine.models.bank_general import converged_roe

        ab = company.assumptions
        singles = [
            {"label": "ROE bền vững riêng (năm 5)", "value": _pct(ab.sustainable_roe)},
            {"label": "ROE trung bình ngành", "value": _pct(ab.industry_roe)},
            {
                "label": f"ROE terminal (hội tụ λ = {ab.roe_convergence:.2f}, trước trần)",
                "value": _pct(
                    converged_roe(ab.sustainable_roe, ab.industry_roe, ab.roe_convergence)
                    if ab.sustainable_roe is not None else None
                ),
            },
            {"label": "Tăng trưởng vĩnh viễn g", "value": _pct(a.terminal_growth_rate)},
            {"label": "Trọng số Residual Income", "value": _pct(a.weight_ri)},
        ]
    else:
        rows = [
            {"label": "Tăng trưởng doanh thu", "values": [_pct(v) for v in a.revenue_growth]},
            {"label": "Biên EBIT", "values": [_pct(v) for v in a.ebit_margin]},
            {"label": "CapEx / Doanh thu", "values": [_pct(v) for v in a.capex_to_revenue]},
            {"label": "Khấu hao / Doanh thu", "values": [_pct(v) for v in a.depr_to_revenue]},
            {"label": "Thuế suất hiệu dụng", "values": [_pct(a.tax_rate)] * 5},
        ]
        singles = [
            {"label": "Biên EBIT mid-cycle (terminal)", "value": _pct(a.mid_cycle_ebit_margin)},
            {"label": "Tăng trưởng vĩnh viễn g", "value": _pct(a.terminal_growth_rate)},
            {"label": "EV/EBITDA mục tiêu", "value": _fmt(a.target_ev_ebitda, "{:.1f}x")},
            {"label": "Trọng số DCF", "value": _pct(a.weight_dcf)},
        ]
    return {"schedule_rows": rows, "single_rows": singles}


# ---------------------------------------------------------------------------
# Phần 8 — Bóc tách chi phí vốn (WACC/COE breakdown)
# ---------------------------------------------------------------------------

def build_wacc_breakdown(company: Union[Company, CompanyBank]) -> List[Dict[str, str]]:
    """Bảng bóc tách COE (CAPM) và WACC (nếu phi tài chính)."""
    a = company.assumptions
    coe = a.cost_of_equity if a.cost_of_equity else a.risk_free_rate + a.beta * a.erp
    rows = [
        {"label": "Lợi suất phi rủi ro (rf — TPCP VN 10Y)", "value": _pct(a.risk_free_rate)},
        {"label": "Beta", "value": _fmt(a.beta, "{:.2f}")},
        {"label": "ERP (mature + CRP Việt Nam)", "value": _pct(a.erp)},
        {"label": "Chi phí vốn cổ phần Re (CAPM)", "value": _pct(coe)},
    ]
    if isinstance(company, Company):
        # Cùng hàm WACC mô hình DCF/RNAV dùng (thuế lá chắn nợ theo dcf.wacc_tax_mode) — không tự tính lại.
        from valuation.engine.wacc import company_wacc, cost_of_debt_from_rf, wacc_tax_rate
        base_bs = company.historical_bs[-1]
        debt = (base_bs.short_term_debt + base_bs.long_term_debt) * 1e9
        equity_mkt = company.shares_outstanding * 1e6 * company.current_price
        cod = a.cost_of_debt if a.cost_of_debt is not None else cost_of_debt_from_rf(a.risk_free_rate)
        wacc = company_wacc(company)
        total = equity_mkt + debt
        rows += [
            {"label": "Chi phí nợ vay trước thuế (Rd)", "value": _pct(cod)},
            {"label": "Thuế cho lá chắn thuế nợ", "value": _pct(wacc_tax_rate(a))},
            {"label": "Tỷ trọng vốn cổ phần E/(D+E) — theo market cap", "value": _pct(equity_mkt / total if total > 0 else None)},
            {"label": "Tỷ trọng nợ vay D/(D+E)", "value": _pct(debt / total if total > 0 else None)},
            {"label": "WACC", "value": _pct(wacc)},
        ]
    return rows


# ---------------------------------------------------------------------------
# Phần 8b — Đối chiếu consensus CTCK
# ---------------------------------------------------------------------------

def build_consensus_comparison(ticker: str, blended_fv: float, db=None,
                               current_price: float = None) -> Optional[Dict[str, Any]]:
    """So sánh định giá hệ thống với các CTCK: bảng từng CTCK + AI tổng hợp
    điểm chung/riêng (consensus_synthesis) + chênh lệch so với mô hình.

    Giữ nguyên các khóa cũ (our_target/consensus_median/n_reports/deviation/
    flag_high) để template/docx cũ vẫn chạy; các khóa mới là phần mở rộng.
    """
    if db is None:
        return None
    try:
        import datetime
        from valuation.calibration.consensus_view import get_consensus_view
        from valuation.engine.consensus_helper import get_synthesis

        today = datetime.date.today()

        # Dùng NGUỒN ĐỌC DUY NHẤT (D23): trước đây hàm này tự dedup theo CTCK còn
        # KPI median lại lấy từ get_consensus_stats (không dedup) → hai số lệch nhau
        # trên cùng màn hình. Nay median và bảng chi tiết cùng từ một `view`.
        view = get_consensus_view(db, ticker, as_of=today, window_days=180)
        median = view.median
        if not median:
            return None
        deviation = (blended_fv - median) / median

        # Bảng từng CTCK: báo cáo MỚI NHẤT của mỗi CTCK, sắp xếp giá mục tiêu
        # giảm dần để đọc như football field.
        broker_rows = [
            {
                "broker": q.broker,
                "report_date": q.report_date.strftime("%d/%m/%Y"),
                "target_price": q.target_price,
                "rating": q.rating or "—",
                # Chênh lệch của MÔ HÌNH so với CTCK này (dương = mô hình cao hơn)
                "vs_model": (blended_fv - q.target_price) / q.target_price,
                "age_days": q.age_days,
            }
            for q in view.quotes
        ]

        tps = [b["target_price"] for b in broker_rows]
        out = {
            "consensus_median": median,
            # Số CTCK theo dõi (đã dedup) — khớp đúng số dòng bảng bên dưới.
            "n_reports": view.count,
            "n_reports_raw": view.n_reports_raw,
            "consensus_weighted": view.weighted_median,
            "consensus_stale": view.stale,
            # Quá ít CTCK để gọi là "đồng thuận" — báo cáo phải nói rõ, tránh
            # trình bày ý kiến của 1 CTCK như quan điểm thị trường.
            "consensus_thin": view.thin,
            "our_target": blended_fv,
            "deviation": deviation,
            "flag_high": abs(deviation) > 0.25,
            # --- mở rộng ---
            "current_price": current_price,
            "broker_rows": broker_rows,
            "n_brokers": len(broker_rows),
            "range_min": min(tps) if tps else None,
            "range_max": max(tps) if tps else None,
            "synthesis": get_synthesis(ticker, db),  # None nếu chưa chạy AI tổng hợp
            "calibration": _calibration_note(ticker, deviation),  # D25
        }
        return out
    except Exception:
        logger.warning(f"build_consensus_comparison({ticker}) lỗi, bỏ qua tab So sánh CTCK", exc_info=True)
        return None  # thiếu bảng/không có dữ liệu → bỏ qua phần này


def _calibration_note(ticker: str, deviation: float) -> Optional[Dict[str, Any]]:
    """Kết luận hiệu chuẩn của 1 mã để hiển thị kèm bảng so sánh CTCK (D25).

    Trả về band đang áp dụng, mã có nằm trong band không, và — quan trọng nhất —
    LUẬN ĐIỂM giải trình nếu mô hình cố ý lệch. Người đọc cần biết "lệch vì
    chúng tôi tin X" hay "lệch vì đang có lỗi đã biết", chứ không chỉ thấy con số.
    """
    try:
        from valuation.calibration.metrics import classify_band
        from valuation.calibration.registry import band_for, govern, load_registry
        from valuation.engine.sector_router import route

        registry = load_registry()
        plan = route(ticker) or {}
        band = band_for(ticker, plan.get("method"), registry)
        band_status = classify_band(deviation, band)
        gov_status, entry = govern(ticker, band_status, registry)
        return {
            "band": band,
            "band_status": band_status,
            "governance_status": gov_status,
            "thesis": (entry.thesis if entry else ""),
            "evidence": list(entry.evidence) if entry else [],
            "decision_ref": (entry.decision_ref if entry else None),
            "reviewed_on": (entry.reviewed_on.isoformat() if entry and entry.reviewed_on else None),
        }
    except Exception:
        logger.warning(f"_calibration_note({ticker}) lỗi", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Phần 9 — Kịch bản Bull/Base/Bear
# ---------------------------------------------------------------------------

def build_scenarios(company: Union[Company, CompanyBank]) -> Optional[Dict[str, Any]]:
    """Bảng 3 kịch bản từ engine chuẩn (sensitivity.run_scenario_analysis)."""
    try:
        from valuation.engine.sensitivity import run_scenario_analysis
        res = run_scenario_analysis(company)
        price = company.current_price
        out = []
        for name in ("Bull", "Base", "Bear"):
            fv = res.get(name, 0.0)
            out.append({
                "scenario": name,
                "target": fv,
                "upside": (fv - price) / price if price else 0.0,
            })
        # Phương pháp proxy (RNAV/SOTP từ giá trị sổ sách) không co giãn theo
        # growth/margin → 3 kịch bản trùng nhau: đánh dấu để báo cáo ghi chú.
        targets = {r["target"] for r in out}
        return {"rows": out, "applicable": len(targets) > 1}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Phần 11 — Phụ lục BCTC đầy đủ
# ---------------------------------------------------------------------------

def build_appendix_financials(company: Union[Company, CompanyBank]) -> Dict[str, Any]:
    """BCTC lịch sử đầy đủ (KQKD + CĐKT [+ LCTT với phi tài chính])."""
    years = [str(r.year) for r in company.historical_is]
    is_bank = isinstance(company, CompanyBank)

    if is_bank:
        is_rows = [
            ("Thu nhập lãi thuần", [r.net_interest_income for r in company.historical_is]),
            ("Thu nhập ngoài lãi", [r.non_interest_income for r in company.historical_is]),
            ("Tổng thu nhập hoạt động", [r.total_operating_income for r in company.historical_is]),
            ("Chi phí hoạt động", [r.operating_expenses for r in company.historical_is]),
            ("LN trước dự phòng (PPOP)", [r.pre_provision_profit for r in company.historical_is]),
            ("Chi phí dự phòng RRTD", [r.provision_expense for r in company.historical_is]),
            ("LN trước thuế", [r.pretax_income for r in company.historical_is]),
            ("LN sau thuế", [r.net_income for r in company.historical_is]),
        ]
        bs_rows = [
            ("Cho vay khách hàng", [b.customer_loans for b in company.historical_bs]),
            ("Tài sản sinh lời khác", [b.other_earning_assets for b in company.historical_bs]),
            ("Tổng tài sản", [b.total_assets for b in company.historical_bs]),
            ("Tiền gửi khách hàng", [b.customer_deposits for b in company.historical_bs]),
            ("Nợ phải trả khác", [b.other_liabilities for b in company.historical_bs]),
            ("Vốn chủ sở hữu", [b.total_equity for b in company.historical_bs]),
        ]
        cf_rows = []
    else:
        is_rows = [
            ("Doanh thu thuần", [r.revenue for r in company.historical_is]),
            ("Giá vốn hàng bán", [r.cogs for r in company.historical_is]),
            ("Lợi nhuận gộp", [r.gross_profit for r in company.historical_is]),
            ("Chi phí BH + QLDN", [r.opex for r in company.historical_is]),
            ("EBIT", [r.ebit for r in company.historical_is]),
            ("Chi phí lãi vay", [r.interest_expense for r in company.historical_is]),
            ("Thuế TNDN", [r.tax for r in company.historical_is]),
            ("LN sau thuế", [r.net_income for r in company.historical_is]),
        ]
        bs_rows = [
            ("Tiền & tương đương tiền", [b.cash_and_equivalents for b in company.historical_bs]),
            ("Phải thu khách hàng", [b.receivables for b in company.historical_bs]),
            ("Hàng tồn kho", [b.inventory for b in company.historical_bs]),
            ("Tài sản cố định", [b.fixed_assets for b in company.historical_bs]),
            ("Tổng tài sản", [b.total_assets for b in company.historical_bs]),
            ("Nợ vay ngắn hạn", [b.short_term_debt for b in company.historical_bs]),
            ("Phải trả người bán", [b.accounts_payable for b in company.historical_bs]),
            ("Nợ vay dài hạn", [b.long_term_debt for b in company.historical_bs]),
            ("Vốn chủ sở hữu", [b.total_equity for b in company.historical_bs]),
        ]
        cf_rows = [
            ("Dòng tiền HĐKD (CFO)", [c.cfo for c in company.historical_cf]),
            ("Khấu hao & phân bổ (D&A)", [c.depreciation for c in company.historical_cf]),
            ("Chi đầu tư TSCĐ (CapEx)", [c.capex for c in company.historical_cf]),
        ]

    def _table(rows):
        return [{"label": lb, "values": [_fmt(v) for v in vals]} for lb, vals in rows]

    return {
        "headers": years,
        "income_statement": _table(is_rows),
        "balance_sheet": _table(bs_rows),
        "cash_flow": _table(cf_rows),
    }


# ---------------------------------------------------------------------------
# Tổng hợp — 1 lệnh gom đủ dữ liệu 11 phần
# ---------------------------------------------------------------------------

def build_report_sections(
    company: Union[Company, CompanyBank],
    blended_fv: float,
    db=None,
    flags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Gom toàn bộ dữ liệu định lượng cho báo cáo (trừ văn bản AI — module riêng)."""
    return {
        "cover": build_cover(company, blended_fv),
        "historical": build_historical_analysis(company),
        "assumptions": build_assumptions_table(company),
        "wacc_breakdown": build_wacc_breakdown(company),
        "consensus": build_consensus_comparison(company.ticker, blended_fv, db,
                                                current_price=company.current_price),
        "scenarios": build_scenarios(company),
        "appendix": build_appendix_financials(company),
        "flags": list(flags or []) + list(getattr(company, "warnings", []) or []),
    }
