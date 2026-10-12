"""Giao diện xếp hạng toàn rổ, độc lập với phiên định giá từng mã."""

from __future__ import annotations

import io
from collections import Counter
from datetime import datetime
from itertools import chain
from math import isfinite

import pandas as pd
import streamlit as st

from valuation.analysis.investment_ranking import load_ranking_config
from valuation.services.investment_job import job_status, local_now, next_run, start_job
from valuation.services.ranking_store import STORE, latest_snapshot, read_json

SOFT_REASONS = {
    "Chưa kiểm chứng hồ sơ quản trị và lợi thế cạnh tranh",
    "Chưa có đối chiếu định giá được duyệt cho hồ sơ này",
    "Kỳ BCTC mới nhất chưa có ngày công bố được lưu; chưa xác minh độ mới",
    "Chưa đủ ngày công bố để kiểm chứng toàn bộ lịch sử",
}

HARD_REASON_PREFIXES = (
    "NOT_RATED",
    "NOT_RATEABLE",
    "VALUATION_PROXY",
    "PROXY_IMPLAUSIBLE",
    "UPSIDE_EXTREME_REVIEW",
    "DOWNSIDE_EXTREME_REVIEW",
    "NEGATIVE_EQUITY_VALUE",
    "SOURCE_CONFLICT",
    "MISSING_FINANCIAL_INPUT",
)

HARD_REASON_TEXT = {
    "Không đủ cơ sở định giá",
    "Giá trị hợp lý thiếu hoặc không dương.",
    "Chênh lệch định giá quá lớn, cần kiểm tra lại",
    "Thanh khoản thiếu dữ liệu hoặc dưới ngưỡng",
}


def _money(value: float | None) -> str:
    return f"{value:,.0f} đ" if value is not None else "Chưa đủ dữ liệu"


def _date_label(value: str) -> str:
    return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")


def selected_lists(snapshot: dict, profile: str) -> tuple[list[str], list[str]]:
    if snapshot["ai"]["status"] == "SUCCESS":
        rows = {row["ticker"]: row for row in snapshot["rows"]}
        picks = [r["ticker"] for r in snapshot["ai"]["review"][profile]["picks"]]
        return (
            [
                ticker
                for ticker in picks
                if rows[ticker]["profiles"][profile]["eligible"]
            ],
            [
                ticker
                for ticker in picks
                if not rows[ticker]["profiles"][profile]["eligible"]
            ],
        )
    selected = snapshot["selections"][profile]
    return selected["qualified"], [
        t for t in selected["research"] if t not in selected["qualified"]
    ]


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
    )


def _hard_reason(reason: str) -> bool:
    if reason in HARD_REASON_TEXT:
        return True
    if reason.startswith(HARD_REASON_PREFIXES):
        return True
    if (
        "chưa có đầy đủ lưu chuyển đầu tư/tài chính" in reason
    ):  # dòng cũ (trước 02/09/2026)
        return True
    if "Thiếu lưu chuyển đầu tư/tài chính" in reason:  # dòng gộp mới
        return True
    if "không tự tạo khoản bù" in reason:
        return True
    if "vượt ngưỡng đối chiếu" in reason:  # lệch đối chiếu Δtiền thật
        return True
    return "!=" in reason or " lệch " in reason


def _relaxed_limits(cfg: dict, profile: str) -> dict[str, float]:
    base = cfg["profiles"][profile]
    if profile == "defensive":
        return {
            "min_mos": max(0.15, base["min_mos"] - 0.10),
            "min_quality": max(60.0, base["min_quality"] - 5.0),
            "min_safety": max(60.0, base["min_safety"] - 5.0),
            "min_coverage": max(70.0, cfg["min_coverage"] - 10.0),
        }
    return {
        "min_mos": max(0.12, base["min_mos"] - 0.03),
        "min_quality": max(60.0, base["min_quality"] - 5.0),
        "min_safety": base["min_safety"],
        "min_coverage": max(60.0, cfg["min_coverage"] - 20.0),
    }


