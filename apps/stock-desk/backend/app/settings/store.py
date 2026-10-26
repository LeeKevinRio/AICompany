"""SQLite-backed storage for :class:`app.settings.models.AppSettings`.

One row per section (``risk_budget`` / ``cost_model`` / ``alerts`` /
``net_worth``) holding the section's validated JSON, in the same database file
as the price cache and the
positions table (``STOCK_DESK_DB_PATH``), following ``app/positions/store.py``:
connections are opened per operation and closed via ``contextlib.closing``.

Reads are forgiving on purpose. A section that is absent, unparseable, or no
longer matches the schema (an older build wrote a field that has since been
removed) falls back to that section's **defaults** and logs a warning, rather
than taking the API down: settings are preferences, and refusing to serve a
risk budget because one stored key drifted would be worse than serving the
conservative default and saying so in the log.

Writes are not the only thing that changes a stored section: constructing the
store runs the S2 migration (:mod:`app.settings.migrations`, CEO #63), which
rewrites a stored cap-1 ``max_position_weight`` of 0.15 to 0.10 once and keeps
a record of it in its own table. It works on the raw stored JSON, never through
:meth:`SettingsStore.load` and :meth:`SettingsStore.save`, for the reason given
there.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.advice.limits import RiskBudget
from app.data.cache import BUSY_TIMEOUT_MS, resolve_db_path
from app.data.sqlite_util import enable_wal
from app.settings.migrations import (
    Cap1MigrationRecord,
    init_migrations_table,
    migrate_cap1_default,
    read_cap1_migration,
)
from app.settings.models import (
    AlertSettings,
    AppSettings,
    CostModelSettings,
    NetWorthSettings,
)

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_settings (
    section TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

#: section name -> the model that validates it.
_SECTIONS: dict[str, type[BaseModel]] = {
    "risk_budget": RiskBudget,
    "cost_model": CostModelSettings,
    "alerts": AlertSettings,
    # The row's own ``updated_at`` column is rewritten on every save of any
    # section, so it cannot answer "when did the user last report this". The
    # net worth carries its own timestamp inside the payload for that reason.
    "net_worth": NetWorthSettings,
}


class SettingsStore:
    """Load and persist the settings document, section by section."""

    def __init__(self, db_path: str | Path | None = None, *, now: datetime | None = None) -> None:
        """Open (creating if needed) the settings tables, then run the S2 migration.

        ``now`` fixes the migration record's timestamp for tests; it is still the
        server's clock either way.
        """
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema(now=now)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        # Callers wrap this in contextlib.closing; see app/positions/store.py.
        return sqlite3.connect(self._db_path, timeout=BUSY_TIMEOUT_MS / 1000)

    def _init_schema(self, *, now: datetime | None = None) -> None:
        # One connection for the DDL and the migration: an in-memory database
        # exists only for the connection that created it.
        with closing(self._connect()) as conn, conn:
            enable_wal(conn)
            conn.execute(_CREATE_TABLE_SQL)
            init_migrations_table(conn)
            # Every construction is a "start" for the S2 migration (CEO #63):
            # it is idempotent, and terminal once it has migrated or found
            # nothing to migrate (app/settings/migrations.py).
            migrate_cap1_default(
                conn, _SECTIONS, now=now if now is not None else datetime.now(UTC)
            )

    def cap1_migration(self) -> Cap1MigrationRecord | None:
        """The S2 cap-1 migration record, or ``None`` if none was ever written."""
        with closing(self._connect()) as conn:
            init_migrations_table(conn)
            return read_cap1_migration(conn)

    def load(self) -> AppSettings:
        """Return the stored settings, falling back to defaults per section."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT section, payload FROM app_settings").fetchall()
        stored = {str(section): str(payload) for section, payload in rows}
        sections: dict[str, Any] = {}
        for name, model in _SECTIONS.items():
            parsed = self._parse_section(name, model, stored.get(name))
            if parsed is not None:
                sections[name] = parsed
        return AppSettings(**sections)

    def save(self, settings: AppSettings, *, now: datetime | None = None) -> AppSettings:
        """Persist every section and return what was written."""
        moment = (now if now is not None else datetime.now(UTC)).isoformat()
        rows = [
            (name, json.dumps(getattr(settings, name).model_dump(), ensure_ascii=False), moment)
            for name in _SECTIONS
        ]
        with closing(self._connect()) as conn, conn:
            conn.executemany(
                """
                INSERT INTO app_settings (section, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(section) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
        return settings

    @staticmethod
    def _parse_section(name: str, model: type[BaseModel], payload: str | None) -> Any | None:
        """Validate one stored section, or ``None`` to use the model's defaults."""
        if payload is None:
            return None
        try:
            return model.model_validate_json(payload)
        except ValidationError:
            logger.warning(
                "stored settings section %r no longer matches its schema; "
                "falling back to defaults for this section",
                name,
            )
            return None
