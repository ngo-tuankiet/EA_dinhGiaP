import pandas as pd
from valuation.quality.scores import run_qc_checks

def test_run_qc_checks_financial_sector():
    # Ngân hàng (VCB) -> bank
    res = run_qc_checks("VCB", "Ngân hàng", pd.DataFrame())
    assert res["altman_z_score"] is None
    assert res["beneish_m_score"] is None
    assert res["piotroski_f_score"] is None
    assert "financial_sector_skipped_standard_qc" in res["flags"]

def test_run_qc_checks_non_financial_sector():
    # Phi tài chính (FPT) -> default (non_financial)
    res = run_qc_checks("FPT", "Công nghệ", pd.DataFrame())
    assert res["altman_z_score"] is None
    assert res["beneish_m_score"] is None
    assert res["piotroski_f_score"] is None
