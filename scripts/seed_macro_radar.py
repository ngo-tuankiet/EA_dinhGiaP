"""Seed bảng macro_radar — map (sector, indicator) → driver greek cho daily_signal.

daily_signal áp: fv_fast = fv_base + Σ macro_delta * elasticity * dFV/ddriver.
Để khớp, `mapped_driver` PHẢI trùng driver_code của greek production (có prefix
`delta_`), và elasticity lấy từ config/elasticities.yaml (1 nguồn sự thật, không
trùng lặp hệ số).

Phạm vi seed: path phi tài chính (greek delta_revenue_growth_1_to_3 /
delta_ebit_margin / delta_wacc — đang hoạt động cho FPT/HPG/DGC). Ngân hàng dùng
calculate_greeks riêng (delta_nim_10bps... convention % change, KHÔNG tương thích
daily_signal) → CHƯA seed, cần thống nhất greek bank trước.

Idempotent: UPSERT theo PK (sector, indicator_code). Chạy lại không nhân đôi.
Chạy: ./venv/bin/python -m scripts.seed_macro_radar
"""
from sqlalchemy.dialects.postgresql import insert

from valuation.db.session import SessionLocalWrite
from valuation.db.models import MacroRadar
from valuation.config import load_elasticities


def build_rows() -> list[dict]:
    el = load_elasticities().get("macro_overlay", {})
    rev_gdp = el.get("revenue_growth_to_gdp", {})
    hrc = el.get("steel_margin_to_hrc_per_usd", {})

    def gdp_beta(sector_key: str) -> float:
        return float(rev_gdp.get(sector_key, rev_gdp.get("default", 1.0)))

    # (sector, indicator_code, mapped_driver, elasticity, freq, warn_low, warn_high)
    rows = [
        # GDP → tăng trưởng doanh thu, beta theo ngành (DB sector → key elasticities)
        ("Technology", "GDP_YOY", "delta_revenue_growth_1_to_3", gdp_beta("technology"), "Q", 0.04, 0.10),
        ("Steel",      "GDP_YOY", "delta_revenue_growth_1_to_3", gdp_beta("steel"),      "Q", 0.04, 0.10),
        ("Chemicals",  "GDP_YOY", "delta_revenue_growth_1_to_3", gdp_beta("default"),    "Q", 0.04, 0.10),
        # Lãi suất TPCP → WACC (~1:1) cho mọi ngành phi tài chính
        ("ALL",        "TPCP_10Y", "delta_wacc",                 1.0,                    "D", None, 0.07),
        # Giá HRC → biên EBIT thép (TẮT: elasticity 0.0 chờ hiệu chỉnh chi phí đầu vào)
        ("Steel",      "STEEL_HRC", "delta_ebit_margin",         float(hrc.get("steel", 0.0)), "D", None, None),
    ]
    return [
        {
            "sector": s, "indicator_code": ind, "mapped_driver": drv,
            "elasticity": elas, "frequency": freq, "source": "config/elasticities.yaml",
            "warn_low": wl, "warn_high": wh,
        }
        for (s, ind, drv, elas, freq, wl, wh) in rows
    ]


def main() -> None:
    rows = build_rows()
    db = SessionLocalWrite()
    try:
        for r in rows:
            stmt = insert(MacroRadar).values(**r).on_conflict_do_update(
                index_elements=["sector", "indicator_code"],
                set_={
                    "mapped_driver": r["mapped_driver"],
                    "elasticity": r["elasticity"],
                    "frequency": r["frequency"],
                    "source": r["source"],
                    "warn_low": r["warn_low"],
                    "warn_high": r["warn_high"],
                },
            )
            db.execute(stmt)
        db.commit()
        print(f"Seeded/updated {len(rows)} macro_radar rows:")
        for r in rows:
            print(f"  {r['sector']:<12} {r['indicator_code']:<10} -> {r['mapped_driver']:<28} elasticity={r['elasticity']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
