"""
Forecast bank module — Dự phóng 3 dòng BCTC 5 năm tiếp theo cho Ngân hàng.
"""
from typing import List, Dict, Any
from valuation.config import load_defaults
from valuation.models.financials_bank import CompanyBank


def converged_roe(roe: float, industry_roe: float | None, convergence: float) -> float:
    """ROE terminal trước sàn/trần = ROE riêng + λ·(ROE ngành − ROE riêng).

    Damodaran ("Valuing Financial Service Firms"): ở giai đoạn tăng trưởng ổn định ROE hội tụ về
    trung bình ngành (vd ABN AMRO 15,56% → 15% 'Ind. avg'). λ = 1 hội tụ đầy đủ; thiếu ROE ngành
    → giữ ROE riêng."""
    return roe if industry_roe is None else roe + convergence * (industry_roe - roe)


def ni_from_avg_roe(roe_avg: float, book_begin: float, payout: float) -> float:
    """LN từ ROE trên VCSH BÌNH QUÂN: r = LN / (B + (LN − cổ tức)/2), cổ tức = p·LN khi lãi → LN = r·B / (1 − r(1 − p)/2);
    lỗ (r < 0) không chia cổ tức → LN = r·B / (1 − r/2). Ca tay: B = 100, r = 12%, p = 20% → 12 / 0,952 = 12,605.
    Dùng chung NH (fade năm chuyển tiếp), CTCK và bảo hiểm (ROE lịch sử đo trên VCSH bình quân)."""
    return roe_avg * book_begin / (1 - roe_avg * ((1 - payout) if roe_avg >= 0 else 1.0) / 2)


def begin_roe_from_avg(roe_avg: float, g: float) -> float:
    """ROE trên VCSH ĐẦU kỳ ở trạng thái dừng: VCSH tăng g/năm → VCSH bình quân năm sau = B·(1 + g/2), nên
    LN / B đầu kỳ = ROE bình quân × (1 + g/2) (đẳng thức). Dùng cho RI terminal và P/B hợp lý (ROE − g)/(COE − g)."""
    return roe_avg * (1 + g / 2)


def bank_own_roe(company: CompanyBank) -> float:
    """ROE riêng trước hội tụ: sustainable_roe (roe5 repo / analyst nhập / kịch bản D67); thiếu → ROE TTM.
    D67: giá trị ≤ 0 vẫn dùng — kịch bản Bear có thể lỗ năm 5; trước đây ≤ 0 bị thay bằng ROE TTM (đảo dấu sốc)."""
    sustainable = company.assumptions.sustainable_roe
    if sustainable is not None:
        return sustainable
    base_is, base_bs = company.historical_is[-1], company.historical_bs[-1]
    cap = float((load_defaults().get("bank_terminal", {}) or {}).get("terminal_roe_cap", 0.20))
    return base_is.net_income / base_bs.total_equity if base_bs.total_equity > 0 else cap


def bank_terminal_roe(company: CompanyBank) -> tuple[float, float]:
    """(ROE terminal sau sàn/trần, trước sàn/trần) trên VCSH BÌNH QUÂN (bank_terminal): hội tụ ROE bền vững
    (roe5) về ROE ngành theo λ. Nguồn duy nhất cho dự phóng (fade năm cuối) và BankGeneralValuationModel."""
    cfg = load_defaults().get("bank_terminal", {}) or {}
    cap = float(cfg.get("terminal_roe_cap", 0.20))
    floor = float(cfg.get("terminal_roe_floor", 0.0))
    a = company.assumptions
    raw = converged_roe(bank_own_roe(company), a.industry_roe, a.roe_convergence)
    return min(max(raw, floor), cap), raw


def driver_roe5(company: CompanyBank) -> float | None:
    """ROE năm 5 trên VCSH bình quân của dự phóng driver thuần (fade_to_terminal=False, không dòng cân): roe5 bền
    vững của repo và phần dịch roe5 của kịch bản (D67). VCSH bình quân năm 5 ≤ 0 → None (ROE vô nghĩa)."""
    p = forecast_bank_financials(company, fade_to_terminal=False)
    eq_avg = (p[-2]["total_equity"] + p[-1]["total_equity"]) / 2
    return p[-1]["net_income"] / eq_avg if eq_avg > 0 else None


def fade_plug_share(projections: list[dict[str, Any]], tax_rate: float) -> float | None:
    """Tỷ trọng LN năm cuối do dòng cân roe_fade_adjustment (không theo driver NIM/CIR/chi phí tín dụng):
    điều chỉnh LNTT × (1 − thuế) / LN. LN ≤ 0 → None."""
    last = projections[-1]
    ni = last["net_income"]
    return last.get("roe_fade_adjustment", 0.0) * (1.0 - tax_rate) / ni if ni > 0 else None


