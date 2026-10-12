"""Test sổ đăng ký hiệu chuẩn (D25).

Registry là chỗ hiện thực hoá quyết định #1: lệch khỏi CTCK thì phải giải trình
được. Test ở đây bảo đảm không ai có thể "giải trình" bằng một dòng rỗng.
"""
import datetime

import pytest
import yaml

from valuation.calibration.registry import (
    GOV_DATA_BLOCKED,
    GOV_KNOWN_DEFECT,
    GOV_MISSING,
    GOV_OBSOLETE,
    GOV_OK,
    GOV_OK_JUSTIFIED,
    GOV_STALE,
    RegistryError,
    band_for,
    govern,
    load_registry,
)
from valuation.config import PROJECT_ROOT

_REGISTRY_PATH = PROJECT_ROOT / "config" / "calibration_registry.yaml"
TODAY = datetime.date(2026, 8, 11)


@pytest.fixture(scope="module")
def registry():
    return load_registry()


class TestBangGovernance:
    """Bảng chân trị của govern() — xem docstring registry.py."""

    def test_trong_band_khong_can_gi(self, registry):
        assert govern("FPT", "IN_BAND", registry, TODAY)[0] == GOV_OK

    def test_ngoai_band_khong_khai_bao_thi_phai_xu_ly(self, registry):
        assert govern("KHONGCOTRONGREGISTRY", "OUT_LOW", registry, TODAY)[0] == GOV_MISSING

    def test_ngoai_band_co_luan_diem_con_han(self, registry):
        assert govern("SSI", "OUT_LOW", registry, TODAY)[0] == GOV_OK_JUSTIFIED

    def test_luan_diem_het_han_thi_phai_ra_soat_lai(self, registry):
        """Giải trình CÓ HẠN — không miễn nhiễm vĩnh viễn."""
        muon = TODAY + datetime.timedelta(days=200)   # TTL 180 ngày
        assert govern("SSI", "OUT_LOW", registry, muon)[0] == GOV_STALE

    def test_loi_da_thua_nhan_la_backlog(self, registry):
        # MBB còn trong backlog sau D29 (ACB/VIB/OCB/BID đã vào band và được gỡ).
        assert govern("MBB", "OUT_HIGH", registry, TODAY)[0] == GOV_KNOWN_DEFECT

    def test_thieu_du_lieu_khong_phai_loi_mo_hinh(self, registry):
        assert govern("NVL", "OUT_HIGH", registry, TODAY)[0] == GOV_DATA_BLOCKED

    def test_vao_band_roi_ma_con_khai_bao_thi_bao_don_registry(self, registry):
        """Chống registry mục nát: mã đã vào band mà vẫn còn entry -> nhắc xoá."""
        assert govern("MBB", "IN_BAND", registry, TODAY)[0] == GOV_OBSOLETE

    def test_khong_do_duoc_thi_khong_phan_xet(self, registry):
        for bs in ("NO_CONSENSUS", "ERROR"):
            assert govern("MBB", bs, registry, TODAY)[0] == GOV_OK


class TestBand:
    def test_proxy_duoc_noi_band(self, registry):
        assert band_for("MSN", "SOTP", registry) == pytest.approx(0.35)
        assert band_for("BCM", "RNAV", registry) == pytest.approx(0.30)

    def test_phuong_phap_khac_dung_band_mac_dinh(self, registry):
        assert band_for("FPT", "DCF", registry) == pytest.approx(0.20)
        assert band_for("ACB", "RI_PB", registry) == pytest.approx(0.20)

    def test_band_rieng_cua_ma_thang_band_theo_phuong_phap(self, tmp_path):
        p = tmp_path / "r.yaml"
        p.write_text(yaml.safe_dump({
            "default_band": 0.20,
            "bands_by_method": {"SOTP": 0.35},
            "tickers": {"XYZ": {"status": "out_of_band_must_fix", "band": 0.5}},
        }), encoding="utf-8")
        reg = load_registry(p)
        assert band_for("XYZ", "SOTP", reg) == pytest.approx(0.5)


