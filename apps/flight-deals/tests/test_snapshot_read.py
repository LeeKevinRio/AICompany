"""Snapshot read through the protected set (ADR-0002 FD-8 Decisions 1-3, 7; C-55..C-57, C-60).

``Snapshot.build`` over ``snapshot_observations_for_watch`` must give exactly what it gives
over ``observations_for_watch`` (the full current revision). The full read is the
reference implementation here; the FD-7 retention SQL is kept verbatim as the reference
for ``retention_snapshot_runs``.
"""

from __future__ import annotations

import ast
import random
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.dates import sample_pairs
from flight_deals.domain.models import DatePair, PriceKind, PriceQuote
from flight_deals.domain.timeutil import taipei_date, to_utc_iso
from flight_deals.ports import SourceResult
from flight_deals.services.digest import taipei_midnight
from flight_deals.services.price_snapshot import Snapshot, cheapest_pairs, eligible
from flight_deals.services.scan import ScanOutcome
from flight_deals.storage.db import Database
from flight_deals.storage.repository import ObservationRecord, Repository
from tests.conftest import Harness

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
NOW = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)  # 12:00 Asia/Taipei
TODAY = taipei_date(NOW)  # 2026-10-25
MIDNIGHT = taipei_midnight(NOW)  # 2026-10-24T16:00:00Z
SECOND = timedelta(seconds=1)

# FD-7 ``retention_snapshot_runs`` SQL, verbatim (reference for C-57 retention equivalence).
FD7_RETENTION_SNAPSHOT_RUNS_SQL = (
    "WITH cur AS ("
    "  SELECT o.id, o.scan_run_id, o.watch_id, o.depart_date, o.return_date,"
    "   o.price_kind, o.currency, o.fetched_at, o.amount_minor"
    "  FROM price_observation o JOIN watch w"
    "   ON w.id = o.watch_id AND o.watch_revision = w.revision"
    "), ranked AS ("
    "  SELECT scan_run_id, depart_date,"
    "   ROW_NUMBER() OVER (PARTITION BY watch_id, depart_date, return_date,"
    "    price_kind, currency ORDER BY fetched_at DESC, id DESC) AS rn_pair,"
    "   ROW_NUMBER() OVER (PARTITION BY watch_id, price_kind, currency"
    "    ORDER BY amount_minor, id) AS rn_min"
    "  FROM cur"
    "), before_midnight AS ("
    "  SELECT scan_run_id, ROW_NUMBER() OVER (PARTITION BY watch_id, depart_date,"
    "    return_date, price_kind, currency ORDER BY fetched_at DESC, id DESC) AS rn"
    "  FROM cur WHERE fetched_at < :midnight AND depart_date >= :today"
    ")"
    " SELECT scan_run_id FROM ranked"
    "  WHERE (rn_pair <= 2 AND depart_date >= :today) OR rn_min = 1"
    " UNION SELECT scan_run_id FROM before_midnight WHERE rn = 1"
)


# ---- helpers -----------------------------------------------------------------------------


@dataclass
class Store:
    database: Database
    repo: Repository

    def conn(self) -> Any:
        return self.database.connect()


@pytest.fixture
def store(tmp_path: Path) -> Store:
    database = Database(tmp_path / "snap.db")
    database.migrate()
    return Store(database, Repository(database))


def add_watch(store: Store, *, revision: int = 1, currency: str = "TWD") -> int:
    with store.conn() as conn:
        cur = conn.execute(
            "INSERT INTO watch (name, destination, trip_type, date_mode, currency, revision,"
            " created_at, updated_at) VALUES ('w', 'NRT', 'round_trip', 'flexible', ?, ?, ?, ?)",
            (currency, revision, to_utc_iso(NOW), to_utc_iso(NOW)),
        )
        return int(cur.lastrowid or 0)


def set_revision(store: Store, watch_id: int, revision: int) -> None:
    with store.conn() as conn:
        conn.execute("UPDATE watch SET revision = ? WHERE id = ?", (revision, watch_id))


