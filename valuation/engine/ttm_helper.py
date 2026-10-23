"""
TTM Helper — Utility tổng hợp Trailing Twelve Months từ dữ liệu quý trong DB.

Mục đích:
- Lấy giá trị Balance Sheet (quý cuối cùng)
- Tổng hợp Income Statement / Cash Flow theo TTM (sum 4 quý gần nhất)
- Tính shares outstanding từ Vốn điều lệ / mệnh giá
- Tính các driver lịch sử (NIM, CIR, credit growth) từ dữ liệu thật
"""
from datetime import date, timedelta
from pathlib import Path
from typing import Any, List, Optional, Tuple

import yaml
from sqlalchemy.orm import Session
from sqlalchemy import desc
from valuation.db.models import FinancialsQuarterly, MacroSeries, PricesDaily


_SHARES_EVENTS_FILE = (
    Path(__file__).resolve().parents[2] / "config" / "corporate_actions.yaml"
)


def _load_shares_events() -> List[dict[str, Any]]:
    if not _SHARES_EVENTS_FILE.exists():
        return []
    with _SHARES_EVENTS_FILE.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return list(data.get("shares_outstanding_events") or [])


def resolve_shares_override(
    ticker: str, as_of_date: date, events: List[dict[str, Any]]
) -> Optional[float]:
    """Lấy số cổ phiếu từ corporate action gần nhất đã có hiệu lực."""
    eligible: List[tuple[date, float]] = []
    for event in events:
        if str(event.get("ticker", "")).upper() != ticker.upper():
            continue
        effective_date = date.fromisoformat(str(event["effective_date"]))
        if effective_date <= as_of_date:
            eligible.append((effective_date, float(event["shares_outstanding"])))
    if not eligible:
        return None
    return max(eligible, key=lambda item: item[0])[1]



_DIRECT_SHARE_KEYS = ["outstanding_shares_volume", "shares_outstanding_value"]
_CAPITAL_KEYS = ["charter_capital", "Vốn điều lệ", "Vốn góp của chủ sở hữu", "paid_in_capital", "common_shares"]
_SPLIT_EVENT_TYPES = ("STOCK_DIVIDEND", "BONUS_SHARE")
# Cờ thiếu ngày GDKHQ theo loại: cổ tức CP/thưởng → CORPORATE_ACTION_UNDATED (số cp có thể sai, lỗi dữ
# liệu); quyền mua → RIGHTS_ISSUE_UNDATED (thông tin): quyền mua không bao giờ vào hệ số chia (đi kèm tiền,
# chờ BCTC phản ánh cả cp lẫn tiền — Dữ liệu F9) nên thiếu ngày không làm sai số cp đang dùng.
_UNDATED_FLAG_BY_TYPE = {
    "STOCK_DIVIDEND": "CORPORATE_ACTION_UNDATED",
    "BONUS_SHARE": "CORPORATE_ACTION_UNDATED",
    "RIGHTS_ISSUE": "RIGHTS_ISSUE_UNDATED",
}


def undated_split_flags(db: Session, ticker: str, as_of_date: Optional[date] = None,
                        lookback_days: int = 180) -> List[str]:
    """Cờ sự kiện công bố gần đây nhưng thiếu ngày GDKHQ và chưa có số cp ghi đè sau ngày công bố:
    CORPORATE_ACTION_UNDATED (cổ tức CP/thưởng — engine có thể đang dùng số cp cũ, D48) và
    RIGHTS_ISSUE_UNDATED (quyền mua — chỉ nhắc theo dõi)."""
    from datetime import timedelta

    from valuation.db.models import CorporateAction

    as_of_date = as_of_date or date.today()
    rows = db.query(CorporateAction.event_type, CorporateAction.announcement_date).filter(
        CorporateAction.ticker == ticker,
        CorporateAction.event_type.in_(tuple(_UNDATED_FLAG_BY_TYPE)),
        CorporateAction.ex_right_date.is_(None),
        CorporateAction.announcement_date.isnot(None),
        CorporateAction.announcement_date > as_of_date - timedelta(days=lookback_days),
        CorporateAction.announcement_date <= as_of_date,
    ).all()
    overrides = [date.fromisoformat(str(e["effective_date"])) for e in _load_shares_events()
                 if str(e.get("ticker", "")).upper() == ticker.upper()]
    return sorted({_UNDATED_FLAG_BY_TYPE[etype] for etype, ann in rows
                   if not any(o >= ann for o in overrides)})


def _quarter_end(year: int, quarter: int) -> date:
    return date(year, 3 * quarter, 30 if quarter in (2, 3) else 31)


