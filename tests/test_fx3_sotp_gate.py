"""Bước fx3 (20/10/2026): SOTP_HOLDINGS & cổng công bố — sửa các phát hiện của vòng phản biện.

Mỗi test tái hiện một lỗi đã kiểm chứng trên DB thật trước khi sửa (GEL, VSH, TBC, TMP, HHS mang
SOURCE_AUDIT_MISSING mức error nhưng GEX/REE/TCH không bị chặn vì lý do đó).
"""

import datetime
import importlib.util
from types import SimpleNamespace as N

import pytest

import valuation.config as cfg_mod
from valuation.config import PROJECT_ROOT, sotp_holdings_for
from valuation.data_access import repo
from valuation.engine.models.sotp import SOTPValuationModel


def _sub(ticker="GELX", flags=(), total_le=1_000.0):
    """Công ty con giả đủ trường cho run_deterministic_checks (đơn vị tỷ đồng)."""
    is_row = N(
        year=2025,
        revenue=1_000.0,
        cogs=600.0,
        gross_profit=400.0,
        ebit=300.0,
        opex=100.0,
    )
    bs_row = N(
        year=2025,
        total_assets=1_000.0,
        total_liabilities_and_equity=total_le,
        parent_equity=500.0,
    )
    return N(
        ticker=ticker,
        sector="",
        current_price=20_000.0,
        shares_outstanding=100.0,
        data_flags=list(flags),
        warnings=[],
        historical_is=[is_row],
        historical_bs=[bs_row],
    )


def _entry(*tickers):
    return {
        "as_of": None,
        "reviewed_by": None,
        "review_ttl_days": 180,
        "holdings": [
            {"ticker": t, "stake": 0.5, "source": "https://x"} for t in tickers
        ],
    }


# --- (1) Lỗi dữ liệu mức error của công ty con phải chặn mã mẹ -------------------------------------


def test_resolve_holdings_carries_subsidiary_error_checks(monkeypatch):
    subs = {
        "GELX": _sub("GELX", ["SOURCE_AUDIT_MISSING", "CORPORATE_ACTION_UNDATED"]),
        "BSX": _sub(
            "BSX", total_le=900.0
        ),  # tổng tài sản 1.000 ≠ nguồn vốn 900 → lệch 11% > 0,5%
        "STLX": _sub("STLX", ["STALE_PRICE"]),
        "OKX": _sub("OKX"),
    }
    monkeypatch.setattr(cfg_mod, "sotp_holdings_for", lambda t: _entry(*subs))
    monkeypatch.setattr(repo, "build_company_data", lambda db, t, **kw: subs[t])
    rows = {
        h["ticker"]: h for h in repo.resolve_sotp_holdings(None, "HOLDX")["holdings"]
    }
    assert rows["GELX"]["data_errors"] == [
        "SOURCE_AUDIT_MISSING"
    ]  # cảnh báo không chuyển lên
    assert rows["BSX"]["data_errors"] == ["BALANCE_SHEET_MISMATCH"]
    # Giá cũ đi đường riêng (SOTP_HOLDINGS_STALE), không nhân đôi thành lỗi dữ liệu.
    assert rows["STLX"]["data_errors"] == [] and rows["STLX"]["price_stale"] is True
    assert rows["OKX"]["data_errors"] == []
    # Vốn hóa vẫn tính để truy vết: 20.000đ × 100 tr cp / 1000 = 2.000 tỷ.
    assert rows["OKX"]["market_cap_bn"] == pytest.approx(2_000.0)


def _holding(ticker, stake, mc, bv, **over):
    return {
        "ticker": ticker,
        "stake": stake,
        "market_cap_bn": mc,
        "book_equity_bn": bv,
        "carrying_value_bn": None,
        "price_stale": False,
        "source": "https://x",
        **over,
    }


def _cfg(holdings, reviewed_by="phi", as_of="2026-10-01"):
    return {
        "as_of": as_of,
        "reviewed_by": reviewed_by,
        "review_ttl_days": 180,
        "valuation_date": "2026-10-20",
        "holdings": holdings,
    }


