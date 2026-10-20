"""
Lõi định giá DUY NHẤT — hợp nhất CLI/batch/Sheets và Streamlit về cùng một engine.

Trước đây có 2 đường tính khác nhau cho cùng một mã (vd ACB: 47,774 vs 68,929):
  - batch.value_ticker  → valuate() (bank: BankGeneralValuationModel / phi TC: _dispatch_nonfin)
  - views/results.py    → forecast → run_valuation_engine → blend_intrinsic_relative

`valuate()` là lõi chung best-of-both theo ngành:
  - Ngân hàng     → forecast_bank + run_valuation_engine (RI + P/B) + blend
  - Phi tài chính → _dispatch_nonfin (DCF/RNAV/SOTP/PE/PB/EV_EBITDA, giữ cả flags)

Lưu ý: run_valuation_engine (dùng cho ma trận độ nhạy/scenario của UI) cũng đã được
sửa để delegate non-fin sang _dispatch_nonfin → mọi đường ra cùng một con số.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Union

from valuation.models.financials import Company
from valuation.models.financials_bank import CompanyBank
from valuation.engine.decision_engine import recommend
from valuation.engine.sector_router import route as _route_fn

from valuation.models.macro_env import MacroEnvironment


def _review_flags(upside_pct: float) -> list:
    """Cờ review khi upside cực đoan — buộc analyst rà lại giả định thay vì tin mù.

    upside_pct: upside tính theo % (vd 302.8 = +302.8%). Ngưỡng (config publication_gate)
    đặt rộng để chỉ bắt trường hợp thực sự bất thường (giá hợp lý > 2.5× hoặc < 0.4× thị giá).
    """
    if upside_pct is None:
        return []
    from valuation.config import load_defaults

    gate = load_defaults()["publication_gate"]
    if upside_pct > float(gate["upside_extreme_review_pct"]):
        return ["UPSIDE_EXTREME_REVIEW"]
    if upside_pct < float(gate["downside_extreme_review_pct"]):
        return ["DOWNSIDE_EXTREME_REVIEW"]
    return []


_FLAG_CODE = re.compile(r"[A-Z][A-Z0-9_]+")


def _warning_codes(company) -> list:
    """Chỉ lấy mã UPPER_SNAKE trước ':' (vd BANK_PB_CLAMPED_LOW). Cảnh báo văn bản tự do ("Năm 2018: ...")
    không thành mã cờ rác nhưng vẫn nằm trong company.warnings để hiển thị."""
    prefixes = (str(w).split(":", 1)[0].strip() for w in (getattr(company, "warnings", None) or []))
    return [p for p in prefixes if _FLAG_CODE.fullmatch(p)]


# Mã cờ (trước ':') chặn công bố; flag_descriptions phải ghi level 'error' cho mọi mã ở đây (test r3b).
PUBLICATION_BLOCKING_FLAGS = frozenset({
    "VALUATION_PROXY", "NOT_RATED", "PROXY_IMPLAUSIBLE", "VALUATION_LEGS_DIVERGE",
    "CIP_DOMINATES_VALUE", "UPSIDE_EXTREME_REVIEW", "DOWNSIDE_EXTREME_REVIEW",
    "MATERIAL_EVENT_HOLD", "SOTP_HOLDINGS_UNVERIFIED", "SOTP_HOLDINGS_STALE",
    "SOTP_SUBSIDIARY_DATA_ERROR", "LAND_BANK_INPUT_MISSING", "AI_INPUTS_UNVERIFIED",
})


def _apply_publication_gate(company, result: Dict[str, Any]) -> Dict[str, Any]:
    """Giữ số chẩn đoán nội bộ nhưng chặn phát hành khi đầu vào/mô hình lỗi."""
    from valuation.report.verified_summary import run_deterministic_checks

    result = dict(result)
    value = result["blended_fair_value_per_share"]
    upside = (value / company.current_price - 1) * 100 if company.current_price > 0 else 0
    checks = run_deterministic_checks(company, blended_fv=value, upside=upside)
    flags = set(result.get("flags", []))
    ai_unverified = bool(flags & {"AI_RNAV_MODE", "AI_SOTP_MODE"}) and not getattr(
        getattr(company, "assumptions", None), "ai_inputs_verified", False
    )
    if ai_unverified:
        flags.add("AI_INPUTS_UNVERIFIED")
    # D46: sự kiện trọng yếu mô hình chưa phản ánh (vd PNJ lỗ dự kiến + pha loãng 107%).
    # ponytail: so với ngày chạy, không theo as_of backtest → chỉ chặn thừa, không lookahead có lợi.
    from datetime import date
    from valuation.config import active_event_hold
    if active_event_hold(company.ticker, date.today()):
        flags.add("MATERIAL_EVENT_HOLD")
    # Kết quả cực đoan phải được rà soát trước khi phát hành (số chẩn đoán vẫn giữ lại).
    # So theo mã cờ trước ':' — cờ mang chi tiết (vd SOTP_SUBSIDIARY_DATA_ERROR:GEL(...)) vẫn chặn.
    codes = {str(f).split(":", 1)[0].strip() for f in flags}
    blocked = any(c["severity"] == "error" for c in checks) or bool(
        codes & PUBLICATION_BLOCKING_FLAGS
    ) or result.get("not_rated", False) or ai_unverified
    result["data_checks"] = checks
    result["publication_allowed"] = not blocked
    if blocked:
        result["not_rated"] = True
        result["recommendation"] = "NOT_RATED"
        result["decision"] = {**result.get("decision", {}), "recommendation": "NOT_RATED"}
        result["flags"] = sorted(flags | {"DATA_REVIEW_REQUIRED", "NOT_RATED"})
    return result


def valuate(company: Union[Company, CompanyBank], projections=None, macro_env: MacroEnvironment = None) -> Dict[str, Any]:
    """
    Định giá 1 doanh nghiệp bằng engine chuẩn (Base case).

    projections: dự phóng cho sẵn (vd analyst đã sửa trên UI). Chỉ dùng cho bank;
    nếu None thì tự forecast. Phi tài chính bỏ qua tham số này.
    macro_env: Thông số vĩ mô để điều chỉnh định giá.
    """
    from valuation.engine.sector_router import ValuationRouter

    route = ValuationRouter().get_routing(company.ticker)
    weight_intrinsic = route.get("weight_primary", 1.0)

    # Vĩ mô chỉ nới biên an toàn trong decision_engine. KHÔNG cộng ERP theo công tắc
    # CPI>5%: tạo vách đứng (CPI 5,6% → 4,7% làm FV nhảy 15-25%) và từng ghi đè thẳng
    # vào Company của caller.

    if isinstance(company, CompanyBank):
        from valuation.engine.forecast_bank import forecast_bank_financials
        from valuation.engine.sensitivity import run_valuation_engine
        from valuation.engine.blend import blend_intrinsic_relative

        if projections is None:
            projections = forecast_bank_financials(company)
        intrinsic_fv, relative_fv = run_valuation_engine(company, projections=projections)
        leg_flags = []
        try:
            blended_fv, _ = blend_intrinsic_relative(
                intrinsic_fv, relative_fv, weight_intrinsic, company.current_price
            )
        except ValueError:
            # Chân RI/P/B âm: không pha âm thầm (trước đây kẹp về 0 → FV mất nửa).
            blended_fv, leg_flags = 0.0, ["BANK_NEGATIVE_VALUATION_LEG"]
        from valuation.engine.guardrails import legs_diverge

        # Cùng cổng với DCF/CK/BH: hai chân RI và P/B vênh quá ngưỡng thì trung bình không phải giá trị hợp lý.
        diverge = (
            ["VALUATION_LEGS_DIVERGE"]
            if not leg_flags and 0.0 < weight_intrinsic < 1.0 and legs_diverge(intrinsic_fv, relative_fv)
            else []
        )
        from valuation.config import load_defaults
        from valuation.engine.forecast_bank import fade_plug_share

        # LN năm 5 phần lớn do dòng cân phai ROE (không theo driver) → nói rõ, không chặn công bố.
        plug = fade_plug_share(projections, company.assumptions.tax_rate)
        plug_flags = (
            [f"BANK_ROE_FADE_PLUG:{plug:.0%}"]
            if plug is not None and abs(plug) >= float(load_defaults()["bank_terminal"]["fade_plug_flag_share"])
            else []
        )

        decision = recommend(
            company.ticker, company.current_price, blended_fv,
            governance=company.governance, macro_env=macro_env, not_rated=bool(leg_flags),
        )

        return _apply_publication_gate(company, {
            "not_rated": bool(leg_flags),
            "blended_fair_value_per_share": blended_fv,
            "intrinsic_fv": intrinsic_fv,
            "relative_fv": relative_fv,
            "weight_intrinsic": weight_intrinsic,
            "upside": decision["upside"],
            "recommendation": decision["recommendation"],
            "projections": projections,
            "flags": leg_flags + diverge + plug_flags + _review_flags(decision["upside"]) + _warning_codes(company)
                     + list(getattr(company, "data_flags", []) or []),
            "decision": decision
        })

    # Phi tài chính: dispatch theo method (đủ PE/PB/EV_EBITDA/RNAV/SOTP/DCF, giữ flags)
    from valuation.engine.batch import _dispatch_nonfin, _collect_flags
    plan = _route_fn(company.ticker) or {}
    model, res = _dispatch_nonfin(company, plan.get("method"), plan.get("group"), macro_env=macro_env)
    if model is None:
        raise ValueError(f"METHOD_NOT_IMPLEMENTED:{plan.get('method')}")

    blended_fv = float(res["blended_fair_value_per_share"])

    # Land Bank add-on: cộng thêm giá trị quỹ đất CHƯA phản ánh trong BCTC
    # (nông nghiệp/cao su/KCN...) — độc lập với phương pháp chính. Mặc định 0
    # khi analyst chưa nhập dữ liệu (không bịa số liệu).
    from valuation.engine.land_bank import compute_land_bank_value_per_share
    land_bank = compute_land_bank_value_per_share(company)
    blended_fv += land_bank["land_bank_value_per_share"]

    # D28: model tự nhận không đủ cơ sở định giá (proxy lệch phi lý, thiếu dữ
    # liệu cấu trúc tập đoàn...) -> không phát khuyến nghị MUA/BÁN.
    not_rated = bool(res.get("not_rated"))
    decision = recommend(
        company.ticker, company.current_price, blended_fv,
        governance=company.governance, macro_env=macro_env, not_rated=not_rated,
    )

    return _apply_publication_gate(company, {
        "not_rated": not_rated,
        "blended_fair_value_per_share": blended_fv,
        "intrinsic_fv": blended_fv,
        "relative_fv": res.get("multiples_fvps", blended_fv),
        "weight_intrinsic": weight_intrinsic,
        "upside": decision["upside"],
        "recommendation": decision["recommendation"],
        "flags": _collect_flags(model, res) + land_bank["flags"] + _review_flags(decision["upside"])
                 + _warning_codes(company) + list(getattr(company, "data_flags", []) or []),
        "land_bank_npv": land_bank["land_bank_npv"],
        "decision": decision,
        "projections": res.get("forecasts", None)
    })
