"""
DEPRECATED shim — ValuationRouter đã chuyển về valuation.engine.sector_router
(nguồn sự thật routing DUY NHẤT). Giữ file này để consumer cũ import không vỡ.
"""
from valuation.engine.sector_router import ValuationRouter  # noqa: F401