def _conditional_candidates(snapshot: dict, profile: str) -> list[dict]:
    """Danh sách tư vấn có điều kiện: nới nhẹ định lượng, không nới lỗi dữ liệu."""
    cfg = snapshot.get("config", load_ranking_config())
    limits = _relaxed_limits(cfg, profile)
    rows: list[dict] = []
    for row in snapshot["rows"]:
        score = row["profiles"][profile]
        components = score.get("components", {})
        reasons = score.get("reasons", [])
        if score.get("eligible") or not _finite_number(score.get("score")):
            continue
        if any(
            _hard_reason(check.get("message", "")) for check in row.get("checks", [])
        ):
            continue
        if not row.get("liquidity_ok"):
            continue
        if any(
            _hard_reason(reason) for reason in reasons if reason not in SOFT_REASONS
        ):
            continue
        if not _finite_number(row.get("mos")) or row["mos"] < limits["min_mos"]:
            continue
        if (
            not _finite_number(components.get("quality"))
            or components["quality"] < limits["min_quality"]
        ):
            continue
        if (
            not _finite_number(components.get("safety"))
            or components["safety"] < limits["min_safety"]
        ):
            continue
        if score.get("coverage", 0) < limits["min_coverage"]:
            continue
        rows.append(row)

    selected: list[dict] = []
    sector_count: dict[str, int] = {}
    max_picks = cfg.get("max_picks", 7)
    max_per_sector = cfg.get("max_per_sector", 2)
    for row in sorted(
        rows, key=lambda r: (-r["profiles"][profile]["score"], r["ticker"])
    ):
        sector = row.get("sector", "Chưa rõ")
        if sector_count.get(sector, 0) >= max_per_sector:
            continue
        selected.append(row)
        sector_count[sector] = sector_count.get(sector, 0) + 1
        if len(selected) >= max_picks:
            break
    return selected


def _reason_summary(snapshot: dict, profile: str) -> pd.DataFrame:
    counter: Counter[str] = Counter()
    for row in snapshot["rows"]:
        score = row["profiles"][profile]
        if not score["eligible"]:
            counter.update(score["reasons"])
    labels = {
        "Chưa kiểm chứng hồ sơ quản trị và lợi thế cạnh tranh": "Chưa có hồ sơ lợi thế cạnh tranh/quản trị",
        "Chưa có đối chiếu định giá được duyệt cho hồ sơ này": "Chưa có golden-test định giá",
        "Chưa đủ ngày công bố để kiểm chứng toàn bộ lịch sử": "Thiếu ngày công bố BCTC lịch sử",
        "Kỳ BCTC mới nhất chưa có ngày công bố được lưu; chưa xác minh độ mới": "Thiếu ngày công bố BCTC mới nhất",
        "Chưa đạt tiêu chí sức khỏe tài chính": "Sức khỏe tài chính chưa đạt",
        "Chưa đạt tiêu chí chất lượng": "Chất lượng kinh doanh chưa đạt",
        "Giá chưa có đủ biên an toàn": "Giá chưa đủ rẻ theo biên an toàn",
        "Độ phủ dữ liệu chưa đủ": "Thiếu dữ liệu để chấm đủ điểm",
        "Không đủ cơ sở định giá": "Không đủ cơ sở định giá",
        "Thanh khoản thiếu dữ liệu hoặc dưới ngưỡng": "Thanh khoản chưa đạt",
    }
    return pd.DataFrame(
        [
            {"Nguyên nhân": labels.get(reason, reason), "Số mã": count}
            for reason, count in counter.most_common(10)
        ]
    )


def _table(snapshot: dict, profile: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Hạng": r["profiles"][profile]["rank"],
                "Mã": r["ticker"],
                "Doanh nghiệp": r.get("name", r["ticker"]),
                "Ngành": r.get("sector"),
                "Thị giá (đ)": r.get("price"),
                "Giá hợp lý (đ)": r.get("fair_value"),
                "Chênh lệch (%)": r.get("upside_pct"),
                "Biên an toàn (%)": (
                    r["mos"] * 100 if r.get("mos") is not None else None
                ),
                "Điểm / 100": r["profiles"][profile]["score"],
                "Độ phủ (%)": r["profiles"][profile]["coverage"],
                "Tăng hạng": r["profiles"][profile].get("rank_change"),
                "Trạng thái": (
                    "Có thể cân nhắc"
                    if r["profiles"][profile]["eligible"]
                    else (
                        "Không xếp hạng"
                        if r["profiles"][profile]["score"] is None
                        else "Chờ kiểm chứng / chờ giá"
                    )
                ),
                "Phiên giá": r.get("price_date"),
                "Kỳ BCTC": r.get("financial_period"),
                "Điều kiện chưa đạt": "; ".join(r["profiles"][profile]["reasons"]),
            }
            for r in snapshot["rows"]
        ]
    )


