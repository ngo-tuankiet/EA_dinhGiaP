"""Test bóc tách luận điểm CTCK (D31).

Fixture là văn bản THẬT lấy từ 24hmoney (2026-08-11), không phải câu tự bịa —
để test bám đúng cách CTCK Việt Nam thật sự viết.

Test quan trọng nhất: `TestUuTienDuPhong` — một tóm tắt thường nêu CẢ kết quả quý
vừa công bố LẪN dự phóng cả năm; lấy nhầm con số quý làm dự phóng sẽ sai hoàn
toàn về ý nghĩa.
"""
import pytest

from valuation.engine.consensus_extract import EXTRACT_VERSION, extract_thesis

# --- Văn bản thật, giữ nguyên (rút gọn phần đuôi) ---
NHSV_ACB = (
    "NHSV cập nhật kết quả kinh doanh Q2/2026 của ACB với lợi nhuận sau thuế đạt "
    "4.292 tỷ đồng (-12,1% YoY). Dự phóng cả năm 2026 LNST đạt 17.207 tỷ đồng "
    "(+10,1% YoY) với giá mục tiêu là 27.000 đồng/cổ phiếu. Upside tương ứng đạt "
    "20,0%. P/B dự phóng cho năm 2026 đạt 1,1x."
)
MIRAE_FPT = (
    "Mirae Asset khuyến nghị MUA đối với FPT với giá mục tiêu là 78.000 đồng. "
    "Upside dự kiến là 23,8%. Dự phóng năm 2026 doanh thu thuần đạt 57.588 tỷ đồng "
    "và LNST-CĐTS đạt 10.136 tỷ đồng (+8,1% YoY). P/E dự phóng 2026 đạt 10,7x và "
    "ROE dự kiến đạt 20,8%."
)
VIX_ACB = (
    "VIX Research duy trì đánh giá TÍCH CỰC cho mã ACB với giá mục tiêu 28.000 đồng. "
    "Upside kỳ vọng đạt 25%. Lợi nhuận sau thuế năm 2026 dự báo đạt 16.196 tỷ đồng "
    "(+3,65% YoY). Ngân hàng hiện giao dịch tại mức P/B 1,31x và P/E 7,85x."
)


class TestUuTienDuPhong:
    """Không được lấy nhầm kết quả quý làm dự phóng cả năm."""

    def test_lay_dung_LNST_du_phong_khong_phai_loi_nhuan_quy(self):
        e = extract_thesis(NHSV_ACB)
        assert e.forecast_net_income_ty == pytest.approx(17207.0), (
            "phải lấy 17.207 (dự phóng cả năm), không phải 4.292 (LNST quý 2)"
        )

    def test_lay_dung_tang_truong_du_phong(self):
        e = extract_thesis(NHSV_ACB)
        assert e.forecast_growth == pytest.approx(0.101, abs=1e-6), (
            "phải lấy +10,1% (dự phóng), không phải -12,1% (YoY quý 2)"
        )

    def test_danh_dau_khi_khong_ro_du_phong_hay_da_cong_bo(self):
        txt = "Doanh nghiệp ghi nhận LNST Q2 đạt 500 tỷ đồng."
        e = extract_thesis(txt)
        assert e.forecast_net_income_ty == pytest.approx(500.0)
        assert any("KHÔNG RÕ" in s for s in e.matched_spans)


class TestBocSoLieu:
    def test_so_kieu_viet_nam(self):
        """'17.207' = mười bảy nghìn (chấm ngăn nghìn); '10,1' = mười phẩy một."""
        e = extract_thesis(NHSV_ACB)
        assert e.target_price == pytest.approx(27000.0)
        assert e.target_pb == pytest.approx(1.1)
        assert e.upside == pytest.approx(0.20)

    def test_boi_so_va_ty_suat(self):
        e = extract_thesis(MIRAE_FPT)
        assert e.target_pe == pytest.approx(10.7)
        assert e.forecast_roe == pytest.approx(0.208)
        assert e.forecast_revenue_ty == pytest.approx(57588.0)
        assert e.forecast_net_income_ty == pytest.approx(10136.0)

    def test_bat_duoc_ca_PB_va_PE_trong_cung_doan(self):
        e = extract_thesis(VIX_ACB)
        assert e.target_pb == pytest.approx(1.31)
        assert e.target_pe == pytest.approx(7.85)

    def test_nam_du_phong(self):
        assert 2026 in extract_thesis(MIRAE_FPT).forecast_years


class TestKhongBiaSo:
    """Quy tắc vàng: thiếu dữ liệu -> None, TUYỆT ĐỐI không phải 0."""

    def test_van_ban_rong(self):
        e = extract_thesis("")
        assert e.target_pb is None and e.target_pe is None
        assert e.forecast_net_income_ty is None
        assert e.confidence == 0.0

    def test_van_ban_thuan_dinh_tinh(self):
        e = extract_thesis("Chúng tôi đánh giá tích cực triển vọng dài hạn của doanh nghiệp.")
        assert e.target_pb is None
        assert e.forecast_roe is None
        assert e.confidence == 0.0
        assert e.matched_spans == ()

    def test_thieu_truong_khong_bien_thanh_khong(self):
        e = extract_thesis("Giá mục tiêu 50.000 đồng.")
        assert e.target_price == pytest.approx(50000.0)
        assert e.target_pb is None, "thiếu P/B phải là None, không phải 0.0"
        assert e.wacc is None


class TestTruyVet:
    def test_luu_nguyen_van_doan_khop_de_doi_chieu(self):
        e = extract_thesis(NHSV_ACB)
        assert e.matched_spans, "phải giữ nguyên văn để người đọc truy được nguồn"
        assert any("17.207" in s for s in e.matched_spans)

    def test_co_version_de_biet_khi_nao_can_boc_lai(self):
        assert extract_thesis(NHSV_ACB).to_dict()["extract_version"] == EXTRACT_VERSION

    def test_tat_dinh_chay_hai_lan_ra_cung_ket_qua(self):
        a, b = extract_thesis(MIRAE_FPT), extract_thesis(MIRAE_FPT)
        assert a == b, "regex phải tất định — đó là lý do không dùng LLM"


class TestPhuongPhap:
    @pytest.mark.parametrize("text,expect", [
        ("Chúng tôi dùng phương pháp chiết khấu dòng tiền FCFF.", "DCF"),
        ("Định giá theo thu nhập thặng dư kết hợp P/B.", "RI"),
        ("Áp dụng RNAV cho quỹ đất.", "RNAV"),
        ("Định giá SOTP từng mảng.", "SOTP"),
    ])
    def test_nhan_dien_tu_khoa_phuong_phap(self, text, expect):
        assert expect in extract_thesis(text).methods

    def test_khong_co_tu_khoa_thi_rong(self):
        assert extract_thesis("Doanh nghiệp có nền tảng tốt.").methods == ()


class TestConfidence:
    def test_confidence_phan_anh_ty_le_boc_duoc(self):
        rich = extract_thesis(MIRAE_FPT).confidence
        poor = extract_thesis("Đánh giá tích cực.").confidence
        assert rich > poor
        assert 0.0 <= rich <= 1.0 and poor == 0.0
