"""Chỉ số định lượng cho nghiên cứu tích sản (chỉ đọc DB) → signals_20260929.csv/.json.

Mọi chỉ số tính từ vn100_full.db; công thức ghi trong FORMULAS (xuất kèm JSON).
  PYTHONPATH=. ~/.venv/bin/python reports/research/signals_20260929.py
"""
from __future__ import annotations

import csv
import datetime
import json
import math
import statistics
from pathlib import Path

from valuation.data_access.repo import build_company_data
from valuation.db.models import CorporateAction, PricesDaily
from valuation.db.session import SessionLocalRead
from valuation.ingest.universe import get_vn100_symbols

OUT = Path(__file__).with_suffix("")
AS_OF = datetime.date(2026, 9, 29)
FORMULAS = {
    "adtv20_bn": "Trung bình 20 phiên (close × volume) / 1e9 — cột value trong DB trống",
    "ret_{n}": "close_t / close_{t-n phiên} - 1 (giá đã điều chỉnh quyền của VCI)",
    "vs_sma50/vs_sma200": "close / SMA(n) - 1",
    "rsi14": "RSI Wilder 14 phiên",
    "pos_52w": "(close - min 250 phiên) / (max - min)",
    "dd_from_52w_high": "close / max 250 phiên - 1",
    "vol60_ann": "độ lệch chuẩn log-return 60 phiên × sqrt(250)",
    "cmf20": "Chaikin Money Flow 20 phiên = Σ(((C-L)-(H-C))/(H-L)·V) / ΣV",
    "updown_vol60": "Σ khối lượng phiên tăng / Σ khối lượng phiên giảm, 60 phiên",
    "obv_trend60": "(OBV_t - OBV_{t-60}) / Σ khối lượng 60 phiên",
    "fnet_{w}_ratio": "Σ foreign_net_val / Σ(close×volume) trên các phiên CÓ dữ liệu khối ngoại trong cửa sổ",
    "prop_net_ratio": "Σ proprietary_net_val / Σ(close×volume), các phiên có dữ liệu tự doanh",
    "cfo_ni_3y": "Σ CFO 3 năm tài chính / Σ LNST mẹ 3 năm (phi ngân hàng)",
    "fcf_3y_bn": "Σ (CFO - capex) 3 năm tài chính",
    "fcf_yield_ttm": "(CFO - capex) TTM / vốn hóa",
    "div_cash_12m": "Σ cổ tức tiền (đ/cp) GDKHQ trong 365 ngày / giá",
    "issuance_3y": "Sự kiện phát hành có thu tiền/pha loãng (ESOP, quyền mua, riêng lẻ, chuyển đổi) 3 năm",
    "stock_div_3y": "Σ tỷ lệ cổ tức CP/thưởng 3 năm (không pha loãng giá trị, nhưng dấu hiệu giữ tiền)",
}


def _series(db, t):
    rows = (
        db.query(PricesDaily)
        .filter(PricesDaily.ticker == t, PricesDaily.trade_date <= AS_OF)
        .order_by(PricesDaily.trade_date)
        .all()
    )
    return [r for r in rows if r.close]


def _rsi(closes, n=14):
    if len(closes) <= n:
        return None
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, lo in zip(gains[n:], losses[n:]):
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + lo) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def price_signals(rows):
    c = [float(r.close) for r in rows]
    v = [float(r.volume or 0) for r in rows]
    if len(c) < 60:
        return {}
    tv = [ci * vi for ci, vi in zip(c, v)]
    out = {"price_date": rows[-1].trade_date.isoformat(), "close": c[-1], "adtv20_bn": statistics.mean(tv[-20:]) / 1e9}
    for n in (20, 60, 120, 250):
        if len(c) > n:
            out[f"ret_{n}"] = c[-1] / c[-1 - n] - 1
    for n in (50, 200):
        if len(c) >= n:
            out[f"vs_sma{n}"] = c[-1] / statistics.mean(c[-n:]) - 1
    out["rsi14"] = _rsi(c[-120:])
    hi, lo = max(c[-250:]), min(c[-250:])
    out["pos_52w"] = (c[-1] - lo) / (hi - lo) if hi > lo else None
    out["dd_from_52w_high"] = c[-1] / hi - 1
    lr = [math.log(c[i] / c[i - 1]) for i in range(len(c) - 60, len(c))]
    out["vol60_ann"] = statistics.pstdev(lr) * math.sqrt(250)
    mf, vs = 0.0, 0.0
    for r in rows[-20:]:
        h, l_, cl, vol = float(r.high or 0), float(r.low or 0), float(r.close), float(r.volume or 0)
        if h > l_:
            mf += ((cl - l_) - (h - cl)) / (h - l_) * vol
        vs += vol
    out["cmf20"] = mf / vs if vs else None
    up = sum(v[i] for i in range(len(c) - 60, len(c)) if c[i] > c[i - 1])
    dn = sum(v[i] for i in range(len(c) - 60, len(c)) if c[i] < c[i - 1])
    out["updown_vol60"] = up / dn if dn else None
    obv = 0.0
    obv_hist = []
    for i in range(1, len(c)):
        obv += v[i] if c[i] > c[i - 1] else (-v[i] if c[i] < c[i - 1] else 0)
        obv_hist.append(obv)
    out["obv_trend60"] = (obv_hist[-1] - obv_hist[-61]) / sum(v[-60:]) if sum(v[-60:]) else None
    for w in (20, 60, 120):
        win = [r for r in rows[-w * 3 :] if r.foreign_net_val is not None][-w:]  # w phiên CÓ dữ liệu gần nhất
        if win:
            den = sum(float(r.close) * float(r.volume or 0) for r in win)
            out[f"fnet_{w}_ratio"] = sum(float(r.foreign_net_val) for r in win) / den if den else None
            out[f"fnet_{w}_bn"] = sum(float(r.foreign_net_val) for r in win) / 1e9
            out[f"fnet_{w}_last_date"] = win[-1].trade_date.isoformat()
    pw = [r for r in rows[-250:] if r.proprietary_net_val is not None][-60:]
    if pw:
        den = sum(float(r.close) * float(r.volume or 0) for r in pw)
        out["prop_net_ratio"] = sum(float(r.proprietary_net_val) for r in pw) / den if den else None
        out["prop_last_date"] = pw[-1].trade_date.isoformat()
    return out


