# Quy trình refresh vĩ mô qua Chrome (nguồn JS-render)

Các chuỗi vĩ mô sau **render bằng JavaScript** nên `httpx` không lấy được số;
phải cào qua **Chrome MCP** (claude-in-chrome). Dữ liệu đổi chậm (CPI theo
tháng, lãi suất điều hành theo sự kiện, TPCP theo ngày nhưng ổn định) → refresh
tuần/tháng là đủ, KHÔNG cần mỗi lần quét.

## Nguồn & giá trị (đã đối chiếu, chính thống)

| Chỉ báo | Nguồn | URL |
|---|---|---|
| TPCP_10Y (+ toàn đường cong 1Y–30Y) | worldgovernmentbonds.com | http://www.worldgovernmentbonds.com/country/vietnam/ |
| CPI_YOY, POLICY_RATE, GDP_YOY, RETAIL_SALES_YOY | tradingeconomics.com | https://tradingeconomics.com/vietnam/indicators |

## Cách làm (Claude chạy — đã được cấp quyền Chrome)

1. `tabs_context_mcp{createIfEmpty:true}` → lấy tabId.
2. `navigate` tới URL nguồn.
3. `javascript_tool` trích số:

**worldgovernmentbonds (đường cong lợi suất):**
```js
[...document.querySelectorAll('table tr')]
  .map(tr => tr.innerText.replace(/\s+/g,' ').trim())
  .filter(t => /\d+\s*years?/i.test(t) && /%/.test(t));
// dòng "10 years 4.537% ... 10 Jul" → TPCP_10Y = 4.537/100
```

**tradingeconomics (bảng indicators):**
```js
(() => { const want=['Inflation Rate','Interest Rate','GDP Annual Growth','Retail Sales'];
  const out={}; document.querySelectorAll('table tr').forEach(tr=>{
    const c=[...tr.querySelectorAll('td,th')].map(x=>x.innerText.trim());
    if(c.length>=2) want.forEach(w=>{ if(c[0].toLowerCase().includes(w.toLowerCase())&&!out[w]) out[w]=c.slice(1);});
  }); return out; })();
// Inflation Rate -> CPI_YOY ; Interest Rate -> POLICY_RATE ;
// GDP Annual Growth -> GDP_YOY ; Retail Sales -> RETAIL_SALES_YOY
```

4. Ghi DB (idempotent, % → decimal):
```python
from valuation.db.session import SessionLocalWrite
from valuation.ingest.macro_store import MacroPoint, upsert_macro_series
import datetime
pts=[MacroPoint('TPCP_10Y', datetime.date(Y,M,D), yield/100, source='worldgovernmentbonds.com'), ...]
db=SessionLocalWrite(); upsert_macro_series(pts, db); db.close()
```

## Lưu ý
- **KHÔNG bịa số** — chỉ ghi giá trị thật đọc được; ghi kèm `source` để truy vết.
- M2_YOY: tradingeconomics chỉ có SỐ TUYỆT ĐỐI (VND Billion), không phải %YoY →
  chưa ingest (tránh suy diễn sai). Cần nguồn %YoY từ SBV hoặc tự tính từ 2 mốc
  cùng kỳ khi có dữ liệu rõ ràng.
- CREDIT_GROWTH: lấy từ SBV (CSV) — chưa có nguồn JS tin cậy.

## Lần refresh gần nhất
- 2026-07-11: TPCP_10Y=4.537% (10/7), CPI=4.69%, POLICY_RATE=4.5%, GDP=8.39%,
  RETAIL_SALES=14.8% (Jun/26).
