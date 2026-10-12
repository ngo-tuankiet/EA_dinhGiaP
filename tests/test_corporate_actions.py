import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.analysis.corporate_actions import (
    analyze_corporate_action,
    analyze_historical_price_impact,
    explain_historical_price_impact,
    explain_upcoming_action,
)
from valuation.data_access.corporate_actions import (
    corporate_actions_context,
    load_corporate_actions,
    load_upcoming_vn100_corporate_actions,
    should_refresh_corporate_actions,
)
from valuation.db.models import (
    CorporateAction,
    CorporateActionSync,
    PricesDaily,
    Ticker,
)
from valuation.db.session import Base
from valuation.ingest.corporate_actions import (
    normalize_vci_event,
    upsert_corporate_actions,
)
from valuation.views.corporate_actions import _historical_impact_rows


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Ticker(ticker="AAA", company_name="Công ty kiểm thử", is_vn100=True))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _vci_cash_event() -> dict:
    return {
        "id": "evt-cash-2026",
        "ticker": "AAA",
        "eventCode": "DIV",
        "eventTitleVi": "Trả cổ tức bằng tiền mặt - 1.500 VND/cổ phiếu",
        "publicDate": "2026-03-01T00:00:00",
        "recordDate": "2026-03-20T00:00:00",
        "exrightDate": "2026-03-19T00:00:00",
        "payoutDate": "2026-04-10T00:00:00",
        "exerciseRatio": 0.15,
        "valuePerShare": 1500,
    }


def test_normalize_vci_cash_dividend_keeps_vnd_and_source_metadata():
    event = normalize_vci_event(_vci_cash_event(), ticker="AAA")

    assert event["event_type"] == "CASH_DIVIDEND"
    assert event["cash_amount_vnd_per_share"] == 1_500
    assert event["exercise_ratio"] == pytest.approx(0.15)
    assert event["announcement_date"] == datetime.date(2026, 3, 1)
    assert event["source_site"] == "VCI"
    assert event["source_tier"] == "AGGREGATOR"


def test_upsert_is_idempotent_and_does_not_rewrite_unchanged_event(db):
    event = normalize_vci_event(_vci_cash_event(), ticker="AAA")

    first = upsert_corporate_actions(db, [event])
    second = upsert_corporate_actions(db, [event])

    assert first == {"inserted": 1, "updated": 0, "unchanged": 0}
    assert second == {"inserted": 0, "updated": 0, "unchanged": 1}
    assert db.query(CorporateAction).count() == 1


def test_reader_blocks_lookahead_but_keeps_announced_future_action(db):
    announced = normalize_vci_event(_vci_cash_event(), ticker="AAA")
    future_disclosure = normalize_vci_event(
        {
            **_vci_cash_event(),
            "id": "evt-future-disclosure",
            "publicDate": "2026-05-01T00:00:00",
            "recordDate": "2026-05-20T00:00:00",
        },
        ticker="AAA",
    )
    upsert_corporate_actions(db, [announced, future_disclosure])

    rows = load_corporate_actions(
        db,
        "AAA",
        as_of_date=datetime.date(2026, 4, 1),
        history_years=5,
        future_days=365,
    )

    assert [row.source_event_id for row in rows] == ["evt-cash-2026"]
    assert rows[0].payment_date > datetime.date(2026, 4, 1)


