"""Operations alert model (ADR-0029 D-2, D-7; OA-23 model half).

Every row of the D-2 rule 4 applicability table builds; every other
(event, source, step, write_outcome) combination and every value outside the
enumerations is refused at construction; the payloads validate their own
fields; the D-2 ``None`` cases of the two timestamps and the E-1 field pairing
hold; a bad exception class name degrades instead of failing.
"""

from __future__ import annotations

import dataclasses
import itertools
from datetime import date
from typing import Any

import pytest

from app.ops_alert.model import (
    EVENT_PAYLOAD_TYPES,
    FORECAST_RECORD_JOB_ID,
    INVALID_EXCEPTION_CLASS,
    OPS_ALERT_APPLICABILITY,
    OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS,
    OPS_ALERT_PUSH_MAX_LIST_ITEMS,
    JobSkippedPayload,
    JobSkipReason,
    MarketRunRegressedPayload,
    OpsAlert,
    OpsAlertEvent,
    OpsAlertSink,
    OpsAlertSource,
    OpsAlertStep,
    ReferenceKind,
    RegressionKind,
    SelftestPayload,
    SettleDeadlineNotStartedPayload,
    StepFailedPayload,
    UnregisteredUnobservedWeekdayPayload,
    WriteOutcome,
    exception_class_name,
)

E1 = OpsAlertEvent.UNREGISTERED_UNOBSERVED_WEEKDAY
E2 = OpsAlertEvent.MARKET_RUN_REGRESSED
E3B = OpsAlertEvent.JOB_SKIPPED
E3C = OpsAlertEvent.SETTLE_DEADLINE_NOT_STARTED
E3D = OpsAlertEvent.STEP_FAILED
SELFTEST = OpsAlertEvent.SELFTEST

S = OpsAlertSource
ST = OpsAlertStep
W = WriteOutcome

OCCURRED = "2026-10-08T14:12:03.250000+00:00"
STARTED = "2026-10-08T14:10:00.004000+00:00"

#: ADR-0029 D-2 rule 4, written out by hand so the code's table is checked
#: against the ADR rather than against itself (E-2 correction row: see below).
D2_RULE_4_ROWS = [
    (E1, S.SETTLEMENT, ST.SETTLEMENT, W.NOT_WRITTEN),
    (E1, S.CORRECTION, ST.LATE_SCAN_CORRECTION, W.NOT_WRITTEN),
    (E2, S.SETTLEMENT, ST.SETTLEMENT, W.NOT_WRITTEN),
    (E2, S.AUDIT, ST.GAP_AUDIT, W.WRITTEN_WITHOUT_REGISTRATION),
    (E3B, None, None, W.NOT_STARTED),
    (E3C, S.SETTLEMENT, ST.SETTLEMENT, W.NOT_STARTED),
    (E3D, None, ST.RECORD, W.UNSPECIFIED),
    (E3D, None, ST.SETTLEMENT, W.UNSPECIFIED),
    (E3D, None, ST.GAP_AUDIT, W.UNSPECIFIED),
    (E3D, None, ST.LATE_SCAN_CORRECTION, W.UNSPECIFIED),
    (E3D, None, ST.VALIDATION_SNAPSHOT, W.UNSPECIFIED),
    (E3D, None, ST.PLAN, W.UNSPECIFIED),
    (E3D, None, ST.ORCHESTRATOR, W.UNSPECIFIED),
    (SELFTEST, None, None, None),
]
E2_CORRECTION_ROW = (E2, S.CORRECTION, ST.LATE_SCAN_CORRECTION, W.DEFERRED)


def _e1(source: OpsAlertSource | None, **overrides: Any) -> UnregisteredUnobservedWeekdayPayload:
    fields: dict[str, Any] = {
        "unregistered_session_dates": ("2026-10-01", "2026-10-02"),
        "affected_forecast_count": 3,
        "d_reg": "2026-09-01",
    }
    if source is S.CORRECTION:
        fields.update(recheck_from="2026-09-15", recheck_to="2026-10-08", market_scan_to=41)
    else:
        fields.update(snapshot_from="2026-09-15", snapshot_to="2026-10-08")
    fields.update(overrides)
    return UnregisteredUnobservedWeekdayPayload(**fields)


def _e2(**overrides: Any) -> MarketRunRegressedPayload:
    fields: dict[str, Any] = {
        "market_run_current": 5,
        "regression_kind": RegressionKind.RUN_REGRESSED,
        "reference_kind": ReferenceKind.SETTLE_EVAL,
        "reference_value": 7,
        "reference_id": 12,
        "reference_started_at": STARTED,
        "reference_recorded_at": "2026-10-08T13:31:02.123456+00:00",
        "current_recorded_at": None,
    }
    fields.update(overrides)
    return MarketRunRegressedPayload(**fields)


