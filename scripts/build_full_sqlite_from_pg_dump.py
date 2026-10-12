"""Build a portable SQLite DB from the PostgreSQL dump.

This keeps the Drive copy self-contained: the Streamlit app can read
``vn100_full.db`` without requiring a local PostgreSQL service.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


TABLE_COLUMNS: dict[str, list[str]] = {
    "backfill_status": [
        "ticker", "last_financial_period", "last_price_date", "status", "updated_at",
    ],
    "consensus_history": [
        "ticker", "broker", "report_date", "target_price", "rating", "source_url",
        "raw_quote", "ingested_at",
    ],
    "daily_signal": [
        "ticker", "trade_date", "close_price", "fair_value_fast", "upside",
        "margin_of_safety", "conviction_score", "flags", "computed_at", "created_at",
    ],
    "financials_quarterly": [
        "ticker", "fiscal_year", "fiscal_quarter", "is_consolidated", "is_restated",
        "statement", "line_item", "value", "currency", "source", "ingested_at",
        "published_at",
    ],
    "industry_indicators": ["sector", "indicator_code", "period", "value"],
    "macro_radar": [
        "sector", "indicator_code", "frequency", "source", "warn_low", "warn_high",
        "mapped_driver", "elasticity",
    ],
    "macro_series": ["id", "indicator_code", "date", "value", "source", "created_at"],
    "prices_daily": [
        "ticker", "trade_date", "open", "high", "low", "close", "adj_close",
        "volume", "value", "foreign_buy", "foreign_sell", "price_unit",
        "foreign_buy_vol", "foreign_buy_val", "foreign_sell_vol", "foreign_sell_val",
        "foreign_net_vol", "foreign_net_val", "proprietary_buy_vol",
        "proprietary_buy_val", "proprietary_sell_vol", "proprietary_sell_val",
        "proprietary_net_vol", "proprietary_net_val",
    ],
    "tickers": [
        "ticker", "company_name", "exchange", "sector", "industry", "is_vn100",
        "updated_at",
    ],
    "valuation_outputs": [
        "id", "ticker", "blended_fair_value_per_share", "fair_value_bull",
        "fair_value_bear", "margin_of_safety", "flags", "macro_snapshot",
        "created_at",
    ],
    "valuation_runs": [
        "id", "ticker", "analyst", "created_at", "engine", "method", "scenario",
        "assumptions_json", "base_year_mode", "wacc", "terminal_g", "target_price",
        "current_price", "upside", "recommendation", "report_path", "notes",
    ],
    "valuation_sensitivities": [
        "ticker", "assumption_version", "driver_code", "dFV_ddriver",
        "base_driver_value", "created_at",
    ],
}


SCHEMA_SQL = """
PRAGMA foreign_keys = OFF;

CREATE TABLE tickers (
  ticker TEXT PRIMARY KEY,
  company_name TEXT,
  exchange TEXT,
  sector TEXT,
  industry TEXT,
  is_vn100 INTEGER,
  updated_at TEXT
);

CREATE TABLE financials_quarterly (
  ticker TEXT NOT NULL,
  fiscal_year INTEGER NOT NULL,
  fiscal_quarter INTEGER NOT NULL,
  is_consolidated INTEGER NOT NULL,
  is_restated INTEGER NOT NULL,
  statement TEXT NOT NULL,
  line_item TEXT NOT NULL,
  value NUMERIC,
  currency TEXT,
  source TEXT,
  published_at TEXT,
  ingested_at TEXT,
  PRIMARY KEY (ticker, fiscal_year, fiscal_quarter, is_consolidated, is_restated, statement, line_item)
);

CREATE TABLE prices_daily (
  ticker TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  adj_close NUMERIC,
  volume INTEGER,
  value NUMERIC,
  foreign_buy NUMERIC,
  foreign_sell NUMERIC,
  foreign_buy_vol NUMERIC,
  foreign_buy_val NUMERIC,
  foreign_sell_vol NUMERIC,
  foreign_sell_val NUMERIC,
  foreign_net_vol NUMERIC,
  foreign_net_val NUMERIC,
  proprietary_buy_vol NUMERIC,
  proprietary_buy_val NUMERIC,
  proprietary_sell_vol NUMERIC,
  proprietary_sell_val NUMERIC,
  proprietary_net_vol NUMERIC,
  proprietary_net_val NUMERIC,
  price_unit TEXT,
  PRIMARY KEY (ticker, trade_date)
);

