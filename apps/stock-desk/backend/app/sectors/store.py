"""Main-DB tables of the sector card (ADR-0012 C-8, D-5, D-6, D-14).

Tables (main DB, ``STOCK_DESK_DB_PATH`` via ``app.data.cache.resolve_db_path``
-- the only thing this module may take from ``app.data.cache``, C-1):

* ``sector_board`` / ``sector_board_members`` / ``sector_board_excluded`` --
  one board per refresh: the card header (market counts, provenance), one row
  per ranked sector (with its full ``C_g(t,L)`` for audit and its three listed
  constituents), one row per excluded sector.
* ``sector_rank_stats`` / ``sector_gate_checks`` / ``sector_gate_approvals`` /
  ``sector_method_registry`` -- the gate's inputs. These four are append-only
  by SQLite trigger (C-21, SQL as in ADR-0012 D-6); the registry allows exactly
  two NULL -> value updates (``first_forward_eval_at`` together with
  ``counts_toward_m = 1``, and ``accumulation_start``).

No class here offers UPDATE or DELETE on a gate table; the registry's two
permitted updates are the only UPDATE statements in the module.

:class:`SectorStatsRepository` refuses, on save **and** on load, anything that
is not ``regime="pit"`` + ``data_regime="forward_pit"`` with a source
fingerprint (``source_run_min``, ``source_run_max``, ``source_session_end``,
``source_run_count``, ``source_digest``) matching the market DB's
``pit_snapshot_runs`` -- raising :class:`BiasedDataRejected` (D-14, C-27,
C-50). ``save()`` recomputes the fingerprint in full, for the new row and for
the version's previous row; every read (``load()``, ``latest_history()``,
``find()``, :class:`SectorCardReader`) makes one light check for the whole
batch -- every row's first and last run are existing ``ok`` runs, and the
latest row's count and first / last run match -- and never recomputes a
digest. The market DB is reached through an injected :class:`RunIdVerifier`
(:class:`SourceTallyReader` for the card), implemented in
``app.data.market_panel``, because this package may not import the market-DB
store (C-1).

A ``sector_rank_stats`` table of the pre-v9 schema (with ``source_run_ids``)
is rebuilt when empty; with rows it is left as is and every save and load of
statistics is refused (C-50: no automatic migration).

``sector_board.source_run_ids`` is written for audit but never read back:
the board SQL does not select it (C-51).

Ratios are never stored: the header and sector rows keep counts, and readers
rebuild ratios through :mod:`app.sectors.coverage`, the one formula.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Collection, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final, Protocol, cast

from app.data.cache import resolve_db_path
from app.data.panel import SourceFingerprint, SourceTally
from app.sectors.coverage import coverage_from_counts
from app.sectors.definition import SectorMomentumDefinition
from app.sectors.models import (
    ApprovalKind,
    ApprovalOperator,
    ApprovalRecord,
    Coverage,
    DataRegime,
    GateCheckRecord,
    GateName,
    MethodRegistryRow,
    ReasonCode,
    SelfcheckRecord,
    SelfcheckStatus,
    StatsRecord,
    StatsRegime,
)
from app.sectors.ranking import SectorRanking
from app.sectors.universe import CalculationSet

logger = logging.getLogger(__name__)

#: Milliseconds a connection waits for a concurrent writer (C-9).
BUSY_TIMEOUT_MS: Final = 5000

#: The four append-only gate tables (C-21).
APPEND_ONLY_TABLES: Final[tuple[str, ...]] = (
    "sector_rank_stats",
    "sector_gate_checks",
    "sector_gate_approvals",
    "sector_method_registry",
)

_SCHEMA: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS sector_board (
        board_id TEXT PRIMARY KEY,
        market TEXT NOT NULL,
        method_version TEXT NOT NULL,
        lookback_days INTEGER NOT NULL,
        holding_days INTEGER NOT NULL,
        data_as_of TEXT NOT NULL,
        window_start TEXT,
        data_source TEXT NOT NULL,
        bars_run_id TEXT,
        bars_recorded_at TEXT,
        computed_at TEXT NOT NULL,
        benchmark_return_l REAL,
        reference_taiex_return_l REAL,
        market_expected_count INTEGER NOT NULL,
        market_missing_count INTEGER NOT NULL,
        market_ex_date_excluded_count INTEGER NOT NULL,
        market_corporate_action_excluded_count INTEGER NOT NULL,
        ex_dividend_feed_covered INTEGER NOT NULL CHECK (ex_dividend_feed_covered IN (0, 1)),
        constituent_invariant_violated INTEGER NOT NULL
            CHECK (constituent_invariant_violated IN (0, 1)),
        listing_run_id TEXT,
        classification_run_id TEXT,
        source_run_ids TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sector_board_latest
    ON sector_board (market, data_as_of, computed_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS sector_board_members (
        board_id TEXT NOT NULL,
        rank INTEGER NOT NULL,
        sector_code TEXT NOT NULL,
        sector_name TEXT NOT NULL,
        sector_return_l REAL NOT NULL,
        rel_return_l REAL NOT NULL,
        up_count INTEGER NOT NULL,
        expected_count INTEGER NOT NULL,
        missing_count INTEGER NOT NULL,
        ex_date_excluded_count INTEGER NOT NULL,
        corporate_action_excluded_count INTEGER NOT NULL,
        turnover_value_ratio_5_20 REAL,
        top_contributor_share REAL,
        single_stock_dominated INTEGER NOT NULL CHECK (single_stock_dominated IN (0, 1)),
        member_symbols TEXT NOT NULL,
        constituents TEXT NOT NULL,
        PRIMARY KEY (board_id, sector_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sector_board_excluded (
        board_id TEXT NOT NULL,
        sector_code TEXT NOT NULL,
        sector_name TEXT NOT NULL,
        reason_code TEXT NOT NULL CHECK (reason_code IN (
            'unranked_category', 'too_few_members', 'low_coverage', 'ex_dividend_exclusion')),
        expected_count INTEGER NOT NULL,
        missing_count INTEGER NOT NULL,
        ex_date_excluded_count INTEGER NOT NULL,
        corporate_action_excluded_count INTEGER NOT NULL,
        internal_reason TEXT,
        PRIMARY KEY (board_id, sector_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sector_rank_stats (
        run_id TEXT PRIMARY KEY,
        method_version TEXT NOT NULL,
        regime TEXT NOT NULL CHECK (regime = 'pit'),
        data_regime TEXT NOT NULL CHECK (data_regime = 'forward_pit'),
        source_run_min INTEGER NOT NULL,
        source_run_max INTEGER NOT NULL CHECK (source_run_max >= source_run_min),
        source_session_end TEXT NOT NULL,
        source_run_count INTEGER NOT NULL CHECK (source_run_count > 0),
        source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
        m_at_evaluation INTEGER NOT NULL,
        sample_count INTEGER NOT NULL,
        effective_sample_count REAL NOT NULL,
        beat_count_net INTEGER NOT NULL,
        beat_count_gross INTEGER NOT NULL,
        base_rate_net REAL NOT NULL,
        base_rate_gross REAL NOT NULL,
        ci_low_net REAL NOT NULL,
        ci_high_net REAL NOT NULL,
        bootstrap_low_net REAL NOT NULL,
        bootstrap_high_net REAL NOT NULL,
        delta_real REAL,
        delta_shuffle REAL,
        sample_start TEXT NOT NULL,
        sample_end TEXT NOT NULL,
        stats_as_of TEXT NOT NULL,
        computed_at TEXT NOT NULL,
        recompute_session TEXT NOT NULL,
        running_commit TEXT NOT NULL,
        selfcheck_passed INTEGER NOT NULL CHECK (selfcheck_passed IN (0, 1)),
        data_quality_passed INTEGER NOT NULL CHECK (data_quality_passed IN (0, 1)),
        pit_history_missing INTEGER NOT NULL CHECK (pit_history_missing IN (0, 1))
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sector_rank_stats_version
    ON sector_rank_stats (method_version, computed_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS sector_gate_checks (
        run_id TEXT NOT NULL,
        check_kind TEXT NOT NULL CHECK (check_kind IN ('gate', 'selfcheck')),
        check_name TEXT NOT NULL,
        status TEXT NOT NULL
            CHECK (status IN ('pass', 'fail', 'skipped_insufficient_n', 'vacuous')),
        seed INTEGER,
        value REAL,
        detail TEXT,
        CHECK (check_kind = 'selfcheck' OR status IN ('pass', 'fail')),
        PRIMARY KEY (run_id, check_kind, check_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sector_gate_approvals (
        approval_id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('first_transition_risk', 'quarterly_qa')),
        run_id TEXT NOT NULL,
        method_version TEXT NOT NULL,
        operator TEXT NOT NULL CHECK (operator IN ('ceo', 'dev-lead')),
        reviewer TEXT NOT NULL,
        review_doc_path TEXT NOT NULL,
        review_doc_blob_hash TEXT NOT NULL,
        approved_at TEXT NOT NULL,
        CHECK (kind <> 'quarterly_qa' OR operator = 'dev-lead')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sector_method_registry (
        method_version TEXT PRIMARY KEY,
        lookback_days INTEGER NOT NULL,
        holding_days INTEGER NOT NULL,
        frozen_commit TEXT NOT NULL,
        registered_at TEXT NOT NULL,
        accumulation_start TEXT,
        first_forward_eval_at TEXT,
        counts_toward_m INTEGER NOT NULL CHECK (counts_toward_m IN (0, 1))
    )
    """,
)


