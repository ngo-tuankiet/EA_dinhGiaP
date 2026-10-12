import os
import json
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from valuation.data_access.repo import build_company_data
from valuation.engine.valuate import valuate
from valuation.engine.sector_router import route

engine = create_engine(os.environ["DATABASE_URL_READONLY"])  # secret trong .env
Session = sessionmaker(bind=engine)
db = Session()

with open('valuation/config/routing.json', 'r', encoding='utf-8') as f:
    routing_data = json.load(f)

tickers = list(routing_data.keys())

# Vĩ mô cập nhật MỖI LẦN QUÉT: refresh FX/hàng hóa (idempotent, chỉ 3 call
# yfinance) rồi dựng MacroEnvironment từ DB — mọi mã trong batch dùng cùng
# một snapshot vĩ mô nhất quán.
from valuation.db.session import SessionLocalWrite
from valuation.ingest.macro_fetcher import fetch_market_macro
from valuation.models.macro_env import MacroEnvironment
_db_w = SessionLocalWrite()
try:
    n = fetch_market_macro(_db_w)
    print(f"Refreshed {n} macro series (USDVND/STEEL_HRC/CRUDE_OIL)")
except Exception as e:
    print(f"Macro refresh failed (dùng dữ liệu DB hiện có): {e}")
finally:
    _db_w.close()
macro_env = MacroEnvironment.from_db(db)
print(f"MacroEnvironment: inflation={macro_env.inflation_rate:.2%}, stance={macro_env.sbv_stance}, rf={macro_env.risk_free_rate}")

results = []
import time
for i, ticker in enumerate(tickers):
    try:
        print(f"[{i+1}/{len(tickers)}] Valuating {ticker}...")
        r = route(ticker)
        if not r: continue
        comp = build_company_data(db, ticker, 'TTM')
        res = valuate(comp, macro_env=macro_env)
        time.sleep(1.2) # Avoid rate limit
        
        decision = res.get('decision', {})
        results.append({
            'Ticker': ticker,
            # route() trả sector dưới key 'group' (KHÔNG phải 'sector'); business_nature riêng.
            'Sector': r.get('group', ''),
            'Business Nature': r.get('business_nature', ''),
            'Method': r.get('method', ''),
            'Current Price': comp.current_price,
            'Intrinsic FV': res.get('intrinsic_fv', 0),
            'Relative FV': res.get('relative_fv', 0),
            'Blended FV': res.get('blended_fair_value_per_share', 0),
            # valuate() trả upside SẴN theo % (không nhân 100 nữa — trước đây double-scale).
            'Upside (%)': res.get('upside', 0),
            # MOS nằm trong res['decision']['target_mos'] (ratio) — KHÔNG phải res['mos_target'].
            'MOS Target (%)': decision.get('target_mos', 0) * 100,
            'Recommendation': res.get('recommendation', ''),
            'Flags': ', '.join(res.get('flags', []))
        })
    except Exception as e:
        results.append({
            'Ticker': ticker,
            'Sector': routing_data[ticker].get('sector', ''),
            'Recommendation': f'ERROR: {e}'
        })

df = pd.DataFrame(results)
output_path = '/Users/macos/Desktop/VN100_Valuation_Results.csv'
df.to_csv(output_path, index=False, encoding='utf-8-sig')
print(f"Done! Exported to {output_path}")