def _model(cfg):
    cf = {
        "total_equity": 40_000e9,
        "cash_and_equivalents": 0.0,
        "total_debt": 0.0,
        "minority_interest": 0.0,
        "net_income_history": [1_000.0] * 3,
        "shares_outstanding": 1_000e6,
        "current_price": 50_000.0,
    }
    a = {
        "sotp_operating_pe": 11.0,
        "sotp_earnings_weight": 0.6,
        "sotp_holding_discount": 0.10,
        "sotp_segments": [],
        "sotp_holdings": cfg,
    }
    return SOTPValuationModel("HOLDX", cf, a)


def test_holdings_value_flags_subsidiary_data_error_without_changing_fv():
    # FV không đổi: (40.000 + 0,5 × 10.000 − 0,5 × 8.000) / 1.000 tr cp × 1000 × 0,9 = 36.900đ
    bad = _holding(
        "GELX",
        0.5,
        10_000.0,
        8_000.0,
        data_errors=["SOURCE_AUDIT_MISSING", "SOURCE_CONFLICT:2"],
    )
    ok = _holding("OKX", 0.5, 10_000.0, 8_000.0, data_errors=[])
    res = _model(_cfg([bad])).perform_valuation()
    assert res["blended_fair_value_per_share"] == pytest.approx(36_900.0)
    assert (
        "SOTP_SUBSIDIARY_DATA_ERROR:GELX(SOURCE_AUDIT_MISSING,SOURCE_CONFLICT:2)"
        in res["flags"]
    )
    clean = _model(_cfg([ok])).perform_valuation()
    assert not any(f.startswith("SOTP_SUBSIDIARY_DATA_ERROR") for f in clean["flags"])
    assert clean["blended_fair_value_per_share"] == pytest.approx(36_900.0)


@pytest.mark.parametrize(
    "flag,blocked",
    [
        ("SOTP_SUBSIDIARY_DATA_ERROR:GELX(SOURCE_AUDIT_MISSING)", True),
        ("SOTP_HOLDINGS_MODE", False),
    ],
)
def test_publication_gate_blocks_subsidiary_data_error(monkeypatch, flag, blocked):
    import valuation.report.verified_summary as vs
    from valuation.engine.valuate import _apply_publication_gate

    monkeypatch.setattr(vs, "run_deterministic_checks", lambda *a, **k: [])
    monkeypatch.setattr(cfg_mod, "active_event_hold", lambda *a, **k: None)
    company = N(
        ticker="HOLDX", current_price=50_000.0, assumptions=N(ai_inputs_verified=False)
    )
    out = _apply_publication_gate(
        company, {"blended_fair_value_per_share": 52_000.0, "flags": [flag]}
    )
    assert out["publication_allowed"] is (not blocked)


# --- (2) TTL: có người duyệt mà thiếu/hỏng ngày duyệt → không được coi là đã duyệt ------------------


@pytest.mark.parametrize("as_of", [None, "", "không rõ", "2026-13-45"])
def test_reviewed_without_valid_as_of_is_unverified(as_of):
    h = _holding("OKX", 0.5, 10_000.0, 8_000.0)
    flags = _model(_cfg([h], reviewed_by="phi", as_of=as_of)).perform_valuation()[
        "flags"
    ]
    assert "SOTP_HOLDINGS_UNVERIFIED" in flags


def test_reviewed_with_valid_as_of_is_clean():
    flags = _model(_cfg([_holding("OKX", 0.5, 10_000.0, 8_000.0)])).perform_valuation()[
        "flags"
    ]
    assert (
        "SOTP_HOLDINGS_UNVERIFIED" not in flags and "SOTP_HOLDINGS_STALE" not in flags
    )


def _holders(**entry):
    return {
        "review_ttl_days": 180,
        "holders": {
            "HOLD": {
                "holdings": [{"ticker": "AAA", "stake": 0.5, "source": "https://x"}],
                **entry,
            }
        },
    }


@pytest.mark.parametrize("as_of", [None, "", "không rõ"])
def test_sotp_holdings_for_requires_as_of_when_reviewed(as_of):
    with pytest.raises(ValueError, match="as_of"):
        sotp_holdings_for("HOLD", _holders(reviewed_by="phi", as_of=as_of))


