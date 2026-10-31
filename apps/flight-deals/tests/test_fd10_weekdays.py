"""Departure weekdays: domain type, revision, validation, expansion and sampling
(ADR-0002 FD-10 Decisions 2-5, C-72, C-73, C-74)."""

from __future__ import annotations

import ast
import itertools
import math
import random
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain import dates as dates_module
from flight_deals.domain.dates import (
    MAX_MONTH_CELLS,
    expand_pairs,
    first_pair,
    is_expired,
    month_pairs,
    month_weekday_counts,
    range_months,
    range_pairs,
    sample_pairs,
    weekday_filter_leaves_nothing,
)
from flight_deals.domain.messages import (
    WEEKDAYS_INVALID,
    WEEKDAYS_NO_MATCH_WINDOW,
    WEEKDAYS_REQUIRED,
)
from flight_deals.domain.models import DatePair, ExplorationSpec, WatchSpec
from flight_deals.domain.validation import validate_comparison, validate_watch_input
from flight_deals.domain.weekdays import (
    ALL_WEEKDAYS,
    ALL_WEEKDAYS_MASK,
    is_all_weekdays,
    normalize_weekdays,
    weekdays_from_mask,
    weekdays_to_mask,
)
from flight_deals.storage.repository import AlertStateRecord
from tests.conftest import CLIENT_HEADERS, Harness

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
TODAY = date(2026, 10, 25)  # Sunday; the harness clock's Asia/Taipei date


# ---- FD-9 expand_pairs, copied verbatim as the reference (C-74) ---------------------

FD9_MAX_EXPAND_SPAN_DAYS = 366
FD9_MAX_DAYS_AHEAD = 365


def _fd9_days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def fd9_expand_pairs(spec: WatchSpec, today: date) -> list[DatePair]:
    """All (depart, return) pairs still in the future (depart >= today), sorted."""
    if spec.date_mode == "fixed":
        if spec.depart_date is None or spec.depart_date < today:
            return []
        ret = spec.return_date if spec.trip_type == "round_trip" else None
        return [DatePair(spec.depart_date, ret)]

    if spec.window_start is None or spec.window_end is None:
        return []
    first = max(spec.window_start, today)
    if first > spec.window_end:
        return []
    end = min(spec.window_end, first + timedelta(days=FD9_MAX_EXPAND_SPAN_DAYS))
    if spec.trip_type == "one_way":
        return [DatePair(day) for day in _fd9_days(first, end)]

    low = spec.min_trip_days or 0
    high = spec.max_trip_days if spec.max_trip_days is not None else low
    pairs: list[DatePair] = []
    for depart in _fd9_days(first, end):
        for length in range(low, high + 1):
            ret = depart + timedelta(days=length)
            if ret <= end:
                pairs.append(DatePair(depart, ret))
    return sorted(pairs)


def window(
    start: date,
    end: date,
    low: int | None = 3,
    high: int | None = 5,
    *,
    one_way: bool = False,
    weekdays: tuple[int, ...] = ALL_WEEKDAYS,
) -> WatchSpec:
    return WatchSpec(
        name="w",
        origin="TPE",
        destination="NRT",
        trip_type="one_way" if one_way else "round_trip",
        date_mode="flexible",
        depart_date=None,
        return_date=None,
        window_start=start,
        window_end=end,
        min_trip_days=None if one_way else low,
        max_trip_days=None if one_way else high,
        max_stops=None,
        budget_amount_minor=1_000_000,
        depart_weekdays=weekdays,
    )


def fixed(depart: date, ret: date | None, weekdays: tuple[int, ...] = ALL_WEEKDAYS) -> WatchSpec:
    return replace(
        window(depart, depart),
        date_mode="fixed",
        depart_date=depart,
        return_date=ret,
        window_start=None,
        window_end=None,
        min_trip_days=None,
        max_trip_days=None,
        depart_weekdays=weekdays,
    )


# ---- weekdays module (C-72) ------------------------------------------------------------


