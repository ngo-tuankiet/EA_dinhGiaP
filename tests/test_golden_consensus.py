"""Golden test toàn VN100 — đối chiếu giá trị hợp lý với đồng thuận CTCK (AGENTS.md luật vàng #8, D49).

Chạy đúng đường thật (harness → batch.value_ticker) trên ảnh DB ở HAI mốc 28/09/2026 và 20/10/2026
(r3b: chỉ một mốc cố định thì mã ra band sau mốc — BID, VIB — lọt qua):
  1. Mỗi mã có đồng thuận mà lệch ngoài band (±20%, SOTP/RNAV rộng hơn) ở BẤT KỲ mốc nào phải được phân
     loại trong config/calibration_registry.yaml (giải trình còn hạn / lỗi đã thừa nhận / thiếu dữ liệu).
     Không chấp nhận lệch "im lặng", giải trình hết hạn, hay mục registry lỗi thời — mục chỉ lỗi thời
     khi KHÔNG mốc nào còn cần nó (trong band ở một mốc nhưng ngoài band ở mốc kia thì vẫn cần).
  2. Nhãn verified=true trong routing.json chỉ dành cho mã có ≥3 CTCK và lệch ≤ golden_tolerance
     (10%) ở mọi mốc — nhãn "đã kiểm chứng" phải có bằng chứng số.
"""

import datetime
import json
import logging
from typing import ClassVar

import pytest
import yaml

from valuation.calibration.harness import run_calibration
from valuation.calibration.registry import (
    GOV_KNOWN_DEFECT,
    GOV_MISSING,
    GOV_OBSOLETE,
    GOV_OK_JUSTIFIED,
    GOV_STALE,
    load_registry,
)
from valuation.config import PROJECT_ROOT
from valuation.db.session import SessionLocalRead

AS_OF_DATES = (datetime.date(2026, 9, 28), datetime.date(2026, 10, 20))
MIN_BROKERS = 3


class _KeyTracking(dict):
    """dict ghi lại khóa top-level config/defaults.yaml được đọc (để kiểm snapshot của harness)."""

    seen: ClassVar[set] = set()

    def __getitem__(self, key):
        self.seen.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.seen.add(key)
        return super().get(key, default)

    def __contains__(self, key):
        self.seen.add(key)
        return super().__contains__(key)


@pytest.fixture(scope="module")
def runs():
    """{mốc: {mã: Observation}}. load_defaults() trả _KeyTracking trong lúc chạy (cache lru được
    nạp lại bằng bản theo dõi rồi xoá sau đó) → ghi lại khóa config mà đường định giá thật đọc.
    """
    import valuation.config as vc

    logging.disable(logging.WARNING)
    original_safe_load = vc.yaml.safe_load
    vc.load_defaults.cache_clear()
    vc.yaml.safe_load = lambda f: _KeyTracking(original_safe_load(f))
    try:
        vc.load_defaults()
    finally:
        vc.yaml.safe_load = original_safe_load
    db = SessionLocalRead()
    try:
        registry = load_registry()
        return {
            d: {
                o.ticker: o
                for o in run_calibration(db, registry=registry, as_of=d).observations
            }
            for d in AS_OF_DATES
        }
    finally:
        db.close()
        vc.load_defaults.cache_clear()
        logging.disable(logging.NOTSET)


def test_engine_config_snapshot_covers_keys_read(runs):
    """Luật vàng #5: mọi khóa defaults.yaml mà 100 mã × 2 mốc đọc phải nằm trong snapshot engine_config."""
    from valuation.calibration.harness import _ENGINE_CONFIG_KEYS

    assert _KeyTracking.seen, "không ghi được khóa nào — cơ chế theo dõi hỏng"
    missing = _KeyTracking.seen - set(_ENGINE_CONFIG_KEYS)
    assert (
        not missing
    ), f"Khóa config engine đọc nhưng thiếu trong snapshot harness: {sorted(missing)}"


def test_every_out_of_band_ticker_is_classified(runs):
    bad = {
        (d.isoformat(), t): o.governance_status
        for d, obs in runs.items()
        for t, o in obs.items()
        if o.governance_status in (GOV_MISSING, GOV_STALE)
    }
    # Mục registry còn được dùng (ngoài band) ở ít nhất một mốc thì không lỗi thời.
    used = {
        t
        for obs in runs.values()
        for t, o in obs.items()
        if o.governance_status in (GOV_KNOWN_DEFECT, GOV_OK_JUSTIFIED)
    }
    bad.update(
        {
            (d.isoformat(), t): o.governance_status
            for d, obs in runs.items()
            for t, o in obs.items()
            if o.governance_status == GOV_OBSOLETE and t not in used
        }
    )
    assert not bad, f"Lệch CTCK chưa phân loại / hết hạn / registry lỗi thời: {bad}"


def test_verified_flag_backed_by_golden_deviation(runs):
    tol = yaml.safe_load(
        (PROJECT_ROOT / "config" / "investment_ranking.yaml").read_text()
    )["golden_tolerance"]
    routing = json.loads(
        (PROJECT_ROOT / "valuation" / "config" / "routing.json").read_text()
    )
    unproven = {}
    for d, observations in runs.items():
        for t, v in routing.items():
            if not v.get("verified"):
                continue
            o = observations[t]
            if (
                o.n_brokers < MIN_BROKERS
                or o.dev_vs_consensus is None
                or abs(o.dev_vs_consensus) > tol
            ):
                unproven[(d.isoformat(), t)] = (o.n_brokers, o.dev_vs_consensus)
    assert not unproven, f"verified=true nhưng không đạt golden ±{tol:.0%}: {unproven}"