def _e3b(**overrides: Any) -> JobSkippedPayload:
    fields: dict[str, Any] = {
        "job_id": FORECAST_RECORD_JOB_ID,
        "reason": JobSkipReason.MAX_INSTANCES,
        "skipped_run_times": ("2026-10-08T14:10:00+00:00", "2026-10-08T15:10:00+00:00"),
    }
    fields.update(overrides)
    return JobSkippedPayload(**fields)


def _payload(event: OpsAlertEvent, source: OpsAlertSource | None) -> object:
    if event is E1:
        return _e1(source)
    if event is E2:
        return _e2()
    if event is E3B:
        return _e3b()
    if event is E3C:
        return SettleDeadlineNotStartedPayload(deadline_at="2026-10-08T15:40:00+00:00")
    if event is E3D:
        return StepFailedPayload(exception_class="OperationalError")
    return SelftestPayload()


def _kwargs(
    event: OpsAlertEvent,
    source: OpsAlertSource | None,
    step: OpsAlertStep | None,
    write_outcome: WriteOutcome | None,
    **overrides: Any,
) -> dict[str, Any]:
    no_execution = event in (E3B, SELFTEST) or (event is E3D and step is ST.ORCHESTRATOR)
    kwargs: dict[str, Any] = {
        "event": event,
        "occurred_at": None if event is SELFTEST else OCCURRED,
        "execution_started_at": None if no_execution else STARTED,
        "source": source,
        "step": step,
        "write_outcome": write_outcome,
        "payload": _payload(event, source),
    }
    kwargs.update(overrides)
    return kwargs


# --- Applicability table (D-2 rule 4; OA-23) --------------------------------------------


@pytest.mark.parametrize("row", D2_RULE_4_ROWS, ids=lambda row: "-".join(str(v) for v in row))
def test_every_applicability_row_builds(row: tuple[Any, ...]) -> None:
    alert = OpsAlert(**_kwargs(*row))
    assert (alert.event, alert.source, alert.step, alert.write_outcome) == row
    assert alert.severity == "WARNING"


def test_the_table_is_the_d2_rule_4_table() -> None:
    assert set(D2_RULE_4_ROWS) == OPS_ALERT_APPLICABILITY
    assert len(OPS_ALERT_APPLICABILITY) == 14


def test_every_combination_outside_the_table_is_refused() -> None:
    combos = list(
        itertools.product(
            list(OpsAlertEvent),
            [None, *OpsAlertSource],
            [None, *OpsAlertStep],
            [None, *WriteOutcome],
        )
    )
    assert len(combos) == 1152
    refused = 0
    for combo in combos:
        if combo in OPS_ALERT_APPLICABILITY:
            continue
        with pytest.raises(ValueError, match="outside the table"):
            OpsAlert(**_kwargs(*combo))
        refused += 1
    assert refused == 1152 - 14


def test_e2_correction_deferred_is_refused_until_ceo_42() -> None:
    # ADR-0029 D-7: this row is inverted only once CEO #42 has explicitly
    # consented and ADR-0027 N-23 batch 2 has landed. If the CEO does not
    # consent it is not inverted; ADR-0029 is revised and re-reviewed by risk.
    assert E2_CORRECTION_ROW not in OPS_ALERT_APPLICABILITY
    with pytest.raises(ValueError, match="outside the table"):
        OpsAlert(**_kwargs(*E2_CORRECTION_ROW))


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"event": "forecast.step.failed"}, id="event-plain-string"),
        pytest.param({"source": None, "step": "record"}, id="step-plain-string"),
        pytest.param({"write_outcome": "unspecified"}, id="outcome-plain-string"),
        pytest.param({"event": "forecast.step.crashed"}, id="event-outside"),
        pytest.param({"source": "audit"}, id="source-plain-string"),
    ],
)
def test_values_outside_the_enumerations_are_refused(overrides: dict[str, Any]) -> None:
    # An equal plain string is not an enumeration member.
    kwargs = _kwargs(E3D, None, ST.RECORD, W.UNSPECIFIED)
    kwargs.update(overrides)
    with pytest.raises(ValueError, match="member"):
        OpsAlert(**kwargs)


def test_severity_is_always_warning_and_not_an_argument() -> None:
    with pytest.raises(TypeError):
        OpsAlert(**_kwargs(E3D, None, ST.PLAN, W.UNSPECIFIED, severity="ERROR"))


