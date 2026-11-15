"""Job ``forecast_record`` (``app/forecast/recorder.py``; ADR-0030 D-1 point 3, D-2, D-3, D-5, D-6).

Every ledger is a ``tmp_path`` file and every clock an injected ``FakeClock``.
The index answer comes from the real ``app.services.index.load_market_benchmark``
over a fake price service holding synthetic bars (freeze pack 2.10 FX-B closes
on consecutive weekdays): no network, no service database, no real ``^TWII``
value. The rule sets are the landed h3 / h5 files and the definition the G7
stand-in, registered for each test only (K-11: the production registries stay
empty).

Covered: every outcome once; no end row on interruption; the first write
before any market read; CG-2's positive case and each counter-example; the
cross-commit check (a label-changing byte, a byte that changes nothing, a
runtime change, no change, and the run after a ``gate_closed`` one);
supplement 2 S-4a ((a) re-fetch once then ``inputs_not_ready``; (b) the
LA-G2-5 clock premise and the unchanged ``content_hash``; ``fetched_at ==
as_of`` in the stored snapshot); the ``late`` boundary (23:59:59.999999 and
00:00:00); K-4, K-10 and the S-4a call-site rule.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import logging
import operator
import shutil
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.dirdef.definition import DirectionDefinition
from app.dirdef.registry import PublishedRuleset
from app.dirdef.rules import rules_logic_sha256
from app.forecast import definitions
from app.forecast import recorder as recorder_module
from app.forecast import store as store_module
from app.forecast.canonical import APP_ROOT, code_digest, code_digest_files
from app.forecast.recorder import (
    LOADED,
    BenchmarkLoader,
    Provenance,
    RunResult,
    check_recording_claims,
    load_provenance,
    record_forecasts,
)
from app.forecast.store import ForecastStore, ForecastStoreError, SnapshotInput, StoredSnapshot
from app.outlook import engine
from app.outlook.inputs import late_cutoff_at
from app.services.index import IndexServiceResolver, LoadedBenchmark, load_market_benchmark
from tests.dirdef_helpers import DIRDEF_V1_0_G7
from tests.forecast_ledger_helpers import FakeClock, file_ledger, publish_definition
from tests.forecast_ledger_helpers import bar as ledger_bar
from tests.import_graph import executed_app_modules, offenders, reachable_app_modules
from tests.outlook_helpers import (
    FIXTURES,
    TAIPEI,
    FakeIndexService,
    closes_from_logs,
    definition,
    price_bar,
    rule_bytes,
    ruleset,
)

#: Static check (mypy): the production loader has the shape the entry takes.
_LOADER: BenchmarkLoader[IndexServiceResolver] = load_market_benchmark

T = date(2026, 11, 12)  # a Thursday
NEXT = date(2026, 11, 13)  # the Friday after it
H3 = "outlook-market-v1.0-h3"
H5 = "outlook-market-v1.0-h5"

TIME_PARAMS = frozenset(
    {"t", "T", "as_of", "data_as_of", "decision_date", "clock", "now", "today", "when"}
)


def _sessions_ending(last: date, count: int) -> list[date]:
    days: list[date] = []
    day = last
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return list(reversed(days))


_FXB = closes_from_logs(FIXTURES["FX-B"])
#: 316 synthetic closes: FX-B ending on T, then one more session (NEXT).
CLOSES = [*_FXB, _FXB[-1] * 1.002]
SESSIONS = _sessions_ending(NEXT, len(CLOSES))
assert SESSIONS[-2] == T


def at(day: date, hour: int, minute: int = 0, second: int = 0, micro: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, micro, tzinfo=TAIPEI)


def series(*, until: date = NEXT, stamps: Mapping[date, datetime] | None = None) -> list[PriceBar]:
    """The synthetic bars up to ``until``, each stamped 20:00 on its session unless given."""
    stamps = stamps or {}
    return [
        price_bar(day, Decimal(close), stamps.get(day, at(day, 20)))
        for day, close in zip(SESSIONS, CLOSES, strict=True)
        if day <= until
    ]


class SequencedService(FakeIndexService):
    """Serves one bar list per call, then keeps serving the last one."""

    def __init__(self, *answers: Sequence[PriceBar]) -> None:
        super().__init__(answers[0])
        self.answers = [list(answer) for answer in answers]

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        self.bars = self.answers[min(len(self.calls), len(self.answers) - 1)]
        return super().get_daily_bars(symbol, market, start, end)


def _definition_like(**overrides: Any) -> DirectionDefinition:
    return DirectionDefinition.model_validate({**DIRDEF_V1_0_G7, **overrides})


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def publish(
    monkeypatch: pytest.MonkeyPatch,
    *,
    defn: DirectionDefinition | None = None,
    rulesets: Mapping[str, PublishedRuleset] | None = None,
) -> None:
    """Register the definition and the rule sets in ``app.forecast.definitions`` (test only)."""
    publish_definition(monkeypatch, defn or definition())
    entries = rulesets
    if entries is None:
        entries = {
            H3: PublishedRuleset(horizon=3, rules_sha256=_sha(rule_bytes(3))),
            H5: PublishedRuleset(horizon=5, rules_sha256=_sha(rule_bytes(5))),
        }
    monkeypatch.setattr(definitions, "PUBLISHED_RULESETS", MappingProxyType(dict(entries)))
    monkeypatch.setattr(definitions, "_RULESET_CACHE", {})


class Desk:
    """A ``tmp_path`` ledger with an injected clock and the two core claims registered."""

    def __init__(
        self, root: Path, monkeypatch: pytest.MonkeyPatch, *, register: bool = True
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.path = file_ledger(root)
        self.clock = FakeClock(at(date(2026, 10, 1), 9))
        self.store = ForecastStore(self.path, clock=self.clock)
        self.monkeypatch = monkeypatch
        publish(monkeypatch)
        self.service: FakeIndexService | None = None
        if register:
            self.h3 = self.register(3)
            self.h5 = self.register(5)

    def register(self, horizon: int, **overrides: Any) -> str:
        self.clock.advance(seconds=1)
        kwargs: dict[str, Any] = {
            "horizon": horizon,
            "rules_version": H3 if horizon == 3 else H5,
            "rules_bytes": rule_bytes(horizon),
            "rules_logic_sha256": rules_logic_sha256(ruleset(horizon)),
            "definition": definition(),
            "frozen_commit": "abc123",
            "prereg_doc_path": "docs/prereg-v0.32.md",
            "prereg_doc_blob": b"prereg",
            "review_refs": "work/reviews/x.md",
            "replaces_claim_id": None,
            "replace_reason": None,
            "provisional_results_seen": False,
        }
        kwargs.update(overrides)
        return self.store.register_claim(**kwargs)

    def run(
        self,
        now: datetime,
        bars: Sequence[PriceBar] | None = None,
        *,
        service: FakeIndexService | None = None,
    ) -> RunResult:
        self.clock.now = now
        self.service = service or FakeIndexService(series() if bars is None else bars)
        resolver: IndexServiceResolver = {"TW": self.service}
        return record_forecasts(self.store, load_benchmark=load_market_benchmark, resolver=resolver)

    def rows(self, table: str) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]

    def count(self, table: str) -> int:
        return len(self.rows(table))


@pytest.fixture
def desk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Desk:
    return Desk(tmp_path, monkeypatch)


EVENING = at(T, 22, 10)


def _end(desk: Desk, run_id: int) -> dict[str, Any]:
    (row,) = [r for r in desk.rows("forecast_run_end") if r["run_id"] == run_id]
    return row


# --- ok ----------------------------------------------------------------------------------


def test_ok_writes_one_record_per_recording_claim_from_one_snapshot(desk: Desk) -> None:
    result = desk.run(EVENING)
    assert result.outcome == "ok"
    assert (result.candidate_t, result.records_written, result.error_class) == (T, 2, None)
    end = _end(desk, result.run_id)
    assert (end["outcome"], end["candidate_t"], end["records_written"]) == ("ok", "2026-11-12", 2)
    assert end["error_class"] is None
    records = desk.rows("forecast_record")
    assert [r["claim_id"] for r in records] == [desk.h3, desk.h5]
    assert {r["data_as_of"] for r in records} == {"2026-11-12"}
    assert {r["late"] for r in records} == {0}
    (snapshot,) = desk.rows("forecast_input_series")
    # D-4 point 1: the model and the four baselines of both records read one snapshot.
    assert {r["input_series_sha256"] for r in records} == {snapshot["content_sha256"]}
    for record in records:
        assert set(json.loads(record["baseline_predictions_json"])) == {"B1", "B2", "B6", "B8"}
    bars = json.loads(snapshot["bars_json"])
    assert len(bars) == 315 and bars[-1]["session_date"] == "2026-11-12"
    # Supplement 2 point 3 / S-4a: one retrieval stamp per bar.
    assert all(bar["fetched_at"] == bar["as_of"] for bar in bars)
    assert snapshot["raw_timestamp_available"] == 0
    assert json.loads(snapshot["dropped_rows_json"]) == []


def test_the_run_row_carries_the_loaded_provenance(desk: Desk) -> None:
    result = desk.run(EVENING)
    (run,) = desk.rows("forecast_run")
    assert run["run_id"] == result.run_id and run["trigger"] == "scheduled"
    assert run["code_digest"] == LOADED.code_digest == code_digest()
    assert run["runtime_json"] == LOADED.runtime_json
    runtime = json.loads(run["runtime_json"])
    assert set(runtime) == {
        "python_version",
        "python_implementation",
        "python_build",
        "platform",
        "machine",
        "lockfile_sha256",
    }
    assert runtime["lockfile_sha256"] == _sha((APP_ROOT.parent / "uv.lock").read_bytes())


def test_the_loader_is_called_with_the_market_and_a_500_day_window(desk: Desk) -> None:
    desk.run(EVENING)
    assert desk.service is not None
    ((symbol, market, start, end),) = desk.service.calls
    assert (symbol, market, end) == ("^TWII", "TW", T)
    assert (T - start).days >= 500


def test_the_first_write_precedes_every_market_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = Desk(tmp_path, monkeypatch)
    seen: list[tuple[int, int, int, int]] = []

    def loader(resolver: IndexServiceResolver, *, market: Market, start: date, end: date) -> Any:
        seen.append(
            (
                desk.count("forecast_run"),
                desk.count("forecast_run_end"),
                desk.count("forecast_input_series"),
                desk.count("forecast_record"),
            )
        )
        return load_market_benchmark(resolver, market=market, start=start, end=end)

    desk.clock.now = EVENING
    resolver: IndexServiceResolver = {"TW": FakeIndexService(series())}
    result = record_forecasts(desk.store, load_benchmark=loader, resolver=resolver)
    assert result.outcome == "ok"
    assert seen == [(1, 0, 0, 0)]


# --- no_new_session ----------------------------------------------------------------------------


def test_a_second_run_for_the_same_t_is_no_new_session(desk: Desk) -> None:
    desk.run(EVENING)
    before = desk.rows("forecast_record")
    result = desk.run(EVENING + timedelta(hours=1))
    assert (result.outcome, result.candidate_t, result.records_written) == (
        "no_new_session",
        T,
        0,
    )
    end = _end(desk, result.run_id)
    assert (end["outcome"], end["candidate_t"], end["error_class"]) == (
        "no_new_session",
        "2026-11-12",
        None,
    )
    assert desk.rows("forecast_record") == before
    assert desk.count("forecast_input_series") == 1


def test_only_the_claim_without_a_record_for_t_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # h3 is replaced after both claims recorded T: the new h3 claim is the only
    # recording claim without a record for T.
    desk = Desk(tmp_path, monkeypatch)
    assert desk.run(EVENING).records_written == 2
    _publish_with_v11(monkeypatch)
    newer = desk.register(
        3,
        rules_version="outlook-market-v1.1-h3",
        replaces_claim_id=desk.h3,
        replace_reason="test replacement",
    )
    second = desk.run(EVENING + timedelta(minutes=30))
    assert (second.outcome, second.records_written) == ("ok", 1)
    assert [r["claim_id"] for r in desk.rows("forecast_record")] == [desk.h3, desk.h5, newer]
    assert desk.count("forecast_input_series") == 1  # the same content, stored once


# --- supplement 3 (revised) point 7: one transaction per run (f2) --------------------------------


def test_s12a_a_failing_second_record_rolls_back_the_whole_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = Desk(tmp_path, monkeypatch)
    # Both records get one forecast_id: the second INSERT is refused by the
    # forecast_record_no_replace trigger, inside the run's one transaction.
    monkeypatch.setattr(store_module, "new_ulid", lambda at: "01JCZ0000000000000000000AB")
    first = desk.run(EVENING)
    assert (first.outcome, first.records_written, first.error_class) == (
        "error",
        0,
        "IntegrityError",
    )
    end = _end(desk, first.run_id)
    assert (end["outcome"], end["records_written"]) == ("error", 0)
    assert desk.count("forecast_input_series") == 0
    assert desk.count("forecast_record") == 0


def test_s12a_the_next_run_after_a_rolled_back_one_writes_both_from_one_snapshot(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = store_module.new_ulid
    calls: list[int] = []

    def second_fails(at: datetime, *args: Any) -> str:
        calls.append(1)
        if len(calls) == 2:
            raise sqlite3.OperationalError("disk I/O error")
        return real(at, *args)

    monkeypatch.setattr(store_module, "new_ulid", second_fails)
    first = desk.run(EVENING)
    assert (first.outcome, first.records_written) == ("error", 0)
    assert desk.count("forecast_record") == 0 and desk.count("forecast_input_series") == 0
    later = desk.run(EVENING + timedelta(minutes=30))
    assert (later.outcome, later.records_written) == ("ok", 2)
    (snapshot,) = desk.rows("forecast_input_series")
    records = desk.rows("forecast_record")
    assert [r["claim_id"] for r in records] == [desk.h3, desk.h5]
    assert {r["input_series_sha256"] for r in records} == {snapshot["content_sha256"]}


def test_s12a_the_batch_refuses_an_empty_or_foreign_record_list(desk: Desk) -> None:
    run_id = desk.store.begin_run(code_commit="c", code_digest="d" * 64, runtime={})
    snapshot = SnapshotInput(
        bars=[ledger_bar(T)],
        source="yfinance",
        source_status="backup",
        staleness_minutes=0,
        reason=None,
        dropped_rows=None,
        raw_timestamp_available=False,
    )
    bad: Any = object()
    with pytest.raises(ForecastStoreError, match="snapshot must be a SnapshotInput"):
        desk.store.write_run_records(run_id=run_id, snapshot=bad, records=[])
    cases: list[tuple[Any, str]] = [([], "non-empty"), ("x", "non-empty"), ([bad], "RecordInput")]
    for records, match in cases:
        with pytest.raises(ForecastStoreError, match=match):
            desk.store.write_run_records(run_id=run_id, snapshot=snapshot, records=records)
    assert desk.count("forecast_input_series") == 0


# --- inputs_not_ready: supplement 2 point 2 (a) -----------------------------------------------


def test_a_non_final_t_bar_after_its_cutoff_is_refetched_once_then_not_ready(desk: Desk) -> None:
    # 22:10 on T, and T's bar is still the copy fetched at 14:00 (not final).
    bars = series(until=T, stamps={T: at(T, 14)})
    result = desk.run(EVENING, bars)
    assert (result.outcome, result.candidate_t, result.records_written) == (
        "inputs_not_ready",
        T,
        0,
    )
    assert desk.service is not None and len(desk.service.calls) == 2
    assert desk.count("forecast_record") == 0
    assert desk.count("forecast_input_series") == 0  # not the previous day either
    assert _end(desk, result.run_id)["candidate_t"] == "2026-11-12"


def test_a_refetch_that_brings_the_final_bar_records_t(desk: Desk) -> None:
    service = SequencedService(series(until=T, stamps={T: at(T, 14)}), series(until=T))
    result = desk.run(EVENING, service=service)
    assert (result.outcome, result.candidate_t, result.records_written) == ("ok", T, 2)
    assert len(service.calls) == 2


def test_after_the_next_day_cutoff_a_non_final_next_bar_is_not_ready(desk: Desk) -> None:
    # TA SP-C counter-example: the clock is past NEXT's 15:00 and NEXT's bar stays
    # non-final after the re-fetch -> inputs_not_ready, T is not moved back.
    bars = series(until=NEXT, stamps={NEXT: at(NEXT, 10)})
    result = desk.run(at(NEXT, 22, 10), bars)
    assert (result.outcome, result.candidate_t) == ("inputs_not_ready", NEXT)
    assert desk.service is not None and len(desk.service.calls) == 2
    assert desk.count("forecast_record") == 0


def test_an_older_non_final_bar_is_not_ready_with_its_session(desk: Desk) -> None:
    # A gap inside the series (qa low, 2026-11-15): never a snapshot with a hole.
    hole = SESSIONS[-10]
    bars = series(until=T, stamps={hole: at(hole, 13)})
    result = desk.run(EVENING, bars)
    assert (result.outcome, result.candidate_t) == ("inputs_not_ready", hole)
    assert desk.count("forecast_record") == 0


def test_no_bar_at_all_is_not_ready_without_a_candidate(desk: Desk) -> None:
    result = desk.run(EVENING, [])
    assert (result.outcome, result.candidate_t, result.records_written) == (
        "inputs_not_ready",
        None,
        0,
    )
    assert desk.service is not None and len(desk.service.calls) == 1
    assert _end(desk, result.run_id)["candidate_t"] is None


# --- supplement 3 (revised) point 4: no final bar (S-12a) ----------------------------------------


def test_s12a_only_settling_bars_is_not_ready_with_the_largest_session(desk: Desk) -> None:
    # Every bar the loader returns is (a): non-final with its publish cutoff passed.
    early = SESSIONS[-3]
    bars = [
        price_bar(day, Decimal(close), at(day, 14))
        for day, close in zip(SESSIONS, CLOSES, strict=True)
        if early <= day <= T
    ]
    assert len(bars) == 2 and bars[-1].date == T
    result = desk.run(EVENING, bars)
    assert (result.outcome, result.candidate_t, result.records_written) == (
        "inputs_not_ready",
        T,
        0,
    )
    assert desk.service is not None and len(desk.service.calls) == 2  # re-fetched once
    assert _end(desk, result.run_id)["candidate_t"] == T.isoformat()
    assert desk.count("forecast_input_series") == 0 and desk.count("forecast_record") == 0


def test_s12a_only_bars_before_their_cutoff_is_not_ready_without_a_candidate(desk: Desk) -> None:
    # The loader returns one (b) bar and nothing final: no T, no (a) bar.
    morning = at(NEXT, 10, 5)
    result = desk.run(morning, [price_bar(NEXT, Decimal(CLOSES[-1]), at(NEXT, 10))])
    assert (result.outcome, result.candidate_t, result.records_written) == (
        "inputs_not_ready",
        None,
        0,
    )
    assert desk.service is not None and len(desk.service.calls) == 1
    assert _end(desk, result.run_id)["candidate_t"] is None
    assert desk.count("forecast_input_series") == 0


# --- supplement 3 (revised) point 5: source_status is recorded, never branched on -------------


def _status_loader(status: DataStatus) -> Any:
    """A loader answering the synthetic bars with ``status`` (the service layer bypassed)."""

    def loader(resolver: Any, *, market: Market, start: date, end: date) -> LoadedBenchmark:
        return LoadedBenchmark(
            series_symbol="^TWII",
            label="TAIEX",
            bars=[b for b in series(until=T) if start <= b.date <= end],
            status=status,
            source="yfinance",
            staleness_minutes=0,
            reason=None,
        )

    return loader


POINT5_COLUMNS = ("data_as_of", "label", "band_def", "baseline_predictions_json", "missing_json")


def test_s12a_the_four_data_statuses_give_the_same_record_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, tuple[object, ...]] = {}
    for status in DataStatus:
        desk = Desk(tmp_path / status.value, monkeypatch)
        desk.clock.now = EVENING
        result = record_forecasts(desk.store, load_benchmark=_status_loader(status), resolver={})
        assert (result.outcome, result.candidate_t, result.records_written) == ("ok", T, 2)
        (snapshot,) = desk.rows("forecast_input_series")
        assert snapshot["source_status"] == status.value  # recorded as it came
        seen[status.value] = (
            result.candidate_t,
            *(tuple(r[c] for c in POINT5_COLUMNS) for r in desk.rows("forecast_record")),
        )
    assert len(seen) == 4
    assert len(set(seen.values())) == 1


def _status_branches(source: str) -> list[str]:
    """Branch conditions that read ``source_status`` or an answer's ``status``.

    ``MissingItem``'s own ``self.source_status`` (the D-13 missing-item field,
    ``fetch_failed`` / ``not_yet_published``, not the snapshot's DataStatus) is
    its validator's invariant and is not counted.
    """
    found: list[str] = []

    def reads_status(expr: ast.AST, owner: str | None) -> bool:
        for node in ast.walk(expr):
            if isinstance(node, ast.Name) and node.id in {"source_status", "DataStatus"}:
                return True
            if isinstance(node, ast.Attribute) and node.attr in {"source_status", "status"}:
                own = (
                    owner == "MissingItem"
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                    and node.attr == "source_status"
                )
                if not own:
                    return True
        return False

    def visit(node: ast.AST, owner: str | None) -> None:
        if isinstance(node, ast.ClassDef):
            owner = node.name
        tests: list[ast.AST] = []
        if isinstance(node, ast.If | ast.IfExp | ast.While | ast.Assert):
            tests.append(node.test)
        elif isinstance(node, ast.comprehension):
            tests.extend(node.ifs)
        elif isinstance(node, ast.Match):
            tests.append(node.subject)
        elif isinstance(node, ast.match_case) and node.guard is not None:
            tests.append(node.guard)
        elif isinstance(node, ast.BoolOp):
            tests.extend(node.values)
        found.extend(ast.unparse(test) for test in tests if reads_status(test, owner))
        for child in ast.iter_child_nodes(node):
            visit(child, owner)

    visit(ast.parse(source), None)
    return found


def test_s12a_source_status_is_no_branch_condition_in_the_recorder_or_the_outlook() -> None:
    paths = [APP_ROOT / "forecast" / "recorder.py", *sorted((APP_ROOT / "outlook").rglob("*.py"))]
    violations = {
        path.relative_to(APP_ROOT).as_posix(): found
        for path in paths
        if (found := _status_branches(path.read_text(encoding="utf-8")))
    }
    assert violations == {}


@pytest.mark.parametrize(
    "source",
    [
        "if snapshot.source_status != 'backup':\n    pass\n",
        "x = 1 if answer.status is DataStatus.FRESH else 2\n",
        "while source_status:\n    pass\n",
        "ok = [b for b in bars if answer.status == 'fresh']\n",
        "ready = done and snapshot.source_status == 'fresh'\n",
        "match answer.status:\n    case _:\n        pass\n",
        "assert snapshot.source_status\n",
        "class MissingItem:\n    def f(self, other):\n"
        "        if other.source_status:\n            pass\n",
        "class Other:\n    def f(self):\n        if self.source_status:\n            pass\n",
    ],
)
def test_the_status_branch_scan_has_teeth(source: str) -> None:
    assert _status_branches(source) != []


def test_the_status_branch_scan_lets_recording_and_the_missing_item_through() -> None:
    assert _status_branches("row = {'source_status': answer.status.value}\n") == []
    assert (
        _status_branches(
            "class MissingItem:\n    def f(self):\n        if self.source_status is None:\n"
            "            pass\n"
        )
        == []
    )


# --- supplement 2 point 2 (b): LA-G2-5 with its clock premise ----------------------------------


def test_la_g2_5_a_next_day_bar_before_its_cutoff_is_dropped_and_leaves_the_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    morning = at(NEXT, 10, 5)  # premise: the clock is before NEXT's 15:00
    assert morning < at(NEXT, 15)
    early = {NEXT: at(NEXT, 10)}
    with_bar = Desk(tmp_path / "with", monkeypatch)
    result = with_bar.run(morning, series(until=NEXT, stamps=early))
    without = Desk(tmp_path / "without", monkeypatch)
    plain = without.run(morning, series(until=T))
    assert (result.outcome, result.candidate_t) == ("ok", T)
    assert (plain.outcome, plain.candidate_t) == ("ok", T)
    assert with_bar.service is not None and len(with_bar.service.calls) == 1
    (snapshot,) = with_bar.rows("forecast_input_series")
    assert json.loads(snapshot["dropped_rows_json"]) == [
        {"reason": "not_final", "session_date": "2026-11-13"}
    ]
    assert json.loads(snapshot["bars_json"])[-1]["session_date"] == "2026-11-12"
    hashes = [r["content_hash"] for r in with_bar.rows("forecast_record")]
    assert hashes == [r["content_hash"] for r in without.rows("forecast_record")]
    assert {r["late"] for r in with_bar.rows("forecast_record")} == {1}


# --- late boundary (D-3 point 3) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "late"),
    [
        pytest.param(at(T, 23, 59, 59, 999999), 0, id="23:59:59.999999"),
        pytest.param(at(NEXT, 0), 1, id="00:00:00"),
    ],
)
def test_late_at_the_cutoff_boundary(desk: Desk, now: datetime, late: int) -> None:
    result = desk.run(now, series(until=T))
    assert result.outcome == "ok"
    records = desk.rows("forecast_record")
    assert {r["late"] for r in records} == {late}
    assert {r["late_cutoff_at"] for r in records} == {
        late_cutoff_at(T).isoformat(timespec="microseconds")
    }
    assert {r["label"] for r in records} != {"insufficient"}


# --- gate_closed: CG-2 (D-6) --------------------------------------------------------------------


def _closed(desk: Desk) -> None:
    result = desk.run(EVENING)
    assert (result.outcome, result.error_class) == ("gate_closed", "WriteGateClosedError")
    assert (result.candidate_t, result.records_written) == (None, 0)
    end = _end(desk, result.run_id)
    assert (end["outcome"], end["error_class"]) == ("gate_closed", "WriteGateClosedError")
    assert desk.service is not None and desk.service.calls == []  # no market read
    assert desk.count("forecast_record") == 0
    assert desk.count("forecast_input_series") == 0


def test_cg2_no_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _closed(Desk(tmp_path, monkeypatch, register=False))


@pytest.mark.parametrize("horizon", [3, 5])
def test_cg2_one_claim_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, horizon: int) -> None:
    desk = Desk(tmp_path, monkeypatch, register=False)
    desk.register(horizon)
    _closed(desk)


def _publish_with_v11(monkeypatch: pytest.MonkeyPatch, data: bytes | None = None) -> None:
    publish(
        monkeypatch,
        rulesets={
            H3: PublishedRuleset(horizon=3, rules_sha256=_sha(rule_bytes(3))),
            H5: PublishedRuleset(horizon=5, rules_sha256=_sha(rule_bytes(5))),
            "outlook-market-v1.1-h3": PublishedRuleset(
                horizon=3, rules_sha256=_sha(data or rule_bytes(3))
            ),
        },
    )


def test_cg2_a_later_claim_without_replacement_leaves_one_unreplaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = Desk(tmp_path, monkeypatch)
    _publish_with_v11(monkeypatch)
    desk.register(3, rules_version="outlook-market-v1.1-h3")
    _closed(desk)


def test_cg2_a_replaced_claim_is_not_recorded_and_the_gate_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = Desk(tmp_path, monkeypatch)
    _publish_with_v11(monkeypatch)
    newer = desk.register(
        3,
        rules_version="outlook-market-v1.1-h3",
        replaces_claim_id=desk.h3,
        replace_reason="test replacement",
    )
    assert {c.claim.claim_id for c in check_recording_claims(desk.store)} == {newer, desk.h5}
    result = desk.run(EVENING)
    assert result.outcome == "ok"
    assert [r["claim_id"] for r in desk.rows("forecast_record")] == [newer, desk.h5]


def test_cg2_the_recording_claims_carry_their_checked_objects(desk: Desk) -> None:
    checked = check_recording_claims(desk.store)
    assert [c.claim.horizon for c in checked] == [3, 5]
    assert [c.ruleset for c in checked] == [ruleset(3), ruleset(5)]
    assert all(c.definition == definition() for c in checked)


@pytest.mark.parametrize(
    "case",
    [
        "definition-unpublished",
        "ruleset-unpublished",
        "definition-text-changed",
        "definition-logic-changed",
        "rules-bytes-differ",
        "rules-logic-differs",
        "ruleset-published-for-the-other-horizon",
        "rule-file-unreadable",
    ],
)
def test_cg2_hash_counter_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    desk = Desk(
        tmp_path, monkeypatch, register=case not in {"rules-bytes-differ", "rules-logic-differs"}
    )
    if case == "definition-unpublished":
        monkeypatch.setattr(definitions, "PUBLISHED_DIRECTION_DEFINITIONS", MappingProxyType({}))
        monkeypatch.setattr(definitions, "_DEFINITION_CACHE", {})
    elif case == "ruleset-unpublished":
        publish(monkeypatch, rulesets={H5: PublishedRuleset(5, _sha(rule_bytes(5)))})
    elif case == "definition-text-changed":
        publish(monkeypatch, defn=_definition_like(description="another fixture text"))
    elif case == "definition-logic-changed":
        publish(monkeypatch, defn=_definition_like(K3=0.44))
    elif case == "rules-bytes-differ":
        desk.register(3, rules_bytes=rule_bytes(3) + b"# appended\n")
        desk.register(5)
    elif case == "rules-logic-differs":
        desk.register(3, rules_logic_sha256="0" * 64)
        desk.register(5)
    elif case == "ruleset-published-for-the-other-horizon":
        publish(
            monkeypatch,
            rulesets={
                H3: PublishedRuleset(horizon=5, rules_sha256=_sha(rule_bytes(3))),
                H5: PublishedRuleset(horizon=5, rules_sha256=_sha(rule_bytes(5))),
            },
        )
    else:
        monkeypatch.setattr(definitions, "RULES_DIR", tmp_path / "missing")
    _closed(desk)


def test_cg2_a_recording_claim_outside_the_core_scope_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The store's CHECKs keep scope_key = TAIEX; the run-time check does not rely on them.
    desk = Desk(tmp_path, monkeypatch)
    real = desk.store.recording_claims()
    other = {key: replace(claim, scope_key="OTHER") for key, claim in real.items()}
    monkeypatch.setattr(desk.store, "recording_claims", lambda: other)
    _closed(desk)


def test_cg2_a_rules_version_whose_entry_names_another_horizon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Bytes and hashes match, only the registry entry's horizon is wrong.
    desk = Desk(tmp_path, monkeypatch)
    publish(
        monkeypatch,
        rulesets={
            H3: PublishedRuleset(horizon=5, rules_sha256=_sha(rule_bytes(3))),
            H5: PublishedRuleset(horizon=5, rules_sha256=_sha(rule_bytes(5))),
        },
    )
    monkeypatch.setattr(definitions, "_read_rules_bytes", lambda horizon: rule_bytes(3))
    _closed(desk)


# --- CG-2: the replacement chain (supplement 3 (revised) point 6, f1) ---------------------------

OLD_H3 = "market|h3|outlook-market-v0.9-h3|dirdef-v1.0|forward"
MID_H3 = "market|h3|outlook-market-v0.95-h3|dirdef-v1.0|forward"


def _registry(desk: Desk, case: str) -> list[Any]:
    """A registry the store would refuse, built from the two registered (hash-valid) rows.

    Every case keeps "each other forward claim is replaced by a later one", so
    only the chain rule can close the gate (except "twice", see the test).
    """
    h3, h5 = desk.store.forward_claims()
    old = replace(h3, claim_id=OLD_H3)
    if case == "valid":
        return [old, replace(h3, replaces_claim_id=OLD_H3), h5]
    if case == "cross-horizon":  # the h3 claim is replaced by the h5 one
        return [old, h3, replace(h5, replaces_claim_id=OLD_H3)]
    if case == "names-a-later-claim":
        return [
            replace(old, replaces_claim_id=h3.claim_id),
            replace(h3, replaces_claim_id=OLD_H3),
            h5,
        ]
    assert case == "twice"
    mid = replace(h3, claim_id=MID_H3, replaces_claim_id=OLD_H3)
    return [old, mid, replace(h3, replaces_claim_id=OLD_H3), h5]


def test_cg2_a_valid_replacement_chain_opens_the_gate(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = _registry(desk, "valid")
    monkeypatch.setattr(desk.store, "forward_claims", lambda: rows)
    assert desk.run(EVENING).outcome == "ok"


@pytest.mark.parametrize("case", ["cross-horizon", "names-a-later-claim", "twice"])
def test_cg2_a_broken_replacement_chain_closes_the_gate(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    rows = _registry(desk, case)
    assert store_module.replacement_violations(rows) != []
    monkeypatch.setattr(desk.store, "forward_claims", lambda: rows)
    _closed(desk)


# --- error and interruption ---------------------------------------------------------------------


class _Boom(RuntimeError):
    pass


def _raising(exc: BaseException) -> Any:
    def loader(resolver: Any, *, market: Market, start: date, end: date) -> Any:
        raise exc

    return loader


def test_an_exception_ends_the_run_as_error_with_its_class(desk: Desk) -> None:
    desk.clock.now = EVENING
    result = record_forecasts(desk.store, load_benchmark=_raising(_Boom("x")), resolver={})
    assert (result.outcome, result.error_class, result.records_written) == ("error", "_Boom", 0)
    end = _end(desk, result.run_id)
    assert (end["outcome"], end["error_class"]) == ("error", "_Boom")
    assert desk.count("forecast_record") == 0


def test_the_error_class_goes_through_exception_class_name(desk: Desk) -> None:
    weird = type("bad-name", (RuntimeError,), {})
    desk.clock.now = EVENING
    result = record_forecasts(desk.store, load_benchmark=_raising(weird()), resolver={})
    assert result.error_class == "invalid_exception_class"
    assert _end(desk, result.run_id)["error_class"] == "invalid_exception_class"


def test_a_series_of_another_symbol_is_an_error(desk: Desk) -> None:
    result = desk.run(EVENING, [price_bar(T, Decimal("1"), at(T, 20), symbol="^GSPC")])
    assert (result.outcome, result.error_class) == ("error", "SnapshotShapeError")


@pytest.mark.parametrize("exc", [KeyboardInterrupt(), SystemExit(1)], ids=["sigint", "exit"])
def test_an_interrupted_run_has_no_end_row(desk: Desk, exc: BaseException) -> None:
    desk.clock.now = EVENING
    with pytest.raises(type(exc)):
        record_forecasts(desk.store, load_benchmark=_raising(exc), resolver={})
    assert desk.count("forecast_run") == 1
    assert desk.count("forecast_run_end") == 0
    latest = desk.store.latest_run()
    assert latest is not None and latest.outcome is None


# --- gate_closed: cross-commit (D-5 point 6) ----------------------------------------------------


def _tree_copy(tmp_path: Path, edit: tuple[str, str, str] | None = None) -> Path:
    """A copy of the ``code_digest`` sources; ``edit`` = (relative file, old, new) applied once."""
    root = tmp_path / "app"
    for package in ("forecast", "outlook", "dirdef"):
        shutil.copytree(
            APP_ROOT / package, root / package, ignore=shutil.ignore_patterns("__pycache__")
        )
    (root / "data").mkdir(parents=True)
    shutil.copy2(APP_ROOT / "data" / "session_calendar.py", root / "data" / "session_calendar.py")
    if edit is not None:
        name, old, new = edit
        path = root / name
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1
        path.write_text(text.replace(old, new), encoding="utf-8")
    return root


def _as_loaded(monkeypatch: pytest.MonkeyPatch, provenance: Provenance) -> None:
    monkeypatch.setattr(recorder_module, "LOADED", provenance)


def _count_recomputes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    real = recorder_module._reproduces

    def spy(store: ForecastStore, recording: Any, row: Mapping[str, object]) -> bool:
        seen.append(str(row["claim_id"]))
        return real(store, recording, row)

    monkeypatch.setattr(recorder_module, "_reproduces", spy)
    return seen


def test_an_unedited_copy_has_the_loaded_digest(tmp_path: Path) -> None:
    assert load_provenance(_tree_copy(tmp_path)).code_digest == LOADED.code_digest


def test_the_loaded_commit_is_a_sha_or_unknown(tmp_path: Path) -> None:
    commit = LOADED.code_commit
    assert commit == "unknown" or (len(commit) == 40 and not commit.strip("0123456789abcdef"))
    assert recorder_module.code_commit(tmp_path) == "unknown"  # not a checkout
    assert recorder_module.code_commit(tmp_path / "missing") == "unknown"  # no directory


def test_runtime_info_hashes_the_given_lock_file(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_bytes(b"version = 1\n")
    info = recorder_module.runtime_info(lock)
    assert info["lockfile_sha256"] == _sha(b"version = 1\n")
    assert json.loads(Provenance("c", "d" * 64, info).runtime_json) == info


def test_a_label_changing_byte_closes_the_gate(
    desk: Desk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = desk.run(EVENING, series(until=T))
    assert first.outcome == "ok"
    # One byte of engine.py changes: "gt" now compares as "<" -- in the file and
    # in the running program alike.
    tree = _tree_copy(tmp_path, ("outlook/engine.py", '"gt": operator.gt,', '"gt": operator.lt,'))
    _as_loaded(monkeypatch, load_provenance(tree))
    monkeypatch.setitem(engine._OPS, "gt", operator.lt)
    second = desk.run(at(NEXT, 22, 10))
    assert (second.outcome, second.error_class) == ("gate_closed", "SemanticsChanged")
    assert (second.candidate_t, second.records_written) == (None, 0)
    assert desk.service is not None and desk.service.calls == []
    assert [r["data_as_of"] for r in desk.rows("forecast_record")] == ["2026-11-12"] * 2
    # The next run under the same changed program does not skip the check.
    third = desk.run(at(NEXT, 23, 10))
    assert (third.outcome, third.error_class) == ("gate_closed", "SemanticsChanged")
    assert desk.count("forecast_record") == 2


def test_a_byte_that_changes_no_result_keeps_recording(
    desk: Desk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert desk.run(EVENING, series(until=T)).outcome == "ok"
    tree = _tree_copy(
        tmp_path, ("outlook/engine.py", "# --- Rules ---", "# --- Rule evaluation ---")
    )
    changed = load_provenance(tree)
    assert changed.code_digest != LOADED.code_digest
    _as_loaded(monkeypatch, changed)
    recomputed = _count_recomputes(monkeypatch)
    second = desk.run(at(NEXT, 22, 10))
    assert (second.outcome, second.candidate_t, second.records_written) == ("ok", NEXT, 2)
    assert sorted(recomputed) == sorted([desk.h3, desk.h5])
    assert desk.rows("forecast_run")[-1]["code_digest"] == changed.code_digest


def test_a_runtime_change_alone_triggers_the_recomputation(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert desk.run(EVENING, series(until=T)).outcome == "ok"
    runtime = {**LOADED.runtime, "python_version": "3.99.0"}
    _as_loaded(
        monkeypatch,
        Provenance(code_commit=LOADED.code_commit, code_digest=LOADED.code_digest, runtime=runtime),
    )
    recomputed = _count_recomputes(monkeypatch)
    assert desk.run(at(NEXT, 22, 10)).outcome == "ok"
    assert len(recomputed) == 2


def test_the_same_program_skips_the_recomputation(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert desk.run(EVENING, series(until=T)).outcome == "ok"
    recomputed = _count_recomputes(monkeypatch)
    assert desk.run(at(NEXT, 22, 10)).outcome == "ok"
    assert recomputed == []


def test_a_recomputation_the_program_refuses_counts_as_changed(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert desk.run(EVENING, series(until=T)).outcome == "ok"
    _as_loaded(
        monkeypatch,
        Provenance(code_commit="x", code_digest="9" * 64, runtime=LOADED.runtime),
    )

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise engine.OutlookInvariantError("refused")

    monkeypatch.setattr(recorder_module, "compute_outlook", refuse)
    result = desk.run(at(NEXT, 22, 10))
    assert (result.outcome, result.error_class) == ("gate_closed", "SemanticsChanged")


def test_a_ledger_read_failure_during_the_recomputation_is_an_error(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert desk.run(EVENING, series(until=T)).outcome == "ok"
    _as_loaded(
        monkeypatch,
        Provenance(code_commit="x", code_digest="9" * 64, runtime=LOADED.runtime),
    )

    def broken(content_sha256: str) -> Any:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(desk.store, "snapshot", broken)
    result = desk.run(at(NEXT, 22, 10))
    assert (result.outcome, result.error_class) == ("error", "OperationalError")


# --- supplement 3 (revised) point 8: ledger-side vs program-side failures (f3) -----------------


def _under_program_b(desk: Desk, monkeypatch: pytest.MonkeyPatch) -> None:
    assert desk.run(EVENING, series(until=T)).outcome == "ok"
    _as_loaded(monkeypatch, PROGRAM_B)


@pytest.mark.parametrize("case", ["unparsable-bar", "registry-row-gone", "bars-json-unreadable"])
def test_f3_a_ledger_side_failure_is_an_error_with_its_class(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    _under_program_b(desk, monkeypatch)
    if case == "unparsable-bar":
        real = desk.store.snapshot

        def unparsable(content_sha256: str) -> StoredSnapshot:
            stored = real(content_sha256)
            bars = ({**stored.bars[0], "open": "not a number"}, *stored.bars[1:])
            return replace(stored, bars=bars)

        monkeypatch.setattr(desk.store, "snapshot", unparsable)
        expected = "InvalidOperation"
    elif case == "registry-row-gone":

        def vanishing(conn: sqlite3.Connection, claim_id: str) -> None:
            return None

        monkeypatch.setattr(ForecastStore, "_claim", staticmethod(vanishing))
        expected = "LedgerInconsistentError"
    else:

        def unreadable(text: str) -> Any:
            raise KeyError("as_of")

        monkeypatch.setattr(store_module, "_stored_bars", unreadable)
        expected = "LedgerInconsistentError"
    result = desk.run(at(NEXT, 22, 10))
    assert (result.outcome, result.error_class) == ("error", expected)
    assert result.records_written == 0
    assert _end(desk, result.run_id)["error_class"] == expected
    assert desk.count("forecast_record") == 2


@pytest.mark.parametrize("case", ["refused", "program-bug", "invalid-values"])
def test_f3_a_program_side_failure_closes_the_gate_as_semantics_changed(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    _under_program_b(desk, monkeypatch)
    if case in {"refused", "program-bug"}:
        exc: Exception = (
            engine.OutlookInvariantError("refused") if case == "refused" else TypeError("bug")
        )

        def failing(*args: Any, **kwargs: Any) -> Any:
            raise exc

        monkeypatch.setattr(recorder_module, "compute_outlook", failing)
    else:
        real = recorder_module._record_content

        def invalid(outcome: Any) -> Any:
            return {**real(outcome), "label": "insufficient", "missing": ()}

        monkeypatch.setattr(recorder_module, "_record_content", invalid)
    result = desk.run(at(NEXT, 22, 10))
    assert (result.outcome, result.error_class) == ("gate_closed", "SemanticsChanged")
    assert _end(desk, result.run_id)["error_class"] == "SemanticsChanged"
    assert desk.count("forecast_record") == 2


def test_f3_both_kinds_leave_the_next_run_to_recompute(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Neither an error nor a gate_closed run is a passed run (point 1), so the
    # program B run after them recomputes again.
    _under_program_b(desk, monkeypatch)

    def broken(content_sha256: str) -> Any:
        raise sqlite3.OperationalError("database is locked")

    with monkeypatch.context() as patch:
        patch.setattr(desk.store, "snapshot", broken)
        assert desk.run(at(NEXT, 22, 10)).outcome == "error"
    recomputed = _count_recomputes(monkeypatch)
    assert desk.run(at(NEXT, 23, 10)).outcome == "ok"
    assert len(recomputed) == 2


def test_the_check_compares_with_the_last_run_that_passed(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Old program A writes; B closes the gate; back on A the previous run (B)
    # differs, so the records are recomputed -- and A reproduces them.
    assert desk.run(EVENING, series(until=T)).outcome == "ok"
    loaded = LOADED
    _as_loaded(
        monkeypatch, Provenance(code_commit="b", code_digest="9" * 64, runtime=loaded.runtime)
    )
    monkeypatch.setitem(engine._OPS, "gt", operator.lt)
    assert desk.run(at(NEXT, 22, 10)).outcome == "gate_closed"
    monkeypatch.setitem(engine._OPS, "gt", operator.gt)
    _as_loaded(monkeypatch, loaded)
    recomputed = _count_recomputes(monkeypatch)
    result = desk.run(at(NEXT, 23, 10))
    assert (result.outcome, result.records_written) == ("ok", 2)
    assert len(recomputed) == 2


# --- supplement 3 (revised) point 1: the comparison baseline (S-12a) ----------------------------

PROGRAM_B = Provenance(code_commit="b", code_digest="9" * 64, runtime=LOADED.runtime)


def test_s12a_a_ok_then_b_closed_twice_then_back_on_a_it_passes(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    recomputed = _count_recomputes(monkeypatch)
    assert desk.run(EVENING, series(until=T)).outcome == "ok"  # program A
    recomputed.clear()
    _as_loaded(monkeypatch, PROGRAM_B)
    monkeypatch.setitem(engine._OPS, "gt", operator.lt)
    second = desk.run(at(NEXT, 22, 10))
    assert (second.outcome, second.error_class) == ("gate_closed", "SemanticsChanged")
    assert len(recomputed) == 2
    # Third run, still B: the previous run (B) is the same program, the last passed
    # run (A) is not -- recomputed again and still closed.
    third = desk.run(at(NEXT, 23, 10))
    assert (third.outcome, third.error_class) == ("gate_closed", "SemanticsChanged")
    assert len(recomputed) == 4
    # Back on A: the previous run (B) differs, A reproduces every record.
    monkeypatch.setitem(engine._OPS, "gt", operator.gt)
    _as_loaded(monkeypatch, LOADED)
    fourth = desk.run(at(NEXT, 23, 30))
    assert (fourth.outcome, fourth.records_written) == ("ok", 2)
    assert len(recomputed) == 6
    assert [r["outcome"] for r in desk.rows("forecast_run_end")] == [
        "ok",
        "gate_closed",
        "gate_closed",
        "ok",
    ]


def test_s12a_without_a_passed_run_the_records_are_recomputed(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The first run commits its records and is interrupted before its end row:
    # there is no passed run, so the next run under the same program recomputes.
    real_end = desk.store.end_run

    def interrupted(run_id: int, **kwargs: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(desk.store, "end_run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        desk.run(EVENING, series(until=T))
    monkeypatch.setattr(desk.store, "end_run", real_end)
    assert desk.count("forecast_record") == 2 and desk.count("forecast_run_end") == 0
    assert desk.store.latest_run_before(10**6, outcomes=("ok",)) is None
    recomputed = _count_recomputes(monkeypatch)
    result = desk.run(at(NEXT, 22, 10))
    assert (result.outcome, result.records_written) == ("ok", 2)
    assert sorted(recomputed) == sorted([desk.h3, desk.h5])


@pytest.mark.parametrize(
    ("exc", "ends"),
    [
        pytest.param(_Boom("x"), True, id="error"),
        pytest.param(KeyboardInterrupt(), False, id="no-end-row"),
    ],
)
def test_s12a_an_error_or_interrupted_run_is_not_a_baseline(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, exc: BaseException, ends: bool
) -> None:
    assert desk.run(EVENING, series(until=T)).outcome == "ok"  # program A
    _as_loaded(monkeypatch, PROGRAM_B)  # B reproduces every record (no semantic change)
    recomputed = _count_recomputes(monkeypatch)
    desk.clock.now = at(NEXT, 22, 10)
    if ends:
        failed = record_forecasts(desk.store, load_benchmark=_raising(exc), resolver={})
        assert failed.outcome == "error"
    else:
        with pytest.raises(KeyboardInterrupt):
            record_forecasts(desk.store, load_benchmark=_raising(exc), resolver={})
    assert len(recomputed) == 2
    # The previous run is B itself, but it is not a passed run: the baseline (ii) is
    # still A, so B recomputes again.
    result = desk.run(at(NEXT, 23, 10))
    assert (result.outcome, result.records_written) == ("ok", 2)
    assert len(recomputed) == 4


# --- supplement 3 (revised) point 2: provenance taken at import (S-12a) -------------------------

LABEL_WORDS = ("bullish", "bearish", "range", "insufficient", "偏多", "偏空", "震盪")


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == recorder_module.__name__]


def _record_view(desk: Desk) -> list[tuple[object, ...]]:
    return [
        (r["claim_id"], r["data_as_of"], r["content_hash"]) for r in desk.rows("forecast_record")
    ]


def test_s12a_an_unchanged_disk_logs_nothing(desk: Desk, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=recorder_module.__name__)
    assert desk.run(EVENING).outcome == "ok"
    assert _warnings(caplog) == []


@pytest.mark.parametrize("change", ["source", "lock-file", "unreadable"])
def test_s12a_a_disk_change_without_restart_logs_one_warning_and_changes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    change: str,
) -> None:
    reference = Desk(tmp_path / "reference", monkeypatch)
    expected = reference.run(EVENING)
    drifted = Desk(tmp_path / "drifted", monkeypatch)
    if change == "source":
        tree = _tree_copy(
            tmp_path / "tree", ("outlook/engine.py", '"gt": operator.gt,', '"gt": operator.lt,')
        )
        assert code_digest(tree) != LOADED.code_digest
        monkeypatch.setattr(recorder_module, "APP_ROOT", tree)
    elif change == "lock-file":
        lock = tmp_path / "uv.lock"
        lock.write_bytes(b"version = 2\n")
        monkeypatch.setattr(recorder_module, "LOCK_FILE", lock)
    else:
        monkeypatch.setattr(recorder_module, "APP_ROOT", tmp_path / "missing")
    caplog.set_level(logging.DEBUG, logger=recorder_module.__name__)
    result = drifted.run(EVENING)
    # The outcome and every record are the ones of the loaded program.
    assert (result.outcome, result.candidate_t, result.records_written, result.error_class) == (
        expected.outcome,
        expected.candidate_t,
        expected.records_written,
        expected.error_class,
    )
    assert _record_view(drifted) == _record_view(reference) != []
    # The run row keeps the provenance taken at import.
    (run,) = drifted.rows("forecast_run")
    assert (run["code_digest"], run["runtime_json"]) == (LOADED.code_digest, LOADED.runtime_json)
    # One WARNING line, no label and no value in it.
    (warning,) = _warnings(caplog)
    assert warning.levelno == logging.WARNING
    message = warning.getMessage()
    assert message == recorder_module.DISK_DIFFERS_WARNING and "\n" not in message
    assert not any(word in message for word in LABEL_WORDS)
    assert LOADED.code_digest not in message


def test_s12a_the_warning_check_reports_whether_it_warned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert recorder_module.warn_if_disk_differs() is False
    monkeypatch.setattr(recorder_module, "APP_ROOT", tmp_path / "missing")
    assert recorder_module.warn_if_disk_differs() is True


def _function_level_imports(source: str) -> list[str]:
    """Supplement 3 (revised) point 2: imports inside a function, ``importlib``, ``__import__``."""
    found: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            found += [
                f"import in function: {ast.unparse(inner)}"
                for inner in ast.walk(node)
                if isinstance(inner, ast.Import | ast.ImportFrom)
            ]
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in {"__import__", "importlib", "import_module"}:
                found.append(name)
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] == "importlib"]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "importlib":
            found.append(node.module or "")
    return found


def test_s12a_the_digested_sources_import_at_module_level_only() -> None:
    files = code_digest_files()
    assert len(files) > 20
    violations = {
        path.relative_to(APP_ROOT).as_posix(): found
        for path in files
        if (found := _function_level_imports(path.read_text(encoding="utf-8")))
    }
    assert violations == {}


@pytest.mark.parametrize(
    "source",
    [
        "def f():\n    import json\n",
        "def f():\n    from app.outlook import engine\n",
        "async def f():\n    import json\n",
        "class C:\n    def m(self):\n        from . import x\n",
        "g = lambda: __import__('json')\n",
        "import importlib\n",
        "from importlib import import_module\n",
        "import importlib.util\n",
        "x = __import__('json')\n",
    ],
)
def test_the_function_level_import_scan_has_teeth(source: str) -> None:
    assert _function_level_imports(source) != []


def test_the_function_level_import_scan_lets_module_imports_through() -> None:
    source = (
        "from __future__ import annotations\nimport json\nfrom typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from app.forecast.store import ForecastStore\n"
        "def f():\n    return json.dumps(1)\n"
    )
    assert _function_level_imports(source) == []


RECORDER_MODULE = "app.forecast.recorder"


def _module_level_recorder_import_violations(source: str) -> list[str]:
    """Supplement 3 (revised) point 2: ``app/scheduler.py`` imports the recorder at module level.

    For the wiring PR (this batch wires nothing, so it is not applied to the
    scheduler yet): at least one top-level statement imports
    ``app.forecast.recorder`` (``import``, ``from app.forecast.recorder import
    ...`` or ``from app.forecast import recorder``), and no import of it sits
    inside a function.
    """
    tree = ast.parse(source)

    def names_recorder(node: ast.stmt) -> bool:
        if isinstance(node, ast.Import):
            return any(a.name == RECORDER_MODULE for a in node.names)
        if isinstance(node, ast.ImportFrom) and not node.level:
            return node.module == RECORDER_MODULE or (
                node.module == "app.forecast" and any(a.name == "recorder" for a in node.names)
            )
        return False

    found: list[str] = []
    if not any(names_recorder(node) for node in tree.body):
        found.append("no module-level import of app.forecast.recorder")
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found += [
                f"recorder imported inside {node.name}()"
                for inner in ast.walk(node)
                if isinstance(inner, ast.Import | ast.ImportFrom) and names_recorder(inner)
            ]
    return found


@pytest.mark.parametrize(
    ("source", "ok"),
    [
        pytest.param("from app.forecast.recorder import record_forecasts\n", True, id="from"),
        pytest.param("from app.forecast import recorder\n", True, id="package-from"),
        pytest.param("import app.forecast.recorder\n", True, id="plain"),
        pytest.param("import json\n", False, id="absent"),
        pytest.param(
            "def job():\n    from app.forecast.recorder import record_forecasts\n",
            False,
            id="in-function",
        ),
        pytest.param(
            "from app.forecast.recorder import record_forecasts\n"
            "def job():\n    from app.forecast import recorder\n",
            False,
            id="also-in-function",
        ),
        pytest.param(
            "if True:\n    from app.forecast.recorder import record_forecasts\n",
            False,
            id="nested-block",
        ),
    ],
)
def test_the_module_level_recorder_import_scan_has_teeth(source: str, ok: bool) -> None:
    assert (_module_level_recorder_import_violations(source) == []) is ok


def test_the_scheduler_is_not_wired_yet_so_the_scan_waits() -> None:
    # The wiring PR asserts _module_level_recorder_import_violations(scheduler) == [].
    source = (APP_ROOT / "scheduler.py").read_text(encoding="utf-8")
    assert _module_level_recorder_import_violations(source) == [
        "no module-level import of app.forecast.recorder"
    ]


# --- K-10, K-4, S-4a call sites -----------------------------------------------------------------


def _public_functions() -> dict[str, Any]:
    return {
        name: value
        for name, value in vars(recorder_module).items()
        if inspect.isfunction(value)
        and value.__module__ == recorder_module.__name__
        and not name.startswith("_")
    }


def test_the_entry_takes_the_store_the_loader_and_its_resolver_only() -> None:
    params = inspect.signature(record_forecasts).parameters
    assert list(params) == ["store", "load_benchmark", "resolver"]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in list(params.values())[1:])


def test_no_public_recorder_function_takes_a_time_parameter() -> None:
    functions = _public_functions()
    assert {"record_forecasts", "check_recording_claims", "check_semantics"} <= set(functions)
    offenders = {
        name: sorted(set(inspect.signature(f).parameters) & TIME_PARAMS)
        for name, f in functions.items()
        if set(inspect.signature(f).parameters) & TIME_PARAMS
    }
    assert offenders == {}


def _app_sources() -> dict[str, str]:
    return {
        path.relative_to(APP_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(APP_ROOT.rglob("*.py"))
    }


def _referrers(name: str, sources: Mapping[str, str]) -> set[str]:
    """Files that name ``name`` in code (call, reference, attribute or import)."""
    found: set[str] = set()
    for path, source in sources.items():
        for node in ast.walk(ast.parse(source)):
            if (
                (isinstance(node, ast.Name) and node.id == name)
                or (isinstance(node, ast.Attribute) and node.attr == name)
                or (isinstance(node, ast.ImportFrom) and any(a.name == name for a in node.names))
            ):
                found.add(path)
    return found


#: Supplement 2 S-4a. This batch wires nothing, so no app/ module refers to the
#: entry. The wiring PR changes WIRED_REFERRERS to {"scheduler.py"}, keeps
#: ``_wiring_violations`` at [] for the scheduler source and adds the ``is``
#: check on the registered job (``_job_wiring_violations``).
WIRED_REFERRERS: frozenset[str] = frozenset()


def test_s4a_only_the_scheduler_may_refer_to_the_entry() -> None:
    sources = {p: s for p, s in _app_sources().items() if p != "forecast/recorder.py"}
    assert _referrers("record_forecasts", sources) == WIRED_REFERRERS
    assert "record_forecasts" not in (APP_ROOT / "scheduler.py").read_text(encoding="utf-8")


def test_the_referrer_scan_has_teeth() -> None:
    sources = {
        "a.py": "from app.forecast.recorder import record_forecasts\n",
        "b.py": "recorder.record_forecasts(store, load_benchmark=f, resolver=r)\n",
        "c.py": "engine.add_job(record_forecasts, id='forecast_record')\n",
        "d.py": "record_forecasts_x = 1\n",
    }
    assert _referrers("record_forecasts", sources) == {"a.py", "b.py", "c.py"}


def _wiring_violations(source: str) -> list[str]:
    """The wiring rule for ``app/scheduler.py``: ``load_benchmark`` is the index loader itself.

    ``load_market_benchmark`` must be imported from ``app.services.index`` and
    every ``load_benchmark=`` keyword must pass that bare name.
    """
    tree = ast.parse(source)
    found: list[str] = []
    imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.services.index"
        and any(a.name == "load_market_benchmark" and a.asname is None for a in node.names)
        for node in ast.walk(tree)
    )
    if not imported:
        found.append("load_market_benchmark is not imported from app.services.index")
    keywords = [kw for node in ast.walk(tree) if isinstance(node, ast.Call) for kw in node.keywords]
    loaders = [kw.value for kw in keywords if kw.arg == "load_benchmark"]
    dict_values = [
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and key.value == "load_benchmark"
    ]
    passed = [*loaders, *dict_values]
    if not passed:
        found.append("no load_benchmark is passed")
    found += [
        f"load_benchmark={ast.unparse(value)}"
        for value in passed
        if not (isinstance(value, ast.Name) and value.id == "load_market_benchmark")
    ]
    return found


def _job_wiring_violations(job_kwargs: Mapping[str, object]) -> list[str]:
    """The ``is`` check on a registered job's kwargs (S-4a; used by the wiring PR)."""
    if job_kwargs.get("load_benchmark") is not load_market_benchmark:
        return ["the job's load_benchmark is not app.services.index.load_market_benchmark"]
    return []


