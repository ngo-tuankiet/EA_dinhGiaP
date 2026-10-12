"""Test chỉ số hiệu chuẩn — hàm thuần, không chạm DB.

Mọi trị số kỳ vọng đều tính tay được (AGENTS.md §4.3).
"""
import pytest

from valuation.calibration.consensus_view import recency_weight, weighted_median
from valuation.calibration.metrics import (
    BAND_DEFAULT,
    ERROR,
    IN_BAND,
    NO_CONSENSUS,
    OUT_HIGH,
    OUT_LOW,
    Observation,
    aggregate,
    build_observation,
    classify_band,
)


class TestClassifyBand:
    def test_trong_band(self):
        assert classify_band(0.0, 0.20) == IN_BAND
        assert classify_band(0.19, 0.20) == IN_BAND
        assert classify_band(-0.19, 0.20) == IN_BAND

    def test_dung_bang_bien_van_la_trong_band(self):
        # Quyết định thiết kế: ±20% ĐÚNG BẰNG biên vẫn tính đạt, không bắt giải trình.
        assert classify_band(0.20, 0.20) == IN_BAND
        assert classify_band(-0.20, 0.20) == IN_BAND

    def test_ngoai_band(self):
        assert classify_band(0.2001, 0.20) == OUT_HIGH
        assert classify_band(-0.2001, 0.20) == OUT_LOW
        assert classify_band(0.341, 0.20) == OUT_HIGH      # ACB thực tế
        assert classify_band(-0.761, 0.20) == OUT_LOW      # nhóm PB thực tế

    def test_khong_co_consensus(self):
        assert classify_band(None, 0.20) == NO_CONSENSUS

    def test_band_rong_hon_cho_proxy(self):
        # SOTP/RNAV được nới band vì bản chất proxy kém chính xác.
        assert classify_band(-0.30, 0.35) == IN_BAND
        assert classify_band(-0.30, 0.20) == OUT_LOW


class TestWeightedMedian:
    def test_trong_so_bang_nhau_n_le_trung_median_thuong(self):
        assert weighted_median([10.0, 20.0, 30.0], [1.0, 1.0, 1.0]) == 20.0

    def test_trong_so_lech_keo_ve_phia_nang(self):
        # Tính tay: tổng trọng số = 1+1+8 = 10, mốc 50% = 5.
        # Sắp xếp: 10(w=1, tích luỹ 1), 20(w=1, tích luỹ 2), 30(w=8, tích luỹ 10 >= 5)
        # -> trả 30.
        assert weighted_median([10.0, 20.0, 30.0], [1.0, 1.0, 8.0]) == 30.0

    def test_bo_qua_trong_so_khong(self):
        assert weighted_median([10.0, 999.0], [1.0, 0.0]) == 10.0

    def test_rong_tra_none(self):
        assert weighted_median([], []) is None
        assert weighted_median([10.0], [0.0]) is None


class TestRecencyWeight:
    def test_tat_weighting(self):
        assert recency_weight(365, None) == 1.0

    def test_dung_chu_ky_ban_ra_thi_bang_mot_nua(self):
        assert recency_weight(90, 90) == pytest.approx(0.5)
        assert recency_weight(180, 90) == pytest.approx(0.25)

    def test_hom_nay_trong_so_toi_da(self):
        assert recency_weight(0, 90) == pytest.approx(1.0)


class _FakeView:
    """ConsensusView tối giản cho test build_observation."""

    def __init__(self, median=None, weighted=None, count=0,
                 vmin=None, vmax=None, age=None):
        self.median = median
        self.weighted_median = weighted
        self.count = count
        self.min = vmin
        self.max = vmax
        self.newest_age_days = age


