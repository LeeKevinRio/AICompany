"""The ADR-0030 D-7 30-day pipeline acceptance harness (placeholder rules P-0 / P-1).

Use (D-7 point 1): pipeline verification only. Not evidence of performance,
not part of any validation statistic, and not the pre-registration section 4.7
replay. Nothing it prints may be cited as rule performance.

What one run does (D-7 points 2-6):

1. refuses a production path (:func:`refuse_production`: the claims CLI's
   production path rule -- a file named ``stock-desk.db``, the production
   database, a file in its folder or the one ``STOCK_DESK_DB_PATH`` names --
   plus anything inside ``<backend>/data/``) and an existing file, then
   creates the ledger schema in a fresh file under ``work_dir`` (D-7 point 3:
   nothing is registered or written in the production database);
2. injects the registry (:func:`injected_registry`): the placeholder rule set
   of each horizon and the definition are put into
   ``app.forecast.definitions``' module attributes for the duration of the
   run and restored afterwards. That is the only way they pass CG-2: no
   ``app/`` function takes a registry, a rule set or a definition (K-11;
   ``tests/test_forecast_pipeline_harness.py`` proves it);
3. registers the two claims through ``app.forecast.claims.register`` (the CLI's
   own function) into that file -- ``kind`` is ``forward``, the only kind;
4. for each session T of the window -- the latest :data:`WINDOW_SESSIONS`
   final sessions before the run date, decided by :func:`acceptance_window`
   from the input, never chosen by hand (D-7 point 6) -- sets the injected
   store clock (by default T 22:10 Taipei) and calls
   ``app.forecast.recorder.record_forecasts``, the production entry, with a
   loader that answers from the given bars only: no network, no database, no
   ``price_bars_cache`` (D-7 point 2). The loader returns only bars stamped at
   or before the store clock, so it can answer nothing a fetch at that time
   could not have had; the answer's ``reason`` is ``synthetic_timestamps``
   (D-7 point 6: the stamps are injected, not the source's);
5. checks, record by record: the model label equals the placeholder's
   baseline (P-0: B6, P-1: B8) for every record that is not ``insufficient``,
   an ``insufficient`` record carries a missing item; where a provisional
   comparison exists, the model and that baseline match or not alike; every
   record passes ``report verify`` (D-5 point 3); every run ended ``ok``;
6. renders the output: the two fixed lines of D-7 point 5 first
   (:data:`HEADER`), then the report's own ``records``, ``compare`` (between
   its fixed banners), ``verify`` and ``status`` sections, so every D-4
   point 3 / 5 rule of the report holds for the harness output too. "Passed"
   (D-4 point 3) is read with ``wall_clock`` -- the actual clock unless a test
   injects one (D-7 point 6).

:func:`render_summary` is what may leave the machine that ran the harness: the
pass / fail line, counts of runs and records, and hashes -- no label, no
comparison, no realised value.

PIT, finality and ``late`` are verified with synthetic fixtures only (D-7
point 6): :func:`synthetic_series` builds deterministic closes on consecutive
weekdays, each bar stamped 20:00 Taipei on its own session.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from app.data.interface import DataStatus, Market, PriceBar
from app.dirdef.definition import (
    DirectionDefinition,
    definition_logic_sha256,
    definition_sha256,
)
from app.dirdef.registry import PublishedDefinition, PublishedRuleset
from app.forecast import claims, definitions, recorder, report, scoring
from app.forecast.claims import BACKEND_DIR
from app.forecast.recorder import RunResult, record_forecasts
from app.forecast.schema import create_schema
from app.forecast.store import ForecastStore, system_clock
from app.outlook.inputs import SERIES_SYMBOL
from tests.outlook_helpers import TAIPEI

#: D-7 point 5: the first line of every output, and the placeholder-rule second line.
HEADER: Final = (
    "管線驗收：使用歷史資料，不是前瞻紀錄；只驗證程式流程，不是績效證據，不計入任何驗證統計；"
    "規則未經驗證。",
    "本次使用佔位規則，輸出不是任何將登記規則的判斷。",
)
#: D-7 point 6: the latest 21 final sessions before the run date.
WINDOW_SESSIONS: Final = 21
#: D-7 point 6: the stamps are injected values.
SYNTHETIC_REASON: Final = "synthetic_timestamps"
SYNTHETIC_SOURCE: Final = "synthetic"
LEDGER_NAME: Final = "pipeline-acceptance.db"
#: The default run time of a session's run (D-3 point 7: 22:10 Taipei).
RUN_TIME: Final = time(22, 10)


# --- placeholder rules ------------------------------------------------------------------

_P0: Final = """\
# Placeholder rule set P-0 (ADR-0030 D-7 point 4): always range, equal to B6.
# Not a candidate rule; pipeline acceptance only.
version: "0.0.1"
aggregation:
  theta: 1
  min_completeness: 1.0
