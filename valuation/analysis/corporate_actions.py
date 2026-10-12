"""Công thức thuần để lượng hóa tác động cơ học của quyền cổ đông."""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from math import isfinite
from typing import Any

_SHARE_GRANT_TYPES = {
    "STOCK_DIVIDEND",
    "BONUS_SHARE",
    "STOCK_BONUS_COMBO",
}

_SHARE_DILUTION_TYPES = {
    *_SHARE_GRANT_TYPES,
    "RIGHTS_ISSUE",
    "ESOP",
    "PRIVATE_PLACEMENT",
    "SHARE_ISSUE",
}

_UNRATEABLE_FLAG_CODES = {
    "DATA_REVIEW_REQUIRED",
    "NOT_RATED",
    "NOT_RATEABLE",
    "PROXY_IMPLAUSIBLE",
    "SOURCE_CONFLICT",
    "VALUATION_PROXY",
}


def analyze_corporate_action(
    *,
    event_type: str,
    current_price_vnd: float,
    shares_outstanding: float,
    exercise_ratio: float | None = None,
    cash_amount_vnd_per_share: float | None = None,
    issue_price_vnd: float | None = None,
) -> dict[str, Any]:
    """Tính tác động lý thuyết; không suy đoán trường dữ liệu còn thiếu."""
    event_type = str(event_type or "OTHER").upper()
    price = float(current_price_vnd or 0.0)
    shares = float(shares_outstanding or 0.0)
    ratio = float(exercise_ratio) if exercise_ratio is not None else None
    cash = (
        float(cash_amount_vnd_per_share)
        if cash_amount_vnd_per_share is not None
        else None
    )
    issue_price = float(issue_price_vnd) if issue_price_vnd is not None else None

    out: dict[str, Any] = {
        "dividend_yield_pct": None,
        "theoretical_ex_price_vnd": None,
        "right_value_vnd_per_old_share": None,
        "shares_after": None,
        "eps_dilution_pct_before_new_profit": None,
        "cash_raised_billion_vnd": None,
        "data_warning": None,
    }

    if event_type == "CASH_DIVIDEND":
        if price <= 0 or cash is None or cash < 0:
            out["data_warning"] = "Thiếu thị giá hoặc mức cổ tức tiền mặt hợp lệ."
            return out
        out["dividend_yield_pct"] = cash / price * 100.0
        out["theoretical_ex_price_vnd"] = max(price - cash, 0.0)
        return out

    if event_type not in _SHARE_DILUTION_TYPES:
        return out

    if ratio is None or ratio <= 0 or shares <= 0:
        out["data_warning"] = "Thiếu tỷ lệ thực hiện hoặc số cổ phiếu lưu hành hợp lệ."
        return out

    out["shares_after"] = shares * (1.0 + ratio)
    out["eps_dilution_pct_before_new_profit"] = (1.0 / (1.0 + ratio) - 1.0) * 100.0

    if event_type in _SHARE_GRANT_TYPES:
        if price <= 0:
            out["data_warning"] = "Thiếu thị giá để tính giá tham chiếu lý thuyết."
            return out
        out["theoretical_ex_price_vnd"] = price / (1.0 + ratio)
        return out

    if event_type == "RIGHTS_ISSUE":
        if issue_price is None or issue_price < 0:
            out["data_warning"] = (
                "Thiếu giá phát hành quyền mua; không tính TERP hoặc giá trị quyền bằng giả định."
            )
            return out
        if price <= 0:
            out["data_warning"] = "Thiếu thị giá để tính TERP."
            return out
        terp = (price + ratio * issue_price) / (1.0 + ratio)
        out["theoretical_ex_price_vnd"] = terp
        out["right_value_vnd_per_old_share"] = price - terp
        out["cash_raised_billion_vnd"] = shares * ratio * issue_price / 1_000_000_000.0
        return out

    if issue_price is not None and issue_price >= 0:
        out["cash_raised_billion_vnd"] = shares * ratio * issue_price / 1_000_000_000.0
    return out


