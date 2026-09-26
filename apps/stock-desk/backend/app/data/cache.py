"""SQLite-backed local cache for daily price bars.

This is the third layer of the degradation ladder (primary provider ->
backup provider -> this cache -> unavailable). It is intentionally a plain
``sqlite3`` wrapper (stdlib only) running in WAL mode so reads and writes
can interleave safely for a single-machine, single-user deployment per
ADR-0002.

Database location is controlled by the ``STOCK_DESK_DB_PATH`` environment
variable (default ``./data/stock-desk.db``).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import monotonic, sleep
from typing import Final

from app.data.interface import Market, PriceBar

DEFAULT_DB_PATH: Final[str] = "./data/stock-desk.db"

#: How many trade dates go into one ``IN (...)`` probe. Comfortably below
#: SQLite's host-parameter limit (999 on the oldest builds still in the wild),
#: so a multi-year batch is chunked instead of failing at the driver.
_PROBE_CHUNK_SIZE: Final[int] = 400
#: Milliseconds a connection waits for a concurrent writer before failing.
#: Public because every store sharing this database file uses the same value.
BUSY_TIMEOUT_MS: Final[int] = 5000
#: Primary result code of ``SQLITE_BUSY`` (extended codes keep it in the low byte).
_SQLITE_BUSY: Final[int] = 5
#: First pause between :func:`enable_wal` attempts; doubles up to the maximum.
_WAL_FIRST_RETRY_DELAY_S: Final[float] = 0.005
_WAL_MAX_RETRY_DELAY_S: Final[float] = 0.1
#: Journal modes :func:`enable_wal` accepts back: ``memory`` is what an
#: in-memory database reports, since it has no file to put into WAL mode.
_WAL_ACCEPTED_MODES: Final[frozenset[str]] = frozenset({"wal", "memory"})

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS price_bars_cache (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open TEXT NOT NULL,
    high TEXT NOT NULL,
    low TEXT NOT NULL,
    close TEXT NOT NULL,
    volume INTEGER NOT NULL,
    currency TEXT NOT NULL,
    source TEXT NOT NULL,
    as_of TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market, trade_date)
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_price_bars_cache_lookup
ON price_bars_cache (symbol, market, trade_date)
"""

