"""Kiểm kê VN100 và đối chiếu cache nguồn; chỉ đọc DB, không gọi AI/mạng."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from valuation.config import PROJECT_ROOT, load_defaults
from valuation.data_access.repo import build_company_data, drop_incomplete_filing_bs
from valuation.db.models import FinancialsQuarterly, PricesDaily
from valuation.db.session import SessionLocalRead
from valuation.engine.valuate import valuate
from valuation.ingest.normalizer import unpivot_financials
from valuation.ingest.taxonomy import (
    classify_source_value,
    source_fingerprint,
    taxonomy_mapping,
)
from valuation.ingest.universe import load_vn100_snapshot, select_audit_tickers
from valuation.services.ranking_store import read_json, write_json


def source_status(
    existing_value: float | None,
    existing_is_restated: bool | None,
    existing_source: str | None,
    source_value: float,
    line_item: str,
) -> str:
    """Như classify_source_value, nhưng ô DB đang thắng là filing chính thức đã soát xét
    (restated, nguồn https thuộc audit.filing_source_domains) VÀ lệch vendor không vượt
    audit.filing_precedence_max_rel_diff thì là đúng thứ tự ưu tiên (filing > vnstock), không
    phải xung đột: PVT Q2/2026 = BCTC giữa niên độ Deloitte vs bản quý VCI chưa soát xét.
    Lệch lớn hơn (GAS Q2/2026 tồn kho 9,3%: filing ghi số net vào khóa gross) vẫn là xung đột.
    """
    status = classify_source_value(existing_value, source_value, line_item)
    if not (
        status.endswith("CONFLICT")
        and existing_is_restated
        and existing_value is not None
    ):
        return status
    cfg = load_defaults()["audit"]
    url = urlparse(str(existing_source or ""))
    host = (url.hostname or "").lower()
    official = url.scheme == "https" and any(
        host == d or host.endswith("." + d) for d in cfg["filing_source_domains"]
    )
    rel_diff = abs(existing_value - source_value) / max(
        abs(existing_value), abs(source_value), 1
    )
    if official and rel_diff <= float(cfg["filing_precedence_max_rel_diff"]):
        return "FILING_PRECEDENCE"
    return status


def records_used(records: list[Any]) -> list[Any]:
    """Bản ghi định giá THỰC dùng: bỏ bộ BS restated của kỳ mà repo.drop_incomplete_filing_bs
    loại (filing thiếu tổng mục → định giá dùng BS vendor), để so nguồn trên đúng số đang dùng.
    """
    frame = pd.DataFrame(
        [
            {
                "fiscal_year": r.fiscal_year,
                "fiscal_quarter": r.fiscal_quarter,
                "statement": r.statement,
                "line_item": r.line_item,
                "is_restated": bool(r.is_restated),
            }
            for r in records
        ]
    )
    dropped = set(drop_incomplete_filing_bs(frame)[1])
    return [
        r
        for r in records
        if not (
            r.statement == "BS"
            and r.is_restated
            and (r.fiscal_year, r.fiscal_quarter) in dropped
        )
    ]


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
    used = sorted(
        records_used(records),
        key=lambda x: (bool(x.is_restated), str(x.published_at or "")),
    )
    current = {
        (r.statement, r.fiscal_year, r.fiscal_quarter, r.line_item): r for r in used
    }
    audited: set[tuple[int, int]] = set()
    critical = set(taxonomy_mapping()["publication_critical_items"])
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
            # Kỳ chỉ "đã đối chiếu" khi DB có ô TRỌNG YẾU khớp khóa nguồn. Kỳ chỉ có ở cache nguồn (DB
            # chưa nạp) mà vào tập này thì khi DB nạp kỳ đó, dấu vân tay đổi → SOURCE_AUDIT_STALE nhầm.
            if existing is not None and item["line_item"] in critical:
                audited.add((int(item["fiscal_year"]), int(item["fiscal_quarter"])))
            value = (
                float(existing.value)
                if existing and existing.value is not None
                else None
            )
            status = source_status(
                value,
                existing.is_restated if existing else None,
                existing.source if existing else None,
                item["value"],
                item["line_item"],
            )
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
    return {
        **counts,
        "source_checked_at": max(checked) if checked else None,
        # Chỉ các kỳ có ô trọng yếu thực sự so với nguồn; kỳ nạp sau → SOURCE_AUDIT_PARTIAL.
        "audited_periods": [list(p) for p in sorted(audited)],
        "db_fingerprint": source_fingerprint(records, year_from, audited),
    }, details


def _memory_session(overrides: list[tuple]) -> Any:
    """Bản sao DB TRONG BỘ NHỚ (sqlite backup) có ghi đè các ô; không chạm DB thật."""
    import sqlite3

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from valuation.db.session import engine_read

    if engine_read.url.get_backend_name() != "sqlite":
        raise RuntimeError("Đo ΔFV (F2c) chỉ hỗ trợ DB SQLite portable")
    path = Path(engine_read.url.database).resolve()
    mem = sqlite3.connect(":memory:", check_same_thread=False)
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        src.backup(mem)
    finally:
        src.close()
    mem.executemany(
        "UPDATE financials_quarterly SET value = ? WHERE ticker = ? AND statement = ? "
        "AND fiscal_year = ? AND fiscal_quarter = ? AND line_item = ? "
        "AND is_consolidated = 1 AND currency = 'VND'",
        overrides,
    )
    # commit trên bản sao: pool SQLAlchemy ROLLBACK khi trả kết nối → ghi đè chưa commit bị mất.
    mem.commit()
    if overrides and mem.total_changes < len(overrides):
        raise RuntimeError("Ghi đè trong bộ nhớ không khớp đủ ô xung đột")
    engine = create_engine("sqlite://", creator=lambda: mem, poolclass=StaticPool)
    return sessionmaker(bind=engine)()


def critical_fv_impact_pct(ticker: str, details: list[dict[str, Any]]) -> float | None:
    """F2c: |FV(ô CRITICAL thay bằng số nguồn) / FV(DB hiện tại) − 1| × 100, đo trên cùng một
    bản sao trong bộ nhớ. FV gốc ≤ 0 hoặc lỗi định giá → None (thiếu số đo → vẫn chặn).
    """
    from valuation.data_access import repo

    crit = [
        (
            d["source_value_vnd"],
            ticker,
            d["statement"],
            d["year"],
            d["quarter"],
            d["field"],
        )
        for d in details
        if d.get("ticker") == ticker and d.get("status") == "CRITICAL_CONFLICT"
    ]
    if not crit:
        return None
    fvs = []
    for overrides in ([], crit):
        repo._PEER_CACHE.clear()  # trung vị nhóm phải tính trên cùng bản sao
        db = _memory_session(overrides)
        try:
            result = valuate(build_company_data(db, ticker, fetch_live=False))
        except (ValueError, TypeError, KeyError, ArithmeticError):
            return None
        finally:
            db.close()
        fvs.append(float(result["blended_fair_value_per_share"]))
    repo._PEER_CACHE.clear()
    return abs(fvs[1] / fvs[0] - 1) * 100 if fvs[0] > 0 else None


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_portable_status(
    rows: list[dict[str, Any]], checked_at: str, year_from: int
) -> None:
    """Chỉ công bố trạng thái kiểm tra; không phát tán số nguồn Golden."""
    write_json(
        PROJECT_ROOT / "data/source_quality_status.json",
        {
            "checked_at": checked_at,
            "mapping_version": taxonomy_mapping()["version"],
            "year_from": year_from,
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
                        "FILING_PRECEDENCE",
                        "NO_MATCHING_KEY",
                        "source_contract_errors",
                        "source_checked_at",
                        "audited_periods",
                        "db_fingerprint",
                        "critical_fv_impact_pct",
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
        new_status = source_status(
            detail.get("old_value_vnd"),
            detail.get("old_is_restated"),
            detail.get("old_source"),
            detail["source_value_vnd"],
            detail["field"],
        )
        if new_status == old_status:
            continue
        row = rows[detail["ticker"]]
        row[old_status] = max(int(row.get(old_status, 0)) - 1, 0)
        row["CONFLICT"] = max(int(row.get("CONFLICT", 0)) - 1, 0)
        row[new_status] = int(row.get(new_status) or 0) + 1
        if new_status.endswith("CONFLICT"):
            row["CONFLICT"] = int(row.get("CONFLICT") or 0) + 1
        detail["status"] = new_status
        detail["affects_valuation"] = new_status == "CRITICAL_CONFLICT"
    saved["mapping_version"] = taxonomy_mapping()["version"]


def partial_audit_base(root: Path) -> dict[str, Any] | None:
    """Nền gộp cho lượt --tickers: source_audit.json (cache cục bộ, .gitignore); máy mới / bản portable
    chưa có file đó thì dùng data/source_quality_status.json (được commit) — trước đây thiếu
    source_audit.json thì status bị ghi đè chỉ còn các mã vừa chạy → mọi mã khác SOURCE_AUDIT_MISSING.
    """
    return read_json(root / ".vn100_ranking/sponsor/source_audit.json") or read_json(
        root / "data/source_quality_status.json"
    )


def partial_audit_year_from(
    saved: dict[str, Any] | None, mapping_version: str, default: int
) -> int:
    """year_from cho lượt audit một phần (--tickers): phải trùng audit đã lưu, vì dấu vân tay các mã
    giữ nguyên được băm từ year_from đó. mapping_version là của cả file → đổi thì phải audit đầy đủ.
    Chưa có audit nào để gộp → cũng phải audit đầy đủ.
    """
    if not saved:
        raise ValueError(
            "Chưa có audit đã lưu (source_audit.json / source_quality_status.json): chạy audit đầy đủ"
        )
    if saved.get("mapping_version") != mapping_version or "year_from" not in saved:
        raise ValueError(
            "Audit đã lưu khác mapping_version hoặc thiếu year_from: chạy audit đầy đủ (bỏ --tickers)"
        )
    return int(saved["year_from"])


def merge_partial_audit(
    saved: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    differences: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Lượt --tickers chỉ thay dòng/chênh lệch của các mã vừa chạy, GIỮ NGUYÊN trạng thái mã khác
    (trước đây ghi đè cả file → mọi mã khác thành SOURCE_AUDIT_MISSING). Nền là status portable thì
    không có 'differences' → chỉ còn chênh lệch của mã vừa chạy."""
    if not saved:
        raise ValueError(
            "Không có audit đã lưu để gộp: chạy audit đầy đủ (bỏ --tickers)"
        )
    done = {row["ticker"] for row in rows}
    kept = [row for row in saved.get("rows", []) if row["ticker"] not in done]
    kept_diff = [d for d in saved.get("differences", []) if d.get("ticker") not in done]
    return sorted(kept + rows, key=lambda row: row["ticker"]), kept_diff + differences