def _no_update_delete(table: str) -> tuple[str, str]:
    return (
        f"CREATE TRIGGER IF NOT EXISTS {table}_no_update\n"
        f"BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END;",
        f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete\n"
        f"BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END;",
    )


#: ADR-0012 D-6, verbatim in substance.
_REGISTRY_TRIGGERS: Final[tuple[str, ...]] = (
    """
    CREATE TRIGGER IF NOT EXISTS sector_method_registry_no_delete
    BEFORE DELETE ON sector_method_registry BEGIN SELECT RAISE(ABORT, 'append-only'); END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS sector_method_registry_update_guard
    BEFORE UPDATE ON sector_method_registry
    WHEN NOT (
        NEW.method_version IS OLD.method_version
        AND NEW.lookback_days IS OLD.lookback_days
        AND NEW.holding_days IS OLD.holding_days
        AND NEW.frozen_commit IS OLD.frozen_commit
        AND NEW.registered_at IS OLD.registered_at
        AND (NEW.accumulation_start IS OLD.accumulation_start
             OR (OLD.accumulation_start IS NULL AND NEW.accumulation_start IS NOT NULL))
        AND (NEW.first_forward_eval_at IS OLD.first_forward_eval_at
             OR (OLD.first_forward_eval_at IS NULL AND NEW.first_forward_eval_at IS NOT NULL
                 AND NEW.counts_toward_m = 1))
        AND (NEW.counts_toward_m IS OLD.counts_toward_m
             OR (OLD.first_forward_eval_at IS NULL AND NEW.first_forward_eval_at IS NOT NULL))
    )
    BEGIN SELECT RAISE(ABORT, 'append-only'); END;
    """,
)

_TRIGGERS: Final[tuple[str, ...]] = (
    *_no_update_delete("sector_rank_stats"),
    *_no_update_delete("sector_gate_checks"),
    *_no_update_delete("sector_gate_approvals"),
    *_REGISTRY_TRIGGERS,
)

#: Every trigger name the schema must contain (T-16 existence check).
EXPECTED_TRIGGERS: Final[frozenset[str]] = frozenset(
    {
        "sector_rank_stats_no_update",
        "sector_rank_stats_no_delete",
        "sector_gate_checks_no_update",
        "sector_gate_checks_no_delete",
        "sector_gate_approvals_no_update",
        "sector_gate_approvals_no_delete",
        "sector_method_registry_no_delete",
        "sector_method_registry_update_guard",
    }
)


class BiasedDataRejected(Exception):
    """A statistics record that is not forward point-in-time data (D-14, C-27, C-50)."""


class SourceTallyReader(Protocol):
    """The read-time light check of statistics sources (C-50): one SQL statement.

    ``endpoints`` are run ids that must be existing ``ok`` runs; ``run_max`` and
    ``session_end`` name one row's source set, whose count and first / last run
    are returned. Implemented in ``app.data.market_panel``; never computes a
    digest.
    """

    def source_tally(
        self, endpoints: Collection[int], run_max: int, session_end: date
    ) -> SourceTally: ...


class RunIdVerifier(SourceTallyReader, Protocol):
    """Both source checks (C-50): the read-time tally and the write-time full recompute.

    ``source_fingerprint`` recomputes the fingerprint of the source set
    (every ``ok`` run with ``session_date <= session_end`` and
    ``run_id <= run_max``) from the market DB, with the evaluator's own
    ``app.data.panel.source_fingerprint``; ``None`` when that set is empty.
    """

    def source_fingerprint(self, run_max: int, session_end: date) -> SourceFingerprint | None: ...


