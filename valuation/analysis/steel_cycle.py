"""Thống kê chu kỳ ngành thép: đỉnh/đáy, thời lượng pha, xác suất pha kết thúc, lợi suất theo pha.

Toàn bộ là hàm thuần trên chuỗi theo tháng (không gọi mạng, không ghi DB) — dữ liệu do
scripts/steel_cycle_report.py nạp. Kết quả là xác suất LỊCH SỬ (tần suất quá khứ), không phải dự báo
hay khuyến nghị: mẫu chỉ vài chục pha nên sai số lớn, luôn đi kèm số quan sát.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

import pandas as pd


@dataclass(frozen=True)
class Turn:
    idx: int  # vị trí cực trị (đỉnh/đáy)
    kind: str  # "P" đỉnh, "T" đáy
    confirmed_idx: int  # vị trí lúc đảo chiều đủ ngưỡng — thời điểm nhà đầu tư BIẾT có đỉnh/đáy


def zigzag(values: list[float], threshold: float) -> tuple[list[Turn], list[str | None]]:
    """Đỉnh/đáy theo zigzag: đỉnh xác nhận khi giá rơi ≥ threshold từ mức cao nhất kể từ đáy trước,
    đáy xác nhận khi giá tăng ≥ threshold từ mức thấp nhất kể từ đỉnh trước.

    Trả (các điểm đảo chiều, trạng thái thời gian thực từng kỳ "up"/"down"/None). Trạng thái chỉ
    dùng dữ liệu tới kỳ đó (không nhìn trước) nên dùng được để đo lợi suất theo trạng thái.
    """
    turns: list[Turn] = []
    state: list[str | None] = []
    direction: str | None = None
    hi = lo = ext = 0
    for i, v in enumerate(values):
        if direction is None:
            hi = i if v > values[hi] else hi
            lo = i if v < values[lo] else lo
            if v >= values[lo] * (1 + threshold) and lo < i:
                turns.append(Turn(lo, "T", i))
                direction, ext = "up", i
            elif v <= values[hi] * (1 - threshold) and hi < i:
                turns.append(Turn(hi, "P", i))
                direction, ext = "down", i
        elif direction == "up":
            if v > values[ext]:
                ext = i
            elif v <= values[ext] * (1 - threshold):
                turns.append(Turn(ext, "P", i))
                direction, ext = "down", i
        else:
            if v < values[ext]:
                ext = i
            elif v >= values[ext] * (1 + threshold):
                turns.append(Turn(ext, "T", i))
                direction, ext = "up", i
        state.append(direction)
    return turns, state


def phases(values: list[float], turns: list[Turn]) -> list[dict]:
    """Pha giữa 2 điểm đảo chiều + pha đang diễn ra (censored=True, tính tới kỳ cuối)."""
    out = []
    for a, b in pairwise(turns):
        out.append(_phase(values, a, b.idx, censored=False))
    if turns:
        out.append(_phase(values, turns[-1], len(values) - 1, censored=True))
    return out


def _phase(values: list[float], start: Turn, end_idx: int, censored: bool) -> dict:
    return {
        "type": "up" if start.kind == "T" else "down",
        "start": start.idx,
        "end": end_idx,
        "months": end_idx - start.idx,
        "change": values[end_idx] / values[start.idx] - 1,
        "censored": censored,
    }


def duration_stats(ph: list[dict], kind: str) -> dict:
    """Thời lượng/biên độ các pha ĐÃ KẾT THÚC của một loại (up/down)."""
    done = [p for p in ph if p["type"] == kind and not p["censored"]]
    if not done:
        return {"n": 0}
    m = sorted(p["months"] for p in done)
    ch = sorted(p["change"] for p in done)
    return {
        "n": len(done),
        "median_months": _median(m),
        "mean_months": sum(m) / len(m),
        "min_months": m[0],
        "max_months": m[-1],
        "median_change": _median(ch),
    }


def km_survival(durations: list[float], censored: list[bool]) -> list[tuple[float, float, int]]:
    """Kaplan–Meier: [(t, S(t) ngay sau t, số pha còn 'sống' ngay trước t)] tại các thời điểm có pha kết thúc.

    Pha đang diễn ra là quan sát bị cắt (censored): biết nó đã kéo dài ≥ t nhưng chưa biết khi nào hết.
    """
    pts = sorted(zip(durations, censored, strict=True))
    s, out, i = 1.0, [], 0
    while i < len(pts):
        t = pts[i][0]
        at_risk = len(pts) - i
        ended = sum(1 for d, c in pts[i:] if d == t and not c)
        n_t = sum(1 for d, _ in pts[i:] if d == t)
        if ended:
            s *= 1 - ended / at_risk
            out.append((t, s, at_risk))
        i += n_t
    return out


def survival_at(curve: list[tuple[float, float, int]], t: float) -> float:
    """S(t) dạng bậc thang (giá trị sau thời điểm kết thúc cuối cùng ≤ t)."""
    s = 1.0
    for ti, si, _ in curve:
        if ti <= t:
            s = si
        else:
            break
    return s


def prob_end_within(
    durations: list[float], censored: list[bool], age: float, horizon: float
) -> dict:
    """P(pha kết thúc trong `horizon` tháng tới | đã kéo dài `age` tháng) = 1 − S(age+h)/S(age).

    Kèm số pha lịch sử đã sống tới `age` (n_at_risk) — càng ít thì xác suất càng kém tin cậy.
    """
    curve = km_survival(durations, censored)
    s_age = survival_at(curve, age)
    n_at_risk = sum(1 for d in durations if d >= age)
    if s_age <= 0 or n_at_risk == 0:
        return {"prob": None, "n_at_risk": n_at_risk}
    return {
        "prob": 1 - survival_at(curve, age + horizon) / s_age,
        "n_at_risk": n_at_risk,
    }


def forward_return_by_state(
    prices: pd.Series, state: pd.Series, months: int
) -> dict[str, dict]:
    """Lợi suất `months` tháng tới của `prices`, chia theo trạng thái thời gian thực `state` tại thời điểm đầu kỳ.

    Cửa sổ chồng lấn nên số quan sát độc lập ≈ n / months (ghi kèm n_independent).
    """
    fwd = prices.shift(-months) / prices - 1
    df = pd.DataFrame({"fwd": fwd, "state": state}).dropna()
    out = {}
    for st, g in df.groupby("state"):
        out[str(st)] = {
            "n": len(g),
            "n_independent": round(len(g) / months, 1),
            "mean": float(g["fwd"].mean()),
            "median": float(g["fwd"].median()),
            "hit_rate": float((g["fwd"] > 0).mean()),
        }
    return out


def event_returns(prices: pd.Series, events: list[tuple[pd.Period, str]], horizons: list[int]) -> list[dict]:
    """Lợi suất của `prices` h tháng sau mỗi sự kiện (tháng xác nhận đỉnh/đáy của chuỗi khác).
    Mỗi sự kiện là một quan sát độc lập — trung thực hơn trung bình cửa sổ chồng lấn."""
    out = []
    for when, kind in events:
        if when not in prices.index:
            continue
        i = prices.index.get_loc(when)
        row = {"date": str(when), "kind": kind}
        for h in horizons:
            row[f"r{h}"] = float(prices.iloc[i + h] / prices.iloc[i] - 1) if i + h < len(prices) else None
        out.append(row)
    return out


def lagged_correlation(y: pd.Series, x: pd.Series, max_lag: int) -> dict[int, float]:
    """corr(y_t, x_{t−k}) theo k. k > 0: x đi TRƯỚC y k kỳ."""
    out = {}
    for k in range(-max_lag, max_lag + 1):
        pair = pd.concat([y, x.shift(k)], axis=1).dropna()
        if len(pair) > 12:
            out[k] = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
    return out


def turn_lags(turns_a: list[tuple[pd.Timestamp, str]], turns_b: list[tuple[pd.Timestamp, str]], window: int) -> list[dict]:
    """Với mỗi đỉnh/đáy của A, tìm đỉnh/đáy CÙNG LOẠI gần nhất của B trong ±window tháng.
    lag_months > 0: B xảy ra trước A."""
    out = []
    for da, ka in turns_a:
        cands = [(db, abs(_months_between(db, da))) for db, kb in turns_b if kb == ka]
        cands = [c for c in cands if c[1] <= window]
        if cands:
            db = min(cands, key=lambda c: c[1])[0]
            out.append({"date": da, "kind": ka, "other": db, "lag_months": _months_between(db, da)})
        else:
            out.append({"date": da, "kind": ka, "other": None, "lag_months": None})
    return out


def seasonality(monthly_returns: pd.Series) -> dict[int, dict]:
    """Lợi suất trung bình, tỷ lệ tháng tăng và t-stat theo tháng dương lịch."""
    out = {}
    for m, g in monthly_returns.dropna().groupby(monthly_returns.dropna().index.month):
        sd = g.std(ddof=1)
        out[int(m)] = {
            "n": len(g),
            "mean": float(g.mean()),
            "hit_rate": float((g > 0).mean()),
            "t_stat": float(g.mean() / (sd / math.sqrt(len(g)))) if len(g) > 2 and sd > 0 else None,
        }
    return out


def _months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    """Số tháng từ a tới b (b − a)."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def _median(xs: list[float]) -> float:
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