def attach_valuation(row: dict[str, Any]) -> None:
    """Kết quả công bố theo ĐÚNG ma trận nguồn vừa ghi (cổng của valuate đã gồm cờ audit)."""
    with SessionLocalRead() as db:
        try:
            result = valuate(build_company_data(db, row["ticker"], fetch_live=False))
            allowed = bool(result.get("publication_allowed", False))
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--finalize-existing", action="store_true")
    args = parser.parse_args()
    # VN100 ∪ công ty con SOTP (r4b): audit đầy đủ cũng giữ dòng công ty con, nếu không mã mẹ lại bị chặn.
    try:
        tickers = select_audit_tickers(args.tickers)
    except ValueError as exc:
        parser.error(str(exc))
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    output = args.output or PROJECT_ROOT / "temp_reports" / (
        "data_quality_" + now.strftime("%Y%m%d_%H%M%S")
    )
    output.mkdir(parents=True, exist_ok=True)
    # --tickers: gộp vào audit đã lưu thay vì ghi đè (giữ trạng thái các mã không chạy lại).
    partial = bool(args.tickers) and not args.finalize_existing
    saved_partial = partial_audit_base(PROJECT_ROOT) if partial else None
    if args.finalize_existing:
        saved = read_json(PROJECT_ROOT / ".vn100_ranking/sponsor/source_audit.json")
        # Đủ = có dòng cho mọi mã VN100; dòng công ty con SOTP là phần thêm (r4b), không làm audit "thừa".
        audited = {row["ticker"] for row in (saved or {}).get("rows", [])}
        if not saved or set(load_vn100_snapshot()["symbols"]) - audited:
            parser.error("Chưa có audit đủ 100 mã VN100 để hoàn tất")
        if "year_from" not in saved or any(
            "audited_periods" not in row for row in saved["rows"]
        ):
            parser.error(
                "Audit cũ chưa có dấu vân tay/tập kỳ đã đối chiếu: chạy lại audit đầy đủ"
            )
        reclassify_saved_audit(saved)
        summary, differences = saved["rows"], saved["differences"]
        checked_at, year_from = saved["checked_at"], int(saved["year_from"])
    else:
        summary, differences = [], []
        checked_at, year_from = now.isoformat(), now.year - 5
        if partial:
            try:
                year_from = partial_audit_year_from(
                    saved_partial, taxonomy_mapping()["version"], year_from
                )
            except ValueError as exc:
                parser.error(str(exc))
        for index, ticker in enumerate(tickers, start=1):
            with SessionLocalRead() as db:
                comparison, details = compare_source(
                    db, ticker, PROJECT_ROOT / ".vn100_ranking/sponsor", year_from
                )
                row = {"ticker": ticker, **comparison}
                differences.extend(details)
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
            print(
                f"{index}/{len(tickers)} {ticker}: critical_conflicts={row.get('CRITICAL_CONFLICT', 0)}, "
                f"filing_precedence={row.get('FILING_PRECEDENCE', 0)}",
                flush=True,
            )
    # F2c: đo tác động lên FV của các ô xung đột trọng yếu (ghi đè trong bộ nhớ, không ghi DB).
    for row in summary:
        if row.get("CRITICAL_CONFLICT", 0):
            row["critical_fv_impact_pct"] = critical_fv_impact_pct(
                row["ticker"], differences
            )
            print(
                f"{row['ticker']}: |ΔFV| khi dùng số nguồn = {row['critical_fv_impact_pct']}",
                flush=True,
            )
    audited_now = list(summary)
    if partial:
        summary, differences = merge_partial_audit(saved_partial, summary, differences)
    # Công bố ma trận nguồn TRƯỚC khi tính kết quả, để cổng của valuate đọc đúng audit mới.
    write_portable_status(summary, checked_at, year_from)
    for row in audited_now:
        attach_valuation(row)
    write_csv(output / "VN100_chat_luong_du_lieu.csv", summary)
    write_csv(output / "Doi_chieu_nguon.csv", differences)
    write_json(
        PROJECT_ROOT / ".vn100_ranking/sponsor/source_audit.json",
        {
            "checked_at": checked_at,
            "mapping_version": taxonomy_mapping()["version"],
            "year_from": year_from,
            "rows": summary,
            "differences": differences,
        },
    )
    print(f"Báo cáo nội bộ: {output}")


if __name__ == "__main__":
    main()
