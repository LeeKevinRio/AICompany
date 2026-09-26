"""SQLite-backed, append-only store for the forward-looking PIT snapshot (ADR-0012 D-2).

Separate database file from the main store (``STOCK_DESK_DB_PATH`` /
``price_bars_cache``) and from the research store (its own file, named only
inside ``app/research/``, C-27): ``STOCK_DESK_MARKET_DB_PATH`` (default
``./data/stock-desk-market.db``). This string must only appear here and in
tests (T-3, C-8) -- no other module may import or hardcode it.

## Why a separate file (ADR-0012 Option B3)

The market DB holds ``pit_snapshot_runs``, ``market_daily_bars``,
``pit_listing_rows``, ``pit_classification_rows``,
``pit_dividend_announce_rows`` and ``market_backfill_progress`` -- roughly
27万 rows/year of whole-market daily bars plus the PIT listing/classification/
ex-dividend history. None of it is ever written to or read from
``price_bars_cache`` or its two log tables (C-7): the write-lock and quota
disciplines those tables observe (ADR-0009/ADR-0010) are for the
request-triggered, per-symbol positions data chain, not this scheduled,
whole-market batch chain.

## Append-only discipline (D-2, C-10, C-21's sibling for this DB)

Every table here is INSERT-only. This store does not implement update/delete
methods, and every table additionally carries ``BEFORE UPDATE``/
``BEFORE DELETE`` SQLite triggers that ``RAISE(ABORT, 'append-only')`` --
belt and suspenders, per ADR-0007's disclosed reality that a Python-level
omission alone is not an enforcement boundary.

The one exception is ``market_backfill_progress``: it is a *checkpoint* for
the pre-D0 warm-up CLI (ADR-0012 D-3), not part of the permanent PIT record,
so it is allowed ordinary upserts and carries no append-only trigger.

``recorded_at`` is filled in by this store's own clock (injectable for
tests), never accepted from a caller -- callers cannot claim a row was seen
earlier than it actually was (D-2, C-10, T-4).

## Content-addressed rows (D-2)

``pit_listing_rows``, ``pit_classification_rows`` and
``pit_dividend_announce_rows`` are keyed on ``(content_hash, key)``.
``content_hash`` is the SHA-256 of the day's full row set for that kind,
canonically serialized (sorted, JSON-encoded); ``key`` is ``symbol`` for
listing/classification and ``"{symbol}|{raw_date}"`` for dividend
announcements (a symbol can appear more than once per day in
``TWT48U_ALL``, once per upcoming ex-date). When a day's content is
byte-identical to a previous day's (the very common case for classification
and listing, which change rarely), the same ``content_hash`` already has
rows on disk and this store skips the redundant insert -- "跨日只存一份".
Every day still gets its own ``pit_snapshot_runs`` row pointing at that
(possibly shared) ``content_hash``, so the append-only capture history is
unbroken even when nothing changed.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Callable, Collection, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final

import pandas as pd

from app.data.interface import (
    BarSnapshotRow,
    ClassificationSnapshotRow,
    DividendAnnounceSnapshotRow,
    ListingSnapshotRow,
    SnapshotKind,
    SnapshotRunStatus,
)
from app.data.panel import (
    BARS_COLUMNS,
    CLASSIFICATION_COLUMNS,
    EX_DIVIDEND_COLUMNS,
    LISTING_COLUMNS,
    RUNS_COLUMNS,
    PanelFrames,
    SourceFingerprint,
    SourceTally,
    source_fingerprint,
)

#: Default location; overridden by the ``STOCK_DESK_MARKET_DB_PATH``
#: environment variable. This literal string, and the env var name below,
#: must only appear in this file and in tests (C-8, T-3).
DEFAULT_MARKET_DB_PATH: Final[str] = "./data/stock-desk-market.db"
_MARKET_DB_PATH_ENV_VAR: Final[str] = "STOCK_DESK_MARKET_DB_PATH"

_BUSY_TIMEOUT_MS: Final[int] = 5000

#: Bars run coverage below this is not eligible for ``status="ok"`` (D-2).
#: Enforcement lives in ``app.services.pit_snapshot`` (it needs the PIT
#: listing size to compute ``expected_count``); this constant is re-exported
#: here so the two files never drift.
BARS_OK_COVERAGE_MIN: Final[float] = 0.98

#: A kind without an ``ok`` run for more than this many consecutive trading
#: sessions makes the affected samples invalid (D-2 "缺日沿用"). This store
#: does not itself implement the carry-forward view -- that is
#: ``MarketPanel.as_of()``'s job (``app.data.panel``, dev-lead) -- but the
#: constant is defined once here since it is this store's data the rule
#: applies to.
MAX_CARRY_FORWARD_SESSIONS: Final[int] = 5

_ALL_KINDS: Final[tuple[SnapshotKind, ...]] = (
    "bars",
    "listing",
    "classification",
    "dividend_announce",
)

_CREATE_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS pit_snapshot_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('bars', 'listing', 'classification', 'dividend_announce')),
    session_date TEXT,
    recorded_at TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'partial', 'failed', 'quality_failed')),
    row_count INTEGER NOT NULL,
    expected_count INTEGER,
    content_hash TEXT,
    reason TEXT
)
"""

