from valuation.ingest.scraper_base import ScraperBase

class HoseFilingsScraper(ScraperBase):
    """Scraper cho website HOSE (chưa implement)"""
    def __init__(self):
        super().__init__(base_url="https://www.hsx.vn")
        
    def get_latest_filings(self):
        pass
