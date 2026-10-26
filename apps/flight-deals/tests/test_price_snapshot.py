"""Snapshot minimum and change versus previous run / previous day (FD-4 FR-TR, C-34)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from flight_deals.domain.models import PriceKind
from flight_deals.services.price_snapshot import Snapshot, latest_per_pair
from flight_deals.storage.repository import ObservationRecord
from tests.conftest import Harness

T0 = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)
TODAY = date(2026, 10, 25)


def obs(
    obs_id: int,
    run: int,
    depart: str,
    amount: int,
    *,
    at: datetime = T0,
    revision: int = 1,
    kind: PriceKind = "live",
    currency: str = "TWD",
    ret: str | None = None,
) -> ObservationRecord:
    return ObservationRecord(
        id=obs_id,
        scan_run_id=run,
        watch_id=1,
        watch_revision=revision,
        source="google_flights",
        price_kind=kind,
        depart_date=date.fromisoformat(depart),
        return_date=date.fromisoformat(ret) if ret else None,
        amount_minor=amount * 100,
        currency=currency,
        as_of=at,
        as_of_basis="fetch_time",
        fetched_at=at,
        carrier=None,
        stops=None,
        duration_minutes=None,
    )


def snap(observations: list[ObservationRecord], today: date = TODAY) -> Snapshot:
    return Snapshot.build(observations, revision=1, currency="TWD", today=today)


def test_latest_per_pair_keeps_newest() -> None:
    older = obs(1, 1, "2026-12-10", 9000, at=T0)
    newer = obs(2, 2, "2026-12-10", 9500, at=T0 + timedelta(hours=6))
    assert latest_per_pair([newer, older]) == {latest_per_pair([older]).popitem()[0]: newer}


def test_snapshot_filters_revision_kind_currency_and_departed_dates() -> None:
    s = snap(
        [
            obs(1, 1, "2026-10-24", 1000),  # departed yesterday
            obs(2, 1, "2026-12-10", 2000, revision=0),
            obs(3, 1, "2026-12-11", 3000, kind="cached"),
            obs(4, 1, "2026-12-12", 4000, currency="USD"),
            obs(5, 1, "2026-12-13", 9000),
        ]
    )
    assert s.cheapest is not None and s.cheapest.id == 5


def test_departed_date_dropped_when_day_changes() -> None:
    observations = [obs(1, 1, "2026-10-26", 5000), obs(2, 1, "2026-12-10", 9000)]
    assert snap(observations).cheapest is not None
    assert snap(observations).cheapest.id == 1  # type: ignore[union-attr]
    later = snap(observations, today=date(2026, 10, 27))
    assert later.cheapest is not None and later.cheapest.id == 2


@pytest.mark.parametrize(
    ("before", "after", "direction", "delta"),
    [(10_000, 9_400, "down", -600), (9_000, 9_450, "up", 450), (9_000, 9_000, "flat", 0)],
)
def test_delta_since_previous_run(before: int, after: int, direction: str, delta: int) -> None:
    s = snap(
        [
            obs(1, 1, "2026-12-10", before),
            obs(2, 2, "2026-12-10", after, at=T0 + timedelta(hours=6)),
        ]
    )
    change = s.delta_since_previous_run()
    assert change is not None
    assert (change.direction, change.delta_minor) == (direction, delta * 100)
    assert isinstance(change.delta_minor, int)


def test_flexible_rotation_compares_snapshots_not_rounds() -> None:
    # Round 1 sampled 12/10 (9,000); round 2 sampled 12/20 (12,000). The snapshot minimum
    # stays 9,000 (12/10 is still the newest price for that pair), so the change is flat.
    s = snap(
        [
            obs(1, 1, "2026-12-10", 9_000),
            obs(2, 2, "2026-12-20", 12_000, at=T0 + timedelta(hours=6)),
        ]
    )
    change = s.delta_since_previous_run()
    assert change is not None and change.direction == "flat"


def test_no_baseline_cases() -> None:
    assert snap([]).delta_since_previous_run() is None
    assert snap([obs(1, 1, "2026-12-10", 9000)]).delta_since_previous_run() is None
    # Previous run only had an old revision (AC-TR4): no baseline.
    s = Snapshot.build(
        [obs(1, 1, "2026-12-10", 9000, revision=1), obs(2, 2, "2026-12-10", 8000, revision=2)],
        revision=2,
        currency="TWD",
        today=TODAY,
    )
    assert s.delta_since_previous_run() is None


def test_delta_since_moment_uses_snapshot_before_it() -> None:
    midnight = datetime(2026, 10, 24, 16, 0, tzinfo=UTC)  # 2026-10-25 00:00 Asia/Taipei
    s = snap(
        [
            obs(1, 1, "2026-12-10", 10_000, at=midnight - timedelta(hours=2)),
            obs(2, 2, "2026-12-10", 9_400, at=midnight + timedelta(hours=2)),
        ]
    )
    change = s.delta_since(midnight)
    assert change is not None and change.delta_minor == -60_000
    assert snap([obs(2, 2, "2026-12-10", 9_400, at=midnight)]).delta_since(midnight) is None


# ---- list page ----------------------------------------------------------------------


def row_of(harness: Harness, watch_id: int) -> dict[str, Any]:
    rows = harness.services.views.list_page()["watches"]
    return next(r for r in rows if r["id"] == watch_id)


def test_list_delta_down_up_flat_and_none(harness: Harness) -> None:  # AC-TR1..TR3
    watch_id = harness.create_watch()
    assert row_of(harness, watch_id)["delta"] is None
    harness.source.default_price = 10_000
    harness.scan(watch_id)
    assert row_of(harness, watch_id)["delta"] is None  # only one round
    harness.clock.advance(hours=6)
    harness.source.default_price = 9_400
    harness.scan(watch_id)
    assert row_of(harness, watch_id)["delta"] == {"direction": "down", "amount_label": "TWD 600"}
    harness.clock.advance(hours=6)
    harness.source.default_price = 9_850
    harness.scan(watch_id)
    assert row_of(harness, watch_id)["delta"] == {"direction": "up", "amount_label": "TWD 450"}
    harness.clock.advance(hours=6)
    harness.scan(watch_id)
    assert row_of(harness, watch_id)["delta"]["direction"] == "flat"
    assert harness.client.get("/").status_code == 200


def test_list_delta_resets_after_revision_change(harness: Harness) -> None:  # AC-TR4
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    harness.clock.advance(hours=6)
    harness.scan(watch_id)
    result = harness.services.watches.update(
        watch_id,
        {
            "destination": "HND",
            "trip_type": "round_trip",
            "date_mode": "fixed",
            "depart_date": "2026-12-10",
            "return_date": "2026-12-15",
            "budget": 12000,
        },
    )
    assert result.ok
    harness.clock.advance(hours=6)
    harness.scan(watch_id)
    assert row_of(harness, watch_id)["delta"] is None


def test_list_min_price_excludes_departed_dates(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    assert row_of(harness, watch_id)["min_price"] == "TWD 10,000"
    harness.clock.now = datetime(2026, 12, 10, 16, 1, tzinfo=UTC)  # 12/11 Asia/Taipei
    row = row_of(harness, watch_id)
    assert row["min_price"] is None and row["delta"] is None


def test_list_page_query_count_unchanged(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = [harness.create_watch(budget=12000 + i) for i in range(3)]
    for watch_id in ids:
        harness.scan(watch_id)
        harness.clock.advance(hours=6)
        harness.scan(watch_id)
    database = harness.repo.db
    real = database.connect
    calls: list[int] = []

    @contextmanager
    def counting() -> Iterator[Any]:
        calls.append(1)
        with real() as conn:
            yield conn

    monkeypatch.setattr(database, "connect", counting)
    harness.services.views.list_page()
    # FD-3 baseline: list_watches + one observations query per watch.
    assert len(calls) == 1 + len(ids)


def test_detail_page_unchanged_by_snapshot_filter(harness: Harness) -> None:  # AC-TR6
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    data = harness.services.views.detail_page(watch_id)
    assert data is not None and data["top"] and data["top"][0]["amount_text"] == "TWD 10,000"