_CREATE_RUNS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_pit_snapshot_runs_kind_session_status
ON pit_snapshot_runs (kind, session_date, status)
"""

_CREATE_BARS_SQL = """
CREATE TABLE IF NOT EXISTS market_daily_bars (
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    session_date TEXT NOT NULL,
    market TEXT NOT NULL,
    exchange TEXT NOT NULL,
    open TEXT NOT NULL,
    high TEXT NOT NULL,
    low TEXT NOT NULL,
    close TEXT NOT NULL,
    shares INTEGER NOT NULL,
    traded_value TEXT NOT NULL,
    change TEXT,
    source TEXT NOT NULL,
    PRIMARY KEY (run_id, symbol)
) WITHOUT ROWID
"""

_CREATE_BARS_SESSION_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_market_daily_bars_session_symbol
ON market_daily_bars (session_date, symbol)
"""

_CREATE_BARS_SYMBOL_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_market_daily_bars_symbol_session
ON market_daily_bars (symbol, session_date)
"""

_CREATE_LISTING_SQL = """
CREATE TABLE IF NOT EXISTS pit_listing_rows (
    content_hash TEXT NOT NULL,
    symbol TEXT NOT NULL,
    security_type TEXT NOT NULL,
    PRIMARY KEY (content_hash, symbol)
) WITHOUT ROWID
"""

_CREATE_CLASSIFICATION_SQL = """
CREATE TABLE IF NOT EXISTS pit_classification_rows (
    content_hash TEXT NOT NULL,
    symbol TEXT NOT NULL,
    sector_code TEXT NOT NULL,
    sector_name TEXT NOT NULL,
    PRIMARY KEY (content_hash, symbol)
) WITHOUT ROWID
"""

_CREATE_DIVIDEND_SQL = """
CREATE TABLE IF NOT EXISTS pit_dividend_announce_rows (
    content_hash TEXT NOT NULL,
    key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    ex_date TEXT,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (content_hash, key)
) WITHOUT ROWID
"""

#: Checkpoint table for the pre-D0 warm-up CLI (``app.services.pit_snapshot
#: --warmup``). Deliberately mutable (ordinary upsert) -- see module
#: docstring "Append-only discipline" -- because it tracks *tool progress*,
#: not part of the permanent PIT record; losing or rewriting it only costs a
#: re-fetch, never a look-ahead violation.
_CREATE_BACKFILL_PROGRESS_SQL = """
CREATE TABLE IF NOT EXISTS market_backfill_progress (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'done', 'failed')),
    last_attempt_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market)
)
"""

#: (table, id-column-list) pairs the append-only triggers below are built for.
_APPEND_ONLY_TABLES: Final[tuple[str, ...]] = (
    "pit_snapshot_runs",
    "market_daily_bars",
    "pit_listing_rows",
    "pit_classification_rows",
    "pit_dividend_announce_rows",
)


def _append_only_trigger_sql(table: str) -> tuple[str, str]:
    update_sql = f"""
    CREATE TRIGGER IF NOT EXISTS {table}_no_update
    BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END
    """
    delete_sql = f"""
    CREATE TRIGGER IF NOT EXISTS {table}_no_delete
    BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END
    """
    return update_sql, delete_sql


def resolve_market_db_path() -> Path:
    """Resolve the market DB path from ``STOCK_DESK_MARKET_DB_PATH`` (or the default)."""
    raw = os.environ.get(_MARKET_DB_PATH_ENV_VAR, DEFAULT_MARKET_DB_PATH)
    return Path(raw)


def _to_utc_timestamp(recorded_at: str) -> pd.Timestamp:
    """Parse a stored ISO ``recorded_at`` string into a tz-aware UTC ``pd.Timestamp``.

    ``self._clock()`` always writes a UTC-aware ``datetime.isoformat()``
    string (never caller-supplied, see :meth:`MarketPanelStore.record_run`),
    so this is a round-trip, not a guess -- but it is defensive about the
    offset already being UTC vs. some other explicit offset, since
    ``pd.Timestamp`` preserves whatever offset was written.
    """
    ts = pd.Timestamp(recorded_at)
    return ts.tz_convert("UTC") if ts.tzinfo is not None else ts.tz_localize("UTC")


#: Columns every ``pit_snapshot_runs`` read feeding :func:`_runs_frame` selects, in order.
_RUN_SELECT_COLUMNS: Final = (
    "run_id, kind, session_date, recorded_at, source, status, "
    "row_count, expected_count, content_hash"
)

#: The source set 𝒮 of a statistics row (ADR-0012 C-50), for named parameters
#: ``:session_end`` and ``:run_max``.
_SOURCE_SET_WHERE: Final = (
    "status = 'ok' AND session_date IS NOT NULL "
    "AND session_date <= :session_end AND run_id <= :run_max"
)

#: Write time: every run of 𝒮, for the full recompute of its fingerprint.
_SOURCE_RUNS_SQL: Final = (
    f"SELECT {_RUN_SELECT_COLUMNS} FROM pit_snapshot_runs WHERE {_SOURCE_SET_WHERE} ORDER BY run_id"
)

#: Read time: the light check as ONE statement (C-50, C-51) -- which of the
#: asked-for endpoints are existing ok runs, and the count / first / last run of
#: the latest row's 𝒮. No row of 𝒮 leaves the database.
_SOURCE_TALLY_SQL: Final = f"""
    SELECT
        (SELECT json_group_array(run_id) FROM pit_snapshot_runs
         WHERE status = 'ok' AND session_date IS NOT NULL
           AND run_id IN (SELECT value FROM json_each(:endpoints))),
        COUNT(*), MIN(run_id), MAX(run_id)
    FROM pit_snapshot_runs
    WHERE {_SOURCE_SET_WHERE}
