"""The D-7 30-day pipeline acceptance, run on synthetic data in CI (ADR-0030 D-7 points 1-7).

Every ledger is a ``tmp_path`` file; the production path stand-ins are
``tmp_path`` folders (no test looks at the real ``<backend>/data/``). The
placeholder rule sets P-0 / P-1 (CEO #67) pass CG-2 through the harness's
injected registry only. No assertion message or test output carries a label.

Covered:

* one full run per placeholder rule set with the actual clock (D-7 point 6:
  "passed" is read with the actual clock; the window is the latest 21 final
  sessions before today), plus fixed-clock runs: every run ``ok``, every
  record's model label equal to its baseline (P-0: B6, P-1: B8), the
  provisional match of the two alike, every record consistent under
  ``report verify``;
* the harness's own failure kinds (quant point 1 (a)-(c); ADR-0030
  supplement 5 point 3 (a)), each with positive and negative cases:
  ``vacuous_equality`` when a rule set and horizon has no record that is
  both evaluable and compared (every record insufficient, one combination
  insufficient, or evaluable records without a comparison),
  ``baseline_unavailable`` apart from ``label_differs``, and
  ``missing_not_iff_insufficient`` in both directions;
* the synthetic fixtures of D-7 point 4: sigma degenerate, insufficient
  evidence (bars short), a short snapshot, and the ``late`` boundary
  (23:59:59.999999 and 00:00:00);
* the output: the two D-7 point 5 lines first, every D-4 point 3 / 5 rule of
  the report, a deterministic output hash, a summary without labels;
* isolation (D-7 points 2-3, K-11): production paths are refused before any
  file is opened; the injected registry is restored; no ``app/`` module
  imports the harness or rebinds the registries; the harness reads no
  ``price_bars_cache`` and opens no database but its own.
"""

from __future__ import annotations

import ast
import inspect
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import MappingProxyType

import pytest

from app.data.interface import PriceBar
from app.dirdef import registry
from app.forecast import claims, definitions, report
from app.forecast.recorder import record_forecasts
from app.forecast.store import ForecastStore, system_clock
from tests import forecast_pipeline_harness as harness
from tests.forecast_pipeline_harness import (
    HEADER,
    P0,
    P1,
    WINDOW_SESSIONS,
    AcceptanceResult,
    HarnessRefused,
    PlaceholderRules,
    acceptance_window,
    refuse_production,
    render_summary,
    run_acceptance,
    synthetic_series,
)
from tests.import_graph import APP_ROOT
from tests.outlook_helpers import TAIPEI, definition
from tests.test_forecast_report import LABEL_WORDS, d4_violations

#: A fixed "actual" clock for the deterministic runs: Monday 2026-11-16, 09:00 Taipei.
FIXED_NOW = datetime(2026, 11, 16, 9, tzinfo=TAIPEI)
LAST = date(2026, 11, 13)  # the Friday before it


def _previous_weekday(day: date) -> date:
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _run(
    root: Path,
    rules: PlaceholderRules,
    *,
    bars: Sequence[PriceBar] | None = None,
    now: datetime = FIXED_NOW,
    run_time: Callable[[date], datetime] | None = None,
) -> AcceptanceResult:
    backend = root / "backend"
    (backend / "data").mkdir(parents=True, exist_ok=True)
    work = root / "work"
    work.mkdir(parents=True, exist_ok=True)
    return run_acceptance(
        work,
        bars=list(bars) if bars is not None else synthetic_series(LAST, 360),
        rules=rules,
        definition=definition(),
        wall_clock=lambda: now,
        backend_dir=backend,
        env={},
        cwd=root,
        run_time=run_time,
    )


def _unpassed(root: Path, today: date) -> set[str]:
    store = ForecastStore(root / "work" / harness.LEDGER_NAME)
    return {
        str(row["content_hash"])
        for claim in store.forward_claims()
        for row in store.stored_records(claim.claim_id)
        if not report.has_passed(row["valid_until_session_estimate"], today)
    }


