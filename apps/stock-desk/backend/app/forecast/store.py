"""Append-only writes and read-only queries of the forecast ledger core (ADR-0030 D-1 point 3, D-2).

The only module that INSERTs into the five tables of ``schema.py`` (K-4); it
never UPDATEs, DELETEs or REPLACEs (D-2 point 6). Every write:

* first checks the schema against ``sqlite_master`` and refuses when it is not
  exactly the D-2 schema (``schema.require_complete_schema``);
* runs in one ``BEGIN IMMEDIATE`` transaction, validation and insert together;
* takes every timestamp from the store clock -- ``started_at``,
  ``captured_at``, ``registered_at``, ``created_at``, ``ended_at`` are never
  parameters (S-2) -- and derives ``late`` and ``late_cutoff_at`` itself (D-3
  point 3, S-3; the cutoff rule is ``app.outlook.inputs.late_cutoff_at``, the
  one definition the computation's ``E-PIT-UNVERIFIED`` check also uses). The
  clock is injectable for tests (``clock=``); it must return timezone-aware
  datetimes.

Record write validation (D-2 point 7; D-3 points 1, 2, 4, 6):

* the claim is a registered forward claim; scope, horizon and the version /
  hash columns are copied from its registry row, never passed in;
* the referenced snapshot exists, was captured no later than ``created_at``,
  has no bar whose ``fetched_at`` or ``as_of`` is later than its
  ``captured_at`` (point in time), holds only final bars
  (``app.data.session_calendar.is_final``) and ends on ``data_as_of`` (T is
  the latest final bar); ``inputs_max_fetched_at`` is derived from it;
* ``missing`` items are ``app.outlook.missing.MissingItem`` and re-validated;
  ``label = insufficient`` exactly when ``missing`` is non-empty, and then
  ``up_pct`` / ``down_pct`` are null;
* an insufficient record's ``band_def.sigma_d`` is what
  ``app.outlook.volatility.sigma_d`` returned: null exactly when ``missing``
  holds an ``E-VOL-*`` item, and when it is not null the snapshot must have no
  violation under ``labeled_snapshot_violations`` (ADR-0030 freeze pack Q3);
* a labelled record's ``band_def`` must have no violation under
  ``app.forecast.band.labeled_snapshot_violations`` against the definition from
  ``app.forecast.definitions.get_definition`` -- whose ``definition_sha256``
  must equal the claim's -- else ``LabeledThresholdSnapshotIncompleteError``;
* all four baselines B1, B2, B6, B8 are present (S-8).

A run's snapshot and records (ADR-0030 supplement 3 (revised) point 7):
``write_run_records`` validates and inserts the snapshot and every record of
the run in one transaction, so a failure of any one of them leaves none of
them; it is the recorder's only write of a run's ledger rows (AST).
``put_input_series`` and ``write_record`` are the one-row forms of the same
validation and INSERT.

Claim registration (ADR-0030 supplement 7): ``register_claim`` and
``bootstrap`` share one validation (``_prepare_claim``, which reads no ledger)
and one in-transaction step (``_insert_claim``: store clock, registration
order, chain rule, INSERT). ``provisional_results_seen`` is the read-only query
of the post-registration check.

Connections are opened per operation with ``foreign_keys`` and
``recursive_triggers`` on. The ``{table}_no_replace`` BEFORE INSERT triggers
refuse an ``INSERT OR REPLACE`` on any connection (ADR-0030 supplement 1);
``recursive_triggers`` is the second layer: it makes the delete a REPLACE would
perform fire the append-only DELETE trigger (SQLite skips delete triggers on
REPLACE otherwise). The store creates the schema in one place only:
``bootstrap`` creates every ledger object and registers the two core claims in
one transaction (``_write(fresh=True)``; ADR-0030 supplement 4 point 2,
supplement 7); every other write requires the complete schema and refuses
otherwise, creating nothing. Every read-only
query runs on a ``query_only`` connection (``_read``), so a write on it fails
in SQLite itself; ``_connect`` -- the write-path connection -- is opened only
by ``_write`` (ADR-0030 supplement 3 (revised) point 9).

Read-only queries: ``first_record_at`` and "counts toward m" are the D-2 point
6 definitions; ``m_db`` counts the forward claims with at least one record
(m itself also needs the ``work/`` registrations and is not computed here);
``recording_claims`` is the latest-registered forward claim per
``(scope_kind, horizon)`` (D-6 CG-2); ``d_v`` and ``n_hat`` follow D-8 point 4,
over the one grid definition ``phase0_grid`` (which also gives the F-2
phase-0 grid point loss count), and ``review_trigger`` derives d_1 and whether
T1 or T2 holds (D-8 point 4: only from this module's read-only queries);
``f2_status`` derives the counts and the verdict of failure condition F-2's
first sentence over its rolling 20-weekday windows (supplement 5 point 1:
only here); ``grid_loss_status`` derives the second sentence's G, L and
verdict over the phase-0 grid (supplement 9 point 5: only here).
For the operator report (``report.py``): ``registered_material`` (the stored
rule bytes and definition JSON, D-5 points 2-3), ``runs``,
``snapshot_digests``, ``on_time_sessions`` and ``ledger_schema_status``.
For the recorder (``recorder.py``): ``now`` (the store clock, the recorder's
only clock), ``latest_run_before``, ``has_record``, ``stored_records``,
``snapshot`` and ``expected_record_columns`` -- the last one derives the
``content_hash`` columns exactly as ``write_record`` does (``_record_columns``,
one definition), so the D-5 point 6 recomputation compares like with like.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import secrets
import sqlite3
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
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
    n_min,
)
from app.dirdef.hashing import canonical_json
from app.forecast import claims as claim_keys  # a module import: claims.py imports this module
from app.forecast.band import labeled_snapshot_violations
from app.forecast.canonical import (
    bars_json,
    canonical_price,
    canonical_timestamp,
    content_sha256,
    record_content_hash,
)
from app.forecast.definitions import get_definition
from app.forecast.errors import (
    LabeledThresholdSnapshotIncompleteError,
    ThresholdViolation,
    exception_class_name,
)
from app.forecast.schema import (
    BAND_DEF_KEYS,
    BASELINE_KEYS,
    SCHEMA_VERSION,
    SchemaStatus,
    create_objects,
    require_complete_schema,
    schema_status,
)
from app.outlook.inputs import late_cutoff_at as late_cutoff_at  # re-exported (tests)
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

#: The code prefix of ``app.outlook.volatility``'s missing codes (``E-VOL-SHORT``,
#: ``E-VOL-DEGENERATE``): exactly the cases where ``sigma_d`` returns no value.
VOLATILITY_MISSING_PREFIX: Final = "E-VOL-"

#: Milliseconds a connection waits for a concurrent writer before failing.
BUSY_TIMEOUT_MS: Final = 5000
#: ``bootstrap``: how long the store clock is re-read for a later ``registered_at``
#: (supplement 7 point 4), and the pause between two reads.
CLOCK_WAIT_SECONDS: Final = 1.0
CLOCK_REREAD_INTERVAL_SECONDS: Final = 0.001

_CROCKFORD: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: The well-formed snapshot reference ``check_record_content`` validates with: the
#: content checks do not depend on which snapshot a record will reference.
_CONTENT_ONLY_SNAPSHOT: Final = "0" * 64


class ForecastStoreError(ValueError):
    """A write was refused by the store's validation; nothing was written."""


