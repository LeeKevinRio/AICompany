"""Sector momentum evaluator: labels, statistics, look-ahead self-checks, candidate G1..G6.

ADR-0012 D-8, D-13, C-15, C-36, C-41; methodology §5, §6, §8 (fifth edition).

What lives here and nowhere else (C-15, with :mod:`app.backtest.basket`):
forward returns of sector baskets, their excess over the equal-weight market
(B_EW), the round-trip cost deduction, the historical rates p / q, the tests
on them (Wilson, circular block bootstrap, random-sector permutation), the
time-shift and label-shuffle placebos, and the candidate G1..G6 outcome.

What does **not** live here:

* the effective ``gate_status`` -- only :mod:`app.sectors.gate` composes it
  (C-20); this module produces a *candidate* (``GateCheckRecord`` rows) that
  never reaches the API as such;
* any second implementation of the universe or the ranking: every decision is
  ``rank_sectors(calculation_set(panel.as_of(t), definition), definition)``
  with the very function objects of :mod:`app.sectors.universe` and
  :mod:`app.sectors.ranking` (T-15, methodology T2);
* configuration or environment reads (C-24, T-17): every threshold comes from
  the :class:`SectorMomentumDefinition` passed in.

Timing (methodology §5.1): decide at the close of ``t`` on ``panel.as_of(t)``;
enter at the t+1 open; exit at the t+H close; the next decision of the same
phase is t+H, so samples never overlap. The main result is phase 0 from D0;
the other H-1 phases are all computed and all reported (G5), never selected.

Backtest-protocol rule 3 (walk-forward) -- known deviation approved by the CEO
(派工單 §12 item 4, ADR-0012 Consequences): the judged data is the forward
point-in-time segment after the parameters were frozen, so there is no
training window; in-sample is "none" and out-of-sample is the whole segment.
The 126-session test-window geometry of ``walk_forward_splits`` is kept for
segment reporting only.
"""

from __future__ import annotations

import dataclasses
import math
import random
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from fractions import Fraction
from types import MappingProxyType
from typing import Final, Literal

import numpy as np
import pandas as pd

from app.backtest.basket import (
    BasketExecution,
    BasketFill,
    BasketResult,
    BasketSample,
    BasketStrategy,
    HoldingOutcomes,
    HoldingWindow,
    PriceBook,
    assemble_result,
    compare_fills,
    fill_basket,
    holding_outcomes,
    round_trip_cost,
)
from app.backtest.costs import CostModel
from app.backtest.episodes import wilson_interval
from app.backtest.splits import walk_forward_splits
from app.data.panel import (
    BARS_SOURCE_PRIORITY,
    MarketPanel,
    PanelFrames,
    PointInTimePanel,
    Regime,
    cutoff,
)
from app.sectors.coverage import ex_dividend_feed_covered
from app.sectors.definition import SectorMomentumDefinition
from app.sectors.gate import (
    EvaluationWindow,
    InsufficientChecks,
    PitStatus,
    insufficient_reason,
    pit_gaps,
)
from app.sectors.index import mean_return, up_count
from app.sectors.models import (
    DataRegime,
    GateCheckRecord,
    GateName,
    InsufficientReason,
    PitGap,
    SelfcheckRecord,
    SelfcheckStatus,
    StatsRecord,
)
from app.sectors.ranking import SectorRanking, rank_sectors
from app.sectors.universe import CalculationSet, calculation_set

#: The test-window length of the walk-forward geometry kept for segment reports.
SEGMENT_SESSIONS: Final = 126
#: Snapshots carried longer than this many trading sessions invalidate a sample (D-2).
MAX_CARRIED_SESSIONS: Final = 5
#: Block lengths reported beside the judged one (methodology §6.2: 2 and 8 besides 4).
REPORTED_BLOCK_LENGTHS: Final[tuple[int, ...]] = (2, 4, 8)
#: Smallest time shift of the placebo (methodology §8.2: 4 <= k <= N-4).
PLACEBO_MIN_SHIFT: Final = 4

# Self-check names (``sector_gate_checks.check_name`` with check_kind='selfcheck').
T1: Final = "T1_future_perturbation"
T3A: Final = "T3a_leak_control"
T3B: Final = "T3b_lag_one_session"
T4: Final = "T4_ex_dividend_no_leak"
T5: Final = "T5_survivorship"
T6: Final = "T6_classification_pit"
T7: Final = "T7_benchmark_consistency"
T8: Final = "T8_time_shift_placebo"
T8_SHUFFLE: Final = "T8_label_shuffle"
T9: Final = "T9_board_replay_same_set"
SELFCHECK_ORDER: Final[tuple[str, ...]] = (T1, T3A, T3B, T4, T5, T6, T7, T8, T8_SHUFFLE, T9)
#: C-36: which checks may be ``skipped_insufficient_n`` (N < 30) or ``vacuous``.
#: The label shuffle is the diagnostic half of T8, so it shares T8's allowance.
SKIPPABLE_CHECKS: Final[frozenset[str]] = frozenset({T3A, T8, T8_SHUFFLE})
VACUOUS_ALLOWED: Final[frozenset[str]] = frozenset({T4, T5, T6})

InvalidReason = Literal[
    "no_board",
    "card_insufficient",
    "lookback_gap",
    "snapshot_stale",
    "bars_gap",
    "no_ranked_sector",
    "all_excluded",
    "empty_benchmark",
]


# ---------------------------------------------------------------------------
# Decisions: the one pipeline (T-15)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    """What the board of ``decision_date`` was, recomputed with the shared functions."""

    decision_date: date
    regime: Regime
    calc: CalculationSet
    ranking: SectorRanking
    #: Session of the ex-dividend announcement run in force (latest visible ok).
    dividend_session: date | None
    #: The decision date has bars in its own view (a board could be computed).
    has_bars: bool
    #: Symbols of the listing snapshot the decision read (T5 audits its content).
    listed: frozenset[str] = frozenset()
    #: The whole-card state the board showed that day (C-42); a card in
    #: ``insufficient_data`` shows no ranking, so it cannot be a sample.
    insufficient: InsufficientReason | None = None

    @property
    def rank_1(self) -> str | None:
        return self.ranking.ranked[0].sector_code if self.ranking.ranked else None


def decide(view: PointInTimePanel, definition: SectorMomentumDefinition) -> Decision:
    """The board of ``view.decision_date``: ``calculation_set`` then ``rank_sectors``."""
    calc = calculation_set(view, definition)
    ranking = rank_sectors(calc, definition)
    t = view.decision_date
    dividend = [day for day in view.ok_run_sessions("dividend_announce") if day <= t]
    listing = view.snapshot("listing")
    card = ranking.assessment.card
    has_bars = t in view.sessions
    insufficient = insufficient_reason(
        InsufficientChecks(
            data_as_of_known=has_bars,
            ex_dividend_feed_covered=ex_dividend_feed_covered(view, definition),
            completeness_low=card.completeness_low,
            computable_low=card.computable_low,
            any_sector_ranked=bool(ranking.ranked),
        )
    )
    return Decision(
        decision_date=t,
        regime=view.regime,
        calc=calc,
        ranking=ranking,
        dividend_session=max(dividend) if dividend else None,
        has_bars=has_bars,
        listed=frozenset(str(symbol) for symbol in listing.rows["symbol"])
        if listing is not None
        else frozenset(),
        insufficient=insufficient,
    )


def rank_1_strategy(definition: SectorMomentumDefinition) -> BasketStrategy:
    """Equal weight over ``C_g(t,L)`` of the rank-1 sector (the judged basket)."""

    def strategy(view: PointInTimePanel) -> Mapping[str, float]:
        top = decide(view, definition).ranking.ranked
        return {symbol: 1.0 for symbol in top[0].members} if top else {}

    return strategy


def benchmark_strategy(definition: SectorMomentumDefinition) -> BasketStrategy:
    """B_EW: equal weight over ``C_M(t,L)`` (T7: the same set the card uses)."""

    def strategy(view: PointInTimePanel) -> Mapping[str, float]:
        members = calculation_set(view, definition).market.members
        return {symbol: 1.0 for symbol in members}

    return strategy


# ---------------------------------------------------------------------------
# Point-in-time restoration factors for labels (D-4, T-7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelFactor:
    """``previous close / (close - change)`` on an ex-date, from snapshots saved by then."""

    symbol: str
    ex_date: date
    factor: float | None
    #: Why ``factor`` is None (machine code), else None.
    reason: str | None


class LabelFactorTable:
    """Multiplicative restoration factors keyed by symbol and ex-date."""

    def __init__(self, factors: Iterable[LabelFactor]) -> None:
        by_symbol: dict[str, list[LabelFactor]] = {}
        for item in factors:
            by_symbol.setdefault(item.symbol, []).append(item)
        self._events = {
            symbol: sorted(items, key=lambda item: item.ex_date)
            for symbol, items in by_symbol.items()
        }
        self._dates = {
            symbol: [item.ex_date for item in items] for symbol, items in self._events.items()
        }

    @property
    def factors(self) -> tuple[LabelFactor, ...]:
        return tuple(item for items in self._events.values() for item in items)

    def adjustment(self, symbol: str, after: date, through: date) -> float | None:
        """Product of factors with an ex-date in ``(after, through]``; None if one is unusable."""
        dates = self._dates.get(symbol)
        if not dates:
            return 1.0
        product = 1.0
        for item in self._events[symbol][bisect_right(dates, after) : bisect_right(dates, through)]:
            if item.factor is None:
                return None
            product *= item.factor
        return product


