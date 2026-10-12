"""Xuất 4 báo cáo kiểm chứng và 1 báo cáo tổng hợp ACB/CTG/PVT/GAS."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import statistics
from pathlib import Path
from typing import Any, Iterable

import yaml
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import desc

from valuation.data_access.repo import build_company_data
from valuation.db.models import Consensus, FinancialsQuarterly
from valuation.db.session import SessionLocalRead
from valuation.engine.sensitivity import run_scenario_analysis
from valuation.engine.valuate import valuate
from valuation.models.financials_bank import CompanyBank


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "four_ticker_audit_20260829.yaml"
DEFAULT_OUTPUT = ROOT / "reports" / "20260829_kiem_chung_4_ma"

NAVY = colors.HexColor("#16324F")
BLUE = colors.HexColor("#226F8A")
TEAL = colors.HexColor("#1F8A70")
GOLD = colors.HexColor("#C58B24")
RED = colors.HexColor("#B64A4A")
INK = colors.HexColor("#202C35")
MUTED = colors.HexColor("#60717D")
PALE = colors.HexColor("#EEF3F5")
PALE_GOLD = colors.HexColor("#F7F0E3")


def _register_fonts() -> None:
    pdfmetrics.registerFont(
        TTFont("AuditSans", "/System/Library/Fonts/Supplemental/Arial.ttf")
    )
    pdfmetrics.registerFont(
        TTFont("AuditSans-Bold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
    )


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="AuditSans-Bold",
            fontSize=27,
            leading=31,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=7 * mm,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="AuditSans",
            fontSize=11,
            leading=16,
            textColor=MUTED,
            spaceAfter=5 * mm,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="AuditSans-Bold",
            fontSize=16,
            leading=20,
            textColor=NAVY,
            spaceBefore=3 * mm,
            spaceAfter=3 * mm,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="AuditSans-Bold",
            fontSize=11.5,
            leading=15,
            textColor=BLUE,
            spaceBefore=2 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="AuditSans",
            fontSize=9.2,
            leading=13.2,
            textColor=INK,
            spaceAfter=2 * mm,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName="AuditSans",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
        ),
        "metric": ParagraphStyle(
            "Metric",
            parent=base["Normal"],
            fontName="AuditSans-Bold",
            fontSize=16,
            leading=18,
            textColor=NAVY,
            alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            parent=base["Normal"],
            fontName="AuditSans",
            fontSize=7.2,
            leading=9,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "cell": ParagraphStyle(
            "Cell",
            parent=base["Normal"],
            fontName="AuditSans",
            fontSize=7.7,
            leading=10,
            textColor=INK,
        ),
        "cell_bold": ParagraphStyle(
            "CellBold",
            parent=base["Normal"],
            fontName="AuditSans-Bold",
            fontSize=7.7,
            leading=10,
            textColor=INK,
        ),
        "source": ParagraphStyle(
            "Source",
            parent=base["Normal"],
            fontName="AuditSans",
            fontSize=7,
            leading=9,
            textColor=BLUE,
            wordWrap="CJK",
        ),
    }


def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(str(text)).replace("\n", "<br/>"), style)


def _bullets(items: Iterable[str], styles: dict[str, ParagraphStyle]) -> list[Paragraph]:
    return [
        Paragraph(f"&#8226;&nbsp; {html.escape(item)}", styles["body"])
        for item in items
    ]


def _fmt(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.{digits}f}"


def _preferred_rows(db, ticker: str, statement: str, line_item: str):
    rows = (
        db.query(FinancialsQuarterly)
        .filter(
            FinancialsQuarterly.ticker == ticker,
            FinancialsQuarterly.fiscal_year == 2026,
            FinancialsQuarterly.fiscal_quarter.in_([1, 2]),
            FinancialsQuarterly.statement == statement,
            FinancialsQuarterly.line_item == line_item,
        )
        .all()
    )
    selected = {}
    for row in rows:
        rank = (
            int(bool(row.is_restated)),
            row.published_at or dt.date.min,
            row.ingested_at or dt.datetime.min,
        )
        quarter = row.fiscal_quarter
        if quarter not in selected or rank > selected[quarter][0]:
            selected[quarter] = (rank, float(row.value or 0.0))
    return selected


def _h1(db, ticker: str, statement: str, line_item: str) -> float:
    return sum(value for _, value in _preferred_rows(db, ticker, statement, line_item).values()) / 1e9


def _latest_line(db, ticker: str, statement: str, line_item: str) -> float:
    rows = (
        db.query(FinancialsQuarterly)
        .filter(
            FinancialsQuarterly.ticker == ticker,
            FinancialsQuarterly.statement == statement,
            FinancialsQuarterly.line_item == line_item,
        )
        .order_by(
            desc(FinancialsQuarterly.fiscal_year),
            desc(FinancialsQuarterly.fiscal_quarter),
            desc(FinancialsQuarterly.is_restated),
            desc(FinancialsQuarterly.published_at),
        )
        .first()
    )
    return float(rows.value or 0.0) / 1e9 if rows else 0.0


def _metric(db, company, code: str) -> float:
    ticker = company.ticker
    latest_bs = company.historical_bs[-1]
    if code == "shares":
        return company.shares_outstanding * 1e6
    if code == "latest_assets":
        return latest_bs.total_assets
    if code == "latest_gross_loans":
        return _latest_line(db, ticker, "BS", "loans_and_advances_to_customers")
    if code == "latest_deposits":
        return latest_bs.customer_deposits
    if code == "latest_liquid_funds":
        return latest_bs.cash_and_equivalents + latest_bs.short_term_financial_investments
    if code == "latest_nci":
        return latest_bs.minority_interest
    mapping = {
        "h1_pbt": ("IS", "net_accounting_profit_loss_before_tax"),
        "h1_nii": ("IS", "net_interest_income"),
        "h1_toi": ("IS", "total_operating_income"),
        "h1_revenue": ("IS", "net_sales"),
        "h1_parent_pat": ("IS", "attributable_to_parent_company"),
        "h1_cfo": ("CF", "net_cash_inflows_outflows_from_operating_activities"),
    }
    statement, line_item = mapping[code]
    return _h1(db, ticker, statement, line_item)


def _audit_rows(db, company, cfg: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for fact in cfg["facts"]:
        system = _metric(db, company, fact["metric"])
        official = float(fact["official"])
        deviation = (system / official - 1.0) * 100 if official else 0.0
        passed = abs(deviation) <= float(fact.get("tolerance_pct", 1.0))
        digits = 0 if fact["unit"] == "cp" else 1
        rows.append(
            [
                fact["label"],
                _fmt(official, digits),
                _fmt(system, digits),
                f"{deviation:+.2f}%",
                "KHỚP" if passed else "CẦN SOÁT",
            ]
        )
    return rows


def _consensus(db, ticker: str, as_of: dt.date) -> dict[str, Any] | None:
    cutoff = as_of - dt.timedelta(days=180)
    rows = (
        db.query(Consensus)
        .filter(
            Consensus.ticker == ticker,
            Consensus.report_date >= cutoff,
            Consensus.report_date <= as_of,
            Consensus.target_price > 0,
        )
        .order_by(desc(Consensus.report_date))
        .all()
    )
    latest_by_broker = {}
    for row in rows:
        broker = row.broker_canon or row.broker
        latest_by_broker.setdefault(broker, row)
    if not latest_by_broker:
        return None
    targets = [float(row.target_price) for row in latest_by_broker.values()]
    return {
        "median": statistics.median(targets),
        "min": min(targets),
        "max": max(targets),
        "count": len(targets),
    }


def _metric_table(data: list[tuple[str, str]], styles) -> Table:
    cells = []
    for value, label in data:
        cells.append(
            [
                _p(value, styles["metric"]),
                _p(label, styles["metric_label"]),
            ]
        )
    table = Table([cells], colWidths=[44 * mm] * len(cells))
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E0E5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _table(headers, rows, widths, styles, status_column: int | None = None) -> Table:
    prepared = [[_p(x, styles["cell_bold"]) for x in headers]]
    prepared += [[_p(x, styles["cell"]) for x in row] for row in rows]
    table = Table(prepared, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CFD9DF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if status_column is not None:
        for index, row in enumerate(rows, start=1):
            color = TEAL if row[status_column] == "KHỚP" else RED
            commands.append(("TEXTCOLOR", (status_column, index), (status_column, index), color))
    table.setStyle(TableStyle(commands))
    return table


def _history_rows(company) -> tuple[list[str], list[list[str]]]:
    years = [str(row.year) for row in company.historical_is[-4:]]
    if isinstance(company, CompanyBank):
        series = [
            ("TOI", [row.total_operating_income for row in company.historical_is[-4:]]),
            ("LNTT", [row.pretax_income for row in company.historical_is[-4:]]),
            ("LNST", [row.net_income for row in company.historical_is[-4:]]),
            ("Cho vay KH", [row.customer_loans for row in company.historical_bs[-4:]]),
            ("Vốn CSH", [row.total_equity for row in company.historical_bs[-4:]]),
        ]
    else:
        series = [
            ("Doanh thu", [row.revenue for row in company.historical_is[-4:]]),
            ("EBIT", [row.ebit for row in company.historical_is[-4:]]),
            ("LNST", [row.net_income for row in company.historical_is[-4:]]),
            ("CFO", [row.cfo for row in company.historical_cf[-4:]]),
            ("Nợ vay", [row.short_term_debt + row.long_term_debt for row in company.historical_bs[-4:]]),
        ]
    rows = [[label] + [_fmt(v, 0) for v in values] for label, values in series]
    return years, rows


def _on_page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D8E1E6"))
    canvas.line(18 * mm, 15 * mm, 192 * mm, 15 * mm)
    canvas.setFont("AuditSans", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "KIỂM CHỨNG ĐỊNH GIÁ VN100 | 29.08.2026")
    canvas.drawRightString(192 * mm, 10 * mm, f"Trang {doc.page}")
    canvas.restoreState()


def _doc(path: Path, title: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=20 * mm,
        title=title,
        author="Hệ thống định giá VN100",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates(PageTemplate(id="audit", frames=[frame], onPage=_on_page))
    return doc


def _two_columns(left_title, left_items, right_title, right_items, styles) -> Table:
    left = [_p(left_title, styles["h2"])] + _bullets(left_items, styles)
    right = [_p(right_title, styles["h2"])] + _bullets(right_items, styles)
    table = Table([[left, right]], colWidths=[86 * mm, 86 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#EDF6F2")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F8EEEE")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DEE3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def build_ticker_report(db, ticker: str, cfg: dict, shared: list[str], as_of: dt.date, path: Path) -> dict[str, Any]:
    styles = _styles()
    company = build_company_data(db, ticker, mode="TTM", fetch_live=False)
    valuation = valuate(company.model_copy(deep=True))
    fair_value = float(valuation["blended_fair_value_per_share"])
    upside = fair_value / company.current_price - 1.0
    scenarios = run_scenario_analysis(company.model_copy(deep=True))
    consensus = _consensus(db, ticker, as_of)
    story = []

    story += [
        _p(ticker, styles["title"]),
        _p(cfg["title"], styles["subtitle"]),
        HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=6 * mm),
        _metric_table(
            [
                (_fmt(company.current_price), "Giá đóng cửa 28/08"),
                (_fmt(fair_value), "Giá trị hợp lý hệ thống"),
                (f"{upside:+.1%}", "Upside base case"),
                (valuation.get("recommendation", "N/A"), "Tín hiệu máy"),
            ],
            styles,
        ),
        Spacer(1, 6 * mm),
        _p("Kết luận kiểm chứng", styles["h1"]),
        _p(cfg["data_verdict"], styles["body"]),
        _p(
            "Mức tin cậy: TRUNG BÌNH - THẤP. Dữ liệu hiện tại đã được sửa theo nguồn chính thức, "
            "nhưng mô hình cấp mã chưa có golden test độc lập. Không dùng riêng con số này để đặt lệnh.",
            styles["body"],
        ),
        Spacer(1, 4 * mm),
        _two_columns("Luận điểm ủng hộ", cfg["bull"], "Luận điểm phản đối", cfg["bear"], styles),
        PageBreak(),
    ]

    story += [
        _p("1. Kiểm chứng dữ liệu", styles["h1"]),
        _p("Đối chiếu bản hợp nhất với công bố doanh nghiệp/VSDC. Đơn vị theo từng dòng.", styles["body"]),
        _table(
            ["Chỉ tiêu", "Nguồn chính thức", "Hệ thống sau sửa", "Lệch", "Kết luận"],
            _audit_rows(db, company, cfg),
            [47 * mm, 34 * mm, 37 * mm, 24 * mm, 28 * mm],
            styles,
            status_column=4,
        ),
        Spacer(1, 4 * mm),
        _p("Chỉ tiêu ngoài mô hình", styles["h2"]),
        *_bullets(cfg["external_metrics"], styles),
        _p("Điểm dữ liệu còn yếu", styles["h2"]),
        *_bullets(shared, styles),
        PageBreak(),
    ]

    years, hist_rows = _history_rows(company)
    scenario_rows = []
    for name in ("Bull", "Base", "Bear"):
        target = float(scenarios[name])
        scenario_rows.append([name, _fmt(target), f"{target / company.current_price - 1:+.1%}"])
    story += [
        _p("2. Tài chính và định giá", styles["h1"]),
        _p(f"Bản chất ngành: {cfg['sector_view']}.", styles["body"]),
        _p("Lịch sử gần nhất", styles["h2"]),
        _table(
            ["Tỷ đồng"] + years,
            hist_rows,
            [42 * mm] + [32 * mm] * len(years),
            styles,
        ),
        Spacer(1, 4 * mm),
        _p("Kịch bản engine", styles["h2"]),
        _table(
            ["Kịch bản", "Giá trị/cp", "Upside"],
            scenario_rows,
            [58 * mm, 58 * mm, 58 * mm],
            styles,
        ),
        Spacer(1, 4 * mm),
    ]
    if len({float(value) for value in scenarios.values()}) == 1:
        story += [
            _p(
                "Lưu ý: model EV/EBITDA của mã này chưa co giãn theo cấu hình Bull/Bear; "
                "ba dòng trùng nhau không phải là tuyên bố rủi ro bằng 0.",
                styles["body"],
            )
        ]
    if consensus:
        divergence = fair_value / consensus["median"] - 1.0
        story += [
            _p("Đối chiếu CTCK 180 ngày", styles["h2"]),
            _p(
                f"{consensus['count']} CTCK, trung vị {_fmt(consensus['median'])} đồng/cp, "
                f"biên {_fmt(consensus['min'])}-{_fmt(consensus['max'])}. Mô hình cao hơn trung vị {divergence:+.1%}.",
                styles["body"],
            ),
        ]
    story += [
        _p("Giải thích trọng yếu", styles["h2"]),
        _p(
            "Giá trị hợp lý phản ánh phương pháp routing theo ngành. Ngân hàng dùng Residual Income + P/B; "
            "PVT dùng EV/EBITDA chuẩn hóa chu kỳ; GAS dùng DCF phối hợp EV/EBITDA. Tiền và đầu tư ngắn hạn "
            "được cộng trong cầu nối EV, còn NCI được trừ để chỉ giữ phần thuộc cổ đông công ty mẹ.",
            styles["body"],
        ),
        PageBreak(),
    ]

    story += [
        _p("3. Phản biện và điều kiện hành động", styles["h1"]),
        _p("Phản biện mạnh nhất", styles["h2"]),
        *_bullets(cfg["counter"], styles),
        _p("Điều kiện xác nhận luận điểm", styles["h2"]),
        *_bullets(cfg["catalysts"], styles),
        _p("Điều gì khiến kết luận đổi chiều?", styles["h2"]),
        _p(
            "Chuyển sang Bear case khi các chỉ tiêu cốt lõi không đạt giả định engine trong hai quý liên tiếp, "
            "hoặc xuất hiện thay đổi chất lượng tài sản/dòng tiền/cơ cấu vốn không được phản ánh trong dữ liệu hiện tại.",
            styles["body"],
        ),
        _p("Kết luận sử dụng", styles["h2"]),
        _p(
            "Có thể dùng báo cáo này để lập danh sách theo dõi và chuẩn bị câu hỏi thẩm định. Chưa đủ điều kiện "
            "để coi giá trị hợp lý là giá mục tiêu đầu tư chính thức cho đến khi hoàn thành golden test.",
            styles["body"],
        ),
        Spacer(1, 4 * mm),
        _p("Nguồn kiểm chứng", styles["h2"]),
    ]
    for source in cfg["sources"]:
        story.append(_p(source, styles["source"]))

    doc = _doc(path, f"Báo cáo kiểm chứng {ticker}")
    doc.build(story)
    return {
        "ticker": ticker,
        "price": company.current_price,
        "fair_value": fair_value,
        "upside": upside,
        "recommendation": valuation.get("recommendation", "N/A"),
        "scenarios": scenarios,
        "consensus": consensus,
        "path": str(path),
    }


def build_overview(results: list[dict[str, Any]], cfg: dict, path: Path) -> None:
    styles = _styles()
    by_ticker = {row["ticker"]: row for row in results}
    comparison = []
    for ticker in ("ACB", "CTG", "PVT", "GAS"):
        row = by_ticker[ticker]
        consensus = row["consensus"]
        comparison.append(
            [
                ticker,
                _fmt(row["price"]),
                _fmt(row["fair_value"]),
                f"{row['upside']:+.1%}",
                _fmt(consensus["median"]) if consensus else "N/A",
                f"{row['fair_value'] / consensus['median'] - 1:+.1%}" if consensus else "N/A",
            ]
        )

    story = [
        _p("Bốn mã ngân hàng và dầu khí", styles["title"]),
        _p("Tổng hợp kiểm chứng, so sánh và phản biện | Dữ liệu đến 29/08/2026", styles["subtitle"]),
        HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=6 * mm),
        _p("Kết luận ngắn", styles["h1"]),
        _p(
            "Không có một mã tốt nhất cho mọi khẩu vị. ACB có chất lượng tài sản tốt và độ lệch mô hình thấp hơn; "
            "CTG có upside lớn nhưng nhạy với giả định ROE/PB; PVT có upside máy cao nhất nhưng cũng có rủi ro "
            "chu kỳ và chênh lớn nhất với CTCK; GAS có bảng cân đối mạnh nhất nhưng upside thấp hơn PVT/CTG.",
            styles["body"],
        ),
        _table(
            ["Mã", "Giá", "FV hệ thống", "Upside", "Trung vị CTCK", "FV lệch CTCK"],
            comparison,
            [20 * mm, 29 * mm, 34 * mm, 27 * mm, 36 * mm, 31 * mm],
            styles,
        ),
        Spacer(1, 5 * mm),
        _p("Ba cách chọn", styles["h1"]),
        _two_columns(
            "Phòng thủ: ACB + GAS",
            [
                "Ưu tiên chất lượng tài sản, thanh khoản và bảng cân đối.",
                "Chấp nhận upside không cao nhất để giảm rủi ro mô hình và chu kỳ.",
            ],
            "Tấn công: CTG + PVT",
            [
                "Ưu tiên upside định giá và đòn bẩy chu kỳ lợi nhuận.",
                "Cần biên an toàn lớn hơn vì cả hai có độ lệch đáng kể với CTCK.",
            ],
            styles,
        ),
        Spacer(1, 4 * mm),
        _p("Cân bằng: ACB + PVT", styles["h2"]),
        _p(
            "ACB đóng vai trò chất lượng/phòng thủ trong ngân hàng; PVT cung cấp động lực tăng trưởng và đa dạng "
            "ngành. Đây là cặp hợp lý hơn nếu chỉ chọn hai mã nhưng vẫn chấp nhận rủi ro chu kỳ ở mức vừa.",
            styles["body"],
        ),
        PageBreak(),
        _p("1. Góc nhìn đối lập", styles["h1"]),
    ]

    for ticker in ("ACB", "CTG", "PVT", "GAS"):
        item = cfg["tickers"][ticker]
        story += [
            KeepTogether(
                [
                    _p(f"{ticker}: vì sao có thể sai?", styles["h2"]),
                    *_bullets(item["counter"], styles),
                ]
            )
        ]
    story += [
        _p("Rủi ro chung", styles["h2"]),
        *_bullets(cfg["shared_limitations"], styles),
        PageBreak(),
        _p("2. Ma trận ra quyết định", styles["h1"]),
        _table(
            ["Tiêu chí", "ACB", "CTG", "PVT", "GAS"],
            [
                ["Chất lượng dữ liệu sau sửa", "Tốt", "Tốt", "Tốt - đã restated", "Tốt - đã bổ sung tiền gửi"],
                ["Rủi ro mô hình", "Vừa", "Vừa-cao", "Cao", "Vừa-cao"],
                ["Rủi ro chu kỳ", "Vừa", "Vừa", "Cao", "Cao"],
                ["Sức mạnh bảng cân đối", "Tốt", "Tốt", "Khá", "Rất tốt"],
                ["Độ lệch với CTCK", "Thấp-vừa", "Vừa", "Cao", "Vừa-cao"],
                ["Vai trò phù hợp", "Lõi chất lượng", "Value/cyclical bank", "Tăng trưởng chu kỳ", "Phòng thủ năng lượng"],
            ],
            [44 * mm, 33 * mm, 33 * mm, 33 * mm, 33 * mm],
            styles,
        ),
        Spacer(1, 5 * mm),
        _p("Thứ tự ưu tiên theo mục tiêu", styles["h2"]),
        *_bullets(
            [
                "Bảo toàn vốn tương đối: ACB, GAS, CTG, PVT.",
                "Upside theo engine: PVT, CTG, ACB, GAS.",
                "Độ tin cậy sau phản biện: ACB, CTG, GAS, PVT.",
                "Không mua đuổi chỉ vì upside máy; kiểm tra lại giá mục tiêu sau mỗi BCTC quý.",
            ],
            styles,
        ),
        _p("Kết luận cuối", styles["h2"]),
        _p(
            "Nếu buộc chọn một mã duy nhất theo tỷ lệ lợi nhuận/rủi ro, ACB là lựa chọn thận trọng hơn. Nếu chấp "
            "nhận biến động và yêu cầu upside cao, CTG là lựa chọn ngân hàng hấp dẫn hơn nhưng cần hạ giá mục tiêu "
            "về gần vùng CTCK để có biên an toàn. Trong dầu khí, GAS phù hợp phòng thủ; PVT chỉ phù hợp khi nhà đầu "
            "tư chấp nhận chu kỳ và coi 32,3 nghìn là kịch bản lạc quan cần kiểm chứng thêm.",
            styles["body"],
        ),
        _p("Lưu ý", styles["h2"]),
        _p(
            "Đây là tài liệu nghiên cứu, không phải tư vấn đầu tư cá nhân. Giá trị hợp lý thay đổi khi giả định, "
            "dữ liệu, lãi suất và giá thị trường thay đổi.",
            styles["body"],
        ),
    ]
    _doc(path, "Tổng hợp phản biện 4 mã").build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    _register_fonts()
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    as_of = dt.date.fromisoformat(cfg["as_of_date"])
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    with SessionLocalRead() as db:
        for ticker in ("ACB", "CTG", "PVT", "GAS"):
            path = args.output_dir / f"Bao_cao_kiem_chung_{ticker}.pdf"
            results.append(
                build_ticker_report(
                    db,
                    ticker,
                    cfg["tickers"][ticker],
                    cfg["shared_limitations"],
                    as_of,
                    path,
                )
            )
        build_overview(
            results,
            cfg,
            args.output_dir / "Tong_hop_phan_bien_4_ma.pdf",
        )
    for result in results:
        print(
            f"{result['ticker']}: FV={result['fair_value']:,.0f}, "
            f"upside={result['upside']:+.1%}, file={result['path']}"
        )


if __name__ == "__main__":
    main()
