"""Risk-layer statistics: volatility, drawdown, beta, correlation.

Two seams on purpose:

* Pure numeric functions (``annualized_volatility``, ``max_drawdown``,
  ``current_drawdown``, ``beta``) take plain float sequences so their behaviour
  is pinned by golden tests with hand-computed values, independent of any bar
  plumbing.
* Bar-level wrappers (``position_risk``, ``correlation_matrix``) convert bars to
  returns/prices once and delegate, attaching ``inputs_used`` provenance.

Every result declares its computation window and inputs, and reports
``insufficient_data`` (never a fabricated number) when there are too few
observations. A benchmark series (TWSE index for TW, SPY for US) is supplied by
the caller; beta is ``insufficient_data`` when it is missing or too short.

Conventions:

* Daily simple returns, ``r_t = close_t / close_{t-1} - 1``.
* Volatility uses the **sample** std (``ddof=1``) annualized by ``sqrt(252)``.
* Beta = cov(asset, benchmark) / var(benchmark) using sample moments.
* Correlations are Pearson, computed pairwise on each pair's overlapping dates.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from app.data.interface import PriceBar
from app.signals.frame import CLOSE, bars_to_frame, provenance
from app.signals.models import InputsUsed, Status

TRADING_DAYS_PER_YEAR = 252


class VolatilityResult(BaseModel):
    """Annualized volatility of daily returns."""

    model_config = ConfigDict(frozen=True)

    status: Status
    annualized_volatility: float | None
    daily_volatility: float | None
    observations: int
    inputs_used: InputsUsed
    as_of: str | None = None
    source: str | None = None


class DrawdownResult(BaseModel):
    """Drawdown of a price/equity path: the worst one, and the one in force now.

    ``max_drawdown`` / ``peak_date`` / ``trough_date`` describe the *historical
    extreme* over the whole window: once a deep fall happened inside the window
    the number stays put until that stretch rolls out, even after the price has
    made new highs.

    ``current`` / ``current_peak_date`` describe *where the latest close stands
    now*: ``latest close / highest close up to and including the latest bar - 1``
    (``<= 0``; ``0.0`` on the day of a new high). Only closes on or before the
    latest bar enter it, so it is point-in-time by construction. It is the last
    point of :func:`drawdown_series` and therefore never below ``max_drawdown``.
    ``current_peak_date`` is the **most recent** date the close stood at that
    highest level (a revisit of an earlier high moves it forward).

    Both new fields default to ``None`` so a payload produced before they
    existed still validates (backward compatible, additive only).
    """

    model_config = ConfigDict(frozen=True)

    status: Status
    max_drawdown: float | None
    peak_date: str | None
    trough_date: str | None
    observations: int
    inputs_used: InputsUsed
    as_of: str | None = None
    source: str | None = None
    current: float | None = None
    current_peak_date: str | None = None


class BetaResult(BaseModel):
    """Beta of an asset's returns against a benchmark's returns."""

    model_config = ConfigDict(frozen=True)

    status: Status
    beta: float | None
    observations: int
    benchmark: str | None
    inputs_used: InputsUsed
    as_of: str | None = None
    source: str | None = None


class CorrelationResult(BaseModel):
    """Pairwise Pearson correlation matrix across symbols.

    ``matrix[a][b]`` is ``None`` when the two symbols share fewer than
    ``min_overlap`` common-dated returns; such pairs are also listed in
    ``insufficient_pairs`` so a sparse matrix is never mistaken for a
    zero-correlation one.
    """

    model_config = ConfigDict(frozen=True)

    status: Status
    symbols: list[str]
    matrix: dict[str, dict[str, float | None]]
    insufficient_pairs: list[tuple[str, str]]
    min_overlap: int
    inputs_used: InputsUsed


# --- Pure numeric cores ------------------------------------------------------


def annualized_volatility(
    daily_returns: Sequence[float], *, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> tuple[float, float] | None:
    """Return ``(daily_std, annualized_std)`` or ``None`` if < 2 returns.

    Uses the sample standard deviation (``ddof=1``); annualization multiplies by
    ``sqrt(periods_per_year)``.
    """
    values = np.asarray(daily_returns, dtype="float64")
    if values.size < 2:
        return None
    daily = float(np.std(values, ddof=1))
    return daily, daily * math.sqrt(periods_per_year)


def _drawdown_path(values: np.ndarray) -> np.ndarray:
    """``value / running_peak - 1`` per point -- the one definition of drawdown."""
    return np.asarray(values / np.maximum.accumulate(values) - 1.0, dtype="float64")


def drawdown_series(prices: Sequence[float]) -> list[float]:
    """Return the underwater path ``price/running_peak - 1`` (every point ``<= 0``).

    The very series :func:`max_drawdown` takes its minimum over, exposed so a
    display layer can draw the whole underwater curve without restating what a
    drawdown is. ``min(drawdown_series(p))`` therefore equals
    ``max_drawdown(p)[0]`` by construction whenever the latter is defined
    (``len(p) >= 2``).
    """
    values = np.asarray(prices, dtype="float64")
    if values.size == 0:
        return []
    return [float(x) for x in _drawdown_path(values)]


def max_drawdown(prices: Sequence[float]) -> tuple[float, int, int] | None:
    """Return ``(max_drawdown, peak_index, trough_index)`` or ``None``.

    ``max_drawdown`` is the most negative ``price/running_peak - 1`` over the
    path (``<= 0``); the indices locate the peak the trough fell from and the
    trough itself. Needs at least 2 prices.
    """
    values = np.asarray(prices, dtype="float64")
    if values.size < 2:
        return None
    drawdown = _drawdown_path(values)
    trough_index = int(np.argmin(drawdown))
    worst = float(drawdown[trough_index])
    peak_index = int(np.argmax(values[: trough_index + 1]))
    return worst, peak_index, trough_index


def current_drawdown(prices: Sequence[float]) -> tuple[float, int] | None:
    """Return ``(current_drawdown, peak_index)`` or ``None``.

    ``current_drawdown`` is ``prices[-1] / max(prices) - 1`` (``<= 0``): how far
    the latest price sits below the highest price seen up to and including
    itself. Because the latest point is the end of the path, the running peak at
    that point *is* the overall maximum -- no later price exists to enter it.
    The value equals ``drawdown_series(prices)[-1]`` by construction.

    ``peak_index`` is the **last** index at which the price equalled that
    maximum, so a path that revisits its high reports the revisit, not the
    first touch. Needs at least 2 prices (same floor as :func:`max_drawdown`).
    """
    values = np.asarray(prices, dtype="float64")
    if values.size < 2:
        return None
    drawdown = _drawdown_path(values)
    peak_value = float(np.max(values))
    peak_index = int(np.flatnonzero(values == peak_value)[-1])
    return float(drawdown[-1]), peak_index


def beta(asset_returns: Sequence[float], benchmark_returns: Sequence[float]) -> float | None:
    """Return beta = cov(asset, benchmark) / var(benchmark), or ``None``.

    Returns ``None`` if the two series differ in length, have fewer than 2
    points, or the benchmark has zero variance.
    """
    asset = np.asarray(asset_returns, dtype="float64")
    bench = np.asarray(benchmark_returns, dtype="float64")
    if asset.size != bench.size or asset.size < 2:
        return None
    bench_var = float(np.var(bench, ddof=1))
    if bench_var == 0.0:
        return None
    covariance = float(np.cov(asset, bench, ddof=1)[0, 1])
    return covariance / bench_var


# --- Bar-level wrappers ------------------------------------------------------


def _close_returns(bars: list[PriceBar]) -> pd.Series:
    frame = bars_to_frame(bars)
    return frame[CLOSE].pct_change().dropna()


def volatility(
    bars: list[PriceBar], *, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> VolatilityResult:
    """Annualized volatility of a symbol's daily close returns."""
    inputs_used = InputsUsed(
        columns=[CLOSE],
        window={"lookback_bars": len(bars)},
        description=(
            "Std (ddof=1) of daily close returns annualized by sqrt("
            f"{periods_per_year}); needs at least 3 bars (2 returns)."
        ),
    )
    returns = _close_returns(bars)
    result = annualized_volatility(returns.tolist(), periods_per_year=periods_per_year)
    as_of, source = provenance(bars)
    if result is None:
        return VolatilityResult(
            status="insufficient_data",
            annualized_volatility=None,
            daily_volatility=None,
            observations=int(returns.size),
            inputs_used=inputs_used,
            as_of=as_of,
            source=source,
        )
    daily, annual = result
    return VolatilityResult(
        status="ok",
        annualized_volatility=annual,
        daily_volatility=daily,
        observations=int(returns.size),
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )


def drawdown(bars: list[PriceBar]) -> DrawdownResult:
    """Drawdown of a symbol's close path: historical maximum and current value.

    ``max_drawdown`` (with peak/trough dates) is the worst ``close/running_peak
    - 1`` over the window; ``current`` (with ``current_peak_date``) is the latest
    close against the highest close up to and including the latest bar. See
    :class:`DrawdownResult` for how the two differ.
    """
    inputs_used = InputsUsed(
        columns=[CLOSE],
        window={"lookback_bars": len(bars)},
        description=(
            "max_drawdown: most negative close/running_peak - 1 over the full "
            "close path. current: latest close / highest close up to and "
            "including the latest bar - 1. Needs at least 2 bars. Dates "
            "reported as ISO dates."
        ),
    )
    as_of, source = provenance(bars)
    if len(bars) < 2:
        return DrawdownResult(
            status="insufficient_data",
            max_drawdown=None,
            peak_date=None,
            trough_date=None,
            observations=len(bars),
            inputs_used=inputs_used,
            as_of=as_of,
            source=source,
        )
    frame = bars_to_frame(bars)
    close = frame[CLOSE]
    result = max_drawdown(close.tolist())
    assert result is not None  # len >= 2 guaranteed above
    worst, peak_index, trough_index = result
    now = current_drawdown(close.tolist())
    assert now is not None  # same length floor as max_drawdown
    current, current_peak_index = now
    dates = [ts.date().isoformat() for ts in frame.index]
    return DrawdownResult(
        status="ok",
        max_drawdown=worst,
        peak_date=dates[peak_index],
        trough_date=dates[trough_index],
        observations=len(bars),
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
        current=current,
        current_peak_date=dates[current_peak_index],
    )