def insert_run(conn: sqlite3.Connection, watch_id: int, at: datetime, revision: int) -> int:
    cur = conn.execute(
        "INSERT INTO scan_run (watch_id, watch_revision, started_at, finished_at, status,"
        " sampled_pairs, query_results, queries_used) VALUES (?, ?, ?, ?, 'ok', '[]', '[]', 1)",
        (watch_id, revision, to_utc_iso(at), to_utc_iso(at)),
    )
    return int(cur.lastrowid or 0)


def insert_obs(
    conn: sqlite3.Connection,
    run_id: int,
    watch_id: int,
    depart: date,
    ret: date | None,
    amount: int,
    at: datetime,
    *,
    revision: int = 1,
    kind: str = "live",
    currency: str = "TWD",
) -> int:
    cur = conn.execute(
        "INSERT INTO price_observation (scan_run_id, watch_id, watch_revision, source,"
        " price_kind, depart_date, return_date, amount_minor, currency, as_of, as_of_basis,"
        " fetched_at) VALUES (?, ?, ?, 'google_flights', ?, ?, ?, ?, ?, ?, 'fetch_time', ?)",
        (
            run_id,
            watch_id,
            revision,
            kind,
            depart.isoformat(),
            ret.isoformat() if ret else None,
            amount,
            currency,
            to_utc_iso(at),
            to_utc_iso(at),
        ),
    )
    return int(cur.lastrowid or 0)


def add_run(store: Store, watch_id: int, at: datetime, *, revision: int = 1) -> int:
    with store.conn() as conn:
        return insert_run(conn, watch_id, at, revision)


def add_obs(
    store: Store,
    run_id: int,
    watch_id: int,
    depart: date,
    ret: date | None,
    amount: int,
    at: datetime,
    **kw: Any,
) -> int:
    with store.conn() as conn:
        return insert_obs(conn, run_id, watch_id, depart, ret, amount, at, **kw)


def outputs(
    observations: Sequence[ObservationRecord],
    *,
    revision: int,
    currency: str,
    today: date,
    midnight: datetime,
) -> tuple[Any, ...]:
    snapshot = Snapshot.build(observations, revision=revision, currency=currency, today=today)
    pairs = cheapest_pairs(observations, revision=revision, currency=currency, today=today)
    return (
        snapshot.cheapest,
        snapshot.delta_since_previous_run(),
        snapshot.delta_since(midnight),
        pairs,
    )


def expected_ids(
    full: Sequence[ObservationRecord],
    *,
    revision: int,
    currency: str,
    today: date,
    midnight: datetime,
) -> set[int]:
    """Decision 1 in Python: per pair the newest two plus the newest before midnight."""
    by_pair: dict[DatePair, list[ObservationRecord]] = {}
    for o in eligible(full, revision=revision, currency=currency, today=today):
        by_pair.setdefault(DatePair(o.depart_date, o.return_date), []).append(o)
    keep: set[int] = set()
    for group in by_pair.values():
        group.sort(key=lambda o: (o.fetched_at, o.id), reverse=True)
        keep |= {o.id for o in group[:2]}
        before = [o for o in group if o.fetched_at < midnight]
        if before:
            keep.add(before[0].id)
    return keep


@dataclass(frozen=True)
class Compared:
    old: tuple[Any, ...]
    new: tuple[Any, ...]
    full: list[ObservationRecord]
    rows: list[ObservationRecord]


def compare(
    store: Store,
    watch_id: int,
    *,
    revision: int = 1,
    currency: str = "TWD",
    today: date = TODAY,
    midnight: datetime = MIDNIGHT,
) -> Compared:
    full = store.repo.observations_for_watch(watch_id, revision=revision)
    rows = store.repo.snapshot_observations_for_watch(
        watch_id, revision=revision, currency=currency, today=today, midnight=midnight
    )
    args: dict[str, Any] = {
        "revision": revision,
        "currency": currency,
        "today": today,
        "midnight": midnight,
    }
    result = Compared(outputs(full, **args), outputs(rows, **args), full, rows)
    assert result.new == result.old
    assert {o.id for o in rows} == expected_ids(full, **args)
    assert rows == sorted(rows, key=lambda o: (o.fetched_at, o.id), reverse=True)
    return result


