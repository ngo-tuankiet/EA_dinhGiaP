"""
Test seed macro_radar + elasticity scaling trong get_macro_deltas.

- build_rows(): map đúng elasticity theo ngành từ elasticities.yaml, mapped_driver
  có prefix `delta_` (khớp greek production).
- get_macro_deltas(): driver_delta = macro_delta * elasticity.
  Dùng SessionLocalWrite + rollback với code ZZ_TEST_* → không đụng dữ liệu thật
  (xem memory tests-run-against-real-db).
"""
import datetime
import pytest

from valuation.db.session import SessionLocalWrite
from valuation.db.models import MacroRadar, MacroSeries
from valuation.analysis.macro_radar import get_macro_deltas
from scripts.seed_macro_radar import build_rows


def test_build_rows_elasticities_and_prefix():
    rows = {(r["sector"], r["indicator_code"]): r for r in build_rows()}

    steel = rows[("Steel", "GDP_YOY")]
    tech = rows[("Technology", "GDP_YOY")]
    chem = rows[("Chemicals", "GDP_YOY")]
    rate = rows[("ALL", "TPCP_10Y")]
    hrc = rows[("Steel", "STEEL_HRC")]

    assert steel["elasticity"] == 2.0       # thép cyclical mạnh
    assert tech["elasticity"] == 1.2
    assert chem["elasticity"] == 1.0        # default
    assert rate["elasticity"] == 1.0        # bond yield → WACC 1:1
    assert hrc["elasticity"] == 0.0         # tắt, chờ hiệu chỉnh

    # mapped_driver phải khớp greek production (prefix delta_)
    for r in build_rows():
        assert r["mapped_driver"].startswith("delta_"), r["mapped_driver"]


@pytest.fixture
def db_session():
    s = SessionLocalWrite()
    yield s
    s.rollback()
    s.close()


def test_elasticity_scales_macro_delta(db_session):
    sector = "ZZ_TEST_SECTOR"
    ind = "ZZ_TEST_FADE_GDP"
    # elasticity 2.0: macro_delta 0.03 → driver_delta 0.06
    db_session.add(MacroRadar(
        sector=sector, indicator_code=ind,
        mapped_driver="delta_revenue_growth_1_to_3", elasticity=2.0, frequency="Q",
    ))
    today = datetime.date.today()
    db_session.add_all([
        MacroSeries(indicator_code=ind, date=today, value=0.08),
        MacroSeries(indicator_code=ind, date=today - datetime.timedelta(days=400), value=0.05),
    ])
    db_session.flush()

    deltas = get_macro_deltas(sector, macro_snapshot=None, db=db_session)
    assert "delta_revenue_growth_1_to_3" in deltas
    d = deltas["delta_revenue_growth_1_to_3"]
    assert abs(d["delta"] - 0.06) < 1e-9, d  # 0.03 * 2.0


def test_default_elasticity_is_one_when_null(db_session):
    sector = "ZZ_TEST_SECTOR2"
    ind = "ZZ_TEST_FADE_RATE"
    # elasticity = None → mặc định 1.0 (tương thích ngược)
    # mapped_driver riêng để không đụng row seed thật ALL→delta_wacc (sector "ALL"
    # luôn được get_macro_deltas gộp vào).
    db_session.add(MacroRadar(
        sector=sector, indicator_code=ind,
        mapped_driver="delta_zz_test_driver", elasticity=None, frequency="D",
    ))
    today = datetime.date.today()
    db_session.add_all([
        MacroSeries(indicator_code=ind, date=today, value=0.055),
        MacroSeries(indicator_code=ind, date=today - datetime.timedelta(days=30), value=0.050),
    ])
    db_session.flush()

    deltas = get_macro_deltas(sector, macro_snapshot=None, db=db_session)
    d = deltas["delta_zz_test_driver"]
    assert abs(d["delta"] - 0.005) < 1e-9, d  # 0.005 * 1.0