class LedgerInconsistentError(RuntimeError):
    """Stored rows contradict an invariant the store's writes guarantee."""


def system_clock() -> datetime:
    return datetime.now(UTC)


def _open_connection(db_path: Path) -> sqlite3.Connection:
    """A connection with the store's pragmas; ``_connect`` and ``_read`` are its only callers."""
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA recursive_triggers = ON")
    return conn


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
    rules_logic_sha256: str
    definition_version: str
    definition_sha256: str
    definition_logic_sha256: str
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


_RUN_SELECT: Final = (
    "SELECT r.run_id, r.started_at, r.code_commit, r.code_digest, r.runtime_json,"
    " e.outcome, e.ended_at FROM forecast_run r"
    " LEFT JOIN forecast_run_end e ON e.run_id = r.run_id"
)


def _run_row(row: Sequence[object]) -> RunRow:
    return RunRow(
        run_id=int(str(row[0])),
        started_at=datetime.fromisoformat(str(row[1])),
        code_commit=str(row[2]),
        code_digest=str(row[3]),
        runtime_json=str(row[4]),
        outcome=None if row[5] is None else str(row[5]),
        ended_at=None if row[6] is None else datetime.fromisoformat(str(row[6])),
    )


@dataclass(frozen=True)
class StoredSnapshot:
    """A ``forecast_input_series`` row as stored; ``bars`` are the parsed ``bars_json``."""

    content_sha256: str
    bars: tuple[Mapping[str, object], ...]
    source: str
    source_status: str
    staleness_minutes: int | None
    reason: str | None
    raw_timestamp_available: bool
    captured_at: datetime


@dataclass(frozen=True)
class _RecordContent:
    """The validated, normalised content of one record, before any ledger read."""

    data_as_of: date
    label: str
    range_basis: str | None
    missing_json: str
    band: dict[str, object]
    band_json: str
    evidence_json: str
    base_close: str
    baselines_json: str
    input_series_sha256: str


@dataclass(frozen=True)
class SnapshotInput:
    """The arguments of :meth:`ForecastStore.put_input_series`, for a batch write."""

    bars: Sequence[Mapping[str, object]]
    source: str
    source_status: str
    staleness_minutes: int | None
    reason: str | None
    dropped_rows: Sequence[Mapping[str, object]] | None
    raw_timestamp_available: bool


@dataclass(frozen=True)
class RecordInput:
    """The content arguments of :meth:`ForecastStore.write_record`, for a batch write.

    No ``run_id`` and no ``input_series_sha256``: the batch supplies both.
    """

    claim_id: str
    data_as_of: date
    label: Label
    range_basis: str | None
    missing: Sequence[MissingItem]
    evidence: Mapping[str, object]
    band_def: Mapping[str, object]
    base_close: Decimal | int | str
    baseline_predictions: Mapping[str, object]


@dataclass(frozen=True)
class _SeriesRow:
    """A validated snapshot, ready for its INSERT."""

    digest: str
    bars_json: str
    source: str
    source_status: str
    staleness_minutes: int | None
    reason: str | None
    dropped_json: str | None
    raw_timestamp_available: bool


def _series_row(snapshot: SnapshotInput) -> _SeriesRow:
    """Validate and normalise a snapshot (no ledger read)."""
    if not isinstance(snapshot, SnapshotInput):
        raise ForecastStoreError("snapshot must be a SnapshotInput")
    text = bars_json(snapshot.bars)
    digest = content_sha256(snapshot.bars)
    _require_text("source", snapshot.source)
    _require_text("source_status", snapshot.source_status)
    if snapshot.reason is not None:
        _require_text("reason", snapshot.reason)
    staleness = snapshot.staleness_minutes
    if staleness is not None and (isinstance(staleness, bool) or not isinstance(staleness, int)):
        raise ForecastStoreError("staleness_minutes must be an int or None")
    if not isinstance(snapshot.raw_timestamp_available, bool):
        raise ForecastStoreError("raw_timestamp_available must be a bool")
    dropped_rows = snapshot.dropped_rows
    dropped = None if dropped_rows is None else _json_text("dropped_rows", list(dropped_rows))
    return _SeriesRow(
        digest=digest,
        bars_json=text,
        source=snapshot.source,
        source_status=snapshot.source_status,
        staleness_minutes=staleness,
        reason=snapshot.reason,
        dropped_json=dropped,
        raw_timestamp_available=snapshot.raw_timestamp_available,
    )


_CLAIM_COLUMNS: Final = (
    "claim_id, scope_kind, scope_key, horizon, kind, rules_version, rules_sha256, "
    "definition_version, definition_sha256, replaces_claim_id, registered_at, "
    "rules_logic_sha256, definition_logic_sha256"
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
        rules_logic_sha256=str(row[11]),
        definition_logic_sha256=str(row[12]),
    )


def replacement_violations(forward: Sequence[ClaimRow]) -> list[str]:
    """The replacement chain rule over the forward claims in registration order.

    ADR-0030 supplement 3 (revised) point 6: a ``replaces_claim_id`` names a
    forward claim registered earlier with the same ``(scope_kind, scope_key,
    horizon)``, and no claim is replaced more than once. With CG-2's "every
    other forward claim is replaced by a later one" this makes each key one
    linear chain ending in its recording claim. The one definition: the
    registration (:meth:`ForecastStore.register_claim`) refuses a row that
    breaks it, the recorder's CG-2 check closes the gate on a registry that
    breaks it. An empty list means the rule holds.
    """
    earlier: dict[str, ClaimRow] = {}
    replaced: set[str] = set()
    found: list[str] = []
    for claim in forward:
        target_id = claim.replaces_claim_id
        if target_id is not None:
            target = earlier.get(target_id)
            if target is None:
                found.append(
                    f"{claim.claim_id}: replaces_claim_id names no forward claim registered"
                    " before it"
                )
            elif (target.scope_kind, target.scope_key, target.horizon) != (
                claim.scope_kind,
                claim.scope_key,
                claim.horizon,
            ):
                found.append(
                    f"{claim.claim_id}: a replacement keeps the scope and horizon of the claim"
                    " it replaces"
                )
            if target_id in replaced:
                found.append(f"{target_id}: replaced more than once")
            replaced.add(target_id)
        earlier[claim.claim_id] = claim
    return found


_TAIPEI: Final = ZoneInfo(TW_POLICY.timezone)


def _taipei_date(moment: datetime) -> date:
    """The Asia/Taipei calendar date of an aware timestamp."""
    return moment.astimezone(_TAIPEI).date()


def _weekdays_after(day: date, count: int) -> date:
    """``day`` moved by ``count`` Monday-Friday days; exchange holidays are not modelled."""
    for _ in range(count):
        day = next_weekday(day)
    return day


def valid_until_session_estimate(data_as_of: date, horizon: int) -> date:
    """T moved by ``horizon`` Monday-Friday days; exchange holidays are not modelled."""
    return _weekdays_after(data_as_of, horizon)


