"""Golden test cho model chứng khoán + bảo hiểm (D26/D27).

AGENTS.md luật vàng #8: module định giá chưa có golden test đối chiếu tính tay
= module chưa xong. Mọi trị số kỳ vọng dưới đây tính tay được, có ghi phép tính.

Test QUAN TRỌNG NHẤT: `TestSuaLoiLechTuMauSo` — tái hiện đúng bug đã làm nhóm CK
lệch -76% và chứng minh công thức mới sửa được.
"""
import pytest

from valuation.engine.models.insurance import InsuranceValuationModel
from valuation.engine.models.securities import (
    SecuritiesValuationModel,
    roe_path_from_history,
)


class TestSuaLoiLechTuMauSo:
    """Bug gốc: median(LNST 3 kỳ) / VCSH MỚI NHẤT.

    Tử số là lợi nhuận TRƯỚC tăng vốn, mẫu số là vốn SAU tăng vốn → ROE bị bóp
    xuống máy móc với mọi công ty vừa phát hành thêm. VCI là ca thật: VCSH
    3.643 -> 17.138 tỷ (gấp 4,7 lần) trong khi lợi nhuận đi ngang.
    """

    def test_roe_tinh_tren_vcsh_cung_ky(self):
        # VCSH gấp đôi ở kỳ cuối (tăng vốn), lợi nhuận tăng nhẹ.
        ni = [100.0, 120.0, 130.0]
        eq = [1000.0, 1000.0, 2000.0]

        roes = roe_path_from_history(ni, eq)
        # Tính tay:
        #   kỳ 1: 120 / ((1000+1000)/2) = 120/1000 = 12,0%
        #   kỳ 2: 130 / ((2000+1000)/2) = 130/1500 =  8,667%
        assert len(roes) == 2
        assert roes[0] == pytest.approx(0.12, abs=1e-6)
        assert roes[1] == pytest.approx(0.0866667, abs=1e-6)

    def test_cong_thuc_moi_cao_hon_cong_thuc_cu_khi_vua_tang_von(self):
        import statistics
        ni = [100.0, 120.0, 130.0]
        eq = [1000.0, 1000.0, 2000.0]

        cu = statistics.median(ni) / eq[-1]                    # 120/2000 = 6,0%
        moi = statistics.median(roe_path_from_history(ni, eq))  # median(12%, 8,67%) = 10,33%

        assert cu == pytest.approx(0.060, abs=1e-6)
        assert moi == pytest.approx(0.1033333, abs=1e-6)
        assert moi > cu, "công thức mới phải sửa được thiên lệch xuống sau tăng vốn"

    def test_vcsh_khong_doi_thi_hai_cong_thuc_trung_nhau(self):
        """Không tăng vốn -> fix này không làm đổi kết quả (không tác dụng phụ)."""
        import statistics
        ni = [100.0, 100.0, 100.0]
        eq = [1000.0, 1000.0, 1000.0]
        cu = statistics.median(ni) / eq[-1]
        moi = statistics.median(roe_path_from_history(ni, eq))
        assert moi == pytest.approx(cu, abs=1e-9)

    def test_chuoi_qua_ngan_khong_lam_no(self):
        assert roe_path_from_history([], []) == []
        assert roe_path_from_history([100.0], [1000.0]) == [pytest.approx(0.1)]


def _sec_model(ni, eq, coe=0.15, g=0.02, book0=None, **over):
    cf = {
        "total_equity": (book0 if book0 is not None else (eq[-1] if eq else 0.0)) * 1e9,
        "net_income_history": ni,
        "equity_history": eq,
        "shares_outstanding": 100e6,     # 100 triệu cp
        "current_price": 10000.0,
    }
    a = {"cost_of_equity": coe, "long_term_growth": g, "risk_free_rate": 0.20,
         "norm_years_recent": 3, "capital_deployment_years": 3,
         "terminal_roe_floor": 0.05, "terminal_roe_cap": 0.20,
         "payout_ratio": 0.20, "weight_ri": 0.5, "forecast_years": 5, **over}
    return SecuritiesValuationModel("TEST", cf, a)


