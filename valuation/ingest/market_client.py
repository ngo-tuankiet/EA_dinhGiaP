import pandas as pd
import logging
import importlib.util
import os

logger = logging.getLogger(__name__)

HAS_VNSTOCK_DATA = importlib.util.find_spec("vnstock_data") is not None

class MarketFlowClient:
    """
    Client sử dụng vnstock_data (Sponsor) để lấy dữ liệu dòng tiền khối ngoại và tự doanh.
    Nếu chưa cài đặt vnstock_data, trả về DataFrame rỗng có schema chuẩn.
    """
    def __init__(self):
        self.mkt = None

    def _market(self):
        if self.mkt is None:
            from valuation.config import settings
            os.environ["VNSTOCK_API_KEY"] = settings.vnstock_api_key
            from vnstock_data import Market
            self.mkt = Market()
        return self.mkt

    def fetch_foreign_flow(self, ticker: str, start: str, end: str = None) -> pd.DataFrame:
        """
        Lấy dữ liệu mua bán ròng khối ngoại.
        Trả về DataFrame với các cột: time, buy_vol, buy_val, sell_vol, sell_val, net_vol, net_val.
        """
        if not HAS_VNSTOCK_DATA:
            logger.info(f"Không cập nhật foreign_flow cho {ticker} từ {start}: thiếu vnstock_data optional.")
            # Trả về DF rỗng với cấu trúc chuẩn
            return pd.DataFrame(columns=['time', 'buy_vol', 'buy_val', 'sell_vol', 'sell_val', 'net_vol', 'net_val'])
            
        try:
            # Tham khảo schema từ docs
            df = self._market().equity(ticker).foreign_flow(start=start, end=end, interval='1D')
            if df is not None and not df.empty:
                df['time'] = pd.to_datetime(df['time']).dt.date
            return df
        except Exception as e:
            logger.error(f"Lỗi khi lấy foreign_flow cho {ticker}: {e}")
            raise

    def fetch_proprietary_flow(self, ticker: str, start: str, end: str = None) -> pd.DataFrame:
        """
        Lấy dữ liệu mua bán ròng tự doanh.
        Trả về DataFrame với các cột: time, buy_vol, buy_val, sell_vol, sell_val, net_vol, net_val.
        """
        if not HAS_VNSTOCK_DATA:
            logger.info(f"Không cập nhật proprietary_flow cho {ticker} từ {start}: thiếu vnstock_data optional.")
            return pd.DataFrame(columns=['time', 'buy_vol', 'buy_val', 'sell_vol', 'sell_val', 'net_vol', 'net_val'])
            
        try:
            df = self._market().equity(ticker).proprietary_flow(start=start, end=end, interval='1D')
            if df is not None and not df.empty:
                df['time'] = pd.to_datetime(df['time']).dt.date
            return df
        except Exception as e:
            logger.error(f"Lỗi khi lấy proprietary_flow cho {ticker}: {e}")
            raise

market_client = MarketFlowClient()
