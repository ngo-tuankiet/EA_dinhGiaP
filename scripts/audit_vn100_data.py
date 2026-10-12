"""Kiểm kê VN100 và đối chiếu cache nguồn; chỉ đọc DB, không gọi AI/mạng."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from valuation.config import PROJECT_ROOT
from valuation.data_access.repo import build_company_data
from valuation.db.models import FinancialsQuarterly, PricesDaily
from valuation.db.session import SessionLocalRead
from valuation.engine.valuate import valuate
from valuation.ingest.normalizer import unpivot_financials
from valuation.ingest.taxonomy import classify_source_value, taxonomy_mapping
from valuation.ingest.universe import load_vn100_snapshot
from valuation.services.ranking_store import read_json, write_json


def compare_source(
    db: Any, ticker: str, root: Path, year_from: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = (
        db.query(FinancialsQuarterly)
        .filter(
            FinancialsQuarterly.ticker == ticker,
            FinancialsQuarterly.fiscal_year >= year_from,
            FinancialsQuarterly.is_consolidated.is_(True),
            FinancialsQuarterly.currency == "VND",
        )
        .all()
    )
    records.sort(key=lambda x: (bool(x.is_restated), str(x.published_at or "")))
    current = {
        (r.statement, r.fiscal_year, r.fiscal_quarter, r.line_item): r for r in records
    }
    counts: Counter = Counter()
    details: list[dict[str, Any]] = []
    checked = []
    for kind in ("BS", "IS", "CF", "BS_FY", "IS_FY", "CF_FY"):
        payload = read_json(root / ticker / f"{kind}.json")
        if not payload:
            counts["missing_source_files"] += 1
            continue
        raw = pd.DataFrame(payload["rows"])
        raw.attrs.update(payload.get("attrs", {}), source=payload["source"])
        try:
            rows = unpivot_financials(raw, kind.removesuffix("_FY"))
        except ValueError as exc:
            counts["source_contract_errors"] += 1
            details.append(
                {
                    "ticker": ticker,
                    "statement": kind,
                    "status": "SOURCE_CONTRACT_ERROR",
                    "reason": str(exc),
                }
            )
            continue
        checked.append(payload["checked_at"])
        for item in rows.to_dict("records"):
            if item["fiscal_year"] < year_from:
                continue
            key = (
                item["statement"],
                item["fiscal_year"],
                item["fiscal_quarter"],
                item["line_item"],
            )
            existing = current.get(key)
            value = (
                float(existing.value)
                if existing and existing.value is not None
                else None
            )
            status = classify_source_value(value, item["value"], item["line_item"])
            if status.endswith("CONFLICT"):
                counts["CONFLICT"] += 1
            counts[status] += 1
            if status != "MATCH":
                denominator = max(abs(value or 0), abs(item["value"]), 1)
                details.append(
                    {
                        "ticker": ticker,
                        "statement": key[0],
                        "year": key[1],
                        "quarter": key[2],
                        "field": key[3],
                        "old_value_vnd": value,
                        "source_value_vnd": item["value"],
                        "old_source": existing.source if existing else None,
                        "old_is_restated": (
                            bool(existing.is_restated) if existing else None
                        ),
                        "relative_difference": (
                            abs(value - item["value"]) / denominator
                            if value is not None
                            else None
                        ),
                        "affects_valuation": status == "CRITICAL_CONFLICT",
                        "status": status,
                        "source_checked_at": payload["checked_at"],
                        "source_file": str(root / ticker / f"{kind}.json"),
                    }
                )
    return {**counts, "source_checked_at": max(checked) if checked else None}, details


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_portable_status(rows: list[dict[str, Any]], checked_at: str) -> None:
    """Chỉ công bố trạng thái kiểm tra; không phát tán số nguồn Golden."""
    write_json(
        PROJECT_ROOT / "data/source_quality_status.json",
        {
            "checked_at": checked_at,
            "mapping_version": taxonomy_mapping()["version"],
            "rows": [
                {
                    key: row.get(key)
                    for key in (
                        "ticker",
                        "MATCH",
                        "SIGN_CONVENTION_MATCH",
                        "ROUNDING_MATCH",
                        "CONFLICT",
                        "CRITICAL_CONFLICT",
                        "INFORMATIONAL_CONFLICT",
                        "NO_MATCHING_KEY",
                        "source_contract_errors",
                        "source_checked_at",
                    )
                }
                for row in rows
            ],
        },
    )


def reclassify_saved_audit(saved: dict[str, Any]) -> None:
    """Áp quy tắc so sánh mới lên bằng chứng đã tải, không gọi lại nguồn."""
    rows = {row["ticker"]: row for row in saved["rows"]}
    conflict_statuses = {"CRITICAL_CONFLICT", "INFORMATIONAL_CONFLICT"}
    for detail in saved["differences"]:
        old_status = detail.get("status")
        if old_status not in conflict_statuses:
            continue
        new_status = classify_source_value(
            detail.get("old_value_vnd"),
            detail["source_value_vnd"],
            detail["field"],
        )
        if new_status == old_status:
            continue
        row = rows[detail["ticker"]]
        row[old_status] = max(int(row.get(old_status, 0)) - 1, 0)
        row["CONFLICT"] = max(int(row.get("CONFLICT", 0)) - 1, 0)
        row[new_status] = int(row.get(new_status, 0)) + 1
        detail["status"] = new_status
        detail["affects_valuation"] = new_status == "CRITICAL_CONFLICT"
    saved["mapping_version"] = taxonomy_mapping()["version"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--finalize-existing", action="store_true")
    args = parser.parse_args()
    universe = load_vn100_snapshot()["symbols"]
    tickers = args.tickers or universe
    if set(tickers) - set(universe):
        parser.error("Mã ngoài VN100")
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    output = args.output or PROJECT_ROOT / "temp_reports" / (
        "data_quality_" + now.strftime("%Y%m%d_%H%M%S")
    )
    output.mkdir(parents=True, exist_ok=True)
    if args.finalize_existing:
        saved = read_json(PROJECT_ROOT / ".vn100_ranking/sponsor/source_audit.json")
        if not saved or len(saved.get("rows", [])) != 100:
            parser.error("Chưa có audit đủ 100 mã để hoàn tất")
        reclassify_saved_audit(saved)
        # Công bố ma trận nguồn trước, để build_company_data không tự chặn vì
        # phiên bản audit trước đó đã hết hạn trong lúc tính lại kết quả.
        write_portable_status(saved["rows"], saved["checked_at"])
        for row in saved["rows"]:
            with SessionLocalRead() as db:
                try:
                    company = build_company_data(db, row["ticker"], fetch_live=False)
                    result = valuate(company)
                    allowed = result.get("publication_allowed", False) and not row.get(
                        "CRITICAL_CONFLICT", 0
                    )
                    row.update(
                        publication_allowed=allowed,
                        fair_value_vnd=(
                            result["blended_fair_value_per_share"] if allowed else None
                        ),
                        flags=" | ".join(result.get("flags", [])),
                        errors=" | ".join(
                            check["message"]
                            for check in result.get("data_checks", [])
                            if check["severity"] == "error"
                        ),
                    )
                except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                    row.update(
                        publication_allowed=False,
                        fair_value_vnd=None,
                        errors=f"{type(exc).__name__}: {exc}",
                    )
            if row.get("CRITICAL_CONFLICT", 0):
                row["publication_allowed"] = False
                row["fair_value_vnd"] = None
                marker = f"SOURCE_CONFLICT:{row['CRITICAL_CONFLICT']}"
                if marker not in row.get("errors", ""):
                    row["errors"] = (row.get("errors", "") + " | " + marker).strip(" |")
        write_csv(output / "VN100_chat_luong_du_lieu.csv", saved["rows"])
        write_csv(output / "Doi_chieu_nguon.csv", saved["differences"])
        write_json(PROJECT_ROOT / ".vn100_ranking/sponsor/source_audit.json", saved)
        write_portable_status(saved["rows"], saved["checked_at"])
        print(f"Đã hoàn tất báo cáo từ audit đủ 100 mã: {output}")
        return
    summary: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []
    for index, ticker in enumerate(tickers, start=1):
        with SessionLocalRead() as db:
            comparison, details = compare_source(
                db, ticker, PROJECT_ROOT / ".vn100_ranking/sponsor", now.year - 5
            )
            row = {"ticker": ticker, **comparison}
            differences.extend(details)
            try:
                company = build_company_data(db, ticker, fetch_live=False)
                result = valuate(company)
                allowed = result.get(
                    "publication_allowed", False
                ) and not comparison.get("CRITICAL_CONFLICT", 0)
                row.update(
                    publication_allowed=allowed,
                    fair_value_vnd=(
                        result["blended_fair_value_per_share"] if allowed else None
                    ),
                    flags=" | ".join(result.get("flags", [])),
                    errors=" | ".join(
                        c["message"]
                        for c in result.get("data_checks", [])
                        if c["severity"] == "error"
                    ),
                )
                if comparison.get("CRITICAL_CONFLICT", 0):
                    row["errors"] = (
                        row["errors"] + " | " if row["errors"] else ""
                    ) + f"SOURCE_CONFLICT:{comparison['CRITICAL_CONFLICT']}"
            except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                row.update(
                    publication_allowed=False, errors=f"{type(exc).__name__}: {exc}"
                )
            records = (
                db.query(FinancialsQuarterly)
                .filter(FinancialsQuarterly.ticker == ticker)
                .all()
            )
            row["financial_rows"] = len(records)
            row["published_date_rows"] = sum(
                r.published_at is not None for r in records
            )
            prices = (
                db.query(PricesDaily)
                .filter(PricesDaily.ticker == ticker, PricesDaily.close > 0)
                .order_by(PricesDaily.trade_date.desc())
                .first()
            )
            row["price_date"] = str(prices.trade_date) if prices else None
        summary.append(row)
        write_json(
            output / "audit.json",
            {
                "checked_at": now.isoformat(),
                "mapping_version": taxonomy_mapping()["version"],
                "rows": summary,
            },
        )
        print(
            f"{index}/{len(tickers)} {ticker}: publication_allowed={row['publication_allowed']}, critical_conflicts={row.get('CRITICAL_CONFLICT', 0)}",
            flush=True,
        )
    write_csv(output / "VN100_chat_luong_du_lieu.csv", summary)
    write_csv(output / "Doi_chieu_nguon.csv", differences)
    write_json(
        PROJECT_ROOT / ".vn100_ranking/sponsor/source_audit.json",
        {
            "checked_at": now.isoformat(),
            "mapping_version": taxonomy_mapping()["version"],
            "rows": summary,
            "differences": differences,
        },
    )
    write_portable_status(summary, now.isoformat())
    print(f"Báo cáo nội bộ: {output}")


if __name__ == "__main__":
    main()
