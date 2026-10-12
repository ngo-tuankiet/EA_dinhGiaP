import re
import unicodedata

import pandas as pd


def _ascii_slug(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _disambiguate_legacy_item_ids(df_wide: pd.DataFrame) -> pd.DataFrame:
    """Giữ đủ các dòng khi VCI tái sử dụng một item_id cho nhiều khái niệm.

    Một số layout ngân hàng trả cùng ``item_id`` cho cả chỉ tiêu tổng và chỉ
    tiêu con. Dùng thẳng item_id sẽ tạo xung đột khóa và trước đây làm hỏng cả
    báo cáo BS. Giữ khóa gốc cho dòng đầu để tương thích dữ liệu cũ; các dòng
    khác nhận hậu tố từ nhãn nguồn. Nếu nhãn cũng trùng, dùng số thứ tự nguồn
    có chủ đích thay vì tự chọn một giá trị rồi làm mất dòng còn lại.
    """
    if "item_id" not in df_wide or not df_wide["item_id"].duplicated().any():
        return df_wide
    if "item" not in df_wide.columns and "item_en" not in df_wide.columns:
        return df_wide

    data = df_wide.copy()
    period_cols = [
        col for col in data.columns if re.fullmatch(r"\d{4}(?:-Q[1-4])?", str(col))
    ]
    for item_id, indexes in data.groupby("item_id", sort=False).groups.items():
        indexes = list(indexes)
        if len(indexes) < 2:
            continue

        # Bản sao hoàn toàn giống nhau sẽ được drop_duplicates ở cuối; chỉ
        # tách khóa khi ít nhất một kỳ thực sự có số khác nhau.
        values = data.loc[indexes, period_cols]
        if not any(values[col].nunique(dropna=False) > 1 for col in period_cols):
            continue

        used = {str(item_id)}
        for variant_number, index in enumerate(indexes[1:], start=2):
            label = data.at[index, "item"] if "item" in data else ""
            if (pd.isna(label) or not str(label).strip()) and "item_en" in data:
                label = data.at[index, "item_en"]
            suffix = _ascii_slug(label)
            candidate = f"{item_id}__{suffix}" if suffix else ""
            if not candidate or candidate in used:
                candidate = f"{item_id}__source_variant_{variant_number}"
            while candidate in used:
                variant_number += 1
                candidate = f"{item_id}__source_variant_{variant_number}"
            data.at[index, "item_id"] = candidate
            used.add(candidate)
    return data


def normalize_daily_prices(df: pd.DataFrame) -> pd.DataFrame:
    """
    Chuẩn hóa giá daily từ vnstock.
    vnstock trả giá ở đơn vị nghìn VND (ví dụ: 56.29 = 56,290 VND).
    Hàm này nhân các cột giá với 1000 để chuẩn hóa về VND tuyệt đối, khớp với BCTC.
    """
    if df.empty:
        return df

    # Các cột cần nhân x1000
    price_cols = ["open", "high", "low", "close"]

    # Tạo bản sao để tránh DtypeWarning hoặc SettingWithCopyWarning
    df_norm = df.copy()
    units = df_norm.get(
        "price_unit",
        pd.Series(df.attrs.get("price_unit", "thousand_VND"), index=df_norm.index),
    )
    factors = units.map({"VND": 1.0, "thousand_VND": 1000.0})
    if factors.isna().any():
        raise ValueError("Đơn vị giá không được hỗ trợ; không tự đoán hệ số quy đổi")

    for col in price_cols:
        if col in df_norm.columns:
            df_norm[col] = df_norm[col] * factors

    # Thêm cột price_unit để rõ ràng
    df_norm["price_unit"] = "VND"

    return df_norm


def unpivot_financials(df_wide: pd.DataFrame, statement_type: str) -> pd.DataFrame:
    """
    Unpivot (melt) BCTC từ dạng wide (quý làm cột) sang dạng long.
    df_wide có các cột như: 'item', 'item_en', 'item_id', '2024-Q1', '2023-Q4'...
    Đầu ra sẽ có: 'line_item', 'fiscal_year', 'fiscal_quarter', 'value', 'statement'.
    """
    if df_wide.empty:
        return pd.DataFrame()

    # Tìm các cột là quý (format: YYYY-QX) hoặc năm (format: YYYY)
    value_vars = [c for c in df_wide.columns if re.match(r"^\d{4}(-Q\d)?$", str(c))]

    if "id" in df_wide.columns and "unit" in df_wide.columns:
        from valuation.ingest.taxonomy import taxonomy_to_legacy_long

        df_long = taxonomy_to_legacy_long(df_wide, statement_type)
    else:
        legacy_wide = _disambiguate_legacy_item_ids(df_wide)
        df_long = legacy_wide.melt(
            id_vars=["item_id"],
            value_vars=value_vars,
            var_name="period",
            value_name="value",
        )

    # Đổi tên 'item_id' thành 'line_item'
    df_long = df_long.rename(columns={"item_id": "line_item"})

    # Loại bỏ giá trị NA
    df_long = df_long.dropna(subset=["value"])
    if not df_long["period"].astype(str).str.fullmatch(r"\d{4}(?:-Q[1-4])?").all():
        raise ValueError("Kỳ BCTC không hợp lệ")

    # Parse period -> fiscal_year, fiscal_quarter
    df_long["fiscal_year"] = df_long["period"].str[:4].astype(int)

    def parse_quarter(p):
        if "-Q" in p:
            return int(p[-1])
        return 0  # 0 indicates Full Year data

    df_long["fiscal_quarter"] = df_long["period"].apply(parse_quarter)

    metadata = df_wide.attrs
    if statement_type not in {"BS", "IS", "CF"}:
        raise ValueError("Loại báo cáo không hợp lệ")
    if metadata.get("currency", "VND") != "VND":
        raise ValueError("Chỉ nhận BCTC VND; ngoại tệ cần quy trình quy đổi riêng")
    multiplier = float(metadata.get("unit_multiplier", 1.0))
    if multiplier not in {1.0, 1000.0, 1e6, 1e9}:
        raise ValueError("Hệ số đơn vị BCTC không được hỗ trợ")
    df_long["value"] = pd.to_numeric(df_long["value"], errors="raise") * multiplier
    import numpy as np

    if not np.isfinite(df_long["value"]).all():
        raise ValueError("Số BCTC phải hữu hạn")
    basis = metadata.get("period_basis", "quarter")
    if basis not in {"quarter", "cumulative"}:
        raise ValueError("Chưa xác minh số quý riêng hay lũy kế")
    if basis == "cumulative" and statement_type != "BS":
        original = df_long.set_index(["line_item", "fiscal_year", "fiscal_quarter"])[
            "value"
        ]
        for idx, row in df_long.iterrows():
            q = int(row["fiscal_quarter"])
            if q <= 1:
                continue
            previous = (row["line_item"], row["fiscal_year"], q - 1)
            if previous not in original.index:
                raise ValueError(
                    f"Thiếu quý trước để tách số lũy kế: {row['line_item']} {row['period']}"
                )
            df_long.at[idx, "value"] = row["value"] - original.loc[previous]

    df_long["statement"] = statement_type
    df_long["is_consolidated"] = metadata.get("is_consolidated", True)
    df_long["is_restated"] = metadata.get("is_restated", False)
    df_long["currency"] = "VND"
    df_long["source"] = metadata.get("source", "vnstock")
    publication_dates = metadata.get("publication_dates", {})
    publication_values = pd.to_datetime(
        df_long["period"]
        .map(publication_dates)
        .fillna(metadata.get("published_at") or pd.NaT),
        errors="raise",
    ).dt.date
    df_long["published_at"] = pd.Series(
        [None if pd.isna(value) else value for value in publication_values],
        index=df_long.index,
        dtype=object,
    )

    # Chỉ giữ các cột cần thiết
    cols_to_keep = [
        "fiscal_year",
        "fiscal_quarter",
        "is_consolidated",
        "is_restated",
        "statement",
        "line_item",
        "value",
        "currency",
        "source",
        "published_at",
    ]

    df_long = df_long[cols_to_keep]
    # Bỏ các dòng trùng lặp dựa trên khóa chính
    keys = [
        "fiscal_year",
        "fiscal_quarter",
        "is_consolidated",
        "is_restated",
        "statement",
        "line_item",
    ]
    if (df_long.groupby(keys)["value"].nunique() > 1).any():
        raise ValueError("Nguồn trả nhiều số mâu thuẫn cho cùng chỉ tiêu và kỳ")
    df_long = df_long.drop_duplicates(subset=keys, keep="last")

    return df_long.reset_index(drop=True)
