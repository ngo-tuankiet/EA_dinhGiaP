"""Khung "Chỉ số vĩ mô" trên sidebar + nhận định nhanh theo quy tắc (D50).

Chỉ đọc bảng macro_series khi render (không gọi mạng, không gọi AI). Nút "Cập nhật vĩ mô" mới lấy
dữ liệu thị trường (yfinance) và FRED. Nhận định nhanh là suy luận số học từ số liệu đã lưu,
ngưỡng trong config/defaults.yaml → macro_dashboard; không phải khuyến nghị đầu tư.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo

# (series_code, nhãn, kiểu hiển thị) — "rate" hiện %, "fx"/"usd" hiện số.
PANEL: list[tuple[str, str, str]] = [
    ("FED_FUNDS_UPPER", "Lãi suất Fed", "rate"),
    ("POLICY_RATE", "Lãi suất SBV", "rate"),
    ("UST_10Y", "TPCP Mỹ 10N", "rate"),
    ("TPCP_10Y", "TPCP VN 10N", "rate"),
    ("CPI_YOY", "CPI VN (YoY)", "rate"),
    ("USDVND", "USD/VND", "fx"),
    ("CRUDE_OIL", "Dầu WTI (USD)", "usd"),
]


@dataclass(frozen=True)
class MacroObs:
    value: float
    date: datetime.date
    prev: float | None  # quan sát trước (Fed: mức KHÁC gần nhất trong cửa sổ lookback)
    frequency: str


def _pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:.{digits}f}%".replace(".", ",")


def _pts(x: float) -> str:
    s = f"{abs(x) * 100:.2f}".replace(".", ",")
    return ("+" if x >= 0 else "−") + s + " điểm %"


def is_stale(obs: MacroObs, cfg: dict, today: datetime.date) -> bool:
    limit = (cfg.get("stale_days") or {}).get(obs.frequency)
    return limit is not None and (today - obs.date).days > int(limit)


def _stale_note(obs: MacroObs, cfg: dict, today: datetime.date) -> str:
    return f" (số liệu {obs.date:%d/%m/%Y})" if is_stale(obs, cfg, today) else ""


def quick_takes(
    snap: dict[str, MacroObs], cfg: dict, today: datetime.date
) -> list[str]:
    """Tối đa 4 dòng nhận định suy ra từ số liệu (bỏ dòng nếu thiếu đầu vào)."""
    takes: list[str] = []
    cpi, vn10, us10, fed = (
        snap.get(k) for k in ("CPI_YOY", "TPCP_10Y", "UST_10Y", "FED_FUNDS_UPPER")
    )
    if cpi:
        target = float(cfg.get("cpi_target", 0.045))
        band = float(cfg.get("cpi_near_band", 0.005))
        if cpi.value > target:
            view = f"vượt mục tiêu {_pct(target, 1)} → SBV khó nới lỏng thêm"
        elif cpi.value >= target - band:
            view = f"sát mục tiêu {_pct(target, 1)} → dư địa chính sách hẹp"
        else:
            view = f"dưới mục tiêu {_pct(target, 1)} → còn dư địa giữ lãi suất thấp"
        takes.append(
            f"Lạm phát {_pct(cpi.value)} {view}{_stale_note(cpi, cfg, today)}."
        )
    if cpi and vn10:
        real = vn10.value - cpi.value
        mood = (
            "lãi suất thực âm → tiền rẻ hỗ trợ tài sản rủi ro, nhưng rủi ro lạm phát/tỷ giá"
            if real < 0
            else "lãi suất thực dương → kênh tiết kiệm/trái phiếu còn hấp dẫn"
        )
        takes.append(
            f"TPCP VN 10 năm − CPI = {_pts(real)}: {mood}{_stale_note(cpi, cfg, today)}."
        )
    if vn10 and us10:
        spread = vn10.value - us10.value
        mood = (
            "TPCP VN thấp hơn Mỹ → áp lực tỷ giá, dòng vốn ngoại khó quay lại"
            if spread < 0
            else "TPCP VN vẫn cao hơn Mỹ"
            + (" nhưng chênh lệch mỏng → tỷ giá nhạy với Fed" if spread < 0.01 else "")
        )
        takes.append(
            f"Chênh lệch TPCP 10 năm VN − Mỹ {_pts(spread)}: {mood}{_stale_note(us10, cfg, today)}."
        )
    if fed:
        if fed.prev is None or abs(fed.value - fed.prev) < 1e-9:
            takes.append(f"Fed giữ lãi suất cận trên {_pct(fed.value)}.")
        else:
            verb = "hạ" if fed.value < fed.prev else "tăng"
            to = "về" if fed.value < fed.prev else "lên"
            # fed.date là ngày quan sát mới nhất, không phải ngày đổi lãi suất → chỉ nêu cửa sổ.
            takes.append(
                f"Fed {verb} {abs(fed.value - fed.prev) * 100:.2f} điểm %".replace(
                    ".", ","
                )
                + f" {to} cận trên {_pct(fed.value)} trong"
                f" {int(cfg.get('fed_lookback_days', 120))} ngày qua."
            )
    return takes


def build_snapshot(db, cfg: dict, frequencies: dict[str, str]) -> dict[str, MacroObs]:
    """Quan sát mới nhất + quan sát trước của mỗi chỉ số trong PANEL từ macro_series."""
    from valuation.db.models import MacroSeries

    lookback = int(cfg.get("fed_lookback_days", 120))
    snap: dict[str, MacroObs] = {}
    # FED_FUNDS_LOWER không có ô riêng nhưng cần để hiện khoảng "cận dưới–cận trên".
    for code in [c for c, _, _ in PANEL] + ["FED_FUNDS_LOWER"]:
        rows = (
            db.query(MacroSeries.date, MacroSeries.value)
            .filter(MacroSeries.indicator_code == code)
            .order_by(MacroSeries.date.desc())
            .limit(400)
            .all()
        )
        if not rows:
            continue
        d0, v0 = rows[0]
        prev = None
        if code.startswith("FED_FUNDS"):
            prev = next(
                (
                    v
                    for d, v in rows[1:]
                    if abs(v - v0) > 1e-9 and (d0 - d).days <= lookback
                ),
                v0,
            )
        elif len(rows) > 1:
            # Chỉ so với kỳ trước khi đủ gần (≤ 2× ngưỡng cũ của tần suất): khoảng trống dữ liệu
            # (vd tỷ giá 10/07 → 10/10) không được hiện thành "thay đổi" như một kỳ.
            limit = (cfg.get("stale_days") or {}).get(frequencies.get(code, "DAILY"))
            if limit is None or (d0 - rows[1][0]).days <= 2 * int(limit):
                prev = rows[1][1]
        snap[code] = MacroObs(
            float(v0),
            d0,
            None if prev is None else float(prev),
            frequencies.get(code, "DAILY"),
        )
    return snap


def _fmt_value(obs: MacroObs, kind: str) -> tuple[str, str | None]:
    if kind == "rate":
        delta = (
            None
            if obs.prev is None
            else f"{(obs.value - obs.prev) * 100:+.2f} điểm %".replace(".", ",")
        )
        return _pct(obs.value), delta
    digits = 0 if kind == "fx" else 1
    val = (
        f"{obs.value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    delta = None
    if obs.prev:
        delta = f"{(obs.value / obs.prev - 1) * 100:+.1f}%".replace(".", ",")
    return val, delta


def render_macro_panel(db) -> None:
    """Vẽ khung chỉ số + nhận định nhanh + nút cập nhật (chỉ nút mới gọi mạng)."""
    import streamlit as st

    from valuation.config import get_macro_series_registry, load_defaults

    cfg = load_defaults().get("macro_dashboard") or {}
    freqs = {
        k: v.get("frequency", "DAILY") for k, v in get_macro_series_registry().items()
    }
    snap = build_snapshot(db, cfg, freqs)
    today = datetime.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()

    st.sidebar.header("Chỉ số vĩ mô")
    for i, (code, label, kind) in enumerate(PANEL):
        if i % 2 == 0:  # mỗi cặp một hàng mới để 2 cột thẳng hàng
            cols = st.sidebar.columns(2)
        obs = snap.get(code)
        col = cols[i % 2]
        if obs is None:
            col.metric(label, "—", help="Chưa có dữ liệu — bấm Cập nhật vĩ mô")
            continue
        value, delta = _fmt_value(obs, kind)
        if code == "FED_FUNDS_UPPER" and "FED_FUNDS_LOWER" in snap:
            low = f"{snap['FED_FUNDS_LOWER'].value * 100:.2f}".replace(".", ",")
            value = f"{low}–{value}"
        stale = is_stale(obs, cfg, today)
        col.metric(
            label,
            value,
            delta,
            delta_color="off",
            help=f"Ngày số liệu {obs.date:%d/%m/%Y}" + (" — ĐÃ CŨ" if stale else ""),
        )
        col.caption(("⚠️ cũ · " if stale else "") + f"{obs.date:%d/%m/%Y}")

    takes = quick_takes(snap, cfg, today)
    if takes:
        st.sidebar.markdown(
            "**Nhận định nhanh**\n" + "\n".join(f"- {t}" for t in takes)
        )
    st.sidebar.caption(
        "Suy ra từ số liệu trên theo quy tắc cố định; không phải khuyến nghị đầu tư."
    )

    notice = st.session_state.pop("macro_refresh_notice", None)
    if notice:
        msgs, errors = notice
        if msgs:
            st.sidebar.success("Đã cập nhật · " + " · ".join(msgs))
        for err in errors:
            st.sidebar.error(f"Lỗi nguồn {err}")

    if st.sidebar.button(
        "Cập nhật vĩ mô",
        width="stretch",
        help="Lấy lãi suất Fed, TPCP Mỹ 10Y (FRED), tỷ giá, dầu (yfinance), VN-Index (vnstock). CPI/SBV cập nhật qua CSV.",
    ):
        _refresh(st)


def _fetch_vnindex(_db) -> int:
    from valuation.ingest.pipeline import run_ingest

    res = run_ingest("VNINDEX", data_types=["prices"], include_market_flows=False)[
        "prices"
    ]
    if res["status"] != "UPDATED":
        raise RuntimeError(res.get("error") or res["status"])
    return int(res["rows"])


def _refresh(st) -> None:
    from valuation.db.session import SessionLocalWrite
    from valuation.ingest.fred_fetcher import fetch_fred
    from valuation.ingest.macro_fetcher import fetch_market_macro

    db = SessionLocalWrite()
    msgs, errors = [], []
    try:
        for name, fn in (
            ("FRED", fetch_fred),
            ("yfinance", fetch_market_macro),
            ("VN-Index", _fetch_vnindex),
        ):
            try:
                msgs.append(f"{name}: {fn(db)} bản ghi")
            # Lỗi nguồn ngoài hiện rõ trên UI (không nuốt), nguồn còn lại vẫn chạy.
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:120]}")
    finally:
        db.close()
    st.session_state["macro_refresh_notice"] = (msgs, errors)
    st.rerun()
