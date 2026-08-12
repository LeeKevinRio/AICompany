"""One 除權息 (ex-dividend / ex-rights) event, and the factor derived from it.

Mirrors ``app.data.interface.PriceBar``'s provenance discipline: every event
carries ``as_of`` (when it was retrieved) and ``source`` (which adapter
produced it), and prices stay ``Decimal`` end to end -- the Decimal->float
boundary is ``app.signals.frame``, not here.

## Where the adjustment factor comes from (and why it is point-in-time clean)

The exchange itself publishes, for every ex-date, both the **前一日收盤價**
(the close the day before the event) and the **除權息參考價** (the reference
price the day opens from). Their ratio::

    factor = 除權息參考價 / 前一日收盤價

is the exact proportional drop the distribution mechanically causes, already
netting cash dividends, stock dividends and rights together, computed by the
exchange rather than re-derived here from a formula we would have to guess.

Both numbers are known **on the ex-date itself, before the open** -- the
reference price is what the exchange publishes to set that day's price limits.
So the factor for ex-date ``d`` uses only information available at ``d``; no
future bar is consulted. (Whether *applying* that factor to earlier bars leaks
anything is a separate question, answered in ``app.dividends.adjust``.)

When the reference price is missing the factor falls back to
``(前一日收盤價 - 現金股利 - 權值) / 前一日收盤價``, which is the same
quantity reconstructed from the components. When neither route is available,
or the result is not a plausible factor, :attr:`DividendEvent.adjustment_factor`
returns ``None`` -- the event is refused rather than guessed, and the caller
reports it as skipped instead of silently corrupting a price series.

## Where ``previous_close`` comes from for the 預告表 source (2026-08-12)

``app.dividends.providers.TwseDividendAdapter`` now reads TWSE's 除權除息預告表
(``TWT48U_ALL``, verified by the CEO 2026-08-12 -- see that module's docstring),
which is a **forecast** of upcoming ex-dates. It never publishes 前一日收盤價 or
除權息參考價 at all: at publish time the ex-date has not happened yet, so
neither number exists. Rows from that source therefore always construct this
model with ``previous_close=None`` and ``reference_price=None``; the field
stays a plain optional here, so ``adjustment_factor`` is ``None`` (unusable)
until something fills ``previous_close`` in.

``app.dividends.adjust.back_adjust_bars`` is the one place that fills it in:
once the actual trading history reaches the day before the ex-date, that bar's
own raw close **is** 前一日收盤價 -- the same public number a person could look
up by hand, not a guess. See that module's docstring for why looking it up
from the bar series does not leak the future.

## ``stock_dividend_ratio`` -- recorded, not computed, this phase

``TWT48U_ALL`` also publishes ``StockDividendRatio`` for 除權 (stock dividend)
events, but as a **share ratio** (e.g. "每千股配股 N 股"), not a dollar amount.
``rights_value`` above expects a dollar figure (息值/權值, as TWSE's old
除權除息計算結果表 published it) -- converting a ratio into that figure needs a
per-unit share value this source does not publish, so forcing the ratio into
``rights_value`` would be guessing, not computing. Instead the raw ratio is
kept on ``stock_dividend_ratio`` purely as an observable record that a stock
component exists; :attr:`DividendEvent.adjustment_factor` refuses (returns
``None``) for any event carrying one, cash amount or not, because the cash
alone is only part of the story and a partial factor is not a fact. Widening
this is a tracked follow-up, not a silent gap.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.data.interface import Market

#: A factor at or below this is not a distribution, it is a broken row (a
#: 99%+ single-day drop). Refuse it rather than wreck the whole history.
MIN_PLAUSIBLE_FACTOR = Decimal("0.01")

#: Rounding noise in the exchange's own published reference price can push the
#: ratio a hair above 1. Anything beyond this is not rounding, so it is refused.
FACTOR_ROUNDING_TOLERANCE = Decimal("0.0001")


class DividendEvent(BaseModel):
    """One symbol's 除權息 event on one ex-date.

    ``previous_close`` / ``reference_price`` are the exchange's own published
    pair; ``cash_dividend`` (息值) and ``rights_value`` (權值) are kept as the
    fallback route and because they are what a reader wants to see when asking
    "why did this factor come out at 0.97?". ``stock_dividend_ratio`` is a
    third, separate signal -- see the module docstring's "recorded, not
    computed" section for why it never feeds the factor.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    market: Market
    #: 除權息交易日 -- the first day the price trades without the distribution.
    ex_date: date_type
    previous_close: Decimal | None = None
    reference_price: Decimal | None = None
    cash_dividend: Decimal = Decimal("0")
    rights_value: Decimal = Decimal("0")
    #: Raw 除權 share ratio from TWT48U_ALL's ``StockDividendRatio`` column,
    #: kept only as an observable record -- see the module docstring for why
    #: it is deliberately never folded into ``rights_value`` or the factor.
    stock_dividend_ratio: Decimal | None = None
    source: str
    as_of: datetime

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC)")
        return value

    @field_validator("symbol", "source")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @field_validator("cash_dividend", "rights_value")
    @classmethod
    def _must_be_non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("dividend components must be non-negative")
        return value

    @field_validator("previous_close", "reference_price")
    @classmethod
    def _prices_must_be_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("prices must be positive when present")
        return value

    @field_validator("stock_dividend_ratio")
    @classmethod
    def _stock_dividend_ratio_must_be_non_negative(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("stock_dividend_ratio must be non-negative when present")
        return value

    @property
    def adjustment_factor(self) -> Decimal | None:
        """The proportional price drop this event caused, or ``None`` if unusable.

        Preference order (both documented at module level):

        1. ``reference_price / previous_close`` -- the exchange's own numbers.
        2. ``(previous_close - cash - rights) / previous_close`` -- the same
           quantity rebuilt from components, used only when the reference price
           was not published in the row we parsed.

        Returns ``None`` -- never a guess -- when there is no usable route or
        the result is outside ``(MIN_PLAUSIBLE_FACTOR, 1]``.
        """
        raw = self._raw_factor()
        if raw is None:
            return None
        if raw <= MIN_PLAUSIBLE_FACTOR:
            return None
        if raw > Decimal(1) + FACTOR_ROUNDING_TOLERANCE:
            return None
        return min(raw, Decimal(1))

    def _raw_factor(self) -> Decimal | None:
        if self.stock_dividend_ratio is not None:
            # A stock/rights component exists but this phase has no dollar
            # value for it (see the module docstring) -- a cash-only factor
            # here would be incomplete, not conservative, so refuse the whole
            # event rather than understate the true drop.
            return None
        prev = self.previous_close
        if prev is None or prev <= 0:
            return None
        if self.reference_price is not None:
            return self.reference_price / prev
        distributed = self.cash_dividend + self.rights_value
        if distributed <= 0:
            return None
        return (prev - distributed) / prev

    @property
    def is_usable(self) -> bool:
        """Whether this event can actually adjust a price series."""
        return self.adjustment_factor is not None
