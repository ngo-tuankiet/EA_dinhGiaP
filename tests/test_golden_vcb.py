"""
VCB — số cổ phiếu lưu hành xác minh độc lập với HOSE (8,355,675,094 cp).

Giá trị định giá VCB được đối chiếu báo cáo CTCK thật ở tests/test_golden_broker.py
(chân P/B + trọng số pha trộn theo Shinhan 27/08/2026). Test cũ ở đây kiểm model đã gỡ
`VCBValuationModel` (không còn chạy trong app/batch/API).
"""
import pytest
from valuation.db.session import SessionLocalRead
from valuation.engine.ttm_helper import get_shares_outstanding

@pytest.fixture
def db():
    session = SessionLocalRead()
    yield session
    session.close()

class TestVCBSharesOutstanding:
    def test_shares_vcb_hose_verified(self, db):
        """Số lượng cổ phiếu lưu hành VCB phải đúng 8,355,675,094 cp (đối chiếu HOSE)."""
        shares = get_shares_outstanding(db, "VCB")
        # Số lượng shares thực tế sau đợt tăng vốn điều lệ lên 83.56T VND (cho phép lệch cực nhỏ do làm tròn Vốn điều lệ trong BCTC)
        assert abs(shares - 8_355_675_094) <= 10, (
            f"Shares={shares:,.0f} lệch quá 10cp so với số liệu xác minh từ HOSE (8,355,675,094)"
        )
