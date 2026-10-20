"""Bước r4b (20/10/2026, quyết định phi Q3/Q4): audit nguồn cho công ty con SOTP ngoài VN100; MSN cộng MSR/MML.

Q3: collect_sponsor_data.py / audit_vn100_data.py nhận thêm mã công ty con khai trong config/sotp_holdings.yaml
(whitelist + regex), audit --tickers gộp không ghi đè mã khác (số dòng status = cũ + mới).
Q4: MSN holdings thêm MSR 92,89% và MML 94,3% (thị giá), reviewed_by để trống cho người dùng rà.
Test viết TRƯỚC khi sửa.
"""

import importlib.util
import json

import pytest

from valuation.config import PROJECT_ROOT, sotp_holdings_for
from valuation.ingest import universe

SUBS = {"GEL", "VSH", "TBC", "TMP", "HHS", "MSR", "MML"}


def _script(name: str):
    spec = importlib.util.spec_from_file_location(
        f"r4b_{name}", PROJECT_ROOT / f"scripts/{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Q3: phạm vi mã của collect/audit ------------------------------------------------------------


def test_audit_universe_is_vn100_then_sotp_subsidiaries():
    allowed = universe.audit_universe()
    assert allowed[:100] == universe.get_vn100_symbols()
    assert SUBS <= set(allowed[100:])
    assert len(allowed) == len(set(allowed))


def test_audit_universe_rejects_malformed_config_ticker(monkeypatch):
    # config/sotp_holdings.yaml cũng là đầu vào: mã sai định dạng không được đi tới API nguồn / đường dẫn cache.
    monkeypatch.setattr(
        "valuation.config.sotp_holding_tickers", lambda: {"GEL", "GE/L"}
    )
    with pytest.raises(ValueError, match="GE/L"):
        universe.audit_universe()


@pytest.mark.parametrize(
    "requested,ok",
    [
        (None, True),
        ([], True),
        (["GEL", "MSR"], True),
        (["FPT", "HHS"], True),
        (["ZZZ"], False),  # đúng định dạng nhưng không thuộc VN100 ∪ công ty con
        (["gel"], False),
        (["../GEL"], False),
    ],
)
def test_select_audit_tickers_whitelist(requested, ok):
    if ok:
        got = universe.select_audit_tickers(requested)
        assert got == (requested or universe.audit_universe())
    else:
        with pytest.raises(ValueError, match="ngoài"):
            universe.select_audit_tickers(requested)


@pytest.mark.parametrize("script", ["collect_sponsor_data", "audit_vn100_data"])
def test_scripts_reject_ticker_outside_whitelist(script, monkeypatch):
    mod = _script(script)
    monkeypatch.setattr("sys.argv", [script, "--tickers", "ZZZ"])
    with pytest.raises(SystemExit):
        mod.main()


def test_collect_accepts_sotp_subsidiary(tmp_path, monkeypatch):
    """GEL (công ty con GEX, ngoài VN100) đi tới bước tải nguồn; nguồn giả để không gọi API trong test."""
    mod = _script("collect_sponsor_data")
    calls = []

    def fake_collect(ticker, kind, start, end, now, root):
        calls.append((ticker, kind))
        return {"status": "cached", "rows": 1}

    monkeypatch.setattr(mod, "collect_sponsor_dataset", fake_collect)
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["collect_sponsor_data", "--tickers", "GEL", "--financials"]
    )
    mod.main()
    assert {k for t, k in calls if t == "GEL"} >= {
        "BS",
        "IS",
        "CF",
        "BS_FY",
        "IS_FY",
        "CF_FY",
    }
    status = json.loads(
        (tmp_path / ".vn100_ranking/sponsor/collection_status.json").read_text()
    )
    assert {r["ticker"] for r in status["results"]} == {"GEL"}


def _saved_status(mapping: str) -> dict:
    return {
        "checked_at": "2026-10-20T03:28:57+07:00",
        "mapping_version": mapping,
        "year_from": 2021,
        "rows": [
            {
                "ticker": t,
                "MATCH": 7,
                "audited_periods": [[2026, 2]],
                "db_fingerprint": f"fp-{t}",
            }
            for t in universe.get_vn100_symbols()
        ],
    }