rules:
  - id: placeholder_range
    name: 佔位規則 P-0（恆判震盪）
    direction: range
    weight: 1.0
    condition: {{field: close, op: gt, value: 0}}
    explanation: 管線驗收用的佔位規則，不是候選規則；收盤可用時恆判震盪（h{h}），輸出等於 B6。
    counterargument: 佔位規則不含任何判斷內容，只用來驗證程式流程。
    invalidation: {{field: close, op: lte, value: 0}}
"""

_P1: Final = """\
# Placeholder rule set P-1 (ADR-0030 D-7 point 4): the sign of the past h-day return, equal to B8.
# Not a candidate rule; pipeline acceptance only.
version: "0.0.1"
aggregation:
  theta: 1
  min_completeness: 1.0
rules:
  - id: placeholder_sign_up
    name: 佔位規則 P-1（符號延續，偏多）
    direction: bullish
    weight: 1.0
    condition: {{field: logret_past_{h}, op: gt, value: 0}}
    explanation: 管線驗收用的佔位規則；過去 {h} 個交易日的對數報酬為正時判偏多（等於 B8）。
    counterargument: 佔位規則不含任何判斷內容，只用來驗證程式流程。
    invalidation: {{field: logret_past_{h}, op: lte, value: 0}}
  - id: placeholder_sign_down
    name: 佔位規則 P-1（符號延續，偏空）
    direction: bearish
    weight: 1.0
    condition: {{field: logret_past_{h}, op: lt, value: 0}}
    explanation: 管線驗收用的佔位規則；過去 {h} 個交易日的對數報酬為負時判偏空（等於 B8）。
    counterargument: 佔位規則不含任何判斷內容，只用來驗證程式流程。
    invalidation: {{field: logret_past_{h}, op: gte, value: 0}}
"""


@dataclass(frozen=True)
class PlaceholderRules:
    """One placeholder rule set of D-7 point 4 and the baseline it equals."""

    name: str
    baseline: str
    template: str

    def rules_version(self, horizon: int) -> str:
        return f"pipeline-acceptance-{self.name}-h{horizon}"

    def rule_bytes(self, horizon: int) -> bytes:
        return self.template.format(h=horizon).encode("utf-8")


P0: Final = PlaceholderRules(name="P-0", baseline="B6", template=_P0)
P1: Final = PlaceholderRules(name="P-1", baseline="B8", template=_P1)
HORIZONS: Final = (3, 5)


# --- refusal and the injected registry ----------------------------------------------------


class HarnessRefused(RuntimeError):
    """The harness will not run on this path; nothing was opened."""


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
    except ValueError:
        return False
    return True


def refuse_production(
    db_path: Path, *, backend_dir: Path, cwd: Path, env: Mapping[str, str]
) -> None:
    """D-7 point 2 / K-11: raise :class:`HarnessRefused` on a production path (no file opened)."""
    reason = claims.production_path_refusal(db_path, backend_dir=backend_dir, cwd=cwd, env=env)
    if reason is not None:
        raise HarnessRefused(reason.replace("--db", "the harness ledger"))
    if _inside(cwd / db_path, backend_dir / "data"):
        raise HarnessRefused("refused: the harness ledger is inside the production data folder")


@contextmanager
def injected_registry(rules: PlaceholderRules, definition: DirectionDefinition) -> Iterator[None]:
    """The injected registry of D-7 point 2 (tests and this harness only; K-11).

    Replaces the two registries, the rule file reader and the two caches of
    ``app.forecast.definitions`` with the placeholder rule sets and
    ``definition``, and restores every one of them on exit.
    """
    names = (
        "PUBLISHED_DIRECTION_DEFINITIONS",
        "PUBLISHED_RULESETS",
        "_read_rules_bytes",
        "_DEFINITION_CACHE",
        "_RULESET_CACHE",
    )
    saved = {name: vars(definitions)[name] for name in names}
    entry = PublishedDefinition(
        definition=definition,
        definition_logic_sha256=definition_logic_sha256(definition),
        definition_sha256=definition_sha256(definition),
    )
    rulesets = {
        rules.rules_version(h): PublishedRuleset(
            horizon=h, rules_sha256=hashlib.sha256(rules.rule_bytes(h)).hexdigest()
        )
        for h in HORIZONS
    }
    replaced: dict[str, Any] = {
        "PUBLISHED_DIRECTION_DEFINITIONS": MappingProxyType({definition.definition_version: entry}),
        "PUBLISHED_RULESETS": MappingProxyType(rulesets),
        "_read_rules_bytes": rules.rule_bytes,
        "_DEFINITION_CACHE": {},
        "_RULESET_CACHE": {},
    }
    try:
        for name, value in replaced.items():
            setattr(definitions, name, value)
        yield
    finally:
        for name, value in saved.items():
            setattr(definitions, name, value)


# --- synthetic input ----------------------------------------------------------------------


def _weekdays_ending(last: date, count: int) -> list[date]:
    days: list[date] = []
    day = last
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return list(reversed(days))


def synthetic_return(j: int) -> float:
    """A deterministic daily log return (no random generator)."""
    return 0.008 * math.sin(0.7 * j) + 0.003 * (((j * 7919) % 13) - 6) / 6


def synthetic_series(
    last: date,
    count: int,
    *,
    returns: Callable[[int], float] = synthetic_return,
    stamp_hour: int = 20,
) -> list[PriceBar]:
    """``count`` synthetic ``^TWII`` bars on consecutive weekdays ending ``last``.

    Each bar is stamped ``stamp_hour``:00 Taipei on its own session (an
    injected stamp; final when at or after the 15:00 cutoff).
    """
    closes = [10000.0]
    for j in range(1, count):
        closes.append(closes[-1] * math.exp(returns(j)))
    return [
        PriceBar(
            symbol=SERIES_SYMBOL,
            market="TW",
            date=day,
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=0,
            currency="TWD",
            as_of=datetime.combine(day, time(stamp_hour), TAIPEI),
            source=SYNTHETIC_SOURCE,
        )
        for day, close in zip(_weekdays_ending(last, count), closes, strict=True)
    ]


@dataclass(frozen=True)
class SyntheticAnswer:
    """An index answer (``app.outlook.inputs.IndexSeriesAnswer``) from the given bars only."""

    bars: Sequence[PriceBar]
    series_symbol: str | None = SERIES_SYMBOL
    status: DataStatus = DataStatus.BACKUP
    source: str = SYNTHETIC_SOURCE
    staleness_minutes: int | None = None
    reason: str | None = SYNTHETIC_REASON


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _loader(bars: Sequence[PriceBar], clock: _Clock) -> Callable[..., SyntheticAnswer]:
    """What a fetch at the store clock's time could return: bars stamped by then, in range."""

    def load(resolver: object, *, market: Market, start: date, end: date) -> SyntheticAnswer:
        now = clock()
        return SyntheticAnswer(
            bars=[b for b in bars if start <= b.date <= end and b.as_of <= now],
        )

    return load


