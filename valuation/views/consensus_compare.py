"""
Tab "So sánh CTCK" — đối chiếu định giá mô hình VN100 với các công ty chứng khoán.

Nội dung:
  1. KPI hàng đầu: FV mô hình | Median CTCK | Chênh lệch | Số CTCK.
  2. Biểu đồ football-field ngang: giá mục tiêu từng CTCK vs FV mô hình vs thị giá.
  3. Bảng chi tiết từng CTCK (giá mục tiêu, khuyến nghị, ngày, chênh so mô hình).
  4. AI tổng hợp (consensus_synthesis): điểm CHUNG / điểm RIÊNG / điểm MẤU CHỐT /
     đối chiếu mô hình nội bộ.

Dữ liệu: consensus_history (64 CTCK — 24hmoney + Simplize + Vietcap) và
consensus_synthesis (được sinh trong lượt báo cáo DeepSeek duy nhất ở tab BCTC).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy.orm import Session

from valuation.models.financials import Company
from valuation.models.financials_bank import CompanyBank
from valuation.report.report_data import build_consensus_comparison
from valuation.views.device import phone_collapsible, render_alerts

# Bảng màu đồng bộ giao diện báo cáo
_C_MODEL = "#1F4E78"  # xanh navy — mô hình VN100
_C_PRICE = "#EF4444"  # đỏ — thị giá
_C_BROKER = "#94A3B8"  # xám xanh — CTCK
_C_MEDIAN = "#F59E0B"  # cam — median CTCK


def _fmt_vnd(v: float | None) -> str:
    return f"{v:,.0f}".replace(",", ".") if v is not None else "—"


def _football_field(data: dict[str, Any]) -> go.Figure:
    """Bar ngang: giá mục tiêu từng CTCK; vline FV mô hình / thị giá / median."""
    rows = data["broker_rows"]
    brokers = [r["broker"] for r in rows][::-1]  # đảo để cao nhất nằm trên
    tps = [r["target_price"] for r in rows][::-1]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=brokers,
            x=tps,
            orientation="h",
            marker={"color": _C_BROKER, "opacity": 0.85},
            text=[_fmt_vnd(v) for v in tps],
            textposition="outside",
            hovertemplate="%{y}: %{x:,.0f} VND<extra></extra>",
            name="Giá mục tiêu CTCK",
        )
    )

    def _vline(x, color, label, dash):
        fig.add_vline(x=x, line_width=2, line_dash=dash, line_color=color)
        fig.add_annotation(
            x=x,
            y=1.06,
            yref="paper",
            showarrow=False,
            text=f"<b>{label}</b>",
            font={"color": color, "size": 12},
        )

    _vline(
        data["our_target"], _C_MODEL, f"Mô hình {_fmt_vnd(data['our_target'])}", "solid"
    )
    if data.get("current_price"):
        _vline(
            data["current_price"],
            _C_PRICE,
            f"Thị giá {_fmt_vnd(data['current_price'])}",
            "dash",
        )
    _vline(
        data["consensus_median"],
        _C_MEDIAN,
        f"Median {_fmt_vnd(data['consensus_median'])}",
        "dot",
    )

    fig.update_layout(
        height=max(320, 60 + 42 * len(brokers)),
        margin={"l": 10, "r": 90, "t": 60, "b": 10},
        xaxis={
            "title": "VND/cổ phiếu",
            "tickformat": ",.0f",
            "showgrid": True,
            "gridcolor": "rgba(148,163,184,0.25)",
        },
        yaxis={"title": None},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


def _panel(title: str, icon: str, color: str, items) -> None:
    """Panel gạch đầu dòng có viền màu (điểm chung/riêng/mấu chốt)."""
    if not items:
        return
    if isinstance(items, str):
        items = [items]
    lis = "".join(f"<li style='margin-bottom:6px;'>{it}</li>" for it in items)
    st.markdown(
        f"""
        <div style="border-left:4px solid {color}; background:{color}12;
                    border-radius:0 8px 8px 0; padding:12px 16px; margin-bottom:12px;">
          <div style="font-weight:700; color:{color}; margin-bottom:6px;">{icon} {title}</div>
          <ul style="margin:0; padding-left:18px; font-size:14px;">{lis}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_calibration(data: dict, dev: float) -> None:
    """Kết luận hiệu chuẩn cho mã này (D25).

    Thay cho cảnh báo cứng ">25%" trước đây: nay nói rõ mã có nằm trong band
    không, và nếu lệch thì lệch CÓ CHỦ Ý (kèm luận điểm) hay đang là LỖI ĐÃ BIẾT.
    Người đọc cần phân biệt hai thứ đó.
    """
    cal = data.get("calibration") or {}
    status = cal.get("governance_status")
    band = cal.get("band")
    band_txt = f"±{band:.0%}" if band else "±20%"

    if not status:  # không lấy được registry -> giữ cảnh báo cũ
        if data.get("flag_high"):
            st.warning(
                f"Mô hình lệch **{dev:+.1%}** so với trung vị CTCK (>25%) — rà soát giả định.",
                icon="🚨",
            )
        return

    if cal.get("band_status") == "IN_BAND":
        st.success(
            f"Mô hình lệch **{dev:+.1%}** — nằm trong ngưỡng chấp nhận {band_txt} "
            f"so với đồng thuận CTCK.",
            icon="✅",
        )
        return

    if status == "OK_JUSTIFIED":
        st.info(
            f"Mô hình lệch **{dev:+.1%}** (ngoài ngưỡng {band_txt}) — **lệch có chủ ý, "
            f"đã được giải trình**:",
            icon="🧭",
        )
        st.markdown(f"> {cal.get('thesis')}")
        ev = cal.get("evidence") or []
        if ev:
            st.caption("Bằng chứng: " + " · ".join(ev))
        if cal.get("decision_ref"):
            st.caption(
                f"Tham chiếu quyết định: {cal['decision_ref']} · "
                f"rà soát lần cuối {cal.get('reviewed_on')}"
            )
    elif status == "KNOWN_DEFECT":
        st.error(
            f"Mô hình lệch **{dev:+.1%}** (ngoài ngưỡng {band_txt}) — **đây là LỖI ĐÃ BIẾT** "
            f"của phương pháp định giá cho mã này, đang trong hàng đợi sửa. "
            f"Đừng dùng con số định giá này để ra quyết định.",
            icon="🛠️",
        )
        if cal.get("decision_ref"):
            st.caption(f"Tham chiếu: {cal['decision_ref']}")
    elif status == "DATA_BLOCKED":
        st.warning(
            f"Chưa đủ dữ liệu để kết luận mô hình đúng hay sai: {cal.get('thesis')}",
            icon="📭",
        )
    elif status == "STALE_JUSTIFICATION":
        st.warning(
            f"Mô hình lệch **{dev:+.1%}** — có luận điểm giải trình nhưng **đã quá hạn "
            f"rà soát** ({cal.get('reviewed_on')}). Cần xem lại còn đúng không.",
            icon="🕒",
        )
    else:  # MISSING_JUSTIFICATION
        st.warning(
            f"Mô hình lệch **{dev:+.1%}**, vượt ngưỡng {band_txt} so với đồng thuận CTCK "
            f"và **chưa có luận điểm giải trình**. Theo quy ước hiệu chuẩn, cần hoặc "
            f"giải trình được, hoặc coi là lỗi giả định và sửa.",
            icon="⚠️",
        )