def fundamental_signals(db, t, price):
    c = build_company_data(db, t, mode="TTM", fetch_live=False)
    out = {"shares_m": c.shares_outstanding}
    mcap_bn = price * c.shares_outstanding / 1e3
    out["mcap_bn"] = mcap_bn
    is_bank = hasattr(c.historical_is[-1], "net_interest_income")
    out["is_bank"] = is_bank
    cf = getattr(c, "historical_cf", None) or []
    if not is_bank and cf:
        fy_is = {x.year: x for x in c.historical_is[:-1]}
        fy_cf = [x for x in cf[:-1] if x.year in fy_is][-3:]
        ni3 = sum(fy_is[x.year].net_income for x in fy_cf)
        cfo3 = sum(x.cfo for x in fy_cf)
        out["cfo_ni_3y"] = cfo3 / ni3 if ni3 > 0 else None
        out["fcf_3y_bn"] = sum(x.cfo - abs(x.capex) for x in fy_cf)
        out["div_paid_3y_bn"] = sum(x.dividends_paid for x in fy_cf)
        ttm = cf[-1]
        out["fcf_yield_ttm"] = (ttm.cfo - abs(ttm.capex)) / mcap_bn if mcap_bn else None
        out["cf_full_sections"] = all(getattr(x, "has_full_cashflow_sections", True) for x in fy_cf)
    return out


def action_signals(db, t, price):
    since = AS_OF - datetime.timedelta(days=3 * 365)
    evs = (
        db.query(CorporateAction)
        .filter(CorporateAction.ticker == t, CorporateAction.ex_right_date >= since, CorporateAction.ex_right_date <= AS_OF)
        .all()
    )
    seen = set()
    cash12, stock3, issuance = 0.0, 0.0, []
    for e in evs:
        k = (e.event_type, e.ex_right_date, e.exercise_ratio, e.cash_amount_vnd_per_share)
        if k in seen:
            continue
        seen.add(k)
        if e.event_type == "CASH_DIVIDEND" and e.cash_amount_vnd_per_share and e.ex_right_date >= AS_OF - datetime.timedelta(days=365):
            cash12 += float(e.cash_amount_vnd_per_share)
        elif e.event_type in ("STOCK_DIVIDEND", "BONUS_SHARE") and e.exercise_ratio:
            stock3 += float(e.exercise_ratio)
        elif e.event_type in ("ESOP", "RIGHTS_ISSUE", "PRIVATE_PLACEMENT", "CONVERTIBLE", "SHARE_ISSUE"):
            issuance.append(f"{e.event_type}:{e.ex_right_date}:{e.exercise_ratio}")
    return {"div_cash_12m": cash12 / price if price else None, "div_cash_12m_vnd": cash12,
            "stock_div_3y": stock3, "issuance_3y": "; ".join(sorted(issuance))}


def main():
    db = SessionLocalRead()
    rows_out = []
    try:
        for t in get_vn100_symbols():
            rows = _series(db, t)
            ps = price_signals(rows)
            rec = {"ticker": t, **ps}
            price = ps.get("close")
            if price:
                try:
                    rec.update(fundamental_signals(db, t, price))
                except Exception as e:  # noqa: BLE001 — ghi lỗi vào cột, không nuốt
                    rec["fund_error"] = f"{type(e).__name__}: {str(e)[:80]}"
                rec.update(action_signals(db, t, price))
            rows_out.append(rec)
    finally:
        db.close()
    keys = sorted({k for r in rows_out for k in r}, key=lambda k: (k != "ticker", k))
    with open(OUT.with_suffix(".csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows_out)
    json.dump({"as_of": AS_OF.isoformat(), "formulas": FORMULAS, "rows": rows_out},
              open(OUT.with_suffix(".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"→ {OUT.with_suffix('.csv')} ({len(rows_out)} mã)")


if __name__ == "__main__":
    main()