@dataclass(frozen=True)
class Phase0Grid:
    """The phase-0 grid of one claim (D-8 point 4): the one definition of its points.

    ``sessions`` is the union of final sessions of every snapshot, ``first``
    the index of D_v in it; the points are ``sessions[first::horizon]``.
    """

    horizon: int
    sessions: tuple[date, ...]
    first: int
    on_time: frozenset[date]

    @property
    def points(self) -> tuple[date, ...]:
        return self.sessions[self.first :: self.horizon]

    @property
    def n_hat(self) -> int:
        """Points with a ``late = 0`` record whose h-th final session after it has appeared."""
        return sum(
            1
            for index in range(self.first, len(self.sessions), self.horizon)
            if self.sessions[index] in self.on_time and index + self.horizon < len(self.sessions)
        )

    @property
    def lost(self) -> int:
        """Points without a ``late = 0`` record (the F-2 phase-0 grid point loss count)."""
        return sum(1 for point in self.points if point not in self.on_time)


#: D-8 point 4 (T2): the review starts this many calendar days before d_1.
REVIEW_T2_DAYS: Final = 90


@dataclass(frozen=True)
class ReviewTrigger:
    """D-8 point 4 for one claim, as :meth:`ForecastStore.review_trigger` derives it."""

    claim_id: str
    horizon: int
    c1: int
    d_v: date | None
    n_hat: int
    d_1: date | None
    t1: bool
    t2: bool

    @property
    def triggered(self) -> bool:
        return self.t1 or self.t2


#: ADR-0030 failure condition F-2, first sentence (supplement 5 point 1): weekdays per window.
F2_WINDOW_WEEKDAYS: Final = 20
#: (f) fewer than 20 weekdays since the start: F-2 holds when the numerator exceeds this.
F2_SHORT_WINDOW_LIMIT: Final = 6
#: (e) F-2 holds when numerator / denominator exceeds 3 / 10 (compared in integers).
F2_RATIO_NUMERATOR: Final = 3
F2_RATIO_DENOMINATOR: Final = 10


@dataclass(frozen=True)
class F2Window:
    """One F-2 window of one claim: its calendar range, the two numerator terms, the verdict.

    ``denominator`` is ``None`` for the short range of (f) (fewer than 20
    weekdays since the start), where the verdict is ``numerator > 6``.
    """

    first: date
    last: date
    missed_sessions: int
    not_ready_days: int
    denominator: int | None
    holds: bool

    @property
    def numerator(self) -> int:
        """(d): the two terms added as they are, overlaps not deducted."""
        return self.missed_sessions + self.not_ready_days


@dataclass(frozen=True)
class F2Status:
    """F-2 (first sentence) for one claim, as :meth:`ForecastStore.f2_status` derives it.

    ``start`` is S_c, ``None`` when there is no ``forecast_run`` yet;
    ``weekdays`` the weekdays since S_c whose ``late_cutoff_at`` has passed;
    ``window`` the latest full window when ``full``, else the short range of
    (f) (``None`` when there is no such weekday); ``ever_held`` whether any
    full window since S_c held (or, before the first full window, the short
    range holds).
    """

    claim_id: str
    start: date | None
    weekdays: int
    full: bool
    window: F2Window | None
    ever_held: bool


#: ADR-0030 supplement 9 point 5: F-2's second sentence holds when L x 5 > G (over 20 %).
GRID_LOSS_FACTOR: Final = 5

GridLossVerdict = Literal["holds", "not_held", "undecidable"]


@dataclass(frozen=True)
class GridLossStatus:
    """F-2 second sentence for one claim, as :meth:`ForecastStore.grid_loss_status` derives it.

    ``counted`` is G (phase-0 grid points whose ``late_cutoff_at`` has passed),
    ``lost`` is L (those without a ``late = 0`` record); ``verdict`` is
    ``undecidable`` when G = 0, else ``holds`` exactly when L x 5 > G;
    ``ever_held`` whether any prefix j of the counted points had L_j x 5 > j.
    """

    claim_id: str
    counted: int
    lost: int
    verdict: GridLossVerdict
    ever_held: bool


@dataclass(frozen=True)
class RegisteredMaterial:
    """A claim's registry row with the stored rule bytes and definition JSON (D-5 point 2)."""

    claim: ClaimRow
    rules_bytes: bytes
    definition_json: str


@dataclass(frozen=True)
class ClaimInput:
    """One claim to register: the fields of ``ForecastStore.register_claim`` (supplement 7)."""

    horizon: Horizon
    rules_version: str
    rules_bytes: bytes
    rules_logic_sha256: str
    definition: DirectionDefinition
    frozen_commit: str
    prereg_doc_path: str
    prereg_doc_blob: bytes
    review_refs: str
    replaces_claim_id: str | None
    replace_reason: str | None
    provisional_results_seen: bool


@dataclass(frozen=True)
class _PreparedClaim:
    """A validated :class:`ClaimInput` with every derived registry column but ``registered_at``."""

    claim_id: str
    horizon: Horizon
    rules_version: str
    rules_bytes: bytes
    rules_sha256: str
    rules_logic_sha256: str
    definition_version: str
    definition_sha256: str
    definition_logic_sha256: str
    definition_json: str
    frozen_commit: str
    prereg_doc_path: str
    prereg_doc_blob: bytes
    review_refs: str
    replaces_claim_id: str | None
    replace_reason: str | None
    provisional_results_seen: int


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


def _prepare_claim(claim: ClaimInput) -> _PreparedClaim:
    """Validate ``claim`` and derive its registry columns; reads no ledger (supplement 7)."""
    definition = claim.definition
    if not isinstance(definition, DirectionDefinition):
        raise ForecastStoreError("definition must be a DirectionDefinition")
    try:
        new_id = claim_keys.claim_id(
            scope_kind=SCOPE_KIND,
            horizon=claim.horizon,
            rules_version=claim.rules_version,
            definition_version=definition.definition_version,
            kind=CLAIM_KIND,
        )
    except ValueError as exc:
        raise ForecastStoreError(str(exc)) from None
    rules = _require_bytes("rules_bytes", claim.rules_bytes)
    _require_sha256("rules_logic_sha256", claim.rules_logic_sha256)
    _require_text("frozen_commit", claim.frozen_commit)
    _require_text("prereg_doc_path", claim.prereg_doc_path)
    _require_bytes("prereg_doc_blob", claim.prereg_doc_blob)
    _require_text("review_refs", claim.review_refs)
    if (claim.replaces_claim_id is None) != (claim.replace_reason is None):
        raise ForecastStoreError("replace_reason is required exactly when replacing a claim")
    if claim.replace_reason is not None:
        _require_text("replace_reason", claim.replace_reason)
    if not isinstance(claim.provisional_results_seen, bool):
        raise ForecastStoreError("provisional_results_seen must be a bool")
    return _PreparedClaim(
        claim_id=new_id,
        horizon=claim.horizon,
        rules_version=claim.rules_version,
        rules_bytes=rules,
        rules_sha256=hashlib.sha256(rules).hexdigest(),
        rules_logic_sha256=claim.rules_logic_sha256,
        definition_version=definition.definition_version,
        definition_sha256=definition_sha256(definition),
        definition_logic_sha256=definition_logic_sha256(definition),
        definition_json=canonical_json(definition.model_dump(mode="json")),
        frozen_commit=claim.frozen_commit,
        prereg_doc_path=claim.prereg_doc_path,
        prereg_doc_blob=claim.prereg_doc_blob,
        review_refs=claim.review_refs,
        replaces_claim_id=claim.replaces_claim_id,
        replace_reason=claim.replace_reason,
        provisional_results_seen=int(claim.provisional_results_seen),
    )


