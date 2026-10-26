"""One-time, recorded rewrites of stored settings (S2, CEO #63, 2026-10-26).

There is exactly one migration today: cap 1's stored ``max_position_weight``
equal to the old default 0.15 becomes the new default 0.10
(:data:`app.advice.limits.DEFAULT_MAX_POSITION_WEIGHT`). Changing the default
alone would not reach any installation that had ever saved its settings,
because :meth:`app.settings.store.SettingsStore.save` writes every section in
full -- a stored 0.15 is usually the old default frozen in place, not a choice
(quant proposal 2026-10-26, conclusion 2).

The rules, each from the risk review of 2026-10-26
(``work/reviews/2026-10-26-第1條上限下修審查-風控.md`` S2 附加實作約束) and the
quant proposal's constraint 4:

* **Raw payload in, one key out.** The migration never goes through
  ``load`` -> change -> ``save``: ``load`` silently replaces any section that no
  longer validates with its defaults, and ``save`` would then write those
  defaults over the user's real data for good. It reads the stored JSON
  directly and changes ``risk_budget.max_position_weight`` and nothing else;
  every other key of that section keeps its stored value and every other
  section's row is not written at all.
* **Any invalid section, no migration.** If any stored section fails its
  schema (or is not JSON), nothing is rewritten. A ``skipped`` record naming
  the failed sections is kept and served, so the state is visible rather than
  only logged. A skip is not final: the next construction of the store looks
  again, so a repaired document is migrated then.
* **Only the old default moves.** A stored value equal to 0.15 (within
  :data:`app.advice.limits.EPSILON`) is rewritten; any other value -- 0.12,
  0.10, 0.20 -- is the user's and is left exactly as stored.
* **Recorded, once.** The record (previous value, new value, when, on what
  basis) lives in its own table, never in a ``RiskBudget`` field, where it
  would travel through ``PUT`` bodies and could be edited. ``migrated`` and
  ``not_applicable`` are terminal: a later start never rewrites again, so a
  user who sets 0.15 back on purpose keeps it. The marker sits in the same
  database as the settings, so restoring a pre-migration backup restores the
  absence of the marker too, and the migration (and its notice) runs again.
* **Never clamps.** Evaluation keeps reading the stored value as it is; there
  is no ``min(stored, 0.10)`` anywhere (``limits.py`` "不夾值").

The user-facing notice is :data:`CAP1_MIGRATION_NOTICES`. Its copy is drafted
by creative-lead and reviewed verbatim by risk-compliance; until then each slot
holds :data:`NOTICE_PENDING_RISK_REVIEW`, and
``tests/test_settings_migrations.py`` fails while any slot still does -- the
merge gate for this batch.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, Literal

from pydantic import BaseModel, ValidationError

from app.advice.limits import (
    DEFAULT_MAX_POSITION_WEIGHT,
    EPSILON,
    PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT,
    RiskBudget,
    format_reported_at,
)

logger = logging.getLogger(__name__)

#: Stable id of the cap-1 migration; the primary key of its record row.
CAP1_MIGRATION_ID: Final = "cap1-max-position-weight-0.15-to-0.10"

#: What the rewrite rests on, stored with the record for audit. An identifier,
#: not display copy: the notice says the "why" in words risk-compliance signed.
CAP1_MIGRATION_BASIS: Final = (
    "CEO #61/#62/#63 2026-10-26; "
    "work/reviews/2026-10-26-第1條上限下修審查-風控.md; "
    "work/reviews/2026-10-26-第1條上限下修提案-quant-researcher.md"
)

#: ``migrated`` -- the stored 0.15 was rewritten to 0.10 (terminal);
#: ``not_applicable`` -- nothing to rewrite: never saved, or saved with another
#: value (terminal); ``skipped`` -- a stored section failed validation, so
#: nothing was touched (retried on the next start).
Cap1MigrationStatus = Literal["migrated", "not_applicable", "skipped"]

_TERMINAL: Final[frozenset[str]] = frozenset({"migrated", "not_applicable"})

#: Where a notice is rendered; see :meth:`Cap1MigrationRecord.notice`.
NoticeSurface = Literal["settings", "risk_gauge"]

#: Placeholder for copy that has not been through risk-compliance yet. A slot of
#: :data:`CAP1_MIGRATION_NOTICES` still holding it fails the test suite.
NOTICE_PENDING_RISK_REVIEW: Final = "PENDING_RISK_REVIEW"

#: The S2 notice copy, the one place it lives (CEO #63; risk review 2026-10-26
#: S2 告知字面要點 1-9). Drafted by creative-lead, verbatim-reviewed by
#: risk-compliance; **dev does not write these sentences**.
#:
#: * ``migrated`` -- shown, standing, beside the field on the settings page,
#:   and on the risk gauge's cap-1 row for as long as the stored value is still
#:   the migrated one (at least until the user changes it themselves).
#: * ``skipped`` -- shown in the same two places while the record says the
#:   migration could not run because a stored section failed validation.
#:
#: Each slot is a ``str.format`` template. Available fields (any subset may be
#: used, none is required):
#:
#: * ``{previous_value}`` / ``{new_value}`` -- ``"0.15"`` / ``"0.10"``;
#: * ``{previous_percent}`` / ``{new_percent}`` -- ``"15%"`` / ``"10%"``;
#: * ``{recorded_at}`` -- when the record was written, local and labelled
#:   (:func:`app.advice.limits.format_reported_at`);
#: * ``{failed_sections}`` -- the section ids that failed, comma-separated
#:   (``skipped`` only; empty otherwise).
CAP1_MIGRATION_NOTICES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "migrated": NOTICE_PENDING_RISK_REVIEW,
        "skipped": NOTICE_PENDING_RISK_REVIEW,
    }
)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings_migrations (
    migration_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    previous_value REAL,
    new_value REAL,
    failed_sections TEXT NOT NULL,
    basis TEXT NOT NULL,
    recorded_at TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class Cap1MigrationRecord:
    """The stored outcome of the cap-1 migration."""

    status: Cap1MigrationStatus
    #: The stored value before the migration looked at it; ``None`` when there
    #: was no readable ``risk_budget`` row.
    previous_value: float | None
    #: The value written; ``None`` unless ``status == "migrated"``.
    new_value: float | None
    #: Section ids that failed validation; empty unless ``status == "skipped"``.
    failed_sections: tuple[str, ...]
    basis: str
    #: ISO 8601 UTC.
    recorded_at: str

    def notice(self, *, current_max_position_weight: float, surface: NoticeSurface) -> str | None:
        """The sentence a surface must show for this record, or ``None``.

        ``settings`` (beside the field) shows ``migrated`` and ``skipped``
        whenever the record says so: a standing record, never a toast. The
        ``risk_gauge`` cap-1 row shows ``skipped`` likewise, and ``migrated``
        only while the stored value is still the one the migration wrote --
        once the user sets a different value the change is theirs, and the
        settings page keeps the record. ``not_applicable`` shows nothing.
        """
        if self.status == "not_applicable":
            return None
        if (
            self.status == "migrated"
            and surface == "risk_gauge"
            and (
                self.new_value is None
                or not math.isclose(
                    current_max_position_weight, self.new_value, rel_tol=0.0, abs_tol=EPSILON
                )
            )
        ):
            return None
        return CAP1_MIGRATION_NOTICES[self.status].format(**self.notice_fields())

    def notice_fields(self) -> dict[str, str]:
        """The interpolation fields :data:`CAP1_MIGRATION_NOTICES` may use."""
        previous = (
            self.previous_value
            if self.previous_value is not None
            else PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT
        )
        new = self.new_value if self.new_value is not None else DEFAULT_MAX_POSITION_WEIGHT
        return {
            "previous_value": f"{previous:.2f}",
            "new_value": f"{new:.2f}",
            "previous_percent": f"{previous:.0%}",
            "new_percent": f"{new:.0%}",
            "recorded_at": format_reported_at(self.recorded_at),
            "failed_sections": ", ".join(self.failed_sections),
        }



def init_migrations_table(conn: sqlite3.Connection) -> None:
    """Create the record table if missing (DDL only, no transaction opened)."""
    conn.execute(_CREATE_TABLE_SQL)


def read_cap1_migration(conn: sqlite3.Connection) -> Cap1MigrationRecord | None:
    """The cap-1 record, or ``None`` if the migration has never run here."""
    row = conn.execute(
        "SELECT status, previous_value, new_value, failed_sections, basis, recorded_at "
        "FROM settings_migrations WHERE migration_id = ?",
        (CAP1_MIGRATION_ID,),
    ).fetchone()
    if row is None:
        return None
    status, previous_value, new_value, failed_sections, basis, recorded_at = row
    return Cap1MigrationRecord(
        status=status,
        previous_value=None if previous_value is None else float(previous_value),
        new_value=None if new_value is None else float(new_value),
        failed_sections=tuple(json.loads(failed_sections)),
        basis=str(basis),
        recorded_at=str(recorded_at),
    )


def migrate_cap1_default(
    conn: sqlite3.Connection,
    sections: Mapping[str, type[BaseModel]],
    *,
    now: datetime,
) -> Cap1MigrationRecord:
    """Run the cap-1 migration once; return the record in force afterwards.

    ``sections`` is the store's section -> model map, so "every section
    validates" means exactly what ``load`` means by it. Runs inside one
    ``BEGIN IMMEDIATE`` (the device ``app.kelly.store`` uses for its own
    migration): the backend and the scheduler may start against the same file
    at once, and the loser must find the winner's record, not repeat the work.
    Must be called outside any open transaction.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = read_cap1_migration(conn)
        if existing is not None and existing.status in _TERMINAL:
            conn.execute("COMMIT")
            return existing
        record = _decide_and_apply(conn, sections, now=now)
        _write_record(conn, record)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    _log(record)
    return record


