"""SQLite-backed store for the security directory.

Shares the same database file as every other store in this backend (the
``STOCK_DESK_DB_PATH`` environment variable, default ``./data/stock-desk.db``,
resolved by ``app.data.cache.resolve_db_path``) -- per the CEO 裁示紀錄 in
``work/stock-desk-代號目錄-PRD.md`` ("沿用既有 adapter/快取/SQLite 慣例,無新
依賴無新架構層"), this is a new table in the existing database, not a new
database file or a new architecture layer.

Writes are an idempotent upsert keyed on ``(symbol, market)`` -- re-running the
sync CLI (``python -m app.directory.sync``) refreshes existing rows in place
rather than duplicating them, mirroring ``PriceBarCache.put``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.data.cache import resolve_db_path
from app.directory.models import DirectoryEntry

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS security_directory (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    as_of TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market)
)
"""

#: Supports both the resolve (`symbol` prefix on the primary key already
#: covers this) and the search endpoint's substring-on-name scan.
_CREATE_NAME_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_security_directory_name
ON security_directory (name)
"""


class SecurityDirectoryStore:
    """SQLite (WAL mode) store for ``symbol -> name -> market`` lookups."""

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
            conn.execute(_CREATE_NAME_INDEX_SQL)

    def upsert(
        self,
        entries: Sequence[DirectoryEntry],
        *,
        synced_at: datetime | None = None,
    ) -> int:
        """Upsert ``entries``, keyed on ``(symbol, market)``. Returns the row count written."""
        if not entries:
            return 0
        moment = synced_at if synced_at is not None else datetime.now(UTC)
        rows = [
            (
                entry.symbol,
                entry.market,
                entry.name,
                entry.source,
                entry.as_of.isoformat(),
                moment.isoformat(),
            )
            for entry in entries
        ]
        with closing(self._connect()) as conn, conn:
            conn.executemany(
                """
                INSERT INTO security_directory (symbol, market, name, source, as_of, synced_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, market) DO UPDATE SET
                    name=excluded.name,
                    source=excluded.source,
                    as_of=excluded.as_of,
                    synced_at=excluded.synced_at
                """,
                rows,
            )
        return len(rows)

    def count(self) -> int:
        """Total number of directory rows. ``0`` means "never synced" for FR-7's purposes."""
        with closing(self._connect()) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM security_directory")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def is_synced(self) -> bool:
        """Whether the directory has ever been populated (FR-7's degrade signal)."""
        return self.count() > 0

    def resolve(self, symbol: str) -> DirectoryEntry | None:
        """Exact-match lookup by symbol. Returns ``None`` when not in the directory."""
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                SELECT symbol, market, name, source, as_of
                FROM security_directory
                WHERE symbol = ?
                """,
                (symbol,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    def search(self, query: str, *, limit: int) -> tuple[list[DirectoryEntry], bool]:
        """Prefix-on-symbol + substring-on-name candidates, merged and deduped.

        Returns ``(items, truncated)`` where ``truncated`` is ``True`` when
        more candidates matched than ``limit`` allows (AC-7): the caller must
        not claim "these are the only results" in that case.

        Ranking: symbol-prefix hits are returned before name-substring hits
        (per the dispatch's "代號命中排前"), each group ordered by symbol.
        """
        stripped = query.strip()
        if not stripped or limit <= 0:
            return [], False

        with closing(self._connect()) as conn:
            prefix_cursor = conn.execute(
                """
                SELECT symbol, market, name, source, as_of
                FROM security_directory
                WHERE symbol LIKE ? ESCAPE '\\'
                ORDER BY symbol ASC
                """,
                (f"{_escape_like(stripped)}%",),
            )
            prefix_rows = prefix_cursor.fetchall()

            name_cursor = conn.execute(
                """
                SELECT symbol, market, name, source, as_of
                FROM security_directory
                WHERE name LIKE ? ESCAPE '\\'
                ORDER BY symbol ASC
                """,
                (f"%{_escape_like(stripped)}%",),
            )
            name_rows = name_cursor.fetchall()

        seen: set[tuple[str, str]] = set()
        merged: list[DirectoryEntry] = []
        for row in (*prefix_rows, *name_rows):
            key = (row[0], row[1])
            if key in seen:
                continue
            seen.add(key)
            merged.append(_row_to_entry(row))

        truncated = len(merged) > limit
        return merged[:limit], truncated


def _escape_like(value: str) -> str:
    """Escape SQLite ``LIKE`` wildcards so a literal ``%``/``_`` in a query is not a wildcard."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_entry(row: tuple[str, str, str, str, str]) -> DirectoryEntry:
    symbol, market, name, source, as_of_str = row
    return DirectoryEntry(
        symbol=symbol,
        name=name,
        market=market,  # type: ignore[arg-type]  # DB only ever holds validated Market values
        source=source,
        as_of=datetime.fromisoformat(as_of_str),
    )
