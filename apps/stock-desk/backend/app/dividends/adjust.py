r"""Back-adjustment (還原除權息) of a daily bar series -- for backtesting only.

## The boundary this module must not cross

**Adjusted prices are a measurement device, not a market quote.**

* ``run_backtest`` and every return statistic derived from it may use the
  adjusted series. Without it, a Taiwanese equity's measured return is
  systematically *understated*: on every ex-date the raw close drops by the
  distribution the holder actually received, and the raw series counts that
  drop as a loss while never counting the cash.
* **Position valuation, portfolio totals, exposure and every risk cap keep
  using the raw close** (``app.portfolio.valuation`` / ``app.advice.limits``).
  The raw close is the real market value of what the user holds today. A
  long-held position's back-adjusted price is *lower* than its real price by
  the cumulative factor, so quoting it as market value would misstate the
  portfolio and shift every cap computed from it. Nothing in this module is
  imported by the valuation or risk-limit path, and that is deliberate.

Adjusted bars are additionally re-labelled ``source="<source>+divadj"`` so that
if one ever escapes into a response by accident it is visibly not a raw quote.

## The method

For each usable event with ex-date ``d`` and factor ``f_d`` (see
``app.dividends.models``), every bar **strictly before** ``d`` is multiplied by
``f_d``. With several events, a bar's factor is the product of the factors of
all events after it::

    adjusted(b) = raw(b) * PROD{ f_d : b.date < d <= last_bar.date }

The most recent bar therefore keeps its raw price (nothing comes after it):
the series is anchored at the present, which is the standard convention and
the reason the level of the newest bar still matches reality.

Worked example (the golden test pins exactly this): closes 100.0 (06-14),
102.0 (06-15), ex-date 06-17 with 前收 102.0 and 參考價 99.0 so
``f = 99/102``, then 99.0 (06-17) and 101.0 (06-18).

* 06-14 -> ``100 * 99/102 = 97.0588235...``
* 06-15 -> ``102 * 99/102 = 99.0``
* 06-17, 06-18 unchanged (no event after them).

The raw series shows ``99/102 - 1 = -2.94%`` across the ex-date; the adjusted
series shows ``99/99 - 1 = 0%``, which is what the holder -- who received the
3.00 dividend -- actually experienced.

## Look-ahead: what is and is not leaked

Back-adjustment is the one place in this backtester where a *later* fact
touches an *earlier* bar, so it needs an explicit argument, not a promise.

Split a bar's factor at the decision date ``t``::

    adjusted(b) = raw(b) * PROD{f_d : b.date < d <= t}  *  PROD{f_d : t < d <= last}
                  \________ point-in-time part _______/    \___ constant K(t) ___/

For every bar visible on day ``t`` (all ``b.date <= t``), the second product is
the **same positive constant** ``K(t)``. So the window the strategy sees on day
``t`` equals the strictly point-in-time series (only events up to ``t``) times
one overall scale factor. The consequences, stated plainly:

* **Ratios, returns and any scale-invariant indicator are untouched by the
  future.** Moving averages vs price, RSI, breakout channels, momentum -- every
  strategy shipped in ``app.backtest.strategies`` -- see numbers identical to
  the point-in-time construction. ``tests/test_dividends_lookahead.py`` proves
  this by rebuilding the series forward-only and comparing.
* **Absolute price levels are not point-in-time.** A strategy that hard-codes
  a price threshold ("buy below NT$50") would be reading the future through the
  level. No shipped strategy does, and the look-ahead suite would catch it, but
  a future strategy author must know this: **do not condition on the absolute
  level of an adjusted price.**
* Events **after the last bar** are excluded entirely. They are strictly future
  relative to the whole backtest window, and including them would only rescale
  everything anyway.

## Filling in ``previous_close`` for the 預告表 source

``app.dividends.providers.TwseDividendAdapter`` (TWT48U_ALL, a forecast table)
never publishes 前一日收盤價: at the moment TWSE lists an upcoming ex-date, the
close from the day before it does not exist yet. Its events therefore arrive
here with ``previous_close=None``, and would be permanently unusable if
nothing filled that in. ``back_adjust_bars`` does: for every event missing
``previous_close``, it looks up the raw close of the last bar strictly before
the event's ``ex_date`` in the very same ``bars`` series being adjusted, and
uses that. This is not a guess -- it is the same public closing price a person
could read off the exchange by hand once the ex-date has actually arrived, and
it changes nothing about the point-in-time argument above: an event still
only touches bars *before* its ex-date, and the number used to size that touch
(``bars[ex_date - 1].close``) is itself dated strictly before the ex-date, so
no bar's derived factor depends on anything dated on or after that bar.
Events whose ex-date already carries a published ``previous_close`` (any
future non-forecast source) pass through this step unchanged.

Events still carrying a ``stock_dividend_ratio`` are unaffected by this fill
-- ``DividendEvent.adjustment_factor`` refuses them regardless of
``previous_close`` (see ``app.dividends.models``), so there is nothing to
gain by resolving a close for them.

## Known second-order assumption

The proportional (ratio) method is used, which is the industry convention: it
is equivalent to assuming the distribution is reinvested at the **ex-date
reference price**. Reinvesting at the ex-date *close* instead would give a
slightly different number. The difference is second order (it does not change
signal direction), but it is a modelling choice, not a fact, and the API
discloses it.

Volume is left raw on purpose. Adjusting share counts for stock dividends is a
separate transformation with its own conventions, no shipped strategy reads
volume, and a half-adjusted volume column would be worse than an honestly raw
one.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from app.data.interface import PriceBar
from app.dividends.models import DividendEvent

#: Suffix appended to ``PriceBar.source`` on adjusted bars, so an adjusted bar
#: that leaks somewhere it should not be is identifiable on sight.
ADJUSTED_SOURCE_SUFFIX = "+divadj"

#: Adjusted prices are synthetic; this keeps them from growing unbounded digits
#: while staying far finer than any price tick.
_PRICE_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True)
class DividendAdjustment:
    """The outcome of a back-adjustment attempt -- applied or honestly not.

    ``bars`` is always usable: when ``applied`` is ``False`` it is the original
    raw series, so callers never have to branch to keep working. What they must
    not do is *hide* ``applied=False`` from the reader.
    """

    bars: list[PriceBar]
    applied: bool
    events_applied: int
    events_skipped: int
    first_ex_date: date_type | None
    last_ex_date: date_type | None
    #: Factor applied to the oldest bar (1 when nothing was applied). The raw
    #: series understated the window's total return by ``1/oldest_factor - 1``.
    oldest_bar_factor: Decimal

    @property
    def understatement(self) -> float | None:
        """How much the raw series understated the window's total return.

        ``None`` when no adjustment was applied (there is nothing to quantify).
        """
        if not self.applied or self.oldest_bar_factor <= 0:
            return None
        return float(Decimal(1) / self.oldest_bar_factor - Decimal(1))


def _fill_previous_close_from_bars(
    events: Iterable[DividendEvent], ordered_bars: Sequence[PriceBar]
) -> list[DividendEvent]:
    """Fill ``previous_close`` from ``ordered_bars`` for events missing it.

    See the module docstring's "Filling in ``previous_close`` for the 預告表
    source" section for the full rationale. ``ordered_bars`` must already be
    sorted ascending by date (``back_adjust_bars`` guarantees this).  An event
    whose ex-date sits on or before every bar has no earlier close to borrow
    and is left unchanged -- it will simply be "not applicable" or "unusable"
    downstream, exactly as before this fill existed.
    """
    if not ordered_bars:
        return list(events)
    bar_dates = [bar.date for bar in ordered_bars]
    resolved: list[DividendEvent] = []
    for event in events:
        if event.previous_close is not None:
            resolved.append(event)
            continue
        # Index of the last bar strictly before ex_date.
        index = bisect_left(bar_dates, event.ex_date) - 1
        if index < 0:
            resolved.append(event)
            continue
        resolved.append(
            event.model_copy(update={"previous_close": ordered_bars[index].close})
        )
    return resolved


def relevant_events(
    events: Iterable[DividendEvent],
    *,
    first_bar_date: date_type,
    last_bar_date: date_type,
) -> tuple[list[DividendEvent], int]:
    """Select the events that can move this window, and count the unusable ones.

    Kept: usable events (a computable factor) whose ex-date falls in
    ``(first_bar_date, last_bar_date]``. An event on or before the first bar has
    no earlier bar to adjust; an event after the last bar is future information
    relative to the entire window (see the module docstring).

    Counted as skipped: events inside the window whose factor could not be
    derived. Out-of-window events are not "skipped", they are simply not
    applicable, and counting them would make the disclosure misleading.
    """
    kept: list[DividendEvent] = []
    skipped = 0
    for event in events:
        if not (first_bar_date < event.ex_date <= last_bar_date):
            continue
        if event.adjustment_factor is None:
            skipped += 1
            continue
        kept.append(event)
    kept.sort(key=lambda item: item.ex_date)
    return kept, skipped


def back_adjust_bars(
    bars: Sequence[PriceBar], events: Iterable[DividendEvent]
) -> DividendAdjustment:
    """Back-adjust ``bars`` for ``events``; return the outcome, never raise.

    An empty bar list, or no applicable event, yields ``applied=False`` with
    the input returned untouched -- a state to disclose, not an error.
    """
    ordered = sorted(bars, key=lambda bar: bar.date)
    if not ordered:
        return DividendAdjustment(
            bars=[],
            applied=False,
            events_applied=0,
            events_skipped=0,
            first_ex_date=None,
            last_ex_date=None,
            oldest_bar_factor=Decimal(1),
        )

    filled_events = _fill_previous_close_from_bars(events, ordered)
    applicable, skipped = relevant_events(
        filled_events, first_bar_date=ordered[0].date, last_bar_date=ordered[-1].date
    )
    if not applicable:
        return DividendAdjustment(
            bars=list(ordered),
            applied=False,
            events_applied=0,
            events_skipped=skipped,
            first_ex_date=None,
            last_ex_date=None,
            oldest_bar_factor=Decimal(1),
        )

    # Walk backwards accumulating the factors of every event still ahead of the
    # bar; this is exactly PROD{f_d : bar.date < d <= last_bar.date}.
    factors: list[Decimal] = [Decimal(1)] * len(ordered)
    cumulative = Decimal(1)
    event_index = len(applicable) - 1
    for position in range(len(ordered) - 1, -1, -1):
        bar_date = ordered[position].date
        while event_index >= 0 and applicable[event_index].ex_date > bar_date:
            factor = applicable[event_index].adjustment_factor
            if factor is not None:  # always true: relevant_events filtered these
                cumulative *= factor
            event_index -= 1
        factors[position] = cumulative

    adjusted = [
        _scale_bar(bar, factor) if factor != 1 else bar
        for bar, factor in zip(ordered, factors, strict=True)
    ]
    return DividendAdjustment(
        bars=adjusted,
        applied=True,
        events_applied=len(applicable),
        events_skipped=skipped,
        first_ex_date=applicable[0].ex_date,
        last_ex_date=applicable[-1].ex_date,
        oldest_bar_factor=factors[0],
    )


def _scale_bar(bar: PriceBar, factor: Decimal) -> PriceBar:
    """Return ``bar`` with OHLC scaled by ``factor`` and its source re-labelled."""
    return bar.model_copy(
        update={
            "open": _scale(bar.open, factor),
            "high": _scale(bar.high, factor),
            "low": _scale(bar.low, factor),
            "close": _scale(bar.close, factor),
            "source": f"{bar.source}{ADJUSTED_SOURCE_SUFFIX}",
        }
    )


def _scale(price: Decimal, factor: Decimal) -> Decimal:
    return (price * factor).quantize(_PRICE_QUANTUM)
