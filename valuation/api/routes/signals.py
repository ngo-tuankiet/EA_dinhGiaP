from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel
from valuation.db.session import get_write_db
from sqlalchemy.orm import Session
from valuation.engine.daily_signal import calculate_batch_signals, calculate_daily_signal
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class SignalRequest(BaseModel):
    tickers: List[str]

@router.post("/generate", summary="Tạo Daily Signal theo lô (Batch)")
def generate_batch_signals(request: SignalRequest, db: Session = Depends(get_write_db)):
    """
    Chạy định giá Daily Signal cho một danh sách các mã (ví dụ toàn bộ rổ VN100).
    """
    try:
        results = calculate_batch_signals(request.tickers, db=db)
        return {"status": "success", "data": results}
    except Exception as e:
        logger.error(f"Error calculating batch signals: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/generate/{ticker}", summary="Tạo Daily Signal cho 1 mã")
def generate_single_signal(ticker: str, db: Session = Depends(get_write_db)):
    try:
        res = calculate_daily_signal(ticker, db=db)
        db.commit()
        return {"status": "success", "data": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error calculating signal for {ticker}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