def _unreflected_split_factor(
    db: Session, ticker: str, keys: List[str], as_of_date: date
) -> float:
    """Hệ số nhân số cp cho cổ tức CP/thưởng đã qua GDKHQ mà BCTC gần nhất chưa ghi nhận.

    Chỉ loại không kèm tiền: giá đã chia (1+tỷ lệ) từ GDKHQ. Quyền mua/ESOP/riêng lẻ
    mang theo tiền mới nên chờ BCTC phản ánh đồng thời cả cp lẫn tiền. Vốn điều lệ
    thường chỉ tăng khi hoàn tất phát hành, có thể trễ qua một kỳ BCTC.
    """
    from valuation.config import load_defaults

    tol = float((load_defaults().get("corporate_actions") or {}).get("split_reflected_tolerance", 0.02))
    basis = [
        (_quarter_end(y, q), _query_value(db, ticker, keys, y, q))
        for y, q in _find_latest_4_quarters(db, ticker)
    ]  # mới → cũ
    if not basis or basis[0][1] <= 0:
        return 1.0
    now = basis[0][1]
    factor = 1.0
    for ex, ratio in sorted(_split_ratios_by_ex_date(db, ticker, None, as_of_date).items()):
        before = [v for end, v in basis if end < ex and v > 0]
        if not before:
            continue  # cũ hơn cửa sổ 4 quý → BCTC hiện tại đã phản ánh
        if now >= before[0] * (1 + ratio) * (1 - tol):
            continue
        factor *= 1 + ratio
    return factor


def _split_ratios_by_ex_date(
    db: Session, ticker: str, after: date | None, until: date
) -> dict[date, float]:
    """Σ tỷ lệ cổ tức CP/thưởng theo ngày GDKHQ trong (after, until]. Các đợt CÙNG ngày tính trên cùng
    số cp gốc nên cộng tỷ lệ (HDB 09/10/2026: 25% + 5% = 30%, không phải 1,25 × 1,05 = 31,25%); dòng
    trùng nhiều nguồn (cùng loại, ngày, tỷ lệ) chỉ tính một lần."""
    from valuation.db.models import CorporateAction

    query = db.query(
        CorporateAction.ex_right_date, CorporateAction.event_type, CorporateAction.exercise_ratio
    ).filter(
        CorporateAction.ticker == ticker,
        CorporateAction.event_type.in_(_SPLIT_EVENT_TYPES),
        CorporateAction.ex_right_date.isnot(None),
        CorporateAction.ex_right_date <= until,
        CorporateAction.exercise_ratio > 0,
    )
    if after is not None:
        query = query.filter(CorporateAction.ex_right_date > after)
    ratios: dict[date, float] = {}
    for ex, _etype, ratio in {(ex, et, float(r)) for ex, et, r in query}:
        ratios[ex] = ratios.get(ex, 0.0) + ratio
    return ratios


def _find_latest_4_quarters(db: Session, ticker: str) -> List[Tuple[int, int]]:
    """Tìm 4 quý gần nhất có dữ liệu cho ticker."""
    rows = (
        db.query(
            FinancialsQuarterly.fiscal_year,
            FinancialsQuarterly.fiscal_quarter,
        )
        .filter(
            FinancialsQuarterly.ticker == ticker,
            FinancialsQuarterly.fiscal_quarter > 0,  # Bỏ annual (Q=0)
        )
        .distinct()
        .order_by(
            desc(FinancialsQuarterly.fiscal_year),
            desc(FinancialsQuarterly.fiscal_quarter),
        )
        .limit(4)
        .all()
    )
    return [(r[0], r[1]) for r in rows]


def _query_value(
    db: Session,
    ticker: str,
    keywords: List[str],
    year: int,
    quarter: int,
) -> float:
    """
    Tìm giá trị cho một line_item bằng keyword matching.

    Chiến lược matching (theo thứ tự ưu tiên):
    1. Line item BẮT ĐẦU bằng keyword (startswith) → match chính xác nhất
    2. Line item CHỨA keyword (contains) → fallback

    Ví dụ: keyword='IX. Chi phí hoạt động' sẽ match đúng dòng tổng
    chứ không bị shadowed bởi '4. Chi phí hoạt động dịch vụ'.
    """
    rows = (
        db.query(FinancialsQuarterly)
        .filter(
            FinancialsQuarterly.ticker == ticker,
            FinancialsQuarterly.fiscal_year == year,
            FinancialsQuarterly.fiscal_quarter == quarter,
        )
        .all()
    )
    # Pass 1: ưu tiên startswith
    for kw in keywords:
        kw_lower = kw.lower()
        for r in rows:
            if r.line_item.lower().startswith(kw_lower):
                return float(r.value) if r.value is not None else 0.0

    # Pass 2: fallback contains
    for kw in keywords:
        kw_lower = kw.lower()
        for r in rows:
            if kw_lower in r.line_item.lower():
                return float(r.value) if r.value is not None else 0.0
    return 0.0


