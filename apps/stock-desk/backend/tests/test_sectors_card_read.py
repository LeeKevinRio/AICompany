"""The card's read path at the store level (ADR-0012 C-6, C-9, D-14; T-2, T-21).

* ``load_board`` is **one** JOIN statement (header, ranked, excluded) and never
  selects ``sector_board.source_run_ids`` (C-51); the statistics of a version
  with their checks are one LEFT JOIN, re-admitted with **one** light source
  check however many rows there are and no digest recompute (C-50);
* :class:`SectorCardReader` spends at most four statements on one connection,
  none of them a ``PRAGMA``, and still has a ``busy_timeout`` (C-9);
* :class:`MarketPanelReader` is read only, never creates the market DB, and
  answers the light check in one statement however many endpoints it is asked;
* ``latest_boards`` keeps each session's last board only (what T9 replays).
"""

from __future__ import annotations

import dataclasses
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.data.market_panel import MarketPanelReader, MarketPanelStore
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.store import (
    BiasedDataRejected,
    SectorBoardStore,
    SectorCardReader,
    SectorMethodRegistry,
    SectorStatsRepository,
)
from app.services.sector_board import SectorBoardService
from tests.sector_board_helpers import stats_record, store_market
from tests.sector_eval_helpers import synthetic_market
from tests.source_helpers import FakeSources, fingerprint

NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