def test_upcoming_vn100_reader_uses_next_milestone_and_blocks_lookahead(db):
    as_of = datetime.date(2026, 9, 9)
    db.add(Ticker(ticker="BBB", company_name="Ngoài VN100", is_vn100=False))
    db.add_all(
        [
            CorporateAction(
                ticker="AAA",
                source_site="VCI",
                source_event_id="cash-payment-soon",
                event_type="CASH_DIVIDEND",
                event_code="DIV",
                title="Trả cổ tức tiền mặt 1.000 đồng/cổ phiếu",
                announcement_date=datetime.date(2026, 8, 1),
                ex_right_date=datetime.date(2026, 8, 20),
                record_date=datetime.date(2026, 8, 21),
                payment_date=datetime.date(2026, 9, 18),
                cash_amount_vnd_per_share=1_000,
                source_tier="AGGREGATOR",
                content_hash="cash-payment-soon",
            ),
            CorporateAction(
                ticker="AAA",
                source_site="VCI",
                source_event_id="outside-window",
                event_type="RIGHTS_ISSUE",
                event_code="ISS",
                title="Quyền mua ngoài cửa sổ",
                announcement_date=datetime.date(2026, 8, 1),
                start_date=datetime.date(2026, 10, 10),
                source_tier="AGGREGATOR",
                content_hash="outside-window",
            ),
            CorporateAction(
                ticker="AAA",
                source_site="VCI",
                source_event_id="future-disclosure",
                event_type="CASH_DIVIDEND",
                event_code="DIV",
                title="Chưa được công bố tại ngày xem",
                announcement_date=datetime.date(2026, 9, 12),
                payment_date=datetime.date(2026, 9, 20),
                source_tier="AGGREGATOR",
                content_hash="future-disclosure",
            ),
            CorporateAction(
                ticker="BBB",
                source_site="VCI",
                source_event_id="outside-vn100",
                event_type="CASH_DIVIDEND",
                event_code="DIV",
                title="Mã ngoài VN100",
                announcement_date=datetime.date(2026, 8, 1),
                payment_date=datetime.date(2026, 9, 15),
                source_tier="AGGREGATOR",
                content_hash="outside-vn100",
            ),
        ]
    )
    db.commit()

    items = load_upcoming_vn100_corporate_actions(
        db,
        as_of_date=as_of,
        future_days=30,
    )

    assert len(items) == 1
    assert items[0].action.ticker == "AAA"
    assert items[0].event_date == datetime.date(2026, 9, 18)
    assert items[0].date_role == "Ngày thanh toán"


def test_refresh_gate_uses_checkpoint_ttl(db):
    now = datetime.datetime(2026, 8, 30, 8, 0, 0, tzinfo=datetime.timezone.utc)
    db.add(
        CorporateActionSync(
            ticker="AAA",
            source_site="VCI",
            last_checked_at=now - datetime.timedelta(hours=6),
            status="OK",
        )
    )
    db.commit()

    assert not should_refresh_corporate_actions(db, "AAA", now=now, ttl_hours=24)
    assert should_refresh_corporate_actions(
        db, "AAA", now=now + datetime.timedelta(hours=25), ttl_hours=24
    )


def test_failed_checkpoint_uses_short_backoff_instead_of_retrying_every_rerun(db):
    now = datetime.datetime(2026, 8, 30, 8, 0, 0, tzinfo=datetime.timezone.utc)
    db.add(
        CorporateActionSync(
            ticker="AAA",
            source_site="VCI",
            last_checked_at=now - datetime.timedelta(minutes=1),
            status="ERROR",
            last_error="Nguồn tạm ngắt kết nối",
        )
    )
    db.commit()

    assert not should_refresh_corporate_actions(
        db, "AAA", now=now, ttl_hours=24, error_retry_minutes=30
    )
    assert should_refresh_corporate_actions(
        db,
        "AAA",
        now=now + datetime.timedelta(minutes=31),
        ttl_hours=24,
        error_retry_minutes=30,
    )


