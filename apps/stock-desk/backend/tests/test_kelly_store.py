"""Storage rules for ``kelly_inputs``: one row per key, server stamp, no purge."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.kelly.models import (
    KellyInputRecord,
    anchor_moment,
    freshness_of,
    normalize_symbol,
)
from app.kelly.store import (
    _COLUMNS,
    _OPTIONAL_COLUMN_TYPES,
    KellyInputStore,
    _migrate_add_optional_columns,
)
from app.positions.models import Market

_NOW = datetime(2026, 8, 19, 3, 0, tzinfo=UTC)


def _manual(
    symbol: str = "2330",
    market: Market = "TW",
    *,
    win_rate: float = 0.55,
    payoff_ratio: float = 1.8,
) -> KellyInputRecord:
    return KellyInputRecord.manual(
        symbol=symbol, market=market, win_rate=win_rate, payoff_ratio=payoff_ratio
    )


def _imported(symbol: str = "2330") -> KellyInputRecord:
    """A row shaped like one the import path will write (ADR-0006 D-2)."""
    return KellyInputRecord(
        symbol=symbol,
        market="TW",
        win_rate=0.6,
        payoff_ratio=2.0,
        source="backtest",
        backtest_win_rate=0.6,
        backtest_payoff_ratio=2.0,
        strategy_id="ma_cross",
        window_start="2020-01-02",
        window_end="2026-06-30",
        oos_start_date="2025-01-02",
        oos_end_date="2026-06-30",
        produced_at="2026-08-19T02:00:00+00:00",
        rates_verified=False,
        dividend_reason_code="no_events",
        adjust_dividends=True,
        oos_round_trips=24,
        oos_win_trips=14,
        oos_loss_trips=10,
        oos_excluded_boundary_trips=2,
        oos_open_trip_at_end=1,
        oos_observations=372,
        p_ci_low=0.41,
        p_ci_high=0.77,
        f_star=0.4,
        f_star_ci_low=-0.05,
        f_star_ci_high=0.61,
        bootstrap_seed=305419896,
        bootstrap_draws=2000,
        bootstrap_degenerate_no_loss_draws=6,
        bootstrap_degenerate_no_win_draws=0,
        spec_hash="1234abcd" * 8,
        low_sample_warning=True,
        k_observed_at_write=3,
    )


@pytest.fixture
def store(tmp_path: Path) -> KellyInputStore:
    return KellyInputStore(db_path=tmp_path / "kelly.db")


def test_manual_input_round_trips_with_a_server_stamp(store: KellyInputStore) -> None:
    stored = store.upsert(_manual(), now=_NOW)

    assert (stored.symbol, stored.market) == ("2330", "TW")
    assert (stored.win_rate, stored.payoff_ratio) == (0.55, 1.8)
    assert stored.source == "manual"
    assert stored.updated_at == _NOW
    assert store.get("2330", "TW") == stored


def test_a_manual_input_carries_no_strategy_or_provenance(store: KellyInputStore) -> None:
    """約束 2: a hand-typed pair was produced by no strategy."""
    stored = store.upsert(_manual(), now=_NOW)

    assert stored.strategy_id is None
    assert stored.backtest_win_rate is None
    assert stored.oos_round_trips is None
    assert stored.low_sample_warning is None


def test_the_record_model_cannot_carry_a_write_stamp() -> None:
    """約束 3: ``updated_at`` is the server's to write, so no caller may send one."""
    assert "updated_at" not in KellyInputRecord.model_fields
    with pytest.raises(ValidationError):
        KellyInputRecord.model_validate(
            {
                "symbol": "2330",
                "market": "TW",
                "win_rate": 0.5,
                "payoff_ratio": 1.0,
                "source": "manual",
                "updated_at": "2020-01-01T00:00:00+00:00",
            }
        )


def test_a_manual_input_may_not_name_a_strategy() -> None:
    with pytest.raises(ValidationError, match="strategy_id"):
        KellyInputRecord(
            symbol="2330",
            market="TW",
            win_rate=0.5,
            payoff_ratio=1.0,
            source="manual",
            strategy_id="ma_cross",
        )


