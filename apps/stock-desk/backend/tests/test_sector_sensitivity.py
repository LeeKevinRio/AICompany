"""Sensitivity variants of the biased study (ADR-0012 D-15; C-48, C-49; methodology §11.1).

* **T-31** -- ``app/research/**`` never inherits from, ``dataclasses.replace``-s
  or constructs a published type (AST scan, with teeth); ``ResearchVariant``
  refuses ``sector-rel-*`` names and names outside its namespace; each variant
  differs from its base in exactly one parameter and carries the base's own
  ``gate`` object; ``SENSITIVITY_VARIANTS`` is exactly the two independent
  axes of §11.1 -- liquidity {NT$5M, NT$20M} and minimum constituents {3, 8}
  -- with no cross combination;
* **T-32** -- a point-in-time view, a non-backfill source, or a panel reaching
  D0 each raise and leave the research DB's row counts unchanged; one run
  outputs the base and every variant, each row labelled with the bias label,
  ``variant_of`` and ``variant_diff``; the sensitivity path calls the very
  ``calculation_set`` / ``rank_sectors`` objects of ``app.sectors``; and, as
  T-10, the API response is byte-identical with or without the research DB.
"""

from __future__ import annotations

import ast
import dataclasses
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app.backtest import sector_eval
from app.backtest.costs import CostModel
from app.data.market_panel import MarketPanelReader, MarketPanelStore
from app.data.panel import MarketPanel, PanelFrames
from app.research.sector_biased import sensitivity, study
from app.research.sector_biased.hindsight import BIAS_LABEL
from app.research.sector_biased.sensitivity import (
    LIQUIDITY,
    MIN_CONSTITUENTS,
    SENSITIVITY_BASE,
    SENSITIVITY_VARIANTS,
    InvalidVariant,
    ResearchCoverageRules,
    ResearchUniverseRules,
    ResearchVariant,
    SensitivityReport,
    check_variant,
    derive_variant,
    expected_versions,
    run_sensitivity,
    save_sensitivity,
    variant_diff,
)
from app.research.sector_biased.store import RESEARCH_DB_PATH_ENV_VAR, ResearchStore
from app.research.sector_biased.study import (
    BiasedScopeViolation,
    backfill_frames,
    run_biased_study,
    save_study,
)
from app.sectors import ranking, universe
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.definition import (
    CoverageRules,
    SectorMomentumDefinition,
    UniverseRules,
    UnpublishedDefinition,
    is_method_version,
    require_published,
)
from tests.import_graph import APP_ROOT
from tests.sector_board_helpers import card_client, live_card, verified_runtime
from tests.sector_eval_helpers import SyntheticMarket, synthetic_market

RESEARCH_ROOT = APP_ROOT / "research"
CARD_NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)
TRAIN, TEST = 60, 20

#: The published concrete types research code may not extend, replace or build (C-48).
PUBLISHED_TYPES = frozenset(
    {"SectorMomentumDefinition", "UniverseRules", "CoverageRules", "GateRules"}
)


# ---------------------------------------------------------------------------
# T-31: the research types
# ---------------------------------------------------------------------------


