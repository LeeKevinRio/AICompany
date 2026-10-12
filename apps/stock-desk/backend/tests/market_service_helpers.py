"""One way for tests to build a ``MarketDataService`` (F-9b0, ADR-0024 TA5 R-68).

The service takes its currency lookup and its ``scope`` as required
keyword-only arguments with no default. Tests build it through
:func:`equity_service` or :func:`index_service`, which pass both explicitly --
the same lookup over ``MARKET_CURRENCY`` the assembly layer uses -- so a test
names the path it stands for and the production class keeps no default.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from app.data.cache import PriceBarCache
from app.data.interface import Market, MarketDataProvider
from app.data.service import CurrencyLookup, MarketDataService, ServiceScope
from app.positions.models import MARKET_CURRENCY


def market_currency(market: Market) -> str | None:
    """The lookup ``app.api.deps`` injects, restated for tests."""
    return MARKET_CURRENCY.get(market)


def build_service(
    *,
    primary: MarketDataProvider,
    cache: PriceBarCache,
    scope: ServiceScope,
    currency_for_market: CurrencyLookup = market_currency,
    backups: Sequence[MarketDataProvider] = (),
    clock: Callable[[], datetime] | None = None,
    cache_first: bool = False,
) -> MarketDataService:
    """A service with every gate argument passed explicitly; ``clock`` only when given."""
    if clock is None:
        return MarketDataService(
            primary=primary,
            backups=backups,
            cache=cache,
            cache_first=cache_first,
            currency_for_market=currency_for_market,
            scope=scope,
        )
    return MarketDataService(
        primary=primary,
        backups=backups,
        cache=cache,
        clock=clock,
        cache_first=cache_first,
        currency_for_market=currency_for_market,
        scope=scope,
    )


def equity_service(
    *,
    primary: MarketDataProvider,
    cache: PriceBarCache,
    backups: Sequence[MarketDataProvider] = (),
    clock: Callable[[], datetime] | None = None,
    cache_first: bool = False,
) -> MarketDataService:
    """A TW / US ladder as ``deps._default_resolver`` builds it: ``scope="equity"``."""
    return build_service(
        primary=primary,
        cache=cache,
        scope="equity",
        currency_for_market=market_currency,
        backups=backups,
        clock=clock,
        cache_first=cache_first,
    )


def index_service(
    *,
    primary: MarketDataProvider,
    cache: PriceBarCache,
    backups: Sequence[MarketDataProvider] = (),
    clock: Callable[[], datetime] | None = None,
    cache_first: bool = False,
) -> MarketDataService:
    """The index ladder as ``deps._default_index_resolver`` builds it: ``scope="index"``."""
    return build_service(
        primary=primary,
        cache=cache,
        scope="index",
        currency_for_market=market_currency,
        backups=backups,
        clock=clock,
        cache_first=cache_first,
    )