@pytest.mark.parametrize("win_rate", [0.0, 1.0, -0.1, 1.2])
def test_a_win_rate_outside_the_open_unit_interval_is_refused(win_rate: float) -> None:
    with pytest.raises(ValidationError, match="勝率"):
        _manual(win_rate=win_rate)


@pytest.mark.parametrize("payoff_ratio", [0.0, -1.0])
def test_a_non_positive_payoff_ratio_is_refused(payoff_ratio: float) -> None:
    with pytest.raises(ValidationError, match="賠率"):
        _manual(payoff_ratio=payoff_ratio)


def test_the_stored_pair_is_never_clamped_into_range(store: KellyInputStore) -> None:
    """約束 6: the refusal path writes nothing, it does not write a corrected value."""
    store.upsert(_manual(), now=_NOW)
    with pytest.raises(ValidationError):
        _manual(win_rate=1.4)

    stored = store.get("2330", "TW")
    assert stored is not None
    assert stored.win_rate == 0.55


def test_one_key_keeps_exactly_one_row(store: KellyInputStore) -> None:
    """D-2: latest write wins; no history table and no second live row."""
    store.upsert(_manual(), now=_NOW)
    later = store.upsert(_manual(win_rate=0.61), now=_NOW + timedelta(days=2))

    assert later.win_rate == 0.61
    assert later.updated_at == _NOW + timedelta(days=2)
    assert len(store.list_all()) == 1


def test_the_same_ticker_in_two_markets_is_two_rows(store: KellyInputStore) -> None:
    store.upsert(_manual(symbol="AAPL", market="US"), now=_NOW)
    store.upsert(_manual(symbol="AAPL", market="TW"), now=_NOW)

    assert [(row.symbol, row.market) for row in store.list_all()] == [
        ("AAPL", "TW"),
        ("AAPL", "US"),
    ]


def test_the_symbol_is_upper_normalised_on_both_doors(store: KellyInputStore) -> None:
    """約束 1: one ticker, one spelling -- on the way in and on the way out."""
    stored = store.upsert(_manual(symbol=" aapl ", market="US"), now=_NOW)

    assert stored.symbol == "AAPL"
    assert store.get("aapl", "US") is not None
    assert normalize_symbol(" aapl ") == "AAPL"


def test_an_imported_row_keeps_every_traceability_column(store: KellyInputStore) -> None:
    """D-2: the provenance travels with the value, so no history table is needed."""
    stored = store.upsert(_imported(), now=_NOW)

    assert stored.model_dump(exclude={"updated_at"}) == _imported().model_dump()
    assert stored.updated_at == _NOW
    assert stored.bootstrap_degenerate_no_loss_draws == 6
    assert stored.bootstrap_degenerate_no_win_draws == 0


def test_a_hand_edit_of_an_imported_row_keeps_the_imported_numbers(
    store: KellyInputStore,
) -> None:
    """約束 4: source becomes ``backtest_overridden`` and the original stands."""
    imported = store.upsert(_imported(), now=_NOW)

    edited = store.upsert(
        KellyInputRecord.overriding(imported, win_rate=0.52, payoff_ratio=1.4),
        now=_NOW + timedelta(days=1),
    )

    assert edited.source == "backtest_overridden"
    assert (edited.win_rate, edited.payoff_ratio) == (0.52, 1.4)
    assert (edited.backtest_win_rate, edited.backtest_payoff_ratio) == (0.6, 2.0)
    assert edited.strategy_id == "ma_cross"
    assert edited.oos_round_trips == 24


def test_an_expired_row_is_kept_and_returned(store: KellyInputStore) -> None:
    """D-2: deleting a stale row would erase "never entered" vs "gone stale"."""
    long_ago = _NOW - timedelta(days=400)
    store.upsert(_manual(), now=long_ago)

    reopened = KellyInputStore(db_path=store.db_path)
    stored = reopened.get("2330", "TW")

    assert stored is not None
    assert stored.updated_at == long_ago
    assert freshness_of((_NOW - anchor_moment(stored)).days) == "expired"


def test_delete_removes_the_row_and_reports_whether_it_did(store: KellyInputStore) -> None:
    store.upsert(_manual(), now=_NOW)

    assert store.delete("2330", "TW") is True
    assert store.get("2330", "TW") is None
    assert store.delete("2330", "TW") is False


