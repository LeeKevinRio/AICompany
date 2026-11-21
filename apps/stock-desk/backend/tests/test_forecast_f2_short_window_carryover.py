"""F-2 first sentence: does a short-range "holds" carry into the full windows?

Pins supplement 13 point 9 (d) (tech-architect, 2026-11-21): on the wired
``store.f2_status``, a "holds" shown while the window is not yet full is
contained in the first full window (the short range is its prefix, the
numerator only grows, the full threshold is at most 6 misses of 20), so that
window holds and the report keeps printing "ever held: yes". The earlier ruling
(2026-11-20, question 4 (d)) said the opposite -- that the short-range "holds"
is shown only at the moment and disappears later. These tests pin what the
code does, stage by stage, on synthetic ledgers under ``tmp_path``.

Ledger shape of the main scenario: Monday 2026-10-05 is the start; the first
``MISSED`` weekdays are sessions without a ``late = 0`` record; every later
weekday is recorded on time, nothing else is ever missed. Only the clock
(``now``) moves between stages; the rows for later days are already stored, which
the query cannot tell apart from rows written day by day (it reads dates up to
the last eligible weekday only, and the per-day rows never change).

(iii) "Ever held" is recomputed from the history, not stored: it is the ``any``
over every rolling full window since the start, with no cap on how far back.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from app.forecast import report
from app.forecast.store import (
    F2_RATIO_DENOMINATOR,
    F2_RATIO_NUMERATOR,
    F2_SHORT_WINDOW_LIMIT,
    F2_WINDOW_WEEKDAYS,
    ForecastStore,
)
from tests import approved_copy
from tests.forecast_ledger_helpers import file_ledger, weekdays
from tests.test_forecast_f2_window import (
    CLAIM_H3,
    MONDAY,
    Ledger,
    after_cutoff,
    at,
    f2_lines,
)

#: Smallest short-range numerator that holds: strictly more than 6.
MISSED = F2_SHORT_WINDOW_LIMIT + 1
#: Weekdays recorded in the long scenario (about 14 months of weekdays).
LONG_SPAN = 300
EVER_YES = "曾否成立：是（成立後不撤銷）"


def build(tmp_path: Path, span: int, *, missed: int) -> tuple[Ledger, list[date]]:
    """A ledger of ``span`` weekdays from MONDAY; the first ``missed`` have no record."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(path=file_ledger(tmp_path))
    ledger.claim(CLAIM_H3, horizon=3, registered=at(date(2026, 9, 1), 9, 0))
    days = weekdays(MONDAY, span)
    ledger.run(at(MONDAY, 9, 0))
    ledger.snapshot(days)
    for day in days[missed:]:
        ledger.record(CLAIM_H3, day)
    return ledger, days


def line_at(ledger: Ledger, now: datetime) -> str:
    """The one F-2 first-sentence line of the only claim, as ``report status`` prints it."""
    lines = report.render_execution_status(ForecastStore(ledger.path), now=now)
    found = f2_lines(lines)
    assert len(found) == 1
    return found[0]


def short_line(missed: int, days: Sequence[date], k: int, *, holds: bool) -> str:
    template = approved_copy.f2_lines()["short"]
    return approved_copy.fill(
        template,
        0 if holds else 1,
        claim_id=CLAIM_H3,
        k=k,
        起=days[0],
        迄=days[k - 1],
        a=missed,
        b=0,
    )


def full_line(days: Sequence[date], first: int, missed: int, *, holds: bool, ever: bool) -> str:
    """A full-window line over ``days[first]..days[first + 19]`` with denominator 20."""
    template = approved_copy.f2_lines()["full"]
    return approved_copy.fill(
        template,
        0 if holds else 1,
        0 if ever else 1,
        claim_id=CLAIM_H3,
        起=days[first],
        迄=days[first + F2_WINDOW_WEEKDAYS - 1],
        a=missed,
        b=0,
        d=F2_WINDOW_WEEKDAYS,
    )


def now_after(days: Sequence[date], weekday_count: int) -> datetime:
    """The first instant at which exactly ``weekday_count`` weekdays are eligible."""
    return after_cutoff(days[weekday_count - 1])


# --- (i) the main scenario ----------------------------------------------------------------------


def test_supplement_13_point_9_d_short_range_holds_carries_into_first_full_window(
    tmp_path: Path,
) -> None:
    """Pins supplement 13 point 9 (d): the stage-by-stage outputs of one ledger."""
    ledger, days = build(tmp_path, LONG_SPAN, missed=MISSED)

    # Stage 0: while the window is not full the first sentence holds (7 > 6), from 7 up to 19
    # weekdays, the numerator staying at 7.
    for k in (MISSED, 10, 19):
        assert line_at(ledger, now_after(days, k)) == short_line(MISSED, days, k, holds=True)

    # Stage 1: the first full window (weekdays 1..20) holds (7 * 10 > 20 * 3); ever held: yes.
    assert line_at(ledger, now_after(days, 20)) == full_line(days, 0, MISSED, holds=True, ever=True)

    # Stage 2: the next weekday drops the first missed day: 6 misses, this window does not
    # hold, but the first one did, so "ever held" stays yes.
    assert line_at(ledger, now_after(days, 21)) == full_line(
        days, 1, MISSED - 1, holds=False, ever=True
    )

    # Stage 3: one weekday before the last missed day slides out: one miss left.
    assert line_at(ledger, now_after(days, 26)) == full_line(days, 6, 1, holds=False, ever=True)

    # Stage 4: all missed days are outside the rolling window; the current window is clean and
    # "ever held" is still yes.
    assert line_at(ledger, now_after(days, 27)) == full_line(days, 7, 0, holds=False, ever=True)
    assert line_at(ledger, now_after(days, 60)) == full_line(days, 40, 0, holds=False, ever=True)


