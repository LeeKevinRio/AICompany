"""SQLite-backed store for 除權息 events.

Shares the same database file as every other store in this backend (the
``STOCK_DESK_DB_PATH`` environment variable, default ``./data/stock-desk.db``,
resolved by ``app.data.cache.resolve_db_path``) -- a new table in the existing
database, not a new database file or a new architecture layer, exactly as
``app.directory.store`` did.

Writes are an idempotent upsert keyed on ``(symbol, market, ex_date)``:
re-running ``python -m app.dividends.sync`` refreshes existing rows in place
rather than duplicating them. The upstream dataset (TWT48U_ALL, a forecast
table of *upcoming* ex-dates -- see ``app.dividends.providers``) has no
history endpoint at all, so repeated runs are the only way coverage
**accumulates** over time -- which is why the key is the event, not the sync.

Money columns are stored as TEXT and read back as ``Decimal``. Storing prices
as SQLite REAL would silently round the exchange's own published figures, and
the adjustment factor is a ratio of two of them.

## The sync record (ADR-0016 D-5.2)

Two more append-only tables live in the same file: ``dividend_sync_runs`` (one
row per sync attempt, ``ok`` or ``failed``) and ``dividend_sync_unparsed`` (the
symbols of refused rows that did name one). :meth:`DividendEventStore.record_sync`
writes the event upsert and the run in **one** ``BEGIN IMMEDIATE`` transaction,
so an ``ok`` run always has its events in ``dividend_events``. ``recorded_at``
comes from the store's own (injectable) clock and is never caller-supplied.
:meth:`DividendEventStore.dividend_announce_observations` reads the record back
in one statement for ``app.dividends.coverage.AnnounceRunCoverageRule``. This
module reads nothing from the market DB and must not reach it (ADR-0012 C-7).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Collection, Sequence
from contextlib import closing
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal

from app.data.cache import BUSY_TIMEOUT_MS, resolve_db_path
from app.data.interface import DividendAnnounceObservation
from app.data.sqlite_util import enable_wal
from app.dividends.models import DividendEvent
from app.positions.models import Market

#: Who started a sync: the scheduler, or a person running the CLI.
SyncTrigger = Literal["scheduled", "cli"]

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS dividend_events (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    previous_close TEXT,
    reference_price TEXT,
    cash_dividend TEXT NOT NULL,
    rights_value TEXT NOT NULL,
    stock_dividend_ratio TEXT,
    source TEXT NOT NULL,
    as_of TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market, ex_date)
)
"""

#: ``stock_dividend_ratio`` was added to the schema after this table had
#: already shipped (see ``_migrate_add_stock_dividend_ratio_column`` below):
#: a pre-existing local SQLite file synced before this change needs the
#: column added in place, since ``CREATE TABLE IF NOT EXISTS`` alone would
#: silently leave it missing.
_STOCK_DIVIDEND_RATIO_COLUMN = "stock_dividend_ratio"

#: The read path is always "one symbol, one date range", which the primary key's
#: leading columns already serve; this index only helps the coverage queries.
_CREATE_DATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_dividend_events_ex_date
ON dividend_events (ex_date)
"""

#: ADR-0016 D-5.2, verbatim. Neither table name starts with ``pit_`` (K-19): the
#: ``pit_`` prefix is the market DB's point-in-time namespace.
_CREATE_SYNC_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS dividend_sync_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    trigger TEXT NOT NULL CHECK (trigger IN ('scheduled', 'cli')),
    source TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
    event_count INTEGER NOT NULL,
    unparsed_count INTEGER NOT NULL,
    unattributed_count INTEGER NOT NULL,
    reason TEXT
)
"""

_CREATE_SYNC_RUNS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_dividend_sync_runs_status_recorded
ON dividend_sync_runs (status, recorded_at)
"""

_CREATE_SYNC_UNPARSED_SQL = """
CREATE TABLE IF NOT EXISTS dividend_sync_unparsed (
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    PRIMARY KEY (run_id, symbol)
) WITHOUT ROWID
"""

_SYNC_RECORD_TABLES: Final[tuple[str, ...]] = ("dividend_sync_runs", "dividend_sync_unparsed")


def _append_only_trigger_sql(table: str) -> tuple[str, str]:
    """Same shape as ``app.data.market_panel``'s triggers; copied, not imported (C-7)."""
    update_sql = f"""
    CREATE TRIGGER IF NOT EXISTS {table}_no_update
    BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END
    """
    delete_sql = f"""
    CREATE TRIGGER IF NOT EXISTS {table}_no_delete
    BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END
    """
    return update_sql, delete_sql