def _decide_and_apply(
    conn: sqlite3.Connection,
    sections: Mapping[str, type[BaseModel]],
    *,
    now: datetime,
) -> Cap1MigrationRecord:
    stored = {
        str(section): str(payload)
        for section, payload in conn.execute("SELECT section, payload FROM app_settings")
    }
    moment = now.isoformat()

    failed = tuple(
        name
        for name, model in sections.items()
        if name in stored and not _validates(model, stored[name])
    )
    raw_budget = stored.get("risk_budget")
    previous = _stored_weight(raw_budget) if raw_budget is not None else None
    if failed:
        return Cap1MigrationRecord(
            status="skipped",
            previous_value=previous,
            new_value=None,
            failed_sections=failed,
            basis=CAP1_MIGRATION_BASIS,
            recorded_at=moment,
        )
    if (
        raw_budget is None
        or previous is None
        or not math.isclose(
            previous, PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT, rel_tol=0.0, abs_tol=EPSILON
        )
    ):
        # Never saved (the model default is already 0.10), or saved with a value
        # other than the old default: that value is the user's.
        return Cap1MigrationRecord(
            status="not_applicable",
            previous_value=previous,
            new_value=None,
            failed_sections=(),
            basis=CAP1_MIGRATION_BASIS,
            recorded_at=moment,
        )

    payload: dict[str, Any] = json.loads(raw_budget)
    payload["max_position_weight"] = DEFAULT_MAX_POSITION_WEIGHT
    # Re-validated before it is written: the rewritten section has to be one
    # ``load`` will accept, or the migration would itself be the corruption.
    RiskBudget.model_validate(payload)
    conn.execute(
        "UPDATE app_settings SET payload = ?, updated_at = ? WHERE section = 'risk_budget'",
        (json.dumps(payload, ensure_ascii=False), moment),
    )
    return Cap1MigrationRecord(
        status="migrated",
        previous_value=previous,
        new_value=DEFAULT_MAX_POSITION_WEIGHT,
        failed_sections=(),
        basis=CAP1_MIGRATION_BASIS,
        recorded_at=moment,
    )


