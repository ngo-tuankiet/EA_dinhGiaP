"""Khung "Tổng quan thị trường" trên sidebar — nhìn 5 giây, mở chi tiết khi cần (D51).

Chấm 4 trụ cột −1/0/+1 theo quy tắc cố định (ngưỡng: config/defaults.yaml → market_overview):
vĩ mô & chính sách, xu hướng VN-Index & độ rộng, khối ngoại, định giá. Tổng → Thuận lợi /
Trung tính / Khó khăn. Ngành/mã nổi bật chỉ theo giá + dòng tiền khối ngoại. Render chỉ đọc DB và
snapshot xếp hạng — không gọi mạng/AI. Chấm điều kiện HIỆN TẠI, không dự báo giá, không khuyến nghị.
"""

from __future__ import annotations

import datetime
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from valuation.views.macro_panel import MacroObs, _pct, _pts

# normalizer mặc định coi giá là nghìn đồng và nhân ×1000 — áp cả cho VNINDEX.
_INDEX_SCALE = 1000.0
_ROUTING = Path(__file__).resolve().parents[1] / "config" / "routing.json"
_SECTOR_NAMES = {"NH": "Ngân hàng", "CK": "Chứng khoán", "BH": "Bảo hiểm"}
_LEVELS = {1: "✅", 0: "➖", -1: "❌", None: "⚪"}


@dataclass(frozen=True)
class Pillar:
    name: str
    score: int | None  # None = thiếu dữ liệu
    summary: str
    details: list[str] = field(default_factory=list)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def _vi(x: float, digits: int = 0) -> str:
    return f"{x:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _chg(x: float) -> str:
    return f"{x * 100:+.1f}%".replace(".", ",").replace("-", "−")


def _summary(sig: list[tuple[int, str]], score: int) -> str:
    if score == 0:
        return (
            "tín hiệu trái chiều" if any(s for s, _ in sig) else "chưa có tín hiệu rõ"
        )
    return ", ".join(t for s, t in sig if s == score)


def macro_pillar(snap: dict[str, MacroObs], mcfg: dict, cfg: dict) -> Pillar:
    """Mỗi tín hiệu +1 (hỗ trợ) / −1 (cản trở); trụ cột = dấu của tổng."""
    name = "Vĩ mô & chính sách"
    sig: list[tuple[int, str]] = []
    det: list[str] = []
    cpi, vn10, us10 = (snap.get(k) for k in ("CPI_YOY", "TPCP_10Y", "UST_10Y"))
    if cpi:
        target = float(mcfg.get("cpi_target", 0.045))
        band = float(mcfg.get("cpi_near_band", 0.005))
        s = -1 if cpi.value > target else (1 if cpi.value < target - band else 0)
        word = {-1: "vượt", 0: "sát", 1: "dưới"}[s]
        sig.append((s, f"CPI {word} mục tiêu"))
        det.append(
            f"CPI {_pct(cpi.value)} ({cpi.date:%m/%Y}) {word} mục tiêu {_pct(target, 1)}"
        )
    if vn10 and us10:
        spread = vn10.value - us10.value
        s = -1 if spread < 0 else (1 if spread >= float(cfg["spread_comfort"]) else 0)
        sig.append(
            (s, {-1: "TPCP VN < Mỹ", 0: "chênh lệch VN–Mỹ mỏng", 1: "TPCP VN > Mỹ"}[s])
        )
        det.append(
            f"TPCP 10N VN {_pct(vn10.value)} − Mỹ {_pct(us10.value)} = {_pts(spread)}"
        )
    for code, who in (("FED_FUNDS_UPPER", "Fed"), ("POLICY_RATE", "SBV")):
        obs = snap.get(code)
        if not obs:
            continue
        if obs.prev is None or abs(obs.value - obs.prev) < 1e-9:
            s = 0
        else:
            s = 1 if obs.value < obs.prev else -1
        verb = {-1: "tăng", 0: "giữ", 1: "hạ"}[s]
        sig.append((s, f"{who} {verb} lãi suất"))
        det.append(
            f"{who} {verb} lãi suất: {_pct(obs.value)} (số liệu {obs.date:%d/%m/%Y})"
        )
    if not sig:
        return Pillar(name, None, "thiếu dữ liệu")
    score = _sign(sum(s for s, _ in sig))
    return Pillar(name, score, _summary(sig, score), det)


