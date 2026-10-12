"""So sánh hai lần chạy hiệu chuẩn — hàng rào chống hồi quy.

Đây là phần cốt lõi của GĐ0. Bài học tháng 7/2026 (DECISIONS.md D20): sửa
undervaluation ngân hàng làm nhóm RI_PB đi từ ~-25% sang +10.7% — dịch 35 điểm
phần trăm, xuyên qua band ra phía bên kia. Tổng thể nhìn "khá hơn" nên không ai
phát hiện. `RULE_METHOD_SHIFT` bên dưới sinh ra để chặn đúng kịch bản đó.

Triết lý: KHÔNG tự động chặn mọi thay đổi làm một mã xấu đi — mô hình có quyền
bất đồng với CTCK. Chỉ chặn khi (a) sinh lỗi mới, (b) đẩy mã ra khỏi band nhiều
hơn kéo vào, (c) một nhóm phương pháp dịch chuyển bất thường, hoặc (d) sinh ra
FV thấp hơn thị giá một cách phi lý.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from valuation.calibration.metrics import (
    BELOW_PRICE_ALARM,
    ERROR,
    IN_BAND,
    NO_CONSENSUS,
    Observation,
)

# Ngưỡng mặc định — ghi đè qua config/calibration_rules.yaml
DEFAULT_RULES: dict[str, float] = {
    # Bỏ qua dao động nhỏ hơn mức này khi phán IMPROVED/WORSENED (nhiễu giá thị trường).
    "tol": 0.02,
    # Lệch tuyệt đối median toàn cục được phép xấu đi tối đa bao nhiêu.
    "max_overall_regression": 0.01,
    # Nhóm phương pháp phải có ít nhất bấy nhiêu mã mới áp rule dịch chuyển.
    "min_method_n": 3,
    # Lệch median CÓ DẤU của một nhóm PP được phép dịch tối đa bao nhiêu.
    "max_method_shift": 0.15,
}

# Verdict
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

# Mã rule (để thông điệp vi phạm truy ngược được về tài liệu)
RULE_NEW_ERRORS = "NEW_ERRORS"
RULE_BAND_NET_LOSS = "BAND_NET_LOSS"
RULE_OVERALL_REGRESSION = "OVERALL_REGRESSION"
RULE_METHOD_SHIFT = "METHOD_SHIFT"
RULE_BELOW_PRICE = "NEW_BELOW_PRICE_ALARM"


@dataclass(frozen=True)
class TickerDelta:
    ticker: str
    method: Optional[str]
    dev_before: Optional[float]
    dev_after: Optional[float]
    band_before: str
    band_after: str
    verdict: str


@dataclass(frozen=True)
class RunDiff:
    baseline_label: str
    candidate_label: str
    deltas: tuple[TickerDelta, ...]
    counts: dict[str, int]
    aggregate_before: dict[str, Any]
    aggregate_after: dict[str, Any]
    violations: tuple[str, ...]
    verdict: str


def _classify_delta(before: Observation, after: Observation, tol: float) -> str:
    """Phán xét thay đổi của 1 mã.

    Ưu tiên trạng thái band hơn độ lớn: band là đơn vị quản trị (một mã vào band
    quan trọng hơn một mã đã trong band nhích thêm vài %).
    """
    if before.error and not after.error:
        return "FIXED_ERROR"
    if after.error and not before.error:
        return "NEW_ERROR"
    if before.band_status == NO_CONSENSUS and after.band_status != NO_CONSENSUS:
        return "NEW_COVERAGE"
    if after.band_status == NO_CONSENSUS and before.band_status != NO_CONSENSUS:
        return "LOST_COVERAGE"

    if before.band_status != IN_BAND and after.band_status == IN_BAND:
        return "ENTERED_BAND"
    if before.band_status == IN_BAND and after.band_status not in (IN_BAND, NO_CONSENSUS, ERROR):
        return "LEFT_BAND"

    d_before, d_after = before.dev_vs_consensus, after.dev_vs_consensus
    if d_before is None or d_after is None:
        return "UNCHANGED"
    if abs(d_after) < abs(d_before) - tol:
        return "IMPROVED"
    if abs(d_after) > abs(d_before) + tol:
        return "WORSENED"
    return "UNCHANGED"


def compare_runs(
    baseline: "Any",
    candidate: "Any",
    tol: Optional[float] = None,
    rules: Optional[dict[str, float]] = None,
) -> RunDiff:
    """So sánh 2 CalibrationRun, trả RunDiff kèm verdict PASS/WARN/FAIL."""
    cfg = {**DEFAULT_RULES, **(rules or {})}
    tol = cfg["tol"] if tol is None else tol

    before_by = {o.ticker: o for o in baseline.observations}
    after_by = {o.ticker: o for o in candidate.observations}

    deltas: list[TickerDelta] = []
    for ticker in sorted(set(before_by) | set(after_by)):
        b, a = before_by.get(ticker), after_by.get(ticker)
        if b is None or a is None:
            # Mã chỉ có ở 1 run (đổi rổ VN100) — ghi nhận, không phán xét.
            ref = a or b
            deltas.append(TickerDelta(
                ticker=ticker, method=ref.method,
                dev_before=(b.dev_vs_consensus if b else None),
                dev_after=(a.dev_vs_consensus if a else None),
                band_before=(b.band_status if b else "ABSENT"),
                band_after=(a.band_status if a else "ABSENT"),
                verdict="ADDED" if b is None else "REMOVED",
            ))
            continue
        deltas.append(TickerDelta(
            ticker=ticker, method=a.method,
            dev_before=b.dev_vs_consensus, dev_after=a.dev_vs_consensus,
            band_before=b.band_status, band_after=a.band_status,
            verdict=_classify_delta(b, a, tol),
        ))

    counts: dict[str, int] = {}
    for d in deltas:
        counts[d.verdict] = counts.get(d.verdict, 0) + 1

    agg_b, agg_a = baseline.aggregates, candidate.aggregates
    violations: list[str] = []

    # Rule 1 — lỗi định giá mới
    n_new_err = counts.get("NEW_ERROR", 0)
    if n_new_err > 0:
        bad = [d.ticker for d in deltas if d.verdict == "NEW_ERROR"]
        violations.append(f"{RULE_NEW_ERRORS}: {n_new_err} mã sinh lỗi mới ({', '.join(bad[:8])})")

    # Rule 2 — đẩy ra khỏi band nhiều hơn kéo vào
    left, entered = counts.get("LEFT_BAND", 0), counts.get("ENTERED_BAND", 0)
    if left > entered:
        violations.append(
            f"{RULE_BAND_NET_LOSS}: {left} mã rời band nhưng chỉ {entered} mã vào band"
        )

    # Rule 3 — lệch tuyệt đối toàn cục xấu đi
    mad_b = (agg_b.get("overall") or {}).get("median_abs_dev")
    mad_a = (agg_a.get("overall") or {}).get("median_abs_dev")
    if mad_b is not None and mad_a is not None:
        if mad_a > mad_b + cfg["max_overall_regression"]:
            violations.append(
                f"{RULE_OVERALL_REGRESSION}: |lệch| median toàn cục {mad_b:+.1%} → {mad_a:+.1%}"
            )

    # Rule 4 — nhóm phương pháp dịch chuyển bất thường (canh đúng sự cố tháng 7)
    for method, stats_a in (agg_a.get("by_method") or {}).items():
        stats_b = (agg_b.get("by_method") or {}).get(method)
        if not stats_b:
            continue
        n = min(stats_a.get("n_with_consensus") or 0, stats_b.get("n_with_consensus") or 0)
        if n < cfg["min_method_n"]:
            continue
        d_b, d_a = stats_b.get("median_dev"), stats_a.get("median_dev")
        if d_b is None or d_a is None:
            continue
        shift = d_a - d_b
        if abs(shift) > cfg["max_method_shift"]:
            violations.append(
                f"{RULE_METHOD_SHIFT}: nhóm {method} (n={n}) lệch median dịch "
                f"{d_b:+.1%} → {d_a:+.1%} ({shift:+.1%}, ngưỡng ±{cfg['max_method_shift']:.0%})"
            )

    # Rule 5 — mã mới rơi xuống dưới thị giá quá sâu
    newly_below: list[str] = []
    for ticker, a in after_by.items():
        b = before_by.get(ticker)
        if b is None:
            continue
        was_ok = b.dev_vs_price is None or b.dev_vs_price > -BELOW_PRICE_ALARM
        now_bad = a.dev_vs_price is not None and a.dev_vs_price <= -BELOW_PRICE_ALARM
        if was_ok and now_bad:
            newly_below.append(ticker)
    if newly_below:
        violations.append(
            f"{RULE_BELOW_PRICE}: {len(newly_below)} mã có FV thấp hơn thị giá "
            f">{BELOW_PRICE_ALARM:.0%} ({', '.join(sorted(newly_below)[:8])})"
        )

    if violations:
        verdict = FAIL
    elif counts.get("WORSENED", 0) > counts.get("IMPROVED", 0):
        verdict = WARN
    else:
        verdict = PASS

    return RunDiff(
        baseline_label=baseline.label,
        candidate_label=candidate.label,
        deltas=tuple(deltas),
        counts=counts,
        aggregate_before=agg_b,
        aggregate_after=agg_a,
        violations=tuple(violations),
        verdict=verdict,
    )


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:+.1%}"


def render_diff_markdown(diff: RunDiff, max_rows: int = 25) -> str:
    """Bảng markdown dán thẳng vào DECISIONS.md (AGENTS.md yêu cầu ghi D-entry)."""
    lines: list[str] = []
    lines.append(f"**Hiệu chuẩn: `{diff.baseline_label}` → `{diff.candidate_label}` — {diff.verdict}**")
    lines.append("")

    ob, oa = diff.aggregate_before.get("overall", {}), diff.aggregate_after.get("overall", {})
    lines.append("| Chỉ số | Trước | Sau |")
    lines.append("|---|---|---|")
    lines.append(f"| Lệch median vs CTCK | {_pct(ob.get('median_dev'))} | {_pct(oa.get('median_dev'))} |")
    lines.append(f"| \\|Lệch\\| median | {_pct(ob.get('median_abs_dev'))} | {_pct(oa.get('median_abs_dev'))} |")
    lines.append(f"| Tỷ lệ trong band | {_pct(ob.get('share_in_band'))} | {_pct(oa.get('share_in_band'))} |")
    lines.append(f"| Số mã FV < thị giá 40% | {ob.get('n_below_price_40')} | {oa.get('n_below_price_40')} |")
    lines.append(f"| Số mã lỗi | {ob.get('n_errors')} | {oa.get('n_errors')} |")
    lines.append("")

    lines.append("| Nhóm PP | n | Lệch median trước | sau | dịch |")
    lines.append("|---|---|---|---|---|")
    for method, sa in sorted((diff.aggregate_after.get("by_method") or {}).items()):
        sb = (diff.aggregate_before.get("by_method") or {}).get(method, {})
        d_b, d_a = sb.get("median_dev"), sa.get("median_dev")
        shift = _pct(d_a - d_b) if (d_b is not None and d_a is not None) else "—"
        lines.append(f"| {method} | {sa.get('n_with_consensus')} | {_pct(d_b)} | {_pct(d_a)} | {shift} |")
    lines.append("")

    summary = ", ".join(f"{k}={v}" for k, v in sorted(diff.counts.items()))
    lines.append(f"Tổng hợp thay đổi: {summary}")
    lines.append("")

    notable = [d for d in diff.deltas if d.verdict not in ("UNCHANGED",)]
    notable.sort(key=lambda d: abs((d.dev_after or 0) - (d.dev_before or 0)), reverse=True)
    if notable:
        lines.append(f"| Mã | PP | Trước | Sau | Band | Kết luận |")
        lines.append("|---|---|---|---|---|---|")
        for d in notable[:max_rows]:
            band = f"{d.band_before}→{d.band_after}" if d.band_before != d.band_after else d.band_before
            lines.append(
                f"| {d.ticker} | {d.method or '—'} | {_pct(d.dev_before)} | "
                f"{_pct(d.dev_after)} | {band} | {d.verdict} |"
            )
        if len(notable) > max_rows:
            lines.append(f"| … | | | | | (+{len(notable) - max_rows} mã nữa) |")
        lines.append("")

    if diff.violations:
        lines.append("**Vi phạm hàng rào hồi quy:**")
        for v in diff.violations:
            lines.append(f"- 🚨 {v}")
    else:
        lines.append("_Không vi phạm hàng rào hồi quy._")

    return "\n".join(lines)