def _factor_from_prices(
    previous_close: float, close: float, change: float
) -> tuple[float | None, str | None]:
    if not math.isfinite(close) or close <= 0.0:
        return None, "no_bar_on_ex_date"
    if not math.isfinite(change):
        return None, "no_change_on_ex_date"
    reference = close - change
    if reference <= 0.0:
        return None, "non_positive_reference"
    if not math.isfinite(previous_close) or previous_close <= 0.0:
        return None, "no_previous_close"
    return previous_close / reference, None


def pit_label_factors(panel: MarketPanel) -> LabelFactorTable:
    """One factor per announced ``(symbol, ex_date)``, using only what was saved by then.

    For each event the view is ``as_of(ex_date)`` of a one-symbol sub-panel: the
    announcement must be visible at ``cutoff(ex_date)`` (else the event was not
    known in time and is not restored), and the ex-date bar's ``close -
    change`` and the previous visible close come from that same view. A
    one-symbol panel resolves bars exactly like the full one, because bar
    resolution and visibility are per ``(session, symbol)`` row.
    """
    frames = panel.frames
    announced = frames.ex_dividend.loc[:, ["symbol", "ex_date"]].drop_duplicates()
    if announced.empty:
        return LabelFactorTable(())
    bar_rows = frames.bars.groupby("symbol").indices
    dividend_rows = frames.ex_dividend.groupby("symbol").indices
    empty_listing = frames.listing.iloc[0:0]
    empty_classes = frames.classification.iloc[0:0]
    out: list[LabelFactor] = []
    for symbol, events in announced.groupby("symbol"):
        name = str(symbol)
        sub = MarketPanel(
            PanelFrames(
                bars=frames.bars.iloc[bar_rows.get(name, [])],
                listing=empty_listing,
                classification=empty_classes,
                ex_dividend=frames.ex_dividend.iloc[dividend_rows[name]],
                runs=frames.runs,
            )
        )
        for ex_date in sorted(set(events["ex_date"])):
            view = sub.as_of(ex_date)
            seen = view.ex_dividend_announcements()
            if not ((seen["symbol"] == name) & (seen["ex_date"] == ex_date)).any():
                continue  # not known by cutoff(ex_date): not a point-in-time event
            if ex_date not in view.sessions:
                out.append(LabelFactor(name, ex_date, None, "no_bar_on_ex_date"))
                continue
            before = view.sessions_before(ex_date, 1)
            previous = (
                float(view.field_matrix("close", before, [name]).to_numpy()[0, 0])
                if before
                else math.nan
            )
            today = float(view.field_matrix("close", [ex_date], [name]).to_numpy()[0, 0])
            change = float(view.field_matrix("change", [ex_date], [name]).to_numpy()[0, 0])
            factor, reason = _factor_from_prices(previous, today, change)
            out.append(LabelFactor(name, ex_date, factor, reason))
    return LabelFactorTable(out)


def _rebuild_factor(bars: pd.DataFrame, runs: pd.DataFrame, ex_date: date) -> float | None:
    """Independent rebuild of one factor from one symbol's raw bar rows (T4 ②).

    Re-derives visibility (``recorded_at <= cutoff(ex_date)``, ok runs only) and
    bar resolution (source priority, then latest record, then run id) straight
    from the frames, without the view machinery the evaluator used.
    """
    cut = cutoff(ex_date)
    ok = runs.loc[
        (runs["status"] == "ok")
        & (runs["kind"] == "bars")
        & (runs["recorded_at"] <= cut)
        & (runs["session_date"] <= ex_date)
    ]
    bars = bars.loc[
        (bars["recorded_at"] <= cut)
        & (bars["session_date"] <= ex_date)
        & bars["run_id"].isin(set(ok["run_id"]))
    ]
    if bars.empty:
        return None
    ranked = bars.assign(
        _p=[BARS_SOURCE_PRIORITY.get(str(source), 9) for source in bars["source"]]
    ).sort_values(
        ["session_date", "_p", "recorded_at", "run_id"], ascending=[True, True, False, True]
    )
    resolved = ranked.drop_duplicates("session_date", keep="first").set_index("session_date")
    if ex_date not in resolved.index:
        return None
    closes = pd.to_numeric(resolved["close"], errors="coerce").astype(float)
    changes = pd.to_numeric(resolved["change"], errors="coerce").astype(float)
    days = list(resolved.index)
    position = days.index(ex_date)
    earlier = closes.to_numpy()[:position]
    earlier = earlier[np.isfinite(earlier) & (earlier > 0.0)]
    previous = float(earlier[-1]) if earlier.size else math.nan
    factor, _ = _factor_from_prices(
        previous, float(closes.to_numpy()[position]), float(changes.to_numpy()[position])
    )
    return factor


def _audit_factor(frames: PanelFrames, symbol: str, ex_date: date) -> float | None:
    """:func:`_rebuild_factor` for one event, straight from the full frames."""
    return _rebuild_factor(frames.bars.loc[frames.bars["symbol"] == symbol], frames.runs, ex_date)


def factor_rebuild_mismatches(frames: PanelFrames, table: LabelFactorTable) -> list[str]:
    """T4 ②: every point-in-time factor equals its independent rebuild from raw rows."""
    by_symbol = frames.bars.groupby("symbol").indices
    empty = frames.bars.iloc[0:0]
    mismatches: list[str] = []
    for item in table.factors:
        rows = frames.bars.iloc[by_symbol[item.symbol]] if item.symbol in by_symbol else empty
        if not _same_factor(item.factor, _rebuild_factor(rows, frames.runs, item.ex_date)):
            mismatches.append(f"{item.symbol}:{item.ex_date.isoformat()}")
    return mismatches


# ---------------------------------------------------------------------------
# Weeks: one decision, one holding window, every ranked sector labelled
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShuffleArrays:
    """Per-name inputs of the label-shuffle placebo for one week (ranked sectors pooled)."""

    sizes: tuple[int, ...]
    lookback: np.ndarray
    forward: np.ndarray
    benchmark_return: float


@dataclass(frozen=True)
class Week:
    """One decision date of one phase, labelled for every ranked sector."""

    decision_date: date
    phase: int
    window: HoldingWindow
    invalid_reason: InvalidReason | None
    rank_1: str | None
    #: Every ranked sector's sample (basket = its C_g, benchmark = C_M), by code.
    labels: Mapping[str, BasketSample]
    benchmark: BasketFill | None
    shuffle: ShuffleArrays | None

    @property
    def valid(self) -> bool:
        return self.invalid_reason is None

    @property
    def rank_1_sample(self) -> BasketSample | None:
        return self.labels.get(self.rank_1) if self.rank_1 is not None else None

    def net_beats(self) -> dict[str, bool]:
        """Labelled sectors' ``excess_net > 0`` (exactly 0 is not a beat)."""
        return {
            code: sample.excess_net > 0.0
            for code, sample in self.labels.items()
            if sample.valid and sample.excess_net is not None
        }

    def gross_beats(self) -> dict[str, bool]:
        return {
            code: sample.excess_gross > 0.0
            for code, sample in self.labels.items()
            if sample.valid and sample.excess_gross is not None
        }


def _carried(calendar: Sequence[date], since: date | None, t: date) -> int:
    """Calendar sessions in ``(since, t]``; a missing snapshot counts as forever."""
    if since is None:
        return len(calendar) + 1
    return bisect_right(calendar, t) - bisect_right(calendar, since)


def _invalid_reason(
    decision: Decision,
    calendar: Sequence[date],
    definition: SectorMomentumDefinition,
    book: PriceBook,
    window: HoldingWindow,
) -> InvalidReason | None:
    t = decision.decision_date
    calc = decision.calc
    if not decision.has_bars:
        return "no_board"
    if decision.insufficient is not None:
        return "card_insufficient"
    position = bisect_left(calendar, t)
    expected_window = tuple(calendar[position - definition.lookback_days : position + 1])
    if position < definition.lookback_days or calc.window != expected_window:
        return "lookback_gap"
    snapshots = (
        calc.listing.session_date if calc.listing else None,
        calc.classification.session_date if calc.classification else None,
        decision.dividend_session,
    )
    if any(_carried(calendar, since, t) > MAX_CARRIED_SESSIONS for since in snapshots):
        return "snapshot_stale"
    if not book.has_sessions(window.sessions):
        return "bars_gap"
    if decision.rank_1 is None:
        return "no_ranked_sector"
    return None


