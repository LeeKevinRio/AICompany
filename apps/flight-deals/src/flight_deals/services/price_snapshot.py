"""Price snapshot and change since a baseline (ADR-0002 FD-4 Decision 5, C-34).

Pure Python over observations that are already loaded; no I/O. A snapshot keeps only the
watch's current revision, live prices, the watch currency and departure dates from today
(Asia/Taipei) on, then the newest observation of each date pair. Flexible windows sample
different dates each round, so per-round minimums are never compared with each other;
only snapshot minimums are. Changes are integer minor units plus a direction.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from flight_deals.domain.models import DatePair
from flight_deals.storage.repository import ObservationRecord

Direction = Literal["up", "down", "flat"]


@dataclass(frozen=True)
class PriceDelta:
    """Current snapshot minimum minus the baseline snapshot minimum."""

    delta_minor: int
    direction: Direction
    currency: str


def latest_per_pair(observations: Iterable[ObservationRecord]) -> dict[DatePair, ObservationRecord]:
    """Newest observation (by ``fetched_at``, then id) of each date pair."""
    latest: dict[DatePair, ObservationRecord] = {}
    for obs in observations:
        key = DatePair(obs.depart_date, obs.return_date)
        current = latest.get(key)
        if current is None or (obs.fetched_at, obs.id) > (current.fetched_at, current.id):
            latest[key] = obs
    return latest


def eligible(
    observations: Iterable[ObservationRecord], *, revision: int, currency: str, today: date
) -> list[ObservationRecord]:
    """Observations a snapshot may use (current revision, live, currency, not departed)."""
    return [
        o
        for o in observations
        if o.watch_revision == revision
        and o.price_kind == "live"
        and o.currency == currency
        and o.depart_date >= today
    ]


def snapshot_min(observations: Iterable[ObservationRecord]) -> ObservationRecord | None:
    """Cheapest entry of the snapshot built from already-eligible observations."""
    return min(
        latest_per_pair(observations).values(),
        key=lambda o: (o.amount_minor, o.depart_date, o.return_date or o.depart_date),
        default=None,
    )


def cheapest_pairs(
    observations: Iterable[ObservationRecord], *, revision: int, currency: str, today: date
) -> list[ObservationRecord]:
    """Newest observation per pair among the snapshot-eligible ones, cheapest first.

    The detail page's top list and ``/watch`` both use this, so neither ever shows a
    departed date, a cached price or another currency (FD-7 risk review R1).
    """
    usable = eligible(observations, revision=revision, currency=currency, today=today)
    # Same tie-break order as ``snapshot_min`` so both agree on the cheapest pair.
    return sorted(
        latest_per_pair(usable).values(),
        key=lambda o: (o.amount_minor, o.depart_date, o.return_date or o.depart_date),
    )


def _delta(
    current: ObservationRecord | None, baseline: ObservationRecord | None
) -> PriceDelta | None:
    if current is None or baseline is None:
        return None
    diff = current.amount_minor - baseline.amount_minor
    direction: Direction = "up" if diff > 0 else ("down" if diff < 0 else "flat")
    return PriceDelta(diff, direction, current.currency)


def _delta_where(
    observations: Sequence[ObservationRecord],
    current: ObservationRecord | None,
    keep: Callable[[ObservationRecord], bool],
) -> PriceDelta | None:
    return _delta(current, snapshot_min([o for o in observations if keep(o)]))


@dataclass(frozen=True)
class Snapshot:
    """Snapshot minimum of one watch plus the eligible observations behind it."""

    observations: tuple[ObservationRecord, ...]
    cheapest: ObservationRecord | None

    @classmethod
    def build(
        cls,
        observations: Iterable[ObservationRecord],
        *,
        revision: int,
        currency: str,
        today: date,
    ) -> Snapshot:
        usable = tuple(eligible(observations, revision=revision, currency=currency, today=today))
        return cls(usable, snapshot_min(usable))

    def delta_since_previous_run(self) -> PriceDelta | None:
        """List page: versus the snapshot as it was before the latest scan run (R)."""
        if not self.observations:
            return None
        latest_run = max(o.scan_run_id for o in self.observations)
        return _delta_where(self.observations, self.cheapest, lambda o: o.scan_run_id < latest_run)

    def delta_since(self, moment: datetime) -> PriceDelta | None:
        """Digest: versus the snapshot built from observations fetched before ``moment``."""
        return _delta_where(self.observations, self.cheapest, lambda o: o.fetched_at < moment)
