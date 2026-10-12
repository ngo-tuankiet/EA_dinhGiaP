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
