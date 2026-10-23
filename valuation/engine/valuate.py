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


REVIEWS_FILE = None  # None → config/valuation_reviews.yaml (test có thể trỏ file khác)


def load_valuation_reviews() -> dict:
    """config/valuation_reviews.yaml: ticker → {reviewed_by, reviewed_on, decision, basis, reason...}."""
    import yaml
    from valuation.config import PROJECT_ROOT

    path = REVIEWS_FILE or PROJECT_ROOT / "config" / "valuation_reviews.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        reviews = (yaml.safe_load(f) or {}).get("reviews") or {}
    return {str(k).upper(): v for k, v in reviews.items()}


def active_review(ticker: str, basis: str, as_of) -> dict | None:
    """Review còn hạn (TTL) và cùng basis với phương pháp đang dùng; thiếu trường bắt buộc → lỗi."""
    from datetime import date, timedelta
    from valuation.config import load_defaults

    rv = load_valuation_reviews().get(ticker.upper())
    if not rv:
        return None
    missing = [k for k in ("reviewed_by", "reviewed_on", "decision", "basis", "reason") if not rv.get(k)]
    if missing or rv["decision"] not in ("publish", "block") or rv["basis"] not in ("own_model", "broker_synth"):
        raise ValueError(f"valuation_reviews.yaml: {ticker} sai/thiếu {missing or 'decision/basis'}")
    on = date.fromisoformat(str(rv["reviewed_on"]))
    ttl = int(load_defaults()["valuation_review"]["ttl_days"])
    if rv["basis"] != basis or not (on <= as_of <= on + timedelta(days=ttl)):
        return None
    return rv


def _gate(company, result: Dict[str, Any], macro_env=None) -> Dict[str, Any]:
    """Giữ số chẩn đoán nội bộ nhưng chặn phát hành khi đầu vào/mô hình lỗi."""
    from valuation.report.verified_summary import run_deterministic_checks
    from valuation.config import load_defaults

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
    blocking = codes & PUBLICATION_BLOCKING_FLAGS
    not_rated = bool(result.get("not_rated", False))
    basis = "broker_synth" if result.get("method") == "BROKER_SYNTH" else "own_model"
    review = active_review(company.ticker, basis, date.today())
    review_block = bool(review and review["decision"] == "block")
    lifted = False
    if review and review["decision"] == "publish":
        # Chỉ gỡ cờ "rà soát được"; cờ lỗi dữ liệu thật và lỗi checks (severity error) vẫn chặn.
        rcfg = load_defaults()["valuation_review"]
        ok = set(rcfg["reviewable_flags"])
        if basis == "broker_synth":
            ok |= set(rcfg["reviewable_if_broker_synth"])
        if review.get("stakes_verified"):
            ok |= set(rcfg["reviewable_if_stakes_verified"])
        hard_left = blocking - ok
        # not_rated từ mô hình chỉ gỡ được khi FV > 0 và không có cờ vốn chủ/chân âm.
        negative = value <= 0 or any("NEGATIVE" in c for c in codes)
        if not hard_left and not (not_rated and negative):
            lifted = bool(blocking) or not_rated
            blocking, not_rated = set(), False
    blocked = (any(c["severity"] == "error" for c in checks) or bool(blocking) or not_rated
               or ai_unverified or review_block)
    result["data_checks"] = checks
    result["publication_allowed"] = not blocked
    if review_block:
        flags.add(f"REVIEW_BLOCKED:{review['reason']}")
    if review and not blocked:
        flags.add(f"REVIEWED_PUBLISH:{review['reason']}")
        result["review"] = review
        result["review_label"] = f"Đã rà soát: {review['reason']}"
    if lifted and not blocked:
        result["not_rated"] = False
        decision = recommend(company.ticker, company.current_price, value,
                             governance=getattr(company, "governance", None), macro_env=macro_env)
        result.update(decision=decision, recommendation=decision["recommendation"], upside=decision["upside"])
        flags -= {"NOT_RATED", "DATA_REVIEW_REQUIRED"}
    result["flags"] = sorted(flags)
    if blocked:
        result["not_rated"] = True
        result["recommendation"] = "NOT_RATED"
        result["decision"] = {**result.get("decision", {}), "recommendation": "NOT_RATED"}
        result["flags"] = sorted(flags | {"DATA_REVIEW_REQUIRED", "NOT_RATED"})
    return result