class TestGoldenChungKhoan:
    """ROE phẳng 12%, COE 15%, g 2% — mọi số tính tay được."""

    def _flat(self):
        # VCSH không đổi 1.000 tỷ; ROE mỗi kỳ = 12%
        return _sec_model(ni=[120.0, 120.0, 120.0, 120.0], eq=[1000.0] * 4)

    def test_terminal_roe_bang_mid_cycle(self):
        drv = self._flat().forecast_drivers()
        assert drv["roe_now"] == pytest.approx(0.12, abs=1e-9)
        assert drv["roe_midcycle"] == pytest.approx(0.12, abs=1e-9)
        assert drv["terminal_roe"] == pytest.approx(0.12, abs=1e-9)

    def test_justified_pb_tinh_tay(self):
        """P/B = (ROE - g)/(COE - g) = (0,12-0,02)/(0,15-0,02) = 0,10/0,13 = 0,76923"""
        res = self._flat().perform_valuation()
        assert res["justified_pb"] == pytest.approx(0.769231, abs=1e-5)
        # FVPS chân P/B = P/B × VCSH / số cp = 0,769231 × 1.000e9 / 100e6 = 7.692,31 đ
        assert res["pb_fvps"] == pytest.approx(7692.31, rel=1e-4)

    def test_vcsh_cuon_chieu_dung_ty_le_giu_lai(self):
        """Năm 1: VCSH 1.000, LNST 120, payout 20% -> VCSH năm 2 = 1.000 + 96 = 1.096 tỷ"""
        f = self._flat().forecast_drivers()["forecasts"]
        assert f[0]["book_value_start"] == pytest.approx(1000e9)
        assert f[0]["net_income"] == pytest.approx(120e9)
        assert f[1]["book_value_start"] == pytest.approx(1096e9, rel=1e-9)

    def test_roe_duoi_coe_thi_ri_am_va_co_co_bao(self):
        """ROE 12% < COE 15% -> công ty chưa tạo thêm giá trị -> P/B < 1, phải báo."""
        res = self._flat().perform_valuation()
        assert res["justified_pb"] < 1.0
        assert any("SEC_ROE_BELOW_COE" in f for f in res["flags"])

    def test_fade_tu_roe_hien_tai_ve_mid_cycle(self):
        """ROE gần đây thấp (tăng vốn) nhưng mid-cycle cao -> phải fade LÊN dần."""
        # Kỳ đầu ROE cao, 3 kỳ cuối thấp do VCSH phình.
        ni = [200.0, 200.0, 200.0, 120.0, 120.0, 120.0]
        eq = [1000.0, 1000.0, 1000.0, 2000.0, 2000.0, 2000.0]
        drv = _sec_model(ni, eq).forecast_drivers()
        assert drv["roe_now"] < drv["roe_midcycle"], "gần đây phải thấp hơn mid-cycle"
        roes = [f["roe"] for f in drv["forecasts"]]
        assert roes[0] < roes[1] < roes[2], "ROE phải tăng dần trong kỳ giải ngân vốn"
        assert roes[2] == pytest.approx(drv["terminal_roe"], abs=1e-9)
        assert roes[3] == pytest.approx(drv["terminal_roe"], abs=1e-9)

    def test_terminal_roe_bi_kep_thi_len_tieng(self):
        # ROE 40% -> vượt trần 20%
        m = _sec_model(ni=[400.0] * 4, eq=[1000.0] * 4)
        drv = m.forecast_drivers()
        assert drv["terminal_roe"] == pytest.approx(0.20)
        assert any("SEC_TERMINAL_ROE_CLAMPED" in f for f in drv["flags"])

    def test_thieu_du_lieu_thi_khong_bia_so(self):
        """Có VCSH nhưng không có lịch sử lợi nhuận -> từ chối, không đoán ROE."""
        m = _sec_model(ni=[], eq=[], book0=1000.0)
        res = m.perform_valuation()
        assert res["blended_fair_value_per_share"] == 0.0
        assert "NO_SEC_DATA" in res["flags"]

    def test_duong_legacy_van_chay_khi_analyst_nhap_driver(self):
        """API cũ truyền driver doanh thu môi giới -> phải còn hoạt động."""
        cf = {"total_equity": 22e12, "shares_outstanding": 1.5e9, "current_price": 35000}
        a = {"cost_of_equity": 0.12, "long_term_growth": 0.04,
             "market_liquidity_vnd_billion": 18000.0, "brokerage_market_share": 0.095,
             "brokerage_margin": 0.0015, "margin_loans": 16000.0,
             "net_margin_rate": 0.055, "prop_trading_income": 1800.0,
             "opex_ratio": 0.35, "tax_rate": 0.20, "payout_ratio": 0.20, "weight_ri": 0.5}
        res = SecuritiesValuationModel("SSI", cf, a).perform_valuation()
        assert res["blended_fair_value_per_share"] > 0
        assert any("SEC_LEGACY_DRIVER_MODE" in f for f in res["flags"])


