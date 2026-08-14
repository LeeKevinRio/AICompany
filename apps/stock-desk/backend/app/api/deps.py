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
from app.data.providers.alpha_vantage import AlphaVantageAdapter
from app.data.providers.finmind import FinMindAdapter
from app.data.providers.fx import BankOfTaiwanFxAdapter, FxRateProvider
from app.data.providers.tpex import TpexAdapter
from app.data.providers.twse import TwseAdapter
from app.data.providers.yfinance import YFinanceAdapter
from app.data.quota import QuotaLedger
from app.data.service import MarketDataService
from app.directory.store import SecurityDirectoryStore
from app.dividends.store import DividendEventStore
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from app.portfolio.valuation import PositionValuator
from app.positions.store import PositionStore
from app.services.index import (
    IndexProviderBridge,
    IndexSeriesService,
    IndexServiceResolver,
)
from app.services.market import MarketDataResolver
from app.settings.store import SettingsStore


@lru_cache(maxsize=1)
def _default_store() -> PositionStore:
    return PositionStore()


@lru_cache(maxsize=1)
def _default_cache() -> PriceBarCache:
    """One cache object for every ladder in this process.

    They all address the same SQLite file anyway, and index series live in the
    ``^``-prefixed key space no equity ticker can occupy (ADR-0005 constraint
    I-7), so sharing costs nothing and keeps a single TTL policy.
    """
    return PriceBarCache()


@lru_cache(maxsize=1)
def _default_yfinance() -> YFinanceAdapter:
    """The one yfinance adapter, in both of its roles.

    It is the US backup *and* the only index source (ADR-0005 決策一). One
    instance means one ``RateLimitedClient``, so the client-side throttle
    applies across both roles instead of each keeping its own budget against
    the same host.
    """
    return YFinanceAdapter()


@lru_cache(maxsize=1)
def _default_resolver() -> MarketDataResolver:
    """market -> price service, one degradation ladder per market.

    TW: TWSE 主 + TPEx/FinMind 備援, ``cache_first`` **off**. Taiwan has no
    comparable quota pressure and ADR-0005 constraint D-1 pins its behaviour
    exactly as it was.

    US: Alpha Vantage 主 + yfinance 備援, ``cache_first`` **on** -- the full
    five-layer chain of ADR-0005 決策四 (TTL 內快取 -> AV -> yfinance -> 任何
    快取 -> unavailable). Layer 0 is what stops a page reload from burning the
    day's Alpha Vantage budget on a symbol fetched an hour ago.

    Fail-closed is deliberate: with no ``ALPHA_VANTAGE_API_KEY`` the primary
    declines without issuing a request, and if the backup cannot be reached
    either, the ladder ends at ``unavailable`` carrying both reasons -- never
    at a fabricated price. A market absent from this map has no adapter at all
    and surfaces as ``insufficient_data`` (see ``app/services/market.py``).
    """
    cache = _default_cache()
    tw_service = MarketDataService(
        primary=TwseAdapter(),
        backups=[TpexAdapter(), FinMindAdapter()],
        cache=cache,
    )
    us_service = MarketDataService(
        primary=AlphaVantageAdapter(),
        backups=[_default_yfinance()],
        cache=cache,
        cache_first=True,
    )
    return {"TW": tw_service, "US": us_service}


@lru_cache(maxsize=1)
def _default_index_resolver() -> IndexServiceResolver:
    """index series market -> the service that can quote it.

    The index path is assembled here and nowhere else: the yfinance adapter's
    index method is bridged onto the provider contract
    (:class:`IndexProviderBridge`), given the same cache and layer 0 as the US
    ladder, and then presented through :class:`IndexSeriesService` so the
    series can never be labelled ``fresh`` (ADR-0005 constraint I-3).

    Alpha Vantage is absent by design -- it never participates in the index
    path, so no index lookup can eat into the quota reserved for the symbols a
    user actually holds. Both markets share one service; the market is only a
    cache-key dimension, and which one an index belongs to is the adapter's
    fact to state.
    """
    service = MarketDataService(
        primary=IndexProviderBridge(_default_yfinance()),
        cache=_default_cache(),
        cache_first=True,
    )
    disclosed = IndexSeriesService(service)
    return {"TW": disclosed, "US": disclosed}


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