def assess_corporate_action(
    *,
    event_type: str,
    analysis: dict[str, Any],
    attractive_dividend_yield_pct: float,
    dilution_warning_pct: float,
) -> dict[str, str]:
    """Phân loại thận trọng; sự kiện đơn lẻ không tạo khuyến nghị mua."""
    event_type = str(event_type or "OTHER").upper()
    warning = analysis.get("data_warning")
    if warning:
        return {
            "verdict": "THIẾU DỮ LIỆU",
            "reason": str(warning),
        }

    if event_type == "CASH_DIVIDEND":
        dividend_yield = float(analysis.get("dividend_yield_pct") or 0.0)
        verdict = (
            "TÍCH CỰC"
            if dividend_yield >= attractive_dividend_yield_pct
            else "TRUNG TÍNH"
        )
        return {
            "verdict": verdict,
            "reason": (
                f"Tiền cổ tức tương đương {dividend_yield:.1f}% thị giá. Cần xem "
                "doanh nghiệp có đủ tiền và có thể trả đều trong tương lai hay không."
            ),
        }

    if event_type in {"STOCK_DIVIDEND", "BONUS_SHARE"}:
        return {
            "verdict": "TRUNG TÍNH",
            "reason": (
                "Số cổ phiếu và giá tham chiếu cùng điều chỉnh; bản thân chia cổ phiếu "
                "không tạo thêm giá trị doanh nghiệp."
            ),
        }

    dilution = abs(float(analysis.get("eps_dilution_pct_before_new_profit") or 0.0))
    if event_type in {"RIGHTS_ISSUE", "ESOP", "PRIVATE_PLACEMENT", "SHARE_ISSUE"}:
        verdict = "CẦN THẬN TRỌNG" if dilution >= dilution_warning_pct else "TRUNG TÍNH"
        return {
            "verdict": verdict,
            "reason": (
                f"Lợi nhuận trên mỗi cổ phiếu (EPS) có thể giảm {dilution:.1f}% nếu "
                "lợi nhuận chưa tăng. Cần xem giá bán cổ phiếu mới và tiền huy động "
                "được dùng có hiệu quả hay không."
            ),
        }

    return {
        "verdict": "THÔNG TIN",
        "reason": "Sự kiện triển khai/niêm yết; cần tránh tính pha loãng lần thứ hai.",
    }


def _event_investment_note(
    event_type: str,
    event_analysis: dict[str, Any],
) -> str:
    event_type = str(event_type or "OTHER").upper()
    warning = event_analysis.get("data_warning")
    if warning:
        return "Sự kiện còn thiếu dữ liệu nên chưa tính được tác động đầy đủ."
    if event_type == "CASH_DIVIDEND":
        dividend_yield = event_analysis.get("dividend_yield_pct")
        if isinstance(dividend_yield, (int, float)) and isfinite(dividend_yield):
            return (
                f"Cổ tức tiền mặt {float(dividend_yield):.1f}% là điểm hỗ trợ, "
                "nhưng không đủ để tự quyết định mua."
            )
        return "Chưa đủ dữ liệu để tính tỷ suất cổ tức trên thị giá."
    if event_type in _SHARE_GRANT_TYPES:
        return "Chia thêm cổ phiếu không tự tạo thêm giá trị doanh nghiệp."
    if event_type == "RIGHTS_ISSUE":
        if event_analysis.get("right_value_vnd_per_old_share") is None:
            return (
                "Thiếu giá phát hành nên chưa biết quyền mua có thực sự rẻ hay không."
            )
        return "Quyền mua có giá trị, nhưng cần kiểm tra hiệu quả sử dụng vốn mới."
    if event_type in {"ESOP", "PRIVATE_PLACEMENT", "SHARE_ISSUE"}:
        dilution = event_analysis.get("eps_dilution_pct_before_new_profit")
        if isinstance(dilution, (int, float)) and isfinite(dilution):
            return (
                f"Có thể pha loãng EPS khoảng {abs(float(dilution)):.1f}% "
                "nếu lợi nhuận chưa tăng."
            )
        return "Có rủi ro pha loãng; cần biết tỷ lệ, giá phát hành và mục đích vốn."
    if event_type == "ADDITIONAL_LISTING":
        return "Đây là bước niêm yết, không phải quyền lợi mới; nguồn cung có thể tăng."
    return "Sự kiện này chưa đủ để thay đổi luận điểm đầu tư tổng thể."


