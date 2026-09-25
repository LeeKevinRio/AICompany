"""Biased research stays in its box (ADR-0012 T-10; C-4, C-8, C-9, C-22, C-27; D-14).

* import layer: no ``app.*`` module outside ``app.research`` reaches it; the
  guarded modules of T-10 are listed and resolve when they exist; every file
  under ``app/research`` is scanned; ``app.backtest.basket`` never reaches
  ``app.sectors``; ``app.backtest.*`` never reaches ``app.sectors.store``;
* string / identifier layer: ``STOCK_DESK_RESEARCH_DB_PATH`` appears only
  under ``app/research`` (raw text, docstrings included); ``hindsight_view`` is
  defined and used only there; the research table names too;
* file layer: the research DB holds only research tables, every row carries
  the bias label and ``backfill_non_pit`` (CHECK constraints), busy_timeout;
* type / run-time layer: hindsight evaluations never become statistics rows,
  and the repository refuses them with ``BiasedDataRejected``.

Every scan has a teeth test.
"""

from __future__ import annotations

import ast
import dataclasses
import sqlite3
from collections.abc import Collection
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.backtest import sector_eval
from app.backtest.costs import CostModel
from app.data.panel import MarketPanel, PointInTimePanel
from app.research.sector_biased import BIAS_DIRECTIONS, BIAS_LABEL, hindsight_view
from app.research.sector_biased.store import (
    RESEARCH_DB_PATH_ENV_VAR,
    RESEARCH_TABLES,
    ResearchStore,
    resolve_research_db_path,
)
from app.research.sector_biased.study import backfill_frames, run_biased_study, save_study
from app.sectors import universe
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.models import StatsRecord
from app.sectors.store import BiasedDataRejected, SectorStatsRepository
from tests.import_graph import (
    APP_ROOT,
    imported_modules,
    module_path,
    offenders,
    reachable_app_modules,
)
from tests.sector_eval_helpers import SyntheticMarket, synthetic_market

RESEARCH_ROOT = APP_ROOT / "research"

#: ADR-0012 T-10 GUARDED_MODULES (the sector core is expanded from disk).
GUARDED = (
    "app.api.sectors",
    "app.services.sector_board",
    "app.backtest.sector_eval",
    "app.backtest.basket",
)
#: Wave 3 lands these; until then they must simply not exist.
LATER_WAVES = frozenset({"app.api.sectors", "app.services.sector_board"})


