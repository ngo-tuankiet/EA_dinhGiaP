"""Test năm gốc dự phóng + ranh giới kiến trúc (D32/D33).

`TestRanhGioiKienTruc` là phần quan trọng nhất: biến lời hứa "engine KHÔNG BAO GIỜ
fit theo CTCK" (quyết định #2 của người dùng) thành thuộc tính KIỂM CHỨNG ĐƯỢC
bằng máy, thay vì trông chờ vào kỷ luật của người viết code.
"""
import ast
import pathlib

import pytest

from valuation.forecast.base_year import (
    build_forward_base,
    is_cyclical_sector,
    quarterly_momentum,
    revenue_growth_path,
)


class TestDongLuongTheoQuy:
    def test_tinh_tay(self):
        """4 quý gần nhất tổng 440 / 4 quý trước 400 -> +10%."""
        q = [90, 95, 105, 110, 100, 110, 110, 120]
        assert sum(q[-4:]) == 440 and sum(q[-8:-4]) == 400
        assert quarterly_momentum(q) == pytest.approx(0.10)

    def test_thieu_du_lieu_tra_None_khong_doan(self):
        assert quarterly_momentum([1, 2, 3]) is None
        assert quarterly_momentum([]) is None
        assert quarterly_momentum([100] * 7) is None, "cần đủ 8 quý"

    def test_mau_so_bang_khong_khong_lam_no(self):
        assert quarterly_momentum([0, 0, 0, 0, 10, 10, 10, 10]) is None


class TestCoNgot:
    """Co ngót về median lịch sử — chống động lượng nhiễu ở doanh nghiệp chu kỳ."""

    def test_ket_qua_nam_giua_dong_luong_va_median(self):
        q = [100] * 4 + [120] * 4          # động lượng = +20%
        fb = build_forward_base(q, trailing_median_growth=0.0, cfg={"momentum_weight": 0.5})
        # 0,5 × 20% + 0,5 × 0% = 10%, nằm trong band [−10%, +10%]
        assert fb.fy1_revenue_growth == pytest.approx(0.10)
        assert fb.method == "QUARTERLY_MOMENTUM"

    def test_trong_so_0_thi_bang_trailing(self):
        q = [100] * 4 + [200] * 4
        fb = build_forward_base(q, trailing_median_growth=0.08, cfg={"momentum_weight": 0.0})
        assert fb.fy1_revenue_growth == pytest.approx(0.08)


class TestKepAnToan:
    def test_kep_tran_so_voi_median_lich_su(self):
        q = [100] * 4 + [300] * 4          # động lượng +200%
        fb = build_forward_base(q, trailing_median_growth=0.05,
                                cfg={"momentum_weight": 1.0, "max_uplift_vs_trailing": 0.10})
        assert fb.fy1_revenue_growth == pytest.approx(0.15)   # 5% + 10%
        assert any("FWD_CLAMPED_HIGH" in f for f in fb.flags)

    def test_kep_san(self):
        q = [200] * 4 + [100] * 4          # động lượng −50%
        fb = build_forward_base(q, trailing_median_growth=0.12,
                                cfg={"momentum_weight": 1.0, "max_cut_vs_trailing": 0.10})
        assert fb.fy1_revenue_growth == pytest.approx(0.02)   # 12% − 10%
        assert any("FWD_CLAMPED_LOW" in f for f in fb.flags)

    def test_band_ngoai_cung_van_ap_dung(self):
        q = [100] * 4 + [400] * 4
        fb = build_forward_base(q, trailing_median_growth=0.30,
                                cfg={"momentum_weight": 1.0, "growth_cap": 0.25})
        assert fb.fy1_revenue_growth <= 0.25