class TestBuildObservation:
    def test_tinh_lech_dung(self):
        # FV 39.547, CTCK median 29.500 -> (39547-29500)/29500 = +34.06%
        # FV vs thị giá 22.650 -> +74.6%   (số thật của ACB)
        obs = build_observation(
            "ACB",
            {"method": "RI_PB", "group": "NH", "fair_value": 39547.0, "price": 22650.0},
            _FakeView(median=29500.0, count=3),
        )
        assert obs.dev_vs_consensus == pytest.approx(0.3406, abs=1e-4)
        assert obs.dev_vs_price == pytest.approx(0.7460, abs=1e-4)
        assert obs.band_status == OUT_HIGH

    def test_mac_lo_thi_band_status_la_error(self):
        obs = build_observation(
            "XYZ", {"method": "DCF", "error": "ValueError: hỏng"}, _FakeView(median=100.0),
        )
        assert obs.band_status == ERROR
        assert obs.error is not None

    def test_khong_co_consensus(self):
        obs = build_observation(
            "XYZ", {"method": "DCF", "fair_value": 100.0, "price": 90.0}, _FakeView(),
        )
        assert obs.band_status == NO_CONSENSUS
        assert obs.dev_vs_consensus is None
        # Vẫn đo được lệch vs thị giá — đây là sanity độc lập với CTCK.
        assert obs.dev_vs_price == pytest.approx(0.1111, abs=1e-4)

    def test_chia_cho_khong_khong_lam_no_chuong_trinh(self):
        obs = build_observation(
            "XYZ", {"method": "DCF", "fair_value": 100.0, "price": 0.0}, _FakeView(median=0.0),
        )
        assert obs.dev_vs_price is None
        assert obs.dev_vs_consensus is None

    def test_co_bao_dong_fv_thap_hon_thi_gia(self):
        # VIC thật: FV 16.911 vs thị giá 208.500 -> -91.9%
        obs = build_observation(
            "VIC", {"method": "SOTP", "fair_value": 16911.0, "price": 208500.0}, _FakeView(),
        )
        assert obs.below_price_alarm is True


class TestAggregate:
    def _obs(self, ticker, method, dev, dev_price=None, band=BAND_DEFAULT):
        return Observation(
            ticker=ticker, method=method, dev_vs_consensus=dev,
            dev_vs_price=dev_price, band=band,
            band_status=classify_band(dev, band),
        )

    def test_tong_hop_toan_cuc_va_theo_nhom(self):
        obs = [
            self._obs("A", "DCF", -0.30, -0.50),
            self._obs("B", "DCF", -0.10, -0.20),
            self._obs("C", "RI_PB", 0.40, 0.10),
            self._obs("D", "RI_PB", 0.10, 0.05),
        ]
        agg = aggregate(obs)
        # median của [-0.30, -0.10, 0.40, 0.10] = (-0.10 + 0.10)/2 = 0.0
        assert agg["overall"]["median_dev"] == pytest.approx(0.0)
        assert agg["overall"]["n"] == 4
        assert agg["overall"]["n_with_consensus"] == 4
        # 2/4 trong band (B: -0.10, D: +0.10)
        assert agg["overall"]["share_in_band"] == pytest.approx(0.5)
        # Chỉ A có dev_vs_price <= -0.40
        assert agg["overall"]["n_below_price_40"] == 1
        assert agg["overall"]["n_below_price"] == 2

        assert agg["by_method"]["DCF"]["median_dev"] == pytest.approx(-0.20)
        assert agg["by_method"]["RI_PB"]["median_dev"] == pytest.approx(0.25)

    def test_nhom_rong_khong_lam_no(self):
        agg = aggregate([])
        assert agg["overall"]["n"] == 0
        assert agg["overall"]["median_dev"] is None
        assert agg["overall"]["share_in_band"] is None

    def test_ma_loi_khong_lam_hong_thong_ke(self):
        obs = [
            self._obs("A", "DCF", -0.10),
            Observation(ticker="B", method="DCF", error="boom", band_status=ERROR),
        ]
        agg = aggregate(obs)
        assert agg["overall"]["n"] == 2
        assert agg["overall"]["n_with_consensus"] == 1
        assert agg["overall"]["n_errors"] == 1
