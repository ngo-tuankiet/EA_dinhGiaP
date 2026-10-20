"""fin_a (20/10/2026) — sửa các phát hiện nhỏ của phản biện vòng 4 (journal wf_8f83e31a-a14).

(1) forecast_bank: đường driver gốc tự áp ràng buộc vốn của CHÍNH nó, độc lập với đường analyst sửa.
(5) calibration harness: engine_config chụp hash nội dung sotp_holdings.yaml và event_holds.yaml.
(6)/(7) hold REE/TCH và ngưỡng hold mã mới mở là tham số config.

Test viết TRƯỚC khi sửa (tái hiện lỗi).
"""

from itertools import pairwise

import pytest

from tests.helpers_bank import build_fake_bank

_DRIVERS = ("credit_growth", "nim", "cir", "credit_cost")


# --- (1) Ràng buộc vốn đối xứng -----------------------------------------------------------------------------


def _capped_bank(cg_year3: float | None = None):
    """NH giả: tín dụng gốc 20%/năm nhưng VCSH chỉ tăng ~13–14% → ràng buộc vốn (VCSH/TS ≥ 10%) kẹp đường gốc
    cả 5 năm. Analyst chỉ sửa tăng trưởng tín dụng năm 3 (driver_base giữ 20%)."""
    c = build_fake_bank(sustainable_roe=0.16, coe=0.12, g=0.04)
    c.ticker = "SHB"  # routing có trọng số RI/P/B
    a = c.assumptions
    a.industry_roe, a.roe_convergence = 0.20, 0.5
    a.credit_growth = [0.20] * 5
    a.min_equity_to_assets = 0.10
    a.driver_base = {k: list(getattr(a, k)) for k in _DRIVERS}
    if cg_year3 is not None:
        a.credit_growth[2] = cg_year3
    return c


def _sweep() -> list[tuple[float, float, float, float]]:
    """(cg analyst năm 3, LN năm 3, FV, tăng trưởng TS thực năm 3) khi quét 5% → 25%, bước 0,5 điểm %."""
    from valuation.engine.forecast_bank import forecast_bank_financials
    from valuation.engine.valuate import valuate

    out = []
    for k in range(41):
        cg = 0.05 + 0.005 * k
        p = forecast_bank_financials(_capped_bank(cg))
        fv = valuate(_capped_bank(cg))["blended_fair_value_per_share"]
        out.append(
            (
                cg,
                p[2]["net_income"],
                fv,
                p[2]["total_assets"] / p[1]["total_assets"] - 1,
            )
        )
    return out


def test_bank_base_path_capital_cap_independent_of_edited_path():
    """Phản biện r4: trước sửa cg gốc chỉ bị kẹp khi đường SỬA chạm trần → analyst hạ tín dụng dưới trần thì LN
    gốc tính với tăng trưởng gốc CHƯA kẹp (mức mô hình không sửa không bao giờ cho ra) → LN/FV nhảy bậc khi kéo
    ô qua mức trần. Ca giả (đo trước sửa): dưới trần LN3 +0,551 tỷ mỗi 0,5 điểm %, qua trần nhảy +2,849 tỷ; FV
    +5,38đ → +17,87đ."""
    rows = _sweep()
    assert rows[0][3] == pytest.approx(0.05)  # dưới trần: tăng trưởng thực = input
    assert rows[-1][3] < 0.20  # trên trần: bị kẹp → ca quét thật sự đi qua mức trần
    ni = [r[1] for r in rows]
    fv = [r[2] for r in rows]
    d_ni = [b - a for a, b in pairwise(ni)]
    d_fv = [b - a for a, b in pairwise(fv)]
    # Đơn điệu: tăng tín dụng (biên dương: (NIM + non-II/TS)(1 − CIR) > chi phí tín dụng) không làm giảm LN/FV.
    assert min(d_ni) >= -1e-9
    assert min(d_fv) >= -1e-6
    # Liên tục: vùng dưới trần tuyến tính → không bước nào vượt độ dốc dưới trần (bước đầu) quá 1,5 lần.
    assert max(d_ni) <= 1.5 * d_ni[0]
    assert max(d_fv) <= 1.5 * d_fv[0]


