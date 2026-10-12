"""Đồng bộ snapshot VN100 vào bảng tickers mà không xóa lịch sử."""
from valuation.config import settings
from valuation.db.models import Ticker
from valuation.db.session import SessionLocalWrite
from valuation.engine.sector_router import route
from valuation.ingest.universe import get_vn100_symbols, sync_vn100_membership
from valuation.ingest.vnstock_client import vnstock_client


_DB_SECTOR_MAP = {
    "NH": "Banks",
    "CK": "Securities",
    "BH": "Insurance",
    "BĐS": "Real Estate",
    "KCN": "Industrial Real Estate",
    "Công nghệ": "Technology",
    "Điện": "Utilities",
    "Nước": "Utilities",
    "Tiện ích": "Utilities",
    "Bán lẻ": "Retail",
    "Tiêu dùng": "Consumer",
}


def _metadata_from_vnstock(symbol: str) -> dict:
    overview = vnstock_client.get_company_overview(symbol)
    if overview.empty:
        raise ValueError(f"vnstock không trả metadata cho {symbol}")
    row = overview.iloc[0]
    plan = route(symbol) or {}
    routing_sector = plan.get("group", "")
    return {
        "company_name": row.get("organ_name") or symbol,
        "exchange": "HOSE",
        "sector": _DB_SECTOR_MAP.get(routing_sector, routing_sector),
        "industry": row.get("sector") or routing_sector,
    }


def main() -> None:
    if settings.vnstock_api_key:
        from vnstock.core import setup_api_key

        setup_api_key(settings.vnstock_api_key)

    symbols = get_vn100_symbols()
    db = SessionLocalWrite()
    try:
        existing = {row[0] for row in db.query(Ticker.ticker).all()}
        missing = [symbol for symbol in symbols if symbol not in existing]
        metadata = {symbol: _metadata_from_vnstock(symbol) for symbol in missing}
        result = sync_vn100_membership(db, symbols, metadata)
        print(
            f"VN100: {result['members']} mã; thêm {result['added']}; "
            f"đổi trạng thái {result['changed']}."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