def get_latest_balance(
    db: Session, ticker: str, keywords: List[str], as_of: Optional[date] = None
) -> float:
    """
    Lấy giá trị Balance Sheet từ quý gần nhất CÓ chỉ tiêu đó (quý mới nạp dở, vd TCB Q3/2026 chỉ có IS+CF,
    không làm mất số). as_of: chỉ dùng quý đã quá hạn công bố (publication_lag_days) — chống lookahead.
    Dùng cho: Tổng tài sản, VCSH, Cho vay KH, Tiền gửi KH, vốn điều lệ...
    """
    from valuation.config import load_defaults

    lag = int((load_defaults().get("publication_lag_days") or {}).get("quarterly", 30))
    for yr, q in _find_latest_4_quarters(db, ticker):
        if as_of is not None and _quarter_end(yr, q) + timedelta(days=lag) > as_of:
            continue
        value = _query_value(db, ticker, keywords, yr, q)
        if value:
            return value
    return 0.0


def get_ttm_value(
    db: Session, ticker: str, keywords: List[str]
) -> float:
    """
    Tổng hợp TTM (sum 4 quý gần nhất) cho Income Statement items.
    Dùng cho: LNST, Thu nhập lãi thuần, Chi phí hoạt động...
    """
    quarters = _find_latest_4_quarters(db, ticker)
    if len(quarters) < 4:
        # Không đủ 4 quý → annualize quý có sẵn
        if not quarters:
            return 0.0
        total = sum(
            _query_value(db, ticker, keywords, yr, q)
            for yr, q in quarters
        )
        return total * (4 / len(quarters))

    return sum(
        _query_value(db, ticker, keywords, yr, q)
        for yr, q in quarters
    )


def get_mid_cycle_average(
    db: Session, ticker: str, keywords: List[str], years: int = 5
) -> float:
    """
    Tính trung bình của một chỉ tiêu (như LNST, EBITDA) trong chu kỳ 'years' năm (mặc định 5 năm).
    Nếu chưa đủ 5 năm thì tính trung bình số năm có sẵn.
    """
    rows = (
        db.query(
            FinancialsQuarterly.fiscal_year,
            FinancialsQuarterly.fiscal_quarter,
        )
        .filter(
            FinancialsQuarterly.ticker == ticker,
            FinancialsQuarterly.fiscal_quarter > 0,
        )
        .distinct()
        .order_by(
            desc(FinancialsQuarterly.fiscal_year),
            desc(FinancialsQuarterly.fiscal_quarter),
        )
        .limit(years * 4)
        .all()
    )
    if not rows:
        return 0.0
        
    # Tính tổng tất cả giá trị
    total_val = sum(
        _query_value(db, ticker, keywords, yr, q) for yr, q in rows
    )
    
    # Số năm thực tế có dữ liệu
    actual_years = len(rows) / 4.0
    if actual_years < 1.0:
        actual_years = 1.0
        
    return total_val / actual_years


