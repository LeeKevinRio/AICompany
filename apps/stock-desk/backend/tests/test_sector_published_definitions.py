"""Definition type layers and the published-object gate (ADR-0012 D-15; C-16, C-46, C-47).

* **T-29** -- mypy (strict, ``mypy app tests`` in CI) accepts a research
  variant as a ``SectorEvalDefinition`` (the module-level assignment below);
  the four protocols are defined in ``app/sectors/definition.py`` only, their
  members are read-only properties and mirror the concrete rules; every
  function D-15 lists carries the protocol it names, and ``gate.py``,
  ``store.py`` and ``published_thresholds`` keep ``SectorMomentumDefinition``;
* **T-30** -- table-driven over every C-47 entry: a research variant, an equal
  ``dataclasses.replace`` copy, a subclass instance and a tightened copy that
  reuses the v1 string are all refused, ``SECTOR_MOMENTUM_V1`` itself passes;
  the statistics repository (save and load), the registry and the approval
  CLI refuse unknown strings; teeth: each entry's body calls
  ``require_published``, and removing that call from a copy fails the check;
* quant residual risk 1 -- every published definition keeps ``alpha == 0.05``.
"""

from __future__ import annotations

import ast
import dataclasses
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.api import sectors as api
from app.backtest import sector_eval
from app.backtest.costs import CostModel
from app.data.calendar import TradingCalendar
from app.data.market_panel import MarketPanelStore
from app.research.sector_biased.sensitivity import SENSITIVITY_VARIANTS, ResearchVariant
from app.sectors import coverage
from app.sectors import definition as definition_module
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.definition import (
    CoverageRules,
    CoverageRulesView,
    GateRules,
    SectorEvalDefinition,
    SectorMomentumDefinition,
    UniverseRules,
    UniverseRulesView,
    UnpublishedDefinition,
    is_method_version,
    published_versions,
    require_published,
)
from app.sectors.gate import EvaluationWindow, GateInputs, PitStatus
from app.sectors.store import (
    BiasedDataRejected,
    SectorBoardStore,
    SectorMethodRegistry,
    SectorStatsRepository,
)
from app.services import sector_board
from app.services.sector_board import SectorBoardService, approve, published_definition
from tests.import_graph import APP_ROOT
from tests.published_helpers import published
from tests.sector_board_helpers import stats_record
from tests.source_helpers import FakeSources

# T-29: CI's ``mypy app tests`` (strict) proves a research variant satisfies the
# evaluator's structural definition. If ResearchVariant lost or loosened a
# member (``gate`` no longer ``GateRules``, say), this line stops type-checking.
_VARIANT_AS_EVAL_DEFINITION: SectorEvalDefinition = SENSITIVITY_VARIANTS[0]
_PUBLISHED_AS_EVAL_DEFINITION: SectorEvalDefinition = V1

DEFINITION_FILE = APP_ROOT / "sectors" / "definition.py"
PROTOCOLS = (
    "UniverseRulesView",
    "CoverageRulesView",
    "SectorCoreDefinition",
    "SectorEvalDefinition",
)


# ---------------------------------------------------------------------------
# The published registry itself
# ---------------------------------------------------------------------------


def test_v1_is_the_only_published_definition() -> None:
    assert definition_module.PUBLISHED_DEFINITIONS == (V1,)
    assert definition_module.PUBLISHED_DEFINITIONS[0] is V1
    assert published_versions() == frozenset({V1.method_version})
    assert require_published(V1) is V1


def test_is_method_version_is_the_version_pattern() -> None:
    assert is_method_version("sector-rel-v1.0-L5-H5")
    assert is_method_version("sector-rel-v2.3-L20-H10")
    assert not is_method_version("research-sens-v1.0-l5-h5-liq5m")
    assert not is_method_version("sector-rel-v1.0-L5-H5-liq5m")
    assert not is_method_version("")


def test_require_published_reads_the_module_attribute_at_call_time() -> None:
    fast = SectorMomentumDefinition(
        method_version=V1.method_version,
        lookback_days=5,
        holding_days=5,
        gate=GateRules(lookahead_sample_dates=4),
    )
    with pytest.raises(UnpublishedDefinition):
        require_published(fast)
    with published(fast):
        assert require_published(fast) is fast
        assert require_published(V1) is V1
    with pytest.raises(UnpublishedDefinition):
        require_published(fast)
    assert definition_module.PUBLISHED_DEFINITIONS == (V1,)


