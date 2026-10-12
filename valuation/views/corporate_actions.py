"""Tab cổ tức, tăng vốn và quyền cổ đông."""

from __future__ import annotations

import datetime
import html
from types import SimpleNamespace
from typing import Any

import pandas as pd
import streamlit as st

from valuation.analysis.corporate_actions import (
    analyze_corporate_action,
    analyze_historical_price_impact,
    assess_corporate_action,
    explain_historical_price_impact,
    explain_upcoming_action,
    quick_investment_opinion,
)
from valuation.config import load_defaults
from valuation.data_access.corporate_actions import (
    load_corporate_actions,
    load_upcoming_vn100_corporate_actions,
)
from valuation.db.models import PricesDaily
from valuation.ingest.corporate_actions import refresh_corporate_actions
from valuation.services.ranking_store import latest_snapshot
from valuation.views.device import phone_collapsible

_VN_TZ = datetime.timezone(datetime.timedelta(hours=7))


def _today_vn() -> datetime.date:
    return datetime.datetime.now(_VN_TZ).date()


_EVENT_LABELS = {
    "CASH_DIVIDEND": "Cổ tức tiền mặt",
    "STOCK_DIVIDEND": "Cổ tức cổ phiếu",
    "BONUS_SHARE": "Cổ phiếu thưởng",
    "STOCK_BONUS_COMBO": "Cổ tức cổ phiếu + cổ phiếu thưởng",
    "RIGHTS_ISSUE": "Quyền mua",
    "ESOP": "ESOP/CBCNV",
    "PRIVATE_PLACEMENT": "Phát hành riêng lẻ",
    "SHARE_ISSUE": "Phát hành cổ phiếu",
    "ADDITIONAL_LISTING": "Niêm yết bổ sung",
    "SHARE_BUYBACK": "Mua lại cổ phiếu",
    "CONVERTIBLE": "Chuyển đổi",
    "MERGER": "Sáp nhập",
    "OTHER_CAPITAL_ACTION": "Sự kiện vốn khác",
}

_PRICE_IMPACT_TYPES = {
    "CASH_DIVIDEND",
    "STOCK_DIVIDEND",
    "BONUS_SHARE",
    "STOCK_BONUS_COMBO",
    "RIGHTS_ISSUE",
    "ESOP",
    "PRIVATE_PLACEMENT",
    "SHARE_ISSUE",
}

_SHARE_GRANT_TYPES = {"STOCK_DIVIDEND", "BONUS_SHARE"}


def _render_capital_actions_style() -> None:
    st.markdown(
        """
<style>
    .ca-hero {
        padding: 0 0 22px; margin: 0 0 20px;
        border-bottom: 1px solid var(--ag-line, #e4e9ec);
    }
    .ca-hero-row, .ca-section-head {
        display: flex; justify-content: space-between; gap: 18px;
        align-items: flex-start; flex-wrap: wrap;
    }
    .ca-kicker { color: #00843d; font-size: 12px; font-weight: 700; margin-bottom: 8px; }
    .ca-title { color: #2e3a5b; font-size: 26px; line-height: 1.35; font-weight: 700; margin: 0 0 10px; }
    .ca-copy { color: #596481; font-size: 15px; line-height: 1.7; max-width: 880px; margin: 0; }
    .ca-pill-row { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 14px; }
    .ca-pill { color: #596481; font-size: 13px; line-height: 1.6; }
    .ca-stat-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 8px 0 28px; background: #f5f8f7; }
    .ca-stat { padding: 20px; border-right: 1px solid #e4e9ec; }
    .ca-stat:last-child { border-right: 0; }
    .ca-stat-label { color: #596481; font-size: 13px; margin-bottom: 10px; }
    .ca-stat-value { color: #00843d; font-size: 28px; line-height: 1.3; font-weight: 700; font-variant-numeric: tabular-nums; }
    .ca-section-head { border-bottom: 1px solid #e4e9ec; padding: 10px 0 14px; margin: 24px 0 16px; }
    .ca-section-head h3 { color: #2e3a5b; font-size: 22px; font-weight: 700; margin: 0; }
    .ca-section-note, .ca-meta { color: #596481; font-size: 13px; line-height: 1.6; }
    .ca-meta { margin-bottom: 16px; }
    .ca-card { border: 1px solid #e4e9ec; border-radius: 8px; background: #fff; padding: 22px; margin: 14px 0; transition: border-color 140ms ease; }
    .ca-card:hover { border-color: #00b74f; }
    .ca-card-title { color: #2e3a5b; font-size: 18px; font-weight: 700; line-height: 1.5; margin: 0 0 8px; }
    .ca-mini-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; margin-top: 18px; padding-top: 16px; border-top: 1px solid #e4e9ec; }
    .ca-mini { min-width: 0; }
    .ca-mini-label { color: #596481; font-size: 12px; margin-bottom: 6px; }
    .ca-mini-value { color: #2e3a5b; font-size: 18px; font-weight: 700; line-height: 1.4; overflow-wrap: anywhere; }
    .ca-mini-sub { color: #596481; font-size: 12px; margin-top: 6px; line-height: 1.5; }
    .ca-verdict { display: inline-flex; align-items: center; border-radius: 4px; padding: 6px 10px; font-size: 12px; font-weight: 700; line-height: 1.5; }
    .ca-good { color: #007334; background: #eaf8ef; }
    .ca-flat { color: #596481; background: #f0f3f5; }
    .ca-bad { color: #a52828; background: #fff0f0; }
    .ca-warn { color: #885800; background: #fff6df; }
    .ca-explain { padding: 16px 0 0; margin-top: 16px; border-top: 1px solid #e4e9ec; }
    .ca-explain p { color: #2e3a5b; font-size: 14px; line-height: 1.7; margin: 0 0 12px; }
    .ca-explain p:last-child { margin-bottom: 0; }
    .ca-table-note { border-left: 3px solid #1d4289; background: #f5f7fb; color: #2e3a5b; padding: 12px 16px; margin: 12px 0; font-size: 13px; line-height: 1.7; }
    @media (max-width: 900px) {
        .ca-mini-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 560px) {
        .ca-stat-grid { grid-template-columns: 1fr; }
        .ca-stat { border-right: 0; border-bottom: 1px solid #e4e9ec; }
        .ca-title { font-size: 23px; }
        .ca-card { padding: 16px; }
    }
    @media (prefers-reduced-motion: reduce) {
        .ca-card { transition: none; }
    }
</style>
        """,
        unsafe_allow_html=True,
    )