def test_weekdays_module_is_stdlib_only() -> None:  # C-72, C-79
    tree = ast.parse((SRC / "domain" / "weekdays.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert set(imported) <= {"__future__", "collections.abc"}


def test_every_non_empty_subset_round_trips() -> None:  # C-72
    seen = set()
    for size in range(1, 8):
        for combo in itertools.combinations(ALL_WEEKDAYS, size):
            mask = weekdays_to_mask(combo)
            assert weekdays_from_mask(mask) == combo
            assert weekdays_to_mask(reversed(combo)) == mask
            seen.add(mask)
    assert seen == set(range(1, 128)) and len(seen) == 127
    assert weekdays_to_mask(ALL_WEEKDAYS) == ALL_WEEKDAYS_MASK == 127


def test_bit_i_is_date_weekday_i() -> None:  # C-72
    day = date(2026, 12, 7)  # Monday
    for offset in range(7):
        current = day + timedelta(days=offset)
        assert weekdays_from_mask(1 << current.weekday()) == (current.weekday(),)
        assert weekdays_to_mask([current.weekday()]) == 1 << offset


@pytest.mark.parametrize("values", [[], [7], [-1], [True], [4.0], ["4"]])
def test_normalize_rejects(values: list[Any]) -> None:
    with pytest.raises(ValueError):
        normalize_weekdays(values)


@pytest.mark.parametrize("mask", [0, 128, -1, True])
def test_from_mask_rejects(mask: Any) -> None:
    with pytest.raises(ValueError):
        weekdays_from_mask(mask)


def test_normalize_sorts_and_dedupes() -> None:
    assert normalize_weekdays([5, 4, 4]) == (4, 5)
    assert is_all_weekdays([6, 5, 4, 3, 2, 1, 0]) and not is_all_weekdays([0])


def test_search_shape_ends_with_normalized_weekdays() -> None:  # C-72
    spec = window(date(2026, 12, 1), date(2026, 12, 31), weekdays=(5, 4))
    assert spec.search_shape()[-1] == (4, 5)
    assert window(date(2026, 12, 1), date(2026, 12, 31)).search_shape()[-1] == ALL_WEEKDAYS


# ---- revision behaviour through the service (C-72, AC-D7) -------------------------------

FLEX: dict[str, Any] = {
    "destination": "NRT",
    "trip_type": "round_trip",
    "date_mode": "flexible",
    "window_start": "2026-12-01",
    "window_end": "2026-12-31",
    "min_trip_days": 3,
    "max_trip_days": 5,
    "budget": 12000,
    "name": "東京",
}


def watch_state(harness: Harness, watch_id: int) -> tuple[int, int, int, tuple[int, ...]]:
    watch = harness.repo.get_watch(watch_id)
    return (
        watch.revision,
        watch.sample_offset,
        watch.consecutive_failed_scans,
        watch.spec.depart_weekdays,
    )


def update(harness: Harness, watch_id: int, **changes: Any) -> None:
    result = harness.services.watches.update(watch_id, {**FLEX, **changes})
    assert result.ok, result.errors


def dirty(harness: Harness, watch_id: int) -> None:
    """Give the watch progress and a baseline that a revision bump must reset."""
    harness.repo.record_watch_scan(
        watch_id,
        scanned_at=harness.clock(),
        sample_offset=5,
        consecutive_failed_scans=2,
        status="active",
    )
    harness.repo.save_alert_state(
        watch_id, "live", AlertStateRecord(900_000, harness.clock(), False)
    )


def test_revision_sequence(harness: Harness) -> None:  # C-72, AC-D7
    watch_id = harness.create_watch(**FLEX)
    assert watch_state(harness, watch_id) == (1, 0, 0, ALL_WEEKDAYS)
    dirty(harness, watch_id)
    update(harness, watch_id, depart_weekdays=[4])  # all -> (4,): +1 and reset
    assert watch_state(harness, watch_id) == (2, 0, 0, (4,))
    assert harness.repo.get_alert_state(watch_id, "live") == AlertStateRecord(None, None, True)
    update(harness, watch_id, depart_weekdays=[4, 5])  # (4,) -> (4,5): +1
    assert watch_state(harness, watch_id)[0] == 3
    dirty(harness, watch_id)
    update(harness, watch_id, depart_weekdays=[5, 4])  # same set, other order: no bump
    assert watch_state(harness, watch_id) == (3, 5, 2, (4, 5))
    update(harness, watch_id)  # edit without the key keeps the stored weekdays
    assert watch_state(harness, watch_id) == (3, 5, 2, (4, 5))
    update(harness, watch_id, name="改名", depart_weekdays=[4, 5])  # rename: no bump
    assert watch_state(harness, watch_id)[0] == 3
    update(harness, watch_id, depart_weekdays=list(ALL_WEEKDAYS))  # back to all: +1
    assert watch_state(harness, watch_id) == (4, 0, 0, ALL_WEEKDAYS)
    update(harness, watch_id, depart_weekdays=list(ALL_WEEKDAYS))  # all -> all: no bump
    update(harness, watch_id)
    assert watch_state(harness, watch_id)[0] == 4


def test_fixed_watch_ignores_weekdays(harness: Harness) -> None:  # C-72, C-73, AC-D6
    watch_id = harness.create_watch(depart_weekdays=[7])  # invalid value is ignored
    assert watch_state(harness, watch_id) == (1, 0, 0, ALL_WEEKDAYS)
    result = harness.services.watches.update(
        watch_id,
        {
            "destination": "NRT",
            "trip_type": "round_trip",
            "date_mode": "fixed",
            "depart_date": "2026-12-10",
            "return_date": "2026-12-15",
            "budget": 12000,
            "depart_weekdays": [4],
        },
    )
    assert result.ok and watch_state(harness, watch_id) == (1, 0, 0, ALL_WEEKDAYS)


def test_new_watch_without_key_is_all_weekdays(harness: Harness) -> None:  # C-73
    watch_id = harness.create_watch(**FLEX)
    assert harness.repo.get_watch(watch_id).spec.depart_weekdays == ALL_WEEKDAYS


# ---- validation matrix (C-73) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], WEEKDAYS_REQUIRED),
        ("4,5", WEEKDAYS_INVALID),
        ([7], WEEKDAYS_INVALID),
        ([-1], WEEKDAYS_INVALID),
        ([True], WEEKDAYS_INVALID),
        ([4.0], WEEKDAYS_INVALID),
        (["4"], WEEKDAYS_INVALID),
        ({}, WEEKDAYS_INVALID),
        (None, WEEKDAYS_INVALID),
    ],
)
def test_watch_weekdays_rejected(harness: Harness, value: Any, message: str) -> None:  # C-73
    response = harness.client.post(
        "/api/watches", json={**FLEX, "depart_weekdays": value}, headers=CLIENT_HEADERS
    )
    assert response.status_code == 422
    assert response.json()["errors"] == {"depart_weekdays": message}
    assert harness.repo.list_watches() == []


