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


def _mem_db():
    """DB SQLite trong bộ nhớ: không mở phiên ghi vào file DB (kể cả bản copy của conftest)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from valuation.db.models import Ticker
    from valuation.db.session import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Ticker(ticker="ZZTEST", company_name="ZZTEST", is_vn100=True))
    return session


def _event(db, event_id, event_type, ratio, announced, ex=None):
    from valuation.db.models import CorporateAction

    db.add(
        CorporateAction(
            ticker="ZZTEST",
            source_site="test",
            source_event_id=event_id,
            event_type=event_type,
            title=f"test {event_type} {ratio:.2%}",
            content_hash=event_id,
            exercise_ratio=ratio,
            announcement_date=announced,
            ex_right_date=ex,
        )
    )
    db.commit()


def test_undated_split_flag_raised_until_override_added(monkeypatch):
    """Sự kiện giả lập trên DB trong bộ nhớ để không phụ thuộc lần đồng bộ corporate_actions gần nhất."""
    from valuation.engine import ttm_helper
    from valuation.engine.ttm_helper import undated_split_flags

    db = _mem_db()
    _event(db, "d48-flag", "BONUS_SHARE", 0.1, date(2026, 9, 1))
    monkeypatch.setattr(ttm_helper, "_load_shares_events", list)
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


def test_undated_rights_issue_raises_flag_but_not_split_factor(monkeypatch):
    """Dữ liệu F9: quyền mua thiếu ngày GDKHQ (SJS 67,23%, công bố 22/08/2026) → cờ RIGHTS_ISSUE_UNDATED
    (thông tin, fx1); có override → hết cờ. Quyền mua CÓ ngày GDKHQ sau kỳ BCTC vẫn KHÔNG vào hệ số chia
    (đi kèm tiền, chờ BCTC) → hệ số = 1; đối chứng cổ tức CP 15% cùng ngày → hệ số 1,15."""
    from valuation.db.models import FinancialsQuarterly
    from valuation.engine import ttm_helper
    from valuation.engine.ttm_helper import undated_split_flags

    db = _mem_db()
    _event(db, "f9-rights", "RIGHTS_ISSUE", 0.6723, date(2026, 8, 22))
    monkeypatch.setattr(ttm_helper, "_load_shares_events", list)
    assert undated_split_flags(db, "ZZTEST", date(2026, 10, 20)) == ["RIGHTS_ISSUE_UNDATED"]
    monkeypatch.setattr(
        ttm_helper,
        "_load_shares_events",
        lambda: [{"ticker": "ZZTEST", "effective_date": "2026-10-01", "shares_outstanding": 1}],
    )
    assert undated_split_flags(db, "ZZTEST", date(2026, 10, 20)) == []

    # Vốn điều lệ 1.000 tỷ (100 tr cp) ở 4 quý tới Q2/2026; GDKHQ 02/10/2026 sau kỳ BCTC.
    for y, q in ((2025, 3), (2025, 4), (2026, 1), (2026, 2)):
        db.add(FinancialsQuarterly(ticker="ZZTEST", fiscal_year=y, fiscal_quarter=q,
                                   is_consolidated=True, is_restated=False, statement="BS",
                                   line_item="paid_in_capital", value=1e12, currency="VND"))
    _event(db, "f9-rights-dated", "RIGHTS_ISSUE", 0.5, date(2026, 9, 1), ex=date(2026, 10, 2))
    keys = ttm_helper._CAPITAL_KEYS
    assert ttm_helper._unreflected_split_factor(db, "ZZTEST", keys, date(2026, 10, 20)) == 1.0
    _event(db, "f9-stock-div", "STOCK_DIVIDEND", 0.15, date(2026, 9, 1), ex=date(2026, 10, 2))
    assert ttm_helper._unreflected_split_factor(
        db, "ZZTEST", keys, date(2026, 10, 20)
    ) == pytest.approx(1.15)


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
