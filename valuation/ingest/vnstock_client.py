import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from valuation.config import settings

logger = logging.getLogger(__name__)


def _configure_vnstock_api_key(api_key: str) -> None:
    """Đưa key vào tiến trình; không tạo thêm file chứa secret trong HOME."""
    os.environ["VNSTOCK_API_KEY"] = api_key


def _call_with_rate_limit_retry(
    func, *args, max_retries: int = 2, backoff_sec: float = 65.0, **kwargs
):
    """Gọi 1 API vnstock, tự retry khi bị chặn Rate Limit.

    `vnai` (dependency quota-enforcement của vnstock) raise `SystemExit` khi
    vượt giới hạn free-tier (60 req/phút) thay vì `Exception` thông thường.
    SystemExit xuyên qua mọi `except Exception` ở tầng gọi (weekly_updater,
    scripts batch) và giết chết cả tiến trình/luồng đang chạy giữa chừng —
    đây là nguyên nhân các đợt quét VN100 hàng tuần bị bỏ dở. Bắt riêng
    SystemExit ở đây, chờ rồi thử lại; hết lượt vẫn lỗi thì quy về
    RuntimeError (Exception thường) để tầng gọi xử lý per-ticker như bình
    thường thay vì sập toàn bộ batch.
    """
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except SystemExit as e:
            if attempt < max_retries:
                logger.warning(
                    f"vnstock rate limit — chờ {backoff_sec:.0f}s rồi thử lại "
                    f"(lần {attempt + 1}/{max_retries})..."
                )
                time.sleep(backoff_sec)
            else:
                raise RuntimeError(
                    f"vnstock rate limit vượt quá số lần thử lại: {e}"
                ) from e


class VnstockClient:
    """Wrapper cho vnstock 4.0.6+ để lấy dữ liệu từ VCI."""

    def __init__(self):
        self.source = "VCI"
        self._api_key_ready = False
        self._api_key_lock = threading.Lock()

    def _ensure_api_key(self) -> None:
        """Áp dụng key trong `.env` đúng một lần trước request đầu tiên."""
        if self._api_key_ready:
            return
        with self._api_key_lock:
            if self._api_key_ready:
                return
            if settings.vnstock_api_key:
                _configure_vnstock_api_key(settings.vnstock_api_key)
            self._api_key_ready = True

    def get_company_overview(self, symbol: str) -> pd.DataFrame:
        """Lấy thông tin tổng quan công ty"""
        self._ensure_api_key()
        from vnstock.api.company import Company

        # Bọc cả khởi tạo (Company(...)) lẫn gọi method trong retry: vnai có
        # thể raise SystemExit ngay lúc khởi tạo, không chỉ lúc gọi .overview().
        return _call_with_rate_limit_retry(
            lambda: Company(source=self.source, symbol=symbol).overview()
        )

    def get_financials(
        self, symbol: str, statement_type: str = "BS", period: str = "quarter"
    ) -> pd.DataFrame:
        """
        Lấy báo cáo tài chính
        statement_type: 'BS' (Balance Sheet), 'IS' (Income Statement), 'CF' (Cash Flow)
        period: 'quarter' hoặc 'year'
        """
        self._ensure_api_key()

        def _fetch():
            from vnstock.api.financial import Finance

            finance = Finance(
                source=self.source, symbol=symbol, period=period, get_all=True
            )
            if statement_type == "BS":
                return finance.balance_sheet()
            elif statement_type == "IS":
                return finance.income_statement()
            elif statement_type == "CF":
                return finance.cash_flow()
            else:
                raise ValueError(f"Unknown statement_type: {statement_type}")

        return _call_with_rate_limit_retry(_fetch)

    def get_historical_prices(self, symbol: str, start_date: str) -> pd.DataFrame:
        """Lấy giá lịch sử từ ngày start_date (YYYY-MM-DD)"""
        self._ensure_api_key()
        from vnstock.api.quote import Quote

        return _call_with_rate_limit_retry(
            lambda: Quote(source=self.source, symbol=symbol).history(start=start_date)
        )

    def get_live_price(self, symbol: str) -> float:
        """Lấy giá thị trường hiện tại (real-time/intraday)"""
        try:
            self._ensure_api_key()

            from vnstock.api.quote import Quote

            # Lấy 7 ngày gần nhất để đảm bảo có dữ liệu
            start_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
                "%Y-%m-%d"
            )
            quote = Quote(source=self.source, symbol=symbol)
            # Không retry-với-sleep ở đây: hàm này chạy trên luồng UI chính mỗi
            # lần rerun, chờ 65s sẽ đứng hình app. Rate limit → fail-fast về 0.0,
            # streamlit_app.py đã có fallback đọc giá gần nhất từ DB.
            df = quote.history(start=start_date)
            if not df.empty and "close" in df.columns:
                close_val = df.iloc[-1]["close"]
                return float(close_val) * 1000.0
        except (Exception, SystemExit):
            pass
        return 0.0

    def get_vn100_symbols(self) -> pd.Series:
        """Lấy danh sách mã VN100"""
        self._ensure_api_key()
        from vnstock.api.listing import Listing

        return _call_with_rate_limit_retry(
            lambda: Listing(source=self.source).symbols_by_group("VN100")
        )


vnstock_client = VnstockClient()
