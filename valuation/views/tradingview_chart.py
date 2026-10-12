"""Biểu đồ kỹ thuật tương tác dùng dữ liệu vnstock và Plotly."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from sqlalchemy.exc import SQLAlchemyError

from valuation.analysis.technical_chart import (
    add_technical_indicators,
    normalize_price_history,
    period_start_date,
    price_snapshot,
    resample_price_history,
)

_CHART_HANDLED_EXCEPTIONS = (
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    NameError,
    SQLAlchemyError,
)

OVERLAY_OPTIONS = {
    "MA 20": "MA20",
    "MA 50": "MA50",
    "EMA 20": "EMA20",
    "Dải Bollinger": "BOLLINGER",
}
PANEL_OPTIONS = ("Khối lượng", "MACD", "RSI")


def get_clean_ticker(ticker: str) -> str:
    """Loại bỏ tiền tố sàn nếu có để lấy mã cổ phiếu gốc."""
    value = str(ticker).upper().strip()
    return value.split(":")[-1] if ":" in value else value


def _load_stored_price_history(ticker: str, start_date: str) -> pd.DataFrame:
    """Đọc giá VND đã lưu và đổi về nghìn VND cho biểu đồ hiện tại."""
    from valuation.db.models import PricesDaily
    from valuation.db.session import SessionLocalRead

    start = pd.Timestamp(start_date).date()
    with SessionLocalRead() as db:
        rows = (
            db.query(PricesDaily)
            .filter(
                PricesDaily.ticker == ticker,
                PricesDaily.trade_date >= start,
            )
            .order_by(PricesDaily.trade_date)
            .all()
        )
    frame = pd.DataFrame(
        [
            {
                "time": row.trade_date,
                "open": float(row.open) / 1_000,
                "high": float(row.high) / 1_000,
                "low": float(row.low) / 1_000,
                "close": float(row.close) / 1_000,
                "volume": float(row.volume or 0),
            }
            for row in rows
            if all(
                value is not None for value in (row.open, row.high, row.low, row.close)
            )
        ]
    )
    frame.attrs["data_source"] = "CSDL giá nội bộ"
    return frame


@st.cache_data(ttl=60, show_spinner=False, max_entries=64)
def _load_price_history(ticker: str, start_date: str) -> pd.DataFrame:
    """Chỉ đọc giá đã lưu (đã điều chỉnh quyền). KHÔNG gọi vnstock khi hiển thị:
    nguồn chậm từng làm treo cả trang nhiều phút và mọi nút phải xếp hàng chờ.
    Giá mới vào DB qua nút "Tải mới"/"Quét VN100"."""
    return _load_stored_price_history(ticker, start_date)


def _format_price(value: float) -> str:
    return f"{value * 1_000:,.0f}".replace(",", ".")


def _format_volume(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} triệu"
    if value >= 1_000:
        return f"{value / 1_000:.1f} nghìn"
    return f"{value:,.0f}"


def _theme_colors(dark_mode: bool) -> dict[str, str]:
    if dark_mode:
        return {
            "paper": "#0B1220",
            "plot": "#111827",
            "text": "#E5E7EB",
            "muted": "#9CA3AF",
            "grid": "#273449",
            "border": "#374151",
            "hover": "#172033",
        }
    return {
        "paper": "#FFFFFF",
        "plot": "#FFFFFF",
        "text": "#111827",
        "muted": "#64748B",
        "grid": "#E5E7EB",
        "border": "#CBD5E1",
        "hover": "#F8FAFC",
    }


def _row_layout(panels: list[str]) -> tuple[dict[str, int], list[float], list[str]]:
    rows = {"Giá": 1}
    titles = ["Giá"]
    for panel in PANEL_OPTIONS:
        if panel in panels:
            rows[panel] = len(rows) + 1
            titles.append(panel if panel != "RSI" else "RSI (14)")

    extra_count = len(rows) - 1
    if extra_count == 0:
        heights = [1.0]
    else:
        price_height = max(0.52, 0.7 - (0.05 * extra_count))
        panel_height = (1.0 - price_height) / extra_count
        heights = [price_height] + ([panel_height] * extra_count)
    return rows, heights, titles


def _add_price_trace(fig: go.Figure, frame: pd.DataFrame, chart_type: str) -> None:
    if chart_type == "Nến":
        fig.add_trace(
            go.Candlestick(
                x=frame["time"],
                open=frame["open"],
                high=frame["high"],
                low=frame["low"],
                close=frame["close"],
                increasing={
                    "line": {"color": "#089981", "width": 1},
                    "fillcolor": "#089981",
                },
                decreasing={
                    "line": {"color": "#F23645", "width": 1},
                    "fillcolor": "#F23645",
                },
                name="Giá",
                hoverlabel={"namelength": 0},
            ),
            row=1,
            col=1,
        )
    elif chart_type == "OHLC":
        fig.add_trace(
            go.Ohlc(
                x=frame["time"],
                open=frame["open"],
                high=frame["high"],
                low=frame["low"],
                close=frame["close"],
                increasing_line_color="#089981",
                decreasing_line_color="#F23645",
                name="Giá",
            ),
            row=1,
            col=1,
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame["close"],
                mode="lines",
                line={"color": "#2563EB", "width": 2},
                fill="tozeroy",
                fillcolor="rgba(37, 99, 235, 0.08)",
                name="Giá đóng cửa",
                hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Giá: %{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )


def _add_overlays(fig: go.Figure, frame: pd.DataFrame, overlays: list[str]) -> None:
    styles = {
        "MA20": ("MA 20", "#F59E0B"),
        "MA50": ("MA 50", "#2563EB"),
        "EMA20": ("EMA 20", "#8B5CF6"),
    }
    selected = {OVERLAY_OPTIONS[label] for label in overlays}
    for code, (label, color) in styles.items():
        if code not in selected:
            continue
        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame[code],
                mode="lines",
                line={"color": color, "width": 1.6},
                name=label,
                hovertemplate=f"{label}: %{{y:.2f}}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    if "BOLLINGER" in selected:
        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame["BB_LOWER"],
                mode="lines",
                line={"color": "rgba(14, 116, 144, 0.45)", "width": 1},
                name="Bollinger dưới",
                hovertemplate="BB dưới: %{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame["BB_UPPER"],
                mode="lines",
                line={"color": "rgba(14, 116, 144, 0.65)", "width": 1},
                fill="tonexty",
                fillcolor="rgba(14, 116, 144, 0.08)",
                name="Bollinger trên",
                hovertemplate="BB trên: %{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )


def _add_panels(
    fig: go.Figure,
    frame: pd.DataFrame,
    rows: dict[str, int],
    colors: dict[str, str],
) -> None:
    up_color = "#089981"
    down_color = "#F23645"
    bar_colors = [
        up_color if close >= open_ else down_color
        for open_, close in zip(frame["open"], frame["close"])
    ]

    if "Khối lượng" in rows:
        fig.add_trace(
            go.Bar(
                x=frame["time"],
                y=frame["volume"],
                marker={"color": bar_colors, "line": {"width": 0}},
                opacity=0.72,
                name="Khối lượng",
                hovertemplate="Khối lượng: %{y:,.0f}<extra></extra>",
            ),
            row=rows["Khối lượng"],
            col=1,
        )

    if "MACD" in rows:
        macd_colors = [
            up_color if value >= 0 else down_color
            for value in frame["MACD_HIST"].fillna(0)
        ]
        row = rows["MACD"]
        fig.add_trace(
            go.Bar(
                x=frame["time"],
                y=frame["MACD_HIST"],
                marker={"color": macd_colors, "line": {"width": 0}},
                opacity=0.62,
                name="MACD Histogram",
                hovertemplate="Histogram: %{y:.3f}<extra></extra>",
            ),
            row=row,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame["MACD"],
                mode="lines",
                line={"color": "#2563EB", "width": 1.5},
                name="MACD",
                hovertemplate="MACD: %{y:.3f}<extra></extra>",
            ),
            row=row,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame["MACD_SIGNAL"],
                mode="lines",
                line={"color": "#F59E0B", "width": 1.5},
                name="Tín hiệu MACD",
                hovertemplate="Tín hiệu: %{y:.3f}<extra></extra>",
            ),
            row=row,
            col=1,
        )
        fig.add_hline(y=0, line={"color": colors["border"], "width": 1}, row=row, col=1)

    if "RSI" in rows:
        row = rows["RSI"]
        fig.add_hrect(
            y0=30,
            y1=70,
            fillcolor="rgba(37, 99, 235, 0.035)",
            line_width=0,
            row=row,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame["RSI14"],
                mode="lines",
                line={"color": "#7C3AED", "width": 1.8},
                name="RSI 14",
                hovertemplate="RSI: %{y:.1f}<extra></extra>",
            ),
            row=row,
            col=1,
        )
        fig.add_hline(
            y=70, line={"color": down_color, "dash": "dot", "width": 1}, row=row, col=1
        )
        fig.add_hline(
            y=30, line={"color": up_color, "dash": "dot", "width": 1}, row=row, col=1
        )
        fig.update_yaxes(range=[0, 100], tickvals=[30, 50, 70], row=row, col=1)


def _build_chart(
    frame: pd.DataFrame,
    ticker: str,
    period: str,
    interval: str,
    chart_type: str,
    overlays: list[str],
    panels: list[str],
    dark_mode: bool,
    log_scale: bool,
    show_range_slider: bool,
    base_height: int,
) -> go.Figure:
    colors = _theme_colors(dark_mode)
    rows, row_heights, titles = _row_layout(panels)
    figure_height = max(base_height, 510 + (115 * (len(rows) - 1)))
    fig = make_subplots(
        rows=len(rows),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.045,
        row_heights=row_heights,
        subplot_titles=titles,
    )
    _add_price_trace(fig, frame, chart_type)
    _add_overlays(fig, frame, overlays)
    _add_panels(fig, frame, rows, colors)

    fig.update_layout(
        height=figure_height,
        paper_bgcolor=colors["paper"],
        plot_bgcolor=colors["plot"],
        font={
            "color": colors["text"],
            "family": "Inter, Arial, sans-serif",
            "size": 12,
        },
        margin={"l": 20, "r": 22, "t": 72, "b": 24},
        hovermode="x unified",
        hoverlabel={
            "bgcolor": colors["hover"],
            "bordercolor": colors["border"],
            "font_color": colors["text"],
        },
        dragmode="pan",
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.035,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
        },
        modebar={
            "orientation": "h",
            "bgcolor": "rgba(0,0,0,0)",
            "color": colors["muted"],
        },
        uirevision=f"{ticker}-{period}-{interval}",
        bargap=0.16,
    )
    fig.update_annotations(
        font={"size": 12, "color": colors["muted"]}, x=0, xanchor="left"
    )
    fig.update_xaxes(
        showgrid=False,
        showline=True,
        linecolor=colors["border"],
        tickfont={"color": colors["muted"]},
        showspikes=True,
        spikecolor=colors["muted"],
        spikethickness=1,
        spikedash="dot",
        spikesnap="cursor",
        rangeslider_visible=False,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=colors["grid"],
        gridwidth=1,
        zeroline=False,
        side="right",
        tickfont={"color": colors["muted"]},
        fixedrange=False,
    )
    fig.update_yaxes(type="log" if log_scale else "linear", row=1, col=1)
    if show_range_slider:
        fig.update_xaxes(
            rangeslider={"visible": True, "thickness": 0.07}, row=len(rows), col=1
        )
    return fig


def _render_metrics(frame: pd.DataFrame) -> None:
    snapshot = price_snapshot(frame)
    if not snapshot:
        return
    session_change = snapshot["session_change_pct"]
    delta_class = "positive" if session_change >= 0 else "negative"
    st.markdown(
        f"""
        <style>
        .technical-metric-strip {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            border-top: 1px solid #E5E7EB;
            border-bottom: 1px solid #E5E7EB;
            margin: 0.45rem 0 0.75rem;
        }}
        .technical-metric {{
            min-width: 0;
            padding: 0.65rem 0.75rem;
            border-right: 1px solid #E5E7EB;
        }}
        .technical-metric:last-child {{ border-right: 0; }}
        .technical-metric-label {{
            min-height: 2.1em;
            color: #64748B;
            font-size: 0.75rem;
            line-height: 1.05rem;
        }}
        .technical-metric-value {{
            color: #111827;
            font-size: 1.35rem;
            font-weight: 650;
            line-height: 1.65rem;
            white-space: normal;
        }}
        .technical-metric-delta {{
            font-size: 0.72rem;
            line-height: 1rem;
            margin-top: 0.1rem;
        }}
        .technical-metric-delta.positive {{ color: #047857; }}
        .technical-metric-delta.negative {{ color: #DC2626; }}
        @media (max-width: 760px) {{
            .technical-metric-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
            .technical-metric:nth-child(2) {{ border-right: 0; }}
            .technical-metric:nth-child(-n+2) {{ border-bottom: 1px solid #E5E7EB; }}
        }}
        </style>
        <div class="technical-metric-strip">
            <div class="technical-metric">
                <div class="technical-metric-label">Giá gần nhất (VND)</div>
                <div class="technical-metric-value">{_format_price(snapshot["latest_close"])}</div>
                <div class="technical-metric-delta {delta_class}">{session_change:+.2f}% phiên gần nhất</div>
            </div>
            <div class="technical-metric">
                <div class="technical-metric-label">Thay đổi trong kỳ</div>
                <div class="technical-metric-value">{snapshot["period_change_pct"]:+.2f}%</div>
            </div>
            <div class="technical-metric">
                <div class="technical-metric-label">Cao nhất / thấp nhất</div>
                <div class="technical-metric-value">{_format_price(snapshot["period_high"])} / {_format_price(snapshot["period_low"])}</div>
            </div>
            <div class="technical-metric">
                <div class="technical-metric-label">KL bình quân 20 phiên</div>
                <div class="technical-metric-value">{_format_volume(snapshot["average_volume_20"])}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _chart_config(ticker: str) -> dict[str, Any]:
    return {
        "displayModeBar": True,
        "displaylogo": False,
        "scrollZoom": True,
        "doubleClick": "reset",
        "modeBarButtonsToAdd": [
            "drawline",
            "drawopenpath",
            "drawclosedpath",
            "drawcircle",
            "drawrect",
            "eraseshape",
        ],
        "modeBarButtonsToRemove": ["select2d", "lasso2d"],
        "toImageButtonOptions": {
            "format": "png",
            "filename": f"{ticker}_technical_chart",
            "scale": 2,
        },
    }


def render_tradingview_widget(
    ticker: str,
    height: int = 700,
    theme: str = "light",
    key_prefix: str = "main",
) -> None:
    """Render biểu đồ kỹ thuật có thể tùy biến trực tiếp trong Streamlit."""
    clean_ticker = get_clean_ticker(ticker)
    state_key = f"technical_{key_prefix}_{clean_ticker}"

    header_left, header_right = st.columns([4, 1.25], vertical_alignment="bottom")
    with header_left:
        st.subheader(f"Biểu đồ kỹ thuật {clean_ticker}")
    with header_right:
        entered_ticker = st.text_input(
            "Mã cổ phiếu",
            value=clean_ticker,
            key=f"{state_key}_ticker",
            max_chars=12,
        )
        if entered_ticker:
            clean_ticker = get_clean_ticker(entered_ticker)

    control_1, control_2, control_3 = st.columns([2.8, 1.45, 1.35])
    with control_1:
        period = (
            st.segmented_control(
                "Khoảng thời gian",
                options=["3T", "6T", "1N", "2N", "5N"],
                default="1N",
                key=f"{state_key}_period",
                width="stretch",
            )
            or "1N"
        )
    with control_2:
        interval = st.selectbox(
            "Khung nến",
            options=["Ngày", "Tuần", "Tháng"],
            key=f"{state_key}_interval",
        )
    with control_3:
        chart_type = st.selectbox(
            "Kiểu biểu đồ",
            options=["Nến", "OHLC", "Đường"],
            key=f"{state_key}_type",
        )
    with st.popover("Tùy chỉnh biểu đồ", icon=":material/tune:"):
        overlays = st.multiselect(
            "Đường trên biểu đồ giá",
            options=list(OVERLAY_OPTIONS),
            default=["MA 20", "MA 50"],
            key=f"{state_key}_overlays",
        )
        panels = st.multiselect(
            "Biểu đồ phụ",
            options=list(PANEL_OPTIONS),
            default=["Khối lượng", "RSI"],
            key=f"{state_key}_panels",
        )
        dark_mode = st.toggle(
            "Nền tối",
            value=theme == "dark",
            key=f"{state_key}_dark",
        )
        log_scale = st.toggle("Thang giá logarithm", key=f"{state_key}_log")
        show_range_slider = st.toggle(
            "Thanh chọn vùng thời gian", key=f"{state_key}_range"
        )

    start_date = period_start_date(period)
    try:
        with st.spinner(f"Đang tải dữ liệu giá {clean_ticker}..."):
            raw_frame = _load_price_history(clean_ticker, start_date)
        data_source = raw_frame.attrs.get("data_source", "CSDL giá nội bộ")
        daily_frame = normalize_price_history(raw_frame)
        if daily_frame.empty:
            st.warning(
                f"Chưa có dữ liệu giá cho mã {clean_ticker} trong khoảng đã chọn."
            )
            return

        frame = resample_price_history(daily_frame, interval)
        frame = add_technical_indicators(frame)
        _render_metrics(frame)
        fig = _build_chart(
            frame=frame,
            ticker=clean_ticker,
            period=period,
            interval=interval,
            chart_type=chart_type,
            overlays=overlays,
            panels=panels,
            dark_mode=dark_mode,
            log_scale=log_scale,
            show_range_slider=show_range_slider,
            base_height=height,
        )
        st.plotly_chart(
            fig,
            width="stretch",
            theme=None,
            config=_chart_config(clean_ticker),
            key=f"{state_key}_chart_{period}_{interval}_{chart_type}",
        )
        latest_date = frame.iloc[-1]["time"].strftime("%d/%m/%Y")
        st.caption(
            f"Nguồn: {data_source} · Dữ liệu gần nhất: {latest_date} · "
            "Trục giá: nghìn VND."
        )
    except (ValueError, KeyError) as exc:
        st.error(f"Dữ liệu biểu đồ chưa hợp lệ: {exc}")
    except _CHART_HANDLED_EXCEPTIONS as exc:
        st.error(f"Không thể tải biểu đồ kỹ thuật: {exc}")
