"""Test nguồn đọc đồng thuận CTCK duy nhất.

Trọng tâm: dedup theo CTCK (một CTCK ra nhiều báo cáo chỉ được 1 phiếu) và chống
lookahead (không nhìn thấy báo cáo tương lai) — hai thứ mà `get_consensus_stats`
cũ làm sai/không làm.
"""
import datetime

import pytest

from valuation.calibration.consensus_view import get_consensus_view
from valuation.db.models import Consensus, Ticker
from valuation.db.session import SessionLocalWrite

_TK = "TESTCV"


@pytest.fixture
def db_session():
    s = SessionLocalWrite()
    s.query(Consensus).filter(Consensus.ticker == _TK).delete()
    s.query(Ticker).filter(Ticker.ticker == _TK).delete()
    s.commit()
    s.add(Ticker(ticker=_TK, company_name="Test CV", sector="Tech", is_vn100=False))
    s.commit()
    yield s
    s.query(Consensus).filter(Consensus.ticker == _TK).delete()
    s.query(Ticker).filter(Ticker.ticker == _TK).delete()
    s.commit()
    s.close()


def _add(s, broker, date, tp, rating="MUA", canon=None, synthetic=False):
    s.add(Consensus(ticker=_TK, broker=broker, report_date=date,
                    target_price=tp, rating=rating,
                    broker_canon=(canon or broker), is_synthetic=synthetic,
                    source_url="https://24hmoney.vn/stock/TESTCV", raw_quote="test"))
    s.commit()


TODAY = datetime.date(2026, 8, 11)


class TestDedupTheoCTCK:
    def test_mot_ctck_nhieu_bao_cao_chi_duoc_mot_phieu(self, db_session):
        """Bug cũ: SSI ra 3 báo cáo -> 3 phiếu, kéo lệch median."""
        _add(db_session, "SSI", TODAY - datetime.timedelta(days=10), 30000)
        _add(db_session, "SSI", TODAY - datetime.timedelta(days=20), 28000)
        _add(db_session, "SSI", TODAY - datetime.timedelta(days=30), 26000)
        _add(db_session, "VNDS", TODAY - datetime.timedelta(days=5), 50000)

        view = get_consensus_view(db_session, _TK, as_of=TODAY)
        assert view.count == 2, "Phải là SỐ CTCK (2), không phải số báo cáo (4)"
        assert view.n_reports_raw == 4
        # Chỉ báo cáo MỚI NHẤT của SSI (30.000) được tính -> median(30000, 50000) = 40000
        assert view.median == pytest.approx(40000.0)

    def test_tat_dedup_thi_dem_moi_bao_cao(self, db_session):
        _add(db_session, "SSI", TODAY - datetime.timedelta(days=10), 30000)
        _add(db_session, "SSI", TODAY - datetime.timedelta(days=20), 28000)
        view = get_consensus_view(db_session, _TK, as_of=TODAY, dedup=False)
        assert view.count == 2


class TestGopTheoTenChuanHoa:
    """D24: cùng một CTCK dưới hai tên nguồn khác nhau chỉ được 1 phiếu."""

    def test_VCSC_va_VIETCAP_la_mot_ctck(self, db_session):
        # 24hmoney gọi VIETCAP, Simplize gọi VCSC — cùng Vietcap.
        _add(db_session, "VIETCAP", TODAY - datetime.timedelta(days=2), 30000, canon="VIETCAP")
        _add(db_session, "VCSC", TODAY - datetime.timedelta(days=9), 20000, canon="VIETCAP")
        _add(db_session, "SSI", TODAY - datetime.timedelta(days=1), 50000, canon="SSI")

        view = get_consensus_view(db_session, _TK, as_of=TODAY)
        assert view.count == 2, "VIETCAP và VCSC phải gộp thành 1 CTCK"
        assert view.n_reports_raw == 3
        # Giữ báo cáo mới nhất của Vietcap (30.000) -> median(30000, 50000)
        assert view.median == pytest.approx(40000.0)

    def test_giu_lai_ten_goc_de_truy_vet(self, db_session):
        _add(db_session, "VCSC", TODAY, 20000, canon="VIETCAP")
        view = get_consensus_view(db_session, _TK, as_of=TODAY)
        q = view.quotes[0]
        assert q.broker == "VIETCAP"      # tên chuẩn dùng để gộp
        assert q.broker_raw == "VCSC"     # tên gốc vẫn truy vết được


