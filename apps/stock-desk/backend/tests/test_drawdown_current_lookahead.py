"""Look-ahead detection for ``drawdown.current`` (rule set 1.1.0, CEO D1).

``current`` is what the two drawdown rules now read, so a future close leaking
into it would turn the rule hits into hindsight. Three checks, per the
backtest protocol:

1. Causality: the value published for day ``k`` (from bars ``0..k``) equals the
   running-peak path at ``k`` -- and a deliberately non-causal definition
   (dividing by the *whole* series' high) differs on the same data, so the test
   has teeth.
2. Shift: dropping the newest bar yields exactly the previous day's value, and
   the one-bar-shifted feature series is not identical to the unshifted one.
3. Future high: appending a much higher close after day ``T`` changes no
   value, and no drawdown rule hit, on any day ``<= T``.
"""

from __future__ import annotations

import random

from app.advice.context import build_context
from app.advice.engine import evaluate_rule
from app.advice.limits import PortfolioContext
from app.advice.loader import load_default_rules
from app.data.interface import PriceBar
from app.signals import risk as R
from app.signals.service import compute_signals
from tests.signals_helpers import bars_from_closes

_DRAWDOWN_RULES = ("drawdown_protection", "deep_drawdown_stop")


def _walk(n: int = 160, *, seed: int = 7) -> list[float]:
    """A deterministic walk with a rise, a > 30% fall and a partial recovery."""
    rnd = random.Random(seed)
    closes = [100.0]
    for i in range(1, n):
        drift = 0.006 if i < 60 else (-0.012 if i < 100 else 0.004)
        closes.append(round(closes[-1] * (1.0 + drift + rnd.gauss(0.0, 0.01)), 4))
    return closes


def _current(bars: list[PriceBar]) -> float:
    value = R.drawdown(bars).current
    assert value is not None
    return value


def test_current_for_each_day_is_causal() -> None:
    closes = _walk()
    bars = bars_from_closes(closes)
    path = R.drawdown_series(closes)
    overall_high = max(closes)
    leaks = 0
    for k in range(1, len(bars)):
        published = _current(bars[: k + 1])
        assert published == path[k], f"day {k}: {published} != causal {path[k]}"
        # A look-ahead definition would divide by the whole series' high.
        if closes[k] / overall_high - 1.0 != published:
            leaks += 1
    # The non-causal variant must disagree on a meaningful share of days,
    # otherwise this fixture could not tell the two apart.
    assert leaks > len(bars) // 4


def test_dropping_the_newest_bar_gives_the_previous_days_value() -> None:
    closes = _walk()
    bars = bars_from_closes(closes)
    path = R.drawdown_series(closes)
    for end in range(3, len(bars) + 1):
        assert _current(bars[: end - 1]) == path[end - 2]
    feature = [_current(bars[: k + 1]) for k in range(1, len(bars))]
    shifted = [feature[0], *feature[:-1]]
    assert feature != shifted


def test_a_future_high_changes_nothing_before_it() -> None:
    closes = _walk()
    cutoff = len(closes)  # days 0..cutoff-1 are "the past"
    future = [closes[-1] * 1.5, closes[-1] * 1.8]
    base = bars_from_closes(closes)
    extended = bars_from_closes(closes + future)
    assert [b.date for b in extended[:cutoff]] == [b.date for b in base]

    # Discriminating check: the per-day path computed over the *whole* extended
    # series (future highs included) must agree, on every past day, with the
    # value a caller gets from the truncated bars. A non-causal path (e.g. one
    # normalised by the global maximum) would differ once the future highs are
    # in the input.
    extended_path = R.drawdown_series([float(b.close) for b in extended])
    rules = {rule.id: rule for rule in load_default_rules().rules}
    for k in range(1, cutoff):
        before = R.drawdown(base[: k + 1])
        assert before.current is not None
        assert before.current == extended_path[k]
        # Guard only (same input both sides): truncating the extended bars must
        # be indistinguishable from the base bars.
        after = R.drawdown(extended[: k + 1])
        assert before.current == after.current
        assert before.current_peak_date == after.current_peak_date

    # Rule level: the hits on days <= cutoff do not move either. Checked on a
    # stride to keep the run short; every indicator is recomputed per day.
    for k in range(60, cutoff, 7):
        hits = []
        for bars in (base[: k + 1], extended[: k + 1]):
            signals = compute_signals("TEST", bars)
            context = build_context(
                signals, PortfolioContext(symbol="TEST", close=float(bars[-1].close))
            )
            hits.append(
                tuple(rid for rid in _DRAWDOWN_RULES if evaluate_rule(rules[rid], context).matched)
            )
        assert hits[0] == hits[1]

    # Sanity: the appended future high does register once it is in the window.
    assert _current(extended) == 0.0
    assert _current(base) < 0.0