class TestXacThucCauTruc:
    """Không cho phép 'giải trình' bằng nội dung rỗng."""

    def _write(self, tmp_path, entry):
        p = tmp_path / "r.yaml"
        p.write_text(yaml.safe_dump({"tickers": {"XYZ": entry}}), encoding="utf-8")
        return p

    def test_justified_bat_buoc_co_thesis(self, tmp_path):
        p = self._write(tmp_path, {"status": "out_of_band_justified",
                                   "evidence": ["x"], "reviewed_on": "2026-08-11"})
        with pytest.raises(RegistryError, match="thesis"):
            load_registry(p)

    def test_justified_bat_buoc_co_evidence(self, tmp_path):
        p = self._write(tmp_path, {"status": "out_of_band_justified",
                                   "thesis": "vì abc", "reviewed_on": "2026-08-11"})
        with pytest.raises(RegistryError, match="evidence"):
            load_registry(p)

    def test_justified_bat_buoc_co_ngay_ra_soat(self, tmp_path):
        p = self._write(tmp_path, {"status": "out_of_band_justified",
                                   "thesis": "vì abc", "evidence": ["x"]})
        with pytest.raises(RegistryError, match="reviewed_on"):
            load_registry(p)

    def test_status_la_bi_tu_choi(self, tmp_path):
        p = self._write(tmp_path, {"status": "co_le_on_ap"})
        with pytest.raises(RegistryError, match="không hợp lệ"):
            load_registry(p)

    def test_must_fix_khong_can_luan_diem(self, tmp_path):
        """must_fix là THỪA NHẬN LỖI, không phải bảo vệ quan điểm."""
        p = self._write(tmp_path, {"status": "out_of_band_must_fix"})
        reg = load_registry(p)
        assert reg["XYZ"].status == "out_of_band_must_fix"

    def test_khong_co_file_thi_tra_rong_chu_khong_no(self, tmp_path):
        assert load_registry(tmp_path / "khong-ton-tai.yaml") == {}


class TestRegistryThatCuaDuAn:
    def test_file_that_doc_duoc_va_hop_le(self, registry):
        assert len(registry) > 0
        assert _REGISTRY_PATH.exists()

    def test_moi_ma_khai_bao_deu_nam_trong_VN100(self, registry):
        """Gõ nhầm mã sẽ tạo ra một entry không bao giờ khớp -> im lặng vô dụng."""
        from valuation.engine.sector_router import _router
        vn100 = set(_router().routing_data.keys())
        for tk in registry:
            assert tk in vn100, f"{tk} không có trong routing.json"

    def test_ngay_ra_soat_khong_o_tuong_lai(self, registry):
        today = datetime.date.today()
        for tk, e in registry.items():
            if e.reviewed_on:
                assert e.reviewed_on <= today, f"{tk}: reviewed_on ở tương lai"

    def test_ma_justified_deu_co_du_luan_diem_va_bang_chung(self, registry):
        for tk, e in registry.items():
            if e.status == "out_of_band_justified":
                assert e.thesis.strip(), f"{tk}: thesis rỗng"
                assert e.evidence, f"{tk}: thiếu evidence"


class TestRatchet:
    """Cưỡng chế quy ước band bằng máy — quyết định #1 của người dùng.

    Hiện còn ~38 mã MISSING_JUSTIFICATION (chủ yếu nhóm DCF, sẽ xử lý một thể ở
    GĐ7). Test này khai báo NGƯỠNG TRẦN và siết dần: mỗi giai đoạn giảm được số
    mã chưa giải trình thì hạ ngưỡng xuống, không cho phép tăng trở lại.
    """

    MAX_MISSING = 40   # hạ dần sau mỗi giai đoạn; KHÔNG được nâng lên

    def test_so_ma_chua_giai_trinh_khong_duoc_tang(self, registry):
        from valuation.calibration.harness import load_run
        from valuation.db.session import SessionLocalRead

        db = SessionLocalRead()
        try:
            run = load_run(db)   # lần chạy mới nhất
        finally:
            db.close()
        if run is None:
            pytest.skip("chưa có lần chạy hiệu chuẩn nào trong DB")

        missing = [o.ticker for o in run.observations
                   if o.governance_status == GOV_MISSING]
        assert len(missing) <= self.MAX_MISSING, (
            f"{len(missing)} mã ngoài band chưa giải trình (trần {self.MAX_MISSING}). "
            f"Hoặc khai báo vào config/calibration_registry.yaml, hoặc sửa mô hình. "
            f"Ví dụ: {sorted(missing)[:10]}"
        )
