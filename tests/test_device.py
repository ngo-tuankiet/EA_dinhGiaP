"""Giao diện điện thoại (D54): nhận diện User-Agent và chọn 2 cảnh báo nặng nhất."""

import pytest

from valuation.views.device import is_phone, is_phone_ua, split_alerts

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
ANDROID_PHONE = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Mobile Safari/537.36"
ANDROID_TABLET = "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
IPAD = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"


@pytest.mark.parametrize(
    ("ua", "phone"),
    [
        (IPHONE, True),
        (ANDROID_PHONE, True),
        (ANDROID_TABLET, False),
        (IPAD, False),
        (None, False),
        ("", False),
    ],
)
def test_is_phone_ua(ua, phone):
    assert is_phone_ua(ua) is phone


def test_is_phone_outside_streamlit_is_desktop():
    assert is_phone() is False  # không có request → hiển thị đầy đủ như desktop


def test_split_alerts_keeps_two_most_severe_in_original_order():
    alerts = [
        ("success", "governance", None),
        ("warning", "not rated", "🚫"),
        ("info", "flag info", None),
        ("error", "data error", None),
        ("warning", "flag warning", None),
    ]
    shown, rest = split_alerts(alerts, 2)
    # Nặng nhất: error, rồi warning xuất hiện trước ("not rated"); giữ thứ tự gốc khi hiển thị.
    assert [b for _, b, _ in shown] == ["not rated", "data error"]
    assert [b for _, b, _ in rest] == ["governance", "flag info", "flag warning"]
    assert split_alerts([], 2) == ([], [])


def test_split_alerts_never_promotes_info_or_success():
    alerts = [("info", "jv note", "ℹ️"), ("success", "ok", None)]
    assert split_alerts(alerts, 2) == ([], alerts)
    assert split_alerts([("error", "e", None)], 0) == ([], [("error", "e", None)])
