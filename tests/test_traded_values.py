"""Engine xếp hạng: cột prices_daily.value trống (vnstock không trả) từng khiến MỌI mã "thanh khoản không đạt"."""

from types import SimpleNamespace

from valuation.data_access.investment_snapshot import traded_values


def _p(value, close, volume):
    return SimpleNamespace(value=value, close=close, volume=volume)


def test_traded_value_falls_back_to_close_times_volume():
    # value trống: 10.000 đ × 2.000.000 cp = 20 tỷ; value có sẵn thì dùng nguyên.
    rows = [_p(None, 10000, 2_000_000), _p(15e9, 10000, 1), _p(None, 10000, None)]
    assert traded_values(rows) == [20e9, 15e9]
