"""Migration 0009: flight details on the three price tables (ADR-0002 FD-12, C-95)."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.models import DatePair, PriceQuote
from flight_deals.storage import db as db_module
from flight_deals.storage.db import Database, backup_path, needs_foreign_keys_off
from flight_deals.storage.repository import CellUpdate, Repository
from tests.test_migration_0003 import ORIGINAL_MIGRATIONS, only_up_to
from tests.test_migration_0007 import insert_cell as insert_comparison_cell
from tests.test_migration_0008 import all_tables, build_v7_db, snapshot

TABLES = ("price_observation", "exploration_cell", "comparison_cell")
COLUMNS = ("flight_numbers", "arrive_time", "arrive_day_offset", "route_airports")
NOW = datetime(2026, 10, 25, 4, tzinfo=UTC)
MIGRATIONS = Path(db_module.__file__).parent / "migrations"

# sha256 (LF line endings) of 0001..0008 as released in v0.1.0 (C-95: diff empty).
EARLIER = {
    "0001_initial.sql": "ffda1bf14ede879c44ad07b940203130ac4712247eace4b72656c86432f1d296",
    "0002_notification_kind_daily_digest.sql": (
        "01300b44b8d962b4d6311d13d8c634c9d32a47cc458b6d32cb9bc4a877318f04"
    ),
    "0003_watch_trip_options.sql": (
        "70e6f25c8190e84241581fc8b6fbb691a0de1e0b516ae61a79cc2a5f97139d02"
    ),
    "0004_exploration.sql": "fc5d77890f7c4cca570d88bf11a1a8f5e81357a35401140a7f5bc04ade652bd1",
    "0005_notification_kinds_and_indexes.sql": (
        "c79e4cf906603ee158cd9e1349fa897960494426f8766ffffaf5938fb4a340d2"
    ),
    "0006_snapshot_index.sql": "eb5085dd2a8f1e7b9515f1755ed2902daea4cdacee4c04b3a4bb5315d603c70a",
    "0007_comparison.sql": "2917c11d223dbaf6187446731c839dcea48d4f7bd71b6f682b4aa606e701d3ab",
    "0008_depart_weekdays_and_exploration_range.sql": (
        "1ddad19b0d5099e635868598b998cf06ab54972b4087d58e0a9e0ad440f22421"
    ),
}


def sql_0009() -> str:
    return dict(ORIGINAL_MIGRATIONS())[9]


def statements(sql: str) -> list[str]:
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    return [" ".join(s.split()) for s in code.split(";") if s.strip()]


def build_v8_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    """v8 database with data: observations of two watches, ok / no_data / error /
    skipped exploration cells and ok / no_data comparison cells."""
    database = build_v7_db(path, monkeypatch)
    assert database.migrate() == 8
    with database.connect() as conn:
        insert_comparison_cell(conn, 1, position=1, destination="OSA", status="no_data")
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(9))
    return database


def migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    database = build_v8_db(tmp_path / "fd.db", monkeypatch)
    assert database.migrate() == 9
    return database


# ---- the SQL text itself ------------------------------------------------------------------------


def test_0009_is_twelve_add_columns_without_marker() -> None:  # C-95
    names = sorted(p.name for p in MIGRATIONS.glob("0009_*.sql"))
    assert names == ["0009_flight_details.sql"]
    sql = sql_0009()
    assert not needs_foreign_keys_off(sql)
    assert "foreign_keys" not in sql.lower()
    found = statements(sql)
    assert len(found) == 12
    expected = [(t, c) for t in TABLES for c in COLUMNS]
    for stmt, (table, column) in zip(found, expected, strict=True):
        assert stmt.startswith(f"ALTER TABLE {table} ADD COLUMN {column} "), stmt
    upper = "\n".join(found).upper()
    for banned in ("CREATE ", "DROP ", "RENAME", "INDEX", "UPDATE ", "DELETE ", "INSERT "):
        assert banned not in upper, banned


def test_arrive_time_check_copies_0003_depart_time() -> None:  # C-95
    sql_3 = dict(ORIGINAL_MIGRATIONS())[3]
    start = sql_3.index("CHECK (depart_time IS NULL")
    check_3 = sql_3[start : sql_3.index(";", start)]
    copied = check_3.replace("depart_time", "arrive_time")
    flat = " ".join(sql_0009().split())
    assert flat.count(" ".join(copied.split())) == 3


def test_earlier_migrations_are_unchanged() -> None:  # C-95
    names = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    assert names == [*EARLIER, "0009_flight_details.sql", "0010_overhead_bin_excluded.sql"]
    for name, digest in EARLIER.items():
        data = (MIGRATIONS / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, name


# ---- upgrading a v8 database with data -----------------------------------------------------------


def test_v8_data_survives_new_columns_are_null_and_backup_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-95
    database = build_v8_db(tmp_path / "flight-deals.db", monkeypatch)
    before = snapshot(database)
    assert all(len(before[t]) >= 2 for t in TABLES)
    statuses = {r["status"] for r in before["exploration_cell"]}
    assert {"ok", "no_data"} <= statuses
    assert {r["status"] for r in before["comparison_cell"]} >= {"ok", "no_data"}
    assert database.migrate() == 9
    after = snapshot(database)
    assert set(after) == set(before)
    for table, rows in before.items():
        if table == "schema_version":
            continue
        assert len(after[table]) == len(rows), table
        for old, new in zip(rows, after[table], strict=True):
            assert {k: new[k] for k in old} == old, table
            if table in TABLES:
                assert set(new) - set(old) == set(COLUMNS)
                assert all(new[c] is None for c in COLUMNS)
            else:
                assert new == old, table
    with database.connect() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert all_tables(conn) == sorted(before)
    backup = backup_path(database.path, 9)
    assert backup == tmp_path / "flight-deals.pre-v9.db" and backup.is_file()
    assert Database(backup).schema_version() == 8
    with sqlite3.connect(backup) as conn:
        assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == len(
            before["price_observation"]
        )


def test_new_db_is_v10_without_backup(tmp_path: Path) -> None:  # C-95, FD-15 adds 0010
    database = Database(tmp_path / "fresh.db")
    assert database.migrate() == 10
    assert sorted(p.name for p in tmp_path.glob("*.db")) == ["fresh.db"]


# ---- CHECK constraints ---------------------------------------------------------------------


def _write(conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    sets = ", ".join(f"{k} = ?" for k in values)
    conn.execute(
        f"UPDATE {table} SET {sets} WHERE rowid = (SELECT MIN(rowid) FROM {table})",
        list(values.values()),
    )


REJECTED: list[dict[str, Any]] = [
    {"flight_numbers": "br184"},
    {"flight_numbers": "BR184,"},
    {"flight_numbers": ",BR184"},
    {"flight_numbers": "BR184,,JL99"},
    {"flight_numbers": "BR 184"},
    {"flight_numbers": "BR"},
    {"arrive_time": "7:55", "arrive_day_offset": 0},
    {"arrive_time": "24:00", "arrive_day_offset": 0},
    {"arrive_time": "07:55", "arrive_day_offset": 4},
    {"arrive_time": "07:55", "arrive_day_offset": -2},
    {"arrive_time": "07:55", "arrive_day_offset": 1.5},
    {"arrive_time": "07:55"},
    {"arrive_day_offset": 0},
    {"route_airports": "TPE"},
    {"route_airports": "TPE,NR"},
    {"route_airports": "tpe,nrt"},
    {"route_airports": "TPE;NRT"},
    {"route_airports": "TPENRT,"},
]
ACCEPTED: list[dict[str, Any]] = [
    {"flight_numbers": "BR184"},
    {"flight_numbers": "CZ3088,CZ3575"},
    {"arrive_time": "12:00", "arrive_day_offset": 0},
    {"arrive_time": "06:10", "arrive_day_offset": -1},
    {"arrive_time": "03:30", "arrive_day_offset": 3},
    {"route_airports": "TPE,NRT"},
    {"route_airports": "TPE,SZX,SHA"},
    {"route_airports": "TPE,HKG,BKK,SIN,KUL,MNL,NRT"},
]


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("values", REJECTED, ids=[str(v) for v in REJECTED])
def test_checks_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, table: str, values: dict[str, Any]
) -> None:  # C-95
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        _write(conn, table, values)


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("values", ACCEPTED, ids=[str(v) for v in ACCEPTED])
def test_checks_accept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, table: str, values: dict[str, Any]
) -> None:  # C-95
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        _write(conn, table, values)
        stored = conn.execute(
            f"SELECT {', '.join(values)} FROM {table}"
            f" WHERE rowid = (SELECT MIN(rowid) FROM {table})"
        ).fetchone()
    assert tuple(stored) == tuple(values.values())


# ---- repository round trip ---------------------------------------------------------------------

DETAILS: dict[str, Any] = {
    "flight_numbers": "BR198,JL99",
    "arrive_time": "03:30",
    "arrive_day_offset": 1,
    "route_airports": "TPE,HKG,NRT",
}


def test_repository_round_trips_all_three_tables(tmp_path: Path) -> None:  # C-95, contract 1.3
    from flight_deals.domain.models import ComparisonSpec, ExplorationSpec, WatchSpec

    database = Database(tmp_path / "fd.db")
    database.migrate()
    repo = Repository(database)
    spec = WatchSpec(
        name="t",
        origin="TPE",
        destination="NRT",
        trip_type="one_way",
        date_mode="fixed",
        depart_date=date(2026, 12, 10),
        return_date=None,
        window_start=None,
        window_end=None,
        min_trip_days=None,
        max_trip_days=None,
        max_stops=None,
        budget_amount_minor=None,
    )
    watch_id = repo.insert_watch(spec, NOW)
    run_id = repo.insert_scan_run(
        watch_id=watch_id,
        revision=1,
        trigger="manual",
        started_at=NOW,
        sampled_pairs=[DatePair(date(2026, 12, 10))],
        total_pairs=1,
        limit_reached=False,
    )
    quote = PriceQuote(
        source="google_flights",
        price_kind="live",
        depart_date=date(2026, 12, 10),
        return_date=None,
        amount_minor=900_000,
        currency="TWD",
        as_of=NOW,
        as_of_basis="fetch_time",
        fetched_at=NOW,
        carrier="長榮航空、日本航空",
        stops=1,
        duration_minutes=300,
        depart_time="23:55",
        **DETAILS,
    )
    repo.insert_observation(scan_run_id=run_id, watch_id=watch_id, revision=1, quote=quote)
    (obs,) = repo.observations_for_watch(watch_id)
    assert {k: getattr(obs, k) for k in DETAILS} == DETAILS
    (snap,) = repo.snapshot_observations_for_watch(
        watch_id, revision=1, currency="TWD", today=date(2026, 10, 25), midnight=NOW
    )
    assert {k: getattr(snap, k) for k in DETAILS} == DETAILS

    exploration = ExplorationSpec("TPE", "NRT", "one_way", 2026, 12, None, None)
    exploration_id = repo.insert_exploration(
        exploration, [DatePair(date(2026, 12, 10)), DatePair(date(2026, 12, 11))], NOW
    )
    repo.record_exploration_cell(
        exploration_id,
        date(2026, 12, 10),
        CellUpdate(status="ok", amount_minor=900_000, currency="TWD", **DETAILS),
    )
    repo.record_exploration_cell(exploration_id, date(2026, 12, 11), CellUpdate(status="no_data"))
    ok, empty = repo.exploration_cells(exploration_id)
    assert {k: getattr(ok, k) for k in DETAILS} == DETAILS
    assert all(getattr(empty, k) is None for k in DETAILS)

    comparison = ComparisonSpec("TPE", ("NRT", "KIX"), "one_way", date(2026, 12, 10), None, None)
    comparison_id = repo.insert_comparison(comparison, NOW)
    repo.record_comparison_cell(
        comparison_id, 0, CellUpdate(status="ok", amount_minor=900_000, currency="TWD", **DETAILS)
    )
    repo.record_comparison_cell(comparison_id, 1, CellUpdate(status="no_data"))
    first, second = repo.comparison_cells(comparison_id)
    assert {k: getattr(first, k) for k in DETAILS} == DETAILS
    assert all(getattr(second, k) is None for k in DETAILS)


def test_cell_update_without_price_has_no_details() -> None:  # contract 1.3, 2.1
    from flight_deals.services.exploration import cell_update
    from flight_deals.services.source_query import PairQuery

    entry = {"status": "no_data", "reason": "no_embedded_results", "source": "google_flights"}
    update = cell_update(PairQuery(entry, queries=1), "TWD", lambda s: s, NOW)
    assert update.status == "no_data"
    assert all(getattr(update, k) is None for k in DETAILS)
    quote = PriceQuote(
        source="google_flights",
        price_kind="live",
        depart_date=date(2026, 12, 10),
        return_date=None,
        amount_minor=900_000,
        currency="TWD",
        as_of=NOW,
        as_of_basis="fetch_time",
        fetched_at=NOW,
        carrier="長榮航空",
        stops=1,
        duration_minutes=300,
        **DETAILS,
    )
    priced = cell_update(
        PairQuery({"status": "ok"}, queries=1, cheapest=quote), "TWD", lambda s: s, NOW
    )
    assert {k: getattr(priced, k) for k in DETAILS} == DETAILS


def test_no_index_mentions_the_new_columns(tmp_path: Path) -> None:  # C-96
    database = Database(tmp_path / "fd.db")
    database.migrate()
    with database.connect() as conn:
        index_sql = " ".join(
            str(r[0])
            for r in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'index'")
            if r[0]
        )
    for column in COLUMNS:
        assert re.search(rf"\b{column}\b", index_sql) is None