def _records(root: Path) -> list[dict[str, object]]:
    store = ForecastStore(root / "work" / harness.LEDGER_NAME)
    return [row for claim in store.forward_claims() for row in store.stored_records(claim.claim_id)]


# --- the full run (D-7 points 4-6) ----------------------------------------------------------


@pytest.mark.parametrize("rules", [P0, P1], ids=lambda r: r.name)
def test_the_full_run_with_the_actual_clock_passes(tmp_path: Path, rules: PlaceholderRules) -> None:
    now = system_clock()
    today = report.taipei_date(now)
    bars = synthetic_series(_previous_weekday(today), 360)
    result = _run(tmp_path, rules, bars=bars, now=now)
    assert result.failures == []
    assert result.passed
    assert [r.outcome for r in result.runs] == ["ok"] * WINDOW_SESSIONS
    assert sum(r.records_written for r in result.runs) == 2 * WINDOW_SESSIONS
    assert (result.records, result.verified, result.insufficient) == (42, 42, 0)
    assert result.labels_checked == 42
    # The window ends on the session before today, so the last records have not passed.
    assert result.window[-1] == _previous_weekday(today)
    assert 0 < result.compared < result.records
    assert tuple(result.output[:2]) == HEADER
    assert d4_violations(result.output, unpassed_hashes=_unpassed(tmp_path, today)) == []


@pytest.mark.parametrize("rules", [P0, P1], ids=lambda r: r.name)
def test_the_fixed_clock_run_passes_and_its_output_hash_is_stable(
    tmp_path: Path, rules: PlaceholderRules
) -> None:
    first = _run(tmp_path / "a", rules)
    second = _run(tmp_path / "b", rules)
    assert first.passed and second.passed
    assert first.output == second.output
    assert first.output_sha256 == second.output_sha256
    # h3 records with T + 3 sessions inside the window are compared, likewise h5.
    assert first.compared == (WINDOW_SESSIONS - 3) + (WINDOW_SESSIONS - 5)
    today = report.taipei_date(FIXED_NOW)
    assert d4_violations(first.output, unpassed_hashes=_unpassed(tmp_path / "a", today)) == []


def test_the_model_equals_its_baseline_record_by_record(tmp_path: Path) -> None:
    # The harness's own check, read back from the ledger (no label in the assertion text).
    for rules, root in ((P0, tmp_path / "p0"), (P1, tmp_path / "p1")):
        result = _run(root, rules)
        assert result.passed
        rows = _records(root)
        same = [
            row["label"]
            == json.loads(str(row["baseline_predictions_json"]))[rules.baseline]["label"]
            for row in rows
        ]
        assert len(rows) == 42 and all(same)
    # P-1 is not constant: the synthetic series moves both ways.
    assert len({row["label"] for row in _records(tmp_path / "p1")}) > 1


def test_a_differing_model_label_fails_the_run(tmp_path: Path) -> None:
    # Negative case: P-0's rules checked against B8 instead of B6.
    wrong = PlaceholderRules(name="P-0", baseline="B8", template=P0.template)
    result = _run(tmp_path, wrong)
    assert not result.passed
    assert "label_differs" in result.failure_kinds
    assert "baseline_unavailable" not in result.failure_kinds
    assert not any(word in str(failure) for failure in result.failures for word in LABEL_WORDS)
    assert "失敗" in "\n".join(render_summary(result))


# --- quant point 1 (a)-(c): the harness's own failure kinds --------------------------------------


def _row(label: str, missing: list[object], **baselines: object) -> dict[str, object]:
    stored = {"B1": {"label": "range"}, "B2": {"label": "range"}, "B6": {"label": "range"}}
    stored["B8"] = {"label": "range"}
    stored.update(baselines)  # type: ignore[arg-type]
    return {
        "label": label,
        "missing_json": json.dumps(missing),
        "baseline_predictions_json": json.dumps(stored),
    }