def breadth_share(closes: pd.DataFrame, n: int) -> tuple[float, int] | None:
    """Tỷ lệ mã có giá cuối > MA n phiên của chính nó; (tỷ lệ, số mã đủ dữ liệu)."""
    above = eligible = 0
    for col in closes.columns:
        s = closes[col].dropna()
        if len(s) >= n:
            eligible += 1
            above += bool(s.iloc[-1] > s.iloc[-n:].mean())
    return (above / eligible, eligible) if eligible else None


def trend_pillar(vni: pd.Series, closes: pd.DataFrame, cfg: dict) -> Pillar:
    """VN-Index so MA ngắn/dài (+1/−1 mỗi MA) + độ rộng VN100 trên MA ngắn."""
    name = "Xu hướng & độ rộng"
    sig: list[tuple[int, str]] = []
    det: list[str] = []
    short = int(cfg["ma_short"])
    if not vni.empty:
        last = float(vni.iloc[-1])
        det.append(
            f"VN-Index {_vi(last / _INDEX_SCALE, 2)} điểm ({vni.index[-1]:%d/%m/%Y})"
        )
        for n in (short, int(cfg["ma_long"])):
            if len(vni) >= n:
                ma = float(vni.iloc[-n:].mean())
                s = 1 if last > ma else -1
                pos = "trên" if s > 0 else "dưới"
                sig.append((s, f"VN-Index {pos} MA{n}"))
                det.append(f"MA{n} {_vi(ma / _INDEX_SCALE, 2)} → VN-Index {pos} MA{n}")
        r = int(cfg["return_sessions"])
        if len(vni) > r:
            det.append(
                f"VN-Index {r} phiên: {_chg(last / float(vni.iloc[-1 - r]) - 1)}"
            )
    b = breadth_share(closes, short)
    if b is not None:
        share, n_ok = b
        s = (
            1
            if share >= float(cfg["breadth_high"])
            else (-1 if share <= float(cfg["breadth_low"]) else 0)
        )
        sig.append((s, f"{share:.0%} mã trên MA{short}"))
        det.append(f"Độ rộng: {share:.0%} ({n_ok} mã VN100 đủ dữ liệu) trên MA{short}")
    if not sig:
        return Pillar(name, None, "thiếu dữ liệu")
    score = _sign(sum(s for s, _ in sig))
    return Pillar(name, score, _summary(sig, score), det)


def foreign_pillar(flows: pd.DataFrame, universe: int, cfg: dict) -> Pillar:
    """Tổng mua/bán ròng khối ngoại VN100 trong `return_sessions` phiên gần nhất (VND)."""
    name = "Khối ngoại"
    r = int(cfg["return_sessions"])
    window = flows.dropna(how="all").iloc[-r:]
    covered = int(window.notna().any().sum())
    if window.empty or covered < float(cfg["min_coverage"]) * universe:
        return Pillar(name, None, f"thiếu dữ liệu ({covered}/{universe} mã)")
    total = float(window.sum().sum())
    band = float(cfg["flow_band_bn"]) * 1e9
    score = 1 if total > band else (-1 if total < -band else 0)
    verb = "mua ròng" if total >= 0 else "bán ròng"
    last5 = float(window.iloc[-5:].sum().sum())
    det = [
        f"{len(window)} phiên đến {window.index[-1]:%d/%m/%Y}: {verb} {_vi(abs(total) / 1e9)} tỷ",
        f"5 phiên gần nhất: {'mua' if last5 >= 0 else 'bán'} ròng {_vi(abs(last5) / 1e9)} tỷ",
        f"Độ phủ: {covered}/{universe} mã có dữ liệu khối ngoại",
    ]
    return Pillar(
        name, score, f"{verb} {_vi(abs(total) / 1e9)} tỷ/{len(window)} phiên", det
    )


