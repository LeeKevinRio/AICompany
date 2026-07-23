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
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final

from app.data.interface import Market, PriceBar

DEFAULT_DB_PATH: Final[str] = "./data/stock-desk.db"
DEFAULT_TTL_SECONDS: Final[int] = 24 * 60 * 60

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


def resolve_db_path() -> Path:
    """Resolve the cache database path from ``STOCK_DESK_DB_PATH`` (or the default)."""
    raw = os.environ.get("STOCK_DESK_DB_PATH", DEFAULT_DB_PATH)
    return Path(raw)


@dataclass(frozen=True)
class CacheReadResult:
    """What the cache has on hand for a requested symbol/date range.

    ``fetched_at`` is the oldest ``fetched_at`` among the returned rows
    (the conservative choice: staleness is reported as "at least this old").
    """

    bars: list[PriceBar]
    fetched_at: datetime
    source: str
    staleness_minutes: int
    is_within_ttl: bool


class PriceBarCache:
    """SQLite (WAL mode) cache of daily price bars, keyed by symbol/market/date."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ttl_seconds = ttl_seconds
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)

    def put(
        self,
        bars: list[PriceBar],
        *,
        source: str,
        fetched_at: datetime | None = None,
    ) -> None:
        """Upsert a batch of bars into the cache, tagged with a fetch timestamp."""
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
        with self._connect() as conn:
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
        exist, they are returned regardless of TTL (the cache is a
        last-resort layer in the degradation ladder) but ``is_within_ttl``
        tells the caller whether the data is still inside the configured
        freshness window.
        """
        moment = now if now is not None else datetime.now(UTC)
        with self._connect() as conn:
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
        is_within_ttl = staleness.total_seconds() <= self._ttl_seconds
        return CacheReadResult(
            bars=bars,
            fetched_at=oldest_fetched_at,
            source=row_source,
            staleness_minutes=staleness_minutes,
            is_within_ttl=is_within_ttl,
        )
