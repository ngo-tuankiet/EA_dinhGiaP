import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from valuation.db.models import ConsensusSynthesis

def get_consensus_stats(ticker: str, trade_date: datetime.date, db: Session) -> Dict[str, Any]:
    """
    Thống kê khuyến nghị CTCK cho 1 mã trong 180 ngày tính đến `trade_date`.

    Giữ nguyên contract cũ {median, mean, count} cho code đang dùng, nhưng nay
    uỷ quyền cho `calibration.consensus_view` — NGUỒN ĐỌC DUY NHẤT (D23).

    Thay đổi hành vi CÓ CHỦ Ý (sửa bug): trước đây KHÔNG dedup theo CTCK, nên một
    CTCK ra 3 báo cáo trong cửa sổ được tính 3 phiếu vào median; trong khi bảng chi
    tiết ở `report_data.build_consensus_comparison` LẠI dedup. Hậu quả: KPI
    "Median CTCK" và bảng ngay dưới nó hiển thị hai con số khác nhau. Nay cả hai
    dùng chung một nguồn. `count` giờ là SỐ CTCK, không phải số báo cáo.
    """
    from valuation.calibration.consensus_view import get_consensus_view

    view = get_consensus_view(db, ticker, as_of=trade_date, window_days=180)
    return {"median": view.median, "mean": view.mean, "count": view.count}


def get_synthesis(ticker: str, db: Session) -> Optional[Dict[str, Any]]:
    """Lấy bản AI tổng hợp đa-CTCK (điểm chung/riêng/mấu chốt) cho 1 mã.

    Trả None nếu chưa có. Dùng cho báo cáo/app hiển thị nhận định tổng hợp.
    """
    row = db.query(ConsensusSynthesis).filter(
        ConsensusSynthesis.ticker == ticker.upper()).one_or_none()
    if row is None:
        return None
    return {
        "ticker": row.ticker,
        "n_reports": row.n_reports,
        "brokers": row.brokers,
        "diem_chung": row.diem_chung or [],
        "diem_rieng": row.diem_rieng or [],
        "diem_mau_chot": row.diem_mau_chot or [],
        "doi_chieu_noi_bo": row.doi_chieu_noi_bo or "",
        "internal_fv": float(row.internal_fv) if row.internal_fv is not None else None,
        "consensus_median": float(row.consensus_median) if row.consensus_median is not None else None,
        "generated_at": row.generated_at,
    }
