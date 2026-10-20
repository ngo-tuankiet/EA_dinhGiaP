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
        assert isinstance(company, Company)  # thu hẹp kiểu cho mypy (is_bank đã xác định)
        assumptions = company.assumptions
        col4, col5, col5b = st.columns(3)
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
                help="Thuế hiệu dụng giai đoạn dự phóng (năm 1–5, gồm ưu đãi có thời hạn) — áp cho NOPAT/LN "
                "các năm dự phóng; giá trị vĩnh viễn dùng ô thuế terminal bên cạnh.",
            )
        assumptions.cost_of_debt = cod
        assumptions.tax_rate = tax
        with col5b:
            from valuation.engine.wacc import marginal_tax_rate

            # Mặc định theo config: thuế biên (sector_tax_rates.default) hoặc thuế hiệu dụng nếu terminal_tax_mode
            # = effective. Giữ None khi analyst không đổi để config đổi thì mặc định đổi theo (như rnav_wacc).
            term_default = marginal_tax_rate(None, tax)
            term_shown = (
                assumptions.terminal_tax_rate
                if assumptions.terminal_tax_rate is not None
                else term_default
            )
            term_tax = st.number_input(
                "Thuế terminal (vĩnh viễn):",
                value=float(term_shown),
                min_value=0.0,
                max_value=0.50,
                step=0.01,
                format="%.2f",
                help="Thuế suất biên cho NOPAT vĩnh viễn sau năm 5 và lá chắn thuế nợ trong WACC (Damodaran). "
                "Mặc định thuế TNDN phổ thông; chỉ nhập mức ưu đãi khi ưu đãi KHÔNG có thời hạn theo luật.",
            )
        if (
            assumptions.terminal_tax_rate is not None
            or abs(term_tax - term_default) > 5e-5
        ):
            assumptions.terminal_tax_rate = term_tax

        # Cập nhật WACC ước lượng ở cấu trúc vốn hiện tại
        E = company.historical_bs[-1].total_equity
        D = (
            company.historical_bs[-1].short_term_debt
            + company.historical_bs[-1].long_term_debt
        )
        from valuation.engine.wacc import compute_wacc, wacc_tax_rate

        wacc_est = compute_wacc(coe, cod, E, D, wacc_tax_rate(assumptions))
        st.markdown(f"**Ước lượng WACC (ở cấu trúc vốn lịch sử):** `{wacc_est:.2%}`")

    st.subheader("2. Giả định dự phóng 5 năm tiếp theo")

    # Tạo bảng st.data_editor cho các schedule 5 năm
    forecast_years = [company.historical_is[-1].year + i for i in range(1, 6)]

    if is_bank:
        assert isinstance(company, CompanyBank)  # thu hẹp kiểu cho mypy (is_bank đã xác định)
        if company.assumptions.driver_base is None:
            # Ảnh chụp driver gốc (repo đã đặt khi dựng; thiếu thì chụp trước khi analyst sửa) — forecast_bank
            # tính dòng cân phai ROE từ driver gốc và cộng phần analyst sửa vào LN (r4a).
            company.assumptions.driver_base = {
                k: list(getattr(company.assumptions, k))
                for k in ("credit_growth", "nim", "cir", "credit_cost")
            }
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

        # Năm chuyển tiếp: LN phai về ROE terminal bằng dòng cân tính từ driver gốc; phần analyst sửa driver cộng
        # thẳng vào LN (forecast_bank) nên mọi ô driver đều có tác dụng, đúng dấu (AGENTS §7).
        from valuation.engine.forecast_bank import (
            fade_plug_share,
            forecast_bank_financials,
        )

        _share = fade_plug_share(
            forecast_bank_financials(company), assumptions.tax_rate
        )
        if _share:
            st.caption(
                f"LN năm {forecast_years[-1]}: {_share:.0%} do dòng cân phai ROE về ROE terminal (tính từ "
                "driver gốc; phần driver bạn sửa được cộng thêm vào LN)."
            )
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
                "ROE bền vững riêng (năm 5):",
                value=float(assumptions.sustainable_roe or 0.18),
                min_value=0.01,
                max_value=0.50,
                step=0.01,
                format="%.2f",
                help="ROE năm 5 của dự phóng chuẩn hóa. ROE terminal = mức này hội tụ về ROE ngành theo λ (bên dưới).",
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
        # ROE terminal = ROE bền vững + λ·(ROE ngành − ROE bền vững) (Damodaran): máy đặt base case,
        # analyst chỉnh được đích và mức hội tụ (AGENTS §7).
        col_ind, col_lam = st.columns(2)
        with col_ind:
            if assumptions.industry_roe is not None:
                assumptions.industry_roe = st.number_input(
                    "ROE trung bình ngành (đích hội tụ):",
                    value=float(assumptions.industry_roe),
                    min_value=0.0,
                    max_value=0.50,
                    step=0.005,
                    format="%.4f",
                    help="Trung vị các NH cùng nhóm của ROE 3 năm tài chính gần nhất.",
                )
            else:
                st.caption("Nhóm ngành chưa đủ mã để tính ROE ngành — ROE terminal = ROE bền vững.")
        with col_lam:
            assumptions.roe_convergence = st.slider(
                "Mức hội tụ về ROE ngành (λ):",
                0.0,
                1.0,
                float(assumptions.roe_convergence),
                step=0.05,
                help="1 = ROE terminal bằng ROE ngành (chuẩn giai đoạn ổn định); 0 = giữ ROE riêng vĩnh viễn.",
            )

    if primary_method in ["RNAV", "SOTP"]:
        st.subheader("4. Tham số Khối Dự án & Trợ lý AI Bóc tách")

        col_rnav1, col_rnav2 = st.columns(2)
        with col_rnav1:
            if primary_method == "RNAV":
                from valuation.engine.models.rnav import default_project_rate

                # Mặc định theo config proxy_valuation.rnav_project_discount_rate (WACC: dòng tiền dự án chưa trừ nợ).
                coe = default_project_rate(company)
                rnav_wacc = st.number_input(
                    "Suất chiết khấu dòng tiền dự án (RNAV, mặc định = WACC — dòng tiền trước tài trợ):",
                    value=float(assumptions.rnav_wacc if assumptions.rnav_wacc is not None else coe),
                    min_value=0.01,
                    max_value=0.30,
                    step=0.01,
                    format="%.4f",
                )
                # Giữ None (= theo mặc định config) khi analyst không đổi, để WACC/COE đổi thì suất chiết khấu đổi theo.
                if assumptions.rnav_wacc is not None or abs(rnav_wacc - coe) > 5e-5:
                    assumptions.rnav_wacc = rnav_wacc
                assumptions.rnav_revaluation_premium = st.number_input(
                    "Premium đánh giá lại tồn kho + BĐS đầu tư (proxy RNAV):",
                    value=float(assumptions.rnav_revaluation_premium),
                    min_value=0.0,
                    max_value=2.0,
                    step=0.05,
                    format="%.2f",
                    help="Giả định nội bộ, chưa có nguồn (config proxy_valuation.rnav_land_premium); chỉ dùng "
                    "khi chưa nhập dự án. Thặng dư trừ thuế TNDN rồi mới trừ chiết khấu RNAV.",
                )
        with col_rnav2:
            if primary_method == "RNAV":
                rnav_discount = st.number_input(
                    "Chiết khấu phần đánh giá lại (RNAV Discount, không áp lên VCSH sổ sách):",
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
                if "gia_tri_so_sach_rong_ty" not in df_proj:
                    df_proj["gia_tri_so_sach_rong_ty"] = None
                st.caption(
                    "Bắt buộc mỗi dự án: diện tích sàn thương phẩm còn lại, giá bán, chi phí toàn bộ /m2, "
                    "ty_le_so_huu (%) và gia_tri_so_sach_rong_ty (tỷ đồng: tồn kho/XDCB/BĐS đầu tư của dự án − "
                    "tiền khách đã trả trước). Thiếu → quay về proxy (bị chặn công bố)."
                )
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
                for col in ("hop_nhat", "no_vay_rong_ty", "cdkks_ty"):
                    if col not in df_seg:
                        df_seg[col] = None
                st.caption(
                    "Mảng Equity: hop_nhat = True/False. Công ty con hợp nhất phải nhập no_vay_rong_ty (nợ vay ròng "
                    "100% của nó) và cdkks_ty (CĐKKS của nó, tỷ đồng) để không trừ nợ/CĐKKS hai lần."
                )
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
                    "gia_tri_so_sach_ty",
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
                    "gia_tri_so_sach_ty",
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
                "gia_tri_so_sach_ty": st.column_config.NumberColumn(
                    "Giá sổ đất trên BCĐKT (tỷ đồng, 0 nếu không ghi)", min_value=0.0
                ),
            },
            key=f"land_bank_editor_{company.ticker}",
        )
        assumptions.land_bank_projects = edited_land.dropna(how="all").to_dict(
            "records"
        )
