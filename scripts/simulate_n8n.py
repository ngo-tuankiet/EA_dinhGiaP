import requests
import json

URL = "http://localhost:8000/orchestration/run-daily"
payload = {
    "tickers": ["VCB", "HPG"],
    "force_override": True
}
# Bỏ trade_date để mặc định lấy ngày hôm nay

try:
    print(f"Triggering {URL} ...")
    response = requests.post(URL, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"Error: {e}")
