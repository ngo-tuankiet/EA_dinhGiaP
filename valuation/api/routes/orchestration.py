from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import distinct
import logging
import datetime

from valuation.db.session import get_write_db, SessionLocalRead
from valuation.db.models import FinancialsQuarterly
from valuation.engine.daily_signal import calculate_batch_signals
from valuation.engine.batch import value_all
from valuation.output.gsheets_exporter import build_vn100_dataframe, export_vn100_valuations_to_gsheets, _METHOD_LABEL
from valuation.output.discord_alerter import send_daily_alerts, notify_discord
from valuation.output.ai_insight import call_deepseek_sync
from valuation.config import PROJECT_ROOT

router = APIRouter()
logger = logging.getLogger(__name__)

_batch_state = {"running": False}

class RunDailyRequest(BaseModel):
    tickers: List[str]
    trade_date: str = None # Format YYYY-MM-DD
    force_override: bool = False

@router.post("/run-daily", summary="Chạy Daily Signal toàn bộ thị trường & Cập nhật Output")
def run_daily_pipeline(request: RunDailyRequest, db: Session = Depends(get_write_db)):
    """
    Endpoint duy nhất dành cho n8n để kích hoạt toàn bộ luồng xử lý cuối ngày:
    1. Tính toán Daily Signal cho rổ mã cung cấp.
    2. Đẩy kết quả vào Google Sheets (Two-Way Model).
    3. Phân tích kết quả và bắn cảnh báo Discord nếu cần.
    """
    try:
        trade_date = None
        if request.trade_date:
            trade_date = datetime.date.fromisoformat(request.trade_date)
            
        logger.info(f"Starting daily pipeline for {len(request.tickers)} tickers on {trade_date or 'LATEST'}")
        
        # Step 1: Calculate signals
        signals_res = calculate_batch_signals(
            tickers=request.tickers, 
            trade_date=trade_date,
            force_override=request.force_override,
            db=db
        )
        
        # Determine the effective trade_date for export
        effective_dates = []
        if isinstance(signals_res, dict):
            signals_values = signals_res.values()
        elif isinstance(signals_res, list):
            signals_values = signals_res
        else:
            signals_values = []
            
        for s in signals_values:
            if isinstance(s, dict) and 'trade_date' in s:
                effective_dates.append(datetime.date.fromisoformat(s['trade_date']))
                
        export_date = max(effective_dates) if effective_dates else (trade_date or datetime.date.today())
        
        # Step 2: Export to Google Sheets
        sheets_res = export_daily_signals_to_gsheets(trade_date=export_date, db=db)
        
        # Step 3: Discord Alerts
        discord_res = send_daily_alerts(trade_date=export_date, db=db)
        
        return {
            "status": "success",
            "pipeline_summary": {
                "signals_processed": len(signals_res),
                "google_sheets_sync": sheets_res,
                "discord_alerts": discord_res
            }
        }
        
    except Exception as e:
        logger.error(f"Daily pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _format_ranking_lines(rows: list) -> str:
    lines = []
    for r in rows:
        method_label = _METHOD_LABEL.get(r["method"], r["method"])
        lines.append(
            f"**{r['ticker']}** ({method_label}) — Giá {r['price']:,.0f} → FV {r['fair_value']:,.0f} "
            f"(Upside {r['upside']*100:+.1f}%)"
        )
    return "\n".join(lines) if lines else "Không có dữ liệu."


def _build_market_summary_prompt(valid: list, top10: list, bottom10: list) -> str:
    avg_upside = sum(r["upside"] for r in valid) / len(valid) * 100
    n_positive = sum(1 for r in valid if r["upside"] > 0)
    top_groups = ", ".join(sorted({r["group"] for r in top10 if r.get("group")})) or "N/A"
    bottom_groups = ", ".join(sorted({r["group"] for r in bottom10 if r.get("group")})) or "N/A"
    return (
        "Bạn là chuyên gia phân tích chiến lược thị trường chứng khoán Việt Nam. "
        "Dựa trên số liệu tổng hợp dưới đây, viết ĐÚNG 1 câu tiếng Việt (không quá 40 từ) "
        "nhận định tổng kết ngắn gọn về định giá thị trường VN100 hiện tại, súc tích dễ hiểu, "
        "không lặp lại số liệu thô, không thêm giải thích ngoài câu nhận định.\n\n"
        f"- Số mã đã định giá: {len(valid)}\n"
        f"- Upside trung bình toàn rổ: {avg_upside:+.1f}%\n"
        f"- Số mã có upside dương: {n_positive}/{len(valid)}\n"
        f"- Ngành nổi bật trong nhóm định giá tốt nhất: {top_groups}\n"
        f"- Ngành nổi bật trong nhóm cần tránh: {bottom_groups}\n"
    )


def _run_vn100_batch_job(channel_id=None):
    """Định giá batch toàn VN100 chạy nền, thông báo top 10 tốt/xấu + nhận định qua Discord khi xong."""
    db = SessionLocalRead()
    try:
        tickers = sorted(r[0] for r in db.query(distinct(FinancialsQuarterly.ticker)).all() if r[0] != "VNINDEX")
        results = value_all(db, tickers)
        df = build_vn100_dataframe(results)

        out_csv = PROJECT_ROOT / "vn100_valuations.csv"
        df.to_csv(out_csv, index=False)
        ok = sum(1 for r in results if "error" not in r)

        sheets_res = export_vn100_valuations_to_gsheets(results)

        valid = [r for r in results if "error" not in r and r.get("upside") is not None]
        valid_sorted = sorted(valid, key=lambda r: r["upside"], reverse=True)
        top10 = valid_sorted[:10]
        bottom10 = valid_sorted[-10:][::-1] if len(valid_sorted) > 10 else []

        if valid:
            summary_prompt = _build_market_summary_prompt(valid, top10, bottom10)
            market_summary = call_deepseek_sync(summary_prompt, max_tokens=1000, temperature=0.4)
        else:
            market_summary = "Không đủ dữ liệu hợp lệ để đưa ra nhận định thị trường."

        notify_discord(
            embed_title="📊 Báo cáo định giá VN100",
            embed_desc=f"**Nhận định thị trường:** {market_summary}",
            color="5865F2",
            fields=[
                {"name": "🟢 TOP 10 ĐỊNH GIÁ TỐT (Upside cao)", "value": _format_ranking_lines(top10), "inline": False},
                {"name": "🔴 TOP 10 CẦN TRÁNH (Upside thấp/Overvalued)", "value": _format_ranking_lines(bottom10), "inline": False},
            ],
            footer=f"Đã định giá {ok}/{len(tickers)} mã | Google Sheets: {sheets_res.get('status')} | CSV: {out_csv.name}",
            channel_id=channel_id,
        )
    except Exception as e:
        logger.error(f"VN100 batch job failed: {e}")
        notify_discord(
            embed_title="❌ Batch định giá VN100 thất bại",
            embed_desc=f"Lỗi: {e}",
            color="FF0000",
            channel_id=channel_id,
        )
    finally:
        db.close()
        _batch_state["running"] = False


class RunBatchRequest(BaseModel):
    channel_id: int | None = None


@router.post("/run-batch-vn100", summary="Chạy định giá batch toàn VN100 (chạy nền)")
def run_batch_vn100(background_tasks: BackgroundTasks, request: RunBatchRequest = RunBatchRequest()):
    """
    Kích hoạt định giá batch cho toàn bộ rổ VN100 đã có dữ liệu trong DB.
    Chạy nền để tránh timeout; kết quả được thông báo về đúng kênh Discord (channel_id)
    hoặc webhook cố định nếu không truyền channel_id.
    """
    if _batch_state["running"]:
        raise HTTPException(status_code=409, detail="Batch VN100 đang chạy, vui lòng đợi hoàn tất.")
    _batch_state["running"] = True
    background_tasks.add_task(_run_vn100_batch_job, request.channel_id)
    return {"status": "started", "message": "Batch VN100 đã bắt đầu chạy nền."}
