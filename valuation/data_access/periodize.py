"""
Periodize utility — Chuyển đổi dữ liệu quý sang năm.
Quy tắc:
- Flow items (Doanh thu, LNST, Chi phí...): cộng 4 quý (TTM) hoặc sum 4 quý cùng năm (FY).
- Stock items (Tài sản, Nợ, Vốn CSH...): lấy giá trị cuối kỳ của quý gần nhất.
"""

from collections import defaultdict
from typing import Any
from weakref import ref

import pandas as pd
from sqlalchemy import desc
from sqlalchemy.orm import Session

from valuation.db.models import FinancialsQuarterly

# Danh sách phân loại các line_items thông dụng
# Mọi line_item chứa các từ khóa này sẽ được phân loại tương ứng.
# Mặc định nếu không match sẽ coi là Flow (cho an toàn) hoặc Stock tùy ngữ cảnh.
# Nhưng tốt nhất ta định nghĩa rõ ràng.

STOCK_KEYWORDS = [
    "tài sản",
    "vốn",
    "nợ",
    "cho vay",
    "tiền gửi",
    "tiền và",
    "đầu tư tài chính",
    "phải thu",
    "tồn kho",
    "phải trả",
    "assets",
    "equity",
    "loans",
    "deposits",
    "cash",
    "borrowings",
    "investments",
    "receivable",
    "inventories",
    "payable",
]


STATEMENT_PRIORITY = {"BS": 0, "IS": 1, "CF": 2}
_RECORDS_CACHE: dict[int, tuple[ref[pd.DataFrame], list[dict[str, Any]]]] = {}


def _has_value(value: Any) -> bool:
    return value is not None and not pd.isna(value)


def _statement_code(record: dict[str, Any]) -> str | None:
    value = record.get("statement")
    if not _has_value(value):
        return None
    text = str(value).strip().upper()
    return text or None


def _published_rank(value: Any) -> str:
    if not _has_value(value):
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _row_rank(record: dict[str, Any]) -> tuple[int, str]:
    return (
        int(bool(record.get("is_restated"))),
        _published_rank(record.get("published_at")),
    )


def _records_for(df_quarterly: pd.DataFrame) -> list[dict[str, Any]]:
    key = id(df_quarterly)
    cached = _RECORDS_CACHE.get(key)
    if cached is not None and cached[0]() is df_quarterly:
        return cached[1]
    records = df_quarterly.to_dict("records")
    _RECORDS_CACHE[key] = (
        ref(
            df_quarterly,
            lambda _dead, cache_key=key: _RECORDS_CACHE.pop(cache_key, None),
        ),
        records,
    )
    return records


def _preferred_statement(records: list[dict[str, Any]]) -> str | None:
    statements = {code for record in records if (code := _statement_code(record))}
    if len(statements) <= 1:
        return next(iter(statements), None)
    return min(statements, key=lambda code: STATEMENT_PRIORITY.get(code, 99))


def _best_rows_by_quarter(
    records: list[dict[str, Any]],
) -> dict[tuple[int, int], dict[str, Any]]:
    best: dict[tuple[int, int], dict[str, Any]] = {}
    for record in records:
        key = (int(record["fiscal_year"]), int(record["fiscal_quarter"]))
        if key not in best or _row_rank(record) >= _row_rank(best[key]):
            best[key] = record
    return best


def is_stock_item(line_item: str, statement: str | None = None) -> bool:
    """Kiểm tra line item là stock hay flow.

    Khi có loại báo cáo, dùng nó làm nguồn sự thật: BS là stock, IS/CF là
    flow. Keyword chỉ là fallback cho dữ liệu cũ chưa lưu ``statement``.
    """
    statement_code = (statement or "").strip().upper()
    if statement_code == "BS":
        return True
    if statement_code in {"IS", "CF"}:
        return False

    item_lower = line_item.lower()

    # Loại trừ một số khoản mục đặc thù của Lưu chuyển tiền tệ (Cash flow)
    # Vì chúng chứa từ "cash" hoặc "assets" nhưng lại là Flow item (cần được cộng dồn).
    if any(
        x in item_lower
        for x in [
            "cash_flow",
            "cash_inflow",
            "cash_outflow",
            "lưu chuyển",
            "payments",
            "purchases",
            "proceeds",
            "acquisition",
            "disposal",
            "tiền chi",
            "chi trả",
            "thu nhập",
        ]
    ):
        return False

    for kw in STOCK_KEYWORDS:
        if kw in item_lower:
            return True
    return False


