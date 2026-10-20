"""Chốt chặn công bố, lỗi code và cờ dữ liệu (nâng cấp 19/10/2026, bước s1).

Số liệu tính tay; ca DB thật lấy từ chẩn đoán (NAB 2018, BVH, VPI 2018, PVT Q2/2026, BAF/DXG).
"""

import datetime
from types import SimpleNamespace as N

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.data_access import repo
from valuation.db.models import FinancialsQuarterly, Ticker
from valuation.db.session import Base, SessionLocalRead


@pytest.fixture(scope="module")
def db():
    s = SessionLocalRead()
    yield s
    s.close()


# --- (0) Cổng công bố ---------------------------------------------------------------------------


def test_legs_diverge_hand_cases():
    from valuation.engine.models.dcf import legs_diverge

    # Ngưỡng cấu hình publication_gate.leg_ratio_review (5,0 từ 20/10/2026; 8,67 vượt mọi ngưỡng ≤ 8).
    assert legs_diverge(1_500, 13_000)  # 13.000 / 1.500 = 8,67 > 5
    assert not legs_diverge(10_000, 12_000)  # 1,2
    assert legs_diverge(5_000, -200)  # chân bội số âm bị pha vào trung bình
    # fx2: hàm dùng chung (guardrails) coi một chân ≤ 0 là vênh; DCF không gọi khi chân DCF âm (NEGATIVE_DCF_LEG).
    assert legs_diverge(-251, 12_568)
    assert not legs_diverge(-251, -12)  # cả hai chân âm: đã có cờ chân âm riêng


def test_review_flag_thresholds_come_from_config(monkeypatch):
    from valuation.engine import valuate as V

    cfg = {
        "publication_gate": {
            "upside_extreme_review_pct": 80.0,
            "downside_extreme_review_pct": -30.0,
        }
    }
    monkeypatch.setattr("valuation.config.load_defaults", lambda: cfg)
    assert V._review_flags(90.0) == ["UPSIDE_EXTREME_REVIEW"]
    assert V._review_flags(-31.0) == ["DOWNSIDE_EXTREME_REVIEW"]
    assert V._review_flags(70.0) == []


def test_legs_divergence_blocks_publication(db):
    from valuation.engine.valuate import _apply_publication_gate

    c = repo.build_company_data(db, "FPT")
    res = _apply_publication_gate(
        c,
        {
            "blended_fair_value_per_share": c.current_price * 1.1,
            "flags": ["VALUATION_LEGS_DIVERGE"],
        },
    )
    assert res["publication_allowed"] is False and res["recommendation"] == "NOT_RATED"


def test_holds_for_unreviewed_models_active():
    from valuation.config import active_event_hold, load_event_holds

    holds = load_event_holds()
    for t in ("NAB", "BVH", "VRE"):
        assert active_event_hold(t, datetime.date(2026, 10, 19))
        assert holds[t].get("lift_when")


# --- (1) Khóa nhóm trong sector_peer_multiples ---------------------------------------------------


def test_sector_peer_multiples_matches_routing_sector_key(monkeypatch):
    routing = {t: {"sector": "X", "primary": "FCFF"} for t in ("A", "B", "C", "D")}
    routing["E"] = {"sector": "Y", "primary": "FCFF"}
    monkeypatch.setattr(
        "valuation.engine.sector_router._router", lambda: N(routing_data=routing)
    )
    mult = {"B": (8.0, 6.0), "C": (10.0, 30.0), "D": (12.0, 9.0), "E": (99.0, 9.0)}
    monkeypatch.setattr(repo, "build_company_data", lambda db, p, **k: p)
    monkeypatch.setattr(repo, "Company", str)  # "peer" là tên mã (str) trong ca này
    monkeypatch.setattr(
        repo, "current_multiples", lambda p: {"pe": mult[p][0], "ev_ebitda": mult[p][1]}
    )
    monkeypatch.setattr(repo, "current_pb", lambda p: {"B": 1.2, "C": 1.5, "D": 9.0, "E": 0.1}[p])
    repo._PEER_CACHE.clear()
    out = repo.sector_peer_multiples(None, "A", "X")
    repo._PEER_CACHE.clear()
    # P/E trung vị(8, 10, 12) = 10; EV/EBITDA 30x ngoài dải [2, 25] → còn 2 quan sát < min_peers 3;
    # P/B 9,0x ngoài dải [0,3; 4,0] → còn 2 quan sát → None.
    assert out == {"pe": pytest.approx(10.0), "ev_ebitda": None, "pb": None}


