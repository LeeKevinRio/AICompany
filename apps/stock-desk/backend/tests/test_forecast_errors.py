"""Fail-closed exception types of the forecast ledger (ADR-0027 ``errors.py``).

Covers FL-72 (m), FL-71 (d) (the construction half), FL-79 (c) and (d), and the
"no identifying text" half of FL-71 (f) for exception messages: every message
is pinned verbatim, and none carries a sentinel, a label, an identifying key or
an F-class literal.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, get_args

import pytest

from app.forecast import errors
from app.forecast.errors import (
    EXCEPTION_CLASS_MAX_CHARS,
    EXCEPTION_CLASS_PATTERN,
    INVALID_EXCEPTION_CLASS,
    THRESHOLD_VIOLATION_ORDER,
    ForecastFailClosedError,
    GapAuditRunInconsistencyError,
    LabeledThresholdSnapshotIncompleteError,
    MarketRunRegressedError,
    NoCandidateSessionError,
    ReplayAbortedError,
    ReplayExecutionRefusedError,
    ReplayPitProofViolationError,
    SpanRegistrationGap,
    ThresholdViolation,
    UnregisteredUnobservedWeekdayError,
    ValidationSnapshotPartialSetError,
    WriteGateClosedError,
    exception_class_name,
)
from app.ops_alert import model as ops_alert_model
from tests.import_graph import APP_ROOT

D1 = date(2026, 10, 1)
D2 = date(2026, 10, 8)
D3 = date(2026, 10, 15)

#: Identifying sentinels of FL-71 (f) class E, the label strings, the keys that
#: must never appear, and the F-class literals an exception text could leak.
SENTINELS = ("ZZQ9", "987654321", "claim-sentinel-x", "13579.24", "scope-sentinel-q")
LABELS = ("bullish", "bearish", "range", "insufficient")
IDENTIFYING_KEYS = ("symbol=", "forecast_id=", "claim_id=", "scope_key=", "label=", "sector=")
F_CLASS_LITERALS = ("Traceback", 'File "', ".db", ".env", "token=", "api_key=", "STOCK_DESK_")


def _any(value: object) -> Any:
    """Pass a deliberately invalid value past the type checker."""
    return value


def _assert_no_identifying_text(message: str) -> None:
    for needle in (*SENTINELS, *IDENTIFYING_KEYS, *F_CLASS_LITERALS):
        assert needle not in message
    for label in LABELS:
        assert re.search(rf"\b{label}\b", message) is None


def _labeled(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "source": "record",
        "violations": ("sigma_d_missing", "valid_returns_below_min"),
        "affected_forecast_count": 1,
        "data_as_of_from": D1,
        "data_as_of_to": D1,
    }
    kwargs.update(overrides)
    return kwargs


def _unregistered_settlement(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "source": "settlement",
        "unregistered_session_dates": (D1, D2),
        "affected_forecast_count": 3,
        "d_reg": D1,
        "snapshot_from": D1,
        "snapshot_to": D3,
    }
    kwargs.update(overrides)
    return kwargs


def _unregistered_correction(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "source": "correction",
        "unregistered_session_dates": (D2,),
        "affected_forecast_count": 2,
        "d_reg": D1,
        "recheck_from": D1,
        "recheck_to": D3,
        "market_scan_to": 41,
    }
    kwargs.update(overrides)
    return kwargs


def _market_run(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "source": "settlement",
        "market_run_current": 5,
        "regression_kind": "run_regressed",
        "reference_kind": "settle_eval",
        "reference_value": 7,
        "reference_id": 12,
        "reference_started_at": "2026-10-08T14:10:00+00:00",
        "reference_recorded_at": "2026-10-08T13:31:02.123456+00:00",
        "current_recorded_at": None,
    }
    kwargs.update(overrides)
    return kwargs


# --- The violation list -----------------------------------------------------------------


def test_the_violation_type_and_its_order_list_the_same_values() -> None:
    # One definition site (C1) still holds two spellings; pin them to each other.
    assert get_args(ThresholdViolation) == THRESHOLD_VIOLATION_ORDER


# --- LabeledThresholdSnapshotIncompleteError (FL-72 (m)) ------------------------------


@pytest.mark.parametrize(
    ("source", "count", "expected"),
    [
        (
            "record",
            1,
            "source=record violations=sigma_d_missing,valid_returns_below_min "
            "affected_forecast_count=1 data_as_of_from=2026-10-01 data_as_of_to=2026-10-08",
        ),
        (
            "settlement",
            3,
            "source=settlement violations=sigma_d_missing,valid_returns_below_min "
            "affected_forecast_count=3 data_as_of_from=2026-10-01 data_as_of_to=2026-10-08",
        ),
        (
            "correction",
            2,
            "source=correction violations=sigma_d_missing,valid_returns_below_min "
            "affected_forecast_count=2 data_as_of_from=2026-10-01 data_as_of_to=2026-10-08",
        ),
        (
            "replay",
            4,
            "source=replay violations=sigma_d_missing,valid_returns_below_min "
            "affected_forecast_count=4 data_as_of_from=2026-10-01 data_as_of_to=2026-10-08",
        ),
    ],
)
def test_labeled_message_is_the_fixed_format_of_its_attributes(
    source: str, count: int, expected: str
) -> None:
    exc = LabeledThresholdSnapshotIncompleteError(
        **_labeled(source=source, affected_forecast_count=count, data_as_of_to=D2)
    )
    assert str(exc) == expected
    assert exc.args == (expected,)
    assert exc.source == source
    assert exc.violations == ("sigma_d_missing", "valid_returns_below_min")
    assert exc.affected_forecast_count == count
    assert (exc.data_as_of_from, exc.data_as_of_to) == (D1, D2)
    _assert_no_identifying_text(str(exc))


@pytest.mark.parametrize(
    "missing",
    ["source", "violations", "affected_forecast_count", "data_as_of_from", "data_as_of_to"],
)
def test_labeled_missing_a_required_attribute_fails(missing: str) -> None:
    kwargs = _labeled()
    del kwargs[missing]
    with pytest.raises(TypeError):
        LabeledThresholdSnapshotIncompleteError(**kwargs)


@pytest.mark.parametrize(
    "violations",
    [
        pytest.param((), id="empty"),
        pytest.param(("valid_returns_below_min", "sigma_d_missing"), id="out-of-order"),
        pytest.param(("sigma_d_missing", "sigma_d_missing"), id="repeated"),
        pytest.param(("sigma_d_unknown",), id="outside-the-list"),
        pytest.param(["sigma_d_missing"], id="not-a-tuple"),
    ],
)
def test_labeled_rejects_bad_violations(violations: object) -> None:
    with pytest.raises(ValueError):
        LabeledThresholdSnapshotIncompleteError(**_labeled(violations=violations))


def test_labeled_attributes_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        LabeledThresholdSnapshotIncompleteError("record", ("sigma_d_missing",), 1, D1, D1)  # type: ignore[call-arg]


@pytest.mark.parametrize("key", ["forecast_id", "claim_id", "scope_key", "symbol", "label"])
def test_labeled_takes_no_identifying_keyword(key: str) -> None:
    with pytest.raises(TypeError):
        LabeledThresholdSnapshotIncompleteError(**_labeled(**{key: "ZZQ9"}))


def test_labeled_message_never_carries_a_label_even_from_its_inputs() -> None:
    # The only free-standing strings are closed-list members, so a label or a
    # sentinel smuggled into one of them is refused rather than printed.
    for field, value in (
        ("source", "bullish"),
        ("violations", ("bullish",)),
        ("violations", ("sigma_d_missing", "ZZQ9")),
    ):
        with pytest.raises(ValueError):
            LabeledThresholdSnapshotIncompleteError(**_labeled(**{field: value}))


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"affected_forecast_count": 2}, id="record-counts-one"),
        pytest.param({"affected_forecast_count": 0, "source": "settlement"}, id="zero"),
        pytest.param({"affected_forecast_count": -1, "source": "settlement"}, id="negative"),
        pytest.param({"affected_forecast_count": True}, id="bool"),
        pytest.param({"affected_forecast_count": "1"}, id="string-count"),
        pytest.param({"data_as_of_from": D2, "data_as_of_to": D1}, id="from-after-to"),
        pytest.param({"data_as_of_from": datetime(2026, 10, 1)}, id="datetime-not-date"),
        pytest.param({"data_as_of_to": "2026-10-01"}, id="string-date"),
    ],
)
def test_labeled_rejects_bad_counts_and_dates(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        LabeledThresholdSnapshotIncompleteError(**_labeled(**overrides))


def test_labeled_rejects_a_source_outside_its_list() -> None:
    for source in ("scoring", "RECORD", None):
        with pytest.raises(ValueError):
            LabeledThresholdSnapshotIncompleteError(**_labeled(source=source))


# --- UnregisteredUnobservedWeekdayError (FL-71 (d)) -----------------------------------


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param(
            _unregistered_settlement(),
            "source=settlement unregistered_session_dates=2026-10-01,2026-10-08 "
            "affected_forecast_count=3 d_reg=2026-10-01 "
            "snapshot_from=2026-10-01 snapshot_to=2026-10-15",
            id="settlement",
        ),
        pytest.param(
            _unregistered_correction(),
            "source=correction unregistered_session_dates=2026-10-08 "
            "affected_forecast_count=2 d_reg=2026-10-01 "
            "recheck_from=2026-10-01 recheck_to=2026-10-15 market_scan_to=41",
            id="correction",
        ),
    ],
)
def test_unregistered_message_lists_only_the_fields_of_its_source(
    kwargs: dict[str, Any], expected: str
) -> None:
    exc = UnregisteredUnobservedWeekdayError(**kwargs)
    assert str(exc) == expected
    for name, value in kwargs.items():
        assert getattr(exc, name) == value
    # The fields that do not apply to the source are None, not left unset.
    other = (
        ("recheck_from", "recheck_to", "market_scan_to")
        if kwargs["source"] == "settlement"
        else ("snapshot_from", "snapshot_to")
    )
    assert all(getattr(exc, name) is None for name in other)
    _assert_no_identifying_text(str(exc))


def test_unregistered_d_reg_may_be_none() -> None:
    exc = UnregisteredUnobservedWeekdayError(**_unregistered_settlement(d_reg=None))
    assert exc.d_reg is None
    assert " d_reg=none " in str(exc)


@pytest.mark.parametrize(
    "missing", ["source", "unregistered_session_dates", "affected_forecast_count", "d_reg"]
)
def test_unregistered_missing_a_required_attribute_fails(missing: str) -> None:
    kwargs = _unregistered_settlement()
    del kwargs[missing]
    with pytest.raises(TypeError):
        UnregisteredUnobservedWeekdayError(**kwargs)


@pytest.mark.parametrize(
    ("builder", "missing"),
    [
        (_unregistered_settlement, "snapshot_from"),
        (_unregistered_settlement, "snapshot_to"),
        (_unregistered_correction, "recheck_from"),
        (_unregistered_correction, "recheck_to"),
        (_unregistered_correction, "market_scan_to"),
    ],
)
def test_unregistered_requires_the_fields_of_its_source(builder: Any, missing: str) -> None:
    kwargs = builder()
    del kwargs[missing]
    with pytest.raises(ValueError):
        UnregisteredUnobservedWeekdayError(**kwargs)


@pytest.mark.parametrize(
    ("builder", "extra", "value"),
    [
        (_unregistered_settlement, "recheck_from", D1),
        (_unregistered_settlement, "recheck_to", D3),
        (_unregistered_settlement, "market_scan_to", 41),
        (_unregistered_correction, "snapshot_from", D1),
        (_unregistered_correction, "snapshot_to", D3),
    ],
)
def test_unregistered_refuses_the_fields_of_the_other_source(
    builder: Any, extra: str, value: object
) -> None:
    with pytest.raises(ValueError):
        UnregisteredUnobservedWeekdayError(**builder(**{extra: value}))


@pytest.mark.parametrize(
    "dates",
    [
        pytest.param((), id="empty"),
        pytest.param((D2, D1), id="descending"),
        pytest.param((D1, D1), id="repeated"),
        pytest.param([D1, D2], id="not-a-tuple"),
        pytest.param((datetime(2026, 10, 1),), id="datetime"),
    ],
)
def test_unregistered_dates_must_be_ascending_unique_and_non_empty(dates: object) -> None:
    with pytest.raises(ValueError):
        UnregisteredUnobservedWeekdayError(
            **_unregistered_settlement(unregistered_session_dates=dates)
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(_unregistered_settlement(snapshot_from=D3, snapshot_to=D1), id="snapshot"),
        pytest.param(_unregistered_correction(recheck_from=D3, recheck_to=D1), id="recheck"),
        pytest.param(_unregistered_correction(market_scan_to=-1), id="negative-scan"),
        pytest.param(_unregistered_correction(market_scan_to=True), id="bool-scan"),
        pytest.param(_unregistered_settlement(source="audit"), id="audit-source"),
    ],
)
def test_unregistered_rejects_bad_ranges_and_sources(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        UnregisteredUnobservedWeekdayError(**kwargs)


# --- MarketRunRegressedError (FL-71 (e)) ------------------------------------------------


def test_market_run_message_is_the_fixed_format() -> None:
    exc = MarketRunRegressedError(**_market_run())
    assert str(exc) == (
        "source=settlement market_run_current=5 regression_kind=run_regressed "
        "reference_kind=settle_eval reference_value=7 reference_id=12 "
        "reference_started_at=2026-10-08T14:10:00+00:00 "
        "reference_recorded_at=2026-10-08T13:31:02.123456+00:00 current_recorded_at=none"
    )
    assert exc.source == "settlement"
    _assert_no_identifying_text(str(exc))


def test_market_run_identity_mismatch_keeps_both_recorded_at() -> None:
    exc = MarketRunRegressedError(
        **_market_run(
            market_run_current=9,
            regression_kind="reference_identity_mismatch",
            reference_kind="gap_audit",
            current_recorded_at="2026-10-09T13:30:00+00:00",
        )
    )
    assert exc.current_recorded_at == "2026-10-09T13:30:00+00:00"
    assert str(exc).endswith("current_recorded_at=2026-10-09T13:30:00+00:00")


@pytest.mark.parametrize("source", ["audit", "correction"])
def test_market_run_refuses_any_source_but_settlement(source: str) -> None:
    with pytest.raises(ValueError):
        MarketRunRegressedError(**_market_run(source=source))


@pytest.mark.parametrize(
    ("current", "reference", "kind", "builds"),
    [
        (5, 7, "run_regressed", True),
        (5, 7, "reference_identity_mismatch", False),
        (7, 7, "run_regressed", False),
        (8, 7, "reference_identity_mismatch", True),
    ],
)
def test_run_regressed_holds_iff_the_current_run_is_below_the_reference(
    current: int, reference: int, kind: str, builds: bool
) -> None:
    kwargs = _market_run(
        market_run_current=current, reference_value=reference, regression_kind=kind
    )
    if builds:
        assert MarketRunRegressedError(**kwargs).regression_kind == kind
    else:
        with pytest.raises(ValueError):
            MarketRunRegressedError(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"market_run_current": -1}, id="negative-current"),
        pytest.param({"reference_value": 0, "market_run_current": 0}, id="no-reference"),
        pytest.param({"reference_id": 0}, id="reference-id-zero"),
        pytest.param({"reference_started_at": "2026-10-08T14:10:00"}, id="naive-start"),
        pytest.param({"reference_started_at": "2026-10-08T22:10:00+08:00"}, id="not-utc"),
        pytest.param({"reference_started_at": "yesterday"}, id="not-iso"),
        pytest.param({"reference_recorded_at": ""}, id="empty-reference-recorded-at"),
        pytest.param({"current_recorded_at": ""}, id="empty-current-recorded-at"),
        pytest.param({"regression_kind": "restored"}, id="kind-outside"),
        pytest.param({"reference_kind": "settlement"}, id="reference-kind-outside"),
    ],
)
def test_market_run_rejects_bad_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        MarketRunRegressedError(**_market_run(**overrides))


def test_recorded_at_strings_are_kept_raw_not_parsed() -> None:
    exc = MarketRunRegressedError(
        **_market_run(reference_recorded_at="not-a-timestamp", current_recorded_at="x")
    )
    assert (exc.reference_recorded_at, exc.current_recorded_at) == ("not-a-timestamp", "x")
    # Unlike the two recorded_at strings, reference_started_at is validated.
    with pytest.raises(ValueError):
        MarketRunRegressedError(
            **_market_run(reference_started_at=datetime(2026, 10, 8, 14, 10, tzinfo=UTC))
        )


def test_market_run_missing_a_required_attribute_fails() -> None:
    # Every attribute is a required keyword, ``source`` included (D-9.2), even
    # though settlement is its only allowed value.
    for missing in _market_run():
        kwargs = _market_run()
        del kwargs[missing]
        with pytest.raises(TypeError):
            MarketRunRegressedError(**kwargs)


# --- ReplayPitProofViolationError -------------------------------------------------------


def test_replay_pit_message_is_the_fixed_format() -> None:
    exc = ReplayPitProofViolationError(
        violations=("input_bar_after_t", "snapshot_sha256_mismatch"),
        affected_forecast_count=1,
        data_as_of_from=D1,
        data_as_of_to=D2,
    )
    assert str(exc) == (
        "violations=input_bar_after_t,snapshot_sha256_mismatch affected_forecast_count=1 "
        "data_as_of_from=2026-10-01 data_as_of_to=2026-10-08"
    )


@pytest.mark.parametrize(
    "violations",
    [
        pytest.param((), id="empty"),
        pytest.param(("snapshot_sha256_mismatch", "input_bar_after_t"), id="out-of-order"),
        pytest.param(("sigma_d_missing",), id="outside-the-list"),
    ],
)
def test_replay_pit_rejects_bad_violations(violations: object) -> None:
    with pytest.raises(ValueError):
        ReplayPitProofViolationError(
            violations=violations,  # type: ignore[arg-type]
            affected_forecast_count=1,
            data_as_of_from=D1,
            data_as_of_to=D1,
        )


# --- The N115-4 attributes (FL-79 (c)) --------------------------------------------------


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        pytest.param(
            lambda: ValidationSnapshotPartialSetError(
                computed_for_session=D2, present_claim_count=2, missing_claim_count=4
            ),
            "computed_for_session=2026-10-08 present_claim_count=2 missing_claim_count=4",
            id="validation-snapshot-partial-set",
        ),
        pytest.param(
            lambda: GapAuditRunInconsistencyError(
                session=D2, run_id=31, run_outcome="partial", run_role="basis"
            ),
            "session=2026-10-08 run_id=31 run_outcome=partial run_role=basis",
            id="gap-audit-run-inconsistency",
        ),
        pytest.param(lambda: NoCandidateSessionError(), "", id="no-candidate-session"),
        pytest.param(
            lambda: WriteGateClosedError(failed_gates=("G-3", "dirdef_fields")),
            "failed_gates=G-3,dirdef_fields",
            id="write-gate-closed",
        ),
        pytest.param(
            lambda: ReplayExecutionRefusedError(reason="already_committed"),
            "reason=already_committed",
            id="replay-execution-refused",
        ),
        pytest.param(
            lambda: ReplayAbortedError(
                registration_id=3,
                execution_seq=2,
                result="result_abort",
                exception_class="OperationalError",
            ),
            "registration_id=3 execution_seq=2 result=result_abort "
            "exception_class=OperationalError",
            id="replay-aborted",
        ),
    ],
)
def test_n115_exceptions_build_with_the_fixed_format(build: Any, expected: str) -> None:
    exc = build()
    assert isinstance(exc, ForecastFailClosedError)
    assert str(exc) == expected
    _assert_no_identifying_text(str(exc))


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(
            lambda: ValidationSnapshotPartialSetError(
                computed_for_session=D2, present_claim_count=0, missing_claim_count=1
            ),
            id="present-zero",
        ),
        pytest.param(
            lambda: ValidationSnapshotPartialSetError(
                computed_for_session=D2, present_claim_count=1, missing_claim_count=0
            ),
            id="missing-zero",
        ),
        pytest.param(
            lambda: GapAuditRunInconsistencyError(
                session=D2, run_id=1, run_outcome=_any("error"), run_role="decisive"
            ),
            id="run-outcome-outside",
        ),
        pytest.param(
            lambda: GapAuditRunInconsistencyError(
                session=D2, run_id=1, run_outcome="ok", run_role=_any("latest")
            ),
            id="run-role-outside",
        ),
        pytest.param(
            lambda: GapAuditRunInconsistencyError(
                session=D2, run_id=0, run_outcome="ok", run_role="decisive"
            ),
            id="run-id-zero",
        ),
        pytest.param(lambda: WriteGateClosedError(failed_gates=()), id="gates-empty"),
        pytest.param(lambda: WriteGateClosedError(failed_gates=("G-4", "G-4")), id="gates-repeat"),
        pytest.param(lambda: WriteGateClosedError(failed_gates=("G-4", "G-3")), id="gates-order"),
        pytest.param(lambda: WriteGateClosedError(failed_gates=_any(("G-1",))), id="gates-outside"),
        pytest.param(lambda: ReplayExecutionRefusedError(reason=_any("busy")), id="reason-outside"),
        pytest.param(
            lambda: ReplayAbortedError(
                registration_id=1, execution_seq=1, result=_any("commit"), exception_class="E"
            ),
            id="result-outside",
        ),
        pytest.param(
            lambda: ReplayAbortedError(
                registration_id=1,
                execution_seq=1,
                result="pre_validation_abort",
                exception_class="bad-name",
            ),
            id="exception-class-invalid",
        ),
        pytest.param(
            lambda: ReplayAbortedError(
                registration_id=0,
                execution_seq=1,
                result="pre_validation_abort",
                exception_class="E",
            ),
            id="registration-id-zero",
        ),
    ],
)
def test_n115_exceptions_reject_bad_values(build: Any) -> None:
    with pytest.raises(ValueError):
        build()


def test_gap_audit_run_inconsistency_takes_no_scope_key() -> None:
    with pytest.raises(TypeError):
        GapAuditRunInconsistencyError(  # type: ignore[call-arg]
            session=D2,
            run_id=1,
            run_outcome="ok",
            run_role="decisive",
            scope_key="scope-sentinel-q",
        )


def test_no_candidate_session_takes_no_attribute() -> None:
    with pytest.raises(TypeError):
        NoCandidateSessionError(session=D1)  # type: ignore[call-arg]


def test_replay_aborted_keeps_no_original_exception() -> None:
    exc = ReplayAbortedError(
        registration_id=1,
        execution_seq=1,
        result="pre_validation_abort",
        exception_class=exception_class_name(ValueError("ZZQ9 secret")),
    )
    assert exc.exception_class == "ValueError"
    assert exc.__cause__ is None and exc.__context__ is None
    _assert_no_identifying_text(str(exc))


# --- SpanRegistrationGap ----------------------------------------------------------------


def test_span_registration_gap_carries_only_its_dates() -> None:
    gap = SpanRegistrationGap(session_dates=(D1, D2))
    assert not isinstance(gap, ForecastFailClosedError)
    assert gap.session_dates == (D1, D2)
    assert str(gap) == "session_dates=2026-10-01,2026-10-08"
    for dates in ((), (D2, D1)):
        with pytest.raises(ValueError):
            SpanRegistrationGap(session_dates=dates)


# --- Exception class name rule (FL-79 (d)) ----------------------------------------------


def _named(name: str) -> BaseException:
    """An exception instance whose class is called ``name`` (built with ``type()``)."""
    cls: type[Exception] = type(name, (Exception,), {})
    return cls()


EXCEPTION_CLASS_TABLE = [
    pytest.param("OperationalError", "OperationalError", id="ordinary"),
    pytest.param("E" * 128, "E" * 128, id="128-chars"),
    pytest.param("E" * 129, INVALID_EXCEPTION_CLASS, id="129-chars"),
    pytest.param("Erreuré", INVALID_EXCEPTION_CLASS, id="non-ascii"),
    pytest.param("Bad-Name", INVALID_EXCEPTION_CLASS, id="dash-via-type"),
    pytest.param("9Lives", INVALID_EXCEPTION_CLASS, id="leading-digit"),
    pytest.param("Trailing\n", INVALID_EXCEPTION_CLASS, id="trailing-newline"),
]


@pytest.mark.parametrize(("name", "expected"), EXCEPTION_CLASS_TABLE)
def test_both_copies_of_the_exception_class_rule_agree(name: str, expected: str) -> None:
    exc = _named(name)
    assert exception_class_name(exc) == expected
    assert ops_alert_model.exception_class_name(exc) == expected


def test_the_two_copies_share_their_constants() -> None:
    assert EXCEPTION_CLASS_PATTERN == ops_alert_model.OPS_ALERT_EXCEPTION_CLASS_PATTERN
    assert EXCEPTION_CLASS_MAX_CHARS == ops_alert_model.OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS == 128
    assert INVALID_EXCEPTION_CLASS == ops_alert_model.INVALID_EXCEPTION_CLASS
    assert INVALID_EXCEPTION_CLASS == "invalid_exception_class"


def test_the_rule_exists_exactly_twice_in_app() -> None:
    holders = sorted(
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*.py")
        if EXCEPTION_CLASS_PATTERN in path.read_text(encoding="utf-8")
    )
    assert holders == ["forecast/errors.py", "ops_alert/model.py"]


def test_every_fail_closed_type_is_listed_here() -> None:
    # A new subclass in errors.py must come with its own construction cells.
    defined = {
        name
        for name, value in vars(errors).items()
        if isinstance(value, type) and issubclass(value, ForecastFailClosedError)
    }
    assert defined == {
        "ForecastFailClosedError",
        "LabeledThresholdSnapshotIncompleteError",
        "UnregisteredUnobservedWeekdayError",
        "MarketRunRegressedError",
        "ReplayPitProofViolationError",
        "ValidationSnapshotPartialSetError",
        "GapAuditRunInconsistencyError",
        "NoCandidateSessionError",
        "WriteGateClosedError",
        "ReplayExecutionRefusedError",
        "ReplayAbortedError",
    }
    assert Path(errors.__file__).name == "errors.py"