def _ranking_data_caveat(ranking_row: dict[str, Any]) -> str | None:
    codes = {str(flag).split(":", 1)[0] for flag in ranking_row.get("flags", [])}
    caveats = []
    if "STALE_PRICE" in codes:
        caveats.append("giá xếp hạng cần cập nhật")
    reasons = {
        reason
        for profile in ranking_row.get("profiles", {}).values()
        for reason in profile.get("reasons", [])
    }
    if "Chưa đạt tiêu chí chất lượng" in reasons:
        caveats.append("chất lượng kinh doanh chưa đạt")
    if "Chưa đạt tiêu chí sức khỏe tài chính" in reasons:
        caveats.append("sức khỏe tài chính chưa đạt")
    if "Thanh khoản thiếu dữ liệu hoặc dưới ngưỡng" in reasons:
        caveats.append("thanh khoản chưa được xác nhận")
    return ", ".join(caveats[:2]) if caveats else None


def quick_investment_opinion(
    *,
    event_type: str,
    event_analysis: dict[str, Any],
    ranking_row: dict[str, Any] | None,
) -> str:
    """Nhận định sàng lọc ngắn; sự kiện đơn lẻ không được nâng mã thành khuyến nghị."""
    event_note = _event_investment_note(event_type, event_analysis)
    if not ranking_row:
        return (
            "CHƯA ĐỦ CƠ SỞ — chưa có hồ sơ xếp hạng mới nhất cho mã này. "
            f"{event_note}"
        )

    flags = {str(flag).split(":", 1)[0] for flag in ranking_row.get("flags", [])}
    profiles = ranking_row.get("profiles", {})
    profile_values = [
        profile for profile in profiles.values() if isinstance(profile, dict)
    ]
    scores = [
        float(profile["score"])
        for profile in profile_values
        if isinstance(profile.get("score"), (int, float)) and isfinite(profile["score"])
    ]
    eligible_profiles = [
        key
        for key, profile in profiles.items()
        if isinstance(profile, dict) and profile.get("eligible")
    ]
    upside = ranking_row.get("upside_pct")
    valid_upside = (
        isinstance(upside, (int, float))
        and not isinstance(upside, bool)
        and isfinite(upside)
    )

    unrateable = flags.intersection(_UNRATEABLE_FLAG_CODES)
    if ranking_row.get("error") or unrateable or not scores:
        check_errors = [
            str(check.get("message") or "").strip()
            for check in ranking_row.get("checks", [])
            if check.get("severity") == "error" and check.get("message")
        ]
        if "SOURCE_CONFLICT" in flags:
            return (
                "CẦN ĐỐI CHIẾU DỮ LIỆU — số liệu giữa các nguồn đang xung đột; "
                f"chưa nên xuống tiền. {event_note}"
            )
        if flags.intersection({"VALUATION_PROXY", "PROXY_IMPLAUSIBLE"}):
            method = str(ranking_row.get("method") or "định giá")
            return (
                f"CHƯA THỂ ĐỊNH GIÁ — mô hình {method} mới là bản tham chiếu, "
                f"chưa hoàn thiện để kết luận. {event_note}"
            )
        if check_errors:
            return (
                f"CẦN KIỂM TRA BCTC — {check_errors[0][:180]} "
                f"Chưa nên xuống tiền. {event_note}"
            )
        if ranking_row.get("error"):
            reason = str(ranking_row["error"])[:180]
        elif "DATA_REVIEW_REQUIRED" in flags:
            reason = "dữ liệu tài chính cần kiểm tra lại"
        else:
            reason = "chưa có định giá đủ tin cậy"
        return f"CHƯA ĐỦ CƠ SỞ — {reason}; chưa nên xuống tiền. {event_note}"

    caveat = _ranking_data_caveat(ranking_row)
    caveat_text = f"; lưu ý {caveat}" if caveat else ""
    if eligible_profiles:
        profile_label = (
            "thận trọng và tăng trưởng"
            if len(eligible_profiles) > 1
            else "thận trọng" if eligible_profiles[0] == "defensive" else "tăng trưởng"
        )
        valuation_text = (
            f", định giá còn dư địa {float(upside):+.1f}%" if valid_upside else ""
        )
        return (
            f"ĐÁNG NGHIÊN CỨU SÂU — đã qua bộ lọc tích sản {profile_label}"
            f"{valuation_text}{caveat_text}. {event_note}"
        )

    if valid_upside and float(upside) < 0:
        return (
            "CHƯA HẤP DẪN — giá trị hợp lý đang thấp hơn thị giá "
            f"{abs(float(upside)):.1f}%{caveat_text}; chưa nên mua chỉ vì sự kiện. "
            f"{event_note}"
        )
    if valid_upside:
        return (
            f"THEO DÕI, CHƯA VỘI MUA — định giá còn dư địa {float(upside):+.1f}% "
            f"nhưng chưa qua bộ lọc tích sản{caveat_text}. {event_note}"
        )
    return f"CHƯA ĐỦ CƠ SỞ — chưa có định giá sử dụng được. {event_note}"