def _research_offenders(root: Path) -> list[str]:
    """Inheritance from, ``replace`` on, or construction of a published type under ``root``."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        where = path.relative_to(root).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
                    if name in PUBLISHED_TYPES:
                        found.append(f"{where}:{node.lineno}:inherits {name}")
            elif isinstance(node, ast.ImportFrom) and node.module == "dataclasses":
                if any(alias.name == "replace" for alias in node.names):
                    found.append(f"{where}:{node.lineno}:imports dataclasses.replace")
            elif isinstance(node, ast.Attribute) and node.attr == "replace":
                if isinstance(node.value, ast.Name) and node.value.id == "dataclasses":
                    found.append(f"{where}:{node.lineno}:dataclasses.replace")
            elif isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name in PUBLISHED_TYPES:
                    found.append(f"{where}:{node.lineno}:constructs {name}")
                elif name == "replace" and isinstance(func, ast.Name):
                    found.append(f"{where}:{node.lineno}:replace()")
    return found


def test_research_never_extends_replaces_or_builds_a_published_type() -> None:
    files = {path.name for path in RESEARCH_ROOT.rglob("*.py")}
    assert "sensitivity.py" in files
    assert _research_offenders(RESEARCH_ROOT) == []


def test_research_type_scan_has_teeth(tmp_path: Path) -> None:
    cases = {
        "a.py": "class Loose(SectorMomentumDefinition):\n    pass\n",
        "b.py": "import app.sectors.definition as d\nclass Loose(d.UniverseRules):\n    pass\n",
        "c.py": "import dataclasses\nx = dataclasses.replace(V1, holding_days=10)\n",
        "d.py": "from dataclasses import replace\nx = replace(V1)\n",
        "e.py": "x = CoverageRules(min_constituents=5)\n",
        "f.py": "import app.sectors.definition as d\nx = d.GateRules()\n",
    }
    for name, source in cases.items():
        (tmp_path / name).write_text(source, encoding="utf-8")
    found = _research_offenders(tmp_path)
    for name in cases:
        assert any(hit.startswith(f"{name}:") for hit in found), name


def test_research_rules_mirror_the_published_rules_field_for_field() -> None:
    def names(cls: Any) -> list[str]:
        return [field.name for field in dataclasses.fields(cls)]

    assert names(ResearchUniverseRules) == names(UniverseRules)
    assert names(ResearchCoverageRules) == names(CoverageRules)
    for cls in (ResearchVariant, ResearchUniverseRules, ResearchCoverageRules):
        assert dataclasses.is_dataclass(cls)
        assert vars(cls)["__dataclass_params__"].frozen
        assert cls.__mro__[1:] == (object,)  # inherits from nothing


def _variant(**overrides: object) -> ResearchVariant:
    base = SENSITIVITY_VARIANTS[0]
    fields = {field.name: getattr(base, field.name) for field in dataclasses.fields(base)}
    fields.update(overrides)
    return ResearchVariant(**fields)


@pytest.mark.parametrize(
    "name",
    [
        "sector-rel-v1.0-L5-H5",  # a method version
        "sector-rel-v1.1-L20-H5",
        "research-sens-v1.0-L5-H5-liq5m",  # upper case is outside the namespace
        "research-sens-",
        "research-sens-v1.0--liq5m",
        "research-sensv1.0",
        "research-x-v1.0",
        "sens-v1.0-l5-h5-liq5m",
        "research-sens-v1.0-l5-h5-liq5m ",
    ],
)
def test_a_variant_name_outside_the_research_namespace_is_refused(name: str) -> None:
    with pytest.raises(InvalidVariant):
        _variant(method_version=name)


def test_every_variant_name_is_in_the_namespace_and_never_a_method_version() -> None:
    names = [variant.method_version for variant in SENSITIVITY_VARIANTS]
    assert names == [
        "research-sens-v1.0-l5-h5-liq5m",
        "research-sens-v1.0-l5-h5-liq20m",
        "research-sens-v1.0-l5-h5-minc3",
        "research-sens-v1.0-l5-h5-minc8",
    ]
    for variant in SENSITIVITY_VARIANTS:
        assert sensitivity.RESEARCH_VERSION_PATTERN.fullmatch(variant.method_version)
        assert not is_method_version(variant.method_version)
        with pytest.raises(UnpublishedDefinition):
            require_published(variant)


def _flat(definition: Any) -> dict[str, object]:
    """Every parameter by value, independently of ``sensitivity.parameters``."""
    flat: dict[str, object] = {
        name: getattr(definition, name)
        for name in ("lookback_days", "holding_days", "open_limit_up_factor")
    }
    flat["single_stock_dominance_share"] = definition.single_stock_dominance_share
    for field in dataclasses.fields(UniverseRules):
        flat[f"universe.{field.name}"] = getattr(definition.universe, field.name)
    for field in dataclasses.fields(CoverageRules):
        flat[f"coverage.{field.name}"] = getattr(definition.coverage, field.name)
    return flat


@pytest.mark.parametrize("variant", SENSITIVITY_VARIANTS, ids=lambda v: v.method_version)
def test_each_variant_changes_exactly_one_parameter_and_shares_the_gate(
    variant: ResearchVariant,
) -> None:
    base = SENSITIVITY_BASE
    assert base is V1 and variant.variant_of == base.method_version
    assert variant.gate is base.gate
    left, right = _flat(base), _flat(variant)
    changed = [name for name in left if left[name] != right[name]]
    assert len(changed) == 1 and changed[0] in (LIQUIDITY, MIN_CONSTITUENTS)
    assert list(variant_diff(base, variant)) == changed
    assert (variant.lookback_days, variant.holding_days, variant.open_limit_up_factor) == (
        base.lookback_days,
        base.holding_days,
        base.open_limit_up_factor,
    )
    assert variant.coverage.min_constituents >= 3


def test_the_variant_table_is_exactly_the_two_axes_of_section_11_1() -> None:
    base = _flat(SENSITIVITY_BASE)
    table = set()
    for variant in SENSITIVITY_VARIANTS:
        ((name, values),) = variant_diff(SENSITIVITY_BASE, variant).items()
        table.add((name, values["variant"]))
        # The other axis stays at the base value: no cross combination.
        other = MIN_CONSTITUENTS if name == LIQUIDITY else LIQUIDITY
        assert _flat(variant)[other] == base[other]
    assert table == {
        (LIQUIDITY, 5_000_000.0),
        (LIQUIDITY, 20_000_000.0),
        (MIN_CONSTITUENTS, 3),
        (MIN_CONSTITUENTS, 8),
    }
    assert len(SENSITIVITY_VARIANTS) == 4
    assert expected_versions() == (
        V1.method_version,
        *(variant.method_version for variant in SENSITIVITY_VARIANTS),
    )


def test_variants_that_break_the_rules_are_refused() -> None:
    with pytest.raises(InvalidVariant, match="at least 3"):
        derive_variant(V1, MIN_CONSTITUENTS, 2, "minc2")
    with pytest.raises(InvalidVariant):
        derive_variant(V1, LIQUIDITY, 0.0, "liq0")
    with pytest.raises(UnpublishedDefinition):
        derive_variant(dataclasses.replace(V1), LIQUIDITY, 5e6, "liq5m")
    two = _variant(
        coverage=dataclasses.replace(SENSITIVITY_VARIANTS[0].coverage, min_constituents=8)
    )
    with pytest.raises(InvalidVariant, match="exactly one"):
        check_variant(V1, two)
    copied_gate = _variant(gate=dataclasses.replace(V1.gate))
    with pytest.raises(InvalidVariant, match="gate"):
        check_variant(V1, copied_gate)
    with pytest.raises(InvalidVariant, match="derived"):
        check_variant(V1, _variant(variant_of="sector-rel-v1.1-L20-H5"))
    shifted = _variant(holding_days=10)
    with pytest.raises(InvalidVariant, match="exactly one"):
        check_variant(V1, shifted)


# ---------------------------------------------------------------------------
# T-32: data scope, output, same core functions, API untouched
# ---------------------------------------------------------------------------


def _backfill_panel(market: SyntheticMarket) -> MarketPanel:
    """Today's universe over back-filled history (as in test_research_isolation)."""
    frames = market.panel.frames
    bars = frames.bars.sort_values(["session_date", "symbol", "recorded_at"]).drop_duplicates(
        ["session_date", "symbol"], keep="first"
    )
    final_class = frames.classification.loc[
        frames.classification["run_id"] == frames.classification["run_id"].iloc[-1]
    ]
    classification = {
        str(r.symbol): (str(r.sector_code), str(r.sector_name))
        for r in final_class.itertuples(index=False)
    }
    return MarketPanel(
        backfill_frames(
            bars.drop(columns=["run_id", "recorded_at", "source", "change"]),
            listing=sorted(classification),
            classification=classification,
            fetched_at=datetime(2026, 9, 25, 3, tzinfo=UTC),
        )
    )