def render_consensus_compare(
    company: Company | CompanyBank, blended_fv: float, db: Session
) -> None:
    """Render tab So sánh CTCK cho 1 mã."""
    st.header("So sánh với định giá công ty chứng khoán")

    data = build_consensus_comparison(
        company.ticker, blended_fv, db, current_price=company.current_price
    )
    if not data or not data.get("broker_rows"):
        st.info(
            "Chưa có dữ liệu khuyến nghị CTCK trong 180 ngày cho mã này. "
            "Bấm nút **'Tải mới "
            + company.ticker
            + "'** hoặc **'Quét VN100 Hàng Tuần'** "
            "ở thanh bên (điện thoại: nút « Chọn mã · Vĩ mô ») để thu thập báo cáo CTCK (Simplize/24hmoney) cho mã này.",
            icon="ℹ️",
        )
        return

    # ---- 1. KPI hàng đầu -------------------------------------------------
    dev = data["deviation"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🎯 FV mô hình VN100", f"{_fmt_vnd(data['our_target'])} đ")
    c2.metric(
        "🏦 Median CTCK",
        f"{_fmt_vnd(data['consensus_median'])} đ",
        help=f"Trung vị {data['n_reports']} CTCK trong 180 ngày "
        f"(từ {data.get('n_reports_raw', data['n_reports'])} báo cáo, "
        f"mỗi CTCK tính báo cáo mới nhất)",
    )
    c3.metric(
        "↔️ Mô hình vs CTCK", f"{dev:+.1%}", delta=f"{dev:+.1%}", delta_color="normal"
    )
    c4.metric(
        "📄 Số CTCK theo dõi",
        f"{data['n_brokers']}",
        help=f"Dải giá mục tiêu: {_fmt_vnd(data['range_min'])} – {_fmt_vnd(data['range_max'])} đ",
    )

    alerts: list[tuple[str, str, str | None]] = []
    # Đồng thuận quá mỏng: median chỉ phản ánh ý kiến 1 CTCK, không phải thị trường.
    if data.get("consensus_thin"):
        alerts.append(
            (
                "warning",
                (
                    f"Chỉ **{data['n_brokers']} CTCK** theo dõi mã này — con số 'đồng thuận' "
                    "bên trên thực chất là ý kiến đơn lẻ, không đại diện quan điểm thị trường. "
                    "Hãy đọc kèm luận điểm thay vì chỉ nhìn độ lệch."
                ),
                "⚠️",
            )
        )
    if data.get("consensus_stale"):
        alerts.append(
            (
                "info",
                (
                    "Báo cáo CTCK mới nhất đã cũ hơn 120 ngày — có thể chưa phản ánh "
                    "kết quả kinh doanh gần đây."
                ),
                "🕒",
            )
        )
    # D54: số CTCK đã có ở KPI c4; kết luận hiệu chuẩn bên dưới luôn hiện.
    render_alerts(alerts, max_visible=0)

    _render_calibration(data, dev)

    # ---- 2. Football field ------------------------------------------------
    with phone_collapsible("Giá mục tiêu từng CTCK"):
        st.subheader("Giá mục tiêu CTCK, mô hình và thị giá")
        st.plotly_chart(_football_field(data), width="stretch", theme=None)

        # ---- 3. Bảng chi tiết -------------------------------------------------
        st.subheader("Chi tiết khuyến nghị từng CTCK")
        df = pd.DataFrame(data["broker_rows"])
        df = df.rename(
            columns={
                "broker": "CTCK",
                "report_date": "Ngày BC",
                "target_price": "Giá mục tiêu (đ)",
                "rating": "Khuyến nghị",
                "vs_model": "Mô hình so với CTCK",
                "age_days": "Tuổi (ngày)",
            }
        )
        styler = (
            df.style.format(
                {
                    "Giá mục tiêu (đ)": lambda v: _fmt_vnd(v),
                    "Mô hình so với CTCK": "{:+.1%}",
                }
            )
            .map(
                lambda v: (
                    "color:#EF4444;font-weight:600;"
                    if isinstance(v, float) and v < -0.25
                    else (
                        "color:#16A34A;font-weight:600;"
                        if isinstance(v, float) and v > 0.25
                        else ""
                    )
                ),
                subset=["Mô hình so với CTCK"],
            )
            .map(
                lambda v: "color:#EF4444;" if isinstance(v, int) and v > 120 else "",
                subset=["Tuổi (ngày)"],
            )
        )
        st.dataframe(
            styler,
            width="stretch",
            hide_index=True,
            column_config={"CTCK": st.column_config.TextColumn(pinned=True)},
        )
        st.caption(
            "🔴 chênh >25% (mô hình thấp hơn) · 🟢 chênh >25% (mô hình cao hơn) · tuổi đỏ = báo cáo >120 ngày"
        )

    # ---- 4. AI tổng hợp điểm chung / riêng --------------------------------
    with phone_collapsible("Luận điểm CTCK (AI tổng hợp)"):
        st.subheader("Tổng hợp luận điểm CTCK")
        synth = data.get("synthesis")
        if synth:
            gen_at = synth.get("generated_at")
            gen_str = gen_at.strftime("%d/%m/%Y") if gen_at else "—"
            st.caption(
                f"Tổng hợp từ {synth['n_reports']} báo cáo ({synth['brokers']}) · "
                f"sinh ngày {gen_str} · ⚠️ AI tổng hợp từ báo cáo CTCK — cần analyst review"
            )
            col_l, col_r = st.columns(2)
            with col_l:
                _panel(
                    "Điểm CHUNG các CTCK đồng thuận",
                    "🤝",
                    "#16A34A",
                    synth["diem_chung"],
                )
                _panel(
                    "Điểm MẤU CHỐT / thị trường dễ bỏ sót",
                    "💡",
                    "#1D4ED8",
                    synth["diem_mau_chot"],
                )
            with col_r:
                _panel(
                    "Điểm RIÊNG / khác biệt giữa CTCK",
                    "⚖️",
                    "#D97706",
                    synth["diem_rieng"],
                )
                _panel(
                    "Đối chiếu mô hình nội bộ",
                    "🧭",
                    "#7C3AED",
                    synth["doi_chieu_noi_bo"],
                )
        else:
            st.info(
                "Chưa có bản AI tổng hợp cho mã này. Dùng nút **Kiểm chứng dữ liệu & "
                "sinh báo cáo qua DeepSeek** ở tab BCTC; cùng một lượt sẽ tạo luôn "
                "phần tổng hợp CTCK tại đây.",
                icon="🤖",
            )
