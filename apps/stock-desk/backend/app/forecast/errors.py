"""Fail-closed exception types of the forecast ledger (ADR-0027 D-1 ``errors.py``).

Standard library only (ADR-0027 D-1). Every type is built from keyword-only,
structured attributes that are validated at construction: a missing keyword is
a ``TypeError``, an invalid value a ``ValueError``. ``str(exc)`` is produced only
from those attributes, in one fixed ``key=value`` format (space separated;
``None`` as ``none``, dates in ISO form, tuples joined with commas). It never
carries a scope key, a symbol, a label, a cost, a share count, or the message
of any other exception.

Attribute sources:

* ``LabeledThresholdSnapshotIncompleteError`` -- ADR-0027 D-9 point 6, N-46
  sub-point "type and fields" (``replay`` source from N-53);
* ``UnregisteredUnobservedWeekdayError`` -- ADR-0027 D-9.3 B-3 "type and fields";
* ``MarketRunRegressedError`` -- ADR-0027 D-9.2 "R regression" (N-20 attributes);
* ``ReplayPitProofViolationError`` -- ADR-0027 D-9 point 7, V26-01 sub-point;
* ``ValidationSnapshotPartialSetError``, ``GapAuditRunInconsistencyError``,
  ``NoCandidateSessionError``, ``WriteGateClosedError``,
  ``ReplayExecutionRefusedError``, ``ReplayAbortedError`` and the exception class
  name rule -- ADR-0027 D-1 ``errors.py`` row, N-115 sentence (landed 38572c1).

The threshold violation list (``ThresholdViolation``,
``THRESHOLD_VIOLATION_ORDER``) is defined here and nowhere else in ``app/``;
``band.py`` imports it from this module -- ADR-0027 D-1 ``band.py`` row and
D-3 "scope and missing inputs", N-115 sentences (N115-10, landed 94fa2f9).

``SpanRegistrationGap`` is the internal signal of ``span_sessions``; it is not a
``ForecastFailClosedError`` (ADR-0027 D-1, D-9.3 B-3).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from itertools import pairwise
from typing import Final, Literal

# --- Closed lists --------------------------------------------------------------

#: ADR-0027 D-3 "scope and missing inputs", ``label != insufficient`` item.
ThresholdViolation = Literal[
    "k_h_missing",
    "k_h_mismatch",
    "eps_missing",
    "eps_mismatch",
    "sigma_d_missing",
    "sigma_d_not_positive_finite",
    "sigma_d_below_floor",
    "valid_returns_below_min",
]

#: The fixed order of the violation values; results follow it without repeats.
THRESHOLD_VIOLATION_ORDER: Final[tuple[ThresholdViolation, ...]] = (
    "k_h_missing",
    "k_h_mismatch",
    "eps_missing",
    "eps_mismatch",
    "sigma_d_missing",
    "sigma_d_not_positive_finite",
    "sigma_d_below_floor",
    "valid_returns_below_min",
)

LabeledSnapshotSource = Literal["record", "settlement", "correction", "replay"]
LABELED_SNAPSHOT_SOURCES: Final[tuple[LabeledSnapshotSource, ...]] = (
    "record",
    "settlement",
    "correction",
    "replay",
)

UnobservedWeekdaySource = Literal["settlement", "correction"]
UNOBSERVED_WEEKDAY_SOURCES: Final[tuple[UnobservedWeekdaySource, ...]] = (
    "settlement",
    "correction",
)

MarketRunRegressionSource = Literal["settlement"]
MARKET_RUN_REGRESSION_SOURCES: Final[tuple[MarketRunRegressionSource, ...]] = ("settlement",)

RegressionKind = Literal["run_regressed", "reference_identity_mismatch"]
REGRESSION_KINDS: Final[tuple[RegressionKind, ...]] = (
    "run_regressed",
    "reference_identity_mismatch",
)

ReferenceKind = Literal["settle_eval", "correction_job", "gap_audit"]
REFERENCE_KINDS: Final[tuple[ReferenceKind, ...]] = ("settle_eval", "correction_job", "gap_audit")

ReplayPitViolation = Literal[
    "input_bar_after_t",
    "input_digest_mismatch",
    "snapshot_sha256_mismatch",
]
REPLAY_PIT_VIOLATION_ORDER: Final[tuple[ReplayPitViolation, ...]] = (
    "input_bar_after_t",
    "input_digest_mismatch",
    "snapshot_sha256_mismatch",
)

GapAuditRunOutcome = Literal["ok", "partial"]
GAP_AUDIT_RUN_OUTCOMES: Final[tuple[GapAuditRunOutcome, ...]] = ("ok", "partial")

GapAuditRunRole = Literal["decisive", "basis"]
GAP_AUDIT_RUN_ROLES: Final[tuple[GapAuditRunRole, ...]] = ("decisive", "basis")

WriteGate = Literal["G-3", "G-4", "dirdef_fields"]
WRITE_GATE_ORDER: Final[tuple[WriteGate, ...]] = ("G-3", "G-4", "dirdef_fields")

ReplayRefusalReason = Literal["schedule_window", "gate_not_passed", "already_committed"]
REPLAY_REFUSAL_REASONS: Final[tuple[ReplayRefusalReason, ...]] = (
    "schedule_window",
    "gate_not_passed",
    "already_committed",
)

ReplayAbortResult = Literal["pre_validation_abort", "result_abort"]
REPLAY_ABORT_RESULTS: Final[tuple[ReplayAbortResult, ...]] = (
    "pre_validation_abort",
    "result_abort",
)

# --- Exception class name rule (N-115 #13) -------------------------------------

#: The format an exception class name must match to be stored or alerted on.
#: Use it only through ``re.fullmatch`` or ``is_valid_exception_class()``: with
#: ``re.match`` / ``re.search`` the ``$`` also matches before a trailing newline.
EXCEPTION_CLASS_PATTERN: Final = r"^[A-Za-z_][A-Za-z0-9_]*$"
#: Names longer than this are replaced, never truncated.
EXCEPTION_CLASS_MAX_CHARS: Final = 128
#: The fixed stand-in for a name that breaks the format or the length.
INVALID_EXCEPTION_CLASS: Final = "invalid_exception_class"

_EXCEPTION_CLASS_RE: Final = re.compile(EXCEPTION_CLASS_PATTERN)


def is_valid_exception_class(name: object) -> bool:
    """Whether ``name`` is a string within the format and the length limit."""
    return (
        isinstance(name, str)
        and len(name) <= EXCEPTION_CLASS_MAX_CHARS
        and _EXCEPTION_CLASS_RE.fullmatch(name) is not None
    )


def exception_class_name(exc: BaseException) -> str:
    """``type(exc).__name__``, or ``INVALID_EXCEPTION_CLASS`` when it is not valid.

    The only source of ``error_class`` / ``exception_class`` values in
    ``app/forecast/**``. A bad name degrades to the fixed value instead of
    failing, so the caller's own failure path is never replaced by this one.
    """
    name = type(exc).__name__
    return name if is_valid_exception_class(name) else INVALID_EXCEPTION_CLASS


# --- Validation and message helpers --------------------------------------------

type _Scalar = str | int | date
type _Value = _Scalar | tuple[_Scalar, ...] | None
type _Fields = tuple[tuple[str, _Value], ...]


def _render(value: _Value) -> str:
    if value is None:
        return "none"
    if isinstance(value, tuple):
        return ",".join(_render(item) for item in value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _format(fields: _Fields) -> str:
    return " ".join(f"{key}={_render(value)}" for key, value in fields)


def _choice[T: str](name: str, value: object, choices: tuple[T, ...]) -> T:
    if isinstance(value, str):
        for choice in choices:
            if value == choice:
                return choice
    raise ValueError(f"{name} is outside its closed list")


def _ordered[T: str](name: str, value: object, order: tuple[T, ...]) -> tuple[T, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{name} must be a non-empty tuple")
    positions = [order.index(_choice(name, item, order)) for item in value]
    if any(later <= earlier for earlier, later in pairwise(positions)):
        raise ValueError(f"{name} must follow its closed order without repeats")
    return tuple(order[position] for position in positions)


def _int_at_least(name: str, value: object, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _plain_date(name: str, value: object) -> date:
    # ``datetime`` is a ``date`` subclass; a timestamp is not a session date.
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"{name} must be a date")
    return value


def _optional_date(name: str, value: object) -> date | None:
    return None if value is None else _plain_date(name, value)


def _date_range(
    from_name: str, from_value: object, to_name: str, to_value: object
) -> tuple[date, date]:
    start = _plain_date(from_name, from_value)
    end = _plain_date(to_name, to_value)
    if start > end:
        raise ValueError(f"{from_name} must not be after {to_name}")
    return start, end


def _ascending_dates(name: str, value: object) -> tuple[date, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{name} must be a non-empty tuple")
    dates = tuple(_plain_date(name, item) for item in value)
    if any(later <= earlier for earlier, later in pairwise(dates)):
        raise ValueError(f"{name} must be ascending without repeats")
    return dates


def _must_be_none(name: str, value: object) -> None:
    if value is not None:
        raise ValueError(f"{name} does not apply to this source and must be None")


def _non_empty_str(name: str, value: object) -> str:
    # Stored raw strings (ADR-0029 D-7): checked for presence, never parsed.
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _utc_iso(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a UTC ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{name} must be a UTC ISO 8601 string") from None
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a UTC ISO 8601 string")
    return value


# --- Base ------------------------------------------------------------------------


class ForecastFailClosedError(Exception):
    """Base of every fail-closed exception of the forecast ledger.

    Subclasses validate and store their attributes, then call this ``__init__``,
    which builds the message from ``_fields()`` and nothing else.
    """

    def __init__(self) -> None:
        super().__init__(_format(self._fields()))

    def _fields(self) -> _Fields:
        return ()


# --- ADR-defined attributes --------------------------------------------------------


class LabeledThresholdSnapshotIncompleteError(ForecastFailClosedError):
    """A labelled forecast whose threshold snapshot is incomplete (N-46, N-53)."""

    source: LabeledSnapshotSource
    violations: tuple[ThresholdViolation, ...]
    affected_forecast_count: int
    data_as_of_from: date
    data_as_of_to: date

    def __init__(
        self,
        *,
        source: LabeledSnapshotSource,
        violations: tuple[ThresholdViolation, ...],
        affected_forecast_count: int,
        data_as_of_from: date,
        data_as_of_to: date,
    ) -> None:
        self.source = _choice("source", source, LABELED_SNAPSHOT_SOURCES)
        self.violations = _ordered("violations", violations, THRESHOLD_VIOLATION_ORDER)
        self.affected_forecast_count = _int_at_least(
            "affected_forecast_count", affected_forecast_count, 1
        )
        if self.source == "record" and self.affected_forecast_count != 1:
            raise ValueError("affected_forecast_count is always 1 for source=record")
        self.data_as_of_from, self.data_as_of_to = _date_range(
            "data_as_of_from", data_as_of_from, "data_as_of_to", data_as_of_to
        )
        super().__init__()

    def _fields(self) -> _Fields:
        return (
            ("source", self.source),
            ("violations", self.violations),
            ("affected_forecast_count", self.affected_forecast_count),
            ("data_as_of_from", self.data_as_of_from),
            ("data_as_of_to", self.data_as_of_to),
        )


class UnregisteredUnobservedWeekdayError(ForecastFailClosedError):
    """A settlement window holds an unobserved weekday with no registration (B-3).

    ``source = settlement`` carries ``snapshot_from`` / ``snapshot_to``;
    ``source = correction`` carries ``recheck_from`` / ``recheck_to`` /
    ``market_scan_to``. The fields that do not apply must be ``None`` and are
    left out of the message.
    """

    source: UnobservedWeekdaySource
    unregistered_session_dates: tuple[date, ...]
    affected_forecast_count: int
    d_reg: date | None
    snapshot_from: date | None
    snapshot_to: date | None
    recheck_from: date | None
    recheck_to: date | None
    market_scan_to: int | None

    def __init__(
        self,
        *,
        source: UnobservedWeekdaySource,
        unregistered_session_dates: tuple[date, ...],
        affected_forecast_count: int,
        d_reg: date | None,
        snapshot_from: date | None = None,
        snapshot_to: date | None = None,
        recheck_from: date | None = None,
        recheck_to: date | None = None,
        market_scan_to: int | None = None,
    ) -> None:
        self.source = _choice("source", source, UNOBSERVED_WEEKDAY_SOURCES)
        self.unregistered_session_dates = _ascending_dates(
            "unregistered_session_dates", unregistered_session_dates
        )
        self.affected_forecast_count = _int_at_least(
            "affected_forecast_count", affected_forecast_count, 1
        )
        self.d_reg = _optional_date("d_reg", d_reg)
        self.snapshot_from = self.snapshot_to = None
        self.recheck_from = self.recheck_to = None
        self.market_scan_to = None
        if self.source == "settlement":
            _must_be_none("recheck_from", recheck_from)
            _must_be_none("recheck_to", recheck_to)
            _must_be_none("market_scan_to", market_scan_to)
            self.snapshot_from, self.snapshot_to = _date_range(
                "snapshot_from", snapshot_from, "snapshot_to", snapshot_to
            )
        else:
            _must_be_none("snapshot_from", snapshot_from)
            _must_be_none("snapshot_to", snapshot_to)
            self.recheck_from, self.recheck_to = _date_range(
                "recheck_from", recheck_from, "recheck_to", recheck_to
            )
            self.market_scan_to = _int_at_least("market_scan_to", market_scan_to, 0)
        super().__init__()

    def _fields(self) -> _Fields:
        common: _Fields = (
            ("source", self.source),
            ("unregistered_session_dates", self.unregistered_session_dates),
            ("affected_forecast_count", self.affected_forecast_count),
            ("d_reg", self.d_reg),
        )
        if self.source == "settlement":
            return (
                *common,
                ("snapshot_from", self.snapshot_from),
                ("snapshot_to", self.snapshot_to),
            )
        return (
            *common,
            ("recheck_from", self.recheck_from),
            ("recheck_to", self.recheck_to),
            ("market_scan_to", self.market_scan_to),
        )


class MarketRunRegressedError(ForecastFailClosedError):
    """The settlement guard found the market DB behind its reference (D-9.2).

    ``regression_kind = run_regressed`` holds if and only if
    ``market_run_current < reference_value``. The two ``recorded_at`` values are
    the stored raw strings: checked to be non-empty strings, never parsed.
    """

    source: MarketRunRegressionSource
    market_run_current: int
    regression_kind: RegressionKind
    reference_kind: ReferenceKind
    reference_value: int
    reference_id: int
    reference_started_at: str
    reference_recorded_at: str
    current_recorded_at: str | None

    def __init__(
        self,
        *,
        source: MarketRunRegressionSource,
        market_run_current: int,
        regression_kind: RegressionKind,
        reference_kind: ReferenceKind,
        reference_value: int,
        reference_id: int,
        reference_started_at: str,
        reference_recorded_at: str,
        current_recorded_at: str | None,
    ) -> None:
        self.source = _choice("source", source, MARKET_RUN_REGRESSION_SOURCES)
        self.market_run_current = _int_at_least("market_run_current", market_run_current, 0)
        self.regression_kind = _choice("regression_kind", regression_kind, REGRESSION_KINDS)
        self.reference_kind = _choice("reference_kind", reference_kind, REFERENCE_KINDS)
        self.reference_value = _int_at_least("reference_value", reference_value, 1)
        self.reference_id = _int_at_least("reference_id", reference_id, 1)
        self.reference_started_at = _utc_iso("reference_started_at", reference_started_at)
        self.reference_recorded_at = _non_empty_str("reference_recorded_at", reference_recorded_at)
        self.current_recorded_at = (
            None
            if current_recorded_at is None
            else _non_empty_str("current_recorded_at", current_recorded_at)
        )
        regressed = self.market_run_current < self.reference_value
        if regressed != (self.regression_kind == "run_regressed"):
            raise ValueError("run_regressed holds iff market_run_current < reference_value")
        super().__init__()

    def _fields(self) -> _Fields:
        return (
            ("source", self.source),
            ("market_run_current", self.market_run_current),
            ("regression_kind", self.regression_kind),
            ("reference_kind", self.reference_kind),
            ("reference_value", self.reference_value),
            ("reference_id", self.reference_id),
            ("reference_started_at", self.reference_started_at),
            ("reference_recorded_at", self.reference_recorded_at),
            ("current_recorded_at", self.current_recorded_at),
        )


class ReplayPitProofViolationError(ForecastFailClosedError):
    """A replay forecast failed the point-in-time check (D-9 point 7, V26-01)."""

    violations: tuple[ReplayPitViolation, ...]
    affected_forecast_count: int
    data_as_of_from: date
    data_as_of_to: date

    def __init__(
        self,
        *,
        violations: tuple[ReplayPitViolation, ...],
        affected_forecast_count: int,
        data_as_of_from: date,
        data_as_of_to: date,
    ) -> None:
        self.violations = _ordered("violations", violations, REPLAY_PIT_VIOLATION_ORDER)
        self.affected_forecast_count = _int_at_least(
            "affected_forecast_count", affected_forecast_count, 1
        )
        self.data_as_of_from, self.data_as_of_to = _date_range(
            "data_as_of_from", data_as_of_from, "data_as_of_to", data_as_of_to
        )
        super().__init__()

    def _fields(self) -> _Fields:
        return (
            ("violations", self.violations),
            ("affected_forecast_count", self.affected_forecast_count),
            ("data_as_of_from", self.data_as_of_from),
            ("data_as_of_to", self.data_as_of_to),
        )


# --- Attributes per ADR-0027 D-1 ``errors.py`` row, N-115 (landed 38572c1) ---------


class ValidationSnapshotPartialSetError(ForecastFailClosedError):
    """Some claims already have a validation snapshot for the session, others not."""

    computed_for_session: date
    present_claim_count: int
    missing_claim_count: int

    def __init__(
        self,
        *,
        computed_for_session: date,
        present_claim_count: int,
        missing_claim_count: int,
    ) -> None:
        self.computed_for_session = _plain_date("computed_for_session", computed_for_session)
        self.present_claim_count = _int_at_least("present_claim_count", present_claim_count, 1)
        self.missing_claim_count = _int_at_least("missing_claim_count", missing_claim_count, 1)
        super().__init__()

    def _fields(self) -> _Fields:
        return (
            ("computed_for_session", self.computed_for_session),
            ("present_claim_count", self.present_claim_count),
            ("missing_claim_count", self.missing_claim_count),
        )


class GapAuditRunInconsistencyError(ForecastFailClosedError):
    """The gap audit found a run whose books contradict its end row (D-8 point 2).

    ``run_role`` is ``decisive`` for the deciding run, ``basis`` for a run listed
    in ``basis_json``. There is no scope key attribute.
    """

    session: date
    run_id: int
    run_outcome: GapAuditRunOutcome
    run_role: GapAuditRunRole

    def __init__(
        self,
        *,
        session: date,
        run_id: int,
        run_outcome: GapAuditRunOutcome,
        run_role: GapAuditRunRole,
    ) -> None:
        self.session = _plain_date("session", session)
        self.run_id = _int_at_least("run_id", run_id, 1)
        self.run_outcome = _choice("run_outcome", run_outcome, GAP_AUDIT_RUN_OUTCOMES)
        self.run_role = _choice("run_role", run_role, GAP_AUDIT_RUN_ROLES)
        super().__init__()

    def _fields(self) -> _Fields:
        return (
            ("session", self.session),
            ("run_id", self.run_id),
            ("run_outcome", self.run_outcome),
            ("run_role", self.run_role),
        )


class NoCandidateSessionError(ForecastFailClosedError):
    """The market DB has no ok bars run, so there is no candidate T (D-7 point 3).

    It has no attributes, and its message is empty.
    """


class WriteGateClosedError(ForecastFailClosedError):
    """The run-time write gate is not open (D-7 point 7, N-86 sub-point)."""

    failed_gates: tuple[WriteGate, ...]

    def __init__(self, *, failed_gates: tuple[WriteGate, ...]) -> None:
        self.failed_gates = _ordered("failed_gates", failed_gates, WRITE_GATE_ORDER)
        super().__init__()

    def _fields(self) -> _Fields:
        return (("failed_gates", self.failed_gates),)


class ReplayExecutionRefusedError(ForecastFailClosedError):
    """The replay execution refused to start or to commit (D-9 point 7, V26-04)."""

    reason: ReplayRefusalReason

    def __init__(self, *, reason: ReplayRefusalReason) -> None:
        self.reason = _choice("reason", reason, REPLAY_REFUSAL_REASONS)
        super().__init__()

    def _fields(self) -> _Fields:
        return (("reason", self.reason),)


class ReplayAbortedError(ForecastFailClosedError):
    """A replay execution aborted on a non fail-closed exception (V26-04).

    ``exception_class`` is the value of ``exception_class_name()`` for the
    original exception; the original object itself is never kept.
    """

    registration_id: int
    execution_seq: int
    result: ReplayAbortResult
    exception_class: str

    def __init__(
        self,
        *,
        registration_id: int,
        execution_seq: int,
        result: ReplayAbortResult,
        exception_class: str,
    ) -> None:
        self.registration_id = _int_at_least("registration_id", registration_id, 1)
        self.execution_seq = _int_at_least("execution_seq", execution_seq, 1)
        self.result = _choice("result", result, REPLAY_ABORT_RESULTS)
        if not is_valid_exception_class(exception_class):
            raise ValueError("exception_class breaks the exception class name rule")
        self.exception_class = exception_class
        super().__init__()

    def _fields(self) -> _Fields:
        return (
            ("registration_id", self.registration_id),
            ("execution_seq", self.execution_seq),
            ("result", self.result),
            ("exception_class", self.exception_class),
        )


# --- Internal signal -----------------------------------------------------------------


class SpanRegistrationGap(Exception):
    """``span_sessions`` met dates with no registration; carries only those dates.

    Not a ``ForecastFailClosedError``: settlement and correction convert it into
    ``UnregisteredUnobservedWeekdayError`` at their single conversion point.
    """

    session_dates: tuple[date, ...]

    def __init__(self, *, session_dates: tuple[date, ...]) -> None:
        self.session_dates = _ascending_dates("session_dates", session_dates)
        super().__init__(_format((("session_dates", self.session_dates),)))