@pytest.mark.parametrize("row", [D2_RULE_4_ROWS[i] for i in (0, 2, 4, 5, 6, 13)], ids=str)
def test_the_payload_type_must_match_the_event(row: tuple[Any, ...]) -> None:
    wrong = SelftestPayload() if row[0] is not SELFTEST else StepFailedPayload(exception_class=None)
    assert type(wrong) is not EVENT_PAYLOAD_TYPES[row[0]]
    with pytest.raises(ValueError, match="payload"):
        OpsAlert(**_kwargs(*row, payload=wrong))


def test_the_alert_is_frozen() -> None:
    alert = OpsAlert(**_kwargs(*D2_RULE_4_ROWS[0]))
    with pytest.raises(dataclasses.FrozenInstanceError):
        alert.step = ST.PLAN  # type: ignore[misc]


# --- Timestamps (D-2) -----------------------------------------------------------------------


@pytest.mark.parametrize("row", [D2_RULE_4_ROWS[i] for i in (4, 12, 13)], ids=str)
def test_execution_started_at_is_none_where_d2_says_so(row: tuple[Any, ...]) -> None:
    assert OpsAlert(**_kwargs(*row)).execution_started_at is None
    with pytest.raises(ValueError):
        OpsAlert(**_kwargs(*row, execution_started_at=STARTED))


@pytest.mark.parametrize("row", [D2_RULE_4_ROWS[i] for i in (0, 3, 5, 6)], ids=str)
def test_execution_started_at_is_required_everywhere_else(row: tuple[Any, ...]) -> None:
    with pytest.raises(ValueError):
        OpsAlert(**_kwargs(*row, execution_started_at=None))


def test_occurred_at_is_none_for_the_selftest_only() -> None:
    with pytest.raises(ValueError):
        OpsAlert(**_kwargs(*D2_RULE_4_ROWS[13], occurred_at=OCCURRED))
    with pytest.raises(ValueError):
        OpsAlert(**_kwargs(*D2_RULE_4_ROWS[4], occurred_at=None))


def test_a_z_suffix_counts_as_utc() -> None:
    alert = OpsAlert(
        **_kwargs(
            *D2_RULE_4_ROWS[6],
            occurred_at="2026-10-08T14:12:03Z",
            execution_started_at="2026-10-08T14:10:00Z",
        )
    )
    assert alert.occurred_at == "2026-10-08T14:12:03Z"


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("2026-10-08T14:10:00", id="naive"),
        pytest.param("2026-10-08T22:10:00+08:00", id="not-utc"),
        pytest.param("2026-10-08", id="date-only"),
        pytest.param("22:10 tonight", id="not-iso"),
    ],
)
def test_timestamps_must_be_utc_iso_8601(value: str) -> None:
    with pytest.raises(ValueError):
        OpsAlert(**_kwargs(*D2_RULE_4_ROWS[6], occurred_at=value))
    with pytest.raises(ValueError):
        OpsAlert(**_kwargs(*D2_RULE_4_ROWS[6], execution_started_at=value))


# --- E-1 payload and pairing ----------------------------------------------------------------


def test_e1_count_is_derived_from_the_dates() -> None:
    payload = _e1(S.SETTLEMENT)
    assert payload.unregistered_count == 2
    with pytest.raises(TypeError):
        UnregisteredUnobservedWeekdayPayload(  # type: ignore[call-arg]
            unregistered_session_dates=("2026-10-01",),
            unregistered_count=99,
            affected_forecast_count=1,
            d_reg=None,
        )


@pytest.mark.parametrize(
    ("source", "overrides"),
    [
        pytest.param(S.SETTLEMENT, {"recheck_from": "2026-09-15"}, id="settlement+recheck_from"),
        pytest.param(S.SETTLEMENT, {"recheck_to": "2026-10-08"}, id="settlement+recheck_to"),
        pytest.param(S.SETTLEMENT, {"market_scan_to": 41}, id="settlement+market_scan_to"),
        pytest.param(S.SETTLEMENT, {"snapshot_from": None}, id="settlement-snapshot_from"),
        pytest.param(S.SETTLEMENT, {"snapshot_to": None}, id="settlement-snapshot_to"),
        pytest.param(S.CORRECTION, {"snapshot_from": "2026-09-15"}, id="correction+snapshot"),
        pytest.param(S.CORRECTION, {"snapshot_to": "2026-10-08"}, id="correction+snapshot_to"),
        pytest.param(S.CORRECTION, {"recheck_from": None}, id="correction-recheck_from"),
        pytest.param(S.CORRECTION, {"recheck_to": None}, id="correction-recheck_to"),
        pytest.param(S.CORRECTION, {"market_scan_to": None}, id="correction-market_scan_to"),
    ],
)
def test_e1_fields_go_with_their_source(source: OpsAlertSource, overrides: dict[str, Any]) -> None:
    step = ST.SETTLEMENT if source is S.SETTLEMENT else ST.LATE_SCAN_CORRECTION
    with pytest.raises(ValueError, match="E-1"):
        OpsAlert(**_kwargs(E1, source, step, W.NOT_WRITTEN, payload=_e1(source, **overrides)))