def populate(store: Store, rng: random.Random, watch_id: int) -> int:
    """Random history for one watch obeying A1 (one row per pair per run) and A2
    ((fetched_at, id) order follows scan_run_id order within the watch). Returns the
    revision to make current."""
    departs = [TODAY + timedelta(days=d) for d in range(-3, 6)]
    pairs = [DatePair(d, None) for d in departs[2:6]] + [
        DatePair(d, d + timedelta(days=k)) for d in departs for k in (2, 4)
    ]
    pairs = rng.sample(pairs, rng.randint(1, 10))
    rounds = rng.randint(0, 24)
    switch = rng.randint(0, rounds)
    t = MIDNIGHT - timedelta(hours=rng.randint(4, 60))
    with store.conn() as conn:
        _populate_rounds(conn, rng, watch_id, pairs, rounds, switch, t)
    return 2 if switch < rounds else 1


def _populate_rounds(
    conn: sqlite3.Connection,
    rng: random.Random,
    watch_id: int,
    pairs: list[DatePair],
    rounds: int,
    switch: int,
    t: datetime,
) -> None:
    for index in range(rounds):
        revision = 1 if index < switch else 2
        step = timedelta(seconds=rng.choice([0, 0, 1, 600, 3600, 3 * 3600, 6 * 3600]))
        candidate = t + step
        if t < MIDNIGHT <= candidate and rng.random() < 0.6:
            candidate = max(t, rng.choice([MIDNIGHT - SECOND, MIDNIGHT]))
        t = candidate
        run_id = insert_run(conn, watch_id, t, revision)
        for pair in rng.sample(pairs, rng.randint(0, len(pairs))):
            t += timedelta(seconds=rng.choice([0, 0, 1, 7]))
            kind = "live" if rng.random() < 0.8 else "cached"
            currency = "TWD" if rng.random() < 0.85 else "USD"
            amount = rng.choice([900_000, 950_000, 1_000_000]) + rng.randint(0, 40) * 1_000
            insert_obs(
                conn,
                run_id,
                watch_id,
                pair.depart,
                pair.return_date,
                amount,
                t,
                revision=revision,
                kind=kind,
                currency=currency,
            )


# ---- C-57 equivalence: random data ---------------------------------------------------------


@pytest.mark.parametrize("seed_block", range(4))
def test_random_histories_give_identical_snapshots(store: Store, seed_block: int) -> None:
    for seed in range(seed_block * 15, seed_block * 15 + 15):
        rng = random.Random(seed)
        watch_id = add_watch(store)
        other = add_watch(store)  # interleaved neighbour watch must never leak in
        current = populate(store, rng, watch_id)
        populate(store, rng, other)
        set_revision(store, watch_id, current)
        for revision in (1, 2):
            for currency in ("TWD", "USD"):
                for today, midnight in (
                    (TODAY, MIDNIGHT),
                    (TODAY - timedelta(days=1), MIDNIGHT - timedelta(days=1)),
                    (TODAY + timedelta(days=1), MIDNIGHT + timedelta(days=1)),
                ):
                    result = compare(
                        store,
                        watch_id,
                        revision=revision,
                        currency=currency,
                        today=today,
                        midnight=midnight,
                    )
                    assert all(o.watch_id == watch_id for o in result.rows), seed