# ---------------------------------------------------------------------------
# quant residual risk 1: the card's {level} assumes alpha = 0.05
# ---------------------------------------------------------------------------


def test_every_published_definition_keeps_alpha_at_five_percent() -> None:
    for definition in definition_module.PUBLISHED_DEFINITIONS:
        assert definition.gate.alpha == 0.05, (
            f"{definition.method_version}: gate.alpha is {definition.gate.alpha}. The card "
            "renders the interval level {level} as 1 - 0.05/m (dispatch sheet §14.2). "
            "Tightening alpha first needs the API to expose the interval level and the "
            "front end to render that field instead."
        )


# ---------------------------------------------------------------------------
# T-29: the protocols and the parameter annotations
# ---------------------------------------------------------------------------


def _class_defs(path: Path) -> dict[str, ast.ClassDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def test_the_four_protocols_are_defined_in_definition_py_only() -> None:
    owners: dict[str, list[str]] = {name: [] for name in PROTOCOLS}
    for path in sorted(APP_ROOT.rglob("*.py")):
        for name in _class_defs(path):
            if name in owners:
                owners[name].append(path.relative_to(APP_ROOT).as_posix())
    assert owners == {name: ["sectors/definition.py"] for name in PROTOCOLS}


def _members(node: ast.ClassDef) -> dict[str, str]:
    """Protocol member -> return annotation; fails on anything but a read-only property."""
    members: dict[str, str] = {}
    for item in node.body:
        if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant):
            continue  # docstring
        assert isinstance(item, ast.FunctionDef), f"{node.name}: {ast.dump(item)}"
        decorators = [ast.unparse(d) for d in item.decorator_list]
        assert decorators == ["property"], f"{node.name}.{item.name}: {decorators}"
        assert item.returns is not None
        members[item.name] = ast.unparse(item.returns)
    return members


def test_protocol_members_are_read_only_properties_mirroring_the_rules() -> None:
    classes = _class_defs(DEFINITION_FILE)
    universe = _members(classes["UniverseRulesView"])
    assert set(universe) == {field.name for field in dataclasses.fields(UniverseRules)}
    cover = _members(classes["CoverageRulesView"])
    assert set(cover) == {field.name for field in dataclasses.fields(CoverageRules)}
    core = _members(classes["SectorCoreDefinition"])
    assert core == {
        "method_version": "str",
        "lookback_days": "int",
        "universe": "UniverseRulesView",
        "coverage": "CoverageRulesView",
        "single_stock_dominance_share": "float",
    }
    evaluation = _members(classes["SectorEvalDefinition"])
    assert evaluation == {
        "holding_days": "int",
        "open_limit_up_factor": "float",
        "gate": "GateRules",
    }
    bases = [ast.unparse(base) for base in classes["SectorEvalDefinition"].bases]
    assert bases == ["SectorCoreDefinition", "Protocol"]
    for name in PROTOCOLS[:3]:
        assert [ast.unparse(base) for base in classes[name].bases] == ["Protocol"]


def test_the_protocol_views_accept_the_concrete_rules() -> None:
    # Run-time face of the structural typing: the concrete rules have every member.
    views: tuple[tuple[type[Any], object], ...] = (
        (UniverseRulesView, V1.universe),
        (CoverageRulesView, V1.coverage),
    )
    classes = _class_defs(DEFINITION_FILE)
    for view, rules in views:
        for member in _members(classes[view.__name__]):
            assert hasattr(rules, member), (view.__name__, member)


