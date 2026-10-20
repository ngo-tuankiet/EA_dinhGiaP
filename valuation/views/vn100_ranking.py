"""Tab VN100: bảng xếp hạng toàn rổ theo upside của mô hình + 5 mã ứng viên tích sản (D55).

Giá trị hợp lý lấy từ đợt định giá VN100 mới nhất (snapshot); upside tính lại theo giá đóng cửa mới nhất
trong DB. 5 mã tích sản = upside cao nhất sau khi loại mã có cờ lỗi dữ liệu, upside quá ngưỡng rà soát,
thanh khoản dưới ngưỡng; tối đa `max_per_sector` mã/ngành (ngưỡng ở config/investment_ranking.yaml).
"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from math import isfinite

import pandas as pd
import streamlit as st

from valuation.analysis.investment_ranking import load_ranking_config
from valuation.services.investment_job import job_status, local_now, next_run, start_job
from valuation.services.ranking_store import latest_snapshot
from valuation.views.market_overview import sector_map

# Cổ tức CP/thưởng thiếu ngày GDKHQ → số cp có thể sai → giá trị hợp lý chưa tin được (D48). Quyền mua
# thiếu ngày mang cờ riêng RIGHTS_ISSUE_UNDATED (thông tin, không vào hệ số chia) → không phải lỗi dữ liệu.
DATA_FLAGS_EXTRA = {"CORPORATE_ACTION_UNDATED", "MATERIAL_EVENT_HOLD"}
_LIQ_SESSIONS = 20  # cùng cửa sổ 20 phiên với engine xếp hạng (investment_snapshot.py)
_LOOKBACK_DAYS = 60  # ngày lịch đủ chứa 20 phiên kể cả nghỉ lễ


def _num(value: object) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
    ):
        return float(value)
    return None


def market_data(db) -> dict[str, tuple[float, date, float | None]]:
    """{mã: (giá đóng cửa mới nhất, ngày, giá trị giao dịch TB 20 phiên)}.

    Cột `value` trong prices_daily trống (vnstock không trả) nên engine cũ coi mọi mã thiếu thanh khoản;
    ở đây ước lượng giá trị khớp = giá đóng cửa × khối lượng (gần đúng, không phải VWAP).
    """
    from valuation.db.models import PricesDaily, Ticker

    start = local_now().date() - timedelta(days=_LOOKBACK_DAYS)
    rows = (
        db.query(
            PricesDaily.ticker,
            PricesDaily.trade_date,
            PricesDaily.close,
            PricesDaily.volume,
        )
        .join(Ticker, Ticker.ticker == PricesDaily.ticker)
        .filter(Ticker.is_vn100, PricesDaily.trade_date >= start)
        .order_by(PricesDaily.ticker, PricesDaily.trade_date)
        .all()
    )
    by: dict[str, list[tuple[date, float, float | None]]] = {}
    for t, d, close, vol in rows:
        if close is not None:
            by.setdefault(t, []).append(
                (d, float(close), None if vol is None else float(vol))
            )
    out: dict[str, tuple[float, date, float | None]] = {}
    for t, series in by.items():
        last = series[-_LIQ_SESSIONS:]
        vals = [c * v for _, c, v in last if v is not None]
        adtv = sum(vals) / len(vals) if len(vals) == _LIQ_SESSIONS else None
        out[t] = (series[-1][1], series[-1][0], adtv)
    return out


def ranking_table(snapshot: dict, market: dict, cfg: dict) -> pd.DataFrame:
    """Một dòng/mã; có giá trị hợp lý thì xếp hạng theo upside, chưa định giá được nằm cuối."""
    blocking = set(cfg.get("blocking_flags", [])) | DATA_FLAGS_EXTRA
    max_up = float(cfg["max_upside_pct"])
    min_liq = float(cfg["scales"]["min_traded_value_vnd"])
    sectors = sector_map()
    records = []
    for r in snapshot["rows"]:
        fv = _num(r.get("fair_value"))
        price, price_date, adtv = market.get(
            r["ticker"], (_num(r.get("price")), None, None)
        )
        upside = (fv / price - 1) * 100 if fv and fv > 0 and price else None
        flags = [str(f).split(":")[0] for f in r.get("flags", [])]
        bad = [f for f in flags if f in blocking]
        if upside is None:
            note = "Chưa định giá được"
        elif bad:
            note = "Lỗi dữ liệu: " + ", ".join(bad)
        elif upside > max_up:
            note = f"Upside > {max_up:.0f}%: cần rà soát"
        elif adtv is None or adtv < min_liq:
            note = f"Thanh khoản < {min_liq / 1e9:.0f} tỷ/phiên"
        else:
            note = ""
        records.append(
            {
                "Mã": r["ticker"],
                "Upside (%)": upside,
                "Giá (đ)": price,
                "Giá trị hợp lý (đ)": fv if upside is not None else None,
                "Ngành": sectors.get(r["ticker"]) or r.get("sector") or "Chưa rõ",
                "GTGD (tỷ/phiên)": adtv / 1e9 if adtv else None,
                "Ghi chú": note,
                "_price_date": price_date,
            }
        )
    df = pd.DataFrame(records)
    df = df.sort_values("Upside (%)", ascending=False, na_position="last").reset_index(
        drop=True
    )
    df.insert(
        0,
        "Hạng",
        pd.array(
            [i + 1 if pd.notna(u) else None for i, u in enumerate(df["Upside (%)"])],
            dtype="Int64",  # số nguyên cho phép trống (mã chưa định giá không có hạng)
        ),
    )
    return df


def accumulation_picks(
    table: pd.DataFrame, max_per_sector: int, n: int = 5
) -> pd.DataFrame:
    """Top `n` upside trong các mã không có ghi chú loại trừ, tối đa `max_per_sector` mã/ngành."""
    picked, per_sector = [], {}
    for _, row in table[table["Ghi chú"] == ""].iterrows():
        if per_sector.get(row["Ngành"], 0) >= max_per_sector:
            continue
        picked.append(row)
        per_sector[row["Ngành"]] = per_sector.get(row["Ngành"], 0) + 1
        if len(picked) == n:
            break
    return pd.DataFrame(picked, columns=table.columns)


_FMT = {
    "Hạng": st.column_config.NumberColumn(width="small", pinned=True),
    "Mã": st.column_config.TextColumn(width="small", pinned=True),
    "Giá (đ)": st.column_config.NumberColumn(format="localized"),
    "Giá trị hợp lý (đ)": st.column_config.NumberColumn(format="localized"),
    "Upside (%)": st.column_config.NumberColumn(format="%.1f"),
    "GTGD (tỷ/phiên)": st.column_config.NumberColumn(format="%.0f"),
}


@st.fragment(run_every="5s")
def _progress() -> None:
    status = job_status()
    if status.get("status") in ("QUEUED", "RUNNING"):
        st.progress(
            status.get("completed", 0) / max(1, status.get("total", 100)),
            text=status.get("message", "Đang cập nhật"),
        )
        st.session_state["ranking_waiting"] = True
    elif st.session_state.pop("ranking_waiting", False):
        st.rerun()
    elif status.get("status") in ("FAILED", "INTERRUPTED"):
        st.warning(status["message"])


def _excel(table: pd.DataFrame, picks: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Xep hang VN100", index=False)
        picks.to_excel(writer, sheet_name="5 ma tich san", index=False)
    return buffer.getvalue()


def render_vn100_ranking() -> None:
    from valuation.db.session import SessionLocalRead

    st.subheader("Xếp hạng VN100 theo mô hình định giá")
    snapshot = latest_snapshot()
    if not snapshot:
        st.info(
            "Chưa có đợt định giá VN100. Mở mục « Cập nhật xếp hạng » bên dưới để chạy."
        )
    else:
        cfg = snapshot.get("config", load_ranking_config())
        db = SessionLocalRead()
        try:
            table = ranking_table(snapshot, market_data(db), cfg)
        finally:
            db.close()
        done = datetime.fromisoformat(snapshot["completed_at"])
        dates = table["_price_date"].dropna()
        rated = int(table["Hạng"].notna().sum())
        st.caption(
            f"Giá trị hợp lý: đợt {done:%d/%m/%Y} · Giá: {max(dates):%d/%m/%Y} · "
            f"{rated}/{len(table)} mã định giá được · Upside = giá trị hợp lý ÷ giá − 1"
            if len(dates)
            else f"Giá trị hợp lý: đợt {done:%d/%m/%Y}"
        )
        if (local_now() - done).days >= cfg["price_max_age_days"]:
            st.warning("Giá trị hợp lý đã cũ — nên cập nhật xếp hạng trước khi dùng.")
        st.dataframe(
            table.drop(columns="_price_date"),
            hide_index=True,
            width="stretch",
            height=560,
            column_config=_FMT,
        )

        st.markdown("#### 5 mã ứng viên tích sản")
        picks = accumulation_picks(table, int(cfg.get("max_per_sector", 2)))
        if picks.empty:
            st.info("Đợt này chưa có mã qua đủ bộ lọc.")
        else:
            st.dataframe(
                picks[["Mã", "Upside (%)", "Giá (đ)", "Giá trị hợp lý (đ)", "Ngành"]],
                hide_index=True,
                width="stretch",
                column_config=_FMT,
            )
        st.caption(
            f"Upside cao nhất sau khi loại: lỗi dữ liệu, upside > {cfg['max_upside_pct']}% (cần rà soát), "
            f"thanh khoản < {cfg['scales']['min_traded_value_vnd'] / 1e9:.0f} tỷ/phiên; tối đa "
            f"{cfg.get('max_per_sector', 2)} mã/ngành. Sàng lọc theo mô hình — không phải khuyến nghị đầu tư."
        )

    with st.expander("Cập nhật xếp hạng"):
        _progress()
        if st.button(
            "Định giá lại VN100",
            icon=":material/refresh:",
            key="ranking_refresh",
            disabled=job_status().get("status") in ("QUEUED", "RUNNING"),
        ):
            started = start_job()
            st.session_state["ranking_waiting"] = started
            if not started:
                st.info("Một đợt cập nhật đang chạy; không tạo thêm yêu cầu.")
            st.rerun()
        st.caption(
            f"Lịch tự động: thứ Ba 09:30 · lần tới {next_run(local_now()):%d/%m/%Y %H:%M}"
        )
        if snapshot:
            st.download_button(
                "Xuất Excel",
                _excel(table.drop(columns="_price_date"), picks),
                file_name=f"VN100_xep_hang_{snapshot['run_id']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:",
            )