def test_watch_weekdays_duplicates_collapse() -> None:  # C-73
    outcome = validate_watch_input({**FLEX, "depart_weekdays": [4, 4]}, TODAY)
    assert outcome.spec is not None and outcome.spec.depart_weekdays == (4,)


def test_ac_d5_no_matching_day_is_422(harness: Harness) -> None:  # AC-D5, C-73
    payload = {
        **FLEX,
        "window_start": "2026-12-01",
        "window_end": "2026-12-03",
        "trip_type": "one_way",
        "depart_weekdays": [5],
    }
    response = harness.client.post("/api/watches", json=payload, headers=CLIENT_HEADERS)
    assert response.status_code == 422
    assert response.json()["errors"] == {"depart_weekdays": WEEKDAYS_NO_MATCH_WINDOW}
    assert WEEKDAYS_NO_MATCH_WINDOW == "所選日期區間內沒有符合出發星期的日子"
    assert harness.repo.list_watches() == []
    # The same check guards an edit that changes the conditions.
    watch_id = harness.create_watch(**FLEX)
    result = harness.services.watches.update(watch_id, payload)
    assert result.errors == {"depart_weekdays": WEEKDAYS_NO_MATCH_WINDOW}
    assert harness.repo.get_watch(watch_id).spec.depart_weekdays == ALL_WEEKDAYS


@pytest.mark.parametrize(
    "changes",
    [
        {"trip_type": "one_way", "depart_weekdays": [4]},
        # Single-day window on a Friday, one way.
        {
            "trip_type": "one_way",
            "window_start": "2026-12-04",
            "window_end": "2026-12-04",
            "depart_weekdays": [4],
        },
    ],
)
def test_matching_windows_are_accepted(harness: Harness, changes: dict[str, Any]) -> None:
    harness.create_watch(**{**FLEX, **changes})


def test_today_friday_only_friday_is_accepted(harness: Harness) -> None:  # C-73
    harness.clock.advance(days=5)  # 2026-10-30 (Friday) in Taipei
    harness.create_watch(
        **{
            **FLEX,
            "trip_type": "one_way",
            "window_start": "2026-10-30",
            "window_end": "2026-10-31",
            "depart_weekdays": [4],
        }
    )


