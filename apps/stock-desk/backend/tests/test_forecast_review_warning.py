"""D-8 point 4: the review trigger WARNING of the recorder (ADR-0030 supplement 5 point 2, C5-4).

Every ledger is a ``tmp_path`` file filled by the real recorder over synthetic
bars with the landed h3 / h5 rule files and the stand-in definition,
registered for each test only (K-11). The four S-10a cases -- nothing holds,
only T1, T1 and T2, the determination raises -- each compare the run's result
and every stored ``content_hash`` with a run where the trigger is not judged
at all, and check the log lines against the fixed format. T2 is also reached
for real, by the store clock; T1 and "both" are injected through
``ForecastStore.review_trigger`` (reaching n-hat >= 15 for real takes ~45
runs, and the arithmetic is the store's own, tested with the report).
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from app.dirdef.registry import PublishedRuleset
from app.dirdef.rules import rules_logic_sha256
from app.forecast import definitions
from app.forecast import recorder as recorder_module
from app.forecast.recorder import (
    REVIEW_TRIGGER_CHECK_FAILED,
    REVIEW_TRIGGER_WARNING,
    RunResult,
    record_forecasts,
    warn_review_triggers,
)
from app.forecast.store import ForecastStore, ReviewTrigger
from app.services.index import IndexServiceResolver, load_market_benchmark
from tests.forecast_ledger_helpers import FakeClock, file_ledger, publish_definition
from tests.outlook_helpers import (
    TAIPEI,
    FakeIndexService,
    definition,
    price_bar,
    rule_bytes,
    ruleset,
)

H3 = "outlook-market-v1.0-h3"
H5 = "outlook-market-v1.0-h5"
LAST = date(2026, 11, 13)  # a Friday: the last synthetic session
LOGGER = recorder_module.__name__
LINE = re.compile(
    r"forecast_record: review trigger holds; claim_id=market\|h[35]\|\S+ trigger=(T1|T2|T1\+T2)"
)
#: Nothing a WARNING line may carry besides the claim and which trigger.
FORBIDDEN_IN_LINES = ("n̂", "n_hat", "c1", "c₁", "d1", "d₁", "D_v", "2026", "bullish", "range")


def _sessions(count: int) -> list[date]:
    days: list[date] = []
    day = LAST
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day = date.fromordinal(day.toordinal() - 1)
    return list(reversed(days))


def _publish(monkeypatch: pytest.MonkeyPatch) -> None:
    publish_definition(monkeypatch, definition())
    entries = {
        H3: PublishedRuleset(horizon=3, rules_sha256=hashlib.sha256(rule_bytes(3)).hexdigest()),
        H5: PublishedRuleset(horizon=5, rules_sha256=hashlib.sha256(rule_bytes(5)).hexdigest()),
    }
    monkeypatch.setattr(definitions, "PUBLISHED_RULESETS", MappingProxyType(entries))
    monkeypatch.setattr(definitions, "_RULESET_CACHE", {})


class World:
    """A ``tmp_path`` ledger with the two core claims and the synthetic index answer."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root.mkdir(parents=True, exist_ok=True)
        _publish(monkeypatch)
        self.path = file_ledger(root)
        self.clock = FakeClock(datetime(2026, 10, 1, 9, tzinfo=TAIPEI))
        self.store = ForecastStore(self.path, clock=self.clock)
        for horizon in (3, 5):
            self.clock.advance(seconds=1)
            self.store.register_claim(
                horizon=3 if horizon == 3 else 5,
                rules_version=H3 if horizon == 3 else H5,
                rules_bytes=rule_bytes(horizon),
                rules_logic_sha256=rules_logic_sha256(ruleset(horizon)),
                definition=definition(),
                frozen_commit="abc123",
                prereg_doc_path="docs/prereg-v0.32.md",
                prereg_doc_blob=b"prereg",
                review_refs="work/reviews/x.md",
                replaces_claim_id=None,
                replace_reason=None,
                provisional_results_seen=False,
            )
        days = _sessions(330)
        closes = [10000.0]
        for j in range(1, len(days)):
            step = 0.008 * math.sin(0.7 * j) + 0.003 * (((j * 7919) % 13) - 6) / 6
            closes.append(closes[-1] * math.exp(step))
        bars = [
            price_bar(day, Decimal(close), datetime.combine(day, time(20), TAIPEI))
            for day, close in zip(days, closes, strict=True)
        ]
        self.resolver: IndexServiceResolver = {"TW": FakeIndexService(bars)}

    def run(self, at: datetime) -> RunResult:
        self.clock.now = at
        return record_forecasts(
            self.store, load_benchmark=load_market_benchmark, resolver=self.resolver
        )

    def hashes(self) -> list[str]:
        return [
            str(row["content_hash"])
            for claim in self.store.forward_claims()
            for row in self.store.stored_records(claim.claim_id)
        ]


def _lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER and record.levelno == logging.WARNING
    ]


RUN_AT = datetime.combine(LAST, time(22, 10), TAIPEI)


def _baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[RunResult, list[str]]:
    """The same run with the determination switched off entirely."""
    world = World(tmp_path / "baseline", monkeypatch)
    with monkeypatch.context() as patch:
        patch.setattr(recorder_module, "warn_review_triggers", lambda store: ())
        result = world.run(RUN_AT)
    return result, world.hashes()