def _broker_synth_result(company, own: Dict[str, Any], synth: Dict[str, Any], macro_env=None) -> Dict[str, Any]:
    """Kết quả công bố theo BROKER_SYNTH; giữ FV/cờ mô hình riêng để so sánh."""
    fv = float(synth["blended_fair_value_per_share"])
    decision = recommend(company.ticker, company.current_price, fv,
                         governance=getattr(company, "governance", None), macro_env=macro_env)
    # Cờ cấp doanh nghiệp (dữ liệu nguồn) vẫn đi theo; cờ của mô hình riêng chỉ nằm ở own_model_flags.
    return {
        "not_rated": False,
        "blended_fair_value_per_share": fv,
        "intrinsic_fv": fv,
        "relative_fv": fv,
        "weight_intrinsic": 1.0,
        "upside": decision["upside"],
        "recommendation": decision["recommendation"],
        "decision": decision,
        "method": "BROKER_SYNTH",
        "method_label": synth["method_label"],
        "broker_synth": synth,
        "own_model_fv": own.get("blended_fair_value_per_share"),
        "own_model_flags": own.get("flags", []),
        "projections": own.get("projections"),
        "flags": ["BROKER_SYNTHESIZED"] + synth["flags"] + _review_flags(decision["upside"])
                 + _warning_codes(company) + list(getattr(company, "data_flags", []) or []),
    }


def _apply_publication_gate(company, result: Dict[str, Any], macro_env=None) -> Dict[str, Any]:
    """Cổng công bố: chặn/gỡ theo cờ + review; mô hình riêng bị chặn vì lỗi dữ liệu/mô hình
    và mã có config/broker_synth/<MÃ>.yaml → công bố theo Mô hình tổng hợp CTCK."""
    from valuation.config import load_defaults
    from valuation.engine.models.broker_synth import load_broker_synth, valuate_broker_synth

    gated = _gate(company, result, macro_env)
    # load_broker_synth() raise ValueError cho mã sai định dạng (chống path injection, cố ý —
    # xem test_broker_synth.py::test_ticker_khong_hop_le). Mã mô phỏng trong unit test (vd
    # "HOLDX") không phải mã VN100 thật, không nên làm sập cả valuate() — bỏ qua broker_synth
    # cho các mã không đúng dạng [A-Z0-9]{3} thay vì gọi load_broker_synth với chúng.
    if not re.fullmatch(r"[A-Z0-9]{3}", str(company.ticker).upper()):
        return gated
    cfg = load_broker_synth(company.ticker)
    if not cfg:
        return gated
    prefixes = tuple(load_defaults()["broker_synth"]["trigger_flag_prefixes"])
    own_codes = {str(f).split(":", 1)[0].strip() for f in gated["flags"]}
    triggered = not gated["publication_allowed"] and any(c.startswith(prefixes) for c in own_codes)
    if not (cfg.get("use_broker_synth") or triggered):
        return gated
    synth = valuate_broker_synth(company, cfg)
    published = _gate(company, _broker_synth_result(company, gated, synth, macro_env), macro_env)
    # Cờ chẩn đoán của mô hình riêng (lý do nó không dùng được, vd VALUATION_PROXY) hiển thị
    # minh bạch trong kết quả cuối — nhưng chỉ nối SAU khi _gate ở trên đã quyết xong, để không
    # bị cổng chặn nhầm lần hai (VALUATION_PROXY/PROXY_IMPLAUSIBLE... vẫn nằm trong
    # PUBLICATION_BLOCKING_FLAGS, đúng cho mô hình riêng nhưng không áp cho BROKER_SYNTH).
    own_diag = [f for f in gated.get("flags", []) if f not in ("NOT_RATED", "DATA_REVIEW_REQUIRED")]
    published["flags"] = sorted(set(published["flags"]) | set(own_diag))
    return published


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

        return _apply_publication_gate(company, macro_env=macro_env, result={
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

    return _apply_publication_gate(company, macro_env=macro_env, result={
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