def test_delete_only_touches_the_named_key(store: KellyInputStore) -> None:
    store.upsert(_manual(symbol="AAPL", market="US"), now=_NOW)
    store.upsert(_manual(symbol="AAPL", market="TW"), now=_NOW)

    assert store.delete("aapl", "US") is True
    assert [(row.symbol, row.market) for row in store.list_all()] == [("AAPL", "TW")]


def test_the_column_list_and_the_record_model_agree() -> None:
    """A column in one and not the other is a value silently dropped."""
    assert _COLUMNS == (*KellyInputRecord.model_fields, "updated_at")
    assert set(_OPTIONAL_COLUMN_TYPES) < set(_COLUMNS)


def test_every_declared_column_exists_in_the_created_table(store: KellyInputStore) -> None:
    with closing(sqlite3.connect(store.db_path)) as conn:
        columns = [column[1] for column in conn.execute("PRAGMA table_info(kelly_inputs)")]
    assert tuple(columns) == _COLUMNS


def _seed_legacy_db(db_path: Path) -> None:
    """A ``kelly_inputs`` written before the traceability columns existed."""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            """
            CREATE TABLE kelly_inputs (
                symbol TEXT NOT NULL,
                market TEXT NOT NULL,
                win_rate REAL NOT NULL,
                payoff_ratio REAL NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (symbol, market)
            )
            """
        )
        conn.execute(
            "INSERT INTO kelly_inputs (symbol, market, win_rate, payoff_ratio, source, updated_at)"
            " VALUES ('2330', 'TW', 0.55, 1.8, 'manual', ?)",
            (_NOW.isoformat(),),
        )


def test_the_migration_adds_the_missing_columns_and_keeps_the_row(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _seed_legacy_db(db_path)

    store = KellyInputStore(db_path=db_path)
    stored = store.get("2330", "TW")

    assert stored is not None
    assert (stored.win_rate, stored.updated_at) == (0.55, _NOW)
    assert stored.oos_round_trips is None  # added as NULL, classifying nothing
    with closing(sqlite3.connect(db_path)) as conn:
        columns = [column[1] for column in conn.execute("PRAGMA table_info(kelly_inputs)")]
    assert set(_COLUMNS) <= set(columns)


def test_the_migration_is_a_no_op_the_second_time(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _seed_legacy_db(db_path)
    KellyInputStore(db_path=db_path)

    with closing(sqlite3.connect(db_path)) as conn, conn:
        _migrate_add_optional_columns(conn)
        columns = [column[1] for column in conn.execute("PRAGMA table_info(kelly_inputs)")]

    assert columns.count("oos_round_trips") == 1
    assert len(KellyInputStore(db_path=db_path).list_all()) == 1


def test_the_migration_still_raises_an_unrelated_operational_error(tmp_path: Path) -> None:
    """Only "already migrated" is quiet; a real failure stays loud."""
    with closing(sqlite3.connect(tmp_path / "missing-table.db")) as conn, conn:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            _migrate_add_optional_columns(conn)


def test_two_stores_opening_the_same_legacy_database_at_once_both_survive(
    tmp_path: Path,
) -> None:
    """The backend and a CLI starting together must not corrupt the table.

    ``BEGIN IMMEDIATE`` serialises the two migrators: the loser blocks at the
    write lock, re-checks inside it and finds the columns already there. Both
    must come back with the single seeded row intact and no duplicated column.
    """
    db_path = tmp_path / "legacy.db"
    _seed_legacy_db(db_path)
    barrier = threading.Barrier(2)
    failures: list[Exception] = []

    def open_store() -> None:
        try:
            barrier.wait(timeout=10)
            KellyInputStore(db_path=db_path)
        except Exception as error:  # noqa: BLE001 - collected for the assertion
            failures.append(error)

    threads = [threading.Thread(target=open_store) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    with closing(sqlite3.connect(db_path)) as conn:
        columns = [column[1] for column in conn.execute("PRAGMA table_info(kelly_inputs)")]
    assert len(columns) == len(set(columns)) == len(_COLUMNS)
    rows = KellyInputStore(db_path=db_path).list_all()
    assert len(rows) == 1
    assert rows[0].win_rate == 0.55
