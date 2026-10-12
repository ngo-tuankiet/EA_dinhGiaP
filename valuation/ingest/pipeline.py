import logging
from datetime import datetime
from typing import Any

import pandas as pd

from valuation.db.models import BackfillStatus, FinancialsQuarterly, PricesDaily, Ticker
from valuation.db.session import SessionLocalWrite
from valuation.db.upsert import dialect_insert
from valuation.ingest.market_client import market_client
from valuation.ingest.normalizer import normalize_daily_prices, unpivot_financials
from valuation.ingest.vnstock_client import vnstock_client

logger = logging.getLogger(__name__)


def upsert_prices(df: pd.DataFrame, ticker: str):
    if df.empty:
        return

    # Chuẩn bị records
    records = []
    price_columns = [
        c
        for c in ("open", "high", "low", "close", "volume", "value", "adj_close")
        if c in df.columns
    ]
    for _, row in df.iterrows():
        records.append(
            {
                "ticker": ticker,
                "trade_date": (
                    row["time"].date()
                    if isinstance(row["time"], pd.Timestamp)
                    else pd.to_datetime(row["time"]).date()
                ),
                **{c: row[c] if pd.notna(row[c]) else None for c in price_columns},
                "price_unit": row.get("price_unit", "VND"),
            }
        )

    db = SessionLocalWrite()
    try:
        stmt = dialect_insert(db, PricesDaily).values(records)
        from sqlalchemy import func

        update_dict = {
            c: func.coalesce(getattr(stmt.excluded, c), getattr(PricesDaily, c))
            for c in [*price_columns, "price_unit"]
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "trade_date"], set_=update_dict
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error upserting prices for {ticker}: {e}")
        raise e
    finally:
        db.close()


# Cột market-flow duy nhất được phép ghi bởi upsert_market_flows. KHÔNG được
# đụng open/high/low/close/volume — đây từng là bug nghiêm trọng: update_dict
# lấy TOÀN BỘ cột bảng PricesDaily, khiến ON CONFLICT DO UPDATE set OHLCV về
# NULL (record market-flow không có các cột đó → SQLAlchemy coi là NULL) và
# GHI ĐÈ giá lịch sử đã có (vi phạm luật vàng #6 — không phá dữ liệu lịch sử).
_MARKET_FLOW_COLUMNS = [
    "foreign_buy_vol",
    "foreign_buy_val",
    "foreign_sell_vol",
    "foreign_sell_val",
    "foreign_net_vol",
    "foreign_net_val",
    "proprietary_buy_vol",
    "proprietary_buy_val",
    "proprietary_sell_vol",
    "proprietary_sell_val",
    "proprietary_net_vol",
    "proprietary_net_val",
]


def upsert_market_flows(ticker: str, df_foreign: pd.DataFrame, df_prop: pd.DataFrame):
    """Upsert dữ liệu dòng tiền ngoại và tự doanh vào bảng PricesDaily.

    CHỈ ghi các cột market-flow (_MARKET_FLOW_COLUMNS) — không đụng OHLCV.
    """
    if (df_foreign is None or df_foreign.empty) and (df_prop is None or df_prop.empty):
        return

    # Gộp 2 df theo ngày. Mỗi record LUÔN đủ toàn bộ _MARKET_FLOW_COLUMNS
    # (None nếu thiếu nguồn) để mọi dict trong batch insert có cùng shape.
    records_dict: dict[Any, dict[str, Any]] = {}

    def _get_or_init(d):
        if d not in records_dict:
            records_dict[d] = {
                "ticker": ticker,
                "trade_date": d,
                **{col: None for col in _MARKET_FLOW_COLUMNS},
            }
        return records_dict[d]

    if df_foreign is not None and not df_foreign.empty:
        for _, row in df_foreign.iterrows():
            d = (
                row["time"].date()
                if isinstance(row["time"], pd.Timestamp)
                else pd.to_datetime(row["time"]).date()
            )
            rec = _get_or_init(d)
            rec.update(
                {
                    "foreign_buy_vol": row.get("buy_vol"),
                    "foreign_buy_val": row.get("buy_val"),
                    "foreign_sell_vol": row.get("sell_vol"),
                    "foreign_sell_val": row.get("sell_val"),
                    "foreign_net_vol": row.get("net_vol"),
                    "foreign_net_val": row.get("net_val"),
                }
            )

    if df_prop is not None and not df_prop.empty:
        for _, row in df_prop.iterrows():
            d = (
                row["time"].date()
                if isinstance(row["time"], pd.Timestamp)
                else pd.to_datetime(row["time"]).date()
            )
            rec = _get_or_init(d)
            rec.update(
                {
                    "proprietary_buy_vol": row.get("buy_vol"),
                    "proprietary_buy_val": row.get("buy_val"),
                    "proprietary_sell_vol": row.get("sell_vol"),
                    "proprietary_sell_val": row.get("sell_val"),
                    "proprietary_net_vol": row.get("net_vol"),
                    "proprietary_net_val": row.get("net_val"),
                }
            )

    records = list(records_dict.values())
    if not records:
        return

    db = SessionLocalWrite()
    try:
        stmt = dialect_insert(db, PricesDaily).values(records)
        # CHỈ update các cột market-flow — giữ nguyên OHLCV đã có.
        from sqlalchemy import func

        update_dict = {
            col: func.coalesce(getattr(stmt.excluded, col), getattr(PricesDaily, col))
            for col in _MARKET_FLOW_COLUMNS
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "trade_date"], set_=update_dict
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error upserting market flows for {ticker}: {e}")
        raise e
    finally:
        db.close()


