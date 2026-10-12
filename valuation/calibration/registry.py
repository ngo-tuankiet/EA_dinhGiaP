"""Sổ đăng ký hiệu chuẩn từng mã — cơ chế "giữ nguyên hay phải sửa" (D25).

Quyết định #1 của người dùng: mô hình ĐƯỢC PHÉP lệch khỏi đồng thuận CTCK, nhưng
mỗi lần lệch phải GIẢI TRÌNH ĐƯỢC bằng luận điểm cụ thể. Lệch mà không giải trình
được thì coi là lỗi giả định và phải sửa.

Module này biến nguyên tắc đó thành thứ máy kiểm tra được:
  - mã trong band            -> OK
  - ngoài band + có luận điểm còn hạn -> OK_JUSTIFIED (giữ nguyên mô hình)
  - ngoài band + KHÔNG luận điểm      -> MISSING_JUSTIFICATION (phải xử lý)
  - ngoài band + đã thừa nhận là lỗi  -> KNOWN_DEFECT (nằm trong backlog sửa)

Luận điểm CÓ HẠN (`review_ttl_days`): "đã giải thích một lần năm 2026" không cấp
quyền miễn nhiễm vĩnh viễn — bối cảnh doanh nghiệp thay đổi thì phải rà lại.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from valuation.config import PROJECT_ROOT

_REGISTRY_FILE = PROJECT_ROOT / "config" / "calibration_registry.yaml"

# --- Trạng thái khai báo trong registry ---
STATUS_JUSTIFIED = "out_of_band_justified"
STATUS_MUST_FIX = "out_of_band_must_fix"
STATUS_DATA_BLOCKED = "data_blocked"
_VALID_STATUSES = {STATUS_JUSTIFIED, STATUS_MUST_FIX, STATUS_DATA_BLOCKED}

# --- Kết luận governance gắn vào mỗi quan sát ---
GOV_OK = "OK"
GOV_OK_JUSTIFIED = "OK_JUSTIFIED"
GOV_MISSING = "MISSING_JUSTIFICATION"
GOV_STALE = "STALE_JUSTIFICATION"
GOV_KNOWN_DEFECT = "KNOWN_DEFECT"
GOV_DATA_BLOCKED = "DATA_BLOCKED"
GOV_OBSOLETE = "OBSOLETE_ENTRY"

_DEFAULT_TTL_DAYS = 180


class RegistryError(ValueError):
    """Registry sai cấu trúc — dừng sớm còn hơn chạy với giải trình rỗng."""


@dataclass(frozen=True)
class RegistryEntry:
    ticker: str
    status: str
    band: Optional[float]
    thesis: str
    evidence: tuple[str, ...]
    owner: str
    reviewed_on: Optional[datetime.date]
    expires_on: Optional[datetime.date]
    decision_ref: Optional[str]

    def is_expired(self, today: datetime.date) -> bool:
        return self.expires_on is not None and today > self.expires_on


def _as_date(value) -> Optional[datetime.date]:
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def load_registry(path=None, validate: bool = True) -> dict[str, RegistryEntry]:
    """Đọc config/calibration_registry.yaml -> {ticker: RegistryEntry}.

    Không có file → trả dict rỗng (hệ thống vẫn chạy, mọi mã ngoài band sẽ là
    MISSING_JUSTIFICATION — đúng ý: chưa khai báo tức là chưa giải trình).
    """
    import yaml

    p = path or _REGISTRY_FILE
    if not getattr(p, "exists", lambda: False)():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    ttl = int(cfg.get("review_ttl_days", _DEFAULT_TTL_DAYS))
    out: dict[str, RegistryEntry] = {}
    for ticker, raw in (cfg.get("tickers") or {}).items():
        raw = raw or {}
        status = str(raw.get("status", "")).strip()
        thesis = str(raw.get("thesis", "") or "").strip()
        evidence = tuple(str(e) for e in (raw.get("evidence") or []))
        reviewed = _as_date(raw.get("reviewed_on"))

        if validate:
            if status not in _VALID_STATUSES:
                raise RegistryError(
                    f"{ticker}: status '{status}' không hợp lệ (cho phép: {sorted(_VALID_STATUSES)})"
                )
            # Chỉ nhánh "đã giải trình" mới bắt buộc luận điểm + bằng chứng.
            # `must_fix` là thừa nhận LỖI nên không cần luận điểm bảo vệ.
            if status == STATUS_JUSTIFIED:
                if not thesis:
                    raise RegistryError(f"{ticker}: status={status} nhưng thesis rỗng")
                if not evidence:
                    raise RegistryError(f"{ticker}: status={status} nhưng thiếu evidence")
                if reviewed is None:
                    raise RegistryError(f"{ticker}: status={status} nhưng thiếu reviewed_on")

        out[str(ticker).upper()] = RegistryEntry(
            ticker=str(ticker).upper(),
            status=status,
            band=(float(raw["band"]) if raw.get("band") is not None else None),
            thesis=thesis,
            evidence=evidence,
            owner=str(raw.get("owner", "") or ""),
            reviewed_on=reviewed,
            expires_on=(reviewed + datetime.timedelta(days=ttl)) if reviewed else None,
            decision_ref=(str(raw["decision_ref"]) if raw.get("decision_ref") else None),
        )
    return out


def _config() -> dict:
    import yaml
    if not _REGISTRY_FILE.exists():
        return {}
    with open(_REGISTRY_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def band_for(
    ticker: str,
    method: Optional[str],
    registry: Optional[dict[str, RegistryEntry]] = None,
    default: float = 0.20,
) -> float:
    """Band áp dụng cho 1 mã: ưu tiên band riêng của mã > band theo PP > mặc định.

    Nới band cho SOTP/RNAV là có chủ ý: đó là phương pháp proxy dựa trên giá trị
    sổ sách/quỹ đất, sai số bản chất lớn hơn DCF — bắt chúng vào ±20% sẽ tạo ra
    hàng loạt "vi phạm" giả.
    """
    cfg = _config()
    entry = (registry or {}).get(str(ticker).upper())
    if entry is not None and entry.band is not None:
        return entry.band
    by_method = cfg.get("bands_by_method") or {}
    if method and method in by_method:
        return float(by_method[method])
    return float(cfg.get("default_band", default))


def govern(
    ticker: str,
    band_status: str,
    registry: Optional[dict[str, RegistryEntry]] = None,
    today: Optional[datetime.date] = None,
) -> tuple[str, Optional[RegistryEntry]]:
    """Kết luận governance cho 1 mã. Trả (governance_status, entry|None).

    `band_status` là kết quả đo (IN_BAND / OUT_HIGH / OUT_LOW / NO_CONSENSUS /
    ERROR) từ `metrics.classify_band`.
    """
    today = today or datetime.date.today()
    entry = (registry or {}).get(str(ticker).upper())

    if entry is not None and entry.status == STATUS_DATA_BLOCKED:
        return (GOV_DATA_BLOCKED, entry)

    # Không đo được thì không phán xét (thiếu consensus không phải lỗi mô hình).
    if band_status in ("NO_CONSENSUS", "ERROR"):
        return (GOV_OK, entry)

    if band_status == "IN_BAND":
        # Đã vào band mà registry còn ghi "ngoài band" -> dọn registry.
        if entry is not None and entry.status in (STATUS_JUSTIFIED, STATUS_MUST_FIX):
            return (GOV_OBSOLETE, entry)
        return (GOV_OK, entry)

    # --- Ngoài band ---
    if entry is None:
        return (GOV_MISSING, None)
    if entry.status == STATUS_MUST_FIX:
        return (GOV_KNOWN_DEFECT, entry)
    if entry.status == STATUS_JUSTIFIED:
        return (GOV_STALE if entry.is_expired(today) else GOV_OK_JUSTIFIED, entry)
    return (GOV_MISSING, entry)


def summarize(observations) -> dict[str, int]:
    """Đếm governance_status cho báo cáo cuối mỗi lần chạy hiệu chuẩn."""
    out: dict[str, int] = {}
    for o in observations:
        key = getattr(o, "governance_status", GOV_OK)
        out[key] = out.get(key, 0) + 1
    return out