def get_shares_outstanding(
    db: Session, ticker: str, as_of_date: Optional[date] = None, price_basis: bool = False
) -> float:
    """
    Tính shares outstanding từ:
    1. Trực tiếp từ outstanding_shares_volume hay shares_outstanding_value (HPG, SSI)
    2. Vốn điều lệ / Vốn góp / paid_in_capital (VCB, FPT) chia cho mệnh giá (10,000 VND/cp).

    price_basis=True: quy số cp tại as_of về CÙNG GỐC với chuỗi giá prices_daily — nguồn giá điều chỉnh
    lùi theo cổ tức CP/thưởng tới ngày giá cuối, nên as_of quá khứ (golden/registry) phải nhân thêm
    (1 + Σ tỷ lệ) các đợt có GDKHQ trong (as_of, ngày giá cuối] (HDB 28/09/2026: × 1,30). Mặc định
    False = số cp thật tại as_of.
    """
    latest_price = (
        db.query(PricesDaily.trade_date)
        .filter(PricesDaily.ticker == ticker)
        .order_by(PricesDaily.trade_date.desc())
        .first()
    )
    price_date = latest_price[0] if latest_price else date.today()
    # Chỉ cắt BCTC theo hạn công bố khi được hỏi một ngày quá khứ; chạy hiện tại dùng mọi kỳ đã có trong DB.
    bs_cutoff = as_of_date
    if as_of_date is None:
        as_of_date = price_date
    basis_date = max(as_of_date, price_date) if price_basis else as_of_date

    verified_shares = resolve_shares_override(
        ticker, as_of_date, _load_shares_events()
    )
    if verified_shares is not None:
        # Số VSDC là số thật tại as_of → mọi đợt chia sau as_of (tới ngày gốc giá) đều chưa có trong số này.
        factor = 1.0
        for ratio in _split_ratios_by_ex_date(db, ticker, as_of_date, basis_date).values():
            factor *= 1 + ratio
        return verified_shares * factor

    direct_shares = get_latest_balance(db, ticker, _DIRECT_SHARE_KEYS, as_of=bs_cutoff)
    if direct_shares > 0:
        return direct_shares * _unreflected_split_factor(db, ticker, _DIRECT_SHARE_KEYS, basis_date)

    # Vốn điều lệ thật: charter_capital/paid_in_capital. KHÔNG dùng owners_equity
    # làm proxy (đó là TỔNG vốn CSH, không phải vốn điều lệ → phóng đại số cp).
    von_dieu_le = get_latest_balance(db, ticker, _CAPITAL_KEYS, as_of=bs_cutoff)
    if von_dieu_le > 0:
        # Mệnh giá cổ phiếu VN = 10,000 VND
        return von_dieu_le / 10_000 * _unreflected_split_factor(db, ticker, _CAPITAL_KEYS, basis_date)

    raise ValueError(f"Không tìm được Vốn điều lệ hay Số lượng cổ phiếu cho {ticker} trong DB")


def get_balance_at_quarter(
    db: Session,
    ticker: str,
    keywords: List[str],
    year: int,
    quarter: int,
) -> float:
    """Lấy giá trị BS tại một quý cụ thể."""
    return _query_value(db, ticker, keywords, year, quarter)


def compute_historical_nim(
    db: Session, ticker: str, n_quarters: int = 4
) -> float:
    """
    Tính NIM thực tế TTM = Thu nhập lãi thuần TTM / Tổng tài sản trung bình.
    """
    quarters = _find_latest_4_quarters(db, ticker)
    if len(quarters) < n_quarters:
        return 0.0

    nii_ttm = sum(
        _query_value(db, ticker, ["net_interest_income", "Thu nhập lãi thuần"], yr, q)
        for yr, q in quarters[:n_quarters]
    )
    # Số dư bình quân đúng cửa sổ TTM: đầu kỳ = cuối CÙNG QUÝ năm trước (trước quý cũ nhất
    # của cửa sổ), cuối kỳ = quý mới nhất. Lấy cuối quý cũ nhất là bỏ mất một quý.
    ta_end = _query_value(
        db, ticker, ["total_assets", "TỔNG TÀI SẢN"], quarters[0][0], quarters[0][1]
    )
    ta_start = _query_value(
        db, ticker, ["total_assets", "TỔNG TÀI SẢN"], quarters[0][0] - 1, quarters[0][1]
    )
    # Thiếu số dư năm trước (mã mới niêm yết) → số dư cuối kỳ, không chia đôi thành NIM gấp đôi.
    avg_ta = (ta_start + ta_end) / 2 if ta_start > 0 else ta_end
    if avg_ta <= 0:
        return 0.0
    return nii_ttm / avg_ta


def compute_historical_cir(
    db: Session, ticker: str, n_quarters: int = 4
) -> float:
    """
    CIR TTM = Chi phí hoạt động TTM / Tổng thu nhập hoạt động TTM.
    """
    quarters = _find_latest_4_quarters(db, ticker)
    if len(quarters) < n_quarters:
        return 0.0

    opex_ttm = abs(sum(
        _query_value(db, ticker, ["general_and_admin_expenses", "IX. Chi phí hoạt động", "Chi phí hoạt động"], yr, q)
        for yr, q in quarters[:n_quarters]
    ))
    toi_ttm = sum(
        _query_value(db, ticker, ["total_operating_income", "VIII. Tổng thu nhập hoạt động", "Tổng thu nhập hoạt động"], yr, q)
        for yr, q in quarters[:n_quarters]
    )
    if toi_ttm <= 0:
        return 0.0
    return opex_ttm / toi_ttm