def test_expired_watch_rename_has_no_weekday_error(harness: Harness) -> None:  # C-73
    payload = {**FLEX, "window_start": "2026-11-02", "window_end": "2026-11-20"}
    watch_id = harness.create_watch(**payload, depart_weekdays=[4])
    harness.clock.advance(days=40)  # 2026-12-04: the window is over
    result = harness.services.watches.update(watch_id, {**payload, "name": "新名稱"})
    assert result.ok, result.errors
    watch = harness.repo.get_watch(watch_id)
    assert watch.spec.name == "新名稱" and watch.status == "expired" and watch.revision == 1


def test_rename_when_remaining_days_miss_the_weekdays(harness: Harness) -> None:  # C-73
    payload = {
        **FLEX,
        "trip_type": "one_way",
        "window_start": "2026-11-02",
        "window_end": "2026-11-12",
    }
    watch_id = harness.create_watch(**payload, depart_weekdays=[0])  # Mondays 11/2, 11/9
    harness.clock.advance(days=16)  # 2026-11-10 (Tue): no Monday left in the window
    result = harness.services.watches.update(watch_id, {**payload, "name": "改名"})
    assert result.ok, result.errors
    assert harness.repo.get_watch(watch_id).status == "expired"


def test_comparison_ignores_weekdays() -> None:  # C-73
    raw = {
        "origin": "TPE",
        "destinations": ["NRT", "KIX"],
        "trip_type": "one_way",
        "date_input": "fixed",
        "depart_date": "2026-12-10",
    }
    plain = validate_comparison(raw, TODAY)
    with_weekdays = validate_comparison({**raw, "depart_weekdays": [7, "x"]}, TODAY)
    assert plain.spec is not None and with_weekdays.spec == plain.spec
    assert with_weekdays.errors == {}


# ---- expansion (C-74) ---------------------------------------------------------------------


def all_weekday_cases() -> list[tuple[WatchSpec, date]]:
    d = date
    return [
        (window(d(2026, 12, 1), d(2026, 12, 31)), TODAY),
        (window(d(2026, 12, 1), d(2026, 12, 31), one_way=True), TODAY),
        (window(d(2026, 11, 20), d(2027, 1, 10), 2, 9), TODAY),  # crosses month and year
        (window(d(2028, 2, 25), d(2028, 3, 5), 1, 3), d(2027, 3, 10)),  # 2028-02-29
        (window(d(2026, 10, 1), d(2026, 11, 10), 3, 4), TODAY),  # start in the past
        (window(d(2026, 12, 4), d(2026, 12, 4), one_way=True), TODAY),  # single-day window
        (window(d(2026, 12, 1), d(2026, 12, 20), 4, 4), TODAY),  # min == max
        (window(d(2026, 10, 25), d(2027, 10, 26), 1, 60), TODAY),  # 366-day window
        (window(d(2026, 10, 25), d(2027, 10, 26), one_way=True), TODAY),
        (fixed(d(2026, 12, 10), d(2026, 12, 15)), TODAY),
        (fixed(d(2026, 10, 1), None), TODAY),
    ]


@pytest.mark.parametrize(("spec", "today"), all_weekday_cases())
def test_all_weekdays_equals_fd9(spec: WatchSpec, today: date) -> None:  # C-74, AC-D2
    assert expand_pairs(spec, today) == fd9_expand_pairs(spec, today)


