"""Nạp dòng tiền Golden đã kiểm tra vào DB; không gọi mạng và không đụng OHLCV."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valuation.config import PROJECT_ROOT
from valuation.ingest.pipeline import upsert_market_flows
from valuation.ingest.universe import load_vn100_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*")
    args = parser.parse_args()
    universe = load_vn100_snapshot()["symbols"]
    tickers = args.tickers or universe
    if set(tickers) - set(universe):
        parser.error("Mã ngoài VN100")
    root = PROJECT_ROOT / ".vn100_ranking/sponsor"
    total = 0
    for ticker in tickers:
        payload = json.loads(
            (root / ticker / "foreign.json").read_text(encoding="utf-8")
        )
        frame = pd.DataFrame(payload["rows"])
        required = {
            "time",
            "buy_vol",
            "buy_val",
            "sell_vol",
            "sell_val",
            "net_vol",
            "net_val",
        }
        if (
            len(frame) != 20
            or not required.issubset(frame)
            or frame[list(required)].isna().any().any()
        ):
            raise ValueError(f"Cache dòng tiền chưa đủ hoặc không hợp lệ: {ticker}")
        if frame["time"].astype(str).str[:10].nunique() != 20:
            raise ValueError(f"Ngày dòng tiền bị trùng: {ticker}")
        upsert_market_flows(ticker, frame, pd.DataFrame())
        total += len(frame)
    print(
        f"Đã upsert {total} phiên dòng tiền ngoại; giữ nguyên OHLCV và dữ liệu tự doanh."
    )


if __name__ == "__main__":
    main()