#: The pre-v9 column that listed every source run (C-50 replaced it).
LEGACY_SOURCE_COLUMN: Final = "source_run_ids"


def _legacy_stats_rows(conn: sqlite3.Connection) -> int | None:
    """Rows of a pre-v9 ``sector_rank_stats``; an empty one is dropped for a rebuild.

    ``None`` when the table is absent, current, or was empty and dropped. With
    rows it is left untouched: C-50 forbids an automatic migration.
    """
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(sector_rank_stats)")}
    if LEGACY_SOURCE_COLUMN not in columns:
        return None
    (count,) = conn.execute("SELECT COUNT(*) FROM sector_rank_stats").fetchone()
    if int(count) == 0:
        # Its index and triggers go with it; _SCHEMA / _TRIGGERS recreate all three.
        conn.execute("DROP TABLE sector_rank_stats")
        return None
    return int(count)


def _legacy_message(rows: int) -> str:
    return (
        f"sector_rank_stats has the pre-v9 {LEGACY_SOURCE_COLUMN} column and {rows} row(s); "
        "it is not migrated automatically, so statistics are neither written nor read "
        "(ADR-0012 C-50)"
    )


class _SectorDb:
    """Connection discipline shared by every store here (WAL, busy_timeout, closing)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            self._legacy_stats_rows = _legacy_stats_rows(conn)
            for statement in (*_SCHEMA, *_TRIGGERS):
                conn.execute(statement)

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def legacy_stats_rows(self) -> int | None:
        """Rows kept in a pre-v9 ``sector_rank_stats`` (C-50); ``None`` when current."""
        return self._legacy_stats_rows

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as conn, conn:
            yield conn


def ensure_schema(db_path: str | Path | None = None) -> Path:
    """Create the sector tables and triggers; returns the database path."""
    return _SectorDb(db_path).db_path


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value is not None else None


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoardProvenance:
    """What the pure core cannot know about a board: ids, clocks, sources."""

    board_id: str
    market: str
    data_source: str
    bars_run_id: str | None
    bars_recorded_at: datetime | None
    computed_at: datetime
    #: Written to ``sector_board.source_run_ids`` for audit; never read back (C-51).
    source_run_ids: tuple[str, ...]
    ex_dividend_feed_covered: bool
    reference_taiex_return_L: float | None = None  # noqa: N815 -- D-10 field name


@dataclass(frozen=True)
class StoredConstituent:
    symbol: str
    name: str
    return_L: float  # noqa: N815 -- D-10 field name


@dataclass(frozen=True)
class StoredRankedSector:
    rank: int
    sector_code: str
    sector_name: str
    sector_return_L: float  # noqa: N815 -- D-10 field name
    rel_return_L: float  # noqa: N815 -- D-10 field name
    up_count: int
    coverage: Coverage
    turnover_value_ratio_5_20: float | None
    top_contributor_share: float | None
    single_stock_dominated: bool
    member_symbols: tuple[str, ...]
    constituents: tuple[StoredConstituent, ...]

    @property
    def constituent_count(self) -> int:
        return self.coverage.calculation_count


@dataclass(frozen=True)
class StoredExcludedSector:
    sector_code: str
    sector_name: str
    reason_code: ReasonCode
    coverage: Coverage
    internal_reason: str | None

    @property
    def computable_count(self) -> int:
        return self.coverage.calculation_count

    @property
    def expected_count(self) -> int:
        return self.coverage.expected_count


@dataclass(frozen=True)
class StoredBoard:
    board_id: str
    market: str
    method_version: str
    lookback_days: int
    holding_days: int
    data_as_of: date
    window_start: date | None
    data_source: str
    bars_run_id: str | None
    bars_recorded_at: str | None
    computed_at: str
    benchmark_return_L: float | None  # noqa: N815 -- D-10 field name
    reference_taiex_return_L: float | None  # noqa: N815 -- D-10 field name
    market_expected_count: int
    market_missing_count: int
    market_ex_date_excluded_count: int
    market_corporate_action_excluded_count: int
    ex_dividend_feed_covered: bool
    constituent_invariant_violated: bool
    ranked: tuple[StoredRankedSector, ...]
    excluded: tuple[StoredExcludedSector, ...]


class SectorBoardStore(_SectorDb):
    """Writes and reads boards. One transaction per board; no UPDATE / DELETE."""

    def save_board(
        self,
        *,
        definition: SectorMomentumDefinition,
        calc: CalculationSet,
        ranking: SectorRanking,
        provenance: BoardProvenance,
        turnover: Mapping[str, float | None],
        names: Mapping[str, str],
    ) -> None:
        """Persist one board computed by the pure core.

        ``turnover`` is keyed by sector code (descriptive only); ``names`` maps
        symbols to display names (a missing name falls back to the symbol).
        """
        if ranking.method_version != definition.method_version or (
            calc.method_version != definition.method_version
        ):
            raise ValueError("board parts disagree on method_version")
        market = calc.market
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO sector_board (
                    board_id, market, method_version, lookback_days, holding_days,
                    data_as_of, window_start, data_source, bars_run_id, bars_recorded_at,
                    computed_at, benchmark_return_l, reference_taiex_return_l,
                    market_expected_count, market_missing_count,
                    market_ex_date_excluded_count, market_corporate_action_excluded_count,
                    ex_dividend_feed_covered, constituent_invariant_violated,
                    listing_run_id, classification_run_id, source_run_ids
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provenance.board_id,
                    provenance.market,
                    definition.method_version,
                    definition.lookback_days,
                    definition.holding_days,
                    calc.decision_date.isoformat(),
                    calc.window[0].isoformat() if calc.window else None,
                    provenance.data_source,
                    provenance.bars_run_id,
                    _iso(provenance.bars_recorded_at),
                    provenance.computed_at.isoformat(),
                    ranking.benchmark_return,
                    provenance.reference_taiex_return_L,
                    len(market.expected),
                    len(market.missing),
                    len(market.ex_date_excluded),
                    len(market.corporate_action_excluded),
                    int(provenance.ex_dividend_feed_covered),
                    int(bool(ranking.invariant_violations)),
                    calc.listing.run_id if calc.listing else None,
                    calc.classification.run_id if calc.classification else None,
                    json.dumps(sorted(provenance.source_run_ids)),
                ),
            )
            conn.executemany(
                """
                INSERT INTO sector_board_members (
                    board_id, rank, sector_code, sector_name, sector_return_l, rel_return_l,
                    up_count, expected_count, missing_count, ex_date_excluded_count,
                    corporate_action_excluded_count, turnover_value_ratio_5_20,
                    top_contributor_share, single_stock_dominated, member_symbols, constituents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        provenance.board_id,
                        row.rank,
                        row.sector_code,
                        row.sector_name,
                        row.sector_return,
                        row.rel_return,
                        row.up_count,
                        row.coverage.expected_count,
                        row.coverage.missing_count,
                        row.coverage.ex_date_excluded_count,
                        row.coverage.corporate_action_excluded_count,
                        turnover.get(row.sector_code),
                        row.top_contributor_share,
                        int(row.single_stock_dominated),
                        json.dumps(sorted(row.members)),
                        json.dumps(
                            [
                                {
                                    "symbol": item.symbol,
                                    "name": names.get(item.symbol, item.symbol),
                                    "return_L": item.return_L,
                                }
                                for item in row.constituents
                            ]
                        ),
                    )
                    for row in ranking.ranked
                ],
            )
            conn.executemany(
                """
                INSERT INTO sector_board_excluded (
                    board_id, sector_code, sector_name, reason_code, expected_count,
                    missing_count, ex_date_excluded_count, corporate_action_excluded_count,
                    internal_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        provenance.board_id,
                        row.sector_code,
                        row.sector_name,
                        row.reason_code,
                        row.coverage.expected_count,
                        row.coverage.missing_count,
                        row.coverage.ex_date_excluded_count,
                        row.coverage.corporate_action_excluded_count,
                        row.internal_reason,
                    )
                    for row in ranking.excluded
                ],
            )

    def latest_board_id(self, market: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(_LATEST_BOARD_ID_SQL, (market,)).fetchone()
        return str(row[0]) if row else None

    def load_board(self, board_id: str) -> StoredBoard | None:
        """One board -- header, ranked and excluded rows -- in one JOIN statement."""
        with closing(self._connect()) as conn:
            rows = conn.execute(_board_sql("SELECT ? AS board_id"), (board_id,)).fetchall()
        return _board_from_rows(rows)

    def latest_board(self, market: str) -> StoredBoard | None:
        """The newest board of ``market`` (latest session, then latest computation)."""
        with closing(self._connect()) as conn:
            rows = conn.execute(_board_sql(_LATEST_BOARD_ID_SQL), (market,)).fetchall()
        return _board_from_rows(rows)

    def latest_boards(self, market: str, method_version: str) -> tuple[StoredBoard, ...]:
        """The last board written for each session of one method version, oldest first.

        What the evaluator's T9 compares against its replay (ADR-0012 D-8): a
        session recomputed after a later capture keeps only its final board.
        """
        with closing(self._connect()) as conn:
            ids = conn.execute(
                """
                SELECT board_id FROM (
                    SELECT board_id, data_as_of, ROW_NUMBER() OVER (
                        PARTITION BY data_as_of ORDER BY computed_at DESC, board_id DESC
                    ) AS position
                    FROM sector_board WHERE market = ? AND method_version = ?
                ) WHERE position = 1 ORDER BY data_as_of
                """,
                (market, method_version),
            ).fetchall()
            boards = [
                _board_from_rows(conn.execute(_board_sql("SELECT ? AS board_id"), row).fetchall())
                for row in ids
            ]
        return tuple(board for board in boards if board is not None)


_LATEST_BOARD_ID_SQL: Final = (
    "SELECT board_id FROM sector_board WHERE market = ? "
    "ORDER BY data_as_of DESC, computed_at DESC, board_id DESC LIMIT 1"
)
#: The header columns boards are read with. ``source_run_ids`` is deliberately
#: absent: it grows with the market DB's runs and the join would repeat it on
#: every member row (C-51).
_HEADER_COLUMNS: Final[tuple[str, ...]] = (
    "board_id",
    "market",
    "method_version",
    "lookback_days",
    "holding_days",
    "data_as_of",
    "window_start",
    "data_source",
    "bars_run_id",
    "bars_recorded_at",
    "computed_at",
    "benchmark_return_l",
    "reference_taiex_return_l",
    "market_expected_count",
    "market_missing_count",
    "market_ex_date_excluded_count",
    "market_corporate_action_excluded_count",
    "ex_dividend_feed_covered",
    "constituent_invariant_violated",
)
_MEMBER_COLUMNS: Final[tuple[str, ...]] = (
    "rank",
    "sector_code",
    "sector_name",
    "sector_return_l",
    "rel_return_l",
    "up_count",
    "expected_count",
    "missing_count",
    "ex_date_excluded_count",
    "corporate_action_excluded_count",
    "turnover_value_ratio_5_20",
    "top_contributor_share",
    "single_stock_dominated",
    "member_symbols",
    "constituents",
)
_EXCLUDED_COLUMNS: Final[tuple[str, ...]] = (
    "sector_code",
    "sector_name",
    "reason_code",
    "expected_count",
    "missing_count",
    "ex_date_excluded_count",
    "corporate_action_excluded_count",
    "internal_reason",
)
_H, _M = len(_HEADER_COLUMNS), len(_MEMBER_COLUMNS)


def _board_sql(target: str) -> str:
    """Header x ranked rows, then header x excluded rows, as one statement.

    ``target`` is a SELECT yielding the one ``board_id`` to read. Each result
    row is ``part, header..., member..., excluded...`` with the other part's
    columns NULL; a board without ranked rows still yields its header once
    (the LEFT JOIN). Ordered by part, then rank, then excluded sector code.
    """
    header = ", ".join(f"b.{column}" for column in _HEADER_COLUMNS)
    members = ", ".join(f"m.{column}" for column in _MEMBER_COLUMNS)
    excluded = ", ".join(f"e.{column}" for column in _EXCLUDED_COLUMNS)
    no_members = ", ".join("NULL" for _ in _MEMBER_COLUMNS)
    no_excluded = ", ".join("NULL" for _ in _EXCLUDED_COLUMNS)
    rank_column, code_column = 2 + _H, 2 + _H + _M
    return f"""
        WITH target AS ({target})
        SELECT 'm' AS part, {header}, {members}, {no_excluded}
        FROM sector_board b JOIN target t ON t.board_id = b.board_id
        LEFT JOIN sector_board_members m ON m.board_id = b.board_id
        UNION ALL
        SELECT 'x' AS part, {header}, {no_members}, {excluded}
        FROM sector_board b JOIN target t ON t.board_id = b.board_id
        JOIN sector_board_excluded e ON e.board_id = b.board_id
        ORDER BY 1, {rank_column}, {code_column}
    """


def _coverage_of(row: Sequence[object]) -> Coverage:
    return coverage_from_counts(
        expected=int(cast(int, row[0])),
        missing=int(cast(int, row[1])),
        ex_date=int(cast(int, row[2])),
        corporate_action=int(cast(int, row[3])),
    )


def _board_from_rows(rows: Sequence[Sequence[object]]) -> StoredBoard | None:
    """Rebuild a :class:`StoredBoard` from the rows of :func:`_board_sql`."""
    if not rows:
        return None
    header = rows[0][1 : 1 + _H]
    ranked: list[StoredRankedSector] = []
    excluded: list[StoredExcludedSector] = []
    for row in rows:
        part = row[0]
        member = row[1 + _H : 1 + _H + _M]
        other = row[1 + _H + _M :]
        if part == "m" and member[0] is not None:
            ranked.append(
                StoredRankedSector(
                    rank=int(cast(int, member[0])),
                    sector_code=str(member[1]),
                    sector_name=str(member[2]),
                    sector_return_L=float(cast(float, member[3])),
                    rel_return_L=float(cast(float, member[4])),
                    up_count=int(cast(int, member[5])),
                    coverage=_coverage_of(member[6:10]),
                    turnover_value_ratio_5_20=cast(float | None, member[10]),
                    top_contributor_share=cast(float | None, member[11]),
                    single_stock_dominated=bool(member[12]),
                    member_symbols=tuple(json.loads(str(member[13]))),
                    constituents=tuple(
                        StoredConstituent(
                            symbol=item["symbol"], name=item["name"], return_L=item["return_L"]
                        )
                        for item in json.loads(str(member[14]))
                    ),
                )
            )
        elif part == "x":
            excluded.append(
                StoredExcludedSector(
                    sector_code=str(other[0]),
                    sector_name=str(other[1]),
                    reason_code=cast(ReasonCode, other[2]),
                    coverage=_coverage_of(other[3:7]),
                    internal_reason=cast(str | None, other[7]),
                )
            )
    data_as_of = _date(cast(str | None, header[5]))
    if data_as_of is None:  # pragma: no cover - NOT NULL column
        raise ValueError("sector_board.data_as_of is NULL")
    return StoredBoard(
        board_id=str(header[0]),
        market=str(header[1]),
        method_version=str(header[2]),
        lookback_days=int(cast(int, header[3])),
        holding_days=int(cast(int, header[4])),
        data_as_of=data_as_of,
        window_start=_date(cast(str | None, header[6])),
        data_source=str(header[7]),
        bars_run_id=cast(str | None, header[8]),
        bars_recorded_at=cast(str | None, header[9]),
        computed_at=str(header[10]),
        benchmark_return_L=cast(float | None, header[11]),
        reference_taiex_return_L=cast(float | None, header[12]),
        market_expected_count=int(cast(int, header[13])),
        market_missing_count=int(cast(int, header[14])),
        market_ex_date_excluded_count=int(cast(int, header[15])),
        market_corporate_action_excluded_count=int(cast(int, header[16])),
        ex_dividend_feed_covered=bool(header[17]),
        constituent_invariant_violated=bool(header[18]),
        ranked=tuple(ranked),
        excluded=tuple(excluded),
    )


# ---------------------------------------------------------------------------
# Statistics (append-only, PIT only)
# ---------------------------------------------------------------------------

_STATS_COLUMNS: Final[tuple[str, ...]] = (
    "run_id",
    "method_version",
    "regime",
    "data_regime",
    "source_run_min",
    "source_run_max",
    "source_session_end",
    "source_run_count",
    "source_digest",
    "m_at_evaluation",
    "sample_count",
    "effective_sample_count",
    "beat_count_net",
    "beat_count_gross",
    "base_rate_net",
    "base_rate_gross",
    "ci_low_net",
    "ci_high_net",
    "bootstrap_low_net",
    "bootstrap_high_net",
    "delta_real",
    "delta_shuffle",
    "sample_start",
    "sample_end",
    "stats_as_of",
    "computed_at",
    "recompute_session",
    "running_commit",
    "selfcheck_passed",
    "data_quality_passed",
    "pit_history_missing",
)


#: The five fixed-width source columns (C-50), in :class:`SourceFingerprint` order.
_SOURCE_COLUMNS: Final[tuple[str, ...]] = (
    "source_run_min",
    "source_run_max",
    "source_session_end",
    "source_run_count",
    "source_digest",
)


class SectorStatsRepository(_SectorDb):
    """``sector_rank_stats`` + ``sector_gate_checks``; forward PIT records only."""

    def __init__(self, verifier: RunIdVerifier, db_path: str | Path | None = None) -> None:
        super().__init__(db_path)
        self._verifier = verifier
        if self.legacy_stats_rows is not None:
            logger.error(_legacy_message(self.legacy_stats_rows))

    def _refuse_legacy(self) -> None:
        if self.legacy_stats_rows is not None:
            message = _legacy_message(self.legacy_stats_rows)
            logger.error(message)
            raise BiasedDataRejected(message)

    def _previous(self, method_version: str) -> tuple[str, SourceFingerprint] | None:
        """The version's latest stored row (``run_id``, fingerprint), unchecked."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT run_id, source_run_min, source_run_max, source_session_end, "
                "source_run_count, source_digest FROM sector_rank_stats "
                "WHERE method_version = ? ORDER BY computed_at DESC, run_id DESC LIMIT 1",
                (method_version,),
            ).fetchone()
        if row is None:
            return None
        return str(row[0]), _fingerprint_from_values(row[1:6])

    def _recompute(self, run_id: str, claimed: SourceFingerprint) -> None:
        actual = self._verifier.source_fingerprint(claimed.run_max, claimed.session_end)
        if actual != claimed:
            raise BiasedDataRejected(
                f"stats run {run_id}: source fingerprint {claimed} does not match the market "
                f"DB's pit_snapshot_runs ({actual}) (ADR-0012 C-50)"
            )

    def save(self, record: StatsRecord) -> None:
        """Append one statistics row and its G1..G6 / T1..T9 check rows.

        The row's source fingerprint, and that of the version's previous row,
        are recomputed in full from the market DB first; any difference raises
        :class:`BiasedDataRejected` and nothing is written (C-50, T-22).
        """
        self._refuse_legacy()
        _admit_regime(record.regime, record.data_regime, record.run_id)
        claimed = record_fingerprint(record)
        _admit_shape(record.run_id, claimed)
        previous = self._previous(record.method_version)
        self._recompute(record.run_id, claimed)
        if previous is not None:
            self._recompute(*previous)
        values = (
            record.run_id,
            record.method_version,
            record.regime,
            record.data_regime,
            claimed.run_min,
            claimed.run_max,
            claimed.session_end.isoformat(),
            claimed.run_count,
            claimed.digest,
            record.m_at_evaluation,
            record.sample_count,
            record.effective_sample_count,
            record.beat_count_net,
            record.beat_count_gross,
            record.base_rate_net,
            record.base_rate_gross,
            record.ci_low_net,
            record.ci_high_net,
            record.bootstrap_low_net,
            record.bootstrap_high_net,
            record.delta_real,
            record.delta_shuffle,
            record.sample_start.isoformat(),
            record.sample_end.isoformat(),
            record.stats_as_of.isoformat(),
            record.computed_at.isoformat(),
            record.recompute_session.isoformat(),
            record.running_commit,
            int(record.selfcheck_passed),
            int(record.data_quality_passed),
            int(record.pit_history_missing),
        )
        placeholders = ", ".join("?" for _ in _STATS_COLUMNS)
        with self._transaction() as conn:
            conn.execute(
                f"INSERT INTO sector_rank_stats ({', '.join(_STATS_COLUMNS)}) "
                f"VALUES ({placeholders})",
                values,
            )
            conn.executemany(
                "INSERT INTO sector_gate_checks "
                "(run_id, check_kind, check_name, status, seed, value, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        record.run_id,
                        "gate",
                        check.gate,
                        "pass" if check.passed else "fail",
                        None,
                        None,
                        check.detail,
                    )
                    for check in record.gate_checks
                ]
                + [
                    (
                        record.run_id,
                        "selfcheck",
                        check.check_name,
                        check.status,
                        check.seed,
                        check.value,
                        check.detail,
                    )
                    for check in record.selfchecks
                ],
            )

    def _load(self, where: str, params: tuple[object, ...]) -> tuple[StatsRecord, ...]:
        self._refuse_legacy()
        with closing(self._connect()) as conn:
            rows = conn.execute(_stats_sql(where), params).fetchall()
        return _records_from_rows(rows, self._verifier)

    def load(self, method_version: str) -> tuple[StatsRecord, ...]:
        """Every row of ``method_version``, oldest first (the batch re-checked on the way out)."""
        return self._load("s.method_version = ?", (method_version,))

    def latest_history(self) -> tuple[StatsRecord, ...]:
        """The history of whichever version wrote the most recent row (gate input)."""
        return self._load(f"s.method_version = {_LATEST_STATS_VERSION_SQL}", ())

    def find(self, run_id: str) -> StatsRecord | None:
        """One row by ``run_id`` (re-checked like every read), or ``None``."""
        found = self._load("s.run_id = ?", (run_id,))
        return found[0] if found else None


