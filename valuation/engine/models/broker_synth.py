"""Mô hình tổng hợp CTCK (BROKER_SYNTH) — xem docs/BROKER_SYNTH.md.

Dùng khi mô hình riêng chưa định giá được (proxy, vốn chủ âm, CIP lấn át...). Với mỗi báo
cáo CTCK, TÍNH LẠI giá trị vốn chủ tuyệt đối (tỷ đồng) bằng công thức chuẩn của chính
phương pháp CTCK dùng, rồi chia cho SỐ CP HIỆN TẠI — không lấy thẳng giá mục tiêu, vì giá
mục tiêu cũ đã/ chưa điều chỉnh quyền thì rất dễ điều chỉnh hai lần.

Đơn vị: *_bn = tỷ đồng; *_mn = triệu cp; giá = đồng/cp (tỷ/triệu cp × 1000 = đồng/cp).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from valuation.config import PROJECT_ROOT, load_defaults
from valuation.engine.weighted_stats import recency_weight, weighted_median

BROKER_SYNTH_DIR = PROJECT_ROOT / "config" / "broker_synth"
_TICKER = re.compile(r"^[A-Z0-9]{3}$")
_SUM_METHODS = {"RNAV", "SOTP", "DCF"}
_MULTIPLE_METHODS = {"PE", "PB", "EV_EBITDA"}


def _cfg() -> dict:
    return load_defaults()["broker_synth"]


def load_broker_synth(ticker: str, directory: Path | None = None) -> dict | None:
    """Đọc config/broker_synth/<MÃ>.yaml; mã sai định dạng → lỗi (chống path injection)."""
    t = str(ticker).upper()
    if not _TICKER.fullmatch(t):
        raise ValueError(f"broker_synth: mã không hợp lệ {ticker!r}")
    path = (directory or BROKER_SYNTH_DIR) / f"{t}.yaml"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if str(data.get("ticker", "")).upper() != t:
        raise ValueError(
            f"broker_synth: {path.name} ghi ticker {data.get('ticker')!r} khác tên file"
        )
    return data


def _num(d: dict, key: str, default: float = 0.0) -> float:
    """Số có mặc định (vd net_debt_bn thiếu → 0) — không bao giờ trả None."""
    v = d.get(key)
    return default if v is None else float(v)


def _num_opt(d: dict, key: str) -> float | None:
    """Số không có mặc định hợp lý (vd target_multiple) — caller phải tự kiểm None."""
    v = d.get(key)
    return None if v is None else float(v)


def _leg_equity_bn(leg: dict, shares_used_mn: float | None) -> float:
    """Giá trị vốn chủ (tỷ đồng) của một chân định giá theo công thức chuẩn của phương pháp."""
    method = str(leg.get("method", "")).upper()
    net_debt = _num(leg, "net_debt_bn")
    minority = _num(leg, "minority_bn")
    other = _num(leg, "other_adjustments_bn")
    fc = leg.get("forecast") or {}
    if method == "TARGET_PRICE":
        # D71: chỉ có giá mục tiêu (consensus_history, nguồn đã điều chỉnh quyền) — vốn chủ ngụ ý =
        # giá mục tiêu × số cp CTCK dùng; không biết cấu phần nên không bóc nợ/CĐTS.
        tp = _num_opt(leg, "target_price")
        if tp is None or not shares_used_mn:
            raise ValueError("broker_synth: TARGET_PRICE thiếu target_price hoặc shares_used_mn")
        return tp * shares_used_mn / 1000.0
    if method in _SUM_METHODS:
        comps = leg.get("components") or []
        if comps:
            # RNAV/SOTP: Σ cấu phần (EV) − nợ ròng − CĐTS ± điều chỉnh; DCF: components = EV.
            equity = sum(float(c["value_bn"]) for c in comps) - net_debt - minority + other
        elif leg.get("equity_value_bn") is not None:
            equity = float(leg["equity_value_bn"])  # CTCK công bố thẳng vốn chủ
        else:
            raise ValueError(f"broker_synth: chân {method} thiếu components và equity_value_bn")
        return equity * (1.0 - _num(leg, "discount_pct") / 100.0)
    if method in _MULTIPLE_METHODS:
        mult = _num_opt(leg, "target_multiple")
        if mult is None:
            raise ValueError(f"broker_synth: chân {method} thiếu target_multiple")
        if method == "EV_EBITDA":
            ebitda = _num_opt(fc, "ebitda_bn")
            if ebitda is None:
                raise ValueError("broker_synth: EV_EBITDA thiếu forecast.ebitda_bn")
            return mult * ebitda - net_debt - minority + other
        base_bn_key, per_share_key = ("npat_bn", "eps") if method == "PE" else ("equity_bn", "bvps")
        if fc.get(base_bn_key) is not None:
            return mult * float(fc[base_bn_key])
        if fc.get(per_share_key) is not None and shares_used_mn:
            return mult * float(fc[per_share_key]) * shares_used_mn / 1000.0
        raise ValueError(
            f"broker_synth: {method} thiếu forecast.{base_bn_key} hoặc {per_share_key}+shares_used_mn"
        )
    raise ValueError(f"broker_synth: phương pháp không hỗ trợ {method!r}")


def report_equity_bn(rep: dict) -> float:
    """Vốn chủ (tỷ đồng) tại ngày báo cáo, theo phương pháp CTCK; BLEND = Σ trọng số × chân."""
    shares = _num_opt(rep, "shares_used_mn")
    if str(rep.get("method", "")).upper() == "BLEND":
        legs = rep.get("legs") or []
        total_w = sum(float(leg["weight"]) for leg in legs)
        if not legs or abs(total_w - 1.0) > 1e-6:
            raise ValueError(
                f"broker_synth: BLEND {rep.get('broker')} trọng số phải cộng = 1 (đang {total_w})"
            )
        return sum(float(leg["weight"]) * _leg_equity_bn(leg, shares) for leg in legs)
    return _leg_equity_bn(rep, shares)


def company_coe(company) -> float:
    """COE như dcf.py: nhập tay nếu có, không thì CAPM rf + β×ERP."""
    a = company.assumptions
    return float(a.cost_of_equity or (a.risk_free_rate + a.beta * a.erp))


def valuate_broker_synth(company, cfg: dict, today: date | None = None) -> dict[str, Any]:
    """Tổng hợp các báo cáo CTCK → giá trị/cp hôm nay theo số cp hiện tại."""
    p = _cfg()
    today = today or date.today()
    shares_now = float(company.shares_outstanding)
    if shares_now <= 0:
        raise ValueError("broker_synth: shares_outstanding ≤ 0")
    coe = company_coe(company)
    events = cfg.get("capital_events_after_report") or []
    flags: list[str] = []
    details, values, weights = [], [], []
    for rep in cfg.get("reports") or []:
        rdate = date.fromisoformat(str(rep["date"]))
        age = (today - rdate).days
        broker = str(rep["broker"])
        if age > int(p["max_report_age_days"]) or age < 0:
            details.append({"broker": broker, "date": str(rdate), "excluded": f"tuổi {age} ngày"})
            continue
        equity_bn = report_equity_bn(rep)
        d: dict[str, Any] = {
            "broker": broker,
            "date": str(rdate),
            "method": rep.get("method"),
            "equity_value_bn": equity_bn,
            "target_price": rep.get("target_price"),
        }
        # Kiểm nhất quán: tính lại tại số cp CTCK dùng phải ra giá mục tiêu ± ngưỡng.
        shares_used = _num_opt(rep, "shares_used_mn")
        tp = _num_opt(rep, "target_price")
        if shares_used and tp:
            recon = equity_bn / shares_used * 1000.0
            gap = recon / tp - 1.0
            d.update(recon_price=recon, recon_gap=gap)
            if abs(gap) > float(p["recon_tolerance"]):
                flags.append(f"BROKER_SYNTH_RECON_GAP:{broker}")
                d["recon_note"] = (
                    f"tính lại {recon:,.0f} vs giá mục tiêu {tp:,.0f} đ/cp ({gap:+.0%})"
                )
        # Vốn vào/ra sau ngày báo cáo (đến hôm nay): + tiền phát hành, − cổ tức tiền.
        later = [e for e in events if rdate < date.fromisoformat(str(e["date"])) <= today]
        adj = sum(_num(e, "proceeds_bn") - _num(e, "cash_dividend_bn") for e in later)
        value = (equity_bn + adj) / shares_now * 1000.0
        if (
            str(rep.get("horizon", "valuation_date")) == "12m_forward"
            and p["discount_forward_to_today"]
        ):
            # Damodaran: giá mục tiêu 12T là giá kỳ vọng sau 1 năm → chiết về hôm nay bằng COE.
            value /= 1.0 + coe
        d.update(capital_adjustment_bn=adj, fair_value_per_share=value)
        details.append(d)
        values.append(value)
        weights.append(recency_weight(age, p.get("recency_half_life_days")))
    if not values:
        raise ValueError(
            f"broker_synth: {company.ticker} không còn báo cáo nào trong {p['max_report_age_days']} ngày"
        )
    fv = weighted_median(values, weights)
    used = [d for d in details if "fair_value_per_share" in d]
    label = "Mô hình tổng hợp CTCK ({} báo cáo: {})".format(
        len(used), ", ".join(f"{d['broker']} {d['date']}" for d in used)
    )
    return {
        "blended_fair_value_per_share": fv,
        "method": "BROKER_SYNTH",
        "method_label": label,
        "reports": details,
        "cost_of_equity": coe,
        "shares_now_mn": shares_now,
        "flags": flags,
    }