def _validates(model: type[BaseModel], payload: str) -> bool:
    try:
        model.model_validate_json(payload)
    except ValidationError:
        return False
    return True


def _stored_weight(raw_budget: str) -> float | None:
    """``max_position_weight`` as stored, or ``None`` if it cannot be read."""
    try:
        payload = json.loads(raw_budget)
    except ValueError:
        return None
    value = payload.get("max_position_weight") if isinstance(payload, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _write_record(conn: sqlite3.Connection, record: Cap1MigrationRecord) -> None:
    conn.execute(
        """
        INSERT INTO settings_migrations (
            migration_id, status, previous_value, new_value, failed_sections, basis, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(migration_id) DO UPDATE SET
            status = excluded.status,
            previous_value = excluded.previous_value,
            new_value = excluded.new_value,
            failed_sections = excluded.failed_sections,
            basis = excluded.basis,
            recorded_at = excluded.recorded_at
        """,
        (
            CAP1_MIGRATION_ID,
            record.status,
            record.previous_value,
            record.new_value,
            json.dumps(list(record.failed_sections)),
            record.basis,
            record.recorded_at,
        ),
    )


def _log(record: Cap1MigrationRecord) -> None:
    if record.status == "migrated":
        logger.info(
            "settings migration %s: max_position_weight %s -> %s at %s",
            CAP1_MIGRATION_ID,
            record.previous_value,
            record.new_value,
            record.recorded_at,
        )
    elif record.status == "skipped":
        logger.warning(
            "settings migration %s skipped: stored sections failed validation: %s",
            CAP1_MIGRATION_ID,
            ", ".join(record.failed_sections),
        )
