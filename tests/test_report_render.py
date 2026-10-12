"""
Golden render test — báo cáo 11 phần chuẩn quỹ (SPEC PHẦN B + Test Spec M5).

Render end-to-end trên DB thật cho 1 mã ngân hàng (ACB) + 1 phi tài chính (FPT):
- HTML chứa đủ các section title 1→10 + phụ lục.
- Số trên header khớp engine (giá mục tiêu, upside).
- Word (.docx) build được, mở lại đọc được số section.
Không gọi DeepSeek trong test (dùng narrative fallback) — không phụ thuộc mạng.
"""

import os

import jinja2
import pytest

from valuation.data_access.repo import build_company_data
from valuation.db.session import SessionLocalRead
from valuation.engine.valuate import valuate
from valuation.report.ai_narrative import _FALLBACK
from valuation.report.build_docx import build_docx_report
from valuation.report.report_data import build_report_sections

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "valuation",
    "report",
    "template.html",
)

# 11 phần theo khuôn SPEC PHẦN B (tiêu đề trong template)
EXPECTED_SECTIONS = [
    "KHUYẾN NGHỊ ĐẦU TƯ",  # 1. Cover
    "1. Luận điểm đầu tư",  # 2
    "2. Tóm tắt định giá",  # 3
    "3. Tổng quan doanh nghiệp",  # 4
    "4. Bối cảnh ngành",  # 5
    "5. Phân tích tài chính lịch sử",  # 6
    "6. Giả định dự phóng",  # 7
    "7. Chi tiết định giá",  # 8
    "8. Phân tích độ nhạy & kịch bản",  # 9
    "9. Rủi ro đầu tư",  # 10
    "10. Phụ lục — Báo cáo tài chính lịch sử",  # 11
]


@pytest.fixture
def db():
    s = SessionLocalRead()
    yield s
    s.close()


def _render_html(ticker: str, db) -> tuple:
    """Chạy pipeline báo cáo như trên app (không Streamlit, không AI call)."""
    company = build_company_data(db, ticker, mode="TTM")
    res = valuate(company)
    blended_fv = res["blended_fair_value_per_share"]
    sections = build_report_sections(company, blended_fv, db=db, flags=res.get("flags"))
    cover = sections["cover"]

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = jinja2.Template(f.read())

    report_data = {
        "ticker": ticker,
        "name": company.name,
        "sector": company.sector,
        "date": "2026-07-02",
        "analyst": "Golden Test",
        "recommendation": cover["recommendation"],
        "rec_color": "#10B981",
        "upside": f"{cover['upside'] * 100:+.2f}",
        "target_price": f"{blended_fv:,.0f}",
        "current_price": f"{company.current_price:,.0f}",
        "shares": f"{company.shares_outstanding:,.2f}",
        "market_cap": f"{cover['market_cap']:,.0f}",
        "weight_intrinsic": 50,
        "weight_relative": 50,
        "intrinsic_method": "TEST_PRIMARY",
        "relative_method": "TEST_SECONDARY",
        "intrinsic_price": "0 VND",
        "relative_price": "0 VND",
        "notes": "",
        "chart_football": "",
        "chart_heatmap": "",
        "chart_history": "",
        "chart_profitability": "",
        "proj_cols": ["N1", "N2", "N3", "N4", "N5"],
        "proj_rows": [{"label": "Doanh thu", "values": ["1", "2", "3", "4", "5"]}],
        "narrative": {**_FALLBACK, "ai_generated": False},
        "hist": sections["historical"],
        "assumptions": sections["assumptions"],
        "wacc_rows": sections["wacc_breakdown"],
        "consensus": sections["consensus"],
        "scenarios": sections["scenarios"],
        "appendix": sections["appendix"],
        "flags": sections["flags"],
    }
    html = template.render(**report_data)
    return html, report_data, blended_fv


@pytest.mark.parametrize("ticker", ["ACB", "FPT"])
def test_report_html_contains_all_11_sections(db, ticker):
    html, _, _ = _render_html(ticker, db)
    for section in EXPECTED_SECTIONS:
        assert section in html, f"{ticker}: thiếu section '{section}' trong báo cáo"