def acceptance_window(sessions: Sequence[date], run_date: date) -> tuple[date, ...]:
    """D-7 point 6: the latest :data:`WINDOW_SESSIONS` sessions before ``run_date``."""
    before = sorted({day for day in sessions if day < run_date})
    if len(before) < WINDOW_SESSIONS:
        raise HarnessRefused(f"fewer than {WINDOW_SESSIONS} final sessions before the run date")
    return tuple(before[-WINDOW_SESSIONS:])


def _final_sessions(bars: Sequence[PriceBar]) -> list[date]:
    cutoff = time(15)
    return [b.date for b in bars if b.as_of >= datetime.combine(b.date, cutoff, TAIPEI)]


# --- the run ------------------------------------------------------------------------------


@dataclass
class AcceptanceResult:
    """What one harness run found; :func:`render_summary` is its shareable part."""

    rules: str
    window: tuple[date, ...]
    runs: list[RunResult] = field(default_factory=list)
    records: int = 0
    insufficient: int = 0
    labels_checked: int = 0
    compared: int = 0
    verified: int = 0
    failures: list[str] = field(default_factory=list)
    output: list[str] = field(default_factory=list)
    ledger_sha256: str = ""

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def output_sha256(self) -> str:
        return hashlib.sha256("\n".join(self.output).encode("utf-8")).hexdigest()


def _create_ledger(db_path: Path) -> None:
    """The harness's own ledger file: a fresh database with the schema (refused already)."""
    with closing(sqlite3.connect(db_path, isolation_level=None)) as conn:
        create_schema(conn)


