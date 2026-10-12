"""
Input financials view — Hiển thị báo cáo tài chính lịch sử (Khóa) và BCTC dự phóng 5 năm (Cho phép hiệu chỉnh).
"""

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from sqlalchemy.exc import SQLAlchemyError

from valuation.engine.forecast import forecast_company_financials
from valuation.engine.forecast_bank import forecast_bank_financials
from valuation.models.financials import Company
from valuation.models.financials_bank import CompanyBank
from valuation.report.verified_summary import (
    collect_consensus_context,
    collect_market_context,
    generate_verified_summary_cached,
    legacy_verified_summary_session_keys,
    persist_consensus_synthesis,
    report_markdown,
    verified_summary_session_key,
)
from valuation.views.device import phone_collapsible, render_alerts

_UI_HANDLED_EXCEPTIONS = (
    SQLAlchemyError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)

PLOTLY_CONFIG = {
    "modeBarButtonsToAdd": [
        "drawline",
        "drawopenpath",
        "drawclosedpath",
        "drawcircle",
        "drawrect",
        "eraseshape",
    ],
    "displaylogo": False,
}


def apply_financial_styling(df: pd.DataFrame) -> Any:
    """
    Áp dụng format dấu phân cách nghìn là '.' và thập phân là ',' theo chuẩn Việt Nam,
    đồng thời tô màu đỏ cho các số âm trong bảng.
    """
    # Tạo Pandas Styler và áp dụng định dạng
    styler = df.style.format(precision=1, thousands=".", decimal=",")
    # Tô đỏ số âm
    styler = styler.map(
        lambda v: (
            "color: #EF4444; font-weight: 500;"
            if isinstance(v, (int, float)) and v < 0
            else ""
        )
    )
    return styler