#: (file under app/, function, parameter) -> the annotation D-15 prescribes.
ANNOTATIONS: dict[tuple[str, str, str], str] = {
    ("sectors/universe.py", "eligible", "definition"): "SectorCoreDefinition",
    ("sectors/universe.py", "calculation_set", "definition"): "SectorCoreDefinition",
    ("sectors/ranking.py", "rank_sectors", "definition"): "SectorCoreDefinition",
    ("sectors/coverage.py", "assess", "definition"): "SectorCoreDefinition",
    ("sectors/coverage.py", "ex_dividend_feed_covered", "definition"): "SectorCoreDefinition",
    ("sectors/coverage.py", "attribute", "rules"): "CoverageRulesView",
    ("sectors/coverage.py", "assess_card", "rules"): "CoverageRulesView",
    ("sectors/coverage.py", "card_from_counts", "rules"): "CoverageRulesView",
    ("sectors/coverage.py", "published_thresholds", "definition"): "SectorMomentumDefinition",
    **{
        ("backtest/sector_eval.py", name, "definition"): "SectorEvalDefinition"
        for name in (
            "evaluate_views",
            "decide",
            "build_week",
            "build_decisions_and_weeks",
            "summarise",
            "compute_statistics",
            "candidate_gates",
            "future_perturbation_check",
            "leak_control_status",
            "time_shift_status",
            "selfchecks_passed",
            "rank_1_strategy",
            "benchmark_strategy",
            "_invalid_reason",
        )
    },
    ("backtest/sector_eval.py", "evaluate", "definition"): "SectorMomentumDefinition",
    ("backtest/sector_eval.py", "to_stats_record", "definition"): "SectorMomentumDefinition",
    ("sectors/store.py", "save_board", "definition"): "SectorMomentumDefinition",
    ("sectors/store.py", "register", "definition"): "SectorMomentumDefinition",
}


