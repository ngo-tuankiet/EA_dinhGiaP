"""Test terminal ngân hàng (D29) + hợp nhất kịch bản (D30).

Test quan trọng nhất: `TestUocLuongROETheoXuHuong` — chặn đúng nguyên nhân gốc
của overshoot D20 (dùng TRUNG BÌNH toàn lịch sử gồm cả đỉnh chu kỳ làm ước lượng
"ROE bền vững").
"""
import statistics

import pytest

from valuation.config import load_defaults


class TestUocLuongROETheoXuHuong:
    """ACB thật: ROE 21%,23%,23%,20%,17%,16% — đang phai rõ rệt."""

    ACB_ROES = [0.21, 0.23, 0.23, 0.20, 0.17, 0.16]

    def test_trung_binh_toan_lich_su_thoi_phong_ROE(self):
        """Chứng minh cách cũ sai ở đâu: trung bình kéo ROE lên sát đỉnh chu kỳ."""
        cu = statistics.mean(self.ACB_ROES)
        moi = statistics.median(self.ACB_ROES[-3:])
        assert cu == pytest.approx(0.20, abs=0.005)
        assert moi == pytest.approx(0.17, abs=0.005)
        assert moi < cu - 0.02, "median 3 kỳ cuối phải thấp hơn hẳn trung bình toàn lịch sử"

    def test_chuoi_di_ngang_thi_hai_cach_gan_nhu_nhau(self):
        """Không có chu kỳ -> fix không gây tác dụng phụ."""
        roes = [0.15] * 6
        assert statistics.median(roes[-3:]) == pytest.approx(statistics.mean(roes))

    def test_cua_so_lay_tu_config(self):
        cfg = load_defaults().get("bank_terminal") or {}
        assert cfg.get("roe_window") == 3
        assert "terminal_roe_cap" in cfg


class TestBoHeThongTier:
    """D20 dùng ngưỡng 18% -> trần 20%/15%: chênh 0,2pp đầu vào tạo chênh 5pp đầu ra."""

    def test_khong_con_vach_dung_quanh_nguong_18_phan_tram(self):
        """Hai ngân hàng ROE 17,9% và 18,1% phải cho terminal ROE gần nhau."""
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        from tests.helpers_bank import build_fake_bank

        a = BankGeneralValuationModel(build_fake_bank(sustainable_roe=0.179)).terminal_roe
        b = BankGeneralValuationModel(build_fake_bank(sustainable_roe=0.181)).terminal_roe
        assert abs(a - b) < 0.01, (
            f"chênh 0,2pp đầu vào không được tạo vách đứng ở đầu ra ({a:.1%} vs {b:.1%})"
        )

    def test_van_con_tran_chong_ROE_phi_ly(self):
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        from tests.helpers_bank import build_fake_bank

        m = BankGeneralValuationModel(build_fake_bank(sustainable_roe=0.45))
        assert m.terminal_roe == pytest.approx(0.20)
        assert any("BANK_TERMINAL_ROE_CAPPED" in w for w in m.company.warnings)


class TestTranPB:
    def test_co_san_thi_phai_co_tran(self):
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        from tests.helpers_bank import build_fake_bank

        # ROE 20%, COE 8%, g 2% -> P/B lý thuyết = 0,18/0,06 = 3,0x (đúng trần)
        # Đẩy COE xuống 7% -> 0,18/0,05 = 3,6x > trần 3,0x
        m = BankGeneralValuationModel(build_fake_bank(sustainable_roe=0.20, coe=0.07))
        res = m.calculate_pb_valuation()
        assert res["target_pb"] == pytest.approx(3.0)
        assert any("BANK_PB_CLAMPED_HIGH" in w for w in m.company.warnings)

    def test_san_van_hoat_dong(self):
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        from tests.helpers_bank import build_fake_bank

        m = BankGeneralValuationModel(build_fake_bank(sustainable_roe=0.03, coe=0.13))
        res = m.calculate_pb_valuation()
        assert res["target_pb"] == pytest.approx(0.3)
        assert any("BANK_PB_CLAMPED_LOW" in w for w in m.company.warnings)