def auto_balance_bank_projections(
    proj_list: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Tự động tính toán lại các chỉ số phụ thuộc của Ngân hàng để đảm bảo tính tự khớp:
    TOI = NII + Non-II ; PPOP = TOI - OpEx ; LNTT = PPOP - Dự phòng
    """
    balanced_list = []
    for item in proj_list:
        row = item.copy()

        # OpEx và Provision lưu số dương trong model
        opex = abs(row.get("operating_expenses", 0.0))
        prov = abs(row.get("provision_expense", 0.0))

        nii = row.get("net_interest_income", 0.0)
        non_ii = row.get("non_interest_income", 0.0)

        toi = nii + non_ii
        ppop = toi - opex
        pbt = ppop - prov

        # Cập nhật ngược lại
        row["operating_expenses"] = opex
        row["provision_expense"] = prov
        row["total_operating_income"] = toi
        row["pre_provision_profit"] = ppop
        row["pretax_income"] = pbt
        # Ước lượng LNST từ LNTT (thuế 20%)
        row["net_income"] = max(0.0, pbt * 0.8)

        # Cân đối CĐKT: other_earning_assets, other_liabilities
        assets = row.get("total_assets", 0.0)
        loans = row.get("customer_loans", 0.0)
        deposits = row.get("customer_deposits", 0.0)
        equity = row.get("total_equity", 0.0)

        row["other_earning_assets"] = max(0.0, assets - loans)
        row["earning_assets"] = loans + row["other_earning_assets"]
        row["other_liabilities"] = max(0.0, assets - deposits - equity)

        balanced_list.append(row)
    return balanced_list


def auto_balance_non_bank_projections(
    proj_list: list[dict[str, Any]], tax_rate: float
) -> list[dict[str, Any]]:
    """
    Tự động tính toán lại các chỉ số của doanh nghiệp phi tài chính:
    Gross Profit = Revenue - COGS ; EBIT = Gross Profit - OpEx
    """
    balanced_list = []
    for item in proj_list:
        row = item.copy()

        rev = row.get("revenue", 0.0)
        cogs = abs(row.get("cogs", 0.0))
        opex = abs(row.get("opex", 0.0))
        int_exp = abs(row.get("interest_expense", 0.0))

        gp = rev - cogs
        ebit = gp - opex
        nopat = ebit * (1.0 - tax_rate)

        # Cập nhật ngược lại
        row["cogs"] = cogs
        row["opex"] = opex
        row["interest_expense"] = int_exp
        row["gross_profit"] = gp
        row["ebit"] = ebit
        row["nopat"] = nopat

        # Khớp LNST và FCFF
        pbt = ebit - int_exp
        row["net_income"] = max(0.0, pbt * (1.0 - tax_rate))

        depr = row.get("depreciation", 0.0)
        capex = abs(row.get("capex", 0.0))
        row["capex"] = capex

        delta_nwc = row.get("delta_nwc", 0.0)
        row["fcff"] = nopat + depr - capex - delta_nwc

        balanced_list.append(row)
    return balanced_list


def render_input_financials(
    company: Company | CompanyBank,
    blended_fv: float = 0.0,
    upside: float = 0.0,
    rec: str = "",
    db: Any = None,
    corporate_actions_context: Any = None,
):
    """
    Render giao diện xem BCTC Lịch sử (Đã khóa) và Dự phóng (Cho sửa đổi).
    """
    is_bank = isinstance(company, CompanyBank)
    base_year_mode = st.session_state.get("current_mode", "TTM")

    st.header("Báo cáo tài chính lịch sử & dự phóng")
    st.caption(
        "Đơn vị: tỷ đồng. Phần lịch sử dùng dữ liệu đã khóa, phần dự phóng cho phép chỉnh giả định."
    )
    st.markdown(
        f"**Mốc dữ liệu:** `{base_year_mode}` | **Năm gốc:** `{company.historical_is[-1].year}`"
    )
    st.markdown("---")

    # DeepSeek chỉ được gọi bên trong nhánh button này. Một response tạo toàn bộ
    # nội dung AI cho BCTC, PDF/Word, CTCK và sự kiện doanh nghiệp.
    st.subheader("Kiểm chứng dữ liệu & tóm tắt đầu tư")
    st.caption(
        "Dữ liệu không đổi: dùng lại báo cáo đã lưu, không gọi API. "
        "Dữ liệu thay đổi: tự động gọi DeepSeek đúng một lần."
    )
    force_ai = st.toggle(
        "Buộc DeepSeek viết lại dù dữ liệu không đổi",
        value=False,
        help="Chỉ bật khi bạn thật sự muốn một bản viết mới; thao tác này tốn một lượt API.",
    )
    ai_state_key = verified_summary_session_key(company.ticker)
    for legacy_key in legacy_verified_summary_session_keys(company.ticker):
        st.session_state.pop(legacy_key, None)
    if st.button(
        "Kiểm chứng dữ liệu & sinh báo cáo qua DeepSeek",
        type="primary",
        width="stretch",
        help="Một lần bấm tạo kiểm chứng, báo cáo PDF/Word, tổng hợp CTCK và phân tích sự kiện bằng tối đa một API call.",
    ):
        with st.spinner(
            "Đang kiểm tra BCTC và sinh toàn bộ nội dung báo cáo trong một lượt..."
        ):
            if corporate_actions_context is None and db is not None:
                from valuation.data_access.corporate_actions import (
                    corporate_actions_context as load_corporate_actions_context,
                )

                corporate_actions_context = load_corporate_actions_context(
                    db,
                    ticker=company.ticker,
                    current_price_vnd=company.current_price,
                    shares_outstanding=company.shares_outstanding * 1_000_000.0,
                )
            consensus_context = collect_consensus_context(
                ticker=company.ticker,
                blended_fv=blended_fv,
                current_price=company.current_price,
                db=db,
            )
            market_context = collect_market_context(
                ticker=company.ticker,
                sector=company.sector,
                db=db,
                current_price=company.current_price,
            )
            generated = generate_verified_summary_cached(
                company=company,
                blended_fv=blended_fv,
                current_price=company.current_price,
                upside=upside,
                recommendation=rec,
                consensus_context=consensus_context,
                corporate_actions_context=corporate_actions_context,
                market_context=market_context,
                force=force_ai,
            )
            generated["consensus_collection_warning"] = consensus_context.get(
                "collection_warning"
            )
            generated["consensus_available"] = consensus_context.get("available", False)
            generated["consensus_saved"] = False
            if generated.get("ai_generated") and db is not None:
                try:
                    generated["consensus_saved"] = persist_consensus_synthesis(
                        result=generated,
                        context=consensus_context,
                        ticker=company.ticker,
                        db=db,
                    )
                except _UI_HANDLED_EXCEPTIONS as exc:
                    generated["consensus_persist_error"] = str(exc)
            st.session_state[ai_state_key] = generated

    result = st.session_state.get(ai_state_key)
    if result:
        status = result.get("status", "WARNING")
        if status == "OK":
            st.success(
                "Kiểm chứng nội bộ đạt: chưa phát hiện sai lệch số học hoặc bất thường trọng yếu."
            )
        elif status == "ERROR":
            st.error(
                "Phát hiện lỗi dữ liệu trọng yếu. Không nên sử dụng báo cáo để ra quyết định trước khi đối chiếu filing gốc."
            )
        else:
            st.warning(
                "Dữ liệu có điểm cần kiểm tra thêm trước khi sử dụng kết quả định giá."
            )

        alerts: list[tuple[str, str, str | None]] = [
            ("warning", f"`{item['code']}` — {item['message']}", None)
            for item in result.get("python_issues", [])
        ]
        for item in result.get("ai_issues", []):
            message = (
                f"DeepSeek nghi vấn `{item['metric']}` ({item['period']}): "
                f"{item['finding']} Hành động: {item['action']}"
            )
            alerts.append(
                (
                    "error" if item.get("severity") == "error" else "warning",
                    message,
                    None,
                )
            )

        if result.get("error"):
            alerts.append(("error", result["error"], None))
        if result.get("ai_generated"):
            if result.get("cache_hit"):
                alerts.append(
                    (
                        "info",
                        (
                            "Dữ liệu không thay đổi nên hệ thống dùng lại báo cáo đã lưu. "
                            "Lần này không phát sinh API call."
                        ),
                        None,
                    )
                )
            completed = [
                "kiểm chứng dữ liệu",
                "tóm tắt đầu tư",
                "nhận định catalyst/kỹ thuật",
                "nội dung PDF",
            ]
            if result.get("consensus_saved"):
                completed.append("tổng hợp CTCK")
            alerts.append(("success", "Đã hoàn tất: " + " · ".join(completed), None))
            if not result.get("consensus_available"):
                alerts.append(
                    (
                        "info",
                        "Chưa có dữ liệu CTCK đủ dùng; các phần báo cáo còn lại vẫn đã được tạo.",
                        "ℹ️",
                    )
                )
            if result.get("consensus_collection_warning"):
                alerts.append(("warning", result["consensus_collection_warning"], None))
            if result.get("consensus_persist_error"):
                alerts.append(
                    (
                        "warning",
                        "Đã sinh tổng hợp CTCK nhưng chưa lưu được vào kho dữ liệu: "
                        + result["consensus_persist_error"],
                        None,
                    )
                )
        # Kết luận kiểm chứng ở trên luôn hiện; chi tiết gom lại trên điện thoại (D54).
        render_alerts(alerts, max_visible=0)
        if result.get("ai_generated"):
            with phone_collapsible("Báo cáo AI (nháp, cần review)"):
                st.caption(
                    f"Model: {result.get('model')} · "
                    f"Input: {result.get('input_tokens', 'N/A')} token · "
                    f"Output: {result.get('output_tokens', 'N/A')} token"
                )
                st.markdown("**NHÁP DO AI — CẦN ANALYST REVIEW TRƯỚC KHI PHÁT HÀNH**")
                st.markdown(report_markdown(result))
    st.markdown("---")

    # 1. Khởi tạo projections trong session state nếu chưa có
    if (
        "projections" not in st.session_state
        or st.session_state.get("projections_ticker") != company.ticker
        or st.session_state.get("projections_mode") != base_year_mode
    ):
        if is_bank:
            st.session_state["projections"] = forecast_bank_financials(company)
        else:
            st.session_state["projections"] = forecast_company_financials(company)
        st.session_state["projections_ticker"] = company.ticker
        st.session_state["projections_mode"] = base_year_mode
        st.session_state["last_assumptions"] = company.assumptions.model_dump()

    # 2. RÀ SOÁT TỰ ĐỘNG CHẠY LẠI KHI ĐỔI GIẢ ĐỊNH (đồng bộ Việc 3)
    curr_ass_dump = company.assumptions.model_dump()
    if st.session_state.get("last_assumptions") != curr_ass_dump:
        if is_bank:
            st.session_state["projections"] = forecast_bank_financials(company)
        else:
            st.session_state["projections"] = forecast_company_financials(company)
        st.session_state["last_assumptions"] = curr_ass_dump

    # ----------------------------------------------------
    # PHÂN ĐOẠN 0: BIỂU ĐỒ TỔNG QUAN TÀI CHÍNH
    # ----------------------------------------------------
    st.subheader("0. Tổng quan tài chính")

    # Chuẩn bị dữ liệu vẽ biểu đồ
    years = [str(item.year) for item in company.historical_is] + [
        f"{proj['year']}E" for proj in st.session_state["projections"]
    ]

    if is_bank:
        rev_hist = [item.total_operating_income for item in company.historical_is]
        ni_hist = [item.net_income for item in company.historical_is]
        rev_proj = [
            proj.get("net_interest_income", 0) + proj.get("non_interest_income", 0)
            for proj in st.session_state["projections"]
        ]
        ni_proj = [
            proj.get("net_income", 0) for proj in st.session_state["projections"]
        ]
        rev_name = "Tổng thu nhập HĐ (TOI - Total Operating Income)"
    else:
        rev_hist = [item.revenue for item in company.historical_is]
        ni_hist = [item.net_income for item in company.historical_is]
        rev_proj = [proj.get("revenue", 0) for proj in st.session_state["projections"]]
        ni_proj = [
            proj.get("net_income", 0) for proj in st.session_state["projections"]
        ]
        rev_name = "Doanh thu thuần (Net Revenue)"

    rev_total = rev_hist + rev_proj
    ni_total = ni_hist + ni_proj

    # Plotly figure
    fig_overview = make_subplots(specs=[[{"secondary_y": True}]])

    # Revenue/TOI Bar
    fig_overview.add_trace(
        go.Bar(
            x=years,
            y=rev_total,
            name=rev_name,
            marker_color=["#3b82f6"] * len(rev_hist) + ["#60a5fa"] * len(rev_proj),
            opacity=0.9,
        ),
        secondary_y=False,
    )

    # Net Income Line
    fig_overview.add_trace(
        go.Scatter(
            x=years,
            y=ni_total,
            name="Lợi nhuận sau thuế (Net Income)",
            mode="lines+markers",
            marker_color="#10b981",
            line={"width": 3},
        ),
        secondary_y=True,
    )

    fig_overview.update_layout(
        height=450,
        paper_bgcolor="#0F172A",
        plot_bgcolor="#1E293B",
        font={"color": "#F8FAFC", "family": "Inter"},
        hovermode="x unified",
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.2,
            "xanchor": "left",
            "x": 0,
            "font": {"color": "#F8FAFC"},
            "bgcolor": "rgba(15, 23, 42, 0.9)",
            "bordercolor": "#334155",
            "borderwidth": 1,
        },
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
    )
    fig_overview.update_yaxes(
        title_text=f"{rev_name} (Tỷ VNĐ)",
        secondary_y=False,
        showgrid=True,
        gridcolor="#334155",
    )
    fig_overview.update_yaxes(
        title_text="Lợi nhuận (Tỷ VNĐ)", secondary_y=True, showgrid=False
    )

    st.plotly_chart(fig_overview, width="stretch", theme=None, config=PLOTLY_CONFIG)

    # ----------------------------------------------------
    # PHÂN ĐOẠN 1: BÁO CÁO KẾT QUẢ KINH DOANH (IS)
    # ----------------------------------------------------
    with phone_collapsible("1. Kết quả kinh doanh (IS)"):
        st.subheader("1. Báo cáo Kết quả Kinh doanh (IS)")

        # 1.1. Dữ liệu lịch sử IS
        is_hist_data = []
        for item in company.historical_is:
            if is_bank:
                is_hist_data.append(
                    {
                        "Năm": f"{item.year} (Lịch sử)",
                        "Thu nhập lãi thuần": item.net_interest_income,
                        "Thu nhập ngoài lãi": item.non_interest_income,
                        "Tổng thu nhập hoạt động (TOI)": item.total_operating_income,
                        "Chi phí hoạt động": item.operating_expenses,
                        "Lợi nhuận trước dự phòng (PPOP)": item.pre_provision_profit,
                        "Chi phí dự phòng": item.provision_expense,
                        "Lợi nhuận trước thuế (LNTT)": item.pretax_income,
                        "Lợi nhuận sau thuế (LNST)": item.net_income,
                    }
                )
            else:
                is_hist_data.append(
                    {
                        "Năm": f"{item.year} (Lịch sử)",
                        "Doanh thu thuần": item.revenue,
                        "Giá vốn hàng bán": item.cogs,
                        "Lợi nhuận gộp": item.gross_profit,
                        "Chi phí hoạt động": item.opex,
                        "Lợi nhuận trước lãi vay & thuế (EBIT)": item.ebit,
                        "Chi phí lãi vay": item.interest_expense,
                        "Thuế TNDN": item.tax,
                        "Lợi nhuận sau thuế (LNST)": item.net_income,
                    }
                )

        df_is_hist = pd.DataFrame(is_hist_data).set_index("Năm")

        st.caption(
            "Số liệu lịch sử từ kho dữ liệu; trạng thái kiểm chứng được ghi riêng, không đồng nghĩa đã kiểm toán lại."
        )
        st.dataframe(apply_financial_styling(df_is_hist), width="stretch")

        # --- BIỂU ĐỒ 1: Xu hướng IS lịch sử ---
        _dark_theme = {
            "paper_bgcolor": "#0F172A",
            "plot_bgcolor": "#1E293B",
            "font": {"color": "#F8FAFC", "family": "Inter"},
            "legend": {
                "orientation": "h",
                "yanchor": "top",
                "y": -0.2,
                "xanchor": "left",
                "x": 0,
                "font": {"color": "#F8FAFC"},
                "bgcolor": "rgba(15, 23, 42, 0.9)",
                "bordercolor": "#334155",
                "borderwidth": 1,
            },
        }
        hist_years = [str(item.year) for item in company.historical_is]

        if is_bank:
            # Ngân hàng: cột NII + đường CIR
            nii_vals = [item.net_interest_income for item in company.historical_is]
            toi_vals = [item.total_operating_income for item in company.historical_is]
            cir_vals = [
                (
                    (abs(item.operating_expenses) / item.total_operating_income * 100)
                    if item.total_operating_income
                    else 0.0
                )
                for item in company.historical_is
            ]

            fig_is_trend = make_subplots(specs=[[{"secondary_y": True}]])
            fig_is_trend.add_trace(
                go.Bar(
                    x=hist_years,
                    y=nii_vals,
                    name="Thu nhập lãi thuần (Net Interest Income)",
                    marker_color="#3B82F6",
                ),
                secondary_y=False,
            )
            fig_is_trend.add_trace(
                go.Bar(
                    x=hist_years,
                    y=toi_vals,
                    name="Tổng thu nhập HĐ (TOI)",
                    marker_color="#10B981",
                    opacity=0.6,
                ),
                secondary_y=False,
            )
            fig_is_trend.add_trace(
                go.Scatter(
                    x=hist_years,
                    y=cir_vals,
                    name="Tỷ lệ chi phí/thu nhập (CIR %)",
                    line={"color": "#F59E0B", "width": 3},
                    mode="lines+markers",
                ),
                secondary_y=True,
            )
            fig_is_trend.update_yaxes(title_text="Tỷ đồng", secondary_y=False)
            fig_is_trend.update_yaxes(title_text="CIR (%)", secondary_y=True)
            fig_is_trend.update_layout(
                title="Xu hướng Thu nhập & CIR (Lịch sử)",
                barmode="group",
                height=420,
                **_dark_theme,
            )
        else:
            # Phi tài chính: cột Revenue + đường EBIT Margin
            rev_vals = [item.revenue for item in company.historical_is]
            ebit_margins = [
                (item.ebit / item.revenue * 100) if item.revenue else 0.0
                for item in company.historical_is
            ]

            fig_is_trend = make_subplots(specs=[[{"secondary_y": True}]])
            fig_is_trend.add_trace(
                go.Bar(
                    x=hist_years,
                    y=rev_vals,
                    name="Doanh thu thuần (Net Revenue)",
                    marker_color="#3B82F6",
                ),
                secondary_y=False,
            )
            fig_is_trend.add_trace(
                go.Scatter(
                    x=hist_years,
                    y=ebit_margins,
                    name="Biên lợi nhuận EBIT (EBIT Margin %)",
                    line={"color": "#10B981", "width": 3},
                    mode="lines+markers",
                ),
                secondary_y=True,
            )
            fig_is_trend.update_yaxes(title_text="Tỷ đồng", secondary_y=False)
            fig_is_trend.update_yaxes(title_text="Biên EBIT (%)", secondary_y=True)
            fig_is_trend.update_layout(
                title="Xu hướng Doanh thu & Biên EBIT (Lịch sử)",
                barmode="group",
                height=420,
                **_dark_theme,
            )

        st.plotly_chart(fig_is_trend, width="stretch", theme=None, config=PLOTLY_CONFIG)

        # 1.2. Dữ liệu dự phóng IS
        is_proj_data = []
        for proj in st.session_state["projections"]:
            if is_bank:
                is_proj_data.append(
                    {
                        "Năm": f"{proj['year']} (Dự phóng)",
                        "Thu nhập lãi thuần": proj.get("net_interest_income", 0.0),
                        "Thu nhập ngoài lãi": proj.get("non_interest_income", 0.0),
                        "Tổng thu nhập hoạt động (TOI)": proj.get(
                            "total_operating_income", 0.0
                        ),
                        "Chi phí hoạt động": proj.get("operating_expenses", 0.0),
                        "Lợi nhuận trước dự phòng (PPOP)": proj.get(
                            "pre_provision_profit", 0.0
                        ),
                        "Chi phí dự phòng": proj.get("provision_expense", 0.0),
                        "Lợi nhuận trước thuế (LNTT)": proj.get("pretax_income", 0.0),
                        "Lợi nhuận sau thuế (LNST)": proj.get("net_income", 0.0),
                    }
                )
            else:
                is_proj_data.append(
                    {
                        "Năm": f"{proj['year']} (Dự phóng)",
                        "Doanh thu thuần": proj.get("revenue", 0.0),
                        "Giá vốn hàng bán": proj.get("cogs", 0.0),
                        "Lợi nhuận gộp": proj.get("gross_profit", 0.0),
                        "Chi phí hoạt động": proj.get("opex", 0.0),
                        "Lợi nhuận trước lãi vay & thuế (EBIT)": proj.get("ebit", 0.0),
                        "Chi phí lãi vay": proj.get("interest_expense", 0.0),
                        "Thuế TNDN": proj.get("tax", 0.0),
                        "Lợi nhuận sau thuế (LNST)": proj.get("net_income", 0.0),
                    }
                )

        df_is_proj = pd.DataFrame(is_proj_data).set_index("Năm")

        st.caption("🟢 Phần Dự phóng (Cho phép hiệu chỉnh):")
        # Cho phép chỉnh sửa bảng dự phóng
        edited_is_proj = st.data_editor(
            df_is_proj,
            width="stretch",
            disabled=[
                "Tổng thu nhập hoạt động (TOI)",
                "Lợi nhuận trước dự phòng (PPOP)",
                "Lợi nhuận trước thuế (LNTT)",
                "Lợi nhuận sau thuế (LNST)",
                "Lợi nhuận gộp",
                "EBIT",
                "nopat",
                "fcff",
            ],
            key="is_proj_editor",
        )

    # ----------------------------------------------------
    # PHÂN ĐOẠN 2: BẢNG CÂN ĐỐI KẾ TOÁN (BS)
    # ----------------------------------------------------
    with phone_collapsible("2. Cân đối kế toán (BS)"):
        st.subheader("2. Bảng Cân đối Kế toán (BS)")

        # 2.1. Dữ liệu lịch sử BS
        bs_hist_data = []
        for item in company.historical_bs:
            if is_bank:
                bs_hist_data.append(
                    {
                        "Năm": f"{item.year} (Lịch sử)",
                        "Cho vay khách hàng": item.customer_loans,
                        "Tài sản sinh lời khác": item.other_earning_assets,
                        "Tổng tài sản": item.total_assets,
                        "Tiền gửi của khách hàng": item.customer_deposits,
                        "Nợ phải trả khác": item.other_liabilities,
                        "Vốn chủ sở hữu": item.total_equity,
                    }
                )
            else:
                bs_hist_data.append(
                    {
                        "Năm": f"{item.year} (Lịch sử)",
                        "Tiền & Tương đương tiền": item.cash_and_equivalents,
                        "Phải thu khách hàng": item.receivables,
                        "Hàng tồn kho": item.inventory,
                        "Tài sản ngắn hạn khác": item.other_current_assets,
                        "Tài sản cố định": item.fixed_assets,
                        "Tài sản dài hạn khác": item.other_long_term_assets,
                        "Tổng tài sản": item.total_assets,
                        "Nợ vay ngắn hạn": item.short_term_debt,
                        "Phải trả người bán": item.accounts_payable,
                        "Nợ ngắn hạn khác": item.other_current_liabilities,
                        "Nợ vay dài hạn": item.long_term_debt,
                        "Nợ dài hạn khác": item.other_long_term_liabilities,
                        "Vốn chủ sở hữu": item.total_equity,
                    }
                )

        df_bs_hist = pd.DataFrame(bs_hist_data).set_index("Năm")

        st.caption(
            "Số liệu lịch sử từ kho dữ liệu; chưa đồng nghĩa đã đối chiếu BCTC gốc."
        )
        st.dataframe(apply_financial_styling(df_bs_hist), width="stretch")

        # --- BIỂU ĐỒ 2: Cấu trúc Bảng cân đối kế toán (Stacked Bar) ---
        if is_bank:
            # Ngân hàng: Cho vay + Tài sản sinh lời khác
            bs_years = [str(item.year) for item in company.historical_bs]
            loans_vals = [item.customer_loans for item in company.historical_bs]
            other_ea_vals = [
                item.other_earning_assets for item in company.historical_bs
            ]

            fig_bs_comp = go.Figure()
            fig_bs_comp.add_trace(
                go.Bar(
                    x=bs_years,
                    y=loans_vals,
                    name="Cho vay khách hàng (Customer Loans)",
                    marker_color="#3B82F6",
                )
            )
            fig_bs_comp.add_trace(
                go.Bar(
                    x=bs_years,
                    y=other_ea_vals,
                    name="Tài sản sinh lời khác (Other Earning Assets)",
                    marker_color="#10B981",
                )
            )
            fig_bs_comp.update_layout(
                title="Cấu trúc Tài sản Ngân hàng (Lịch sử)",
                barmode="stack",
                height=420,
                yaxis_title="Tỷ đồng",
                paper_bgcolor="#0F172A",
                plot_bgcolor="#1E293B",
                font={"color": "#F8FAFC", "family": "Inter"},
                margin={"l": 40, "r": 20, "t": 50, "b": 40},
                legend={
                    "orientation": "h",
                    "yanchor": "top",
                    "y": -0.2,
                    "xanchor": "left",
                    "x": 0,
                    "font": {"color": "#F8FAFC"},
                    "bgcolor": "rgba(15, 23, 42, 0.9)",
                    "bordercolor": "#334155",
                    "borderwidth": 1,
                },
            )
        else:
            # Phi tài chính: Cash + Receivables + Inventory + Fixed Assets + Other
            bs_years = [str(item.year) for item in company.historical_bs]
            cash_vals = [item.cash_and_equivalents for item in company.historical_bs]
            recv_vals = [item.receivables for item in company.historical_bs]
            inv_vals = [item.inventory for item in company.historical_bs]
            fa_vals = [item.fixed_assets for item in company.historical_bs]
            other_vals = [
                item.other_current_assets + item.other_long_term_assets
                for item in company.historical_bs
            ]

            fig_bs_comp = go.Figure()
            fig_bs_comp.add_trace(
                go.Bar(
                    x=bs_years,
                    y=cash_vals,
                    name="Tiền & Tương đương tiền (Cash & Equivalents)",
                    marker_color="#3B82F6",
                )
            )
            fig_bs_comp.add_trace(
                go.Bar(
                    x=bs_years,
                    y=recv_vals,
                    name="Phải thu (Receivables)",
                    marker_color="#10B981",
                )
            )
            fig_bs_comp.add_trace(
                go.Bar(
                    x=bs_years,
                    y=inv_vals,
                    name="Hàng tồn kho (Inventory)",
                    marker_color="#F59E0B",
                )
            )
            fig_bs_comp.add_trace(
                go.Bar(
                    x=bs_years,
                    y=fa_vals,
                    name="Tài sản cố định (Fixed Assets)",
                    marker_color="#8B5CF6",
                )
            )
            fig_bs_comp.add_trace(
                go.Bar(
                    x=bs_years,
                    y=other_vals,
                    name="Tài sản khác (Other Assets)",
                    marker_color="#64748B",
                )
            )
            fig_bs_comp.update_layout(
                title="Cấu trúc Tài sản (Lịch sử)",
                barmode="stack",
                height=420,
                yaxis_title="Tỷ đồng",
                paper_bgcolor="#0F172A",
                plot_bgcolor="#1E293B",
                font={"color": "#F8FAFC", "family": "Inter"},
                margin={"l": 40, "r": 20, "t": 50, "b": 40},
                legend={
                    "orientation": "h",
                    "yanchor": "top",
                    "y": -0.2,
                    "xanchor": "left",
                    "x": 0,
                    "font": {"color": "#F8FAFC"},
                    "bgcolor": "rgba(15, 23, 42, 0.9)",
                    "bordercolor": "#334155",
                    "borderwidth": 1,
                },
            )

        st.plotly_chart(fig_bs_comp, width="stretch", theme=None, config=PLOTLY_CONFIG)

        # 2.2. Dữ liệu dự phóng BS
        bs_proj_data = []
        for proj in st.session_state["projections"]:
            if is_bank:
                bs_proj_data.append(
                    {
                        "Năm": f"{proj['year']} (Dự phóng)",
                        "Cho vay khách hàng": proj.get("customer_loans", 0.0),
                        "Tài sản sinh lời khác": proj.get("other_earning_assets", 0.0),
                        "Tổng tài sản": proj.get("total_assets", 0.0),
                        "Tiền gửi của khách hàng": proj.get("customer_deposits", 0.0),
                        "Nợ phải trả khác": proj.get("other_liabilities", 0.0),
                        "Vốn chủ sở hữu": proj.get("total_equity", 0.0),
                    }
                )
            else:
                # Đối với phi ngân hàng, ta tạo dữ liệu BS dự phóng xấp xỉ hoặc lấy từ projections
                # Nếu projections chưa có các cột BS, ta tự lấy giá trị của năm lịch sử gần nhất làm default
                last_bs = company.historical_bs[-1]
                bs_proj_data.append(
                    {
                        "Năm": f"{proj['year']} (Dự phóng)",
                        "Tiền & Tương đương tiền": proj.get(
                            "cash_and_equivalents", last_bs.cash_and_equivalents
                        ),
                        "Phải thu khách hàng": proj.get(
                            "receivables", last_bs.receivables
                        ),
                        "Hàng tồn kho": proj.get("inventory", last_bs.inventory),
                        "Tài sản ngắn hạn khác": proj.get(
                            "other_current_assets", last_bs.other_current_assets
                        ),
                        "Tài sản cố định": proj.get(
                            "fixed_assets", last_bs.fixed_assets
                        ),
                        "Tài sản dài hạn khác": proj.get(
                            "other_long_term_assets", last_bs.other_long_term_assets
                        ),
                        "Tổng tài sản": proj.get("total_assets", last_bs.total_assets),
                        "Nợ vay ngắn hạn": proj.get(
                            "short_term_debt", last_bs.short_term_debt
                        ),
                        "Phải trả người bán": proj.get(
                            "accounts_payable", last_bs.accounts_payable
                        ),
                        "Nợ ngắn hạn khác": proj.get(
                            "other_current_liabilities",
                            last_bs.other_current_liabilities,
                        ),
                        "Nợ vay dài hạn": proj.get(
                            "long_term_debt", last_bs.long_term_debt
                        ),
                        "Nợ dài hạn khác": proj.get(
                            "other_long_term_liabilities",
                            last_bs.other_long_term_liabilities,
                        ),
                        "Vốn chủ sở hữu": proj.get(
                            "total_equity", last_bs.total_equity
                        ),
                    }
                )

        df_bs_proj = pd.DataFrame(bs_proj_data).set_index("Năm")

        st.caption("🟢 Phần Dự phóng (Cho phép hiệu chỉnh):")
        edited_bs_proj = st.data_editor(
            df_bs_proj,
            width="stretch",
            disabled=(
                ["Tài sản sinh lời khác", "Nợ phải trả khác", "earning_assets"]
                if is_bank
                else []
            ),
            key="bs_proj_editor",
        )

    # 3. ĐỒNG BỘ HÓA SỐ LIỆU ĐÃ SỬA TỪ CẢ HAI BẢNG
    # Lấy dữ liệu sửa đổi từ các data_editor
    updated_projections = []

    for i, proj in enumerate(st.session_state["projections"]):
        year_str = f"{proj['year']} (Dự phóng)"
        row = proj.copy()

        # 3.1. Đồng bộ IS
        if is_bank:
            row["net_interest_income"] = float(
                edited_is_proj.loc[year_str, "Thu nhập lãi thuần"]
            )
            row["non_interest_income"] = float(
                edited_is_proj.loc[year_str, "Thu nhập ngoài lãi"]
            )
            row["operating_expenses"] = abs(
                float(edited_is_proj.loc[year_str, "Chi phí hoạt động"])
            )
            row["provision_expense"] = abs(
                float(edited_is_proj.loc[year_str, "Chi phí dự phòng"])
            )

            # 3.2. Đồng bộ BS
            row["customer_loans"] = float(
                edited_bs_proj.loc[year_str, "Cho vay khách hàng"]
            )
            row["total_assets"] = float(edited_bs_proj.loc[year_str, "Tổng tài sản"])
            row["customer_deposits"] = float(
                edited_bs_proj.loc[year_str, "Tiền gửi của khách hàng"]
            )
            row["total_equity"] = float(edited_bs_proj.loc[year_str, "Vốn chủ sở hữu"])
        else:
            row["revenue"] = float(edited_is_proj.loc[year_str, "Doanh thu thuần"])
            row["cogs"] = abs(float(edited_is_proj.loc[year_str, "Giá vốn hàng bán"]))
            row["opex"] = abs(float(edited_is_proj.loc[year_str, "Chi phí hoạt động"]))
            row["interest_expense"] = abs(
                float(edited_is_proj.loc[year_str, "Chi phí lãi vay"])
            )
            row["tax"] = abs(float(edited_is_proj.loc[year_str, "Thuế TNDN"]))

            # Đồng bộ BS
            row["cash_and_equivalents"] = float(
                edited_bs_proj.loc[year_str, "Tiền & Tương đương tiền"]
            )
            row["receivables"] = float(
                edited_bs_proj.loc[year_str, "Phải thu khách hàng"]
            )
            row["inventory"] = float(edited_bs_proj.loc[year_str, "Hàng tồn kho"])
            row["other_current_assets"] = float(
                edited_bs_proj.loc[year_str, "Tài sản ngắn hạn khác"]
            )
            row["fixed_assets"] = float(edited_bs_proj.loc[year_str, "Tài sản cố định"])
            row["other_long_term_assets"] = float(
                edited_bs_proj.loc[year_str, "Tài sản dài hạn khác"]
            )
            row["total_assets"] = float(edited_bs_proj.loc[year_str, "Tổng tài sản"])
            row["short_term_debt"] = float(
                edited_bs_proj.loc[year_str, "Nợ vay ngắn hạn"]
            )
            row["accounts_payable"] = float(
                edited_bs_proj.loc[year_str, "Phải trả người bán"]
            )
            row["other_current_liabilities"] = float(
                edited_bs_proj.loc[year_str, "Nợ ngắn hạn khác"]
            )
            row["long_term_debt"] = float(
                edited_bs_proj.loc[year_str, "Nợ vay dài hạn"]
            )
            row["other_long_term_liabilities"] = float(
                edited_bs_proj.loc[year_str, "Nợ dài hạn khác"]
            )
            row["total_equity"] = float(edited_bs_proj.loc[year_str, "Vốn chủ sở hữu"])

        updated_projections.append(row)

    # 3.3. Chạy tự động khớp và lưu lại session state
    if is_bank:
        st.session_state["projections"] = auto_balance_bank_projections(
            updated_projections
        )
    else:
        st.session_state["projections"] = auto_balance_non_bank_projections(
            updated_projections, company.assumptions.tax_rate
        )

    # 4. Kiểm tra tính cân đối của BS và in cảnh báo
    st.markdown("---")
    with phone_collapsible("Kiểm tra cân đối BCĐKT"):
        st.subheader("🔍 Kiểm tra Tính Cân Đối Bảng Cân Đối Kế Toán")

        warnings = []
        # 4.1. Lịch sử BS
        for bs in company.historical_bs:
            diff = abs(bs.total_assets - bs.total_liabilities_and_equity)
            if diff > 0.05:
                warnings.append(
                    f"Năm {bs.year} (Lịch sử): Bảng cân đối không cân! Lệch {diff:.1f} tỷ đồng."
                )

        # 4.2. Dự phóng BS
        for proj in st.session_state["projections"]:
            year = proj["year"]
            if is_bank:
                tot_assets = proj.get("total_assets", 0.0)
                tot_liab_eq = (
                    proj.get("customer_deposits", 0.0)
                    + proj.get("other_liabilities", 0.0)
                    + proj.get("total_equity", 0.0)
                )
            else:
                tot_assets = proj.get("total_assets", 0.0)
                tot_liab_eq = (
                    proj.get("short_term_debt", 0.0)
                    + proj.get("accounts_payable", 0.0)
                    + proj.get("other_current_liabilities", 0.0)
                    + proj.get("long_term_debt", 0.0)
                    + proj.get("other_long_term_liabilities", 0.0)
                    + proj.get("total_equity", 0.0)
                )
            diff = abs(tot_assets - tot_liab_eq)
            if diff > 0.05:
                warnings.append(
                    f"Năm {year} (Dự phóng): Bảng cân đối không cân! Lệch {diff:.1f} tỷ đồng."
                )

        if warnings:
            for warn in warnings:
                st.warning(warn, icon="⚠️")
        else:
            st.success(
                "Bảng cân đối kế toán (Lịch sử & Dự phóng) hoàn toàn cân đối!",
                icon="✅",
            )