@pytest.mark.parametrize(
    ("source", "ok"),
    [
        pytest.param(
            "from app.services.index import load_market_benchmark\n"
            "engine.add_job(record_forecasts, kwargs={'store': s,"
            " 'load_benchmark': load_market_benchmark, 'resolver': r})\n",
            True,
            id="wired",
        ),
        pytest.param(
            "from app.services.index import load_market_benchmark\n"
            "record_forecasts(s, load_benchmark=load_market_benchmark, resolver=r)\n",
            True,
            id="called",
        ),
        pytest.param(
            "from app.services.index import load_market_benchmark\n"
            "record_forecasts(s, load_benchmark=partial(load_market_benchmark), resolver=r)\n",
            False,
            id="wrapped",
        ),
        pytest.param(
            "record_forecasts(s, load_benchmark=load_market_benchmark, resolver=r)\n",
            False,
            id="not-imported",
        ),
        pytest.param(
            "from app.services.index import load_market_benchmark as lmb\n"
            "record_forecasts(s, load_benchmark=lmb, resolver=r)\n",
            False,
            id="aliased",
        ),
        pytest.param(
            "from app.services.index import load_market_benchmark\n"
            "record_forecasts(s, load_benchmark=other_loader, resolver=r)\n",
            False,
            id="other-loader",
        ),
    ],
)
def test_the_wiring_scan_has_teeth(source: str, ok: bool) -> None:
    assert (_wiring_violations(source) == []) is ok