def _pct(current: float, base: float) -> float | None:
    if base <= 0:
        return None
    return (current / base - 1.0) * 100.0


def analyze_historical_price_impact(
    *,
    prices: Iterable[dict[str, Any]],
    event_date: datetime.date,
    event_type: str,
    exercise_ratio: float | None = None,
    cash_amount_vnd_per_share: float | None = None,
    issue_price_vnd: float | None = None,
    short_sessions: int = 5,
    long_sessions: int = 20,
    adjusted_series_suspicion_pct: float = 20.0,
) -> dict[str, Any]:
    """Đo phản ứng giá quanh sự kiện và tách phần điều chỉnh cơ học.

    Đây là event study mô tả, không khẳng định quan hệ nhân quả. Giá trước sự
    kiện là phiên gần nhất trước mốc; giá sự kiện là phiên đầu tiên tại/sau mốc.
    """

    normalized = []
    for item in prices:
        trade_date = item.get("date") or item.get("trade_date")
        close = item.get("close")
        if isinstance(trade_date, datetime.datetime):
            trade_date = trade_date.date()
        if not isinstance(trade_date, datetime.date):
            continue
        try:
            close_value = float(close)
        except (TypeError, ValueError):
            continue
        if close_value > 0:
            normalized.append((trade_date, close_value))
    normalized = sorted(dict(normalized).items())

    before = [(day, close) for day, close in normalized if day < event_date]
    after = [(day, close) for day, close in normalized if day >= event_date]
    if not before or not after:
        return {
            "available": False,
            "data_warning": "Không đủ giá trước và sau sự kiện để đo phản ứng.",
        }

    before_date, price_before = before[-1]
    event_trade_date, price_event = after[0]
    event_index = normalized.index((event_trade_date, price_event))

    mechanical = analyze_corporate_action(
        event_type=event_type,
        current_price_vnd=price_before,
        shares_outstanding=1.0,
        exercise_ratio=exercise_ratio,
        cash_amount_vnd_per_share=cash_amount_vnd_per_share,
        issue_price_vnd=issue_price_vnd,
    )
    theoretical = mechanical.get("theoretical_ex_price_vnd")
    theoretical = float(theoretical) if theoretical is not None else None

    wealth_change = None
    event_type = str(event_type or "").upper()
    market_reaction = (
        _pct(price_event, theoretical) if theoretical is not None else None
    )
    price_series_adjusted = False
    estimated_unadjusted_price_before = None
    if event_type == "CASH_DIVIDEND" and cash_amount_vnd_per_share is not None:
        wealth_change = _pct(
            price_event + float(cash_amount_vnd_per_share), price_before
        )
    elif event_type in _SHARE_GRANT_TYPES and exercise_ratio:
        ratio = float(exercise_ratio)
        if (
            market_reaction is not None
            and market_reaction > adjusted_series_suspicion_pct
        ):
            # Một số nguồn đã đưa giá trước ngày GDKHQ về cùng mặt bằng sau chia.
            # Khi đó không cộng thêm cổ phiếu lần nữa, nếu không sẽ double-count.
            price_series_adjusted = True
            estimated_unadjusted_price_before = price_before * (1.0 + ratio)
            theoretical = price_before
            market_reaction = _pct(price_event, theoretical)
            wealth_change = _pct(price_event, price_before)
        else:
            wealth_change = _pct(price_event * (1.0 + ratio), price_before)
    elif (
        event_type == "RIGHTS_ISSUE"
        and mechanical.get("right_value_vnd_per_old_share") is not None
    ):
        wealth_change = _pct(
            price_event + float(mechanical["right_value_vnd_per_old_share"]),
            price_before,
        )

    def _after_return(sessions: int) -> float | None:
        target_index = event_index + sessions
        if target_index >= len(normalized):
            return None
        return _pct(normalized[target_index][1], price_event)

    return {
        "available": True,
        "event_date": event_date.isoformat(),
        "price_before_date": before_date.isoformat(),
        "event_trade_date": event_trade_date.isoformat(),
        "price_before_vnd": price_before,
        "price_event_vnd": price_event,
        "raw_event_return_pct": _pct(price_event, price_before),
        "theoretical_ex_price_vnd": theoretical,
        "price_series_adjusted": price_series_adjusted,
        "estimated_unadjusted_price_before_vnd": estimated_unadjusted_price_before,
        "mechanical_adjustment_pct": (
            _pct(theoretical, price_before) if theoretical is not None else None
        ),
        "market_reaction_vs_theoretical_pct": market_reaction,
        "shareholder_wealth_change_pct": wealth_change,
        "exercise_ratio": exercise_ratio,
        "cash_amount_vnd_per_share": cash_amount_vnd_per_share,
        "issue_price_vnd": issue_price_vnd,
        "return_after_5_sessions_pct": _after_return(short_sessions),
        "return_after_20_sessions_pct": _after_return(long_sessions),
        "data_warning": (
            None
            if event_index + long_sessions < len(normalized)
            else f"Chưa đủ {long_sessions} phiên sau sự kiện."
        ),
    }


