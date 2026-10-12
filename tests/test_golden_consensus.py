"""Golden test toàn VN100 — đối chiếu giá trị hợp lý với đồng thuận CTCK (AGENTS.md luật vàng #8, D49).

Chạy đúng đường thật (harness → batch.value_ticker) trên ảnh DB ngày 28/09/2026:
  1. Mỗi mã có đồng thuận mà lệch ngoài band (±20%, SOTP/RNAV rộng hơn) phải được phân loại trong
     config/calibration_registry.yaml (giải trình còn hạn / lỗi đã thừa nhận / thiếu dữ liệu).
     Không chấp nhận lệch "im lặng", giải trình hết hạn, hay mục registry lỗi thời.
  2. Nhãn verified=true trong routing.json chỉ dành cho mã có ≥3 CTCK và lệch ≤ golden_tolerance
     (10%) — nhãn "đã kiểm chứng" phải có bằng chứng số.
"""

import datetime
import json
import logging

import pytest
import yaml

from valuation.calibration.harness import run_calibration
from valuation.calibration.registry import (
    GOV_MISSING,
    GOV_OBSOLETE,
    GOV_STALE,
    load_registry,
)
from valuation.config import PROJECT_ROOT
from valuation.db.session import SessionLocalRead

AS_OF = datetime.date(2026, 9, 28)
MIN_BROKERS = 3


@pytest.fixture(scope="module")
def observations():
    logging.disable(logging.WARNING)
    db = SessionLocalRead()
    try:
        run = run_calibration(db, registry=load_registry(), as_of=AS_OF)
    finally:
        db.close()
        logging.disable(logging.NOTSET)
    return {o.ticker: o for o in run.observations}


def test_every_out_of_band_ticker_is_classified(observations):
    bad = {
        t: o.governance_status
        for t, o in observations.items()
        if o.governance_status in (GOV_MISSING, GOV_STALE, GOV_OBSOLETE)
    }
    assert not bad, f"Lệch CTCK chưa phân loại / hết hạn / registry lỗi thời: {bad}"


def test_verified_flag_backed_by_golden_deviation(observations):
    tol = yaml.safe_load(
        (PROJECT_ROOT / "config" / "investment_ranking.yaml").read_text()
    )["golden_tolerance"]
    routing = json.loads(
        (PROJECT_ROOT / "valuation" / "config" / "routing.json").read_text()
    )
    unproven = {}
    for t, v in routing.items():
        if not v.get("verified"):
            continue
        o = observations[t]
        if (
            o.n_brokers < MIN_BROKERS
            or o.dev_vs_consensus is None
            or abs(o.dev_vs_consensus) > tol
        ):
            unproven[t] = (o.n_brokers, o.dev_vs_consensus)
    assert not unproven, f"verified=true nhưng không đạt golden ±{tol:.0%}: {unproven}"
