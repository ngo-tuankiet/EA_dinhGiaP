"""Ô chọn mã đầu sidebar: tên công ty bỏ loại hình pháp lý để danh sách gọn."""

import pytest

from valuation.views.select_ticker import short_company_name


@pytest.mark.parametrize(
    ("ticker", "name", "expected"),
    [
        ("FPT", "Công ty cổ phần FPT", ""),  # trùng mã → chỉ hiện mã
        (
            "VPB",
            "Ngân hàng Thương mại Cổ phần Việt Nam Thịnh Vượng",
            "Ngân hàng Việt Nam Thịnh Vượng",
        ),
        ("VGC", "Tổng Công ty Viglacera - Công ty Cổ phần", "Tổng Công ty Viglacera"),
        ("VTP", "Tổng Công ty Cổ phần Bưu chính Viettel", "Bưu chính Viettel"),
        ("BCM", "Tập đoàn Becamex - CTCP", "Tập đoàn Becamex"),
        (
            "TAL",
            "Công Ty Cổ Phần Đầu Tư Bất Động Sản Taseco",
            "Đầu Tư Bất Động Sản Taseco",
        ),
        ("XYZ", None, ""),
    ],
)
def test_short_company_name(ticker, name, expected):
    assert short_company_name(ticker, name) == expected