def test_the_short_range_wording_exists_only_before_the_window_fills(tmp_path: Path) -> None:
    """The literal "F-2 成立（兩項合計已超過 6" clause is printed only by the short line.

    Later the same signal is carried by the "曾否成立：是" tail, not by the first clause.
    """
    ledger, days = build(tmp_path, LONG_SPAN, missed=MISSED)
    early = line_at(ledger, now_after(days, 10))
    later = line_at(ledger, now_after(days, 40))
    assert "F-2 成立（兩項合計已超過 6" in early
    assert "兩項合計已超過 6" not in later
    assert "此視窗 F-2 未成立" in later
    assert EVER_YES in later


# --- (ii) the boundary --------------------------------------------------------------------------


def test_the_two_thresholds_in_the_constants() -> None:
    # Short range: holds above 6. Full window of 20 sessions: holds above 30 %, i.e. from 7.
    assert F2_SHORT_WINDOW_LIMIT == 6
    assert (F2_RATIO_NUMERATOR, F2_RATIO_DENOMINATOR) == (3, 10)
    assert F2_WINDOW_WEEKDAYS == 20
    assert not 6 * F2_RATIO_DENOMINATOR > F2_WINDOW_WEEKDAYS * F2_RATIO_NUMERATOR
    assert 7 * F2_RATIO_DENOMINATOR > F2_WINDOW_WEEKDAYS * F2_RATIO_NUMERATOR


def test_the_smallest_holding_miss_count_carries_over_and_one_fewer_never_holds(
    tmp_path: Path,
) -> None:
    """Seven misses hold in the short range and ever after; six never hold anywhere."""
    holding, days = build(tmp_path / "seven", LONG_SPAN, missed=MISSED)
    assert line_at(holding, now_after(days, 19)) == short_line(MISSED, days, 19, holds=True)
    assert line_at(holding, now_after(days, 20)).endswith(EVER_YES)
    assert line_at(holding, now_after(days, LONG_SPAN)).endswith(EVER_YES)

    control, days = build(tmp_path / "six", LONG_SPAN, missed=MISSED - 1)
    assert line_at(control, now_after(days, 19)) == short_line(MISSED - 1, days, 19, holds=False)
    assert line_at(control, now_after(days, 20)) == full_line(
        days, 0, MISSED - 1, holds=False, ever=False
    )
    for count in (21, 27, 60, LONG_SPAN):
        assert line_at(control, now_after(days, count)).endswith("曾否成立：否")


def test_the_short_range_is_a_prefix_of_the_first_full_window(tmp_path: Path) -> None:
    """Same first day, numerator never above the first full window's."""
    ledger, days = build(tmp_path, LONG_SPAN, missed=MISSED)
    store = ForecastStore(ledger.path)
    first = store.f2_status(CLAIM_H3, now=now_after(days, 20))
    assert first.window is not None and first.window.first == days[0]
    for k in range(MISSED, F2_WINDOW_WEEKDAYS):
        short = store.f2_status(CLAIM_H3, now=now_after(days, k))
        assert short.window is not None and short.window.first == first.window.first
        assert short.window.numerator <= first.window.numerator


# --- (iii) how far back "ever held" looks -------------------------------------------------------


def test_ever_held_is_recomputed_from_every_window_since_the_start_with_no_cap(
    tmp_path: Path,
) -> None:
    """No stored flag: the answer is any() over all rolling windows, however old the first is.

    Looking 300 weekdays (over a year) after the start, 280 after the misses slid out, still
    prints yes.
    """
    ledger, days = build(tmp_path, LONG_SPAN, missed=MISSED)
    status = ForecastStore(ledger.path).f2_status(CLAIM_H3, now=now_after(days, LONG_SPAN))
    assert status.full and status.weekdays == LONG_SPAN
    assert status.window is not None
    assert (status.window.first, status.window.last) == (days[-20], days[-1])
    assert status.window.numerator == 0 and not status.window.holds
    assert status.ever_held
    assert line_at(ledger, now_after(days, LONG_SPAN)) == full_line(
        days, LONG_SPAN - F2_WINDOW_WEEKDAYS, 0, holds=False, ever=True
    )


def test_ever_held_is_derived_from_all_windows_not_a_stored_flag() -> None:
    """The derivation source: ``any`` over every window index since the start."""
    source = inspect.getsource(ForecastStore.f2_status)
    assert "ever_held=any(item.holds for item in windows)" in source
    assert "for index in range(len(eligible) - F2_WINDOW_WEEKDAYS + 1)" in source


def test_a_spread_miss_pattern_stays_at_no_for_the_whole_history(tmp_path: Path) -> None:
    """Contrast: one miss every 4th weekday (at most 5 per 20) never holds anywhere."""
    ledger = Ledger(path=file_ledger(tmp_path))
    ledger.claim(CLAIM_H3, horizon=3, registered=at(date(2026, 9, 1), 9, 0))
    days = weekdays(MONDAY, 100)
    ledger.run(at(MONDAY, 9, 0))
    ledger.snapshot(days)
    skipped = set(days[::4])
    for day in days:
        if day not in skipped:
            ledger.record(CLAIM_H3, day)
    assert line_at(ledger, now_after(days, 10)).endswith("尚未判定（兩項合計未超過 6）")
    for count in (20, 50, 100):
        assert line_at(ledger, now_after(days, count)).endswith("曾否成立：否")