"""


def _runs_frame(rows: Sequence[Sequence[object]]) -> pd.DataFrame:
    """``PanelFrames.runs`` from ``pit_snapshot_runs`` rows selected as :data:`_RUN_SELECT_COLUMNS`.

    The one row -> frame conversion: :meth:`MarketPanelStore.load_panel_frames`
    builds the evaluator's frame with it and the fingerprint recompute builds
    the verifier's (ADR-0012 C-50), so both hash the same values.
    """
    return pd.DataFrame(
        [
            {
                "run_id": str(run_id),
                "kind": kind,
                "session_date": date.fromisoformat(str(session_date)),
                "recorded_at": _to_utc_timestamp(str(recorded_at)),
                "source": source,
                "status": status,
                "row_count": row_count,
                "expected_count": expected_count,
            }
            for (
                run_id,
                kind,
                session_date,
                recorded_at,
                source,
                status,
                row_count,
                expected_count,
                _content_hash,
            ) in rows
        ],
        columns=list(RUNS_COLUMNS),
    )


def _source_fingerprint_on(
    conn: sqlite3.Connection, run_max: int, session_end: date
) -> SourceFingerprint | None:
    """Recompute the fingerprint of 𝒮(``run_max``, ``session_end``) from the runs on disk."""
    rows = conn.execute(
        _SOURCE_RUNS_SQL, {"session_end": session_end.isoformat(), "run_max": int(run_max)}
    ).fetchall()
    return source_fingerprint(_runs_frame(rows))


def _source_tally_on(
    conn: sqlite3.Connection, endpoints: Collection[int], run_max: int, session_end: date
) -> SourceTally:
    row = conn.execute(
        _SOURCE_TALLY_SQL,
        {
            "endpoints": json.dumps(sorted({int(value) for value in endpoints})),
            "session_end": session_end.isoformat(),
            "run_max": int(run_max),
        },
    ).fetchone()
    found, count, first, last = row
    return SourceTally(
        ok_endpoints=frozenset(int(value) for value in json.loads(found or "[]")),
        run_count=int(count),
        run_min=int(first) if first is not None else None,
        run_max=int(last) if last is not None else None,
    )


def _canonical_content_hash(rows: Sequence[tuple[object, ...]]) -> str:
    """SHA-256 of a day's full row set for one content-addressed kind.

    Rows are sorted before hashing so row order (a JSON/HTTP artifact, not a
    fact about the data) never changes the hash of otherwise-identical
    content.
    """
    canonical = json.dumps(sorted(rows), sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KindRunSummary:
    """One kind's run history inside a queried date window (for D-12 ``pit_gaps``).

    ``ok_sessions`` and ``last_ok_session`` are exactly what D-2's "缺日沿用"
    /``pit_gaps`` computation needs to know per kind; this store does not
    itself decide PIT visibility or carry-forward eligibility (D-12: that is
    ``app.sectors.gate.pit_gaps``, which must not touch ``sqlite3`` per C-24
    -- it consumes pre-read summaries like this one instead).
    """

    kind: SnapshotKind
    ok_sessions: frozenset[date]
    last_ok_session: date | None


class MarketPanelStore:
    """Append-only SQLite (WAL) store for the ADR-0012 forward-looking PIT snapshot."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_market_db_path()
        self._clock = clock
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_RUNS_SQL)
            conn.execute(_CREATE_RUNS_INDEX_SQL)
            conn.execute(_CREATE_BARS_SQL)
            conn.execute(_CREATE_BARS_SESSION_INDEX_SQL)
            conn.execute(_CREATE_BARS_SYMBOL_INDEX_SQL)
            conn.execute(_CREATE_LISTING_SQL)
            conn.execute(_CREATE_CLASSIFICATION_SQL)
            conn.execute(_CREATE_DIVIDEND_SQL)
            conn.execute(_CREATE_BACKFILL_PROGRESS_SQL)
            for table in _APPEND_ONLY_TABLES:
                update_sql, delete_sql = _append_only_trigger_sql(table)
                conn.execute(update_sql)
                conn.execute(delete_sql)

    # -- writes -------------------------------------------------------

    def record_run(
        self,
        *,
        kind: SnapshotKind,
        session_date: date | None,
        source: str,
        status: SnapshotRunStatus,
        row_count: int,
        expected_count: int | None,
        reason: str | None = None,
        bars_rows: Sequence[BarSnapshotRow] = (),
        listing_rows: Sequence[ListingSnapshotRow] = (),
        classification_rows: Sequence[ClassificationSnapshotRow] = (),
        dividend_announce_rows: Sequence[DividendAnnounceSnapshotRow] = (),
    ) -> int:
        """Write one ``pit_snapshot_runs`` row (plus its content) and return ``run_id``.

        ``recorded_at`` is never a parameter -- it is this store's own clock
        (D-2, C-10, T-4). Exactly one of the four ``*_rows`` sequences should
        be non-empty, matching ``kind``; the others are ignored. Passing rows
        for a non-``ok``/``partial`` run (e.g. ``status="failed"``) is a
        caller bug -- callers should pass an empty sequence in that case, and
        this method does not second-guess it beyond writing what it is given.

        Every row written by one call shares this run's single
        ``session_date`` -- ``market_daily_bars``'s primary key is
        ``(run_id, symbol)`` (D-2), so one run cannot hold more than one row
        per symbol, i.e. cannot span more than one trading session. The
        pre-D0 warm-up backfill (D-3), which fetches many sessions per
        symbol from FinMind, therefore does **not** use this method for its
        bars -- see :meth:`record_symbol_backfill`, which writes one run per
        *day* per symbol, atomically per symbol.
        """
        recorded_at = self._clock()
        content_hash: str | None = None
        with closing(self._connect()) as conn, conn:
            if kind == "listing" and listing_rows:
                content_hash = self._write_listing_content(conn, listing_rows)
            elif kind == "classification" and classification_rows:
                content_hash = self._write_classification_content(conn, classification_rows)
            elif kind == "dividend_announce" and dividend_announce_rows:
                content_hash = self._write_dividend_content(conn, dividend_announce_rows)

            cursor = conn.execute(
                """
                INSERT INTO pit_snapshot_runs
                    (kind, session_date, recorded_at, source, status,
                     row_count, expected_count, content_hash, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kind,
                    session_date.isoformat() if session_date is not None else None,
                    recorded_at.isoformat(),
                    source,
                    status,
                    row_count,
                    expected_count,
                    content_hash,
                    reason,
                ),
            )
            run_id = int(cursor.lastrowid)  # type: ignore[arg-type]

            if kind == "bars" and bars_rows and session_date is not None:
                conn.executemany(
                    """
                    INSERT INTO market_daily_bars
                        (run_id, symbol, session_date, market, exchange,
                         open, high, low, close, shares, traded_value, change, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id,
                            row.symbol,
                            session_date.isoformat(),
                            "TW",
                            "twse",
                            str(row.open),
                            str(row.high),
                            str(row.low),
                            str(row.close),
                            row.shares,
                            str(row.traded_value),
                            str(row.change) if row.change is not None else None,
                            source,
                        )
                        for row in bars_rows
                    ],
                )
        return run_id

    def _write_listing_content(
        self, conn: sqlite3.Connection, rows: Sequence[ListingSnapshotRow]
    ) -> str:
        keyed = {row.symbol: row.security_type for row in rows}
        content_hash = _canonical_content_hash(sorted(keyed.items()))
        existing = conn.execute(
            "SELECT 1 FROM pit_listing_rows WHERE content_hash = ? LIMIT 1", (content_hash,)
        ).fetchone()
        if existing is None:
            conn.executemany(
                "INSERT INTO pit_listing_rows (content_hash, symbol, security_type) "
                "VALUES (?, ?, ?)",
                [(content_hash, symbol, security_type) for symbol, security_type in keyed.items()],
            )
        return content_hash

    def _write_classification_content(
        self, conn: sqlite3.Connection, rows: Sequence[ClassificationSnapshotRow]
    ) -> str:
        keyed = {row.symbol: (row.sector_code, row.sector_name) for row in rows}
        content_hash = _canonical_content_hash(
            sorted((symbol, code, name) for symbol, (code, name) in keyed.items())
        )
        existing = conn.execute(
            "SELECT 1 FROM pit_classification_rows WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ).fetchone()
        if existing is None:
            conn.executemany(
                "INSERT INTO pit_classification_rows "
                "(content_hash, symbol, sector_code, sector_name) VALUES (?, ?, ?, ?)",
                [(content_hash, symbol, code, name) for symbol, (code, name) in keyed.items()],
            )
        return content_hash

    def _write_dividend_content(
        self, conn: sqlite3.Connection, rows: Sequence[DividendAnnounceSnapshotRow]
    ) -> str:
        # ``key`` disambiguates a symbol appearing more than once per day
        # (TWT48U_ALL lists one row per upcoming ex-date, and a symbol may
        # have more than one pending event). A colliding key within the same
        # batch is a genuine payload anomaly (skill red line: surface, don't
        # silently drop) -- the later row wins and the collision count is
        # folded into the caller-visible row_count mismatch, since this store
        # layer has no channel to raise without breaking the "one failing
        # kind never takes down the batch" rule; the provider is expected to
        # keep raw dates distinguishable enough that this does not happen in
        # practice.
        keyed: dict[str, tuple[str, str | None, dict[str, str]]] = {}
        for row in rows:
            raw_date = row.raw.get("Date", "")
            key = f"{row.symbol}|{raw_date}"
            keyed[key] = (row.symbol, row.ex_date.isoformat() if row.ex_date else None, row.raw)
        content_hash = _canonical_content_hash(
            sorted(
                (key, symbol, ex_date, json.dumps(raw, sort_keys=True))
                for key, (symbol, ex_date, raw) in keyed.items()
            )
        )
        existing = conn.execute(
            "SELECT 1 FROM pit_dividend_announce_rows WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ).fetchone()
        if existing is None:
            conn.executemany(
                "INSERT INTO pit_dividend_announce_rows "
                "(content_hash, key, symbol, ex_date, raw_json) VALUES (?, ?, ?, ?, ?)",
                [
                    (content_hash, key, symbol, ex_date, json.dumps(raw, sort_keys=True))
                    for key, (symbol, ex_date, raw) in keyed.items()
                ],
            )
        return content_hash

    def record_symbol_backfill(
        self, *, symbol: str, source: str, rows: Sequence[tuple[date, BarSnapshotRow]]
    ) -> list[int]:
        """Write one ``kind="bars"`` run PER trading day for one symbol's warm-up history.

        ADR-0012 D-3's "以 symbol 為最小重試單位，一檔一個 transaction" is
        honoured at the *transaction* level, not the *run* level:
        ``market_daily_bars``'s primary key is ``(run_id, symbol)`` (D-2), so
        a run cannot hold two days for the same symbol -- every day in
        ``rows`` gets its own ``pit_snapshot_runs`` row (``status="ok"``,
        ``row_count=1``), and all of them are written inside one SQLite
        transaction so a crash mid-backfill leaves either every day for this
        symbol committed or none of them, never a partial day set.

        This also means each day this symbol covers correctly shows up in
        ``run_status_summary``/``ok_run_sessions`` for ``kind="bars"`` --
        unlike a single multi-day run would, which the run-level PIT
        visibility gate in ``app.data.panel`` can only test against one
        ``session_date`` at a time.
        """
        recorded_at = self._clock()
        run_ids: list[int] = []
        with closing(self._connect()) as conn, conn:
            for session_date, bar in sorted(rows, key=lambda item: item[0]):
                cursor = conn.execute(
                    """
                    INSERT INTO pit_snapshot_runs
                        (kind, session_date, recorded_at, source, status,
                         row_count, expected_count, content_hash, reason)
                    VALUES ('bars', ?, ?, ?, 'ok', 1, NULL, NULL, NULL)
                    """,
                    (session_date.isoformat(), recorded_at.isoformat(), source),
                )
                run_id = int(cursor.lastrowid)  # type: ignore[arg-type]
                conn.execute(
                    """
                    INSERT INTO market_daily_bars
                        (run_id, symbol, session_date, market, exchange,
                         open, high, low, close, shares, traded_value, change, source)
                    VALUES (?, ?, ?, 'TW', 'twse', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        bar.symbol,
                        session_date.isoformat(),
                        str(bar.open),
                        str(bar.high),
                        str(bar.low),
                        str(bar.close),
                        bar.shares,
                        str(bar.traded_value),
                        str(bar.change) if bar.change is not None else None,
                        source,
                    ),
                )
                run_ids.append(run_id)
        return run_ids

    def upsert_backfill_progress(
        self,
        symbol: str,
        *,
        market: str = "TW",
        status: str,
        last_error: str | None = None,
        at: datetime | None = None,
    ) -> None:
        """Record the warm-up CLI's per-symbol checkpoint (mutable, see module docstring)."""
        moment = at if at is not None else self._clock()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO market_backfill_progress
                    (symbol, market, status, last_attempt_at, last_error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, market) DO UPDATE SET
                    status=excluded.status,
                    last_attempt_at=excluded.last_attempt_at,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (symbol, market, status, moment.isoformat(), last_error, moment.isoformat()),
            )

    def backfill_progress(self, *, market: str = "TW") -> dict[str, str]:
        """``{symbol: status}`` for every symbol the warm-up CLI has touched."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT symbol, status FROM market_backfill_progress WHERE market = ?",
                (market,),
            ).fetchall()
        return {symbol: status for symbol, status in rows}

    # -- reads ----------------------------------------------------------

    def first_all_kinds_ok_session(self) -> date | None:
        """D0: the earliest session where all four kinds have an ``ok`` run.

        Used by the warm-up CLI (D-3: "D0 之後 CLI 拒絕執行暖身") -- a single
        ``INTERSECT`` query, not four round trips.
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT MIN(session_date) FROM (
                    SELECT session_date FROM pit_snapshot_runs
                    WHERE kind = 'bars' AND status = 'ok' AND session_date IS NOT NULL
                    INTERSECT
                    SELECT session_date FROM pit_snapshot_runs
                    WHERE kind = 'listing' AND status = 'ok' AND session_date IS NOT NULL
                    INTERSECT
                    SELECT session_date FROM pit_snapshot_runs
                    WHERE kind = 'classification' AND status = 'ok' AND session_date IS NOT NULL
                    INTERSECT
                    SELECT session_date FROM pit_snapshot_runs
                    WHERE kind = 'dividend_announce' AND status = 'ok' AND session_date IS NOT NULL
                )
                """
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return date.fromisoformat(row[0])

    def run_status_summary(self, start: date, end: date) -> dict[SnapshotKind, KindRunSummary]:
        """Per-kind run history within ``[start, end]``, in one query (D-12).

        Returns every kind in :data:`_ALL_KINDS`, even ones with no rows in
        range (empty ``ok_sessions``, ``last_ok_session=None``).
        """
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT kind, session_date, status FROM pit_snapshot_runs
                WHERE session_date IS NOT NULL AND session_date BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        ok_by_kind: dict[SnapshotKind, set[date]] = {kind: set() for kind in _ALL_KINDS}
        for kind, session_date_str, status in rows:
            if status == "ok" and kind in ok_by_kind:
                ok_by_kind[kind].add(date.fromisoformat(session_date_str))
        return {
            kind: KindRunSummary(
                kind=kind,
                ok_sessions=frozenset(sessions),
                last_ok_session=max(sessions) if sessions else None,
            )
            for kind, sessions in ok_by_kind.items()
        }

    def last_ok_session(self, kind: SnapshotKind, *, before: date | None = None) -> date | None:
        """Most recent session with an ``ok`` run for ``kind``, optionally bounded by ``before``."""
        with closing(self._connect()) as conn:
            if before is None:
                row = conn.execute(
                    "SELECT MAX(session_date) FROM pit_snapshot_runs "
                    "WHERE kind = ? AND status = 'ok' AND session_date IS NOT NULL",
                    (kind,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT MAX(session_date) FROM pit_snapshot_runs "
                    "WHERE kind = ? AND status = 'ok' AND session_date IS NOT NULL "
                    "AND session_date <= ?",
                    (kind, before.isoformat()),
                ).fetchone()
        if row is None or row[0] is None:
            return None
        return date.fromisoformat(row[0])

    def pit_visible_listing_symbols(
        self, *, on_or_before: date, security_type: str | None = None
    ) -> frozenset[str]:
        """Symbols in the most recent ``ok`` listing run at or before ``on_or_before``.

        Used by ``app.services.pit_snapshot`` to compute ``expected_count``
        for the bars coverage check (D-2: "當日可見上市名單中應有交易的檔數"),
        without requiring the caller to reimplement the content-hash join.

        ``security_type``, when given, restricts the result to that one
        ``ListingSnapshotRow.security_type`` value (e.g. ``"common_stock"``,
        excluding TDRs) -- the bars coverage gate must divide by the common-
        stock population only (qa-reviewer wave-1 blocking finding), not
        every listed security.
        """
        session = self.last_ok_session("listing", before=on_or_before)
        if session is None:
            return frozenset()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT content_hash FROM pit_snapshot_runs "
                "WHERE kind = 'listing' AND status = 'ok' AND session_date = ? "
                "ORDER BY run_id DESC LIMIT 1",
                (session.isoformat(),),
            ).fetchone()
            if row is None or row[0] is None:
                return frozenset()
            content_hash = row[0]
            if security_type is None:
                symbols = conn.execute(
                    "SELECT symbol FROM pit_listing_rows WHERE content_hash = ?", (content_hash,)
                ).fetchall()
            else:
                symbols = conn.execute(
                    "SELECT symbol FROM pit_listing_rows "
                    "WHERE content_hash = ? AND security_type = ?",
                    (content_hash, security_type),
                ).fetchall()
        return frozenset(symbol for (symbol,) in symbols)

    def _latest_ok_run_before(
        self, conn: sqlite3.Connection, kind: SnapshotKind, before: date
    ) -> tuple[object, ...] | None:
        """The single latest ``ok`` run of ``kind`` with ``session_date < before``, if any.

        Used by :meth:`load_panel_frames`'s carry-forward lookback. Shape
        matches the tuples that method's main query returns, so it can be
        folded straight into that result list.
        """
        row = conn.execute(
            f"SELECT {_RUN_SELECT_COLUMNS} FROM pit_snapshot_runs "
            "WHERE kind = ? AND status = 'ok' AND session_date IS NOT NULL AND session_date < ? "
            "ORDER BY session_date DESC, run_id DESC LIMIT 1",
            (kind, before.isoformat()),
        ).fetchone()
        return tuple(row) if row is not None else None

    # -- statistics-row source verification (ADR-0012 C-50, D-14) ---------

    def source_fingerprint(self, run_max: int, session_end: date) -> SourceFingerprint | None:
        """Write time, in full: recompute the fingerprint of 𝒮(``run_max``, ``session_end``).

        One statement reads every run of 𝒮; the frame is built by
        :func:`_runs_frame` (the conversion ``load_panel_frames`` uses) and
        hashed by :func:`app.data.panel.source_fingerprint`, the evaluator's own
        function. ``None`` when 𝒮 is empty. Satisfies the write half of
        ``app.sectors.store.RunIdVerifier``.
        """
        with closing(self._connect()) as conn:
            return _source_fingerprint_on(conn, run_max, session_end)

    def source_tally(
        self, endpoints: Collection[int], run_max: int, session_end: date
    ) -> SourceTally:
        """Read time, light: one statement, no digest (see :data:`_SOURCE_TALLY_SQL`)."""
        with closing(self._connect()) as conn:
            return _source_tally_on(conn, endpoints, run_max, session_end)

    def load_panel_frames(self, start: date, end: date) -> PanelFrames:
        """Return the raw ``PanelFrames`` for ``[start, end]`` (by ``session_date``).

        Deliberately includes runs of **every** status, not just ``"ok"``:
        ``app.data.panel.MarketPanel``/``PointInTimePanel`` (dev-lead) is the
        consumer that derives ``ok_ids`` per kind and filters on it (see that
        module's ``_visible()``), and it also needs the non-``ok`` runs for
        diagnostics (``visible_runs()``, staleness checks). This method does
        not apply PIT visibility (``recorded_at <= cutoff(t)``) or bars
        source-priority resolution -- both live in ``app.data.panel`` now
        (``_visible`` / ``_resolve_bars``); this is the unfiltered raw
        material those are built from. Runs whose ``session_date`` could not
        be self-certified (``NULL``) are excluded -- there is no valid date
        to attach a row to (and ``PanelFrames`` columns require one).

        Every run (whether from the daily live capture or the pre-D0
        warm-up, see :meth:`record_symbol_backfill`) spans exactly one
        ``session_date``, so a single window filter on
        ``pit_snapshot_runs.session_date`` is precise for every kind
        including ``bars``.

        **Carry-forward lookback for listing/classification/dividend_announce**:
        these three kinds are "latest snapshot in force" (or, for
        dividend_announce, "union of every visible run") per D-2's
        "缺日沿用" -- so if the most recent ``ok`` run for one of them falls
        *before* ``start`` (e.g. `start` is today and that kind has been
        failing for several days, or simply was not captured every single
        day), the plain window filter above would silently drop the only
        snapshot a decision date early in ``[start, end]`` could carry
        forward from. To guard against that, this method additionally
        fetches the single latest ``ok`` run **before** ``start`` for each of
        these three kinds (one extra tiny query each) and folds it into the
        result, even though its own ``session_date`` lies outside
        ``[start, end]``. ``app.data.panel``'s visibility rules still apply
        normally to it (a decision date must be `>= that run's session_date`
        to see it).

        This is a bounded, single-step lookback, not a full historical
        replay: for ``dividend_announce``'s union semantics specifically, it
        only guarantees the most recent pre-``start`` run is included, not
        every run back to D0. Callers building a ``MarketPanel`` meant to
        answer point-in-time questions across the full accumulation period
        (D-12) should pass ``start <= D0`` so nothing is left to backfill.
        """
        with closing(self._connect()) as conn:
            runs = conn.execute(
                f"SELECT {_RUN_SELECT_COLUMNS} FROM pit_snapshot_runs "
                "WHERE session_date IS NOT NULL AND session_date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            ).fetchall()

            for lookback_kind in ("listing", "classification", "dividend_announce"):
                lookback_run = self._latest_ok_run_before(conn, lookback_kind, start)
                if lookback_run is not None:
                    runs = [*runs, lookback_run]

            runs_frame = _runs_frame(runs)

            bars_frame = self._load_bars(conn, runs)
            listing_frame = self._load_content_frame(
                conn,
                runs,
                kind="listing",
                table="pit_listing_rows",
                extra_columns=("security_type",),
                columns=LISTING_COLUMNS,
            )
            classification_frame = self._load_content_frame(
                conn,
                runs,
                kind="classification",
                table="pit_classification_rows",
                extra_columns=("sector_code", "sector_name"),
                columns=CLASSIFICATION_COLUMNS,
            )
            ex_dividend_frame = self._load_dividend_frame(conn, runs)

        return PanelFrames(
            bars=bars_frame,
            listing=listing_frame,
            classification=classification_frame,
            ex_dividend=ex_dividend_frame,
            runs=runs_frame,
        )

    def _load_bars(
        self, conn: sqlite3.Connection, runs: Sequence[tuple[object, ...]]
    ) -> pd.DataFrame:
        records: list[dict[str, object]] = []
        for (
            run_id,
            kind,
            session_date,
            recorded_at,
            source,
            _status,
            _row_count,
            _expected_count,
            _content_hash,
        ) in runs:
            if kind != "bars":
                continue
            rows = conn.execute(
                """
                SELECT symbol, open, high, low, close, shares, traded_value, change
                FROM market_daily_bars WHERE run_id = ?
                """,
                (run_id,),
            ).fetchall()
            recorded_ts = _to_utc_timestamp(str(recorded_at))
            for symbol, open_, high, low, close, shares, traded_value, change in rows:
                records.append(
                    {
                        "run_id": str(run_id),
                        "session_date": date.fromisoformat(str(session_date)),
                        "recorded_at": recorded_ts,
                        "source": source,
                        "symbol": symbol,
                        "open": float(Decimal(open_)),
                        "high": float(Decimal(high)),
                        "low": float(Decimal(low)),
                        "close": float(Decimal(close)),
                        "shares": int(shares),
                        "traded_value": float(Decimal(traded_value)),
                        "change": float(Decimal(change)) if change is not None else float("nan"),
                    }
                )
        return pd.DataFrame(records, columns=list(BARS_COLUMNS))

    def _load_content_frame(
        self,
        conn: sqlite3.Connection,
        runs: Sequence[tuple[object, ...]],
        *,
        kind: SnapshotKind,
        table: str,
        extra_columns: tuple[str, ...],
        columns: tuple[str, ...],
    ) -> pd.DataFrame:
        records: list[dict[str, object]] = []
        for (
            run_id,
            run_kind,
            session_date,
            recorded_at,
            _source,
            _status,
            _row_count,
            _expected_count,
            content_hash,
        ) in runs:
            if run_kind != kind or content_hash is None:
                continue
            column_list = ", ".join(("symbol", *extra_columns))
            rows = conn.execute(
                f"SELECT {column_list} FROM {table} WHERE content_hash = ?",  # noqa: S608 - fixed table name from a closed set above
                (content_hash,),
            ).fetchall()
            recorded_ts = _to_utc_timestamp(str(recorded_at))
            for row in rows:
                record: dict[str, object] = {
                    "run_id": str(run_id),
                    "session_date": date.fromisoformat(str(session_date)),
                    "recorded_at": recorded_ts,
                }
                record.update(dict(zip(("symbol", *extra_columns), row, strict=True)))
                records.append(record)
        return pd.DataFrame(records, columns=list(columns))

    def _load_dividend_frame(
        self, conn: sqlite3.Connection, runs: Sequence[tuple[object, ...]]
    ) -> pd.DataFrame:
        records: list[dict[str, object]] = []
        for (
            run_id,
            run_kind,
            session_date,
            recorded_at,
            _source,
            _status,
            _row_count,
            _expected_count,
            content_hash,
        ) in runs:
            if run_kind != "dividend_announce" or content_hash is None:
                continue
            rows = conn.execute(
                "SELECT symbol, ex_date FROM pit_dividend_announce_rows "
                "WHERE content_hash = ? AND ex_date IS NOT NULL",
                (content_hash,),
            ).fetchall()
            recorded_ts = _to_utc_timestamp(str(recorded_at))
            for symbol, ex_date in rows:
                records.append(
                    {
                        "run_id": str(run_id),
                        "session_date": date.fromisoformat(str(session_date)),
                        "recorded_at": recorded_ts,
                        "symbol": symbol,
                        "ex_date": date.fromisoformat(str(ex_date)),
                    }
                )
        return pd.DataFrame(records, columns=list(EX_DIVIDEND_COLUMNS))


class MarketPanelReader:
    """Read-only access to the market DB for the API process (ADR-0012 D-1, C-6).

    ``app.api.sectors`` reads the market DB and never writes it, so this class
    opens it with ``mode=ro`` and never creates it: a missing file simply
    reads as "no runs". Each method is one SQL statement on its own
    connection; ``busy_timeout`` comes from the connection's ``timeout``
    argument (C-9) rather than a ``PRAGMA`` statement, so the endpoint's
    statement count (C-6, T-2) is exactly the queries it runs.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_market_db_path()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection | None:
        if not self._db_path.is_file():
            return None
        uri = f"{self._db_path.resolve().as_uri()}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=_BUSY_TIMEOUT_MS / 1000)

    def ok_sessions(self, start: date, end: date) -> dict[SnapshotKind, frozenset[date]]:
        """Sessions in ``[start, end]`` with an ``ok`` run, per kind (one statement)."""
        found: dict[SnapshotKind, set[date]] = {kind: set() for kind in _ALL_KINDS}
        conn = self._connect()
        if conn is None:
            return {kind: frozenset() for kind in _ALL_KINDS}
        with closing(conn):
            rows = conn.execute(
                "SELECT DISTINCT kind, session_date FROM pit_snapshot_runs "
                "WHERE status = 'ok' AND session_date IS NOT NULL "
                "AND session_date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        for kind, session in rows:
            if kind in found:
                found[kind].add(date.fromisoformat(session))
        return {kind: frozenset(days) for kind, days in found.items()}

    def source_fingerprint(self, run_max: int, session_end: date) -> SourceFingerprint | None:
        """:meth:`MarketPanelStore.source_fingerprint` on the read-only file; ``None`` if absent."""
        conn = self._connect()
        if conn is None:
            return None
        with closing(conn):
            return _source_fingerprint_on(conn, run_max, session_end)

    def source_tally(
        self, endpoints: Collection[int], run_max: int, session_end: date
    ) -> SourceTally:
        """The read-time light check (one statement); a missing file knows no run.

        Satisfies ``app.sectors.store.SourceTallyReader`` -- the only market-DB
        question the card's statistics read asks (ADR-0012 C-50, C-51).
        """
        conn = self._connect()
        if conn is None:
            return SourceTally(ok_endpoints=frozenset(), run_count=0, run_min=None, run_max=None)
        with closing(conn):
            return _source_tally_on(conn, endpoints, run_max, session_end)