def _functions(path: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def _annotation(path: Path, function: str, parameter: str) -> str | None:
    node = _functions(path).get(function)
    if node is None:
        return None
    arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    for argument in arguments:
        if argument.arg == parameter and argument.annotation is not None:
            return ast.unparse(argument.annotation)
    return None


@pytest.mark.parametrize(("where", "expected"), sorted(ANNOTATIONS.items()))
def test_d15_parameter_annotations(where: tuple[str, str, str], expected: str) -> None:
    relative, function, parameter = where
    assert _annotation(APP_ROOT / relative, function, parameter) == expected


def _names_in_annotations(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        annotations: list[ast.expr | None] = []
        if isinstance(node, ast.arg):
            annotations.append(node.annotation)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        elif isinstance(node, ast.FunctionDef):
            annotations.append(node.returns)
        for annotation in annotations:
            if annotation is not None:
                names |= {n.id for n in ast.walk(annotation) if isinstance(n, ast.Name)}
    return names


@pytest.mark.parametrize("relative", ["sectors/gate.py", "sectors/store.py"])
def test_gate_and_store_keep_the_nominal_definition(relative: str) -> None:
    names = _names_in_annotations(APP_ROOT / relative)
    assert "SectorMomentumDefinition" in names
    assert not names & set(PROTOCOLS), relative


@pytest.mark.parametrize("relative", ["sectors/index.py", "sectors/constituents.py"])
def test_index_and_constituents_take_no_definition(relative: str) -> None:
    names = _names_in_annotations(APP_ROOT / relative)
    assert not names & {"SectorMomentumDefinition", *PROTOCOLS}


def test_annotation_check_has_teeth(tmp_path: Path) -> None:
    source = (APP_ROOT / "sectors" / "ranking.py").read_text(encoding="utf-8")
    leaked = tmp_path / "ranking.py"
    leaked.write_text(
        source.replace(
            "definition: SectorCoreDefinition) -> SectorRanking",
            "definition: SectorMomentumDefinition) -> SectorRanking",
        ),
        encoding="utf-8",
    )
    assert _annotation(leaked, "rank_sectors", "definition") == "SectorMomentumDefinition"


# ---------------------------------------------------------------------------
# T-30: every C-47 entry refuses anything but the published object
# ---------------------------------------------------------------------------


class _SubclassedV1(SectorMomentumDefinition):
    """A subclass instance: ``isinstance`` would let it through; identity does not."""


def _unpublished() -> dict[str, object]:
    return {
        "research_variant": SENSITIVITY_VARIANTS[0],
        "equal_copy": dataclasses.replace(V1),
        "subclass_instance": _SubclassedV1(
            method_version=V1.method_version, lookback_days=5, holding_days=5
        ),
        "tightened_copy_with_v1_string": SectorMomentumDefinition(
            method_version=V1.method_version,
            lookback_days=5,
            holding_days=5,
            coverage=CoverageRules(min_constituents=8),
        ),
    }


def test_the_unpublished_candidates_really_are_the_hard_cases() -> None:
    candidates = _unpublished()
    assert candidates["equal_copy"] == V1 and candidates["equal_copy"] is not V1
    assert isinstance(candidates["subclass_instance"], SectorMomentumDefinition)
    tightened = cast(SectorMomentumDefinition, candidates["tightened_copy_with_v1_string"])
    assert tightened.method_version == V1.method_version and tightened != V1
    assert isinstance(candidates["research_variant"], ResearchVariant)


DAY = date(2027, 3, 1)


def _gate_inputs(definition: Any) -> GateInputs:
    return GateInputs(
        definition=definition,
        data_source="twse_snapshot",
        board_method_version=None,
        board_invariant_violated=False,
        as_of_session=None,
        calendar=TradingCalendar([DAY]),
        fee_verified_on=None,
        de5_verified_on=None,
        ci_passed_commit=None,
        pit_status=PitStatus(accumulation_start=None, ok_sessions={}),
        window=EvaluationWindow(decision_dates=(), trading_days=()),
        stats_history=(),
        approvals=(),
    )


def _evaluate(definition: Any, tmp_path: Path) -> object:
    return sector_eval.evaluate(
        cast(Any, None),  # never reached for an unpublished definition
        definition,
        cost_model=CostModel(),
        start=DAY,
        m=1,
        seed=1,
        pit_status=PitStatus(accumulation_start=None, ok_sessions={}),
        de5_verified_on=None,
    )


def _to_stats_record(definition: Any, tmp_path: Path) -> object:
    evaluation = SimpleNamespace(regime="hindsight", data_regime="backfill_non_pit")
    return sector_eval.to_stats_record(
        cast(Any, evaluation),
        definition,
        run_id="r",
        computed_at=datetime(2027, 3, 1, tzinfo=UTC),
        recompute_session=DAY,
        running_commit="c",
        ci_attestation_ok=True,
    )


def _save_board(definition: Any, tmp_path: Path) -> object:
    parts = cast(Any, SimpleNamespace(method_version="not-this-one"))
    SectorBoardStore(tmp_path / "main.db").save_board(
        definition=definition,
        calc=parts,
        ranking=parts,
        provenance=cast(Any, None),
        turnover={},
        names={},
    )
    return None


def _register(definition: Any, tmp_path: Path) -> object:
    SectorMethodRegistry(tmp_path / "main.db").register(
        definition, frozen_commit="c0ffee", registered_at=datetime(2027, 3, 1, tzinfo=UTC)
    )
    return None


def _service(definition: Any, tmp_path: Path) -> object:
    return SectorBoardService(
        market_store=MarketPanelStore(tmp_path / "market.db"),
        main_db=tmp_path / "main.db",
        definition=definition,
    )


def _build_card(definition: Any, tmp_path: Path) -> object:
    return api.build_sector_momentum(
        market="TW",
        read=cast(Any, None),  # never reached for an unpublished definition
        ok_sessions={},
        runtime=cast(Any, None),
        held=None,
        now=datetime(2027, 3, 1, tzinfo=UTC),
        definition=definition,
    )


#: Every C-47 entry, as ``(definition, tmp_path) -> result``.
ENTRIES: dict[str, Callable[[Any, Path], object]] = {
    "sector_eval.evaluate": _evaluate,
    "sector_eval.to_stats_record": _to_stats_record,
    "gate.GateInputs": lambda d, _: _gate_inputs(d),
    "coverage.published_thresholds": lambda d, _: coverage.published_thresholds(d),
    "SectorBoardStore.save_board": _save_board,
    "SectorMethodRegistry.register": _register,
    "services.sector_board.published_definition": lambda d, _: published_definition(d),
    "services.SectorBoardService": _service,
    "api.sectors.served_definition": lambda d, _: api.served_definition(d),
    "api.sectors.build_sector_momentum": _build_card,
}


@pytest.mark.parametrize("candidate", sorted(_unpublished()))
@pytest.mark.parametrize("entry", sorted(ENTRIES))
def test_every_entry_refuses_unpublished_definitions(
    entry: str, candidate: str, tmp_path: Path
) -> None:
    definition = _unpublished()[candidate]
    with pytest.raises(UnpublishedDefinition):
        ENTRIES[entry](definition, tmp_path)
    main_db = tmp_path / "main.db"
    if main_db.exists():
        with closing(sqlite3.connect(main_db)) as conn:
            for table in ("sector_board", "sector_method_registry"):
                assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("entry", sorted(ENTRIES))
def test_every_entry_accepts_the_published_object(entry: str, tmp_path: Path) -> None:
    """V1 itself passes the gate; whatever the dummy arguments do next is not a refusal."""
    try:
        ENTRIES[entry](V1, tmp_path)
    except UnpublishedDefinition:  # pragma: no cover - the failure being tested for
        pytest.fail(f"{entry} refused SECTOR_MOMENTUM_V1")
    except (AttributeError, TypeError, ValueError):
        pass  # the gate let V1 through; the dummy arguments then ran out


def test_the_published_object_is_really_accepted_where_it_is_cheap(tmp_path: Path) -> None:
    assert coverage.published_thresholds(V1)["min_constituents"] == V1.coverage.min_constituents
    assert _gate_inputs(V1).definition is V1
    assert published_definition(V1) is V1 and published_definition(V1.method_version) is V1
    assert api.served_definition() is V1
    _register(V1, tmp_path)
    assert SectorMethodRegistry(tmp_path / "main.db").get(V1.method_version) is not None


def test_services_resolve_version_strings_to_published_objects_only() -> None:
    with pytest.raises(UnpublishedDefinition):
        published_definition("sector-rel-v1.1-L20-H5")
    with pytest.raises(UnpublishedDefinition):
        published_definition(SENSITIVITY_VARIANTS[0].method_version)


# -- the string-keyed layers ---------------------------------------------------

UNKNOWN_VERSIONS = ("sector-rel-v1.1-L20-H5", SENSITIVITY_VARIANTS[0].method_version)


@pytest.mark.parametrize("version", UNKNOWN_VERSIONS)
def test_the_repository_refuses_unpublished_versions_on_save(version: str, tmp_path: Path) -> None:
    repo = SectorStatsRepository(FakeSources(), tmp_path / "main.db")
    with pytest.raises(BiasedDataRejected, match="not a published"):
        repo.save(stats_record("r1", method_version=version))
    with closing(sqlite3.connect(tmp_path / "main.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sector_rank_stats").fetchone()[0] == 0
    repo.save(stats_record("r2"))  # the published version is accepted


@pytest.mark.parametrize("version", UNKNOWN_VERSIONS)
def test_the_repository_refuses_unpublished_versions_on_read(version: str, tmp_path: Path) -> None:
    main_db = tmp_path / "main.db"
    repo = SectorStatsRepository(FakeSources(), main_db)
    repo.save(stats_record("r1"))
    with closing(sqlite3.connect(main_db)) as conn, conn:
        # A row that never went through save(): r1 copied as r9 with only the version changed.
        columns = [row[1] for row in conn.execute("PRAGMA table_info(sector_rank_stats)")]
        picked = {"run_id": "'r9'", "method_version": "?"}
        values = ", ".join(picked.get(column, column) for column in columns)
        conn.execute(
            f"INSERT INTO sector_rank_stats ({', '.join(columns)}) "
            f"SELECT {values} FROM sector_rank_stats WHERE run_id = 'r1'",
            (version,),
        )
    with pytest.raises(BiasedDataRejected, match="not a published"):
        repo.load(version)
    with pytest.raises(BiasedDataRejected, match="not a published"):
        repo.find("r9")
    assert [record.run_id for record in repo.load(V1.method_version)] == ["r1"]


@pytest.mark.parametrize("version", UNKNOWN_VERSIONS)
def test_the_registry_refuses_unpublished_version_strings(version: str, tmp_path: Path) -> None:
    registry = SectorMethodRegistry(tmp_path / "main.db")
    with pytest.raises(UnpublishedDefinition):
        registry.record_accumulation_start(version, DAY)
    with pytest.raises(UnpublishedDefinition):
        registry.record_first_forward_eval(version, datetime(2027, 3, 1, tzinfo=UTC))


class _StatsWithForeignRow:
    """Stands in for a repository that let an unpublished row through (defence in depth)."""

    def find(self, run_id: str) -> object:
        return stats_record(run_id, method_version=UNKNOWN_VERSIONS[1])


def test_the_approval_cli_refuses_unpublished_versions(tmp_path: Path) -> None:
    doc = tmp_path / "review.md"
    doc.write_text(f"run-1 {UNKNOWN_VERSIONS[1]}\n", encoding="utf-8")
    with pytest.raises(BiasedDataRejected, match="not a published"):
        approve(
            kind="first_transition_risk",
            run_id="run-1",
            operator="ceo",
            reviewer="risk-compliance-officer",
            review_doc=doc,
            stats=cast(Any, _StatsWithForeignRow()),
            approvals=cast(Any, None),  # never reached
            repo_root=tmp_path,
        )


# -- teeth: every entry's body calls require_published -------------------------

#: (file under app/, class or None, function) of each C-47 entry.
GATED_BODIES: tuple[tuple[str, str | None, str], ...] = (
    ("backtest/sector_eval.py", None, "evaluate"),
    ("backtest/sector_eval.py", None, "to_stats_record"),
    ("sectors/gate.py", "GateInputs", "__post_init__"),
    ("sectors/coverage.py", None, "published_thresholds"),
    ("sectors/store.py", "SectorBoardStore", "save_board"),
    ("sectors/store.py", "SectorMethodRegistry", "register"),
    ("services/sector_board.py", None, "published_definition"),
    ("api/sectors.py", None, "served_definition"),
)


def _function(tree: ast.Module, owner: str | None, name: str) -> ast.FunctionDef | None:
    scope: list[ast.stmt] = tree.body
    if owner is not None:
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner]
        if not classes:
            return None
        scope = classes[0].body
    for node in scope:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _calls(node: ast.AST, callee: str) -> bool:
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            func = call.func
            if (isinstance(func, ast.Name) and func.id == callee) or (
                isinstance(func, ast.Attribute) and func.attr == callee
            ):
                return True
    return False


def _gated(path: Path, owner: str | None, name: str) -> bool:
    function = _function(ast.parse(path.read_text(encoding="utf-8")), owner, name)
    return function is not None and _calls(function, "require_published")


@pytest.mark.parametrize(("relative", "owner", "name"), GATED_BODIES)
def test_every_entry_body_calls_require_published(
    relative: str, owner: str | None, name: str
) -> None:
    assert _gated(APP_ROOT / relative, owner, name)


class _DropRequirePublished(ast.NodeTransformer):
    """``require_published(x)`` -> ``x``: the entry still runs, ungated."""

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func = node.func
        if isinstance(func, ast.Name) and func.id == "require_published" and node.args:
            return node.args[0]
        return node


@pytest.mark.parametrize(("relative", "owner", "name"), GATED_BODIES)
def test_body_check_has_teeth(relative: str, owner: str | None, name: str, tmp_path: Path) -> None:
    tree = ast.parse((APP_ROOT / relative).read_text(encoding="utf-8"))
    ungated = tmp_path / Path(relative).name
    ungated.write_text(ast.unparse(_DropRequirePublished().visit(tree)), encoding="utf-8")
    assert not _gated(ungated, owner, name)


def test_the_card_and_the_service_take_the_definition_through_their_gate() -> None:
    """``build_sector_momentum`` and the router read the definition via ``served_definition``;
    the service reads ``self.definition`` only as the argument of ``published_definition``."""
    api_tree = ast.parse((APP_ROOT / "api" / "sectors.py").read_text(encoding="utf-8"))
    build = _function(api_tree, None, "build_sector_momentum")
    route = _function(api_tree, None, "read_sector_momentum")
    assert build is not None and _calls(build.body[1], "served_definition")
    assert route is not None and _calls(route, "served_definition")
    assert _service_reads_outside_the_gate(APP_ROOT / "services" / "sector_board.py") == []


def _service_reads_outside_the_gate(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _calls(node, "published_definition") and node.args:
            allowed.add(id(node.args[0]))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "definition"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and id(node) not in allowed
    ]


def test_service_read_check_has_teeth(tmp_path: Path) -> None:
    source = (APP_ROOT / "services" / "sector_board.py").read_text(encoding="utf-8")
    leaked = tmp_path / "sector_board.py"
    leaked.write_text(
        source.replace(
            "judged_window(days, d0, definition.holding_days)",
            "judged_window(days, d0, self.definition.holding_days)",
        ),
        encoding="utf-8",
    )
    assert _service_reads_outside_the_gate(leaked) != []


@pytest.mark.parametrize("version", UNKNOWN_VERSIONS)
def test_the_register_cli_offers_published_versions_only(version: str) -> None:
    base = ["register-version", "--operator", "ceo", "--review-doc", "doc.md"]
    parsed = sector_board._parser().parse_args(base)
    assert parsed.method_version == V1.method_version
    with pytest.raises(SystemExit):
        sector_board._parser().parse_args([*base, "--method-version", version])
