"""Test hàng rào chống hồi quy.

Test quan trọng nhất file này là `TestSuCoNganHangThang7` — tái hiện đúng sự cố
DECISIONS.md D20 (sửa undervaluation ngân hàng làm nhóm RI_PB nhảy từ -25% sang
+10.7% mà không ai phát hiện) và khẳng định hàng rào giờ BẮT được nó.

Test đó là bộ nhớ thể chế của dự án: nếu ai đó nới lỏng `max_method_shift` trong
tương lai, test này đỏ ngay.
"""
import datetime

import pytest

from valuation.calibration.compare import (
    FAIL,
    PASS,
    RULE_BAND_NET_LOSS,
    RULE_BELOW_PRICE,
    RULE_METHOD_SHIFT,
    RULE_NEW_ERRORS,
    compare_runs,
    render_diff_markdown,
)
from valuation.calibration.harness import CalibrationRun
from valuation.calibration.metrics import ERROR, Observation, aggregate, classify_band


def _obs(ticker, method, dev, dev_price=None, band=0.20, error=None):
    return Observation(
        ticker=ticker, method=method, dev_vs_consensus=dev, dev_vs_price=dev_price,
        band=band, band_status=(ERROR if error else classify_band(dev, band)),
        error=error,
    )


def _run(label, observations):
    obs = tuple(observations)
    return CalibrationRun(
        label=label, git_sha="deadbeef", as_of=datetime.date(2026, 8, 11),
        window_days=180, dedup_mode="latest_per_broker", weighting="none",
        engine_config={}, observations=obs, aggregates=aggregate(obs),
    )


class TestSuCoNganHangThang7:
    """Tái hiện D20: nhóm RI_PB dịch từ ~-25% sang +10.7% (35 điểm phần trăm).

    Đây chính là kịch bản hàng rào sinh ra để chặn. Tổng thể trông "khá hơn"
    (nhiều mã vào band hơn) nên các chỉ số tổng hợp KHÔNG báo động — chỉ có
    rule theo nhóm phương pháp mới bắt được.
    """

    def _fixture(self):
        # 15 ngân hàng: trước -25%, sau +10.7% (số thật đo được)
        before = [_obs(f"BANK{i}", "RI_PB", -0.25, -0.10) for i in range(15)]
        after = [_obs(f"BANK{i}", "RI_PB", 0.107, 0.30) for i in range(15)]
        return _run("truoc-D20", before), _run("sau-D20", after)

    def test_hang_rao_bat_duoc_su_co(self):
        baseline, candidate = self._fixture()
        diff = compare_runs(baseline, candidate)
        assert diff.verdict == FAIL, (
            "Hàng rào PHẢI chặn cú dịch 35pp của nhóm RI_PB — đây là sự cố D20"
        )
        assert any(RULE_METHOD_SHIFT in v for v in diff.violations)

    def test_chi_so_tong_the_KHONG_bao_dong_chung_minh_can_rule_theo_nhom(self):
        """|lệch| median đi từ 25% xuống 10.7% — nhìn tổng thể là 'tốt lên'.

        Nếu chỉ dựa vào chỉ số tổng thể thì sự cố lọt lưới. Test này chứng minh
        vì sao rule theo nhóm phương pháp là bắt buộc.
        """
        baseline, candidate = self._fixture()
        mad_before = baseline.aggregates["overall"]["median_abs_dev"]
        mad_after = candidate.aggregates["overall"]["median_abs_dev"]
        assert mad_after < mad_before  # "tốt lên" theo chỉ số tổng thể
        diff = compare_runs(baseline, candidate)
        # ... nhưng vẫn phải FAIL nhờ rule theo nhóm
        assert diff.verdict == FAIL

    def test_sua_dung_muc_thi_khong_bi_chan(self):
        """Sửa từ -25% về -8% (vào band, dịch 17pp) — vẫn quá ngưỡng 15pp.

        Chấp nhận: hàng rào thà báo động thừa còn hơn bỏ lọt; người sửa xem diff
        rồi quyết định. Nhưng sửa vừa phải -25% -> -12% (13pp) thì phải PASS.
        """
        baseline = _run("truoc", [_obs(f"B{i}", "RI_PB", -0.25, -0.10) for i in range(15)])
        candidate = _run("sau", [_obs(f"B{i}", "RI_PB", -0.12, 0.02) for i in range(15)])
        diff = compare_runs(baseline, candidate)
        assert diff.verdict == PASS
        assert diff.counts.get("ENTERED_BAND") == 15


