"""DCF: liên doanh định giá theo lợi nhuận, CapEx nhất quán với tăng trưởng (D45).

Số liệu tính tay; đơn vị đồng trừ khi ghi chú.
"""
import pytest

from valuation.data_access.repo import growth_consistent_capex, sales_to_capital
from valuation.engine.models.dcf import DCFValuationModel

SHARES = 100e6


def _dcf(jv_income=0.0, jv_book=0.0, non_operating=0.0, target_pe=10.0):
    cf = {
        "total_equity": 5_000e9, "total_assets": 8_000e9, "cash_and_equivalents": 1_000e9,
        "total_debt": 500e9, "minority_interest": 0.0, "non_operating_assets": non_operating,
        "jv_income": jv_income, "jv_book": jv_book,
        "total_revenue": 4_000e9, "cogs": 2_800e9, "ebitda": 800e9,
        "shares_outstanding": SHARES, "current_price": 50_000.0,
    }
    ass = {
        "cost_of_equity": 0.12, "wacc": 0.11, "revenue_growth": [0.10] * 5,
        "ebit_margin": [0.15] * 5, "tax_rate": 0.20, "capex_to_revenue": [0.05] * 5,
        "depr_to_revenue": [0.04] * 5, "dso": [30.0] * 5, "dio": [30.0] * 5, "dpo": [30.0] * 5,
        "interest_rate": [0.08] * 5, "debt_repayment_rate": [0.2] * 5,
        "new_borrowing_rate": [0.05] * 5, "target_ev_ebitda": 8.0, "target_pe": target_pe,
        "long_term_growth": 0.04, "weight_dcf": 0.5,
    }
    return DCFValuationModel("TST", cf, ass)


def test_jv_stake_valued_at_parent_pe_in_dcf_leg_only():
    # Đầu tư dài hạn 250 tỷ, trong đó liên doanh 200 tỷ sổ sách, lãi liên doanh 100 tỷ/năm.
    # P/E 10x → liên doanh đáng 1.000 tỷ: chân DCF tăng (1.000 − 200) tỷ / 100 triệu cp = 8.000đ.
    book = _dcf(non_operating=250e9).perform_valuation()
    jv = _dcf(jv_income=100e9, jv_book=200e9, non_operating=250e9).perform_valuation()
    assert jv["dcf_fvps"] - book["dcf_fvps"] == pytest.approx(8_000.0)
    # Chân EV/EBITDA: bội số lịch sử đã phản ánh giá thị trường của liên doanh → không đổi.
    assert jv["multiples_fvps"] == pytest.approx(book["multiples_fvps"])
    assert jv["jv_value"] == pytest.approx(1_000e9)


def test_jv_loss_or_missing_book_keeps_book_value():
    base = _dcf(non_operating=250e9).perform_valuation()["dcf_fvps"]
    # Liên doanh lỗ: giữ giá sổ sách, không tạo giá trị âm.
    assert _dcf(jv_income=-50e9, jv_book=200e9, non_operating=250e9).perform_valuation()["dcf_fvps"] == pytest.approx(base)
    # Không tách được sổ sách liên doanh: không định giá lại (tránh cộng trùng vào đầu tư dài hạn).
    assert _dcf(jv_income=100e9, jv_book=0.0, non_operating=250e9).perform_valuation()["dcf_fvps"] == pytest.approx(base)


def test_sales_to_capital_from_operating_invested_capital():
    # Vốn vận hành = VCSH 15.607 + nợ vay 2.519 − tiền 1.788 − ĐTNH 3.640 − ĐTDH 4.856 = 7.842 tỷ.
    # Doanh thu 6.399 / 7.842 = 0,816 (GMD TTM Q2/2026).
    assert sales_to_capital(6_399, 15_607, 2_519, 1_788, 3_640, 4_856) == pytest.approx(0.816, abs=1e-3)
    # Vốn vận hành ≤ 0 (tiền và đầu tư lớn hơn vốn) → không tính được, trả None.
    assert sales_to_capital(1_000, 500, 0, 400, 200, 100) is None
    # Ngoài dải cấu hình thì kẹp về biên (mặc định [0,3; 5,0]).
    assert sales_to_capital(10_000, 1_000, 0, 0, 0, 0) == pytest.approx(5.0)


def test_capex_schedule_falls_as_growth_fades():
    # CapEx/DT = khấu hao/DT + g/(1+g) × (1/doanh thu trên vốn − vốn lưu động/DT)
    # g 10%: 0,04 + 0,1/1,1 × (1/1,0 − 0,1) = 0,04 + 0,0818 = 0,1218
    # g 4%:  0,04 + 0,04/1,04 × 0,9 = 0,04 + 0,0346 = 0,0746
    capex = growth_consistent_capex([0.10, 0.04], depr_ratio=0.04, nwc_ratio=0.10, s2c=1.0)
    assert capex[0] == pytest.approx(0.1218, abs=1e-4)
    assert capex[1] == pytest.approx(0.0746, abs=1e-4)
    # Không thấp hơn khấu hao (CapEx duy trì ≥ khấu hao), kể cả khi doanh thu giảm.
    assert growth_consistent_capex([-0.05], depr_ratio=0.04, nwc_ratio=0.10, s2c=1.0) == [pytest.approx(0.04)]