CREATE TABLE backfill_status (
  ticker TEXT PRIMARY KEY,
  last_financial_period TEXT,
  last_price_date TEXT,
  status TEXT,
  updated_at TEXT
);

CREATE TABLE macro_series (
  id INTEGER PRIMARY KEY,
  indicator_code TEXT,
  date TEXT,
  value NUMERIC,
  source TEXT,
  created_at TEXT,
  UNIQUE (indicator_code, date)
);
CREATE INDEX ix_macro_series_indicator_code ON macro_series (indicator_code);
CREATE INDEX ix_macro_series_date ON macro_series (date);

CREATE TABLE macro_radar (
  sector TEXT NOT NULL,
  indicator_code TEXT NOT NULL,
  frequency TEXT,
  source TEXT,
  warn_low NUMERIC,
  warn_high NUMERIC,
  mapped_driver TEXT,
  elasticity NUMERIC,
  PRIMARY KEY (sector, indicator_code)
);

CREATE TABLE industry_indicators (
  sector TEXT NOT NULL,
  indicator_code TEXT NOT NULL,
  period TEXT NOT NULL,
  value NUMERIC,
  PRIMARY KEY (sector, indicator_code, period)
);

CREATE TABLE valuation_outputs (
  id INTEGER PRIMARY KEY,
  ticker TEXT,
  blended_fair_value_per_share NUMERIC,
  fair_value_bull NUMERIC,
  fair_value_bear NUMERIC,
  margin_of_safety NUMERIC,
  flags TEXT,
  macro_snapshot TEXT,
  created_at TEXT
);

CREATE TABLE valuation_sensitivities (
  ticker TEXT NOT NULL,
  assumption_version INTEGER NOT NULL,
  driver_code TEXT NOT NULL,
  dFV_ddriver NUMERIC,
  base_driver_value NUMERIC,
  created_at TEXT,
  PRIMARY KEY (ticker, assumption_version, driver_code)
);

CREATE TABLE daily_signal (
  ticker TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  close_price NUMERIC,
  fair_value_fast NUMERIC,
  upside NUMERIC,
  margin_of_safety NUMERIC,
  conviction_score NUMERIC,
  flags TEXT,
  computed_at TEXT,
  created_at TEXT,
  PRIMARY KEY (ticker, trade_date)
);

CREATE TABLE consensus_history (
  ticker TEXT NOT NULL,
  broker TEXT NOT NULL,
  report_date TEXT NOT NULL,
  target_price NUMERIC,
  rating TEXT,
  source_url TEXT,
  raw_quote TEXT,
  ingested_at TEXT,
  broker_canon TEXT,
  source_site TEXT,
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  report_title TEXT,
  currency_unit TEXT DEFAULT 'VND',
  PRIMARY KEY (ticker, broker, report_date)
);

CREATE TABLE consensus_synthesis (
  ticker TEXT PRIMARY KEY,
  n_reports INTEGER,
  brokers TEXT,
  diem_chung TEXT,
  diem_rieng TEXT,
  diem_mau_chot TEXT,
  doi_chieu_noi_bo TEXT,
  internal_fv NUMERIC,
  consensus_median NUMERIC,
  model TEXT,
  generated_at TEXT
);

CREATE TABLE consensus_report_text (
  ticker TEXT NOT NULL,
  broker_canon TEXT NOT NULL,
  report_date TEXT NOT NULL,
  source_site TEXT NOT NULL,
  detail_url TEXT,
  title TEXT,
  summary_text TEXT,
  lang TEXT,
  extracted TEXT,
  extract_version TEXT,
  fetched_at TEXT,
  PRIMARY KEY (ticker, broker_canon, report_date, source_site)
);

CREATE TABLE valuation_runs (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  analyst TEXT,
  created_at TEXT,
  engine TEXT,
  method TEXT,
  scenario TEXT,
  assumptions_json TEXT,
  base_year_mode TEXT,
  wacc NUMERIC,
  terminal_g NUMERIC,
  target_price NUMERIC,
  current_price NUMERIC,
  upside NUMERIC,
  recommendation TEXT,
  report_path TEXT,
  notes TEXT
);

CREATE TABLE calibration_runs (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL UNIQUE,
  git_sha TEXT,
  as_of TEXT NOT NULL,
  window_days INTEGER,
  dedup_mode TEXT,
  weighting TEXT,
  engine_config TEXT,
  n_tickers INTEGER,
  n_valued INTEGER,
  n_with_consensus INTEGER,
  median_dev_vs_consensus NUMERIC,
  median_abs_dev_vs_consensus NUMERIC,
  share_in_band NUMERIC,
  median_dev_vs_price NUMERIC,
  n_below_price INTEGER,
  n_below_price_40 INTEGER,
  aggregates TEXT,
  notes TEXT,
  created_at TEXT
);

