"""Mark-to-market valuation of a position and P&L attribution.

Notation (all quantities in the instrument's own currency unless noted):

    q   -- quantity held
    P0  -- cost basis per unit == the position's ``avg_cost`` (never fetched;
           the user tells us their average cost)
    P1  -- latest market price per unit (fetched: the most recent daily close)
    F0  -- FX rate on the open date (original -> TWD); 1 for TWD positions
    F1  -- latest FX rate (original -> TWD); 1 for TWD positions

Total unrealized P&L in TWD and its attribution:

    total_twd = q * (P1 * F1 - P0 * F0)
    asset_contribution_twd = q * (P1 - P0) * F1
    fx_contribution_twd    = q * P0 * (F1 - F0)

Why this split (asset-first, "current FX on the price move"): the asset term
prices the *price* change at today's FX, and the FX term prices the *original*
cost basis at the FX change. Algebraically they sum to ``total`` exactly --

    q*(P1-P0)*F1 + q*P0*(F1-F0)
      = q*(P1*F1 - P0*F1 + P0*F1 - P0*F0)
      = q*(P1*F1 - P0*F0)

-- so ``asset_contribution + fx_contribution == total`` is an identity, not an
approximation, and is asserted by the golden tests. (The mirror convention --
FX on the price move and asset at original FX -- would also sum to total; we
fix this one so the attribution is deterministic and testable.)

Any missing input (no price adapter for the market, no cached/live price, a
latest close that is unusable, no open date to price F0 at, no FX rate on or
before the open date within the lookback window) yields
``status = insufficient_data`` with the affected outputs left null. Nothing is
ever interpolated or fabricated.

An unusable latest close -- zero, negative or not finite, as judged by the one
definition in :func:`app.data.price_guard.usable_price` -- is treated exactly
like having no bar at all: no ``PriceInfo``, no change basis, and the same
missing token. The earlier bars in the window are **not** fallen back on; the
bar is dropped and a warning is logged so the bad row can be traced. No new
token is introduced for this case, which means the live-mode token ``price``
also covers "a price was found, but its latest close is unusable", not only
"no price was found" (risk-compliance R-1); the cache-only token
``price_not_queried`` keeps its meaning, since a cache-only read never asked a
source either way.

A position whose ``currency`` is not the one its ``market`` is quoted in (a
legacy row stored before ADR-0017's write rule) is valued exactly as before,
but each pass logs one warning per such row, naming only its id, market and
currency (task X-3b, KX-6/KX-7). The judgement is
:func:`app.positions.models.currency_matches_market` itself; this module keeps
no copy of the market -> currency table.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.data.price_guard import usable_price
from app.data.providers.fx import FxRateProvider
from app.positions.models import Currency, Position, currency_matches_market
from app.services.fx_notes import source_note

logger = logging.getLogger(__name__)

#: How far back to look for the latest daily close (skips weekends/holidays).
PRICE_LOOKBACK_DAYS = 10
#: How far back to accept an FX rate on/before a target date (per the spec).
FX_BACKTRACK_DAYS = 7

_TWD_RATE = Decimal(1)

#: One ``value_all`` pass's FX answers, keyed by ``(pair, target)`` (ADR-0010 D-2).
FxMemo = dict[tuple[str, date], tuple["Decimal | None", "FxInfo"]]


class PriceService(Protocol):
    """The slice of ``MarketDataService`` the valuator depends on.

    Declared as a Protocol so the valuator is decoupled from the concrete
    service (and trivially fakeable in tests without a cache or network).
    """

    def get_daily_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult: ...

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        """The same range from the local cache only -- never a live call (ADR-0010 D-1)."""
        ...


#: How a valuator obtains prices (ADR-0010 D-1). ``live`` runs the full
#: degradation ladder per position; ``cache_only`` reads what the cache already
#: holds and never asks a source. An explicit constructor argument, never an
#: environment switch: two machines running the same code must produce the same
#: data-layer answer for the same request (tech-architect R-8).
PriceMode = Literal["live", "cache_only"]

#: ``Valuation.missing`` token for a cache-only read that found no rows: the
#: source was not asked this time, which is a different fact from "the source
#: had nothing" (tech-architect R-5).
PRICE_NOT_QUERIED = "price_not_queried"

#: What kind of price ``PriceInfo.value`` is (ADR-0014 D-5). Only
#: ``daily_close`` is ever produced until the intraday quote path lands (W15);
#: the field ships ahead of it so the front end reads the kind instead of
#: inferring it (ADR-0016 K-8).
PriceKind = Literal["daily_close", "intraday_quote"]

#: Which price bases a summary's change column may carry (ADR-0016 D-8). Fixed
#: by how the valuator was constructed, never by the data in one response and
#: never by an environment switch.
ChangeMode = Literal["close_only", "may_include_intraday"]


@dataclass(frozen=True)
class Decomposition:
    """The three-way split of a position's TWD P&L."""

    total_twd: Decimal
    asset_contribution_twd: Decimal
    fx_contribution_twd: Decimal