def test_audit_tickers_subsidiary_merges_rows_old_plus_new(tmp_path, monkeypatch):
    """--tickers GEL: status sau = 100 dòng cũ (giữ nguyên từng dòng) + 1 dòng GEL."""
    mod = _script("audit_vn100_data")
    mapping = mod.taxonomy_mapping()["version"]
    saved = _saved_status(mapping)
    (tmp_path / "data").mkdir()
    (tmp_path / "data/source_quality_status.json").write_text(
        json.dumps(saved), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        mod,
        "compare_source",
        lambda db, t, root, yf: (
            {"MATCH": 3, "audited_periods": [[2026, 2]], "db_fingerprint": "fp-new"},
            [],
        ),
    )
    monkeypatch.setattr(mod, "attach_valuation", lambda row: None)
    monkeypatch.setattr(
        "sys.argv",
        ["audit_vn100_data", "--tickers", "GEL", "--output", str(tmp_path / "out")],
    )
    mod.main()
    after = json.loads((tmp_path / "data/source_quality_status.json").read_text())
    assert len(after["rows"]) == len(saved["rows"]) + 1
    by_t = {r["ticker"]: r for r in after["rows"]}
    assert by_t["GEL"]["db_fingerprint"] == "fp-new"
    for old in saved["rows"]:
        assert by_t[old["ticker"]]["db_fingerprint"] == old["db_fingerprint"]
    assert after["year_from"] == 2021


def test_audit_finalize_accepts_vn100_plus_subsidiary_rows(tmp_path, monkeypatch):
    """--finalize-existing: audit đã lưu có 100 mã VN100 + công ty con là audit đủ (trước: đòi đúng 100 dòng)."""
    mod = _script("audit_vn100_data")
    saved = _saved_status(mod.taxonomy_mapping()["version"])
    saved["rows"].append(
        {
            "ticker": "GEL",
            "MATCH": 3,
            "audited_periods": [[2026, 2]],
            "db_fingerprint": "g",
        }
    )
    saved["differences"] = []
    sponsor = tmp_path / ".vn100_ranking/sponsor"
    sponsor.mkdir(parents=True)
    (sponsor / "source_audit.json").write_text(json.dumps(saved), encoding="utf-8")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(mod, "attach_valuation", lambda row: None)
    monkeypatch.setattr(
        "sys.argv",
        ["audit_vn100_data", "--finalize-existing", "--output", str(tmp_path / "o")],
    )
    mod.main()
    after = json.loads((tmp_path / "data/source_quality_status.json").read_text())
    assert len(after["rows"]) == 101
    # Thiếu một mã VN100 vẫn là audit chưa đủ.
    saved["rows"] = [r for r in saved["rows"] if r["ticker"] != "FPT"]
    (sponsor / "source_audit.json").write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.main()


# --- Q4: MSN cộng MSR, MML theo thị giá (owner phi) ---------------------------------------------


def test_msn_holds_msr_and_mml_structure():
    """Stake MSR/MML đang chờ phi rà (sotp_review_table) → chỉ kiểm cấu trúc, không khoá trị số hay trạng thái
    duyệt (fin_a, phản biện r4: test khoá reviewed_by trống sẽ đỏ đúng lúc phi duyệt).
    """
    held = {h["ticker"]: h for h in sotp_holdings_for("MSN")["holdings"]}
    for t in ("MSR", "MML"):
        h = held[t]
        assert 0 < h["stake"] <= 1
        assert str(h["source"]).startswith("https://") and h.get("source_date")


@pytest.mark.parametrize(
    "reviewed_by,as_of,unverified",
    [(None, None, True), ("phi", None, True), ("phi", "2026-10-20", False)],
)
def test_msn_review_gate_behaviour(reviewed_by, as_of, unverified):
    """Hành vi cổng trên đúng danh sách holdings MSN trong config: chưa duyệt (hoặc thiếu ngày duyệt) →
    SOTP_HOLDINGS_UNVERIFIED (chặn); có reviewed_by + as_of hợp lệ → không cờ."""
    from tests.test_sotp_holdings import _cfg, _holding, _model

    holdings = [
        _holding(h["ticker"], h["stake"], 10_000.0, bv=5_000.0)
        for h in sotp_holdings_for("MSN")["holdings"]
    ]
    flags = _model(
        _cfg(holdings, reviewed_by=reviewed_by, as_of=as_of)
    ).perform_valuation()["flags"]
    assert ("SOTP_HOLDINGS_UNVERIFIED" in flags) is unverified
    assert "SOTP_HOLDINGS_STALE" not in flags