def _market_db(path: Path, d0: date | None) -> MarketPanelReader:
    """A market DB whose D0 is ``d0`` (all four kinds ok that session), or none."""
    store = MarketPanelStore(path)
    if d0 is not None:
        for kind in ("bars", "listing", "classification", "dividend_announce"):
            store.record_run(
                kind=kind,
                session_date=d0,
                source="twse_snapshot",
                status="ok",
                row_count=0,
                expected_count=None,
            )
    return MarketPanelReader(path)


@dataclass(frozen=True)
class Run:
    market: SyntheticMarket
    panel: MarketPanel
    data_end: date
    no_d0: MarketPanelReader
    report: SensitivityReport
    #: ``(function, definition)`` of every call the spies saw.
    calls: tuple[tuple[str, object], ...]
    research_db: Path


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Run]:
    market = synthetic_market(seed=31, warmup=70, forward=130, n_dividends=0)
    panel = _backfill_panel(market)
    data_end = max(panel.frames.runs["session_date"])
    root = tmp_path_factory.mktemp("sensitivity")
    no_d0 = _market_db(root / "market-none.db", None)
    calls: list[tuple[str, object]] = []
    original_calc, original_rank = universe.calculation_set, ranking.rank_sectors

    def spy_calc(view: Any, definition: Any) -> Any:
        calls.append(("calculation_set", definition))
        return original_calc(view, definition)

    def spy_rank(calc: Any, definition: Any) -> Any:
        calls.append(("rank_sectors", definition))
        return original_rank(calc, definition)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sector_eval, "calculation_set", spy_calc)
        patch.setattr(sector_eval, "rank_sectors", spy_rank)
        report = run_sensitivity(
            panel,
            market_db=no_d0,
            cost_model=CostModel(),
            start=market.calendar[70],
            seed=4,
            train_sessions=TRAIN,
            test_sessions=TEST,
        )
    research_db = root / "research.db"
    save_sensitivity(report, ResearchStore(research_db))
    yield Run(market, panel, data_end, no_d0, report, tuple(calls), research_db)