def test_the_job_is_check_has_teeth() -> None:
    assert _job_wiring_violations({"load_benchmark": load_market_benchmark}) == []
    assert _job_wiring_violations({"load_benchmark": _raising(RuntimeError())}) != []
    assert _job_wiring_violations({}) != []


#: The recorder's writes; a run's snapshot and records go through the batch only
#: (supplement 3 (revised) point 7).
WRITE_METHODS = ("begin_run", "end_run", "write_run_records")
#: The one-row forms of the batch write: no app/ module calls them.
SINGLE_ROW_WRITES = ("put_input_series", "write_record")


def _callers(name: str, sources: Mapping[str, str]) -> set[str]:
    return {
        path
        for path, source in sources.items()
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    }


@pytest.mark.parametrize("method", WRITE_METHODS)
def test_k4_the_ledger_writes_are_called_from_the_recorder_only(method: str) -> None:
    assert _callers(method, _app_sources()) == {"forecast/recorder.py"}


@pytest.mark.parametrize("method", SINGLE_ROW_WRITES)
def test_k4_no_app_module_writes_a_snapshot_or_record_outside_the_batch(method: str) -> None:
    assert _callers(method, _app_sources()) == set()


def test_k4_the_recorder_calls_the_batch_once() -> None:
    tree = ast.parse((APP_ROOT / "forecast" / "recorder.py").read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "write_run_records"
    ]
    assert len(calls) == 1