@pytest.mark.parametrize(("spec", "today"), all_weekday_cases())
def test_all_weekdays_path_never_filters(
    spec: WatchSpec, today: date, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-74
    def boom(*_args: Any) -> Any:
        raise AssertionError("weekday filter called on the all-weekdays path")

    monkeypatch.setattr(dates_module, "_expand_filtered", boom)
    monkeypatch.setattr(dates_module, "_first_filtered", boom)
    expand_pairs(spec, today)
    first_pair(spec, today)
    weekday_filter_leaves_nothing(spec, today)


def test_fixed_dates_ignore_weekdays_in_expansion() -> None:
    spec = fixed(date(2026, 12, 10), date(2026, 12, 15), weekdays=(0,))  # 12/10 is Thursday
    assert expand_pairs(spec, TODAY) == [DatePair(date(2026, 12, 10), date(2026, 12, 15))]


def test_ac_d3_only_friday() -> None:  # AC-D3
    pairs = expand_pairs(window(date(2026, 12, 1), date(2026, 12, 31), weekdays=(4,)), TODAY)
    assert len(pairs) == 12
    assert sorted({p.depart.day for p in pairs}) == [4, 11, 18, 25]
    assert {p.depart.weekday() for p in pairs} == {4}
    assert {p.return_date.weekday() for p in pairs if p.return_date} == {0, 1, 2}


def test_ac_d4_friday_and_saturday_and_friday_start() -> None:  # AC-D4
    pairs = expand_pairs(window(date(2026, 12, 1), date(2026, 12, 31), weekdays=(4, 5)), TODAY)
    assert len(pairs) == 24 and len({p.depart for p in pairs}) == 8
    from_friday = expand_pairs(
        window(date(2026, 12, 4), date(2026, 12, 31), weekdays=(4, 5)), TODAY
    )
    assert from_friday[0].depart == date(2026, 12, 4)


def random_specs(seed: int, count: int) -> list[tuple[WatchSpec, date]]:
    rng = random.Random(seed)
    cases = []
    for _ in range(count):
        today = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 900))
        start = today + timedelta(days=rng.randrange(-20, 300))
        end = start + timedelta(days=rng.randrange(0, 120))
        weekdays = tuple(sorted(rng.sample(ALL_WEEKDAYS, rng.randrange(1, 8))))
        if rng.random() < 0.3:
            spec = window(start, end, one_way=True, weekdays=weekdays)
        else:
            low = rng.randrange(1, 15)
            spec = window(start, end, low, low + rng.randrange(0, 10), weekdays=weekdays)
        cases.append((spec, today))
    return cases


def test_filtered_output_is_the_matching_subset() -> None:  # C-74
    for spec, today in random_specs(10, 300):
        everything = expand_pairs(replace(spec, depart_weekdays=ALL_WEEKDAYS), today)
        expected = [p for p in everything if p.depart.weekday() in spec.depart_weekdays]
        got = expand_pairs(spec, today)
        assert got == expected and got == sorted(got)


def test_first_pair_and_expiry_agree_with_expansion() -> None:  # C-74
    for spec, today in random_specs(20, 600):
        pairs = expand_pairs(spec, today)
        assert first_pair(spec, today) == (pairs[0] if pairs else None)
        assert is_expired(spec, today) == (not pairs)
        everything = expand_pairs(replace(spec, depart_weekdays=ALL_WEEKDAYS), today)
        assert weekday_filter_leaves_nothing(spec, today) == (bool(everything) and not pairs)


@pytest.mark.parametrize("low", [1, 300, 360, 366, 367, 400])
@pytest.mark.parametrize("weekdays", [(4,), (0, 6), (2, 3, 4)])
def test_filtered_first_pair_matches_expansion_beyond_the_span_cap(
    low: int, weekdays: tuple[int, ...]
) -> None:  # windows longer than validation allows, built directly
    for end_days in (366, 367, 500, 800):
        spec = window(TODAY, TODAY + timedelta(days=end_days), low, low + 5, weekdays=weekdays)
        pairs = expand_pairs(spec, TODAY)
        assert first_pair(spec, TODAY) == (pairs[0] if pairs else None), (low, end_days)
        one_way = replace(spec, trip_type="one_way", min_trip_days=None, max_trip_days=None)
        pairs = expand_pairs(one_way, TODAY)
        assert first_pair(one_way, TODAY) == (pairs[0] if pairs else None)


def test_first_pair_checks_at_most_seven_days(monkeypatch: pytest.MonkeyPatch) -> None:  # C-74
    seen: list[date] = []
    real = date.weekday

    class Spy(date):
        def weekday(self) -> int:
            seen.append(self)
            return real(self)

    start = Spy(2026, 12, 1)
    spec = window(start, date(2027, 6, 30), weekdays=(0,))
    first_pair(spec, TODAY)
    assert 0 < len(seen) <= 7
    seen.clear()
    first_pair(replace(spec, depart_weekdays=(6,)), TODAY)
    assert len(seen) <= 7