def test_one_run_outputs_the_base_and_every_variant(run: Run) -> None:
    report = run.report
    assert [entry.method_version for entry in report.entries] == list(expected_versions())
    assert report.bias_label == BIAS_LABEL and report.base_version == V1.method_version
    assert report.d0 is None and report.data_end == run.data_end
    for entry in report.entries:
        assert entry.variant_of == V1.method_version
        assert entry.study.regime == "hindsight" and entry.study.data_regime == "backfill_non_pit"
        assert entry.study.bias_label == BIAS_LABEL
        assert entry.study.segment("full").summary.sample_count > 0
    assert dict(report.entry(V1.method_version).variant_diff) == {}
    liq5m = report.entry(SENSITIVITY_VARIANTS[0].method_version)
    assert dict(liq5m.variant_diff) == {LIQUIDITY: {"base": 10_000_000.0, "variant": 5_000_000.0}}


def test_every_stored_row_carries_the_label_variant_of_and_variant_diff(run: Run) -> None:
    rows = ResearchStore(run.research_db).sensitivity_rows(run.report.sensitivity_id)
    assert len(rows) == len(expected_versions()) * 3
    assert {row.method_version for row in rows} == set(expected_versions())
    for row in rows:
        assert row.bias_label == BIAS_LABEL and row.report["bias_label"] == BIAS_LABEL
        assert row.variant_of == V1.method_version == row.report["variant_of"]
        entry = run.report.entry(row.method_version)
        assert row.variant_diff == {k: dict(v) for k, v in entry.variant_diff.items()}
        assert row.report["variant_diff"] == row.variant_diff
    minc3 = [r for r in rows if r.method_version.endswith("-minc3")]
    assert {r.segment for r in minc3} == {"in_sample", "out_of_sample", "full"}
    assert minc3[0].variant_diff == {MIN_CONSTITUENTS: {"base": 5, "variant": 3}}