def test_e1_d_reg_may_be_none() -> None:
    assert _e1(S.SETTLEMENT, d_reg=None).d_reg is None
    # Dates travel as ISO strings (D-2 rule 2), not as date objects.
    with pytest.raises(ValueError):
        _e1(S.SETTLEMENT, d_reg=date(2026, 9, 1))


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"unregistered_session_dates": ()}, id="empty"),
        pytest.param({"unregistered_session_dates": ("2026-10-02", "2026-10-01")}, id="desc"),
        pytest.param({"unregistered_session_dates": ("2026-10-01", "2026-10-01")}, id="repeat"),
        pytest.param({"unregistered_session_dates": ("20261001",)}, id="not-canonical"),
        pytest.param({"unregistered_session_dates": ["2026-10-01"]}, id="not-a-tuple"),
        pytest.param({"affected_forecast_count": 0}, id="count-zero"),
        pytest.param({"affected_forecast_count": True}, id="count-bool"),
        pytest.param({"d_reg": "2026/09/01"}, id="bad-d_reg"),
        pytest.param({"snapshot_from": "2026-10-09"}, id="snapshot-backwards"),
    ],
)
def test_e1_payload_rejects_bad_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _e1(S.SETTLEMENT, **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"recheck_from": "2026-10-09"}, id="recheck-backwards"),
        pytest.param({"market_scan_to": -1}, id="negative-scan"),
    ],
)
def test_e1_correction_payload_rejects_bad_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _e1(S.CORRECTION, **overrides)


# --- E-2 payload ----------------------------------------------------------------------------


def test_e2_payload_fields_match_the_exception_attributes() -> None:
    names = [f.name for f in dataclasses.fields(MarketRunRegressedPayload)]
    assert names == [
        "market_run_current",
        "regression_kind",
        "reference_kind",
        "reference_value",
        "reference_id",
        "reference_started_at",
        "reference_recorded_at",
        "current_recorded_at",
    ]


@pytest.mark.parametrize(
    ("current", "kind", "builds"),
    [
        (5, RegressionKind.RUN_REGRESSED, True),
        (5, RegressionKind.REFERENCE_IDENTITY_MISMATCH, False),
        (7, RegressionKind.RUN_REGRESSED, False),
        (7, RegressionKind.REFERENCE_IDENTITY_MISMATCH, True),
    ],
)
def test_e2_run_regressed_holds_iff_the_current_run_is_below_the_reference(
    current: int, kind: RegressionKind, builds: bool
) -> None:
    if builds:
        assert _e2(market_run_current=current, regression_kind=kind).regression_kind is kind
    else:
        with pytest.raises(ValueError):
            _e2(market_run_current=current, regression_kind=kind)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"market_run_current": -1}, id="negative-current"),
        pytest.param({"reference_value": 0, "market_run_current": 0}, id="no-reference"),
        pytest.param({"reference_id": 0}, id="reference-id-zero"),
        pytest.param({"reference_started_at": "2026-10-08T22:10:00+08:00"}, id="not-utc"),
        pytest.param({"reference_recorded_at": ""}, id="empty-reference-recorded-at"),
        pytest.param({"current_recorded_at": ""}, id="empty-current-recorded-at"),
        pytest.param({"regression_kind": "run_regressed"}, id="kind-plain-string"),
        pytest.param({"reference_kind": "settle_eval"}, id="reference-kind-plain-string"),
    ],
)
def test_e2_payload_rejects_bad_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _e2(**overrides)


def test_e2_recorded_at_strings_are_kept_raw() -> None:
    payload = _e2(reference_recorded_at="raw value", current_recorded_at="other raw")
    assert (payload.reference_recorded_at, payload.current_recorded_at) == (
        "raw value",
        "other raw",
    )


# --- E-3b payload ---------------------------------------------------------------------------


def test_job_skipped_accepts_the_forecast_record_job() -> None:
    assert FORECAST_RECORD_JOB_ID == "forecast_record"
    payload = _e3b(job_id="forecast_record", reason=JobSkipReason.MISSED)
    assert payload.job_id == "forecast_record"