#: The version of the most recent statistics row (the gate reads that version's history).
_LATEST_STATS_VERSION_SQL: Final = (
    "(SELECT method_version FROM sector_rank_stats ORDER BY computed_at DESC, run_id DESC LIMIT 1)"
)
_CHECK_COLUMNS: Final[tuple[str, ...]] = (
    "check_kind",
    "check_name",
    "status",
    "seed",
    "value",
    "detail",
)


def _stats_sql(where: str) -> str:
    """Statistics rows matching ``where`` with their check rows, as one LEFT JOIN statement."""
    stats = ", ".join(f"s.{column}" for column in _STATS_COLUMNS)
    checks = ", ".join(f"c.{column}" for column in _CHECK_COLUMNS)
    return f"""
        SELECT {stats}, {checks}
        FROM sector_rank_stats s LEFT JOIN sector_gate_checks c ON c.run_id = s.run_id
        WHERE {where}
        ORDER BY s.computed_at, s.run_id, c.rowid
    """


def _admit_regime(regime: str, data_regime: str, run_id: str) -> None:
    if regime != "pit" or data_regime != "forward_pit":
        raise BiasedDataRejected(
            f"stats run {run_id}: regime={regime!r}, data_regime={data_regime!r}; "
            "only pit / forward_pit may reach the gate (ADR-0012 D-14)"
        )


