"""Bước r3b (20/10/2026): audit nguồn, registry hiệu chuẩn, snapshot config, mức cờ — phản biện vòng 2.

Mỗi test tái hiện một phát hiện (journal wf_677a6cd6-b37) TRƯỚC khi sửa; số tính tay ghi trong comment.
"""

import datetime
import importlib.util
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from valuation.config import PROJECT_ROOT
from valuation.data_access import repo
from valuation.db.models import FinancialsQuarterly, Ticker
from valuation.db.session import Base


def _audit_script():
    spec = importlib.util.spec_from_file_location(
        "audit_script_r3b", PROJECT_ROOT / "scripts/audit_vn100_data.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mem_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _fq(ticker, q, item, value_ty):
    return FinancialsQuarterly(
        ticker=ticker,
        fiscal_year=2026,
        fiscal_quarter=q,
        is_consolidated=True,
        is_restated=False,
        statement="BS",
        line_item=item,
        value=value_ty * 1e9,
        currency="VND",
        source="vnstock",
    )


def _bs_cache(root, ticker, rows):
    (root / ticker).mkdir()
    payload = {
        "rows": [
            {"id": i, "unit": "VNĐ", "period": p, "value": v * 1e9} for i, p, v in rows
        ],
        "attrs": {},
        "source": "test",
        "checked_at": "2026-09-01T00:00:00+07:00",
    }
    (root / ticker / "BS.json").write_text(json.dumps(payload), encoding="utf-8")


# --- (1) Kỳ chỉ có ở cache nguồn (DB chưa có ô) KHÔNG được coi là đã đối chiếu -------------------------


def test_source_ahead_period_is_partial_not_stale_after_db_loads_it(tmp_path):
    """Cache nguồn đi trước DB (có Q3/2026, DB mới tới Q2). Trước sửa: audit ghi Q3 vào audited_periods
    và băm dấu trên tập kỳ đó khi DB chưa có ô Q3 → nạp Q3 xong dấu đổi → SOURCE_AUDIT_STALE (chặn nhầm,
    dù số đã đối chiếu không đổi và số Q3 chưa từng so nguồn). Đúng: Q3 chưa đối chiếu → PARTIAL.
    """
    from valuation.ingest.taxonomy import taxonomy_mapping

    audit = _audit_script()
    db = _mem_db()
    db.add(Ticker(ticker="ZZA", company_name="ZZA", is_vn100=False))
    db.add_all(
        [_fq("ZZA", 2, "total_assets", 1_000.0), _fq("ZZA", 2, "owners_equity", 400.0)]
    )
    db.commit()
    _bs_cache(
        tmp_path,
        "ZZA",
        [
            ("BS_TOTAL_ASSETS", "2026-Q2", 1_000.0),
            ("BS_EQUITY", "2026-Q2", 400.0),
            ("BS_TOTAL_ASSETS", "2026-Q3", 1_100.0),
            ("BS_EQUITY", "2026-Q3", 420.0),
        ],
    )
    counts, _ = audit.compare_source(db, "ZZA", tmp_path, 2021)
    assert counts["MATCH"] == 2 and counts["NO_MATCHING_KEY"] == 2
    assert counts["audited_periods"] == [[2026, 2]]

    mapping = taxonomy_mapping()["version"]
    status = {
        "mapping_version": mapping,
        "year_from": 2021,
        "rows": [{"ticker": "ZZA", **counts}],
    }
    # Nạp Q3 vào bản sao DB trong bộ nhớ (số Q2 giữ nguyên).
    db.add_all(
        [_fq("ZZA", 3, "total_assets", 1_100.0), _fq("ZZA", 3, "owners_equity", 420.0)]
    )
    db.commit()
    records = db.query(FinancialsQuarterly).all()
    assert repo._source_audit_flags(status, "ZZA", mapping, records) == [
        "SOURCE_AUDIT_PARTIAL:2026Q3"
    ]


def test_period_with_only_non_critical_match_is_not_audited(tmp_path):
    """Kỳ chỉ khớp ô KHÔNG trọng yếu → không có ô trọng yếu nào được so nguồn → không phải 'đã đối chiếu'."""
    audit = _audit_script()
    db = _mem_db()
    db.add(Ticker(ticker="ZZB", company_name="ZZB", is_vn100=False))
    # 'inventories' (BS_INVENTORIES_GROSS) không thuộc publication_critical_items.
    db.add_all(
        [_fq("ZZB", 2, "total_assets", 1_000.0), _fq("ZZB", 3, "inventories", 5.0)]
    )
    db.commit()
    _bs_cache(
        tmp_path,
        "ZZB",
        [
            ("BS_TOTAL_ASSETS", "2026-Q2", 1_000.0),
            ("BS_INVENTORIES_GROSS", "2026-Q3", 5.0),
        ],
    )
    counts, _ = audit.compare_source(db, "ZZB", tmp_path, 2021)
    assert counts["audited_periods"] == [[2026, 2]]


# --- (2) audit --tickers khi chưa có source_audit.json: gộp với status portable, không ghi đè -----------


def test_partial_audit_base_falls_back_to_portable_status(tmp_path):
    mod = _audit_script()
    status = {"mapping_version": "v1", "year_from": 2021, "rows": [{"ticker": "AAA"}]}
    (tmp_path / "data").mkdir()
    (tmp_path / "data/source_quality_status.json").write_text(
        json.dumps(status), encoding="utf-8"
    )
    # Máy mới / bản portable: chỉ có file status được commit → dùng nó làm nền gộp.
    assert mod.partial_audit_base(tmp_path) == status
    full = {**status, "differences": [{"ticker": "AAA"}]}
    (tmp_path / ".vn100_ranking/sponsor").mkdir(parents=True)
    (tmp_path / ".vn100_ranking/sponsor/source_audit.json").write_text(
        json.dumps(full), encoding="utf-8"
    )
    assert mod.partial_audit_base(tmp_path) == full


def test_partial_audit_without_any_saved_audit_requires_full_run():
    mod = _audit_script()
    with pytest.raises(ValueError, match="đầy đủ"):
        mod.partial_audit_year_from(None, "v1", 2022)
    with pytest.raises(ValueError, match="đầy đủ"):
        mod.merge_partial_audit(None, [{"ticker": "BBB"}], [])


def test_partial_audit_merges_into_portable_status_without_differences():
    mod = _audit_script()
    status = {
        "mapping_version": "v1",
        "year_from": 2021,
        "rows": [{"ticker": "AAA", "MATCH": 5}, {"ticker": "BBB", "MATCH": 1}],
    }
    assert mod.partial_audit_year_from(status, "v1", 2022) == 2021
    rows, diffs = mod.merge_partial_audit(
        status, [{"ticker": "BBB", "MATCH": 9}], [{"ticker": "BBB", "field": "new"}]
    )
    assert rows == [{"ticker": "AAA", "MATCH": 5}, {"ticker": "BBB", "MATCH": 9}]
    assert diffs == [{"ticker": "BBB", "field": "new"}]


# --- (3) SOURCE_AUDIT_PARTIAL có giới hạn: quá audit.max_unaudited_periods kỳ → SOURCE_AUDIT_STALE --------


def _rec(value, q, y=2026):
    from types import SimpleNamespace as N

    return N(
        statement="BS",
        fiscal_year=y,
        fiscal_quarter=q,
        line_item="total_assets",
        is_restated=False,
        value=value,
    )


def _capped_audit():
    from valuation.ingest.taxonomy import source_fingerprint

    audited = [_rec(100.0, 1), _rec(110.0, 2)]
    periods = {(2026, 1), (2026, 2)}
    audit = {
        "mapping_version": "v",
        "year_from": 2021,
        "rows": [
            {
                "ticker": "AAA",
                "audited_periods": [list(p) for p in sorted(periods)],
                "db_fingerprint": source_fingerprint(audited, 2021, periods),
            }
        ],
    }
    return audit, audited


def _pending(n):
    """n kỳ quý nạp SAU audit (2026Q3, 2026Q4, 2027Q1, …) cùng nhãn kỳ tương ứng."""
    qs = [(2026 + (2 + k) // 4, (2 + k) % 4 + 1) for k in range(n)]
    return [_rec(200.0 + k, q, y) for k, (y, q) in enumerate(qs)], [
        f"{y}Q{q}" for y, q in qs
    ]


def test_unaudited_periods_capped_by_config():
    from valuation.config import load_defaults

    # r4a: ngưỡng ĐỌC từ config (đang chờ phi duyệt) rồi sinh ca biên — không khoá cứng giá trị.
    cap = int(load_defaults()["audit"]["max_unaudited_periods"])
    audit, audited = _capped_audit()
    f = repo._source_audit_flags
    # Đúng cap kỳ chưa đối chiếu → cảnh báo từng kỳ (PARTIAL).
    recs, labels = _pending(cap)
    assert f(audit, "AAA", "v", audited + recs) == [
        f"SOURCE_AUDIT_PARTIAL:{x}" for x in labels
    ]
    # cap + 1 kỳ → chặn như audit lỗi thời (TTM/FV dựa trên số chưa từng so nguồn).
    recs, labels = _pending(cap + 1)
    assert f(audit, "AAA", "v", audited + recs) == [
        "SOURCE_AUDIT_STALE:" + ",".join(labels)
    ]
    # Ca tay theo nhãn: Q3 + Q4 + FY2026 (3 kỳ) — FY xếp trước quý trong nhãn (q = 0).
    three = audited + [_rec(120.0, 3), _rec(130.0, 4), _rec(131.0, 0)]
    expected = (
        ["SOURCE_AUDIT_STALE:2026FY,2026Q3,2026Q4"]
        if cap < 3
        else [f"SOURCE_AUDIT_PARTIAL:{x}" for x in ("2026FY", "2026Q3", "2026Q4")]
    )
    assert f(audit, "AAA", "v", three) == expected


def test_unaudited_periods_cap_follows_config_override(monkeypatch):
    from valuation.config import load_defaults

    monkeypatch.setitem(load_defaults()["audit"], "max_unaudited_periods", 0)
    audit, audited = _capped_audit()
    assert repo._source_audit_flags(audit, "AAA", "v", audited + [_rec(120.0, 3)]) == [
        "SOURCE_AUDIT_STALE:2026Q3"
    ]


def test_capped_partial_is_error_in_checks():
    from types import SimpleNamespace as N

    from valuation.report.verified_summary import run_deterministic_checks

    c = N(
        current_price=10.0,
        shares_outstanding=1.0,
        historical_is=[],
        historical_bs=[],
        ticker="AAA",
        sector="",
        data_flags=["SOURCE_AUDIT_STALE:2026FY,2026Q3,2026Q4"],
    )
    sev = {
        x["code"]: x["severity"]
        for x in run_deterministic_checks(c, blended_fv=10.0, upside=0.0)
    }
    assert sev["SOURCE_AUDIT_STALE:2026FY,2026Q3,2026Q4"] == "error"


# --- (4) Registry ở mốc hôm nay ---------------------------------------------------------------------------


def test_registry_entries_well_formed():
    """r4a: chỉ kiểm CẤU TRÚC (status hợp lệ, có owner, có reviewed_on) — không khoá mã/owner/
    ngày cụ thể, để phi duyệt (đổi owner/ngày/trạng thái) không làm đỏ suite."""
    from valuation.calibration.registry import (
        STATUS_DATA_BLOCKED,
        STATUS_JUSTIFIED,
        STATUS_MUST_FIX,
        load_registry,
    )

    reg = load_registry()
    assert reg
    for ticker, entry in reg.items():
        assert entry.status in {
            STATUS_JUSTIFIED,
            STATUS_MUST_FIX,
            STATUS_DATA_BLOCKED,
        }, ticker
        assert entry.owner and entry.owner.strip(), ticker
        assert isinstance(entry.reviewed_on, datetime.date), ticker


# --- (5) Snapshot config của calibration phủ mọi khóa engine đọc ------------------------------------------


def test_engine_config_snapshot_has_new_keys():
    from valuation.calibration.harness import _ENGINE_CONFIG_KEYS

    for key in (
        "relative_multiples",
        "publication_gate",
        "audit",
        "peer_multiples",
        "insurance",
        "guardrails",
        "corporate_actions",
        "publication_lag_days",
    ):
        assert key in _ENGINE_CONFIG_KEYS


# --- (6) Mức cờ khớp cổng công bố -------------------------------------------------------------------------


def test_blocking_and_error_prefix_flags_are_error_level():
    from valuation.engine.flag_descriptions import FLAG_DESCRIPTIONS
    from valuation.engine.valuate import PUBLICATION_BLOCKING_FLAGS
    from valuation.report.verified_summary import DATA_FLAG_ERROR_PREFIXES

    codes = set(PUBLICATION_BLOCKING_FLAGS) | {
        p.split(":", 1)[0] for p in DATA_FLAG_ERROR_PREFIXES
    }
    assert {
        "VALUATION_PROXY",
        "STALE_PRICE",
        "UPSIDE_EXTREME_REVIEW",
        "MISSING_FINANCIAL_INPUT",
    } <= codes
    wrong = {c: FLAG_DESCRIPTIONS.get(c, {}).get("level") for c in codes}
    wrong = {c: lvl for c, lvl in wrong.items() if lvl != "error"}
    assert not wrong, f"Cờ chặn công bố / lỗi dữ liệu nhưng level khác 'error': {wrong}"