def test_k4_only_the_registration_cli_registers_a_claim() -> None:
    # ADR-0030 K-4: the write functions are called by the recorder and the CLI only.
    assert _callers("register_claim", _app_sources()) == {"forecast/claims.py"}


def test_the_caller_scan_has_teeth() -> None:
    assert _callers("write_record", {"x.py": "store.write_record(run_id=1)\n"}) == {"x.py"}
    assert _callers("write_record", {"y.py": "write_record = 1\n"}) == set()


# --- K-2 reachability (supplement 2 point 1: unchanged, by reachability) ----------------------

K2_UNREACHABLE = (
    "app.api",
    "app.advice.loader",
    "app.advice.context",
    "app.services",
    "app.portfolio",
    "app.positions",
    "app.demo",
    "app.backtest",
    "app.research",
    "app.sectors",
    "app.data.market_panel",
    "app.ops_alert",
    "app.main",
    "app.scheduler",
)


@pytest.mark.parametrize("package", K2_UNREACHABLE)
def test_k2_the_recorder_reaches_none_of_the_forbidden_packages(package: str) -> None:
    assert offenders(reachable_app_modules(("app.forecast.recorder",)), package) == []


def _core_modules() -> tuple[str, ...]:
    """Every module of ``app/forecast`` and ``app/outlook`` (the two K-2 packages)."""
    return tuple(
        sorted(
            ".".join(path.relative_to(APP_ROOT.parent).with_suffix("").parts).removesuffix(
                ".__init__"
            )
            for package in ("forecast", "outlook")
            for path in (APP_ROOT / package).rglob("*.py")
        )
    )


