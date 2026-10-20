"""Báo cáo sáng hằng ngày lên Discord: cơ hội định giá, thay đổi so với báo cáo trước, vĩ mô.

Chữ do Python dựng — KHÔNG gọi DeepSeek. Giá trị hợp lý lấy từ snapshot xếp hạng tuần, upside tính
lại theo giá đóng cửa mới nhất trong DB: cùng hàm, cùng bộ lọc với tab VN100 (5 mã tích sản).

  python scripts/daily_report.py                         # cập nhật giá + vĩ mô, gửi webhook, lưu lịch sử
  python scripts/daily_report.py --dry-run --no-refresh  # chỉ in ra màn hình
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from math import isfinite
from typing import Any

from valuation.services.ranking_store import (
    ROOT,
    exclusive_lock,
    latest_snapshot,
    read_json,
    write_json,
)

logger = logging.getLogger(__name__)

STORE = ROOT / ".daily_report"
# Cùng khóa với job "Quét VN100": hai tiến trình không ghi SQLite song song.
DATA_LOCK = ROOT / ".data_update" / "worker.lock"
_MOVE_LOOKBACK_DAYS = 15  # ngày lịch đủ chứa 2 phiên gần nhất kể cả kỳ nghỉ Tết


def _cfg() -> dict:
    from valuation.config import load_defaults

    return load_defaults()["daily_report"]


def _num(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def _pct(x: float) -> str:
    return f"{x:+.1f}%".replace(".", ",").replace("-", "−")


def _ddmm(iso: str | None) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "?"


def refresh_market() -> dict:
    """Kéo giá VN100 + VNINDEX và vĩ mô (FRED, yfinance — giống nút "Cập nhật vĩ mô").

    Lỗi từng mã/nguồn được ghi lại để in trong báo cáo, không nuốt im lặng.
    """
    from valuation.db.models import Ticker
    from valuation.db.session import SessionLocalRead, SessionLocalWrite
    from valuation.ingest.fred_fetcher import fetch_fred
    from valuation.ingest.macro_fetcher import fetch_market_macro
    from valuation.ingest.pipeline import run_ingest

    info: dict[str, Any] = {
        "skipped": None,
        "price_errors": [],
        "macro_errors": [],
        "price_total": 0,
    }
    db = SessionLocalRead()
    try:
        tickers = [
            t
            for (t,) in db.query(Ticker.ticker)
            .filter(Ticker.is_vn100)
            .order_by(Ticker.ticker)
        ]
    finally:
        db.close()  # đóng giao dịch đọc trước khi ghi, tránh "database is locked"
    try:
        with exclusive_lock(DATA_LOCK):
            for t in tickers + ["VNINDEX"]:
                try:
                    res = run_ingest(
                        t, ["prices"], include_yearly=False, include_market_flows=False
                    )["prices"]
                    if res["status"] != "UPDATED":
                        info["price_errors"].append(
                            f"{t}: {res.get('error') or res['status']}"
                        )
                except (
                    Exception
                ) as exc:  # noqa: BLE001 — một mã lỗi (vd bug vnai) không chặn cả báo cáo; vẫn liệt kê
                    info["price_errors"].append(
                        f"{t}: {type(exc).__name__}: {str(exc)[:100]}"
                    )
            info["price_total"] = len(tickers) + 1
            db_w = SessionLocalWrite()
            try:
                for name, fn in (
                    ("FRED", fetch_fred),
                    ("yfinance", fetch_market_macro),
                ):
                    try:
                        fn(db_w)
                    except (
                        Exception
                    ) as exc:  # noqa: BLE001 — nguồn ngoài lỗi thì nguồn còn lại vẫn chạy
                        db_w.rollback()
                        info["macro_errors"].append(
                            f"{name}: {type(exc).__name__}: {str(exc)[:120]}"
                        )
            finally:
                db_w.close()
    except BlockingIOError:
        info["skipped"] = 'Job "Quét VN100" đang chạy nên chưa cập nhật giá và vĩ mô'
    return info


def session_moves(
    rows: list[tuple[str, date, float]], price_date: date
) -> dict[str, float]:
    """% thay đổi phiên gần nhất (đóng cửa price_date so với phiên liền trước) theo giá trong DB.

    Dùng 2 giá cùng một lần tải (cùng điều chỉnh hồi tố) — so với giá lưu hôm qua sẽ ra
    "giảm" giả vào ngày GDKHQ. Mã không giao dịch ở price_date bị bỏ.
    """
    by: dict[str, list[tuple[date, float]]] = {}
    for t, d, close in rows:
        by.setdefault(t, []).append((d, close))
    out = {}
    for t, series in by.items():
        series.sort()
        if len(series) >= 2 and series[-1][0] == price_date and series[-2][1] > 0:
            pct = (series[-1][1] / series[-2][1] - 1) * 100
            if isfinite(pct):
                out[t] = round(pct, 2)
    return out


def _macro_lines(snap: dict, macro_cfg: dict, today: date) -> list[str]:
    from valuation.views.macro_panel import PANEL, _fmt_value, is_stale, quick_takes

    lines = []
    for code, label, kind in PANEL:
        obs = snap.get(code)
        if obs is None:
            continue
        value, delta = _fmt_value(obs, kind)
        if code == "FED_FUNDS_UPPER" and "FED_FUNDS_LOWER" in snap:
            value = (
                f"{snap['FED_FUNDS_LOWER'].value * 100:.2f}".replace(".", ",")
                + "–"
                + value
            )
        stale = (
            f" · số liệu {obs.date:%d/%m/%Y}" if is_stale(obs, macro_cfg, today) else ""
        )
        lines.append(f"{label}: **{value}**" + (f" ({delta})" if delta else "") + stale)
    return lines + [f"→ {t}" for t in quick_takes(snap, macro_cfg, today)]


def collect(today: date) -> dict:
    """Trạng thái báo cáo (JSON được) từ snapshot FV + DB giá + macro_series."""
    from valuation.analysis.investment_ranking import load_ranking_config
    from valuation.config import get_macro_series_registry, load_defaults
    from valuation.db.models import PricesDaily, Ticker
    from valuation.db.session import SessionLocalRead
    from valuation.views.macro_panel import build_snapshot
    from valuation.views.vn100_ranking import (
        accumulation_picks,
        market_data,
        ranking_table,
    )

    snapshot = latest_snapshot()
    if not snapshot:
        raise RuntimeError(
            "Chưa có snapshot xếp hạng VN100 — chạy scripts/update_vn100_ranking.py trước"
        )
    rank_cfg = load_ranking_config()
    macro_cfg = load_defaults().get("macro_dashboard") or {}
    freqs = {
        k: v.get("frequency", "DAILY") for k, v in get_macro_series_registry().items()
    }

    db = SessionLocalRead()
    try:
        market = market_data(db)
        macro = build_snapshot(db, macro_cfg, freqs)
        table = ranking_table(snapshot, market, rank_cfg)
        dates = [d for d in table["_price_date"] if isinstance(d, date)]
        price_date = max(dates) if dates else None
        rows = []
        if price_date:
            rows = [
                (t, d, float(c))
                for t, d, c in db.query(
                    PricesDaily.ticker, PricesDaily.trade_date, PricesDaily.close
                )
                .join(Ticker, Ticker.ticker == PricesDaily.ticker)
                .filter(
                    Ticker.is_vn100,
                    PricesDaily.trade_date
                    >= price_date - timedelta(days=_MOVE_LOOKBACK_DAYS),
                    PricesDaily.close.isnot(None),
                )
                .all()
            ]
    finally:
        db.close()

    max_per_sector = int(rank_cfg.get("max_per_sector", 2))
    picks = accumulation_picks(table, max_per_sector, n=int(_cfg()["top_n"]))
    return {
        "date": today.isoformat(),
        "price_date": price_date.isoformat() if price_date else None,
        "snapshot": {
            "run_id": snapshot["run_id"],
            "completed_at": snapshot.get("completed_at"),
        },
        "max_per_sector": max_per_sector,
        "picks": [
            {
                "ticker": r["Mã"],
                "price": float(r["Giá (đ)"]),
                "fair_value": float(r["Giá trị hợp lý (đ)"]),
                "upside": round(float(r["Upside (%)"]), 2),
                "sector": r["Ngành"],
            }
            for _, r in picks.iterrows()
        ],
        "notes": {r["Mã"]: r["Ghi chú"] for _, r in table.iterrows()},
        "moves": session_moves(rows, price_date) if price_date else {},
        "macro_lines": _macro_lines(macro, macro_cfg, today),
    }


def changes(prev: dict | None, cur: dict, move_pct: float) -> dict | None:
    """So với báo cáo trước: mã vào/ra danh sách cơ hội, mã đổi ghi chú, mã biến động ≥ move_pct."""
    if not prev:
        return None
    before = [p["ticker"] for p in prev["picks"]]
    now = [p["ticker"] for p in cur["picks"]]
    new_session = cur["price_date"] != prev["price_date"]
    movers = sorted(
        ((t, m) for t, m in cur["moves"].items() if abs(m) >= move_pct),
        key=lambda x: -abs(x[1]),
    )
    return {
        "prev_date": prev["date"],
        "entered": [t for t in now if t not in before],
        "left": [t for t in before if t not in now],
        "notes": [
            (t, prev["notes"][t], n)
            for t, n in sorted(cur["notes"].items())
            if t in prev["notes"] and prev["notes"][t] != n
        ],
        "new_session": new_session,
        "movers": movers if new_session else [],
    }


def _capped(items: list[str], limit: int) -> list[str]:
    return items[:limit] + (
        [f"… và {len(items) - limit} mã khác"] if len(items) > limit else []
    )


def build_message(
    state: dict, chg: dict | None, info: dict | None, cfg: dict, today: date
) -> dict:
    """Embed Discord (tham số của notify_discord). info=None: báo cáo theo yêu cầu, không cập nhật."""
    limit = int(cfg["max_lines"])
    warn = []
    done = (state["snapshot"].get("completed_at") or "")[:10]
    if done and (today - date.fromisoformat(done)).days > int(
        cfg["snapshot_stale_days"]
    ):
        warn.append(
            f"⚠️ Giá trị hợp lý lấy từ đợt định giá ngày {_ddmm(done)} "
            f"({(today - date.fromisoformat(done)).days} ngày trước) — nên chạy lại xếp hạng VN100."
        )
    pd_iso = state["price_date"]
    if not pd_iso or (today - date.fromisoformat(pd_iso)).days > int(
        cfg["price_stale_days"]
    ):
        warn.append(f"⚠️ Giá đóng cửa mới nhất trong DB là ngày {_ddmm(pd_iso)}.")
    if info is None:
        warn.append(
            "ℹ️ Báo cáo theo yêu cầu: dùng dữ liệu đang có, không cập nhật giá."
        )
    else:
        if info["skipped"]:
            warn.append(f"⚠️ {info['skipped']}.")
        if info["price_errors"]:
            names = ", ".join(e.split(":")[0] for e in info["price_errors"][:limit])
            more = "…" if len(info["price_errors"]) > limit else ""
            warn.append(
                f"⚠️ {len(info['price_errors'])}/{info['price_total']} mã không cập nhật được giá: {names}{more}"
            )
        for e in info["macro_errors"]:
            warn.append(f"⚠️ Vĩ mô lỗi — {e}")

    picks = [
        f"**{p['ticker']}** {_num(p['price'])} → FV {_num(p['fair_value'])} ({_pct(p['upside'])}) · {p['sector']}"
        for p in state["picks"]
    ] or [
        "Chưa có mã nào qua đủ bộ lọc (lỗi dữ liệu, upside quá ngưỡng rà soát, thanh khoản)."
    ]

    if chg is None:
        diff = ["Chưa có báo cáo trước để so sánh."]
    else:
        diff = [f"So với báo cáo ngày {_ddmm(chg['prev_date'])}:"]
        if chg["entered"]:
            diff.append("➕ Vào danh sách: " + ", ".join(chg["entered"]))
        if chg["left"]:
            diff.append("➖ Ra khỏi danh sách: " + ", ".join(chg["left"]))
        if not chg["entered"] and not chg["left"]:
            diff.append("Danh sách cơ hội không đổi.")
        diff += _capped(
            [
                f"🔁 {t}: {o or 'đạt bộ lọc'} → {n or 'đạt bộ lọc'}"
                for t, o, n in chg["notes"]
            ],
            limit,
        )
        if not chg["new_session"]:
            diff.append("Không có phiên giao dịch mới kể từ báo cáo trước.")
        elif chg["movers"]:
            diff.append(f"Biến động ≥ {cfg['price_move_pct']}% phiên {_ddmm(pd_iso)}:")
            diff += _capped(
                [f"{'📈' if m > 0 else '📉'} {t} {_pct(m)}" for t, m in chg["movers"]],
                limit,
            )
        else:
            diff.append(
                f"Không mã nào biến động ≥ {cfg['price_move_pct']}% phiên {_ddmm(pd_iso)}."
            )

    return {
        "embed_title": f"☀️ Báo cáo sáng {today:%d/%m/%Y}",
        "embed_desc": "\n".join(warn)
        or f"Dữ liệu đã cập nhật đến phiên {_ddmm(pd_iso)}.",
        "color": "F1C40F" if warn else "2ECC71",
        "fields": [
            {
                "name": f"🟢 Cơ hội định giá — top {cfg['top_n']} (tối đa {state['max_per_sector']} mã/ngành)",
                "value": "\n".join(picks),
            },
            {"name": "🔄 Thay đổi", "value": "\n".join(diff)},
            {
                "name": "🌐 Vĩ mô",
                "value": "\n".join(state["macro_lines"]) or "Chưa có dữ liệu vĩ mô.",
            },
        ],
        "footer": (
            f"FV: đợt định giá {state['snapshot']['run_id']} · Giá đóng cửa {_ddmm(pd_iso)} · "
            "Sàng lọc theo mô hình — không phải khuyến nghị đầu tư."
        ),
    }


def previous_report(today: date, store=STORE) -> dict | None:
    """Báo cáo đã lưu gần nhất TRƯỚC hôm nay (chạy lại trong ngày vẫn so cùng mốc)."""
    files = sorted(
        p for p in (store / "history").glob("*.json") if p.stem < today.isoformat()
    )
    return read_json(files[-1]) if files else None


def run(
    *,
    refresh: bool = True,
    save: bool = True,
    send: bool = True,
    channel_id: int | None = None,
) -> dict:
    from valuation.output.discord_alerter import notify_discord
    from valuation.services.investment_job import local_now

    today = local_now().date()
    cfg = _cfg()
    info = refresh_market() if refresh else None
    state = collect(today)
    msg = build_message(
        state,
        changes(previous_report(today), state, float(cfg["price_move_pct"])),
        info,
        cfg,
        today,
    )
    if send:
        resp = notify_discord(**msg, channel_id=channel_id)
        if channel_id is None and (resp is None or resp.status_code >= 300):
            raise RuntimeError(
                f"Gửi webhook Discord thất bại (status {getattr(resp, 'status_code', None)})"
            )
    if save:  # cùng ngày thì ghi đè đúng file ngày đó → chạy lại không nhân đôi
        write_json(
            STORE / "history" / f"{today.isoformat()}.json", {**state, "refresh": info}
        )
    return msg
