"""
Test flag_descriptions — dịch mã cờ engine sang câu giải thích tiếng Việt.

Regression: trước đây UI (streamlit_app.py, views/results.py) không hiển thị
`flags` từ valuate() — người dùng thấy VJC "SELL, Giá MT 0 VND, Upside -100%"
mà không biết nguyên nhân, tưởng là lỗi hệ thống. Test khóa chặt: mọi cờ đang
tồn tại trong engine phải có mô tả, và describe_flags() trả đúng cấu trúc.
"""
from valuation.engine.flag_descriptions import FLAG_DESCRIPTIONS, describe_flags


def test_describe_flags_known_code():
    out = describe_flags(["NEGATIVE_EQUITY_VALUE_EV_EBITDA"])
    assert len(out) == 1
    assert out[0]["code"] == "NEGATIVE_EQUITY_VALUE_EV_EBITDA"
    assert out[0]["level"] == "error"
    assert "âm" in out[0]["message"].lower() or "ÂM" in out[0]["message"]


def test_describe_flags_empty_list():
    assert describe_flags([]) == []
    assert describe_flags(None) == []


def test_describe_flags_unknown_code_has_fallback():
    out = describe_flags(["SOME_NEW_FLAG_NOT_YET_DOCUMENTED"])
    assert len(out) == 1
    assert out[0]["level"] == "info"
    assert "SOME_NEW_FLAG_NOT_YET_DOCUMENTED" in out[0]["message"]


def test_all_descriptions_have_valid_level():
    for code, info in FLAG_DESCRIPTIONS.items():
        assert info["level"] in ("error", "warning", "info"), f"{code} có level không hợp lệ"
        assert info["message"].strip(), f"{code} thiếu message"


def test_critical_engine_flags_are_documented():
    """Các cờ then chốt phải có mô tả — không được rơi vào fallback chung chung."""
    critical = [
        "NEGATIVE_EQUITY_VALUE_EV_EBITDA", "VALUATION_PROXY", "LAND_BANK_VALUE_ADDED",
        "DDM_BLEND", "NEGATIVE_NORMALIZED_EARNINGS", "SOTP_NAV_FALLBACK",
    ]
    for code in critical:
        assert code in FLAG_DESCRIPTIONS, f"Thiếu mô tả cho cờ quan trọng: {code}"
