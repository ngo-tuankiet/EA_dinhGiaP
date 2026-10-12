import os
import json
import requests

API_KEY = os.environ["N8N_API_KEY"]  # secret trong .env, không ghi vào code
N8N_URL = f"{os.environ['N8N_BASE_URL']}/api/v1/workflows"
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]

try:
    with open("docs/n8n_workflow_spec.json", "r") as f:
        workflow_data = json.load(f)
        
    for node in workflow_data.get("nodes", []):
        if node.get("name") == "Discord Error Alert":
            if "parameters" in node and "url" in node["parameters"]:
                node["parameters"]["url"] = DISCORD_WEBHOOK
                
    if "settings" not in workflow_data:
        workflow_data["settings"] = {}
        
    headers = {
        "X-N8N-API-KEY": API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    print("Sending workflow to n8n...")
    response = requests.post(N8N_URL, headers=headers, json=workflow_data)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f"Error: {e}")
