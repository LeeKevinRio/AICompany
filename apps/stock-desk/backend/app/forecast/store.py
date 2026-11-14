"""Append-only writes and read-only queries of the forecast ledger core (ADR-0030 D-1 point 3, D-2).

The only module that INSERTs into the five tables of ``schema.py`` (K-4); it
never UPDATEs, DELETEs or REPLACEs (D-2 point 6). Every write:

* first checks the schema against ``sqlite_master`` and refuses when it is not
  exactly the D-2 schema (``schema.require_complete_schema``);
* runs in one ``BEGIN IMMEDIATE`` transaction, validation and insert together;
* takes every timestamp from the store clock -- ``started_at``,
  ``captured_at``, ``registered_at``, ``created_at``, ``ended_at`` are never
  parameters (S-2) -- and derives ``late`` and ``late_cutoff_at`` itself (D-3
  point 3, S-3). The clock is injectable for tests (``clock=``); it must
  return timezone-aware datetimes.

Record write validation (D-2 point 7; D-3 points 1, 2, 4, 6):

* the claim is a registered forward claim; scope, horizon and the version /
  hash columns are copied from its registry row, never passed in;
* the referenced snapshot exists, was captured no later than ``created_at``,
  holds only final bars (``app.data.session_calendar.is_final``) and ends on
  ``data_as_of`` (T is the latest final bar); ``inputs_max_fetched_at`` is
  derived from it;
* ``missing`` items are ``app.outlook.missing.MissingItem`` and re-validated;
  ``label = insufficient`` exactly when ``missing`` is non-empty, and then
  ``up_pct`` / ``down_pct`` are null;
* a labelled record's ``band_def`` must have no violation under
  ``app.forecast.band.labeled_snapshot_violations`` against the definition from
  ``app.forecast.definitions.get_definition`` -- whose ``definition_sha256``
  must equal the claim's -- else ``LabeledThresholdSnapshotIncompleteError``;
* all four baselines B1, B2, B6, B8 are present (S-8).

Connections are opened per operation with ``foreign_keys`` and
``recursive_triggers`` on: the latter makes an ``INSERT OR REPLACE`` that would
delete a ledger row fire the append-only DELETE trigger (SQLite skips delete
triggers on REPLACE otherwise). The store does not create the schema.

Read-only queries: ``first_record_at`` and "counts toward m" are the D-2 point
6 definitions; ``m_db`` counts the forward claims with at least one record
(m itself also needs the ``work/`` registrations and is not computed here);
``recording_claims`` is the latest-registered forward claim per
``(scope_kind, horizon)`` (D-6 CG-2); ``d_v`` and ``n_hat`` follow D-8 point 4.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal, get_args
from zoneinfo import ZoneInfo

from app.data.freshness import TW_POLICY, next_weekday
from app.data.session_calendar import is_final
from app.dirdef.definition import (
    DirectionDefinition,
    Horizon,
    definition_logic_sha256,
    definition_sha256,
)
from app.dirdef.hashing import canonical_json
from app.forecast.band import labeled_snapshot_violations
from app.forecast.canonical import (
    bars_json,
    canonical_price,
    canonical_timestamp,
    content_sha256,
    record_content_hash,
)
from app.forecast.claims import claim_id as make_claim_id
from app.forecast.definitions import get_definition
from app.forecast.errors import LabeledThresholdSnapshotIncompleteError, exception_class_name
from app.forecast.schema import (
    BAND_DEF_KEYS,
    BASELINE_KEYS,
    SCHEMA_VERSION,
    require_complete_schema,
)
from app.outlook.missing import MissingItem

Clock = Callable[[], datetime]

Label = Literal["bullish", "range", "bearish", "insufficient"]
RunOutcome = Literal["ok", "no_new_session", "inputs_not_ready", "gate_closed", "error"]
#: K-8: the one value, here and in the table CHECK.
ValidationStatus = Literal["unverified"]
VALIDATION_STATUS: Final[ValidationStatus] = "unverified"

#: The core scope (D-1 point 1).
SCOPE_KIND: Final = "market"
SCOPE_KEY: Final = "TAIEX"
CLAIM_KIND: Final = "forward"
RUN_TRIGGER: Final = "scheduled"
SERIES_KIND: Final = "index_bars"
#: The market whose finality rule the TAIEX snapshot bars are judged by.
SNAPSHOT_MARKET: Final = "TW"

#: Milliseconds a connection waits for a concurrent writer before failing.
BUSY_TIMEOUT_MS: Final = 5000

_CROCKFORD: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class ForecastStoreError(ValueError):
    """A write was refused by the store's validation; nothing was written."""