def _trace(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    statements: list[str] = []
    real = sqlite3.connect

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    return statements


@pytest.fixture(scope="module")
def boards(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[date]]:
    base = tmp_path_factory.mktemp("boards")
    market = synthetic_market(seed=8, warmup=62, forward=26, n_dividends=2)
    store = store_market(market, base / "market.db")
    service = SectorBoardService(market_store=store, main_db=base / "main.db", clock=lambda: NOW)
    days = list(market.calendar[-3:])
    for day in days:
        service.refresh_board(day)
    return base / "main.db", days


def test_load_board_is_one_join_statement(
    boards: tuple[Path, list[date]], monkeypatch: pytest.MonkeyPatch
) -> None:
    main_db, days = boards
    store = SectorBoardStore(main_db)
    board_id = store.latest_board_id("TW")
    assert board_id is not None
    statements = _trace(monkeypatch)
    board = store.load_board(board_id)
    real = [s for s in statements if not s.upper().startswith("PRAGMA")]
    assert len(real) == 1 and " JOIN " in real[0].upper()
    assert "source_run_ids" not in real[0]  # C-51: repeated on every member row
    assert board is not None and board.data_as_of == days[-1]
    assert board.ranked and [row.rank for row in board.ranked] == list(
        range(1, len(board.ranked) + 1)
    )
    assert [row.sector_code for row in board.excluded] == sorted(
        row.sector_code for row in board.excluded
    )
    assert store.latest_board("TW") == board
    assert store.load_board("no-such-board") is None


def test_latest_boards_keeps_each_sessions_last_board(boards: tuple[Path, list[date]]) -> None:
    main_db, days = boards
    store = SectorBoardStore(main_db)
    before = store.latest_boards("TW", V1.method_version)
    assert [board.data_as_of for board in before] == days
    # A later board for the middle session replaces it; the others stay.
    with closing(sqlite3.connect(main_db)) as conn, conn:
        conn.execute(
            "INSERT INTO sector_board SELECT 'late', market, method_version, lookback_days, "
            "holding_days, data_as_of, window_start, data_source, bars_run_id, bars_recorded_at, "
            "'2099-01-01T00:00:00+00:00', benchmark_return_l, reference_taiex_return_l, "
            "market_expected_count, market_missing_count, market_ex_date_excluded_count, "
            "market_corporate_action_excluded_count, ex_dividend_feed_covered, "
            "constituent_invariant_violated, listing_run_id, classification_run_id, "
            "source_run_ids FROM sector_board WHERE board_id = ?",
            (before[1].board_id,),
        )
    after = store.latest_boards("TW", V1.method_version)
    assert [board.board_id for board in after] == [before[0].board_id, "late", before[2].board_id]
    assert after[1].ranked == ()  # the late header has no member rows


def test_statistics_are_one_join_and_one_verifier_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = FakeSources()
    repo = SectorStatsRepository(verifier, tmp_path / "main.db")
    for n in range(4):
        repo.save(stats_record(f"r{n}", computed_at=datetime(2029, 1, n + 1, tzinfo=UTC)))
    verifier.tally_calls = verifier.fingerprint_calls = 0
    statements = _trace(monkeypatch)
    history = repo.latest_history()
    assert [row.run_id for row in history] == ["r0", "r1", "r2", "r3"]
    assert (verifier.tally_calls, verifier.fingerprint_calls) == (1, 0)
    real = [s for s in statements if not s.upper().startswith("PRAGMA")]
    assert len(real) == 1 and "LEFT JOIN" in real[0].upper()
    assert "source_run_ids" not in real[0]
    assert [check.gate for check in history[0].gate_checks] == ["G1", "G2", "G3", "G4", "G5", "G6"]
    assert repo.find("r2") == history[2] and repo.find("nope") is None


def test_one_unknown_source_run_refuses_the_whole_read(tmp_path: Path) -> None:
    first = fingerprint(run_min=1, run_max=1, run_count=1)
    second = fingerprint(run_min=1, run_max=2, run_count=2, session_end=date(2026, 12, 2))
    saving = SectorStatsRepository(FakeSources((first, second)), tmp_path / "main.db")
    saving.save(stats_record("r1", first))
    saving.save(stats_record("r2", second, computed_at=datetime(2029, 4, 1, tzinfo=UTC)))
    reading = SectorStatsRepository(FakeSources((first, second), ok_runs={1}), tmp_path / "main.db")
    with pytest.raises(BiasedDataRejected, match="r2"):
        reading.latest_history()


def test_the_card_reader_spends_four_statements_and_no_pragma(
    boards: tuple[Path, list[date]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_db, days = boards
    copy = tmp_path / "main.db"
    with closing(sqlite3.connect(main_db)) as source, closing(sqlite3.connect(copy)) as target:
        source.backup(target)
    SectorStatsRepository(FakeSources(), copy).save(stats_record("s1"))
    SectorMethodRegistry(copy).register(V1, frozen_commit="c0ffee", registered_at=NOW)
    verifier = FakeSources()
    reader = SectorCardReader(verifier=verifier, db_path=copy)
    statements = _trace(monkeypatch)
    read = reader.read("TW", V1.method_version)
    assert len(statements) == 4, statements
    assert not any(s.upper().startswith("PRAGMA") for s in statements)
    assert not any("source_run_ids" in s for s in statements)
    assert (verifier.tally_calls, verifier.fingerprint_calls) == (1, 0)
    assert read.board is not None and read.board.data_as_of == days[-1]
    assert [row.run_id for row in read.stats_history] == ["s1"]
    assert read.accumulation_start is None and read.stats_rejected is None


def test_the_card_reader_fails_closed_on_refused_statistics(tmp_path: Path) -> None:
    SectorStatsRepository(FakeSources(), tmp_path / "main.db").save(stats_record("s1"))
    read = SectorCardReader(verifier=FakeSources(ok_runs=()), db_path=tmp_path / "main.db").read(
        "TW", V1.method_version
    )
    assert read.stats_history == () and read.approvals == ()
    assert read.stats_rejected is not None and "s1" in read.stats_rejected


def test_reader_connections_still_wait_for_writers(tmp_path: Path) -> None:
    """C-9 / T-21: busy_timeout comes from the connection's timeout, not a PRAGMA."""
    reader = SectorCardReader(verifier=FakeSources(), db_path=tmp_path / "main.db")
    with closing(reader._connect()) as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] > 0
    MarketPanelStore(tmp_path / "market.db")
    market = MarketPanelReader(tmp_path / "market.db")
    conn2 = market._connect()
    assert conn2 is not None
    with closing(conn2):
        assert conn2.execute("PRAGMA busy_timeout").fetchone()[0] > 0


def test_the_market_reader_is_read_only_and_never_creates_the_file(tmp_path: Path) -> None:
    missing = MarketPanelReader(tmp_path / "nowhere" / "market.db")
    nothing = missing.source_tally([1], 1, date(2026, 9, 25))
    assert (nothing.ok_endpoints, nothing.run_count, nothing.run_min) == (frozenset(), 0, None)
    assert missing.source_fingerprint(1, date(2026, 9, 25)) is None
    assert all(
        days == frozenset() for days in missing.ok_sessions(date(2026, 1, 1), NOW.date()).values()
    )
    assert not (tmp_path / "nowhere").exists()
    store = MarketPanelStore(tmp_path / "market.db")
    run_id = store.record_run(
        kind="listing",
        session_date=date(2026, 9, 25),
        source="t",
        status="ok",
        row_count=0,
        expected_count=None,
    )
    reader = MarketPanelReader(tmp_path / "market.db")
    assert reader.ok_sessions(date(2026, 9, 1), date(2026, 9, 30))["listing"] == {date(2026, 9, 25)}
    conn = reader._connect()
    assert conn is not None
    with closing(conn), pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute(
            "INSERT INTO market_backfill_progress VALUES ('x', 'TW', 'done', NULL, NULL, 'now')"
        )
    tally = reader.source_tally([run_id, 999], run_id, date(2026, 9, 25))
    assert tally.ok_endpoints == {run_id}
    assert (tally.run_count, tally.run_min, tally.run_max) == (1, run_id, run_id)
    assert reader.source_fingerprint(run_id, date(2026, 9, 25)) == store.source_fingerprint(
        run_id, date(2026, 9, 25)
    )


def test_the_light_check_is_one_statement_however_many_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MarketPanelStore(tmp_path / "market.db")
    real = store.record_run(
        kind="bars",
        session_date=date(2026, 9, 25),
        source="t",
        status="ok",
        row_count=0,
        expected_count=0,
    )
    wanted = range(1, 100_001)
    statements = _trace(monkeypatch)
    tally = MarketPanelReader(tmp_path / "market.db").source_tally(wanted, real, date(2026, 9, 25))
    assert tally.ok_endpoints == {real}
    assert len(statements) == 1
    assert store.source_tally(wanted, real, date(2026, 9, 25)) == tally


def test_the_board_signature_ignores_ids_and_clocks(boards: tuple[Path, list[date]]) -> None:
    from app.services.sector_board import same_board

    board = SectorBoardStore(boards[0]).latest_board("TW")
    assert board is not None
    assert same_board(
        board, dataclasses.replace(board, board_id="x", computed_at="y", bars_recorded_at=None)
    )
    changed = dataclasses.replace(board.ranked[0], up_count=board.ranked[0].up_count + 1)
    assert not same_board(board, dataclasses.replace(board, ranked=(changed, *board.ranked[1:])))