def test_corporate_action_formulas_match_manual_calculation():
    cash = analyze_corporate_action(
        event_type="CASH_DIVIDEND",
        current_price_vnd=30_000,
        shares_outstanding=100_000_000,
        cash_amount_vnd_per_share=1_500,
    )
    assert cash["dividend_yield_pct"] == pytest.approx(5.0)
    assert cash["theoretical_ex_price_vnd"] == pytest.approx(28_500)

    stock = analyze_corporate_action(
        event_type="STOCK_DIVIDEND",
        current_price_vnd=30_000,
        shares_outstanding=100_000_000,
        exercise_ratio=0.20,
    )
    assert stock["shares_after"] == pytest.approx(120_000_000)
    assert stock["theoretical_ex_price_vnd"] == pytest.approx(25_000)
    assert stock["eps_dilution_pct_before_new_profit"] == pytest.approx(-16.6666667)

    rights = analyze_corporate_action(
        event_type="RIGHTS_ISSUE",
        current_price_vnd=30_000,
        shares_outstanding=100_000_000,
        exercise_ratio=0.25,
        issue_price_vnd=10_000,
    )
    assert rights["theoretical_ex_price_vnd"] == pytest.approx(26_000)
    assert rights["right_value_vnd_per_old_share"] == pytest.approx(4_000)
    assert rights["cash_raised_billion_vnd"] == pytest.approx(250.0)


def test_rights_issue_without_price_is_not_guessed():
    result = analyze_corporate_action(
        event_type="RIGHTS_ISSUE",
        current_price_vnd=30_000,
        shares_outstanding=100_000_000,
        exercise_ratio=0.25,
        issue_price_vnd=None,
    )

    assert result["theoretical_ex_price_vnd"] is None
    assert "giá phát hành" in result["data_warning"].lower()


def test_historical_cash_dividend_separates_mechanical_drop_from_market_reaction():
    prices = [
        {
            "date": datetime.date(2026, 3, 18) + datetime.timedelta(days=i),
            "close": close,
        }
        for i, close in enumerate(
            [30_000, 28_600, 28_700, 28_900, 29_000, 29_100, 29_200]
            + [29_300] * 14
            + [30_500]
        )
    ]

    impact = analyze_historical_price_impact(
        prices=prices,
        event_date=datetime.date(2026, 3, 19),
        event_type="CASH_DIVIDEND",
        cash_amount_vnd_per_share=1_500,
    )

    assert impact["price_before_vnd"] == 30_000
    assert impact["price_event_vnd"] == 28_600
    assert impact["raw_event_return_pct"] == pytest.approx(-4.6666667)
    assert impact["mechanical_adjustment_pct"] == pytest.approx(-5.0)
    assert impact["market_reaction_vs_theoretical_pct"] == pytest.approx(
        28_600 / 28_500 * 100 - 100
    )
    assert impact["shareholder_wealth_change_pct"] == pytest.approx(
        (28_600 + 1_500) / 30_000 * 100 - 100
    )
    assert impact["return_after_5_sessions_pct"] == pytest.approx(
        29_200 / 28_600 * 100 - 100
    )
    assert impact["return_after_20_sessions_pct"] == pytest.approx(
        30_500 / 28_600 * 100 - 100
    )
    story = explain_historical_price_impact(
        event_type="CASH_DIVIDEND",
        impact=impact,
        reaction_materiality_pct=2.0,
    )
    assert story["reaction_label"] == "TỔNG TÀI SẢN GẦN NHƯ KHÔNG ĐỔI"
    assert "1.500 vnd tiền mặt" in story["wealth_explanation"].lower()
    assert "cơ học" not in " ".join(story.values()).lower()


def test_historical_stock_dividend_adjusts_for_extra_shares():
    prices = [
        {"date": datetime.date(2026, 5, 29), "close": 30_000},
        {"date": datetime.date(2026, 6, 1), "close": 25_250},
    ]

    impact = analyze_historical_price_impact(
        prices=prices,
        event_date=datetime.date(2026, 6, 1),
        event_type="STOCK_DIVIDEND",
        exercise_ratio=0.20,
    )

    assert impact["theoretical_ex_price_vnd"] == pytest.approx(25_000)
    assert impact["market_reaction_vs_theoretical_pct"] == pytest.approx(1.0)
    assert impact["shareholder_wealth_change_pct"] == pytest.approx(1.0)
    story = explain_historical_price_impact(
        event_type="STOCK_DIVIDEND",
        impact=impact,
        reaction_materiality_pct=2.0,
    )
    assert "20 cổ phiếu" in story["wealth_explanation"]
    assert story["reaction_label"] == "TỔNG TÀI SẢN GẦN NHƯ KHÔNG ĐỔI"


