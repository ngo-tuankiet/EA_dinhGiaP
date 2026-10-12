from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc
from valuation.db.models import MacroRadar, MacroSeries
from valuation.db.session import SessionLocalRead

def capture_macro_snapshot(sector: str, db: Session) -> dict:
    """
    Chụp snapshot các chỉ số vĩ mô mới nhất cho sector cụ thể tại thời điểm định giá chậm.
    """
    configs = db.query(MacroRadar).filter(MacroRadar.sector.in_([sector, "ALL"])).all()
    snapshot = {}
    for cfg in configs:
        if not cfg.mapped_driver:
            continue
        # Lấy giá trị mới nhất
        latest_val = db.query(MacroSeries).filter(
            MacroSeries.indicator_code == cfg.indicator_code
        ).order_by(desc(MacroSeries.date)).first()
        
        if latest_val and latest_val.value is not None:
            snapshot[cfg.indicator_code] = float(latest_val.value)
    return snapshot

def get_macro_deltas(sector: str, macro_snapshot: dict = None, db: Session = None) -> Dict[str, float]:
    """
    Tính toán mức thay đổi (delta) của các macro indicators được map sang drivers.
    Nếu macro_snapshot được truyền vào, delta = latest - snapshot.
    Nếu không, delta = latest - previous (cũ).
    """
    close_db = False
    if db is None:
        db = SessionLocalRead()
        close_db = True
        
    try:
        # Lấy cấu hình radar cho ngành cụ thể và ngành ALL
        configs = db.query(MacroRadar).filter(MacroRadar.sector.in_([sector, "ALL"])).all()
        
        deltas = {}
        for cfg in configs:
            if not cfg.mapped_driver:
                continue
                
            # Lấy giá trị mới nhất hôm nay
            latest_row = db.query(MacroSeries).filter(
                MacroSeries.indicator_code == cfg.indicator_code
            ).order_by(desc(MacroSeries.date)).first()
            
            if not latest_row or latest_row.value is None:
                continue
                
            latest = float(latest_row.value)

            # Elasticity: driver_delta = elasticity * macro_delta. Mặc định 1.0 (map 1:1).
            elasticity = float(cfg.elasticity) if cfg.elasticity is not None else 1.0

            if macro_snapshot is not None:
                # Tính delta so với snapshot vĩ mô
                previous = macro_snapshot.get(cfg.indicator_code)
                if previous is not None:
                    previous = float(previous)
                    macro_delta = latest - previous
                else:
                    # Nếu chưa có snapshot cho indicator này, delta coi như bằng 0
                    previous = latest
                    macro_delta = 0.0
            else:
                # Fallback: Lấy 2 giá trị gần nhất như cũ
                series = db.query(MacroSeries).filter(
                    MacroSeries.indicator_code == cfg.indicator_code
                ).order_by(desc(MacroSeries.date)).limit(2).all()
                if len(series) >= 2:
                    previous = float(series[1].value)
                    macro_delta = latest - previous
                else:
                    previous = latest
                    macro_delta = 0.0

            # Quy đổi biến động vĩ mô sang biến động driver qua elasticity.
            delta_val = macro_delta * elasticity
                    
            # Check warn limits
            status = "NEUTRAL"
            if cfg.warn_low is not None and latest <= float(cfg.warn_low):
                status = "WARNING_LOW"
            elif cfg.warn_high is not None and latest >= float(cfg.warn_high):
                status = "WARNING_HIGH"
                
            # Mapping to driver
            deltas[cfg.mapped_driver] = {
                "delta": delta_val,
                "latest_value": latest,
                "previous_value": previous,
                "status": status,
                "indicator": cfg.indicator_code
            }
            
        return deltas
    finally:
        if close_db:
            db.close()
