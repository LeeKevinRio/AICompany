"""Shared fixtures for the N-156 settings-fallback tests (ADR-0032, CEO #74).

Raw rows are written straight into the store's file here, the way a corrupted
or older-build file would hold them: production code outside ``app/settings``
may not name that table (K-4), but a test has to put a broken payload
somewhere.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any

from app.settings.models import AppSettings
from app.settings.store import LoadedSettings, SettingsStore

#: The four sections in ``_SECTIONS`` order.
SECTIONS: tuple[str, ...] = ("risk_budget", "cost_model", "alerts", "net_worth")

#: A payload no section's schema accepts (an unknown key on an ``extra="forbid"``
#: model), and one that is not JSON at all.
SCHEMA_MISMATCH = '{"not": "valid"}'
NOT_JSON = "{broken"


def write_raw(store: SettingsStore, section: str, payload: str) -> None:
    """Put ``payload`` in ``section``'s row as is, bypassing validation."""
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO app_settings (section, payload, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(section) DO UPDATE SET payload = excluded.payload",
            (section, payload, "2026-01-01T00:00:00+00:00"),
        )


def delete_row(store: SettingsStore, section: str) -> None:
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute("DELETE FROM app_settings WHERE section = ?", (section,))


def raw_rows(store: SettingsStore) -> dict[str, tuple[str, str]]:
    """Every stored row: section -> (payload, updated_at)."""
    with closing(sqlite3.connect(store.db_path)) as conn:
        rows = conn.execute("SELECT section, payload, updated_at FROM app_settings").fetchall()
    return {str(section): (str(payload), str(stamp)) for section, payload, stamp in rows}


def raw_payload(store: SettingsStore, section: str) -> dict[str, Any] | str:
    """One stored payload, parsed when it is JSON and verbatim when it is not."""
    payload, _ = raw_rows(store)[section]
    try:
        parsed: dict[str, Any] = json.loads(payload)
    except ValueError:
        return payload
    return parsed


def break_sections(store: SettingsStore, sections: tuple[str, ...]) -> None:
    """Make each named section a stored-but-invalid one (a fallback section)."""
    for section in sections:
        write_raw(store, section, SCHEMA_MISMATCH)


class SpySettingsStore(SettingsStore):
    """A real store that counts the reads a handler makes (K-5)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.reads: list[str] = []

    def load(self) -> AppSettings:
        self.reads.append("load")
        return super().load()

    def load_with_status(self) -> LoadedSettings:
        self.reads.append("load_with_status")
        return super().load_with_status()