def _anchor(row: Any) -> Any:
    return (
        row.ex_right_date
        or row.record_date
        or row.payment_date
        or row.listing_date
        or row.announcement_date
    )


def _fmt_vnd(value: Any) -> str:
    return "-" if value is None else f"{float(value):,.0f}".replace(",", ".")


def _fmt_pct(value: Any) -> str:
    return "-" if value is None else f"{float(value):+.1f}%"


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _verdict_class(label: str) -> str:
    upper = str(label or "").upper()
    if "TĂNG" in upper or "TÍCH CỰC" in upper:
        return "ca-good"
    if "GIẢM" in upper or "THẬN TRỌNG" in upper:
        return "ca-bad"
    if "THIẾU" in upper or "CHƯA" in upper:
        return "ca-warn"
    return "ca-flat"


def _render_metric_grid(
    *,
    upcoming_count: int,
    nearest_days: int | None,
    historical_count: int,
) -> None:
    nearest_text = f"{nearest_days} ngày" if nearest_days is not None else "Chưa có"
    st.markdown(
        f"""
<div class="ca-stat-grid">
    <div class="ca-stat">
        <div class="ca-stat-label">Đã công bố trong 12 tháng tới</div>
        <div class="ca-stat-value">{upcoming_count}</div>
    </div>
    <div class="ca-stat">
        <div class="ca-stat-label">Sự kiện gần nhất</div>
        <div class="ca-stat-value">{_escape(nearest_text)}</div>
    </div>
    <div class="ca-stat">
        <div class="ca-stat-label">Lịch sử đang phân tích</div>
        <div class="ca-stat-value">{historical_count}</div>
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _section_head(title: str, note: str) -> None:
    st.markdown(
        f"""
<div class="ca-section-head">
    <h3>{_escape(title)}</h3>
    <p class="ca-section-note">{_escape(note)}</p>
</div>
        """,
        unsafe_allow_html=True,
    )


_STOCK_PAYOUTS = ("STOCK_DIVIDEND", "BONUS_SHARE", "STOCK_BONUS_COMBO")


def latest_payouts(rows: list[Any], today: datetime.date) -> dict[str, list[Any]]:
    """Lần chia gần nhất đã thực hiện (mốc ≤ hôm nay): {"cash": [...], "stock": [...]}.

    Gộp các sự kiện cùng mốc (vd cổ tức CP 25% + thưởng 20% cùng ngày GDKHQ) để hiện một lần chia.
    """
    out: dict[str, list[Any]] = {}
    for key, types in (("cash", ("CASH_DIVIDEND",)), ("stock", _STOCK_PAYOUTS)):
        past = [
            r
            for r in rows
            if r.event_type in types and _anchor(r) and _anchor(r) <= today
        ]
        if past:
            last = max(_anchor(r) for r in past)
            out[key] = [r for r in past if _anchor(r) == last]
    return out


def _render_latest_payouts(rows: list[Any], today: datetime.date) -> None:
    latest = latest_payouts(rows, today)
    _section_head(
        "Lần chia gần nhất",
        "Cổ tức tiền mặt và cổ phiếu/thưởng đã thực hiện gần đây nhất trong dữ liệu đã lưu.",
    )
    cells = []
    cash = latest.get("cash")
    if cash:
        r = cash[0]  # một lần chia; nhiều nguồn cùng mốc là bản trùng, không cộng dồn
        sub = f"GDKHQ {_anchor(r):%d/%m/%Y}" + (
            f" · thanh toán {r.payment_date:%d/%m/%Y}" if r.payment_date else ""
        )
        cells.append(("Tiền mặt", f"{_fmt_vnd(r.cash_amount_vnd_per_share)} đ/cp", sub))
    else:
        cells.append(("Tiền mặt", "Chưa có", "Không có trong dữ liệu đã lưu"))
    stock = latest.get("stock")
    if stock:
        by_type = {r.event_type: r for r in stock}  # bỏ bản trùng cùng loại
        value = " + ".join(
            (
                f"{float(r.exercise_ratio) * 100:g}%"
                if r.exercise_ratio is not None
                else "?"
            )
            for r in by_type.values()
        )
        kinds = " + ".join(_EVENT_LABELS.get(t, t) for t in by_type)
        sub = f"{kinds} · GDKHQ {_anchor(stock[0]):%d/%m/%Y}"
        cells.append(("Cổ phiếu / thưởng", value, sub))
    else:
        cells.append(("Cổ phiếu / thưởng", "Chưa có", "Không có trong dữ liệu đã lưu"))
    body = "".join(
        f'<div class="ca-mini"><div class="ca-mini-label">{_escape(label)}</div>'
        f'<div class="ca-mini-value">{_escape(value)}</div>'
        f'<div class="ca-mini-sub">{_escape(sub)}</div></div>'
        for label, value, sub in cells
    )
    st.markdown(
        '<div class="ca-card"><div class="ca-mini-grid" style="grid-template-columns: repeat(2, '
        f'minmax(0, 1fr)); margin-top: 0; padding-top: 0; border-top: 0;">{body}</div></div>',
        unsafe_allow_html=True,
    )


def _style_impact_table(df: pd.DataFrame) -> Any:
    def pct_color(value: Any) -> str:
        text = str(value)
        if text.startswith("+"):
            return "color:#047857;font-weight:800;background-color:#ecfdf5;"
        if text.startswith("-"):
            return "color:#b91c1c;font-weight:800;background-color:#fef2f2;"
        return "color:#334155;"

    def verdict_color(value: Any) -> str:
        klass = _verdict_class(str(value))
        if klass == "ca-good":
            return "color:#047857;font-weight:850;background-color:#ecfdf5;"
        if klass == "ca-bad":
            return "color:#b91c1c;font-weight:850;background-color:#fef2f2;"
        if klass == "ca-warn":
            return "color:#92400e;font-weight:850;background-color:#fffbeb;"
        return "color:#475569;font-weight:750;background-color:#f8fafc;"

    styles = {
        "Tài sản thực": pct_color,
        "Sau 1 tuần": pct_color,
        "Sau 1 tháng": pct_color,
        "Kết luận": verdict_color,
    }
    styler = df.style
    if hasattr(styler, "map"):
        return (
            styler.map(styles["Tài sản thực"], subset=["Tài sản thực"])
            .map(styles["Sau 1 tuần"], subset=["Sau 1 tuần"])
            .map(styles["Sau 1 tháng"], subset=["Sau 1 tháng"])
            .map(styles["Kết luận"], subset=["Kết luận"])
        )
    return (
        styler.applymap(styles["Tài sản thực"], subset=["Tài sản thực"])
        .applymap(styles["Sau 1 tuần"], subset=["Sau 1 tuần"])
        .applymap(styles["Sau 1 tháng"], subset=["Sau 1 tháng"])
        .applymap(styles["Kết luận"], subset=["Kết luận"])
    )


def _style_quick_opinion_table(df: pd.DataFrame) -> Any:
    def opinion_color(value: Any) -> str:
        text = str(value or "").upper()
        if text.startswith("ĐÁNG NGHIÊN CỨU"):
            return "color:#047857;font-weight:750;background-color:#ecfdf5;"
        if text.startswith("THEO DÕI"):
            return "color:#92400e;font-weight:750;background-color:#fffbeb;"
        if text.startswith(
            (
                "CHƯA HẤP DẪN",
                "CHƯA ĐỦ",
                "CHƯA THỂ",
                "CẦN ĐỐI CHIẾU",
                "CẦN KIỂM TRA",
            )
        ):
            return "color:#b91c1c;font-weight:750;background-color:#fef2f2;"
        return "color:#334155;"

    styler = df.style
    if hasattr(styler, "map"):
        return styler.map(opinion_color, subset=["Nhận định nhanh"])
    return styler.applymap(opinion_color, subset=["Nhận định nhanh"])


def _render_history_card(
    *,
    row: Any,
    impact: dict[str, Any],
    story: dict[str, str],
    expanded: bool,
) -> None:
    label = _EVENT_LABELS.get(row.event_type, row.event_type)
    anchor = _anchor(row)
    verdict = story["reaction_label"]
    event_return = impact.get("raw_event_return_pct")
    wealth = impact.get("shareholder_wealth_change_pct")
    after_20 = impact.get("return_after_20_sessions_pct")
    adjusted_note = (
        "Dữ liệu giá đã điều chỉnh quyền, hệ thống đọc trên cùng mặt bằng sau chia."
        if impact.get("price_series_adjusted")
        else "Dữ liệu giá được đọc theo mốc trước/sau ngày chia quyền."
    )

    st.markdown(
        f"""
<div class="ca-card">
    <div class="ca-hero-row">
        <div>
            <div class="ca-kicker">{_escape(anchor.strftime('%d/%m/%Y'))}</div>
            <div class="ca-card-title">{_escape(label)} - {_escape(row.title)}</div>
            <div class="ca-meta">{_escape(adjusted_note)}</div>
        </div>
        <span class="ca-verdict {_verdict_class(verdict)}">{_escape(verdict)}</span>
    </div>
    <div class="ca-mini-grid">
        <div class="ca-mini">
            <div class="ca-mini-label">Giá ngày chia quyền</div>
            <div class="ca-mini-value">{_fmt_vnd(impact.get('price_event_vnd'))} VND</div>
            <div class="ca-mini-sub">Biến động trong ngày: {_fmt_pct(event_return)}</div>
        </div>
        <div class="ca-mini">
            <div class="ca-mini-label">Bạn nhận thêm</div>
            <div class="ca-mini-value">{_escape(_benefit_summary(row))}</div>
        </div>
        <div class="ca-mini">
            <div class="ca-mini-label">Tài sản thực sau quyền</div>
            <div class="ca-mini-value">{_fmt_pct(wealth)}</div>
            <div class="ca-mini-sub">Đã tránh cộng trùng nếu giá đã điều chỉnh.</div>
        </div>
        <div class="ca-mini">
            <div class="ca-mini-label">Sau khoảng 1 tháng</div>
            <div class="ca-mini-value">{_fmt_pct(after_20)}</div>
            <div class="ca-mini-sub">Tính từ giá ngày chia quyền.</div>
        </div>
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander(
        f"Giải thích chi tiết - {label} {anchor.strftime('%d/%m/%Y')}",
        expanded=expanded,
    ):
        st.markdown(
            f"""
<div class="ca-explain">
    <p>{_escape(story["price_explanation"])}</p>
    <p>{_escape(story["wealth_explanation"])}</p>
    <p>{_escape(story["follow_through"])}</p>
</div>
            """,
            unsafe_allow_html=True,
        )
        if impact.get("data_warning"):
            st.caption(impact["data_warning"])


def _date_role(row: Any) -> str:
    if row.ex_right_date:
        return "Ngày GDKHQ"
    if row.record_date:
        return "Ngày chốt quyền"
    if row.payment_date:
        return "Ngày thanh toán"
    if row.listing_date:
        return "Ngày niêm yết"
    return "Ngày công bố"


def _benefit_summary(row: Any) -> str:
    ratio = float(row.exercise_ratio) if row.exercise_ratio is not None else None
    cash = (
        float(row.cash_amount_vnd_per_share)
        if row.cash_amount_vnd_per_share is not None
        else None
    )
    issue_price = (
        float(row.issue_price_vnd) if row.issue_price_vnd is not None else None
    )
    if row.event_type == "CASH_DIVIDEND" and cash is not None:
        return f"{_fmt_vnd(cash)} VND/cổ phiếu"
    if (
        row.event_type in {"STOCK_DIVIDEND", "BONUS_SHARE", "STOCK_BONUS_COMBO"}
        and ratio is not None
    ):
        return f"Thêm {ratio * 100:g} cổ phiếu/100 cổ phiếu"
    if row.event_type == "RIGHTS_ISSUE" and ratio is not None:
        text = f"Được mua {ratio * 100:g} cổ phiếu/100 cổ phiếu"
        return f"{text}, giá {_fmt_vnd(issue_price)} VND" if issue_price else text
    # Phát hành không chia cho cổ đông hiện hữu: trước đây rơi xuống "Chưa đủ thông tin" dù có tỷ lệ.
    dilutive = {
        "ESOP": "Phát hành ESOP cho nhân viên",
        "PRIVATE_PLACEMENT": "Phát hành riêng lẻ",
        "SHARE_ISSUE": "Phát hành thêm",
    }
    if row.event_type in dilutive and ratio:
        pct = f"{ratio * 100:.2f}".rstrip("0").rstrip(".")
        text = f"{dilutive[row.event_type]} {pct}% số cổ phiếu (cổ đông hiện hữu không nhận)"
        return f"{text}, giá {_fmt_vnd(issue_price)} VND" if issue_price else text
    if row.event_type == "CASH_DIVIDEND":
        return "Chưa công bố số tiền/cổ phiếu"
    if not ratio:
        return "Nguồn chưa ghi tỷ lệ"
    return "Chưa đủ thông tin"


def _historical_impact_rows(rows: list[Any]) -> list[Any]:
    """Gộp các quyền nhận cổ phiếu cùng ngày để không double-count khi phân tích."""
    grouped: dict[tuple[Any, Any, Any, Any], list[Any]] = {}
    passthrough: list[Any] = []
    for row in rows:
        if row.event_type not in _SHARE_GRANT_TYPES:
            passthrough.append(row)
            continue
        key = (_anchor(row), row.record_date, row.listing_date, row.source_site)
        grouped.setdefault(key, []).append(row)

    combined: list[Any] = []
    for items in grouped.values():
        if len(items) == 1:
            combined.append(items[0])
            continue
        first = items[0]
        ratio = sum(
            float(item.exercise_ratio)
            for item in items
            if item.exercise_ratio is not None
        )
        titles = " + ".join(str(item.title) for item in items)
        combined.append(
            SimpleNamespace(
                ticker=first.ticker,
                source_site=first.source_site,
                source_event_id="+".join(str(item.source_event_id) for item in items),
                event_type="STOCK_BONUS_COMBO",
                event_code=first.event_code,
                title=titles,
                announcement_date=min(
                    (
                        item.announcement_date
                        for item in items
                        if item.announcement_date is not None
                    ),
                    default=first.announcement_date,
                ),
                ex_right_date=first.ex_right_date,
                record_date=first.record_date,
                payment_date=first.payment_date,
                listing_date=first.listing_date,
                exercise_ratio=ratio or None,
                cash_amount_vnd_per_share=None,
                issue_price_vnd=None,
                shares_after=first.shares_after,
                source_url=first.source_url,
                source_tier=first.source_tier,
            )
        )

    out = passthrough + combined
    out.sort(key=lambda row: _anchor(row) or datetime.date.min, reverse=True)
    return out


def _render_historical_analysis(
    *,
    company: Any,
    db: Any,
    historical_rows: list[Any],
    cfg: dict[str, Any],
) -> None:
    st.markdown(
        """
<div class="ca-table-note">
    Cột <strong>Sau 1 tuần</strong> và <strong>Sau 1 tháng</strong> luôn tính từ
    giá trong ngày chia quyền, tức mốc đã chia xong. Nếu dữ liệu giá đã được điều
    chỉnh quyền, hệ thống không cộng thêm cổ phiếu lần nữa.
</div>
        """,
        unsafe_allow_html=True,
    )
    price_rows = (
        db.query(PricesDaily.trade_date, PricesDaily.close)
        .filter(PricesDaily.ticker == company.ticker)
        .order_by(PricesDaily.trade_date)
        .all()
    )
    prices = [
        {"date": item.trade_date, "close": float(item.close)}
        for item in price_rows
        if item.close is not None
    ]
    max_history = int(cfg.get("historical_impact_max_events", 12))
    impact_items = []
    for row in _historical_impact_rows(historical_rows):
        if row.event_type not in _PRICE_IMPACT_TYPES:
            continue
        ratio = float(row.exercise_ratio) if row.exercise_ratio is not None else None
        cash = (
            float(row.cash_amount_vnd_per_share)
            if row.cash_amount_vnd_per_share is not None
            else None
        )
        issue_price = (
            float(row.issue_price_vnd) if row.issue_price_vnd is not None else None
        )
        impact = analyze_historical_price_impact(
            prices=prices,
            event_date=_anchor(row),
            event_type=row.event_type,
            exercise_ratio=ratio,
            cash_amount_vnd_per_share=cash,
            issue_price_vnd=issue_price,
            short_sessions=int(cfg.get("price_impact_short_sessions", 5)),
            long_sessions=int(cfg.get("price_impact_long_sessions", 20)),
        )
        story = explain_historical_price_impact(
            event_type=row.event_type,
            impact=impact,
            reaction_materiality_pct=float(cfg.get("reaction_materiality_pct", 2.0)),
        )
        impact_items.append((row, impact, story))
        if len(impact_items) >= max_history:
            break

    available_items = [item for item in impact_items if item[1].get("available")]
    if not available_items:
        st.info("Chưa đủ dữ liệu giá trước và sau sự kiện để đo tác động lịch sử.")
    else:
        table_rows = []
        for row, impact, story in available_items:
            price_base = (
                f"{_fmt_vnd(impact.get('price_before_vnd'))} → "
                f"{_fmt_vnd(impact.get('price_event_vnd'))}"
            )
            if impact.get("price_series_adjusted"):
                price_base += " (giá đã điều chỉnh)"
            table_rows.append(
                {
                    "Ngày": _anchor(row),
                    "Sự kiện": _EVENT_LABELS.get(row.event_type, row.event_type),
                    "Mốc giá": price_base,
                    "Quyền lợi": _benefit_summary(row),
                    "Tài sản thực": _fmt_pct(
                        impact.get("shareholder_wealth_change_pct")
                    ),
                    "Sau 1 tuần": _fmt_pct(impact.get("return_after_5_sessions_pct")),
                    "Sau 1 tháng": _fmt_pct(impact.get("return_after_20_sessions_pct")),
                    "Kết luận": story["reaction_label"],
                }
            )
        impact_df = pd.DataFrame(table_rows)
        st.dataframe(
            _style_impact_table(impact_df),
            width="stretch",
            hide_index=True,
            column_config={"Ngày": st.column_config.DateColumn(format="DD/MM/YYYY")},
        )
        st.markdown("**Diễn giải từng sự kiện**")
        for row, impact, story in available_items:
            _render_history_card(
                row=row,
                impact=impact,
                story=story,
                expanded=False,
            )

    implementation_rows = [
        row for row in historical_rows if row.event_type == "ADDITIONAL_LISTING"
    ]
    if implementation_rows:
        with st.expander("Các mốc niêm yết bổ sung đã hoàn tất"):
            st.caption(
                "Các mốc này là bước thực hiện sau phát hành/chia cổ phiếu; không tính "
                "thêm một lần pha loãng để tránh đánh giá trùng."
            )
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Ngày": _anchor(row),
                            "Nội dung": row.title,
                            "Nguồn": f"{row.source_site} ({row.source_tier})",
                        }
                        for row in implementation_rows
                    ]
                ),
                width="stretch",
                hide_index=True,
                column_config={
                    "Ngày": st.column_config.DateColumn(format="DD/MM/YYYY")
                },
            )