def test_the_sensitivity_path_calls_the_core_function_objects(run: Run) -> None:
    assert vars(sector_eval)["calculation_set"] is universe.calculation_set
    assert vars(sector_eval)["rank_sectors"] is ranking.rank_sectors
    for function in ("calculation_set", "rank_sectors"):
        seen = {id(definition) for name, definition in run.calls if name == function}
        wanted = {id(SENSITIVITY_BASE), *(id(v) for v in SENSITIVITY_VARIANTS)}
        assert seen == wanted, function
    # No second implementation in the research package.
    defined = {
        node.name
        for path in RESEARCH_ROOT.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef)
    }
    assert not defined & {"calculation_set", "rank_sectors", "eligible", "assess", "decide"}


def test_a_variant_reaches_the_core_functions(run: Run) -> None:
    """Sanity: the variant's value is what the core reads (min constituents 8 ranks fewer)."""
    from app.research.sector_biased import hindsight_view

    view = hindsight_view(run.panel, run.market.calendar[-20])
    minc8 = SENSITIVITY_VARIANTS[3]
    assert minc8.coverage.min_constituents == 8

    def ranked(definition: Any) -> int:
        calc = universe.calculation_set(view, definition)
        return len(ranking.rank_sectors(calc, definition).ranked)

    assert 0 < ranked(minc8) < ranked(SENSITIVITY_BASE)
    base_full = run.report.entry(V1.method_version).study.segment("full").summary
    minc8_full = run.report.entry(minc8.method_version).study.segment("full").summary
    assert base_full != minc8_full


def _counts(path: Path) -> dict[str, int]:
    return ResearchStore(path).row_counts()


def _attempt(
    run: Run, panel: MarketPanel, market_db: MarketPanelReader, store: Path, match: str
) -> None:
    """The whole pipeline (run, then save) for both the study and the sensitivity."""
    research = ResearchStore(store)
    start = run.market.calendar[70]

    def sensitivity_job() -> None:
        report = run_sensitivity(
            panel,
            market_db=market_db,
            cost_model=CostModel(),
            start=start,
            seed=4,
            train_sessions=TRAIN,
            test_sessions=TEST,
        )
        save_sensitivity(report, research)

    def study_job() -> None:
        report = run_biased_study(
            panel,
            V1,
            market_db=market_db,
            cost_model=CostModel(),
            start=start,
            seed=4,
            train_sessions=TRAIN,
            test_sessions=TEST,
        )
        save_study(report, research)

    for job in (sensitivity_job, study_job):
        with pytest.raises(BiasedScopeViolation, match=match):
            job()


def _with_runs(panel: MarketPanel, change: Callable[[pd.DataFrame], pd.DataFrame]) -> MarketPanel:
    frames = panel.frames
    return MarketPanel(dataclasses.replace(frames, runs=change(frames.runs.copy())))