class TestNhatQuanTerminal:
    def test_chi_canh_bao_khi_trang_thai_dung_khong_ton_tai(self):
        """ROE <= g: phải phát hành vốn vĩnh viễn -> trạng thái dừng không tồn tại."""
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        from tests.helpers_bank import build_fake_bank

        m = BankGeneralValuationModel(build_fake_bank(sustainable_roe=0.015, coe=0.13, g=0.02))
        assert any("TERMINAL_IMPOSSIBLE" in w for w in m.company.warnings)

    def test_khong_canh_bao_o_truong_hop_binh_thuong(self):
        """Chênh payout dự phóng vs trạng thái dừng là BẢN CHẤT mô hình 2 giai đoạn.

        Bản đầu của D29 cảnh báo cả ca này và bắn ở 15/17 ngân hàng -> thành nhiễu.
        """
        from valuation.engine.models.bank_general import BankGeneralValuationModel
        from tests.helpers_bank import build_fake_bank

        m = BankGeneralValuationModel(build_fake_bank(sustainable_roe=0.16, coe=0.12, g=0.02))
        assert not any("TERMINAL_IMPOSSIBLE" in w for w in m.company.warnings)


class TestHopNhatKichBan:
    """D30: run_scenario_analysis phải uỷ quyền cho apply_scenario_adjustments."""

    def test_hai_duong_goi_cho_cung_ket_qua(self):
        from tests.helpers_bank import build_fake_bank
        from valuation.engine.blend import blend_intrinsic_relative
        from valuation.engine.router import ValuationRouter
        from valuation.engine.sensitivity import (
            apply_scenario_adjustments,
            run_scenario_analysis,
            run_valuation_engine,
        )

        company = build_fake_bank(sustainable_roe=0.16, coe=0.12, price=25000.0)
        w = ValuationRouter().get_routing(company.ticker).get("weight_primary", 1.0)
        direct = run_scenario_analysis(company)
        for scenario in ("Bull", "Base", "Bear"):
            comp = apply_scenario_adjustments(company, scenario)
            i, r = run_valuation_engine(comp)
            blended, _ = blend_intrinsic_relative(i, r, w, company.current_price)
            assert direct[scenario] == pytest.approx(round(blended, 0)), (
                f"{scenario}: hai đường gọi phải ra cùng số (D30)"
            )

    def test_kich_ban_bien_thien_ca_khoi_terminal(self):
        """Bản cũ chỉ nhiễu credit_growth/NIM -> dải Bull-Bear chỉ ±6%."""
        from tests.helpers_bank import build_fake_bank
        from valuation.engine.sensitivity import apply_scenario_adjustments

        company = build_fake_bank(sustainable_roe=0.16, coe=0.12)
        bull = apply_scenario_adjustments(company, "Bull")
        bear = apply_scenario_adjustments(company, "Bear")
        assert bull.assumptions.sustainable_roe > company.assumptions.sustainable_roe
        assert bear.assumptions.sustainable_roe < company.assumptions.sustainable_roe
        assert bull.assumptions.terminal_growth_rate > bear.assumptions.terminal_growth_rate

    def test_dai_kich_ban_du_rong_de_co_y_nghia(self):
        from tests.helpers_bank import build_fake_bank
        from valuation.engine.sensitivity import run_scenario_analysis

        company = build_fake_bank(sustainable_roe=0.16, coe=0.12, price=25000.0)
        s = run_scenario_analysis(company)
        spread = (s["Bull"] - s["Bear"]) / s["Base"]
        assert spread > 0.20, f"dải Bull-Bear quá hẹp ({spread:.0%}) — tạo cảm giác an toàn giả"

    def test_base_khong_bi_thay_doi(self):
        from tests.helpers_bank import build_fake_bank
        from valuation.engine.sensitivity import apply_scenario_adjustments

        company = build_fake_bank(sustainable_roe=0.16, coe=0.12)
        base = apply_scenario_adjustments(company, "Base")
        assert base.assumptions.sustainable_roe == company.assumptions.sustainable_roe
        assert base.assumptions.credit_growth == company.assumptions.credit_growth
