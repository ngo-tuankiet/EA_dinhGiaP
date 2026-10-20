from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULTS_FILE = PROJECT_ROOT / "config" / "defaults.yaml"


@lru_cache(maxsize=1)
def load_defaults() -> dict:
    if DEFAULTS_FILE.exists():
        with open(DEFAULTS_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


EVENT_HOLDS_FILE = PROJECT_ROOT / "config" / "event_holds.yaml"


def load_event_holds() -> dict:
    """Mã đang bị analyst chặn công bố vì sự kiện trọng yếu mô hình chưa phản ánh (D46)."""
    if not EVENT_HOLDS_FILE.exists():
        return {}
    with open(EVENT_HOLDS_FILE, "r", encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("holds") or {}


def active_event_hold(ticker: str, as_of, holds: dict | None = None) -> dict | None:
    """Trả hold đang hiệu lực (since ≤ as_of) của mã, hoặc None. Thiếu lý do/nguồn → lỗi."""
    from datetime import date

    holds = load_event_holds() if holds is None else holds
    hold = {k.upper(): v for k, v in holds.items()}.get(ticker.upper())
    if not hold:
        return None
    if not hold.get("reason") or not hold.get("source"):
        raise ValueError(f"event_holds.yaml: {ticker} thiếu reason/source")
    return hold if date.fromisoformat(str(hold["since"])) <= as_of else None


SOTP_HOLDINGS_FILE = PROJECT_ROOT / "config" / "sotp_holdings.yaml"


@lru_cache(maxsize=1)
def load_sotp_holdings() -> dict:
    """Cổ phần niêm yết của các tập đoàn SOTP (config/sotp_holdings.yaml, chế độ SOTP_HOLDINGS)."""
    if not SOTP_HOLDINGS_FILE.exists():
        return {}
    with open(SOTP_HOLDINGS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def sotp_holding_tickers() -> set[str]:
    """Mọi mã công ty con/liên kết niêm yết khai trong config/sotp_holdings.yaml (viết hoa)."""
    holders = (load_sotp_holdings().get("holders") or {}).values()
    return {str(h["ticker"]).upper() for e in holders for h in e.get("holdings") or []}


def sotp_holdings_for(ticker: str, cfg: dict | None = None) -> dict | None:
    """Khai báo holdings đã kiểm tra hợp lệ của mã, hoặc None. Sai cấu trúc → ValueError (không đoán)."""
    cfg = load_sotp_holdings() if cfg is None else cfg
    holders = {k.upper(): v for k, v in (cfg.get("holders") or {}).items()}
    entry = holders.get(ticker.upper())
    if not entry:
        return None
    holdings = entry.get("holdings") or []
    if not holdings:
        raise ValueError(f"sotp_holdings.yaml: {ticker} khai báo nhưng không có holding nào")
    for h in holdings:
        sub = str(h.get("ticker") or "").upper()
        stake = h.get("stake")
        if not sub or not isinstance(stake, (int, float)) or not 0 < stake <= 1:
            raise ValueError(f"sotp_holdings.yaml: {ticker}/{sub or '?'} cần ticker và 0 < stake ≤ 1")
        if not str(h.get("source") or "").startswith("https://"):
            raise ValueError(f"sotp_holdings.yaml: {ticker}/{sub} thiếu source (URL https)")
        if sub in holders:
            raise ValueError(f"sotp_holdings.yaml: {sub} vừa là holding của {ticker} vừa là holder (đệ quy)")
    if entry.get("reviewed_by"):
        # Không có ngày duyệt thì TTL review_ttl_days không bao giờ hết hạn → bắt buộc as_of hợp lệ.
        from datetime import date

        try:
            date.fromisoformat(str(entry.get("as_of") or "")[:10])
        except ValueError:
            raise ValueError(
                f"sotp_holdings.yaml: {ticker} có reviewed_by nhưng as_of thiếu/sai (YYYY-MM-DD)"
            ) from None
    return {**entry, "review_ttl_days": int(cfg["review_ttl_days"])}


_defaults = load_defaults()


ELASTICITIES_FILE = PROJECT_ROOT / "config" / "elasticities.yaml"


@lru_cache(maxsize=1)
def load_elasticities() -> dict:
    """Đọc config macro overlay (elasticities.yaml)."""
    if ELASTICITIES_FILE.exists():
        with open(ELASTICITIES_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_cash_reconciliation_tolerance() -> dict:
    """Ngưỡng đối chiếu Δtiền = CFO - CapEx + cf_other (xem config/defaults.yaml)."""
    defaults = {
        "abs_tolerance_billion_vnd": 1.0,
        "pct_total_assets_tolerance": 0.5,
        "pct_delta_cash_tolerance": 2.0,
    }
    cfg = _defaults.get("cash_reconciliation") or {}
    return {**defaults, **cfg}


def get_macro_series_registry() -> dict:
    """Registry các series_code vĩ mô được phép ghi vào macro_series."""
    return _defaults.get("macro_series_registry", {})


def get_macro_allowed_domains() -> list[str]:
    """Allowlist domain mà scraper macro được phép gọi (Bảo mật mục 5)."""
    return list(_defaults.get("macro_sources", {}).get("allowed_domains", []))


def get_macro_source_config() -> dict:
    """Cấu hình chung cho scraper macro (timeout, user-agent, allowlist)."""
    return _defaults.get("macro_sources", {})


class Settings(BaseSettings):
    vnstock_api_key: str = Field(default="")
    database_url_readonly: str = Field(default="sqlite:///vn100_full.db")
    database_url_write: str = Field(default="sqlite:///vn100_full.db")
    google_service_account_json: str = Field(default="")
    google_sheet_master_id: str = Field(default="")
    google_drive_folder_id: str = Field(default="")
    discord_webhook_url: str = Field(default="")
    recompute_webhook_token: str = Field(default="")
    deepseek_api_key: str = Field(default="")
    discord_bot_token: str = Field(default="")
    discord_owner_id: str = Field(default="")
    discord_channel_id: str = Field(default="")

    erp_vn: float = Field(default=_defaults.get("erp_vn", 8.5))

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