def _module_name(path: Path) -> str:
    relative = path.relative_to(APP_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _all_app_modules() -> list[str]:
    return sorted(_module_name(path) for path in APP_ROOT.rglob("*.py"))


def _outside_research() -> tuple[str, ...]:
    # ``app`` itself is left out: ``import_graph.module_path("app")`` cannot build a
    # path for the bare root, and ``app/__init__.py`` imports nothing.
    return tuple(
        name
        for name in _all_app_modules()
        if name != "app" and not (name == "app.research" or name.startswith("app.research."))
    )


# ---------------------------------------------------------------------------
# Import layer
# ---------------------------------------------------------------------------


def test_guarded_modules_resolve_or_belong_to_a_later_wave() -> None:
    for module in GUARDED:
        if module_path(module) is None:
            assert module in LATER_WAVES, f"{module} is missing"
    sectors = [name for name in _all_app_modules() if name.startswith("app.sectors")]
    assert "app.sectors.universe" in sectors and "app.sectors.store" in sectors


@pytest.mark.parametrize("module", [*GUARDED, "app.sectors", "app.scheduler", "app.main"])
def test_guarded_modules_never_reach_research(module: str) -> None:
    if module_path(module) is None:
        pytest.skip(f"{module} lands in a later wave")
    assert offenders(reachable_app_modules((module,)), "app.research") == []


def test_no_module_outside_research_reaches_research() -> None:
    roots = _outside_research()
    assert len(roots) > 100
    assert offenders(reachable_app_modules(roots), "app.research") == []


def test_every_research_file_is_scanned() -> None:
    files = sorted(RESEARCH_ROOT.rglob("*.py"))
    assert {path.name for path in files} >= {"__init__.py", "hindsight.py", "store.py", "study.py"}
    for path in files:
        name = _module_name(path)
        assert module_path(name) == path
        # Readable by the walk, and recognised as the forbidden package by it.
        imported_modules(path, name)
        assert offenders({name}, "app.research") == [name]


def test_research_boundary_scan_has_teeth(tmp_path: Path) -> None:
    leak = tmp_path / "leak.py"
    leak.write_text("from app.research.sector_biased import hindsight_view\n", encoding="utf-8")
    found = imported_modules(leak, "app.api.leak")
    assert offenders(found, "app.research") != []


def test_basket_never_reaches_the_sector_package() -> None:
    reached = reachable_app_modules(("app.backtest.basket",))
    assert offenders(reached, "app.sectors") == []
    assert offenders(reachable_app_modules(("app.backtest.sector_eval",)), "app.sectors") != []


def test_backtest_never_reaches_the_sector_store_or_research() -> None:
    backtest = tuple(name for name in _all_app_modules() if name.startswith("app.backtest"))
    reached = reachable_app_modules(backtest)
    assert "app.sectors.store" not in reached
    assert offenders(reached, "app.research") == []


# ---------------------------------------------------------------------------
# String / identifier layer
# ---------------------------------------------------------------------------

PROTECTED_STRINGS = (
    "STOCK_DESK_RESEARCH_DB_PATH",
    "research_study_runs",
    "research_backfill_bars",
)


def _string_hits(root: Path) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == "research":
            continue
        text = path.read_text(encoding="utf-8")
        found = [needle for needle in PROTECTED_STRINGS if needle in text]
        if found:
            hits[str(relative)] = found
    return hits


def test_research_db_names_appear_only_under_research() -> None:
    assert _string_hits(APP_ROOT) == {}
    inside = "".join(p.read_text(encoding="utf-8") for p in RESEARCH_ROOT.rglob("*.py"))
    assert all(needle in inside for needle in PROTECTED_STRINGS)


def test_research_string_scan_has_teeth(tmp_path: Path) -> None:
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "leak.py").write_text(
        '"""Mentions STOCK_DESK_RESEARCH_DB_PATH in prose."""\n', encoding="utf-8"
    )
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "ok.py").write_text("X = 'research_study_runs'\n", encoding="utf-8")
    assert _string_hits(tmp_path) == {"api/leak.py": ["STOCK_DESK_RESEARCH_DB_PATH"]}


def _identifier_uses(path: Path, name: str) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name) and node.id == name:
            lines.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == name:
            lines.append(node.lineno)
        elif isinstance(node, ast.alias) and name in (node.name.split(".")[-1], node.asname):
            lines.append(getattr(node, "lineno", 0))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            lines.append(node.lineno)
    return lines


def _hindsight_offenders(root: Path) -> list[str]:
    return [
        str(path.relative_to(root))
        for path in sorted(root.rglob("*.py"))
        if "research" not in path.relative_to(root).parts
        and _identifier_uses(path, "hindsight_view")
    ]


def test_hindsight_view_is_defined_and_called_only_under_research() -> None:
    assert _hindsight_offenders(APP_ROOT) == []
    definitions = [
        path
        for path in RESEARCH_ROOT.rglob("*.py")
        if any(
            isinstance(node, ast.FunctionDef) and node.name == "hindsight_view"
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )
    ]
    assert [p.name for p in definitions] == ["hindsight.py"]


def test_hindsight_scan_has_teeth(tmp_path: Path) -> None:
    (tmp_path / "leak.py").write_text(
        "from app.research.sector_biased import hindsight_view\nv = hindsight_view(p, t)\n",
        encoding="utf-8",
    )
    (tmp_path / "shadow.py").write_text("def hindsight_view(p, t):\n    pass\n", encoding="utf-8")
    assert _hindsight_offenders(tmp_path) == ["leak.py", "shadow.py"]


# ---------------------------------------------------------------------------
# File layer
# ---------------------------------------------------------------------------


def test_research_db_holds_only_research_tables(tmp_path: Path) -> None:
    store = ResearchStore(tmp_path / "research.db")
    with closing(sqlite3.connect(store.db_path)) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert tables == RESEARCH_TABLES
    assert not any(name.startswith(("sector_", "pit_", "market_", "price_")) for name in tables)


