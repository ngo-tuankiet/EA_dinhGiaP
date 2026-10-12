"""Test chuẩn hoá tên CTCK (D24).

Trọng tâm: gộp đúng các cặp trùng đã xác minh, và KHÔNG gộp bừa những tên chưa
xác minh — gộp nhầm hai công ty khác nhau làm sai median đồng thuận mà không ai
nhìn thấy.
"""
import pytest

from valuation.ingest.broker_names import (
    broker_display_name,
    normalize_broker,
    unmatched_policy,
)


class TestGopCapTrungDaXacMinh:
    """Các cặp này quan sát được từ dữ liệu THẬT của cả 24hmoney và Simplize."""

    @pytest.mark.parametrize("a,b", [
        ("MIRAE", "MAS"),          # Mirae Asset
        ("VIETCAP", "VCSC"),       # Vietcap
        ("SSV", "SHINHAN"),        # Shinhan Securities Vietnam
        ("YSVN", "YUANTA"),        # Yuanta
        ("VDSC", "VDS"),           # Rong Viet
        ("AGR", "AGRISECO"),       # Agriseco
        ("SBSC", "SBBS"),          # Saigonbank Berjaya
        ("VIETINBANKSC", "CTS"),   # VietinBank Securities
    ])
    def test_hai_ten_ve_cung_mot_ma(self, a, b):
        code_a, ok_a = normalize_broker(a)
        code_b, ok_b = normalize_broker(b)
        assert ok_a and ok_b
        assert code_a == code_b, f"{a} và {b} phải gộp về cùng một CTCK"


class TestBayPhaiTranh:
    def test_HCM_khong_duoc_map_sang_HSC(self):
        """HCM vừa là MÃ CỔ PHIẾU VN100 (Chứng khoán TP.HCM) vừa là tên gọi tắt
        của HSC. Map bừa sẽ làm nhầm lẫn mọi chỗ đối chiếu ticker <-> broker.

        Nếu ai đó thêm 'HCM' vào aliases của HSC trong broker_aliases.yaml,
        test này đỏ ngay.
        """
        code, matched = normalize_broker("HCM")
        assert code != "HSC"
        assert matched is False

    def test_HSC_van_map_binh_thuong(self):
        code, matched = normalize_broker("HSC")
        assert (code, matched) == ("HSC", True)

    def test_ten_chua_xac_minh_giu_nguyen_khong_gop_bua(self):
        for raw in ("VPX", "ELDIAN", "CTCK_LA_HOAC"):
            code, matched = normalize_broker(raw)
            assert matched is False
            assert code, "phải giữ lại tên chứ không trả rỗng"

    def test_chinh_sach_unmatched_la_keep_raw(self):
        assert unmatched_policy() == "keep_raw"


class TestLamSachChuoi:
    def test_bo_ten_chuyen_vien_trong_ngoac(self):
        """Nguồn vnstock ghép tên chuyên viên: 'VCI (Nguyen Van A)'.
        Không bóc thì cùng một nhà bị tách thành nhiều 'CTCK' khác nhau."""
        assert normalize_broker("VCI (Nguyen Van A)")[0] == "VCI"
        assert normalize_broker("VCI (Tran Thi B)")[0] == "VCI"
        # Hai chuyên viên khác nhau -> cùng một mã
        assert normalize_broker("VCI (A)")[0] == normalize_broker("VCI (B)")[0]

    def test_khong_phan_biet_hoa_thuong_va_khoang_trang(self):
        assert normalize_broker("  mirae  ")[0] == "MIRAE"
        assert normalize_broker("Mirae Asset")[0] == "MIRAE"

    def test_bo_dau_tieng_viet(self):
        assert normalize_broker("Rồng Việt")[0] == "VDSC"

    def test_bo_hau_to_khong_phan_biet(self):
        assert normalize_broker("SSI Research")[0] == "SSI"
        assert normalize_broker("SSI SECURITIES")[0] == "SSI"

    def test_chuoi_rong_khong_lam_no(self):
        for raw in ("", "   ", None):
            code, matched = normalize_broker(raw)
            assert matched is False
            assert code == ""


class TestTenHienThi:
    def test_co_ten_day_du_cho_bao_cao(self):
        assert broker_display_name("MIRAE") == "Mirae Asset"
        assert broker_display_name("VIETCAP") == "Vietcap (VCSC)"

    def test_ma_la_thi_tra_lai_chinh_no(self):
        assert broker_display_name("VPX") == "VPX"


class TestOnDinh:
    def test_chuan_hoa_hai_lan_ra_cung_ket_qua(self):
        """normalize(normalize(x)) == normalize(x) — cần cho backfill idempotent."""
        for raw in ("MAS", "VCSC", "SSI Research", "VPX", "YSVN"):
            once = normalize_broker(raw)[0]
            twice = normalize_broker(once)[0]
            assert once == twice