def test_historical_share_grant_does_not_double_count_adjusted_price_series():
    prices = [
        {"date": datetime.date(2025, 10, 28), "close": 16_100},
        *[
            {
                "date": datetime.date(2025, 10, 29) + datetime.timedelta(days=i),
                "close": 17_200 - i * 50,
            }
            for i in range(21)
        ],
    ]

    impact = analyze_historical_price_impact(
        prices=prices,
        event_date=datetime.date(2025, 10, 29),
        event_type="STOCK_BONUS_COMBO",
        exercise_ratio=0.615,
    )

    assert impact["price_series_adjusted"] is True
    assert impact["estimated_unadjusted_price_before_vnd"] == pytest.approx(
        16_100 * 1.615
    )
    assert impact["shareholder_wealth_change_pct"] == pytest.approx(
        17_200 / 16_100 * 100 - 100
    )
    assert impact["shareholder_wealth_change_pct"] != pytest.approx(
        17_200 * 1.615 / 16_100 * 100 - 100
    )

    story = explain_historical_price_impact(
        event_type="STOCK_BONUS_COMBO",
        impact=impact,
        reaction_materiality_pct=2.0,
    )
    assert "không cộng thêm cổ phiếu lần nữa" in story["wealth_explanation"]
    assert "mốc đã chia xong" in story["follow_through"]


def test_historical_impact_rows_combines_same_day_share_grants():
    common = {
        "ticker": "BSR",
        "source_site": "VCI",
        "event_code": "ISS",
        "announcement_date": datetime.date(2025, 10, 15),
        "ex_right_date": datetime.date(2025, 10, 29),
        "record_date": datetime.date(2025, 10, 30),
        "payment_date": None,
        "listing_date": datetime.date(2025, 12, 8),
        "cash_amount_vnd_per_share": None,
        "issue_price_vnd": None,
        "shares_after": None,
        "source_url": None,
        "source_tier": "AGGREGATOR",
    }
    rows = [
        SimpleNamespace(
            **common,
            source_event_id="stock",
            event_type="STOCK_DIVIDEND",
            title="Trả cổ tức bằng cổ phiếu tỉ lệ 30.0%",
            exercise_ratio=0.30,
        ),
        SimpleNamespace(
            **common,
            source_event_id="bonus",
            event_type="BONUS_SHARE",
            title="Cổ phiếu thưởng tỉ lệ 31.5%",
            exercise_ratio=0.315,
        ),
    ]

    combined = _historical_impact_rows(rows)

    assert len(combined) == 1
    assert combined[0].event_type == "STOCK_BONUS_COMBO"
    assert combined[0].exercise_ratio == pytest.approx(0.615)


def test_upcoming_explanation_uses_plain_language_and_holding_example():
    analysis = analyze_corporate_action(
        event_type="BONUS_SHARE",
        current_price_vnd=30_000,
        shares_outstanding=100_000_000,
        exercise_ratio=0.10,
    )
    explanation = explain_upcoming_action(
        event_type="BONUS_SHARE",
        holding_shares=1_000,
        current_price_vnd=30_000,
        exercise_ratio=0.10,
        cash_amount_vnd_per_share=None,
        issue_price_vnd=None,
        analysis=analysis,
    )

    assert "100 cổ phiếu mới" in explanation["what_you_receive"]
    assert "1.100 cổ phiếu" in explanation["what_you_receive"]
    assert "27.273 VND" in explanation["price_effect"]
    assert "không tự tạo thêm giá trị" in explanation["simple_verdict"].lower()