def _render_vn100_upcoming_calendar(
    *,
    db: Any,
    today: datetime.date,
    future_days: int,
) -> None:
    _section_head(
        f"Lịch cổ tức & quyền mua VN100 trong {future_days} ngày tới",
        "Danh sách toàn VN100, sắp xếp theo ngày gần nhất và có nhận định sàng lọc.",
    )
    items = load_upcoming_vn100_corporate_actions(
        db,
        as_of_date=today,
        future_days=future_days,
    )
    if not items:
        st.info(
            f"Chưa có sự kiện VN100 nào đã công bố với mốc thực hiện từ "
            f"{today.strftime('%d/%m/%Y')} đến "
            f"{(today + datetime.timedelta(days=future_days)).strftime('%d/%m/%Y')}."
        )
        st.caption(
            "Danh sách chỉ phản ánh dữ liệu đã lưu và không tự dự đoán sự kiện chưa công bố."
        )
        return

    snapshot = latest_snapshot() or {}
    ranking_by_ticker = {
        row.get("ticker"): row for row in snapshot.get("rows", []) if row.get("ticker")
    }
    table_rows = []
    for item in items:
        ranking_row = ranking_by_ticker.get(item.action.ticker)
        current_price = float(ranking_row.get("price") or 0.0) if ranking_row else 0.0
        event_analysis = analyze_corporate_action(
            event_type=item.action.event_type,
            current_price_vnd=current_price,
            shares_outstanding=1.0,
            exercise_ratio=(
                float(item.action.exercise_ratio)
                if item.action.exercise_ratio is not None
                else None
            ),
            cash_amount_vnd_per_share=(
                float(item.action.cash_amount_vnd_per_share)
                if item.action.cash_amount_vnd_per_share is not None
                else None
            ),
            issue_price_vnd=(
                float(item.action.issue_price_vnd)
                if item.action.issue_price_vnd is not None
                else None
            ),
        )
        company_name = item.company_name
        if company_name == item.action.ticker and ranking_row:
            company_name = ranking_row.get("name") or company_name
        table_rows.append(
            {
                "Ngày": item.event_date,
                "Còn lại": (
                    "Hôm nay"
                    if item.event_date == today
                    else f"{(item.event_date - today).days} ngày"
                ),
                "Mã": item.action.ticker,
                "Nhận định nhanh": quick_investment_opinion(
                    event_type=item.action.event_type,
                    event_analysis=event_analysis,
                    ranking_row=ranking_row,
                ),
                "Sự kiện": _EVENT_LABELS.get(
                    item.action.event_type, item.action.event_type
                ),
                "Quyền lợi / điều kiện": _benefit_summary(item.action),
                "Doanh nghiệp": company_name,
            }
        )
    table = pd.DataFrame(table_rows)
    opinions = table["Nhận định nhanh"].astype(str)
    research_count = int(opinions.str.startswith("ĐÁNG NGHIÊN CỨU").sum())
    watch_count = int(opinions.str.startswith("THEO DÕI").sum())
    unattractive_count = int(opinions.str.startswith("CHƯA HẤP DẪN").sum())
    unresolved_count = len(table) - research_count - watch_count - unattractive_count
    st.caption(
        f"Tổng hợp: {research_count} mã đáng nghiên cứu sâu · "
        f"{watch_count} mã theo dõi · {unattractive_count} mã chưa hấp dẫn · "
        f"{unresolved_count} mã cần hoàn thiện mô hình hoặc kiểm tra dữ liệu."
    )
    st.dataframe(
        _style_quick_opinion_table(table),
        width="stretch",
        hide_index=True,
        column_config={
            "Ngày": st.column_config.DateColumn(format="DD/MM/YYYY", width="small"),
            "Còn lại": st.column_config.TextColumn(width="small"),
            "Mã": st.column_config.TextColumn(width="small"),
            "Nhận định nhanh": st.column_config.TextColumn(
                width="large",
                help="Kết hợp xếp hạng VN100 mới nhất với tác động riêng của sự kiện.",
            ),
        },
    )
    completed_at = snapshot.get("completed_at")
    try:
        ranking_time = datetime.datetime.fromisoformat(completed_at).strftime(
            "%d/%m/%Y %H:%M"
        )
    except (TypeError, ValueError):
        ranking_time = "chưa rõ thời gian"
    st.caption(
        f"Nhận định dùng snapshot xếp hạng VN100 lúc {ranking_time}. Đây là bước "
        "sàng lọc để chọn mã nghiên cứu sâu hơn, không phải khuyến nghị mua tự động."
    )