class TestCacRuleKhac:
    def test_rule1_lo_moi_thi_fail(self):
        baseline = _run("a", [_obs("X", "DCF", -0.10)])
        candidate = _run("b", [_obs("X", "DCF", None, error="ValueError: hỏng")])
        diff = compare_runs(baseline, candidate)
        assert diff.verdict == FAIL
        assert any(RULE_NEW_ERRORS in v for v in diff.violations)
        assert diff.counts.get("NEW_ERROR") == 1

    def test_rule2_ra_khoi_band_nhieu_hon_vao_band(self):
        baseline = _run("a", [
            _obs("A", "DCF", 0.05), _obs("B", "DCF", 0.05), _obs("C", "DCF", -0.50),
        ])
        candidate = _run("b", [
            _obs("A", "DCF", 0.60), _obs("B", "DCF", 0.60), _obs("C", "DCF", -0.10),
        ])
        diff = compare_runs(baseline, candidate)
        assert diff.verdict == FAIL
        assert any(RULE_BAND_NET_LOSS in v for v in diff.violations)

    def test_rule5_fv_moi_tut_duoi_thi_gia(self):
        """Mã mới rơi xuống dưới thị giá >40% — dấu hiệu lỗi mô hình."""
        baseline = _run("a", [_obs("VIC", "SOTP", -0.10, -0.05)])
        candidate = _run("b", [_obs("VIC", "SOTP", -0.15, -0.92)])
        diff = compare_runs(baseline, candidate)
        assert diff.verdict == FAIL
        assert any(RULE_BELOW_PRICE in v for v in diff.violations)

    def test_khong_doi_gi_thi_pass(self):
        obs = [_obs("A", "DCF", -0.10, 0.05), _obs("B", "RI_PB", 0.05, 0.10)]
        diff = compare_runs(_run("a", obs), _run("b", obs))
        assert diff.verdict == PASS
        assert diff.violations == ()
        assert diff.counts.get("UNCHANGED") == 2

    def test_nhom_qua_it_ma_thi_bo_qua_rule_dich_chuyen(self):
        """n=2 < min_method_n=3 → biến động lớn vẫn không bị chặn (tránh nhiễu)."""
        baseline = _run("a", [_obs("A", "PB", -0.76), _obs("B", "PB", -0.70)])
        candidate = _run("b", [_obs("A", "PB", -0.10), _obs("B", "PB", -0.05)])
        diff = compare_runs(baseline, candidate)
        assert not any(RULE_METHOD_SHIFT in v for v in diff.violations)

    def test_dao_dong_nho_hon_tol_tinh_la_unchanged(self):
        baseline = _run("a", [_obs("A", "DCF", -0.100)])
        candidate = _run("b", [_obs("A", "DCF", -0.115)])   # lệch 1.5pp < tol 2pp
        diff = compare_runs(baseline, candidate)
        assert diff.counts.get("UNCHANGED") == 1

    def test_ma_moi_them_bot_khong_lam_no(self):
        baseline = _run("a", [_obs("A", "DCF", -0.10)])
        candidate = _run("b", [_obs("A", "DCF", -0.10), _obs("Z", "DCF", -0.05)])
        diff = compare_runs(baseline, candidate)
        assert diff.counts.get("ADDED") == 1


class TestRenderMarkdown:
    def test_sinh_duoc_bang_dan_vao_decisions(self):
        # A: OUT_LOW -> IN_BAND (ENTERED_BAND thắng IMPROVED vì band là đơn vị quản trị)
        # B: đã trong band, thu hẹp lệch -> IMPROVED
        baseline = _run("truoc", [_obs("A", "DCF", -0.30, -0.20), _obs("B", "DCF", -0.18, 0.0)])
        candidate = _run("sau", [_obs("A", "DCF", -0.05, 0.02), _obs("B", "DCF", -0.02, 0.0)])
        md = render_diff_markdown(compare_runs(baseline, candidate))
        assert "truoc" in md and "sau" in md
        assert "| Nhóm PP |" in md
        assert "DCF" in md
        assert "ENTERED_BAND" in md
        assert "IMPROVED" in md

    def test_liet_ke_vi_pham(self):
        baseline = _run("a", [_obs(f"B{i}", "RI_PB", -0.25) for i in range(15)])
        candidate = _run("b", [_obs(f"B{i}", "RI_PB", 0.107) for i in range(15)])
        md = render_diff_markdown(compare_runs(baseline, candidate))
        assert "Vi phạm hàng rào hồi quy" in md
        assert RULE_METHOD_SHIFT in md