def test_peer_median_actually_used_for_ticker_without_own_history(db):
    # KDC: P/E lịch sử ngoài dải → trước đây luôn rơi về hằng số ngành (khóa "group" không tồn tại).
    flags = repo.build_company_data(db, "KDC").data_flags
    assert any(f.startswith("MULTIPLE_FROM_PEER_MEDIAN:pe=") for f in flags)
    assert "MULTIPLE_FROM_SECTOR_CONSTANT" not in flags


# --- (5) Chỉ tính/gắn cờ bội số mà phương pháp dùng ----------------------------------------------


@pytest.mark.parametrize(
    "plan,jv,expected",
    [
        (
            {"method": "PB", "business_nature": "Securities", "weight": 0.5},
            False,
            (False, False),
        ),
        (
            {"method": "RNAV", "business_nature": "Developer", "weight": 0.5},
            False,
            (False, False),
        ),
        (
            {"method": "EV_EBITDA", "business_nature": "Cyclical", "weight": 1.0},
            False,
            (True, False),
        ),
        (
            {"method": "PE", "business_nature": "Compounder", "weight": 1.0},
            False,
            (False, True),
        ),
        (
            {"method": "DCF", "business_nature": "Cyclical", "weight": 0.6},
            False,
            (True, False),
        ),
        (
            {"method": "DCF", "business_nature": "Retail", "weight": 0.5},
            False,
            (False, True),
        ),
        (
            {"method": "DCF", "business_nature": "Cyclical", "weight": 1.0},
            False,
            (False, False),
        ),
        (
            {"method": "DCF", "business_nature": "Cyclical", "weight": 1.0},
            True,
            (False, True),
        ),
    ],
)
def test_multiples_used_by_route(plan, jv, expected):
    assert repo.multiples_used(plan, jv_valued=jv) == expected


def test_financial_sector_has_no_multiple_constant_flag(db):
    assert (
        "MULTIPLE_FROM_SECTOR_CONSTANT"
        not in repo.build_company_data(db, "DSE").data_flags
    )


# --- (2)(3) Ngân hàng: dấu dự phòng và số dư bình quân TTM ---------------------------------------


def _bank_db(rows):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Ticker(ticker="ZZB", company_name="ZZB", is_vn100=True, sector="Banks"))
    for (y, q), items in rows.items():
        for item, value in items.items():
            s.add(
                FinancialsQuarterly(
                    ticker="ZZB",
                    fiscal_year=y,
                    fiscal_quarter=q,
                    is_consolidated=True,
                    is_restated=False,
                    statement=(
                        "BS"
                        if item
                        in ("total_assets", "loans_and_advances_to_customers_net")
                        else "IS"
                    ),
                    line_item=item,
                    value=value,
                    currency="VND",
                )
            )
    s.commit()
    return s


def test_ttm_nim_and_credit_cost_use_same_quarter_last_year_as_opening_balance():
    from valuation.engine.ttm_helper import (
        compute_historical_credit_cost,
        compute_historical_nim,
    )

    q = {(2025, 3): 950, (2025, 4): 1_000, (2026, 1): 1_050, (2026, 2): 1_100}
    rows = {
        k: {
            "net_interest_income": 10.0,
            "provision_for_credit_losses": -2.5,
            "total_assets": ta,
            "loans_and_advances_to_customers_net": ta / 2,
        }
        for k, ta in q.items()
    }
    rows[(2025, 2)] = {
        "total_assets": 900.0,
        "loans_and_advances_to_customers_net": 450.0,
    }
    s = _bank_db(rows)
    # NIM = 40 / ((900 + 1.100)/2) = 4,00% (cũ lấy cuối quý cũ nhất 950 → 40/1.025 = 3,90%).
    assert compute_historical_nim(s, "ZZB") == pytest.approx(0.04)
    # Chi phí tín dụng = −(−2,5 × 4) / ((450 + 550)/2) = 10 / 500 = 2,00%.
    assert compute_historical_credit_cost(s, "ZZB") == pytest.approx(0.02)