def render_corporate_actions(
    company: Any,
    db: Any,
    *,
    refresh_result: dict[str, Any] | None = None,
) -> None:
    _render_capital_actions_style()
    cfg = (load_defaults().get("corporate_actions") or {}).copy()
    today = _today_vn()
    rows = load_corporate_actions(
        db,
        company.ticker,
        as_of_date=today,
        history_years=int(cfg.get("history_years", 5)),
        future_days=int(cfg.get("future_days", 365)),
    )

    st.markdown(
        f"""
<div class="ca-hero">
    <div class="ca-hero-row">
        <div>
            <div class="ca-kicker">Theo dõi quyền cổ đông</div>
            <h2 class="ca-title">Cổ tức, tăng vốn & quyền cổ đông - {_escape(company.ticker)}</h2>
            <p class="ca-copy">
                Xem cổ tức, cổ phiếu thưởng, quyền mua và tác động sau ngày chia quyền.
                Phần này tách giá điều chỉnh kỹ thuật khỏi lãi lỗ thực tế để đọc dễ hơn.
            </p>
            <div class="ca-pill-row">
                <span class="ca-pill">Dữ liệu đang lưu trong máy</span>
                <span class="ca-pill">Chỉ tải mới khi cần</span>
                <span class="ca-pill">Ghi rõ mốc trước/sau chia</span>
            </div>
        </div>
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )
    refresh_state_key = f"corporate_action_refresh_result_{company.ticker}"
    manual_refresh_result = st.session_state.pop(refresh_state_key, None)
    if st.button(
        f"Cập nhật sự kiện {company.ticker}",
        help="Bỏ qua cache 24 giờ, gọi nguồn sự kiện cho mã đang mở và lưu kết quả vào máy.",
    ):
        with st.spinner("Đang kiểm tra công bố mới..."):
            result = refresh_corporate_actions(db, company.ticker, force=True)
        st.session_state[refresh_state_key] = result
        st.rerun()

    displayed_refresh = manual_refresh_result or refresh_result
    if displayed_refresh and displayed_refresh.get("status") == "BACKGROUND":
        st.caption(
            "Đang kiểm tra công bố mới trong nền; dữ liệu đã lưu vẫn được hiển thị ngay."
        )
    elif displayed_refresh and displayed_refresh.get("status") == "ERROR":
        st.warning(f"Chưa kiểm tra được nguồn mới: {displayed_refresh.get('error')}")
    elif displayed_refresh and displayed_refresh.get("checked"):
        changed = int(displayed_refresh.get("inserted") or 0) + int(
            displayed_refresh.get("updated") or 0
        )
        if changed:
            st.success(f"Đã nhận {changed} sự kiện mới hoặc được điều chỉnh.")
        else:
            seen = int(displayed_refresh.get("seen") or 0)
            st.info(
                f"Đã kiểm tra nguồn và đọc {seen} sự kiện; không có bản ghi mới "
                "hoặc thay đổi."
            )
    else:
        st.caption("Dữ liệu đang trong thời hạn cache; không phát sinh lượt tải mới.")

    upcoming_rows = [row for row in rows if _anchor(row) and _anchor(row) > today]
    historical_rows = [row for row in rows if _anchor(row) and _anchor(row) <= today]
    nearest = min((_anchor(row) for row in upcoming_rows), default=None)
    days_to_nearest = (nearest - today).days if nearest else None

    _render_metric_grid(
        upcoming_count=len(upcoming_rows),
        nearest_days=days_to_nearest,
        historical_count=len(historical_rows),
    )
    _render_latest_payouts(rows, today)

    with st.expander("Hiểu nhanh các con số trong phần này"):
        st.markdown("""
- **Giá trong ngày chia quyền**: giá trước sự kiện và giá khi cổ tức hoặc quyền mua đã được tách ra.
- **Bạn nhận thêm**: tiền mặt, cổ phiếu mới hoặc quyền được mua cổ phiếu.
- **Tổng tài sản sau khi cộng quyền lợi**: ước tính bạn thực sự tăng hay giảm bao nhiêu sau khi cộng phần nhận thêm.
- **Sau khoảng 1 tuần/1 tháng**: giá tăng hay giảm tiếp so với ngày chia quyền. Đây chỉ là diễn biến giá, không khẳng định sự kiện là nguyên nhân duy nhất.
- **Lợi nhuận trên mỗi cổ phiếu (EPS)**: phần lợi nhuận tương ứng với một cổ phiếu. Khi số cổ phiếu tăng nhanh hơn lợi nhuận, phần này sẽ giảm.
            """)

    _section_head(
        "Sự kiện đã công bố trong 12 tháng tới",
        "Chỉ hiển thị sự kiện đã có công bố và ngày thực hiện.",
    )
    if not upcoming_rows:
        st.info(
            "Hiện chưa có sự kiện cổ tức, quyền mua hoặc tăng vốn nào trong 12 tháng tới "
            "đã được nguồn dữ liệu công bố. Điều này không có nghĩa doanh nghiệp chắc chắn sẽ không phát sinh sự kiện mới."
        )
    else:
        for row in sorted(upcoming_rows, key=_anchor):
            ratio = (
                float(row.exercise_ratio) if row.exercise_ratio is not None else None
            )
            cash = (
                float(row.cash_amount_vnd_per_share)
                if row.cash_amount_vnd_per_share is not None
                else None
            )
            issue_price = (
                float(row.issue_price_vnd) if row.issue_price_vnd is not None else None
            )
            analysis = analyze_corporate_action(
                event_type=row.event_type,
                current_price_vnd=company.current_price,
                shares_outstanding=company.shares_outstanding * 1_000_000.0,
                exercise_ratio=ratio,
                cash_amount_vnd_per_share=cash,
                issue_price_vnd=issue_price,
            )
            assessment = assess_corporate_action(
                event_type=row.event_type,
                analysis=analysis,
                attractive_dividend_yield_pct=float(
                    cfg.get("attractive_dividend_yield_pct", 5.0)
                ),
                dilution_warning_pct=float(cfg.get("dilution_warning_pct", 10.0)),
            )
            explanation = explain_upcoming_action(
                event_type=row.event_type,
                holding_shares=int(cfg.get("example_holding_shares", 1_000)),
                current_price_vnd=company.current_price,
                exercise_ratio=ratio,
                cash_amount_vnd_per_share=cash,
                issue_price_vnd=issue_price,
                analysis=analysis,
            )
            label = _EVENT_LABELS.get(row.event_type, row.event_type)
            anchor = _anchor(row)
            verdict_class = _verdict_class(assessment["verdict"])
            st.markdown(
                f"""
<div class="ca-card">
    <div class="ca-hero-row">
        <div>
            <div class="ca-kicker">{_escape(_date_role(row))} {_escape(anchor.strftime('%d/%m/%Y'))}</div>
            <div class="ca-card-title">{_escape(label)} - {_escape(row.title)}</div>
            <div class="ca-meta">Nguồn {_escape(row.source_site)} ({_escape(row.source_tier)})</div>
        </div>
        <span class="ca-verdict {verdict_class}">{_escape(assessment["verdict"])}</span>
    </div>
    <div class="ca-mini-grid">
        <div class="ca-mini">
            <div class="ca-mini-label">Tỷ lệ</div>
            <div class="ca-mini-value">{_escape(f"{ratio * 100:.1f}%" if ratio is not None else "Chưa có")}</div>
        </div>
        <div class="ca-mini">
            <div class="ca-mini-label">Giá dự kiến sau chia</div>
            <div class="ca-mini-value">{_escape(f"{_fmt_vnd(analysis['theoretical_ex_price_vnd'])} VND" if analysis.get("theoretical_ex_price_vnd") is not None else "Chưa tính được")}</div>
        </div>
        <div class="ca-mini">
            <div class="ca-mini-label">Tiền/cổ phiếu</div>
            <div class="ca-mini-value">{_escape(f"{_fmt_vnd(cash)} VND" if cash is not None else "Không có")}</div>
        </div>
        <div class="ca-mini">
            <div class="ca-mini-label">EPS có thể giảm</div>
            <div class="ca-mini-value">{_escape(f"{abs(float(analysis['eps_dilution_pct_before_new_profit'])):.1f}%" if analysis.get("eps_dilution_pct_before_new_profit") is not None else "Không áp dụng")}</div>
        </div>
    </div>
</div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander(
                f"Diễn giải dễ hiểu - {label} {anchor.strftime('%d/%m/%Y')}",
                expanded=False,
            ):
                st.markdown(
                    f"""
<div class="ca-explain">
    <p><strong>Nếu đang giữ 1.000 cổ phiếu:</strong> {_escape(explanation["what_you_receive"])}</p>
    <p><strong>Giá có thể điều chỉnh:</strong> {_escape(explanation["price_effect"])}</p>
    <p><strong>Cần theo dõi:</strong> {_escape(explanation["watch_for"])}</p>
    <p><strong>Kết luận:</strong> {_escape(explanation["simple_verdict"])}</p>
</div>
                    """,
                    unsafe_allow_html=True,
                )
                if assessment["verdict"] in {"CẦN THẬN TRỌNG", "THIẾU DỮ LIỆU"}:
                    st.warning(f"{assessment['verdict']}: {assessment['reason']}")
                else:
                    st.info(f"{assessment['verdict']}: {assessment['reason']}")
                if row.source_url:
                    st.link_button(
                        "Mở công bố nguồn",
                        row.source_url,
                        icon=":material/open_in_new:",
                    )
                elif row.source_tier != "OFFICIAL":
                    st.caption(
                        "Nguồn tổng hợp; cần đối chiếu VSDC/HOSE/HNX/IR trước quyết định đầu tư."
                    )

    _section_head(
        "Phân tích chuyên sâu các sự kiện đã qua",
        "Mặc định ẩn để tab gọn và tải nhanh hơn.",
    )
    show_history = st.toggle(
        "Xem tác động giá và lãi/lỗ sau các lần chia quyền",
        value=False,
        key=f"corporate_action_history_v2_{company.ticker}",
        help="Chỉ khi bật, hệ thống mới đọc chuỗi giá và tính phân tích lịch sử.",
    )
    if show_history:
        _render_historical_analysis(
            company=company,
            db=db,
            historical_rows=historical_rows,
            cfg=cfg,
        )
    else:
        st.caption(
            "Bật công tắc khi cần xem giá ngày chia quyền, tổng tài sản thực và "
            "diễn biến sau khoảng 1 tuần/1 tháng."
        )

    with phone_collapsible("Lịch quyền VN100 sắp tới"):
        _render_vn100_upcoming_calendar(
            db=db,
            today=today,
            future_days=int(cfg.get("market_upcoming_days", 90)),
        )