def upsert_financials(df: pd.DataFrame, ticker: str):
    if df.empty:
        return

    records = []
    for _, row in df.iterrows():
        val = row.get("value")
        if pd.isna(val):
            val = None
        elif isinstance(val, (int, float)):
            val = float(val)
        published_at = row.get("published_at")
        if pd.isna(published_at):
            published_at = None

        records.append(
            {
                "ticker": ticker,
                "fiscal_year": int(row["fiscal_year"]),
                "fiscal_quarter": int(row["fiscal_quarter"]),
                "is_consolidated": bool(row["is_consolidated"]),
                "is_restated": bool(row["is_restated"]),
                "statement": str(row["statement"]),
                "line_item": str(row["line_item"]),
                "value": val,
                "currency": str(row.get("currency", "VND")),
                "source": str(row.get("source", "vnstock")),
                "published_at": published_at,
            }
        )

    db = SessionLocalWrite()
    try:
        # Chia nhỏ để tránh lỗi quá tải tham số của PostgreSQL
        batch_size = 500
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            stmt = dialect_insert(db, FinancialsQuarterly).values(batch)
            # Không ghi đè bản đã lưu: provider có thể trả số điều chỉnh nhưng
            # không cho biết đó là restatement. Chỉ thêm kỳ/phiên bản mới; khi có
            # filing xác nhận, ingest với is_restated=True để giữ cả hai bản.
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[
                    "ticker",
                    "fiscal_year",
                    "fiscal_quarter",
                    "is_consolidated",
                    "is_restated",
                    "statement",
                    "line_item",
                ]
            )
            db.execute(stmt)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error upserting financials for {ticker}: {e}")
        raise e
    finally:
        db.close()


def update_backfill_status(
    ticker: str, status: str, last_price_date=None, last_financial_period=None
):
    db = SessionLocalWrite()
    try:
        stmt = dialect_insert(db, BackfillStatus).values(
            ticker=ticker,
            status=status,
            last_price_date=last_price_date,
            last_financial_period=last_financial_period,
        )
        update_dict = {"status": stmt.excluded.status, "updated_at": datetime.now()}
        if last_price_date:
            update_dict["last_price_date"] = stmt.excluded.last_price_date
        if last_financial_period:
            update_dict["last_financial_period"] = stmt.excluded.last_financial_period

        stmt = stmt.on_conflict_do_update(index_elements=["ticker"], set_=update_dict)
        db.execute(stmt)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating status for {ticker}: {e}")
    finally:
        db.close()


_FULL_BACKFILL_START = "2020-01-01"


def _overlap_was_readjusted(ticker: str, df_norm: pd.DataFrame) -> bool:
    """vnstock trả giá đã điều chỉnh hồi tố theo sự kiện quyền. Nếu đoạn chồng lấn
    lệch giá đã lưu → có sự kiện sau lần tải trước, lịch sử cũ trong DB đã sai cơ sở."""
    from valuation.config import load_defaults

    tol = float(
        (load_defaults().get("price_ingest") or {}).get("readjust_tolerance", 0.005)
    )
    fetched = dict(
        zip(pd.to_datetime(df_norm["time"]).dt.date, df_norm["close"].astype(float))
    )
    db = SessionLocalWrite()
    try:
        stored = (
            db.query(PricesDaily.trade_date, PricesDaily.close)
            .filter(
                PricesDaily.ticker == ticker,
                PricesDaily.trade_date.in_(list(fetched)),
            )
            .all()
        )
    finally:
        db.close()
    return any(
        old and fetched.get(d) and abs(fetched[d] / float(old) - 1) > tol
        for d, old in stored
    )