ITEM = {"code": "E-BARS-SHORT", "item": "index_bars"}


@pytest.mark.parametrize(
    ("row", "baseline", "kinds"),
    [
        pytest.param(_row("insufficient", [ITEM]), "B6", [], id="insufficient-with-missing"),
        pytest.param(_row("range", []), "B6", [], id="label-equal-no-missing"),
        pytest.param(
            _row("insufficient", []),
            "B6",
            ["missing_not_iff_insufficient"],
            id="insufficient-without-missing",
        ),
        pytest.param(
            _row("range", [ITEM]), "B6", ["missing_not_iff_insufficient"], id="missing-on-a-label"
        ),
        pytest.param(
            _row("bullish", [], B8={"label": "unavailable", "reason": "E-BARS-SHORT"}),
            "B8",
            ["baseline_unavailable"],
            id="baseline-unavailable-not-a-differing-label",
        ),
        pytest.param(
            _row("insufficient", [ITEM], B8={"label": "unavailable", "reason": "E-BARS-SHORT"}),
            "B8",
            [],
            id="unavailable-baseline-on-an-insufficient-record",
        ),
        pytest.param(
            _row("bullish", [], B8={"label": "bearish"}), "B8", ["label_differs"], id="differs"
        ),
    ],
)
def test_record_failures(row: dict[str, object], baseline: str, kinds: list[str]) -> None:
    assert harness.record_failures(row, baseline=baseline) == kinds


@pytest.mark.parametrize(
    ("compared", "where"),
    [
        pytest.param({3: True, 5: True}, [], id="both"),
        pytest.param({3: True}, ["P-0 h5"], id="h5-none"),
        pytest.param({3: True, 5: False}, ["P-0 h5"], id="h5-false"),
        pytest.param({}, ["P-0 h3", "P-0 h5"], id="none"),
    ],
)
def test_vacuous_failures(compared: dict[int, bool], where: list[str]) -> None:
    failures = harness.vacuous_failures(P0, compared)
    # The place is the rule set and the horizon only: no count is printed (D-4 point 5).
    assert [f.where for f in failures] == where
    assert {f.kind for f in failures} <= {"vacuous_equality"}


def _vacuous_where(result: AcceptanceResult) -> list[str]:
    return [f.where for f in result.failures if f.kind == "vacuous_equality"]


def test_an_unavailable_baseline_is_its_own_failure_kind(tmp_path: Path) -> None:
    # Negative case: P-1's rules checked against B2, which a 130-bar series cannot vote for.
    wrong = PlaceholderRules(name="P-1", baseline="B2", template=P1.template)
    result = _run(tmp_path, wrong, bars=synthetic_series(LAST, 130))
    assert not result.passed
    assert result.labels_checked == 42
    assert set(result.failure_kinds) == {"baseline_unavailable", "vacuous_equality"}
    assert "label_differs" not in result.failure_kinds


def _pit_unverified(
    bars: Sequence[PriceBar], late: set[date]
) -> tuple[list[PriceBar], Callable[[date], datetime]]:
    """Bars of the ``late`` sessions stamped 00:30 the next day, and runs at 01:00 then.

    So those sessions' records are ``insufficient`` with ``E-PIT-UNVERIFIED``
    (freeze pack 2.5 (0)); the other sessions run at 22:10 as usual.
    """
    moved = [
        bar.model_copy(
            update={"as_of": datetime.combine(bar.date + timedelta(days=1), time(0, 30), TAIPEI)}
        )
        if bar.date in late
        else bar
        for bar in bars
    ]

    def when(day: date) -> datetime:
        if day in late:
            return datetime.combine(day + timedelta(days=1), time(1), TAIPEI)
        return datetime.combine(day, harness.RUN_TIME, TAIPEI)

    return moved, when


def _window(bars: Sequence[PriceBar]) -> tuple[date, ...]:
    return acceptance_window([b.date for b in bars], report.taipei_date(FIXED_NOW))


