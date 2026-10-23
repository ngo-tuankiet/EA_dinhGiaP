"""Mô hình tổng hợp CTCK + cổng rà soát — ca tính tay (docs/BROKER_SYNTH.md)."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from valuation.engine.models import broker_synth as bs

FIX = Path(__file__).parent / "fixtures" / "broker_synth"
TODAY = date(2026, 10, 20)


def _company(shares=100.0, coe=0.15):
    a = SimpleNamespace(cost_of_equity=coe, risk_free_rate=0.03, beta=1.0, erp=0.045)
    return SimpleNamespace(ticker="XYZ", shares_outstanding=shares, assumptions=a)


def _cfg():
    return bs.load_broker_synth("XYZ", FIX)


def test_rnav_tinh_tay():
    # (1.000 + 500 − 300) × (1 − 20%) = 960 tỷ / 100 tr cp = 9.600 đ/cp
    rep = _cfg()["reports"][0]
    assert bs.report_equity_bn(rep) == pytest.approx(960.0)
    cfg = {**_cfg(), "reports": [rep]}
    out = bs.valuate_broker_synth(_company(), cfg, TODAY)
    assert out["blended_fair_value_per_share"] == pytest.approx(9600.0)
    assert out["method"] == "BROKER_SYNTH" and not out["flags"]
    assert "Mô hình tổng hợp CTCK (1 báo cáo: CTCK_A 2026-09-01)" == out["method_label"]


def test_phat_hanh_sau_bao_cao_chia_so_cp_hien_tai():
    # Phát hành 20 tr cp thu 200 tỷ sau báo cáo: (960 + 200) / 120 × 1000 = 9.666,67 — không điều chỉnh quyền hai lần.
    cfg = {
        **_cfg(),
        "reports": [_cfg()["reports"][0]],
        "capital_events_after_report": [
            {
                "date": "2026-09-20",
                "type": "rights",
                "shares_added_mn": 20,
                "proceeds_bn": 200,
                "source": "test",
            }
        ],
    }
    out = bs.valuate_broker_synth(_company(shares=120.0), cfg, TODAY)
    assert out["blended_fair_value_per_share"] == pytest.approx(1160 / 120 * 1000)


def test_horizon_12m_chiet_ve_bang_coe():
    # P/E 10 × LN 100 tỷ = 1.000 tỷ / 100 tr = 10.000 (12T tới) / 1,15 = 8.695,65
    cfg = {**_cfg(), "reports": [_cfg()["reports"][1]]}
    out = bs.valuate_broker_synth(_company(), cfg, TODAY)
    assert out["blended_fair_value_per_share"] == pytest.approx(10000 / 1.15)


def test_recon_gap_va_bo_bao_cao_cu():
    reps = [
        dict(_cfg()["reports"][0], target_price=12000),
        dict(_cfg()["reports"][1], date="2025-01-01"),
    ]
    out = bs.valuate_broker_synth(_company(), {**_cfg(), "reports": reps}, TODAY)
    assert out["flags"] == ["BROKER_SYNTH_RECON_GAP:CTCK_A"]
    assert out["blended_fair_value_per_share"] == pytest.approx(9600.0)
    assert any("excluded" in d for d in out["reports"])


def test_target_price_nhieu_ctck_trung_vi_trong_so():
    # 3 CTCK, giá mục tiêu 12T đã điều chỉnh quyền, số cp 100 tr = hiện tại. Cùng ngày → trọng số bằng nhau →
    # trung vị 20.000 (bỏ qua 50.000 lệch xa) → chiết về hôm nay 20.000 / 1,15 = 17.391,30.
    reps = [
        {"broker": b, "date": "2026-10-01", "method": "TARGET_PRICE", "horizon": "12m_forward",
         "target_price": tp, "shares_used_mn": 100}
        for b, tp in (("A", 18000), ("B", 20000), ("C", 50000))
    ]
    out = bs.valuate_broker_synth(_company(), {"ticker": "XYZ", "reports": reps}, TODAY)
    assert out["blended_fair_value_per_share"] == pytest.approx(20000 / 1.15)
    assert not out["flags"]  # vốn chủ = tp × cp → tính lại khớp đúng giá mục tiêu


def test_target_price_thieu_so_cp_bao_loi():
    with pytest.raises(ValueError, match="TARGET_PRICE"):
        bs.report_equity_bn({"method": "TARGET_PRICE", "target_price": 1000})


def test_blend_trong_so():
    rep = {
        "broker": "C",
        "date": "2026-10-01",
        "method": "BLEND",
        "shares_used_mn": 100,
        "legs": [
            {"method": "PE", "weight": 0.5, "target_multiple": 10, "forecast": {"npat_bn": 100}},
            {
                "method": "EV_EBITDA",
                "weight": 0.5,
                "target_multiple": 6,
                "forecast": {"ebitda_bn": 200},
                "net_debt_bn": 400,
            },
        ],
    }
    assert bs.report_equity_bn(rep) == pytest.approx(0.5 * 1000 + 0.5 * 800)


def test_ticker_khong_hop_le():
    with pytest.raises(ValueError):
        bs.load_broker_synth("../x", FIX)


# ---- Cổng rà soát + thay thế bằng BROKER_SYNTH (dùng FPT thật trong DB, chỉ đọc) ----
@pytest.fixture
def fpt():
    from valuation.data_access.repo import build_company_data
    from valuation.db.session import SessionLocalRead

    db = SessionLocalRead()
    try:
        yield build_company_data(db, "FPT")
    finally:
        db.close()


@pytest.fixture
def reviews(tmp_path, monkeypatch):
    import valuation.engine.valuate as v

    path = tmp_path / "valuation_reviews.yaml"
    monkeypatch.setattr(v, "REVIEWS_FILE", path)
    monkeypatch.setattr(bs, "BROKER_SYNTH_DIR", tmp_path / "none")

    def write(**rv):
        base = {
            "reviewed_by": "phi",
            "reviewed_on": date.today().isoformat(),
            "basis": "own_model",
            "reason": "lệch CTCK do giả định tăng trưởng",
        }
        path.write_text(
            yaml.safe_dump({"reviews": {"FPT": {**base, **rv}}}, allow_unicode=True),
            encoding="utf-8",
        )

    return write


def _gate(company, flags):
    from valuation.engine.valuate import _apply_publication_gate

    return _apply_publication_gate(
        company,
        {
            "blended_fair_value_per_share": company.current_price * 1.1,
            "flags": flags,
            "recommendation": "HOLD",
        },
    )


def test_khong_review_giu_nguyen(fpt, reviews):
    assert _gate(fpt, ["UPSIDE_EXTREME_REVIEW"])["publication_allowed"] is False


def test_review_publish_go_co_ra_soat_duoc(fpt, reviews):
    reviews(decision="publish")
    res = _gate(fpt, ["UPSIDE_EXTREME_REVIEW"])
    assert res["publication_allowed"] is True
    assert any(f.startswith("REVIEWED_PUBLISH:") for f in res["flags"])
    assert res["review_label"].startswith("Đã rà soát:")


def test_review_khong_go_co_du_lieu_that(fpt, reviews):
    reviews(decision="publish")
    res = _gate(fpt, ["UPSIDE_EXTREME_REVIEW", "SOTP_SUBSIDIARY_DATA_ERROR:GEL", "VALUATION_PROXY"])
    assert res["publication_allowed"] is False  # VALUATION_PROXY chỉ gỡ khi basis=broker_synth


def test_review_het_han_hoac_khac_basis(fpt, reviews):
    reviews(decision="publish", reviewed_on="2020-01-01")
    assert _gate(fpt, ["UPSIDE_EXTREME_REVIEW"])["publication_allowed"] is False
    reviews(decision="publish", basis="broker_synth")
    assert _gate(fpt, ["UPSIDE_EXTREME_REVIEW"])["publication_allowed"] is False


def test_review_block(fpt, reviews):
    reviews(decision="block", reason="sai số cp")
    res = _gate(fpt, [])
    assert res["publication_allowed"] is False and "REVIEW_BLOCKED:sai số cp" in res["flags"]


def test_thay_bang_broker_synth_khi_mo_hinh_rieng_proxy(fpt, reviews, tmp_path, monkeypatch):
    d = tmp_path / "bs"
    d.mkdir()
    cfg = yaml.safe_load((FIX / "XYZ.yaml").read_text(encoding="utf-8"))
    cfg["ticker"] = "FPT"
    cfg["reports"] = [dict(cfg["reports"][0], date=date.today().isoformat())]
    (d / "FPT.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(bs, "BROKER_SYNTH_DIR", d)
    res = _gate(fpt, ["VALUATION_PROXY"])
    assert res["method"] == "BROKER_SYNTH" and "BROKER_SYNTHESIZED" in res["flags"]
    assert res["own_model_flags"] and "VALUATION_PROXY" in res["own_model_flags"]
    assert res["blended_fair_value_per_share"] == pytest.approx(960 / fpt.shares_outstanding * 1000)
    # Mô hình riêng đang công bố bình thường → không thay.
    assert "method" not in _gate(fpt, [])
