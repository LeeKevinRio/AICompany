"""Job ``forecast_record``: the one orchestration of the market core (ADR-0030 D-1 point 3).

:func:`record_forecasts` runs, in this order and nowhere else (D-1 point 3):

1. ``forecast_run`` -- the run's first write, before any market data is read
   (D-2 point 1). ``code_digest`` and ``runtime_json`` are the ones of the
   program this process loaded (:data:`LOADED`, taken when this module is
   imported, so a source tree edited under a running scheduler does not stamp
   old code with a new digest);
2. CG-2 run-time check (D-6, K-9, S-7, S-14) -- :func:`check_recording_claims`;
3. cross-commit check (D-5 points 3 and 6, S-12; supplement 3 (revised) point
   1) -- when this run's ``code_digest`` or ``runtime_json`` differs from the
   previous run's, or from the latest passed run (``ok``, ``no_new_session``,
   ``inputs_not_ready``), or there is no passed run, every stored record of each
   recording claim is recomputed from its stored snapshot with the current
   program; ``label``, ``band_def``, ``baseline_predictions_json``,
   ``missing_json`` and ``content_hash`` must be equal byte for byte;
4. decide T (D-3 points 1-2; supplement 2 points 1-2) -- the index answer comes
   from the injected loader; T is the latest final bar. Each non-final row of
   session S is split by the store clock's ``now``: (a) ``now`` at or after S's
   publish cutoff -> re-fetch once, and if any (a) row remains the run is
   ``inputs_not_ready`` with ``candidate_t`` the largest such S; (b) ``now``
   before it -> the row stays out of the snapshot, listed in
   ``dropped_rows_json``, and T is unchanged (LA-G2-5);
5. when every recording claim already has a record for T: ``no_new_session``
   (D-2 point 2), ``candidate_t`` filled, nothing written;
6. capture the snapshot (``put_input_series``), compute the model and B1, B2,
   B6, B8 from that one snapshot (``app.outlook.engine.compute_outlook``), and
   write each record in one store transaction (D-4 point 1).

Every run that got its ``forecast_run`` row ends with one ``forecast_run_end``
row: ``ok``, ``no_new_session``, ``inputs_not_ready``, ``gate_closed`` (CG-2:
``WriteGateClosedError``; D-5 point 6: ``SemanticsChanged``) or ``error`` (any
other ``Exception``); ``error_class`` only through ``exception_class_name``. A
``BaseException`` that is not an ``Exception`` (interruption, ``SystemExit``)
leaves no end row: no end row means the run was interrupted (D-2 point 2).

What the entry takes (supplement 2 point 1; K-10, S-6): the store -- whose
clock is the run's only clock -- the index loader and the resolver it is
called with. In production ``app.scheduler`` passes
``app.services.index.load_market_benchmark`` itself; this package does not
import ``app.services`` (K-2 reachability). There is no T, ``as_of``, clock,
rule set, definition or registry parameter: a past answer can only produce
``late = 1`` records or be refused by ``UNIQUE``. Other loaders are for tests
and the D-7 harness only (K-11).

The rule sets and definitions are the ones ``app.forecast.definitions``
returns for the recording claims, after CG-2 proved their hashes equal the
registered ones (so they are the registered rule bytes and definition).
Nothing here logs: no output of this module carries a label (D-4 point 3).
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Final, Protocol, TypedDict, get_args
from zoneinfo import ZoneInfo

from app.data.freshness import TW_POLICY
from app.data.interface import Market
from app.data.session_calendar import is_final
from app.dirdef.definition import (
    DirectionDefinition,
    Horizon,
    definition_logic_sha256,
    definition_sha256,
)
from app.dirdef.hashing import canonical_json
from app.dirdef.rules import OutlookRuleSet, rules_logic_sha256
from app.forecast.canonical import APP_ROOT, code_digest
from app.forecast.definitions import (
    PublishedVersionRejectedError,
    UnpublishedVersionError,
    get_definition,
    get_ruleset,
    get_ruleset_entry,
)
from app.forecast.errors import SemanticsChanged, WriteGateClosedError, exception_class_name
from app.forecast.store import (
    CLAIM_KIND,
    SCOPE_KEY,
    SCOPE_KIND,
    ClaimRow,
    ForecastStore,
    Label,
    RunOutcome,
    RunRow,
    StoredSnapshot,
)
from app.outlook.engine import OutlookOutcome, compute_outlook, n_snapshot
from app.outlook.inputs import (
    SNAPSHOT_MARKET,
    DroppedRow,
    IndexSeriesAnswer,
    MarketSnapshot,
    SnapshotBar,
    capture_market_snapshot,
    non_final_rows,
)
from app.outlook.missing import MissingItem

#: The job id (D-3 point 7); the wiring PR registers it, this module does not.
JOB_ID: Final = "forecast_record"
#: The market whose index the core records (D-1 point 1; ADR-0005).
MARKET: Final[Market] = "TW"
#: The core horizons: one recording claim each (D-1 point 1, K-9).
CORE_HORIZONS: Final[tuple[Horizon, ...]] = get_args(Horizon)
#: The request covers at least this many calendar days before T (D-5 point 1) ...
FETCH_CALENDAR_DAYS: Final = 500
#: ... counted from the run date plus this slack, since T is not known before the
#: answer and is the run date or an earlier session (weekends, holiday closures).
FETCH_SLACK_DAYS: Final = 31
#: Outcomes a run reaches only after both checks passed (steps 2 and 3).
CHECKED_OUTCOMES: Final[tuple[RunOutcome, ...]] = ("ok", "no_new_session", "inputs_not_ready")
#: The columns D-5 point 3 recomputes byte for byte (``content_hash`` covers the rest).
RECOMPUTED_COLUMNS: Final = (
    "label",
    "band_def",
    "baseline_predictions_json",
    "missing_json",
    "content_hash",
)
#: The dependency lock file whose sha256 is part of ``runtime_json`` (D-2 point 1).
LOCK_FILE: Final = APP_ROOT.parent / "uv.lock"

_TAIPEI: Final = ZoneInfo(TW_POLICY.timezone)


# --- provenance ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Provenance:
    """``forecast_run``'s provenance columns of the program this process loaded."""

    code_commit: str
    code_digest: str
    runtime: Mapping[str, object]

    @property
    def runtime_json(self) -> str:
        """``runtime_json`` as the store writes it."""
        return canonical_json(dict(self.runtime))