def _fmt_number_vi(value: float) -> str:
    return f"{float(value):,.0f}".replace(",", ".")


def explain_historical_price_impact(
    *,
    event_type: str,
    impact: dict[str, Any],
    reaction_materiality_pct: float,
) -> dict[str, str]:
    """Chuyển event-study thành lời giải thích dễ đọc, không gán quan hệ nhân quả."""
    if not impact.get("available"):
        warning = str(impact.get("data_warning") or "Không đủ dữ liệu giá.")
        return {
            "reaction_label": "CHƯA ĐỦ DỮ LIỆU",
            "price_explanation": warning,
            "wealth_explanation": "Không thể đánh giá phản ứng của cổ đông.",
            "follow_through": "Không có đủ phiên giao dịch để theo dõi sau sự kiện.",
        }

    raw = float(impact.get("raw_event_return_pct") or 0.0)
    wealth = impact.get("shareholder_wealth_change_pct")
    short_return = impact.get("return_after_5_sessions_pct")
    long_return = impact.get("return_after_20_sessions_pct")

    if wealth is None:
        label = "CHƯA TÍNH ĐƯỢC TỔNG TÀI SẢN"
    elif float(wealth) > reaction_materiality_pct:
        label = "TỔNG TÀI SẢN TĂNG"
    elif float(wealth) < -reaction_materiality_pct:
        label = "TỔNG TÀI SẢN GIẢM"
    else:
        label = "TỔNG TÀI SẢN GẦN NHƯ KHÔNG ĐỔI"

    price_before = float(impact["price_before_vnd"])
    price_event = float(impact["price_event_vnd"])
    price_change = price_event - price_before
    if price_change > 0:
        movement = f"tăng {_fmt_number_vi(price_change)} VND"
    elif price_change < 0:
        movement = f"giảm {_fmt_number_vi(abs(price_change))} VND"
    else:
        movement = "không đổi"
    if impact.get("price_series_adjusted"):
        estimated_raw = impact.get("estimated_unadjusted_price_before_vnd")
        raw_note = (
            f", tương đương khoảng {_fmt_number_vi(float(estimated_raw))} VND "
            "nếu quy ngược về giá trước khi chia"
            if estimated_raw is not None
            else ""
        )
        price_text = (
            "Dữ liệu giá trước sự kiện đã được điều chỉnh về cùng mặt bằng sau chia: "
            f"{_fmt_number_vi(price_before)} VND{raw_note}. Trong ngày chia quyền, "
            f"giá là {_fmt_number_vi(price_event)} VND, {movement} ({raw:+.1f}%) "
            "so với mốc đã điều chỉnh."
        )
    else:
        price_text = (
            f"Trước ngày chia quyền, giá là {_fmt_number_vi(price_before)} VND. "
            f"Trong ngày chia quyền, giá là {_fmt_number_vi(price_event)} VND, "
            f"{movement} ({raw:+.1f}%)."
        )

    event_type = str(event_type or "").upper()
    if wealth is None:
        wealth_text = (
            "Chưa đủ thông tin về tỷ lệ, tiền nhận hoặc giá mua để tính tổng tài sản "
            "sau khi nhận quyền lợi."
        )
    elif event_type == "CASH_DIVIDEND":
        cash = float(impact.get("cash_amount_vnd_per_share") or 0.0)
        wealth_text = (
            f"Bạn nhận thêm {_fmt_number_vi(cash)} VND tiền mặt cho mỗi cổ phiếu. "
            f"Sau khi cộng khoản tiền này, tổng tài sản thay đổi {float(wealth):+.1f}%."
        )
    elif event_type in _SHARE_GRANT_TYPES:
        ratio = float(impact.get("exercise_ratio") or 0.0) * 100.0
        if impact.get("price_series_adjusted"):
            wealth_text = (
                f"Cứ 100 cổ phiếu đang có, bạn nhận thêm khoảng {ratio:g} cổ phiếu. "
                "Vì dữ liệu giá đã điều chỉnh quyền, hệ thống không cộng thêm cổ phiếu "
                f"lần nữa. So trên cùng mặt bằng sau chia, tổng tài sản thay đổi "
                f"{float(wealth):+.1f}%."
            )
        else:
            wealth_text = (
                f"Cứ 100 cổ phiếu đang có, bạn nhận thêm khoảng {ratio:g} cổ phiếu. "
                f"Sau khi cộng số cổ phiếu mới, tổng tài sản thay đổi {float(wealth):+.1f}%."
            )
    else:
        ratio = float(impact.get("exercise_ratio") or 0.0) * 100.0
        issue_price = impact.get("issue_price_vnd")
        price_note = (
            f" với giá {_fmt_number_vi(float(issue_price))} VND/cổ phiếu"
            if issue_price is not None
            else ""
        )
        wealth_text = (
            f"Cứ 100 cổ phiếu đang có, bạn được mua thêm khoảng {ratio:g} cổ phiếu"
            f"{price_note}. Sau khi cộng giá trị quyền mua, tổng tài sản thay đổi "
            f"{float(wealth):+.1f}%."
        )

    pieces = []
    if short_return is not None:
        pieces.append(f"sau khoảng 1 tuần {float(short_return):+.1f}%")
    if long_return is not None:
        pieces.append(f"sau khoảng 1 tháng {float(long_return):+.1f}%")
    follow = (
        "So với giá trong ngày chia quyền, tức mốc đã chia xong: "
        + ", ".join(pieces)
        + "."
        if pieces
        else "Chưa đủ dữ liệu để xem giá thay đổi thế nào sau sự kiện."
    )
    return {
        "reaction_label": label,
        "price_explanation": price_text,
        "wealth_explanation": wealth_text,
        "follow_through": follow,
    }


