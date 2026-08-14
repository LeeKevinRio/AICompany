"""One market-aware bar loader for every consumer of price data.

``MarketDataService`` is per-market -- each market has its own provider chain,
and a market nobody has wired up has none -- so callers need a map from market
to service plus a single, consistent answer for "there is no adapter for this
market". :func:`load_bars` is that answer: it
returns a :class:`LoadedBars` whose ``reason`` is a Traditional Chinese sentence
the API can show verbatim, and never raises for an expected failure.

The distinction the whole product rests on is preserved here: **no bars is a
state, not an error**. A market with no adapter, a provider chain that came back
empty, and a cache miss are three different reasons, all reported as
``insufficient_data`` with the reason attached, never as a 500 and never as a
fabricated series.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.data.calendar import TradingCalendar
from app.data.interface import DataStatus, PriceBar
from app.portfolio.valuation import PriceService
from app.positions.models import Market

#: market -> the service that can quote it. A market absent from the map has no
#: adapter at all, and says so rather than being served a substitute.
MarketDataResolver = Mapping[Market, PriceService]


class TradingCalendarSource(Protocol):
    """Whoever can say which dates a market was observed to trade on.

    Structural on purpose: the only implementation today is
    ``app.data.cache.PriceBarCache``, but this layer needs one method out of it
    and must not grow a dependency on SQLite to ask a calendar question.
    """

    def market_trading_days(self, market: Market, start: date, end: date) -> frozenset[date]: ...


NO_ADAPTER_REASON = "目前沒有 {market} 市場的行情來源，無法取得日線資料。"
NO_BARS_REASON = "{market} {symbol} 在指定區間內沒有可用的日線資料（主來源、備援與快取皆無）。"
#: Prefix for the data layer's own sentence when it is appended to one of the
#: reasons above.
PROVIDER_REASON_PREFIX = "來源回報："


def with_provider_reason(base: str, provider_reason: str | None) -> str:
    """Append the data layer's own ``reason`` to this layer's sentence.

    The two answer different questions and neither replaces the other: the base
    sentence says *what* is missing in terms the endpoint's reader understands,
    while ``ProviderResult.reason`` says *why this time* -- quota spent, API key
    not configured, source unreachable, upstream that cannot tell "no such
    ticker" from "no data today" apart. Dropping the second one (which is what
    happened before this was wired) turns every distinct failure into the same
    opaque sentence.
    """
    if not provider_reason:
        return base
    return f"{base}{PROVIDER_REASON_PREFIX}{provider_reason}"


@dataclass(frozen=True)
class LoadedBars:
    """Bars plus the provenance every downstream response has to carry."""

    bars: list[PriceBar] = field(default_factory=list)
    status: DataStatus = DataStatus.UNAVAILABLE
    source: str = "none"
    staleness_minutes: int | None = None
    reason: str | None = None
    #: Only meaningful for ``cached_stale``: whether the cached data is still
    #: inside its TTL (ADR-0005 決策四 / constraint D-2). ``None`` for every
    #: live rung, where "within TTL" is not a question that applies.
    is_within_ttl: bool | None = None
    #: How many observed market sessions happened after ``last_bar_date``
    #: (C4). ``None`` means "no trading calendar was available to ask", which
    #: is not the same as ``0`` ("asked, and the market has had no session
    #: since"). See :func:`trading_days_behind_market`.
    trading_days_behind: int | None = None

    def meta(self) -> dict[str, object]:
        """The ``data`` block echoed on every endpoint that loads bars."""
        first = min((bar.date for bar in self.bars), default=None)
        last = max((bar.date for bar in self.bars), default=None)
        return {
            "status": self.status.value,
            "source": self.source,
            "staleness_minutes": self.staleness_minutes,
            "is_within_ttl": self.is_within_ttl,
            "bar_count": len(self.bars),
            "first_bar_date": first.isoformat() if first is not None else None,
            "last_bar_date": last.isoformat() if last is not None else None,
            "trading_days_behind": self.trading_days_behind,
            "reason": self.reason,
        }


def trading_days_behind_market(
    source: TradingCalendarSource | None,
    *,
    market: Market,
    last_bar_date: date | None,
    today: date,
) -> int | None:
    """Observed sessions the market has had since ``last_bar_date`` (C4).

    This replaces the front end's "more than 10 calendar days" stand-in, which
    was a buffer wide enough to swallow 農曆年 because no real calendar was
    available to it (``frontend/app/lib/tradingCalendar.ts``, B1 of
    ``work/reviews/risk-fix-review.md``; the threshold was flagged as an
    unsourced estimate). The measure here is the one the risk review asked for
    in the first place -- **trading** days, threshold back down to 1 -- and it
    is honest about not knowing:

    * ``None`` -- nobody could be asked (no calendar source, no bars, or a
      calendar that has observed nothing in the window). The caller must treat
      this as "cannot judge", never as "fresh" and never as "old".
    * ``0`` -- the market has had no session since ``last_bar_date``. This is
      also the answer during a closure the calendar never had to model: a
      typhoon day, 農曆年, an ad-hoc suspension. No bars exist for those days,
      so no session is counted and no false "資料過舊" alarm fires. That is the
      deliberate direction of the trade-off: under-report staleness rather than
      invent it (the R4/B1 regression was the opposite direction).
    * ``n >= 1`` -- the market traded ``n`` sessions this series does not have.

    The blind spot this leaves, stated rather than hidden: when the *whole*
    data layer is stale, the market calendar stops advancing too, so the gap
    reads 0. That case is not silent -- it is what ``status`` /
    ``staleness_minutes`` / ``is_within_ttl`` report, and what the front end's
    ``DataMetaStatusBadge`` renders (the split of duties R4 established).
    """
    if source is None or last_bar_date is None:
        return None
    observed = source.market_trading_days(market, last_bar_date, today)
    if not observed:
        return None
    return TradingCalendar(observed).observed_days_after(last_bar_date)


def load_bars(
    resolver: MarketDataResolver,
    *,
    symbol: str,
    market: Market,
    start: date,
    end: date,
    calendar_source: TradingCalendarSource | None = None,
) -> LoadedBars:
    """Load daily bars for ``symbol``, degrading to an explained empty result.

    ``calendar_source`` is optional and defaults to "no calendar": an endpoint
    that does not publish a data-age judgement has nothing to gain from the
    extra lookup, and every caller that omits it gets ``trading_days_behind``
    as ``None`` -- unknown, which is what it is.
    """
    service = resolver.get(market)
    if service is None:
        return LoadedBars(reason=NO_ADAPTER_REASON.format(market=market))
    result = service.get_daily_bars(symbol, market, start, end)
    if result.status is DataStatus.UNAVAILABLE or not result.bars:
        return LoadedBars(
            status=result.status,
            source=result.source,
            staleness_minutes=result.staleness_minutes,
            is_within_ttl=result.is_within_ttl,
            reason=with_provider_reason(
                NO_BARS_REASON.format(market=market, symbol=symbol), result.reason
            ),
        )
    bars = list(result.bars)
    return LoadedBars(
        bars=bars,
        status=result.status,
        source=result.source,
        staleness_minutes=result.staleness_minutes,
        is_within_ttl=result.is_within_ttl,
        trading_days_behind=trading_days_behind_market(
            calendar_source,
            market=market,
            last_bar_date=max(bar.date for bar in bars),
            today=end,
        ),
    )
