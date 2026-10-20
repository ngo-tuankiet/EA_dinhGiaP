"""Bước fx1 (20/10/2026): dữ liệu, audit nguồn, bảo mật — sửa các phát hiện của vòng phản biện.

Mỗi test tái hiện một lỗi đã kiểm chứng trên DB thật trước khi sửa; số liệu tính tay ghi trong comment.
"""

import datetime
import importlib.util
import json
import sqlite3
from types import SimpleNamespace as N

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from valuation.config import PROJECT_ROOT
from valuation.data_access import repo
from valuation.db.models import (
    CorporateAction,
    FinancialsQuarterly,
    PricesDaily,
    Ticker,
)
from valuation.db.session import Base


def _audit_script():
    spec = importlib.util.spec_from_file_location(
        "audit_script_fx1", PROJECT_ROOT / "scripts/audit_vn100_data.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mem_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# --- (1) Dấu vân tay chỉ băm các kỳ đã đối chiếu; kỳ mới → SOURCE_AUDIT_PARTIAL (warning) ---------


def _rec(value, y=2026, q=2, item="total_assets", restated=False):
    return N(
        statement="BS",
        fiscal_year=y,
        fiscal_quarter=q,
        line_item=item,
        is_restated=restated,
        value=value,
    )


def _audit_for(records, periods):
    from valuation.ingest.taxonomy import source_fingerprint

    return {
        "mapping_version": "v",
        "year_from": 2021,
        "rows": [
            {
                "ticker": "AAA",
                "audited_periods": [list(p) for p in sorted(periods)],
                "db_fingerprint": source_fingerprint(records, 2021, periods),
            }
        ],
    }


def test_new_period_after_audit_is_partial_not_stale():
    audited = [_rec(100.0, q=1), _rec(110.0, q=2)]
    audit = _audit_for(audited, {(2026, 1), (2026, 2)})
    assert repo._source_audit_flags(audit, "AAA", "v", audited) == []
    # Nạp BCTC Q3/2026 và BCTC năm 2026 sau audit: số đã đối chiếu không đổi → chỉ cảnh báo từng kỳ.
    later = audited + [_rec(120.0, q=3), _rec(121.0, q=0)]
    assert repo._source_audit_flags(audit, "AAA", "v", later) == [
        "SOURCE_AUDIT_PARTIAL:2026FY",
        "SOURCE_AUDIT_PARTIAL:2026Q3",
    ]


def test_changed_audited_cell_is_still_stale():
    audited = [_rec(100.0, q=1), _rec(110.0, q=2)]
    audit = _audit_for(audited, {(2026, 1), (2026, 2)})
    changed = [_rec(100.0, q=1), _rec(111.0, q=2), _rec(120.0, q=3)]
    assert repo._source_audit_flags(audit, "AAA", "v", changed) == [
        "SOURCE_AUDIT_STALE"
    ]
    # Audit cũ chưa lưu tập kỳ đã đối chiếu → không biết kỳ nào đã kiểm → STALE (chạy lại audit).
    old = json.loads(json.dumps(audit))
    del old["rows"][0]["audited_periods"]
    assert repo._source_audit_flags(old, "AAA", "v", audited) == ["SOURCE_AUDIT_STALE"]


def test_partial_flag_is_warning_stale_is_error():
    from valuation.report.verified_summary import run_deterministic_checks

    c = N(
        current_price=10.0,
        shares_outstanding=1.0,
        historical_is=[],
        historical_bs=[],
        ticker="AAA",
        sector="",
        data_flags=["SOURCE_AUDIT_PARTIAL:2026Q3", "SOURCE_AUDIT_STALE"],
    )
    sev = {
        x["code"]: x["severity"]
        for x in run_deterministic_checks(c, blended_fv=10.0, upside=0.0)
    }
    assert sev["SOURCE_AUDIT_PARTIAL:2026Q3"] == "warning"
    assert sev["SOURCE_AUDIT_STALE"] == "error"


# --- (3) FILING_PRECEDENCE: ngưỡng trọng yếu, allowlist nguồn, chỉ trên giá trị thực dùng ----------


_STFI = "short_term_financial_investments"


@pytest.mark.parametrize(
    "existing,source_url,source_value,item,expected",
    [
        # PVT Q2/2026 đầu tư ngắn hạn: filing 4.422,23 vs vendor 4.385,51 tỷ → 36,72/4.422,23 = 0,83% ≤ 5%.
        (
            4_422.23e9,
            "https://pvtrans.com/web/content/document/download",
            4_385.51e9,
            _STFI,
            "FILING_PRECEDENCE",
        ),
        # GAS Q2/2026 tồn kho: filing 5.134,99 vs vendor 5.661,27 → 526,28/5.661,27 = 9,30% > 5% → hiện
        # lại xung đột (tồn kho không thuộc publication_critical_items nên là INFORMATIONAL).
        (
            5_134.99e9,
            "https://www.pvgas.com.vn/DesktopModules/x",
            5_661.27e9,
            "inventories",
            "INFORMATIONAL_CONFLICT",
        ),
        # PVT Q2/2026 chi phí QLDN (mục trọng yếu): −97,51 vs −107,61 → 10,10/107,61 = 9,39% > 5%.
        (
            -97.51e9,
            "https://pvtrans.com/web/content/document/download",
            -107.61e9,
            "general_and_admin_expenses",
            "CRITICAL_CONFLICT",
        ),
        # Ngoài allowlist hoặc không https → không được coi là filing chính thức.
        (
            4_422.23e9,
            "https://evil.example.com/pvtrans.com",
            4_385.51e9,
            _STFI,
            "CRITICAL_CONFLICT",
        ),
        (
            4_422.23e9,
            "http://pvtrans.com/report.pdf",
            4_385.51e9,
            _STFI,
            "CRITICAL_CONFLICT",
        ),
        (
            4_422.23e9,
            "https://pvtrans.com.evil.io/x",
            4_385.51e9,
            _STFI,
            "CRITICAL_CONFLICT",
        ),
    ],
)
def test_filing_precedence_materiality_and_allowlist(
    existing, source_url, source_value, item, expected
):
    assert (
        _audit_script().source_status(existing, True, source_url, source_value, item)
        == expected
    )


def _payload(rows):
    return {
        "rows": rows,
        "attrs": {},
        "source": "test",
        "checked_at": "2026-09-01T00:00:00+07:00",
    }


def test_compare_source_uses_vendor_bs_when_filing_period_dropped(tmp_path):
    """PVT Q2/2026: BS filing thiếu tổng mục bị drop_incomplete_filing_bs loại → định giá dùng BS
    vendor → so nguồn phải đo trên số vendor (khớp), không tính FILING_PRECEDENCE cho ô filing.
    """
    from valuation.ingest.taxonomy import source_fingerprint

    audit = _audit_script()
    db = _mem_db()
    db.add(Ticker(ticker="ZZP", company_name="ZZP", is_vn100=False))
    url = "https://pvtrans.com/web/content/document/download"
    cells = [  # (item, restated, value tỷ)
        ("total_assets", False, 23_021.17),
        ("owners_equity", False, 12_180.96),
        ("total_assets", True, 23_064.49),
        ("owners_equity", True, 12_375.16),
    ]
    for item, restated, value in cells:
        db.add(
            FinancialsQuarterly(
                ticker="ZZP",
                fiscal_year=2026,
                fiscal_quarter=2,
                is_consolidated=True,
                is_restated=restated,
                statement="BS",
                line_item=item,
                value=value * 1e9,
                currency="VND",
                source=url if restated else "vnstock",
            )
        )
    db.commit()
    (tmp_path / "ZZP").mkdir()
    (tmp_path / "ZZP" / "BS.json").write_text(
        json.dumps(
            _payload(
                [
                    {
                        "id": "BS_TOTAL_ASSETS",
                        "unit": "VNĐ",
                        "period": "2026-Q2",
                        "value": 23_021.17e9,
                    },
                    {
                        "id": "BS_EQUITY",
                        "unit": "VNĐ",
                        "period": "2026-Q2",
                        "value": 12_180.96e9,
                    },
                ]
            )
        ),
        encoding="utf-8",
    )
    counts, _details = audit.compare_source(db, "ZZP", tmp_path, 2021)
    assert counts["MATCH"] == 2
    assert not counts.get("FILING_PRECEDENCE") and not counts.get("CONFLICT")
    assert counts["audited_periods"] == [[2026, 2]]
    records = db.query(FinancialsQuarterly).all()
    assert counts["db_fingerprint"] == source_fingerprint(records, 2021, {(2026, 2)})


# --- (2) Chỉ bỏ năm vi phạm đẳng thức IS nằm NGOÀI mọi cửa sổ mô hình ---------------------------


def test_inconsistent_year_drop_window_hand_cases():
    # TTM Q2/2026 → năm tài chính đầy đủ gần nhất 2025; cửa sổ biên 4 năm → chỉ bỏ năm < 2025 − 4 = 2021.
    assert repo.inconsistent_year_droppable(
        2018, latest_year=2026, latest_quarter=2, window=4
    )
    assert not repo.inconsistent_year_droppable(
        2021, latest_year=2026, latest_quarter=2, window=4
    )
    assert not repo.inconsistent_year_droppable(
        2025, latest_year=2026, latest_quarter=2, window=4
    )
    # Kỳ cuối là Q4 → năm 2026 đã đầy đủ: mốc 2026 − 4 = 2022.
    assert repo.inconsistent_year_droppable(
        2021, latest_year=2026, latest_quarter=4, window=4
    )


def _memory_copy_session(sql: str, params: tuple):
    from valuation.db.session import engine_read

    path = engine_read.url.database
    mem = sqlite3.connect(":memory:", check_same_thread=False)
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        src.backup(mem)
    finally:
        src.close()
    mem.execute(sql, params)
    mem.commit()
    eng = create_engine("sqlite://", creator=lambda: mem, poolclass=StaticPool)
    return sessionmaker(bind=eng)()


def test_latest_full_year_violating_gross_profit_identity_is_kept_and_blocks():
    """FPT FY2025 (tỷ): DT 70.113 − giá vốn 44.224 = 25.889 ≈ LN gộp 25.888. Tăng LN gộp 5% → 27.183:
    |27.183 − 25.889| / 27.183 = 4,8% > 0,5% → FY2025 phải giữ để GROSS_PROFIT_MISMATCH chặn công bố.
    """
    from valuation.report.verified_summary import run_deterministic_checks

    db = _memory_copy_session(
        "UPDATE financials_quarterly SET value = value * 1.05 WHERE ticker = ? AND fiscal_year = 2025 "
        "AND line_item = 'gross_profit'",
        ("FPT",),
    )
    try:
        c = repo.build_company_data(db, "FPT", peer_lookup=False)
    finally:
        db.close()
    assert not any(f.startswith("INCONSISTENT_YEAR_DROPPED") for f in c.data_flags)
    assert 2025 in [i.year for i in c.historical_is]
    checks = run_deterministic_checks(c, blended_fv=c.current_price, upside=0.0)
    gp = [x for x in checks if x["code"] == "GROSS_PROFIT_MISMATCH"]
    assert gp and gp[0]["severity"] == "error"


# --- (4) Bảo mật: mã mới không tự vào rổ VN100; route /ingest validate mã ------------------------


def test_run_ingest_default_does_not_add_ticker_to_vn100(monkeypatch):
    import pandas as pd

    from valuation.ingest import pipeline

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pipeline, "SessionLocalWrite", factory)
    monkeypatch.setattr(
        pipeline.vnstock_client,
        "get_company_overview",
        lambda _t: pd.DataFrame([{"organ_name": "New", "sector": "X"}]),
    )
    prices = pd.DataFrame(
        {
            "time": ["2026-10-19"],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1],
        }
    )
    monkeypatch.setattr(
        pipeline.vnstock_client, "get_historical_prices", lambda *_: prices
    )
    pipeline.run_ingest(
        "NEW", ["prices"], include_yearly=False, include_market_flows=False
    )
    with factory() as db:
        assert db.get(Ticker, "NEW").is_vn100 is False


