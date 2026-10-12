"""Dựng báo cáo danh sách nghiên cứu tích sản từ kết quả workflow (không gõ tay số liệu).

  ~/.venv/bin/python reports/research/build_report_20260929.py
Đầu vào: round1_workflow_20260929.json, round2_workflow_20260929.json, research_base_20260929.json.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
r1 = json.loads((HERE / "round1_workflow_20260929.json").read_text(encoding="utf-8"))
r2 = json.loads((HERE / "round2_workflow_20260929.json").read_text(encoding="utf-8"))
base = json.loads((HERE / "research_base_20260929.json").read_text(encoding="utf-8"))
s = r2["synth"]

# Ghi chú kiểm chứng của người tổng hợp (đã tự chạy lại trên DB/code, xem mục 6).
VERIFY = {
    "FPT": (
        "Đã xác nhận thưởng 10% GDKHQ 21/09/2026: giá DB trước 21/09 đều bị chia 1,1 "
        "(66.090×1,1=72.699≈72.700; 65.180×1,1=71.698≈71.700, đúng bước giá 100đ) nhưng bản ghi "
        "corporate_actions thiếu ex_right_date → engine dùng số cp trước thưởng; GTHL/Bear/Bull trong Excel "
        "cao ~10%. Nhận định của agent 'DCF tính trùng lãi liên kết' KHÔNG đứng: EBIT engine = lãi gộp − "
        "chi phí bán hàng/QLDN (22.090,8 − 12.134,1 = 9.956,6 tỷ TTM), không gồm lãi liên kết/tài chính."
    ),
    "GMD": (
        "Nhận định 'nhãn 50/50 nhưng GTHL bằng chân nội tại' là do nhãn cột: với DCF phi tài chính, "
        "GTHL 56.864 đã là trộn 50% DCF (≈43.245) + 50% EV/EBITDA (70.483) bên trong mô hình; cột "
        "'GTHL nội tại' của Excel đang hiển thị giá trị đã trộn (lỗi nhãn, sẽ sửa). Điểm đúng: FCFF không "
        "gồm lãi liên doanh/liên kết và cầu nối chỉ cộng giá trị sổ sách đầu tư → định giá thấp GMD "
        "(Gemalink). Thưởng 50% chưa tới GDKHQ."
    ),
}


def vn(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def fmt_scores(sc: dict) -> str:
    names = {"valuation": "Định giá", "cash_flow": "Dòng tiền DN", "industry_macro": "Vĩ mô ngành",
             "country_macro": "Vĩ mô QG", "technical": "Kỹ thuật", "money_flow": "Dòng tiền TT",
             "game_theory": "Trò chơi", "manipulation_safety": "An toàn làm giá"}
    return " · ".join(f"{names[k]} {v:g}" for k, v in sc.items() if k in names)


def para(text: str) -> str:
    return text.strip() + "\n"


out: list[str] = []
w = out.append
w("# Danh sách nghiên cứu tích sản dài hạn — 5 mã VN100 (29/09/2026)\n")
w("> **Không phải tư vấn đầu tư.** Người soạn không phải chuyên viên tư vấn được cấp phép. Đây là danh sách "
  "ỨNG VIÊN ĐỂ NGHIÊN CỨU TIẾP, rút ra từ mô hình định giá và tiêu chí sàng lọc của chính hệ thống, không xét tình "
  "hình tài chính, khẩu vị rủi ro hay kỳ hạn vốn của người đọc; không có lệnh mua/bán, không có tỷ trọng vốn. "
  "Các 'vùng tham chiếu' là mốc quan sát để nghiên cứu, không phải điểm mua.\n")

w("## 1. Kết luận nhanh\n")
w("Rổ = **4 mã có luận điểm đứng được sau phản biện + 1 mã theo dõi có điều kiện**. Không mã nào đạt ≥6/10 sau "
  "phản biện; ACB và MBB có tương quan 0,68 nên rủi ro hiệu dụng ≈ 4 mảnh, không phải 5.\n")
w("| # | Mã | Ngành | Vai trò | Điểm sau phản biện | Luận điểm | Giá 28/09 | GTHL hệ thống | Trung vị CTCK | ADTV20 (tỷ) |")
w("|---|---|---|---|---|---|---|---|---|---|")
for p in s["picks"]:
    t = p["ticker"]
    v = base["tickers"][t]["valuation_sheet"]
    sig = base["tickers"][t]["signals"]
    fv, med = v["GIÁ TRỊ HỢP LÝ (VND)"], v["Trung vị giá MT CTCK (VND)"]
    fv_s = vn(fv) if fv else "—"
    med_s = vn(med) if med else "—"
    if t == "FPT":
        fv_s += " (≈78.500 sau thưởng)"
        med_s += " (≈83.800 sau thưởng)"
    status = "đứng được" if p["thesis_holds"] else "**chưa đứng — theo dõi có điều kiện**"
    role = p["role_in_basket"].split(".")[0]
    w(f"| {p['rank']:g} | **{t}** | {p['sector']} | {role} | {str(p['final_fit']).replace('.', ',')}/10 ({p['severity']}) | {status} | "
      f"{vn(v['Giá thị trường (VND)'])} | {fv_s} | {med_s} | {sig['adtv20_bn']:.0f} |")
w("")

w("## 2. Bối cảnh vĩ mô và 'trò chơi' thị trường\n")
w(para(s["macro_game_overlay"]))
w("**Quy tắc lý thuyết trò chơi / luật nhà cái dùng để lọc (R1–R10):**\n")
for rule in r1["game"]["rules_for_accumulation"]:
    w(f"- {rule}")
w("")

w("## 3. Thẻ nghiên cứu từng mã\n")
w("> `buy_below` trong các thẻ là trường tính sẵn của bộ xếp hạng hệ thống; mọi mã đang `eligible=false` "
  "(thiếu ngày công bố BCTC, chưa duyệt quản trị) — KHÔNG phải điểm mua. Số liệu ghi \"web\" chưa được kiểm chứng lại "
  "bằng nguồn sơ cấp, không dùng làm điểm then chốt.\n")
sections = [("Vì sao vào danh sách", "why"), ("Định giá", "valuation_snapshot"), ("Dòng tiền doanh nghiệp", "cash_flow_snapshot"),
            ("Vĩ mô & ngành", "macro_industry"), ("Kỹ thuật & dòng tiền thị trường", "technical_flow"),
            ("Cốt lõi lý thuyết trò chơi", "game_theory_core"), ("Đọc theo luật nhà cái (Wyckoff)", "market_maker_reading"),
            ("Điều kiện làm luận điểm sai", "invalidation"), ("Tín hiệu cần chờ xác nhận", "watch_signals"),
            ("Vùng tham chiếu nghiên cứu (không phải điểm mua)", "reference_zones")]
for p in s["picks"]:
    t = p["ticker"]
    w(f"### {p['rank']:g}. {t} — {p['sector']}\n")
    w(f"**Luận điểm sau phản biện:** {'đứng được' if p['thesis_holds'] else 'CHƯA đứng'} · mức phản biện: {p['severity']} · "
      f"điểm {str(p['final_fit']).replace('.', ',')}/10  \n**Điểm 8 chiều:** {fmt_scores(p['final_scores'])}  \n**Vai trò:** {p['role_in_basket']}\n")
    if t in VERIFY:
        w(f"> **Kiểm chứng của người tổng hợp:** {VERIFY[t]}\n")
    for title, key in sections:
        w(f"**{title}**\n")
        w(para(p[key]))
    w("**Rủi ro chính**\n")
    for r in p["main_risks"]:
        w(f"- {r}")
    w("\n**Việc cần nghiên cứu tiếp**\n")
    for r in p["next_research"]:
        w(f"- {r}")
    w("")

w("## 4. Rủi ro chung của rổ và tương quan\n")
w(para(s["correlation_note"]))
w(para(s["basket_rationale"]))

w("## 5. Dự phòng và mã bị loại\n")
w("**Dự phòng:**\n")
for x in s["reserves"]:
    w(f"- **{x['ticker']}** — {x['reason']}")
w("\n**Bị loại:**\n")
for x in s["excluded"]:
    w(f"- **{x['ticker']}** — {x['reason']}")
w("")

w("## 6. Đính chính & lỗi dữ liệu/mô hình phát hiện trong quá trình phân tích\n")
w("- **Giá mục tiêu CTCK đã được nguồn điều chỉnh sẵn** (cổ tức CP và tiền): ACB 03/03 tiêu đề 30.400 → DB 26.200 = "
  "(30.400−700)/1,13; HPG 25/02 33.000 → 29.500; CTD 105.500 → 100.400; HHV 16.900 → 16.000; báo cáo sau GDKHQ giữ "
  "nguyên. Vòng 1 có agent chia thêm lần nữa (ACB/HPG) — đã đính chính. Ngoại lệ: sự kiện GDKHQ SAU lần cập nhật "
  "(FPT 21/09) → phải quy đổi một lần.")
w("- **Sự kiện chia/thưởng thiếu ngày GDKHQ trong corporate_actions** (đồng bộ lần cuối 30/08/2026) → engine dùng số "
  "cp trước sự kiện, GTHL/cp bị phóng đại: **FPT +10% (GDKHQ 21/09), PHR +80% (~11/09), VPB +26% (~24/09)** đã qua "
  "GDKHQ; HDB (30%), TPB, BCM, CMG, SJS, GMD (50%) chưa tới. File Excel ngày 29/09 cần xuất lại sau khi sửa.")
w("- **Nhãn cột 'GTHL nội tại'** trong Excel với DCF phi tài chính đang là giá trị đã trộn DCF+EV/EBITDA (không phải "
  "DCF thuần) — lỗi hiển thị, không đổi GTHL.")
w("- Các agent nêu thêm (chưa được người tổng hợp kiểm chứng đủ, cần duyệt trước khi sửa mô hình): ROIC terminal "
  "mặc định bằng WACC (VNM/MCH); FCFF bỏ lãi LDLK (GMD); mô hình ngân hàng payout 8,7% (MBB), COE thấp (ACB 10,9%); "
  "cổ tức tiền GAS 2.500đ thiếu trong corporate_actions; macro_series CRUDE_OIL/USDVND dừng 10/07/2026.\n")
w("**Giới hạn dữ liệu:**\n")
for x in s["data_limitations"]:
    w(f"- {x}")
w("")

w("## 7. Phương pháp và truy vết\n")
w(para(s["methodology"]))
w("- Nhóm ứng viên: 15 mã từ bộ xếp hạng tích sản của hệ thống (chạy lại 29/09 13:02, `--no-refresh --no-ai`) + VNM, "
  "MCH, GMD bổ sung theo phản biện danh mục vòng 1.")
w("- Quy trình: 2 vòng workflow, 44 agent (vĩ mô, cấu trúc trò chơi, 18 hồ sơ 8 chiều, 18 phản biện đối kháng, "
  "đính chính, đo tương quan, 2 tổng hợp, 2 phản biện danh mục). Phản biện danh mục lần 2: final_ok = "
  f"{r2['critic']['final_ok']}, không đề xuất hoán đổi.")
w("- File truy vết: `reports/research/signals_20260929.{py,csv,json}` (chỉ số định lượng), `research_base_20260929.json` "
  "(gói dữ liệu), `round1_workflow_20260929.json`, `round2_workflow_20260929.json` (toàn bộ hồ sơ/phản biện), "
  "`reports/vn100_dinh_gia_chuan_20260929.xlsx`.")

(HERE / "tich_san_5_ma_20260929.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(HERE / "tich_san_5_ma_20260929.md")