def test_sample_pairs_is_unchanged() -> None:  # C-74: diff of sample_pairs is empty
    source = Path(dates_module.__file__).read_text(encoding="utf-8")
    fd9 = '''def sample_pairs(
    pairs: list[DatePair], limit: int, offset: int
) -> tuple[list[DatePair], int, bool]:
    """Pick at most ``limit`` pairs evenly spread over ``pairs``.

    Returns ``(sampled, next_offset, truncated)``. When truncated, each scan shifts the
    picks by one position so that coverage accumulates across scans.
    """
    total = len(pairs)
    if limit <= 0:
        return [], offset, total > 0
    if total <= limit:
        return list(pairs), 0, False
    step = math.ceil(total / limit)
    shift = offset % step
    indices = sorted({((i * total) // limit + shift) % total for i in range(limit)})
    return [pairs[i] for i in indices], (shift + 1) % step, True
'''
    assert fd9 in source


def test_ac_d15_twelve_or_fewer_in_one_round() -> None:  # AC-D15
    pairs = expand_pairs(window(date(2026, 12, 1), date(2026, 12, 31), weekdays=(4,)), TODAY)
    sampled, offset, truncated = sample_pairs(pairs, 12, 0)
    assert sampled == pairs and not truncated and offset == 0
    assert all(p.depart.weekday() == 4 for p in sampled)


def test_ac_d15_rotation_covers_the_filtered_set() -> None:  # AC-D15
    pairs = expand_pairs(window(date(2026, 12, 1), date(2027, 2, 28), weekdays=(4, 5)), TODAY)
    total = len(pairs)
    assert total > 12
    offset, union = 0, set()
    for _ in range(math.ceil(total / 12)):
        sampled, offset, truncated = sample_pairs(pairs, 12, offset)
        assert truncated and all(p.depart.weekday() in (4, 5) for p in sampled)
        union.update(sampled)
    assert union == set(pairs)


def test_scan_samples_only_filtered_pairs(harness: Harness) -> None:  # AC-D15, end to end
    watch_id = harness.create_watch(**FLEX, depart_weekdays=[4])
    harness.scan(watch_id)
    departs = {q.pair.depart for q in harness.source.calls}
    assert departs == {date(2026, 12, d) for d in (4, 11, 18, 25)}
    assert len(harness.source.calls) == 12


# ---- exploration ranges (C-74) ------------------------------------------------------------


def exploration(**changes: Any) -> ExplorationSpec:
    base = ExplorationSpec("TPE", "KIX", "round_trip", 2026, 12, 4, None)
    return replace(base, **changes)


def test_range_months_and_pairs_order() -> None:  # C-74
    spec = exploration(end_year=2027, end_month=2, depart_weekdays=(4, 5))
    assert range_months(spec) == [(2026, 12), (2027, 1), (2027, 2)]
    pairs = range_pairs(spec, TODAY)
    assert pairs == sorted(pairs) and len(pairs) == 26
    assert {p.depart.weekday() for p in pairs} == {4, 5}
    assert {(p.depart.year, p.depart.month) for p in pairs} == {(2026, 12), (2027, 1), (2027, 2)}


def test_range_pairs_never_truncates() -> None:  # C-74
    spec = exploration(end_year=2027, end_month=2)
    assert len(range_pairs(spec, TODAY)) == 31 + 31 + 28


def test_month_pairs_is_the_truncated_range() -> None:  # C-74
    for spec in (
        exploration(),
        exploration(end_year=2027, end_month=2),
        exploration(depart_weekdays=(0,)),
        exploration(trip_type="one_way", trip_days=None, year=2026, month=10),
    ):
        assert month_pairs(spec, TODAY) == range_pairs(spec, TODAY)[:MAX_MONTH_CELLS]


def test_services_never_call_month_pairs() -> None:  # C-74
    for path in (SRC / "services").rglob("*.py"):
        assert "month_pairs(" not in path.read_text(encoding="utf-8"), path


def test_month_weekday_counts() -> None:
    # December 2026 starts on a Tuesday: 31 days, Tue/Wed/Thu appear five times.
    assert month_weekday_counts(2026, 12, TODAY) == (4, 5, 5, 5, 4, 4, 4)
    # Current month: only today (Sunday 10/25) and later.
    assert month_weekday_counts(2026, 10, TODAY) == (1, 1, 1, 1, 1, 1, 1)
    assert sum(month_weekday_counts(2026, 10, TODAY)) == 7
    # Beyond the 365-day horizon nothing is counted.
    assert month_weekday_counts(2027, 11, TODAY) == (0, 0, 0, 0, 0, 0, 0)
    for spec in (exploration(), exploration(trip_type="one_way", trip_days=None)):
        counts = month_weekday_counts(spec.year, spec.month, TODAY)
        assert sum(counts) >= len(range_pairs(spec, TODAY))