@pytest.mark.parametrize(
    "raw,ok",
    [
        ("FPT", True),
        (" fpt ", True),  # VN100
        ("GEL", True),  # công ty con niêm yết khai trong sotp_holdings.yaml
        ("ZZZ", False),  # đúng định dạng nhưng ngoài whitelist
        ("FPT;DROP", False),
        ("../etc", False),
        ("", False),
        ("FPTT", False),
    ],
)
def test_ingest_route_validates_ticker(raw, ok):
    from pydantic import ValidationError

    from valuation.api.routes.ingest import IngestRequest

    if ok:
        assert IngestRequest(ticker=raw).ticker == raw.strip().upper()
    else:
        with pytest.raises(ValidationError):
            IngestRequest(ticker=raw)


def test_ingest_route_rejects_unknown_ticker_over_http(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import valuation.api.routes.ingest as route

    calls = []
    monkeypatch.setattr(route, "_run_ingest_job", lambda *a, **k: calls.append(a))
    app = FastAPI()
    app.include_router(route.router)
    client = TestClient(app)
    assert client.post("/ingest/", json={"ticker": "ZZZ"}).status_code == 422
    assert client.post("/ingest/", json={"ticker": "FPT"}).status_code == 200
    assert [a[0] for a in calls] == ["FPT"]


# --- (6) Quyền mua thiếu ngày GDKHQ: cờ riêng mức thông tin, không phải lỗi dữ liệu ----------------


def test_undated_rights_issue_has_own_info_flag(monkeypatch):
    from valuation.engine import ttm_helper
    from valuation.engine.flag_descriptions import describe_flags
    from valuation.views.vn100_ranking import DATA_FLAGS_EXTRA

    db = _mem_db()
    db.add(Ticker(ticker="ZZR", company_name="ZZR", is_vn100=True))
    db.add(
        CorporateAction(
            ticker="ZZR",
            source_site="t",
            source_event_id="r1",
            event_type="RIGHTS_ISSUE",
            title="quyền mua 20%",
            content_hash="r1",
            exercise_ratio=0.2,
            announcement_date=datetime.date(2026, 9, 1),
        )
    )
    db.commit()
    monkeypatch.setattr(ttm_helper, "_load_shares_events", list)
    flags = ttm_helper.undated_split_flags(db, "ZZR", datetime.date(2026, 10, 20))
    assert flags == ["RIGHTS_ISSUE_UNDATED"]
    assert "RIGHTS_ISSUE_UNDATED" not in DATA_FLAGS_EXTRA
    assert describe_flags(flags)[0]["level"] == "info"


# --- (5) Cập nhật công ty con SOTP thất bại → trạng thái tổng không được là SUCCESS ---------------


def test_weekly_status_reflects_sotp_subsidiary_failures(monkeypatch):
    import valuation.config as cfg_mod
    from valuation.ingest import weekly_updater

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(Ticker(ticker="HOLD", company_name="HOLD", is_vn100=True))
        db.commit()

    def fake_ingest(ticker, data_types, **kw):
        status = "FAILED" if ticker == "SUB" else "SUCCESS"
        return {"status": status, "prices": {"status": "UPDATED"}, "errors": []}

    monkeypatch.setattr(weekly_updater, "run_ingest", fake_ingest)
    monkeypatch.setattr(weekly_updater, "_CONSENSUS_SOURCES", ())
    monkeypatch.setattr(weekly_updater.time, "sleep", lambda _s: None)
    holdings = {"holders": {"HOLD": {"holdings": [{"ticker": "SUB"}]}}}
    monkeypatch.setattr(cfg_mod, "load_sotp_holdings", lambda: holdings)
    with factory() as db:
        out = weekly_updater.run_weekly_auto_update(db)
    assert out["sotp_subs"] == {"SUB": "FAILED"}
    assert out["status"] == "PARTIAL"
    assert "SOTP" in out["message"]


# --- (7) Thuế: giữ dấu lợi ích thuế; mẫu số thuế hiệu dụng loại lãi/lỗ liên doanh ------------------


def test_tax_benefit_keeps_sign_baf_2023():
    """BAF FY2023 (tỷ): nguồn ghi thuế TNDN +5,81 (lợi ích, quy ước âm = chi phí); LNTT 24,52;
    LNST 30,33 = 24,52 + 5,81 → chi phí thuế = −5,81, không phải +5,81."""
    b = 1e9
    data = {
        "attributable_to_parent_company": 30.33 * b,
        "net_sales": 1_000.0 * b,
        "cost_of_sales": -900.0 * b,
        "gross_profit": 100.0 * b,
        "selling_expenses": -10.0 * b,
        "general_and_admin_expenses": -20.0 * b,
        "corporate_income_tax_expenses": 5.81 * b,
    }
    assert repo._nonfinancial_income_values(data)["tax"] == pytest.approx(-5.81 * b)
    data["corporate_income_tax_expenses"] = -51.10 * b  # BAF 2022: chi phí thuế 51,10
    assert repo._nonfinancial_income_values(data)["tax"] == pytest.approx(51.10 * b)


def _is(year, tax, pbt, jv=0.0):
    from valuation.models.financials import IncomeStatement

    return IncomeStatement(
        year=year,
        revenue=1.0,
        cogs=0.0,
        gross_profit=1.0,
        opex=0.0,
        ebit=1.0,
        interest_expense=0.0,
        tax=tax,
        net_income=1.0,
        pbt=pbt,
        jv_income=jv,
    )


def test_effective_tax_signed_baf():
    # BAF FY2023–2025: thuế −5,81 + 87,31 − 27,29 = 54,21; LNTT 24,52 + 406,25 + 99,84 = 530,61
    # → 10,22% (abs cũ: 120,41 / 530,61 = 22,69%).
    hist = [_is(2023, -5.81, 24.52), _is(2024, 87.31, 406.25), _is(2025, -27.29, 99.84)]
    assert repo.effective_tax_rate(hist) == pytest.approx(54.21 / 530.61)
    assert repo.effective_tax_rate(hist) == pytest.approx(0.1022, abs=1e-4)


def test_effective_tax_excludes_jv_income_from_denominator_gmd():
    # GMD FY2023–2025 (tỷ): thuế 613,55 + 175,01 + 218,30 = 1.006,86; LNTT − lãi LD/LK:
    # (3.147,49 − 274,23) + (2.098,59 − 829,31) + (2.520,83 − 1.157,66) = 5.505,71 → 18,29%
    # (mẫu số gồm lãi LD/LK cũ: 1.006,86 / 7.766,91 = 12,96%).
    hist = [
        _is(2023, 613.55, 3_147.49, 274.23),
        _is(2024, 175.01, 2_098.59, 829.31),
        _is(2025, 218.30, 2_520.83, 1_157.66),
    ]
    assert repo.effective_tax_rate(hist) == pytest.approx(1_006.86 / 5_505.71)
    assert repo.effective_tax_rate(hist) == pytest.approx(0.1829, abs=1e-4)
    # Năm chỉ có lãi LD/LK (LNTT − LD ≤ 0) không có thu nhập chịu thuế → bỏ khỏi cửa sổ.
    assert (
        repo.effective_tax_rate([_is(2024, 1.0, 100.0, 120.0), _is(2025, 20.0, 100.0)])
        is None
    )


# --- (8) as_of quá khứ: số cp quy về cùng gốc với giá đã điều chỉnh lùi --------------------------


def _shares_db(events, overrides_ok=True):
    """Mã ZZS: vốn điều lệ 50.052.763.230.000đ (5.005,28 tr cp) ở 4 quý tới Q2/2026, giá tới 19/10/2026."""
    db = _mem_db()
    db.add(Ticker(ticker="ZZS", company_name="ZZS", is_vn100=True))
    for y, q in ((2025, 3), (2025, 4), (2026, 1), (2026, 2)):
        db.add(
            FinancialsQuarterly(
                ticker="ZZS",
                fiscal_year=y,
                fiscal_quarter=q,
                is_consolidated=True,
                is_restated=False,
                statement="BS",
                line_item="paid_in_capital",
                value=50_052_763_230_000,
                currency="VND",
            )
        )
    for d in (datetime.date(2026, 9, 28), datetime.date(2026, 10, 19)):
        db.add(PricesDaily(ticker="ZZS", trade_date=d, close=21_150))
    for i, (etype, ratio, ex) in enumerate(events):
        db.add(
            CorporateAction(
                ticker="ZZS",
                source_site="t",
                source_event_id=f"e{i}",
                event_type=etype,
                title=etype,
                content_hash=f"e{i}",
                exercise_ratio=ratio,
                ex_right_date=ex,
                announcement_date=datetime.date(2026, 9, 1),
            )
        )
    db.commit()
    return db


HDB_EVENTS = [
    ("STOCK_DIVIDEND", 0.25, datetime.date(2026, 10, 9)),
    ("BONUS_SHARE", 0.05, datetime.date(2026, 10, 9)),
]


def test_as_of_shares_on_adjusted_price_basis_hdb(monkeypatch):
    """HDB: cổ tức CP 25% + thưởng 5% cùng GDKHQ 09/10/2026 (cùng gốc cp → +30%, không 1,25 × 1,05).
    Giá 28/09 trong DB đã chia lùi → số cp tại as_of 28/09 phải × 1,30: 5.005,28 × 1,30 = 6.506,86 tr.
    """
    from valuation.engine import ttm_helper

    monkeypatch.setattr(ttm_helper, "_load_shares_events", list)
    db = _shares_db(HDB_EVENTS)
    as_of = datetime.date(2026, 9, 28)
    assert repo.get_shares_outstanding_repo(db, "ZZS", as_of=as_of) == pytest.approx(
        5_005.276323 * 1.30
    )
    # Số cp thật tại as_of (không quy gốc giá) giữ nguyên — chống lookahead ở nơi khác.
    assert ttm_helper.get_shares_outstanding(
        db, "ZZS", as_of_date=as_of
    ) == pytest.approx(5_005_276_323)


def test_as_of_override_path_also_rebased(monkeypatch):
    """Số cp ghi đè (VSDC) hiệu lực trước as_of + sự kiện chia sau as_of: GMD 432,89 tr cp (11/08/2026),
    thưởng 50% GDKHQ 07/10/2026 → tại as_of 28/09 quy gốc giá = 432,89 × 1,5 = 649,34 tr.
    """
    from valuation.engine import ttm_helper

    monkeypatch.setattr(
        ttm_helper,
        "_load_shares_events",
        lambda: [
            {
                "ticker": "ZZS",
                "effective_date": "2026-08-11",
                "shares_outstanding": 432_892_509,
            }
        ],
    )
    db = _shares_db([("BONUS_SHARE", 0.5, datetime.date(2026, 10, 7))])
    got = repo.get_shares_outstanding_repo(db, "ZZS", as_of=datetime.date(2026, 9, 28))
    assert got == pytest.approx(432.892509 * 1.5)


def test_rights_issue_after_as_of_not_in_factor(monkeypatch):
    """Quyền mua có ngày GDKHQ (kèm tiền, chờ BCTC) không vào hệ số chia → hệ số = 1."""
    from valuation.engine import ttm_helper

    monkeypatch.setattr(ttm_helper, "_load_shares_events", list)
    db = _shares_db([("RIGHTS_ISSUE", 0.2, datetime.date(2026, 10, 9))])
    got = repo.get_shares_outstanding_repo(db, "ZZS", as_of=datetime.date(2026, 9, 28))
    assert got == pytest.approx(5_005.276323)
