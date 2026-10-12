import pandas as pd
from sqlalchemy import create_engine
import datetime

# DB Connection
engine = create_engine("postgresql://macos@localhost:5432/vn100")
FILE_PATH = "docs/reference/2026.05.03. data_bank_v1.xlsx"

def import_tickers():
    print("Importing Tickers...")
    df = pd.read_excel(FILE_PATH, sheet_name="MaCK")
    records = []
    for _, row in df.iterrows():
        ticker = str(row.get("Mã CK", "")).strip()
        if not ticker or pd.isna(ticker): continue
        records.append({
            "ticker": ticker,
            "company_name": row.get("Tên công ty", ""),
            "exchange": row.get("Sàn", ""),
            "sector": row.get("Ngành ICB", ""),
            "is_vn100": True,
            "updated_at": datetime.datetime.now()
        })
    if not records: return
    for rec in records:
        try:
            pd.DataFrame([rec]).to_sql("tickers", engine, if_exists="append", index=False)
        except Exception:
            pass

def import_prices():
    print("Importing Prices...")
    df = pd.read_excel(FILE_PATH, sheet_name="Giá cổ phiếu")
    records = []
    for _, row in df.iterrows():
        ticker = str(row.get("Mã CK", "")).strip()
        date_val = row.get("Ngày")
        if pd.isna(date_val) or not ticker: continue
        records.append({
            "ticker": ticker,
            "trade_date": date_val,
            "close": row.get("Giá đóng cửa"),
            "price_unit": "VND"
        })
    if records:
        for rec in records:
            try:
                pd.DataFrame([rec]).to_sql("prices_daily", engine, if_exists="append", index=False)
            except Exception:
                pass

def import_financials():
    print("Importing Financials...")
    df = pd.read_excel(FILE_PATH, sheet_name="BCTC")
    key_cols = ["Mã CK", "Năm", "Quý", "Loại báo cáo (Q)", "Trạng thái kiểm toán (Q)"]
    value_cols = [c for c in df.columns if c not in key_cols]
    df_long = pd.melt(df, id_vars=key_cols, value_vars=value_cols, var_name="line_item", value_name="value")
    df_long = df_long.dropna(subset=["value"])
    
    records = []
    for _, row in df_long.iterrows():
        ticker = str(row["Mã CK"]).strip()
        if not ticker or pd.isna(ticker): continue
        records.append({
            "ticker": ticker,
            "fiscal_year": int(row["Năm"]) if not pd.isna(row["Năm"]) else 0,
            "fiscal_quarter": int(row["Quý"]) if not pd.isna(row["Quý"]) else 0,
            "is_consolidated": True,
            "is_restated": False,
            "statement": "BS", # We don't have statement separation in columns, defaulting to BS
            "line_item": str(row["line_item"]),
            "value": float(row["value"]),
            "currency": "VND"
        })
    if records:
        df_insert = pd.DataFrame(records)
        df_insert = df_insert.drop_duplicates(subset=["ticker", "fiscal_year", "fiscal_quarter", "is_consolidated", "is_restated", "statement", "line_item"])
        for _, rec in df_insert.iterrows():
            try:
                pd.DataFrame([rec]).to_sql("financials_quarterly", engine, if_exists="append", index=False)
            except Exception:
                pass

if __name__ == "__main__":
    import_tickers()
    import_prices()
    import_financials()
    print("Data Bank Import Completed Successfully!")
