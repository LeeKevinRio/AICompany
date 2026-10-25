"""Operations alert model (ADR-0029 D-1 ``app/ops_alert/model.py``, D-2, D-7).

Standard library only (ADR-0029 D-1). ``app.forecast.*`` may import this module
and no other part of ``app.ops_alert``; this module imports no ``app.*`` at all.

* ``OpsAlert`` is frozen and only takes structured attributes: enumeration
  members, ISO 8601 strings, ints and validated exception class names, never an
  exception's text (D-2 rule 1). ``severity`` is always ``WARNING``.
* Construction validates, in order: enumeration membership (an equal plain
  string is not a member), that the payload type matches the event, the D-2
  rule 4 applicability table (``OPS_ALERT_APPLICABILITY``), the two UTC
  timestamps and the cases where D-2 makes them ``None``, and the E-1 fields
  that go with each ``source``. Anything else raises ``ValueError`` (D-2 rule 2).
* ``OpsAlertSink`` is the Protocol the orchestrator receives, without a
  default; its one implementation comes with ``sink.py`` in a later batch.
* ``exception_class_name()`` keeps this package's own copy of the exception
  class name rule (D-3 point 10); ``app.forecast.errors`` holds the other copy,
  and tests pin the two to the same table (ADR-0027 FL-79 (d) and D-1
  ``errors.py`` row, N-115; landed 38572c1).

Per ADR-0029 as read by the tech-architect B1 ruling (item 7, 2026-10-24),
which needs no ADR change:

* E-2 ``source = correction`` / ``write_outcome = deferred`` is left out of the
  applicability table and is refused. It is inverted only once CEO #42 has
  explicitly consented and ADR-0027 N-23 batch 2 has landed; if the CEO does
  not consent it is not inverted -- ADR-0029 is revised and sent back to risk
  review instead (ADR-0029 D-7 rules).
* ``JobSkippedPayload.job_id`` accepts ``FORECAST_RECORD_JOB_ID`` only
  (ADR-0029 D-6, D-7 E-3b); any other value raises ``ValueError``.
* The self-test payload has no fields yet; its fixed fields are defined with
  the renderer and confirmed with risk (ADR-0029 D-10 item 8).
* ``reference_recorded_at`` / ``current_recorded_at`` are the stored raw
  strings: checked to be non-empty strings, never parsed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from itertools import pairwise
from typing import Final, Protocol

# --- Constants -------------------------------------------------------------------

#: Push lists at most this many ``unregistered_session_dates`` (ADR-0029 D-4).
OPS_ALERT_PUSH_MAX_LIST_ITEMS: Final = 20
#: Longest exception class name kept; longer ones are replaced (D-3 point 10).
OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS: Final = 128
#: The exception class name format (D-2 rule 1).
OPS_ALERT_EXCEPTION_CLASS_PATTERN: Final = r"^[A-Za-z_][A-Za-z0-9_]*$"
#: The fixed stand-in for a name that breaks the format or the length.
INVALID_EXCEPTION_CLASS: Final = "invalid_exception_class"
#: The only job the skipped listener reports on (ADR-0029 D-6).
FORECAST_RECORD_JOB_ID: Final = "forecast_record"
#: ``OpsAlert.severity`` is always this (D-2).
OPS_ALERT_SEVERITY: Final = "WARNING"

_EXCEPTION_CLASS_RE: Final = re.compile(OPS_ALERT_EXCEPTION_CLASS_PATTERN)


def _is_valid_exception_class(name: object) -> bool:
    return (
        isinstance(name, str)
        and len(name) <= OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS
        and _EXCEPTION_CLASS_RE.fullmatch(name) is not None
    )


def exception_class_name(exc: BaseException) -> str:
    """``type(exc).__name__``, or ``INVALID_EXCEPTION_CLASS`` when it is not valid."""
    name = type(exc).__name__
    return name if _is_valid_exception_class(name) else INVALID_EXCEPTION_CLASS


# --- Closed enumerations ---------------------------------------------------------------


class OpsAlertEvent(StrEnum):
    """ADR-0029 D-7 event catalogue."""

    UNREGISTERED_UNOBSERVED_WEEKDAY = "forecast.unregistered_unobserved_weekday"  # E-1
    MARKET_RUN_REGRESSED = "forecast.market_run_regressed"  # E-2
    JOB_SKIPPED = "forecast.job.skipped"  # E-3b
    SETTLE_DEADLINE_NOT_STARTED = "forecast.settle.deadline_not_started"  # E-3c
    STEP_FAILED = "forecast.step.failed"  # E-3d
    SELFTEST = "ops_alert.selftest"


class OpsAlertSource(StrEnum):
    SETTLEMENT = "settlement"
    AUDIT = "audit"
    CORRECTION = "correction"


class OpsAlertStep(StrEnum):
    """The six ADR-0027 D-7 point 2 steps in order, then ``orchestrator``."""

    RECORD = "record"
    SETTLEMENT = "settlement"
    GAP_AUDIT = "gap_audit"
    LATE_SCAN_CORRECTION = "late_scan_correction"
    VALIDATION_SNAPSHOT = "validation_snapshot"
    PLAN = "plan"
    ORCHESTRATOR = "orchestrator"


class WriteOutcome(StrEnum):
    NOT_WRITTEN = "not_written"
    WRITTEN_WITHOUT_REGISTRATION = "written_without_registration"
    DEFERRED = "deferred"
    NOT_STARTED = "not_started"
    UNSPECIFIED = "unspecified"


class RegressionKind(StrEnum):
    RUN_REGRESSED = "run_regressed"
    REFERENCE_IDENTITY_MISMATCH = "reference_identity_mismatch"


class ReferenceKind(StrEnum):
    SETTLE_EVAL = "settle_eval"
    CORRECTION_JOB = "correction_job"
    GAP_AUDIT = "gap_audit"


class JobSkipReason(StrEnum):
    MAX_INSTANCES = "max_instances"
    MISSED = "missed"


# --- Validation helpers ------------------------------------------------------------------


def _int_at_least(name: str, value: object, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _iso_date(name: str, value: object) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO 8601 date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{name} must be an ISO 8601 date string") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{name} must be an ISO 8601 date string")
    return parsed


def _optional_iso_date(name: str, value: object) -> date | None:
    return None if value is None else _iso_date(name, value)


def _utc_iso(name: str, value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a UTC ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{name} must be a UTC ISO 8601 string") from None
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a UTC ISO 8601 string")
    return parsed


def _non_empty_str(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _member(name: str, value: object, enum: type[StrEnum], *, optional: bool) -> None:
    if value is None and optional:
        return
    if not isinstance(value, enum):
        raise ValueError(f"{name} must be a {enum.__name__} member")


def _in_order(first_name: str, first: date | None, second_name: str, second: date | None) -> None:
    if first is not None and second is not None and first > second:
        raise ValueError(f"{first_name} must not be after {second_name}")


# --- Payloads (ADR-0029 D-7) -----------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class UnregisteredUnobservedWeekdayPayload:
    """E-1. ``unregistered_count`` is derived from the dates, never passed in.

    ``source = settlement`` carries ``snapshot_*``; ``source = correction``
    carries ``recheck_*`` and ``market_scan_to``. ``OpsAlert`` checks the pairing.
    """

    unregistered_session_dates: tuple[str, ...]
    unregistered_count: int = field(init=False)
    affected_forecast_count: int
    d_reg: str | None
    snapshot_from: str | None = None
    snapshot_to: str | None = None
    recheck_from: str | None = None
    recheck_to: str | None = None
    market_scan_to: int | None = None

    def __post_init__(self) -> None:
        dates = self.unregistered_session_dates
        if not isinstance(dates, tuple) or not dates:
            raise ValueError("unregistered_session_dates must be a non-empty tuple")
        parsed = [_iso_date("unregistered_session_dates", item) for item in dates]
        if any(later <= earlier for earlier, later in pairwise(parsed)):
            raise ValueError("unregistered_session_dates must be ascending without repeats")
        object.__setattr__(self, "unregistered_count", len(dates))
        _int_at_least("affected_forecast_count", self.affected_forecast_count, 1)
        _optional_iso_date("d_reg", self.d_reg)
        _in_order(
            "snapshot_from",
            _optional_iso_date("snapshot_from", self.snapshot_from),
            "snapshot_to",
            _optional_iso_date("snapshot_to", self.snapshot_to),
        )
        _in_order(
            "recheck_from",
            _optional_iso_date("recheck_from", self.recheck_from),
            "recheck_to",
            _optional_iso_date("recheck_to", self.recheck_to),
        )
        if self.market_scan_to is not None:
            _int_at_least("market_scan_to", self.market_scan_to, 0)


@dataclass(frozen=True, kw_only=True)
class MarketRunRegressedPayload:
    """E-2. Field names match ``MarketRunRegressedError`` / ``MarketRunRegression``."""

    market_run_current: int
    regression_kind: RegressionKind
    reference_kind: ReferenceKind
    reference_value: int
    reference_id: int
    reference_started_at: str
    reference_recorded_at: str
    current_recorded_at: str | None

    def __post_init__(self) -> None:
        _int_at_least("market_run_current", self.market_run_current, 0)
        _member("regression_kind", self.regression_kind, RegressionKind, optional=False)
        _member("reference_kind", self.reference_kind, ReferenceKind, optional=False)
        _int_at_least("reference_value", self.reference_value, 1)
        _int_at_least("reference_id", self.reference_id, 1)
        _utc_iso("reference_started_at", self.reference_started_at)
        _non_empty_str("reference_recorded_at", self.reference_recorded_at)
        if self.current_recorded_at is not None:
            _non_empty_str("current_recorded_at", self.current_recorded_at)
        regressed = self.market_run_current < self.reference_value
        if regressed != (self.regression_kind is RegressionKind.RUN_REGRESSED):
            raise ValueError("run_regressed holds iff market_run_current < reference_value")


@dataclass(frozen=True, kw_only=True)
class JobSkippedPayload:
    """E-3b. ``skipped_run_times`` are UTC ISO 8601 strings in ascending order."""

    job_id: str
    reason: JobSkipReason
    skipped_run_times: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, str) or self.job_id != FORECAST_RECORD_JOB_ID:
            raise ValueError("job_id must be the forecast_record job")
        _member("reason", self.reason, JobSkipReason, optional=False)
        times = self.skipped_run_times
        if not isinstance(times, tuple) or not times:
            raise ValueError("skipped_run_times must be a non-empty tuple")
        parsed = [_utc_iso("skipped_run_times", item) for item in times]
        if any(later < earlier for earlier, later in pairwise(parsed)):
            raise ValueError("skipped_run_times must be in ascending order")


@dataclass(frozen=True, kw_only=True)
class SettleDeadlineNotStartedPayload:
    """E-3c."""

    deadline_at: str

    def __post_init__(self) -> None:
        _utc_iso("deadline_at", self.deadline_at)


@dataclass(frozen=True, kw_only=True)
class StepFailedPayload:
    """E-3d. ``exception_class`` is ``None`` for a step that returned a failed result."""

    exception_class: str | None

    def __post_init__(self) -> None:
        if self.exception_class is not None and not _is_valid_exception_class(self.exception_class):
            raise ValueError("exception_class breaks the exception class name rule")


@dataclass(frozen=True, kw_only=True)
class SelftestPayload:
    """``ops_alert.selftest``. No fields until the renderer batch defines them."""


type OpsAlertPayload = (
    UnregisteredUnobservedWeekdayPayload
    | MarketRunRegressedPayload
    | JobSkippedPayload
    | SettleDeadlineNotStartedPayload
    | StepFailedPayload
    | SelftestPayload
)

#: The one payload type each event carries.
EVENT_PAYLOAD_TYPES: Final[dict[OpsAlertEvent, type]] = {
    OpsAlertEvent.UNREGISTERED_UNOBSERVED_WEEKDAY: UnregisteredUnobservedWeekdayPayload,
    OpsAlertEvent.MARKET_RUN_REGRESSED: MarketRunRegressedPayload,
    OpsAlertEvent.JOB_SKIPPED: JobSkippedPayload,
    OpsAlertEvent.SETTLE_DEADLINE_NOT_STARTED: SettleDeadlineNotStartedPayload,
    OpsAlertEvent.STEP_FAILED: StepFailedPayload,
    OpsAlertEvent.SELFTEST: SelftestPayload,
}

type ApplicabilityRow = tuple[
    OpsAlertEvent, OpsAlertSource | None, OpsAlertStep | None, WriteOutcome | None
]

#: ADR-0029 D-2 rule 4: the (event, source, step, write_outcome) rows that build.
#: The E-2 ``correction`` / ``late_scan_correction`` / ``deferred`` row is left out
#: until CEO #42 explicitly consents and ADR-0027 N-23 batch 2 has landed; if the
#: CEO does not consent it stays out and ADR-0029 is revised for risk re-review.
OPS_ALERT_APPLICABILITY: Final[frozenset[ApplicabilityRow]] = frozenset(
    {
        (
            OpsAlertEvent.UNREGISTERED_UNOBSERVED_WEEKDAY,
            OpsAlertSource.SETTLEMENT,
            OpsAlertStep.SETTLEMENT,
            WriteOutcome.NOT_WRITTEN,
        ),
        (
            OpsAlertEvent.UNREGISTERED_UNOBSERVED_WEEKDAY,
            OpsAlertSource.CORRECTION,
            OpsAlertStep.LATE_SCAN_CORRECTION,
            WriteOutcome.NOT_WRITTEN,
        ),
        (
            OpsAlertEvent.MARKET_RUN_REGRESSED,
            OpsAlertSource.SETTLEMENT,
            OpsAlertStep.SETTLEMENT,
            WriteOutcome.NOT_WRITTEN,
        ),
        (
            OpsAlertEvent.MARKET_RUN_REGRESSED,
            OpsAlertSource.AUDIT,
            OpsAlertStep.GAP_AUDIT,
            WriteOutcome.WRITTEN_WITHOUT_REGISTRATION,
        ),
        (OpsAlertEvent.JOB_SKIPPED, None, None, WriteOutcome.NOT_STARTED),
        (
            OpsAlertEvent.SETTLE_DEADLINE_NOT_STARTED,
            OpsAlertSource.SETTLEMENT,
            OpsAlertStep.SETTLEMENT,
            WriteOutcome.NOT_STARTED,
        ),
        *(
            (OpsAlertEvent.STEP_FAILED, None, step, WriteOutcome.UNSPECIFIED)
            for step in OpsAlertStep
        ),
        (OpsAlertEvent.SELFTEST, None, None, None),
    }
)


# --- The alert -----------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class OpsAlert:
    """One operations alert (ADR-0029 D-2)."""

    event: OpsAlertEvent
    occurred_at: str | None
    execution_started_at: str | None
    source: OpsAlertSource | None
    step: OpsAlertStep | None
    write_outcome: WriteOutcome | None
    payload: OpsAlertPayload
    severity: str = field(default=OPS_ALERT_SEVERITY, init=False)

    def __post_init__(self) -> None:
        _member("event", self.event, OpsAlertEvent, optional=False)
        _member("source", self.source, OpsAlertSource, optional=True)
        _member("step", self.step, OpsAlertStep, optional=True)
        _member("write_outcome", self.write_outcome, WriteOutcome, optional=True)
        if type(self.payload) is not EVENT_PAYLOAD_TYPES[self.event]:
            raise ValueError("payload type does not match the event")
        row = (self.event, self.source, self.step, self.write_outcome)
        if row not in OPS_ALERT_APPLICABILITY:
            raise ValueError("(event, source, step, write_outcome) is outside the table")
        self._check_timestamps()
        self._check_e1_pairing()

    def _check_timestamps(self) -> None:
        # D-2: selftest has no occurred_at; E-3b, the orchestrator E-3d and
        # selftest have no execution_started_at. Every other alert has both.
        if self.event is OpsAlertEvent.SELFTEST:
            if self.occurred_at is not None:
                raise ValueError("occurred_at must be None for the self-test")
        else:
            _utc_iso("occurred_at", self.occurred_at)
        no_execution = self.event in (OpsAlertEvent.JOB_SKIPPED, OpsAlertEvent.SELFTEST) or (
            self.event is OpsAlertEvent.STEP_FAILED and self.step is OpsAlertStep.ORCHESTRATOR
        )
        if no_execution:
            if self.execution_started_at is not None:
                raise ValueError("execution_started_at must be None for this alert")
        else:
            _utc_iso("execution_started_at", self.execution_started_at)

    def _check_e1_pairing(self) -> None:
        payload = self.payload
        if not isinstance(payload, UnregisteredUnobservedWeekdayPayload):
            return
        settlement: tuple[object, ...] = (payload.snapshot_from, payload.snapshot_to)
        correction: tuple[object, ...] = (
            payload.recheck_from,
            payload.recheck_to,
            payload.market_scan_to,
        )
        if self.source is OpsAlertSource.SETTLEMENT:
            present, absent = settlement, correction
        else:
            present, absent = correction, settlement
        if any(value is None for value in present):
            raise ValueError("E-1 is missing a field of its source")
        if any(value is not None for value in absent):
            raise ValueError("E-1 carries a field that does not apply to its source")


class OpsAlertSink(Protocol):
    """Sends an alert; ``emit`` never raises (ADR-0029 D-1, D-3 point 4)."""

    def emit(self, alert: OpsAlert) -> None: ...
