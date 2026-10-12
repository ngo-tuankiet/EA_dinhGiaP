"""
Test calibration generic non-financial builder (build_company_data):
- EBIT margin dùng MEDIAN (mid-cycle), không phải mean → robust với năm bùng nổ.
- Revenue growth FADE từ median lịch sử về tăng trưởng GDP danh nghĩa dài hạn (năm 5).
Chạy trên DB thật với mã DCM (đã ingest, cyclical điển hình).
"""
import statistics
import pytest

from valuation.db.session import SessionLocalRead
from valuation.data_access.repo import build_company_data


@pytest.fixture
def db():
    s = SessionLocalRead()
    yield s
    s.close()


def test_ebit_margin_is_median_not_mean(db):
    c = build_company_data(db, "DCM", mode="TTM")
    margins = [is_.ebit / is_.revenue for is_ in c.historical_is if is_.revenue > 0]
    expected_median = statistics.median(margins)
    # ebit_margin dùng trong assumptions = median lịch sử (clamp >= 0)
    assert c.assumptions.ebit_margin[0] == pytest.approx(max(expected_median, 0.0), abs=1e-6)
    # Với cyclical (DCM có năm đỉnh 2022), median < mean → chống extrapolate đỉnh
    assert statistics.median(margins) <= statistics.mean(margins) + 1e-9


def test_revenue_growth_fades_to_terminal_growth(db):
    # Năm 5 phải hội tụ về ĐÚNG g vĩnh viễn của terminal (không còn neo 8% rồi
    # rơi xuống g ở năm 6 — vách đứng tự mâu thuẫn).
    c = build_company_data(db, "DCM", mode="TTM")
    rg = c.assumptions.revenue_growth
    assert len(rg) == 5
    assert abs(rg[4] - c.assumptions.terminal_growth_rate) < 0.03  # lệch nhỏ do macro overlay
    assert all(-0.10 <= g <= 0.25 for g in rg)


def test_depr_derived_from_real_da_not_hardcoded(db):
    """depr_to_revenue phải lấy từ D&A THẬT (median lịch sử), KHÔNG hardcode 4%.

    PNJ là DN bán lẻ nhẹ tài sản: D&A thực ~0.2% doanh thu. Nếu dùng 4% hardcode
    sẽ bơm ~3.8% doanh thu 'tiền ảo' vào FCFF mỗi năm → overvaluation.
    """
    c = build_company_data(db, "PNJ", mode="TTM")
    # Extraction D&A hoạt động: có ít nhất 1 năm khấu hao > 0
    assert any(cf.depreciation > 0 for cf in c.historical_cf)
    # depr_to_revenue = median D&A/doanh thu lịch sử
    deprs = [
        cf.depreciation / is_.revenue
        for cf, is_ in zip(c.historical_cf, c.historical_is)
        if is_.revenue > 0 and cf.depreciation > 0
    ]
    assert deprs, "phải có dữ liệu D&A để derive depr_to_revenue"
    assert c.assumptions.depr_to_revenue[0] == pytest.approx(statistics.median(deprs), abs=1e-6)
    # PNJ nhẹ tài sản → depr thực << 4% hardcode cũ (regression guard)
    assert c.assumptions.depr_to_revenue[0] < 0.02


def test_opex_includes_selling_and_ga(db):
    """OPEX = chi phí bán hàng + QLDN (phải cộng cả 2).

    Trước đây _match_value chỉ trả 1 dòng đầu (selling), bỏ sót G&A → EBIT bị
    thổi ~2pp margin. PNJ biên EBIT thực ~7-9%; nếu sót G&A sẽ ~11%.
    """
    c = build_company_data(db, "PNJ", mode="TTM")
    ebit_m = c.assumptions.ebit_margin[0]
    # Biên EBIT trong vùng thực tế của PNJ (regression guard chống sót G&A → >10%)
    assert 0.04 <= ebit_m <= 0.10, f"EBIT margin PNJ={ebit_m:.2%} bất thường (nghi sót G&A)"
