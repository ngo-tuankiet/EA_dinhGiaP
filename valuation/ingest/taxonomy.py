"""Ánh xạ chỉ tiêu VCI có version; phần chưa ánh xạ giữ ở cache nguồn."""

from __future__ import annotations

import json
import math
from functools import lru_cache

import pandas as pd

from valuation.config import PROJECT_ROOT


@lru_cache(maxsize=1)
def taxonomy_mapping() -> dict:
    return json.loads(
        (PROJECT_ROOT / "config/financial_taxonomy.json").read_text(encoding="utf-8")
    )


def taxonomy_to_legacy_long(frame: pd.DataFrame, statement: str) -> pd.DataFrame:
    """Không đoán alias từ tên gần giống; chỉ đổi đơn vị tiền đã biết."""
    data = frame.copy()
    if "period" not in data:
        periods = [
            c
            for c in data
            if pd.Series([str(c)]).str.fullmatch(r"\d{4}(?:-Q[1-4])?").iloc[0]
        ]
        data = data.melt(
            id_vars=["id", "unit"],
            value_vars=periods,
            var_name="period",
            value_name="value",
        )
    mapping = taxonomy_mapping()["items"].copy()
    if "IS_NET_INTEREST_INCOME" in set(data["id"]):
        mapping["IS_OPERATING_EXPENSES"] = "general_and_admin_expenses"
    data = data[
        data["id"].isin(mapping) & data["id"].str.startswith(statement + "_")
    ].copy()
    data["line_item"] = data["id"].map(mapping)
    if data.empty:
        raise ValueError("Chưa có ánh xạ đã xác định cho loại BCTC này")
    factor = data["unit"].map(
        {
            "VNĐ": 1.0,
            "VND": 1.0,
            "nghìn đồng": 1000.0,
            "triệu đồng": 1e6,
            "tỷ đồng": 1e9,
        }
    )
    if factor.isna().any():
        raise ValueError("Đơn vị chỉ tiêu taxonomy chưa được hỗ trợ")
    data["value"] = pd.to_numeric(data["value"], errors="raise") * factor
    return data[["line_item", "period", "value"]]


def classify_source_value(existing: float | None, source: float, line_item: str) -> str:
    """Phân loại đối chiếu, tách sai khác số liệu khỏi quy ước dấu/làm tròn."""
    if existing is None:
        return "NO_MATCHING_KEY"
    mapping = taxonomy_mapping()
    if math.isclose(existing, source, rel_tol=1e-12, abs_tol=1):
        return "MATCH"
    compare_existing = existing
    compare_source = source
    if line_item in set(mapping["absolute_comparison_items"]):
        compare_existing = abs(existing)
        compare_source = abs(source)
        if math.isclose(compare_existing, compare_source, rel_tol=1e-12, abs_tol=1):
            return "SIGN_CONVENTION_MATCH"
    if math.isclose(
        compare_existing,
        compare_source,
        rel_tol=mapping["comparison_relative_tolerance"],
        abs_tol=1,
    ):
        return "ROUNDING_MATCH"
    if line_item in set(mapping["publication_critical_items"]):
        return "CRITICAL_CONFLICT"
    return "INFORMATIONAL_CONFLICT"