class ForecastStore:
    """The ledger store on one SQLite file (the schema must already exist)."""

    def __init__(self, db_path: Path, *, clock: Clock = system_clock) -> None:
        self._db_path = Path(db_path)
        self._clock = clock

    # --- plumbing ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """A write-path connection: only :meth:`_write` opens one (AST)."""
        return _open_connection(self._db_path)

    @contextmanager
    def _write(self, *, fresh: bool = False) -> Iterator[sqlite3.Connection]:
        """One write transaction on a complete schema; rolled back on any error.

        ``fresh``: the transaction first creates every ledger object
        (``schema.create_objects``, which refuses when any exists) and then
        checks the schema complete; only :meth:`bootstrap` passes it (AST).
        """
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if fresh:
                    create_objects(conn)
                require_complete_schema(conn)
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        """A read-only connection (``query_only``): SQLite refuses any write on it.

        Every read-only query goes through here (supplement 3 (revised) point 9).
        """
        with closing(_open_connection(self._db_path)) as conn:
            conn.execute("PRAGMA query_only = ON")
            yield conn

    def _now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ForecastStoreError("the store clock must return a timezone-aware datetime")
        return now.astimezone(UTC)

    def now(self) -> datetime:
        """The store clock's current time in UTC: the recorder's only clock (S-6, K-10)."""
        return self._now()

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
        prepared = _series_row(
            SnapshotInput(
                bars=bars,
                source=source,
                source_status=source_status,
                staleness_minutes=staleness_minutes,
                reason=reason,
                dropped_rows=dropped_rows,
                raw_timestamp_available=raw_timestamp_available,
            )
        )
        with self._write() as conn:
            self._insert_series(conn, prepared)
        return prepared.digest

    def _insert_series(self, conn: sqlite3.Connection, prepared: _SeriesRow) -> None:
        exists = conn.execute(
            "SELECT 1 FROM forecast_input_series WHERE content_sha256 = ?", (prepared.digest,)
        ).fetchone()
        if exists is None:
            conn.execute(
                "INSERT INTO forecast_input_series (content_sha256, series_kind, source,"
                " source_status, staleness_minutes, reason, dropped_rows_json,"
                " raw_timestamp_available, bars_json, captured_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    prepared.digest,
                    SERIES_KIND,
                    prepared.source,
                    prepared.source_status,
                    prepared.staleness_minutes,
                    prepared.reason,
                    prepared.dropped_json,
                    int(prepared.raw_timestamp_available),
                    prepared.bars_json,
                    canonical_timestamp(self._now()),
                ),
            )

    def write_run_records(
        self, *, run_id: int, snapshot: SnapshotInput, records: Sequence[RecordInput]
    ) -> tuple[str, list[str]]:
        """A run's snapshot and every record of it, in one transaction (supplement 3 point 7).

        The same validation as :meth:`put_input_series` and :meth:`write_record`,
        each record referencing the snapshot; any failure rolls back the snapshot
        and every record, so the run wrote nothing. Returns the snapshot's
        ``content_sha256`` and the ``forecast_id`` of each record, in order. The
        recorder's one write of a run's ledger rows (AST).
        """
        prepared = _series_row(snapshot)
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence) or not records:
            raise ForecastStoreError("records must be a non-empty sequence of RecordInput")
        contents: list[tuple[str, _RecordContent]] = []
        for record in records:
            if not isinstance(record, RecordInput):
                raise ForecastStoreError("records must hold RecordInput values only")
            contents.append(
                (
                    record.claim_id,
                    self._record_content(
                        data_as_of=record.data_as_of,
                        label=record.label,
                        range_basis=record.range_basis,
                        missing=record.missing,
                        evidence=record.evidence,
                        band_def=record.band_def,
                        base_close=record.base_close,
                        baseline_predictions=record.baseline_predictions,
                        input_series_sha256=prepared.digest,
                    ),
                )
            )
        with self._write() as conn:
            self._require_open_run(conn, run_id)
            self._insert_series(conn, prepared)
            ids = [
                self._insert_record(conn, run_id=run_id, claim_id=claim_id, content=content)
                for claim_id, content in contents
            ]
        return prepared.digest, ids

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
        order is the time order. A replacement must give a reason (D-1 point 2)
        and name an earlier forward claim of the same scope and horizon that no
        other claim replaces yet (:func:`replacement_violations`; ADR-0030
        supplement 3 (revised) point 6), checked in the write transaction.
        """
        prepared = _prepare_claim(
            ClaimInput(
                horizon=horizon,
                rules_version=rules_version,
                rules_bytes=rules_bytes,
                rules_logic_sha256=rules_logic_sha256,
                definition=definition,
                frozen_commit=frozen_commit,
                prereg_doc_path=prereg_doc_path,
                prereg_doc_blob=prereg_doc_blob,
                review_refs=review_refs,
                replaces_claim_id=replaces_claim_id,
                replace_reason=replace_reason,
                provisional_results_seen=provisional_results_seen,
            )
        )
        with self._write() as conn:
            return self._insert_claim(conn, prepared, wait_for_later_clock=False)

    def bootstrap(self, *, claims: Sequence[ClaimInput]) -> tuple[str, str]:
        """Create the ledger schema and register the two core claims in one transaction.

        ADR-0030 supplement 4 point 2 and supplement 7 points 2-4. Before any
        connection is opened: exactly two :class:`ClaimInput`, horizons 3 then
        5, neither replacing a claim, each passing :func:`_prepare_claim`.
        Then, on one connection in one ``BEGIN IMMEDIATE`` (``_write(fresh=True)``):
        no ledger object may exist (``schema.create_objects`` checks it inside
        the transaction) -> every object is created -> the schema is checked
        complete -> the h3 row -> the h5 row -> COMMIT. Any exception, a
        ``BaseException`` included, rolls the whole transaction back, so the
        database is left with no ledger object. When the store clock does not
        give a ``registered_at`` later than the previous row's, it is re-read
        for up to :data:`CLOCK_WAIT_SECONDS`; still not later is an error (and
        a rollback). Returns the two ``claim_id`` values, h3 first.
        """
        given = tuple(claims)
        if len(given) != 2 or not all(isinstance(claim, ClaimInput) for claim in given):
            raise ForecastStoreError("bootstrap takes exactly two ClaimInput")
        if tuple(claim.horizon for claim in given) != (3, 5):
            raise ForecastStoreError("bootstrap registers horizon 3 then horizon 5")
        if any(claim.replaces_claim_id is not None for claim in given):
            raise ForecastStoreError("bootstrap claims replace no claim")
        first, second = (_prepare_claim(claim) for claim in given)
        with self._write(fresh=True) as conn:
            h3 = self._insert_claim(conn, first, wait_for_later_clock=True)
            h5 = self._insert_claim(conn, second, wait_for_later_clock=True)
        return h3, h5

    def _later_registration_time(
        self, conn: sqlite3.Connection, *, wait_for_later_clock: bool
    ) -> datetime:
        """The store clock's time, later than every ``registered_at`` in the registry.

        Not later: ``register_claim`` refuses at once; ``bootstrap`` re-reads
        the store clock for up to :data:`CLOCK_WAIT_SECONDS` (supplement 7
        point 4). The time is always the store clock's (S-2); the monotonic
        timer only bounds the wait.
        """
        registered_at = self._now()
        last = conn.execute("SELECT max(registered_at) FROM forecast_claim_registry").fetchone()
        if last[0] is None:
            return registered_at
        deadline = time.monotonic() + CLOCK_WAIT_SECONDS
        while canonical_timestamp(registered_at) <= str(last[0]):
            if not wait_for_later_clock or time.monotonic() >= deadline:
                raise ForecastStoreError("registered_at must be later than every registration")
            time.sleep(CLOCK_REREAD_INTERVAL_SECONDS)
            registered_at = self._now()
        return registered_at

    def _insert_claim(
        self, conn: sqlite3.Connection, prepared: _PreparedClaim, *, wait_for_later_clock: bool
    ) -> str:
        """In the caller's write transaction: clock, registration order, chain rule, INSERT."""
        registered_at = self._later_registration_time(
            conn, wait_for_later_clock=wait_for_later_clock
        )
        if prepared.replaces_claim_id is not None:
            replaced = self._claim(conn, prepared.replaces_claim_id)
            if replaced is None or replaced.kind != CLAIM_KIND:
                raise ForecastStoreError("replaces_claim_id is not a registered forward claim")
        # Supplement 3 (revised) point 6, over the registry as it would be.
        candidate = ClaimRow(
            claim_id=prepared.claim_id,
            scope_kind=SCOPE_KIND,
            scope_key=SCOPE_KEY,
            horizon=prepared.horizon,
            kind=CLAIM_KIND,
            rules_version=prepared.rules_version,
            rules_sha256=prepared.rules_sha256,
            rules_logic_sha256=prepared.rules_logic_sha256,
            definition_version=prepared.definition_version,
            definition_sha256=prepared.definition_sha256,
            definition_logic_sha256=prepared.definition_logic_sha256,
            replaces_claim_id=prepared.replaces_claim_id,
            registered_at=registered_at,
        )
        violations = replacement_violations([*self._forward_claims(conn), candidate])
        if violations:
            raise ForecastStoreError("; ".join(violations))
        conn.execute(
            "INSERT INTO forecast_claim_registry (claim_id, scope_kind, scope_key, horizon,"
            " kind, rules_version, rules_sha256, rules_logic_sha256, rules_bytes,"
            " definition_version, definition_sha256, definition_logic_sha256,"
            " definition_json, frozen_commit, prereg_doc_path, prereg_doc_blob, review_refs,"
            " replaces_claim_id, replace_reason, provisional_results_seen, registered_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                prepared.claim_id,
                SCOPE_KIND,
                SCOPE_KEY,
                prepared.horizon,
                CLAIM_KIND,
                prepared.rules_version,
                prepared.rules_sha256,
                prepared.rules_logic_sha256,
                prepared.rules_bytes,
                prepared.definition_version,
                prepared.definition_sha256,
                prepared.definition_logic_sha256,
                prepared.definition_json,
                prepared.frozen_commit,
                prepared.prereg_doc_path,
                prepared.prereg_doc_blob,
                prepared.review_refs,
                prepared.replaces_claim_id,
                prepared.replace_reason,
                prepared.provisional_results_seen,
                canonical_timestamp(registered_at),
            ),
        )
        return prepared.claim_id

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
        content = self._record_content(
            data_as_of=data_as_of,
            label=label,
            range_basis=range_basis,
            missing=missing,
            evidence=evidence,
            band_def=band_def,
            base_close=base_close,
            baseline_predictions=baseline_predictions,
            input_series_sha256=input_series_sha256,
        )
        with self._write() as conn:
            return self._insert_record(conn, run_id=run_id, claim_id=claim_id, content=content)

    def _insert_record(
        self, conn: sqlite3.Connection, *, run_id: int, claim_id: str, content: _RecordContent
    ) -> str:
        """The write-time checks and the INSERT of one validated record (inside a write)."""
        band = content.band
        data_as_of = content.data_as_of
        created = self._now()
        self._require_open_run(conn, run_id)
        claim = self._claim(conn, claim_id)
        if claim is None or claim.kind != CLAIM_KIND:
            raise ForecastStoreError("claim_id is not a registered forward claim")
        max_fetched_at = self._check_snapshot(
            conn, content.input_series_sha256, data_as_of, created
        )
        if content.label != "insufficient":
            self._check_band(band, claim, data_as_of)
        elif band["sigma_d"] is not None:
            violations = self._band_violations(band, claim)
            if violations:
                raise ForecastStoreError(
                    f"an insufficient record's sigma_d snapshot has violations: {list(violations)}"
                )
        cutoff = late_cutoff_at(data_as_of)
        columns: dict[str, object] = {
            "forecast_id": new_ulid(created),
            "run_id": run_id,
            **_record_columns(claim, content, max_fetched_at),
            "created_at": canonical_timestamp(created),
            "late": int(created >= cutoff),
        }
        names = ", ".join(columns)
        marks = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO forecast_record ({names}) VALUES ({marks})", tuple(columns.values())
        )
        return str(columns["forecast_id"])

    def expected_record_columns(
        self,
        *,
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
    ) -> dict[str, object]:
        """The stored columns ``write_record`` would give this content, ``content_hash`` included.

        Read-only: the same normalisation and derivation as :meth:`write_record`
        (one definition, ``_record_columns``) against the registered claim and
        the stored snapshot, without the write-time checks and without the
        columns outside ``content_hash`` (``forecast_id``, ``run_id``,
        ``created_at``, ``late``). The recorder's D-5 point 6 recomputation
        compares these with the stored rows.

        A content that fails validation raises ``ForecastStoreError`` (the
        recorder validates the content first, with :meth:`check_record_content`,
        so there it can only be the stored snapshot reference); a registry or
        snapshot that cannot be read or parsed raises ``LedgerInconsistentError``
        (the ledger's rows; supplement 3 (revised) point 8).
        """
        content = self._record_content(
            data_as_of=data_as_of,
            label=label,
            range_basis=range_basis,
            missing=missing,
            evidence=evidence,
            band_def=band_def,
            base_close=base_close,
            baseline_predictions=baseline_predictions,
            input_series_sha256=input_series_sha256,
        )
        with self._read() as conn:
            claim = self._claim(conn, claim_id)
            if claim is None or claim.kind != CLAIM_KIND:
                raise LedgerInconsistentError("claim_id is not a registered forward claim")
            row = conn.execute(
                "SELECT bars_json FROM forecast_input_series WHERE content_sha256 = ?",
                (input_series_sha256,),
            ).fetchone()
        if row is None:
            raise LedgerInconsistentError("input_series_sha256 is not a stored snapshot")
        try:
            bars = _stored_bars(str(row[0]))
            max_fetched_at = _max_fetched_at(bars)
        except (KeyError, TypeError, ValueError) as exc:
            raise LedgerInconsistentError(
                f"stored bars_json cannot be read ({type(exc).__name__})"
            ) from None
        return _record_columns(claim, content, max_fetched_at)

    @classmethod
    def check_record_content(
        cls,
        *,
        data_as_of: date,
        label: Label,
        range_basis: str | None,
        missing: Sequence[MissingItem],
        evidence: Mapping[str, object],
        band_def: Mapping[str, object],
        base_close: Decimal | int | str,
        baseline_predictions: Mapping[str, object],
    ) -> None:
        """The write validation of a record's content alone: no ledger read, no snapshot.

        Raises ``ForecastStoreError`` exactly when :meth:`write_record` would
        refuse this content before reading the ledger (the same
        ``_record_content`` checks). The recorder runs it on what the current
        program computed, so a recomputation whose values fail validation is a
        program-side failure (ADR-0030 supplement 3 (revised) point 8).
        """
        cls._record_content(
            data_as_of=data_as_of,
            label=label,
            range_basis=range_basis,
            missing=missing,
            evidence=evidence,
            band_def=band_def,
            base_close=base_close,
            baseline_predictions=baseline_predictions,
            input_series_sha256=_CONTENT_ONLY_SNAPSHOT,
        )

    @classmethod
    def _record_content(
        cls,
        *,
        data_as_of: date,
        label: Label,
        range_basis: str | None,
        missing: Sequence[MissingItem],
        evidence: Mapping[str, object],
        band_def: Mapping[str, object],
        base_close: Decimal | int | str,
        baseline_predictions: Mapping[str, object],
        input_series_sha256: str,
    ) -> _RecordContent:
        """Validate and normalise a record's content (no ledger read)."""
        if isinstance(data_as_of, datetime) or not isinstance(data_as_of, date):
            raise ForecastStoreError("data_as_of must be a date")
        if label not in get_args(Label):
            raise ForecastStoreError("label is outside its closed list")
        if range_basis is not None:
            _require_text("range_basis", range_basis)
        missing_json = cls._missing_json(missing)
        if (label == "insufficient") != bool(missing):
            raise ForecastStoreError("label is insufficient exactly when missing is non-empty")
        band = cls._band_def(band_def)
        band_json = _json_text("band_def", band)
        if label == "insufficient" and (band["up_pct"] is not None or band["down_pct"] is not None):
            raise ForecastStoreError("an insufficient record has null up_pct and down_pct")
        if label == "insufficient" and (band["sigma_d"] is None) != any(
            item.code.startswith(VOLATILITY_MISSING_PREFIX) for item in missing
        ):
            raise ForecastStoreError(
                "an insufficient record's sigma_d is null exactly when missing holds"
                " an E-VOL-* item"
            )
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
        return _RecordContent(
            data_as_of=data_as_of,
            label=label,
            range_basis=range_basis,
            missing_json=missing_json,
            band=band,
            band_json=band_json,
            evidence_json=evidence_json,
            base_close=close,
            baselines_json=baselines_json,
            input_series_sha256=input_series_sha256,
        )

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
    def _band_violations(
        band: Mapping[str, object], claim: ClaimRow
    ) -> tuple[ThresholdViolation, ...]:
        """``band.labeled_snapshot_violations`` under the claim's published definition."""
        definition = get_definition(claim.definition_version)
        if definition_sha256(definition) != claim.definition_sha256:
            raise ForecastStoreError("published definition differs from the claim's definition")
        return labeled_snapshot_violations(band, horizon=claim.horizon, definition=definition)

    @classmethod
    def _check_band(cls, band: Mapping[str, object], claim: ClaimRow, data_as_of: date) -> None:
        violations = cls._band_violations(band, claim)
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
        captured = datetime.fromisoformat(str(row[1]))
        if captured > created:
            raise ForecastStoreError("the snapshot was captured after created_at")
        bars = _stored_bars(str(row[0]))
        # Point in time: no bar can have been fetched, or be as of, after its capture.
        if any(bar.fetched_at > captured or bar.as_of > captured for bar in bars):
            raise ForecastStoreError("the snapshot holds a bar stamped after its captured_at")
        if bars[-1].session_date != data_as_of:
            raise ForecastStoreError("data_as_of is not the snapshot's latest session")
        if not all(bar.final for bar in bars):
            raise ForecastStoreError("the snapshot holds a bar that is not final")
        return _max_fetched_at(bars)

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

    @staticmethod
    def _forward_claims(conn: sqlite3.Connection) -> list[ClaimRow]:
        rows = conn.execute(
            f"SELECT {_CLAIM_COLUMNS} FROM forecast_claim_registry WHERE kind = ?"
            " ORDER BY registered_at, rowid",
            (CLAIM_KIND,),
        ).fetchall()
        return [_claim_row(row) for row in rows]

    def forward_claims(self) -> list[ClaimRow]:
        """Every forward claim in registration order."""
        with self._read() as conn:
            return self._forward_claims(conn)

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

    def on_time_sessions(self, claim_id: str) -> frozenset[date]:
        """The T of every ``late = 0`` record of the claim."""
        with self._read() as conn:
            rows = conn.execute(
                "SELECT data_as_of FROM forecast_record WHERE claim_id = ? AND late = 0",
                (claim_id,),
            ).fetchall()
        return frozenset(date.fromisoformat(str(row[0])) for row in rows)

    def phase0_grid(self, claim_id: str) -> Phase0Grid:
        """The phase-0 grid of D-8 point 4: D_v and every h-th final session after it.

        Over the union of final sessions of every snapshot (``final_sessions``).
        The one grid definition behind :meth:`n_hat` and the F-2 "phase-0 grid
        point loss" count (D-4 point 5). No D_v (no ``late = 0`` record) is an
        empty grid.
        """
        claim = self.claim(claim_id)
        if claim is None:
            raise ForecastStoreError("claim_id is not registered")
        start = self.d_v(claim_id)
        if start is None:
            return Phase0Grid(horizon=claim.horizon, sessions=(), first=0, on_time=frozenset())
        sessions = self.final_sessions()
        if start not in sessions:
            raise LedgerInconsistentError("D_v is not a final session of any snapshot")
        return Phase0Grid(
            horizon=claim.horizon,
            sessions=tuple(sessions),
            first=sessions.index(start),
            on_time=self.on_time_sessions(claim_id),
        )

    def n_hat(self, claim_id: str) -> int:
        """The review trigger count n-hat of D-8 point 4 (T1); an approximate upper bound of n.

        Over the union of final sessions of every snapshot, grid points are
        D_v and every h-th session after it; a grid point counts when the claim
        has a ``late = 0`` record with that T and the h-th final session after
        it has appeared. Nothing is deducted (insufficient, void, unavailable
        baselines, PIT violations).
        """
        return self.phase0_grid(claim_id).n_hat

    def review_trigger(self, claim_id: str, *, today: date) -> ReviewTrigger:
        """D-8 point 4 for one claim: n-hat, d_1 and whether T1 or T2 holds on ``today``.

        c_1 is the first checkpoint of the claim's *registered* definition
        (``definition_json``; :func:`app.dirdef.definition.n_min`, 30 for the
        market). (T1) n-hat >= ceil(c_1 / 2). (T2) ``today`` >= d_1 - 90 calendar
        days, d_1 = D_v plus c_1 x h Monday-Friday days, holidays not deducted.
        Without D_v neither holds and d_1 is ``None``. ``today`` is the caller's
        reading of the date (the report's clock), not a stored value.
        """
        if isinstance(today, datetime) or not isinstance(today, date):
            raise ForecastStoreError("today must be a date")
        material = self.registered_material(claim_id)
        try:
            definition = DirectionDefinition.model_validate_json(material.definition_json)
        except ValueError as exc:
            raise LedgerInconsistentError(
                f"registered definition_json cannot be read ({type(exc).__name__})"
            ) from None
        c1 = n_min(definition)
        grid = self.phase0_grid(claim_id)
        start = self.d_v(claim_id)
        d_1 = None if start is None else _weekdays_after(start, c1 * grid.horizon)
        return ReviewTrigger(
            claim_id=claim_id,
            horizon=grid.horizon,
            c1=c1,
            d_v=start,
            n_hat=grid.n_hat,
            d_1=d_1,
            t1=start is not None and grid.n_hat >= -(-c1 // 2),
            t2=d_1 is not None and today >= d_1 - timedelta(days=REVIEW_T2_DAYS),
        )

    def f2_status(self, claim_id: str, *, now: datetime) -> F2Status:
        """ADR-0030 failure condition F-2, first sentence, for one claim (supplement 5 point 1).

        (a) Weekdays are Monday-Friday, holidays not deducted, enumerated by
        :func:`_weekdays_after` -- the function T2 uses; dates are Taipei
        dates; a weekday D enters only once ``late_cutoff_at(D) <= now``, so
        the current day is never counted. (b) S_c = max(Taipei date of the
        claim's ``registered_at``, Taipei date of the first ``forecast_run``'s
        ``started_at``); S_c itself counts when it is a weekday. (c) Every
        run of 20 consecutive weekdays from S_c is a window, rolling by one
        weekday; its calendar range runs from its first to its last weekday,
        weekends included; F-2 has held once any full window held. (d) The
        numerator adds, as they are, the final sessions in the range (the
        union over every snapshot, :meth:`final_sessions`, n-hat's query)
        without a ``late = 0`` record of the claim, and the Taipei dates in
        the range with at least one ``inputs_not_ready`` run (one per date).
        (e) The denominator is min(20, final sessions in the range); a full
        window holds when numerator > 30 % of it, and always when the
        denominator is 0 (ADR-0030 supplement 9 point 4; full windows only). (f) With fewer than 20
        weekdays the range is every weekday since S_c and holds when the
        numerator exceeds 6. ``now`` is the caller's reading of the clock (the
        report's), not a stored value. Read-only.
        """
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ForecastStoreError("now must be a timezone-aware datetime")
        with self._read() as conn:
            claim = self._claim(conn, claim_id)
            runs = [_run_row(row) for row in conn.execute(f"{_RUN_SELECT} ORDER BY r.run_id")]
        if claim is None:
            raise ForecastStoreError("claim_id is not registered")
        if not runs:
            return F2Status(
                claim_id=claim_id, start=None, weekdays=0, full=False, window=None, ever_held=False
            )
        start = max(
            _taipei_date(claim.registered_at),
            min(_taipei_date(run.started_at) for run in runs),
        )
        eligible: list[date] = []
        day = _weekdays_after(start - timedelta(days=1), 1)
        while late_cutoff_at(day) <= now:
            eligible.append(day)
            day = _weekdays_after(day, 1)
        sessions = self.final_sessions()
        on_time = self.on_time_sessions(claim_id)
        missed = [session for session in sessions if session not in on_time]
        not_ready = sorted(
            {_taipei_date(run.started_at) for run in runs if run.outcome == "inputs_not_ready"}
        )

        def within(days: Sequence[date], first: date, last: date) -> int:
            return bisect.bisect_right(days, last) - bisect.bisect_left(days, first)

        def window(first: date, last: date, *, full: bool) -> F2Window:
            missed_count = within(missed, first, last)
            not_ready_count = within(not_ready, first, last)
            numerator = missed_count + not_ready_count
            denominator: int | None = None
            if full:
                limit = min(F2_WINDOW_WEEKDAYS, within(sessions, first, last))
                denominator = limit
                # Supplement 9 point 4: no final session at all in a full window holds.
                holds = limit == 0 or numerator * F2_RATIO_DENOMINATOR > limit * F2_RATIO_NUMERATOR
            else:
                holds = numerator > F2_SHORT_WINDOW_LIMIT
            return F2Window(
                first=first,
                last=last,
                missed_sessions=missed_count,
                not_ready_days=not_ready_count,
                denominator=denominator,
                holds=holds,
            )

        if len(eligible) < F2_WINDOW_WEEKDAYS:
            short = window(eligible[0], eligible[-1], full=False) if eligible else None
            return F2Status(
                claim_id=claim_id,
                start=start,
                weekdays=len(eligible),
                full=False,
                window=short,
                ever_held=short is not None and short.holds,
            )
        windows = [
            window(eligible[index], eligible[index + F2_WINDOW_WEEKDAYS - 1], full=True)
            for index in range(len(eligible) - F2_WINDOW_WEEKDAYS + 1)
        ]
        return F2Status(
            claim_id=claim_id,
            start=start,
            weekdays=len(eligible),
            full=True,
            window=windows[-1],
            ever_held=any(item.holds for item in windows),
        )

    def grid_loss_status(self, claim_id: str, *, now: datetime) -> GridLossStatus:
        """F-2 second sentence: the phase-0 grid point loss of one claim (supplement 9 point 5).

        The grid is :meth:`phase0_grid` (n-hat's grid). Counted are the points
        P with ``late_cutoff_at(P) <= now``, in date order: G of them; L of
        them have no ``late = 0`` record of the claim. G = 0 -- no D_v, or
        D_v's cutoff not passed -- is ``undecidable``, never "not held".
        Otherwise it holds when L x 5 > G in integers (exactly 20 % does not).
        It has ever held when, for some prefix j = 1..G of the counted points,
        its losses L_j satisfy L_j x 5 > j; that is never withdrawn. Counted
        from D_v, no window, no minimum number of points; recomputed from the
        current grid every time. ``now`` is the report's clock. Read-only.
        """
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ForecastStoreError("now must be a timezone-aware datetime")
        with self._read() as conn:
            registered = self._claim(conn, claim_id) is not None
        if not registered:
            raise ForecastStoreError("claim_id is not registered")
        grid = self.phase0_grid(claim_id)
        counted = [point for point in grid.points if late_cutoff_at(point) <= now]
        lost = 0
        ever_held = False
        for index, point in enumerate(counted, start=1):
            if point not in grid.on_time:
                lost += 1
            ever_held = ever_held or lost * GRID_LOSS_FACTOR > index
        if not counted:
            verdict: GridLossVerdict = "undecidable"
        elif lost * GRID_LOSS_FACTOR > len(counted):
            verdict = "holds"
        else:
            verdict = "not_held"
        return GridLossStatus(
            claim_id=claim_id,
            counted=len(counted),
            lost=lost,
            verdict=verdict,
            ever_held=ever_held,
        )

    def registered_material(self, claim_id: str) -> RegisteredMaterial:
        """The registry row's stored rule bytes and definition JSON (D-5 point 2)."""
        with self._read() as conn:
            claim = self._claim(conn, claim_id)
            row = conn.execute(
                "SELECT rules_bytes, definition_json FROM forecast_claim_registry"
                " WHERE claim_id = ?",
                (claim_id,),
            ).fetchone()
        if claim is None or row is None:
            raise ForecastStoreError("claim_id is not registered")
        return RegisteredMaterial(
            claim=claim, rules_bytes=bytes(row[0]), definition_json=str(row[1])
        )

    def runs(self) -> list[RunRow]:
        """Every run with its end row, if any, by ``run_id``."""
        with self._read() as conn:
            rows = conn.execute(f"{_RUN_SELECT} ORDER BY r.run_id").fetchall()
        return [_run_row(row) for row in rows]

    def snapshot_digests(self) -> list[str]:
        """Every stored snapshot's ``content_sha256``, in capture order."""
        with self._read() as conn:
            rows = conn.execute(
                "SELECT content_sha256 FROM forecast_input_series ORDER BY captured_at, rowid"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def ledger_schema_status(self) -> SchemaStatus:
        """``schema.schema_status`` on a read-only connection."""
        with self._read() as conn:
            return schema_status(conn)

    def provisional_results_seen(self) -> list[tuple[str, int]]:
        """``(claim_id, provisional_results_seen)`` of every registry row, in registration order.

        For the post-commit check of ``bootstrap --production`` (supplement 7
        point 5); a value other than the integer 0 or 1 is a
        :class:`LedgerInconsistentError`.
        """
        with self._read() as conn:
            rows = conn.execute(
                "SELECT claim_id, provisional_results_seen FROM forecast_claim_registry"
                " ORDER BY registered_at, rowid"
            ).fetchall()
        found: list[tuple[str, int]] = []
        for claim_id, value in rows:
            if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
                raise LedgerInconsistentError("provisional_results_seen is not 0 or 1")
            found.append((str(claim_id), value))
        return found

    def latest_run(self) -> RunRow | None:
        """The run with the highest ``run_id`` and its end row, if any."""
        with self._read() as conn:
            row = conn.execute(f"{_RUN_SELECT} ORDER BY r.run_id DESC LIMIT 1").fetchone()
        return None if row is None else _run_row(row)

    def latest_run_before(
        self, run_id: int, *, outcomes: Sequence[RunOutcome] | None = None
    ) -> RunRow | None:
        """The latest run before ``run_id``; with ``outcomes``, the latest that ended in one."""
        if isinstance(run_id, bool) or not isinstance(run_id, int):
            raise ForecastStoreError("run_id must be an int")
        query = f"{_RUN_SELECT} WHERE r.run_id < ?"
        params: list[object] = [run_id]
        if outcomes is not None:
            if not outcomes or any(o not in get_args(RunOutcome) for o in outcomes):
                raise ForecastStoreError("outcomes must be a non-empty subset of the outcomes")
            query += f" AND e.outcome IN ({', '.join('?' for _ in outcomes)})"
            params.extend(outcomes)
        with self._read() as conn:
            row = conn.execute(f"{query} ORDER BY r.run_id DESC LIMIT 1", params).fetchone()
        return None if row is None else _run_row(row)

    def has_record(self, claim_id: str, data_as_of: date) -> bool:
        """Whether the claim already has a record for ``data_as_of`` (the UNIQUE key)."""
        if isinstance(data_as_of, datetime) or not isinstance(data_as_of, date):
            raise ForecastStoreError("data_as_of must be a date")
        with self._read() as conn:
            row = conn.execute(
                "SELECT 1 FROM forecast_record WHERE claim_id = ? AND data_as_of = ?",
                (claim_id, data_as_of.isoformat()),
            ).fetchone()
        return row is not None

    def stored_records(self, claim_id: str) -> list[dict[str, object]]:
        """Every ``forecast_record`` row of the claim as stored, by ``data_as_of``."""
        with self._read() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM forecast_record WHERE claim_id = ? ORDER BY data_as_of, rowid",
                (claim_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def snapshot(self, content_sha256: str) -> StoredSnapshot:
        """The stored snapshot with this ``content_sha256``; raises when there is none."""
        with self._read() as conn:
            row = conn.execute(
                "SELECT bars_json, source, source_status, staleness_minutes, reason,"
                " raw_timestamp_available, captured_at FROM forecast_input_series"
                " WHERE content_sha256 = ?",
                (content_sha256,),
            ).fetchone()
        if row is None:
            raise ForecastStoreError("input_series_sha256 is not a stored snapshot")
        bars = json.loads(str(row[0]))
        if not isinstance(bars, list) or not all(isinstance(bar, dict) for bar in bars):
            raise LedgerInconsistentError("bars_json is not an array of bars")
        return StoredSnapshot(
            content_sha256=content_sha256,
            bars=tuple(bars),
            source=str(row[1]),
            source_status=str(row[2]),
            staleness_minutes=None if row[3] is None else int(str(row[3])),
            reason=None if row[4] is None else str(row[4]),
            raw_timestamp_available=bool(row[5]),
            captured_at=datetime.fromisoformat(str(row[6])),
        )


def _record_columns(
    claim: ClaimRow, content: _RecordContent, inputs_max_fetched_at: str
) -> dict[str, object]:
    """Every ``content_hash`` column of a record, and the hash (D-2 point 4; one definition)."""
    columns: dict[str, object] = {
        "claim_id": claim.claim_id,
        "scope_kind": claim.scope_kind,
        "scope_key": claim.scope_key,
        "horizon": claim.horizon,
        "data_as_of": content.data_as_of.isoformat(),
        "definition_version": claim.definition_version,
        "definition_sha256": claim.definition_sha256,
        "rules_version": claim.rules_version,
        "rules_sha256": claim.rules_sha256,
        "label": content.label,
        "range_basis": content.range_basis,
        "missing_json": content.missing_json,
        "evidence_json": content.evidence_json,
        "band_def": content.band_json,
        "base_close": content.base_close,
        "baseline_predictions_json": content.baselines_json,
        "input_series_sha256": content.input_series_sha256,
        "inputs_max_fetched_at": inputs_max_fetched_at,
        "late_cutoff_at": canonical_timestamp(late_cutoff_at(content.data_as_of)),
        "valid_until_session_estimate": valid_until_session_estimate(
            content.data_as_of, claim.horizon
        ).isoformat(),
        "validation_status": VALIDATION_STATUS,
    }
    columns["content_hash"] = record_content_hash(columns)
    return columns


def _max_fetched_at(bars: Sequence[_StoredBar]) -> str:
    """``inputs_max_fetched_at``: the latest ``fetched_at`` of a stored snapshot."""
    return canonical_timestamp(max(bar.fetched_at for bar in bars))


@dataclass(frozen=True)
class _StoredBar:
    session_date: date
    as_of: datetime
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
                as_of=as_of,
                fetched_at=fetched_at,
                final=is_final(SNAPSHOT_MARKET, session, as_of, fetched_at),
            )
        )
    return out
