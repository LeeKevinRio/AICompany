"""SQLite-backed store for 除權息 events.

Shares the same database file as every other store in this backend (the
``STOCK_DESK_DB_PATH`` environment variable, default ``./data/stock-desk.db``,
resolved by ``app.data.cache.resolve_db_path``) -- a new table in the existing
database, not a new database file or a new architecture layer, exactly as
``app.directory.store`` did.

Writes are an idempotent upsert keyed on ``(symbol, market, ex_date)``:
re-running ``python -m app.dividends.sync`` refreshes existing rows in place
rather than duplicating them. Because the upstream dataset is a rolling window
rather than full history, repeated runs **accumulate** coverage over time --
which is why the key is the event, not the sync.

Money columns are stored as TEXT and read back as ``Decimal``. Storing prices
as SQLite REAL would silently round the exchange's own published figures, and
the adjustment factor is a ratio of two of them.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
from pathlib import Path

from app.data.cache import resolve_db_path
from app.dividends.models import DividendEvent
from app.positions.models import Market

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS dividend_events (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    previous_close TEXT,
    reference_price TEXT,
    cash_dividend TEXT NOT NULL,
    rights_value TEXT NOT NULL,
    source TEXT NOT NULL,
    as_of TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market, ex_date)
)
"""

#: The read path is always "one symbol, one date range", which the primary key's
#: leading columns already serve; this index only helps the coverage queries.
_CREATE_DATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_dividend_events_ex_date
ON dividend_events (ex_date)
"""

_SELECT_COLUMNS = (
    "symbol, market, ex_date, previous_close, reference_price, "
    "cash_dividend, rights_value, source, as_of"
)


class DividendEventStore:
    """SQLite (WAL mode) store for 除權息 events, keyed by symbol + ex-date."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_DATE_INDEX_SQL)

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
        rows = [
            (
                event.symbol,
                event.market,
                event.ex_date.isoformat(),
                _to_text(event.previous_close),
                _to_text(event.reference_price),
                str(event.cash_dividend),
                str(event.rights_value),
                event.source,
                event.as_of.isoformat(),
                moment.isoformat(),
            )
            for event in events
        ]
        with closing(self._connect()) as conn, conn:
            conn.executemany(
                """
                INSERT INTO dividend_events (
                    symbol, market, ex_date, previous_close, reference_price,
                    cash_dividend, rights_value, source, as_of, synced_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, market, ex_date) DO UPDATE SET
                    previous_close=excluded.previous_close,
                    reference_price=excluded.reference_price,
                    cash_dividend=excluded.cash_dividend,
                    rights_value=excluded.rights_value,
                    source=excluded.source,
                    as_of=excluded.as_of,
                    synced_at=excluded.synced_at
                """,
                rows,
            )
        return len(rows)

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

    def last_synced_at(self) -> datetime | None:
        """The most recent sync timestamp, or ``None`` when never synced."""
        with closing(self._connect()) as conn:
            cursor = conn.execute("SELECT MAX(synced_at) FROM dividend_events")
            row = cursor.fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(str(row[0]))


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
        source=str(row[7]),
        as_of=datetime.fromisoformat(str(row[8])),
    )