_DIGEST_PATTERN: Final = re.compile(r"[0-9a-f]{64}")


def record_fingerprint(record: StatsRecord) -> SourceFingerprint:
    """The five ``source_*`` fields of ``record`` as one fingerprint."""
    return SourceFingerprint(
        run_min=record.source_run_min,
        run_max=record.source_run_max,
        session_end=record.source_session_end,
        run_count=record.source_run_count,
        digest=record.source_digest,
    )


def _fingerprint_from_values(values: Sequence[object]) -> SourceFingerprint:
    """The fingerprint from stored ``source_run_min .. source_digest`` column values."""
    return SourceFingerprint(
        run_min=int(cast(int, values[0])),
        run_max=int(cast(int, values[1])),
        session_end=date.fromisoformat(str(values[2])),
        run_count=int(cast(int, values[3])),
        digest=str(values[4]),
    )


def _admit_shape(run_id: str, fingerprint: SourceFingerprint) -> None:
    """A fingerprint that could describe a non-empty source set at all (C-50)."""
    if fingerprint.run_count <= 0:
        raise BiasedDataRejected(f"stats run {run_id}: no source runs (source_run_count <= 0)")
    if not 0 < fingerprint.run_min <= fingerprint.run_max:
        raise BiasedDataRejected(f"stats run {run_id}: source run range is not a market-DB range")
    if not _DIGEST_PATTERN.fullmatch(fingerprint.digest):
        raise BiasedDataRejected(f"stats run {run_id}: source_digest is not a SHA-256 hex digest")


