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

Any missing input (no price adapter for the market, no cached/live price, no
open date to price F0 at, no FX rate on or before the open date within the
lookback window) yields
``status = insufficient_data`` with the affected outputs left null. Nothing is
ever interpolated or fabricated.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.data.interface import DataStatus, Market, ProviderResult
from app.data.providers.fx import FxRateProvider
from app.positions.models import Currency, Position

#: How far back to look for the latest daily close (skips weekends/holidays).
PRICE_LOOKBACK_DAYS = 10
#: How far back to accept an FX rate on/before a target date (per the spec).
FX_BACKTRACK_DAYS = 7

_TWD_RATE = Decimal(1)


class PriceService(Protocol):
    """The slice of ``MarketDataService`` the valuator depends on.

    Declared as a Protocol so the valuator is decoupled from the concrete
    service (and trivially fakeable in tests without a cache or network).
    """

    def get_daily_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult: ...


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
    pnl_original: PnlOriginal | None
    pnl_twd: Decimal | None
    asset_contribution_twd: Decimal | None
    fx_contribution_twd: Decimal | None


@dataclass(frozen=True)
class PositionValuation:
    """A valuation plus the TWD cost/market-value used to aggregate totals.

    ``cost_twd`` and ``market_value_twd`` are only populated when the valuation
    is ``ok`` (i.e. every input was available); they are the per-position
    contributions to ``totals`` and are ``None`` otherwise so callers never sum
    fabricated numbers.
    """

    valuation: Valuation
    cost_twd: Decimal | None
    market_value_twd: Decimal | None


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
    ) -> None:
        self._market_services = dict(market_services)
        self._fx_provider = fx_provider
        self._clock = clock

    def value_position(self, position: Position) -> PositionValuation:
        today = self._clock().date()
        missing: list[str] = []

        price_info, price_now = self._resolve_price(position, today)
        if price_now is None:
            missing.append("price")

        fx_open, fx_now = self._resolve_fx(position, today, missing)

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
                    pnl_original=pnl_original,
                    pnl_twd=None,
                    asset_contribution_twd=None,
                    fx_contribution_twd=None,
                ),
                cost_twd=None,
                market_value_twd=None,
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
                pnl_original=pnl_original,
                pnl_twd=parts.total_twd,
                asset_contribution_twd=parts.asset_contribution_twd,
                fx_contribution_twd=parts.fx_contribution_twd,
            ),
            cost_twd=quantity * price_open * fx_open,
            market_value_twd=quantity * price_now * fx_now,
        )

    def _resolve_price(
        self, position: Position, today: date
    ) -> tuple[PriceInfo | None, Decimal | None]:
        service = self._market_services.get(position.market)
        if service is None:
            return None, None
        start = today - timedelta(days=PRICE_LOOKBACK_DAYS)
        result = service.get_daily_bars(position.symbol, position.market, start, today)
        if result.status is DataStatus.UNAVAILABLE or not result.bars:
            return None, None
        latest = max(result.bars, key=lambda bar: bar.date)
        info = PriceInfo(
            value=latest.close,
            as_of=latest.date.isoformat(),
            source=result.source,
            data_status=result.status,
        )
        return info, latest.close

    def _resolve_fx(
        self, position: Position, today: date, missing: list[str]
    ) -> tuple[Decimal | None, Decimal | None]:
        if position.currency == "TWD":
            # A TWD position is already in the reporting currency: F0 = F1 = 1
            # and the FX contribution is therefore identically zero.
            return _TWD_RATE, _TWD_RATE
        pair = f"{position.currency}TWD"
        fx_now = self._latest_fx_on_or_before(pair, today)
        if fx_now is None:
            missing.append("fx_now")
        # Without an open date there is no date to price F0 at, and no rate is
        # substituted for it: the position reports insufficient_data instead.
        fx_open = (
            None
            if position.opened_at is None
            else self._latest_fx_on_or_before(pair, position.opened_at)
        )
        if fx_open is None:
            missing.append("fx_open")
        return fx_open, fx_now

    def _latest_fx_on_or_before(self, pair: str, target: date) -> Decimal | None:
        """Return the FX rate on ``target``, else the nearest earlier one.

        Looks back up to ``FX_BACKTRACK_DAYS`` days; returns ``None`` if no rate
        is published in that window (never guesses a rate).
        """
        start = target - timedelta(days=FX_BACKTRACK_DAYS)
        result = self._fx_provider.get_daily_rates(pair, start, target)
        if result.status is DataStatus.UNAVAILABLE or not result.rates:
            return None
        candidates = [rate for rate in result.rates if rate.date <= target]
        if not candidates:
            return None
        return max(candidates, key=lambda rate: rate.date).rate