def _injected(t1: bool, t2: bool) -> Callable[..., ReviewTrigger]:
    real = ForecastStore.review_trigger

    def review_trigger(self: ForecastStore, claim_id: str, *, today: date) -> ReviewTrigger:
        return replace(real(self, claim_id, today=today), t1=t1, t2=t2)

    return review_trigger


def _raising(exc: BaseException) -> Callable[..., ReviewTrigger]:
    def review_trigger(self: ForecastStore, claim_id: str, *, today: date) -> ReviewTrigger:
        raise exc

    return review_trigger


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        pytest.param("none", [], id="nothing-holds"),
        pytest.param("t1", ["T1", "T1"], id="only-t1"),
        pytest.param("both", ["T1+T2", "T1+T2"], id="t1-and-t2"),
        pytest.param("raises", None, id="the-determination-raises"),
    ],
)
def test_the_warning_changes_nothing_and_has_the_fixed_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    case: str,
    expected: list[str] | None,
) -> None:
    base_result, base_hashes = _baseline(tmp_path, monkeypatch)
    world = World(tmp_path / "judged", monkeypatch)
    if case == "t1":
        monkeypatch.setattr(ForecastStore, "review_trigger", _injected(True, False))
    elif case == "both":
        monkeypatch.setattr(ForecastStore, "review_trigger", _injected(True, True))
    elif case == "raises":
        monkeypatch.setattr(ForecastStore, "review_trigger", _raising(RuntimeError("boom")))
    caplog.set_level(logging.WARNING, logger=LOGGER)
    result = world.run(RUN_AT)
    assert result == base_result and result.outcome == "ok" and result.records_written == 2
    assert world.hashes() == base_hashes
    lines = _lines(caplog)
    if expected is None:
        assert lines == [REVIEW_TRIGGER_CHECK_FAILED]
        return
    assert [LINE.fullmatch(line) is not None for line in lines] == [True] * len(expected)
    assert [line.rsplit("trigger=", 1)[1] for line in lines] == expected
    claims = [claim.claim_id for claim in world.store.forward_claims()]
    assert [line.split("claim_id=", 1)[1].split(" ", 1)[0] for line in lines] == claims[
        : len(expected)
    ]
    assert not any(word in line for line in lines for word in FORBIDDEN_IN_LINES)


def test_t2_is_reached_by_the_store_clock_and_logged_for_that_claim_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    world = World(tmp_path, monkeypatch)
    assert world.run(RUN_AT).outcome == "ok"  # D_v = LAST for both claims
    caplog.set_level(logging.WARNING, logger=LOGGER)
    # d_1(h3) = LAST + 90 weekdays = 2027-03-19; minus 90 calendar days = 2026-12-19.
    # d_1(h5) = LAST + 150 weekdays: T2 is months away.
    before = world.run(datetime(2026, 12, 18, 22, 10, tzinfo=TAIPEI))
    assert _lines(caplog) == []
    caplog.clear()
    after = world.run(datetime(2026, 12, 19, 22, 10, tzinfo=TAIPEI))
    h3 = world.store.recording_claims()[("market", 3)].claim_id
    assert _lines(caplog) == [REVIEW_TRIGGER_WARNING % (h3, "T2")]
    assert before.outcome == after.outcome == "no_new_session"
    # Every run logs again while it holds (no "already logged" state).
    caplog.clear()
    world.run(datetime(2026, 12, 21, 22, 10, tzinfo=TAIPEI))
    assert _lines(caplog) == [REVIEW_TRIGGER_WARNING % (h3, "T2")]


def test_without_d_v_nothing_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    world = World(tmp_path, monkeypatch)
    caplog.set_level(logging.WARNING, logger=LOGGER)
    # Years later, but no record at all: no D_v, so neither T1 nor T2.
    assert warn_review_triggers(world.store) == ()
    world.clock.now = datetime(2030, 1, 7, 22, 10, tzinfo=TAIPEI)
    assert warn_review_triggers(world.store) == ()
    assert _lines(caplog) == []


def test_the_determination_runs_after_the_end_row_on_every_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World(tmp_path, monkeypatch)
    seen: list[str | None] = []
    real = ForecastStore.review_trigger

    def review_trigger(self: ForecastStore, claim_id: str, *, today: date) -> ReviewTrigger:
        seen.append(self.runs()[-1].outcome)  # the end row is already committed
        return real(self, claim_id, today=today)

    monkeypatch.setattr(ForecastStore, "review_trigger", review_trigger)
    world.run(RUN_AT)
    world.resolver = {}  # the loader finds no TW service: still an end row first
    world.run(datetime.combine(LAST, time(23, 10), TAIPEI))
    assert seen[:2] == ["ok", "ok"] and len(seen) == 4 and all(seen)


def test_an_interruption_of_the_determination_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World(tmp_path, monkeypatch)
    monkeypatch.setattr(ForecastStore, "review_trigger", _raising(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        world.run(RUN_AT)
    runs = world.store.runs()
    assert [run.outcome for run in runs] == ["ok"]  # the run itself had ended
    assert len(world.hashes()) == 2


def test_a_failing_store_read_logs_the_fixed_line_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    world = World(tmp_path, monkeypatch)

    def broken(self: ForecastStore) -> Any:
        raise OSError("disk")

    monkeypatch.setattr(ForecastStore, "forward_claims", broken)
    caplog.set_level(logging.WARNING, logger=LOGGER)
    assert warn_review_triggers(world.store) == ()
    assert _lines(caplog) == [REVIEW_TRIGGER_CHECK_FAILED]