def compute_historical_credit_growth(
    db: Session, ticker: str
) -> float:
    """
    Credit growth YoY = (Cho vay KH quý cuối - Cho vay KH cùng quý năm trước) / Cho vay KH năm trước.
    """
    quarters = _find_latest_4_quarters(db, ticker)
    if not quarters:
        return 0.0
    latest_yr, latest_q = quarters[0]

    loans_now = _query_value(
        db, ticker, ["loans_and_advances_to_customers_net", "loans_and_advances_to_customers", "1. Cho vay khách hàng"], latest_yr, latest_q
    )
    loans_prev = _query_value(
        db, ticker, ["loans_and_advances_to_customers_net", "loans_and_advances_to_customers", "1. Cho vay khách hàng"], latest_yr - 1, latest_q
    )
    if loans_prev <= 0:
        return 0.0
    return (loans_now - loans_prev) / loans_prev


def compute_historical_credit_cost(
    db: Session, ticker: str, n_quarters: int = 4
) -> float:
    """
    Credit cost TTM = Chi phí dự phòng TTM / Cho vay KH trung bình.
    """
    quarters = _find_latest_4_quarters(db, ticker)
    if len(quarters) < n_quarters:
        return 0.0

    # Nguồn ghi chi phí mang dấu âm → đổi dấu (hoàn nhập ròng = chi phí âm), không abs.
    provision_ttm = -sum(
        _query_value(
            db, ticker,
            ["provision_for_credit_losses", "Chi phí dự phòng rủi ro tín dụng", "Chi phí dự phòng"],
            yr, q,
        )
        for yr, q in quarters[:n_quarters]
    )
    loans_end = _query_value(
        db, ticker, ["loans_and_advances_to_customers_net", "loans_and_advances_to_customers", "1. Cho vay khách hàng"],
        quarters[0][0], quarters[0][1],
    )
    # Đầu kỳ = cuối cùng quý năm trước (xem compute_historical_nim).
    loans_start = _query_value(
        db, ticker, ["loans_and_advances_to_customers_net", "loans_and_advances_to_customers", "1. Cho vay khách hàng"],
        quarters[0][0] - 1, quarters[0][1],
    )
    avg_loans = (loans_start + loans_end) / 2 if loans_start > 0 else loans_end
    if avg_loans <= 0:
        return 0.0
    return provision_ttm / avg_loans

def get_latest_tpcp_10y(db: Session) -> float:
    """Lấy lợi suất TPCP VN 10Y mới nhất từ bảng macro_series."""
    row = (
        db.query(MacroSeries)
        .filter(MacroSeries.indicator_code == "TPCP_10Y")
        .order_by(desc(MacroSeries.date))
        .first()
    )
    if row and row.value is not None:
        return float(row.value)
    return 0.032  # Fallback

def _beta_from_db(db: Session, ticker: str) -> Optional[float]:
    """Beta vs VNINDEX từ giá DB (đã điều chỉnh quyền), lợi suất TUẦN, 3 năm tính đến
    ngày giá chung mới nhất. Lợi suất ngày thiên thấp do thanh khoản mỏng/biên độ ±7%.
    None nếu thiếu dữ liệu. KHÔNG gọi live."""
    import datetime

    import pandas as pd

    def series(tk):
        rows = (db.query(PricesDaily.trade_date, PricesDaily.close)
                .filter(PricesDaily.ticker == tk).order_by(PricesDaily.trade_date).all())
        return pd.Series({pd.Timestamp(d): float(c) for d, c in rows if c is not None}, dtype=float)

    both = pd.concat({"t": series(ticker), "i": series("VNINDEX")}, axis=1).dropna()
    if both.empty:
        return None
    both = both[both.index >= both.index.max() - datetime.timedelta(days=3 * 365)]
    weekly = both.resample("W-FRI").last().dropna().pct_change().dropna()
    if len(weekly) < 52:
        return None
    var = weekly["i"].var(ddof=1)
    if var <= 0:
        return None
    return max(0.5, min(float(weekly["t"].cov(weekly["i"]) / var), 1.5))


def _blume_adjust(raw_beta: float) -> float:
    """Điều chỉnh Blume: beta_dùng = 0.67·beta_thô + 0.33·1.0.

    Chuẩn ngành (Bloomberg, Value Line) để SỬA SAI SỐ ƯỚC LƯỢNG beta — beta hồi
    quy có xu hướng hồi về 1.0 và bị thiên lệch xuống cho mã thanh khoản mỏng/
    mới niêm yết (vd NAB beta thô 0.59 phi thực tế cho bank nhỏ). Kéo các beta
    cực đoan về gần 1, ít đổi các beta vốn đã gần 1. Chặn dải hợp lý [0.6, 1.5].
    """
    adj = 0.67 * raw_beta + 0.33 * 1.0
    return max(0.6, min(adj, 1.5))


