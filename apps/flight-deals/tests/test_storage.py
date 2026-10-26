"""Storage: migrations, constraints, cascades, UTC/int storage (C-9, C-13, FR-A8)."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from flight_deals.domain.models import DatePair, PriceQuote, WatchSpec
from flight_deals.storage.db import Database, available_migrations
from flight_deals.storage.repository import Repository
from tests.conftest import FakeClock


def make_repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "s.db")
    db.migrate()
    return Repository(db)


def a_spec() -> WatchSpec:
    return WatchSpec(
        name="w",
        origin="TPE",
        destination="NRT",
        trip_type="round_trip",
        date_mode="fixed",
        depart_date=date(2026, 12, 10),
        return_date=date(2026, 12, 15),
        window_start=None,
        window_end=None,
        min_trip_days=None,
        max_trip_days=None,
        max_stops=None,
        budget_amount_minor=1_200_000,
    )


def test_migrations_are_numbered_and_idempotent(tmp_path: Path) -> None:
    versions = [v for v, _ in available_migrations()]
    assert versions == sorted(versions) and versions[0] == 1
    db = Database(tmp_path / "m.db")
    assert db.migrate() == versions[-1]
    assert db.migrate() == versions[-1]
    with db.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_dedupe_key_unique(tmp_path: Path, clock: FakeClock) -> None:  # C-9
    repo = make_repo(tmp_path)
    kwargs = dict(
        watch_id=None,
        kind="ops_source_failure",
        rule=None,
        price_kind=None,
        observation_id=None,
        channel="telegram",
        dedupe_key="ops:google_flights:2026-10-25",
        message_text="x",
        created_at=clock(),
    )
    assert repo.insert_notification(**kwargs) is not None  # type: ignore[arg-type]
    assert repo.insert_notification(**kwargs) is None  # type: ignore[arg-type]
    with repo.db.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO notification (kind, dedupe_key, status, message_text, created_at)"
            " VALUES ('test', 'ops:google_flights:2026-10-25', 'pending', 'x', 'now')"
        )


def test_delete_watch_cascades_history(tmp_path: Path, clock: FakeClock) -> None:  # FR-A8
    repo = make_repo(tmp_path)
    watch_id = repo.insert_watch(a_spec(), clock())
    run_id = repo.insert_scan_run(
        watch_id=watch_id,
        revision=1,
        trigger="manual",
        started_at=clock(),
        sampled_pairs=[DatePair(date(2026, 12, 10), date(2026, 12, 15))],
        total_pairs=1,
        limit_reached=False,
    )
    repo.insert_observation(
        scan_run_id=run_id,
        watch_id=watch_id,
        revision=1,
        quote=PriceQuote(
            source="google_flights",
            price_kind="live",
            depart_date=date(2026, 12, 10),
            return_date=date(2026, 12, 15),
            amount_minor=900_000,
            currency="TWD",
            as_of=clock(),
            as_of_basis="fetch_time",
            fetched_at=clock(),
            carrier="X",
            stops=0,
            duration_minutes=100,
        ),
    )
    assert repo.count_observations(watch_id) == 1
    assert repo.delete_watch(watch_id)
    assert repo.count_observations() == 0
    with repo.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM scan_run").fetchone()[0] == 0


def test_stored_timestamps_are_utc_and_amounts_integers(
    tmp_path: Path, clock: FakeClock
) -> None:  # C-13
    repo = make_repo(tmp_path)
    watch_id = repo.insert_watch(a_spec(), clock())
    with repo.db.connect() as conn:
        row = conn.execute(
            "SELECT created_at, depart_date, budget_amount_minor, typeof(budget_amount_minor) AS t"
            " FROM watch WHERE id = ?",
            (watch_id,),
        ).fetchone()
    assert row["created_at"].endswith("+00:00")
    assert row["depart_date"] == "2026-12-10"
    assert row["t"] == "integer"


def test_amount_must_be_positive(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with repo.db.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO price_observation (scan_run_id, watch_id, watch_revision, source,"
            " price_kind, depart_date, amount_minor, currency, as_of, as_of_basis, fetched_at)"
            " VALUES (1, 1, 1, 's', 'live', '2026-12-10', 0, 'TWD', 'x', 'fetch_time', 'x')"
        )