def valuation_pillar(upsides: list[float], source: str, cfg: dict) -> Pillar:
    """Upside trung vị VN100 theo mô hình dự án (giá trị hợp lý / thị giá − 1)."""
    name = "Định giá"
    if not upsides:
        return Pillar(name, None, "chưa có đợt định giá VN100")
    med = statistics.median(upsides)
    score = (
        1
        if med >= float(cfg["upside_high"])
        else (-1 if med <= float(cfg["upside_low"]) else 0)
    )
    pos = sum(u > 0 for u in upsides)
    det = [
        f"Upside trung vị {_chg(med)} trên {len(upsides)} mã có giá trị hợp lý",
        f"{pos} mã dưới giá trị hợp lý, {len(upsides) - pos} mã trên",
        source,
    ]
    return Pillar(name, score, f"upside trung vị {_chg(med)}", det)


def overall(pillars: list[Pillar], cfg: dict) -> tuple[str, int, int]:
    """(nhãn, tổng điểm, số trụ cột có dữ liệu)."""
    scored = [p.score for p in pillars if p.score is not None]
    total, k = sum(scored), int(cfg["overall_threshold"])
    label = "Thuận lợi" if total >= k else ("Khó khăn" if total <= -k else "Trung tính")
    return label, total, len(scored)