def estimate_vcb_beta(db: Session, ticker: str = "VCB") -> float:
    """Beta điều chỉnh Blume từ giá DB. Thiếu dữ liệu → beta_default trong config
    (không gọi vnstock trong lúc định giá, không dùng beta của VCB cho mọi mã)."""
    db_beta = _beta_from_db(db, ticker)
    if db_beta is not None:
        return _blume_adjust(db_beta)
    from valuation.config import load_defaults

    return float(load_defaults().get("coe_convention", {}).get("beta_default", 1.0))


_PEER_BETA_CACHE: dict = {}


def sector_peer_beta(db: Session, group: str, unlever: bool = False) -> float:
    """Beta ngành bottom-up = trung vị beta Blume các mã cùng nhóm routing.json (Damodaran).

    Beta hồi quy từng mã nhiễu (ACB 0,77; DSE 0,68 chuỗi ngắn) và mã mới niêm yết không có beta;
    cùng mô hình kinh doanh/chu kỳ → dùng chung beta ngành (D47 cho NH, mở rộng cho CTCK).
    Chỉ tính mã có beta hồi quy (≥ 52 tuần giá): beta_default của mã thiếu dữ liệu không phải
    quan sát, đưa vào sẽ kéo méo trung vị. Không mã nào đủ dữ liệu → beta_default.
    `unlever`: định chế tài chính KHÔNG khử đòn bẩy (nợ là nguyên liệu kinh doanh, Damodaran);
    khử/tái đòn bẩy cho phi tài chính chưa làm.
    """
    import json
    import statistics

    if unlever:
        raise ValueError("sector_peer_beta: chưa hỗ trợ khử đòn bẩy (chỉ dùng cho định chế tài chính)")
    last = db.query(PricesDaily.trade_date).filter(PricesDaily.ticker == "VNINDEX") \
        .order_by(PricesDaily.trade_date.desc()).first()
    key = (group, last[0] if last else None)
    if key not in _PEER_BETA_CACHE:
        routing = json.loads((Path(__file__).resolve().parents[1] / "config" / "routing.json")
                             .read_text(encoding="utf-8"))
        raw = (_beta_from_db(db, t) for t, v in sorted(routing.items()) if v.get("sector") == group)
        betas = [_blume_adjust(b) for b in raw if b is not None]
        from valuation.config import load_defaults

        _PEER_BETA_CACHE[key] = (
            statistics.median(betas) if betas
            else float(load_defaults().get("coe_convention", {}).get("beta_default", 1.0))
        )
    return _PEER_BETA_CACHE[key]


def recent_cash_payout(
    dps_events: List[Tuple[date, float]],
    split_events: List[Tuple[date, float]],
    shares: float,
    ttm_net_income: float,
    as_of: date,
) -> float:
    """Tỷ lệ chi trả tiền theo cổ tức đã GDKHQ trong 12 tháng tới as_of / LN TTM.

    DPS chia cho (1+tỷ lệ) của mỗi đợt cổ tức CP/thưởng GDKHQ SAU đợt tiền (cùng cửa sổ)
    để nhân được với số cp hiện tại: tiền chi = DPS_điều_chỉnh × số cp.
    """
    from datetime import timedelta

    if ttm_net_income <= 0 or shares <= 0:
        return 0.0
    start = as_of - timedelta(days=365)
    cash = 0.0
    for ex, dps in dps_events:
        if not (start < ex <= as_of) or dps <= 0:
            continue
        adj = dps
        for sx, ratio in split_events:
            if ex < sx <= as_of and ratio > 0:
                adj /= 1 + ratio
        cash += adj * shares
    return cash / ttm_net_income


def declared_cash_payout(db: Session, ticker: str, shares: float, ttm_net_income: float,
                         as_of: date) -> float:
    """recent_cash_payout với sự kiện lấy từ corporate_actions (chỉ dòng có ngày GDKHQ)."""
    from valuation.db.models import CorporateAction

    rows = db.query(CorporateAction.event_type, CorporateAction.ex_right_date,
                    CorporateAction.cash_amount_vnd_per_share, CorporateAction.exercise_ratio) \
        .filter(CorporateAction.ticker == ticker, CorporateAction.ex_right_date.isnot(None)).all()
    dps = {(ex, float(c)) for et, ex, c, _ in rows if et == "CASH_DIVIDEND" and c}
    splits = {(ex, float(r)) for et, ex, _, r in rows if et in _SPLIT_EVENT_TYPES and r}
    return recent_cash_payout(sorted(dps), sorted(splits), shares, ttm_net_income, as_of)