@st.cache_data(show_spinner=False)
def _excel(snapshot: dict) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for profile, name in (("defensive", "Than trong"), ("growth", "Tang truong")):
            _table(snapshot, profile).to_excel(writer, sheet_name=name, index=False)
            if snapshot["ai"]["status"] == "SUCCESS":
                qualified, _ = selected_lists(snapshot, profile)
                pd.DataFrame(
                    [
                        {
                            "Mã": r["ticker"],
                            "Trạng thái": (
                                "Qua bộ lọc"
                                if r["ticker"] in qualified
                                else "Chỉ nghiên cứu thêm, chưa đề xuất mua"
                            ),
                            "12-24 tháng": r["medium_term"],
                            "3-5 năm": r["long_term"],
                            "Lý do": "\n".join(r["reasons"]),
                            "Rủi ro": "\n".join(r["risks"]),
                            "Bỏ luận điểm khi": r["invalid_if"],
                            "Nguồn": "; ".join(r["source_ids"]),
                        }
                        for r in snapshot["ai"]["review"][profile]["picks"]
                    ]
                ).to_excel(writer, sheet_name=f"AI {name}", index=False)
        pd.DataFrame(
            [
                {"ID": key, **value}
                for key, value in snapshot["ai"].get("sources", {}).items()
            ]
        ).to_excel(writer, sheet_name="Nguon AI", index=False)
        pd.DataFrame(
            [
                {
                    "Định giá lúc": snapshot["completed_at"],
                    "ID": snapshot["run_id"],
                    "Lưu ý": "Điểm là công cụ sàng lọc, không phải xác suất sinh lời. Chờ kiểm chứng không phải khuyến nghị mua.",
                    "AI": snapshot["ai"]["status"],
                }
            ]
        ).to_excel(writer, sheet_name="Thong tin", index=False)
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "C2"
            sheet.auto_filter.ref = sheet.dimensions
            for cells in sheet.columns:
                sheet.column_dimensions[cells[0].column_letter].width = min(
                    48, max(14, len(str(cells[0].value)) + 2)
                )
            # Chuỗi từ nguồn ngoài không được trở thành công thức Excel.
            for cells in sheet.iter_rows():
                for cell in cells:
                    if cell.data_type == "f":
                        cell.data_type = "s"
    return buffer.getvalue()


