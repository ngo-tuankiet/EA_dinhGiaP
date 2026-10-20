"""Nghiên cứu chu kỳ ngành thép & HPG: nạp dữ liệu, chạy thống kê, ghi reports/steel_cycle/results.json.

    python -m scripts.steel_cycle_report            # dùng dữ liệu đã lưu ở data/steel_cycle/
    python -m scripts.steel_cycle_report --refresh  # tải lại từ FRED, World Bank, vnstock

Nguồn (đều trong macro_sources.allowed_domains): FRED (chỉ số giá thép Mỹ WPU101 từ 1926, CPI Mỹ),
World Bank Pink Sheet (quặng sắt, than theo tháng từ 1960), vnstock (giá điều chỉnh HPG/HSG/NKG/VNINDEX),
DB nội bộ (BCTC quý → biên gộp). Không ghi DB.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import urllib.parse
from pathlib import Path

import pandas as pd

from valuation.analysis import steel_cycle as sc
from valuation.config import PROJECT_ROOT, get_macro_allowed_domains, load_defaults

DATA = PROJECT_ROOT / "data" / "steel_cycle"
OUT = PROJECT_ROOT / "reports" / "steel_cycle"


def _get(url: str) -> bytes:
    import httpx

    host = urllib.parse.urlparse(url).hostname
    if host not in get_macro_allowed_domains():
        raise PermissionError(f"{host} chưa nằm trong macro_sources.allowed_domains")
    cfg = load_defaults().get("macro_sources", {}) or {}
    r = httpx.get(url, timeout=60, headers={"User-Agent": cfg.get("user_agent", "antigravity-vn100/1.0")})
    r.raise_for_status()
    return r.content


def refresh(cfg: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for fred_id, name in cfg["fred_series"].items():
        text = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}").decode()
        df = pd.read_csv(io.StringIO(text), na_values=".")
        if list(df.columns) != ["observation_date", fred_id]:
            raise ValueError(f"FRED {fred_id}: header lạ {list(df.columns)}")
        df.columns = ["date", name]
        df.to_csv(DATA / f"{name}.csv", index=False)

    page = _get(cfg["worldbank_page"]).decode("utf-8", "ignore")
    links = re.findall(r'https://thedocs\.worldbank\.org[^"]*CMO-Historical-Data-Monthly\.xlsx', page)
    if not links:
        raise ValueError("Không tìm thấy link CMO-Historical-Data-Monthly.xlsx trên trang World Bank")
    raw = pd.read_excel(io.BytesIO(_get(links[0])), sheet_name="Monthly Prices", header=4)
    raw = raw.rename(columns={raw.columns[0]: "period"})
    raw = raw[raw["period"].astype(str).str.match(r"^\d{4}M\d{2}$")]
    wb = pd.DataFrame({"date": pd.PeriodIndex(raw["period"].str.replace("M", "-"), freq="M").to_timestamp()})
    for col, name in cfg["worldbank_series"].items():
        wb[name] = pd.to_numeric(raw[col].values, errors="coerce")  # '…' = thiếu số liệu
    wb.to_csv(DATA / "worldbank.csv", index=False)

    # Gói tài trợ vnstock_data: đủ lịch sử từ khi niêm yết (bản community trong vnstock_client giới hạn 8 năm).
    from vnstock_data import Quote

    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    for t in [*cfg["stocks"], "VNINDEX"]:
        df = Quote(symbol=t, source="vci").history(start="2000-01-01", end=today, interval="1D")[["time", "close"]]
        df.to_csv(DATA / f"px_{t}.csv", index=False)


def _monthly(path: Path, col: str) -> pd.Series:
    df = pd.read_csv(path, parse_dates=[0])
    s = df.set_index(df.columns[0])[col].dropna()
    return s.groupby(s.index.to_period("M")).last()


def load_series(cfg: dict) -> dict[str, pd.Series]:
    cpi = _monthly(DATA / "us_cpi.csv", "us_cpi")
    def real(s: pd.Series) -> pd.Series:  # USD thực theo mặt bằng giá hiện tại
        return (s / cpi.reindex(s.index)).dropna() * float(cpi.iloc[-1])

    out = {
        "steel_ppi_real": real(_monthly(DATA / "steel_ppi.csv", "steel_ppi")),
        "iron_ore_real": real(_monthly(DATA / "worldbank.csv", "iron_ore")),
        "coal_real": real(_monthly(DATA / "worldbank.csv", "coal_aus")),
    }
    for t in [*cfg["stocks"], "VNINDEX"]:
        out[t] = _monthly(DATA / f"px_{t}.csv", "close")
    return out


def gross_margins(tickers: list[str]) -> pd.DataFrame:
    """Biên gộp quý từ DB nội bộ (quý rời, Q0 = cả năm bị bỏ)."""
    from valuation.db.models import FinancialsQuarterly as F
    from valuation.db.session import SessionLocalRead

    db = SessionLocalRead()
    try:
        rows = (
            db.query(F.ticker, F.fiscal_year, F.fiscal_quarter, F.line_item, F.value)
            .filter(F.ticker.in_(tickers), F.statement == "IS", F.fiscal_quarter > 0,
                    F.line_item.in_(["net_sales", "gross_profit"]))
            .all()
        )
    finally:
        db.close()
    df = pd.DataFrame(rows, columns=["ticker", "y", "q", "item", "value"]).astype({"value": float})
    p = df.pivot_table(index=["ticker", "y", "q"], columns="item", values="value").reset_index()
    p["gm"] = p["gross_profit"] / p["net_sales"]
    p["period"] = pd.PeriodIndex.from_fields(year=p["y"], quarter=p["q"], freq="Q")
    return p.pivot(index="period", columns="ticker", values="gm").sort_index()


def analyse_series(s: pd.Series, threshold: float, horizons: list[int]) -> dict:
    v = s.tolist()
    turns, state = sc.zigzag(v, threshold)
    ph = sc.phases(v, turns)
    idx = s.index
    done = [p for p in ph if not p["censored"]]
    cur = ph[-1] if ph else None
    res = {
        "threshold": threshold,
        "start": str(idx[0]),
        "end": str(idx[-1]),
        "turns": [{"date": str(idx[t.idx]), "kind": t.kind, "confirmed": str(idx[t.confirmed_idx]),
                   "recognition_lag_months": t.confirmed_idx - t.idx, "level": v[t.idx]} for t in turns],
        "phases": [{**p, "start": str(idx[p["start"]]), "end": str(idx[p["end"]])} for p in ph],
        "up": sc.duration_stats(ph, "up"),
        "down": sc.duration_stats(ph, "down"),
        "cycles_trough_to_trough": [
            turns[j].idx - turns[i].idx
            for i in range(len(turns)) for j in range(i + 1, len(turns))
            if turns[i].kind == turns[j].kind == "T" and j == i + 2
        ],
    }
    if cur:
        same = [p for p in ph if p["type"] == cur["type"]]
        res["current"] = {
            "type": cur["type"], "start": str(idx[cur["start"]]), "age_months": cur["months"],
            "change": cur["change"],
            "drawup_from_extreme": v[-1] / max(v[cur["start"]:]) - 1 if cur["type"] == "up"
            else v[-1] / min(v[cur["start"]:]) - 1,
            "prob_end": {h: sc.prob_end_within([p["months"] for p in same], [p["censored"] for p in same],
                                               cur["months"], h) for h in horizons},
        }
    res["n_completed_phases"] = len(done)
    res["_state"] = state
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    cfg = load_defaults()["steel_cycle"]
    if args.refresh or not (DATA / "worldbank.csv").exists():
        refresh(cfg)
    series = load_series(cfg)
    horizons = cfg["horizons_months"]
    commodities = ["steel_ppi_real", "iron_ore_real", "coal_real"]
    res: dict = {"series": {}, "sensitivity": {}}
    for name, s in series.items():
        th = cfg["threshold_commodity"] if name in commodities else cfg["threshold_stock"]
        res["series"][name] = analyse_series(s, th, horizons)
        sens = cfg["sensitivity_commodity"] if name in commodities else cfg["sensitivity_stock"]
        res["sensitivity"][name] = {
            str(t): {k: analyse_series(s, t, horizons)[k] for k in ("up", "down", "n_completed_phases")}
            for t in sens
        }

    # Xác suất pha hiện tại kết thúc theo mẫu GỘP giá thép + quặng + than thực (nhiều pha hơn từng chuỗi),
    # tách "toàn lịch sử" và "kỷ nguyên hiện đại" (Trung Quốc chi phối, quặng giá giao ngay).
    commodity_pool = ("steel_ppi_real", "iron_ore_real", "coal_real")
    for era, since in (("all", None), ("modern", cfg["modern_since"])):
        pool: dict[str, list] = {"up": [], "down": []}
        for name in commodity_pool:
            for p in res["series"][name]["phases"]:
                if since is None or p["start"] >= since:
                    pool[p["type"]].append(p)
        res[f"pooled_{era}"] = {
            k: {**sc.duration_stats(v, k), "n_incl_ongoing": len(v)} for k, v in pool.items()
        }
        res[f"pooled_prob_end_{era}"] = {}
        for name in commodity_pool:
            cur = res["series"][name]["current"]
            same = pool[cur["type"]]
            res[f"pooled_prob_end_{era}"][name] = {
                h: sc.prob_end_within([p["months"] for p in same], [p["censored"] for p in same], cur["age_months"], h)
                for h in horizons
            }
        for name in commodity_pool:
            ph = [p for p in res["series"][name]["phases"] if since is None or p["start"] >= since]
            res["series"][name][f"stats_{era}"] = {k: sc.duration_stats(ph, k) for k in ("up", "down")}

    # HPG so với chu kỳ hàng hóa: tương quan trễ, lợi suất 12 tháng tới theo trạng thái, độ trễ đỉnh/đáy.
    ret = {k: s.pct_change() for k, s in series.items()}
    hpg = series["HPG"]
    res["hpg_vs"] = {}
    for other in ("iron_ore_real", "steel_ppi_real", "coal_real", "VNINDEX", "HSG", "NKG"):
        st = pd.Series(res["series"][other]["_state"], index=series[other].index).reindex(hpg.index)
        res["hpg_vs"][other] = {
            "lagged_corr": sc.lagged_correlation(ret["HPG"], ret[other], cfg["max_lag_months"]),
            "fwd_by_state": sc.forward_return_by_state(hpg, st, cfg["forward_months"]),
            "turn_lags": [
                {**r, "date": str(r["date"]), "other": str(r["other"]) if r["other"] is not None else None}
                for r in sc.turn_lags(
                    [(pd.Period(t["date"]), t["kind"]) for t in res["series"]["HPG"]["turns"]],
                    [(pd.Period(t["date"]), t["kind"]) for t in res["series"][other]["turns"]],
                    window=18,
                )
            ],
            # Nghiên cứu sự kiện: HPG sau mỗi lần chuỗi kia XÁC NHẬN đỉnh/đáy (biết được tại thời điểm đó).
            "events": sc.event_returns(
                hpg,
                [(pd.Period(t["confirmed"]), t["kind"]) for t in res["series"][other]["turns"]],
                horizons,
            ),
        }
    own = pd.Series(res["series"]["HPG"]["_state"], index=hpg.index)
    ore = pd.Series(res["series"]["iron_ore_real"]["_state"], index=series["iron_ore_real"].index).reindex(hpg.index)
    res["hpg_fwd_own_state"] = sc.forward_return_by_state(hpg, own, cfg["forward_months"])
    res["hpg_fwd_joint_state"] = sc.forward_return_by_state(hpg, own.str.cat(ore, sep="|"), cfg["forward_months"])
    res["hpg_seasonality"] = sc.seasonality(ret["HPG"].set_axis(ret["HPG"].index.to_timestamp()))
    res["vnindex_seasonality"] = sc.seasonality(ret["VNINDEX"].set_axis(ret["VNINDEX"].index.to_timestamp()))

    # Biên gộp quý (2018+) — đo lợi nhuận thật của DN thép, và quan hệ trễ với giá cổ phiếu.
    gm = gross_margins(cfg["stocks"])
    q_px = hpg.groupby(hpg.index.asfreq("Q")).last()
    res["gross_margin"] = {t: {str(p): (None if pd.isna(x) else float(x)) for p, x in gm[t].items()} for t in gm}
    res["hpg_price_vs_margin_corr"] = sc.lagged_correlation(gm["HPG"].diff(), q_px.pct_change(), 4)
    ore_q = series["iron_ore_real"].groupby(series["iron_ore_real"].index.asfreq("Q")).mean()
    res["hpg_margin_vs_ore_corr"] = sc.lagged_correlation(gm["HPG"].diff(), ore_q.pct_change(), 4)

    # Chuỗi cho biểu đồ (log giá tháng) — bỏ trạng thái nội bộ.
    res["chart"] = {k: {"dates": [str(p) for p in s.index], "values": [round(float(x), 4) for x in s]} for k, s in series.items()}
    # Mẫu gộp cổ phiếu thép VN (HPG+HSG+NKG): ba mã đi cùng nhịp nên KHÔNG độc lập — chỉ để tham khảo.
    stock_pool = {"up": [], "down": []}
    for t in cfg["stocks"]:
        for p in res["series"][t]["phases"]:
            stock_pool[p["type"]].append(p)
    res["pooled_stocks"] = {k: sc.duration_stats(v, k) for k, v in stock_pool.items()}
    hpg_base = (hpg.shift(-cfg["forward_months"]) / hpg - 1).dropna()
    res["hpg_base"] = {"n": len(hpg_base), "n_independent": round(len(hpg_base) / cfg["forward_months"], 1),
                       "mean": float(hpg_base.mean()), "median": float(hpg_base.median()),
                       "hit_rate": float((hpg_base > 0).mean())}

    for r in res["series"].values():
        r.pop("_state")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float))
    export_tables(res, series, gm, stock_pool, cfg)
    print(f"Đã ghi {OUT / 'results.json'} và các bảng CSV")


def export_tables(res: dict, series: dict, gm: pd.DataFrame, stock_pool: dict, cfg: dict) -> None:
    """Bảng phẳng cho trang báo cáo (mỗi bảng một nguồn dữ liệu, truy vết được)."""
    commodities = {"steel_ppi_real", "iron_ore_real", "coal_real"}
    rows = [{"date": str(p), "series": k, "value": round(float(v), 4)}
            for k, s in series.items() for p, v in s.items() if k not in commodities or str(p) >= "1960-01"]
    pd.DataFrame(rows).to_csv(OUT / "monthly.csv", index=False)

    ph = [{"series": k, **{c: p[c] for c in ("type", "start", "end", "months", "change", "censored")},
           "threshold": s["threshold"]} for k, s in res["series"].items() for p in s["phases"]]
    pd.DataFrame(ph).to_csv(OUT / "phases.csv", index=False)

    st = []
    for k, s in res["series"].items():
        for era in ("all", "modern"):
            src = s.get(f"stats_{era}") if k in commodities else ({"up": s["up"], "down": s["down"]} if era == "all" else None)
            for typ, d in (src or {}).items():
                st.append({"group": k, "era": era, "type": typ, "threshold": s["threshold"], **d})
    for era in ("all", "modern"):
        for typ, d in res[f"pooled_{era}"].items():
            st.append({"group": "pool_commodity", "era": era, "type": typ, "threshold": cfg["threshold_commodity"],
                       **{x: d.get(x) for x in ("n", "median_months", "mean_months", "min_months", "max_months", "median_change")}})
    for typ, d in res["pooled_stocks"].items():
        st.append({"group": "pool_vn_steel", "era": "all", "type": typ, "threshold": cfg["threshold_stock"], **d})
    pd.DataFrame(st).to_csv(OUT / "phase_stats.csv", index=False)

    cur = []
    for k, s in res["series"].items():
        c = s["current"]
        if k in commodities:
            pe, basis = res["pooled_prob_end_modern"][k], "pool_commodity_modern"
        elif k in cfg["stocks"]:
            same = stock_pool[c["type"]]
            pe = {h: sc.prob_end_within([p["months"] for p in same], [p["censored"] for p in same], c["age_months"], h)
                  for h in cfg["horizons_months"]}
            basis = "pool_vn_steel"
        else:
            pe, basis = c["prob_end"], "own"
        cur.append({"series": k, "type": c["type"], "start": c["start"], "age_months": c["age_months"],
                    "change": c["change"], "from_extreme": c["drawup_from_extreme"],
                    "p_end_6": pe[6]["prob"], "p_end_12": pe[12]["prob"], "n_at_risk": pe[12]["n_at_risk"],
                    "basis": basis, "as_of": s["end"]})
    pd.DataFrame(cur).to_csv(OUT / "current.csv", index=False)

    sr = [{"condition": "base", "state": "all", **res["hpg_base"]}]
    for o, d in res["hpg_vs"].items():
        sr += [{"condition": o, "state": stt, **v} for stt, v in d["fwd_by_state"].items()]
    sr += [{"condition": "HPG", "state": stt, **v} for stt, v in res["hpg_fwd_own_state"].items()]
    sr += [{"condition": "HPG|iron_ore_real", "state": stt, **v} for stt, v in res["hpg_fwd_joint_state"].items()]
    pd.DataFrame(sr).to_csv(OUT / "state_returns.csv", index=False)

    ev = [{"other": o, "id": f"{o}:{e['date']}", **e} for o, d in res["hpg_vs"].items() for e in d["events"]
          if o in commodities | {"VNINDEX"}]
    pd.DataFrame(ev).to_csv(OUT / "events.csv", index=False)

    ll = [{"other": o, "id": f"{o}:{r['date']}", "hpg_turn": r["date"], "kind": r["kind"], "other_turn": r["other"],
           "lag_months": r["lag_months"]} for o, d in res["hpg_vs"].items() for r in d["turn_lags"]]
    pd.DataFrame(ll).to_csv(OUT / "lead_lag.csv", index=False)

    lc = [{"pair": f"HPG~{o}", "freq": "M", "lag": int(k), "corr": v}
          for o, d in res["hpg_vs"].items() for k, v in d["lagged_corr"].items()]
    lc += [{"pair": "margin~HPG", "freq": "Q", "lag": int(k), "corr": v} for k, v in res["hpg_price_vs_margin_corr"].items()]
    lc += [{"pair": "margin~iron_ore_real", "freq": "Q", "lag": int(k), "corr": v} for k, v in res["hpg_margin_vs_ore_corr"].items()]
    pd.DataFrame(lc).to_csv(OUT / "lag_corr.csv", index=False)

    se = [{"series": n, "month": m, **v} for n, key in (("HPG", "hpg_seasonality"), ("VNINDEX", "vnindex_seasonality"))
          for m, v in res[key].items()]
    pd.DataFrame(se).to_csv(OUT / "seasonality.csv", index=False)

    g = gm.reset_index().melt(id_vars="period", var_name="ticker", value_name="gross_margin").dropna()
    g["period"] = g["period"].astype(str)
    g.to_csv(OUT / "gross_margin.csv", index=False)


if __name__ == "__main__":
    main()
