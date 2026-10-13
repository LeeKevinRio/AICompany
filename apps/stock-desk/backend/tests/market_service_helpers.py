"""One way for tests to build a ``MarketDataService`` (F-9b0, ADR-0024 TA5 R-68).

The service takes its currency lookup, its ``scope``, its symbol admission and
its wording as required keyword-only arguments with no default. Tests build it
through :func:`equity_service` or :func:`index_service`, which pass all four
explicitly -- the same values the assembly layer passes -- so a test names the
path it stands for and the production class keeps no default.

:func:`build_service` takes the admission as an argument too (default: the
one ``deps`` gives that scope), for a test whose fixture symbol is not one the
equity admission would ask about (TA1 M-12: say so explicitly with
:func:`app.data.admission.admit_any_shape`, never by loosening production).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from app.data.admission import SymbolAdmission, admit_any_shape, admit_equity_daily_bars
from app.data.cache import PriceBarCache
from app.data.gate_wording import EQUITY_GATE_WORDING, GateWording
from app.data.interface import Market, MarketDataProvider
from app.data.service import CurrencyLookup, MarketDataService, ServiceScope
from app.positions.models import MARKET_CURRENCY


def market_currency(market: Market) -> str | None:
    """The lookup ``app.api.deps`` injects, restated for tests."""
    return MARKET_CURRENCY.get(market)


def scope_admission(scope: ServiceScope) -> SymbolAdmission:
    """The admission ``deps`` builds a ``scope`` with (D-4: the index checks no shape)."""
    return admit_equity_daily_bars if scope == "equity" else admit_any_shape


def scope_wording(scope: ServiceScope) -> GateWording | None:
    """The wording ``deps`` builds a ``scope`` with (D-4, F9W-9: the index has none)."""
    return EQUITY_GATE_WORDING if scope == "equity" else None


def build_service(
    *,
    primary: MarketDataProvider,
    cache: PriceBarCache,
    scope: ServiceScope,
    currency_for_market: CurrencyLookup = market_currency,
    backups: Sequence[MarketDataProvider] = (),
    clock: Callable[[], datetime] | None = None,
    cache_first: bool = False,
    admission: SymbolAdmission | None = None,
) -> MarketDataService:
    """A service with every gate argument passed explicitly; ``clock`` only when given."""
    gate_admission = scope_admission(scope) if admission is None else admission
    if clock is None:
        return MarketDataService(
            primary=primary,
            backups=backups,
            cache=cache,
            cache_first=cache_first,
            currency_for_market=currency_for_market,
            scope=scope,
            admission=gate_admission,
            wording=scope_wording(scope),
        )
    return MarketDataService(
        primary=primary,
        backups=backups,
        cache=cache,
        clock=clock,
        cache_first=cache_first,
        currency_for_market=currency_for_market,
        scope=scope,
        admission=gate_admission,
        wording=scope_wording(scope),
    )


def equity_service(
    *,
    primary: MarketDataProvider,
    cache: PriceBarCache,
    backups: Sequence[MarketDataProvider] = (),
    clock: Callable[[], datetime] | None = None,
    cache_first: bool = False,
    admission: SymbolAdmission | None = None,
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
        admission=admission,
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
