"""Chuẩn hóa dữ liệu và tính chỉ báo cho biểu đồ kỹ thuật."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


REQUIRED_PRICE_COLUMNS = ("time", "open", "high", "low", "close", "volume")
PERIOD_DAYS = {
    "3T": 120,
    "6T": 230,
    "1N": 410,
    "2N": 780,
    "5N": 1_900,
}
INTERVAL_RULES = {
    "Ngày": None,
    "Tuần": "W-FRI",
    "Tháng": "ME",
}


def period_start_date(period: str, today: date | None = None) -> str:
    """Trả ngày bắt đầu đủ rộng để tính chỉ báo ở mép trái biểu đồ."""
    if period not in PERIOD_DAYS:
        raise ValueError(f"Khoảng thời gian không hợp lệ: {period}")
    anchor = today or date.today()
    return (anchor - timedelta(days=PERIOD_DAYS[period])).isoformat()


def normalize_price_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Chuẩn hóa OHLCV, loại bản ghi lỗi/trùng và sắp xếp tăng dần."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=REQUIRED_PRICE_COLUMNS)

    missing = [column for column in REQUIRED_PRICE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Dữ liệu giá thiếu cột: {', '.join(missing)}")

    result = frame.loc[:, REQUIRED_PRICE_COLUMNS].copy()
    result["time"] = pd.to_datetime(result["time"], errors="coerce")
    for column in REQUIRED_PRICE_COLUMNS[1:]:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result = result.dropna(subset=["time", "open", "high", "low", "close"])
    result = result[result[["open", "high", "low", "close"]].gt(0).all(axis=1)]
    result["volume"] = result["volume"].fillna(0).clip(lower=0)
    result = result.drop_duplicates(subset=["time"], keep="last")
    return result.sort_values("time").reset_index(drop=True)


def resample_price_history(frame: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Gộp dữ liệu ngày thành nến tuần hoặc tháng theo OHLCV chuẩn."""
    if interval not in INTERVAL_RULES:
        raise ValueError(f"Khung thời gian không hợp lệ: {interval}")
    if frame.empty or interval == "Ngày":
        return frame.copy()

    rule = INTERVAL_RULES[interval]
    indexed = frame.set_index("time")
    result = indexed.resample(rule).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return result.dropna(subset=["open", "high", "low", "close"]).reset_index()


def add_technical_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Tính MA, EMA, Bollinger Bands, MACD, RSI và ATR từ OHLCV."""
    result = frame.copy()
    if result.empty:
        return result

    close = result["close"].astype(float)
    result["MA20"] = close.rolling(window=20, min_periods=20).mean()
    result["MA50"] = close.rolling(window=50, min_periods=50).mean()
    result["EMA20"] = close.ewm(span=20, adjust=False).mean()

    rolling_std = close.rolling(window=20, min_periods=20).std(ddof=0)
    result["BB_UPPER"] = result["MA20"] + (2.0 * rolling_std)
    result["BB_LOWER"] = result["MA20"] - (2.0 * rolling_std)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    result["MACD"] = ema12 - ema26
    result["MACD_SIGNAL"] = result["MACD"].ewm(span=9, adjust=False).mean()
    result["MACD_HIST"] = result["MACD"] - result["MACD_SIGNAL"]

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    average_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    average_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.mask((average_loss == 0) & (average_gain > 0), 100.0)
    rsi = rsi.mask((average_loss == 0) & (average_gain == 0), 50.0)
    result["RSI14"] = rsi

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            result["high"] - result["low"],
            (result["high"] - previous_close).abs(),
            (result["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["ATR14"] = true_range.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    return result


def price_snapshot(frame: pd.DataFrame) -> dict[str, float]:
    """Tạo các số đo ngắn gọn dùng ở đầu biểu đồ."""
    if frame.empty:
        return {}

    first_close = float(frame.iloc[0]["close"])
    latest_close = float(frame.iloc[-1]["close"])
    previous_close = float(frame.iloc[-2]["close"]) if len(frame) > 1 else latest_close
    average_volume = float(frame["volume"].tail(20).mean())
    return {
        "latest_close": latest_close,
        "session_change_pct": ((latest_close / previous_close) - 1) * 100 if previous_close else 0.0,
        "period_change_pct": ((latest_close / first_close) - 1) * 100 if first_close else 0.0,
        "period_high": float(frame["high"].max()),
        "period_low": float(frame["low"].min()),
        "average_volume_20": average_volume,
    }
