"""Deterministic synthetic OHLCV series for the offline demo.

SYNTHETIC DATA NOTICE
=====================
Every number this module produces is fabricated by the formulas below. It is
not a recording of any market, it is not a forecast, and it must never be used
for a real decision. The only reason it exists is to give an offline
environment enough shape to exercise the indicator, risk and advice layers end
to end. Every bar is therefore tagged :data:`DEMO_SOURCE` so its provenance
travels with it all the way to the UI's "來源" line.

Design constraints, in the order they mattered:

* **Deterministic.** A fixed seed drives a plain ``random.Random`` stream, so a
  re-run produces byte-identical prices and a test can assert on them.
* **Regime-shaped, not noise.** A flat random walk leaves MA crossings, RSI
  extremes and drawdowns to chance. The path is instead assembled from explicit
  :class:`Regime` segments -- trend up, correction, mean-reverting range, trend
  up, sell-off, recovery -- so the golden cross, the death cross, an overbought
  and an oversold RSI, and a double-digit drawdown all actually occur.
* **OHLC invariants hold after rounding.** Highs round up and lows round down,
  so ``low <= min(open, close) <= max(open, close) <= high`` survives
  quantization to a two-decimal tick (see ``app.data.quality``).

The leveraged series is not drawn independently: it is derived from the index
series by :func:`daily_reset_closes` applying the fund's stated single-day
multiple plus its expense accrual, so the demo reproduces genuine daily-reset
compounding rather than an invented shape.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Final

from app.data.interface import Market, PriceBar

#: Written into ``PriceBar.source`` (and therefore into the cache's ``source``
#: column and the API's ``data.source``) for every bar this module builds. It is
#: deliberately not a real vendor id: the UI prints it verbatim, so a demo
#: dataset can never be read as TWSE/TPEx/FinMind data.
DEMO_SOURCE: Final = "demo_synthetic"

#: Price tick the synthetic quotes are rounded to. Real TW tick sizes are
#: price-banded; a single 0.01 tick is close enough for a demo and is stated
#: here rather than hidden in the rounding calls.
PRICE_QUANTUM: Final = Decimal("0.01")

#: Denominator for the daily expense accrual of the derived leveraged series,
#: matching ``app.signals.risk.TRADING_DAYS_PER_YEAR``.
TRADING_DAYS_PER_YEAR: Final = 252


@dataclass(frozen=True)
class Regime:
    """One segment of the synthetic path.

    ``drift`` and ``volatility`` are per-bar log-return terms. ``reversion``
    pulls the log price back toward the level the segment opened at, which is
    what turns a segment into a *range* instead of a low-volatility trend; it is
    ``0.0`` for the trending segments.
    """

    name: str
    bars: int
    drift: float
    volatility: float
    reversion: float = 0.0
    volume_multiplier: float = 1.0


#: The shipped layout: 520 bars (~2 years of trading days) covering every
#: regime the four pages need something to show for.
DEFAULT_REGIMES: Final[tuple[Regime, ...]] = (
    Regime(name="warmup", bars=60, drift=0.0005, volatility=0.010, reversion=0.02),
    Regime(name="uptrend", bars=130, drift=0.0024, volatility=0.011, volume_multiplier=1.15),
    Regime(name="correction", bars=55, drift=-0.0038, volatility=0.015, volume_multiplier=1.60),
    Regime(name="range", bars=90, drift=0.0000, volatility=0.009, reversion=0.06),
    Regime(name="second_uptrend", bars=120, drift=0.0025, volatility=0.012, volume_multiplier=1.20),
    Regime(name="selloff", bars=40, drift=-0.0050, volatility=0.014, volume_multiplier=1.80),
    Regime(name="recovery", bars=25, drift=0.0048, volatility=0.013, volume_multiplier=1.30),
)


def regime_bar_count(regimes: Sequence[Regime] = DEFAULT_REGIMES) -> int:
    """Total number of bars a regime layout produces."""
    return sum(regime.bars for regime in regimes)


def regime_volume_multipliers(regimes: Sequence[Regime] = DEFAULT_REGIMES) -> list[float]:
    """Per-bar volume multipliers, so turnover rises in the volatile segments."""
    return [regime.volume_multiplier for regime in regimes for _ in range(regime.bars)]


def trading_days(count: int, *, end: date) -> list[date]:
    """``count`` weekdays ending on or before ``end``, ascending.

    Weekends only: TW market holidays are not modelled, so the demo calendar is
    denser than the real one. That is a stated simplification, not an attempt to
    reproduce the exchange calendar -- ``app.data.quality`` only reports missing
    trading days when a caller supplies a real calendar to compare against.
    """
    if count <= 0:
        raise ValueError("count must be positive")
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


def _shock(rng: random.Random) -> float:
    """A deterministic ~N(0, 1) draw built from three uniforms.

    Three uniforms sum to variance 3/12, so scaling by 2 gives unit variance.
    ``random.gauss`` would do as well; this avoids depending on the exact
    internals of its cached-pair implementation for reproducibility.
    """
    return (rng.random() + rng.random() + rng.random() - 1.5) * 2.0


def synthetic_closes(
    *,
    start_price: float,
    seed: int,
    regimes: Sequence[Regime] = DEFAULT_REGIMES,
) -> list[float]:
    """Build the close path for one instrument from a regime layout."""
    if start_price <= 0.0:
        raise ValueError("start_price must be positive")
    rng = random.Random(seed)
    log_price = math.log(start_price)
    closes: list[float] = []
    for regime in regimes:
        anchor = log_price
        for _ in range(regime.bars):
            pull = regime.reversion * (anchor - log_price)
            log_price += regime.drift + pull + regime.volatility * _shock(rng)
            closes.append(math.exp(log_price))
    return closes


def daily_reset_closes(
    index_closes: Sequence[float],
    *,
    start_price: float,
    leverage_factor: float,
    expense_ratio_annual: float,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> list[float]:
    """Compound an index path into a daily-reset leveraged NAV path.

    Each step applies ``leverage_factor`` to that *single day's* index return
    and subtracts one day of the expense ratio -- the actual mechanic of a
    daily-reset product, which is why the resulting path lags ``L x`` the
    index's cumulative return through a choppy segment.
    """
    if len(index_closes) < 2:
        raise ValueError("index_closes must contain at least two closes")
    if start_price <= 0.0:
        raise ValueError("start_price must be positive")
    daily_expense = expense_ratio_annual / trading_days_per_year
    nav = start_price
    closes = [nav]
    for previous, current in zip(index_closes, index_closes[1:], strict=False):
        index_return = current / previous - 1.0
        nav *= 1.0 + leverage_factor * index_return - daily_expense
        if nav <= 0.0:
            # A demo path must stay quotable; a wipe-out would mean the regime
            # parameters produced a >50% single-day index move, which is a bug
            # in the layout rather than something to silently floor.
            raise ValueError("derived leveraged NAV reached zero; check regime parameters")
        closes.append(nav)
    return closes


def _quantize(value: float, rounding: str) -> Decimal:
    return Decimal(repr(value)).quantize(PRICE_QUANTUM, rounding=rounding)


def build_bars(
    *,
    symbol: str,
    market: Market,
    currency: str,
    dates: Sequence[date],
    closes: Sequence[float],
    base_volume: int,
    seed: int,
    as_of: datetime,
    volume_multipliers: Sequence[float] | None = None,
    source: str = DEMO_SOURCE,
) -> list[PriceBar]:
    """Wrap a close path into full OHLCV bars.

    The open gaps from the previous close, and the intraday range widens with
    the size of the day's move, so ATR and the KD/Bollinger inputs see a
    plausible high/low structure instead of four identical prices. Volume is
    scaled by the same move -- and by the regime's ``volume_multiplier`` when
    ``volume_multipliers`` is supplied -- so the volume z-score has spikes to
    find.
    """
    if len(dates) != len(closes):
        raise ValueError("dates and closes must be the same length")
    multipliers = list(volume_multipliers) if volume_multipliers is not None else [1.0] * len(dates)
    if len(multipliers) != len(dates):
        raise ValueError("volume_multipliers must be the same length as dates")
    rng = random.Random(seed)
    bars: list[PriceBar] = []
    for index, (day, close) in enumerate(zip(dates, closes, strict=True)):
        previous_close = closes[index - 1] if index > 0 else close
        daily_return = close / previous_close - 1.0
        open_price = previous_close * (1.0 + 0.25 * abs(daily_return) * _shock(rng))
        span = (0.4 * abs(daily_return) + 0.004 * (0.5 + rng.random())) / 2.0
        high = max(open_price, close) * (1.0 + span)
        low = min(open_price, close) * (1.0 - span)
        volume = int(
            base_volume
            * multipliers[index]
            * (0.7 + 0.6 * rng.random())
            * (1.0 + 12.0 * abs(daily_return))
        )
        bars.append(
            PriceBar(
                symbol=symbol,
                market=market,
                date=day,
                open=_quantize(open_price, ROUND_HALF_UP),
                high=_quantize(high, ROUND_CEILING),
                low=_quantize(low, ROUND_FLOOR),
                close=_quantize(close, ROUND_HALF_UP),
                volume=volume,
                currency=currency,
                as_of=as_of,
                source=source,
            )
        )
    return bars