def _ins_model(ni, eq, coe=0.13, g=0.02, **over):
    cf = {
        "total_equity": eq[-1] * 1e9,
        "net_income_history": ni,
        "equity_history": eq,
        "shares_outstanding": 100e6,
        "current_price": 10000.0,
    }
    a = {"cost_of_equity": coe, "long_term_growth": g, "risk_free_rate": 0.20,
         "norm_years": 5, "roe_sanity_min": 0.0, "roe_sanity_max": 0.30,
         "terminal_roe_floor": 0.04, "terminal_roe_cap": 0.16,
         "payout_ratio": 0.30, "weight_ri": 0.5, "forecast_years": 5, **over}
    return InsuranceValuationModel("TESTINS", cf, a)


class TestGoldenBaoHiem:
    def test_justified_pb_tinh_tay(self):
        """ROE 10%, COE 13%, g 2% -> P/B = (0,10-0,02)/(0,13-0,02) = 0,08/0,11 = 0,72727"""
        res = _ins_model(ni=[100.0] * 6, eq=[1000.0] * 6).perform_valuation()
        assert res["terminal_roe"] == pytest.approx(0.10, abs=1e-9)
        assert res["justified_pb"] == pytest.approx(0.727273, abs=1e-5)
        assert res["pb_fvps"] == pytest.approx(7272.73, rel=1e-4)

    def test_cua_so_chuan_hoa_dai_hon_chung_khoan(self):
        """Bảo hiểm dùng 5 kỳ (chu kỳ lãi suất) thay vì 3 kỳ như CK."""
        assert _ins_model([100.0] * 6, [1000.0] * 6).assumptions["norm_years"] == 5

    def test_roe_phi_ly_thi_tu_choi_dinh_gia_chu_khong_kep(self):
        """Lợi nhuận bị map nhầm từ doanh thu phí -> ROE vọt -> NOT_RATED.

        Đây là điểm khác then chốt so với pb_relative cũ: model cũ kẹp về 4,0x
        rồi trình bày như một định giá bình thường, giấu mất lỗi dữ liệu.
        """
        # ROE = 500/1000 = 50% > trần sanity 30%
        res = _ins_model(ni=[500.0] * 6, eq=[1000.0] * 6).perform_valuation()
        assert res.get("not_rated") is True
        assert res["blended_fair_value_per_share"] == 0.0
        assert any("NI_MAPPING_UNVERIFIED" in f for f in res["flags"])

    def test_roe_hop_ly_thi_dinh_gia_binh_thuong(self):
        res = _ins_model(ni=[110.0] * 6, eq=[1000.0] * 6).perform_valuation()
        assert not res.get("not_rated")
        assert res["blended_fair_value_per_share"] > 0


class TestGuardrail:
    def test_canh_bao_fv_thap_hon_thi_gia(self):
        from valuation.engine.guardrails import check_fv_vs_price
        # VIC thật: FV 16.911 vs thị giá 208.500 -> -91,9%
        assert any("FV_FAR_BELOW_PRICE" in f for f in check_fv_vs_price(16911, 208500))
        # Lệch nhẹ thì không báo
        assert check_fv_vs_price(95000, 100000) == []

    def test_canh_bao_pb_lech_xa_thi_truong(self):
        from valuation.engine.guardrails import check_implied_pb
        # Mô hình 0,5x trong khi thị trường trả 1,5x
        assert any("FAR_BELOW_MARKET" in f for f in check_implied_pb(0.5, 1.5))
        assert any("FAR_ABOVE_MARKET" in f for f in check_implied_pb(3.0, 1.2))
        assert check_implied_pb(1.4, 1.5) == []

    def test_thieu_du_lieu_thi_im_lang(self):
        from valuation.engine.guardrails import check_fv_vs_price, check_implied_pb
        assert check_fv_vs_price(None, 100) == []
        assert check_fv_vs_price(100, 0) == []
        assert check_implied_pb(1.0, None) == []


class TestDispatchTheoNganh:
    """Routing gộp CK và bảo hiểm chung `primary: P/B` — dispatch phải tách đúng."""

    @pytest.mark.parametrize("ticker,expect", [
        ("SSI", "SecuritiesValuationModel"), ("VCI", "SecuritiesValuationModel"),
        ("BVH", "InsuranceValuationModel"), ("MIG", "InsuranceValuationModel"),
    ])
    def test_dung_model_cho_dung_nganh(self, ticker, expect):
        from valuation.data_access.repo import build_company_data
        from valuation.db.session import SessionLocalRead
        from valuation.engine.batch import _dispatch_nonfin
        from valuation.engine.sector_router import route

        db = SessionLocalRead()
        try:
            plan = route(ticker)
            company = build_company_data(db, ticker, mode="TTM", fetch_live=False)
            model, _ = _dispatch_nonfin(company, plan["method"], plan["group"])
        finally:
            db.close()
        assert type(model).__name__ == expect