class TestLoaiDuLieuGia:
    def test_dong_synthetic_bi_loai_khoi_thong_ke(self, db_session):
        """Dòng seed test (scratch) không được lẫn vào median thật."""
        _add(db_session, "REAL", TODAY, 30000)
        _add(db_session, "FAKE", TODAY, 99000, synthetic=True)
        view = get_consensus_view(db_session, _TK, as_of=TODAY)
        assert view.count == 1
        assert view.median == pytest.approx(30000.0)

    def test_co_the_bat_lai_khi_debug(self, db_session):
        _add(db_session, "REAL", TODAY, 30000)
        _add(db_session, "FAKE", TODAY, 99000, synthetic=True)
        view = get_consensus_view(db_session, _TK, as_of=TODAY, include_synthetic=True)
        assert view.count == 2


class TestChongLookahead:
    def test_khong_nhin_thay_bao_cao_tuong_lai(self, db_session):
        _add(db_session, "SSI", TODAY - datetime.timedelta(days=5), 30000)
        _add(db_session, "VNDS", TODAY + datetime.timedelta(days=5), 99000)  # tương lai
        view = get_consensus_view(db_session, _TK, as_of=TODAY)
        assert view.count == 1
        assert view.median == pytest.approx(30000.0)

    def test_bao_cao_ngoai_cua_so_bi_loai(self, db_session):
        _add(db_session, "SSI", TODAY - datetime.timedelta(days=10), 30000)
        _add(db_session, "VNDS", TODAY - datetime.timedelta(days=200), 99000)
        view = get_consensus_view(db_session, _TK, as_of=TODAY, window_days=180)
        assert view.count == 1
        assert view.median == pytest.approx(30000.0)


class TestTrongSoDoMoi:
    def test_bao_cao_moi_duoc_uu_tien_khi_bat_weighting(self, db_session):
        # Cũ (180 ngày, w=0.25 với half-life 90) giá thấp; mới (0 ngày, w=1.0) giá cao.
        _add(db_session, "OLD", TODAY - datetime.timedelta(days=180), 10000)
        _add(db_session, "NEW", TODAY, 30000)
        view = get_consensus_view(db_session, _TK, as_of=TODAY, half_life_days=90)
        assert view.median == pytest.approx(20000.0)      # median thường: (10k+30k)/2
        # Có trọng số: tổng w = 0.25 + 1.0 = 1.25, mốc 50% = 0.625.
        # Sắp xếp tăng dần: 10000(w=0.25, tích luỹ 0.25 < 0.625), 30000(tích luỹ 1.25 >= 0.625)
        assert view.weighted_median == pytest.approx(30000.0)

    def test_tat_weighting_thi_moi_trong_so_bang_1(self, db_session):
        _add(db_session, "OLD", TODAY - datetime.timedelta(days=180), 10000)
        _add(db_session, "NEW", TODAY, 30000)
        view = get_consensus_view(db_session, _TK, as_of=TODAY, half_life_days=None)
        assert all(q.weight == 1.0 for q in view.quotes)


class TestTruongHopBien:
    def test_khong_co_du_lieu(self, db_session):
        view = get_consensus_view(db_session, _TK, as_of=TODAY)
        assert view.count == 0
        assert view.median is None
        assert view.has_data is False
        assert view.stale is True

    def test_gia_muc_tieu_am_hoac_khong_bi_loai(self, db_session):
        _add(db_session, "BAD", TODAY, 0)
        _add(db_session, "GOOD", TODAY, 30000)
        view = get_consensus_view(db_session, _TK, as_of=TODAY)
        assert view.count == 1
        assert view.median == pytest.approx(30000.0)

    def test_co_min_max_va_tuoi_bao_cao(self, db_session):
        _add(db_session, "A", TODAY - datetime.timedelta(days=3), 20000)
        _add(db_session, "B", TODAY - datetime.timedelta(days=30), 40000)
        view = get_consensus_view(db_session, _TK, as_of=TODAY)
        assert view.min == pytest.approx(20000.0)
        assert view.max == pytest.approx(40000.0)
        assert view.newest_age_days == 3
        assert view.stale is False

    def test_co_ma_qua_cu_thi_danh_dau_stale(self, db_session):
        _add(db_session, "A", TODAY - datetime.timedelta(days=150), 20000)
        view = get_consensus_view(db_session, _TK, as_of=TODAY, stale_after_days=120)
        assert view.stale is True


class TestTuongThichNguoc:
    def test_get_consensus_stats_cu_van_chay(self, db_session):
        """Contract cũ {median, mean, count} phải giữ nguyên cho code đang dùng."""
        from valuation.engine.consensus_helper import get_consensus_stats
        _add(db_session, "A", TODAY - datetime.timedelta(days=3), 20000)
        _add(db_session, "B", TODAY - datetime.timedelta(days=5), 40000)
        stats = get_consensus_stats(_TK, TODAY, db_session)
        assert set(stats) >= {"median", "mean", "count"}
        assert stats["median"] == pytest.approx(30000.0)
        assert stats["count"] == 2
