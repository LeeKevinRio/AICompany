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
is not ``regime="pit"`` + ``data_regime="forward_pit"`` with every
``source_run_id`` present in the market DB's ``pit_snapshot_runs`` -- raising
:class:`BiasedDataRejected` (D-14, C-27). The market DB is reached through an
injected :class:`RunIdVerifier`, because this package may not import the
market-DB store.

Ratios are never stored: the header and sector rows keep counts, and readers
rebuild ratios through :mod:`app.sectors.coverage`, the one formula.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Collection, Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final, Protocol, cast

from app.data.cache import resolve_db_path
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
        source_run_ids TEXT NOT NULL,
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
    """A statistics record that is not forward point-in-time data (D-14, C-27)."""


class RunIdVerifier(Protocol):
    """Answers which snapshot run ids exist in the market DB's ``pit_snapshot_runs``."""

    def existing_run_ids(self, run_ids: Collection[str]) -> frozenset[str]: ...


class _SectorDb:
    """Connection discipline shared by every store here (WAL, busy_timeout, closing)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            for statement in (*_SCHEMA, *_TRIGGERS):
                conn.execute(statement)

    @property
    def db_path(self) -> Path:
        return self._db_path

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
    source_run_ids: tuple[str, ...]
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
            row = conn.execute(
                "SELECT board_id FROM sector_board WHERE market = ? "
                "ORDER BY data_as_of DESC, computed_at DESC, board_id DESC LIMIT 1",
                (market,),
            ).fetchone()
        return str(row[0]) if row else None

    def load_board(self, board_id: str) -> StoredBoard | None:
        with closing(self._connect()) as conn:
            header = conn.execute(
                """
                SELECT board_id, market, method_version, lookback_days, holding_days,
                       data_as_of, window_start, data_source, bars_run_id, bars_recorded_at,
                       computed_at, benchmark_return_l, reference_taiex_return_l,
                       market_expected_count, market_missing_count,
                       market_ex_date_excluded_count, market_corporate_action_excluded_count,
                       ex_dividend_feed_covered, constituent_invariant_violated, source_run_ids
                FROM sector_board WHERE board_id = ?
                """,
                (board_id,),
            ).fetchone()
            if header is None:
                return None
            members = conn.execute(
                """
                SELECT rank, sector_code, sector_name, sector_return_l, rel_return_l, up_count,
                       expected_count, missing_count, ex_date_excluded_count,
                       corporate_action_excluded_count, turnover_value_ratio_5_20,
                       top_contributor_share, single_stock_dominated, member_symbols, constituents
                FROM sector_board_members WHERE board_id = ? ORDER BY rank
                """,
                (board_id,),
            ).fetchall()
            excluded = conn.execute(
                """
                SELECT sector_code, sector_name, reason_code, expected_count, missing_count,
                       ex_date_excluded_count, corporate_action_excluded_count, internal_reason
                FROM sector_board_excluded WHERE board_id = ? ORDER BY sector_code
                """,
                (board_id,),
            ).fetchall()
        ranked = tuple(
            StoredRankedSector(
                rank=int(row[0]),
                sector_code=str(row[1]),
                sector_name=str(row[2]),
                sector_return_L=float(row[3]),
                rel_return_L=float(row[4]),
                up_count=int(row[5]),
                coverage=coverage_from_counts(
                    expected=int(row[6]),
                    missing=int(row[7]),
                    ex_date=int(row[8]),
                    corporate_action=int(row[9]),
                ),
                turnover_value_ratio_5_20=row[10],
                top_contributor_share=row[11],
                single_stock_dominated=bool(row[12]),
                member_symbols=tuple(json.loads(row[13])),
                constituents=tuple(
                    StoredConstituent(
                        symbol=item["symbol"], name=item["name"], return_L=item["return_L"]
                    )
                    for item in json.loads(row[14])
                ),
            )
            for row in members
        )
        excluded_rows = tuple(
            StoredExcludedSector(
                sector_code=str(row[0]),
                sector_name=str(row[1]),
                reason_code=cast(ReasonCode, row[2]),
                coverage=coverage_from_counts(
                    expected=int(row[3]),
                    missing=int(row[4]),
                    ex_date=int(row[5]),
                    corporate_action=int(row[6]),
                ),
                internal_reason=row[7],
            )
            for row in excluded
        )
        data_as_of = _date(header[5])
        if data_as_of is None:  # pragma: no cover - NOT NULL column
            raise ValueError("sector_board.data_as_of is NULL")
        return StoredBoard(
            board_id=str(header[0]),
            market=str(header[1]),
            method_version=str(header[2]),
            lookback_days=int(header[3]),
            holding_days=int(header[4]),
            data_as_of=data_as_of,
            window_start=_date(header[6]),
            data_source=str(header[7]),
            bars_run_id=header[8],
            bars_recorded_at=header[9],
            computed_at=str(header[10]),
            benchmark_return_L=header[11],
            reference_taiex_return_L=header[12],
            market_expected_count=int(header[13]),
            market_missing_count=int(header[14]),
            market_ex_date_excluded_count=int(header[15]),
            market_corporate_action_excluded_count=int(header[16]),
            ex_dividend_feed_covered=bool(header[17]),
            constituent_invariant_violated=bool(header[18]),
            source_run_ids=tuple(json.loads(header[19])),
            ranked=ranked,
            excluded=excluded_rows,
        )


# ---------------------------------------------------------------------------
# Statistics (append-only, PIT only)
# ---------------------------------------------------------------------------

_STATS_COLUMNS: Final[tuple[str, ...]] = (
    "run_id",
    "method_version",
    "regime",
    "data_regime",
    "source_run_ids",
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


class SectorStatsRepository(_SectorDb):
    """``sector_rank_stats`` + ``sector_gate_checks``; forward PIT records only."""

    def __init__(self, verifier: RunIdVerifier, db_path: str | Path | None = None) -> None:
        super().__init__(db_path)
        self._verifier = verifier

    def _admit(
        self, *, regime: str, data_regime: str, source_run_ids: tuple[str, ...], run_id: str
    ) -> None:
        if regime != "pit" or data_regime != "forward_pit":
            raise BiasedDataRejected(
                f"stats run {run_id}: regime={regime!r}, data_regime={data_regime!r}; "
                "only pit / forward_pit may reach the gate (ADR-0012 D-14)"
            )
        if not source_run_ids:
            raise BiasedDataRejected(f"stats run {run_id}: no source_run_ids")
        known = self._verifier.existing_run_ids(source_run_ids)
        unknown = sorted(set(source_run_ids) - set(known))
        if unknown:
            raise BiasedDataRejected(
                f"stats run {run_id}: source runs {unknown} are not in pit_snapshot_runs"
            )

    def save(self, record: StatsRecord) -> None:
        """Append one statistics row and its G1..G6 / T1..T9 check rows."""
        self._admit(
            regime=record.regime,
            data_regime=record.data_regime,
            source_run_ids=record.source_run_ids,
            run_id=record.run_id,
        )
        values = (
            record.run_id,
            record.method_version,
            record.regime,
            record.data_regime,
            json.dumps(sorted(record.source_run_ids)),
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
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {', '.join(_STATS_COLUMNS)} FROM sector_rank_stats {where} "
                "ORDER BY computed_at, run_id",
                params,
            ).fetchall()
            run_ids = [str(row[0]) for row in rows]
            checks: dict[str, list[tuple[str, str, str, int | None, float | None, str | None]]]
            checks = {run_id: [] for run_id in run_ids}
            if run_ids:
                marks = ", ".join("?" for _ in run_ids)
                for check in conn.execute(
                    "SELECT run_id, check_kind, check_name, status, seed, value, detail "
                    f"FROM sector_gate_checks WHERE run_id IN ({marks}) "
                    "ORDER BY run_id, rowid",
                    run_ids,
                ).fetchall():
                    checks[str(check[0])].append(
                        (check[1], check[2], check[3], check[4], check[5], check[6])
                    )
        records: list[StatsRecord] = []
        for row in rows:
            data = dict(zip(_STATS_COLUMNS, row, strict=True))
            source_run_ids = tuple(json.loads(str(data["source_run_ids"])))
            self._admit(
                regime=str(data["regime"]),
                data_regime=str(data["data_regime"]),
                source_run_ids=source_run_ids,
                run_id=str(data["run_id"]),
            )
            own = checks[str(data["run_id"])]
            records.append(
                StatsRecord(
                    run_id=str(data["run_id"]),
                    method_version=str(data["method_version"]),
                    regime=cast(StatsRegime, data["regime"]),
                    data_regime=cast(DataRegime, data["data_regime"]),
                    source_run_ids=source_run_ids,
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
                            gate=cast(GateName, name), passed=status == "pass", detail=detail
                        )
                        for kind, name, status, _seed, _value, detail in own
                        if kind == "gate"
                    ),
                    selfchecks=tuple(
                        SelfcheckRecord(
                            check_name=name,
                            status=cast(SelfcheckStatus, status),
                            seed=seed,
                            value=value,
                            detail=detail,
                        )
                        for kind, name, status, seed, value, detail in own
                        if kind == "selfcheck"
                    ),
                )
            )
        return tuple(records)

    def load(self, method_version: str) -> tuple[StatsRecord, ...]:
        """Every row of ``method_version``, oldest first (each re-checked on the way out)."""
        return self._load("WHERE method_version = ?", (method_version,))

    def latest_history(self) -> tuple[StatsRecord, ...]:
        """The history of whichever version wrote the most recent row (gate input)."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT method_version FROM sector_rank_stats "
                "ORDER BY computed_at DESC, run_id DESC LIMIT 1"
            ).fetchone()
        return self.load(str(row[0])) if row else ()


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
        return tuple(
            ApprovalRecord(
                kind=cast(ApprovalKind, row[0]),
                run_id=str(row[1]),
                method_version=str(row[2]),
                operator=cast(ApprovalOperator, row[3]),
                reviewer=str(row[4]),
                review_doc_path=str(row[5]),
                review_doc_blob_hash=str(row[6]),
                approved_at=datetime.fromisoformat(str(row[7])),
            )
            for row in rows
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