def _admit_sources(
    verifier: SourceTallyReader, rows: Sequence[tuple[str, SourceFingerprint]]
) -> None:
    """The read-time light check of a whole batch: **one** verifier call (C-50).

    Every row's first and last run must be existing ``ok`` runs; the latest row
    (the last one, rows being ordered by ``computed_at``, ``run_id``) must also
    match its source set's count and first / last run. No digest is recomputed.
    """
    if not rows:
        return
    latest_id, latest = rows[-1]
    endpoints = {run for _, fp in rows for run in (fp.run_min, fp.run_max)}
    tally = verifier.source_tally(endpoints, latest.run_max, latest.session_end)
    for run_id, fingerprint in rows:
        unknown = sorted({fingerprint.run_min, fingerprint.run_max} - tally.ok_endpoints)
        if unknown:
            raise BiasedDataRejected(
                f"stats run {run_id}: source runs {unknown} are not ok runs in pit_snapshot_runs"
            )
    if (tally.run_count, tally.run_min, tally.run_max) != (
        latest.run_count,
        latest.run_min,
        latest.run_max,
    ):
        raise BiasedDataRejected(
            f"stats run {latest_id}: source set has {tally.run_count} run(s) "
            f"{tally.run_min}..{tally.run_max} in the market DB, the row says "
            f"{latest.run_count} run(s) {latest.run_min}..{latest.run_max} (ADR-0012 C-50)"
        )


