"""ADR-0016 D-5.2 / F6 pair, second leg (end to end): F6 carries a dated in-window event.

The first leg is ``test_dividends_coverage.py``
(``test_main_db_leaves_a_dated_event_in_the_window_to_f6``):
with the main DB as the run source, a dated event inside the window is *not*
reported by ``AnnounceRunCoverageRule`` (it answers ``known``). That answer is
only safe because of this leg: the same data, fed through ``ChangeScreen`` with
``DividendEventStore.ex_dates_between`` as the ex-date lookup, is withheld by F6
before the coverage rule is even asked. Every database lives under ``tmp_path``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest

from app.portfolio.price_change import (
    ChangeScreen,
    CoverageQuery,
    ExDateCoverage,
    ExDateCoverageRule,
    PriceChange,
)
from tests.test_dividends_coverage import EVENING, FRI, OTHER, THU, _MainLog, _query
from tests.test_price_change import _bar, _Calendar, _valued

_SCREEN_LOGGER = "app.portfolio.price_change"
_F6_CODE = "F6_ex_date_in_window"


@dataclass
class _RecordingRule:
    """Wraps the real rule and records what the screen asked it."""

    inner: ExDateCoverageRule
    asked: list[CoverageQuery] = field(default_factory=list)

    def coverage(self, queries: Sequence[CoverageQuery]) -> Mapping[CoverageQuery, ExDateCoverage]:
        self.asked.extend(queries)
        return self.inner.coverage(queries)


def _screen_one(
    log: _MainLog, *, rule: _RecordingRule | None = None
) -> tuple[PriceChange | None, _RecordingRule]:
    recording = rule if rule is not None else _RecordingRule(log.rule())
    screen = ChangeScreen(
        ex_dates=log.store,
        calendar=_Calendar(days={"TW": {THU, FRI}}),
        coverage_rule=recording,
    )
    # Bars THU -> FRI: the basis is THU and the price date FRI, the window (THU, FRI].
    row = _valued([_bar(THU, "100"), _bar(FRI, "101")])
    return screen.screen([row])[0], recording


def test_f6_carries_the_dated_in_window_event_even_though_the_rule_says_known(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """This scenario is carried by F6; the rule answering ``known`` does not mean it is safe.

    The main DB holds a dated ``2330`` event on the price date (inside the window).
    ``AnnounceRunCoverageRule`` answers ``known`` for that symbol (the source returns
    no dated observation -- the event is in ``dividend_events``), so a screen that
    relied on the rule alone would show the change. F6 reads the very same row via
    ``ex_dates_between`` and withholds it: ``change`` is null, for reason F6.
    """
    log = _MainLog(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", FRI)])
    query = _query()

    # Leg one, restated on the same data: the rule alone says ``known``.
    assert log.rule().coverage([query]) == {query: "known"}
    # The same row is what F6 reads.
    assert log.store.ex_dates_between([("2330", "TW")], THU, FRI) == {
        ("2330", "TW"): frozenset({FRI})
    }

    # Leg two: through the screen, the change is withheld, and the reason is F6.
    with caplog.at_level(logging.DEBUG, logger=_SCREEN_LOGGER):
        change, rule = _screen_one(log)
    assert change is None
    reasons = [
        record.getMessage()
        for record in caplog.records
        if record.name == _SCREEN_LOGGER and record.levelno == logging.DEBUG
    ]
    assert [message for message in reasons if _F6_CODE in message] == [
        f"price change withheld ({_F6_CODE}): TW 2330"
    ]
    assert not any("D5_coverage_unknown" in message for message in reasons)
    # F6 won before the coverage rule was consulted for this row.
    assert rule.asked == []


def test_the_same_screen_shows_the_change_when_the_event_is_outside_the_window(
    tmp_path: Path,
) -> None:
    """Control: with no in-window event, the same screen and rule do show the change.

    So the null above is the F6 withholding and nothing else about the harness.
    """
    log = _MainLog(tmp_path)
    log.run(EVENING[THU], [OTHER])
    change, rule = _screen_one(log)
    assert change is not None
    assert change.pct == Decimal("1.0000")
    assert [(q.symbol, q.basis_date, q.price_date) for q in rule.asked] == [("2330", THU, FRI)]
    assert log.rule().coverage([_query()]) == {_query(): "known"}


def test_f6_withholds_an_event_the_rule_never_sees_for_a_symbol_with_a_clean_run(
    tmp_path: Path,
) -> None:
    """Both legs on one book: only the event-carrying symbol is withheld by F6.

    A second event in the window belongs to another symbol; ``2330`` has none, so
    it is not withheld (the rule answers ``known`` for both -- F6 alone separates them).
    """
    log = _MainLog(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2317", FRI)])
    assert log.rule().coverage([_query("2317"), _query("2330")]) == {
        _query("2317"): "known",
        _query("2330"): "known",
    }
    change, _ = _screen_one(log)  # the row under test is 2330
    assert change is not None
    assert log.store.ex_dates_between([("2330", "TW"), ("2317", "TW")], THU, FRI) == {
        ("2317", "TW"): frozenset({FRI})
    }