def build_week(
    decision: Decision,
    window: HoldingWindow,
    *,
    phase: int,
    calendar: Sequence[date],
    definition: SectorMomentumDefinition,
    book: PriceBook,
    execution: BasketExecution,
    cost: float,
    keep_shuffle_arrays: bool,
) -> tuple[Week, HoldingOutcomes | None]:
    """Label every ranked sector of one decision against B_EW over one window."""
    reason = _invalid_reason(decision, calendar, definition, book, window)
    if reason in ("no_board", "bars_gap", "no_ranked_sector") or decision.rank_1 is None:
        empty = Week(
            decision_date=decision.decision_date,
            phase=phase,
            window=window,
            invalid_reason=reason,
            rank_1=decision.rank_1,
            labels=MappingProxyType({}),
            benchmark=None,
            shuffle=None,
        )
        return empty, None
    market = sorted(decision.calc.market.members)
    outcomes = holding_outcomes(book, window, market, execution)
    benchmark = fill_basket(outcomes, {symbol: 1.0 for symbol in market})
    labels: dict[str, BasketSample] = {}
    for sector in decision.ranking.ranked:
        basket = fill_basket(outcomes, {symbol: 1.0 for symbol in sector.members})
        labels[sector.sector_code] = compare_fills(window, basket, benchmark, cost=cost)
    top = labels[decision.rank_1] if decision.rank_1 is not None else None
    if reason is None and top is not None and top.status != "ok":
        reason = "all_excluded" if top.status == "all_excluded" else "empty_benchmark"
    shuffle: ShuffleArrays | None = None
    if keep_shuffle_arrays and benchmark.basket_return is not None:
        ordered = sorted(decision.ranking.ranked, key=lambda sector: sector.sector_code)
        pool = [symbol for sector in ordered for symbol in sorted(sector.members)]
        shuffle = ShuffleArrays(
            sizes=tuple(len(sector.members) for sector in ordered),
            lookback=np.array([decision.calc.member_returns[s] for s in pool], dtype="float64"),
            forward=outcomes.forward_returns(pool),
            benchmark_return=benchmark.basket_return,
        )
    week = Week(
        decision_date=decision.decision_date,
        phase=phase,
        window=window,
        invalid_reason=reason,
        rank_1=decision.rank_1,
        labels=MappingProxyType(labels),
        benchmark=benchmark,
        shuffle=shuffle,
    )
    return week, outcomes


# ---------------------------------------------------------------------------
# Rates p / q (methodology §6.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateSummary:
    """p, q and b over one set of valid weeks (p and q always from the same weeks)."""

    sample_count: int
    beat_count_net: int
    beat_count_gross: int
    p_net: float | None
    p_gross: float | None
    #: Per week, the share of labelled ranked sectors that beat; then the mean over weeks.
    q_net: float | None
    q_gross: float | None
    #: b = max(q_gross, base_rate_floor).
    b: float | None
    mean_excess_net: float | None
    mean_excess_gross: float | None
    median_excess_net: float | None


def _q(beats: Mapping[str, bool]) -> float:
    return sum(beats.values()) / len(beats)


def summarise(weeks: Sequence[Week], definition: SectorMomentumDefinition) -> RateSummary:
    valid = [week for week in weeks if week.valid]
    n = len(valid)
    if n == 0:
        return RateSummary(0, 0, 0, None, None, None, None, None, None, None, None)
    tops = [week.rank_1_sample for week in valid]
    net = [float(sample.excess_net) for sample in tops if sample and sample.excess_net is not None]
    gross = [
        float(sample.excess_gross) for sample in tops if sample and sample.excess_gross is not None
    ]
    k_net = sum(1 for value in net if value > 0.0)
    k_gross = sum(1 for value in gross if value > 0.0)
    q_net = math.fsum(_q(week.net_beats()) for week in valid) / n
    q_gross = math.fsum(_q(week.gross_beats()) for week in valid) / n
    return RateSummary(
        sample_count=n,
        beat_count_net=k_net,
        beat_count_gross=k_gross,
        p_net=k_net / n,
        p_gross=k_gross / n,
        q_net=q_net,
        q_gross=q_gross,
        b=max(q_gross, definition.gate.base_rate_floor),
        mean_excess_net=math.fsum(net) / n,
        mean_excess_gross=math.fsum(gross) / n,
        median_excess_net=float(np.median(net)),
    )


def _beats_b(summary: RateSummary) -> bool:
    """p_net > b, compared exactly (p is k/N; b is the float it was computed as)."""
    if summary.p_net is None or summary.b is None:
        return False
    return Fraction(summary.beat_count_net, summary.sample_count) > Fraction(summary.b)


# ---------------------------------------------------------------------------
# Tests on the rates (methodology §6.2)
# ---------------------------------------------------------------------------


def block_bootstrap_means(
    values: np.ndarray, *, block_length: int, draws: int, rng: np.random.Generator
) -> np.ndarray:
    """Circular block bootstrap of the mean: ``draws`` resampled means."""
    n = int(values.size)
    if n == 0:
        return np.empty(0, dtype="float64")
    blocks = math.ceil(n / block_length)
    starts = rng.integers(0, n, size=(draws, blocks))
    index = (starts[:, :, None] + np.arange(block_length)) % n
    sampled = values[index.reshape(draws, blocks * block_length)[:, :n]]
    return np.asarray(sampled.mean(axis=1), dtype="float64")