def test_vacuous_equality_when_every_record_is_insufficient(tmp_path: Path) -> None:
    # Every session's fetched_at is after its cutoff: no record of any combination is evaluable.
    bars = synthetic_series(LAST, 360)
    moved, when = _pit_unverified(bars, set(_window(bars)))
    result = _run(tmp_path, P0, bars=moved, run_time=when)
    assert result.records == 42 and result.insufficient == 42
    assert "E-PIT-UNVERIFIED" in _missing_codes(tmp_path)
    assert result.failure_kinds == ("vacuous_equality",)
    assert _vacuous_where(result) == ["P-0 h3", "P-0 h5"]
    assert "失敗種類：vacuous_equality" in render_summary(result)


def test_vacuous_equality_when_no_evaluable_record_has_a_comparison(tmp_path: Path) -> None:
    # ADR-0030 supplement 5 point 3 (a): only the last five sessions are evaluable. h3 records
    # among them still have T + 3 inside the window; no h5 record has T + 5 there.
    bars = synthetic_series(LAST, 360)
    window = _window(bars)
    moved, when = _pit_unverified(bars, set(window[:-5]))
    result = _run(tmp_path, P0, bars=moved, run_time=when)
    assert result.labels_checked == 10 and result.compared > 0
    assert result.failure_kinds == ("vacuous_equality",)
    assert _vacuous_where(result) == ["P-0 h5"]


@dataclass(frozen=True)
class _SplitRules(PlaceholderRules):
    """P-0 at h3; at h5 a rule reading ``vol_ratio_20_120`` (N_req 121)."""

    def rule_bytes(self, horizon: int) -> bytes:
        data = super().rule_bytes(horizon)
        if horizon == 5:
            data = data.replace(b"field: close", b"field: vol_ratio_20_120")
        return data


def test_vacuous_equality_names_the_one_combination_left_insufficient(tmp_path: Path) -> None:
    # 110 bars: enough for h3's R = 61, never for h5's R = 121 -- only P-0 h5 is all insufficient.
    split = _SplitRules(name="P-0", baseline="B6", template=P0.template)
    result = _run(tmp_path, split, bars=synthetic_series(LAST, 110))
    rows = _records(tmp_path)
    h5 = [r for r in rows if "|h5|" in str(r["claim_id"])]
    assert h5 and all(r["label"] == "insufficient" for r in h5)
    assert all(r["label"] != "insufficient" for r in rows if r not in h5)
    assert result.failure_kinds == ("vacuous_equality",)
    assert _vacuous_where(result) == ["P-0 h5"]


# --- the window (D-7 point 6) -----------------------------------------------------------------


def test_the_window_is_the_latest_21_final_sessions_before_the_run_date() -> None:
    sessions = [d for d in (date(2026, 10, 1) + timedelta(days=i) for i in range(60))]
    sessions = [d for d in sessions if d.weekday() < 5 and d != date(2026, 10, 9)]  # a holiday
    run_date = date(2026, 11, 16)
    window = acceptance_window(sessions, run_date)
    before = [d for d in sessions if d < run_date]
    assert window == tuple(before[-21:])
    assert run_date not in window and all(d < run_date for d in window)
    with pytest.raises(HarnessRefused, match="fewer than 21"):
        acceptance_window(before[:20], run_date)


def test_the_run_takes_its_window_from_the_input_and_the_clock(tmp_path: Path) -> None:
    # Bars up to and including the run date: the run date itself is not in the window.
    bars = synthetic_series(date(2026, 11, 16), 360)
    result = _run(tmp_path, P0, bars=bars)
    finals = [b.date for b in bars]
    assert result.window == acceptance_window(finals, date(2026, 11, 16))
    assert result.window[-1] == LAST
    assert result.passed