def explain_upcoming_action(
    *,
    event_type: str,
    holding_shares: int,
    current_price_vnd: float,
    exercise_ratio: float | None,
    cash_amount_vnd_per_share: float | None,
    issue_price_vnd: float | None,
    analysis: dict[str, Any],
) -> dict[str, str]:
    """Diễn giải tác động bằng ví dụ tài khoản phổ thông, không hô hào đầu tư."""
    event_type = str(event_type or "OTHER").upper()
    ratio = float(exercise_ratio or 0.0)
    holding = int(holding_shares)
    price = float(current_price_vnd or 0.0)
    theoretical = analysis.get("theoretical_ex_price_vnd")

    if event_type == "CASH_DIVIDEND":
        cash = float(cash_amount_vnd_per_share or 0.0)
        gross = holding * cash
        return {
            "what_you_receive": (
                f"Nếu đang giữ {_fmt_number_vi(holding)} cổ phiếu, bạn nhận khoảng "
                f"{_fmt_number_vi(gross)} VND tiền mặt trước thuế."
            ),
            "price_effect": (
                f"Trong ngày chia quyền, giá thường được điều chỉnh giảm khoảng "
                f"{_fmt_number_vi(cash)} VND/cổ phiếu, từ {_fmt_number_vi(price)} "
                f"xuống khoảng {_fmt_number_vi(theoretical or 0)} VND."
            ),
            "watch_for": "Cần xem dòng tiền có đủ trả đều và doanh nghiệp còn vốn để tăng trưởng hay không.",
            "simple_verdict": "Cổ tức là tiền thật nhận về, nhưng không phải tiền miễn phí vì giá cổ phiếu điều chỉnh tương ứng.",
        }

    if event_type in _SHARE_GRANT_TYPES:
        new_shares = holding * ratio
        total = holding + new_shares
        return {
            "what_you_receive": (
                f"Nếu đang giữ {_fmt_number_vi(holding)} cổ phiếu, bạn nhận thêm "
                f"{_fmt_number_vi(new_shares)} cổ phiếu mới và có tổng cộng "
                f"{_fmt_number_vi(total)} cổ phiếu."
            ),
            "price_effect": (
                f"Giá dự kiến giảm từ {_fmt_number_vi(price)} xuống khoảng "
                f"{_fmt_number_vi(theoretical or 0)} VND. Bạn có nhiều cổ phiếu hơn "
                "nên tổng giá trị ngay sau chia gần như không đổi."
            ),
            "watch_for": "Quan trọng nhất là lợi nhuận tương lai có tăng đủ nhanh để EPS phục hồi sau khi số cổ phiếu tăng hay không.",
            "simple_verdict": "Nhận thêm cổ phiếu nhưng giá mỗi cổ phiếu giảm tương ứng, nên sự kiện không tự tạo thêm giá trị.",
        }

    if event_type == "RIGHTS_ISSUE":
        buy_shares = holding * ratio
        what = (
            f"Nếu đang giữ {_fmt_number_vi(holding)} cổ phiếu, bạn có quyền mua thêm "
            f"{_fmt_number_vi(buy_shares)} cổ phiếu."
        )
        if issue_price_vnd is None:
            return {
                "what_you_receive": what,
                "price_effect": "Chưa có giá phát hành nên chưa thể tính số tiền cần nộp, TERP hoặc giá trị quyền.",
                "watch_for": "Theo dõi giá phát hành, thời hạn đăng ký, khả năng chuyển nhượng quyền và mục đích sử dụng vốn.",
                "simple_verdict": "Không thể kết luận quyền mua hấp dẫn khi chưa có giá phát hành và kế hoạch dùng vốn.",
            }
        capital = buy_shares * float(issue_price_vnd)
        return {
            "what_you_receive": what,
            "price_effect": (
                f"Bạn cần nộp khoảng {_fmt_number_vi(capital)} VND để mua. Sau khi "
                f"tách quyền mua, giá dự kiến khoảng {_fmt_number_vi(theoretical or 0)} VND."
            ),
            "watch_for": "Nếu không thực hiện hoặc bán quyền đúng hạn, tỷ lệ sở hữu sẽ bị pha loãng.",
            "simple_verdict": "Quyền mua chỉ đáng chú ý khi giá đủ rẻ và vốn mới tạo lợi nhuận cao hơn chi phí vốn.",
        }

    if event_type in {"ESOP", "PRIVATE_PLACEMENT", "SHARE_ISSUE"}:
        dilution = abs(float(analysis.get("eps_dilution_pct_before_new_profit") or 0.0))
        return {
            "what_you_receive": "Cổ đông hiện hữu thường không nhận thêm cổ phiếu từ đợt phát hành này.",
            "price_effect": (
                f"Lợi nhuận trên mỗi cổ phiếu (EPS) có thể giảm khoảng {dilution:.1f}% "
                "nếu tiền mới chưa tạo thêm lợi nhuận."
            ),
            "watch_for": "Cần xem giá phát hành có thấp hơn nhiều so thị giá, người mua là ai, hạn chế chuyển nhượng và ROIC dự kiến.",
            "simple_verdict": "Có rủi ro pha loãng; chỉ tích cực nếu vốn mới được dùng hiệu quả và lợi nhuận tăng đủ bù.",
        }

    if event_type == "ADDITIONAL_LISTING":
        return {
            "what_you_receive": "Đây thường là bước hoàn tất niêm yết số cổ phiếu đã phát hành trước đó.",
            "price_effect": "Không nên tính thêm một lần pha loãng tại ngày niêm yết nếu giá đã điều chỉnh ở ngày hưởng quyền/phát hành.",
            "watch_for": "Theo dõi ngày cổ phiếu mới được giao dịch vì nguồn cung có thể tăng trong ngắn hạn.",
            "simple_verdict": "Đây là bước thực hiện, không phải một khoản lợi ích mới cho cổ đông.",
        }

    return {
        "what_you_receive": "Quyền lợi trực tiếp chưa đủ rõ từ dữ liệu hiện có.",
        "price_effect": "Chưa đủ dữ liệu để ước tính giá sẽ thay đổi bao nhiêu.",
        "watch_for": "Đối chiếu nghị quyết và công bố chính thức trước khi hành động.",
        "simple_verdict": "Chưa đủ cơ sở kết luận sự kiện tích cực hay tiêu cực.",
    }
