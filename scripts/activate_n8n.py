import os
import requests

API_KEY = os.environ["N8N_API_KEY"]  # secret trong .env, không ghi vào code
WORKFLOW_ID = "GFpcvTfiJURsNbgF"
URL = f"{os.environ['N8N_BASE_URL']}/api/v1/workflows/{WORKFLOW_ID}/activate"

headers = {
    "X-N8N-API-KEY": API_KEY,
    "Accept": "application/json"
}

print(f"Activating workflow {WORKFLOW_ID}...")
res = requests.post(URL, headers=headers)
print(res.status_code)
print(res.text)