def test_ttm_credit_cost_net_reversal_is_negative():
    from valuation.engine.ttm_helper import compute_historical_credit_cost

    q = {
        (2025, 2): 400.0,
        (2025, 3): 450.0,
        (2025, 4): 500.0,
        (2026, 1): 550.0,
        (2026, 2): 600.0,
    }
    rows = {k: {"loans_and_advances_to_customers_net": v} for k, v in q.items()}
    for k in list(q)[1:]:
        rows[k][
            "provision_for_credit_losses"
        ] = 2.5  # nguồn ghi hoàn nhập ròng là số dương
    # −(+10) / ((400 + 600)/2) = −2,00%: hoàn nhập là chi phí âm, không abs thành chi phí.
    assert compute_historical_credit_cost(_bank_db(rows), "ZZB") == pytest.approx(-0.02)


def test_nab_2018_provision_reversal_keeps_sign(db):
    from valuation.report.verified_summary import run_deterministic_checks

    c = repo.build_company_data(db, "NAB")
    y18 = next(i for i in c.historical_is if i.year == 2018)
    # TOI 1.796,2 − chi phí HĐ 1.154,4 = PPOP 641,8; hoàn nhập 101,1 → LNTT 742,9 ≈ 743,0 báo cáo.
    assert y18.provision_expense == pytest.approx(-101.142, abs=0.01)
    assert y18.pre_provision_profit - y18.provision_expense == pytest.approx(
        y18.pretax_income, rel=0.005
    )
    checks = run_deterministic_checks(c, blended_fv=c.current_price, upside=0.0)
    assert not any(x["code"] == "BANK_PBT_MISMATCH" for x in checks)
    y22 = next(i for i in c.historical_is if i.year == 2022)
    assert y22.provision_expense > 0  # năm trích lập bình thường vẫn là chi phí dương


def test_repo_ttm_credit_cost_opening_balance_same_quarter_last_year(db):
    from valuation.engine.ttm_helper import _find_latest_4_quarters, _query_value

    c = repo.build_company_data(
        db, "ACB"
    )  # ACB: TTM > trung vị 3 năm → dùng chi phí TTM
    ly, lq = _find_latest_4_quarters(db, "ACB")[0]
    loans = ["loans_and_advances_to_customers_net"]
    opening = _query_value(db, "ACB", loans, ly - 1, lq) / 1e9
    expected = c.historical_is[-1].provision_expense / (
        (opening + c.historical_bs[-1].customer_loans) / 2
    )
    assert c.assumptions.credit_cost[0] == pytest.approx(expected)


# --- (6) BVH: nợ khác theo đẳng thức --------------------------------------------------------------


def test_balance_residual_long_term_liabilities_from_identity():
    zero = {
        "cash": 0.0,
        "receivables": 0.0,
        "inventory": 0.0,
        "fixed": 0.0,
        "short_debt": 0.0,
        "payable": 0.0,
    }
    # BVH 2026-Q2 (tỷ): 288.358,83 − 80.339,46 − vay dài hạn 0 = 208.019,37.
    out = repo._balance_residuals(
        {"liabilities": 288_358.83, "current_liabilities": 80_339.46},
        long_debt=0.0,
        **zero,
    )
    assert out["other_long_term_liabilities"] == pytest.approx(208_019.37)
    # BVH 2018: 97.699 − 25.799 − 0 = 71.900 (gồm dự phòng nghiệp vụ, không nằm trong tổng mục nào).
    out = repo._balance_residuals(
        {"liabilities": 97_699.0, "current_liabilities": 25_799.0},
        long_debt=0.0,
        **zero,
    )
    assert out["other_long_term_liabilities"] == pytest.approx(71_900.0)
    # Có tổng mục nợ dài hạn thì giữ cách cũ (tổng mục − vay dài hạn).
    out = repo._balance_residuals(
        {
            "long_term_liabilities": 500.0,
            "liabilities": 900.0,
            "current_liabilities": 300.0,
        },
        long_debt=200.0,
        **zero,
    )
    assert out["other_long_term_liabilities"] == pytest.approx(300.0)


# --- (7) VPI: bỏ năm cũ vi phạm đẳng thức IS ------------------------------------------------------