def test_a_bar_stamped_before_its_cutoff_is_not_a_window_session(tmp_path: Path) -> None:
    bars = synthetic_series(LAST, 360)
    early = synthetic_series(LAST, 360, stamp_hour=14)
    mixed = [*bars[:-1], early[-1]]  # LAST is not final
    result = _run(tmp_path, P0, bars=mixed)
    assert result.window[-1] == _previous_weekday(LAST)


# --- synthetic fixtures (D-7 point 4) -----------------------------------------------------------


def _missing_codes(root: Path) -> set[str]:
    return {item["code"] for row in _records(root) for item in json.loads(str(row["missing_json"]))}


def test_fixture_sigma_degenerate(tmp_path: Path) -> None:
    bars = synthetic_series(LAST, 360, returns=lambda j: 0.0)  # every close equal
    result = _run(tmp_path, P0, bars=bars)
    assert result.records == 42
    assert result.insufficient == 42 and result.labels_checked == 0
    # Nothing was evaluable, so the equalities held over nothing (quant point 1 (a)).
    assert result.failure_kinds == ("vacuous_equality",)
    assert "E-VOL-DEGENERATE" in _missing_codes(tmp_path)
    rows = _records(tmp_path)
    assert all(json.loads(str(r["band_def"]))["sigma_d"] is None for r in rows)
    assert any("無法對照：threshold_inputs_missing" in line for line in result.output)


def test_fixture_insufficient_evidence_with_short_bars(tmp_path: Path) -> None:
    result = _run(tmp_path, P1, bars=synthetic_series(LAST, 45))
    assert result.records == 42 and result.insufficient == 42
    assert result.failure_kinds == ("vacuous_equality",)
    assert _missing_codes(tmp_path) & {"E-BARS-SHORT", "E-VOL-SHORT"}


def test_fixture_a_short_snapshot_keeps_the_labels_and_marks_b2(tmp_path: Path) -> None:
    result = _run(tmp_path, P1, bars=synthetic_series(LAST, 130))
    assert result.passed and result.insufficient == 0 and result.labels_checked == 42
    rows = _records(tmp_path)
    b2 = [json.loads(str(r["baseline_predictions_json"]))["B2"] for r in rows]
    assert all(item.get("reason") == "b2_realized_short" for item in b2)
    snapshot_sizes = {
        len(
            ForecastStore(tmp_path / "work" / harness.LEDGER_NAME)
            .snapshot(str(r["input_series_sha256"]))
            .bars
        )
        for r in rows
    }
    assert max(snapshot_sizes) == 130 and min(snapshot_sizes) < 315


@pytest.mark.parametrize(
    ("offset", "late"),
    [
        pytest.param(
            timedelta(hours=23, minutes=59, seconds=59, microseconds=999999),
            0,
            id="23:59:59.999999",
        ),
        pytest.param(timedelta(days=1), 1, id="00:00:00"),
    ],
)
def test_fixture_the_late_boundary(tmp_path: Path, offset: timedelta, late: int) -> None:
    result = _run(
        tmp_path,
        P0,
        run_time=lambda day: datetime.combine(day, time(0), TAIPEI) + offset,
    )
    assert result.passed
    rows = _records(tmp_path)
    assert len(rows) == 42 and {r["late"] for r in rows} == {late}
    # T is the session itself either way (the next session's bar is not yet stamped).
    assert sorted({str(r["data_as_of"]) for r in rows}) == [d.isoformat() for d in result.window]


# --- output (D-7 point 5) ---------------------------------------------------------------------


def test_the_header_is_the_adr_wording() -> None:
    assert HEADER == (
        "管線驗收：使用歷史資料，不是前瞻紀錄；只驗證程式流程，不是績效證據，不計入任何驗證統計；"
        "規則未經驗證。",
        "本次使用佔位規則，輸出不是任何將登記規則的判斷。",
    )