class LedgerInconsistentError(RuntimeError):
    """Stored rows contradict an invariant the store's writes guarantee."""


def system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ClaimRow:
    """The registry columns the queries return (not the stored bytes)."""

    claim_id: str
    scope_kind: str
    scope_key: str
    horizon: int
    kind: str
    rules_version: str
    rules_sha256: str
    definition_version: str
    definition_sha256: str
    replaces_claim_id: str | None
    registered_at: datetime


@dataclass(frozen=True)
class RunRow:
    """A ``forecast_run`` row with its ``forecast_run_end`` row, if any."""

    run_id: int
    started_at: datetime
    code_commit: str
    code_digest: str
    runtime_json: str
    outcome: str | None
    ended_at: datetime | None


_CLAIM_COLUMNS: Final = (
    "claim_id, scope_kind, scope_key, horizon, kind, rules_version, rules_sha256, "
    "definition_version, definition_sha256, replaces_claim_id, registered_at"
)


def _claim_row(row: Sequence[object]) -> ClaimRow:
    return ClaimRow(
        claim_id=str(row[0]),
        scope_kind=str(row[1]),
        scope_key=str(row[2]),
        horizon=int(str(row[3])),
        kind=str(row[4]),
        rules_version=str(row[5]),
        rules_sha256=str(row[6]),
        definition_version=str(row[7]),
        definition_sha256=str(row[8]),
        replaces_claim_id=None if row[9] is None else str(row[9]),
        registered_at=datetime.fromisoformat(str(row[10])),
    )


def late_cutoff_at(data_as_of: date) -> datetime:
    """T's next calendar day at 00:00:00 Asia/Taipei (D-3 point 3), in UTC."""
    local = datetime.combine(data_as_of + timedelta(days=1), time(0), ZoneInfo(TW_POLICY.timezone))
    return local.astimezone(UTC)


def valid_until_session_estimate(data_as_of: date, horizon: int) -> date:
    """T moved by ``horizon`` Monday-Friday days; exchange holidays are not modelled."""
    day = data_as_of
    for _ in range(horizon):
        day = next_weekday(day)
    return day


def new_ulid(at: datetime, random_bytes: Callable[[int], bytes] = secrets.token_bytes) -> str:
    """A ULID: 48-bit Unix milliseconds of ``at`` and 80 random bits, Crockford base32."""
    millis = int(at.timestamp() * 1000)
    if not 0 <= millis < 1 << 48:
        raise ValueError("timestamp outside the ULID range")
    value = (millis << 80) | int.from_bytes(random_bytes(10), "big")
    return "".join(_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5))


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.strip("0123456789abcdef"):
        raise ForecastStoreError(f"{name} must be 64 lower-case hex digits")
    return value


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ForecastStoreError(f"{name} must be a non-blank string")
    return value


def _require_bytes(name: str, value: object) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise ForecastStoreError(f"{name} must be non-empty bytes")
    return value


def _json_text(name: str, value: object) -> str:
    try:
        return canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise ForecastStoreError(f"{name} is not canonical JSON ({type(exc).__name__})") from None