def test_bank_unedited_capped_path_unchanged():
    """Không sửa driver: dự phóng trùng mô hình thuần (luật ràng buộc vốn một bước) kể cả năm phai ROE.

    Bản nháp đầu của fin_a (đường sửa lượt 1 dùng gốc ĐÃ kẹp) lệch ở năm phai: VPB/SSB/TCB đổi FV Base dù không
    sửa gì → khoá bằng số của code trước fin_a (r4a, giống hệt từng số ở 19 TCTD trên snapshot 20/10/2026).
    """
    from valuation.engine.forecast_bank import forecast_bank_financials

    p = forecast_bank_financials(_capped_bank())
    # Năm 1 tính tay (chưa phai): lượt 1 tại 20% → TS sinh lời bình quân 11.000; NII 385 + non-II 1% × 11.000 =
    # 110 → TOI 495; PPOP 495 × 0,65 = 321,75; dự phòng 1% × (8.000 + 9.600)/2 = 88 → LN 233,75 × 0,8 = 187;
    # VCSH 1.000 + 187 × 0,75 = 1.140,25 < 10% × 12.000 → trần 1.140,25 / 0,10 / 10.000 − 1 = 14,025%.
    # Lượt cuối: TS 11.402,5; TOI 10.701,25 × 0,045 = 481,55625; PPOP 313,0115625; dự phòng 85,61 → LN 181,92125.
    assert p[0]["total_assets"] == pytest.approx(11_402.5)
    assert p[0]["net_income"] == pytest.approx(181.92125)
    expected = [  # (TS, LN) năm 3–5 từ code r4a (trước fin_a), không sửa driver
        (14_753.201356227943, 240.16741366916497),
        (16_829.29073369186, 278.8841959366899),
        (19_244.34733170308, 324.4948496212229),
    ]
    for y, (ta, ni) in zip(p[2:], expected):
        assert y["total_assets"] == pytest.approx(ta, rel=1e-12)
        assert y["net_income"] == pytest.approx(ni, rel=1e-12)
    no_base = _capped_bank()
    no_base.assumptions.driver_base = None
    assert forecast_bank_financials(no_base) == p


# --- (5) Snapshot engine_config chụp hash các file config ngoài defaults.yaml đổi FV / cổng công bố ----------


def test_engine_config_snapshot_hashes_sotp_holdings_and_event_holds(
    tmp_path, monkeypatch
):
    """r4 đổi FV MSN +36% (sotp_holdings.yaml) và mã được công bố (event_holds.yaml) khi chưa commit → git_sha
    không phân biệt hai run; hash nội dung trong engine_config phải đổi theo file (luật vàng #5).
    """
    import hashlib

    import valuation.config as vc
    from valuation.calibration.harness import _engine_config_snapshot

    files = _engine_config_snapshot()["config_files_sha256"]
    for path in (vc.SOTP_HOLDINGS_FILE, vc.EVENT_HOLDS_FILE):
        assert files[path.name] == hashlib.sha256(path.read_bytes()).hexdigest()
    edited = tmp_path / "event_holds.yaml"
    edited.write_bytes(vc.EVENT_HOLDS_FILE.read_bytes() + b"\n# sua\n")
    monkeypatch.setattr(vc, "EVENT_HOLDS_FILE", edited)
    after = _engine_config_snapshot()["config_files_sha256"]
    assert after["event_holds.yaml"] != files["event_holds.yaml"]
    assert after["sotp_holdings.yaml"] == files["sotp_holdings.yaml"]


# --- (6)/(7) Hold mã mới mở: một ngưỡng trong config, REE/TCH đặt sẵn, tài liệu khớp danh sách hold ---------


@pytest.mark.parametrize("ticker", ["REE", "TCH"])
def test_ree_tch_hold_preset_until_registry_review(ticker):
    """REE/TCH chỉ còn bị chặn bởi SOTP_HOLDINGS_UNVERIFIED; điền reviewed_by là tự mở dù lệch CTCK > 40% với mục
    registry chưa duyệt → hold đặt sẵn để luật §13 tự thực thi."""
    import datetime

    from valuation.config import active_event_hold

    hold = active_event_hold(ticker, datetime.date(2026, 10, 20))
    assert hold is not None
    assert "registry" in hold["reason"] and "duyệt" in hold["lift_when"]


def test_new_listing_hold_rule_is_single_config_parameter():
    from valuation.config import load_defaults

    gate = load_defaults()["publication_gate"]
    assert 0 < gate["new_listing_hold_dev"] < 1
    assert int(gate["new_listing_hold_min_brokers"]) >= 1
    assert gate["new_listing_hold_upside_pct"] > 0


def test_manual_hold_list_matches_event_holds():
    """Manual §13 liệt kê đúng danh sách hold hiện hành (phản biện r4: vẫn ghi TPB đã gỡ, thiếu FRT)."""
    import re

    from valuation.config import PROJECT_ROOT, load_event_holds

    text = (PROJECT_ROOT / "docs" / "AGENT_OPERATING_MANUAL.md").read_text(
        encoding="utf-8"
    )
    m = re.search(r"Danh sách hold hiện hành[^:]*:\s*([A-Z0-9,\s]+)\.", text)
    assert m, "manual §13 thiếu dòng 'Danh sách hold hiện hành: ...'"
    listed = {t.strip() for t in m.group(1).split(",") if t.strip()}
    assert listed == {t.upper() for t in load_event_holds()}