def test_random_histories_cover_the_tricky_shapes(store: Store) -> None:
    """The generator really produces what the comparison above is meant to catch."""
    seen = dict.fromkeys(
        (
            "filtered",
            "one_way",
            "same_second_across_runs",
            "at_midnight",
            "day_delta",
            "previous_delta",
            "latest_run_not_eligible",
            "departed",
            "empty",
        ),
        0,
    )
    for seed in range(60):
        rng = random.Random(seed)
        watch_id = add_watch(store)
        current = populate(store, rng, watch_id)
        set_revision(store, watch_id, current)
        result = compare(store, watch_id, revision=current)
        usable = eligible(result.full, revision=current, currency="TWD", today=TODAY)
        seen["filtered"] += len(result.rows) < len(usable)
        seen["one_way"] += any(o.return_date is None for o in result.rows)
        stamps = [(o.fetched_at, o.scan_run_id) for o in result.full]
        seen["same_second_across_runs"] += len({s for s in stamps}) > len({t for t, _ in stamps})
        seen["at_midnight"] += any(o.fetched_at == MIDNIGHT for o in result.full)
        seen["day_delta"] += result.new[2] is not None
        seen["previous_delta"] += result.new[1] is not None
        latest = max((o.scan_run_id for o in result.full), default=None)
        seen["latest_run_not_eligible"] += bool(usable) and latest not in {
            o.scan_run_id for o in usable
        }
        seen["departed"] += any(o.depart_date < TODAY for o in result.full)
        seen["empty"] += not usable
    assert all(seen.values()), seen


def test_random_histories_survive_the_purge(store: Store) -> None:  # AC-Q11
    """Old read before the purge == new read after deleting every unprotected run."""
    watches = []
    for seed in range(100, 130):
        rng = random.Random(seed)
        watch_id = add_watch(store)
        set_revision(store, watch_id, populate(store, rng, watch_id))
        watches.append(watch_id)
    args: dict[str, Any] = {"today": TODAY, "midnight": MIDNIGHT}
    before = {}
    for watch_id in watches:
        watch_rev = current_revision(store, watch_id)
        for currency in ("TWD", "USD"):
            full = store.repo.observations_for_watch(watch_id, revision=watch_rev)
            before[watch_id, currency] = outputs(
                full, revision=watch_rev, currency=currency, **args
            )
    keep = store.repo.retention_snapshot_runs(today=TODAY, midnight=MIDNIGHT)
    with store.conn() as conn:
        all_runs = {int(r[0]) for r in conn.execute("SELECT id FROM scan_run")}
    store.repo.delete_scan_runs(sorted(all_runs - keep))
    assert store.repo.count_observations() > 0
    for watch_id in watches:
        watch_rev = current_revision(store, watch_id)
        for currency in ("TWD", "USD"):
            rows = store.repo.snapshot_observations_for_watch(
                watch_id, revision=watch_rev, currency=currency, **args
            )
            after = outputs(rows, revision=watch_rev, currency=currency, **args)
            assert after == before[watch_id, currency], (watch_id, currency)


def current_revision(store: Store, watch_id: int) -> int:
    with store.conn() as conn:
        return int(
            conn.execute("SELECT revision FROM watch WHERE id = ?", (watch_id,)).fetchone()[0]
        )


# ---- C-57 named cases (a)-(i) ---------------------------------------------------------------

P = DatePair(TODAY + timedelta(days=40), TODAY + timedelta(days=45))
Q = DatePair(TODAY + timedelta(days=41), TODAY + timedelta(days=46))
LATE = NOW - timedelta(hours=3)  # after Taipei midnight


def obs(
    store: Store, run_id: int, watch_id: int, pair: DatePair, amount: int, at: datetime, **kw: Any
) -> int:
    return add_obs(store, run_id, watch_id, pair.depart, pair.return_date, amount, at, **kw)


def test_a_same_pair_in_two_runs_compares_with_the_second_newest(store: Store) -> None:
    w = add_watch(store)
    r1 = add_run(store, w, LATE)
    first = obs(store, r1, w, P, 1_000_000, LATE)
    r2 = add_run(store, w, LATE + timedelta(hours=1))
    obs(store, r2, w, P, 900_000, LATE + timedelta(hours=1))
    result = compare(store, w)
    assert result.new[1] is not None and result.new[1].delta_minor == -100_000
    assert first in {o.id for o in result.rows}  # the baseline is the second newest