def _earliest_price_start(ticker: str) -> str:
    """Tải lại TOÀN BỘ chuỗi đang lưu (kể cả trước mốc backfill mặc định)."""
    from sqlalchemy import func

    db = SessionLocalWrite()
    try:
        first = (
            db.query(func.min(PricesDaily.trade_date))
            .filter(PricesDaily.ticker == ticker)
            .scalar()
        )
    finally:
        db.close()
    if first is None:
        return _FULL_BACKFILL_START
    first_str = pd.Timestamp(first).strftime("%Y-%m-%d")
    return min(first_str, _FULL_BACKFILL_START)


def _incremental_price_start(ticker: str) -> str:
    """Ngày bắt đầu kéo giá THEO KIỂU INCREMENTAL (tiết kiệm API/dữ liệu).

    Lấy max(trade_date) có close hợp lệ trong DB rồi lùi 5 ngày (đệm để vá các
    phiên bị NULL/điều chỉnh; upsert idempotent nên chồng lấn vô hại). Mã chưa
    có dữ liệu → full backfill từ 2020. Trước đây MỌI lần ingest kéo full từ
    2020 (~1,700 dòng/mã) dù chỉ thiếu vài ngày — lãng phí và chậm.
    """
    import datetime

    db = SessionLocalWrite()
    try:
        row = (
            db.query(PricesDaily.trade_date)
            .filter(PricesDaily.ticker == ticker, PricesDaily.close.isnot(None))
            .order_by(PricesDaily.trade_date.desc())
            .first()
        )
        if row and row[0]:
            return (row[0] - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        return _FULL_BACKFILL_START
    except Exception:
        return _FULL_BACKFILL_START
    finally:
        db.close()


def run_ingest(
    ticker: str,
    data_types: list,
    incremental: bool = True,
    include_yearly: bool = True,
    include_market_flows: bool = True,
):
    """
    Orchestrator hàm lấy dữ liệu, chuẩn hóa và lưu DB.
    data_types: ['prices', 'financials']
    incremental: True (mặc định) → giá chỉ kéo từ ngày cuối có dữ liệu −5 ngày;
                 False → full backfill từ 2020 (dùng khi nghi dữ liệu lịch sử hỏng).
    """
    # 1. Đảm bảo ticker tồn tại (để foreign key ko báo lỗi)
    db = SessionLocalWrite()
    try:
        if not db.query(Ticker).filter(Ticker.ticker == ticker).first():
            overview = vnstock_client.get_company_overview(ticker)
            if not overview.empty:
                info = overview.iloc[0]
                db.execute(
                    dialect_insert(db, Ticker)
                    .values(
                        ticker=ticker,
                        company_name=info.get("organ_name", ""),
                        exchange="",
                        sector=info.get("sector", ""),
                        industry=info.get("icb_code_lv4", ""),
                        is_vn100=True,
                    )
                    .on_conflict_do_nothing()
                )
                db.commit()
    finally:
        db.close()

    result: dict[str, Any] = {
        "ticker": ticker,
        "status": "SUCCESS",
        "prices": {"status": "SKIPPED", "rows": 0},
        "market_flows": {"status": "SKIPPED"},
        "financials": {},
        "errors": [],
    }
    successful_units = 0
    last_price = None
    last_fin = None

    if "prices" in data_types:
        try:
            price_start = (
                _incremental_price_start(ticker)
                if incremental
                else _earliest_price_start(ticker)
            )
            flow_start = price_start
            df_prices = vnstock_client.get_historical_prices(ticker, price_start)
            df_norm = normalize_daily_prices(df_prices)
            if df_norm.empty:
                raise ValueError("Nguồn không trả dữ liệu giá")
            full_refresh = incremental and _overlap_was_readjusted(ticker, df_norm)
            if full_refresh:
                price_start = _earliest_price_start(ticker)
                df_prices = vnstock_client.get_historical_prices(ticker, price_start)
                df_norm = normalize_daily_prices(df_prices)
            upsert_prices(df_norm, ticker)
            successful_units += 1
            last_price = pd.to_datetime(df_prices["time"]).max().date()
            result["prices"] = {
                "status": "UPDATED",
                "rows": len(df_norm),
                "last_date": last_price.isoformat(),
                "full_refresh": full_refresh,
            }

            if include_market_flows:
                # Kéo thêm dòng tiền ngoại & tự doanh (cùng cửa sổ incremental).
                try:
                    df_foreign = market_client.fetch_foreign_flow(
                        ticker, start=flow_start
                    )
                    df_prop = market_client.fetch_proprietary_flow(
                        ticker, start=flow_start
                    )
                    upsert_market_flows(ticker, df_foreign, df_prop)
                    result["market_flows"] = {
                        "status": "UPDATED",
                        "foreign_rows": int(
                            0 if df_foreign is None else len(df_foreign)
                        ),
                        "proprietary_rows": int(0 if df_prop is None else len(df_prop)),
                    }
                except Exception as e:
                    logger.warning(f"Could not fetch market flows for {ticker}: {e}")
                    result["market_flows"] = {"status": "FAILED", "error": str(e)}
                    result["errors"].append(
                        {"component": "market_flows", "message": str(e)}
                    )
        except Exception as e:
            logger.error(f"Could not fetch prices for {ticker}: {e}")
            result["prices"] = {"status": "FAILED", "rows": 0, "error": str(e)}
            result["errors"].append({"component": "prices", "message": str(e)})

    if "financials" in data_types:
        for stmt_type in ["BS", "IS", "CF"]:
            statement_result: dict[str, Any] = {
                "quarter": {"status": "SKIPPED", "rows": 0},
                "year": {"status": "SKIPPED", "rows": 0},
            }
            try:
                # Lấy dữ liệu quý (Quarterly)
                df_fin_q = vnstock_client.get_financials(
                    ticker, stmt_type, period="quarter"
                )
                df_long_q = unpivot_financials(df_fin_q, stmt_type)
                if df_long_q.empty:
                    raise ValueError("Nguồn không trả dữ liệu BCTC quý")
                upsert_financials(df_long_q, ticker)
                successful_units += 1
                statement_result["quarter"] = {
                    "status": "UPDATED",
                    "rows": len(df_long_q),
                }
                latest = df_long_q.sort_values(["fiscal_year", "fiscal_quarter"]).iloc[
                    -1
                ]
                candidate = (
                    f"{int(latest['fiscal_year'])}-Q{int(latest['fiscal_quarter'])}"
                )
                if last_fin is None or candidate > last_fin:
                    last_fin = candidate
            except Exception as e:
                logger.warning(
                    f"Could not fetch quarterly {stmt_type} for {ticker}: {e}"
                )
                statement_result["quarter"] = {
                    "status": "FAILED",
                    "rows": 0,
                    "error": str(e),
                }
                result["errors"].append(
                    {
                        "component": "financials",
                        "statement": stmt_type,
                        "period": "quarter",
                        "message": str(e),
                    }
                )

            if include_yearly:
                # Dữ liệu năm chỉ cần cho mã chưa có lịch sử; các mã hiện hữu
                # đã có Q0 và mỗi lần chạy chỉ cần cập nhật quý mới.
                try:
                    df_fin_y = vnstock_client.get_financials(
                        ticker, stmt_type, period="year"
                    )
                    df_long_y = unpivot_financials(df_fin_y, stmt_type)
                    if df_long_y.empty:
                        raise ValueError("Nguồn không trả dữ liệu BCTC năm")
                    upsert_financials(df_long_y, ticker)
                    successful_units += 1
                    statement_result["year"] = {
                        "status": "UPDATED",
                        "rows": len(df_long_y),
                    }
                except Exception as e:
                    logger.warning(
                        f"Could not fetch yearly {stmt_type} for {ticker}: {e}"
                    )
                    statement_result["year"] = {
                        "status": "FAILED",
                        "rows": 0,
                        "error": str(e),
                    }
                    result["errors"].append(
                        {
                            "component": "financials",
                            "statement": stmt_type,
                            "period": "year",
                            "message": str(e),
                        }
                    )
            result["financials"][stmt_type] = statement_result

    if result["errors"]:
        result["status"] = "PARTIAL" if successful_units else "FAILED"
    update_backfill_status(ticker, result["status"], last_price, last_fin)
    return result
