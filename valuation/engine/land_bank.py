"""
Land Bank Add-on — cộng thêm giá trị quỹ đất CHƯA phản ánh trong BCTC vào fair
value chính (bất kể phương pháp DCF/EV_EBITDA/PE/...).

Bối cảnh: DN nông nghiệp/cao su/KCN (PHR, DPR, GVR, SIP, SZC...) sở hữu quỹ đất
lớn ghi nhận theo GIÁ GỐC trên BCTC (thường rất thấp so với giá đền bù/chuyển
đổi thực tế khi Nhà nước/KCN thu hồi). DCF/EV_EBITDA trên dòng tiền hoạt động
lõi (cao su, nông nghiệp) KHÔNG bắt được khoản thu nhập bất thường một lần này
→ định giá thấp hơn giá trị thực nếu doanh nghiệp có kế hoạch chuyển đổi đất.

NGUYÊN TẮC (AGENTS.md — không bịa số liệu): diện tích, giá đền bù, tỷ lệ sở
hữu, năm dự kiến thu tiền, giá sổ PHẢI do analyst nhập từ báo cáo/thuyết minh thật.
Mặc định `land_bank_projects` rỗng → add-on = 0, không ảnh hưởng gì.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Union

from valuation.models.financials import Company
from valuation.models.financials_bank import CompanyBank


def compute_land_bank_value_per_share(
    company: Union[Company, CompanyBank],
) -> Dict[str, Any]:
    """
    Giá trị cộng thêm mỗi dự án = (Diện tích(m2) × Giá đền bù(VND/m2) − Giá sổ đất) × (1 − thuế TNDN)
    × Tỷ lệ sở hữu, chiết khấu về hiện tại theo WACC/COE của công ty tới năm dự kiến thu tiền.

    Giá sổ (gia_tri_so_sach_ty, tỷ đồng; 0 nếu đất không ghi trên BCĐKT, vd đất thuê trả hằng năm) đã nằm
    trong VCSH/FV chính → chỉ cộng phần chênh, không cộng trùng. Thu nhập đền bù/chuyển nhượng đất chịu thuế
    TNDN phổ thông (không hưởng ưu đãi) — Damodaran/CFA. Dự án thiếu giá sổ → bỏ khỏi add-on và gắn cờ
    LAND_BANK_INPUT_MISSING (chặn công bố) thay vì coi là 0.

    Trả {"land_bank_npv": VND, "land_bank_value_per_share": VND, "flags": [...]}.
    """
    from valuation.config import load_defaults
    from valuation.engine.models.base import input_number

    projects: List[Dict[str, Any]] = getattr(company.assumptions, "land_bank_projects", None) or []
    if not projects:
        return {"land_bank_npv": 0.0, "land_bank_value_per_share": 0.0, "flags": []}

    a = company.assumptions
    coe = a.cost_of_equity if getattr(a, "cost_of_equity", None) else (
        a.risk_free_rate + a.beta * a.erp
    )
    tax = float(load_defaults()["sector_tax_rates"]["default"])
    current_year = datetime.date.today().year

    total_npv = 0.0
    missing = []
    for i, p in enumerate(projects, 1):
        book = input_number(p, "gia_tri_so_sach_ty")
        if book is None:
            missing.append(str(p.get("ten") or f"#{i}"))
            continue
        dien_tich_ha = float(p.get("dien_tich_ha", 0) or 0)
        gia_boi_thuong = float(p.get("gia_boi_thuong_vnd_m2", 0) or 0)
        ty_le_so_huu = float(p.get("ty_le_so_huu", 100) or 100) / 100.0
        nam_thu_tien = int(float(p.get("nam_thu_tien", current_year) or current_year))

        gain_after_tax = (dien_tich_ha * 10_000.0 * gia_boi_thuong - book * 1e9) * (1.0 - tax) * ty_le_so_huu
        t = max(0, nam_thu_tien - current_year)
        npv = gain_after_tax / ((1.0 + coe) ** t)
        total_npv += npv

    shares = company.shares_outstanding * 1e6
    per_share = total_npv / shares if shares > 0 else 0.0

    flags = ["LAND_BANK_VALUE_ADDED"] if len(missing) < len(projects) else []
    if missing:
        flags.append("LAND_BANK_INPUT_MISSING")  # mã trần để cổng công bố khớp chính xác
    return {
        "land_bank_npv": total_npv,
        "land_bank_value_per_share": per_share,
        "flags": flags,
    }
