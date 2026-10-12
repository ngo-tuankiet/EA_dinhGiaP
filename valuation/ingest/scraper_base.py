import httpx
from typing import Dict, Any, Optional

class ScraperBase:
    """Base class cho các tác vụ lấy dữ liệu web/API ngoài vnstock"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(timeout=10.0)
        
    def fetch(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        url = f"{self.base_url}{endpoint}"
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response
    
    def close(self):
        self.client.close()
