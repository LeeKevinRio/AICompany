"""FastAPI dependency providers for every router.

Production wiring is built lazily and memoized (``functools.lru_cache``) so the
underlying HTTP clients and SQLite handles are created once per process, and
only when a route actually needs them. Tests override these via
``app.dependency_overrides`` and therefore never construct the real adapters
or touch the network.
"""

from __future__ import annotations

from functools import lru_cache

from app.alerts.store import AlertStore
from app.data.cache import PriceBarCache
from app.data.providers.finmind import FinMindAdapter
from app.data.providers.fx import BankOfTaiwanFxAdapter, FxRateProvider
from app.data.providers.tpex import TpexAdapter
from app.data.providers.twse import TwseAdapter
from app.data.service import MarketDataService
from app.portfolio.valuation import PositionValuator
from app.positions.store import PositionStore
from app.services.market import MarketDataResolver
from app.settings.store import SettingsStore


@lru_cache(maxsize=1)
def _default_store() -> PositionStore:
    return PositionStore()


@lru_cache(maxsize=1)
def _default_resolver() -> MarketDataResolver:
    """market -> price service. US is intentionally absent: no adapter exists yet.

    A market with no entry surfaces as ``insufficient_data`` with the reason
    stated (see ``app/services/market.py``) rather than being served a
    fabricated price.
    """
    cache = PriceBarCache()
    tw_service = MarketDataService(
        primary=TwseAdapter(),
        backups=[TpexAdapter(), FinMindAdapter()],
        cache=cache,
    )
    return {"TW": tw_service}


@lru_cache(maxsize=1)
def _default_fx_provider() -> FxRateProvider:
    """The one FX adapter, shared by the valuation and the risk-context path.

    Both paths must read the same rates: a card whose caps were scaled by one
    quote while the portfolio total used another would be internally
    inconsistent for no visible reason.
    """
    return BankOfTaiwanFxAdapter()


@lru_cache(maxsize=1)
def _default_valuator() -> PositionValuator:
    return PositionValuator(
        market_services=dict(_default_resolver()),
        fx_provider=_default_fx_provider(),
    )


@lru_cache(maxsize=1)
def _default_settings_store() -> SettingsStore:
    return SettingsStore()


@lru_cache(maxsize=1)
def _default_alert_store() -> AlertStore:
    return AlertStore()


def get_position_store() -> PositionStore:
    """Return the process-wide position store."""
    return _default_store()


def get_valuator() -> PositionValuator:
    """Return the process-wide position valuator."""
    return _default_valuator()


def get_fx_provider() -> FxRateProvider:
    """Return the process-wide FX rate provider."""
    return _default_fx_provider()


def get_market_resolver() -> MarketDataResolver:
    """Return the process-wide market -> price service map."""
    return _default_resolver()


def get_settings_store() -> SettingsStore:
    """Return the process-wide settings store."""
    return _default_settings_store()


def get_alert_store() -> AlertStore:
    """Return the process-wide alert store."""
    return _default_alert_store()
