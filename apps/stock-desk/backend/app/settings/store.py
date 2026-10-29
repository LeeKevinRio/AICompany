"""SQLite-backed storage for :class:`app.settings.models.AppSettings`.

One row per section (``risk_budget`` / ``cost_model`` / ``alerts`` /
``net_worth``) holding the section's validated JSON, in the same database file
as the price cache and the
positions table (``STOCK_DESK_DB_PATH``), following ``app/positions/store.py``:
connections are opened per operation and closed via ``contextlib.closing``.

Reads do not refuse to answer. A section that is absent, unparseable, or no
longer matches the schema (an older build wrote a field that has since been
removed) is served with that section's **defaults** rather than taking the API
down. Those defaults are not "the conservative choice": a user whose stored
risk budget was stricter than the defaults is *loosened* by them. So a section
that was stored but failed validation is a **fallback section**, and every read
says which ones it served that way: :meth:`SettingsStore.load_with_status`
returns the values together with ``fallback_sections`` from one and the same
read, and the callers disclose them (ADR-0032 Decision 1-2, K-1/K-2/K-12). An
absent row is not a fallback -- a file saved before a section existed (no
``net_worth`` row before FR-9) is a valid one. The state is judged afresh on
every read and never stored; reading takes no lock and writes nothing (K-3).

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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.advice.limits import RiskBudget
from app.data.cache import BUSY_TIMEOUT_MS, resolve_db_path
from app.data.sqlite_util import enable_wal
from app.settings.migrations import (
    Cap1MigrationRecord,
    init_migrations_table,
    migrate_cap1_default,
    note_cap1_write,
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


#: How one stored section reads: no row, a row that validates, or a row that
#: does not (bad JSON or a schema mismatch). Only ``invalid`` is a fallback.
SectionState = Literal["absent", "valid", "invalid"]


@dataclass(frozen=True)
class LoadedSettings:
    """One read of the settings document: the values in force and the fallbacks.

    ``fallback_sections`` names, in ``_SECTIONS`` order, every section that was
    stored but failed validation and is therefore served with its defaults
    (ADR-0032 K-1/K-2). Both halves come from the same ``SELECT``, so whatever
    a caller discloses is about exactly the values it evaluated with (K-5).
    """

    settings: AppSettings
    fallback_sections: tuple[str, ...]


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
            migrate_cap1_default(conn, _SECTIONS, now=now if now is not None else datetime.now(UTC))

    def cap1_migration(self) -> Cap1MigrationRecord | None:
        """The S2 cap-1 migration record, or ``None`` if none was ever written."""
        with closing(self._connect()) as conn:
            init_migrations_table(conn)
            return read_cap1_migration(conn)

    def load(self) -> AppSettings:
        """Return the stored settings, defaults standing in per fallback section.

        Exactly ``load_with_status().settings``. A caller that shows the user
        anything derived from these values should call
        :meth:`load_with_status` instead, so it can say which sections are
        defaults (ADR-0032 Decision 2).
        """
        return self._read().settings

    def load_with_status(self) -> LoadedSettings:
        """Return the stored settings and the sections that fell back to defaults.

        One ``SELECT`` on a fresh connection, judged on the spot: no lock is
        taken, nothing is written, and nothing about the outcome is kept
        (ADR-0032 Decision 1, K-3).
        """
        return self._read()

    def _read(self) -> LoadedSettings:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT section, payload FROM app_settings").fetchall()
        return self._judge({str(section): str(payload) for section, payload in rows})

    @classmethod
    def _judge(cls, stored: dict[str, str]) -> LoadedSettings:
        """Turn raw stored payloads into values plus the fallback sections."""
        sections: dict[str, Any] = {}
        fallback: list[str] = []
        for name, model in _SECTIONS.items():
            state, parsed = cls._parse_section(name, model, stored.get(name))
            if state == "valid":
                sections[name] = parsed
            elif state == "invalid":
                fallback.append(name)
        return LoadedSettings(settings=AppSettings(**sections), fallback_sections=tuple(fallback))

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
            # Same transaction: a migrated record learns that the user has
            # since written another cap-1 value (F1/F8). Nothing else of the
            # record moves here (app/settings/migrations.py, I-6).
            init_migrations_table(conn)
            note_cap1_write(conn, settings.risk_budget.max_position_weight)
        return settings

    @staticmethod
    def _parse_section(
        name: str, model: type[BaseModel], payload: str | None
    ) -> tuple[SectionState, Any | None]:
        """Judge one stored section: its state, and the validated value if any.

        The only place a stored section is judged (ADR-0032 K-4): nothing
        outside :mod:`app.settings` may read the raw payloads or call this.
        """
        if payload is None:
            return "absent", None
        try:
            return "valid", model.model_validate_json(payload)
        except ValidationError:
            # Invalid JSON is a ValidationError too (``json_invalid``).
            logger.warning(
                "stored settings section %r no longer matches its schema; "
                "serving its defaults and disclosing the fallback",
                name,
            )
            return "invalid", None