def decompose(
    *,
    quantity: Decimal,
    price_open: Decimal,
    price_now: Decimal,
    fx_open: Decimal,
    fx_now: Decimal,
) -> Decomposition:
    """Split unrealized TWD P&L into asset and FX contributions.

    ``asset + fx == total`` holds exactly (see module docstring for the proof).
    """
    total = quantity * (price_now * fx_now - price_open * fx_open)
    asset = quantity * (price_now - price_open) * fx_now
    fx = quantity * price_open * (fx_now - fx_open)
    return Decomposition(
        total_twd=total,
        asset_contribution_twd=asset,
        fx_contribution_twd=fx,
    )


class PriceInfo(BaseModel):
    """The market price used for a valuation, with provenance and freshness."""

    model_config = ConfigDict(frozen=True)

    value: Decimal
    as_of: str
    source: str
    data_status: DataStatus
    #: Passed through verbatim from the data layer's ``ProviderResult``.
    #: For ``CACHED_STALE`` it says whether the local cache already holds the
    #: latest completed session (``True``) or is known to be short of one
    #: (``False``); ``None`` for live sources, where the question does not apply.
    is_within_ttl: bool | None = None
    #: The data layer's user-facing degradation reason, ``None`` on success.
    reason: str | None = None
    #: ``daily_close`` for every price this valuator produces today
    #: (ADR-0014 D-5, shipped ahead by ADR-0016 K-8).
    price_kind: PriceKind = "daily_close"


class FxInfo(BaseModel):
    """The FX rate used for ``fx_now``, with provenance and freshness (ADR-0011).

    Present for every non-TWD position whether or not a rate was found, so the
    summary can disclose a backup-sourced rate (``data_status == BACKUP``)
    exactly where the converted figures are shown, and can say "no rate" when
    ``data_status == UNAVAILABLE``. ``source_note`` is the source's standing
    disclosure (``app/services/fx.py``), fixed verbatim by risk-compliance.
    """

    model_config = ConfigDict(frozen=True)

    pair: str
    as_of: str | None
    source: str
    data_status: DataStatus
    source_note: str
    #: Mirrors ``PriceInfo.is_within_ttl`` so both badges read one contract.
    #: The FX data layer (``FxRateResult``, ADR-0011) has no cache rung and no
    #: TTL concept: it only ever answers ``FRESH`` / ``BACKUP`` (a live fetch)
    #: or ``UNAVAILABLE``, never ``CACHED_STALE``. ``PriceInfo``'s rule for a
    #: live source is ``None`` ("the question does not apply"), so this is
    #: always ``None`` until the FX data layer itself grows a cache rung.
    is_within_ttl: bool | None = None
    #: The FX data layer's user-facing degradation reason
    #: (``FxRateResult.reason``), passed through verbatim; ``None`` on success.
    reason: str | None = None


class PnlOriginal(BaseModel):
    """Unrealized P&L in the instrument's own currency."""

    model_config = ConfigDict(frozen=True)

    value: Decimal
    currency: Currency


