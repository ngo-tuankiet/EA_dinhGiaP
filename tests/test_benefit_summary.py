"""Lịch quyền VN100: cột "Quyền lợi / điều kiện" diễn giải được ESOP/phát hành riêng lẻ (trước đây "Chưa đủ thông tin")."""

from types import SimpleNamespace

from valuation.views.corporate_actions import _benefit_summary


def _ev(kind, ratio=None, cash=None, price=None):
    return SimpleNamespace(
        event_type=kind,
        exercise_ratio=ratio,
        cash_amount_vnd_per_share=cash,
        issue_price_vnd=price,
    )


def test_dilutive_issues_show_ratio_like_db_rows():
    # Số liệu như DB: DGW ESOP 0,913%; DXG riêng lẻ 10,7366% → làm tròn 2 chữ số.
    assert _benefit_summary(_ev("ESOP", 0.00913)) == (
        "Phát hành ESOP cho nhân viên 0.91% số cổ phiếu (cổ đông hiện hữu không nhận)"
    )
    assert _benefit_summary(_ev("PRIVATE_PLACEMENT", 0.107366, price=12000)) == (
        "Phát hành riêng lẻ 10.74% số cổ phiếu (cổ đông hiện hữu không nhận), giá 12.000 VND"
    )


def test_missing_fields_are_named_precisely():
    assert (
        _benefit_summary(_ev("ESOP", 0)) == "Nguồn chưa ghi tỷ lệ"
    )  # như PNJ: tỷ lệ 0
    assert _benefit_summary(_ev("CASH_DIVIDEND")) == "Chưa công bố số tiền/cổ phiếu"
    assert _benefit_summary(_ev("CASH_DIVIDEND", 0.25, 2500)) == "2.500 VND/cổ phiếu"