def test_a_point_in_time_view_is_refused_and_writes_nothing(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "research.db"
    save_sensitivity(run.report, ResearchStore(store))
    before = _counts(store)
    monkeypatch.setattr(study, "hindsight_view", lambda panel, t: panel.as_of(t))
    _attempt(run, run.panel, run.no_d0, store, "read 'pit' views")
    assert _counts(store) == before


def test_a_source_other_than_backfill_is_refused_and_writes_nothing(
    run: Run, tmp_path: Path
) -> None:
    store = tmp_path / "research.db"
    save_sensitivity(run.report, ResearchStore(store))
    before = _counts(store)

    def one_live_run(runs: pd.DataFrame) -> pd.DataFrame:
        runs.loc[runs.index[0], "source"] = "twse_snapshot"
        return runs

    _attempt(run, _with_runs(run.panel, one_live_run), run.no_d0, store, "twse_snapshot")
    assert _counts(store) == before


@pytest.mark.parametrize("offset", [0, -1, -60])
def test_a_panel_reaching_d0_is_refused_and_writes_nothing(
    run: Run, tmp_path: Path, offset: int
) -> None:
    """D0 on, or before, the panel's last session."""
    store = tmp_path / "research.db"
    save_sensitivity(run.report, ResearchStore(store))
    before = _counts(store)
    calendar = sorted(set(run.panel.frames.runs["session_date"]))
    d0 = calendar[len(calendar) - 1 + offset]
    _attempt(run, run.panel, _market_db(tmp_path / "market.db", d0), store, "on or after D0")
    assert _counts(store) == before


def test_a_d0_after_the_panel_is_admitted(run: Run, tmp_path: Path) -> None:
    reader = _market_db(tmp_path / "market.db", run.data_end + timedelta(days=1))
    scope = study.admit_biased_panel(run.panel, reader)
    assert scope.d0 == run.data_end + timedelta(days=1) and scope.data_end == run.data_end


def test_a_missing_market_db_is_not_read_as_no_d0(run: Run, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        study.admit_biased_panel(run.panel, MarketPanelReader(tmp_path / "absent.db"))
    assert not (tmp_path / "absent.db").exists()


def test_a_panel_without_runs_is_refused(run: Run) -> None:
    empty = _with_runs(run.panel, lambda runs: runs.iloc[0:0])
    with pytest.raises(BiasedScopeViolation, match="no runs"):
        study.admit_biased_panel(empty, run.no_d0)


def test_a_partial_or_out_of_scope_report_is_never_stored(run: Run, tmp_path: Path) -> None:
    store = tmp_path / "research.db"
    research = ResearchStore(store)
    before = _counts(store)
    partial = dataclasses.replace(run.report, entries=run.report.entries[:-1])
    with pytest.raises(InvalidVariant, match="every variant"):
        save_sensitivity(partial, research)
    shuffled = dataclasses.replace(run.report, entries=run.report.entries[::-1])
    with pytest.raises(InvalidVariant):
        save_sensitivity(shuffled, research)
    late = dataclasses.replace(run.report, d0=run.data_end)
    with pytest.raises(BiasedScopeViolation):
        save_sensitivity(late, research)
    study_report = run.report.entries[0].study
    with pytest.raises(BiasedScopeViolation):
        save_study(dataclasses.replace(study_report, d0=study_report.data_end), research)
    assert _counts(store) == before


def test_save_refuses_entries_that_are_not_labelled_hindsight_backfill(
    run: Run, tmp_path: Path
) -> None:
    store = tmp_path / "research.db"
    research = ResearchStore(store)
    before = _counts(store)
    entries = run.report.entries

    def with_last(**changes: object) -> SensitivityReport:
        last = entries[-1]
        study_changes = {k: v for k, v in changes.items() if k != "variant_of"}
        entry = dataclasses.replace(
            last,
            variant_of=str(changes.get("variant_of", last.variant_of)),
            study=dataclasses.replace(last.study, **study_changes),  # type: ignore[arg-type]
        )
        return dataclasses.replace(run.report, entries=(*entries[:-1], entry))

    with pytest.raises(ValueError, match="bias label"):
        save_sensitivity(dataclasses.replace(run.report, bias_label="clean"), research)
    with pytest.raises(BiasedScopeViolation):
        save_sensitivity(with_last(regime="pit"), research)
    with pytest.raises(BiasedScopeViolation):
        save_sensitivity(with_last(data_regime="forward_pit"), research)
    with pytest.raises(ValueError, match="labelled"):
        save_sensitivity(with_last(bias_label="clean"), research)
    with pytest.raises(ValueError, match="derived"):
        save_sensitivity(with_last(variant_of="sector-rel-v1.1-L20-H5"), research)
    with pytest.raises(BiasedScopeViolation):
        save_sensitivity(with_last(d0=entries[-1].study.data_end), research)
    with pytest.raises(BiasedScopeViolation):
        save_study(dataclasses.replace(entries[0].study, regime="pit"), research)  # type: ignore[arg-type]
    assert _counts(store) == before


def test_small_refusals_of_the_variant_helpers(run: Run) -> None:
    with pytest.raises(InvalidVariant, match="whole number"):
        derive_variant(V1, MIN_CONSTITUENTS, 3.5, "minc35")
    with pytest.raises(KeyError):
        run.report.entry("research-sens-v1.0-l5-h5-nope")
    undated = _with_runs(run.panel, lambda runs: runs.assign(session_date=None))
    undated = MarketPanel(
        dataclasses.replace(
            undated.frames,
            bars=undated.frames.bars.iloc[0:0],
            listing=undated.frames.listing.iloc[0:0],
            classification=undated.frames.classification.iloc[0:0],
        )
    )
    with pytest.raises(BiasedScopeViolation, match="no dated rows"):
        study.admit_biased_panel(undated, run.no_d0)


def test_the_research_table_refuses_an_unnamespaced_variant_row(run: Run, tmp_path: Path) -> None:
    store = ResearchStore(tmp_path / "research.db")
    with closing(sqlite3.connect(store.db_path)) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO research_sensitivity_runs (sensitivity_id, method_version, variant_of, "
            "variant_diff, segment, regime, data_regime, bias_label, bias_directions, created_at, "
            "sample_count, beat_count_net, beat_count_gross, report_json) VALUES ('s', "
            "'sector-rel-v1.1-L20-H5', 'sector-rel-v1.0-L5-H5', '{}', 'full', 'hindsight', "
            f"'backfill_non_pit', '{BIAS_LABEL}', '{{}}', 'now', 0, 0, 0, '{{}}')"
        )


def _momentum(card: Any) -> bytes:
    with card_client(
        main_db=card.main_db,
        market_db=card.market_db,
        positions=card.positions,
        runtime=verified_runtime(),
        now=CARD_NOW,
    ) as client:
        response = client.get("/api/sectors/momentum")
    assert response.status_code == 200
    return bytes(response.content)


def test_api_response_ignores_the_sensitivity_rows(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-32 / T-10: with sensitivity rows in the research DB, the response is byte-identical."""
    card = live_card(tmp_path / "card", 8, now=CARD_NOW)
    monkeypatch.setenv(RESEARCH_DB_PATH_ENV_VAR, str(tmp_path / "absent" / "research.db"))
    without = _momentum(card)
    assert not (tmp_path / "absent").exists()
    before = run.research_db.read_bytes()
    monkeypatch.setenv(RESEARCH_DB_PATH_ENV_VAR, str(run.research_db))
    assert _momentum(card) == without
    assert run.research_db.read_bytes() == before


def test_a_frame_copy_keeps_its_columns(run: Run) -> None:
    """Guard for the helpers above: replacing runs keeps a valid ``PanelFrames``."""
    frames = _with_runs(run.panel, lambda runs: runs).frames
    assert isinstance(frames, PanelFrames)
    assert list(frames.runs.columns) == list(run.panel.frames.runs.columns)


def test_the_published_definition_stays_unloosened() -> None:
    """The looser values exist only in research types; the published type refuses them."""
    with pytest.raises(ValueError):
        UniverseRules(min_median_traded_value=5_000_000.0)
    with pytest.raises(ValueError):
        CoverageRules(min_constituents=3)
    assert isinstance(SENSITIVITY_BASE, SectorMomentumDefinition)
