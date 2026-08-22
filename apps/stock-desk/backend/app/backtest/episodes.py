"""Holding round trips: the repo's only definition of the Kelly inputs p and b.

A *round trip* (episode) is one complete stretch of being in the market: the bar
the book leaves flat, through every fill in between, to the bar it returns flat.
It is deliberately **not** a fill. The engine rebalances to a target weight every
bar, so a single real entry-to-exit holding period emits a long tail of tiny
position-reducing fills; counting those as trades inflates the sample and
distorts any win rate computed from them. ``report.py``'s existing
``win_rate``/``profit_factor`` are fill-layer statistics and keep that meaning --
nothing here reads them, and nothing here may be substituted for them.

What this module owns, and only this module:

1. round-trip extraction from a :class:`~app.backtest.engine.BacktestResult`;
2. out-of-sample attribution (fully-contained only) plus the counts of what that
   attribution had to throw away;
3. the p / b estimators over round-trip **returns**;
4. the Wilson interval for p and the joint bootstrap interval for the fraction.

What this module deliberately does **not** own: the Kelly fraction formula. It
lives once, in ``app.advice.limits.kelly_fraction``, and reaches the bootstrap
through the keyword-only, no-default ``fraction_fn`` argument of
:func:`bootstrap_fraction_ci`. No arithmetic that re-derives that fraction from p
and b may appear in this file -- a second copy of the formula would be a second
policy, and the point estimate and the resampled estimates would silently stop
being comparable. ``tests/test_backtest_episodes.py`` greps this file for the
shape of it.

Two rules the callers inherit:

* Attribution is by **bar index**, never by date string. The out-of-sample bounds
  come from the fold geometry (:func:`oos_window`), which is the same geometry
  the report was built from.
* A round-trip return is measured against the equity that stood **before** the
  entry, never against raw currency P&L. Averaging TWD amounts across a growing
  (or shrinking) book weights late trades more heavily than early ones and turns
  a payoff ratio into a size ratio.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import NormalDist, fmean
from typing import Literal

import numpy as np

from app.backtest.engine import BacktestResult
from app.backtest.splits import WalkForwardFold

#: Absolute share tolerance below which the book counts as flat.
#:
#: Share counts are floats: the engine sizes a fill as ``delta_value / price``,
#: so a full liquidation lands on a residue of a few ulps rather than on an exact
#: ``0.0``, and a chain of rebalances accumulates a few more. The tolerance is
#: **absolute, in shares**, not relative: the quantity compared is a share count
#: whose scale is set by price and equity, so a relative tolerance would move the
#: flat line whenever the price moved. 1e-9 shares sits many orders of magnitude
#: below the smallest economically meaningful residue (one US share; a TW lot is
#: 1000 shares) and many orders above the float noise of a few thousand fills, so
#: no realistic run can be misread in either direction.
POSITION_EPSILON = 1e-9

#: Which side of the sample was empty when a fraction had to be evaluated.
DegenerateKind = Literal["regular", "no_loss", "no_win"]


@dataclass(frozen=True)
class Episode:
    """One complete holding round trip, located by bar index.

    ``realized_pnl`` is the sum of the realized P&L of **every** fill in
    ``[entry_idx, exit_idx]`` -- the intermediate rebalancing fills included, so
    no currency is lost by treating the stretch as one trade.
    ``return_on_entry_equity`` divides it by ``entry_equity``, the equity of the
    bar before the entry (``initial_cash`` when the entry is the first bar).
    """

    entry_idx: int
    exit_idx: int
    realized_pnl: float
    entry_equity: float
    return_on_entry_equity: float


@dataclass(frozen=True)
class EpisodeExtraction:
    """Every closed round trip of a run, plus the one that may still be open."""

    episodes: tuple[Episode, ...]
    #: Entry bar of a round trip that never closed before the last bar, if any.
    open_entry_idx: int | None


@dataclass(frozen=True)
class RoundTripStats:
    """p and b over a set of round trips, with the counts they were built from.

    ``round_trip_win_rate`` is p; ``round_trip_payoff_ratio`` is b (mean winning
    return / mean absolute losing return). The names are paired on purpose: a
    bare ``payoff_ratio`` next to the fill-layer ``win_rate`` invites reading one
    of each as a set, which is exactly the mix-up this module exists to prevent.
    A round trip that returns exactly zero counts in ``n`` but is neither a win
    nor a loss -- the same convention ``report.py`` applies to fills.
    """

    n: int
    n_win: int
    n_loss: int
    round_trip_win_rate: float | None
    round_trip_payoff_ratio: float | None


@dataclass(frozen=True)
class RoundTripAttribution:
    """The round trips a bar window may claim, and what it had to exclude.

    ``excluded_boundary_trips`` counts round trips that overlap the window but
    are not contained by it. Excluding them is not free: a straddling round trip
    is on average a *longer* one, so the surviving sample is biased towards short
    holds. The count is reported so that bias can be disclosed rather than
    guessed at.
    """

    window_start: int
    window_stop: int
    episodes: tuple[Episode, ...]
    excluded_boundary_trips: int
    open_trip_at_end: int
    stats: RoundTripStats


@dataclass(frozen=True)
class ProportionInterval:
    """A two-sided interval for a proportion."""

    low: float
    high: float


@dataclass(frozen=True)
class FractionInterval:
    """A bootstrap interval for an injected fraction, with its audit trail.

    ``point`` is the fraction of the observed sample, produced by the very same
    ``fraction_fn`` the resamples went through. The two degenerate counts are
    kept apart because they push opposite ends of the interval: a resample with
    no losses props up the upper tail, a resample with no wins pins the lower
    one, and a single merged count would leave an auditor unable to tell which.
    """

    point: float
    low: float
    high: float
    seed: int
    draws: int
    degenerate_no_loss_draws: int
    degenerate_no_win_draws: int


def extract_episodes(result: BacktestResult) -> EpisodeExtraction:
    """Fold a run's fills into complete holding round trips.

    The book opens a round trip on the fill that carries the cumulative position
    across :data:`POSITION_EPSILON` and closes it on the fill that brings the
    position back inside the tolerance. The residue is snapped to zero at each
    close so a long run cannot drift its own flat line.
    """
    episodes: list[Episode] = []
    position = 0.0
    entry_idx: int | None = None
    realized = 0.0

    for trade in result.trades:
        was_flat = abs(position) <= POSITION_EPSILON
        position += trade.shares
        is_flat = abs(position) <= POSITION_EPSILON
        if was_flat and not is_flat:
            entry_idx = trade.bar_index
            realized = 0.0
        if entry_idx is None:
            # A fill that neither opens nor continues a round trip (a dust fill
            # while flat): it belongs to no episode, so it enters no sum.
            continue
        realized += trade.realized_pnl or 0.0
        if is_flat:
            episodes.append(_close_episode(result, entry_idx, trade.bar_index, realized))
            entry_idx = None
            position = 0.0

    return EpisodeExtraction(episodes=tuple(episodes), open_entry_idx=entry_idx)


def _close_episode(
    result: BacktestResult, entry_idx: int, exit_idx: int, realized_pnl: float
) -> Episode:
    """Build the episode record, measuring the return against pre-entry equity."""
    entry_equity = result.equity_curve[entry_idx - 1] if entry_idx > 0 else result.initial_cash
    if entry_equity <= 0.0:  # pragma: no cover - an entry needs positive equity to size
        # Structurally unreachable: the book was flat before ``entry_idx``, so
        # the previous bar's equity is the cash the entry was sized from, and a
        # non-positive one buys nothing. Refuse rather than invent a denominator.
        raise ValueError(f"round trip at bar {entry_idx} has non-positive pre-entry equity")
    return Episode(
        entry_idx=entry_idx,
        exit_idx=exit_idx,
        realized_pnl=realized_pnl,
        entry_equity=entry_equity,
        return_on_entry_equity=realized_pnl / entry_equity,
    )


def oos_window(folds: Sequence[WalkForwardFold]) -> tuple[int, int]:
    """The stitched out-of-sample bar range ``[start, stop)`` of a fold set.

    Taken from the fold geometry itself -- the same bounds
    :func:`app.backtest.report.walk_forward_report` reports on -- so the sample
    a Kelly input is estimated from is the sample that was reported, by
    construction rather than by a date filter that agrees with it today.
    """
    if not folds:
        raise ValueError("an out-of-sample window needs at least one fold")
    return folds[0].test_start, folds[-1].test_stop


def attribute_round_trips(
    result: BacktestResult, *, start: int, stop: int
) -> RoundTripAttribution:
    """Attribute round trips to the bar window ``[start, stop)``, fully contained.

    A round trip belongs to the window only when it both opens and closes inside
    it (``entry_idx >= start`` and ``exit_idx < stop``). One that straddles an
    edge is excluded and counted: crediting it to the window would import the
    P&L of bars the window never covered, and splitting it would invent a trade
    that was never closed. A round trip still open on the last bar is excluded
    and counted separately -- its outcome is not yet an outcome.
    """
    extraction = extract_episodes(result)
    contained: list[Episode] = []
    excluded_boundary = 0
    for episode in extraction.episodes:
        if episode.entry_idx >= start and episode.exit_idx < stop:
            contained.append(episode)
        elif episode.exit_idx >= start and episode.entry_idx < stop:
            excluded_boundary += 1
    # An open round trip runs to the last bar, so it overlaps the window exactly
    # when it opened before the window ended. It is never a boundary exclusion:
    # the two counts answer different questions and must not be merged.
    open_entry_idx = extraction.open_entry_idx
    open_at_end = 1 if open_entry_idx is not None and open_entry_idx < stop else 0
    return RoundTripAttribution(
        window_start=start,
        window_stop=stop,
        episodes=tuple(contained),
        excluded_boundary_trips=excluded_boundary,
        open_trip_at_end=open_at_end,
        stats=round_trip_stats(contained),
    )


def episode_returns(episodes: Sequence[Episode]) -> list[float]:
    """The round-trip returns of ``episodes``, in chronological order."""
    return [episode.return_on_entry_equity for episode in episodes]


def round_trip_stats(episodes: Sequence[Episode]) -> RoundTripStats:
    """Estimate p and b over a set of round trips."""
    return stats_from_returns(episode_returns(episodes))


def stats_from_returns(returns: Sequence[float]) -> RoundTripStats:
    """Estimate p and b over round-trip returns (the only such estimator here).

    p is the share of round trips that made money; b is the mean winning return
    divided by the mean absolute losing return. Both are ``None`` when the
    sample cannot support them -- no round trips at all for p, and no wins or no
    losses for b, whose ratio is then undefined rather than large.
    """
    n = len(returns)
    wins = [value for value in returns if value > 0.0]
    losses = [value for value in returns if value < 0.0]
    win_rate = len(wins) / n if n > 0 else None
    payoff_ratio = fmean(wins) / -fmean(losses) if wins and losses else None
    return RoundTripStats(
        n=n,
        n_win=len(wins),
        n_loss=len(losses),
        round_trip_win_rate=win_rate,
        round_trip_payoff_ratio=payoff_ratio,
    )


def wilson_interval(
    successes: int, trials: int, *, alpha: float = 0.05
) -> ProportionInterval | None:
    """Wilson score interval for a proportion, or ``None`` without observations.

    Wilson rather than the normal approximation because the samples this module
    produces are small and the proportion often sits near an edge, where the
    normal interval runs outside ``[0, 1]`` and understates its own width.
    """
    if trials <= 0 or not 0 <= successes <= trials:
        return None
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie in (0, 1)")
    z = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    z_sq = z * z
    phat = successes / trials
    denominator = 1.0 + z_sq / trials
    centre = (phat + z_sq / (2.0 * trials)) / denominator
    spread = z * math.sqrt(phat * (1.0 - phat) / trials + z_sq / (4.0 * trials * trials))
    half_width = spread / denominator
    return ProportionInterval(low=centre - half_width, high=centre + half_width)


def bootstrap_fraction_ci(
    returns: Sequence[float],
    *,
    fraction_fn: Callable[[float, float], float | None],
    seed: int,
    draws: int,
    alpha: float = 0.05,
) -> FractionInterval:
    """Percentile bootstrap interval for an injected fraction of (p, b).

    Each draw resamples the round-trip returns with replacement and re-estimates
    p and b **together** from that resample, so the correlation between the two
    is carried through instead of being assumed away by intervals built one at a
    time. ``fraction_fn`` supplies the fraction itself; this module never
    computes one, which is what keeps a single formula in the codebase.

    Degenerate resamples are never dropped -- dropping them truncates whichever
    tail they came from and silently narrows the interval:

    * no losses: b is unbounded rather than unknown, so the draw is evaluated at
      ``fraction_fn(p_hat, inf)``. The injected formula's own arithmetic returns
      p_hat there; no special case is written here.
    * no wins: b does not exist at all (there is nothing to average), so the draw
      records ``-inf`` -- the true limit as b approaches zero -- and
      ``fraction_fn`` is not called. Feeding it a fabricated ``b = 0`` would draw
      a ``None`` that could only be dropped, and dropping *lower*-tail draws
      lifts the lower bound, which is the one direction a disclosure interval
      must never move.

    The bounds are taken without interpolation (lower-rank for the low bound,
    upper-rank for the high one): interpolating across an infinite draw produces
    a NaN, and the rank choice widens rather than narrows.
    """
    if draws <= 0:
        raise ValueError("bootstrap needs at least one draw")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie in (0, 1)")
    sample = np.asarray(returns, dtype="float64")
    size = int(sample.size)
    if size == 0:
        raise ValueError("bootstrap needs at least one round-trip return")

    point, _ = _fraction_of_sample(sample, fraction_fn=fraction_fn)
    rng = np.random.default_rng(seed)
    values = np.empty(draws, dtype="float64")
    no_loss_draws = 0
    no_win_draws = 0
    for draw in range(draws):
        resample = sample[rng.integers(0, size, size=size)]
        value, kind = _fraction_of_sample(resample, fraction_fn=fraction_fn)
        if kind == "no_loss":
            no_loss_draws += 1
        elif kind == "no_win":
            no_win_draws += 1
        values[draw] = value

    low = float(np.percentile(values, 100.0 * alpha / 2.0, method="lower"))
    high = float(np.percentile(values, 100.0 * (1.0 - alpha / 2.0), method="higher"))
    return FractionInterval(
        point=point,
        low=low,
        high=high,
        seed=seed,
        draws=draws,
        degenerate_no_loss_draws=no_loss_draws,
        degenerate_no_win_draws=no_win_draws,
    )


def _fraction_of_sample(
    sample: np.ndarray, *, fraction_fn: Callable[[float, float], float | None]
) -> tuple[float, DegenerateKind]:
    """Evaluate the injected fraction on one sample of round-trip returns."""
    size = int(sample.size)
    wins = sample[sample > 0.0]
    losses = sample[sample < 0.0]
    phat = float(wins.size) / size
    if wins.size == 0:
        # Nothing to average on the winning side: b is undefined, not zero.
        return float("-inf"), "no_win"
    if losses.size == 0:
        return _require_fraction(fraction_fn, phat, math.inf), "no_loss"
    payoff_ratio = float(np.mean(wins)) / float(-np.mean(losses))
    return _require_fraction(fraction_fn, phat, payoff_ratio), "regular"


def _require_fraction(
    fraction_fn: Callable[[float, float], float | None], win_rate: float, payoff_ratio: float
) -> float:
    """The injected fraction, refusing a ``None`` instead of dropping the draw."""
    value = fraction_fn(win_rate, payoff_ratio)
    if value is None:
        raise ValueError(
            "fraction_fn returned None for an in-domain sample "
            f"(p={win_rate}, b={payoff_ratio}); a dropped draw would bias the interval"
        )
    return value
