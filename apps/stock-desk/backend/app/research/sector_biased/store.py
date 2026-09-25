"""The research database: ``STOCK_DESK_RESEARCH_DB_PATH`` (ADR-0012 C-8, C-22, D-14).

Default ``./data/stock-desk-research.db``. This module is the only place the
variable is read (C-27); the API process never opens the file, and nothing in
it is read back by the judged path.

Tables:

* ``research_backfill_bars`` -- back-filled daily bars (``backfill_non_pit``):
  history fetched after the fact, so it is never point-in-time and never goes
  near the market DB (ADR-0012 D-3: longer history only lands here);
* ``research_study_runs`` -- one row per study segment (in-sample,
  out-of-sample, full) with its rates and the full JSON report.

Every row carries :data:`~app.research.sector_biased.hindsight.BIAS_LABEL`,
enforced by a ``CHECK`` constraint, and the data regime is pinned to
``backfill_non_pit`` the same way. The file is rebuildable research output, so
no append-only trigger is imposed (ADR-0012 Consequences: 「研究 DB 可以重建」).
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final

import pandas as pd

from app.research.sector_biased.hindsight import BIAS_DIRECTIONS, BIAS_LABEL

#: Environment variable naming the research DB file (read here and nowhere else).
RESEARCH_DB_PATH_ENV_VAR: Final = "STOCK_DESK_RESEARCH_DB_PATH"
DEFAULT_RESEARCH_DB_PATH: Final = Path("./data/stock-desk-research.db")
BUSY_TIMEOUT_MS: Final = 5000
DATA_REGIME: Final = "backfill_non_pit"

#: Every table this file may hold (C-8; the isolation test compares sqlite_master).
RESEARCH_TABLES: Final[frozenset[str]] = frozenset(
    {"research_backfill_bars", "research_study_runs"}
)

_LABEL_CHECK: Final = f"CHECK (bias_label = '{BIAS_LABEL}')"
_REGIME_CHECK: Final = f"CHECK (data_regime = '{DATA_REGIME}')"

_SCHEMA: Final[tuple[str, ...]] = (
    f"""
    CREATE TABLE IF NOT EXISTS research_backfill_bars (
        symbol TEXT NOT NULL,
        session_date TEXT NOT NULL,
        source TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        shares INTEGER,
        traded_value REAL,
        data_regime TEXT NOT NULL {_REGIME_CHECK},
        bias_label TEXT NOT NULL {_LABEL_CHECK},
        PRIMARY KEY (symbol, session_date, source, fetched_at)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS research_study_runs (
        study_id TEXT NOT NULL,
        segment TEXT NOT NULL CHECK (segment IN ('in_sample', 'out_of_sample', 'full')),
        method_version TEXT NOT NULL,
        regime TEXT NOT NULL CHECK (regime = 'hindsight'),
        data_regime TEXT NOT NULL {_REGIME_CHECK},
        bias_label TEXT NOT NULL {_LABEL_CHECK},
        bias_directions TEXT NOT NULL,
        created_at TEXT NOT NULL,
        sample_start TEXT,
        sample_end TEXT,
        sample_count INTEGER NOT NULL,
        beat_count_net INTEGER NOT NULL,
        beat_count_gross INTEGER NOT NULL,
        base_rate_net REAL,
        base_rate_gross REAL,
        report_json TEXT NOT NULL,
        PRIMARY KEY (study_id, segment)
    )
    """,
)


def resolve_research_db_path() -> Path:
    """``STOCK_DESK_RESEARCH_DB_PATH`` or the default location."""
    configured = os.environ.get(RESEARCH_DB_PATH_ENV_VAR)
    return Path(configured) if configured else DEFAULT_RESEARCH_DB_PATH


@dataclass(frozen=True)
class StudyRow:
    """One stored study segment (what :meth:`ResearchStore.study_rows` returns)."""

    study_id: str
    segment: str
    method_version: str
    bias_label: str
    bias_directions: Mapping[str, str]
    sample_count: int
    beat_count_net: int
    base_rate_net: float | None
    report: Mapping[str, object]


class ResearchStore:
    """Writes and reads the research DB. Nothing outside ``app.research`` uses it."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_research_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            for statement in _SCHEMA:
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

    def save_backfill_bars(self, bars: pd.DataFrame, *, source: str, fetched_at: datetime) -> int:
        """Store back-filled bars (``symbol, session_date, open..traded_value``)."""
        frame = bars.loc[
            :, ["symbol", "session_date", "open", "high", "low", "close", "shares", "traded_value"]
        ]
        days = pd.to_datetime(frame["session_date"]).dt.date
        prices = frame[["open", "high", "low", "close", "traded_value"]].astype(float).to_numpy()
        shares = frame["shares"].astype("int64").to_numpy()
        rows = [
            (
                str(symbol),
                day.isoformat(),
                source,
                fetched_at.isoformat(),
                float(price[0]),
                float(price[1]),
                float(price[2]),
                float(price[3]),
                int(volume),
                float(price[4]),
                DATA_REGIME,
                BIAS_LABEL,
            )
            for symbol, day, price, volume in zip(
                frame["symbol"], days, prices, shares, strict=True
            )
        ]
        with self._transaction() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO research_backfill_bars (symbol, session_date, source, "
                "fetched_at, open, high, low, close, shares, traded_value, data_regime, "
                "bias_label) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def load_backfill_bars(self) -> pd.DataFrame:
        with closing(self._connect()) as conn:
            frame = pd.read_sql_query(
                "SELECT symbol, session_date, source, fetched_at, open, high, low, close, "
                "shares, traded_value FROM research_backfill_bars ORDER BY session_date, symbol",
                conn,
            )
        frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.date
        return frame

    def save_study_segment(
        self,
        *,
        study_id: str,
        segment: str,
        method_version: str,
        created_at: datetime,
        sample_start: date | None,
        sample_end: date | None,
        sample_count: int,
        beat_count_net: int,
        beat_count_gross: int,
        base_rate_net: float | None,
        base_rate_gross: float | None,
        report: Mapping[str, object],
    ) -> None:
        payload = {"bias_label": BIAS_LABEL, "bias_directions": dict(BIAS_DIRECTIONS), **report}
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO research_study_runs (study_id, segment, method_version, regime, "
                "data_regime, bias_label, bias_directions, created_at, sample_start, sample_end, "
                "sample_count, beat_count_net, beat_count_gross, base_rate_net, base_rate_gross, "
                "report_json) VALUES (?, ?, ?, 'hindsight', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    study_id,
                    segment,
                    method_version,
                    DATA_REGIME,
                    BIAS_LABEL,
                    json.dumps(dict(BIAS_DIRECTIONS), sort_keys=True),
                    created_at.isoformat(),
                    sample_start.isoformat() if sample_start else None,
                    sample_end.isoformat() if sample_end else None,
                    sample_count,
                    beat_count_net,
                    beat_count_gross,
                    base_rate_net,
                    base_rate_gross,
                    json.dumps(payload, sort_keys=True, default=str),
                ),
            )

    def study_rows(self, study_id: str) -> tuple[StudyRow, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT study_id, segment, method_version, bias_label, bias_directions, "
                "sample_count, beat_count_net, base_rate_net, report_json "
                "FROM research_study_runs WHERE study_id = ? ORDER BY segment",
                (study_id,),
            ).fetchall()
        return tuple(
            StudyRow(
                study_id=str(row[0]),
                segment=str(row[1]),
                method_version=str(row[2]),
                bias_label=str(row[3]),
                bias_directions=json.loads(row[4]),
                sample_count=int(row[5]),
                beat_count_net=int(row[6]),
                base_rate_net=float(row[7]) if row[7] is not None else None,
                report=json.loads(row[8]),
            )
            for row in rows
        )
