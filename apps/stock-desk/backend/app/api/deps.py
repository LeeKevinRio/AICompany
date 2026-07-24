"""FastAPI dependency providers for the position/portfolio routers.

Production wiring is built lazily and memoized (``functools.lru_cache``) so the
underlying HTTP clients and SQLite handles are created once per process, and
only when a route actually needs them. Tests override these via
``app.dependency_overrides`` and therefore never construct the real adapters
or touch the network.
"""

from __future__ import annotations

from functools import lru_cache

from app.data.cache import PriceBarCache
from app.data.providers.finmind import FinMindAdapter
from app.data.providers.fx import BankOfTaiwanFxAdapter
from app.data.providers.tpex import TpexAdapter
from app.data.providers.twse import TwseAdapter
from app.data.service import MarketDataService
from app.portfolio.valuation import PositionValuator, PriceService
from app.positions.models import Market
from app.positions.store import PositionStore


@lru_cache(maxsize=1)
def _default_store() -> PositionStore:
    return PositionStore()


@lru_cache(maxsize=1)
def _default_valuator() -> PositionValuator:
    cache = PriceBarCache()
    tw_service = MarketDataService(
        primary=TwseAdapter(),
        backups=[TpexAdapter(), FinMindAdapter()],
        cache=cache,
    )
    # US has no price adapter yet, so it is intentionally absent: those
    # positions surface as ``insufficient_data`` (missing "price") rather than
    # being valued with a fabricated number.
    market_services: dict[Market, PriceService] = {"TW": tw_service}
    return PositionValuator(
        market_services=market_services,
        fx_provider=BankOfTaiwanFxAdapter(),
    )


def get_position_store() -> PositionStore:
    """Return the process-wide position store."""
    return _default_store()


def get_valuator() -> PositionValuator:
    """Return the process-wide position valuator."""
    return _default_valuator()
