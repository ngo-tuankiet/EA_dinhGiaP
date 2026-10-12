"""Bù valuation_outputs cho các mã VN100 chưa có kết quả lưu DB."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from valuation.db.models import Ticker, ValuationOutput
from valuation.db.session import SessionLocalWrite
from valuation.engine.batch import value_ticker
from valuation.models.macro_env import MacroEnvironment


def _missing_tickers(db) -> list[str]:
    have = {r[0] for r in db.query(ValuationOutput.ticker).distinct().all()}
    return sorted(
        r[0]
        for r in db.query(Ticker.ticker).filter(Ticker.is_vn100.is_(True)).all()
        if r[0] not in have
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bù valuation_outputs còn thiếu")
    parser.add_argument("--tickers", nargs="*", help="Danh sách mã cụ thể, mặc định là mã VN100 còn thiếu")
    args = parser.parse_args()

    db = SessionLocalWrite()
    try:
        tickers = [t.upper() for t in args.tickers] if args.tickers else _missing_tickers(db)
        macro_env = MacroEnvironment.from_db(db)
        print(f"Backfill valuation_outputs: {len(tickers)} mã")

        ok = 0
        failed = 0
        for ticker in tickers:
            if db.query(ValuationOutput.id).filter(ValuationOutput.ticker == ticker).first():
                print(f"{ticker}: skip, already exists")
                continue

            result = value_ticker(db, ticker, macro_env=macro_env)
            if "error" in result:
                failed += 1
                print(f"{ticker}: ERR {result['error']}")
                continue

            fair_value = float(result["fair_value"])
            price = float(result["price"] or 0.0)
            row = ValuationOutput(
                ticker=ticker,
                blended_fair_value_per_share=fair_value,
                margin_of_safety=(fair_value / price - 1.0) if price else None,
                flags=result.get("flags") or [],
                macro_snapshot=macro_env.model_dump() if hasattr(macro_env, "model_dump") else None,
            )
            db.add(row)
            db.commit()
            ok += 1
            print(f"{ticker}: OK fair_value={fair_value:,.0f}")

        print(f"Done. ok={ok}, failed={failed}")
        return 0 if failed == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