def test_the_summary_holds_no_label_and_no_comparison(tmp_path: Path) -> None:
    result = _run(tmp_path, P1)
    summary = render_summary(result)
    assert tuple(summary[:2]) == HEADER
    assert "管線驗收 P-1：通過" in summary
    text = "\n".join(summary)
    assert not any(word in text for word in LABEL_WORDS)
    assert not any(word in text for word in ("實現", "符合", "B1", "B6", "B8", "模型"))
    assert d4_violations(summary, unpassed_hashes=set()) == []
    assert result.ledger_sha256 in text and result.output_sha256 in text


# --- isolation (D-7 points 2-3, K-11) -----------------------------------------------------------


def _stand_in(root: Path) -> Path:
    backend = root / "backend"
    (backend / "data").mkdir(parents=True)
    return backend


@pytest.mark.parametrize("case", ["named", "in-data-folder", "env", "under-data"])
def test_production_paths_are_refused_before_anything_is_opened(tmp_path: Path, case: str) -> None:
    backend = _stand_in(tmp_path)
    env: dict[str, str] = {}
    if case == "named":
        target = tmp_path / "elsewhere" / "stock-desk.db"
    elif case == "in-data-folder":
        target = backend / "data" / "pipeline-acceptance.db"
    elif case == "env":
        target = tmp_path / "named-by-env.db"
        env = {claims.DB_PATH_ENV_VAR: str(target)}
    else:
        target = backend / "data" / "nested" / "pipeline-acceptance.db"
    with pytest.raises(HarnessRefused, match="refused"):
        refuse_production(target, backend_dir=backend, cwd=tmp_path, env=env)
    assert not target.exists()


def test_the_run_refuses_a_work_dir_in_the_production_data_folder(tmp_path: Path) -> None:
    backend = _stand_in(tmp_path)
    with pytest.raises(HarnessRefused):
        run_acceptance(
            backend / "data",
            bars=synthetic_series(LAST, 360),
            rules=P0,
            definition=definition(),
            wall_clock=lambda: FIXED_NOW,
            backend_dir=backend,
            env={},
            cwd=tmp_path,
        )
    assert sorted(p.name for p in (backend / "data").iterdir()) == []


def test_the_run_refuses_an_existing_ledger(tmp_path: Path) -> None:
    _run(tmp_path, P0)
    with pytest.raises(HarnessRefused, match="already exists"):
        _run(tmp_path, P0)


def test_the_injected_registry_is_restored(tmp_path: Path) -> None:
    before = (
        vars(definitions)["PUBLISHED_RULESETS"],
        vars(definitions)["PUBLISHED_DIRECTION_DEFINITIONS"],
        vars(definitions)["_read_rules_bytes"],
    )
    _run(tmp_path, P1)
    assert (
        vars(definitions)["PUBLISHED_RULESETS"],
        vars(definitions)["PUBLISHED_DIRECTION_DEFINITIONS"],
        vars(definitions)["_read_rules_bytes"],
    ) == before
    with pytest.raises(RuntimeError, match="inside"):
        with harness.injected_registry(P0, definition()):
            assert definitions.get_ruleset(P0.rules_version(3)) is not None
            raise RuntimeError("inside")
    assert vars(definitions)["PUBLISHED_RULESETS"] is before[0]
    with pytest.raises(definitions.UnpublishedVersionError):
        definitions.get_ruleset(P0.rules_version(3))


def test_k11_the_production_registries_are_empty_and_read_only() -> None:
    for name in ("PUBLISHED_RULESETS", "PUBLISHED_DIRECTION_DEFINITIONS"):
        value = getattr(registry, name)
        assert isinstance(value, MappingProxyType) and dict(value) == {}
    assert list(inspect.signature(record_forecasts).parameters) == [
        "store",
        "load_benchmark",
        "resolver",
    ]