def runtime_info(lock_file: Path = LOCK_FILE) -> dict[str, object]:
    """Python version and build, platform, and the sha256 of the dependency lock file."""
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_build": list(platform.python_build()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "lockfile_sha256": hashlib.sha256(lock_file.read_bytes()).hexdigest(),
    }


def code_commit(app_root: Path = APP_ROOT) -> str:
    """The checked-out commit, provenance only (D-2 point 1); ``unknown`` when git cannot say."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=app_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    commit = done.stdout.strip()
    if done.returncode != 0 or len(commit) != 40 or commit.strip("0123456789abcdef"):
        return "unknown"
    return commit


def load_provenance(app_root: Path = APP_ROOT, lock_file: Path = LOCK_FILE) -> Provenance:
    """The provenance of the sources under ``app_root`` and the lock file, as of now."""
    return Provenance(
        code_commit=code_commit(app_root),
        code_digest=code_digest(app_root),
        runtime=MappingProxyType(runtime_info(lock_file)),
    )


#: Taken once, when this module is imported -- after the ``app.forecast``,
#: ``app.outlook`` and ``app.dirdef`` modules it runs were imported.
LOADED: Provenance = load_provenance()


# --- the entry ----------------------------------------------------------------------------


class BenchmarkLoader[R](Protocol):
    """The shape of ``app.services.index.load_market_benchmark``."""

    def __call__(
        self, resolver: R, *, market: Market, start: date, end: date
    ) -> IndexSeriesAnswer: ...


@dataclass(frozen=True)
class RunResult:
    """What a run wrote to ``forecast_run_end`` (no label, no rule detail)."""

    run_id: int
    outcome: RunOutcome
    candidate_t: date | None
    records_written: int
    error_class: str | None


@dataclass
class _Progress:
    candidate_t: date | None = None
    records_written: int = 0


@dataclass(frozen=True)
class RecordingClaim:
    """A recording claim with the rule set and definition its hashes were checked against."""

    claim: ClaimRow
    ruleset: OutlookRuleSet
    definition: DirectionDefinition


@dataclass(frozen=True)
class _Stop:
    """A run that ends before writing a record, with its outcome and gate error."""

    outcome: RunOutcome
    error: BaseException | None = None


@dataclass(frozen=True)
class _Captured:
    snapshot: MarketSnapshot | None
    dropped: tuple[DroppedRow, ...]
    settling: tuple[date, ...]


def record_forecasts[R](
    store: ForecastStore, *, load_benchmark: BenchmarkLoader[R], resolver: R
) -> RunResult:
    """Run job ``forecast_record`` once (steps 1-6 of the module docstring)."""
    run_id = store.begin_run(
        code_commit=LOADED.code_commit, code_digest=LOADED.code_digest, runtime=LOADED.runtime
    )
    progress = _Progress()
    try:
        stop = _run(store, run_id, load_benchmark, resolver, progress)
    except Exception as exc:
        store.end_run(
            run_id,
            outcome="error",
            candidate_t=progress.candidate_t,
            records_written=progress.records_written,
            error=exc,
        )
        return RunResult(
            run_id=run_id,
            outcome="error",
            candidate_t=progress.candidate_t,
            records_written=progress.records_written,
            error_class=exception_class_name(exc),
        )
    store.end_run(
        run_id,
        outcome=stop.outcome,
        candidate_t=progress.candidate_t,
        records_written=progress.records_written,
        error=stop.error,
    )
    return RunResult(
        run_id=run_id,
        outcome=stop.outcome,
        candidate_t=progress.candidate_t,
        records_written=progress.records_written,
        error_class=None if stop.error is None else exception_class_name(stop.error),
    )


def _run[R](
    store: ForecastStore,
    run_id: int,
    load_benchmark: BenchmarkLoader[R],
    resolver: R,
    progress: _Progress,
) -> _Stop:
    try:
        claims = check_recording_claims(store)
    except WriteGateClosedError as closed:
        return _Stop("gate_closed", closed)
    changed = check_semantics(store, run_id, claims)
    if changed is not None:
        return _Stop("gate_closed", changed)

    now = store.now()
    size = _snapshot_size(claims)
    captured = _fetch(load_benchmark, resolver, now, size)
    if captured.settling:
        captured = _fetch(load_benchmark, resolver, now, size)  # D-3 point 2: once
        if captured.settling:
            progress.candidate_t = max(captured.settling)
            return _Stop("inputs_not_ready")
    snapshot = captured.snapshot
    if snapshot is None:
        return _Stop("inputs_not_ready")
    progress.candidate_t = snapshot.data_as_of
    pending = [rc for rc in claims if not store.has_record(rc.claim.claim_id, snapshot.data_as_of)]
    if not pending:
        return _Stop("no_new_session")

    outcomes = [
        (
            rc,
            compute_outlook(
                snapshot, ruleset=rc.ruleset, definition=rc.definition, horizon=rc.claim.horizon
            ),
        )
        for rc in pending
    ]
    series = store.put_input_series(
        bars=[bar.as_mapping() for bar in snapshot.bars],
        source=snapshot.source,
        source_status=snapshot.source_status,
        staleness_minutes=snapshot.staleness_minutes,
        reason=snapshot.reason,
        dropped_rows=[
            {"session_date": row.session_date.isoformat(), "reason": row.reason}
            for row in captured.dropped
        ],
        raw_timestamp_available=snapshot.raw_timestamp_available,
    )
    for rc, outcome in outcomes:
        store.write_record(
            run_id=run_id,
            claim_id=rc.claim.claim_id,
            **_record_content(outcome),
            input_series_sha256=series,
        )
        progress.records_written += 1
    return _Stop("ok")


# --- step 2: CG-2 -------------------------------------------------------------------------


def _gate_closed() -> WriteGateClosedError:
    return WriteGateClosedError(failed_gates=("CG-2",))


def check_recording_claims(store: ForecastStore) -> tuple[RecordingClaim, ...]:
    """The D-6 CG-2 run-time check; ``WriteGateClosedError`` (CG-2) when it does not hold.

    For each core ``(scope_kind, horizon)`` the last-registered forward claim
    is the recording claim -- exactly two of them; each one's rule and
    definition hashes equal what ``app.forecast.definitions`` returns; every
    other forward claim is named by the ``replaces_claim_id`` of a row
    registered after it.
    """
    forward = store.forward_claims()
    recording = store.recording_claims()
    if set(recording) != {(SCOPE_KIND, horizon) for horizon in CORE_HORIZONS}:
        raise _gate_closed()
    recording_ids = {claim.claim_id for claim in recording.values()}
    for index, claim in enumerate(forward):
        if claim.claim_id in recording_ids:
            continue
        if not any(later.replaces_claim_id == claim.claim_id for later in forward[index + 1 :]):
            raise _gate_closed()
    checked: list[RecordingClaim] = []
    for horizon in CORE_HORIZONS:
        claim = recording[(SCOPE_KIND, horizon)]
        if claim.scope_key != SCOPE_KEY or claim.kind != CLAIM_KIND:
            raise _gate_closed()
        try:
            definition = get_definition(claim.definition_version)
            ruleset = get_ruleset(claim.rules_version)
            entry = get_ruleset_entry(claim.rules_version)
        except (UnpublishedVersionError, PublishedVersionRejectedError):
            raise _gate_closed() from None
        if (
            entry.horizon != claim.horizon
            or entry.rules_sha256 != claim.rules_sha256
            or rules_logic_sha256(ruleset) != claim.rules_logic_sha256
            or definition_sha256(definition) != claim.definition_sha256
            or definition_logic_sha256(definition) != claim.definition_logic_sha256
        ):
            raise _gate_closed()
        checked.append(RecordingClaim(claim=claim, ruleset=ruleset, definition=definition))
    return tuple(checked)


# --- step 3: cross-commit ------------------------------------------------------------------


def _differs(run: RunRow | None) -> bool:
    """Whether ``run`` is missing or ran another program or runtime than this process."""
    return (
        run is None
        or run.code_digest != LOADED.code_digest
        or run.runtime_json != LOADED.runtime_json
    )


def check_semantics(
    store: ForecastStore, run_id: int, claims: Sequence[RecordingClaim]
) -> SemanticsChanged | None:
    """D-5 point 6: ``SemanticsChanged`` when the current program does not reproduce the ledger.

    The comparison baseline is supplement 3 (revised) point 1: (i) the latest
    run before this one and (ii) the latest passed run -- outcome ``ok``,
    ``no_new_session`` or ``inputs_not_ready``; ``gate_closed``, ``error`` and
    a run without an end row are never (ii). When this run's ``code_digest`` or
    ``runtime_json`` differs from either, or there is no passed run at all,
    every stored record of each recording claim is recomputed. So a
    ``gate_closed`` or ``error`` run under new code does not make the next run
    under that code skip the check.
    """
    previous = store.latest_run_before(run_id)
    passed = store.latest_run_before(run_id, outcomes=CHECKED_OUTCOMES)
    if not (_differs(previous) or _differs(passed)):
        return None
    checked = 0
    differing = 0
    for recording in claims:
        for row in store.stored_records(recording.claim.claim_id):
            checked += 1
            if not _reproduces(store, recording, row):
                differing += 1
    if differing:
        return SemanticsChanged(records_checked=checked, records_differing=differing)
    return None


def _reproduces(store: ForecastStore, recording: RecordingClaim, row: Mapping[str, object]) -> bool:
    """Whether recomputing ``row`` from its stored snapshot gives the same bytes."""
    stored = store.snapshot(str(row["input_series_sha256"]))
    try:
        outcome = compute_outlook(
            _market_snapshot(stored),
            ruleset=recording.ruleset,
            definition=recording.definition,
            horizon=recording.claim.horizon,
        )
        expected = store.expected_record_columns(
            claim_id=recording.claim.claim_id,
            **_record_content(outcome),
            input_series_sha256=stored.content_sha256,
        )
    except (ValueError, ArithmeticError):
        # The current program refuses or cannot compute what it once wrote.
        return False
    return expected["data_as_of"] == row["data_as_of"] and all(
        expected[name] == row[name] for name in RECOMPUTED_COLUMNS
    )


def _market_snapshot(stored: StoredSnapshot) -> MarketSnapshot:
    """A stored snapshot as the computation reads it (the canonical text read back)."""
    bars = tuple(
        SnapshotBar(
            session_date=date.fromisoformat(str(bar["session_date"])),
            open=Decimal(str(bar["open"])),
            high=Decimal(str(bar["high"])),
            low=Decimal(str(bar["low"])),
            close=Decimal(str(bar["close"])),
            volume=int(str(bar["volume"])),
            source=str(bar["source"]),
            as_of=datetime.fromisoformat(str(bar["as_of"])),
            fetched_at=datetime.fromisoformat(str(bar["fetched_at"])),
        )
        for bar in stored.bars
    )
    return MarketSnapshot(
        bars=bars,
        source=stored.source,
        source_status=stored.source_status,
        staleness_minutes=stored.staleness_minutes,
        reason=stored.reason,
        dropped=(),
        raw_timestamp_available=stored.raw_timestamp_available,
    )


# --- steps 4-6 -----------------------------------------------------------------------------


def _snapshot_size(claims: Sequence[RecordingClaim]) -> int:
    """N_SNAPSHOT for the recording claims: one snapshot serves both (D-5 point 1)."""
    rulesets = [recording.ruleset for recording in claims]
    return max(
        n_snapshot(definition=recording.definition, rulesets=rulesets) for recording in claims
    )


def _settling(rows: Sequence[DroppedRow], now: datetime) -> tuple[date, ...]:
    """Supplement 2 point 2 (a): sessions whose publish cutoff ``now`` has reached.

    ``is_final(market, S, now)`` holds exactly when ``now`` is at or after S's
    publish cutoff in the market clock -- the CS-17 comparison, not a copy.
    """
    return tuple(
        row.session_date for row in rows if is_final(SNAPSHOT_MARKET, row.session_date, now)
    )


def _fetch[R](
    load_benchmark: BenchmarkLoader[R], resolver: R, now: datetime, size: int
) -> _Captured:
    """One call of the loader, captured and split (supplement 2 points 1-2)."""
    run_date = now.astimezone(_TAIPEI).date()
    start = run_date - timedelta(days=FETCH_CALENDAR_DAYS + FETCH_SLACK_DAYS)
    answer = load_benchmark(resolver, market=MARKET, start=start, end=run_date)
    dropped = non_final_rows(answer)
    return _Captured(
        snapshot=capture_market_snapshot(answer, size=size),
        dropped=dropped,
        settling=_settling(dropped, now),
    )


class _Content(TypedDict):
    data_as_of: date
    label: Label
    range_basis: str | None
    missing: Sequence[MissingItem]
    evidence: Mapping[str, object]
    band_def: Mapping[str, object]
    base_close: Decimal
    baseline_predictions: Mapping[str, object]


def _record_content(outcome: OutlookOutcome) -> _Content:
    """The content keyword arguments of ``write_record`` / ``expected_record_columns``."""
    evaluation = outcome.evaluation
    return {
        "data_as_of": outcome.data_as_of,
        "label": evaluation.label,
        "range_basis": evaluation.range_basis,
        "missing": evaluation.missing,
        "evidence": evaluation.evidence,
        "band_def": evaluation.band_def,
        "base_close": outcome.base_close,
        "baseline_predictions": outcome.baseline_predictions,
    }