def test_b_pair_missing_from_the_latest_run_uses_its_own_newest(store: Store) -> None:
    w = add_watch(store)
    r1 = add_run(store, w, LATE)
    q_id = obs(store, r1, w, Q, 800_000, LATE)
    obs(store, r1, w, P, 1_000_000, LATE)
    r2 = add_run(store, w, LATE + timedelta(hours=1))
    obs(store, r2, w, P, 900_000, LATE + timedelta(hours=1))
    result = compare(store, w)
    cheapest, previous, _day, _pairs = result.new
    assert cheapest.id == q_id
    assert previous is not None and previous.direction == "flat" and previous.delta_minor == 0


def test_c_same_second_breaks_ties_by_id_across_runs(store: Store) -> None:
    w = add_watch(store)
    r1 = add_run(store, w, LATE)
    obs(store, r1, w, P, 1_000_000, LATE)
    r2 = add_run(store, w, LATE)  # same second, later run
    newest = obs(store, r2, w, P, 900_000, LATE)
    obs(store, r2, w, Q, 990_000, LATE)
    result = compare(store, w)
    assert result.new[0].id == newest
    assert result.new[1] is not None and result.new[1].delta_minor == -100_000


def test_d_latest_run_with_only_cached_or_other_currency(store: Store) -> None:
    w = add_watch(store)
    r1 = add_run(store, w, LATE)
    obs(store, r1, w, P, 1_000_000, LATE)
    r2 = add_run(store, w, LATE + timedelta(hours=1))
    obs(store, r2, w, P, 900_000, LATE + timedelta(hours=1))
    r3 = add_run(store, w, LATE + timedelta(hours=2))
    obs(store, r3, w, P, 500_000, LATE + timedelta(hours=2), kind="cached")
    obs(store, r3, w, Q, 30_000, LATE + timedelta(hours=2), currency="USD")
    result = compare(store, w)
    # The latest run is r2 among eligible rows: r2 vs before r2.
    assert result.new[1] is not None and result.new[1].delta_minor == -100_000
    assert {o.scan_run_id for o in result.rows} == {r1, r2}


def test_e_exactly_midnight_is_not_before_midnight(store: Store) -> None:
    w = add_watch(store)
    r1 = add_run(store, w, MIDNIGHT - SECOND)
    before = obs(store, r1, w, P, 1_000_000, MIDNIGHT - SECOND)
    r2 = add_run(store, w, MIDNIGHT)
    at_midnight = obs(store, r2, w, P, 950_000, MIDNIGHT)
    r3 = add_run(store, w, LATE)
    obs(store, r3, w, P, 900_000, LATE)
    r4 = add_run(store, w, LATE + timedelta(hours=1))
    obs(store, r4, w, P, 880_000, LATE + timedelta(hours=1))
    result = compare(store, w)
    ids = {o.id for o in result.rows}
    assert before in ids and at_midnight not in ids and len(ids) == 3
    assert result.new[2] is not None and result.new[2].delta_minor == -120_000


def test_f_pair_seen_only_after_midnight_has_no_day_delta(store: Store) -> None:
    w = add_watch(store)
    for hours in (0, 1, 2):
        run_id = add_run(store, w, LATE + timedelta(hours=hours))
        obs(store, run_id, w, P, 1_000_000 - hours * 1_000, LATE + timedelta(hours=hours))
    result = compare(store, w)
    assert result.new[2] is None and result.new[0] is not None
    assert len(result.rows) == 2


def test_g_departed_dates_and_old_revisions_are_not_returned(store: Store) -> None:
    w = add_watch(store, revision=2)
    old_run = add_run(store, w, LATE, revision=1)
    old = obs(store, old_run, w, P, 100_000, LATE, revision=1)
    run_id = add_run(store, w, LATE + timedelta(hours=1), revision=2)
    gone = DatePair(TODAY - timedelta(days=1), TODAY + timedelta(days=3))
    departed = obs(store, run_id, w, gone, 200_000, LATE + timedelta(hours=1), revision=2)
    today_pair = DatePair(TODAY, TODAY + timedelta(days=3))
    kept = obs(store, run_id, w, today_pair, 900_000, LATE + timedelta(hours=1), revision=2)
    result = compare(store, w, revision=2)
    assert {o.id for o in result.rows} == {kept}
    assert old not in {o.id for o in result.rows} and departed not in {o.id for o in result.rows}
    assert result.new[0].id == kept