@pytest.mark.parametrize("job_id", ["forecast_recordx", "other_job", "data_refresh", None, ""])
def test_job_skipped_refuses_any_other_job(job_id: object) -> None:
    # ADR-0029 D-6: only forecast_record is reported; anything else is refused
    # here even if the listener's filter lets it through.
    with pytest.raises(ValueError):
        _e3b(job_id=job_id)


def test_job_skipped_allows_equal_run_times() -> None:
    # ADR-0029 D-6 asks for ascending order only, not for distinct times.
    times = ("2026-10-08T14:10:00+00:00", "2026-10-08T14:10:00+00:00")
    assert _e3b(skipped_run_times=times).skipped_run_times == times


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"reason": "missed"}, id="reason-plain-string"),
        pytest.param({"skipped_run_times": ()}, id="no-times"),
        pytest.param(
            {"skipped_run_times": ("2026-10-08T15:10:00+00:00", "2026-10-08T14:10:00+00:00")},
            id="descending",
        ),
        pytest.param({"skipped_run_times": ("2026-10-08T22:10:00+08:00",)}, id="not-utc"),
        pytest.param({"skipped_run_times": ["2026-10-08T14:10:00+00:00"]}, id="not-a-tuple"),
    ],
)
def test_job_skipped_rejects_bad_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _e3b(**overrides)


# --- E-3c, E-3d, selftest -------------------------------------------------------------------


def test_deadline_at_must_be_utc() -> None:
    with pytest.raises(ValueError):
        SettleDeadlineNotStartedPayload(deadline_at="2026-10-08T23:40:00+08:00")


def test_step_failed_without_an_exception_is_a_failed_result() -> None:
    assert StepFailedPayload(exception_class=None).exception_class is None


@pytest.mark.parametrize("name", ["bad-name", "E" * 129, "Trailing\n", "Erreuré", "9x"])
def test_step_failed_refuses_a_name_outside_the_rule(name: str) -> None:
    with pytest.raises(ValueError):
        StepFailedPayload(exception_class=name)


def test_an_odd_class_name_degrades_instead_of_failing() -> None:
    odd = type("Odd-Name", (Exception,), {})()
    payload = StepFailedPayload(exception_class=exception_class_name(odd))
    assert payload.exception_class == INVALID_EXCEPTION_CLASS
    alert = OpsAlert(**_kwargs(E3D, None, ST.RECORD, W.UNSPECIFIED, payload=payload))
    assert alert.payload == payload


def test_the_selftest_payload_has_no_fields_yet() -> None:
    assert dataclasses.fields(SelftestPayload) == ()


# --- Enumerations, constants, Protocol --------------------------------------------------------


def test_the_enumerations_are_the_adr_lists() -> None:
    assert [e.value for e in OpsAlertEvent] == [
        "forecast.unregistered_unobserved_weekday",
        "forecast.market_run_regressed",
        "forecast.job.skipped",
        "forecast.settle.deadline_not_started",
        "forecast.step.failed",
        "ops_alert.selftest",
    ]
    assert [s.value for s in OpsAlertStep] == [
        "record",
        "settlement",
        "gap_audit",
        "late_scan_correction",
        "validation_snapshot",
        "plan",
        "orchestrator",
    ]
    assert {o.value for o in WriteOutcome} == {
        "not_written",
        "written_without_registration",
        "deferred",
        "not_started",
        "unspecified",
    }
    assert {s.value for s in OpsAlertSource} == {"settlement", "audit", "correction"}
    assert {k.value for k in ReferenceKind} == {"settle_eval", "correction_job", "gap_audit"}
    assert {r.value for r in JobSkipReason} == {"max_instances", "missed"}
    assert set(EVENT_PAYLOAD_TYPES) == set(OpsAlertEvent)


def test_the_constants_are_the_adr_values() -> None:
    assert OPS_ALERT_PUSH_MAX_LIST_ITEMS == 20
    assert OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS == 128
    assert INVALID_EXCEPTION_CLASS == "invalid_exception_class"


def test_a_sink_is_anything_with_emit() -> None:
    class RecordingSink:
        def __init__(self) -> None:
            self.alerts: list[OpsAlert] = []

        def emit(self, alert: OpsAlert) -> None:
            self.alerts.append(alert)

    sink: OpsAlertSink = RecordingSink()
    alert = OpsAlert(**_kwargs(*D2_RULE_4_ROWS[4]))
    sink.emit(alert)
    assert isinstance(sink, RecordingSink) and sink.alerts == [alert]