def test_k2_the_core_reaches_no_api_module() -> None:
    # Supplement 3 point 3: by reachability, transitive imports and parent packages included.
    assert offenders(reachable_app_modules(_core_modules()), "app.api") == []
    assert offenders(executed_app_modules(_core_modules()), "app.api") == []


def test_k2_the_core_reaches_exactly_the_advice_package_and_the_leaf_module() -> None:
    assert set(offenders(executed_app_modules(_core_modules()), "app.advice")) == {
        "app.advice",
        "app.advice.banned_phrases",
    }


def test_k2_the_core_module_list_and_the_executed_scan_have_teeth() -> None:
    assert {"app.forecast", "app.forecast.recorder", "app.outlook.engine"} <= set(_core_modules())
    # Through the old route (the loader) the scan sees the api module and the parent package.
    via_loader = executed_app_modules(("app.advice.loader",))
    assert offenders(via_loader, "app.api") != []
    assert {"app.advice", "app.advice.context", "app.advice.limits"} <= via_loader
    # Imported names are not modules.
    assert "app.advice.banned_phrases.BANNED_PHRASES" not in executed_app_modules(
        ("app.forecast.definitions",)
    )


def test_k2_the_loader_and_the_leaf_hold_one_object() -> None:
    from app.advice import banned_phrases, loader

    assert loader.BANNED_PHRASES is banned_phrases.BANNED_PHRASES
    assert vars(definitions)["BANNED_PHRASES"] is banned_phrases.BANNED_PHRASES


def test_the_recorder_reachability_scan_has_teeth() -> None:
    reached = reachable_app_modules(("app.forecast.recorder",))
    assert "app.outlook.engine" in reached and "app.forecast.store" in reached
