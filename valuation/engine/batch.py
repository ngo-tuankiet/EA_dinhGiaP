"""
Batch valuation — định giá router-driven cho toàn VN100.

`value_ticker` là điểm dispatch DUY NHẤT: route(ticker) → đúng model theo bảng CTCK.
Trả về dict chuẩn (method, FV, upside, flags) — dùng cho batch + export Sheets.
Mỗi mã bọc try/except: 1 mã lỗi không làm hỏng cả batch.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from valuation.engine.sector_router import route
from valuation.data_access.repo import get_latest_price, build_company_data
from valuation.config import load_defaults


_NOT_RATEABLE_FLAGS = {
    "NEGATIVE_EQUITY_VALUE_DCF",
    "NEGATIVE_EQUITY_VALUE_EV_EBITDA",
    "PROXY_IMPLAUSIBLE",
    "NOT_RATED",
}


def _collect_flags(model, result: Dict[str, Any]) -> List[str]:
    flags = list(getattr(model, "valuation_warnings", []) or [])
    for f in result.get("flags", []) or []:
        if f not in flags:
            flags.append(f)
    return flags


def value_ticker(db: Session, ticker: str, macro_env=None, as_of=None) -> Dict[str, Any]:
    """Định giá 1 mã theo đúng phương pháp router. Trả dict chuẩn hoặc {error}."""
    plan = route(ticker)
    if not plan:
        return {"ticker": ticker, "error": "NOT_IN_VN100"}

    method, status, group = plan["method"], plan["status"], plan["group"]
    price = get_latest_price(db, ticker, fetch_live=False, as_of=as_of)
    base = {
        "ticker": ticker, "method": method, "status": status,
        "group": group, "verified": plan["verified"], "price": price,
    }
    try:
        # Engine DUY NHẤT: build_company_data → valuate (best-of-both theo ngành).
        # Cùng lõi với Streamlit → CLI/batch/Sheets và UI ra cùng một số.
        from valuation.engine.valuate import valuate
        company = build_company_data(db, ticker, mode="TTM", fetch_live=False, as_of=as_of)
        res = valuate(company, macro_env=macro_env)

        fv = float(res["blended_fair_value_per_share"])
        flags = list(res.get("flags", []) or [])
        # Cổng phát hành của valuate() (lỗi dữ liệu/mô hình) phải chặn cả batch,
        # xếp hạng và file xuất — trước đây chỉ UI tôn trọng nó.
        if fv <= 0 or not res.get("publication_allowed", True) or _NOT_RATEABLE_FLAGS.intersection(flags):
            if "NOT_RATEABLE" not in flags:
                flags.append("NOT_RATEABLE")
            return {
                **base,
                "fair_value": None,
                "upside": None,
                "recommendation": "NOT_RATED",
                "flags": flags,
            }
        upside = (fv / price - 1.0) if price else None
        return {
            **base,
            "fair_value": fv,
            "upside": upside,
            "recommendation": res["recommendation"],
            "flags": flags,
        }
    except Exception as e:  # 1 mã lỗi không phá batch
        return {**base, "error": f"{type(e).__name__}: {str(e)[:80]}"}


def _dispatch_nonfin(company, method: str, group: Optional[str], macro_env=None):
    """Chọn model phi tài chính theo method. Trả (model, result) hoặc (None, None)."""
    
    # Chuẩn hóa chu kỳ nằm TRONG từng model (biên giữa chu kỳ × doanh thu TTM,
    # xem models/base.midcycle_level) — không sửa đè dữ liệu Company ở đây.
    from valuation.engine.models.dcf import DCFValuationModel
    if method == "RNAV":
        from valuation.engine.models.rnav import RNAVValuationModel
        m = RNAVValuationModel.from_pydantic(company)
    elif method == "SOTP":
        from valuation.engine.models.sotp import SOTPValuationModel
        m = SOTPValuationModel.from_pydantic(company)
    elif method == "EV_EBITDA":
        from valuation.engine.models.ev_ebitda import EVEBITDAValuationModel
        m = EVEBITDAValuationModel.from_pydantic(company)
    elif method == "PE":
        from valuation.engine.models.pe_relative import PERelativeValuationModel
        m = PERelativeValuationModel.from_pydantic(company, sector=group)
    elif method == "PB":
        # D26/D27 — routing gộp CK và BẢO HIỂM chung `primary: P/B`, nhưng kinh tế
        # hai ngành khác hẳn (CTCK bám thanh khoản, chu kỳ ngắn biên độ rộng;
        # bảo hiểm bám chu kỳ lãi suất, dài và êm). Tách theo `sector` của routing.
        if (group or "").upper() in ("CK", "CHỨNG KHOÁN", "CHUNG KHOAN"):
            from valuation.engine.models.securities import SecuritiesValuationModel
            m = SecuritiesValuationModel.from_pydantic(company)
        elif (group or "").upper() in ("BH", "BẢO HIỂM", "BAO HIEM"):
            from valuation.engine.models.insurance import InsuranceValuationModel
            m = InsuranceValuationModel.from_pydantic(company)
        else:
            from valuation.engine.models.pb_relative import PBRelativeValuationModel
            m = PBRelativeValuationModel.from_pydantic(company)
    elif method in ("DCF", "DCF_EVEBITDA"):
        m = DCFValuationModel.from_pydantic(company)
        res = m.perform_valuation()
        # ĐIỆN: blend DCF (chủ đạo) + DDM cross-check.
        if group == "Điện":
            from valuation.engine.models.ddm import DDMValuationModel
            w = load_defaults().get("ddm", {}).get("power_dcf_weight", 0.6)
            ddm = DDMValuationModel.from_pydantic(company).perform_valuation()
            ddm_fv = ddm["blended_fair_value_per_share"]
            if ddm_fv > 0:
                res["blended_fair_value_per_share"] = w * res["blended_fair_value_per_share"] + (1 - w) * ddm_fv
                res.setdefault("flags", []).append("DDM_BLEND")
            else:
                res.setdefault("flags", []).extend(ddm.get("flags", []))
        return m, res
    else:
        return None, None
    return m, m.perform_valuation()


def value_all(db: Session, tickers: List[str] = None, macro_env=None) -> List[Dict[str, Any]]:
    """Định giá hàng loạt. Mặc định toàn bộ mã có trong bảng routing (VN100)."""
    if tickers is None:
        from valuation.ingest.universe import get_vn100_symbols
        tickers = get_vn100_symbols()
    return [value_ticker(db, t, macro_env=macro_env) for t in tickers]