def run_acceptance(
    work_dir: Path,
    *,
    bars: Sequence[PriceBar],
    rules: PlaceholderRules,
    definition: DirectionDefinition,
    wall_clock: Callable[[], datetime] = system_clock,
    run_time: Callable[[date], datetime] | None = None,
    backend_dir: Path = BACKEND_DIR,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> AcceptanceResult:
    """One harness run (module docstring); returns what it found, refusing production paths.

    ``backend_dir``, ``env`` and ``cwd`` -- what the production path rule
    compares against -- are for tests; the defaults are this checkout's backend,
    the process environment and working directory.
    """
    db_path = work_dir / LEDGER_NAME
    refuse_production(
        db_path,
        backend_dir=backend_dir,
        cwd=Path.cwd() if cwd is None else cwd,
        env=os.environ if env is None else env,
    )
    if db_path.exists():
        raise HarnessRefused("refused: the harness ledger already exists")
    now = wall_clock()
    window = acceptance_window(_final_sessions(bars), report.taipei_date(now))
    result = AcceptanceResult(rules=rules.name, window=window)
    _create_ledger(db_path)
    clock = _Clock(datetime.combine(window[0], time(9), TAIPEI))
    store = ForecastStore(db_path, clock=clock)
    when = run_time or (lambda day: datetime.combine(day, RUN_TIME, TAIPEI))
    with injected_registry(rules, definition):
        for horizon in HORIZONS:
            clock.now += timedelta(seconds=1)
            claims.register(
                store,
                rules_version=rules.rules_version(horizon),
                definition_version=definition.definition_version,
                frozen_commit="pipeline-acceptance",
                prereg_doc_path="docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md",
                prereg_doc_blob=b"ADR-0030 D-7 pipeline acceptance (placeholder rules)",
                review_refs="ADR-0030 D-7",
                replaces_claim_id=None,
                replace_reason=None,
                provisional_results_seen=False,
                out=[],
            )
        loader = _loader(bars, clock)
        for day in window:
            clock.now = when(day)
            result.runs.append(record_forecasts(store, load_benchmark=loader, resolver=None))
    _check(store, result, rules, now)
    result.output = [
        *HEADER,
        *report.render_records(store, now=now),
        *report.render_compare(store, now=now),
        *report.render_verify(report.verify_records(store, _recording(store))),
        *report.render_status(store, now=now),
    ]
    result.ledger_sha256 = hashlib.sha256(db_path.read_bytes()).hexdigest()
    return result


def _recording(store: ForecastStore) -> list[Any]:
    recording = store.recording_claims()
    return [recording[key] for key in sorted(recording)]


def _check(
    store: ForecastStore, result: AcceptanceResult, rules: PlaceholderRules, now: datetime
) -> None:
    """Step 5 of the module docstring; every failure is a line without a label."""

    for run in result.runs:
        if run.outcome != "ok":
            result.failures.append(f"run {run.run_id}: outcome {run.outcome} ({run.error_class})")
    today = report.taipei_date(now)
    known = store.final_sessions()
    snapshots = [
        recorder.stored_market_snapshot(store.snapshot(d)) for d in store.snapshot_digests()
    ]
    for claim in _recording(store):
        for row in store.stored_records(claim.claim_id):
            result.records += 1
            where = f"{claim.claim_id} T={row['data_as_of']}"
            baseline = json.loads(str(row["baseline_predictions_json"]))[rules.baseline]
            if row["label"] == "insufficient":
                result.insufficient += 1
                if json.loads(str(row["missing_json"])) == []:
                    result.failures.append(f"{where}: insufficient without a missing item")
            else:
                result.labels_checked += 1
                if row["label"] != baseline["label"]:
                    result.failures.append(f"{where}: model and {rules.baseline} differ")
            record = scoring.ComparedRecord.from_row(row)
            later = report.later_snapshot(snapshots, record.data_as_of, record.horizon)
            compared = scoring.provisional_comparison(
                record, later, known_sessions=known, today=today
            )
            if compared.reason is None and row["label"] != "insufficient":
                result.compared += 1
                matches = dict(compared.matches)
                if matches[scoring.MODEL] != matches[rules.baseline]:
                    result.failures.append(
                        f"{where}: provisional match of model and {rules.baseline} differ"
                    )
    for item in report.verify_records(store, _recording(store)):
        result.verified += 1
        if not item.consistent:
            result.failures.append(f"{item.claim_id} T={item.data_as_of}: verify {item.problem}")
    if result.records != len(HORIZONS) * len(result.window):
        result.failures.append(
            f"{result.records} records for {len(result.window)} sessions and two claims"
        )


def render_summary(result: AcceptanceResult) -> list[str]:
    """The shareable part of a run: pass / fail, execution counts and hashes.

    No label, no comparison, no realised value; the counts are execution status
    only (runs per outcome and their ``records_written``; D-4 point 5).
    """
    outcomes: dict[str, int] = {}
    for run in result.runs:
        outcomes[run.outcome] = outcomes.get(run.outcome, 0) + 1
    runs = "，".join(f"{outcome}={count}" for outcome, count in sorted(outcomes.items()))
    written = sum(run.records_written for run in result.runs)
    return [
        HEADER[0],
        HEADER[1],
        f"管線驗收 {result.rules}：{'通過' if result.passed else '失敗'}",
        f"視窗定案 session 數：{len(result.window)}",
        f"執行次數：{runs}；records_written 合計：{written}",
        f"失敗項目數：{len(result.failures)}",
        f"暫存帳 sha256：{result.ledger_sha256}",
        f"輸出 sha256：{result.output_sha256}",
    ]