class TestNganhChuKy:
    """Với ngành chu kỳ, động lượng SAI VỀ BẢN CHẤT — phải giữ mid-cycle."""

    @pytest.mark.parametrize("sector", ["Thép", "Dầu khí", "Hóa chất", "Cao su"])
    def test_bo_qua_dong_luong_cho_nganh_chu_ky(self, sector):
        q = [100] * 4 + [200] * 4
        fb = build_forward_base(q, trailing_median_growth=0.08, sector_group=sector)
        assert fb.fy1_revenue_growth == pytest.approx(0.08)
        assert fb.method == "TRAILING_MEDIAN"
        assert "FWD_SKIPPED_CYCLICAL" in fb.flags

    def test_nganh_thuong_van_dung_dong_luong(self):
        q = [100] * 4 + [120] * 4
        fb = build_forward_base(q, trailing_median_growth=0.05, sector_group="Công nghệ")
        assert fb.method == "QUARTERLY_MOMENTUM"

    def test_dinh_nghia_chu_ky_nhat_quan_voi_engine(self):
        """Cùng một định nghĩa 'chu kỳ' với `engine/batch.py` (ép mid-cycle)."""
        from valuation.forecast.base_year import CYCLICAL_KEYWORDS
        for kw in ("Thép", "Hóa chất", "Dầu khí", "Cao su", "Phân bón",
                   "Vận tải", "Khai khoáng"):
            assert kw in CYCLICAL_KEYWORDS
        assert is_cyclical_sector("Thép") and not is_cyclical_sector("Công nghệ")


class TestDuongFade:
    def test_giu_nguyen_dang_cong_thuc_cu(self):
        """Chỉ ĐIỂM XUẤT PHÁT đổi, hình dạng đường fade giữ nguyên -> cô lập tác động."""
        path = revenue_growth_path(0.20, 0.08, years=5)
        assert path[0] == pytest.approx(0.20)
        assert path[-1] == pytest.approx(0.08)
        # tuyến tính: mỗi bước giảm đều nhau
        deltas = [path[i + 1] - path[i] for i in range(4)]
        assert all(d == pytest.approx(deltas[0]) for d in deltas)


class TestCheDoMacDinh:
    def test_mac_dinh_la_TRAILING(self):
        """Mặc định phải là hành vi CŨ — bật FORWARD là quyết định có ý thức."""
        from valuation.forecast.base_year import base_year_mode
        assert base_year_mode() == "TRAILING"


class TestRanhGioiKienTruc:
    """Engine định giá KHÔNG ĐƯỢC BIẾT GÌ về dữ liệu CTCK (quyết định #2).

    Đây là cách biến lời hứa thành thuộc tính kiểm chứng được bằng máy: nếu ai đó
    (kể cả vô tình) import consensus vào engine để 'cho khớp CTCK hơn', test đỏ.
    """

    FORBIDDEN = ("consensus_helper", "consensus_view", "consensus_extract",
                 "consensus_synthesis", "consensus_text", "calibration")
    GUARDED_PATHS = (
        "valuation/engine/models",
        "valuation/data_access/repo.py",
        "valuation/engine/forecast.py",
        "valuation/engine/forecast_bank.py",
        "valuation/forecast",
    )

    def _files(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        for rel in self.GUARDED_PATHS:
            p = root / rel
            if p.is_file():
                yield p
            elif p.is_dir():
                yield from (f for f in p.rglob("*.py") if "__pycache__" not in str(f))

    def test_engine_khong_import_du_lieu_CTCK(self):
        viphams = []
        for f in self._files():
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                for m in mods:
                    if any(bad in m for bad in self.FORBIDDEN):
                        viphams.append(f"{f.name}:{node.lineno} import {m}")
        assert not viphams, (
            "Engine định giá KHÔNG được import dữ liệu đồng thuận CTCK — dữ liệu đó "
            "chỉ để ĐO, không bao giờ là input định giá (quyết định #2):\n  "
            + "\n  ".join(viphams)
        )

    def test_engine_khong_dung_bang_Consensus(self):
        viphams = []
        for f in self._files():
            src = f.read_text(encoding="utf-8")
            for name in ("ConsensusReportText", "ConsensusSynthesis"):
                if name in src:
                    viphams.append(f"{f.name}: dùng {name}")
            # `Consensus` đứng riêng (không phải tiền tố của tên dài hơn)
            for line in src.splitlines():
                s = line.strip()
                if s.startswith("#"):
                    continue
                if "import" in s and "Consensus," in s.replace(" ", "") + ",":
                    viphams.append(f"{f.name}: import Consensus")
        assert not viphams, "\n".join(viphams)