def _company_detail(
    row: dict, profile: str, review: dict | None, sources: dict
) -> None:
    score = row["profiles"][profile]
    status = (
        "Có thể cân nhắc từng phần" if score["eligible"] else "Chờ kiểm chứng / chờ giá"
    )
    with st.expander(f"{row['ticker']} · {row.get('name', '')} · {status}"):
        st.write(
            f"**{row.get('sector')}** · {_money(row.get('price'))} · Phiên {row.get('price_date', 'chưa rõ')}"
        )
        a, b, c = st.columns(3)
        a.metric("Giá hợp lý cơ sở", _money(row.get("fair_value")))
        b.metric("Ngưỡng giá theo biên an toàn", _money(score.get("buy_below")))
        c.metric(
            "Điểm có đủ bằng chứng",
            f"{score['score'] or 0:.1f}/100",
            help=f"Độ phủ {score['coverage']}%. Phần thiếu không được tự cộng điểm.",
        )
        if not score["eligible"]:
            st.warning("Chưa phải khuyến nghị mua: " + "; ".join(score["reasons"]))
        scenario = row.get("scenarios", {})
        st.write(
            f"Kịch bản bất lợi: **{_money(scenario.get('Bear'))}** · Cơ sở: **{_money(scenario.get('Base'))}** · Thuận lợi: **{_money(scenario.get('Bull'))}**"
        )
        st.caption(
            "Đây là kết quả theo giả định, không phải khoảng giá chắc chắn xảy ra hoặc mức lỗ tối đa."
        )
        if review:
            st.markdown("**Góc nhìn 12–24 tháng**")
            st.write(review["medium_term"])
            st.markdown("**Góc nhìn tích sản 3–5 năm**")
            st.write(review["long_term"])
            left, right = st.columns(2)
            with left:
                st.markdown("**Lý do theo dõi**")
                for reason in review["reasons"]:
                    st.write("• " + reason)
            with right:
                st.markdown("**Điểm cần phản biện**")
                for risk in review["risks"]:
                    st.write("• " + risk)
            st.write("**Khi nào cần bỏ luận điểm:** " + review["invalid_if"])
            for source_id in review["source_ids"]:
                source = sources.get(source_id, {})
                if source.get("url", "").startswith("https://"):
                    st.link_button(source.get("title", source_id), source["url"])
                else:
                    st.caption(
                        f"Nguồn {source_id}: hồ sơ Python, phiên {source.get('price_date', 'chưa rõ')}, {source.get('financial_period', '')}."
                    )
        else:
            st.info(
                "Chưa có nhận định DeepSeek hợp lệ cho mã này trong đợt đang xem. Chưa đủ cơ sở kết luận doanh nghiệp đầu ngành hoặc có lợi thế bền vững."
            )
        st.markdown("**Số liệu và giả định đối chiếu**")
        st.json(
            {
                "phương_pháp": row.get("method"),
                "chỉ_tiêu": row.get("metrics"),
                "điểm_thành_phần": score["components"],
                "giả_định": row.get("assumptions"),
                "nguồn_BCTC": row.get("financial_sources"),
                "dấu_vân_tay_đầu_vào": row.get("input_hash"),
            },
            expanded=False,
        )


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