def test_h_no_observations(store: Store) -> None:
    w = add_watch(store)
    add_run(store, w, LATE)
    result = compare(store, w)
    assert result.rows == []
    assert result.new == (None, None, None, [])


def test_i_a_pair_with_many_rows_returns_at_most_three(store: Store) -> None:
    w = add_watch(store)
    for hours in range(-6, 6):
        at = MIDNIGHT + timedelta(hours=hours)
        run_id = add_run(store, w, at)
        obs(store, run_id, w, P, 1_000_000 + hours * 1_000, at)
    result = compare(store, w)
    assert len(result.full) == 12
    assert len(result.rows) == 3


# ---- A1 guard ------------------------------------------------------------------------------


QUOTE_MIX: tuple[tuple[PriceKind, int], ...] = (
    ("live", 1_100_000),
    ("live", 1_000_000),
    ("cached", 900_000),
    ("live", 1_000_000),
)


def test_scan_writes_at_most_one_row_per_pair_per_run(harness: Harness) -> None:  # A1
    """Several itineraries per query (live and cached, different prices) and rotating
    samples that revisit the same pairs: still one observation per pair per run."""

    def many(query: Any) -> SourceResult:
        now = harness.clock()
        quotes = tuple(
            PriceQuote(
                source="google_flights",
                price_kind=kind,
                depart_date=query.pair.depart,
                return_date=query.pair.return_date,
                amount_minor=amount,
                currency=query.currency,
                as_of=now,
                as_of_basis="fetch_time",
                fetched_at=now,
                carrier="BR",
                stops=0,
                duration_minutes=180,
            )
            for kind, amount in QUOTE_MIX
        )
        return SourceResult("google_flights", "ok", now, quotes=quotes)

    harness.source.handler = many
    harness.services.settings.update({"max_pairs_per_scan": 3})
    watch_id = harness.create_watch(
        date_mode="flexible",
        depart_date="",
        return_date="",
        window_start="2026-12-01",
        window_end="2026-12-06",
        min_trip_days=2,
        max_trip_days=3,
    )
    for _ in range(8):
        harness.scan(watch_id)
        harness.clock.advance(hours=6)
    with harness.assembly.database.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
        repeated = conn.execute(
            "SELECT scan_run_id, depart_date, return_date, COUNT(*) FROM price_observation"
            " GROUP BY scan_run_id, depart_date, return_date HAVING COUNT(*) > 1"
        ).fetchall()
        revisited = conn.execute(
            "SELECT COUNT(*) FROM (SELECT 1 FROM price_observation"
            " GROUP BY depart_date, return_date HAVING COUNT(*) > 1)"
        ).fetchone()[0]
    assert total == 8 * 3
    assert [tuple(r) for r in repeated] == []
    assert revisited > 0  # the rotation did come back to earlier pairs


def test_sample_pairs_never_repeats_a_pair() -> None:  # A1 (the sampler side)
    base = date(2026, 12, 1)
    for total in range(0, 40):
        pairs = [DatePair(base + timedelta(days=i)) for i in range(total)]
        for limit in range(0, 15):
            for offset in range(0, 12):
                sampled, _next, _cut = sample_pairs(pairs, limit, offset)
                assert len(sampled) == len(set(sampled)), (total, limit, offset)


# ---- C-57 retention equivalence ------------------------------------------------------------


def fd7_runs(store: Store, today: date, midnight: datetime) -> set[int]:
    with store.conn() as conn:
        rows = conn.execute(
            FD7_RETENTION_SNAPSHOT_RUNS_SQL,
            {"today": today.isoformat(), "midnight": to_utc_iso(midnight)},
        ).fetchall()
    return {int(r[0]) for r in rows}