def test_inconsistent_income_year_hand_cases():
    b = 1e9
    # VPI 2018: DT 258,3; giá vốn 182,4; LN gộp 440,7 → |440,7 − 75,9| / 440,7 = 82,8% > 0,5%.
    assert repo.inconsistent_income_year(258.3 * b, 182.4 * b, 440.7 * b)
    # VPI 2019: 3.057,3 − 2.224,1 = 833,2 = LN gộp → giữ.
    assert not repo.inconsistent_income_year(3_057.3 * b, 2_224.1 * b, 833.2 * b)
    assert repo.inconsistent_income_year(-3.1 * b, 0.0, -3.1 * b)  # doanh thu âm


def test_vpi_2018_dropped_and_no_gross_profit_error(db):
    from valuation.report.verified_summary import run_deterministic_checks

    c = repo.build_company_data(db, "VPI")
    assert "INCONSISTENT_YEAR_DROPPED:2018" in c.data_flags
    assert all(i.year != 2018 for i in c.historical_is)
    checks = run_deterministic_checks(c, blended_fv=c.current_price, upside=0.0)
    assert not any(x["code"] == "GROSS_PROFIT_MISMATCH" for x in checks)


# --- (9) BS filing thiếu tổng mục: dùng nguyên BS vendor kỳ đó ------------------------------------


def _rows(items, restated, y=2026, q=2, statement="BS"):
    return [
        {
            "fiscal_year": y,
            "fiscal_quarter": q,
            "statement": statement,
            "line_item": i,
            "value": v,
            "is_restated": restated,
            "published_at": None,
        }
        for i, v in items.items()
    ]


def test_incomplete_filing_bs_period_falls_back_to_vendor():
    vendor = _rows(
        {
            "total_assets": 23_021.17,
            "owners_equity": 12_180.96,
            "liabilities": 10_840.22,
            "current_assets": 8_000.0,
        },
        False,
    )
    filing = _rows({"total_assets": 23_064.49, "owners_equity": 12_375.16}, True)
    is_filing = _rows({"net_sales": 5_577.32}, True, statement="IS")
    df, dropped = repo.drop_incomplete_filing_bs(
        pd.DataFrame(vendor + filing + is_filing)
    )
    assert dropped == [(2026, 2)]
    assert not (
        (df["statement"] == "BS") & df["is_restated"]
    ).any()  # không trộn hai nguồn trong BS
    assert len(df[df["statement"] == "IS"]) == 1  # IS filing giữ nguyên
    # Vốn chủ vendor 12.180,96 + nợ vendor 10.840,22 = 23.021,18 ≈ tổng tài sản vendor → cân.
    bs = df.set_index("line_item")["value"]
    assert bs["owners_equity"] + bs["liabilities"] == pytest.approx(
        bs["total_assets"], abs=0.05
    )


def test_complete_filing_bs_or_no_vendor_is_kept():
    full = {k: 1.0 for k in repo._BS_SUBTOTALS} | {"total_assets": 2.0}
    df = pd.DataFrame(_rows({"total_assets": 1.0}, False) + _rows(full, True))
    assert repo.drop_incomplete_filing_bs(df)[1] == []
    only_filing = pd.DataFrame(_rows({"total_assets": 1.0}, True))
    assert repo.drop_incomplete_filing_bs(only_filing)[1] == []


def test_pvt_balance_sheet_balances_with_vendor_bs(db):
    from valuation.report.verified_summary import run_deterministic_checks

    c = repo.build_company_data(db, "PVT")
    assert "FILING_BS_INCOMPLETE:2026Q2" in c.data_flags
    checks = run_deterministic_checks(c, blended_fv=c.current_price, upside=0.0)
    assert not any(x["code"] == "BALANCE_SHEET_MISMATCH" for x in checks)


# --- (8) SOURCE_CONFLICT: dấu vân tay, filing ưu tiên, trọng yếu theo ΔFV --------------------------


def _rec(value, item="total_assets", restated=False, y=2026, q=2):
    return N(
        statement="BS",
        fiscal_year=y,
        fiscal_quarter=q,
        line_item=item,
        is_restated=restated,
        value=value,
    )


def _audit(row, records):
    from valuation.ingest.taxonomy import source_fingerprint

    periods = {(2026, 2)}  # kỳ đã đối chiếu (fx1: dấu vân tay chỉ băm các kỳ này)
    return {
        "mapping_version": "v",
        "year_from": 2021,
        "rows": [
            {
                "ticker": "AAA",
                "audited_periods": [[2026, 2]],
                "db_fingerprint": source_fingerprint(records, 2021, periods),
                **row,
            }
        ],
    }