@pytest.mark.parametrize(
    "entry",
    [
        {
            "reviewed_by": None,
            "as_of": None,
        },  # chưa duyệt: hợp lệ, cổng UNVERIFIED chặn
        {
            "reviewed_by": "phi",
            "as_of": datetime.date(2026, 10, 1),
        },  # YAML đọc ngày thành date
        {"reviewed_by": "phi", "as_of": "2026-10-01"},
    ],
)
def test_sotp_holdings_for_accepts_valid_review_state(entry):
    assert (
        sotp_holdings_for("HOLD", _holders(**entry))["holdings"][0]["ticker"] == "AAA"
    )


# --- (1b) scripts/audit_vn100_data.py --tickers không được xóa trạng thái các mã khác ----------------


def _audit_script():
    spec = importlib.util.spec_from_file_location(
        "audit_script_fx3", PROJECT_ROOT / "scripts/audit_vn100_data.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_partial_audit_merges_rows_and_differences():
    mod = _audit_script()
    saved = {
        "mapping_version": "v1",
        "year_from": 2021,
        "rows": [{"ticker": "AAA", "MATCH": 5}, {"ticker": "BBB", "MATCH": 1}],
        "differences": [
            {"ticker": "AAA", "field": "x"},
            {"ticker": "BBB", "field": "old"},
        ],
    }
    rows, diffs = mod.merge_partial_audit(
        saved, [{"ticker": "BBB", "MATCH": 9}], [{"ticker": "BBB", "field": "new"}]
    )
    assert rows == [{"ticker": "AAA", "MATCH": 5}, {"ticker": "BBB", "MATCH": 9}]
    assert diffs == [{"ticker": "AAA", "field": "x"}, {"ticker": "BBB", "field": "new"}]
    # r3b: chưa có audit nào để gộp → không còn "chỉ dòng vừa chạy" (ghi đè status) mà bắt audit đầy đủ.
    with pytest.raises(ValueError, match="đầy đủ"):
        mod.merge_partial_audit(None, [{"ticker": "BBB"}], [])


def test_partial_audit_reuses_saved_year_from_and_rejects_mapping_change():
    mod = _audit_script()
    saved = {"mapping_version": "v1", "year_from": 2021, "rows": []}
    # Dấu vân tay các mã cũ băm từ year_from 2021: lượt một phần năm 2027 phải giữ 2021.
    assert mod.partial_audit_year_from(saved, "v1", 2022) == 2021
    with pytest.raises(ValueError, match="đầy đủ"):  # r3b: không có nền gộp
        mod.partial_audit_year_from(None, "v1", 2022)
    with pytest.raises(ValueError, match="đầy đủ"):
        mod.partial_audit_year_from(saved, "v2", 2022)
    with pytest.raises(ValueError, match="đầy đủ"):
        mod.partial_audit_year_from({"mapping_version": "v1", "rows": []}, "v1", 2022)


# --- (3) Hold có lý do số đo cho mã mới công bố lệch > 30% CTCK / upside > 100% ----------------------


# r4a: TPB gỡ hold (λ = 0,5 → upside +73,7%, lệch CTCK +11,6%); FRT thêm hold (mở lại khi ngưỡng hai chân 5,0,
# lệch CTCK −49,9%, n=13).
@pytest.mark.parametrize("ticker", ["VCG", "PC1", "FRT"])
def test_event_holds_fx3(ticker):
    from valuation.config import active_event_hold

    hold = active_event_hold(ticker, datetime.date(2026, 10, 20))
    assert hold is not None and hold.get("lift_when")
    assert "duyệt" in hold["lift_when"]


# --- (4) Mô tả cho mọi cờ mới của đợt nâng cấp ------------------------------------------------------

NEW_FLAGS = [
    "AI_INPUTS_UNVERIFIED",
    "BANK_CREDIT_COST_SPIKE",
    "BANK_G_CLAMPED_BELOW_COE",
    "BANK_LEVERAGE_ABOVE_HISTORY",
    "BANK_NEGATIVE_VALUATION_LEG",
    "BANK_NO_MARKET_PB_HISTORY",
    "BANK_ROE_FORECAST_VS_HISTORY",
    "BANK_PB_FAR_BELOW_MARKET",
    "BANK_PB_FAR_ABOVE_MARKET",
    "CIP_DOMINATES_VALUE",
    "CIP_LINE_MISSING",
    "CREDIT_GROWTH_CAPPED",
    "DATA_REVIEW_REQUIRED",
    "DDM_SKIPPED_LOW_PAYOUT",
    "FILING_BS_INCOMPLETE",
    "FILING_PRECEDENCE",
    "FV_FAR_BELOW_PRICE",
    "FV_FAR_ABOVE_PRICE",
    "INCOMPLETE_YEAR_DROPPED",
    "INCONSISTENT_YEAR_DROPPED",
    "INS_NO_MARKET_PB_HISTORY",
    "INS_PAYOUT_FALLBACK",
    "INS_PAYOUT_INCONSISTENT",
    "INS_PB_FAR_BELOW_MARKET",
    "INS_PB_FAR_ABOVE_MARKET",
    "MINORITY_AT_BOOK_MATERIAL",
    "MULTIPLE_FROM_PEER_MEDIAN",
    "MULTIPLE_FROM_SECTOR_CONSTANT",
    "MULTIPLE_PRE_ISSUE_EXCLUDED",
    "NEGATIVE_DCF_LEG",
    "NOT_RATED",
    "PE_DISABLED_TTM_LOSS",
    "PE_ON_MIDCYCLE_EARNINGS_TTM_LOSS",
    "PROXY_IMPLAUSIBLE",
    "RIGHTS_ISSUE_UNDATED",
    "RNAV_PROJECT_INPUT_MISSING",
    "SEC_NO_MARKET_PB_HISTORY",
    "SEC_PAYOUT_FALLBACK",
    "SEC_PAYOUT_INCONSISTENT",
    "SEC_PB_FAR_BELOW_MARKET",
    "SEC_PB_FAR_ABOVE_MARKET",
    "SEC_ROE_BELOW_COE",
    "SOTP_HOLDINGS_INCOMPLETE",
    "SOTP_HOLDINGS_MODE",
    "SOTP_HOLDINGS_STALE",
    "SOTP_HOLDINGS_UNVERIFIED",
    "SOTP_SEGMENT_INPUT_MISSING",
    "SOTP_SUBSIDIARY_DATA_ERROR",
    "SOTP_UNLISTED_AT_BOOK",
    "SOURCE_AUDIT_MISSING",
    "SOURCE_AUDIT_PARTIAL",
    "SOURCE_AUDIT_STALE",
    "SOURCE_CONFLICT",
    "SOURCE_CONFLICT_IMMATERIAL",
    "SOURCE_CONTRACT_ERROR",
    "UNEXPLAINED_CURRENT_ASSETS",
    "VALUATION_LEGS_DIVERGE",
]


@pytest.mark.parametrize("code", NEW_FLAGS)
def test_new_flags_have_descriptions(code):
    from valuation.engine.flag_descriptions import FLAG_DESCRIPTIONS

    assert code in FLAG_DESCRIPTIONS
    assert FLAG_DESCRIPTIONS[code]["level"] in {"error", "warning", "info"}


def test_describe_flags_resolves_code_before_colon():
    from valuation.engine.flag_descriptions import FLAG_DESCRIPTIONS, describe_flags

    out = describe_flags(
        [
            "SOURCE_AUDIT_PARTIAL:2026Q3",
            "SEC_PAYOUT_INCONSISTENT: payout 30% vs Gordon 70%",
        ]
    )
    assert out[0]["code"] == "SOURCE_AUDIT_PARTIAL:2026Q3"
    assert out[0]["message"] == FLAG_DESCRIPTIONS["SOURCE_AUDIT_PARTIAL"]["message"]
    assert out[1]["level"] == FLAG_DESCRIPTIONS["SEC_PAYOUT_INCONSISTENT"]["level"]
    assert describe_flags(["XYZ_UNKNOWN:1"])[0]["message"].startswith("Cờ hệ thống")