def _records_from_rows(
    rows: Sequence[Sequence[object]], verifier: SourceTallyReader
) -> tuple[StatsRecord, ...]:
    """Rebuild statistics records from :func:`_stats_sql` rows; any doubt refuses the batch."""
    width = len(_STATS_COLUMNS)
    grouped: dict[str, tuple[dict[str, object], list[Sequence[object]]]] = {}
    for row in rows:
        data = dict(zip(_STATS_COLUMNS, row[:width], strict=True))
        run_id = str(data["run_id"])
        if run_id not in grouped:
            grouped[run_id] = (data, [])
        check = row[width:]
        if check[0] is not None:
            grouped[run_id][1].append(check)
    sources: list[tuple[str, SourceFingerprint]] = []
    for run_id, (data, _) in grouped.items():
        _admit_regime(str(data["regime"]), str(data["data_regime"]), run_id)
        fingerprint = _fingerprint_from_values([data[column] for column in _SOURCE_COLUMNS])
        _admit_shape(run_id, fingerprint)
        sources.append((run_id, fingerprint))
    _admit_sources(verifier, sources)
    records: list[StatsRecord] = []
    for (data, own), (_, fingerprint) in zip(grouped.values(), sources, strict=True):
        records.append(
            StatsRecord(
                run_id=str(data["run_id"]),
                method_version=str(data["method_version"]),
                regime=cast(StatsRegime, data["regime"]),
                data_regime=cast(DataRegime, data["data_regime"]),
                source_run_min=fingerprint.run_min,
                source_run_max=fingerprint.run_max,
                source_session_end=fingerprint.session_end,
                source_run_count=fingerprint.run_count,
                source_digest=fingerprint.digest,
                m_at_evaluation=int(cast(int, data["m_at_evaluation"])),
                sample_count=int(cast(int, data["sample_count"])),
                effective_sample_count=float(cast(float, data["effective_sample_count"])),
                beat_count_net=int(cast(int, data["beat_count_net"])),
                beat_count_gross=int(cast(int, data["beat_count_gross"])),
                base_rate_net=float(cast(float, data["base_rate_net"])),
                base_rate_gross=float(cast(float, data["base_rate_gross"])),
                ci_low_net=float(cast(float, data["ci_low_net"])),
                ci_high_net=float(cast(float, data["ci_high_net"])),
                bootstrap_low_net=float(cast(float, data["bootstrap_low_net"])),
                bootstrap_high_net=float(cast(float, data["bootstrap_high_net"])),
                delta_real=cast(float | None, data["delta_real"]),
                delta_shuffle=cast(float | None, data["delta_shuffle"]),
                sample_start=date.fromisoformat(str(data["sample_start"])),
                sample_end=date.fromisoformat(str(data["sample_end"])),
                stats_as_of=date.fromisoformat(str(data["stats_as_of"])),
                computed_at=datetime.fromisoformat(str(data["computed_at"])),
                recompute_session=date.fromisoformat(str(data["recompute_session"])),
                running_commit=str(data["running_commit"]),
                selfcheck_passed=bool(data["selfcheck_passed"]),
                data_quality_passed=bool(data["data_quality_passed"]),
                pit_history_missing=bool(data["pit_history_missing"]),
                gate_checks=tuple(
                    GateCheckRecord(
                        gate=cast(GateName, check[1]),
                        passed=check[2] == "pass",
                        detail=cast(str | None, check[5]),
                    )
                    for check in own
                    if check[0] == "gate"
                ),
                selfchecks=tuple(
                    SelfcheckRecord(
                        check_name=str(check[1]),
                        status=cast(SelfcheckStatus, check[2]),
                        seed=cast(int | None, check[3]),
                        value=cast(float | None, check[4]),
                        detail=cast(str | None, check[5]),
                    )
                    for check in own
                    if check[0] == "selfcheck"
                ),
            )
        )
    return tuple(records)


# ---------------------------------------------------------------------------
# Approvals (append-only; written by the CLI only, C-31)
# ---------------------------------------------------------------------------


