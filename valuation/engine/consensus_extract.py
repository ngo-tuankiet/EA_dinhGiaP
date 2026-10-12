"""Bóc tách luận điểm CTCK bằng REGEX TẤT ĐỊNH — không dùng LLM (D31).

Vì sao không LLM: kết quả phải TÁI LẬP ĐƯỢC và AUDIT ĐƯỢC. Cùng một đoạn văn
phải luôn cho cùng một kết quả, và người đọc phải truy được con số bóc ra từ
CHỮ NÀO trong bản gốc (`matched_spans`). LLM cho cả hai thứ đó đều không đảm bảo,
lại tốn token cho việc mà regex làm đủ tốt.

Quy tắc vàng của module này: **thiếu dữ liệu thì trả None, TUYỆT ĐỐI không trả 0**.
Một `target_pe = 0` sẽ lặng lẽ kéo mọi thống kê xuống; `None` thì bị loại khỏi
phép tính. `confidence` = tỷ lệ trường bóc được, để báo cáo hiển thị dạng đếm
("6/11 CTCK nêu phương pháp") thay vì bịa một giá trị trung bình.

Mẫu ngôn ngữ lấy từ dữ liệu THẬT trên 24hmoney (khảo sát 2026-08-11), ví dụ:
  "Dự phóng cả năm 2026 LNST đạt 17.207 tỷ đồng (+10,1% YoY)"
  "P/B dự phóng cho năm 2026 đạt 1,1x"  |  "P/E dự phóng 2026 đạt 10,7x"
  "ROE dự kiến đạt 20,8%"  |  "giá mục tiêu là 27.000 đồng/cổ phiếu"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

EXTRACT_VERSION = "v1"

# Số kiểu Việt Nam: "17.207" (nghìn = dấu chấm), "10,1" (thập phân = dấu phẩy).
_NUM = r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)"


def _to_float(s: str) -> Optional[float]:
    """'17.207' -> 17207.0 ; '10,1' -> 10.1 ; '1,1' -> 1.1"""
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


# --- Bội số mục tiêu ---
_RE_PB = re.compile(rf"P/?B\s*(?:dự\s*phóng|mục\s*tiêu|forward|fw)?[^.\n]{{0,25}}?{_NUM}\s*(?:x|lần)", re.I)
_RE_PE = re.compile(rf"P/?E\s*(?:dự\s*phóng|mục\s*tiêu|forward|fw)?[^.\n]{{0,25}}?{_NUM}\s*(?:x|lần)", re.I)
_RE_EVEBITDA = re.compile(rf"EV/?EBITDA[^.\n]{{0,25}}?{_NUM}\s*(?:x|lần)", re.I)
# --- Tỷ suất ---
_RE_ROE = re.compile(rf"ROE[^.\n]{{0,30}}?{_NUM}\s*%", re.I)
_RE_WACC = re.compile(rf"WACC[^.\n]{{0,25}}?{_NUM}\s*%", re.I)
_RE_COE = re.compile(rf"(?:COE|chi\s*phí\s*vốn\s*(?:cổ\s*phần)?)[^.\n]{{0,25}}?{_NUM}\s*%", re.I)
# --- Giá mục tiêu / upside ---
_RE_TP = re.compile(rf"giá\s*mục\s*tiêu[^.\n]{{0,20}}?{_NUM}\s*(?:đồng|VND|₫)", re.I)
_RE_UPSIDE = re.compile(rf"upside[^.\n]{{0,30}}?{_NUM}\s*%", re.I)
# --- Dự phóng lợi nhuận / doanh thu (kèm năm và tăng trưởng) ---
_RE_NI = re.compile(
    rf"(?:LNST|lợi\s*nhuận\s*sau\s*thuế|LNTT)[^.\n]{{0,40}}?đạt\s*{_NUM}\s*tỷ", re.I)
_RE_REV = re.compile(
    rf"doanh\s*thu[^.\n]{{0,40}}?đạt\s*{_NUM}\s*tỷ", re.I)
_RE_GROWTH = re.compile(rf"\(\s*([+\-])\s*{_NUM}\s*%\s*(?:YoY|svck|so\s*với\s*cùng\s*kỳ)", re.I)
_RE_YEAR = re.compile(r"\b(20\d{2})\b")

# --- Từ khoá phương pháp định giá ---
_METHOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "DCF": ("chiết khấu dòng tiền", "dcf", "fcff", "fcfe"),
    "RI": ("thu nhập thặng dư", "residual income"),
    "PB": ("p/b", "pb mục tiêu", "so sánh p/b"),
    "PE": ("p/e", "pe mục tiêu"),
    "EV_EBITDA": ("ev/ebitda",),
    "RNAV": ("rnav", "giá trị tài sản ròng"),
    "SOTP": ("sotp", "tổng các phần", "sum of the parts"),
    "DDM": ("ddm", "chiết khấu cổ tức"),
}


@dataclass(frozen=True)
class ThesisExtract:
    methods: tuple[str, ...] = ()
    target_pb: Optional[float] = None
    target_pe: Optional[float] = None
    target_ev_ebitda: Optional[float] = None
    forecast_roe: Optional[float] = None          # dạng thập phân (0,208)
    wacc: Optional[float] = None
    coe: Optional[float] = None
    target_price: Optional[float] = None          # VND/cp
    upside: Optional[float] = None                # thập phân
    forecast_net_income_ty: Optional[float] = None
    forecast_revenue_ty: Optional[float] = None
    forecast_growth: Optional[float] = None       # thập phân, +/- theo văn bản
    forecast_years: tuple[int, ...] = ()
    confidence: float = 0.0
    matched_spans: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}
        d["extract_version"] = EXTRACT_VERSION
        return d


# Từ khoá cho biết câu đang nói về DỰ PHÓNG (tương lai), không phải kết quả đã có.
_FORECAST_CUES = ("dự phóng", "dự báo", "kỳ vọng", "cả năm", "ước tính", "forecast")
# Từ khoá cho biết câu đang nói về KẾT QUẢ ĐÃ CÔNG BỐ (quá khứ).
_ACTUAL_CUES = ("q1/", "q2/", "q3/", "q4/", "quý ", "6t20", "9t20", "lũy kế",
                "đạt được", "ghi nhận", "hoàn thành")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _first(pattern: re.Pattern, text: str, spans: list) -> Optional[float]:
    m = pattern.search(text)
    if not m:
        return None
    spans.append(m.group(0).strip())
    return _to_float(m.group(1))


def _first_forecast(pattern: re.Pattern, text: str, spans: list) -> Optional[float]:
    """Như `_first` nhưng ƯU TIÊN câu mang ngữ cảnh dự phóng.

    Cần thiết vì một tóm tắt thường chứa CẢ kết quả quý vừa công bố LẪN dự phóng
    cả năm. Ví dụ thật (NHSV/ACB): "...Q2/2026 với lợi nhuận sau thuế đạt 4.292 tỷ
    đồng (-12,1% YoY). Dự phóng cả năm 2026 LNST đạt 17.207 tỷ đồng (+10,1% YoY)".
    Lấy khớp ĐẦU TIÊN sẽ ra 4.292 (lợi nhuận quý) — sai hoàn toàn về ý nghĩa.
    """
    fallback = None
    for sent in _sentences(text):
        m = pattern.search(sent)
        if not m:
            continue
        low = sent.lower()
        is_forecast = any(c in low for c in _FORECAST_CUES)
        is_actual = any(c in low for c in _ACTUAL_CUES)
        if is_forecast and not is_actual:
            spans.append(m.group(0).strip())
            return _to_float(m.group(1))
        if fallback is None:
            fallback = m
    if fallback is None:
        return None
    # Không câu nào thuần dự phóng -> lấy khớp đầu nhưng ĐÁNH DẤU để người đọc
    # biết con số này có thể là kết quả đã công bố, không phải dự phóng.
    spans.append(fallback.group(0).strip() + " [KHÔNG RÕ: dự phóng hay đã công bố]")
    return _to_float(fallback.group(1))


def extract_thesis(text: str) -> ThesisExtract:
    """Bóc các con số/phương pháp nêu công khai trong đoạn tóm tắt luận điểm."""
    if not text or not text.strip():
        return ThesisExtract()

    spans: list[str] = []
    t = text

    target_pb = _first(_RE_PB, t, spans)
    target_pe = _first(_RE_PE, t, spans)
    ev_ebitda = _first(_RE_EVEBITDA, t, spans)
    roe = _first(_RE_ROE, t, spans)
    wacc = _first(_RE_WACC, t, spans)
    coe = _first(_RE_COE, t, spans)
    tp = _first(_RE_TP, t, spans)
    upside = _first(_RE_UPSIDE, t, spans)
    # Lợi nhuận/doanh thu: BẮT BUỘC ưu tiên câu dự phóng — tóm tắt thường nêu cả
    # kết quả quý vừa công bố lẫn dự phóng cả năm trong hai câu liền nhau.
    ni = _first_forecast(_RE_NI, t, spans)
    rev = _first_forecast(_RE_REV, t, spans)

    growth = None
    for sent in _sentences(t):
        mg = _RE_GROWTH.search(sent)
        if not mg:
            continue
        low = sent.lower()
        if any(c in low for c in _FORECAST_CUES) and not any(c in low for c in _ACTUAL_CUES):
            spans.append(mg.group(0).strip())
            val = _to_float(mg.group(2))
            if val is not None:
                growth = (val / 100.0) * (-1.0 if mg.group(1) == "-" else 1.0)
            break

    low = t.lower()
    methods = tuple(
        code for code, kws in _METHOD_KEYWORDS.items() if any(k in low for k in kws)
    )
    years = tuple(sorted({int(y) for y in _RE_YEAR.findall(t)}))

    # confidence = tỷ lệ trường bóc được / tổng số trường cố gắng bóc.
    attempted = [target_pb, target_pe, ev_ebitda, roe, wacc, coe, tp, upside, ni, rev, growth]
    matched = sum(1 for x in attempted if x is not None) + (1 if methods else 0)
    confidence = matched / (len(attempted) + 1)

    return ThesisExtract(
        methods=methods,
        target_pb=target_pb,
        target_pe=target_pe,
        target_ev_ebitda=ev_ebitda,
        forecast_roe=(roe / 100.0) if roe is not None else None,
        wacc=(wacc / 100.0) if wacc is not None else None,
        coe=(coe / 100.0) if coe is not None else None,
        target_price=tp,
        upside=(upside / 100.0) if upside is not None else None,
        forecast_net_income_ty=ni,
        forecast_revenue_ty=rev,
        forecast_growth=growth,
        forecast_years=years,
        confidence=round(confidence, 3),
        matched_spans=tuple(spans),
    )
