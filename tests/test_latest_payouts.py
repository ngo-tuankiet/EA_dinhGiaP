"""Tab Cổ tức: "Lần chia gần nhất" (tiền mặt + cổ phiếu/thưởng), gộp sự kiện cùng ngày GDKHQ."""

from datetime import date
from types import SimpleNamespace

from valuation.views.corporate_actions import latest_payouts


def _ev(kind, ex=None, pay=None, ratio=None, cash=None):
    return SimpleNamespace(
        event_type=kind,
        ex_right_date=ex,
        record_date=None,
        payment_date=pay,
        listing_date=None,
        announcement_date=None,
        exercise_ratio=ratio,
        cash_amount_vnd_per_share=cash,
    )


def test_latest_payouts_gex_like_history():
    # Như GEX trong DB: CP 25% + thưởng 20% cùng GDKHQ 05/05/2026; tiền mặt 800đ GDKHQ 10/09/2025;
    # niêm yết bổ sung không có ngày; tiền mặt cũ hơn và sự kiện tương lai không được chọn.
    rows = [
        _ev("ADDITIONAL_LISTING"),
        _ev("STOCK_DIVIDEND", date(2026, 5, 5), ratio=0.25),
        _ev("BONUS_SHARE", date(2026, 5, 5), ratio=0.20),
        _ev("CASH_DIVIDEND", date(2025, 9, 10), date(2025, 10, 10), 0.08, 800),
        _ev("CASH_DIVIDEND", date(2024, 9, 10), None, 0.06, 600),
        _ev("CASH_DIVIDEND", date(2026, 12, 1), None, 0.1, 1000),  # chưa tới
    ]
    out = latest_payouts(rows, today=date(2026, 10, 12))
    assert [r.cash_amount_vnd_per_share for r in out["cash"]] == [800]
    assert {r.event_type for r in out["stock"]} == {"STOCK_DIVIDEND", "BONUS_SHARE"}


def test_latest_payouts_empty_when_no_past_dividend():
    rows = [
        _ev("ESOP", date(2026, 1, 1), ratio=0.005),
        _ev("CASH_DIVIDEND", date(2027, 1, 1)),
    ]
    assert latest_payouts(rows, today=date(2026, 10, 12)) == {}
