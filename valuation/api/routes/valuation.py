from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from valuation.output.gsheets_exporter import update_single_ticker_to_gsheets, _METHOD_LABEL
from sqlalchemy.orm import Session
from valuation.db.session import get_read_db, get_write_db
from valuation.db.models import FinancialsQuarterly, Ticker, ValuationOutput
import pandas as pd
from valuation.quality.scores import run_qc_checks

router = APIRouter(prefix="/valuation", tags=["valuation"])


@router.get("/report/{ticker}", summary="Báo cáo định giá dùng engine thống nhất (khớp Streamlit + batch)")
def unified_report(ticker: str, db_read: Session = Depends(get_read_db)):
    """Trả kết quả định giá từ ĐÚNG engine thống nhất (build_company_data → valuate),
    giống hệt Streamlit và batch VN100 — giá live, cùng phương pháp, cùng cờ.

    Đây là nguồn chuẩn cho báo cáo Discord mã đơn (thay cho /revalue cũ vốn dùng
    giá DB cũ + giả định hardcode → lệch số).
    """
    ticker = ticker.upper().strip()
    from valuation.data_access.repo import build_company_data, get_latest_price
    from valuation.engine.valuate import valuate
    from valuation.engine.sector_router import route

    if not db_read.query(Ticker).filter(Ticker.ticker == ticker).first():
        raise HTTPException(status_code=404, detail="Ticker not found")

    price = get_latest_price(db_read, ticker)
    try:
        company = build_company_data(db_read, ticker, mode="TTM")
        res = valuate(company)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {str(e)}")

    plan = route(ticker)
    method = plan["method"] if plan else "DCF"
    group = plan["group"] if plan else None

    fv = float(res["blended_fair_value_per_share"])
    upside = (fv / price - 1.0) if price else None
    decision = res.get("decision", {}) or {}

    return {
        "ticker": ticker,
        "current_price": price,
        "fair_value": fv,
        "intrinsic_fv": res.get("intrinsic_fv"),
        "relative_fv": res.get("relative_fv"),
        "weight_intrinsic": res.get("weight_intrinsic"),
        "upside": upside,
        "method": _METHOD_LABEL.get(method, method),
        "group": group,
        "recommendation": res.get("recommendation") or decision.get("recommendation"),
        "business_nature": decision.get("business_nature"),
        "target_mos": decision.get("target_mos"),
        "hard_gates_violations": decision.get("hard_gates_violations", []),
        "flags": res.get("flags", []),
        "publication_allowed": res.get("publication_allowed", True),
    }


@router.post("/revalue/{ticker}")
def revalue_ticker(ticker: str, background_tasks: BackgroundTasks, db_read: Session = Depends(get_read_db), db_write: Session = Depends(get_write_db)):
    """Định giá lại bằng engine THỐNG NHẤT (build_company_data → valuate), chạy QC,
    lưu ValuationOutput và đẩy Sheets chạy nền (chỉ khi được phép phát hành).

    Bản cũ dựng input riêng (hardcode cho FPT/HPG/SSI/DGC, số cp "placeholder" 1 tỷ,
    WACC theo VCSH sổ sách) → lệch số với UI/batch.
    """
    ticker = ticker.upper().strip()
    t = db_read.query(Ticker).filter(Ticker.ticker == ticker).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticker not found")

    from valuation.analysis.macro_radar import capture_macro_snapshot
    from valuation.data_access.repo import build_company_data
    from valuation.engine.sector_router import route
    from valuation.engine.valuate import valuate

    try:
        company = build_company_data(db_read, ticker, mode="TTM", fetch_live=False)
        res = valuate(company)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {str(e)}")

    fin_records = db_read.query(FinancialsQuarterly).filter(FinancialsQuarterly.ticker == ticker).all()
    df_fin = pd.DataFrame(
        [{"fiscal_year": r.fiscal_year, "fiscal_quarter": r.fiscal_quarter,
          "line_item": r.line_item, "value": r.value} for r in fin_records],
        columns=["fiscal_year", "fiscal_quarter", "line_item", "value"],
    )
    qc_result = run_qc_checks(
        ticker=ticker,
        sector_name=t.sector or "Unknown",
        financials=df_fin,
        market_cap=company.current_price * company.shares_outstanding * 1e6,
    )
    fv = float(res["blended_fair_value_per_share"])
    flags = list(dict.fromkeys(list(res.get("flags", [])) + list(qc_result.get("flags", []))))

    out_record = ValuationOutput(
        ticker=ticker,
        blended_fair_value_per_share=fv,
        flags=flags,
        macro_snapshot=capture_macro_snapshot(t.sector or "Unknown", db_read),
    )
    db_write.add(out_record)
    db_write.commit()

    if res.get("publication_allowed", True):
        background_tasks.add_task(
            update_single_ticker_to_gsheets,
            ticker=ticker,
            curr_price=company.current_price,
            blended_fv=fv,
            greeks={},
            qc_flags=flags,
            db=db_read,
        )

    plan = route(ticker) or {}
    return {
        "ticker": ticker,
        "current_price": company.current_price,
        "valuation": {
            "blended_fair_value_per_share": fv,
            "intrinsic_fv": res.get("intrinsic_fv"),
            "relative_fv": res.get("relative_fv"),
            "upside": res.get("upside"),
            "recommendation": res.get("recommendation"),
            "publication_allowed": res.get("publication_allowed", True),
            "flags": flags,
        },
        "qc": qc_result,
        "method": _METHOD_LABEL.get(plan.get("method"), plan.get("method")),
    }