def test_audit_stale_when_db_changed_after_audit():
    records = [_rec(100.0), _rec(5.0, item="not_critical_item")]
    audit = _audit({"CRITICAL_CONFLICT": 2, "critical_fv_impact_pct": 9.0}, records)
    assert repo._source_audit_flags(audit, "AAA", "v", records) == ["SOURCE_CONFLICT:2"]
    assert repo._source_audit_flags(audit, "AAA", "v", [_rec(101.0), records[1]]) == [
        "SOURCE_AUDIT_STALE"
    ]
    # Ô ngoài danh sách trọng yếu hoặc trước year_from đổi → không làm audit cũ.
    assert repo._source_audit_flags(
        audit, "AAA", "v", [records[0], _rec(6.0, item="not_critical_item")]
    ) == ["SOURCE_CONFLICT:2"]
    old = {
        "mapping_version": "v",
        "rows": [{"ticker": "AAA"}],
    }  # audit chưa có dấu vân tay
    assert repo._source_audit_flags(old, "AAA", "v", records) == ["SOURCE_AUDIT_STALE"]


def test_source_conflict_downgraded_only_when_fv_impact_measured_small():
    records = [_rec(100.0)]
    # Ca tính tay: FV 21.460 → 21.459 khi dùng số nguồn: |21.459/21.460 − 1| = 0,0047% ≤ 1%.
    impact = abs(21_459 / 21_460 - 1) * 100
    assert impact == pytest.approx(0.0047, abs=1e-4)
    f = repo._source_audit_flags
    assert f(
        _audit({"CRITICAL_CONFLICT": 2, "critical_fv_impact_pct": impact}, records),
        "AAA",
        "v",
        records,
    ) == ["SOURCE_CONFLICT_IMMATERIAL:2"]
    assert f(
        _audit({"CRITICAL_CONFLICT": 2, "critical_fv_impact_pct": 2.5}, records),
        "AAA",
        "v",
        records,
    ) == ["SOURCE_CONFLICT:2"]
    assert f(_audit({"CRITICAL_CONFLICT": 2}, records), "AAA", "v", records) == [
        "SOURCE_CONFLICT:2"
    ]
    assert f(_audit({"FILING_PRECEDENCE": 17}, records), "AAA", "v", records) == [
        "FILING_PRECEDENCE:17"
    ]


def test_severity_of_new_source_flags():
    from valuation.report.verified_summary import run_deterministic_checks

    c = N(
        current_price=10.0,
        shares_outstanding=1.0,
        historical_is=[],
        historical_bs=[],
        ticker="AAA",
        data_flags=[
            "SOURCE_CONFLICT_IMMATERIAL:2",
            "FILING_PRECEDENCE:17",
            "FILING_BS_INCOMPLETE:2026Q2",
            "INCONSISTENT_YEAR_DROPPED:2018",
            "SOURCE_CONFLICT:1",
        ],
        sector="",
    )
    sev = {
        x["code"]: x["severity"]
        for x in run_deterministic_checks(c, blended_fv=10.0, upside=0.0)
    }
    assert sev["SOURCE_CONFLICT:1"] == "error"
    for code in (
        "SOURCE_CONFLICT_IMMATERIAL:2",
        "FILING_PRECEDENCE:17",
        "FILING_BS_INCOMPLETE:2026Q2",
        "INCONSISTENT_YEAR_DROPPED:2018",
    ):
        assert sev[code] == "warning"


def test_filing_precedence_status():
    import importlib.util

    from valuation.config import PROJECT_ROOT

    spec = importlib.util.spec_from_file_location(
        "audit_script", PROJECT_ROOT / "scripts/audit_vn100_data.py"
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    # PVT Q2/2026: DB 4.422,23 tỷ (BCTC soát xét, nguồn pvtrans.com) vs vendor 4.385,51.
    url = "https://pvtrans.com/web/content/document/download"
    item = "short_term_financial_investments"
    assert (
        audit.source_status(4_422.23e9, True, url, 4_385.51e9, item)
        == "FILING_PRECEDENCE"
    )
    assert (
        audit.source_status(4_422.23e9, False, "vnstock", 4_385.51e9, item)
        == "CRITICAL_CONFLICT"
    )
    assert audit.source_status(4_422.23e9, True, url, 4_422.23e9, item) == "MATCH"