def test_upcoming_rights_explanation_does_not_invent_missing_issue_price():
    analysis = analyze_corporate_action(
        event_type="RIGHTS_ISSUE",
        current_price_vnd=30_000,
        shares_outstanding=100_000_000,
        exercise_ratio=0.20,
    )
    explanation = explain_upcoming_action(
        event_type="RIGHTS_ISSUE",
        holding_shares=1_000,
        current_price_vnd=30_000,
        exercise_ratio=0.20,
        cash_amount_vnd_per_share=None,
        issue_price_vnd=None,
        analysis=analysis,
    )

    assert "200 cổ phiếu" in explanation["what_you_receive"]
    assert "chưa có giá phát hành" in explanation["price_effect"].lower()
    assert "không thể" in explanation["simple_verdict"].lower()


def test_deepseek_context_contains_only_traceable_events(db):
    upsert_corporate_actions(db, [normalize_vci_event(_vci_cash_event(), ticker="AAA")])

    context = corporate_actions_context(
        db,
        ticker="AAA",
        current_price_vnd=30_000,
        shares_outstanding=100_000_000,
        as_of_date=datetime.date(2026, 4, 1),
    )

    assert context["available"] is True
    assert context["events"][0]["source_site"] == "VCI"
    assert context["events"][0]["analysis"]["dividend_yield_pct"] == pytest.approx(5.0)


def test_deepseek_context_includes_traceable_historical_price_reaction(db):
    upsert_corporate_actions(db, [normalize_vci_event(_vci_cash_event(), ticker="AAA")])
    # Giá DB đã điều chỉnh cổ tức (D57): trước GDKHQ 30.000 gốc − 1.500 cổ tức = 28.500.
    prices = [
        (datetime.date(2026, 3, 18), 28_500),
        (datetime.date(2026, 3, 19), 28_600),
        (datetime.date(2026, 3, 20), 28_900),
    ]
    for trade_date, close in prices:
        db.add(
            PricesDaily(
                ticker="AAA",
                trade_date=trade_date,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1_000_000,
                price_unit="VND",
            )
        )
    db.commit()

    context = corporate_actions_context(
        db,
        ticker="AAA",
        current_price_vnd=30_000,
        shares_outstanding=100_000_000,
        as_of_date=datetime.date(2026, 4, 1),
    )

    reaction = context["events"][0]["historical_price_impact"]
    assert reaction["price_before_vnd"] == 28_500
    assert reaction["estimated_unadjusted_price_before_vnd"] == 30_000
    assert reaction["market_reaction_vs_theoretical_pct"] == pytest.approx(
        28_600 / 28_500 * 100 - 100
    )
    explanation = context["events"][0]["historical_explanation"]
    assert explanation["reaction_label"] == "TỔNG TÀI SẢN GẦN NHƯ KHÔNG ĐỔI"


def test_cash_dividend_on_adjusted_prices_is_not_counted_twice():
    # Giá DB đã điều chỉnh cổ tức: trước GDKHQ 95 (gốc 100), ngày GDKHQ 95, cổ tức 5 đ.
    # Cổ đông: 100 → 95 + 5 tiền = 0%. Cách cũ cộng thêm 5 vào giá đã điều chỉnh → +5,3% (sai).
    prices = [
        {"date": datetime.date(2026, 5, 27), "close": 95},
        {"date": datetime.date(2026, 5, 28), "close": 95},
    ]
    impact = analyze_historical_price_impact(
        prices=prices,
        event_date=datetime.date(2026, 5, 28),
        event_type="CASH_DIVIDEND",
        cash_amount_vnd_per_share=5,
        cash_dividend_prices_adjusted=True,
    )
    assert impact["shareholder_wealth_change_pct"] == pytest.approx(0.0)
    assert impact["price_series_adjusted"] is True
    assert impact["estimated_unadjusted_price_before_vnd"] == pytest.approx(100.0)
    text = explain_historical_price_impact(
        event_type="CASH_DIVIDEND", impact=impact, reaction_materiality_pct=2.0
    )["wealth_explanation"]
    assert "không cộng tiền này lần nữa" in text
