"""Fixtures for the forecast ledger core tests (ADR-0030 D-2): rows, bars, a definition.

Every database here is a ``tmp_path`` file or ``:memory:``; nothing opens the
service database. The values are fixtures, not dirdef or rule values.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final
from zoneinfo import ZoneInfo

import pytest

from app.dirdef.definition import DirectionDefinition, definition_logic_sha256, definition_sha256
from app.dirdef.registry import PublishedDefinition
from app.forecast import definitions
from app.forecast.schema import create_schema
from tests.dirdef_helpers import make_definition

TAIPEI: Final = ZoneInfo("Asia/Taipei")

TS: Final = "2026-11-13T14:10:00.000000+00:00"
HEX_A: Final = "a" * 64
HEX_B: Final = "b" * 64
CLAIM_H3: Final = "market|h3|r1|dirdef-v1.0|forward"
ULID_OK: Final = "01JCZ0000000000000000000AB"

#: One valid raw row per table (columns as stored); the CHECK tests vary one column.
VALID_ROWS: Final[Mapping[str, Mapping[str, object]]] = MappingProxyType(
    {
        "forecast_run": {
            "started_at": TS,
            "trigger": "scheduled",
            "code_commit": "abc123",
            "code_digest": HEX_A,
            "runtime_json": '{"python":"3.13"}',
            "schema_version": 1,
        },
        "forecast_run_end": {
            "run_id": 1,
            "outcome": "ok",
            "candidate_t": "2026-11-13",
            "records_written": 2,
            "error_class": None,
            "ended_at": TS,
        },
        "forecast_input_series": {
            "content_sha256": HEX_B,
            "series_kind": "index_bars",
            "source": "yfinance",
            "source_status": "backup",
            "staleness_minutes": 0,
            "reason": None,
            "dropped_rows_json": "[]",
            "raw_timestamp_available": 0,
            "bars_json": "[{}]",
            "captured_at": TS,
        },
        "forecast_claim_registry": {
            "claim_id": CLAIM_H3,
            "scope_kind": "market",
            "scope_key": "TAIEX",
            "horizon": 3,
            "kind": "forward",
            "rules_version": "r1",
            "rules_sha256": "c" * 64,
            "rules_logic_sha256": "d" * 64,
            "rules_bytes": b"rules: []\n",
            "definition_version": "dirdef-v1.0",
            "definition_sha256": "e" * 64,
            "definition_logic_sha256": "f" * 64,
            "definition_json": "{}",
            "frozen_commit": "abc123",
            "prereg_doc_path": "docs/prereg.md",
            "prereg_doc_blob": b"prereg",
            "review_refs": "work/reviews/x.md",
            "replaces_claim_id": None,
            "replace_reason": None,
            "provisional_results_seen": 0,
            "registered_at": TS,
        },
        "forecast_record": {
            "forecast_id": ULID_OK,
            "run_id": 1,
            "claim_id": CLAIM_H3,
            "scope_kind": "market",
            "scope_key": "TAIEX",
            "horizon": 3,
            "data_as_of": "2026-11-13",
            "definition_version": "dirdef-v1.0",
            "definition_sha256": "e" * 64,
            "rules_version": "r1",
            "rules_sha256": "c" * 64,
            "label": "range",
            "range_basis": None,
            "missing_json": "[]",
            "evidence_json": "{}",
            "band_def": (
                '{"EPS":1e-12,"K_h":0.43,"down_pct":-1.0,"sigma_d":0.01,'
                '"up_pct":1.0,"valid_returns":60}'
            ),
            "base_close": "17000.5",
            "baseline_predictions_json": '{"B1":"range","B2":"range","B6":"range","B8":"range"}',
            "input_series_sha256": HEX_B,
            "inputs_max_fetched_at": TS,
            "created_at": TS,
            "late": 0,
            "late_cutoff_at": "2026-11-13T16:00:00.000000+00:00",
            "valid_until_session_estimate": "2026-11-18",
            "validation_status": "unverified",
            "content_hash": "0" * 64,
        },
    }
)


def memory_ledger() -> sqlite3.Connection:
    """An in-memory database with the ledger schema (foreign keys off: CHECKs only)."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    create_schema(conn)
    return conn


def file_ledger(tmp_path: Path) -> Path:
    """A ``tmp_path`` database file with the ledger schema."""
    path = tmp_path / "ledger.db"
    with sqlite3.connect(path, isolation_level=None) as conn:
        create_schema(conn)
    conn.close()
    return path


def insert(conn: sqlite3.Connection, table: str, row: Mapping[str, object]) -> None:
    names = ", ".join(f'"{name}"' for name in row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", tuple(row.values()))


def row(table: str, **overrides: object) -> dict[str, object]:
    data = dict(VALID_ROWS[table])
    data.update(overrides)
    return data


# --- Store fixtures ----------------------------------------------------------------------


def taipei(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=TAIPEI)


def bar(day: date, close: str = "17000.5", *, fetched: datetime | None = None) -> dict[str, Any]:
    """A final snapshot bar of ``day`` (fetched at 20:00 Taipei that day unless given)."""
    stamp = fetched or datetime.combine(day, datetime.min.time(), TAIPEI) + timedelta(hours=20)
    return {
        "session_date": day,
        "open": Decimal("17000"),
        "high": Decimal("17100.25"),
        "low": Decimal("16900"),
        "close": Decimal(close),
        "volume": 1234,
        "source": "yfinance",
        "as_of": stamp,
        "fetched_at": stamp,
    }


def weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


class FakeClock:
    """A settable store clock."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now = self.now + timedelta(**delta)


def fixture_definition() -> DirectionDefinition:
    return make_definition()


def publish_definition(monkeypatch: pytest.MonkeyPatch, definition: DirectionDefinition) -> None:
    """Register ``definition`` in ``app.forecast.definitions`` for this test only."""
    entry = PublishedDefinition(
        definition=definition,
        definition_logic_sha256=definition_logic_sha256(definition),
        definition_sha256=definition_sha256(definition),
    )
    monkeypatch.setattr(
        definitions,
        "PUBLISHED_DIRECTION_DEFINITIONS",
        MappingProxyType({definition.definition_version: entry}),
    )
    monkeypatch.setattr(definitions, "_DEFINITION_CACHE", {})


def band(definition: DirectionDefinition, horizon: int = 3) -> dict[str, object]:
    """A complete ``band_def`` for a labelled record under ``definition``."""
    return {
        "K_h": definition.k_for(horizon),
        "EPS": definition.EPS,
        "sigma_d": 0.01,
        "valid_returns": definition.SIGMA_MIN_VALID,
        "up_pct": 1.2,
        "down_pct": -1.2,
    }


BASELINES: Final[Mapping[str, object]] = MappingProxyType(
    {
        "B1": {"label": "range"},
        "B2": {"label": "unavailable", "reason": "b2_realized_short"},
        "B6": {"label": "range"},
        "B8": {"label": "bullish"},
    }
)

UTC_NOON: Final = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