def _app_sources() -> dict[str, str]:
    return {
        path.relative_to(APP_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(APP_ROOT.rglob("*.py"))
    }


def _imports_tests(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(
            a.name == "tests" or a.name.startswith("tests.") for a in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "tests":
            return True
    return False


def test_k11_no_app_module_imports_the_tests_or_the_harness() -> None:
    sources = _app_sources()
    assert {p for p, s in sources.items() if _imports_tests(s)} == set()
    assert {p for p, s in sources.items() if "pipeline_harness" in s} == set()


#: The module attributes the harness replaces (its injection seam).
SEAMS = frozenset(
    {
        "PUBLISHED_RULESETS",
        "PUBLISHED_DIRECTION_DEFINITIONS",
        "_read_rules_bytes",
        "_RULESET_CACHE",
        "_DEFINITION_CACHE",
    }
)


def _registry_rebinds(source: str) -> list[str]:
    """K-11: an ``app/`` module rebinding a registry seam (attribute, ``setattr``, ``global``)."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        found += [
            ast.unparse(t) for t in targets if isinstance(t, ast.Attribute) and t.attr in SEAMS
        ]
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"setattr", "delattr"}
            and any(isinstance(a, ast.Constant) and a.value in SEAMS for a in node.args)
        ):
            found.append(ast.unparse(node))
        if isinstance(node, ast.Global | ast.Nonlocal):
            found += [name for name in node.names if name in SEAMS]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                node.func.attr in {"__setitem__", "update", "clear"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in SEAMS - {"_RULESET_CACHE", "_DEFINITION_CACHE"}
            ):
                found.append(ast.unparse(node))
    return found


def test_k11_no_app_module_has_a_registry_injection_path() -> None:
    assert {p: v for p, s in _app_sources().items() if (v := _registry_rebinds(s))} == {}


@pytest.mark.parametrize(
    "source",
    [
        "definitions.PUBLISHED_RULESETS = {}\n",
        "import app\napp.forecast.definitions._read_rules_bytes = f\n",
        "setattr(definitions, 'PUBLISHED_DIRECTION_DEFINITIONS', x)\n",
        "def f():\n    global PUBLISHED_RULESETS\n    PUBLISHED_RULESETS = {}\n",
        "definitions._RULESET_CACHE: dict = {}\n",
    ],
)
def test_the_registry_rebind_scan_has_teeth(source: str) -> None:
    assert _registry_rebinds(source) != []


def test_the_harness_reads_no_price_cache_and_opens_only_its_own_ledger() -> None:
    path = Path(harness.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {getattr(n, "id", None) or getattr(n, "attr", None) for n in ast.walk(tree)}
    assert not names & {"PriceBarCache", "price_bars_cache", "load_market_benchmark"}
    modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    for forbidden in ("app.data.cache", "app.services", "app.data.db", "app.main", "app.scheduler"):
        assert not [m for m in modules if m == forbidden or m.startswith(f"{forbidden}.")]
    connects = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
    ]
    assert len(connects) == 1
    create = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_create_ledger"
    )
    assert connects[0] in list(ast.walk(create))
    run = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_acceptance"
    )
    order = [
        n.func.id
        for n in ast.walk(run)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in {"refuse_production", "_create_ledger"}
    ]
    assert order == ["refuse_production", "_create_ledger"]


def test_every_test_run_compares_against_stand_ins_only() -> None:
    # No test makes the production path rule look at the real <backend>/data/ or at
    # the process working directory's data/ (both default otherwise).
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"run_acceptance", "refuse_production"}
    ]
    assert len(calls) >= 3
    for call in calls:
        assert {"backend_dir", "env", "cwd"} <= {k.arg for k in call.keywords}


def test_the_harness_ledger_kind_is_forward_only(tmp_path: Path) -> None:
    _run(tmp_path, P0)
    store = ForecastStore(tmp_path / "work" / harness.LEDGER_NAME)
    assert {c.kind for c in store.forward_claims()} == {"forward"}
    assert len(store.forward_claims()) == 2
    (tmp_path / "work" / harness.LEDGER_NAME).unlink()  # nothing else was written
    assert sorted(p.name for p in (tmp_path / "work").iterdir()) == []