def test_research_connections_set_busy_timeout(tmp_path: Path) -> None:
    store = ResearchStore(tmp_path / "research.db")
    with closing(store._connect()) as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] > 0


def test_research_rows_must_carry_the_bias_label(tmp_path: Path) -> None:
    store = ResearchStore(tmp_path / "research.db")
    with closing(sqlite3.connect(store.db_path)) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO research_backfill_bars (symbol, session_date, source, fetched_at, "
            "data_regime, bias_label) VALUES ('2330', '2020-01-02', 'x', 'now', "
            "'backfill_non_pit', 'clean')"
        )
    with closing(sqlite3.connect(store.db_path)) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO research_backfill_bars (symbol, session_date, source, fetched_at, "
            "data_regime, bias_label) VALUES ('2330', '2020-01-02', 'x', 'now', "
            f"'forward_pit', '{BIAS_LABEL}')"
        )


def test_research_db_path_comes_from_its_own_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RESEARCH_DB_PATH_ENV_VAR, str(tmp_path / "elsewhere.db"))
    assert resolve_research_db_path() == tmp_path / "elsewhere.db"
    monkeypatch.delenv(RESEARCH_DB_PATH_ENV_VAR)
    assert resolve_research_db_path().name == "stock-desk-research.db"


def test_backfilled_bars_go_to_the_research_db_only(tmp_path: Path) -> None:
    store = ResearchStore(tmp_path / "research.db")
    bars = pd.DataFrame(
        {
            "symbol": ["2330", "2317"],
            "session_date": [date(2020, 1, 2), date(2020, 1, 2)],
            "open": [330.0, 90.0],
            "high": [335.0, 91.0],
            "low": [329.0, 89.0],
            "close": [333.0, 90.5],
            "shares": [1000, 2000],
            "traded_value": [3.3e5, 1.8e5],
        }
    )
    assert store.save_backfill_bars(bars, source="finmind", fetched_at=datetime.now(UTC)) == 2
    loaded = store.load_backfill_bars()
    assert list(loaded["symbol"]) == ["2317", "2330"]
    with closing(sqlite3.connect(store.db_path)) as conn:
        labels = {row[0] for row in conn.execute("SELECT bias_label FROM research_backfill_bars")}
    assert labels == {BIAS_LABEL}


# ---------------------------------------------------------------------------
# Type / run-time layer, and the study end to end
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def backfill_panel() -> tuple[SyntheticMarket, MarketPanel]:
    """Today's universe applied to back-filled history, recorded at fetch time."""
    market = synthetic_market(seed=31, warmup=70, forward=130, n_dividends=0)
    frames = market.panel.frames
    bars = frames.bars.loc[frames.bars["source"] != "finmind_warmup"]
    bars = pd.concat([frames.bars.loc[frames.bars["source"] == "finmind_warmup"], bars])
    bars = bars.sort_values(["session_date", "symbol", "recorded_at"]).drop_duplicates(
        ["session_date", "symbol"], keep="first"
    )
    final_class = frames.classification.loc[
        frames.classification["run_id"] == frames.classification["run_id"].iloc[-1]
    ]
    classification = {
        str(r.symbol): (str(r.sector_code), str(r.sector_name))
        for r in final_class.itertuples(index=False)
    }
    fetched = datetime(2026, 9, 25, 3, tzinfo=UTC)
    panel = MarketPanel(
        backfill_frames(
            bars.drop(columns=["run_id", "recorded_at", "source", "change"]),
            listing=sorted(classification),
            classification=classification,
            fetched_at=fetched,
        )
    )
    return market, panel


def test_backfill_is_invisible_to_point_in_time_views(
    backfill_panel: tuple[SyntheticMarket, MarketPanel],
) -> None:
    market, panel = backfill_panel
    t = market.calendar[-20]
    calc = universe.calculation_set(panel.as_of(t), V1)
    assert calc.market.expected == frozenset()
    hindsight = universe.calculation_set(hindsight_view(panel, t), V1)
    assert hindsight.regime == "hindsight" and hindsight.market.expected


