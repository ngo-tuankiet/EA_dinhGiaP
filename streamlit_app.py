"""
Streamlit App Entrypoint — Giao diện phân tích và định giá tự động VN100.
Đặt trực tiếp tại thư mục gốc của dự án.
"""

import os
import sys
import traceback
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from valuation.views.theme import (
    render_app_theme,
    render_shell_header,
    render_summary_banner,
)

_APP_HANDLED_EXCEPTIONS = (
    SQLAlchemyError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
)

# Thêm đường dẫn dự án vào PYTHONPATH để import đồng bộ
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load biến môi trường từ .env
# Ưu tiên .env ở thư mục chạy exe (cwd) trước, sau đó mới dùng .env đóng gói kèm
env_cwd = os.path.join(os.getcwd(), ".env")
env_bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_cwd):
    load_dotenv(env_cwd)
else:
    load_dotenv(env_bundled)

# Cấu hình giao diện Streamlit (Premium Styling)
st.set_page_config(
    page_title="VN100 Valuation - Hệ thống định giá tự động chuẩn quỹ",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="auto",
)

render_app_theme()


# 1. Cấu hình DB engine cache để tránh cạn kiệt connection pool
@st.cache_resource
def get_db_engines():
    # Máy mới/VPS: giải nén vn100_full.db.gz TRƯỚC khi create_all bên dưới tạo DB rỗng — DB rỗng làm
    # ensure_portable_db tưởng đã có dữ liệu và không giải nén nữa (app chạy với kho trống).
    portable_db = Path(__file__).resolve().parent / "vn100_full.db"
    if not portable_db.exists() and portable_db.with_suffix(".db.gz").exists():
        from scripts.ensure_portable_db import ensure_portable_db

        ensure_portable_db()

    db_url_read = os.getenv("DATABASE_URL_READONLY") or "sqlite:///vn100_full.db"
    db_url_write = os.getenv("DATABASE_URL_WRITE") or "sqlite:///vn100_full.db"

    _pool_kwargs = {"pool_pre_ping": True}
    if "sqlite" in db_url_read:
        _pool_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        _pool_kwargs.update(
            {
                "pool_recycle": 1800,
                "pool_size": 5,
                "max_overflow": 5,
                "pool_timeout": 30,
            }
        )

    try:
        engine_read = create_engine(db_url_read, **_pool_kwargs)
        engine_write = create_engine(db_url_write, **_pool_kwargs)
        # Test connection
        with engine_read.connect():
            pass
    except _APP_HANDLED_EXCEPTIONS:
        # Fallback sang SQLite nếu PostgreSQL local không hoạt động
        sqlite_url = "sqlite:///vn100_full.db"
        engine_read = create_engine(
            sqlite_url, connect_args={"check_same_thread": False}
        )
        engine_write = create_engine(
            sqlite_url, connect_args={"check_same_thread": False}
        )

    # Tự động khởi tạo schema nếu dùng SQLite
    if "sqlite" in str(engine_write.url):
        from valuation.db.models import Base

        Base.metadata.create_all(bind=engine_write)

    return engine_read, engine_write


engine_read, engine_write = get_db_engines()
SessionRead = sessionmaker(bind=engine_read)
SessionWrite = sessionmaker(bind=engine_write)


@st.cache_data(ttl=300)
def fetch_live_price_cached(ticker: str) -> float:
    """Lấy giá live từ vnstock với cache 5 phút để không bị lag UI"""
    if os.getenv("ENABLE_LIVE_PRICE", "").lower() not in {"1", "true", "yes", "on"}:
        return 0.0

    from valuation.ingest.vnstock_client import vnstock_client

    try:
        return vnstock_client.get_live_price(ticker)
    except _APP_HANDLED_EXCEPTIONS:
        return 0.0


# 2. Main app flow
render_shell_header()

# Mở session DB ngắn cho mỗi lượt rerun
db_read = SessionRead()
db_write = SessionWrite()