def render_vn100_ranking() -> None:
    st.subheader("VN100 & tích sản")
    st.caption(
        "Trung hạn 12–24 tháng · Tích sản 3–5 năm · Hai chiến lược, hai bộ tiêu chí riêng"
    )
    left, right = st.columns([3, 2])
    with left:
        if st.button(
            "Định giá VN100 & cập nhật tích sản",
            icon=":material/refresh:",
            key="ranking_refresh",
            type="primary",
            disabled=job_status().get("status") in ("QUEUED", "RUNNING"),
        ):
            started = start_job()
            st.session_state["ranking_waiting"] = started
            if not started:
                st.info("Một đợt cập nhật đang chạy; không tạo thêm yêu cầu.")
            st.rerun()
    with right:
        st.caption(
            f"Lịch thứ Ba 09:30, giờ Việt Nam · Mốc tiếp theo: {next_run(local_now()):%d/%m/%Y %H:%M}"
        )
        st.caption(
            "Lịch chạy trên máy chủ đã thiết lập; máy tắt hoặc ngủ có thể làm chậm lịch. Mở tab không gọi DeepSeek."
        )
    _progress()
    snapshot = latest_snapshot()
    history = sorted((STORE / "history").glob("*.json"), reverse=True)
    if history:
        selected = st.selectbox(
            "Đợt định giá",
            ["Mới nhất"] + [p.stem for p in history],
            key="ranking_history",
        )
        if selected != "Mới nhất":
            snapshot = read_json(STORE / "history" / f"{selected}.json")
    if not snapshot:
        st.info(
            "Chưa có bảng VN100 được lưu. Chạy cập nhật để tạo đợt định giá đầu tiên."
        )
        return
    cfg = snapshot.get("config", load_ranking_config())
    st.caption(
        f"Hoàn thành: {_date_label(snapshot['completed_at'])} (giờ Việt Nam) · Thành phần VN100: {snapshot['universe'].get('as_of', 'chưa rõ')} · Số mã: {len(snapshot['rows'])}"
    )
    if (local_now() - datetime.fromisoformat(snapshot["completed_at"])).days >= cfg[
        "price_max_age_days"
    ]:
        st.error(
            "Đây là bản xếp hạng cũ. Các mức giá và nhận định dưới đây không phản ánh hiện tại; cần cập nhật trước khi tư vấn."
        )
    profile = st.radio(
        "Chiến lược đầu tư",
        list(cfg["profiles"]),
        format_func=lambda key: cfg["profiles"][key]["label"],
        horizontal=True,
        key="ranking_profile",
    )
    st.write(cfg["profiles"][profile]["description"])
    a, b, c = st.columns(3)
    qualified, research = selected_lists(snapshot, profile)
    a.metric("Qua bộ lọc tích sản", f"{len(qualified)} mã")
    b.metric(
        "Cần bổ sung / chờ giá",
        f"{sum(not r['profiles'][profile]['eligible'] for r in snapshot['rows'])} mã",
    )
    c.metric(
        "Không đủ cơ sở xếp hạng",
        f"{sum(r['profiles'][profile]['score'] is None for r in snapshot['rows'])} mã",
    )
    st.warning(
        "Không có cổ phiếu nào được bảo đảm an toàn hoặc sinh lời. Giá hợp lý phụ thuộc giả định; mã chờ kiểm chứng không phải đề xuất mua cho khách hàng."
    )
    ai = snapshot["ai"]
    if ai["status"] == "SUCCESS":
        st.caption(
            f"Nhận định AI: {_date_label(ai['generated_at'])} · {ai['model']} · {'Dùng bản đã lưu' if ai.get('cache_hit') else 'Một yêu cầu API'} · Đầu vào {ai.get('usage', {}).get('prompt_tokens', '?')} token / đầu ra {ai.get('usage', {}).get('completion_tokens', '?')} token"
        )
        strategy = ai["review"][profile]
        st.write(strategy["overview"])
        reviews = {r["ticker"]: r for r in strategy["picks"]}
    else:
        st.info(ai.get("message", "Chưa có báo cáo AI"))
        reviews = {}
    by_ticker = {row["ticker"]: row for row in snapshot["rows"]}
    st.markdown("### Danh sách đạt bộ lọc tích sản")
    if not qualified:
        st.info(
            "Đợt này chưa có mã qua đủ chuẩn nghiêm ngặt. Bảng dưới cho biết vì sao rớt và nhóm có thể theo dõi nếu nới nhẹ phần kiểm chứng thủ công."
        )
        st.dataframe(
            _reason_summary(snapshot, profile), hide_index=True, width="stretch"
        )
        conditional = _conditional_candidates(snapshot, profile)
        if conditional:
            st.markdown("### Ứng viên có điều kiện sau khi nới nhẹ")
            st.caption(
                "Cách nới: tạm cho phép thiếu golden-test và hồ sơ governance/moat, nhưng vẫn chặn lỗi dữ liệu nghiêm trọng, định giá không hợp lệ, thanh khoản yếu và giá chưa đủ rẻ."
            )
            for row in conditional:
                _company_detail(
                    row, profile, reviews.get(row["ticker"]), ai.get("sources", {})
                )
        else:
            st.warning(
                "Ngay cả khi nới nhẹ, chưa có mã đủ sạch để đưa vào nhóm có điều kiện cho chiến lược này."
            )
    for ticker in qualified:
        _company_detail(
            by_ticker[ticker], profile, reviews.get(ticker), ai.get("sources", {})
        )
    st.markdown("### Ứng viên cần nghiên cứu thêm")
    for ticker in research:
        if ticker not in qualified:
            _company_detail(
                by_ticker[ticker], profile, reviews.get(ticker), ai.get("sources", {})
            )
    defensive_lists = selected_lists(snapshot, "defensive")
    growth_lists = selected_lists(snapshot, "growth")
    overlap = set(chain.from_iterable(defensive_lists)) & set(
        chain.from_iterable(growth_lists)
    )
    if overlap:
        st.caption(
            "Mã xuất hiện ở cả hai bộ lọc: "
            + ", ".join(sorted(overlap))
            + ". Hai danh sách không phải hai danh mục độc lập; gộp lại cần kiểm tra tỷ trọng ngành."
        )
    if ai["status"] == "SUCCESS":
        with st.expander("Phản biện chung trước khi tư vấn"):
            st.write(ai["review"]["counterargument"])
    with st.expander("Thay đổi so với tuần trước"):
        previous = snapshot.get("previous_selections", {}).get(profile)
        if previous:
            before = set(previous.get("qualified", []) + previous.get("research", []))
            current = set(qualified + research)
            st.write(
                "Tiếp tục theo dõi: "
                + (", ".join(sorted(before & current)) or "Không có")
            )
            st.write(
                "Mới xuất hiện: " + (", ".join(sorted(current - before)) or "Không có")
            )
            st.write(
                "Không còn trong danh sách: "
                + (", ".join(sorted(before - current)) or "Không có")
            )
            st.caption(
                "Thay đổi phản ánh bộ lọc và dữ liệu của từng đợt, không tự động là tín hiệu mua/bán. Xem lý do chưa đạt và phản biện trước khi hành động."
            )
        else:
            st.write(
                "Chưa có snapshot tuần trước để đối chiếu. Không hồi tố tạo kết quả quá khứ."
            )
    st.markdown("### Bảng xếp hạng toàn VN100")
    frame = _table(snapshot, profile)
    sectors = st.multiselect(
        "Lọc ngành", sorted(frame["Ngành"].dropna().unique()), key="ranking_sectors"
    )
    if sectors:
        frame = frame[frame["Ngành"].isin(sectors)]
    sort = st.selectbox(
        "Sắp xếp", ["Hạng", "Chênh lệch (%)", "Biên an toàn (%)"], key="ranking_sort"
    )
    frame = frame.sort_values(sort, ascending=sort == "Hạng", na_position="last")
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        height=540,
        column_config={
            # Ghim Hạng + Mã: kéo ngang trên điện thoại vẫn biết đang đọc dòng mã nào.
            # width="small": Streamlit tự tắt ghim khi bảng hẹp hơn tổng độ rộng cột ghim (~334px).
            "Hạng": st.column_config.NumberColumn(width="small", pinned=True),
            "Mã": st.column_config.TextColumn(width="small", pinned=True),
            **{
                key: st.column_config.NumberColumn(format="%.1f")
                for key in ("Chênh lệch (%)", "Biên an toàn (%)", "Điểm / 100")
            },
        },
    )
    st.download_button(
        "Xuất Excel hai chiến lược",
        _excel(snapshot),
        file_name=f"VN100_tich_san_{snapshot['run_id']}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:",
    )
    with st.expander("Nguồn, tiêu chí và các dữ liệu còn thiếu"):
        st.write(
            "Điểm là tổng trọng số trên 100. Chỉ tiêu thiếu không được tự coi bằng 0 tốt hoặc tự chia lại trọng số. Vì vậy phải đọc điểm cùng độ phủ, không so điểm thiếu nguồn như điểm hoàn chỉnh."
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Thận trọng": cfg["profiles"]["defensive"]["weights"],
                    "Tăng trưởng": cfg["profiles"]["growth"]["weights"],
                }
            ).rename(
                index={
                    "valuation": "Định giá",
                    "quality": "Chất lượng kinh doanh",
                    "safety": "Sức khỏe tài chính",
                    "moat": "Lợi thế cạnh tranh",
                    "context": "Bối cảnh vĩ mô/doanh nghiệp",
                    "flow": "Dòng tiền giao dịch",
                }
            )
        )
        st.write(
            "Biên an toàn = 1 − thị giá / giá hợp lý. Chênh lệch = giá hợp lý / thị giá − 1. Ngưỡng giá theo biên an toàn chỉ có ý nghĩa khi dữ liệu và mô hình đã đạt các bước kiểm chứng."
        )
        st.json(
            {
                "vĩ_mô": snapshot.get("macro"),
                "kiểm_tra_tin": snapshot.get("news", {}).get("checked_at"),
                "lỗi_nguồn": snapshot.get("source_errors", [])
                + snapshot.get("news", {}).get("errors", []),
            },
            expanded=False,
        )