def forecast_bank_financials(company: CompanyBank, fade_to_terminal: bool = True) -> List[Dict[str, Any]]:
    """
    Dự phóng 5 năm tiếp theo cho Ngân hàng dựa trên các giả định NIM, Tăng trưởng tín dụng, CIR, Credit Cost.

    Mô hình 3 giai đoạn (Damodaran): `bank_terminal.roe_transition_years` năm cuối, ROE trên VCSH bình quân phai
    tuyến tính từ ROE của driver GỐC về ROE terminal (trọng số 1/N … 1). Năm 5 = ROE_T và LN năm 6 (RI terminal)
    nối liền năm 5 khi driver = driver gốc: giả định máy đặt và MỌI kịch bản Bull/Bear (D67: kịch bản sốc cả
    driver gốc và tính lại roe5 → ROE_T của chính kịch bản). Chỉ khi analyst sửa driver thì năm 5 lệch ROE_T đúng
    bằng phần delta dưới đây; lệch quá ngưỡng → cờ BANK_TERMINAL_JUMP (bank_general).
    fade_to_terminal=False: chỉ driver (driver_roe5 đo roe5 = ROE bền vững trước hội tụ).
    Driver analyst sửa so với ảnh chụp máy đặt (assumptions.driver_base) KHÔNG bỏ dòng cân (r4a, phản biện r3:
    bỏ dòng cân trong khi RI terminal vẫn theo ROE_T làm đảo dấu tác động): trên cùng trạng thái đầu kỳ,
    LN = LN_phai(driver gốc) + (LN_driver_sửa − LN_driver_gốc); dòng cân tính từ driver gốc. Không có ảnh chụp
    → driver hiện tại là gốc (giống hệt phai thuần).
    Ràng buộc vốn (VCSH/TS ≥ min_equity_to_assets) áp RIÊNG cho từng đường theo cùng luật một bước (fin_a): đường
    gốc không phụ thuộc việc đường sửa có chạm trần → LN/FV liên tục, đơn điệu khi kéo tăng trưởng tín dụng.
    Dòng cân năm 5 trọng yếu → cờ BANK_ROE_FADE_PLUG (valuate, fade_plug_share).
    """
    hist_is = company.historical_is
    hist_bs = company.historical_bs
    assumptions = company.assumptions

    base_is = hist_is[-1]
    base_bs = hist_bs[-1]

    # Tính tỷ lệ Non-II / Tài sản bình quân lịch sử
    hist_non_ii = base_is.non_interest_income
    hist_assets = base_bs.total_assets
    non_ii_to_assets = hist_non_ii / hist_assets if hist_assets > 0 else 0.005

    projections = []
    
    curr_loans = base_bs.customer_loans
    curr_assets = base_bs.total_assets
    curr_earning_assets = base_bs.earning_assets
    curr_equity = base_bs.total_equity
    curr_deposits = base_bs.customer_deposits
    base_year = base_is.year

    min_eq = getattr(assumptions, "min_equity_to_assets", None)
    tax_rate = getattr(assumptions, 'tax_rate', 0.20)
    target_roe = bank_terminal_roe(company)[0] if fade_to_terminal else None
    n_fade = int((load_defaults().get("bank_terminal") or {})["roe_transition_years"])

    base = getattr(assumptions, "driver_base", None) or {}
    drv0 = {k: base.get(k) or getattr(assumptions, k) for k in ("credit_growth", "nim", "cir", "credit_cost")}

    def _ops(cg: float, nim: float, cir: float, cc: float) -> dict[str, float]:
        next_loans = curr_loans * (1 + cg)
        next_earning_assets = curr_earning_assets * (1 + cg)
        next_assets = curr_assets * (1 + cg)
        avg_earning_assets = (curr_earning_assets + next_earning_assets) / 2
        avg_assets = (curr_assets + next_assets) / 2
        nii = nim * avg_earning_assets
        non_ii = non_ii_to_assets * avg_assets
        toi = nii + non_ii
        opex = cir * toi
        ppop = toi - opex
        provision = cc * (curr_loans + next_loans) / 2
        return dict(
            next_loans=next_loans, next_earning_assets=next_earning_assets, next_assets=next_assets,
            nii=nii, non_ii=non_ii, toi=toi, opex=opex, ppop=ppop, provision=provision,
            ni_drv=(ppop - provision) * (1.0 - tax_rate),  # lỗ vẫn là lỗ, không kẹp về 0
        )

    p = assumptions.dividend_payout_ratio

    def _cap(ni: float, next_assets: float) -> float | None:
        """Ràng buộc vốn: VCSH/Tổng tài sản không xuống dưới mức lịch sử của chính NH — tăng trưởng tài sản bị
        giới hạn bởi vốn tích lũy (thay cho kiểm tra CAR). Trả trần tăng trưởng khi bind, None khi không."""
        next_equity = curr_equity + ni - max(ni, 0.0) * p
        if min_eq and next_equity < min_eq * next_assets:
            return next_equity / min_eq / curr_assets - 1
        return None

    def _faded(ni_drv0: float, i: int) -> float:
        """LN đường gốc sau phai ROE về ROE_T ở các năm chuyển tiếp (năm khác: LN driver)."""
        w = (i + 1 - (5 - n_fade)) / n_fade if target_roe is not None and n_fade > 0 else 0.0
        if w > 0 and curr_equity > 0 and target_roe is not None:
            # ROE bình quân r = LN / (B + (LN − cổ tức)/2); r = r_drv + w·(ROE_T − r_drv) rồi giải LN theo r:
            # LN = r·B / (1 − r·(1 − p)/2) khi LN ≥ 0 (cổ tức p·LN), r·B / (1 − r/2) khi lỗ (không cổ tức).
            r_drv = ni_drv0 / (curr_equity + (ni_drv0 - max(ni_drv0, 0.0) * p) / 2)
            return ni_from_avg_roe(r_drv + w * (target_roe - r_drv), curr_equity, p)
        return ni_drv0

    def _base(i: int) -> tuple[tuple[float, float], tuple[float, float]]:
        """Đường gốc trên CÙNG trạng thái đầu kỳ theo đúng luật ràng buộc vốn một bước của CHÍNH nó, độc lập với
        đường sửa (fin_a, phản biện r4: kẹp theo đường sửa làm LN nhảy bậc khi analyst kéo tín dụng qua trần).
        Trả ((LN driver, LN phai) lượt 1 tại tăng trưởng gốc, (…) lượt cuối sau ràng buộc vốn)."""

        def run(cg0: float) -> tuple[float, tuple[float, float]]:
            o = _ops(cg0, drv0["nim"][i], drv0["cir"][i], drv0["credit_cost"][i])
            return o["next_assets"], (o["ni_drv"], _faded(o["ni_drv"], i))

        assets0, first = run(drv0["credit_growth"][i])
        cap0 = _cap(first[1], assets0)
        return first, (first if cap0 is None else run(cap0)[1])

    def _year(cg: float, dg: float, i: int, ni_drv0: float, ni0: float) -> dict[str, float]:
        y = _ops(cg, assumptions.nim[i], assumptions.cir[i], assumptions.credit_cost[i])
        ni = ni0 + (y["ni_drv"] - ni_drv0)  # phần analyst sửa driver cộng thẳng, đúng dấu
        fade_adj = (ni0 - ni_drv0) / (1.0 - tax_rate)  # cấp LNTT: LNTT = PPOP − dự phòng + điều chỉnh
        div = max(ni, 0.0) * p
        return dict(
            y, next_deposits=curr_deposits * (1 + dg),
            pbt=y["ppop"] - y["provision"] + fade_adj, ni=ni, div=div,
            next_equity=curr_equity + ni - div, fade_adj=fade_adj,
        )

    for i in range(5):
        year = base_year + (i + 1)
        cg = assumptions.credit_growth[i]
        dg = assumptions.deposit_growth[i] if hasattr(assumptions, "deposit_growth") and assumptions.deposit_growth else cg
        # Đường sửa tự áp cùng luật một bước: lượt 1 = gốc lượt 1 + delta driver tại tăng trưởng nhập, lượt cuối
        # = gốc lượt cuối + delta driver tại tăng trưởng sau trần → không sửa gì thì trùng từng số đường gốc;
        # tại ngưỡng bind trần = tăng trưởng nhập nên LN liên tục.
        first, final = _base(i)
        y1 = _year(cg, dg, i, *first)
        cap = _cap(y1["ni"], y1["next_assets"])
        y = _year(cg, dg, i, *final) if cap is None else _year(cap, min(dg, cap), i, *final)
        next_loans, next_deposits = y["next_loans"], y["next_deposits"]
        next_earning_assets, next_assets = y["next_earning_assets"], y["next_assets"]
        nii, non_ii, toi, opex, ppop = y["nii"], y["non_ii"], y["toi"], y["opex"], y["ppop"]
        provision, pbt, ni, div = y["provision"], y["pbt"], y["ni"], y["div"]
        next_equity = y["next_equity"]

        next_other_earning_assets = max(0.0, next_assets - next_loans)
        next_other_liabilities = max(0.0, next_assets - next_deposits - next_equity)

        proj_item = {
            "year": year,
            "customer_loans": next_loans,
            "other_earning_assets": next_other_earning_assets,
            "earning_assets": next_earning_assets,
            "total_assets": next_assets,
            "customer_deposits": next_deposits,
            "other_liabilities": next_other_liabilities,
            "net_interest_income": nii,
            "non_interest_income": non_ii,
            "total_operating_income": toi,
            "operating_expenses": opex,
            "pre_provision_profit": ppop,
            "provision_expense": provision,
            "roe_fade_adjustment": y["fade_adj"],
            "pretax_income": pbt,
            "net_income": ni,
            "dividends": div,
            "total_equity": next_equity
        }
        projections.append(proj_item)

        # Cập nhật cho vòng lặp tiếp theo
        curr_loans = next_loans
        curr_earning_assets = next_earning_assets
        curr_assets = next_assets
        curr_equity = next_equity
        curr_deposits = next_deposits

    return projections