class Valuation(BaseModel):
    """The public ``valuation`` sub-object for one position in the summary."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "insufficient_data"]
    missing: list[str]
    price: PriceInfo | None
    #: ``None`` for a TWD position (no conversion, nothing to disclose).
    fx: FxInfo | None = None
    pnl_original: PnlOriginal | None
    pnl_twd: Decimal | None
    asset_contribution_twd: Decimal | None
    fx_contribution_twd: Decimal | None


@dataclass(frozen=True)
class ChangeBasis:
    """The two bars a day-over-day change would be read from (ADR-0016 D-2).

    Both come out of the **same** ``ProviderResult`` that priced the position,
    so the change's numerator is by construction the price on screen and no
    second series is ever consulted. ``latest`` is the bar behind
    ``PriceInfo.value``; ``previous`` is the newest bar strictly before it, or
    ``None`` when the lookback window held only one. Whether a change may be
    shown from them is :mod:`app.portfolio.price_change`'s call, not this one's.
    """

    latest: PriceBar
    previous: PriceBar | None


@dataclass(frozen=True)
class PositionValuation:
    """A valuation plus the TWD cost/market-value used to aggregate totals.

    ``cost_twd`` and ``market_value_twd`` are only populated when the valuation
    is ``ok`` (i.e. every input was available); they are the per-position
    contributions to ``totals`` and are ``None`` otherwise so callers never sum
    fabricated numbers.

    ``change_basis`` is internal (never serialized): ``None`` whenever no price
    was resolved.
    """

    valuation: Valuation
    cost_twd: Decimal | None
    market_value_twd: Decimal | None
    change_basis: ChangeBasis | None = None


class PositionValuator:
    """Values a ``Position`` using a price service and an FX provider.

    ``market_services`` maps a market to the price service that can quote it.
    A market with no entry (e.g. US, which has no adapter yet) yields a missing
    price rather than a fabricated one.
    """

    def __init__(
        self,
        *,
        market_services: Mapping[Market, PriceService],
        fx_provider: FxRateProvider,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        price_mode: PriceMode = "live",
    ) -> None:
        self._market_services = dict(market_services)
        self._fx_provider = fx_provider
        self._clock = clock
        self._price_mode: PriceMode = price_mode

    @property
    def price_mode(self) -> PriceMode:
        return self._price_mode

    @property
    def change_mode(self) -> ChangeMode:
        """Which change bases this valuator's summaries may carry (ADR-0016 D-8).

        Derived from construction alone. No constructor argument can introduce
        an intraday price yet (ADR-0014 D-4 is not wired), so this is always
        ``close_only``; the intraday branch arrives with that parameter.
        """
        return "close_only"

    def value_all(self, positions: Sequence[Position]) -> list[PositionValuation]:
        """Value every position of one book in one pass.

        FX lookups for the same ``(pair, date)`` are answered once per pass
        (ADR-0010 D-2): within a single request the answer cannot differ, and
        without this a book of N foreign holdings asks the FX source N times
        for the same day's rate.
        """
        fx_memo: FxMemo = {}
        return [self.value_position(position, fx_memo=fx_memo) for position in positions]

    def value_position(
        self,
        position: Position,
        *,
        fx_memo: FxMemo | None = None,
    ) -> PositionValuation:
        today = self._clock().date()
        missing: list[str] = []

        if not currency_matches_market(position.market, position.currency):
            # Observability only (X-3b): the figures below are unchanged. The
            # message carries no quantity, cost or note -- id, market and
            # currency are enough to find the row and correct it.
            logger.warning(
                "position currency does not match market: id=%s market=%s currency=%s",
                position.id,
                position.market,
                position.currency,
            )

        price_info, price_now, price_missing, change_basis = self._resolve_price(position, today)
        if price_now is None:
            missing.append(price_missing)

        fx_open, fx_now, fx_info = self._resolve_fx(position, today, missing, fx_memo)

        price_open = position.avg_cost
        quantity = position.quantity

        pnl_original: PnlOriginal | None = None
        if price_now is not None:
            # Original-currency P&L needs only the price; report it even when
            # an FX rate is missing so the user still sees something truthful.
            pnl_original = PnlOriginal(
                value=quantity * (price_now - price_open),
                currency=position.currency,
            )

        if missing or price_now is None or fx_open is None or fx_now is None:
            return PositionValuation(
                valuation=Valuation(
                    status="insufficient_data",
                    missing=missing,
                    price=price_info,
                    fx=fx_info,
                    pnl_original=pnl_original,
                    pnl_twd=None,
                    asset_contribution_twd=None,
                    fx_contribution_twd=None,
                ),
                cost_twd=None,
                market_value_twd=None,
                change_basis=change_basis,
            )

        parts = decompose(
            quantity=quantity,
            price_open=price_open,
            price_now=price_now,
            fx_open=fx_open,
            fx_now=fx_now,
        )
        return PositionValuation(
            valuation=Valuation(
                status="ok",
                missing=[],
                price=price_info,
                fx=fx_info,
                pnl_original=pnl_original,
                pnl_twd=parts.total_twd,
                asset_contribution_twd=parts.asset_contribution_twd,
                fx_contribution_twd=parts.fx_contribution_twd,
            ),
            cost_twd=quantity * price_open * fx_open,
            market_value_twd=quantity * price_now * fx_now,
            change_basis=change_basis,
        )

    def _resolve_price(
        self, position: Position, today: date
    ) -> tuple[PriceInfo | None, Decimal | None, str, ChangeBasis | None]:
        """``(info, close, missing_token, change_basis)``.

        The token names *why* when close is None. ``change_basis`` is read from
        the same ``result.bars`` as the close (ADR-0016 D-2): no extra service
        call, no wider lookback.

        A latest bar whose close is unusable returns exactly what "no bar"
        returns; an earlier bar is never substituted for it (see the module
        docstring).
        """
        missing_token = PRICE_NOT_QUERIED if self._price_mode == "cache_only" else "price"
        service = self._market_services.get(position.market)
        if service is None:
            return None, None, missing_token, None
        start = today - timedelta(days=PRICE_LOOKBACK_DAYS)
        if self._price_mode == "cache_only":
            result = service.get_cached_bars(position.symbol, position.market, start, today)
        else:
            result = service.get_daily_bars(position.symbol, position.market, start, today)
        if result.status is DataStatus.UNAVAILABLE or not result.bars:
            return None, None, missing_token, None
        latest = max(result.bars, key=lambda bar: bar.date)
        if not usable_price(latest.close):
            logger.warning(
                "unusable latest close dropped from valuation: symbol=%s market=%s "
                "date=%s close=%s source=%s",
                position.symbol,
                position.market,
                latest.date.isoformat(),
                latest.close,
                result.source,
            )
            return None, None, missing_token, None
        earlier = [bar for bar in result.bars if bar.date < latest.date]
        previous = max(earlier, key=lambda bar: bar.date) if earlier else None
        info = PriceInfo(
            value=latest.close,
            as_of=latest.date.isoformat(),
            source=result.source,
            data_status=result.status,
            is_within_ttl=result.is_within_ttl,
            reason=result.reason,
        )
        return info, latest.close, "", ChangeBasis(latest=latest, previous=previous)

    def _resolve_fx(
        self,
        position: Position,
        today: date,
        missing: list[str],
        fx_memo: FxMemo | None,
    ) -> tuple[Decimal | None, Decimal | None, FxInfo | None]:
        if position.currency == "TWD":
            # A TWD position is already in the reporting currency: F0 = F1 = 1
            # and the FX contribution is therefore identically zero.
            return _TWD_RATE, _TWD_RATE, None
        pair = f"{position.currency}TWD"
        fx_now, fx_info = self._latest_fx_on_or_before(pair, today, fx_memo)
        if fx_now is None:
            missing.append("fx_now")
        # Without an open date there is no date to price F0 at, and no rate is
        # substituted for it: the position reports insufficient_data instead.
        fx_open = (
            None
            if position.opened_at is None
            else self._latest_fx_on_or_before(pair, position.opened_at, fx_memo)[0]
        )
        if fx_open is None:
            missing.append("fx_open")
        return fx_open, fx_now, fx_info

    def _latest_fx_on_or_before(
        self,
        pair: str,
        target: date,
        fx_memo: FxMemo | None = None,
    ) -> tuple[Decimal | None, FxInfo]:
        """Return the FX rate on ``target`` (else the nearest earlier one) and its provenance.

        Looks back up to ``FX_BACKTRACK_DAYS`` days; the rate is ``None`` if
        none is published in that window (never guesses a rate). ``fx_memo``
        (one per :meth:`value_all` pass) answers a repeated ``(pair, target)``
        without a second lookup.
        """
        if fx_memo is not None and (pair, target) in fx_memo:
            return fx_memo[(pair, target)]
        answer = self._lookup_fx(pair, target)
        if fx_memo is not None:
            fx_memo[(pair, target)] = answer
        return answer

    def _lookup_fx(self, pair: str, target: date) -> tuple[Decimal | None, FxInfo]:
        start = target - timedelta(days=FX_BACKTRACK_DAYS)
        result = self._fx_provider.get_daily_rates(pair, start, target)
        candidates = [rate for rate in result.rates if rate.date <= target]
        if result.status is DataStatus.UNAVAILABLE or not candidates:
            info = FxInfo(
                pair=pair,
                as_of=None,
                source=result.source,
                data_status=DataStatus.UNAVAILABLE,
                source_note=source_note(result.source),
                reason=result.reason,
            )
            return None, info
        latest = max(candidates, key=lambda rate: rate.date)
        info = FxInfo(
            pair=pair,
            as_of=latest.date.isoformat(),
            source=result.source,
            data_status=result.status,
            source_note=source_note(result.source),
            reason=result.reason,
        )
        return latest.rate, info
