"""D48 — số cp sau cổ phiếu thưởng/cổ tức CP mà corporate_actions thiếu ngày GDKHQ (FPT, PHR, VPB).

Giá VCI đã chia (1+tỷ lệ) từ ngày GDKHQ nhưng engine giữ số cp cũ → GTHL/cp bị phóng đại đúng
bằng tỷ lệ. Số sau sự kiện = số VSDC đăng ký trước sự kiện × (1+tỷ lệ) (tạm tính, chờ VSDC).
HDB, GMD: GDKHQ sau ngày dữ liệu → override chỉ có hiệu lực từ ngày GDKHQ.
"""

from datetime import date

import pytest

from valuation.db.session import SessionLocalRead
from valuation.engine.ttm_helper import get_shares_outstanding


@pytest.fixture(scope="module")
def db():
    s = SessionLocalRead()
    yield s
    s.close()


@pytest.mark.parametrize(
    "ticker,before,ratio,ex",
    [
        ("FPT", 1_714_326_422, 0.10, date(2026, 9, 21)),
        ("PHR", 135_499_198, 0.80, date(2026, 9, 11)),
        ("VPB", 7_933_923_601, 0.2604104, date(2026, 9, 24)),
    ],
)
def test_post_event_shares_from_ex_date(db, ticker, before, ratio, ex):
    after = get_shares_outstanding(db, ticker, as_of_date=ex)
    assert after == pytest.approx(before * (1 + ratio), rel=1e-6)
    # Trước GDKHQ không được dùng số sau sự kiện (chống lookahead).
    assert (
        get_shares_outstanding(db, ticker, as_of_date=date(2026, 9, 1)) < after * 0.99
    )


def test_future_ex_dates_not_applied_early(db):
    assert (
        get_shares_outstanding(db, "GMD", as_of_date=date(2026, 10, 6)) == 432_892_509
    )
    assert (
        get_shares_outstanding(db, "GMD", as_of_date=date(2026, 10, 7)) == 649_338_763
    )
    assert (
        get_shares_outstanding(db, "HDB", as_of_date=date(2026, 10, 9)) == 6_506_859_219
    )


def test_undated_split_flag_raised_until_override_added(monkeypatch):
    """Dùng sự kiện giả lập trên bản DB test (conftest đã copy) để không phụ thuộc lần đồng bộ
    corporate_actions gần nhất — dữ liệu thật được bổ sung ngày GDKHQ dần theo thời gian.
    """
    from valuation.db.models import CorporateAction
    from valuation.db.session import SessionLocalWrite
    from valuation.engine import ttm_helper
    from valuation.engine.ttm_helper import undated_split_flags

    db = SessionLocalWrite()
    try:
        db.add(
            CorporateAction(
                ticker="ZZTEST",
                source_site="test",
                source_event_id="d48-flag",
                event_type="BONUS_SHARE",
                title="test thưởng 10%",
                content_hash="d48-flag-test",
                exercise_ratio=0.1,
                announcement_date=date(2026, 9, 1),
            )
        )
        db.flush()
        monkeypatch.setattr(ttm_helper, "_load_shares_events", lambda: [])
        assert undated_split_flags(db, "ZZTEST", date(2026, 9, 28)) == [
            "CORPORATE_ACTION_UNDATED"
        ]
        # Quá cửa sổ 180 ngày → không cờ.
        assert undated_split_flags(db, "ZZTEST", date(2027, 6, 1)) == []
        # Đã có số cp ghi đè hiệu lực sau ngày công bố → không cờ.
        monkeypatch.setattr(
            ttm_helper,
            "_load_shares_events",
            lambda: [
                {
                    "ticker": "ZZTEST",
                    "effective_date": "2026-09-21",
                    "shares_outstanding": 1,
                }
            ],
        )
        assert undated_split_flags(db, "ZZTEST", date(2026, 9, 28)) == []
    finally:
        db.rollback()
        db.close()


def test_share_count_scales_dcf_leg_only(db, monkeypatch):
    """Giá đã điều chỉnh quyền: P/E lịch sử × EPS bất biến theo số cp (sai số số cp cũ triệt tiêu
    trong nhánh bội số), còn nhánh DCF = vốn CSH / số cp. Không được chia cả GTHL pha trộn theo tỷ
    lệ chia (cách quy đổi tay ×0,9033 trước D48 là điều chỉnh quá tay). Số cp giả lập qua override
    nên test không phụ thuộc dữ liệu sự kiện quyền trong DB."""
    from valuation.data_access.repo import build_company_data
    from valuation.engine import ttm_helper
    from valuation.engine.batch import _dispatch_nonfin
    from valuation.engine.sector_router import route

    plan = route("FPT")

    def run(shares):
        monkeypatch.setattr(
            ttm_helper,
            "_load_shares_events",
            lambda: [
                {
                    "ticker": "FPT",
                    "effective_date": "2026-01-01",
                    "shares_outstanding": shares,
                }
            ],
        )
        return _dispatch_nonfin(
            build_company_data(db, "FPT"), plan["method"], plan["group"]
        )[1]

    small, large = run(1_714_326_422), run(1_885_759_064)
    assert large["multiples_fvps"] == pytest.approx(small["multiples_fvps"], rel=1e-3)
    # Phần liên doanh (lãi LD × P/E lịch sử) không tỷ lệ với số cp → lệch ≤ 2%.
    assert large["dcf_fvps"] == pytest.approx(small["dcf_fvps"] / 1.1, rel=0.02)
