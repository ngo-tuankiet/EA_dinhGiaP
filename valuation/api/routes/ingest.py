import logging
import re

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, field_validator

from valuation.config import sotp_holding_tickers
from valuation.ingest.pipeline import run_ingest
from valuation.ingest.universe import get_vn100_symbols
from valuation.output.discord_alerter import notify_discord

router = APIRouter(prefix="/ingest", tags=["Ingestion"])
logger = logging.getLogger(__name__)


class IngestRequest(BaseModel):
    ticker: str
    data_types: list[str] = ["prices", "financials"]
    channel_id: int | None = (
        None  # Kênh Discord nơi user gõ lệnh (để báo cáo trả về đúng chỗ)
    )

    @field_validator("ticker")
    @classmethod
    def _ticker_whitelisted(cls, value: str) -> str:
        """AGENTS §5: mã từ ngoài phải đúng định dạng VÀ thuộc VN100 ∪ công ty con khai trong
        config/sotp_holdings.yaml trước khi chạm DB/API nguồn (chống injection, chống phình rổ).
        """
        ticker = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{3}", ticker):
            raise ValueError("Mã không hợp lệ (3 ký tự chữ/số)")
        if ticker not in set(get_vn100_symbols()) | sotp_holding_tickers():
            raise ValueError("Mã ngoài VN100 và danh sách công ty con SOTP")
        return ticker


def _run_ingest_job(ticker: str, data_types: list[str], channel_id=None):
    try:
        result = run_ingest(ticker, data_types)
        if result["status"] == "FAILED":
            raise RuntimeError(str(result["errors"]))
        partial_note = (
            f"\nCảnh báo cập nhật một phần: {result['errors']}"
            if result["status"] == "PARTIAL"
            else ""
        )
        notify_discord(
            embed_title=f"Ingest {result['status']}: {ticker}",
            embed_desc=(f"Đã cập nhật dữ liệu: {', '.join(data_types)}{partial_note}"),
            color="00FF00" if result["status"] == "SUCCESS" else "FFC107",
            channel_id=channel_id,
        )
    except Exception as e:
        logger.error(f"Ingest failed for {ticker}: {e}")
        notify_discord(
            embed_title=f"❌ Ingest thất bại: {ticker}",
            embed_desc=f"Lỗi: {e}",
            color="FF0000",
            channel_id=channel_id,
        )


@router.post("/")
async def trigger_ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    try:
        # Nếu muốn gọi đồng bộ thì bỏ background_tasks
        # nhưng ở đây nên chạy nền để không timeout nếu BCTC lớn
        background_tasks.add_task(
            _run_ingest_job, req.ticker, req.data_types, req.channel_id
        )
        return {
            "message": f"Ingestion triggered for {req.ticker}",
            "data_types": req.data_types,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