def position_beta(
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    *,
    benchmark_label: str | None = None,
) -> BetaResult:
    """Beta of a symbol vs a benchmark, aligned on common dates.

    ``benchmark_bars`` is supplied by the caller (TWSE index for TW, SPY for US).
    When it is missing or the overlap is too short, returns
    ``insufficient_data``.
    """
    inputs_used = InputsUsed(
        columns=[CLOSE],
        window={"asset_bars": len(bars), "benchmark_bars": len(benchmark_bars or [])},
        description=(
            "Beta = cov(asset returns, benchmark returns) / var(benchmark "
            "returns), on dates common to both; needs at least 3 overlapping "
            "bars. Benchmark supplied by caller."
        ),
    )
    as_of, source = provenance(bars)
    if not benchmark_bars:
        return BetaResult(
            status="insufficient_data",
            beta=None,
            observations=0,
            benchmark=benchmark_label,
            inputs_used=inputs_used,
            as_of=as_of,
            source=source,
        )
    asset_close = bars_to_frame(bars)[CLOSE]
    bench_close = bars_to_frame(benchmark_bars)[CLOSE]
    aligned = pd.concat(
        {"asset": asset_close, "bench": bench_close}, axis=1, join="inner"
    ).sort_index()
    returns = aligned.pct_change().dropna()
    value = beta(returns["asset"].tolist(), returns["bench"].tolist())
    if value is None:
        return BetaResult(
            status="insufficient_data",
            beta=None,
            observations=int(len(returns)),
            benchmark=benchmark_label,
            inputs_used=inputs_used,
            as_of=as_of,
            source=source,
        )
    return BetaResult(
        status="ok",
        beta=value,
        observations=int(len(returns)),
        benchmark=benchmark_label,
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
    )


def correlation_matrix(
    symbol_bars: Mapping[str, list[PriceBar]], *, min_overlap: int = 3
) -> CorrelationResult:
    """Pairwise Pearson correlation of daily returns across symbols.

    Each pair is correlated on its own overlapping dates; a pair with fewer than
    ``min_overlap`` common returns is ``None`` in the matrix and listed in
    ``insufficient_pairs``.
    """
    symbols = list(symbol_bars.keys())
    inputs_used = InputsUsed(
        columns=[CLOSE],
        window={"symbols": len(symbols), "min_overlap": min_overlap},
        description=(
            "Pairwise Pearson correlation of daily close returns on each pair's "
            f"overlapping dates; a pair with < {min_overlap} common returns is "
            "null and flagged insufficient."
        ),
    )
    returns_by_symbol: dict[str, pd.Series] = {}
    for symbol, bars in symbol_bars.items():
        if len(bars) >= 2:
            returns_by_symbol[symbol] = bars_to_frame(bars)[CLOSE].pct_change().dropna()
        else:
            returns_by_symbol[symbol] = pd.Series(dtype="float64")

    matrix: dict[str, dict[str, float | None]] = {}
    insufficient: list[tuple[str, str]] = []
    for a in symbols:
        matrix[a] = {}
        for b in symbols:
            if a == b:
                matrix[a][b] = 1.0 if returns_by_symbol[a].size >= min_overlap else None
                continue
            joined = pd.concat(
                {"a": returns_by_symbol[a], "b": returns_by_symbol[b]},
                axis=1,
                join="inner",
            ).dropna()
            if len(joined) < min_overlap:
                matrix[a][b] = None
                if a < b:
                    insufficient.append((a, b))
                continue
            corr = float(joined["a"].corr(joined["b"]))
            matrix[a][b] = None if math.isnan(corr) else corr

    status: Literal["ok", "insufficient_data"] = "insufficient_data" if len(symbols) < 2 else "ok"
    return CorrelationResult(
        status=status,
        symbols=symbols,
        matrix=matrix,
        insufficient_pairs=insufficient,
        min_overlap=min_overlap,
        inputs_used=inputs_used,
    )
