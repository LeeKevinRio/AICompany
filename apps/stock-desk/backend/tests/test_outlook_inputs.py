"""The market snapshot (ADR-0030 D-1 ``inputs.py``, D-3 points 1, 2, 4, 5; freeze pack LA-G2-5).

Every answer goes through the real ``app.services.index.load_market_benchmark``
with an injected fake price service (no network, no cache, no database):

* only final bars enter (``is_final``, 15:00 Asia/Taipei on the bar's session);
  T is the latest final bar; non-final bars are listed in ``dropped``;
* LA-G2-5: a non-final bar for the session after T leaves the snapshot, T and
  ``content_sha256`` exactly as if the service had not returned it;
* the snapshot is cut to its size; every bar is ``^TWII``; a repeated or
  out-of-order session is refused, never reordered; no final bar is ``None``;
* ``LoadedBenchmark`` satisfies the ``IndexSeriesAnswer`` Protocol (static);
* why the answer is passed in: ``app.services.index`` reaches ``app.portfolio``
  and ``app.positions`` (fact), which ``app.outlook`` may not (K-2 / D-15 point 5);
* ``late_cutoff_at`` (moved here as the single definition) keeps its values and
  is what the store uses.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.data.interface import DataStatus
from app.forecast import store
from app.forecast.canonical import content_sha256
from app.outlook import inputs
from app.outlook.inputs import (
    IndexSeriesAnswer,
    MarketSnapshot,
    SnapshotShapeError,
    _cut_snapshot,
    capture_market_snapshot,
    late_cutoff_at,
)
from app.services.index import LoadedBenchmark, load_market_benchmark
from tests.import_graph import offenders, reachable_app_modules
from tests.outlook_helpers import (
    TAIPEI,
    FakeIndexService,
    evening,
    fixture_bars,
    price_bar,
    price_bars,
    weekdays,
)

#: Static check (mypy strict): the index service's answer type satisfies the Protocol.
_AS_ANSWER: IndexSeriesAnswer = LoadedBenchmark(series_symbol="^TWII")


def _answer(service: FakeIndexService) -> LoadedBenchmark:
    return load_market_benchmark(
        {"TW": service}, market="TW", start=date(2024, 1, 1), end=date(2027, 1, 1)
    )


def _capture(service: FakeIndexService, size: int = 315) -> MarketSnapshot:
    snapshot = capture_market_snapshot(_answer(service), size=size)
    assert snapshot is not None
    return snapshot


def _digest(snapshot: MarketSnapshot) -> str:
    return content_sha256(bar.as_mapping() for bar in snapshot.bars)


def test_the_answer_comes_through_the_index_service_with_backup_status() -> None:
    service = FakeIndexService(price_bars(fixture_bars("FX-B")), status=DataStatus.FRESH)
    snapshot = _capture(service)
    assert service.calls and service.calls[0][0] == "^TWII"
    # ADR-0005 I-3: the index service never lets an index series claim fresh.
    assert snapshot.source_status == "backup"
    assert snapshot.raw_timestamp_available is False
    assert len(snapshot.bars) == 315
    assert snapshot.data_as_of == fixture_bars("FX-B")[-1].session_date


def test_both_stamps_are_the_bars_retrieval_stamp() -> None:
    snapshot = _capture(FakeIndexService(price_bars(fixture_bars("FX-A"))))
    assert all(bar.fetched_at == bar.as_of for bar in snapshot.bars)


def test_the_snapshot_is_cut_to_its_size_ending_on_t() -> None:
    bars = fixture_bars("FX-A")
    snapshot = _capture(FakeIndexService(price_bars(bars)), size=100)
    assert [b.session_date for b in snapshot.bars] == [b.session_date for b in bars[-100:]]


def test_a_short_answer_is_kept_whole() -> None:
    bars = fixture_bars("FX-A")[-56:]
    assert len(_capture(FakeIndexService(price_bars(bars))).bars) == 56


@pytest.mark.parametrize(
    ("stamp", "final"),
    [
        pytest.param(timedelta(hours=15), True, id="15:00-final"),
        pytest.param(timedelta(hours=15, microseconds=-1), False, id="14:59:59.999999"),
        pytest.param(timedelta(hours=9), False, id="morning"),
        pytest.param(timedelta(days=1, hours=1), True, id="next-day"),
    ],
)
def test_only_final_bars_enter(stamp: timedelta, final: bool) -> None:
    days = weekdays(3)
    last = days[-1]
    as_of = datetime(last.year, last.month, last.day, tzinfo=TAIPEI) + stamp
    bars = [price_bar(day, Decimal("100"), evening(day)) for day in days[:-1]]
    bars.append(price_bar(last, Decimal("101"), as_of))
    snapshot = _capture(FakeIndexService(bars))
    assert (snapshot.data_as_of == last) is final
    assert [d.session_date for d in snapshot.dropped] == ([] if final else [last])


def test_la_g2_5_a_non_final_next_bar_changes_nothing() -> None:
    bars = fixture_bars("FX-B")
    t = bars[-1].session_date
    following = t + timedelta(days=3 if t.weekday() == 4 else 1)
    early = datetime(following.year, following.month, following.day, 14, 0, tzinfo=TAIPEI)
    with_extra = [*price_bars(bars), price_bar(following, Decimal("12345.5"), early)]
    without = _capture(FakeIndexService(price_bars(bars)))
    with_it = _capture(FakeIndexService(with_extra))
    assert with_it.data_as_of == without.data_as_of == t
    assert with_it.bars == without.bars
    assert _digest(with_it) == _digest(without)
    assert [d.session_date for d in with_it.dropped] == [following]


def test_no_final_bar_is_none() -> None:
    day = weekdays(1)[0]
    early = datetime(day.year, day.month, day.day, 10, tzinfo=TAIPEI)
    answer = _answer(FakeIndexService([price_bar(day, Decimal("100"), early)]))
    assert capture_market_snapshot(answer, size=315) is None


def test_an_empty_answer_has_no_snapshot() -> None:
    assert capture_market_snapshot(_answer(FakeIndexService([])), size=315) is None


def test_a_repeated_session_is_refused() -> None:
    bars = price_bars(fixture_bars("FX-A")[-5:])
    with pytest.raises(SnapshotShapeError):
        capture_market_snapshot(
            LoadedBenchmark(series_symbol="^TWII", bars=[*bars, bars[-1]]), size=315
        )


def test_an_out_of_order_answer_is_refused_not_reordered() -> None:
    bars = price_bars(fixture_bars("FX-A")[-5:])
    with pytest.raises(SnapshotShapeError):
        capture_market_snapshot(
            LoadedBenchmark(series_symbol="^TWII", bars=[bars[1], bars[0], *bars[2:]]), size=315
        )


def test_another_series_is_refused() -> None:
    bars = price_bars(fixture_bars("FX-A")[-5:])
    with pytest.raises(SnapshotShapeError):
        capture_market_snapshot(LoadedBenchmark(series_symbol="^GSPC", bars=bars), size=315)
    other = price_bar(bars[-1].date, Decimal("1"), bars[-1].as_of, symbol="0050")
    with pytest.raises(SnapshotShapeError):
        capture_market_snapshot(
            LoadedBenchmark(series_symbol="^TWII", bars=[*bars[:-1], other]), size=315
        )


@pytest.mark.parametrize("size", [0, -1, True, 1.5])
def test_the_size_must_be_a_positive_int(size: object) -> None:
    with pytest.raises(ValueError):
        _cut_snapshot(fixture_bars("FX-A"), fixture_bars("FX-A")[-1].session_date, size)  # type: ignore[arg-type]


def test_the_cut_needs_the_decision_session_in_the_series() -> None:
    bars = fixture_bars("FX-A")
    with pytest.raises(SnapshotShapeError):
        _cut_snapshot(bars, bars[0].session_date - timedelta(days=7), 10)
    saturday = next(
        bars[-1].session_date - timedelta(days=d)
        for d in range(7)
        if (bars[-1].session_date - timedelta(days=d)).weekday() == 5
    )
    with pytest.raises(SnapshotShapeError):
        _cut_snapshot(bars, saturday, 10)


def test_the_index_service_reaches_packages_the_outlook_may_not() -> None:
    # Why inputs.py takes the answer instead of importing app.services.index.
    reachable = reachable_app_modules(("app.services.index",))
    assert offenders(reachable, "app.portfolio") != []
    assert offenders(reachable, "app.positions") != []
    assert offenders(reachable_app_modules(("app.outlook.inputs",)), "app.portfolio") == []


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 11, 13), datetime(2026, 11, 13, 16, 0, tzinfo=UTC)),
        (date(2026, 12, 31), datetime(2026, 12, 31, 16, 0, tzinfo=UTC)),
        (date(2028, 2, 28), datetime(2028, 2, 28, 16, 0, tzinfo=UTC)),
    ],
)
def test_late_cutoff_is_the_next_calendar_day_at_midnight_taipei(
    day: date, expected: datetime
) -> None:
    assert late_cutoff_at(day) == expected


def test_the_store_uses_the_one_cutoff_definition() -> None:
    assert store.late_cutoff_at is inputs.late_cutoff_at