def leaders(
    closes: pd.DataFrame, flows: pd.DataFrame, sectors: dict[str, str], cfg: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bảng mã + bảng ngành theo đà giá tương đối (so trung vị VN100) và khối ngoại.

    So với trung vị VN100 cùng cửa sổ thay vì VN-Index: cùng ngày dữ liệu, không lệch khi
    chuỗi VN-Index chậm cập nhật hơn giá cổ phiếu.
    """
    r, short = int(cfg["return_sessions"]), int(cfg["ma_short"])
    rows = []
    for t in closes.columns:
        s = closes[t].dropna()
        if len(s) <= max(r, short - 1):
            continue
        f = flows[t].dropna().iloc[-r:] if t in flows else pd.Series(dtype=float)
        rows.append(
            {
                "Mã": t,
                "Ngành": sectors.get(t, "Chưa rõ"),
                "ret": float(s.iloc[-1] / s.iloc[-1 - r] - 1),
                "above": bool(s.iloc[-1] > s.iloc[-short:].mean()),
                "flow": float(f.sum()) if len(f) else None,
            }
        )
    tk = pd.DataFrame(rows, columns=["Mã", "Ngành", "ret", "above", "flow"])
    if tk.empty:
        return tk, pd.DataFrame()
    tk["rel"] = tk["ret"] - tk["ret"].median()
    tk["support"] = tk["above"] & (tk["rel"] > 0) & (tk["flow"].fillna(0) > 0)
    sec = tk.groupby("Ngành").agg(
        n=("Mã", "size"),
        rel=("rel", "median"),
        above=("above", "mean"),
        flow=("flow", lambda x: x.dropna().sum()),
    )
    sec = sec[sec["n"] >= int(cfg["sector_min_members"])].copy()
    sec["state"] = 0
    sec.loc[(sec["rel"] > 0) & (sec["flow"] > 0), "state"] = 1
    sec.loc[(sec["rel"] < 0) & (sec["flow"] < 0), "state"] = -1
    return tk.sort_values("rel", ascending=False), sec.sort_values(
        "rel", ascending=False
    )


def sector_map() -> dict[str, str]:
    routing = json.loads(_ROUTING.read_text(encoding="utf-8"))
    return {
        t: _SECTOR_NAMES.get(v.get("sector"), v.get("sector") or "Chưa rõ")
        for t, v in routing.items()
    }


def load_market_data(
    db, cfg: dict
) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame, int]:
    """(VN-Index, giá đóng cửa VN100, khối ngoại VN100, số mã VN100) — cắt đến ngày cuối đủ phủ."""
    from sqlalchemy import or_

    from valuation.db.models import PricesDaily, Ticker

    today = datetime.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    start = today - datetime.timedelta(days=int(cfg["history_days"]))
    rows = (
        db.query(
            PricesDaily.ticker,
            PricesDaily.trade_date,
            PricesDaily.close,
            PricesDaily.foreign_net_val,
        )
        .join(Ticker, Ticker.ticker == PricesDaily.ticker)
        .filter(or_(Ticker.is_vn100, PricesDaily.ticker == "VNINDEX"))
        .filter(PricesDaily.trade_date >= start)
        .all()
    )
    universe = db.query(Ticker).filter(Ticker.is_vn100).count()
    df = pd.DataFrame(rows, columns=["ticker", "date", "close", "flow"])
    if df.empty:
        return pd.Series(dtype=float), pd.DataFrame(), pd.DataFrame(), universe
    df["date"] = pd.to_datetime(df["date"])
    df[["close", "flow"]] = df[["close", "flow"]].astype(float)
    vni = df[df.ticker == "VNINDEX"].set_index("date")["close"].sort_index()
    stocks = df[df.ticker != "VNINDEX"]
    closes = stocks.pivot(index="date", columns="ticker", values="close").sort_index()
    flows = stocks.pivot(index="date", columns="ticker", values="flow").sort_index()
    # Ngày chỉ vài mã được cập nhật lẻ (vd mở 1 mã) không đại diện thị trường → cắt.
    full = closes.notna().sum(axis=1) >= float(cfg["min_coverage"]) * universe
    if full.any():
        last = full[full].index[-1]
        closes, flows = closes.loc[:last], flows.loc[:last]
    return vni, closes, flows, universe


def model_upsides(closes: pd.DataFrame) -> tuple[list[float], str]:
    """Upside theo đợt định giá VN100 mới nhất, chia cho giá đóng cửa mới nhất trong DB."""
    from valuation.services.ranking_store import latest_snapshot

    snap = latest_snapshot()
    if not snap:
        return [], ""
    last = closes.ffill().iloc[-1] if not closes.empty else pd.Series(dtype=float)
    ups = []
    for row in snap.get("rows", []):
        fv = row.get("fair_value")
        price = last.get(row.get("ticker"), row.get("price"))
        if isinstance(fv, (int, float)) and fv > 0 and price and price > 0:
            ups.append(fv / float(price) - 1)
    done = str(snap.get("completed_at", ""))[:10]
    return ups, f"Nguồn: đợt định giá VN100 {done} ÷ giá đóng cửa mới nhất"


_TREND_WORDS = ("ngắn hạn", "trung hạn", "dài hạn")
_SHORT = {
    "Vĩ mô & chính sách": "vĩ mô",
    "Xu hướng & độ rộng": "xu hướng",
    "Khối ngoại": "khối ngoại",
    "Định giá": "định giá",
}


@dataclass(frozen=True)
class IndexView:
    last: float  # điểm
    date: datetime.date
    changes: list[tuple[int, float]]  # (số phiên, % thay đổi)
    trends: list[tuple[str, int]]  # (khung, +1 giá trên MA / −1 dưới MA)
    rsi: float | None
    support: tuple[float, str] | None  # (mức, nguồn) gần nhất DƯỚI giá
    resistance: tuple[float, str] | None  # gần nhất TRÊN giá


def rsi_wilder(close: pd.Series, n: int) -> float | None:
    """RSI Wilder: trung bình lãi/lỗ làm trơn alpha = 1/n.

    shortcut: khởi tạo bằng giá trị đầu thay vì SMA n phiên như Wilder gốc — sai khác tắt dần
    sau vài chục phiên (chuỗi ở đây ~270 phiên); đổi nếu cần khớp từng số với phần mềm khác.
    """
    if len(close) <= n:
        return None
    d = close.diff().dropna()
    gain = float(d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean().iloc[-1])
    loss = float((-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean().iloc[-1])
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def index_view(vni: pd.Series, cfg: dict) -> IndexView | None:
    """Trạng thái kỹ thuật VN-Index: xu hướng theo MA, RSI, hỗ trợ/kháng cự gần nhất."""
    if len(vni) < 2:
        return None
    s = vni / _INDEX_SCALE
    last = float(s.iloc[-1])
    changes = [
        (n, last / float(s.iloc[-1 - n]) - 1)
        for n in cfg["change_sessions"]
        if len(s) > n
    ]
    mas = {
        int(n): float(s.iloc[-int(n) :].mean())
        for n in cfg["ma_trend"]
        if len(s) >= int(n)
    }
    trends = [
        (w, 1 if last > mas[int(n)] else -1)
        for w, n in zip(_TREND_WORDS, cfg["ma_trend"])
        if int(n) in mas
    ]
    win = s.iloc[-int(cfg["level_window"]) :]
    levels = [(v, f"MA{n}") for n, v in mas.items()] + [
        (float(win.min()), f"đáy {len(win)} phiên"),
        (float(win.max()), f"đỉnh {len(win)} phiên"),
    ]
    below = [x for x in levels if x[0] < last]
    above = [x for x in levels if x[0] > last]
    return IndexView(
        last,
        s.index[-1].date(),
        changes,
        trends,
        rsi_wilder(s, int(cfg["rsi_period"])),
        max(below) if below else None,
        min(above) if above else None,
    )


def outlook(view: IndexView, label: str, pillars: list[Pillar], cfg: dict) -> list[str]:
    """Kịch bản CÓ ĐIỀU KIỆN cho các phiên tới — không phải dự báo giá."""
    bad = [_SHORT.get(p.name, p.name) for p in pillars if p.score == -1]
    lines = [
        {
            "Khó khăn": f"Nghiêng thận trọng: {', '.join(bad)} bất lợi — nhịp hồi dễ bị bán.",
            "Thuận lợi": "Nghiêng tích cực: điều kiện đang ủng hộ xu hướng tăng.",
        }.get(
            label, "Chưa rõ xu hướng: chờ vượt kháng cự hoặc thủng hỗ trợ để xác nhận."
        )
    ]
    if view.rsi is not None and view.rsi <= float(cfg["rsi_oversold"]):
        lines.append(
            f"RSI {view.rsi:.0f}: quá bán — dễ có nhịp hồi kỹ thuật, chưa phải đảo chiều."
        )
    elif view.rsi is not None and view.rsi >= float(cfg["rsi_overbought"]):
        lines.append(f"RSI {view.rsi:.0f}: quá mua — dễ rung lắc, điều chỉnh.")
    foreign_bad = any(p.name == "Khối ngoại" and p.score == -1 for p in pillars)
    if view.resistance:
        lvl, src = view.resistance
        lines.append(
            f"▲ Vượt {_vi(lvl, 0)} ({src}) → xu hướng ngắn hạn cải thiện"
            + (", cần khối ngoại mua ròng để xác nhận." if foreign_bad else ".")
        )
    if view.support:
        lvl, src = view.support
        lines.append(f"▼ Thủng {_vi(lvl, 0)} ({src}) → rủi ro giảm sâu hơn.")
    else:
        lines.append(f"▼ Đang ở đáy {cfg['level_window']} phiên — chưa có hỗ trợ gần.")
    return lines


def headline(label: str, pillars: list[Pillar]) -> str:
    """'KHÓ KHĂN — bất lợi: vĩ mô, khối ngoại · thuận: định giá' (thay cho điểm số)."""
    parts = []
    for score, word in ((1, "thuận"), (-1, "bất lợi")):
        names = [_SHORT.get(p.name, p.name) for p in pillars if p.score == score]
        if names:
            parts.append(f"{word}: {', '.join(names)}")
    return f"**{label.upper()}**" + (" — " + " · ".join(parts) if parts else "")


def render_market_overview(db) -> None:
    """Thẻ 5 giây: đèn tổng + 4 trụ cột + ngành/mã nổi bật + nhãn tin; chi tiết trong expander."""
    import streamlit as st

    from valuation.config import get_macro_series_registry, load_defaults
    from valuation.data_access.macro_news import latest_news_tags
    from valuation.views.macro_panel import build_snapshot

    defaults = load_defaults()
    cfg, mcfg = defaults["market_overview"], defaults.get("macro_dashboard") or {}
    freqs = {
        k: v.get("frequency", "DAILY") for k, v in get_macro_series_registry().items()
    }
    vni, closes, flows, universe = load_market_data(db, cfg)
    ups, src = model_upsides(closes)
    pillars = [
        macro_pillar(build_snapshot(db, mcfg, freqs), mcfg, cfg),
        trend_pillar(vni, closes, cfg),
        foreign_pillar(flows, universe, cfg),
        valuation_pillar(ups, src, cfg),
    ]
    label = overall(pillars, cfg)[0]
    tk, sec = leaders(closes, flows, sector_map(), cfg)
    view = index_view(vni, cfg)

    st.sidebar.header("Tổng quan thị trường")
    box = {"Thuận lợi": st.sidebar.success, "Khó khăn": st.sidebar.error}.get(
        label, st.sidebar.warning
    )
    box(headline(label, pillars))
    today = datetime.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    dates = [d for d in (vni.index.max(), closes.index.max()) if pd.notna(d)]
    if dates:
        oldest = min(dates).date()
        stale = (today - oldest).days > int(cfg["stale_days"])
        st.sidebar.caption(
            ("⚠️ Dữ liệu giá cũ — bấm Quét VN100 / Cập nhật vĩ mô · " if stale else "")
            + f"Giá đến {oldest:%d/%m/%Y}"
        )
    if view:
        arrow = {1: "↑", -1: "↓"}
        chg = " · ".join(f"{n} phiên {_chg(c)}" for n, c in view.changes)
        trend = " · ".join(f"{w} {arrow[s]}" for w, s in view.trends)
        rsi = f" · RSI {view.rsi:.0f}" if view.rsi is not None else ""
        lv = []
        if view.resistance:
            lv.append(f"Kháng cự {_vi(view.resistance[0])} ({view.resistance[1]})")
        if view.support:
            lv.append(f"Hỗ trợ {_vi(view.support[0])} ({view.support[1]})")
        st.sidebar.markdown(
            f"📊 **VN-Index {_vi(view.last, 2)}** ({view.date:%d/%m}) · {chg}  \n"
            f"Xu hướng: {trend}{rsi}  \n" + " · ".join(lv)
        )
        st.sidebar.markdown(
            "🔭 **Sắp tới** _(kịch bản, không phải dự báo)_\n"
            + "\n".join(f"- {x}" for x in outlook(view, label, pillars, cfg))
        )
    st.sidebar.markdown(
        "  \n".join(f"{_LEVELS[p.score]} **{p.name}**: {p.summary}" for p in pillars)
    )

    lines = []
    if not sec.empty:
        strong = sec[sec.state == 1].index[:3].tolist()
        weak = sec[sec.state == -1].sort_values("rel").index[:3].tolist()
        lines.append(f"📈 **Ngành mạnh:** {', '.join(strong) or '—'}")
        lines.append(f"📉 **Ngành yếu:** {', '.join(weak) or '—'}")
    if not tk.empty:
        picks = tk[tk.support]["Mã"].head(int(cfg["top_n"])).tolist()
        lines.append(f"🎯 **Mã có lực (giá + khối ngoại):** {', '.join(picks) or '—'}")
    tags = latest_news_tags()
    if tags is None:
        lines.append("📰 Bấm *Làm mới tin tức* để có nhãn tin")
    else:
        good, bad = tags["tich_cuc"], tags["tieu_cuc"]
        lines.append(f"📰 **Tin tích cực:** {', '.join(good) or '—'}")
        lines.append(f"📰 **Tin tiêu cực:** {', '.join(bad) or '—'}")
    st.sidebar.markdown("  \n".join(lines))

    with st.sidebar.expander("Xem chi tiết"):
        for p in pillars:
            st.markdown(f"{_LEVELS[p.score]} **{p.name}**")
            st.markdown("\n".join(f"- {d}" for d in p.details) or "- Thiếu dữ liệu")
        r = int(cfg["return_sessions"])
        if not sec.empty:
            st.markdown(
                f"**Ngành** — ±%: đà {r} phiên so trung vị VN100 · Ngoại: tỷ đồng"
            )
            st.dataframe(
                pd.DataFrame(
                    {
                        "±%": (sec["rel"] * 100).round(1),
                        "Ngoại": (sec["flow"] / 1e9).round(0),
                    }
                ),
                width="stretch",
            )
        if not tk.empty:
            st.markdown(f"**Mã mạnh nhất** — %: {r} phiên · ✓ = có lực")
            top = tk.head(10)
            st.dataframe(
                pd.DataFrame(
                    {
                        "Mã": top["Mã"],
                        "%": (top["ret"] * 100).round(1),
                        "Ngoại": (top["flow"] / 1e9).round(0),
                        "✓": top["support"].map({True: "✓", False: ""}),
                    }
                ),
                hide_index=True,
                width="stretch",
            )
        st.caption(
            "Mã có lực = giá trên MA50, tăng hơn trung vị VN100 và khối ngoại mua ròng "
            f"{r} phiên. Ngành mạnh/yếu: cùng chiều cả đà giá tương đối và khối ngoại."
        )
    st.sidebar.caption(
        "Chấm điều kiện hiện tại theo quy tắc cố định (config market_overview); "
        "không dự báo giá, không phải khuyến nghị đầu tư."
    )
