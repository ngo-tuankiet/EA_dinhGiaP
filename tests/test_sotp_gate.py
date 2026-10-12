"""Test cổng chặn NOT_RATED cho proxy SOTP (D28).

Khiếm khuyết được sửa: proxy sổ sách/lợi nhuận đưa ra MỘT CON SỐ ĐẦY TỰ TIN cho
tập đoàn đa ngành mà nó không mô tả được — VIC ra 16.911đ trong khi thị giá
208.500đ (-92%), và hệ thống vẫn phát khuyến nghị bán như bình thường.
"""
import pytest

from valuation.engine.decision_engine import InvestmentDecisionMaker
from valuation.engine.models.sotp import SOTPValuationModel
from valuation.models.financials import GovernanceData


def _sotp(net_income_ty, equity_ty, shares, price, **over):
    cf = {
        "total_equity": equity_ty * 1e9,
        "cash_and_equivalents": 0.0,
        "total_debt": 0.0,
        "minority_interest": 0.0,
        "net_income_history": net_income_ty,
        "shares_outstanding": shares,
        "current_price": price,
    }
    a = {"sotp_operating_pe": 11.0, "sotp_earnings_weight": 0.6,
         "sotp_holding_discount": 0.10, "sotp_segments": [], **over}
    return SOTPValuationModel("TESTSOTP", cf, a)


class TestCongChanProxy:
    def test_proxy_lech_qua_xa_thi_NOT_RATED(self):
        """Tái hiện ca VIC: proxy ra ~17k trong khi thị giá ~208k."""
        m = _sotp(net_income_ty=[1000.0] * 3, equity_ty=100_000.0,
                  shares=3_800_000_000, price=208_500.0)
        res = m.perform_valuation()
        assert res["not_rated"] is True
        assert any("PROXY_IMPLAUSIBLE" in f for f in res["flags"])
        assert "NOT_RATED" in res["flags"]

    def test_proxy_sat_thi_gia_thi_van_dinh_gia_binh_thuong(self):
        """Không chặn bừa: proxy hợp lý vẫn phải cho ra khuyến nghị."""
        # VCSH 10.000 tỷ / 1 tỷ cp = 10.000đ/cp sổ sách; LNST 900 tỷ.
        # earnings_ps = 900e9 × 11 / 1e9 = 9.900đ ; nav_ps = 10.000đ
        # sotp = (0,6×9.900 + 0,4×10.000) × 0,9 = 9.940 × 0,9 = 8.946đ
        #      -> lệch -0,6% so thị giá 9.000đ, nằm trong ngưỡng ±50%
        m = _sotp(net_income_ty=[900.0] * 3, equity_ty=10_000.0,
                  shares=1_000_000_000, price=9_000.0)
        res = m.perform_valuation()
        assert res["not_rated"] is False
        assert res["blended_fair_value_per_share"] == pytest.approx(8946.0, rel=1e-6)

    def test_nguong_lay_tu_config_khong_hardcode(self):
        from valuation.config import load_defaults
        assert "proxy_max_divergence" in (load_defaults().get("proxy_valuation") or {})

    def test_khong_co_thi_gia_thi_khong_phan_xet(self):
        m = _sotp(net_income_ty=[1000.0] * 3, equity_ty=100_000.0,
                  shares=3_800_000_000, price=0.0)
        assert m.perform_valuation()["not_rated"] is False

    def test_che_do_AI_SOTP_khai_bao_mang_thi_khong_bi_chan(self):
        """Khi analyst đã khai báo từng mảng thì không còn là proxy nữa."""
        segs = [{"gia_tri": 50_000.0, "multiple_ky_vong": 0, "loai_gia_tri": "EQUITY"}]
        m = _sotp(net_income_ty=[1000.0] * 3, equity_ty=100_000.0,
                  shares=1_000_000_000, price=208_500.0, sotp_segments=segs)
        res = m.perform_valuation()
        assert res["not_rated"] is False
        assert "AI_SOTP_MODE" in res["flags"]


class TestDecisionEngineNotRated:
    def _dm(self, not_rated, fv=10000.0, price=20000.0):
        return InvestmentDecisionMaker(
            business_nature="Compounder", current_price=price, fair_value=fv,
            governance=GovernanceData(), not_rated=not_rated,
        )

    def test_not_rated_thi_khong_phat_khuyen_nghi_mua_ban(self):
        assert self._dm(True).make_decision()["recommendation"] == "NOT_RATED"

    def test_binh_thuong_van_ra_khuyen_nghi(self):
        assert self._dm(False).make_decision()["recommendation"] == "SELL"

    def test_hard_gate_uu_tien_cao_hon_not_rated(self):
        """Rủi ro quản trị là thông tin có giá trị kể cả khi không định giá được."""
        gov = GovernanceData(audit_issue=True)
        dm = InvestmentDecisionMaker(
            business_nature="Compounder", current_price=20000.0, fair_value=10000.0,
            governance=gov, not_rated=True,
        )
        assert dm.make_decision()["recommendation"] == "HARD REJECT"


class TestTichHopValuate:
    def test_VIC_khong_con_phat_khuyen_nghi_ban_tu_so_rac(self):
        from valuation.data_access.repo import build_company_data
        from valuation.db.session import SessionLocalRead
        from valuation.engine.valuate import valuate

        db = SessionLocalRead()
        try:
            company = build_company_data(db, "VIC", mode="TTM", fetch_live=False)
            res = valuate(company)
        finally:
            db.close()
        assert res["not_rated"] is True
        assert res["recommendation"] == "NOT_RATED"
        assert any("PROXY_IMPLAUSIBLE" in f for f in res["flags"])