try:
    # Import các view
    from valuation.views.input_assumptions import render_input_assumptions
    from valuation.views.input_financials import render_input_financials
    from valuation.views.results import render_valuation_results
    from valuation.views.select_ticker import render_select_ticker

    # Freshness check on startup. Không tự chạy ingest khi mở app: bản portable
    # trong Drive phải ưu tiên xem dữ liệu đã lưu, tránh spam API/rate-limit và
    # tránh ghi DB ngoài ý muốn.
    if "auto_weekly_check_done" not in st.session_state:
        from valuation.data_access.freshness_checker import (
            check_data_freshness,
            describe_data_freshness,
        )

        freshness_status = check_data_freshness(db_read, threshold_days=7)
        if freshness_status.is_stale:
            freshness_headline, freshness_details = describe_data_freshness(
                freshness_status
            )
            st.info(
                f"**{freshness_headline}.** {freshness_details} "
                "Dùng nút cập nhật ở thanh bên (điện thoại: nút « Chọn mã · Vĩ mô ») khi cần.",
                icon="⚠️",
            )
        st.session_state["auto_weekly_check_done"] = True

    # Render sidebar
    render_select_ticker(db_read, db_write)

    # Render các tab chính
    if "company" in st.session_state:
        company = st.session_state["company"]

        # Cập nhật giá live liên tục mỗi lần rerun để tránh kẹt cache giá cũ
        # Gọi qua cache 5 phút để tránh bị lag UI (do call API vnstock quá nhiều)
        live_p = fetch_live_price_cached(company.ticker)
        if live_p == 0:
            from valuation.data_access.repo import get_latest_price

            live_p = get_latest_price(db_read, company.ticker, fetch_live=False)

        if live_p > 0:
            company.current_price = live_p
            st.session_state["company"] = company

        # Đảm bảo projections được khởi tạo và đồng bộ
        from valuation.models.financials_bank import CompanyBank

        is_bank = isinstance(company, CompanyBank)
        base_year_mode = st.session_state.get("current_mode", "TTM")

        # 1. Khởi tạo projections nếu chưa có
        if (
            "projections" not in st.session_state
            or st.session_state.get("projections_ticker") != company.ticker
            or st.session_state.get("projections_mode") != base_year_mode
        ):
            from valuation.engine.forecast import forecast_company_financials
            from valuation.engine.forecast_bank import forecast_bank_financials

            if is_bank:
                st.session_state["projections"] = forecast_bank_financials(company)
            else:
                st.session_state["projections"] = forecast_company_financials(company)
            st.session_state["projections_ticker"] = company.ticker
            st.session_state["projections_mode"] = base_year_mode
            st.session_state["last_assumptions"] = company.assumptions.model_dump()

        # 2. Định giá real-time cho Summary Banner (áp dụng kịch bản và ghi đè của analyst)
        from valuation.engine.blend import blend_intrinsic_relative
        from valuation.engine.forecast import forecast_company_financials
        from valuation.engine.forecast_bank import forecast_bank_financials
        from valuation.engine.sensitivity import (
            apply_scenario_adjustments,
        )

        analyst_scenario = st.session_state.get("analyst_scenario", "Base")
        scenario_company = apply_scenario_adjustments(company, analyst_scenario)

        # Tạo projections động cho kịch bản
        if is_bank:
            scenario_projections = forecast_bank_financials(scenario_company)
        else:
            scenario_projections = forecast_company_financials(scenario_company)

        # Engine DUY NHẤT: dùng cùng lõi valuate() với CLI/batch/Sheets & tab Kết quả.
        # Base dùng projections trong session (có thể đã chỉnh tay); kịch bản khác forecast lại.
        from valuation.engine.valuate import valuate

        _proj = (
            st.session_state.get("projections")
            if analyst_scenario == "Base"
            else scenario_projections
        )
        # Vĩ mô cập nhật MỖI LẦN QUÉT: ưu tiên analyst chỉnh tay (session_state),
        # mặc định tự dựng từ macro_series trong DB (CPI/TPCP_10Y/POLICY_RATE).
        macro_env = st.session_state.get("macro_env")
        if macro_env is None:
            from valuation.models.macro_env import MacroEnvironment

            macro_env = MacroEnvironment.from_db(db_read)
        _res = valuate(scenario_company, projections=_proj, macro_env=macro_env)
        int_fv = _res["intrinsic_fv"]
        rel_fv = _res["relative_fv"]
        weight_intrinsic = _res["weight_intrinsic"]

        # Ghi đè chủ quan (chỉ khi analyst nhập > 0)
        pb_override = st.session_state.get("analyst_pb_override", 0.0)
        pe_override = st.session_state.get("analyst_pe_override", 0.0)
        has_override = (is_bank and pb_override > 0.0) or (
            (not is_bank) and pe_override > 0.0
        )
        if is_bank and pb_override > 0.0:
            eq_yr1 = (
                scenario_projections[0]["total_equity"]
                if analyst_scenario != "Base"
                else st.session_state["projections"][0]["total_equity"]
            )
            shares = scenario_company.shares_outstanding
            rel_fv = (pb_override * eq_yr1 / shares) * 1000.0 if shares > 0 else rel_fv
        elif (not is_bank) and pe_override > 0.0:
            target_projections = (
                st.session_state["projections"]
                if analyst_scenario == "Base"
                else scenario_projections
            )
            eps_yr1 = (
                target_projections[0].get("net_income", 0.0)
                / scenario_company.shares_outstanding
                if scenario_company.shares_outstanding > 0
                else 0.0
            )
            rel_fv = pe_override * eps_yr1 * 1000.0

        # Bank: int/rel là 2 chân thực → blend (cho phép override). Phi tài chính: valuate
        # đã blend sẵn → dùng thẳng; chỉ blend lại khi có P/E override.
        # Tính toán Fair Value
        if is_bank or has_override:
            blended_fv, upside = blend_intrinsic_relative(
                int_fv, rel_fv, weight_intrinsic, scenario_company.current_price
            )
            from valuation.engine.decision_engine import recommend

            decision = recommend(
                scenario_company.ticker, scenario_company.current_price, blended_fv,
                governance=scenario_company.governance, macro_env=macro_env,
                not_rated=bool(_res.get("not_rated")),
            )
            rec = decision["recommendation"]
        else:
            blended_fv, upside, rec = (
                _res["blended_fair_value_per_share"],
                _res["upside"],
                _res["recommendation"],
            )
            decision = _res.get("decision", {})

        # Ghi đè của analyst không được bỏ qua lỗi đầu vào trọng yếu.
        if not _res.get("publication_allowed", True):
            rec = "NOT_RATED"

        # Hiển thị các cảnh báo Model Integrity (nếu có)
        if scenario_company.warnings:
            st.warning("⚠️ **Cảnh báo tính toàn vẹn mô hình (Model Integrity):**")
            for warn in scenario_company.warnings:
                st.error(f"- {warn}")

        # 3. Hiển thị Summary Banner (Premium Styling)
        # NOT_RATED phải TRUNG TÍNH (xám), không tô đỏ: "chưa đủ cơ sở định giá"
        # hoàn toàn khác "khuyến nghị bán" — tô đỏ sẽ khiến người đọc hiểu nhầm
        # thành tín hiệu tiêu cực (D28).
        if rec == "NOT_RATED":
            rec_color, bg_color, text_color = "#64748B", "#F8FAFC", "#334155"
        elif rec == "BUY":
            rec_color, bg_color, text_color = "#00B74F", "#F1FBF5", "#00843D"
        elif rec in ["HOLD", "TRIM"]:
            rec_color, bg_color, text_color = "#F59E0B", "#FFFBEB", "#92400E"
        else:
            rec_color, bg_color, text_color = "#EF4444", "#FEF2F2", "#991B1B"

        # Với NOT_RATED, KHÔNG hiển thị giá mục tiêu và upside — đó chính là con
        # số hệ thống vừa tuyên bố là không đáng tin. Hiện nó ra rồi dán nhãn
        # "không định giá được" là tự mâu thuẫn, và người đọc sẽ nhớ con số.
        if rec == "NOT_RATED":
            _headline = "CHƯA ĐỦ CƠ SỞ ĐỊNH GIÁ"
            _right = (
                "<div class='ag-summary-upside' style='font-size:18px;color:#64748B;'>"
                "Không công bố giá mục tiêu</div>"
            )
        else:
            from valuation.engine.decision_engine import REC_LABELS_VI

            _headline = f"{REC_LABELS_VI.get(rec, rec)} · Giá mục tiêu {blended_fv:,.0f} VND"
            _right = (
                f"<div class='ag-summary-upside'>So với thị giá: {upside:+.1f}%</div>"
            )

        render_summary_banner(
            ticker=scenario_company.ticker,
            sector=scenario_company.sector,
            headline=_headline,
            current_price=scenario_company.current_price,
            right_html=_right,
            accent_color=rec_color,
            bg_color=bg_color,
            text_color=text_color,
        )
        if rec == "NOT_RATED":
            st.warning(
                "Chưa công bố giá mục tiêu: dữ liệu đầu vào chưa đạt kiểm tra "
                "hoặc mô hình còn thiếu dữ liệu chuyên ngành.",
                icon="🚫",
            )
            for issue in _res.get("data_checks", []):
                if issue["severity"] == "error":
                    st.error(issue["message"])

        # Hard Gates & Governance Section
        violations = decision.get("hard_gates_violations", [])
        if violations:
            st.error("🚨 **HARD GATES BỊ VI PHẠM (Chỉ định: HARD REJECT)**")
            for v in violations:
                st.markdown(f"- {v}")
        else:
            st.success(
                "✅ **Governance Check Passed** (Không phát hiện cờ rủi ro Hard Gates)"
            )

        st.markdown(
            f"**Margin of Safety (MOS) Mục tiêu cho {decision.get('business_nature', 'Unknown')}:** {decision.get('target_mos', 0)*100:.0f}%"
        )

        # Cờ định giá (giải thích TẠI SAO kết quả bất thường — vd Giá MT = 0,
        # upside -100% — thay vì để người dùng tưởng nhầm là lỗi hệ thống).
        from valuation.engine.flag_descriptions import describe_flags

        valuation_flags = describe_flags(_res.get("flags", []))
        if valuation_flags:
            st.markdown("**Cờ định giá (Valuation Flags):**")
            for vf in valuation_flags:
                text = f"`{vf['code']}` — {vf['message']}"
                if vf["level"] == "error":
                    st.error(text, icon="🚨")
                elif vf["level"] == "warning":
                    st.warning(text, icon="⚠️")
                else:
                    st.info(text, icon="ℹ️")

        from valuation.config import load_defaults
        from valuation.data_access.corporate_actions import (
            should_refresh_corporate_actions,
        )
        from valuation.ingest.corporate_actions_background import (
            schedule_corporate_actions_refresh,
        )
        from valuation.views.corporate_actions import render_corporate_actions

        # Dữ liệu đã lưu hiển thị ngay; kiểm tra nguồn mới chạy nền và không chặn UI.
        # Nhiều Streamlit rerun của cùng mã dùng chung một Future nên không tải trùng.
        _corporate_cfg = load_defaults().get("corporate_actions") or {}
        if should_refresh_corporate_actions(
            db_write,
            company.ticker,
            ttl_hours=int(_corporate_cfg.get("refresh_ttl_hours", 24)),
            error_retry_minutes=int(_corporate_cfg.get("error_retry_minutes", 30)),
        ):
            corporate_refresh = schedule_corporate_actions_refresh(company.ticker)
        else:
            corporate_refresh = {
                "status": "FRESH",
                "checked": False,
                "inserted": 0,
                "updated": 0,
            }

        (
            financials_tab,
            valuation_tab,
            consensus_tab,
            corporate_actions_tab,
            ranking_tab,
        ) = st.tabs(
            [
                "Báo cáo tài chính",
                "Định giá & dự phóng",
                "So sánh CTCK",
                "Cổ tức & quyền mua",
                "VN100 & tích sản",
            ]
        )

        with financials_tab:
            render_input_financials(
                company,
                blended_fv=blended_fv,
                upside=upside,
                rec=rec,
                db=db_write,
                corporate_actions_context=None,
            )

        with valuation_tab, st.expander("Giả định & tham số dự phóng", expanded=False):
            render_input_assumptions(company)

        with consensus_tab:
            from valuation.views.consensus_compare import render_consensus_compare

            if _res.get("publication_allowed", True):
                render_consensus_compare(company, blended_fv, db_write)
            else:
                st.warning(
                    "Chưa so sánh giá mục tiêu khi dữ liệu định giá còn lỗi trọng yếu."
                )

        with corporate_actions_tab:
            render_corporate_actions(
                company,
                db_write,
                refresh_result=corporate_refresh,
            )

        with ranking_tab:
            from valuation.views.vn100_ranking import render_vn100_ranking

            render_vn100_ranking()

        # Tab kết quả có phần chuẩn bị biểu đồ/xuất báo cáo tĩnh khá nặng, nên
        # render sau hai tab tham chiếu để người dùng mở tab CTCK/cổ tức nhanh hơn.
        with valuation_tab:
            render_valuation_results(company, db_write)
    else:
        st.info(
            "Chọn mã ở thanh bên (điện thoại: nút « Chọn mã · Vĩ mô » góc trên trái) rồi nhấn **'Nạp lại mô hình đã lưu'** để bắt đầu phân tích định giá.",
            icon="ℹ️",
        )
        from valuation.views.vn100_ranking import render_vn100_ranking

        with st.tabs(["VN100 & tích sản"])[0]:
            render_vn100_ranking()

except _APP_HANDLED_EXCEPTIONS as e:
    st.error(f"Đã xảy ra lỗi hệ thống: {e}")

    st.code(traceback.format_exc())
    with open("streamlit_crash.log", "w", encoding="utf-8") as f:
        f.write(traceback.format_exc())

finally:
    # Luôn đóng session DB đúng cách
    db_read.close()
    db_write.close()