def test_report_header_numbers_match_engine(db):
    """Header phải khớp engine: giá mục tiêu render = blended FV của valuate()."""
    html, data, blended_fv = _render_html("ACB", db)
    assert f"{blended_fv:,.0f}" in html
    assert data["recommendation"] in html
    # Vốn hóa hiển thị trong cover
    assert data["market_cap"] in html


def test_report_ai_notice_shown_only_when_ai_generated(db):
    """Dấu 'Nháp do AI tạo' chỉ hiện khi narrative do AI sinh (SPEC PHẦN G)."""
    html, _, _ = _render_html("ACB", db)
    assert "Nháp do AI tạo" not in html  # fallback → không có dấu AI

    # Render lại với narrative giả lập AI
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = jinja2.Template(f.read())
    _, data, _ = _render_html("ACB", db)
    data["narrative"] = {
        "thesis": "x",
        "overview": "x",
        "industry": "x",
        "market_view": "x",
        "risks": "x",
        "ai_generated": True,
    }
    html_ai = template.render(**data)
    assert "Nháp do AI tạo" in html_ai
    assert "4A. Kỹ thuật, dòng tiền & vị thế thị trường" in html_ai
    assert "4A. Cổ tức, tăng vốn & quyền cổ đông" not in html_ai


def test_docx_builds_with_11_sections(db, tmp_path):
    """Word build được và chứa đủ tiêu đề section (Test Spec M5)."""
    docx = pytest.importorskip("docx")
    _, data, _ = _render_html("ACB", db)
    out = str(tmp_path / "report_acb.docx")
    ok = build_docx_report(data, data["proj_cols"], data["proj_rows"], {}, out)
    assert ok and os.path.exists(out)

    text = "\n".join(p.text for p in docx.Document(out).paragraphs)
    for section in EXPECTED_SECTIONS[1:]:  # cover trong Word nằm ở bảng, kiểm riêng
        assert section in text, f"Word thiếu section '{section}'"


def test_report_consensus_comparison_section(db):
    """Phần 7.3 mở rộng: bảng CTCK + AI tổng hợp điểm chung/riêng hiển thị trong HTML.

    FPT có sẵn consensus_history (Simplize/24hmoney) + consensus_synthesis
    trong DB — golden data của pipeline GĐ2.
    """
    html, data, blended_fv = _render_html("FPT", db)
    consensus = data["consensus"]
    assert consensus is not None, "FPT phải có dữ liệu consensus trong DB"

    # Tiêu đề section mới
    assert "So sánh với định giá các công ty chứng khoán" in html
    # Bảng CTCK: có ít nhất vài CTCK và giá mục tiêu của từng CTCK xuất hiện
    assert consensus["n_brokers"] >= 3
    for b in consensus["broker_rows"][:3]:
        assert b["broker"] in html
        assert f"{b['target_price']:,.0f}" in html
    # Chênh lệch mô hình vs CTCK
    assert "Chênh lệch mô hình vs trung vị CTCK" in html
    # AI tổng hợp: 4 khối điểm chung/riêng/mấu chốt/đối chiếu
    if consensus.get("synthesis"):
        assert "Điểm CHUNG các CTCK đồng thuận" in html
        assert "Điểm RIÊNG / khác biệt giữa các CTCK" in html
        assert "Điểm MẤU CHỐT" in html
        assert "AI tổng hợp từ báo cáo CTCK" in html  # dấu review riêng của synthesis


def test_docx_consensus_comparison_section(db, tmp_path):
    """Word: phần 7.3 mở rộng chứa bảng CTCK + khối AI tổng hợp."""
    docx = pytest.importorskip("docx")
    _, data, _ = _render_html("FPT", db)
    out = str(tmp_path / "report_fpt.docx")
    ok = build_docx_report(data, data["proj_cols"], data["proj_rows"], {}, out)
    assert ok and os.path.exists(out)

    d = docx.Document(out)
    text = "\n".join(p.text for p in d.paragraphs)
    tables_text = "\n".join(
        cell.text for t in d.tables for row in t.rows for cell in row.cells
    )
    assert "So sánh với định giá các công ty chứng khoán" in text
    consensus = data["consensus"]
    for b in consensus["broker_rows"][:3]:
        assert b["broker"] in tables_text, f"Word thiếu CTCK {b['broker']} trong bảng"
    if consensus.get("synthesis"):
        assert "Điểm CHUNG các CTCK đồng thuận:" in text
        assert "AI tổng hợp từ báo cáo CTCK" in text