class ForecastStore:
    """The ledger store on one SQLite file (the schema must already exist)."""

    def __init__(self, db_path: Path, *, clock: Clock = system_clock) -> None:
        self._db_path = Path(db_path)
        self._clock = clock

    # --- plumbing ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA recursive_triggers = ON")
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """One write transaction on a complete schema; rolled back on any error."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                require_complete_schema(conn)
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as conn:
            yield conn

    def _now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ForecastStoreError("the store clock must return a timezone-aware datetime")
        return now.astimezone(UTC)

    # --- writes --------------------------------------------------------------------

    def begin_run(
        self, *, code_commit: str, code_digest: str, runtime: Mapping[str, object]
    ) -> int:
        """Insert a ``forecast_run`` row (``trigger = scheduled``) and return its ``run_id``."""
        _require_text("code_commit", code_commit)
        _require_sha256("code_digest", code_digest)
        if not isinstance(runtime, Mapping):
            raise ForecastStoreError("runtime must be a mapping")
        runtime_json = _json_text("runtime", dict(runtime))
        with self._write() as conn:
            started_at = canonical_timestamp(self._now())
            cursor = conn.execute(
                'INSERT INTO forecast_run (started_at, "trigger", code_commit, code_digest,'
                " runtime_json, schema_version) VALUES (?, ?, ?, ?, ?, ?)",
                (started_at, RUN_TRIGGER, code_commit, code_digest, runtime_json, SCHEMA_VERSION),
            )
            run_id = cursor.lastrowid
        if run_id is None:  # pragma: no cover - sqlite3 always sets it after an INSERT
            raise LedgerInconsistentError("no run_id after insert")
        return run_id

    def end_run(
        self,
        run_id: int,
        *,
        outcome: RunOutcome,
        candidate_t: date | None,
        records_written: int,
        error: BaseException | None = None,
    ) -> None:
        """Insert the run's ``forecast_run_end`` row.

        ``error_class`` is taken from ``error`` through ``exception_class_name`` only.
        """
        if outcome not in get_args(RunOutcome):
            raise ForecastStoreError("outcome is outside its closed list")
        if isinstance(records_written, bool) or not isinstance(records_written, int):
            raise ForecastStoreError("records_written must be an int")
        if candidate_t is not None and (
            isinstance(candidate_t, datetime) or not isinstance(candidate_t, date)
        ):
            raise ForecastStoreError("candidate_t must be a date")
        error_class = None if error is None else exception_class_name(error)
        with self._write() as conn:
            self._require_open_run(conn, run_id)
            conn.execute(
                "INSERT INTO forecast_run_end (run_id, outcome, candidate_t, records_written,"
                " error_class, ended_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    outcome,
                    None if candidate_t is None else candidate_t.isoformat(),
                    records_written,
                    error_class,
                    canonical_timestamp(self._now()),
                ),
            )

    def put_input_series(
        self,
        *,
        bars: Sequence[Mapping[str, object]],
        source: str,
        source_status: str,
        staleness_minutes: int | None,
        reason: str | None,
        dropped_rows: Sequence[Mapping[str, object]] | None,
        raw_timestamp_available: bool,
    ) -> str:
        """Store a snapshot once per content and return its ``content_sha256``.

        A snapshot whose content is already stored is not written again (the
        existing row, with its first ``captured_at``, stays as it is).
        """
        text = bars_json(bars)
        digest = content_sha256(bars)
        _require_text("source", source)
        _require_text("source_status", source_status)
        if reason is not None:
            _require_text("reason", reason)
        if staleness_minutes is not None and (
            isinstance(staleness_minutes, bool) or not isinstance(staleness_minutes, int)
        ):
            raise ForecastStoreError("staleness_minutes must be an int or None")
        if not isinstance(raw_timestamp_available, bool):
            raise ForecastStoreError("raw_timestamp_available must be a bool")
        dropped = None if dropped_rows is None else _json_text("dropped_rows", list(dropped_rows))
        with self._write() as conn:
            exists = conn.execute(
                "SELECT 1 FROM forecast_input_series WHERE content_sha256 = ?", (digest,)
            ).fetchone()
            if exists is None:
                conn.execute(
                    "INSERT INTO forecast_input_series (content_sha256, series_kind, source,"
                    " source_status, staleness_minutes, reason, dropped_rows_json,"
                    " raw_timestamp_available, bars_json, captured_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        digest,
                        SERIES_KIND,
                        source,
                        source_status,
                        staleness_minutes,
                        reason,
                        dropped,
                        int(raw_timestamp_available),
                        text,
                        canonical_timestamp(self._now()),
                    ),
                )
        return digest

    def register_claim(
        self,
        *,
        horizon: Horizon,
        rules_version: str,
        rules_bytes: bytes,
        rules_logic_sha256: str,
        definition: DirectionDefinition,
        frozen_commit: str,
        prereg_doc_path: str,
        prereg_doc_blob: bytes,
        review_refs: str,
        replaces_claim_id: str | None,
        replace_reason: str | None,
        provisional_results_seen: bool,
    ) -> str:
        """Register a forward claim of the core scope and return its ``claim_id``.

        ``claim_id``, ``rules_sha256``, ``definition_json`` and both definition
        hashes are derived here; ``registered_at`` comes from the store clock
        and must be later than every earlier registration, so registration
        order is the time order. A replacement must name an existing forward
        claim of the same scope and horizon and give a reason (D-1 point 2).
        """
        if not isinstance(definition, DirectionDefinition):
            raise ForecastStoreError("definition must be a DirectionDefinition")
        try:
            new_id = make_claim_id(
                scope_kind=SCOPE_KIND,
                horizon=horizon,
                rules_version=rules_version,
                definition_version=definition.definition_version,
                kind=CLAIM_KIND,
            )
        except ValueError as exc:
            raise ForecastStoreError(str(exc)) from None
        rules = _require_bytes("rules_bytes", rules_bytes)
        _require_sha256("rules_logic_sha256", rules_logic_sha256)
        _require_text("frozen_commit", frozen_commit)
        _require_text("prereg_doc_path", prereg_doc_path)
        _require_bytes("prereg_doc_blob", prereg_doc_blob)
        _require_text("review_refs", review_refs)
        if (replaces_claim_id is None) != (replace_reason is None):
            raise ForecastStoreError("replace_reason is required exactly when replacing a claim")
        if replace_reason is not None:
            _require_text("replace_reason", replace_reason)
        if not isinstance(provisional_results_seen, bool):
            raise ForecastStoreError("provisional_results_seen must be a bool")
        definition_json = canonical_json(definition.model_dump(mode="json"))
        with self._write() as conn:
            registered_at = self._now()
            last = conn.execute("SELECT max(registered_at) FROM forecast_claim_registry").fetchone()
            if last[0] is not None and canonical_timestamp(registered_at) <= str(last[0]):
                raise ForecastStoreError("registered_at must be later than every registration")
            if replaces_claim_id is not None:
                replaced = self._claim(conn, replaces_claim_id)
                if replaced is None or replaced.kind != CLAIM_KIND:
                    raise ForecastStoreError("replaces_claim_id is not a registered forward claim")
                if replaced.horizon != horizon:
                    raise ForecastStoreError("a replacement keeps the scope and horizon")
            conn.execute(
                "INSERT INTO forecast_claim_registry (claim_id, scope_kind, scope_key, horizon,"
                " kind, rules_version, rules_sha256, rules_logic_sha256, rules_bytes,"
                " definition_version, definition_sha256, definition_logic_sha256,"
                " definition_json, frozen_commit, prereg_doc_path, prereg_doc_blob, review_refs,"
                " replaces_claim_id, replace_reason, provisional_results_seen, registered_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id,
                    SCOPE_KIND,
                    SCOPE_KEY,
                    horizon,
                    CLAIM_KIND,
                    rules_version,
                    hashlib.sha256(rules).hexdigest(),
                    rules_logic_sha256,
                    rules,
                    definition.definition_version,
                    definition_sha256(definition),
                    definition_logic_sha256(definition),
                    definition_json,
                    frozen_commit,
                    prereg_doc_path,
                    prereg_doc_blob,
                    review_refs,
                    replaces_claim_id,
                    replace_reason,
                    int(provisional_results_seen),
                    canonical_timestamp(registered_at),
                ),
            )
        return new_id

    def write_record(
        self,
        *,
        run_id: int,
        claim_id: str,
        data_as_of: date,
        label: Label,
        range_basis: str | None,
        missing: Sequence[MissingItem],
        evidence: Mapping[str, object],
        band_def: Mapping[str, object],
        base_close: Decimal | int | str,
        baseline_predictions: Mapping[str, object],
        input_series_sha256: str,
    ) -> str:
        """Validate and insert one ``forecast_record``; return its ``forecast_id``."""
        if isinstance(data_as_of, datetime) or not isinstance(data_as_of, date):
            raise ForecastStoreError("data_as_of must be a date")
        if label not in get_args(Label):
            raise ForecastStoreError("label is outside its closed list")
        if range_basis is not None:
            _require_text("range_basis", range_basis)
        missing_json = self._missing_json(missing)
        if (label == "insufficient") != bool(missing):
            raise ForecastStoreError("label is insufficient exactly when missing is non-empty")
        band = self._band_def(band_def)
        band_json = _json_text("band_def", band)
        if label == "insufficient" and (band["up_pct"] is not None or band["down_pct"] is not None):
            raise ForecastStoreError("an insufficient record has null up_pct and down_pct")
        if not isinstance(evidence, Mapping):
            raise ForecastStoreError("evidence must be a mapping")
        evidence_json = _json_text("evidence", dict(evidence))
        if not isinstance(baseline_predictions, Mapping):
            raise ForecastStoreError("baseline_predictions must be a mapping")
        absent = [key for key in BASELINE_KEYS if key not in baseline_predictions]
        if absent:
            raise ForecastStoreError(f"baselines missing: {absent}")
        baselines_json = _json_text("baseline_predictions", dict(baseline_predictions))
        try:
            close = canonical_price(base_close)
        except ValueError as exc:
            raise ForecastStoreError(f"base_close: {exc}") from None
        _require_sha256("input_series_sha256", input_series_sha256)

        with self._write() as conn:
            created = self._now()
            self._require_open_run(conn, run_id)
            claim = self._claim(conn, claim_id)
            if claim is None or claim.kind != CLAIM_KIND:
                raise ForecastStoreError("claim_id is not a registered forward claim")
            max_fetched_at = self._check_snapshot(conn, input_series_sha256, data_as_of, created)
            if label != "insufficient":
                self._check_band(band, claim, data_as_of)
            cutoff = late_cutoff_at(data_as_of)
            columns: dict[str, object] = {
                "forecast_id": new_ulid(created),
                "run_id": run_id,
                "claim_id": claim.claim_id,
                "scope_kind": claim.scope_kind,
                "scope_key": claim.scope_key,
                "horizon": claim.horizon,
                "data_as_of": data_as_of.isoformat(),
                "definition_version": claim.definition_version,
                "definition_sha256": claim.definition_sha256,
                "rules_version": claim.rules_version,
                "rules_sha256": claim.rules_sha256,
                "label": label,
                "range_basis": range_basis,
                "missing_json": missing_json,
                "evidence_json": evidence_json,
                "band_def": band_json,
                "base_close": close,
                "baseline_predictions_json": baselines_json,
                "input_series_sha256": input_series_sha256,
                "inputs_max_fetched_at": max_fetched_at,
                "created_at": canonical_timestamp(created),
                "late": int(created >= cutoff),
                "late_cutoff_at": canonical_timestamp(cutoff),
                "valid_until_session_estimate": valid_until_session_estimate(
                    data_as_of, claim.horizon
                ).isoformat(),
                "validation_status": VALIDATION_STATUS,
            }
            columns["content_hash"] = record_content_hash(columns)
            names = ", ".join(columns)
            marks = ", ".join("?" for _ in columns)
            conn.execute(
                f"INSERT INTO forecast_record ({names}) VALUES ({marks})", tuple(columns.values())
            )
        return str(columns["forecast_id"])

    # --- write validation helpers ---------------------------------------------------

    @staticmethod
    def _require_open_run(conn: sqlite3.Connection, run_id: int) -> None:
        if isinstance(run_id, bool) or not isinstance(run_id, int):
            raise ForecastStoreError("run_id must be an int")
        if (
            conn.execute("SELECT 1 FROM forecast_run WHERE run_id = ?", (run_id,)).fetchone()
            is None
        ):
            raise ForecastStoreError("run_id is not a started run")
        ended = conn.execute(
            "SELECT 1 FROM forecast_run_end WHERE run_id = ?", (run_id,)
        ).fetchone()
        if ended is not None:
            raise ForecastStoreError("run_id has already ended")

    @staticmethod
    def _missing_json(missing: Sequence[MissingItem]) -> str:
        if isinstance(missing, (str, bytes)) or not isinstance(missing, Sequence):
            raise ForecastStoreError("missing must be a sequence of MissingItem")
        items: list[object] = []
        for item in missing:
            if not isinstance(item, MissingItem):
                raise ForecastStoreError("missing must hold MissingItem values only")
            dumped = item.model_dump(mode="json")
            # Re-validate: a model_construct()-built item skipped its invariants.
            try:
                MissingItem.model_validate_json(json.dumps(dumped))
            except ValueError as exc:
                raise ForecastStoreError(f"missing item rejected ({type(exc).__name__})") from None
            items.append(dumped)
        return _json_text("missing", items)

    @staticmethod
    def _band_def(band_def: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(band_def, Mapping):
            raise ForecastStoreError("band_def must be a mapping")
        if set(band_def) != set(BAND_DEF_KEYS):
            raise ForecastStoreError(f"band_def keys must be exactly {list(BAND_DEF_KEYS)}")
        return {key: band_def[key] for key in BAND_DEF_KEYS}

    @staticmethod
    def _check_band(band: Mapping[str, object], claim: ClaimRow, data_as_of: date) -> None:
        definition = get_definition(claim.definition_version)
        if definition_sha256(definition) != claim.definition_sha256:
            raise ForecastStoreError("published definition differs from the claim's definition")
        violations = labeled_snapshot_violations(band, horizon=claim.horizon, definition=definition)
        if violations:
            raise LabeledThresholdSnapshotIncompleteError(
                source="record",
                violations=violations,
                affected_forecast_count=1,
                data_as_of_from=data_as_of,
                data_as_of_to=data_as_of,
            )

    @staticmethod
    def _check_snapshot(
        conn: sqlite3.Connection, digest: str, data_as_of: date, created: datetime
    ) -> str:
        """D-3 points 1, 2 and 4 on the stored snapshot; returns ``inputs_max_fetched_at``."""
        row = conn.execute(
            "SELECT bars_json, captured_at FROM forecast_input_series WHERE content_sha256 = ?",
            (digest,),
        ).fetchone()
        if row is None:
            raise ForecastStoreError("input_series_sha256 is not a stored snapshot")
        if datetime.fromisoformat(str(row[1])) > created:
            raise ForecastStoreError("the snapshot was captured after created_at")
        bars = _stored_bars(str(row[0]))
        if bars[-1].session_date != data_as_of:
            raise ForecastStoreError("data_as_of is not the snapshot's latest session")
        if not all(bar.final for bar in bars):
            raise ForecastStoreError("the snapshot holds a bar that is not final")
        return canonical_timestamp(max(bar.fetched_at for bar in bars))

    # --- reads ---------------------------------------------------------------------

    @staticmethod
    def _claim(conn: sqlite3.Connection, claim_id: str) -> ClaimRow | None:
        row = conn.execute(
            f"SELECT {_CLAIM_COLUMNS} FROM forecast_claim_registry WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        return None if row is None else _claim_row(row)

    def claim(self, claim_id: str) -> ClaimRow | None:
        with self._read() as conn:
            return self._claim(conn, claim_id)

    def forward_claims(self) -> list[ClaimRow]:
        """Every forward claim in registration order."""
        with self._read() as conn:
            rows = conn.execute(
                f"SELECT {_CLAIM_COLUMNS} FROM forecast_claim_registry WHERE kind = ?"
                " ORDER BY registered_at, rowid",
                (CLAIM_KIND,),
            ).fetchall()
        return [_claim_row(row) for row in rows]

    def recording_claims(self) -> dict[tuple[str, int], ClaimRow]:
        """The last-registered forward claim of each ``(scope_kind, horizon)`` (D-6 CG-2)."""
        latest: dict[tuple[str, int], ClaimRow] = {}
        for claim in self.forward_claims():
            latest[(claim.scope_kind, claim.horizon)] = claim
        return latest

    def first_record_at(self, claim_id: str) -> datetime | None:
        """``created_at`` of the claim's first record, ``late`` or not (D-2 point 6)."""
        with self._read() as conn:
            row = conn.execute(
                "SELECT min(created_at) FROM forecast_record WHERE claim_id = ?", (claim_id,)
            ).fetchone()
        return None if row[0] is None else datetime.fromisoformat(str(row[0]))

    def counts_toward_m(self, claim_id: str) -> bool:
        """Whether the claim has at least one ``forecast_record`` (D-2 point 6)."""
        return self.first_record_at(claim_id) is not None

    def m_db(self) -> int:
        """The forward claims with at least one record (D-2 point 6); m also needs ``work/``."""
        with self._read() as conn:
            row = conn.execute(
                "SELECT count(DISTINCT r.claim_id) FROM forecast_record r"
                " JOIN forecast_claim_registry c ON c.claim_id = r.claim_id WHERE c.kind = ?",
                (CLAIM_KIND,),
            ).fetchone()
        return int(row[0])

    def d_v(self, claim_id: str) -> date | None:
        """T of the claim's first ``late = 0`` record (D-8 point 4)."""
        with self._read() as conn:
            row = conn.execute(
                "SELECT min(data_as_of) FROM forecast_record WHERE claim_id = ? AND late = 0",
                (claim_id,),
            ).fetchone()
        return None if row[0] is None else date.fromisoformat(str(row[0]))

    def final_sessions(self) -> list[date]:
        """The union of final session dates over every stored snapshot, ascending."""
        with self._read() as conn:
            rows = conn.execute("SELECT bars_json FROM forecast_input_series").fetchall()
        sessions = {
            bar.session_date for row in rows for bar in _stored_bars(str(row[0])) if bar.final
        }
        return sorted(sessions)

    def n_hat(self, claim_id: str) -> int:
        """The review trigger count n-hat of D-8 point 4 (T1); an approximate upper bound of n.

        Over the union of final sessions of every snapshot, grid points are
        D_v and every h-th session after it; a grid point counts when the claim
        has a ``late = 0`` record with that T and the h-th final session after
        it has appeared. Nothing is deducted (insufficient, void, unavailable
        baselines, PIT violations).
        """
        claim = self.claim(claim_id)
        if claim is None:
            raise ForecastStoreError("claim_id is not registered")
        start = self.d_v(claim_id)
        if start is None:
            return 0
        sessions = self.final_sessions()
        if start not in sessions:
            raise LedgerInconsistentError("D_v is not a final session of any snapshot")
        with self._read() as conn:
            rows = conn.execute(
                "SELECT data_as_of FROM forecast_record WHERE claim_id = ? AND late = 0",
                (claim_id,),
            ).fetchall()
        on_time = {date.fromisoformat(str(row[0])) for row in rows}
        h = claim.horizon
        first = sessions.index(start)
        return sum(
            1
            for index in range(first, len(sessions), h)
            if sessions[index] in on_time and index + h < len(sessions)
        )

    def latest_run(self) -> RunRow | None:
        """The run with the highest ``run_id`` and its end row, if any."""
        with self._read() as conn:
            row = conn.execute(
                "SELECT r.run_id, r.started_at, r.code_commit, r.code_digest, r.runtime_json,"
                " e.outcome, e.ended_at FROM forecast_run r"
                " LEFT JOIN forecast_run_end e ON e.run_id = r.run_id"
                " ORDER BY r.run_id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return RunRow(
            run_id=int(row[0]),
            started_at=datetime.fromisoformat(str(row[1])),
            code_commit=str(row[2]),
            code_digest=str(row[3]),
            runtime_json=str(row[4]),
            outcome=None if row[5] is None else str(row[5]),
            ended_at=None if row[6] is None else datetime.fromisoformat(str(row[6])),
        )


@dataclass(frozen=True)
class _StoredBar:
    session_date: date
    fetched_at: datetime
    final: bool


def _stored_bars(text: str) -> list[_StoredBar]:
    """The dates, ``fetched_at`` and finality of a stored snapshot's bars."""
    out: list[_StoredBar] = []
    for bar in json.loads(text):
        session = date.fromisoformat(bar["session_date"])
        as_of = datetime.fromisoformat(bar["as_of"])
        fetched_at = datetime.fromisoformat(bar["fetched_at"])
        out.append(
            _StoredBar(
                session_date=session,
                fetched_at=fetched_at,
                final=is_final(SNAPSHOT_MARKET, session, as_of, fetched_at),
            )
        )
    return out