def test_retention_runs_match_the_fd7_sql(store: Store) -> None:
    for seed in range(200, 240):
        rng = random.Random(seed)
        watch_id = add_watch(store)
        set_revision(store, watch_id, populate(store, rng, watch_id))
    add_watch(store)  # a watch without observations
    for shift in (-1, 0, 1, 2):
        today = TODAY + timedelta(days=shift)
        midnight = MIDNIGHT + timedelta(days=shift)
        expected = fd7_runs(store, today, midnight)
        assert expected
        assert store.repo.retention_snapshot_runs(today=today, midnight=midnight) == expected


# ---- C-55 call sites and SQL counts ----------------------------------------------------------


def test_snapshot_read_runs_one_statement(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    w = add_watch(store)
    run_id = add_run(store, w, LATE)
    obs(store, run_id, w, P, 1_000_000, LATE)
    statements: list[str] = []
    real = store.database.connect

    @contextmanager
    def tracing() -> Iterator[sqlite3.Connection]:
        with real() as conn:
            conn.set_trace_callback(statements.append)
            yield conn

    monkeypatch.setattr(store.database, "connect", tracing)
    rows = store.repo.snapshot_observations_for_watch(
        w, revision=1, currency="TWD", today=TODAY, midnight=MIDNIGHT
    )
    assert len(rows) == 1
    queries = [s for s in statements if not s.lstrip().upper().startswith("PRAGMA")]
    assert len(queries) == 1 and "price_observation" in queries[0], statements


def spy(repo: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"snapshot": 0, "full": 0}
    real_snapshot = repo.snapshot_observations_for_watch
    real_full = repo.observations_for_watch

    def snapshot(*args: Any, **kwargs: Any) -> Any:
        calls["snapshot"] += 1
        return real_snapshot(*args, **kwargs)

    def full(*args: Any, **kwargs: Any) -> Any:
        calls["full"] += 1
        return real_full(*args, **kwargs)

    monkeypatch.setattr(repo, "snapshot_observations_for_watch", snapshot)
    monkeypatch.setattr(repo, "observations_for_watch", full)
    return calls


def test_twenty_watches_list_page_is_one_plus_twenty(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-55, AC-Q7
    ids = [harness.create_watch(budget=12000 + i) for i in range(20)]
    for watch_id in ids[:5]:
        harness.scan(watch_id)
    database = harness.repo.db
    real = database.connect
    connects: list[int] = []

    @contextmanager
    def counting() -> Iterator[Any]:
        connects.append(1)
        with real() as conn:
            yield conn

    calls = spy(harness.repo, monkeypatch)
    monkeypatch.setattr(database, "connect", counting)
    harness.services.views.list_page()
    assert len(connects) == 1 + 20
    assert calls == {"snapshot": 20, "full": 0}


def test_digest_list_watch_and_scan_reply_use_the_snapshot_read(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-55, AC-Q8
    ids = [harness.create_watch(budget=12000 + i) for i in range(4)]
    for watch_id in ids:
        harness.scan(watch_id)
    commands = harness.services.commands
    assert commands is not None
    now = harness.clock.now
    calls = spy(harness.repo, monkeypatch)
    harness.services.digest.compose(now)
    assert calls == {"snapshot": 4, "full": 0}
    commands.list_text(now)
    assert calls == {"snapshot": 8, "full": 0}
    watch = harness.repo.get_watch(ids[0])
    commands.watch_text(watch, now)  # /watch: top three via top_prices
    assert calls == {"snapshot": 9, "full": 0}
    run = harness.repo.latest_finished_scan_run(ids[0])
    commands.scan_result_text(ids[0], ScanOutcome(ids[0], "ok", run.id))  # /scan reply
    assert calls == {"snapshot": 10, "full": 0}
    harness.services.views.detail_page(ids[0])  # the detail page keeps the full read
    assert calls["full"] == 1 and calls["snapshot"] == 10


# ---- C-56 / C-60 single definition and module boundary --------------------------------------


def py_sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_snapshot_window_is_defined_once() -> None:  # C-56
    hits = {
        p.relative_to(SRC).as_posix(): p.read_text(encoding="utf-8").count("WINDOW snap AS")
        for p in py_sources()
    }
    assert {k: v for k, v in hits.items() if v} == {"storage/repository.py": 1}
    over = [
        p.relative_to(SRC).as_posix()
        for p in sorted(SRC.rglob("*"))
        if p.is_file()
        and p.suffix in {".py", ".sql", ".html", ".js"}
        and re.search(r"OVER \(|OVER snap", p.read_text(encoding="utf-8"))
    ]
    assert over == ["storage/repository.py"]


def _repository_tree() -> ast.Module:
    return ast.parse((SRC / "storage" / "repository.py").read_text(encoding="utf-8"))


def _functions(tree: ast.AST) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]


def test_keep_select_takes_only_module_scope_constants() -> None:  # C-56
    tree = _repository_tree()
    assert [f.name for f in _functions(tree)].count("_snapshot_keep_select") == 1
    constants = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_snapshot_keep_select"
    ]
    assert len(calls) == 2
    for call in calls:
        assert not call.keywords and len(call.args) == 1
        arg = call.args[0]
        assert isinstance(arg, ast.Name), ast.dump(arg)
        assert arg.id.startswith("_SNAPSHOT_SCOPE_") and arg.id in constants, arg.id
    scopes = {call.args[0].id for call in calls if isinstance(call.args[0], ast.Name)}
    assert scopes == {"_SNAPSHOT_SCOPE_WATCH", "_SNAPSHOT_SCOPE_RETENTION"}


def test_both_snapshot_queries_are_built_from_the_keep_select() -> None:  # C-56
    from flight_deals.storage import repository

    keep = repository._snapshot_keep_select(repository._SNAPSHOT_SCOPE_WATCH)
    assert keep in repository.SNAPSHOT_OBSERVATIONS_SQL
    tree = _repository_tree()
    [method] = [f for f in _functions(tree) if f.name == "retention_snapshot_runs"]
    assert "_SNAPSHOT_SCOPE_RETENTION" in ast.unparse(method)
    [read] = [f for f in _functions(tree) if f.name == "snapshot_observations_for_watch"]
    assert "SNAPSHOT_OBSERVATIONS_SQL" in ast.unparse(read)


def test_rn_min_only_in_retention_snapshot_runs() -> None:  # C-56
    tree = _repository_tree()
    owners = {f.name for f in _functions(tree) if "rn_min" in ast.unparse(f)}
    assert owners == {"retention_snapshot_runs"}
    module_level = [
        ast.unparse(node)
        for node in tree.body
        if not isinstance(node, ast.FunctionDef | ast.ClassDef)
    ]
    assert not [text for text in module_level if "rn_min" in text]


def test_only_the_detail_page_reads_every_observation() -> None:  # C-55
    owners: list[str] = []
    for path in py_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in _functions(tree):
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "observations_for_watch"
                ):
                    owners.append(f"{path.relative_to(SRC).as_posix()}::{func.name}")
    assert owners == ["services/views.py::detail_page"]


def _docstring_nodes(tree: ast.Module) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def test_services_hold_no_snapshot_sql() -> None:  # C-60
    """No string literal in ``services`` names the observation table or a window clause.
    Docstrings may mention the table; identifiers such as ``FAILED_SCAN_WINDOW`` are not
    SQL, so whole words only."""
    banned = re.compile(r"\bprice_observation\b|\bOVER\b|\bWINDOW\b")
    offenders = []
    for path in sorted((SRC / "services").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docs
                and banned.search(node.value)
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_retention_service_has_no_sql() -> None:  # C-60
    text = (SRC / "services" / "retention.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(SELECT|DELETE|INSERT|UPDATE)\b", text)


def test_sqlite_supports_window_and_lag() -> None:  # Decision 7 (local: 3.45.1)
    assert sqlite3.sqlite_version_info >= (3, 25, 0), sqlite3.sqlite_version
