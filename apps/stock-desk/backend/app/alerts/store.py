"""SQLite storage for alert rules and the events they raise.

Same database file and connection discipline as ``app/positions/store.py``
(``STOCK_DESK_DB_PATH``, one connection per operation, closed via
``contextlib.closing``). Rule parameters are stored as JSON in a single
``params`` column: the four rule types have different parameter shapes, and one
validated JSON document per row keeps the schema from sprouting a nullable
column per type.

Events are append-only apart from acknowledgement. A fired alert is a record of
something that was observed at a point in time, so it is never rewritten or
deleted when the underlying number moves back; the user acknowledges it instead.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.alerts.models import AlertEvent, AlertRule, AlertRuleInput
from app.data.cache import resolve_db_path

_CREATE_RULES_SQL = """
CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    params TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    rule_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    message TEXT NOT NULL,
    observed TEXT NOT NULL,
    triggered_at TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    acknowledged_at TEXT
)
"""

_CREATE_EVENT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_alert_events_rule_time
ON alert_events (rule_id, triggered_at DESC)
"""

_RULE_COLUMNS = (
    "id",
    "type",
    "symbol",
    "market",
    "params",
    "enabled",
    "note",
    "created_at",
    "updated_at",
)

_EVENT_COLUMNS = (
    "id",
    "rule_id",
    "rule_type",
    "symbol",
    "market",
    "message",
    "observed",
    "triggered_at",
    "acknowledged",
    "acknowledged_at",
)

_SELECT_RULES = ", ".join(_RULE_COLUMNS)
_SELECT_EVENTS = ", ".join(_EVENT_COLUMNS)


class AlertStore:
    """CRUD for alert rules plus append/acknowledge for alert events."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        # Callers wrap this in contextlib.closing; see app/positions/store.py.
        return sqlite3.connect(self._db_path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_RULES_SQL)
            conn.execute(_CREATE_EVENTS_SQL)
            conn.execute(_CREATE_EVENT_INDEX_SQL)

    # --- Rules ---------------------------------------------------------------

    def list_rules(self, *, enabled_only: bool = False) -> list[AlertRule]:
        """Every rule, ordered by id; optionally only the enabled ones."""
        clause = " WHERE enabled = 1" if enabled_only else ""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_RULES} FROM alert_rules{clause} ORDER BY id ASC"
            ).fetchall()
        return [self._row_to_rule(row) for row in rows]

    def get_rule(self, rule_id: int) -> AlertRule | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_SELECT_RULES} FROM alert_rules WHERE id = ?", (rule_id,)
            ).fetchone()
        return self._row_to_rule(row) if row is not None else None

    def create_rule(self, data: AlertRuleInput, *, now: datetime | None = None) -> AlertRule:
        moment = (now if now is not None else datetime.now(UTC)).isoformat()
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                """
                INSERT INTO alert_rules
                    (type, symbol, market, params, enabled, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.type,
                    data.symbol,
                    data.market,
                    json.dumps(data.params.model_dump(), ensure_ascii=False),
                    int(data.enabled),
                    data.note,
                    moment,
                    moment,
                ),
            )
            new_id = int(cursor.lastrowid or 0)
        created = self.get_rule(new_id)
        assert created is not None  # just inserted within the same store
        return created

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule. Its past events are kept: they still happened."""
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
            return cursor.rowcount > 0

    # --- Events --------------------------------------------------------------

    def append_event(
        self,
        *,
        rule: AlertRule,
        message: str,
        observed: dict[str, float | str | None],
        triggered_at: datetime | None = None,
    ) -> AlertEvent:
        """Record one firing of ``rule``."""
        moment = (triggered_at if triggered_at is not None else datetime.now(UTC)).isoformat()
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                """
                INSERT INTO alert_events
                    (rule_id, rule_type, symbol, market, message, observed,
                     triggered_at, acknowledged, acknowledged_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL)
                """,
                (
                    rule.id,
                    rule.type,
                    rule.symbol,
                    rule.market,
                    message,
                    json.dumps(observed, ensure_ascii=False),
                    moment,
                ),
            )
            new_id = int(cursor.lastrowid or 0)
        created = self.get_event(new_id)
        assert created is not None  # just inserted within the same store
        return created

    def get_event(self, event_id: int) -> AlertEvent | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_SELECT_EVENTS} FROM alert_events WHERE id = ?", (event_id,)
            ).fetchone()
        return self._row_to_event(row) if row is not None else None

    def list_events(
        self, *, unacknowledged: bool | None = None, limit: int = 200
    ) -> list[AlertEvent]:
        """Events newest first, optionally filtered by acknowledgement state."""
        clause = ""
        if unacknowledged is True:
            clause = " WHERE acknowledged = 0"
        elif unacknowledged is False:
            clause = " WHERE acknowledged = 1"
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_EVENTS} FROM alert_events{clause} "
                "ORDER BY triggered_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def last_triggered_at(self, rule_id: int) -> datetime | None:
        """When ``rule_id`` last fired, for the cooldown check."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT MAX(triggered_at) FROM alert_events WHERE rule_id = ?", (rule_id,)
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(str(row[0]))

    def acknowledge(self, event_id: int, *, now: datetime | None = None) -> AlertEvent | None:
        """Mark one event acknowledged; ``None`` if it does not exist."""
        moment = (now if now is not None else datetime.now(UTC)).isoformat()
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE alert_events SET acknowledged = 1, acknowledged_at = ? WHERE id = ?",
                (moment, event_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_event(event_id)

    # --- Row mapping ---------------------------------------------------------

    @staticmethod
    def _row_to_rule(row: tuple[Any, ...]) -> AlertRule:
        # sqlite3 hands back dynamically typed cells; the models enforce the
        # real invariants (including the type/params pairing) at construction.
        (
            row_id,
            rule_type,
            symbol,
            market,
            params,
            enabled,
            note,
            created_at,
            updated_at,
        ) = row
        return AlertRule(
            id=int(row_id),
            type=rule_type,
            symbol=str(symbol),
            market=market,
            params=json.loads(str(params)),
            enabled=bool(enabled),
            note=None if note is None else str(note),
            created_at=datetime.fromisoformat(str(created_at)),
            updated_at=datetime.fromisoformat(str(updated_at)),
        )

    @staticmethod
    def _row_to_event(row: tuple[Any, ...]) -> AlertEvent:
        (
            row_id,
            rule_id,
            rule_type,
            symbol,
            market,
            message,
            observed,
            triggered_at,
            acknowledged,
            acknowledged_at,
        ) = row
        return AlertEvent(
            id=int(row_id),
            rule_id=int(rule_id),
            rule_type=rule_type,
            symbol=str(symbol),
            market=market,
            message=str(message),
            observed=json.loads(str(observed)),
            triggered_at=datetime.fromisoformat(str(triggered_at)),
            acknowledged=bool(acknowledged),
            acknowledged_at=(
                None if acknowledged_at is None else datetime.fromisoformat(str(acknowledged_at))
            ),
        )