def percentile_interval(means: np.ndarray, alpha: float) -> tuple[float, float]:
    low, high = np.quantile(means, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(low), float(high)


def effective_sample_count(values: np.ndarray, boot_means: np.ndarray) -> float:
    """N_eff = N x binomial variance / block-bootstrap variance, capped at N.

    Capped at N (conservative): a negatively autocorrelated series would
    otherwise claim more information than it has samples.
    """
    n = int(values.size)
    if n == 0:
        return 0.0
    p = float(values.mean())
    boot_var = float(np.var(boot_means, ddof=1)) if boot_means.size > 1 else 0.0
    binomial_var = p * (1.0 - p) / n
    if boot_var <= 0.0 or binomial_var <= 0.0:
        return float(n)
    return min(float(n), n * binomial_var / boot_var)


def permutation_pvalue(
    week_beats: Sequence[np.ndarray], observed: float, *, draws: int, rng: np.random.Generator
) -> float:
    """Random-sector placebo: each week one labelled ranked sector at random, ``draws`` times.

    One-sided: the share of draws whose rate reaches the observed rank-1 rate,
    ``(1 + #{T* >= T}) / (1 + draws)``.
    """
    if not week_beats:
        return 1.0
    total = np.zeros(draws, dtype="float64")
    for beats in week_beats:
        picks = rng.integers(0, beats.size, size=draws)
        total += beats[picks]
    rates = total / len(week_beats)
    hits = int(np.count_nonzero(rates >= observed - 1e-12))
    return (1 + hits) / (1 + draws)


# ---------------------------------------------------------------------------
# Placebos (methodology §8.2 T8) and shift tests (T3a / T3b)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeShiftResult:
    """Δ_k = p_k - q_k for every shift k, and their median (the judged number)."""

    deltas: Mapping[int, float]
    median: float | None


def time_shift_placebo(
    chosen: Sequence[str | None],
    p_beats: Sequence[Mapping[str, bool]],
    q_beats: Sequence[Mapping[str, bool]],
    *,
    min_shift: int = PLACEBO_MIN_SHIFT,
) -> TimeShiftResult:
    """Shift the chosen-sector sequence against the labels by k weeks, cyclically.

    Week ``w`` is scored with the sector chosen in week ``(w - k) mod N``; when
    that sector has no label in week ``w`` the week is skipped for that k.
    ``p_beats`` scores the shifted choice and ``q_beats`` gives the base rate
    of the same weeks -- the normal call passes the net beats for both.
    """
    n = len(chosen)
    deltas: dict[int, float] = {}
    for k in range(min_shift, n - min_shift + 1):
        hits: list[float] = []
        bases: list[float] = []
        for week in range(n):
            code = chosen[(week - k) % n]
            if code is None or code not in p_beats[week] or not q_beats[week]:
                continue
            hits.append(1.0 if p_beats[week][code] else 0.0)
            bases.append(_q(q_beats[week]))
        if hits:
            deltas[k] = math.fsum(hits) / len(hits) - math.fsum(bases) / len(bases)
    median = float(np.median(list(deltas.values()))) if deltas else None
    return TimeShiftResult(deltas=MappingProxyType(deltas), median=median)


@dataclass(frozen=True)
class ShuffleResult:
    """Label-shuffle placebo: p_net - q_net per draw (fractions)."""

    deltas: np.ndarray
    seed: int

    @property
    def mean(self) -> float:
        return float(self.deltas.mean()) if self.deltas.size else math.nan


def label_shuffle_placebo(
    weeks: Sequence[Week], *, cost: float, draws: int, seed: int
) -> ShuffleResult:
    """Shuffle sector labels (sizes kept) among ranked-sector names, re-rank, re-score.

    Diagnostic only (methodology §8.2 ①): stock-level momentum or reversal alone
    moves it away from 0, so it never gates; it must still be produced.
    """
    rng = np.random.default_rng(seed)
    per_week_p: list[np.ndarray] = []
    per_week_q: list[np.ndarray] = []
    for week in weeks:
        arrays = week.shuffle
        if not week.valid or arrays is None or not arrays.sizes:
            continue
        n = arrays.lookback.size
        starts = np.concatenate(([0], np.cumsum(arrays.sizes)[:-1]))
        sizes = np.asarray(arrays.sizes, dtype="float64")
        perm = rng.permuted(np.tile(np.arange(n), (draws, 1)), axis=1)
        lookback = np.add.reduceat(arrays.lookback[perm], starts, axis=1) / sizes
        forward = arrays.forward[perm]
        held = ~np.isnan(forward)
        sums = np.add.reduceat(np.where(held, forward, 0.0), starts, axis=1)
        counts = np.add.reduceat(held.astype("float64"), starts, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            basket = sums / counts
        excess_net = basket - cost - arrays.benchmark_return
        labelled = counts > 0
        top = np.argmax(lookback, axis=1)
        rows = np.arange(draws)
        top_beat = np.where(labelled[rows, top], (excess_net[rows, top] > 0.0), np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            q = np.nansum(np.where(labelled, excess_net > 0.0, np.nan), axis=1) / labelled.sum(
                axis=1
            )
        per_week_p.append(top_beat.astype("float64"))
        per_week_q.append(q.astype("float64"))
    if not per_week_p:
        return ShuffleResult(deltas=np.empty(0, dtype="float64"), seed=seed)
    p = np.nanmean(np.vstack(per_week_p), axis=0)
    q = np.nanmean(np.vstack(per_week_q), axis=0)
    return ShuffleResult(deltas=np.asarray(p - q, dtype="float64"), seed=seed)


def leak_control_rate(weeks: Sequence[Week]) -> tuple[float | None, tuple[str | None, ...]]:
    """T3a: rank by the *future* close(t) -> close(t+H) return, score like the real one.

    Returns p_leak and the leaked choice per week. On any real data the leaked
    ranking must beat the real one by at least ``leak_margin``; a real ranking
    that comes close to it is suspected of leaking.
    """
    hits: list[bool] = []
    chosen: list[str | None] = []
    for week in weeks:
        if not week.valid:
            continue
        candidates = [
            (sample.basket.close_to_close_return, code)
            for code, sample in week.labels.items()
            if sample.valid
            and sample.basket is not None
            and sample.basket.close_to_close_return is not None
        ]
        if not candidates:
            chosen.append(None)
            continue
        # Highest leaked return first; ties by sector code, as in the real ranking.
        best = min(candidates, key=lambda item: (-item[0], item[1]))[1]
        chosen.append(best)
        excess = week.labels[best].excess_net
        hits.append(excess is not None and excess > 0.0)
    return (sum(hits) / len(hits) if hits else None), tuple(chosen)


# ---------------------------------------------------------------------------
# Small-sector bias monitor (methodology §2.3)
# ---------------------------------------------------------------------------

#: Size groups of |C_g(t,L)| monitored for rank-1 over-representation.
SIZE_GROUPS: Final[tuple[tuple[str, int, int | None], ...]] = (
    ("5-9", 5, 9),
    ("10-19", 10, 19),
    (">=20", 20, None),
)
#: A group is flagged when rank 1 falls in it more than this multiple of chance.
SIZE_GROUP_FLAG_RATIO: Final = 2.0


@dataclass(frozen=True)
class SizeGroupShare:
    """How often rank 1 came from one size group, against a random ranking."""

    group: str
    observed_share: float
    #: Mean over weeks of (ranked sectors in the group / ranked sectors).
    expected_share: float
    flagged: bool


def _group_of(size: int) -> str | None:
    for label, low, high in SIZE_GROUPS:
        if size >= low and (high is None or size <= high):
            return label
    return None


def size_group_monitor(weeks: Sequence[Week]) -> tuple[SizeGroupShare, ...]:
    """Rank-1 frequency per size group vs. its expected frequency under a random pick."""
    valid = [week for week in weeks if week.valid and week.rank_1 is not None]
    if not valid:
        return ()
    observed: Counter[str] = Counter()
    expected: dict[str, float] = {label: 0.0 for label, _, _ in SIZE_GROUPS}
    for week in valid:
        sizes = {
            code: len(sample.basket.requested)
            for code, sample in week.labels.items()
            if sample.basket is not None
        }
        top = _group_of(sizes.get(week.rank_1 or "", 0))
        if top is not None:
            observed[top] += 1
        groups = Counter(_group_of(size) for size in sizes.values())
        for label in expected:
            expected[label] += groups.get(label, 0) / max(len(sizes), 1)
    n = len(valid)
    out: list[SizeGroupShare] = []
    for label, _, _ in SIZE_GROUPS:
        share, chance = observed[label] / n, expected[label] / n
        out.append(
            SizeGroupShare(
                group=label,
                observed_share=share,
                expected_share=chance,
                flagged=chance > 0.0 and share > SIZE_GROUP_FLAG_RATIO * chance,
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# Segments (walk-forward test-window geometry, G5 reporting)
# ---------------------------------------------------------------------------


def segment_bounds(n_sessions: int, size: int = SEGMENT_SESSIONS) -> list[tuple[int, int]]:
    """``[start, stop)`` session bounds of consecutive ``size``-session test windows.

    ``walk_forward_splits`` with a *virtual* training block of the same size
    placed before D0 -- the parameters were frozen before the data existed, so
    nothing is fitted there -- then shifted back; a trailing partial window is
    reported too.
    """
    folds = walk_forward_splits(n_sessions + size, train_size=size, test_size=size, step=size)
    bounds = [(fold.test_start - size, fold.test_stop - size) for fold in folds]
    covered = bounds[-1][1] if bounds else 0
    if covered < n_sessions:
        bounds.append((covered, n_sessions))
    return bounds


# ---------------------------------------------------------------------------
# Candidate G1..G6 (methodology §6.3) -- never the effective gate_status
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectorStatistics:
    """Every number behind the candidate: rates, intervals, tests, placebos, subsets."""

    main: RateSummary
    m: int
    alpha_per_test: float
    effective_sample_count: float
    wilson: tuple[float, float] | None
    #: Block length -> percentile interval at level 1 - alpha/m (4 is the judged one).
    bootstrap: Mapping[int, tuple[float, float]]
    permutation_p: float | None
    halves: tuple[RateSummary, RateSummary]
    phases: tuple[RateSummary, ...]
    without_most_frequent: RateSummary
    most_frequent_sector: str | None
    last_12_months: RateSummary
    #: Segment start date -> summary over that 126-session window (reported, not gated).
    segments: tuple[tuple[date, RateSummary], ...]
    time_shift: TimeShiftResult | None
    shuffle: ShuffleResult | None
    #: (p_net - q_net) in percentage points (C-41).
    delta_real: float | None
    delta_shuffle: float | None
    #: Block-4 bootstrap interval of the weekly (beat_net - q_net_week), in points (T8-3).
    delta_real_interval: tuple[float, float] | None
    #: 2.5% / 97.5% of the shuffle deltas, in points (T8-3).
    delta_shuffle_interval: tuple[float, float] | None
    p_leak: float | None
    p_lag: float | None
    seeds: Mapping[str, int]
    #: Methodology §2.3 small-sector monitor (disclosure; not a gate).
    size_groups: tuple[SizeGroupShare, ...] = ()


def _one_year_earlier(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def compute_statistics(
    main: Sequence[Week],
    phases: Sequence[Sequence[Week]],
    *,
    definition: SectorMomentumDefinition,
    m: int,
    seed: int,
    cost: float,
    calendar: Sequence[date],
    lag_choices: Mapping[date, str | None],
) -> SectorStatistics:
    """Rates, intervals and tests of the main phase; subsets for G5 / G6."""
    rules = definition.gate
    alpha = rules.significance(m)
    seeds = {
        "bootstrap": seed,
        "permutation": seed + 1,
        "label_shuffle": seed + 2,
        "delta_bootstrap": seed + 3,
    }
    valid = [week for week in main if week.valid]
    summary = summarise(valid, definition)
    n = summary.sample_count
    tops = [week.rank_1_sample for week in valid]
    beats = np.array(
        [
            1.0 if sample is not None and (sample.excess_net or 0.0) > 0.0 else 0.0
            for sample in tops
        ],
        dtype="float64",
    )
    bootstrap: dict[int, tuple[float, float]] = {}
    n_eff = 0.0
    for length in REPORTED_BLOCK_LENGTHS:
        rng = np.random.default_rng(seeds["bootstrap"])
        means = block_bootstrap_means(
            beats, block_length=length, draws=rules.bootstrap_draws, rng=rng
        )
        if means.size:
            bootstrap[length] = percentile_interval(means, alpha)
        if length == rules.bootstrap_block_length:
            n_eff = effective_sample_count(beats, means)
    interval = wilson_interval(summary.beat_count_net, n, alpha=alpha) if n else None
    permutation = None
    if n:
        permutation = permutation_pvalue(
            [np.array([float(v) for v in week.net_beats().values()]) for week in valid],
            float(summary.p_net or 0.0),
            draws=rules.permutation_draws,
            rng=np.random.default_rng(seeds["permutation"]),
        )

    half = n // 2
    halves = (summarise(valid[:half], definition), summarise(valid[half:], definition))
    phase_summaries = tuple(summarise(weeks, definition) for weeks in phases)
    counts = Counter(week.rank_1 for week in valid if week.rank_1 is not None)
    most_frequent = min(counts, key=lambda code: (-counts[code], code)) if counts else None
    without = summarise([week for week in valid if week.rank_1 != most_frequent], definition)
    last_decision = valid[-1].decision_date if valid else None
    recent = (
        [week for week in valid if week.decision_date > _one_year_earlier(last_decision)]
        if last_decision is not None
        else []
    )
    segments: list[tuple[date, RateSummary]] = []
    if valid:
        first = bisect_left(calendar, valid[0].decision_date)
        last = bisect_right(calendar, valid[-1].decision_date)
        for start, stop in segment_bounds(last - first):
            lo, hi = calendar[first + start], calendar[first + stop - 1]
            segments.append(
                (lo, summarise([w for w in valid if lo <= w.decision_date <= hi], definition))
            )

    time_shift: TimeShiftResult | None = None
    shuffle: ShuffleResult | None = None
    delta_real = delta_shuffle = None
    delta_real_interval = delta_shuffle_interval = None
    if n:
        net_beats = [week.net_beats() for week in valid]
        time_shift = time_shift_placebo([week.rank_1 for week in valid], net_beats, net_beats)
        shuffle = label_shuffle_placebo(
            valid, cost=cost, draws=rules.label_shuffle_draws, seed=seeds["label_shuffle"]
        )
        assert summary.p_net is not None and summary.q_net is not None
        delta_real = (summary.p_net - summary.q_net) * 100.0
        if shuffle.deltas.size:
            delta_shuffle = shuffle.mean * 100.0
            low, high = np.quantile(shuffle.deltas, [0.025, 0.975])
            delta_shuffle_interval = (float(low) * 100.0, float(high) * 100.0)
        weekly = beats - np.array([_q(b) for b in net_beats], dtype="float64")
        means = block_bootstrap_means(
            weekly,
            block_length=rules.bootstrap_block_length,
            draws=rules.bootstrap_draws,
            rng=np.random.default_rng(seeds["delta_bootstrap"]),
        )
        low, high = percentile_interval(means, 0.05)
        delta_real_interval = (low * 100.0, high * 100.0)

    p_leak, _ = leak_control_rate(valid)
    lag_hits: list[bool] = []
    for week in valid:
        position = bisect_left(calendar, week.decision_date)
        previous = calendar[position - 1] if position > 0 else None
        code = lag_choices.get(previous) if previous is not None else None
        if code is not None and code in week.net_beats():
            lag_hits.append(week.net_beats()[code])
    p_lag = sum(lag_hits) / len(lag_hits) if lag_hits else None

    return SectorStatistics(
        main=summary,
        m=m,
        alpha_per_test=alpha,
        effective_sample_count=n_eff,
        wilson=(interval.low, interval.high) if interval is not None else None,
        bootstrap=MappingProxyType(bootstrap),
        permutation_p=permutation,
        halves=halves,
        phases=phase_summaries,
        without_most_frequent=without,
        most_frequent_sector=most_frequent,
        last_12_months=summarise(recent, definition),
        segments=tuple(segments),
        time_shift=time_shift,
        shuffle=shuffle,
        delta_real=delta_real,
        delta_shuffle=delta_shuffle,
        delta_real_interval=delta_real_interval,
        delta_shuffle_interval=delta_shuffle_interval,
        p_leak=p_leak,
        p_lag=p_lag,
        seeds=MappingProxyType(seeds),
        size_groups=size_group_monitor(valid),
    )


def candidate_gates(
    stats: SectorStatistics, definition: SectorMomentumDefinition
) -> tuple[GateCheckRecord, ...]:
    """G1..G6 as the evaluator sees them (methodology §6.3). A candidate, not a status.

    ``detail`` stays None: gate details reach the API, and a free-text number
    there could put p_net next to q_gross (risk VETO); the numbers live in
    :class:`SectorStatistics` for the review pack instead.
    """
    rules = definition.gate
    main = stats.main
    b = main.b
    n = main.sample_count

    def above(value: float | None) -> bool:
        return value is not None and b is not None and value > b

    g1 = n >= rules.min_samples and stats.effective_sample_count >= rules.min_effective_samples
    block = stats.bootstrap.get(rules.bootstrap_block_length)
    g2 = (
        stats.wilson is not None
        and block is not None
        and above(stats.wilson[0])
        and above(block[0])
    )
    g3 = (
        n > 0
        and b is not None
        and Fraction(main.beat_count_net, n) - Fraction(b) >= Fraction(repr(rules.min_effect))
    )
    g4 = (
        stats.permutation_p is not None
        and stats.permutation_p < stats.alpha_per_test
        and main.mean_excess_net is not None
        and main.mean_excess_net > 0.0
    )
    g5 = (
        all(_beats_b(half) for half in stats.halves)
        and bool(stats.phases)
        and all(_beats_b(phase) for phase in stats.phases)
        and _beats_b(stats.without_most_frequent)
    )
    g6 = _beats_b(stats.last_12_months)
    outcome: dict[GateName, bool] = {
        "G1": g1,
        "G2": g2,
        "G3": g3,
        "G4": g4,
        "G5": g5,
        "G6": g6,
    }
    return tuple(GateCheckRecord(gate=name, passed=passed) for name, passed in outcome.items())


# ---------------------------------------------------------------------------
# Board fingerprints (T9: board == replay)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoardRow:
    rank: int
    sector_code: str
    sector_return: float
    up_count: int
    constituent_count: int
    constituent_symbols: tuple[str, ...]
    missing_count: int
    ex_date_excluded_count: int
    corporate_action_excluded_count: int


@dataclass(frozen=True)
class BoardFingerprint:
    """The columns T9 compares between a stored board and the evaluator's replay."""

    decision_date: date
    method_version: str
    rows: tuple[BoardRow, ...]


def fingerprint_ranking(ranking: SectorRanking) -> BoardFingerprint:
    return BoardFingerprint(
        decision_date=ranking.decision_date,
        method_version=ranking.method_version,
        rows=tuple(
            BoardRow(
                rank=row.rank,
                sector_code=row.sector_code,
                sector_return=row.sector_return,
                up_count=row.up_count,
                constituent_count=row.constituent_count,
                constituent_symbols=tuple(item.symbol for item in row.constituents),
                missing_count=row.coverage.missing_count,
                ex_date_excluded_count=row.coverage.ex_date_excluded_count,
                corporate_action_excluded_count=row.coverage.corporate_action_excluded_count,
            )
            for row in ranking.ranked
        ),
    )


def same_set_violations(decision: Decision) -> list[str]:
    """C-32 / T9: R_g, 「上漲 k／n 家」 and the constituents all come from C_g(t,L)."""
    problems: list[str] = []
    calc = decision.calc
    for row in decision.ranking.ranked:
        members = calc.sector(row.sector_code).members
        if row.members != members:
            problems.append(f"{row.sector_code}:members")
        if row.constituent_count != len(members):
            problems.append(f"{row.sector_code}:constituent_count")
        if row.up_count != up_count(calc.member_returns, members):
            problems.append(f"{row.sector_code}:up_count")
        if row.sector_return != mean_return(calc.member_returns, members):
            problems.append(f"{row.sector_code}:sector_return")
        if not {item.symbol for item in row.constituents} <= members:
            problems.append(f"{row.sector_code}:constituents")
    return problems


# ---------------------------------------------------------------------------
# Runtime self-checks (methodology §8, ADR-0012 D-8 table)
# ---------------------------------------------------------------------------


def _canonical(value: object) -> object:
    """Bit-exact, order-independent rendering of decision outputs (T1)."""
    if isinstance(value, float):
        return ("f", value.hex())
    if isinstance(value, np.floating):
        return ("f", float(value).hex())
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _canonical(model_dump())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__name__,
            tuple(
                (field.name, _canonical(getattr(value, field.name)))
                for field in dataclasses.fields(value)
            ),
        )
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _canonical(item)) for key, item in value.items()))
    if isinstance(value, frozenset | set):
        return ("set", tuple(sorted(repr(_canonical(item)) for item in value)))
    if isinstance(value, list | tuple):
        return tuple(_canonical(item) for item in value)
    return value


def decision_fingerprint(decision: Decision) -> object:
    return _canonical((decision.calc, decision.ranking, decision.dividend_session))


def perturb_future(frames: PanelFrames, t: date, rng: np.random.Generator) -> PanelFrames:
    """Replace every row recorded after ``cutoff(t)`` with noise, and add noise rows for t.

    Prices, symbols, sessions, sector codes, ex-dates and run statuses of the
    future rows are all scrambled towards things that *would* matter if they
    leaked (sessions on or before t, symbols that exist, ``ok`` runs).
    """
    cut = cutoff(t)
    out: dict[str, pd.DataFrame] = {}
    symbols = np.array(sorted(set(frames.bars["symbol"])) or ["0000"], dtype=object)
    codes = np.array(sorted(set(frames.classification["sector_code"])) or ["00"], dtype=object)
    recent = np.array([t - timedelta(days=k) for k in range(31)], dtype=object)
    for name in ("bars", "listing", "classification", "ex_dividend", "runs"):
        frame: pd.DataFrame = getattr(frames, name).copy()
        future = (frame["recorded_at"] > cut).to_numpy()
        count = int(future.sum())
        if count:
            rows = frame.index[future]
            frame.loc[rows, "session_date"] = pd.Series(
                recent[rng.integers(0, 31, count)], index=rows, dtype=object
            )
            if "symbol" in frame.columns:
                frame.loc[rows, "symbol"] = symbols[rng.integers(0, symbols.size, count)]
            if name == "bars":
                for column in ("open", "high", "low", "close", "traded_value"):
                    frame.loc[rows, column] = rng.uniform(1.0, 1e6, count)
                frame.loc[rows, "source"] = "twse_snapshot"
            if name == "classification":
                frame.loc[rows, "sector_code"] = codes[rng.integers(0, codes.size, count)]
            if name == "ex_dividend":
                frame.loc[rows, "ex_date"] = pd.Series(
                    recent[rng.integers(0, 6, count)], index=rows, dtype=object
                )
            if name == "runs":
                frame.loc[rows, "status"] = "ok"
        out[name] = frame
    late = cut + pd.Timedelta(seconds=1)
    noise_run = pd.DataFrame(
        [
            {
                "run_id": "perturb-noise-run",
                "kind": "bars",
                "session_date": t,
                "recorded_at": late,
                "source": "twse_snapshot",
                "status": "ok",
                "row_count": 1,
                "expected_count": 1,
            }
        ]
    )
    noise_bar = pd.DataFrame(
        [
            {
                "run_id": "perturb-noise-run",
                "session_date": t,
                "recorded_at": late,
                "source": "twse_snapshot",
                "symbol": str(symbols[int(rng.integers(0, symbols.size))]),
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "shares": 1,
                "traded_value": 1.0,
                "change": 0.0,
            }
        ]
    )
    out["runs"] = pd.concat([out["runs"], noise_run], ignore_index=True)
    out["bars"] = pd.concat([out["bars"], noise_bar], ignore_index=True)
    return PanelFrames(**out)


def future_perturbation_check(
    panel: MarketPanel,
    definition: SectorMomentumDefinition,
    dates: Sequence[date],
    *,
    seed: int,
) -> SelfcheckRecord:
    """T1 runtime: future noise must leave the decision of each sampled date bit-identical."""
    rng = np.random.default_rng(seed)
    changed: list[str] = []
    for t in dates:
        clean = decision_fingerprint(decide(panel.as_of(t), definition))
        noisy_panel = MarketPanel(perturb_future(panel.frames, t, rng))
        noisy = decision_fingerprint(decide(noisy_panel.as_of(t), definition))
        if noisy != clean:
            changed.append(t.isoformat())
    return SelfcheckRecord(
        check_name=T1,
        status="fail" if changed or not dates else "pass",
        seed=seed,
        value=float(len(dates)),
        detail=("changed:" + ",".join(changed)) if changed else None,
    )


@dataclass
class _Audit:
    """Streaming per-decision audits for T4 ①, T5, T6, T7 and T9."""

    frames: PanelFrames
    boards: Mapping[date, BoardFingerprint] | None
    t4_untraceable: list[str] = dataclasses.field(default_factory=list)
    t4_events_in_period: int = 0
    t5_problems: list[str] = dataclasses.field(default_factory=list)
    t5_events: int = 0
    t6_problems: list[str] = dataclasses.field(default_factory=list)
    t6_events: int = 0
    t7_problems: list[str] = dataclasses.field(default_factory=list)
    t9_problems: list[str] = dataclasses.field(default_factory=list)
    t9_compared: int = 0

    def __post_init__(self) -> None:
        runs = self.frames.runs
        self._ok = runs.loc[runs["status"] == "ok"].sort_values(
            ["session_date", "recorded_at", "run_id"], kind="mergesort"
        )
        self._listing_rows = self.frames.listing.groupby("run_id").indices
        self._class_rows = self.frames.classification.groupby("run_id").indices
        self._dividend = self.frames.ex_dividend
        self._delisted, self._reclassified = self._events()

    def _events(self) -> tuple[dict[str, tuple[date, date]], set[str]]:
        """Delistings (a name leaves the listing) and reclassifications in the panel."""
        listing = self.frames.listing.loc[
            self.frames.listing["run_id"].isin(
                set(self._ok.loc[self._ok["kind"] == "listing", "run_id"])
            )
        ]
        delisted: dict[str, tuple[date, date]] = {}
        if not listing.empty:
            final = listing["session_date"].max()
            seen = listing.groupby("symbol")["session_date"].agg(["min", "max"])
            delisted = {
                str(symbol): (row["min"], row["max"])
                for symbol, row in seen.iterrows()
                if row["max"] < final
            }
        classes = self.frames.classification.loc[
            self.frames.classification["run_id"].isin(
                set(self._ok.loc[self._ok["kind"] == "classification", "run_id"])
            )
        ]
        codes = classes.groupby("symbol")["sector_code"].nunique()
        return delisted, {str(s) for s, n in codes.items() if n > 1}

    def _latest_ok(self, kind: str, t: date) -> str | None:
        cut = cutoff(t)
        rows = self._ok.loc[
            (self._ok["kind"] == kind)
            & (self._ok["session_date"] <= t)
            & (self._ok["recorded_at"] <= cut)
        ]
        return str(rows["run_id"].iloc[-1]) if not rows.empty else None

    def decision(self, decision: Decision) -> None:
        t = decision.decision_date
        calc = decision.calc
        cut = cutoff(t)
        # T4 ①: every ex-date exclusion traces back to an announcement visible at cutoff(t).
        if calc.window:
            ok_dividend = set(
                self._ok.loc[
                    (self._ok["kind"] == "dividend_announce")
                    & (self._ok["session_date"] <= t)
                    & (self._ok["recorded_at"] <= cut),
                    "run_id",
                ]
            )
            rows = self._dividend
            visible = rows.loc[
                rows["run_id"].isin(ok_dividend)
                & (rows["recorded_at"] <= cut)
                & (rows["session_date"] <= t)
                & (rows["ex_date"] > calc.window[0])
                & (rows["ex_date"] <= t)
            ]
            traceable = set(visible["symbol"])
            self.t4_events_in_period += len(calc.market.ex_date_excluded)
            for symbol in sorted(calc.market.ex_date_excluded - traceable):
                self.t4_untraceable.append(f"{t.isoformat()}:{symbol}")
        # T5: the universe is the listing snapshot in force at cutoff(t), not the latest one.
        listing_run = self._latest_ok("listing", t)
        used_listing = calc.listing.run_id if calc.listing else None
        if used_listing != listing_run:
            self.t5_problems.append(f"{t.isoformat()}:listing_run")
        listed: set[str] = set()
        if listing_run is not None:
            listed = set(self.frames.listing.iloc[self._listing_rows[listing_run]]["symbol"])
        if decision.listed != listed:
            self.t5_problems.append(f"{t.isoformat()}:listing_content")
        if not calc.market.expected <= listed:
            self.t5_problems.append(f"{t.isoformat()}:outside_listing")
        # A name that later leaves the listing is in every snapshot before it left.
        snapshot_session = calc.listing.session_date if calc.listing else None
        for symbol, (first_seen, last_seen) in self._delisted.items():
            if snapshot_session is not None and first_seen <= snapshot_session <= last_seen:
                self.t5_events += 1
                if symbol not in decision.listed:
                    self.t5_problems.append(f"{t.isoformat()}:{symbol}:dropped_before_delisting")
        # T6: sector membership is the classification snapshot in force at cutoff(t).
        class_run = self._latest_ok("classification", t)
        used_class = calc.classification.run_id if calc.classification else None
        if used_class != class_run:
            self.t6_problems.append(f"{t.isoformat()}:classification_run")
        if class_run is not None:
            rows = self.frames.classification.iloc[self._class_rows[class_run]]
            code_of = {str(r.symbol): str(r.sector_code) for r in rows.itertuples(index=False)}
            for sector in calc.sectors:
                for symbol in sector.expected:
                    if code_of.get(symbol) != sector.sector_code:
                        self.t6_problems.append(f"{t.isoformat()}:{symbol}")
            self.t6_events += sum(1 for symbol in self._reclassified if symbol in code_of)
        # T9: same set, and the stored board equals the replay.
        self.t9_problems.extend(f"{t.isoformat()}:{p}" for p in same_set_violations(decision))
        if self.boards is not None and t in self.boards:
            self.t9_compared += 1
            if self.boards[t] != fingerprint_ranking(decision.ranking):
                self.t9_problems.append(f"{t.isoformat()}:board_differs")

    def week(self, week: Week, decision: Decision, cost: float) -> None:
        """T7: B_EW is C_M(t,L), equally weighted, and never charged."""
        if not week.valid or week.benchmark is None:
            return
        t = week.decision_date.isoformat()
        if set(week.benchmark.requested) != set(decision.calc.market.members):
            self.t7_problems.append(f"{t}:benchmark_members")
        weights = set(week.benchmark.requested.values())
        if len(weights) > 1 and max(weights) - min(weights) > 1e-15:
            self.t7_problems.append(f"{t}:benchmark_weights")
        for code, sample in week.labels.items():
            if sample.excess_gross is None or sample.excess_net is None:
                continue
            if not math.isclose(
                sample.excess_gross - sample.excess_net, cost, rel_tol=0.0, abs_tol=1e-12
            ):
                self.t7_problems.append(f"{t}:{code}:cost")


def _status(problems: Sequence[str], events: int, *, vacuous_allowed: bool) -> SelfcheckStatus:
    if problems:
        return "fail"
    if vacuous_allowed and events == 0:
        return "vacuous"
    return "pass"


# ---------------------------------------------------------------------------
# Data quality (NE-6)
# ---------------------------------------------------------------------------


def data_quality_problems(panel: MarketPanel, decisions_with_violations: int) -> list[str]:
    """Future-dated rows, duplicates, thin ok bars runs, broken invariants (NE-6)."""
    frames = panel.frames
    problems: list[str] = []
    for name in ("bars", "listing", "classification", "ex_dividend"):
        frame: pd.DataFrame = getattr(frames, name)
        if frame.empty:
            continue
        local = frame["recorded_at"].dt.tz_convert("Asia/Taipei").dt.date
        if bool((frame["session_date"] > local).any()):
            problems.append(f"{name}:future_dated")
        key = ["run_id", "symbol"] + (["ex_date"] if name == "ex_dividend" else [])
        if bool(frame.duplicated(key).any()):
            problems.append(f"{name}:duplicates")
    if bool(frames.runs["run_id"].duplicated().any()):
        problems.append("runs:duplicates")
    ok_bars = frames.runs.loc[(frames.runs["kind"] == "bars") & (frames.runs["status"] == "ok")]
    expected = pd.to_numeric(ok_bars["expected_count"], errors="coerce")
    rows = pd.to_numeric(ok_bars["row_count"], errors="coerce")
    thin = (expected > 0) & (rows / expected < 0.98)
    if bool(thin.any()):
        problems.append("bars:ok_run_below_coverage")
    if decisions_with_violations:
        problems.append("ranking:constituent_invariant_violated")
    return problems


# ---------------------------------------------------------------------------
# The evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectorEvaluation:
    """Everything one evaluation produced; :func:`to_stats_record` makes the stored row."""

    method_version: str
    regime: Regime
    data_regime: DataRegime
    start: date
    calendar_end: date | None
    main: tuple[Week, ...]
    phases: tuple[tuple[Week, ...], ...]
    statistics: SectorStatistics
    gate_checks: tuple[GateCheckRecord, ...]
    selfchecks: tuple[SelfcheckRecord, ...]
    pit_gaps: tuple[PitGap, ...]
    data_quality_problems: tuple[str, ...]
    invalid_counts: Mapping[str, int]
    #: The strategy-layer report of the main phase (rank-1 basket vs B_EW).
    basket_result: BasketResult
    round_trip_cost: float
    cost_verified_on: str | None
    source_run_ids: tuple[str, ...]
    data_source: str | None

    @property
    def sample_count(self) -> int:
        return self.statistics.main.sample_count


def build_decisions_and_weeks(
    view_for: Callable[[date], PointInTimePanel],
    *,
    definition: SectorMomentumDefinition,
    book: PriceBook,
    calendar: Sequence[date],
    start: date,
    execution: BasketExecution,
    cost: float,
    on_decision: Callable[[Decision, Week | None], None] | None = None,
) -> tuple[list[list[Week]], dict[date, str | None], dict[date, HoldingOutcomes]]:
    """Every calendar session from ``start`` decided once; H phases of weeks.

    Returns the weeks per phase (phase 0 = main), the rank-1 choice of every
    decided session (for T3b) and the holding outcomes of the main phase (for
    the strategy report). ``on_decision`` receives each decision for streaming
    audits, so no decision is held in memory longer than needed.
    """
    holding = definition.holding_days
    first = bisect_left(calendar, start)
    weeks: list[list[Week]] = [[] for _ in range(holding)]
    choices: dict[date, str | None] = {}
    main_outcomes: dict[date, HoldingOutcomes] = {}
    for position in range(first, len(calendar) - holding):
        t = calendar[position]
        decision = decide(view_for(t), definition)
        choices[t] = decision.rank_1 if decision.has_bars else None
        phase = (position - first) % holding
        sessions = tuple(calendar[position + 1 : position + holding + 1])
        window = HoldingWindow(
            decision_date=t, entry_date=sessions[0], exit_date=sessions[-1], sessions=sessions
        )
        week, outcomes = build_week(
            decision,
            window,
            phase=phase,
            calendar=calendar,
            definition=definition,
            book=book,
            execution=execution,
            cost=cost,
            keep_shuffle_arrays=phase == 0,
        )
        if phase == 0 and outcomes is not None and week.valid:
            main_outcomes[t] = outcomes
        if on_decision is not None:
            on_decision(decision, week)
        if phase != 0:
            # Only the main phase needs per-name fills (leak control, size monitor,
            # strategy report); the other phases keep their excess returns only.
            week = _lean(week)
        weeks[phase].append(week)
    return weeks, choices, main_outcomes


def _lean(week: Week) -> Week:
    labels = {
        code: dataclasses.replace(sample, basket=None, benchmark=None)
        for code, sample in week.labels.items()
    }
    return dataclasses.replace(week, labels=MappingProxyType(labels), benchmark=None, shuffle=None)


@dataclass(frozen=True)
class EngineRun:
    """What :func:`evaluate_views` produced (shared by the judged and the research path)."""

    weeks: tuple[tuple[Week, ...], ...]
    statistics: SectorStatistics
    basket_result: BasketResult
    round_trip_cost: float
    invalid_counts: Mapping[str, int]
    regime: Regime
    invariant_violations: int
    calendar: tuple[date, ...]


def evaluate_views(
    view_for: Callable[[date], PointInTimePanel],
    panel: MarketPanel,
    definition: SectorMomentumDefinition,
    *,
    cost_model: CostModel,
    start: date,
    m: int,
    seed: int,
    calendar: Sequence[date] | None = None,
    adjustment: LabelFactorTable | None = None,
    audit: _Audit | None = None,
) -> EngineRun:
    """The shared engine room of :func:`evaluate` and the biased research study.

    ``view_for`` builds the view each decision reads. The judged path passes
    ``panel.as_of``; only ``app.research.sector_biased`` passes its hindsight
    factory, and the regime it produces is recorded on every decision, so a
    hindsight run can never be turned into a statistics row (:func:`to_stats_record`
    and the repository both refuse it).
    """
    book = PriceBook.from_panel(panel)
    days = tuple(sorted(set(calendar))) if calendar is not None else book.sessions
    execution = BasketExecution(
        open_limit_up_factor=definition.open_limit_up_factor,
        adjustment=adjustment.adjustment if adjustment is not None else None,
    )
    cost = round_trip_cost(
        cost_model, market=execution.market, instrument_type=execution.instrument_type
    )
    regimes: set[Regime] = set()
    violations = 0

    def observe(decision: Decision, week: Week | None) -> None:
        nonlocal violations
        regimes.add(decision.regime)
        violations += 1 if decision.ranking.invariant_violations else 0
        if audit is not None:
            audit.decision(decision)
            if week is not None:
                audit.week(week, decision, cost)

    weeks, choices, outcomes = build_decisions_and_weeks(
        view_for,
        definition=definition,
        book=book,
        calendar=days,
        start=start,
        execution=execution,
        cost=cost,
        on_decision=observe,
    )
    statistics = compute_statistics(
        weeks[0],
        weeks,
        definition=definition,
        m=m,
        seed=seed,
        cost=cost,
        calendar=days,
        lag_choices=choices,
    )
    main_valid = [week for week in weeks[0] if week.valid]
    samples = [week.rank_1_sample for week in main_valid]
    result = assemble_result(
        book,
        [sample for sample in samples if sample is not None],
        outcomes,
        calendar=days,
        cost_model=cost_model,
        execution=execution,
    )
    invalid = Counter(week.invalid_reason for week in weeks[0] if week.invalid_reason is not None)
    if len(regimes) > 1:
        raise ValueError("an evaluation must not mix point-in-time and hindsight views")
    regime: Regime = regimes.pop() if regimes else "pit"
    return EngineRun(
        weeks=tuple(tuple(phase) for phase in weeks),
        statistics=statistics,
        basket_result=result,
        round_trip_cost=cost,
        invalid_counts=MappingProxyType({str(key): count for key, count in invalid.items()}),
        regime=regime,
        invariant_violations=violations,
        calendar=days,
    )


def leak_control_status(
    p_real: float | None, p_leak: float | None, n: int, definition: SectorMomentumDefinition
) -> SelfcheckStatus:
    """T3a: pass iff ``p_leak - p_real >= leak_margin`` (equivalently ``p_real <= p_leak - δ``).

    Below N=30 the check is ``skipped_insufficient_n`` (C-36); a missing number
    at or above it is a failure, never a skip.
    """
    if n < definition.gate.skip_allowed_below_samples:
        return "skipped_insufficient_n"
    if p_real is None or p_leak is None:
        return "fail"
    return "pass" if p_leak - p_real >= definition.gate.leak_margin else "fail"


def time_shift_status(
    median: float | None, n: int, definition: SectorMomentumDefinition
) -> SelfcheckStatus:
    """T8 (judged half): pass iff |median Δ_k| < 2.5pp; skipped only below N=30."""
    if n < definition.gate.skip_allowed_below_samples:
        return "skipped_insufficient_n"
    if median is None:
        return "fail"
    return "pass" if abs(median) < definition.gate.placebo_shift_tolerance else "fail"


def evaluate(
    panel: MarketPanel,
    definition: SectorMomentumDefinition,
    *,
    cost_model: CostModel,
    start: date,
    m: int,
    seed: int,
    pit_status: PitStatus,
    de5_verified_on: date | None,
    calendar: Sequence[date] | None = None,
    boards: Mapping[date, BoardFingerprint] | None = None,
) -> SectorEvaluation:
    """Evaluate the forward point-in-time segment from ``start`` (D0) on ``panel``.

    Every decision reads ``panel.as_of(t)`` only. Labels read the results side
    (:class:`PriceBook`) with point-in-time restoration factors. ``boards``
    are the stored boards (by decision date) the services layer projected with
    :func:`fingerprint_ranking`'s shape; without them T9 cannot compare and
    fails closed.
    """
    factors = pit_label_factors(panel)
    audit = _Audit(frames=panel.frames, boards=boards)
    run = evaluate_views(
        panel.as_of,
        panel,
        definition,
        cost_model=cost_model,
        start=start,
        m=m,
        seed=seed,
        calendar=calendar,
        adjustment=factors,
        audit=audit,
    )
    if run.regime != "pit":  # pragma: no cover - as_of only builds pit views
        raise ValueError("the judged evaluation must read point-in-time views only")
    weeks, statistics, days = run.weeks, run.statistics, run.calendar
    rules = definition.gate
    n = statistics.main.sample_count
    main = weeks[0]

    selfchecks: list[SelfcheckRecord] = []
    decided = [week.decision_date for phase in weeks for week in phase]
    sample_rng = random.Random(seed)
    t1_dates = sorted(sample_rng.sample(decided, min(rules.lookahead_sample_dates, len(decided))))
    selfchecks.append(future_perturbation_check(panel, definition, t1_dates, seed=seed))

    t3a = leak_control_status(statistics.main.p_net, statistics.p_leak, n, definition)
    selfchecks.append(
        SelfcheckRecord(
            check_name=T3A,
            status=t3a,
            value=statistics.p_leak,
            detail=f"leak_margin={rules.leak_margin}",
        )
    )
    selfchecks.append(
        SelfcheckRecord(
            check_name=T3B,
            status="pass" if n == 0 or statistics.p_lag is not None else "fail",
            value=statistics.p_lag,
        )
    )

    t4_problems = audit.t4_untraceable + factor_rebuild_mismatches(panel.frames, factors)
    period_events = sum(
        1
        for item in factors.factors
        if main and main[0].decision_date < item.ex_date <= main[-1].window.exit_date
    )
    selfchecks.append(
        SelfcheckRecord(
            check_name=T4,
            status=_status(
                t4_problems, period_events + audit.t4_events_in_period, vacuous_allowed=True
            ),
            value=float(period_events),
            detail=";".join(t4_problems[:20]) or None,
        )
    )
    selfchecks.append(
        SelfcheckRecord(
            check_name=T5,
            status=_status(audit.t5_problems, audit.t5_events, vacuous_allowed=True),
            value=float(audit.t5_events),
            detail=";".join(audit.t5_problems[:20]) or None,
        )
    )
    selfchecks.append(
        SelfcheckRecord(
            check_name=T6,
            status=_status(audit.t6_problems, audit.t6_events, vacuous_allowed=True),
            value=float(audit.t6_events),
            detail=";".join(audit.t6_problems[:20]) or None,
        )
    )
    selfchecks.append(
        SelfcheckRecord(
            check_name=T7,
            status=_status(audit.t7_problems, 1, vacuous_allowed=False),
            detail=";".join(audit.t7_problems[:20]) or None,
        )
    )
    placebo = statistics.time_shift
    t8 = time_shift_status(placebo.median if placebo is not None else None, n, definition)
    selfchecks.append(
        SelfcheckRecord(
            check_name=T8,
            status=t8,
            value=placebo.median if placebo is not None else None,
        )
    )
    produced = statistics.delta_real is not None and statistics.delta_shuffle is not None
    # N = 0: nothing to shuffle -- a skip (C-36 state semantics), never a pass. With
    # any sample the two deltas must exist, else T8 fails (C-36, C-41).
    shuffle_status: SelfcheckStatus = (
        "pass" if produced else ("skipped_insufficient_n" if n == 0 else "fail")
    )
    selfchecks.append(
        SelfcheckRecord(
            check_name=T8_SHUFFLE,
            status=shuffle_status,
            seed=statistics.seeds["label_shuffle"],
            value=statistics.delta_shuffle,
        )
    )
    t9_problems = list(audit.t9_problems)
    if boards is None or audit.t9_compared == 0:
        t9_problems.append("no_board_compared")
    selfchecks.append(
        SelfcheckRecord(
            check_name=T9,
            status="fail" if t9_problems else "pass",
            value=float(audit.t9_compared),
            detail=";".join(t9_problems[:20]) or None,
        )
    )

    window = EvaluationWindow(
        decision_dates=tuple(week.decision_date for week in main),
        trading_days=days,
    )
    gaps = tuple(pit_gaps(pit_status, de5_verified_on, window))
    frames = panel.frames
    ok_runs = frames.runs.loc[frames.runs["status"] == "ok", "run_id"]
    last_valid = [week for week in main if week.valid]
    view_source = (
        panel.as_of(last_valid[-1].decision_date).bars_source_on(last_valid[-1].decision_date)
        if last_valid
        else None
    )
    return SectorEvaluation(
        method_version=definition.method_version,
        regime=run.regime,
        data_regime="forward_pit",
        start=start,
        calendar_end=days[-1] if days else None,
        main=tuple(main),
        phases=tuple(tuple(phase) for phase in weeks),
        statistics=statistics,
        gate_checks=candidate_gates(statistics, definition),
        selfchecks=tuple(selfchecks),
        pit_gaps=gaps,
        data_quality_problems=tuple(data_quality_problems(panel, run.invariant_violations)),
        invalid_counts=run.invalid_counts,
        basket_result=run.basket_result,
        round_trip_cost=run.round_trip_cost,
        cost_verified_on=cost_model.verified_on,
        source_run_ids=tuple(sorted(set(str(run_id) for run_id in ok_runs))),
        data_source=view_source,
    )


def _same_factor(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=0.0)


def selfchecks_passed(
    selfchecks: Sequence[SelfcheckRecord], sample_count: int, definition: SectorMomentumDefinition
) -> bool:
    """C-36: every runtime item passed; skip only for T3a / T8 below N=30; vacuous only T4-T6."""
    names = {check.check_name for check in selfchecks}
    if names != set(SELFCHECK_ORDER):
        return False
    for check in selfchecks:
        if check.status == "pass":
            continue
        if check.status == "vacuous" and check.check_name in VACUOUS_ALLOWED:
            continue
        if (
            check.status == "skipped_insufficient_n"
            and check.check_name in SKIPPABLE_CHECKS
            and sample_count < definition.gate.skip_allowed_below_samples
        ):
            continue
        return False
    return True


def to_stats_record(
    evaluation: SectorEvaluation,
    definition: SectorMomentumDefinition,
    *,
    run_id: str,
    computed_at: datetime,
    recompute_session: date,
    running_commit: str,
    ci_attestation_ok: bool,
) -> StatsRecord | None:
    """The ``sector_rank_stats`` row of this evaluation; None when there is no sample.

    Refuses anything but point-in-time forward data before the repository has
    to (D-14 defence in depth). ``ci_attestation_ok`` is the services layer's
    NE-7 CI half (clean tree, ``running_commit == ci_passed_commit``, suite hash).
    """
    if evaluation.regime != "pit" or evaluation.data_regime != "forward_pit":
        raise ValueError("only point-in-time forward evaluations become statistics rows")
    if evaluation.method_version != definition.method_version:
        raise ValueError("evaluation and definition disagree on method_version")
    stats = evaluation.statistics
    main = stats.main
    n = main.sample_count
    if n == 0 or stats.wilson is None:
        return None
    block = stats.bootstrap[definition.gate.bootstrap_block_length]
    valid = [week for week in evaluation.main if week.valid]
    assert main.p_net is not None and main.q_net is not None and main.q_gross is not None
    return StatsRecord(
        run_id=run_id,
        method_version=evaluation.method_version,
        regime="pit",
        data_regime="forward_pit",
        source_run_ids=evaluation.source_run_ids,
        m_at_evaluation=stats.m,
        sample_count=n,
        effective_sample_count=stats.effective_sample_count,
        beat_count_net=main.beat_count_net,
        beat_count_gross=main.beat_count_gross,
        base_rate_net=main.q_net,
        base_rate_gross=main.q_gross,
        ci_low_net=stats.wilson[0],
        ci_high_net=stats.wilson[1],
        bootstrap_low_net=block[0],
        bootstrap_high_net=block[1],
        delta_real=stats.delta_real,
        delta_shuffle=stats.delta_shuffle,
        sample_start=valid[0].decision_date,
        sample_end=valid[-1].decision_date,
        stats_as_of=valid[-1].window.exit_date,
        computed_at=computed_at,
        recompute_session=recompute_session,
        running_commit=running_commit,
        selfcheck_passed=ci_attestation_ok
        and selfchecks_passed(evaluation.selfchecks, n, definition),
        data_quality_passed=not evaluation.data_quality_problems,
        pit_history_missing=bool(evaluation.pit_gaps),
        gate_checks=evaluation.gate_checks,
        selfchecks=evaluation.selfchecks,
    )


def fee_verified_on(cost_model: CostModel) -> date | None:
    """``CostModel.verified_on`` as a date for :class:`app.sectors.gate.GateInputs` (NE-3)."""
    if cost_model.verified_on is None:
        return None
    return date.fromisoformat(cost_model.verified_on)