def get_latest_quarters_for_ticker(
    db: Session, ticker: str, limit: int = 4
) -> list[tuple[int, int]]:
    """Lấy danh sách các quý gần nhất có dữ liệu của ticker (bỏ qua Q0)."""
    rows = (
        db.query(
            FinancialsQuarterly.fiscal_year,
            FinancialsQuarterly.fiscal_quarter,
        )
        .filter(
            FinancialsQuarterly.ticker == ticker,
            FinancialsQuarterly.fiscal_quarter > 0,
        )
        .distinct()
        .order_by(
            desc(FinancialsQuarterly.fiscal_year),
            desc(FinancialsQuarterly.fiscal_quarter),
        )
        .limit(limit)
        .all()
    )
    return [(r[0], r[1]) for r in rows]


def periodize_quarters_to_annual(
    df_quarterly: pd.DataFrame,
    target_year: int,
    mode: str = "TTM",
    latest_quarter: int | None = None,
) -> dict[str, float]:
    """
    Quy đổi dữ liệu quý sang năm cho một năm mục tiêu.
    df_quarterly: DataFrame có các cột ['fiscal_year', 'fiscal_quarter', 'line_item', 'value']
    mode: 'TTM' hoặc 'FY'
    target_year: Năm tài chính hoặc năm kết thúc TTM
    latest_quarter: Quý kết thúc TTM (chỉ dùng khi mode == 'TTM')

    Trả về Dict[line_item, value] đã được quy đổi.
    """
    if df_quarterly.empty:
        return {}

    records = _records_for(df_quarterly)

    # Lọc dữ liệu theo chế độ
    if mode == "FY":
        # Ưu tiên lấy dữ liệu đã được tính sẵn cho cả năm (Q0)
        fy_records = [
            record
            for record in records
            if record.get("fiscal_year") == target_year
            and record.get("fiscal_quarter") == 0
        ]
        if fy_records:
            # Q0 có thể chỉ chứa một báo cáo: vẫn giữ các chỉ tiêu đủ bốn quý
            # của báo cáo khác, rồi ưu tiên số cả năm được công bố.
            result = periodize_quarters_to_annual(
                df_quarterly[df_quarterly["fiscal_quarter"] != 0],
                target_year,
                mode="FY",
            )
            by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for record in fy_records:
                by_item[str(record["line_item"])].append(record)
            for item, item_records in by_item.items():
                statement = _preferred_statement(item_records)
                if statement:
                    item_records = [
                        record
                        for record in item_records
                        if _statement_code(record) == statement
                    ]
                row = max(item_records, key=_row_rank)
                val = row.get("value")
                if _has_value(val):
                    result[item] = float(val)
            return result

        # Fallback: Lấy cả 4 quý của năm target_year
        quarters_in_period = [(target_year, q) for q in range(1, 5)]
        if not any(
            record.get("fiscal_year") == target_year
            and record.get("fiscal_quarter", 0) > 0
            for record in records
        ):
            return {}
        latest_yr, latest_q = target_year, 4
    else:  # TTM
        # Nếu không truyền latest_quarter, tìm quý lớn nhất của target_year có trong df
        if latest_quarter is None:
            quarters = [
                int(record["fiscal_quarter"])
                for record in records
                if record.get("fiscal_year") == target_year
                and record.get("fiscal_quarter", 0) > 0
            ]
            latest_q = max(quarters) if quarters else 4
            latest_yr = target_year
        else:
            latest_yr = target_year
            latest_q = latest_quarter

        # Xác định 4 quý liên tiếp kết thúc tại (latest_yr, latest_q)
        quarters_in_period = []
        cy, cq = latest_yr, latest_q
        for _ in range(4):
            quarters_in_period.append((cy, cq))
            cq -= 1
            if cq == 0:
                cq = 4
                cy -= 1

    period_keys = set(quarters_in_period)
    by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (record.get("fiscal_year"), record.get("fiscal_quarter"))
        if key in period_keys:
            by_item[str(record["line_item"])].append(record)

    if not by_item:
        return {}

    result = {}
    for item, item_records in by_item.items():
        statement = _preferred_statement(item_records)
        if statement:
            item_records = [
                record
                for record in item_records
                if _statement_code(record) == statement
            ]

        # Cùng một kỳ có thể tồn tại cả bản ban đầu và bản đã soát xét/restated;
        # chỉ giữ một dòng mỗi quý, ưu tiên bản restated rồi tới ngày công bố mới.
        rows_by_quarter = _best_rows_by_quarter(item_records)

        if is_stock_item(item, statement=statement):
            latest = rows_by_quarter.get((latest_yr, latest_q))
            if latest and _has_value(latest.get("value")):
                result[item] = float(latest["value"])
        else:
            # Thiếu một quý của chính chỉ tiêu này thì chưa có FY/TTM thật.
            if len(rows_by_quarter) == 4 and all(
                _has_value(record.get("value")) for record in rows_by_quarter.values()
            ):
                result[item] = float(
                    sum(record["value"] for record in rows_by_quarter.values())
                )

    return result
