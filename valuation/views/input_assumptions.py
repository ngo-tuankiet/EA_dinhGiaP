"""
Input assumptions view — Hiệu chỉnh các giả định dự phóng và tham số định giá.
"""

import pandas as pd
import streamlit as st

from valuation.models.financials import Company
from valuation.models.financials_bank import CompanyBank


def render_input_assumptions(company: Company | CompanyBank):
    """
    Render giao diện nhập giả định cho Analyst.
    """
    st.header("⚙️ Giả định Dự phóng & Tham số Định giá")

    is_bank = isinstance(company, CompanyBank)
    assumptions = company.assumptions

    st.subheader("Quản lý kịch bản (Scenario Manager)")
    # QUAN TRỌNG: đọc từ state CHUNG "analyst_scenario" và CHỈ ghi khi user thực sự đổi.
    # Trước đây ô này luôn index=0 và ghi đè "Base" vô điều kiện mỗi lần rerun, đánh nhau với
    # ô chọn kịch bản ở tab "Kết quả" (results.py) → gây VÒNG LẶP RERUN VÔ HẠN (ghim 100% CPU).
    _scen_opts = ["Base", "Bull", "Bear"]
    _scen_cur = st.session_state.get("analyst_scenario", "Base")
    scenario = st.selectbox(
        "Chọn Kịch bản (Scenario):",
        _scen_opts,
        index=_scen_opts.index(_scen_cur) if _scen_cur in _scen_opts else 0,
        key="scenario_select_assumptions",
        help="Base: Cơ sở | Bull: Tích cực | Bear: Tiêu cực",
    )
    # Chỉ cập nhật state chung khi giá trị thực sự thay đổi (tránh ghi đè gây loop).
    if scenario != _scen_cur:
        st.session_state["analyst_scenario"] = scenario

    st.subheader("1. Chi phí sử dụng vốn (COE / WACC)")
    col1, col2, col3 = st.columns(3)
    with col1:
        rf = st.number_input(
            "Lợi suất phi rủi ro (rf):",
            value=float(assumptions.risk_free_rate),
            min_value=0.0,
            max_value=0.20,
            step=0.001,
            format="%.4f",
            help="Lãi suất an toàn nhất, thường lấy theo Lãi suất TPCP 10 năm. Đại diện cho chi phí cơ hội.",
        )
    with col2:
        beta = st.number_input(
            "Hệ số Beta (β):",
            value=float(assumptions.beta),
            min_value=0.1,
            max_value=3.0,
            step=0.01,
            format="%.2f",
            help="Đo lường rủi ro biến động của cổ phiếu so với VN-Index. Beta > 1 nghĩa là rủi ro cao hơn thị trường.",
        )
    with col3:
        erp = st.number_input(
            "Phần bù rủi ro (ERP):",
            value=float(assumptions.erp),
            min_value=0.01,
            max_value=0.20,
            step=0.001,
            format="%.4f",
            help="Tỷ suất sinh lời cộng thêm nhà đầu tư đòi hỏi để bù đắp rủi ro khi đầu tư cổ phiếu thay vì trái phiếu.",
        )

    # Cập nhật lại Re
    assumptions.risk_free_rate = rf
    assumptions.beta = beta
    assumptions.erp = erp
    coe = rf + beta * erp
    st.markdown(f"**Chi phí sử dụng vốn cổ phần (COE - Re):** `{coe:.2%}`")

    if not is_bank:
        col4, col5 = st.columns(2)
        with col4:
            cod = st.number_input(
                "Chi phí nợ vay (Rd):",
                value=float(assumptions.cost_of_debt),
                min_value=0.0,
                max_value=0.20,
                step=0.005,
                format="%.4f",
                help="Lãi suất đi vay bình quân của doanh nghiệp.",
            )
        with col5:
            tax = st.number_input(
                "Thuế suất TNDN (t):",
                value=float(assumptions.tax_rate),
                min_value=0.0,
                max_value=0.50,
                step=0.01,
                format="%.2f",
                help="Thuế suất thuế thu nhập doanh nghiệp áp dụng.",
            )
        assumptions.cost_of_debt = cod
        assumptions.tax_rate = tax

        # Cập nhật WACC ước lượng ở cấu trúc vốn hiện tại
        E = company.historical_bs[-1].total_equity
        D = (
            company.historical_bs[-1].short_term_debt
            + company.historical_bs[-1].long_term_debt
        )
        from valuation.engine.wacc import compute_wacc

        wacc_est = compute_wacc(coe, cod, E, D, tax)
        st.markdown(f"**Ước lượng WACC (ở cấu trúc vốn lịch sử):** `{wacc_est:.2%}`")

    st.subheader("2. Giả định dự phóng 5 năm tiếp theo")

    # Tạo bảng st.data_editor cho các schedule 5 năm
    forecast_years = [company.historical_is[-1].year + i for i in range(1, 6)]

    if is_bank:
        schedule_data = {
            "Năm": forecast_years,
            "Tăng trưởng tín dụng (%)": [
                cg * 100.0 for cg in assumptions.credit_growth
            ],
            "Tăng trưởng tiền gửi (%)": [
                dg * 100.0 for dg in assumptions.deposit_growth
            ],
            "NIM (%)": [n * 100.0 for n in assumptions.nim],
            "CIR (%)": [c * 100.0 for c in assumptions.cir],
            "Credit Cost (%)": [cc * 100.0 for cc in assumptions.credit_cost],
        }
        df_schedule = pd.DataFrame(schedule_data).set_index("Năm")
        edited_schedule = st.data_editor(
            df_schedule,
            width="stretch",
            column_config={
                "Tăng trưởng tín dụng (%)": st.column_config.NumberColumn(
                    "Tăng trưởng tín dụng (%)",
                    help="Dự phóng tốc độ tăng trưởng cho vay khách hàng.",
                ),
                "Tăng trưởng tiền gửi (%)": st.column_config.NumberColumn(
                    "Tăng trưởng tiền gửi (%)",
                    help="Dự phóng tốc độ huy động vốn từ khách hàng.",
                ),
                "NIM (%)": st.column_config.NumberColumn(
                    "NIM (%)",
                    help="Biên lãi thuần (Net Interest Margin). Chênh lệch giữa lãi suất cho vay và lãi suất huy động.",
                ),
                "CIR (%)": st.column_config.NumberColumn(
                    "CIR (%)",
                    help="Tỷ lệ Chi phí trên Thu nhập (Cost to Income Ratio). Càng thấp càng hiệu quả.",
                ),
                "Credit Cost (%)": st.column_config.NumberColumn(
                    "Credit Cost (%)",
                    help="Chi phí tín dụng (Trích lập dự phòng rủi ro / Tổng dư nợ).",
                ),
            },
        )

        # Lưu lại
        assumptions.credit_growth = [
            float(val) / 100.0 for val in edited_schedule["Tăng trưởng tín dụng (%)"]
        ]
        assumptions.deposit_growth = [
            float(val) / 100.0 for val in edited_schedule["Tăng trưởng tiền gửi (%)"]
        ]
        assumptions.nim = [float(val) / 100.0 for val in edited_schedule["NIM (%)"]]
        assumptions.cir = [float(val) / 100.0 for val in edited_schedule["CIR (%)"]]
        assumptions.credit_cost = [
            float(val) / 100.0 for val in edited_schedule["Credit Cost (%)"]
        ]
    else:
        schedule_data = {
            "Năm": forecast_years,
            "Tăng trưởng Doanh thu (%)": [
                g * 100.0 for g in assumptions.revenue_growth
            ],
            "Biên EBIT (%)": [m * 100.0 for m in assumptions.ebit_margin],
            "CapEx / Doanh thu (%)": [c * 100.0 for c in assumptions.capex_to_revenue],
            "Khấu hao / Doanh thu (%)": [
                d * 100.0 for d in assumptions.depr_to_revenue
            ],
            "DSO (Phải thu - ngày)": [nw for nw in assumptions.dso],
            "DIO (Tồn kho - ngày)": [nw for nw in assumptions.dio],
            "DPO (Phải trả - ngày)": [nw for nw in assumptions.dpo],
            "Lãi suất vay (%)": [nw * 100.0 for nw in assumptions.interest_rate],
            "Tỷ lệ trả nợ (%)": [r * 100.0 for r in assumptions.debt_repayment_rate],
            "Vay mới / Doanh thu (%)": [
                b * 100.0 for b in assumptions.new_borrowing_rate
            ],
        }
        df_schedule = pd.DataFrame(schedule_data).set_index("Năm")
        edited_schedule = st.data_editor(
            df_schedule,
            width="stretch",
            column_config={
                "Tăng trưởng Doanh thu (%)": st.column_config.NumberColumn(
                    "Tăng trưởng Doanh thu (%)",
                    help="Dự phóng tốc độ tăng trưởng doanh thu cốt lõi hàng năm.",
                ),
                "Biên EBIT (%)": st.column_config.NumberColumn(
                    "Biên EBIT (%)",
                    help="Biên lợi nhuận hoạt động (Lợi nhuận trước lãi vay và thuế). Đo lường hiệu quả cốt lõi.",
                ),
                "CapEx / Doanh thu (%)": st.column_config.NumberColumn(
                    "CapEx / Doanh thu (%)",
                    help="Tỷ lệ chi tiêu vốn đầu tư (mua sắm tài sản) trên doanh thu. Cao nghĩa là đang mở rộng mạnh.",
                ),
                "Khấu hao / Doanh thu (%)": st.column_config.NumberColumn(
                    "Khấu hao / Doanh thu (%)",
                    help="Tỷ lệ chi phí khấu hao trên doanh thu.",
                ),
                "DSO (Phải thu - ngày)": st.column_config.NumberColumn(
                    "DSO (Phải thu - ngày)",
                    help="Số ngày bình quân thu tiền khách hàng. Càng thấp càng tốt.",
                ),
                "DIO (Tồn kho - ngày)": st.column_config.NumberColumn(
                    "DIO (Tồn kho - ngày)",
                    help="Số ngày bình quân vòng quay hàng tồn kho. Càng thấp bán hàng càng nhanh.",
                ),
                "DPO (Phải trả - ngày)": st.column_config.NumberColumn(
                    "DPO (Phải trả - ngày)",
                    help="Số ngày bình quân trả tiền nhà cung cấp. Càng cao càng chiếm dụng vốn tốt.",
                ),
            },
        )

        # Lưu lại
        assumptions.revenue_growth = [
            float(val) / 100.0 for val in edited_schedule["Tăng trưởng Doanh thu (%)"]
        ]
        assumptions.ebit_margin = [
            float(val) / 100.0 for val in edited_schedule["Biên EBIT (%)"]
        ]
        assumptions.capex_to_revenue = [
            float(val) / 100.0 for val in edited_schedule["CapEx / Doanh thu (%)"]
        ]
        assumptions.depr_to_revenue = [
            float(val) / 100.0 for val in edited_schedule["Khấu hao / Doanh thu (%)"]
        ]
        assumptions.dso = [
            float(val) for val in edited_schedule["DSO (Phải thu - ngày)"]
        ]
        assumptions.dio = [
            float(val) for val in edited_schedule["DIO (Tồn kho - ngày)"]
        ]
        assumptions.dpo = [
            float(val) for val in edited_schedule["DPO (Phải trả - ngày)"]
        ]
        assumptions.interest_rate = [
            float(val) / 100.0 for val in edited_schedule["Lãi suất vay (%)"]
        ]
        assumptions.debt_repayment_rate = [
            float(val) / 100.0 for val in edited_schedule["Tỷ lệ trả nợ (%)"]
        ]
        assumptions.new_borrowing_rate = [
            float(val) / 100.0 for val in edited_schedule["Vay mới / Doanh thu (%)"]
        ]

    st.subheader("3. Tham số vĩnh viễn & Pha trộn")
    from valuation.engine.router import ValuationRouter

    route = ValuationRouter().get_routing(company.ticker)
    primary_method = route.get("primary", "FCFF" if not is_bank else "RI")
    secondary_method = route.get("secondary", "P/E" if not is_bank else "P/B")

    col6, col7, col8 = st.columns(3)
    with col6:
        g = st.number_input(
            "Tăng trưởng vĩnh viễn (g):",
            value=float(assumptions.terminal_growth_rate),
            min_value=-0.05,
            max_value=0.10,
            step=0.001,
            format="%.4f",
            help="Tốc độ tăng trưởng dài hạn mãi mãi sau 5 năm dự phóng. Khuyến nghị <= tốc độ tăng trưởng GDP.",
        )
        assumptions.terminal_growth_rate = g
    with col7:
        if is_bank:
            sus_roe = st.number_input(
                "ROE bền vững vĩnh viễn:",
                value=float(assumptions.sustainable_roe or 0.18),
                min_value=0.01,
                max_value=0.50,
                step=0.01,
                format="%.2f",
                help="Mức Lợi nhuận trên Vốn chủ sở hữu duy trì trong dài hạn ở giai đoạn bão hòa.",
            )
            assumptions.sustainable_roe = sus_roe
        else:
            ev_ebitda = st.number_input(
                "Bội số EV/EBITDA mục tiêu:",
                value=float(assumptions.target_ev_ebitda),
                min_value=1.0,
                max_value=30.0,
                step=0.5,
                format="%.1f",
                help="Dùng cho phương pháp định giá Tương đối so sánh (Relative Valuation) ở cuối kỳ dự phóng.",
            )
            assumptions.target_ev_ebitda = ev_ebitda
    with col8:
        if is_bank:
            weight_ri = st.number_input(
                f"Tỷ trọng phương pháp {primary_method}:",
                value=float(assumptions.weight_ri),
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                format="%.2f",
                help="Tỷ trọng áp dụng cho phương pháp định giá Tuyệt đối. Phần còn lại sẽ dành cho phương pháp Tương đối.",
            )
            assumptions.weight_ri = weight_ri
            st.caption(
                f"Tỷ trọng phương pháp {secondary_method}: {1.0 - weight_ri:.2f}"
            )
        else:
            weight_dcf = st.number_input(
                f"Tỷ trọng phương pháp {primary_method}:",
                value=float(assumptions.weight_dcf),
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                format="%.2f",
                help="Tỷ trọng áp dụng cho phương pháp định giá Tuyệt đối. Phần còn lại sẽ dành cho phương pháp Tương đối.",
            )
            assumptions.weight_dcf = weight_dcf
            st.caption(
                f"Tỷ trọng phương pháp {secondary_method}: {1.0 - weight_dcf:.2f}"
            )

    if is_bank:
        payout = st.slider(
            "Tỷ lệ chi trả cổ tức (Dividend Payout Ratio):",
            0.0,
            1.0,
            float(assumptions.dividend_payout_ratio),
            step=0.05,
        )
        assumptions.dividend_payout_ratio = payout

    if primary_method in ["RNAV", "SOTP"]:
        st.subheader("4. Tham số Khối Dự án & Trợ lý AI Bóc tách")

        col_rnav1, col_rnav2 = st.columns(2)
        with col_rnav1:
            if primary_method == "RNAV":
                rnav_wacc = st.number_input(
                    "WACC áp dụng cho dòng tiền dự án (RNAV):",
                    value=float(assumptions.rnav_wacc),
                    min_value=0.01,
                    max_value=0.30,
                    step=0.01,
                    format="%.4f",
                )
                assumptions.rnav_wacc = rnav_wacc
        with col_rnav2:
            if primary_method == "RNAV":
                rnav_discount = st.number_input(
                    "Tỷ lệ chiết khấu Tập đoàn (RNAV Discount):",
                    value=float(assumptions.rnav_discount),
                    min_value=0.0,
                    max_value=0.80,
                    step=0.05,
                    format="%.2f",
                )
                assumptions.rnav_discount = rnav_discount
            else:
                sotp_discount = st.number_input(
                    "Tỷ lệ chiết khấu Holding (SOTP Discount):",
                    value=float(assumptions.sotp_discount),
                    min_value=0.0,
                    max_value=0.80,
                    step=0.05,
                    format="%.2f",
                )
                assumptions.sotp_discount = sotp_discount

        st.info(
            "Paste nội dung Báo cáo phân tích (hoặc Thuyết minh BCTC) vào đây để AI tự động trích xuất danh sách dự án / mảng kinh doanh."
        )

        context_text = st.text_area("Nội dung Báo cáo:", height=150)

        if st.button("Chạy AI Bóc tách", width="stretch"):
            if not context_text.strip():
                st.warning("Vui lòng nhập nội dung báo cáo!")
            else:
                with st.spinner("AI đang đọc và bóc tách dữ liệu..."):
                    if primary_method == "RNAV":
                        from valuation.engine.ai_extractor import extract_rnav_projects

                        result = extract_rnav_projects(company.ticker, context_text)
                        if "error" in result:
                            st.error(f"Lỗi AI: {result['error']}")
                        else:
                            st.session_state[f"ai_rnav_projects_{company.ticker}"] = (
                                result.get("projects", [])
                            )
                            # Dữ liệu mới → phải đối chiếu lại trước khi phát hành.
                            st.session_state[f"ai_inputs_verified_{company.ticker}"] = False
                            st.success(
                                "Bóc tách thành công! Vui lòng kiểm tra bảng bên dưới."
                            )
                    else:  # SOTP
                        from valuation.engine.ai_extractor import extract_sotp_segments

                        result = extract_sotp_segments(company.ticker, context_text)
                        if "error" in result:
                            st.error(f"Lỗi AI: {result['error']}")
                        else:
                            st.session_state[f"ai_sotp_segments_{company.ticker}"] = (
                                result.get("segments", [])
                            )
                            # Dữ liệu mới → phải đối chiếu lại trước khi phát hành.
                            st.session_state[f"ai_inputs_verified_{company.ticker}"] = False
                            st.success(
                                "Bóc tách thành công! Vui lòng kiểm tra bảng bên dưới."
                            )

        # Hiển thị bảng để edit
        if primary_method == "RNAV":
            current_projects = st.session_state.get(
                f"ai_rnav_projects_{company.ticker}",
                getattr(assumptions, "rnav_projects", []),
            )
            if current_projects:
                st.write("**Danh sách Dự án (Có thể chỉnh sửa):**")
                df_proj = pd.DataFrame(current_projects)
                edited_proj = st.data_editor(
                    df_proj, num_rows="dynamic", width="stretch"
                )
                assumptions.rnav_projects = edited_proj.to_dict("records")
        else:  # SOTP
            current_segments = st.session_state.get(
                f"ai_sotp_segments_{company.ticker}",
                getattr(assumptions, "sotp_segments", []),
            )
            if current_segments:
                st.write("**Danh sách Mảng kinh doanh (Có thể chỉnh sửa):**")
                df_seg = pd.DataFrame(current_segments)
                edited_seg = st.data_editor(df_seg, num_rows="dynamic", width="stretch")
                assumptions.sotp_segments = edited_seg.to_dict("records")

        if getattr(assumptions, "rnav_projects", None) or getattr(assumptions, "sotp_segments", None):
            # Số do LLM bóc tách chưa được phát hành nếu chưa có người đối chiếu (luật vàng #1).
            assumptions.ai_inputs_verified = st.checkbox(
                "Tôi đã đối chiếu từng dự án/mảng ở trên với BCTC/báo cáo thường niên/CBTT",
                value=bool(getattr(assumptions, "ai_inputs_verified", False)),
                key=f"ai_inputs_verified_{company.ticker}",
            )

    if not is_bank:
        st.subheader("5. Quỹ đất chưa phản ánh trong BCTC (Land Bank Add-on)")
        st.info(
            "Áp dụng cho DN nông nghiệp/cao su/KCN có quỹ đất ghi nhận theo giá gốc "
            "(thấp hơn nhiều giá đền bù/chuyển đổi thực tế). Giá trị quỹ đất được "
            "**cộng thêm** vào giá mục tiêu, không thay đổi phương pháp định giá chính. "
            "⚠️ Vui lòng tự nhập diện tích/giá đền bù từ báo cáo thật — hệ thống KHÔNG tự đoán số liệu."
        )
        land_projects = getattr(assumptions, "land_bank_projects", []) or []
        df_land = (
            pd.DataFrame(
                land_projects,
                columns=[
                    "ten",
                    "dien_tich_ha",
                    "gia_boi_thuong_vnd_m2",
                    "ty_le_so_huu",
                    "nam_thu_tien",
                ],
            )
            if land_projects
            else pd.DataFrame(
                columns=[
                    "ten",
                    "dien_tich_ha",
                    "gia_boi_thuong_vnd_m2",
                    "ty_le_so_huu",
                    "nam_thu_tien",
                ]
            )
        )
        edited_land = st.data_editor(
            df_land,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "ten": "Tên khu đất/dự án",
                "dien_tich_ha": st.column_config.NumberColumn(
                    "Diện tích (ha)", min_value=0.0
                ),
                "gia_boi_thuong_vnd_m2": st.column_config.NumberColumn(
                    "Giá đền bù dự kiến (VND/m2)", min_value=0.0
                ),
                "ty_le_so_huu": st.column_config.NumberColumn(
                    "Tỷ lệ sở hữu (%)", min_value=0.0, max_value=100.0
                ),
                "nam_thu_tien": st.column_config.NumberColumn(
                    "Năm dự kiến thu tiền", min_value=2024, max_value=2050, step=1
                ),
            },
            key=f"land_bank_editor_{company.ticker}",
        )
        assumptions.land_bank_projects = edited_land.dropna(how="all").to_dict(
            "records"
        )
