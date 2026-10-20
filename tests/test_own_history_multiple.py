"""Bội số lịch sử của chính mã: quan sát ngoài dải hợp lý bị loại TRƯỚC khi lấy trung vị.

Regression CTD: P/E cuối năm 120x (năm lãi đáy 21 tỷ), 36,9x, 18,9x, 10,6x → trung vị cũ
27,9x bị kéo bởi năm mẫu số méo, áp lên LN đã phục hồi → FV gấp 3 thị giá.
"""
import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.data_access.repo import own_history_multiple
from valuation.db.models import PricesDaily, Ticker
from valuation.db.session import Base


def _db(year_end_prices):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Ticker(ticker="ZZM", company_name="ZZM", is_vn100=True))
    for y, px in year_end_prices.items():
        db.add(PricesDaily(ticker="ZZM", trade_date=datetime.date(y, 12, 30), close=px))
    db.commit()
    return db


def test_out_of_band_observations_are_dropped_before_median():
    # 100 triệu cp; LN (tỷ) chọn để P/E = 120, 36.9, 18.9, 10.6 với giá 12.000đ.
    shares_m, px = 100.0, 12_000
    mcap = px * shares_m / 1e3  # 1.200 tỷ
    ni = {2022: mcap / 120, 2023: mcap / 36.9, 2024: mcap / 18.9, 2025: mcap / 10.6}
    db = _db({y: px for y in ni})
    # Không lọc: trung vị (36,9 + 18,9)/2 = 27,9x
    assert own_history_multiple(db, "ZZM", ni, shares_m) == pytest.approx(27.9)
    # Lọc dải P/E [3, 40]: bỏ 120x → trung vị(36,9; 18,9; 10,6) = 18,9x
    assert own_history_multiple(db, "ZZM", ni, shares_m, kind="pe") == pytest.approx(18.9)


def test_fewer_than_three_valid_observations_returns_none():
    shares_m, px = 100.0, 12_000
    mcap = px * shares_m / 1e3
    ni = {2023: mcap / 120, 2024: mcap / 300, 2025: mcap / 10}
    assert own_history_multiple(_db({y: px for y in ni}), "ZZM", ni, shares_m, kind="pe") is None


def test_ttm_period_priced_at_quarter_end_counts_toward_history():
    # D62. 100 tr cp. 2023: 1.200 tỷ / LN 100 = 12,0x; 2024: 1.200/80 = 15,0x;
    # TTM 2025 (đến Q2): giá 30/06/2025 = 9.000 → 900/120 = 7,5x → trung vị = 12,0x.
    db = _db({2023: 12_000, 2024: 12_000})
    db.add(PricesDaily(ticker="ZZM", trade_date=datetime.date(2025, 6, 30), close=9_000))
    db.commit()
    ni = {2023: 100.0, 2024: 80.0, 2025: 120.0}
    assert own_history_multiple(db, "ZZM", ni, 100.0, kind="pe") is None  # cũ: thiếu giá 31/12/2025
    assert own_history_multiple(
        db, "ZZM", ni, 100.0, kind="pe", period_end={2025: datetime.date(2025, 6, 30)}
    ) == pytest.approx(12.0)


def test_peer_median_drops_meaningless_and_needs_min_peers():
    from valuation.data_access.repo import peer_median_multiple  # dải ev_ebitda [2, 25]

    assert peer_median_multiple([5.0, 9.0, 30.0, -4.0, None], "ev_ebitda", 3) is None
    assert peer_median_multiple([5.0, 9.0, 12.0, 30.0, None], "ev_ebitda", 3) == pytest.approx(9.0)


def test_current_multiples_hand_case():
    from types import SimpleNamespace as N

    from valuation.data_access.repo import current_multiples

    # Vốn hóa = 20.000 × 100 tr / 1e3 = 2.000 tỷ; EV = 2.000 + nợ 500 − tiền 200 = 2.300; EBITDA = 180 + 50.
    c = N(
        current_price=20_000,
        shares_outstanding=100.0,
        historical_is=[N(year=2025, ebit=180.0, net_income=100.0)],
        historical_cf=[N(year=2025, depreciation=50.0)],
        historical_bs=[
            N(short_term_debt=500.0, long_term_debt=0.0, cash_and_equivalents=200.0,
              short_term_financial_investments=0.0, minority_interest=0.0, long_term_investments_net=0.0,
              construction_in_progress=0.0)
        ],
    )
    assert current_multiples(c) == {"ev_ebitda": pytest.approx(10.0), "pe": pytest.approx(20.0)}