CREATE TABLE calibration_observations (
  run_id INTEGER NOT NULL,
  ticker TEXT NOT NULL,
  method TEXT,
  sector_group TEXT,
  business_nature TEXT,
  fair_value NUMERIC,
  market_price NUMERIC,
  consensus_median NUMERIC,
  consensus_weighted NUMERIC,
  n_brokers INTEGER,
  consensus_min NUMERIC,
  consensus_max NUMERIC,
  consensus_age_days INTEGER,
  dev_vs_consensus NUMERIC,
  dev_vs_price NUMERIC,
  band NUMERIC,
  band_status TEXT,
  governance_status TEXT,
  registry_status TEXT,
  registry_thesis TEXT,
  flags TEXT,
  error TEXT,
  PRIMARY KEY (run_id, ticker)
);
"""


def pg_copy_unescape(value: str) -> str | None:
    if value == r"\N":
        return None

    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(value):
            out.append("\\")
            break
        esc = value[i]
        out.append({
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "v": "\v",
            "\\": "\\",
        }.get(esc, esc))
        i += 1
    return "".join(out)


def parse_copy_rows(dump_path: Path) -> Iterable[tuple[str, list[str | None]]]:
    current_table: str | None = None
    current_columns: list[str] | None = None

    with dump_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("COPY public."):
                table_part = line.split()[1]
                table = table_part.split(".", 1)[1]
                if table not in TABLE_COLUMNS:
                    current_table = None
                    current_columns = None
                    continue
                col_start = line.index("(") + 1
                col_end = line.index(")")
                current_table = table
                current_columns = [
                    c.strip().strip('"') for c in line[col_start:col_end].split(",")
                ]
                continue

            if current_table is None:
                continue

            if line == r"\.":
                current_table = None
                current_columns = None
                continue

            values = [pg_copy_unescape(v) for v in line.split("\t")]
            yield current_table, reorder_row(current_table, current_columns or [], values)


def reorder_row(
    table: str,
    source_columns: list[str],
    values: list[str | None],
) -> list[str | None]:
    source = dict(zip(source_columns, values))
    if table == "financials_quarterly":
        # PostgreSQL dump stores ingested_at before published_at; app SQLite schema
        # stores published_at before ingested_at.
        pass
    if table == "prices_daily":
        # PostgreSQL dump stores price_unit before detailed flow columns; app schema
        # keeps price_unit last.
        pass
    out = [source.get(col) for col in TABLE_COLUMNS[table]]
    for idx, value in enumerate(out):
        if value in ("t", "true", "True"):
            out[idx] = "1"
        elif value in ("f", "false", "False"):
            out[idx] = "0"
    return out


def insert_rows(conn: sqlite3.Connection, table: str, rows: list[list[str | None]]) -> None:
    if not rows:
        return
    cols = TABLE_COLUMNS[table]
    placeholders = ", ".join("?" for _ in cols)
    col_sql = ", ".join(f'"{c}"' for c in cols)
    conn.executemany(
        f'INSERT OR REPLACE INTO "{table}" ({col_sql}) VALUES ({placeholders})',
        rows,
    )


def copy_current_sqlite_tables(conn: sqlite3.Connection, current_db: Path) -> None:
    if not current_db.exists():
        return

    conn.execute("ATTACH DATABASE ? AS current_db", (str(current_db),))
    try:
        for table in [
            "tickers", "financials_quarterly", "prices_daily", "backfill_status",
            "macro_series", "macro_radar", "valuation_outputs", "daily_signal",
            "consensus_history", "consensus_synthesis", "consensus_report_text",
            "valuation_runs", "calibration_runs", "calibration_observations",
            "valuation_sensitivities",
        ]:
            exists = conn.execute(
                "SELECT 1 FROM current_db.sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                continue
            cols = [row[1] for row in conn.execute(f'PRAGMA current_db.table_info("{table}")')]
            target_cols = [c for c in cols if c in table_columns_in_db(conn, table)]
            if not target_cols:
                continue
            if table == "tickers":
                current_rows = conn.execute(
                    """
                    SELECT ticker, company_name, exchange, sector, industry, is_vn100, updated_at
                    FROM current_db.tickers
                    """
                ).fetchall()
                conn.executemany(
                    """
                    INSERT INTO tickers
                    (ticker, company_name, exchange, sector, industry, is_vn100, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                      company_name = COALESCE(excluded.company_name, tickers.company_name),
                      exchange = COALESCE(excluded.exchange, tickers.exchange),
                      sector = COALESCE(excluded.sector, tickers.sector),
                      industry = COALESCE(excluded.industry, tickers.industry),
                      is_vn100 = COALESCE(excluded.is_vn100, tickers.is_vn100),
                      updated_at = COALESCE(excluded.updated_at, tickers.updated_at)
                    """,
                    current_rows,
                )
                continue
            col_sql = ", ".join(f'"{c}"' for c in target_cols)
            conn.execute(
                f'INSERT OR REPLACE INTO "{table}" ({col_sql}) '
                f'SELECT {col_sql} FROM current_db."{table}"'
            )
        conn.commit()
    finally:
        conn.execute("DETACH DATABASE current_db")


def table_columns_in_db(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def import_valuation_csv(conn: sqlite3.Connection, csv_path: Path) -> None:
    if not csv_path.exists():
        return

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for idx, row in enumerate(reader, start=1):
            ticker = row.get("Mã") or row.get("Ticker")
            fv = row.get("FV") or row.get("Blended FV")
            price = row.get("Giá") or row.get("Current Price")
            upside = row.get("Upside %") or row.get("Upside (%)")
            if not ticker or not fv:
                continue
            try:
                upside_value = float(upside) / 100 if upside not in (None, "") else None
            except ValueError:
                upside_value = None
            flags = [f.strip() for f in (row.get("Cờ") or row.get("Flags") or "").split(",") if f.strip()]
            rows.append((
                1_000_000 + idx,
                ticker,
                fv,
                None,
                None,
                None,
                json.dumps(flags, ensure_ascii=False),
                json.dumps({"source": csv_path.name}, ensure_ascii=False),
                None,
            ))
            if price:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO valuation_runs
                    (id, ticker, analyst, created_at, engine, method, scenario,
                     assumptions_json, base_year_mode, target_price, current_price,
                     upside, recommendation, notes)
                    VALUES (?, ?, 'Batch CSV', NULL, NULL, ?, 'Base', '{}', 'TTM',
                            ?, ?, ?, NULL, ?)
                    """,
                    (
                        2_000_000 + idx,
                        ticker,
                        row.get("Phương pháp") or row.get("Method"),
                        fv,
                        price,
                        upside_value,
                        f"Imported from {csv_path.name}",
                    ),
                )
        conn.executemany(
            """
            INSERT OR REPLACE INTO valuation_outputs
            (id, ticker, blended_fair_value_per_share, fair_value_bull, fair_value_bear,
             margin_of_safety, flags, macro_snapshot, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def build_database(dump_path: Path, current_db: Path, output_db: Path, valuation_csv: Path) -> None:
    tmp_db = output_db.with_suffix(output_db.suffix + ".tmp")
    if tmp_db.exists():
        tmp_db.unlink()

    conn = sqlite3.connect(tmp_db)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")

        batch: dict[str, list[list[str | None]]] = {table: [] for table in TABLE_COLUMNS}
        counts = {table: 0 for table in TABLE_COLUMNS}
        for table, row in parse_copy_rows(dump_path):
            batch[table].append(row)
            counts[table] += 1
            if len(batch[table]) >= 5000:
                insert_rows(conn, table, batch[table])
                batch[table].clear()
        for table, rows in batch.items():
            insert_rows(conn, table, rows)

        copy_current_sqlite_tables(conn, current_db)
        import_valuation_csv(conn, valuation_csv)

        conn.commit()
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()

    if output_db.exists():
        output_db.unlink()
    tmp_db.rename(output_db)
    print(f"Built {output_db}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", default=str(PROJECT_ROOT / "vn100_backup.sql"))
    parser.add_argument("--current-db", default=str(PROJECT_ROOT / "vn100.db"))
    parser.add_argument("--output-db", default=str(PROJECT_ROOT / "vn100_full.db"))
    parser.add_argument("--valuation-csv", default=str(PROJECT_ROOT / "vn100_valuations.csv"))
    args = parser.parse_args()

    build_database(
        dump_path=Path(args.dump),
        current_db=Path(args.current_db),
        output_db=Path(args.output_db),
        valuation_csv=Path(args.valuation_csv),
    )


if __name__ == "__main__":
    main()