def build_vcb_current_financials(db: Session, ticker: str = "VCB") -> dict:
    """
    Xây dựng dict current_financials cho VCB từ dữ liệu thật trong DB.
    BS items: lấy quý cuối.
    IS items: tổng hợp TTM (4 quý).
    """
    # Ưu tiên key tiếng Anh (vnstock English line_item), fallback tiếng Việt.
    nii = get_ttm_value(db, ticker, ["net_interest_income", "I. Thu nhập lãi thuần", "Thu nhập lãi thuần"])
    toi = get_ttm_value(db, ticker, ["total_operating_income", "VIII. Tổng thu nhập hoạt động", "Tổng thu nhập hoạt động"])
    non_interest_income = toi - nii

    return {
        "total_equity": get_latest_balance(db, ticker, ["owners_equity", "shareholders_equity", "Vốn chủ sở hữu"]),
        "total_assets": get_latest_balance(db, ticker, ["total_assets", "TỔNG TÀI SẢN"]),
        "customer_loans": get_latest_balance(db, ticker, ["loans_and_advances_to_customers_net", "loans_and_advances_to_customers", "1. Cho vay khách hàng"]),
        "customer_deposits": get_latest_balance(
            db, ticker, ["deposits_from_customers", "Tiền gửi của khách hàng"]
        ),
        "net_income": get_ttm_value(
            db, ticker, ["net_profit_loss_after_tax", "XIV. Lợi nhuận sau thuế", "Lợi nhuận sau thuế"]
        ),
        "net_interest_income": nii,
        "non_interest_income": non_interest_income,
        "shares_outstanding": get_shares_outstanding(db, ticker),
        "current_price": 0.0,  # Được gán bên ngoài từ PricesDaily
    }


def build_fpt_current_financials(db: Session, ticker: str = "FPT") -> dict:
    """
    Xây dựng current_financials cho FPT từ DB (dùng line items tiếng Anh).
    """
    equity = get_latest_balance(db, ticker, ["owners_equity", "shareholders_equity", "capital_and_reserves", "Vốn chủ sở hữu"])
    assets = get_latest_balance(db, ticker, ["total_assets", "Tổng tài sản"])
    cash = get_latest_balance(db, ticker, ["cash_and_cash_equivalents", "Tiền và các khoản tương đương tiền"])
    
    st_borrow = get_latest_balance(db, ticker, ["short_term_borrowings", "Vay ngắn hạn"])
    lt_borrow = get_latest_balance(db, ticker, ["long_term_borrowings", "Vay dài hạn"])
    total_debt = st_borrow + lt_borrow
    
    net_sales = get_ttm_value(db, ticker, ["net_sales", "Doanh thu thuần"])
    net_income = get_ttm_value(db, ticker, ["net_profit_loss_after_tax", "Lợi nhuận sau thuế"])
    
    # EBITDA = operating_profit_loss + depreciation_and_amortization
    operating_profit = get_ttm_value(db, ticker, ["operating_profit_loss", "Lợi nhuận từ hoạt động kinh doanh"])
    depr = get_ttm_value(db, ticker, ["depreciation_and_amortization", "Khấu hao"])
    ebitda = operating_profit + depr if operating_profit > 0 or depr > 0 else net_income * 1.2
    
    return {
        "total_equity": equity,
        "total_assets": assets,
        "cash_and_equivalents": cash,
        "total_debt": total_debt,
        "total_revenue": net_sales,
        "net_income": net_income,
        "ebitda": ebitda,
        "shares_outstanding": get_shares_outstanding(db, ticker),
        "current_price": 0.0,
    }


