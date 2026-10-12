import logging
from typing import Dict, Any, List
import datetime
import math
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.dialects.postgresql import insert

from valuation.db.models import Ticker, PricesDaily, ValuationSensitivity, ValuationOutput, DailySignal
from valuation.db.session import SessionLocalWrite
from valuation.analysis.macro_radar import get_macro_deltas
from valuation.engine.consensus_helper import get_consensus_stats

logger = logging.getLogger(__name__)

def calculate_batch_signals(tickers: List[str], trade_date: datetime.date = None, force_override: bool = False, db: Session = None):
    """
    Chạy Daily Signal cho một danh sách mã. Đảm bảo 1 mã lỗi không làm hỏng cả batch.
    """
    close_db = False
    if db is None:
        db = SessionLocalWrite()
        close_db = True
        
    results = {}
    try:
        for ticker in tickers:
            try:
                res = calculate_daily_signal(ticker, trade_date=trade_date, force_override=force_override, db=db)
                results[ticker] = res
            except Exception as e:
                logger.error(f"Error calculating signal for {ticker}: {e}")
                results[ticker] = {"error": str(e)}
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        if close_db:
            db.close()
            
    return results

def calculate_daily_signal(ticker: str, trade_date: datetime.date = None, force_override: bool = False, db: Session = None) -> Dict[str, Any]:
    close_db = False
    if db is None:
        db = SessionLocalWrite()
        close_db = True
        
    try:
        # 1. Fetch Ticker info
        ticker_obj = db.query(Ticker).filter(Ticker.ticker == ticker).first()
        if not ticker_obj:
            raise ValueError(f"Ticker {ticker} not found.")
            
        sector = ticker_obj.sector or "ALL"
        
        # 2. Fetch Latest Price
        if trade_date:
            price_obj = db.query(PricesDaily).filter(
                PricesDaily.ticker == ticker,
                PricesDaily.trade_date <= trade_date
            ).order_by(desc(PricesDaily.trade_date)).first()
        else:
            price_obj = db.query(PricesDaily).filter(
                PricesDaily.ticker == ticker
            ).order_by(desc(PricesDaily.trade_date)).first()
            
        if not price_obj:
            raise ValueError(f"No price data found for {ticker}")
            
        current_price = float(price_obj.close)
        trade_date_used = price_obj.trade_date
        volume = price_obj.volume or 0
        
        # 3. Fetch Base FV
        val_output = db.query(ValuationOutput).filter(
            ValuationOutput.ticker == ticker
        ).order_by(desc(ValuationOutput.created_at)).first()
        
        flags = []
        
        if not val_output:
            flags.append("NO_BASELINE")
            logger.warning(f"[{ticker}] NO_BASELINE: No intrinsic valuation found.")
            return _save_empty_signal(ticker, trade_date_used, current_price, flags, force_override, db)
            
        if val_output.flags and "POOR_QUALITY" in val_output.flags:
            flags.append("POOR_QUALITY")
        if val_output.flags and "FINANCIAL_QC_MISSING" in val_output.flags:
            flags.append("FINANCIAL_QC_MISSING")
            
        fv_base = float(val_output.blended_fair_value_per_share)
        required_mos = float(val_output.margin_of_safety) if val_output.margin_of_safety else (0.20 if sector in ("Ngân hàng", "Banks") else 0.30)
        
        # 4. Fetch Greeks
        greeks = db.query(ValuationSensitivity).filter(
            ValuationSensitivity.ticker == ticker,
            ValuationSensitivity.assumption_version == val_output.id
        ).all()
        
        if not greeks:
            flags.append("NO_BASELINE")
            logger.warning(f"[{ticker}] NO_BASELINE: No greeks found for version {val_output.id}.")
            return _save_empty_signal(ticker, trade_date_used, current_price, flags, force_override, db)
              
        # 5. Fetch Macro Deltas
        macro_deltas = get_macro_deltas(sector, macro_snapshot=val_output.macro_snapshot, db=db)
        
        # 6. Calculate Fast FV
        fv_fast = fv_base
        applied_deltas = []
        has_active_greek_error = False
        
        for g in greeks:
            driver = g.driver_code
            if driver in macro_deltas:
                delta_val = macro_deltas[driver]['delta']
                if g.dFV_ddriver is None:
                    if "SENSITIVITY_FAILED" not in flags:
                        flags.append("SENSITIVITY_FAILED")
                    # Nếu vĩ mô thay đổi (delta != 0) nhưng mất greek
                    if delta_val != 0.0:
                        has_active_greek_error = True
                        logger.error(f"[{ticker}] SENSITIVITY_FAILED: Greek for driver {driver} is None while macro delta is active ({delta_val}). Forcing STALE.")
                    continue
                    
                dfv = float(g.dFV_ddriver)
                impact = delta_val * dfv
                fv_fast += impact
                
                applied_deltas.append({
                    "driver": driver,
                    "delta": delta_val,
                    "dfv_ddriver": dfv,
                    "impact": impact
                })
                
        # 7. STALE_FV Logic
        # Tính toán upside_fast để validator kiểm tra biên
        if current_price > 0 and not math.isnan(current_price):
            upside_fast = (fv_fast - current_price) / current_price
        else:
            upside_fast = None
            
        stale_threshold = 0.05 if sector in ("Ngân hàng", "Banks") else 0.10
        deviation = abs(fv_fast - fv_base) / fv_base
        
        # STALE khi deviation vượt ngưỡng OR fv_fast <= 0 OR giá <= 0/NaN OR upside_fast ngoài [-90%, +300%] OR có active greek error
        is_stale = (
            deviation > stale_threshold or
            fv_fast <= 0 or
            current_price <= 0 or
            math.isnan(current_price) or
            (upside_fast is not None and (upside_fast > 3.0 or upside_fast < -0.90)) or
            has_active_greek_error
        )
        
        if is_stale:
            flags.append("STALE_FV")
            flags.append("PROVISIONAL")
            if fv_fast <= 0:
                flags.append("NEGATIVE_FV_FAST")
            if current_price <= 0 or math.isnan(current_price):
                flags.append("INVALID_PRICE")
                
            logger.warning(f"STALE_FV_ENQUEUE_RECOMPUTE: Ticker {ticker} has fv_fast={fv_fast:,.0f} deviating from fv_base={fv_base:,.0f} or invalid state. Needs revaluation.")
            effective_fv = fv_base
        else:
            effective_fv = fv_fast
            
        if current_price > 0 and not math.isnan(current_price):
            upside = (effective_fv - current_price) / current_price
        else:
            upside = None
            
        if upside is not None and upside > 3.0:
            flags.append("ABSURD_UPSIDE")
            
        # 7.5. Consensus Check
        consensus_stats = get_consensus_stats(ticker, trade_date_used, db)
        consensus_median = consensus_stats["median"]
        if consensus_median is not None:
            deviation_pct = (effective_fv - consensus_median) / consensus_median
            if abs(deviation_pct) > 0.25:
                flags.append("CONSENSUS_DEVIATION_HIGH")
            
        # 8. Calculate Attractiveness (0-100)
        if upside is None:
            attractiveness = 0.0
        else:
            excess_upside = upside - required_mos
            excess_upside_max = 0.15 if sector in ("Ngân hàng", "Banks") else 0.25
            
            if excess_upside <= 0:
                attractiveness = 0.0
            elif excess_upside >= excess_upside_max:
                attractiveness = 100.0
            else:
                attractiveness = (excess_upside / excess_upside_max) * 100.0
            
        # 9. Calculate Confidence (0.5 - 1.0)
        confidence = 1.0
        
        if "SECTOR_UNVALIDATED" in flags:
            confidence -= 0.30
            
        if is_stale:
            confidence -= 0.20
            
        if "POOR_QUALITY" in flags:
            confidence -= 0.15
            
        if "FINANCIAL_QC_MISSING" in flags:
            confidence -= 0.15
            
        # Wide Bull-Bear Spread or Incomplete Data
        if val_output.fair_value_bull and val_output.fair_value_bear:
            wide_spread_threshold = 0.60
            spread = (float(val_output.fair_value_bull) - float(val_output.fair_value_bear)) / fv_base
            if spread > wide_spread_threshold:
                flags.append("WIDE_SPREAD")
                confidence -= 0.10
        else:
            flags.append("DATA_INCOMPLETE")
            confidence -= 0.05
                
        # Sensitivity Failed
        if "SENSITIVITY_FAILED" in flags:
            confidence -= 0.10
            
        # Low Liquidity
        if volume < 500_000:
            flags.append("LOW_LIQUIDITY")
            confidence -= 0.10
            
        # Consensus Deviation High
        if "CONSENSUS_DEVIATION_HIGH" in flags:
            confidence -= 0.10
            
        # 9.5 Dòng tiền khối ngoại và tự doanh (Market Flows)
        # Query 5 phiên gần nhất
        recent_prices = db.query(PricesDaily).filter(
            PricesDaily.ticker == ticker,
            PricesDaily.trade_date <= trade_date_used
        ).order_by(desc(PricesDaily.trade_date)).limit(5).all()
        
        foreign_net_5d = sum([float(p.foreign_net_val) for p in recent_prices if p.foreign_net_val is not None])
        prop_net_5d = sum([float(p.proprietary_net_val) for p in recent_prices if p.proprietary_net_val is not None])
        
        # Nếu tổng mua ròng ngoại > 50 tỷ trong 5 ngày
        if foreign_net_5d > 50_000_000_000:
            flags.append("FOREIGN_STRONG_INFLOW")
            confidence += 0.10
        elif foreign_net_5d < -50_000_000_000:
            flags.append("FOREIGN_STRONG_OUTFLOW")
            confidence -= 0.10
            
        # Nếu tự doanh mua ròng > 20 tỷ trong 5 ngày
        if prop_net_5d > 20_000_000_000:
            flags.append("PROP_STRONG_INFLOW")
            confidence += 0.05
        elif prop_net_5d < -20_000_000_000:
            flags.append("PROP_STRONG_OUTFLOW")
            confidence -= 0.05
            
        # Add floor/ceiling to confidence
        confidence = max(0.5, min(1.2, confidence)) # Cho phép max 1.2 nếu dòng tiền cực mạnh
        
        
        # 10. Conviction Score
        conviction_score = attractiveness * confidence
        
        result = {
            "ticker": ticker,
            "trade_date": trade_date_used.isoformat(),
            "close_price": current_price,
            "fv_base": fv_base,
            "fv_fast": fv_fast,
            "effective_fv": effective_fv,
            "upside": upside,
            "margin_of_safety": required_mos,
            "attractiveness": attractiveness,
            "confidence": confidence,
            "conviction_score": conviction_score,
            "flags": flags,
            "applied_deltas": applied_deltas
        }
        
        # 11. UPSERT Logic
        today = datetime.date.today()
        if trade_date_used < today and not force_override:
            # Replaying history without override -> Skip Upsert
            result["upserted"] = False
            result["skip_reason"] = "Historical date without force_override"
            return result
            
        now_time = datetime.datetime.now(datetime.timezone.utc)
        stmt = insert(DailySignal).values(
            ticker=ticker,
            trade_date=trade_date_used,
            close_price=current_price,
            fair_value_fast=fv_fast, # Store raw fv_fast in DB as recorded, even if PROVISIONAL
            upside=upside,
            margin_of_safety=required_mos,
            conviction_score=conviction_score,
            flags=flags,
            computed_at=now_time
        )
        
        update_dict = {
            "close_price": current_price,
            "fair_value_fast": fv_fast,
            "upside": upside,
            "margin_of_safety": required_mos,
            "conviction_score": conviction_score,
            "flags": flags,
            "computed_at": now_time
        }
        
        stmt = stmt.on_conflict_do_update(
            index_elements=['ticker', 'trade_date'],
            set_=update_dict
        )
        
        db.execute(stmt)
        if not close_db:
            db.flush()
        else:
            db.commit()
            
        result["upserted"] = True
        return result
        
    except Exception as e:
        if db:
            db.rollback()
        raise e
    finally:
        if close_db:
            db.close()

def _save_empty_signal(ticker: str, trade_date: datetime.date, current_price: float, flags: List[str], force_override: bool, db: Session) -> Dict[str, Any]:
    result = {"ticker": ticker, "trade_date": trade_date.isoformat(), "flags": flags, "conviction_score": None}
    today = datetime.date.today()
    
    if trade_date < today and not force_override:
        result["upserted"] = False
        return result
        
    now_time = datetime.datetime.now(datetime.timezone.utc)
    stmt = insert(DailySignal).values(
        ticker=ticker,
        trade_date=trade_date,
        close_price=current_price,
        fair_value_fast=None,
        upside=None,
        margin_of_safety=None,
        conviction_score=None,
        flags=flags,
        computed_at=now_time
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=['ticker', 'trade_date'],
        set_={
            "close_price": current_price,
            "flags": flags,
            "fair_value_fast": None,
            "upside": None,
            "margin_of_safety": None,
            "conviction_score": None,
            "computed_at": now_time
        }
    )
    db.execute(stmt)
    db.flush()
    result["upserted"] = True
    return result
