"""
Land Bank Add-on — cộng thêm giá trị quỹ đất CHƯA phản ánh trong BCTC vào fair
value chính (bất kể phương pháp DCF/EV_EBITDA/PE/...).

Bối cảnh: DN nông nghiệp/cao su/KCN (PHR, DPR, GVR, SIP, SZC...) sở hữu quỹ đất
lớn ghi nhận theo GIÁ GỐC trên BCTC (thường rất thấp so với giá đền bù/chuyển
đổi thực tế khi Nhà nước/KCN thu hồi). DCF/EV_EBITDA trên dòng tiền hoạt động
lõi (cao su, nông nghiệp) KHÔNG bắt được khoản thu nhập bất thường một lần này
→ định giá thấp hơn giá trị thực nếu doanh nghiệp có kế hoạch chuyển đổi đất.

NGUYÊN TẮC (AGENTS.md — không bịa số liệu): diện tích, giá đền bù, tỷ lệ sở
hữu, năm dự kiến thu tiền PHẢI do analyst nhập từ báo cáo/thuyết minh thật.
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
    NPV quỹ đất mỗi dự án = Diện tích(m2) × Giá đền bù(VND/m2) × Tỷ lệ sở hữu,
    chiết khấu về hiện tại theo WACC/COE của công ty tới năm dự kiến thu tiền.

    Trả {"land_bank_npv": VND, "land_bank_value_per_share": VND, "flags": [...]}.
    """
    projects: List[Dict[str, Any]] = getattr(company.assumptions, "land_bank_projects", None) or []
    if not projects:
        return {"land_bank_npv": 0.0, "land_bank_value_per_share": 0.0, "flags": []}

    a = company.assumptions
    coe = a.cost_of_equity if getattr(a, "cost_of_equity", None) else (
        a.risk_free_rate + a.beta * a.erp
    )
    current_year = datetime.date.today().year

    total_npv = 0.0
    for p in projects:
        dien_tich_ha = float(p.get("dien_tich_ha", 0) or 0)
        gia_boi_thuong = float(p.get("gia_boi_thuong_vnd_m2", 0) or 0)
        ty_le_so_huu = float(p.get("ty_le_so_huu", 100) or 100) / 100.0
        nam_thu_tien = int(float(p.get("nam_thu_tien", current_year) or current_year))

        gross_value = dien_tich_ha * 10_000.0 * gia_boi_thuong * ty_le_so_huu
        t = max(0, nam_thu_tien - current_year)
        npv = gross_value / ((1.0 + coe) ** t)
        total_npv += npv

    shares = company.shares_outstanding * 1e6
    per_share = total_npv / shares if shares > 0 else 0.0

    return {
        "land_bank_npv": total_npv,
        "land_bank_value_per_share": per_share,
        "flags": ["LAND_BANK_VALUE_ADDED"],
    }