def build_hpg_current_financials(db: Session, ticker: str = "HPG") -> dict:
    """
    Xây dựng current_financials cho HPG từ DB.
    """
    equity = get_latest_balance(db, ticker, ["owners_equity", "shareholders_equity", "capital_and_reserves", "Vốn chủ sở hữu"])
    assets = get_latest_balance(db, ticker, ["total_assets", "Tổng tài sản"])
    cash = get_latest_balance(db, ticker, ["cash_and_cash_equivalents", "Tiền và các khoản tương đương tiền"])
    st_invest = get_latest_balance(db, ticker, ["short_term_financial_investments", "Đầu tư tài chính ngắn hạn"])
    cash_total = cash + st_invest
    
    st_borrow = get_latest_balance(db, ticker, ["short_term_borrowings", "Vay ngắn hạn"])
    lt_borrow = get_latest_balance(db, ticker, ["long_term_borrowings", "Vay dài hạn"])
    total_debt = st_borrow + lt_borrow
    
    net_sales = get_ttm_value(db, ticker, ["net_revenue_from_goods_and_services_rendered", "net_sales", "Doanh thu thuần"])
    net_income = get_ttm_value(db, ticker, ["net_profit_loss_after_tax", "Lợi nhuận sau thuế"])
    
    # HPG: EBITDA thật từ vnstock có thể không có dòng "ebitda". Dự phòng EBITDA = EBIT + D&A.
    # EBIT = operating_profit_loss hoặc net_profit_loss_before_tax + interest_expenses.
    # Ta lấy ebitda từ DB, nếu bằng 0 thì tính toán xấp xỉ
    ebitda = get_ttm_value(db, ticker, ["ebitda"])
    if ebitda <= 0:
        operating_profit = get_ttm_value(db, ticker, ["operating_profit_loss", "Lợi nhuận từ hoạt động kinh doanh"])
        depr = get_ttm_value(db, ticker, ["depreciation_and_amortization", "Khấu hao"])
        ebitda = operating_profit + depr if operating_profit > 0 or depr > 0 else net_income * 1.2
    
    return {
        "total_equity": equity,
        "total_assets": assets,
        "cash_and_equivalents": cash_total,
        "total_debt": total_debt,
        "total_revenue": net_sales,
        "net_income": net_income,
        "ebitda": ebitda,
        "shares_outstanding": get_shares_outstanding(db, ticker),
        "current_price": 0.0,
    }


def build_ssi_current_financials(db: Session, ticker: str = "SSI") -> dict:
    """
    Xây dựng current_financials cho SSI từ DB.
    """
    equity = get_latest_balance(db, ticker, ["owners_equity", "shareholders_equity", "capital_and_reserves", "Vốn chủ sở hữu"])
    assets = get_latest_balance(db, ticker, ["total_assets", "Tổng tài sản"])
    net_sales = get_ttm_value(db, ticker, ["net_revenue_from_goods_and_services_rendered", "net_sales", "Doanh thu thuần"])
    net_income = get_ttm_value(db, ticker, ["net_profit_loss_after_tax", "Lợi nhuận sau thuế"])
    
    return {
        "total_equity": equity,
        "total_assets": assets,
        "total_revenue": net_sales,
        "net_income": net_income,
        "shares_outstanding": get_shares_outstanding(db, ticker),
        "current_price": 0.0,
    }


def build_dgc_current_financials(db: Session, ticker: str = "DGC") -> dict:
    """
    Xây dựng current_financials cho DGC từ DB.
    """
    equity = get_latest_balance(db, ticker, ["owners_equity", "shareholders_equity", "capital_and_reserves", "Vốn chủ sở hữu"])
    assets = get_latest_balance(db, ticker, ["total_assets", "Tổng tài sản"])
    cash = get_latest_balance(db, ticker, ["cash_and_cash_equivalents", "Tiền và các khoản tương đương tiền"])
    st_invest = get_latest_balance(db, ticker, ["short_term_financial_investments", "Đầu tư tài chính ngắn hạn"])
    cash_total = cash + st_invest
    
    st_borrow = get_latest_balance(db, ticker, ["short_term_borrowings", "Vay ngắn hạn"])
    lt_borrow = get_latest_balance(db, ticker, ["long_term_borrowings", "Vay dài hạn"])
    total_debt = st_borrow + lt_borrow
    
    net_sales = get_ttm_value(db, ticker, ["net_revenue_from_goods_and_services_rendered", "net_sales", "Doanh thu thuần"])
    net_income = get_ttm_value(db, ticker, ["net_profit_loss_after_tax", "Lợi nhuận sau thuế"])
    
    # EBITDA = operating_profit_loss + depreciation_and_amortization
    ebitda = get_ttm_value(db, ticker, ["ebitda"])
    if ebitda <= 0:
        operating_profit = get_ttm_value(db, ticker, ["operating_profit_loss", "Lợi nhuận từ hoạt động kinh doanh"])
        depr = get_ttm_value(db, ticker, ["depreciation_and_amortization", "Khấu hao"])
        ebitda = operating_profit + depr if operating_profit > 0 or depr > 0 else net_income * 1.2
        
    return {
        "total_equity": equity,
        "total_assets": assets,
        "cash_and_equivalents": cash_total,
        "total_debt": total_debt,
        "total_revenue": net_sales,
        "net_income": net_income,
        "ebitda": ebitda,
        "shares_outstanding": get_shares_outstanding(db, ticker),
        "current_price": 0.0,
    }
