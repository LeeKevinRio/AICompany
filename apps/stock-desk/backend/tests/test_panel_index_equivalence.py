"""The indexed ``MarketPanel.as_of`` equals the reference definition, bit for bit (T-5 spirit).

``app.data.panel`` keeps two answers to "what may a decision on t read":

* the reference -- :func:`_visible` then :func:`_resolve_bars`, one filter
  and one sort per view, exactly as ADR-0012 D-2 words the rules;
* the path every caller uses -- :class:`_PanelIndex`, which sorts the history
  once and slices it per view (a pure speed-up; no decision is cached).

This file builds both views for every session of a hand-built market (and
every other session of the evaluator's synthetic market) exercising each rule
(late corrections recorded the next morning, a backup source competing with
the primary on the same session, failed and partial runs, carried-forward
snapshots, a delisting, a reclassification, ex-dividend announcements) and
demands identical output from every accessor, the resolved bar frame itself,
and the decision the sector core derives from the view -- compared through
``sector_eval.decision_fingerprint`` (floats by ``float.hex``). The hindsight
regime is held to the same standard.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from typing import cast

import pandas as pd
import pytest

from app.backtest import sector_eval
from app.data.panel import (
    _VIEW_KEY,
    BAR_FIELDS,
    MarketPanel,
    PointInTimePanel,
    _hindsight_view,
    _visible,
    cutoff,
)
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from tests.sector_eval_helpers import synthetic_market
from tests.sectors_helpers import PanelBuilder, taipei, weekdays

#: Part of the NE-7 CI attestation set: the production view is the indexed one (T-5).
pytestmark = pytest.mark.sector_ne7


def _reference(panel: MarketPanel, t: date, *, hindsight: bool) -> PointInTimePanel:
    cut = None if hindsight else cutoff(t)
    return PointInTimePanel(
        key=_VIEW_KEY,
        decision_date=t,
        regime="hindsight" if hindsight else "pit",
        cutoff_at=cut,
        frames=_visible(panel.frames, t, cut),
    )


def _indexed(panel: MarketPanel, t: date, *, hindsight: bool) -> PointInTimePanel:
    return _hindsight_view(panel, t) if hindsight else panel.as_of(t)


def _same_frame(left: pd.DataFrame, right: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(
        left, right, check_exact=True, check_dtype=True, check_index_type=True
    )


def assert_same_view(
    fast: PointInTimePanel, slow: PointInTimePanel, *, full_matrices: bool = True
) -> None:
    """Every observable of the two views is identical (and the resolved bars themselves).

    ``full_matrices`` also compares every bar field over the whole visible
    history; otherwise the fields are compared over the last 25 sessions (the
    span the sector core reads).
    """
    assert fast.decision_date == slow.decision_date
    assert fast.regime == slow.regime
    assert fast.cutoff == slow.cutoff
    _same_frame(fast._bars, slow._bars)
    assert fast.sessions == slow.sessions
    first_fast, first_slow = fast.first_bar_sessions(), slow.first_bar_sessions()
    assert list(first_fast.items()) == list(first_slow.items())
    symbols = sorted(first_slow)
    sessions = list(slow.sessions) if full_matrices else list(slow.sessions[-25:])
    if sessions:
        for field in sorted(BAR_FIELDS) if full_matrices else ("close", "traded_value"):
            _same_frame(
                fast.field_matrix(field, sessions, symbols),
                slow.field_matrix(field, sessions, symbols),
            )
            if full_matrices:
                _same_frame(fast.field_matrix(field, sessions), slow.field_matrix(field, sessions))
        picked = sessions[-6:][::-1] + sessions[:2]
        _same_frame(
            fast.field_matrix("close", picked, symbols[::3]),
            slow.field_matrix("close", picked, symbols[::3]),
        )
        middle = sessions[len(sessions) // 2]
        _same_frame(fast.bars(middle, sessions[-1]), slow.bars(middle, sessions[-1]))
        _same_frame(fast.bars(sessions[0], middle), slow.bars(sessions[0], middle))
        for day in sessions[-8:]:
            assert fast.bars_source_on(day) == slow.bars_source_on(day)
    t = slow.decision_date
    assert fast.sessions_before(t, 5) == slow.sessions_before(t, 5)
    assert fast.bars_source_on(t + timedelta(days=0)) == slow.bars_source_on(t)
    for kind in ("listing", "classification"):
        left, right = fast.snapshot(kind), slow.snapshot(kind)
        assert (left is None) == (right is None)
        if left is not None and right is not None:
            assert (left.run_id, left.session_date, left.recorded_at, left.carried_sessions) == (
                right.run_id,
                right.session_date,
                right.recorded_at,
                right.carried_sessions,
            )
            _same_frame(left.rows, right.rows)
    _same_frame(fast.ex_dividend_announcements(), slow.ex_dividend_announcements())
    _same_frame(fast.visible_runs(), slow.visible_runs())
    for run_kind in ("bars", "listing", "classification", "dividend_announce"):
        assert fast.ok_run_sessions(run_kind) == slow.ok_run_sessions(run_kind)
    assert sector_eval.decision_fingerprint(
        sector_eval.decide(fast, V1)
    ) == sector_eval.decision_fingerprint(sector_eval.decide(slow, V1))


def _messy_market() -> MarketPanel:
    """Hand-built rows hitting every resolution and visibility rule at once."""
    rng = random.Random(7)
    days = weekdays(95)
    builder = PanelBuilder()
    codes = ["01", "02", "24", "20", "91"]
    symbols = [f"{code}{i:02d}" for code in codes for i in range(6)]
    price = {symbol: 40.0 + rng.random() * 40 for symbol in symbols}
    for n, day in enumerate(days):
        status = "failed" if n % 17 == 5 else ("partial" if n % 23 == 7 else "ok")
        bars = builder.run("bars", day, status=status)
        for symbol in symbols:
            price[symbol] *= 1 + rng.uniform(-0.03, 0.03)
            if rng.random() > 0.05:
                builder.bar(
                    bars,
                    day,
                    symbol,
                    round(price[symbol], 2),
                    change=round(rng.uniform(-1, 1), 2) if rng.random() > 0.3 else math.nan,
                    traded_value=2e7 + rng.random() * 3e7,
                )
        if n % 5 == 0:
            # A backup source for the same session, recorded later the same evening.
            backup = builder.run("bars", day, source="finmind", recorded=taipei(day, 20))
            for symbol in rng.sample(symbols, 8):
                builder.bar(backup, day, symbol, round(price[symbol] * 1.02, 2), source="finmind")
        if n % 7 == 0 and n + 1 < len(days):
            # A primary-source correction visible only from the next day.
            late = builder.run("bars", day, recorded=taipei(days[n + 1], 8))
            for symbol in rng.sample(symbols, 5):
                builder.bar(late, day, symbol, round(price[symbol] * 0.98, 2))
        if n % 11 == 3:
            # Two corrections recorded at the same instant (tie broken by run id).
            for _ in range(2):
                same = builder.run("bars", day, recorded=taipei(day, 21))
                builder.bar(same, day, symbols[0], round(price[symbols[0]] * 1.001, 2))
        if n < 20 or n % 9 == 4:
            continue  # warm-up bars only; later, carried-forward snapshots
        listing = builder.run("listing", day, status="failed" if n % 13 == 0 else "ok")
        classes = builder.run("classification", day)
        dividend = builder.run("dividend_announce", day)
        for symbol in symbols:
            if symbol == "0205" and n > 60:
                continue  # delisted
            builder.listed(listing, day, symbol)
            code = "02" if symbol == "0103" and n >= 50 else symbol[:2]
            builder.classified(classes, day, symbol, code, f"S{code}")
            if rng.random() < 0.02:
                builder.announced(dividend, day, symbol, day + timedelta(days=rng.randint(1, 8)))
    return builder.panel()


@pytest.fixture(scope="module")
def messy() -> MarketPanel:
    return _messy_market()


@pytest.mark.parametrize("hindsight", [False, True])
def test_every_session_of_a_messy_market_matches_the_reference(
    messy: MarketPanel, hindsight: bool
) -> None:
    sessions = sorted(set(messy.frames.bars["session_date"]))
    probes = [sessions[0] - timedelta(days=3), *sessions, sessions[-1] + timedelta(days=4)]
    for n, t in enumerate(probes):
        assert_same_view(
            _indexed(messy, t, hindsight=hindsight),
            _reference(messy, t, hindsight=hindsight),
            full_matrices=n % 10 == 0,
        )


def test_the_evaluator_market_matches_the_reference_on_every_other_session() -> None:
    market = synthetic_market(seed=5, warmup=62, forward=70, n_dividends=8)
    for n, t in enumerate(market.calendar[::2]):
        assert_same_view(
            market.panel.as_of(t),
            _reference(market.panel, t, hindsight=False),
            full_matrices=n % 12 == 0,
        )


def test_an_empty_panel_matches_the_reference() -> None:
    panel = PanelBuilder().panel()
    t = date(2026, 3, 2)
    for hindsight in (False, True):
        fast, slow = (
            _indexed(panel, t, hindsight=hindsight),
            _reference(panel, t, hindsight=hindsight),
        )
        _same_frame(fast._bars, slow._bars)
        assert fast.sessions == slow.sessions == ()
        assert fast.first_bar_sessions() == slow.first_bar_sessions() == {}
        assert fast.snapshot("listing") is None and slow.snapshot("listing") is None


def test_the_equivalence_check_has_teeth(messy: MarketPanel) -> None:
    """A view that differs by a single late-corrected close must fail the comparison."""
    sessions = sorted(set(messy.frames.bars["session_date"]))
    t = sessions[40]
    fast = messy.as_of(t)
    slow = _reference(messy, t, hindsight=False)
    tampered = fast._bars.copy()
    tampered.loc[len(tampered) // 2, "close"] = (
        # ``close`` is a float64 column; the stubs type a .loc cell as Scalar.
        float(cast(float, tampered.loc[len(tampered) // 2, "close"])) + 0.01
    )
    object.__setattr__(fast, "_bars", tampered)
    with pytest.raises(AssertionError):
        assert_same_view(fast, slow)