def test_the_biased_study_is_labelled_split_and_stored_in_research_only(
    backfill_panel: tuple[SyntheticMarket, MarketPanel],
    tmp_path: Path,
) -> None:
    market, panel = backfill_panel
    report = run_biased_study(
        panel,
        V1,
        cost_model=CostModel(),
        start=market.calendar[70],
        seed=4,
        train_sessions=60,
        test_sessions=20,
    )
    assert report.bias_label == BIAS_LABEL == "含已知偏誤，不得上畫面"
    assert dict(report.bias_directions) == dict(BIAS_DIRECTIONS)
    assert report.regime == "hindsight" and report.data_regime == "backfill_non_pit"
    assert report.folds, "the study must report walk-forward folds"
    in_sample, out_of_sample = report.segment("in_sample"), report.segment("out_of_sample")
    assert in_sample.sample_end is not None and out_of_sample.sample_start is not None
    # Non-overlapping: the first out-of-sample decision is at (or after) the
    # close the last in-sample sample exited on.
    assert in_sample.summary.sample_count > 0 and out_of_sample.summary.sample_count > 0
    assert in_sample.sample_end <= out_of_sample.sample_start
    store = ResearchStore(tmp_path / "research.db")
    study_id = save_study(report, store)
    rows = store.study_rows(study_id)
    assert {row.segment for row in rows} == {"in_sample", "out_of_sample", "full"}
    assert {row.bias_label for row in rows} == {BIAS_LABEL}
    assert all(row.report["bias_label"] == BIAS_LABEL for row in rows)


def test_hindsight_runs_are_marked_and_cannot_mix_with_point_in_time(
    backfill_panel: tuple[SyntheticMarket, MarketPanel],
) -> None:
    market, panel = backfill_panel
    run = sector_eval.evaluate_views(
        lambda t: hindsight_view(panel, t),
        panel,
        V1,
        cost_model=CostModel(),
        start=market.calendar[-30],
        m=1,
        seed=1,
    )
    assert run.regime == "hindsight"
    flip = {"n": 0}

    def mixed(t: date) -> PointInTimePanel:
        flip["n"] += 1
        return market.panel.as_of(t) if flip["n"] % 2 else hindsight_view(market.panel, t)

    with pytest.raises(ValueError, match="mix"):
        sector_eval.evaluate_views(
            mixed, market.panel, V1, cost_model=CostModel(), start=market.calendar[-30], m=1, seed=1
        )


class _Verifier:
    def __init__(self, known: Collection[str]) -> None:
        self._known = frozenset(known)

    def existing_run_ids(self, run_ids: Collection[str]) -> frozenset[str]:
        return frozenset(run_ids) & self._known


def _record(**overrides: object) -> StatsRecord:
    base = StatsRecord(
        run_id="r1",
        method_version=V1.method_version,
        regime="pit",
        data_regime="forward_pit",
        source_run_ids=("bars-1",),
        m_at_evaluation=1,
        sample_count=10,
        effective_sample_count=10.0,
        beat_count_net=5,
        beat_count_gross=6,
        base_rate_net=0.4,
        base_rate_gross=0.5,
        ci_low_net=0.2,
        ci_high_net=0.8,
        bootstrap_low_net=0.2,
        bootstrap_high_net=0.8,
        delta_real=10.0,
        delta_shuffle=1.0,
        sample_start=date(2020, 1, 2),
        sample_end=date(2020, 6, 1),
        stats_as_of=date(2020, 6, 8),
        computed_at=datetime(2026, 9, 25, tzinfo=UTC),
        recompute_session=date(2020, 6, 8),
        running_commit="abc",
        selfcheck_passed=True,
        data_quality_passed=True,
        pit_history_missing=False,
        gate_checks=(),
    )
    return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"regime": "hindsight"},
        {"data_regime": "backfill_non_pit"},
        {"source_run_ids": ("bf-bars-000001",)},
        {"source_run_ids": ()},
    ],
)
def test_the_repository_refuses_biased_records(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    repo = SectorStatsRepository(_Verifier({"bars-1"}), tmp_path / "main.db")
    repo.save(_record())
    with pytest.raises(BiasedDataRejected):
        repo.save(_record(run_id="r2", **overrides))


@pytest.mark.skipif(module_path("app.api.sectors") is None, reason="app.api.sectors: wave 3")
def test_api_response_ignores_the_research_db() -> None:  # pragma: no cover - wave 3
    pytest.fail("wave 3: compare the momentum response with and without a populated research DB")
