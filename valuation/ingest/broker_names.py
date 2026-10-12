"""Chuẩn hoá tên công ty chứng khoán (CTCK) giữa các nguồn — D24.

Bài toán: cùng một CTCK xuất hiện dưới nhiều tên tuỳ nguồn ("MIRAE" trên
24hmoney vs "MAS" trên Simplize), và đường vnstock còn ghép cả tên chuyên viên
vào ("VCI (Nguyen Van A)"). Không gộp lại thì một CTCK bị đếm thành nhiều phiếu
trong median đồng thuận.

Nguyên tắc an toàn: KHÔNG khớp được alias thì GIỮ NGUYÊN tên gốc và báo
`matched=False` — thà để hai dòng riêng còn hơn gộp nhầm hai công ty khác nhau
(gộp nhầm làm sai median mà không ai thấy).
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Optional

from valuation.config import PROJECT_ROOT

_ALIASES_FILE = PROJECT_ROOT / "config" / "broker_aliases.yaml"

# Hậu tố trong ngoặc: "VCI (Nguyen Van A)" -> "VCI". Nguồn vnstock ghép tên
# chuyên viên vào tên CTCK, khiến cùng một nhà bị tách thành nhiều "CTCK".
_PAREN = re.compile(r"\s*\([^)]*\)")
# Các hậu tố pháp lý/mô tả không mang thông tin phân biệt.
_NOISE = re.compile(
    r"\b(RESEARCH|SECURITIES|SECURITY|CTCK|CTY|CONG TY|JSC|CORP|COMPANY|LTD)\b"
)


def _load_config() -> dict:
    import yaml
    if not _ALIASES_FILE.exists():
        return {}
    with open(_ALIASES_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _clean(raw: str) -> str:
    """Đưa tên thô về dạng so khớp: bỏ dấu, bỏ ngoặc, viết hoa, gộp khoảng trắng."""
    s = _strip_accents(str(raw or "")).upper()
    s = _PAREN.sub("", s)
    s = s.replace("-", " ").replace("_", " ").replace(".", " ")
    s = _NOISE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """alias (đã chuẩn hoá) -> mã CTCK chuẩn."""
    cfg = _load_config()
    index: dict[str, str] = {}
    for code, entry in (cfg.get("canonical") or {}).items():
        code_up = str(code).upper()
        index[_clean(code_up)] = code_up
        for alias in (entry or {}).get("aliases", []) or []:
            index[_clean(alias)] = code_up
    return index


@lru_cache(maxsize=1)
def _display_index() -> dict[str, str]:
    cfg = _load_config()
    return {
        str(code).upper(): (entry or {}).get("name", str(code).upper())
        for code, entry in (cfg.get("canonical") or {}).items()
    }


def normalize_broker(raw: str) -> tuple[str, bool]:
    """Trả (mã CTCK chuẩn, đã_khớp_alias).

    Chưa khớp → trả tên đã làm sạch (hoặc tên gốc nếu làm sạch ra rỗng) và
    `False`, theo `unmatched_policy: keep_raw`.

    >>> normalize_broker("MAS")
    ('MIRAE', True)
    >>> normalize_broker("VCI (Nguyen Van A)")   # bỏ tên chuyên viên
    ('VCI', False)
    """
    cleaned = _clean(raw)
    if not cleaned:
        return (str(raw or "").strip(), False)
    hit = _alias_index().get(cleaned)
    if hit:
        return (hit, True)
    # Bỏ khoảng trắng thử lần nữa ("SSI RESEARCH" -> "SSIRESEARCH")
    compact = cleaned.replace(" ", "")
    hit = _alias_index().get(compact)
    if hit:
        return (hit, True)
    return (compact or cleaned, False)


def broker_display_name(code: str) -> str:
    """Tên hiển thị đầy đủ cho báo cáo; không có trong config thì trả lại mã."""
    return _display_index().get(str(code).upper(), str(code).upper())


def unmatched_policy() -> str:
    return str(_load_config().get("unmatched_policy", "keep_raw"))
