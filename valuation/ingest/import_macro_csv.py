"""
Khung NHẬP CSV vĩ mô tổng quát — analyst tải số liệu CHÍNH THỐNG (GSO/SBV/HNX/
VBMA) rồi import vào macro_series. Không gọi mạng, không bịa số.

Hỗ trợ 2 định dạng CSV:

(A) WIDE — 1 file 1 chỉ báo:
    date,value
    2026-06-30,3.2
    (value có thể là % "3.2" hoặc decimal "0.032" — xem `as_percent`)

(B) LONG — 1 file nhiều chỉ báo:
    date,indicator_code,value
    2026-06-30,CPI_YOY,3.2
    2026-06-30,POLICY_RATE,4.5

Chuẩn hóa đơn vị theo registry: chỉ báo `decimal_rate` mà nhập dạng % (>1) sẽ
tự chia 100 (bật `as_percent=True`); chỉ báo giá (USDVND/STEEL_HRC/CRUDE_OIL)
giữ nguyên. Ghi idempotent qua upsert_macro_series (validate registry → từ chối
code lạ). Nguồn ghi kèm để truy vết (Luật vàng #5).
"""
from __future__ import annotations

import datetime
from typing import List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from valuation.config import get_macro_series_registry
from valuation.ingest.macro_store import MacroPoint, upsert_macro_series

# Chỉ báo lưu dạng decimal_rate — nếu nhập bằng % (giá trị > 1) thì chia 100.
_RATE_CODES = {
    "TPCP_10Y", "CPI_YOY", "GDP_YOY", "M2_YOY",
    "CREDIT_GROWTH", "POLICY_RATE", "RETAIL_SALES_YOY",
}


def _parse_date(v) -> datetime.date:
    return pd.to_datetime(v, dayfirst=False).date()


def _normalize_value(code: str, raw: float, as_percent: bool = True) -> float:
    """Đưa value về đơn vị registry cho chỉ báo decimal_rate.

    AUTO-DETECT theo ĐỘ LỚN (tin cậy hơn cờ, tránh chia nhầm giá trị đã decimal):
    lãi suất/CPI/... ở dạng decimal luôn |v| < 1 (30% = 0.30), còn ở dạng % thì
    |v| ≥ 1 (3.2%). Nên chỉ chia 100 khi |v| > 1. `as_percent` giữ để tương thích
    API (gợi ý), không ghi đè auto-detect. Chỉ báo giá (USDVND...) giữ nguyên.
    """
    if code in _RATE_CODES and abs(raw) > 1.0:
        return raw / 100.0
    return raw


def rows_to_points(
    rows: List[dict],
    source: str,
    as_percent: bool = True,
    registry: Optional[dict] = None,
) -> List[MacroPoint]:
    """Chuyển list dict {date, indicator_code, value} → MacroPoint đã chuẩn hóa.

    Bỏ qua dòng thiếu value (NaN). Raise nếu code ngoài registry (fail-fast,
    tránh rác — thực thi ở upsert nhưng kiểm sớm ở đây để báo lỗi rõ).
    """
    reg = registry if registry is not None else get_macro_series_registry()
    points: List[MacroPoint] = []
    for r in rows:
        code = str(r["indicator_code"]).strip().upper()
        if code not in reg:
            raise ValueError(f"indicator_code '{code}' không có trong registry {sorted(reg)}")
        val = r["value"]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        points.append(MacroPoint(
            indicator_code=code,
            date=_parse_date(r["date"]),
            value=_normalize_value(code, float(val), as_percent),
            source=source,
        ))
    return points


def import_macro_csv(
    csv_path: str,
    db: Session,
    indicator_code: Optional[str] = None,
    source: str = "manual_csv",
    as_percent: bool = True,
    registry: Optional[dict] = None,
) -> int:
    """Đọc CSV (WIDE hoặc LONG) và ghi macro_series idempotent. Trả số điểm ghi.

    indicator_code: bắt buộc cho CSV WIDE (chỉ có date,value); bỏ trống cho LONG
                    (CSV phải có cột indicator_code).
    as_percent: True nếu cột value là % (vd 3.2 = 3.2%); False nếu đã là decimal.
    """
    df = pd.read_csv(csv_path)
    cols = {c.lower().strip(): c for c in df.columns}

    if "date" not in cols:
        raise ValueError("CSV phải có cột 'date'.")
    date_col = cols["date"]

    if "indicator_code" in cols:  # LONG format
        rows = [
            {"date": r[date_col], "indicator_code": r[cols["indicator_code"]], "value": r[cols["value"]]}
            for _, r in df.iterrows()
        ]
    else:  # WIDE format — cần indicator_code tham số
        if not indicator_code:
            raise ValueError("CSV dạng WIDE (date,value) cần truyền indicator_code.")
        if "value" not in cols:
            raise ValueError("CSV WIDE phải có cột 'value'.")
        rows = [
            {"date": r[date_col], "indicator_code": indicator_code, "value": r[cols["value"]]}
            for _, r in df.iterrows()
        ]

    points = rows_to_points(rows, source=source, as_percent=as_percent, registry=registry)
    return upsert_macro_series(points, db, registry=registry)
