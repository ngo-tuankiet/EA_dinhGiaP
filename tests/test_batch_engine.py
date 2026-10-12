"""
Test batch engine (Phase 3): value_ticker dispatch router-driven đúng phương pháp,
+ build_vn100_dataframe (cột phương pháp, cờ proxy, độ tin cậy). Chạy DB thật.
"""
import pytest
from valuation.db.session import SessionLocalRead
from valuation.engine.batch import value_ticker, value_all
from valuation.output.gsheets_exporter import build_vn100_dataframe


@pytest.fixture
def db():
    s = SessionLocalRead()
    yield s
    s.close()


def test_bank_dispatch(db):
    r = value_ticker(db, "VCB")
    assert r["method"] == "RI_PB"
    assert r.get("fair_value", 0) > 0
    assert r["upside"] is not None


def test_nonfin_dispatch(db):
    r = value_ticker(db, "DCM")
    assert r["method"] == "DCF"
    assert r.get("fair_value", 0) > 0


def test_proxy_flag_propagates(db):
    # RNAV/SOTP phải mang cờ VALUATION_PROXY trong kết quả batch.
    r = value_ticker(db, "NLG")  # RNAV
    assert r["method"] == "RNAV"
    assert "VALUATION_PROXY" in r.get("flags", [])


def test_unknown_ticker_error(db):
    r = value_ticker(db, "ZZZ")
    assert r["error"] == "NOT_IN_VN100"


def test_dataframe_columns_and_proxy_label(db):
    results = value_all(db, ["VCB", "NLG", "DCM"])
    df = build_vn100_dataframe(results)
    for col in ["Mã", "Ngành", "Phương pháp", "FV", "Upside %", "Độ tin cậy", "Cờ"]:
        assert col in df.columns
    # NLG (RNAV) phải ghi rõ proxy không phải khuyến nghị đầu tư.
    nlg = df[df["Mã"] == "NLG"].iloc[0]
    assert nlg["Độ tin cậy"] == "Proxy - không khuyến nghị"


@pytest.mark.parametrize(
    "result,expected_label",
    [
        (
            {
                "ticker": "AAA", "group": "Khác", "method": "DCF",
                "status": "IMPLEMENTED", "verified": True, "price": 10_000,
                "fair_value": 12_000, "upside": 0.2, "flags": [],
            },
            "Đã kiểm chứng",
        ),
        (
            {
                "ticker": "BBB", "group": "Khác", "method": "DCF",
                "status": "IMPLEMENTED", "verified": False, "price": 10_000,
                "fair_value": 12_000, "upside": 0.2, "flags": [],
            },
            "Mô hình ngành - chưa golden test",
        ),
        (
            {
                "ticker": "CCC", "group": "Khác", "method": "DCF",
                "status": "IMPLEMENTED", "verified": True, "price": 10_000,
                "fair_value": 12_000, "upside": 0.2, "flags": ["STALE_PRICE"],
            },
            "Cần cập nhật dữ liệu",
        ),
        (
            {
                "ticker": "DDD", "group": "BĐS", "method": "RNAV",
                "status": "PARTIAL", "verified": False, "price": 10_000,
                "fair_value": 12_000, "upside": 0.2, "flags": ["VALUATION_PROXY"],
            },
            "Proxy - không khuyến nghị",
        ),
        (
            {
                "ticker": "EEE", "group": "Khác", "method": "DCF",
                "status": "IMPLEMENTED", "verified": False, "price": 10_000,
                "fair_value": None, "upside": None,
                "flags": ["NEGATIVE_EQUITY_VALUE_DCF", "NOT_RATEABLE"],
            },
            "Không định giá",
        ),
    ],
)
def test_dataframe_confidence_reflects_data_quality(result, expected_label):
    df = build_vn100_dataframe([result])
    assert df.iloc[0]["Độ tin cậy"] == expected_label