#: One statement for a whole book (K-7, K-20): every ok run recorded on/after the
#: bound, left-joined to the wanted symbols' unparsed rows.
_ANNOUNCE_OBSERVATIONS_SQL: Final = """
    SELECT r.run_id, r.recorded_at, r.unattributed_count, u.symbol
    FROM dividend_sync_runs AS r
    LEFT JOIN dividend_sync_unparsed AS u
        ON u.run_id = r.run_id
        AND u.symbol IN (SELECT value FROM json_each(:symbols))
    WHERE r.status = 'ok' AND r.recorded_at >= :not_before
    ORDER BY r.run_id, u.symbol
"""

#: Symbols per ``IN (...)`` clause in :meth:`DividendEventStore.ex_dates_between`,
#: well below SQLite's historical 999 bound-parameter limit.
_MAX_SYMBOLS_PER_QUERY = 500

_SELECT_COLUMNS = (
    "symbol, market, ex_date, previous_close, reference_price, "
    "cash_dividend, rights_value, stock_dividend_ratio, source, as_of"
)


class DividendEventStore:
    """SQLite (WAL mode) store for 除權息 events, keyed by symbol + ex-date."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # The clock stamps ``dividend_sync_runs.recorded_at`` and nothing else; it
        # is injectable for tests, never a per-call argument (ADR-0016 K-18).
        self._clock: Callable[[], datetime] = clock if clock is not None else _utc_now
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=BUSY_TIMEOUT_MS / 1000)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            enable_wal(conn)
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_DATE_INDEX_SQL)
            self._migrate_add_stock_dividend_ratio_column(conn)
            conn.execute(_CREATE_SYNC_RUNS_SQL)
            conn.execute(_CREATE_SYNC_RUNS_INDEX_SQL)
            conn.execute(_CREATE_SYNC_UNPARSED_SQL)
            for table in _SYNC_RECORD_TABLES:
                for trigger_sql in _append_only_trigger_sql(table):
                    conn.execute(trigger_sql)

    def _migrate_add_stock_dividend_ratio_column(self, conn: sqlite3.Connection) -> None:
        """Add ``stock_dividend_ratio`` in place for a table created before it existed.

        ``PRAGMA table_info`` first, since ``ALTER TABLE ... ADD COLUMN``
        errors on a column that is already there (which it always is for a
        table this ``__init__`` just created via ``_CREATE_TABLE_SQL``).
        """
        columns = {row[1] for row in conn.execute("PRAGMA table_info(dividend_events)")}
        if _STOCK_DIVIDEND_RATIO_COLUMN not in columns:
            conn.execute(
                f"ALTER TABLE dividend_events ADD COLUMN {_STOCK_DIVIDEND_RATIO_COLUMN} TEXT"
            )

    def upsert(
        self,
        events: Sequence[DividendEvent],
        *,
        synced_at: datetime | None = None,
    ) -> int:
        """Upsert ``events``, keyed on ``(symbol, market, ex_date)``. Returns rows written."""
        if not events:
            return 0
        moment = synced_at if synced_at is not None else datetime.now(UTC)
        with closing(self._connect()) as conn, conn:
            return _upsert_on(conn, events, moment)

    def record_sync(
        self,
        *,
        trigger: SyncTrigger,
        source: str,
        adapter_ok: bool,
        reason: str | None,
        events: Sequence[DividendEvent],
        unparsed_symbols: Sequence[str] = (),
        unattributed_count: int = 0,
        synced_at: datetime | None = None,
    ) -> int:
        """Upsert ``events`` and append one sync run, in one transaction; returns ``run_id``.

        ``status`` is ``ok`` only when the adapter was ok **and** it handed over at
        least one event **and** the upsert below succeeds; anything else is a
        ``failed`` run carrying ``reason`` (kept in the database, never in an API
        response). A failure while writing rolls the whole transaction back and is
        re-raised: neither the events nor a run row land (ADR-0016 K-18).

        ``unparsed_symbols`` has one entry per refused row that named a symbol
        (``unparsed_count`` is its length); the distinct normalized codes are
        stored. ``recorded_at`` is the store's own clock, UTC, fixed-width
        ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00`` so string order is time order.
        """
        unparsed = [symbol.strip().upper() for symbol in unparsed_symbols if symbol.strip()]
        usable = adapter_ok and len(events) > 0
        status = "ok" if usable else "failed"
        if usable:
            recorded_reason = None
        elif not adapter_ok:
            recorded_reason = reason or "adapter reported failure without a reason"
        else:
            recorded_reason = "adapter returned ok with no events"
        moment = synced_at if synced_at is not None else datetime.now(UTC)
        recorded_at = _format_recorded_at(self._clock())
        # ``isolation_level=None``: this method owns BEGIN/COMMIT itself so the
        # write lock is taken up front (IMMEDIATE) and held across all three writes.
        conn = sqlite3.connect(self._db_path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        with closing(conn):
            conn.execute("BEGIN IMMEDIATE")
            try:
                if usable:
                    _upsert_on(conn, events, moment)
                cursor = conn.execute(
                    "INSERT INTO dividend_sync_runs (recorded_at, trigger, source, status, "
                    "event_count, unparsed_count, unattributed_count, reason) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        recorded_at,
                        trigger,
                        source,
                        status,
                        len(events) if usable else 0,
                        len(unparsed),
                        unattributed_count,
                        recorded_reason,
                    ),
                )
                run_id = cursor.lastrowid
                if run_id is None:  # pragma: no cover - INSERT always sets it
                    raise sqlite3.DatabaseError("sync run insert returned no row id")
                conn.executemany(
                    "INSERT INTO dividend_sync_unparsed (run_id, symbol) VALUES (?, ?)",
                    [(run_id, symbol) for symbol in sorted(set(unparsed))],
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return int(run_id)

    def dividend_announce_observations(
        self, symbols: Collection[str], recorded_not_before: date_type
    ) -> list[DividendAnnounceObservation]:
        """Ok sync runs recorded on/after a UTC date, as the coverage rule reads them.

        Satisfies ``app.dividends.coverage.AnnounceRunSource``. ``symbols`` are
        matched ``strip().upper()``. One SQL statement for the whole book (K-7,
        K-20); a table that does not exist reads as "no run". Per run:

        * a symbol of the book among the run's unparsed codes: one observation
          ``symbol=<it>, ex_date=None`` (an event of unknown date);
        * ``unattributed_count > 0``: one ``ex_date=None`` observation for every
          queried symbol (the run may hide an event of any of them);
        * otherwise one ``symbol=None`` observation -- the run exists and says
          nothing against the book.

        Dated events are not repeated here: they live in ``dividend_events``,
        written by the same transaction, and F6 reads them there (ADR-0016 D-5.3).
        A stored timestamp that does not parse raises ``ValueError``; the rule
        turns that into ``unknown``.
        """
        wanted = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
        if not wanted:
            return []
        with closing(self._connect()) as conn:
            try:
                rows = conn.execute(
                    _ANNOUNCE_OBSERVATIONS_SQL,
                    {
                        "symbols": json.dumps(wanted),
                        "not_before": recorded_not_before.isoformat(),
                    },
                ).fetchall()
            except sqlite3.OperationalError as error:
                if "no such table" in str(error):
                    return []
                raise
        runs: dict[int, tuple[datetime, int, set[str]]] = {}
        for run_id, recorded_at, unattributed, symbol in rows:
            _, _, hits = runs.setdefault(
                int(run_id),
                (datetime.fromisoformat(str(recorded_at)), int(unattributed), set()),
            )
            if symbol is not None:
                hits.add(str(symbol).upper())
        observations: list[DividendAnnounceObservation] = []
        for run_id, (recorded, unattributed, hits) in sorted(runs.items()):
            named = set(wanted) if unattributed > 0 else hits
            if not named:
                observations.append(
                    DividendAnnounceObservation(
                        run_id=run_id, recorded_at=recorded, symbol=None, ex_date=None
                    )
                )
                continue
            observations.extend(
                DividendAnnounceObservation(
                    run_id=run_id, recorded_at=recorded, symbol=symbol, ex_date=None
                )
                for symbol in sorted(named)
            )
        return observations

    def count(self) -> int:
        """Total number of stored events. ``0`` means "never synced"."""
        with closing(self._connect()) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM dividend_events")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def is_synced(self) -> bool:
        """Whether any event has ever been stored -- the degrade signal for the API."""
        return self.count() > 0

    def events_for(
        self,
        symbol: str,
        market: Market,
        *,
        start: date_type | None = None,
        end: date_type | None = None,
    ) -> list[DividendEvent]:
        """Events for one symbol, ascending by ex-date, optionally bounded inclusively."""
        clauses = ["symbol = ?", "market = ?"]
        params: list[str] = [symbol, market]
        if start is not None:
            clauses.append("ex_date >= ?")
            params.append(start.isoformat())
        if end is not None:
            clauses.append("ex_date <= ?")
            params.append(end.isoformat())
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                # Interpolated parts are a fixed column list and a fixed set of
                # clause templates; every value stays a bound parameter.
                f"SELECT {_SELECT_COLUMNS} FROM dividend_events "
                f"WHERE {' AND '.join(clauses)} ORDER BY ex_date ASC",
                params,
            )
            rows = cursor.fetchall()
        return [_row_to_event(row) for row in rows]

    def ex_dates_between(
        self,
        keys: Collection[tuple[str, Market]],
        start: date_type,
        end: date_type,
    ) -> dict[tuple[str, Market], frozenset[date_type]]:
        """Ex-dates in ``[start, end]`` for many ``(symbol, market)`` keys at once.

        One read for a whole book (ADR-0016 K-7) instead of one
        :meth:`events_for` per holding. Keys with no event in the window are
        absent from the result. Symbols are matched exactly as stored; the
        caller normalizes them the way the sync writes them.
        """
        # Typed keys by their raw column values, so a row maps back to the
        # caller's own key and a symbol stored under another market is dropped.
        wanted: dict[tuple[str, str], tuple[str, Market]] = {
            (symbol, str(market)): (symbol, market) for symbol, market in keys
        }
        found: dict[tuple[str, Market], set[date_type]] = {}
        symbols = sorted({symbol for symbol, _ in wanted})
        if not symbols:
            return {}
        with closing(self._connect()) as conn:
            # Chunked only to stay under SQLite's bound-parameter limit; a
            # book small enough to fit (every real one) is a single query.
            for offset in range(0, len(symbols), _MAX_SYMBOLS_PER_QUERY):
                chunk = symbols[offset : offset + _MAX_SYMBOLS_PER_QUERY]
                placeholders = ", ".join("?" for _ in chunk)
                cursor = conn.execute(
                    "SELECT symbol, market, ex_date FROM dividend_events "
                    f"WHERE ex_date BETWEEN ? AND ? AND symbol IN ({placeholders})",
                    (start.isoformat(), end.isoformat(), *chunk),
                )
                for symbol, market, ex_date in cursor.fetchall():
                    key = wanted.get((str(symbol), str(market)))
                    if key is None:
                        continue
                    found.setdefault(key, set()).add(date_type.fromisoformat(str(ex_date)))
        return {key: frozenset(days) for key, days in found.items()}

    def last_synced_at(self) -> datetime | None:
        """The most recent sync timestamp, or ``None`` when never synced."""
        with closing(self._connect()) as conn:
            cursor = conn.execute("SELECT MAX(synced_at) FROM dividend_events")
            row = cursor.fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(str(row[0]))


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _format_recorded_at(moment: datetime) -> str:
    """UTC, fixed width, so that comparing two stored strings compares the instants."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("the store clock must return a timezone-aware datetime")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _upsert_on(conn: sqlite3.Connection, events: Sequence[DividendEvent], moment: datetime) -> int:
    rows = [
        (
            event.symbol,
            event.market,
            event.ex_date.isoformat(),
            _to_text(event.previous_close),
            _to_text(event.reference_price),
            str(event.cash_dividend),
            str(event.rights_value),
            _to_text(event.stock_dividend_ratio),
            event.source,
            event.as_of.isoformat(),
            moment.isoformat(),
        )
        for event in events
    ]
    conn.executemany(
        """
        INSERT INTO dividend_events (
            symbol, market, ex_date, previous_close, reference_price,
            cash_dividend, rights_value, stock_dividend_ratio,
            source, as_of, synced_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, market, ex_date) DO UPDATE SET
            previous_close=excluded.previous_close,
            reference_price=excluded.reference_price,
            cash_dividend=excluded.cash_dividend,
            rights_value=excluded.rights_value,
            stock_dividend_ratio=excluded.stock_dividend_ratio,
            source=excluded.source,
            as_of=excluded.as_of,
            synced_at=excluded.synced_at
        """,
        rows,
    )
    return len(rows)


def _to_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _to_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _row_to_event(row: tuple[object, ...]) -> DividendEvent:
    return DividendEvent(
        symbol=str(row[0]),
        market=str(row[1]),  # type: ignore[arg-type]  # DB only holds validated Market values
        ex_date=date_type.fromisoformat(str(row[2])),
        previous_close=_to_decimal(row[3]),
        reference_price=_to_decimal(row[4]),
        cash_dividend=Decimal(str(row[5])),
        rights_value=Decimal(str(row[6])),
        stock_dividend_ratio=_to_decimal(row[7]),
        source=str(row[8]),
        as_of=datetime.fromisoformat(str(row[9])),
    )