#: The lookup above is keyed on ``symbol`` first, so the market-wide trade-date
#: scan :meth:`PriceBarCache.market_trading_days` runs cannot use it. This one
#: exists for that query alone (C4): it is issued on every advice request, and a
#: full table scan there would grow with every symbol the user ever opened.
_CREATE_MARKET_DATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_price_bars_cache_market_date
ON price_bars_cache (market, trade_date)
"""

#: One row per series: the one contiguous date range a live source has
#: answered *in full*, and when it last did (ADR-0009). Layer 0 reads this to
#: know (a) whether a request reaches outside anything ever fetched and (b)
#: when a live source last confirmed there was nothing newer -- ``fetched_at``
#: on the bar rows cannot say either (a holiday fetch writes no new rows).
_CREATE_FETCH_LOG_SQL = """
CREATE TABLE IF NOT EXISTS price_bars_fetch_log (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    covered_start TEXT NOT NULL,
    covered_end TEXT NOT NULL,
    last_fetched_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market)
)
"""

#: When a live source was last *asked* for a series, successful or not
#: (ADR-0009 R-8): while the sources are down, this is what keeps layer 0 from
#: re-running the whole ladder on every click.
_CREATE_ATTEMPT_LOG_SQL = """
CREATE TABLE IF NOT EXISTS price_bars_attempt_log (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    last_attempt_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market)
)
"""


def resolve_db_path() -> Path:
    """Resolve the cache database path from ``STOCK_DESK_DB_PATH`` (or the default)."""
    raw = os.environ.get("STOCK_DESK_DB_PATH", DEFAULT_DB_PATH)
    return Path(raw)


def enable_wal(conn: sqlite3.Connection) -> None:
    """Issue ``PRAGMA journal_mode=WAL`` on ``conn``, riding out a concurrent switch.

    Stores put the shared database file into WAL mode when constructed. On a
    file not in WAL mode yet -- a database written before WAL was adopted, or
    a brand-new empty one -- the switch is a write: SQLite opens a read
    transaction (shared lock), then upgrades it to an exclusive lock to
    rewrite the file header. When two connections do this at once (the
    backend and a CLI starting against the same file), both hold the shared
    lock, one takes the reserved lock and waits for the other to let go, and
    the other's upgrade is refused with ``SQLITE_BUSY`` *immediately*: SQLite
    skips the busy handler for a lock upgrade out of an open read transaction
    because waiting there could deadlock (``sqlite3_busy_handler`` docs). So
    ``busy_timeout`` does not help and the loser failed with "database is
    locked" within a millisecond.

    The refusal comes before the loser has changed anything, and its read
    transaction ends with the failed statement, so the switch is retried; by
    then the winner has usually converted the file and the retry is a no-op.
    Retries run for as long as the connection's own ``busy_timeout`` allows
    -- the wait any other statement on it would get -- and a lock still held
    past that deadline, like every other error, is raised unchanged.

    SQLite does not fail a switch it cannot make; it answers with the mode the
    database stayed in. Anything but ``wal`` (or ``memory`` for an in-memory
    database) is therefore raised here, rather than letting the stores run on
    a rollback journal whose readers and writers block each other.

    Must be called outside any open transaction (SQLite refuses to change into
    WAL mode inside one).
    """
    (timeout_ms,) = conn.execute("PRAGMA busy_timeout").fetchone()
    deadline = monotonic() + int(timeout_ms) / 1000
    delay = _WAL_FIRST_RETRY_DELAY_S
    while True:
        try:
            (mode,) = conn.execute("PRAGMA journal_mode=WAL").fetchone()
            break
        except sqlite3.OperationalError as error:
            if (error.sqlite_errorcode & 0xFF) != _SQLITE_BUSY or monotonic() >= deadline:
                raise
        sleep(delay)
        delay = min(delay * 2, _WAL_MAX_RETRY_DELAY_S)
    if str(mode).lower() not in _WAL_ACCEPTED_MODES:
        raise sqlite3.OperationalError(
            f"could not switch the database to WAL journal mode; it stayed in {mode!r}"
        )


@dataclass(frozen=True)
class CacheReadResult:
    """What the cache has on hand for a requested symbol/date range.

    ``fetched_at`` is the oldest ``fetched_at`` among the returned rows
    (the conservative choice: staleness is reported as "at least this old").
    Whether the rows are *current* is not a question of their age (ADR-0009):
    the service answers it from the fetch log and the market's session rule.
    """

    bars: list[PriceBar]
    fetched_at: datetime
    source: str
    staleness_minutes: int


@dataclass(frozen=True)
class FetchCoverage:
    """What live sources were ever asked for one series, and when last (ADR-0009)."""

    covered_start: date
    covered_end: date
    last_fetched_at: datetime


@dataclass(frozen=True)
class ForeignBarConflict:
    """A cached row a writer would overwrite, and the source that owns it."""

    symbol: str
    market: str
    trade_date: date
    source: str


class PriceBarCache:
    """SQLite (WAL mode) cache of daily price bars, keyed by symbol/market/date."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        # WAL is a persistent, on-disk property of the database file, so it is
        # set once in ``_init_schema`` rather than re-issued on every connect.
        # Callers must wrap the returned connection in ``contextlib.closing``
        # (or an equivalent try/finally) so it is explicitly closed; the
        # sqlite3 connection context manager only commits/rolls back the
        # transaction, it does NOT close the connection.
        conn = sqlite3.connect(self._db_path)
        # API and scheduler are documented dual writers (ADR-0005 P-1) and the
        # request path now writes two small log rows per live fetch; wait for
        # a writer instead of surfacing "database is locked" as a 500 (same
        # convention as ``QuotaLedger``).
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            enable_wal(conn)
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
            conn.execute(_CREATE_MARKET_DATE_INDEX_SQL)
            conn.execute(_CREATE_FETCH_LOG_SQL)
            conn.execute(_CREATE_ATTEMPT_LOG_SQL)

    def put(
        self,
        bars: list[PriceBar],
        *,
        source: str,
        fetched_at: datetime | None = None,
    ) -> None:
        """Upsert a batch of bars into the cache, tagged with a fetch timestamp.

        The upsert is keyed on ``(symbol, market, trade_date)`` and deliberately
        ignores the existing row's ``source``: a live provider refreshing a bar
        is the normal case, and the freshest fetch wins. A writer for which
        overwriting another source's row would be *data loss* must therefore
        gate itself on :meth:`find_foreign_bars` before calling this.
        """
        if not bars:
            return
        moment = fetched_at if fetched_at is not None else datetime.now(UTC)
        rows = [
            (
                bar.symbol,
                bar.market,
                bar.date.isoformat(),
                str(bar.open),
                str(bar.high),
                str(bar.low),
                str(bar.close),
                bar.volume,
                bar.currency,
                source,
                bar.as_of.isoformat(),
                moment.isoformat(),
            )
            for bar in bars
        ]
        with closing(self._connect()) as conn, conn:
            conn.executemany(
                """
                INSERT INTO price_bars_cache
                    (symbol, market, trade_date, open, high, low, close,
                     volume, currency, source, as_of, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, market, trade_date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    currency=excluded.currency,
                    source=excluded.source,
                    as_of=excluded.as_of,
                    fetched_at=excluded.fetched_at
                """,
                rows,
            )

    def record_fetch(
        self,
        symbol: str,
        market: Market,
        *,
        start: date,
        end: date,
        fetched_at: datetime | None = None,
    ) -> None:
        """Note that a live source answered ``[start, end]`` of this series in full.

        The coverage is kept as **one contiguous interval**: a new range that
        overlaps or touches the recorded one widens it; a disjoint range
        replaces it (qa 2026-09-13: merging two far-apart ranges with MIN/MAX
        would claim the gap between them was fetched). The *requested* range
        is what gets recorded, not the returned bars' span, so a series listed
        after the requested start is not re-fetched on every request; the
        caller must only call this for a complete answer
        (``ProviderResult.complete``), never for a partial one.

        The read-then-write is serialised with ``BEGIN IMMEDIATE`` (qa
        2026-09-13 second round): the API and the scheduler are dual writers,
        and although a lost update here could only narrow the recorded range
        (one extra live fetch, never a claim about an unfetched range), taking
        the write lock before reading costs nothing and removes the race.
        """
        moment = fetched_at if fetched_at is not None else datetime.now(UTC)
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT covered_start, covered_end FROM price_bars_fetch_log "
                "WHERE symbol = ? AND market = ?",
                (symbol, market),
            ).fetchone()
            covered_start, covered_end = start, end
            if row is not None:
                old_start: date | None
                old_end: date | None
                try:
                    old_start, old_end = date.fromisoformat(row[0]), date.fromisoformat(row[1])
                except ValueError:
                    old_start = old_end = None
                if (
                    old_start is not None
                    and old_end is not None
                    and start <= old_end + timedelta(days=1)
                    and end >= old_start - timedelta(days=1)
                ):
                    covered_start, covered_end = min(start, old_start), max(end, old_end)
            conn.execute(
                """
                INSERT INTO price_bars_fetch_log
                    (symbol, market, covered_start, covered_end, last_fetched_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol, market) DO UPDATE SET
                    covered_start=excluded.covered_start,
                    covered_end=excluded.covered_end,
                    last_fetched_at=excluded.last_fetched_at
                """,
                (
                    symbol,
                    market,
                    covered_start.isoformat(),
                    covered_end.isoformat(),
                    moment.isoformat(),
                ),
            )

    def fetch_coverage(self, symbol: str, market: Market) -> FetchCoverage | None:
        """The recorded complete live-fetch coverage for one series, or ``None``."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT covered_start, covered_end, last_fetched_at
                FROM price_bars_fetch_log WHERE symbol = ? AND market = ?
                """,
                (symbol, market),
            ).fetchone()
        if row is None:
            return None
        try:
            return FetchCoverage(
                covered_start=date.fromisoformat(row[0]),
                covered_end=date.fromisoformat(row[1]),
                last_fetched_at=datetime.fromisoformat(row[2]),
            )
        except ValueError:
            return None

    def record_attempt(self, symbol: str, market: Market, *, at: datetime | None = None) -> None:
        """Note that the ladder asked live sources for this series, whatever they answered."""
        moment = at if at is not None else datetime.now(UTC)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO price_bars_attempt_log (symbol, market, last_attempt_at)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol, market) DO UPDATE SET
                    last_attempt_at=excluded.last_attempt_at
                """,
                (symbol, market, moment.isoformat()),
            )

    def last_trade_date(self, symbol: str, market: Market, start: date, end: date) -> date | None:
        """The newest cached ``trade_date`` of one series inside ``[start, end]``, or ``None``.

        A single ``MAX`` on the primary key instead of :meth:`get` (which builds
        every row): the incremental-fetch decision (ADR-0009 D-7) needs only
        this one date, and must not grow with the length of the range.
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT MAX(trade_date) FROM price_bars_cache
                WHERE symbol = ? AND market = ? AND trade_date BETWEEN ? AND ?
                """,
                (symbol, market, start.isoformat(), end.isoformat()),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        try:
            return date.fromisoformat(row[0])
        except ValueError:
            return None

    def market_has_session(
        self, market: Market, day: date, *, exclude_source: str = "demo_synthetic"
    ) -> bool:
        """Positive evidence that ``market`` published ``day``: some live series has its bar.

        Used only in the monotone direction (ADR-0009 修訂 2026-09-15): it can
        make layer 0 fetch *more* (a close that came out before the assumed
        ``publish_cutoff``), never suppress a fetch. Demo rows are excluded by
        default -- the offline seeder writes a weekday grid with no holidays,
        which would "prove" every weekday a session.
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM price_bars_cache
                WHERE market = ? AND trade_date = ? AND source != ?
                LIMIT 1
                """,
                (market, day.isoformat(), exclude_source),
            ).fetchone()
        return row is not None

    def clear_attempt(self, symbol: str, market: Market) -> bool:
        """Forget the last live attempt for one series so the next ask skips the cooldown.

        An operator action (``python -m app.data.diagnose --clear-cooldown``),
        not a product path: ADR-0009 D-8 keeps the cooldown durable across
        restarts on purpose, so lifting it has to be explicit. Returns whether
        a row existed.
        """
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "DELETE FROM price_bars_attempt_log WHERE symbol = ? AND market = ?",
                (symbol, market),
            )
        return cursor.rowcount > 0

    def last_attempt_at(self, symbol: str, market: Market) -> datetime | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT last_attempt_at FROM price_bars_attempt_log "
                "WHERE symbol = ? AND market = ?",
                (symbol, market),
            ).fetchone()
        if row is None:
            return None
        try:
            return datetime.fromisoformat(row[0])
        except ValueError:
            return None

    def find_foreign_bars(
        self, bars: Sequence[PriceBar], *, source: str
    ) -> list[ForeignBarConflict]:
        """Rows already cached at ``bars``' keys that a **different** source owns.

        :meth:`put` upserts on ``(symbol, market, trade_date)`` and does not
        look at the existing row's ``source``, so a writer that must not clobber
        another provider's data (the offline demo seeder) has to ask first --
        and it has to ask *before* writing, because an overwritten row is gone:
        :meth:`delete_by_source` can only retract rows still tagged with the
        writer's own source.

        Returns one entry per conflicting row, ordered by symbol/market/date.
        An empty list means :meth:`put` would only insert new rows or refresh
        rows this ``source`` already owns.
        """
        keys_by_series: dict[tuple[str, str], set[str]] = {}
        for bar in bars:
            keys_by_series.setdefault((bar.symbol, bar.market), set()).add(bar.date.isoformat())

        conflicts: list[ForeignBarConflict] = []
        with closing(self._connect()) as conn:
            for (symbol, market), trade_dates in sorted(keys_by_series.items()):
                ordered = sorted(trade_dates)
                for start in range(0, len(ordered), _PROBE_CHUNK_SIZE):
                    chunk = ordered[start : start + _PROBE_CHUNK_SIZE]
                    # Only the placeholder count is interpolated; every value
                    # below stays a bound parameter.
                    placeholders = ", ".join("?" * len(chunk))
                    cursor = conn.execute(
                        f"""
                        SELECT trade_date, source
                        FROM price_bars_cache
                        WHERE symbol = ? AND market = ? AND source != ?
                              AND trade_date IN ({placeholders})
                        ORDER BY trade_date ASC
                        """,
                        (symbol, market, source, *chunk),
                    )
                    conflicts.extend(
                        ForeignBarConflict(
                            symbol=symbol,
                            market=market,
                            trade_date=date.fromisoformat(trade_date),
                            source=row_source,
                        )
                        for trade_date, row_source in cursor.fetchall()
                    )
        return conflicts

    def market_trading_days(self, market: Market, start: date, end: date) -> frozenset[date]:
        """Dates in ``[start, end]`` **any** ``market`` series produced a bar on.

        The product's trading calendar, observed rather than tabulated (C4): a
        date is a session because some series traded on it, so 農曆年、颱風假 and
        every other closure -- including the ad-hoc ones no fixed holiday table
        can predict -- are simply absent, with no yearly upkeep.

        Scoped to one market because the two markets keep different calendars,
        and read across every symbol because that is what makes it a *market*
        calendar: a single series can be missing a session because its own
        provider failed, while the market as a whole clearly traded.

        An empty result means "this cache has observed nothing here", never
        "the market never traded" -- see :func:`app.services.market.load_bars`
        for the fail-safe the caller applies to that case.

        One stated limit: the offline demo seeder writes a *weekday* grid with
        no holidays modelled (``app/demo/series.py::trading_days``), so a
        database holding demo bars reports demo weekdays as sessions. It is
        self-limiting -- every demo series shares that one grid, so a
        demo-only database still measures a gap of 0 -- but a database mixing
        seeded and live bars can over-count. Retracting the demo rows
        (``delete_by_source``) is what the seeder documents for leaving demo
        mode, and it clears this too.
        """
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                SELECT DISTINCT trade_date
                FROM price_bars_cache
                WHERE market = ? AND trade_date BETWEEN ? AND ?
                """,
                (market, start.isoformat(), end.isoformat()),
            )
            rows = cursor.fetchall()
        days: set[date] = set()
        for (trade_date,) in rows:
            try:
                days.add(date.fromisoformat(trade_date))
            except ValueError:
                # Corrupt row: skip it, exactly as ``get`` does, rather than
                # letting one bad key take down a freshness check.
                continue
        return frozenset(days)

    def delete_by_source(self, source: str) -> int:
        """Delete every cached bar tagged with ``source``; return the row count.

        Scoped by ``source`` on purpose: it lets a writer retract exactly what
        it put in (the offline demo seeder retracting ``demo_synthetic``)
        without touching rows any other provider wrote into the same cache.
        """
        with closing(self._connect()) as conn, conn:
            # ADR-0009 R-5: a series that loses rows must also lose its
            # coverage claim, or layer 0 would serve the hollowed-out remainder
            # as complete. Forgetting costs one live fetch per series.
            for table in ("price_bars_fetch_log", "price_bars_attempt_log"):
                # Plain EXISTS with fully qualified names: no row-value IN and no
                # DELETE alias, so nothing here needs a newer SQLite than the
                # 999-parameter cap ``find_foreign_bars`` already assumes.
                conn.execute(
                    f"""
                    DELETE FROM {table}
                    WHERE EXISTS (
                        SELECT 1 FROM price_bars_cache
                        WHERE price_bars_cache.symbol = {table}.symbol
                              AND price_bars_cache.market = {table}.market
                              AND price_bars_cache.source = ?
                    )
                    """,
                    (source,),
                )
            cursor = conn.execute("DELETE FROM price_bars_cache WHERE source = ?", (source,))
            return cursor.rowcount

    def get(
        self,
        symbol: str,
        market: Market,
        start: date,
        end: date,
        *,
        now: datetime | None = None,
    ) -> CacheReadResult | None:
        """Return cached bars for ``symbol``/``market`` within ``[start, end]``.

        Returns ``None`` if no rows exist for the range at all. When rows do
        exist, they are returned whatever their age (the cache is the
        last-resort layer of the degradation ladder); how current they are is
        the service's judgement (ADR-0009), not a property of the rows.
        """
        moment = now if now is not None else datetime.now(UTC)
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                SELECT symbol, market, trade_date, open, high, low, close,
                       volume, currency, source, as_of, fetched_at
                FROM price_bars_cache
                WHERE symbol = ? AND market = ? AND trade_date BETWEEN ? AND ?
                ORDER BY trade_date ASC
                """,
                (symbol, market, start.isoformat(), end.isoformat()),
            )
            rows = cursor.fetchall()
        if not rows:
            return None

        bars: list[PriceBar] = []
        oldest_fetched_at: datetime | None = None
        row_source = ""
        for row in rows:
            (
                row_symbol,
                row_market,
                trade_date,
                open_str,
                high_str,
                low_str,
                close_str,
                volume,
                currency,
                source,
                as_of_str,
                fetched_at_str,
            ) = row
            try:
                bar = PriceBar(
                    symbol=row_symbol,
                    market=row_market,
                    date=date.fromisoformat(trade_date),
                    open=Decimal(open_str),
                    high=Decimal(high_str),
                    low=Decimal(low_str),
                    close=Decimal(close_str),
                    volume=volume,
                    currency=currency,
                    as_of=datetime.fromisoformat(as_of_str),
                    source=source,
                )
            except (InvalidOperation, ValueError):
                # Corrupt row: skip rather than fabricate/repair, and keep going.
                continue
            bars.append(bar)
            row_source = source
            fetched_at = datetime.fromisoformat(fetched_at_str)
            if oldest_fetched_at is None or fetched_at < oldest_fetched_at:
                oldest_fetched_at = fetched_at

        if not bars or oldest_fetched_at is None:
            return None

        staleness = moment - oldest_fetched_at
        staleness_minutes = max(0, int(staleness.total_seconds() // 60))
        return CacheReadResult(
            bars=bars,
            fetched_at=oldest_fetched_at,
            source=row_source,
            staleness_minutes=staleness_minutes,
        )