class SectorApprovalStore(_SectorDb):
    def add(self, record: ApprovalRecord) -> None:
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO sector_gate_approvals (
                    kind, run_id, method_version, operator, reviewer, review_doc_path,
                    review_doc_blob_hash, approved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.kind,
                    record.run_id,
                    record.method_version,
                    record.operator,
                    record.reviewer,
                    record.review_doc_path,
                    record.review_doc_blob_hash,
                    record.approved_at.isoformat(),
                ),
            )

    def list_for(self, method_version: str) -> tuple[ApprovalRecord, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT kind, run_id, method_version, operator, reviewer, review_doc_path,
                       review_doc_blob_hash, approved_at
                FROM sector_gate_approvals WHERE method_version = ?
                ORDER BY approved_at, approval_id
                """,
                (method_version,),
            ).fetchall()
        return tuple(_approval_from_row(row) for row in rows)


_APPROVAL_COLUMNS: Final = (
    "kind, run_id, method_version, operator, reviewer, review_doc_path, "
    "review_doc_blob_hash, approved_at"
)


def _approval_from_row(row: Sequence[object]) -> ApprovalRecord:
    return ApprovalRecord(
        kind=cast(ApprovalKind, row[0]),
        run_id=str(row[1]),
        method_version=str(row[2]),
        operator=cast(ApprovalOperator, row[3]),
        reviewer=str(row[4]),
        review_doc_path=str(row[5]),
        review_doc_blob_hash=str(row[6]),
        approved_at=datetime.fromisoformat(str(row[7])),
    )


# ---------------------------------------------------------------------------
# Method registry (append-only with two NULL -> value updates)
# ---------------------------------------------------------------------------


class SectorMethodRegistry(_SectorDb):
    def register(
        self,
        definition: SectorMomentumDefinition,
        *,
        frozen_commit: str,
        registered_at: datetime,
        counts_toward_m: bool = False,
    ) -> None:
        """Register a frozen version. ``counts_toward_m=True`` for post-bias proposals (D-6)."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO sector_method_registry (
                    method_version, lookback_days, holding_days, frozen_commit, registered_at,
                    accumulation_start, first_forward_eval_at, counts_toward_m
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)
                """,
                (
                    definition.method_version,
                    definition.lookback_days,
                    definition.holding_days,
                    frozen_commit,
                    registered_at.isoformat(),
                    int(counts_toward_m),
                ),
            )

    def _set_once(self, sql: str, params: tuple[object, ...], what: str) -> None:
        with self._transaction() as conn:
            cursor = conn.execute(sql, params)
            if cursor.rowcount != 1:
                raise ValueError(f"{what} is already set or the version is not registered")

    def record_accumulation_start(self, method_version: str, d0: date) -> None:
        """Write D0 once (D-12)."""
        self._set_once(
            "UPDATE sector_method_registry SET accumulation_start = ? "
            "WHERE method_version = ? AND accumulation_start IS NULL",
            (d0.isoformat(), method_version),
            "accumulation_start",
        )

    def record_first_forward_eval(self, method_version: str, at: datetime) -> None:
        """First statistics on forward_pit data: stamp it and count the version in m (D-6)."""
        self._set_once(
            "UPDATE sector_method_registry SET first_forward_eval_at = ?, counts_toward_m = 1 "
            "WHERE method_version = ? AND first_forward_eval_at IS NULL",
            (at.isoformat(), method_version),
            "first_forward_eval_at",
        )

    def get(self, method_version: str) -> MethodRegistryRow | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT method_version, lookback_days, holding_days, frozen_commit, registered_at,
                       accumulation_start, first_forward_eval_at, counts_toward_m
                FROM sector_method_registry WHERE method_version = ?
                """,
                (method_version,),
            ).fetchone()
        if row is None:
            return None
        return MethodRegistryRow(
            method_version=str(row[0]),
            lookback_days=int(row[1]),
            holding_days=int(row[2]),
            frozen_commit=str(row[3]),
            registered_at=datetime.fromisoformat(str(row[4])),
            accumulation_start=_date(row[5]),
            first_forward_eval_at=(
                datetime.fromisoformat(str(row[6])) if row[6] is not None else None
            ),
            counts_toward_m=bool(row[7]),
        )

    def m(self) -> int:
        """Number of versions that count toward the Bonferroni m (D-6)."""
        with closing(self._connect()) as conn:
            (count,) = conn.execute(
                "SELECT COUNT(*) FROM sector_method_registry WHERE counts_toward_m = 1"
            ).fetchone()
        return int(count)


# ---------------------------------------------------------------------------
# The card's read path (API process): four statements on one connection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardRead:
    """Everything ``GET /api/sectors/momentum`` needs from the main DB."""

    board: StoredBoard | None
    #: Rows of the version that wrote the latest statistics row, oldest first.
    stats_history: tuple[StatsRecord, ...]
    #: Approvals of that same version.
    approvals: tuple[ApprovalRecord, ...]
    #: D0 of the requested method version (registry); None before D0 / unregistered.
    accumulation_start: date | None
    #: Why the statistics were refused on the way out (D-14, fail closed); None if not.
    stats_rejected: str | None = None


class SectorCardReader:
    """The API's read of the card: one connection, at most four SQL statements.

    1. the latest board (header, ranked, excluded) -- one JOIN;
    2. the latest version's statistics with their check rows -- one LEFT JOIN;
    3. that version's approvals;
    4. the requested version's D0 from the registry.

    The statistics are then re-admitted exactly as :class:`SectorStatsRepository`
    reads them (D-14, C-50): one ``verifier.source_tally`` call -- one market-DB
    statement -- for the whole batch, never a digest. Every column read is
    fixed width; ``sector_board.source_run_ids`` is not selected (C-51).
    ``busy_timeout`` is set through the connection's ``timeout`` (C-9), so no
    ``PRAGMA`` statement is spent per request (C-6 counts statements).

    A pre-v9 statistics table with rows (C-50) is found once, at construction:
    its statistics are then refused on every read (NE-6, fail closed) without
    being queried.
    """

    def __init__(self, verifier: SourceTallyReader, db_path: str | Path | None = None) -> None:
        schema = _SectorDb(db_path)
        self._db_path = schema.db_path
        self._legacy = (
            _legacy_message(schema.legacy_stats_rows)
            if schema.legacy_stats_rows is not None
            else None
        )
        if self._legacy is not None:
            logger.error(self._legacy)
        self._verifier = verifier

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=BUSY_TIMEOUT_MS / 1000)

    def read(self, market: str, method_version: str) -> CardRead:
        with closing(self._connect()) as conn:
            board_rows = conn.execute(_board_sql(_LATEST_BOARD_ID_SQL), (market,)).fetchall()
            stats_rows = (
                conn.execute(
                    _stats_sql(f"s.method_version = {_LATEST_STATS_VERSION_SQL}")
                ).fetchall()
                if self._legacy is None
                else []
            )
            approval_rows = conn.execute(
                f"SELECT {_APPROVAL_COLUMNS} FROM sector_gate_approvals "
                f"WHERE method_version = {_LATEST_STATS_VERSION_SQL} "
                "ORDER BY approved_at, approval_id"
            ).fetchall()
            registry = conn.execute(
                "SELECT accumulation_start FROM sector_method_registry WHERE method_version = ?",
                (method_version,),
            ).fetchone()
        rejected: str | None = self._legacy
        history: tuple[StatsRecord, ...] = ()
        if rejected is None:
            try:
                history = _records_from_rows(stats_rows, self._verifier)
            except BiasedDataRejected as exc:
                rejected = str(exc)
        return CardRead(
            board=_board_from_rows(board_rows),
            stats_history=history,
            approvals=tuple(_approval_from_row(row) for row in approval_rows) if history else (),
            accumulation_start=_date(cast(str | None, registry[0])) if registry else None,
            stats_rejected=rejected,
        )