@lru_cache(maxsize=1)
def _default_directory_store() -> SecurityDirectoryStore:
    """The process-wide security directory store.

    Shares the same ``STOCK_DESK_DB_PATH`` SQLite file as every other store
    (see ``app/directory/store.py``); it is empty until the CEO runs
    ``python -m app.directory.sync`` at least once, which the API surfaces
    honestly via ``directory_synced`` rather than erroring.
    """
    return SecurityDirectoryStore()


@lru_cache(maxsize=1)
def _default_dividend_store() -> DividendEventStore:
    """The process-wide 除權息 event store.

    Shares the same ``STOCK_DESK_DB_PATH`` SQLite file as every other store; it
    is empty until the CEO runs ``python -m app.dividends.sync`` at least once,
    which the backtest endpoint surfaces honestly as "未還原除權息" rather than
    pretending the symbol never paid a dividend.
    """
    return DividendEventStore()


@lru_cache(maxsize=1)
def _default_quota_ledger() -> QuotaLedger:
    """The ledger the API reads for observability only.

    A separate object from the one inside :class:`AlphaVantageAdapter`, but the
    same database file (both resolve ``STOCK_DESK_DB_PATH``): the ledger keeps
    no in-process state, so two handles observe one counter -- which is the
    whole point of ADR-0005 決策三 方案 C.
    """
    return QuotaLedger()


@lru_cache(maxsize=1)
def _default_playbook_store() -> PlaybookStore:
    """The process-wide playbook store (batches, schedule, rule versions).

    Same ``STOCK_DESK_DB_PATH`` file as every other store; empty until batches
    are seeded, which the endpoint reports as "no directives" rather than
    inventing a portfolio.
    """
    return PlaybookStore()


@lru_cache(maxsize=1)
def _default_playbook_service() -> PlaybookService:
    """The playbook service, reading through the existing TW ladder and ^TWII."""
    return PlaybookService(
        store=_default_playbook_store(),
        market_resolver=_default_resolver(),
        index_resolver=_default_index_resolver(),
    )


def get_position_store() -> PositionStore:
    """Return the process-wide position store."""
    return _default_store()


def get_playbook_store() -> PlaybookStore:
    """Return the process-wide playbook store."""
    return _default_playbook_store()


def get_playbook_service() -> PlaybookService:
    """Return the process-wide playbook service."""
    return _default_playbook_service()


def get_valuator() -> PositionValuator:
    """Return the process-wide position valuator."""
    return _default_valuator()


def get_fx_provider() -> FxRateProvider:
    """Return the process-wide FX rate provider."""
    return _default_fx_provider()


def get_market_resolver() -> MarketDataResolver:
    """Return the process-wide market -> price service map."""
    return _default_resolver()


def get_price_bar_cache() -> PriceBarCache:
    """Return the process-wide bar cache, read as a trading calendar (C4).

    The same object every ladder writes through, so the calendar it answers
    with is every session the process has actually observed -- across symbols,
    including the index series -- rather than a second store to keep in sync.
    """
    return _default_cache()


def get_index_resolver() -> IndexServiceResolver:
    """Return the process-wide market -> index series service map."""
    return _default_index_resolver()


def get_settings_store() -> SettingsStore:
    """Return the process-wide settings store."""
    return _default_settings_store()


def get_alert_store() -> AlertStore:
    """Return the process-wide alert store."""
    return _default_alert_store()


def get_quota_ledger() -> QuotaLedger:
    """Return the process-wide provider quota ledger."""
    return _default_quota_ledger()


def get_directory_store() -> SecurityDirectoryStore:
    """Return the process-wide security directory store."""
    return _default_directory_store()


def get_dividend_store() -> DividendEventStore:
    """Return the process-wide 除權息 event store."""
    return _default_dividend_store()
