"""Sàng lọc hai chiến lược bằng quy tắc minh bạch; không dự đoán lợi nhuận."""

from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

MATERIAL_MODEL_WARNING_PHRASES = (
    "chưa có đầy đủ lưu chuyển đầu tư/tài chính",  # dòng cảnh báo cũ (trước 02/09/2026)
    "Thiếu lưu chuyển đầu tư/tài chính",  # dòng gộp mới — xem models/financials.py
    "không tự tạo khoản bù",
    "vượt ngưỡng đối chiếu",  # lệch đối chiếu Δtiền thật (loại B) — xem PLAN_FIX_CASHFLOW_WARNINGS.md
)


def load_ranking_config() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "config/investment_ranking.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    for profile in cfg["profiles"].values():
        if sum(profile["weights"].values()) != 100:
            raise ValueError("Tổng trọng số phải là 100")
    return cfg


def finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def scale(value: Any, limits: list[float]) -> float | None:
    if not finite(value):
        return None
    lo, hi = limits
    return min(100.0, max(0.0, (value - lo) / (hi - lo) * 100))


def average_known(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if len(known) == len(values) and known else None


def score_metrics(rows: list[dict], cfg: dict) -> None:
    """So ROE/tăng trưởng trong cùng ngành; nhóm ít mã dùng thang cố định công bố."""
    for row in rows:
        metrics = row.get("metrics", {})
        parts = row.setdefault("components", {})
        normalized = []
        for name in ("roe", "revenue_cagr"):
            val = metrics.get(name)
            peers = [
                r.get("metrics", {}).get(name)
                for r in rows
                if r.get("sector") == row.get("sector")
                and not r.get("error")
                and not any(c["severity"] == "error" for c in r.get("checks", []))
            ]
            peers = [v for v in peers if finite(v)]
            if finite(val) and len(peers) >= cfg["scales"]["min_peer_count"]:
                normalized.append(
                    100
                    * (sum(v < val for v in peers) + 0.5 * sum(v == val for v in peers))
                    / len(peers)
                )
            else:
                normalized.append(scale(val, cfg["scales"][name]))
        parts["quality"] = average_known(normalized)
        if row.get("is_bank"):
            parts["safety"] = average_known(
                [
                    scale(metrics.get("npl"), cfg["scales"]["npl"]),
                    scale(metrics.get("llr"), cfg["scales"]["llr"]),
                ]
            )
        else:
            parts["safety"] = average_known(
                [
                    scale(
                        metrics.get("debt_to_equity"), cfg["scales"]["debt_to_equity"]
                    ),
                    scale(
                        metrics.get("cash_conversion"), cfg["scales"]["cash_conversion"]
                    ),
                ]
            )
        parts["flow"] = scale(metrics.get("flow_ratio"), cfg["scales"]["flow_ratio"])


def rank_companies(rows: list[dict], cfg: dict) -> list[dict]:
    output = deepcopy(rows)
    for row in output:
        price: Any = row.get("price")
        fv: Any = row.get("fair_value")
        codes = {flag.split(":", 1)[0] for flag in row.get("flags", [])}
        invalid = (
            bool(row.get("error"))
            or bool(codes.intersection(cfg["not_rateable_flags"]))
            or any(c["severity"] == "error" for c in row.get("checks", []))
        )
        valid = finite(price) and finite(fv) and price > 0 and fv > 0 and not invalid
        if invalid:
            row["diagnostic_fair_value"] = fv
            row["fair_value"] = None
        row["mos"] = 1 - price / fv if valid else None
        row["upside_pct"] = (fv / price - 1) * 100 if valid else None
        row["profiles"] = {}
        for key, profile in cfg["profiles"].items():
            parts = dict(row.get("components", {}))
            parts["valuation"] = scale(row["mos"], [0, profile["min_mos"]])
            coverage = sum(
                weight
                for part, weight in profile["weights"].items()
                if finite(parts.get(part))
            )
            score = sum(
                weight * parts[part] / 100
                for part, weight in profile["weights"].items()
                if finite(parts.get(part))
            )
            reasons = list(row.get("blockers", []))
            reasons.extend(
                check["message"]
                for check in row.get("checks", [])
                if check.get("severity") == "warning"
                and any(
                    phrase in check.get("message", "")
                    for phrase in MATERIAL_MODEL_WARNING_PHRASES
                )
            )
            reasons.extend(
                flag
                for flag in row.get("flags", [])
                if flag.split(":", 1)[0] in cfg["blocking_flags"]
            )
            if not valid or invalid:
                reasons.append("Không đủ cơ sở định giá")
            if valid and abs(row["upside_pct"]) > cfg["max_upside_pct"]:
                reasons.append("Chênh lệch định giá quá lớn, cần kiểm tra lại")
            if not row.get("governance_verified"):
                reasons.append("Chưa kiểm chứng hồ sơ quản trị và lợi thế cạnh tranh")
            if not row.get("golden_verified"):
                reasons.append("Chưa có đối chiếu định giá được duyệt cho hồ sơ này")
            if not row.get("liquidity_ok"):
                reasons.append("Thanh khoản thiếu dữ liệu hoặc dưới ngưỡng")
            if coverage < cfg["min_coverage"]:
                reasons.append("Độ phủ dữ liệu chưa đủ")
            for part in ("quality", "safety"):
                if parts.get(part) is None or parts[part] < profile[f"min_{part}"]:
                    reasons.append(
                        f"Chưa đạt tiêu chí {'chất lượng' if part == 'quality' else 'sức khỏe tài chính'}"
                    )
            if valid and row["mos"] < profile["min_mos"]:
                reasons.append("Giá chưa có đủ biên an toàn")
            row["profiles"][key] = {
                "score": round(score, 2) if valid and not invalid else None,
                "coverage": coverage,
                "components": parts,
                "eligible": not reasons,
                "reasons": list(dict.fromkeys(reasons)),
                "rank": None,
                "buy_below": fv * (1 - profile["min_mos"]) if valid else None,
            }
    for key in cfg["profiles"]:
        ranked = sorted(
            [row for row in output if row["profiles"][key]["score"] is not None],
            key=lambda row: (-row["profiles"][key]["score"], row["ticker"]),
        )
        for rank, row in enumerate(ranked, 1):
            row["profiles"][key]["rank"] = rank
    return output


def select_candidates(
    rows: list[dict], profile: str, cfg: dict, *, eligible_only: bool
) -> list[str]:
    def researchable(row: dict) -> bool:
        if row["profiles"][profile]["score"] is None:
            return False
        if eligible_only:
            return row["profiles"][profile]["eligible"]
        codes = {flag.split(":", 1)[0] for flag in row.get("flags", [])}
        if row.get("error") or codes.intersection(cfg["not_rateable_flags"]):
            return False
        if codes.intersection(cfg["blocking_flags"]):
            return False
        return not any(
            check.get("severity") == "error" for check in row.get("checks", [])
        )

    pool = sorted(
        [r for r in rows if researchable(r)],
        key=lambda r: (-r["profiles"][profile]["score"], r["ticker"]),
    )
    selected: list[str] = []
    counts: dict[str, int] = {}
    # Chọn các ngành khác nhau trước, không hạ chuẩn để lấp đủ số lượng.
    for row in pool:
        if len(counts) >= cfg["min_sectors"]:
            break
        if row["sector"] not in counts:
            selected.append(row["ticker"])
            counts[row["sector"]] = 1
    for row in pool:
        if len(selected) >= cfg["max_picks"]:
            break
        if (
            row["ticker"] not in selected
            and counts.get(row["sector"], 0) < cfg["max_per_sector"]
        ):
            selected.append(row["ticker"])
            counts[row["sector"]] = counts.get(row["sector"], 0) + 1
    return selected
