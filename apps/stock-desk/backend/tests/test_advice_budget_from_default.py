"""E2 (CEO #72): while the risk budget is on its defaults, an ``add`` becomes ``hold``.

ADR-0032 Decision 5 / K-13 and 「風控 2026-10-29 N-156 字面定稿與表態」 第 3 項
(required gate rules), DL-4:

* ``add`` -> ``hold`` with the approved sentence in ``downgrade_notices``;
  ``blocked_action`` stays ``None``, ``blocked_notices`` stays empty, and
  ``quantity_range`` is ``None`` -- no buy range.
* reduce, stop-loss, take-profit, hold and insufficient_data are untouched.
* It acts only after the two existing gates: when the defensive downgrade or a
  violated cap already turned the ``add`` into ``hold``, the E2 sentence is not
  added and those gates' wording is unchanged.
* ``budget_from_default`` is keyword-only with no default.
* The advice endpoint takes it from the same ``load_with_status()`` as the
  budget; a ``net_worth`` fallback does not trigger it.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from app.advice import engine
from app.advice.engine import BUDGET_FROM_DEFAULT_NOTICE, build_advice
from app.advice.limits import PortfolioContext
from app.advice.loader import BANNED_PHRASES, load_rules
from app.api import advice as advice_router
from app.api.deps import get_settings_store
from app.main import app
from tests.advice_helpers import (
    make_signals,
    minimal_rule,
    minimal_ruleset,
    reported_net_worth,
    uptrend_signals,
    write_rule_file,
)
from tests.api_helpers import recent_bars
from tests.conftest import ApiHarness
from tests.import_graph import APP_ROOT
from tests.settings_fallback_helpers import SpySettingsStore, break_sections
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

#: Retyped from 第 3 項, never imported.
E2_SENTENCE = (
    "風險預算目前使用預設值（原本存的內容沒有通過驗證），加碼建議改為觀望，不提供買進股數；"
    "在設定頁確認覆寫風險預算後，恢復依規則判定。"
)

STOCK_DESK_ROOT = Path(__file__).resolve().parents[2]


def _portfolio(**overrides: Any) -> PortfolioContext:
    base: dict[str, Any] = {
        "symbol": "2330",
        "total_equity_twd": 1_000_000.0,
        "position_market_value_twd": 50_000.0,
        "position_cost_twd": 45_000.0,
        "gross_exposure_twd": 500_000.0,
        "net_worth": reported_net_worth(1_000_000.0),
        "book_fully_valued": True,
        "quantity": 500.0,
        "close": 110.0,
    }
    base.update(overrides)
    return PortfolioContext(**base)


def _card(
    signals: dict[str, Any], portfolio: PortfolioContext, *, from_default: bool, **kwargs: Any
) -> dict[str, Any]:
    return build_advice(
        symbol="2330",
        signals=signals,
        portfolio=portfolio,
        budget_from_default=from_default,
        **kwargs,
    )


# --- the sentence ------------------------------------------------------------------


def test_the_sentence_is_the_finalised_one() -> None:
    assert BUDGET_FROM_DEFAULT_NOTICE == E2_SENTENCE


def test_the_sentence_passes_the_forbidden_term_scans() -> None:
    shared = json.loads(
        (STOCK_DESK_ROOT / "shared" / "forbidden-terms.json").read_text(encoding="utf-8")
    )
    terms = (
        set(FRONTEND_FORBIDDEN_TERMS)
        | set(shared["guarantee"])
        | set(shared["price_target"])
        | set(BANNED_PHRASES)
    )
    assert [term for term in sorted(terms) if term in E2_SENTENCE] == []
    assert find_bare_realtime_claims(E2_SENTENCE) == []


# --- add -> hold, as a downgrade -----------------------------------------------------


def test_an_add_becomes_hold_with_the_sentence_and_no_buy_range() -> None:
    clean = _card(uptrend_signals(), _portfolio(), from_default=False)
    assert clean["action"] == "add"
    assert clean["quantity_range"] is not None  # not vacuous: a buy range existed

    card = _card(uptrend_signals(), _portfolio(), from_default=True)

    assert card["action"] == "hold"
    assert card["aggregated_action"] == "add"
    assert card["downgrade_notices"] == [E2_SENTENCE]
    assert card["blocked_action"] is None
    assert card["blocked_notices"] == []
    assert card["quantity_range"] is None
    # The rules and the caps themselves are what they were.
    assert card["matched_rules"] == clean["matched_rules"]
    assert card["limits_check"] == clean["limits_check"]
    assert card["action_weights"] == clean["action_weights"]


def test_the_default_gate_never_sets_blocked_action() -> None:
    """第 3 項: ``blocked_action == "add"`` would read as「被風險上限擋下」-- false here."""
    card = _card(uptrend_signals(), _portfolio(), from_default=True)
    assert "擋下" not in json.dumps(card, ensure_ascii=False)


def _single_rule_card(
    tmp_path: Path, action: str, *, from_default: bool, **portfolio: Any
) -> dict[str, Any]:
    payload = minimal_ruleset(
        minimal_rule(
            id=f"only_{action}",
            action=action,
            weight=0.5,
            condition={"field": "rsi14.last", "op": "lt", "value": 90},
        )
    )
    ruleset = load_rules(write_rule_file(tmp_path, payload))
    return _card(
        uptrend_signals(), _portfolio(**portfolio), from_default=from_default, ruleset=ruleset
    )


@pytest.mark.parametrize("action", ["hold", "reduce", "stop_loss", "take_profit"])
@pytest.mark.parametrize(
    "portfolio",
    [{}, {"position_market_value_twd": 200_000.0, "quantity": 1_818.0}],
    ids=["inside-caps", "over-cap-1"],
)
def test_every_non_add_action_is_left_exactly_as_it_was(
    tmp_path: Path, action: str, portfolio: dict[str, Any]
) -> None:
    """CEO #72: reduce and stop-loss as usual -- the whole card is identical."""
    clean = _single_rule_card(tmp_path, action, from_default=False, **portfolio)
    default = _single_rule_card(tmp_path, action, from_default=True, **portfolio)
    assert clean["action"] == action
    assert default == clean


def test_a_reduce_range_is_still_offered() -> None:
    """The defensive side keeps its share range (CEO #72: 減碼與停損照常)."""
    signals = uptrend_signals(max_drawdown=-0.35, current_drawdown=-0.35)
    over = {"position_market_value_twd": 200_000.0, "quantity": 1_818.0, "close": 90.0}
    clean = _card(signals, _portfolio(**over), from_default=False)
    default = _card(signals, _portfolio(**over), from_default=True)
    assert clean["action"] in {"reduce", "stop_loss"}
    assert default == clean
    assert default["quantity_range"] is not None


def test_insufficient_data_is_left_alone() -> None:
    clean = _card(make_signals(), PortfolioContext(symbol="2330"), from_default=False)
    default = _card(make_signals(), PortfolioContext(symbol="2330"), from_default=True)
    assert clean["action"] == "insufficient_data"
    assert default == clean


# --- after the two existing gates ------------------------------------------------------


def test_the_defensive_downgrade_comes_first_and_alone() -> None:
    signals = uptrend_signals(
        rsi=78.0,
        bollinger={
            "middle": 105.0,
            "upper": 115.0,
            "lower": 95.0,
            "bandwidth": 0.19,
            "percent_b": 1.2,
        },
    )
    clean = _card(signals, _portfolio(), from_default=False)
    default = _card(signals, _portfolio(), from_default=True)
    assert clean["action"] == "hold" and len(clean["downgrade_notices"]) == 1
    assert default == clean
    assert E2_SENTENCE not in default["downgrade_notices"]


def test_a_violated_cap_comes_first_and_keeps_its_wording() -> None:
    over = {"position_market_value_twd": 150_000.0, "quantity": 1_363.0}
    clean = _card(uptrend_signals(), _portfolio(**over), from_default=False)
    default = _card(uptrend_signals(), _portfolio(**over), from_default=True)
    assert clean["blocked_action"] == "add"
    assert clean["blocked_notices"] == ["加碼建議被第 1 條上限（單一標的佔比上限）擋下。"]
    assert default == clean
    assert E2_SENTENCE not in default["downgrade_notices"]


def test_the_gate_sits_after_both_existing_gates_in_the_source() -> None:
    source = inspect.getsource(build_advice)
    defensive = source.index("防禦型規則同時命中")
    blocked = source.index("擋下")
    e2 = source.index("BUDGET_FROM_DEFAULT_NOTICE")
    sizing = source.index("suggest_quantity_range(")
    assert defensive < blocked < e2 < sizing


# --- the parameter ---------------------------------------------------------------------


def test_budget_from_default_is_keyword_only_with_no_default() -> None:
    parameter = inspect.signature(build_advice).parameters["budget_from_default"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
    assert parameter.annotation in (bool, "bool")
    with pytest.raises(TypeError):
        build_advice(symbol="2330", signals=uptrend_signals(), portfolio=_portfolio())  # type: ignore[call-arg]


def test_every_production_caller_passes_a_computed_value() -> None:
    """Never a hard-coded ``False`` (第 3 項 觸發條件): every call site in ``app``."""
    calls = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "build_advice"
            ):
                keyword = next(k for k in node.keywords if k.arg == "budget_from_default")
                calls.append((path.relative_to(APP_ROOT).as_posix(), keyword.value))
    assert [where for where, _ in calls] == ["api/advice.py"]
    for _, value in calls:
        assert not isinstance(value, ast.Constant)
        assert "fallback_sections" in ast.unparse(value)
        assert "risk_budget" in ast.unparse(value)


def test_the_only_constant_callers_are_the_offline_replay_scripts() -> None:
    """``scripts/`` reads no stored settings, so ``False`` is the truth there -- and only there."""
    scripts = APP_ROOT.parent / "scripts"
    callers = set()
    for path in sorted(scripts.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "build_advice"
            ):
                keyword = next(k for k in node.keywords if k.arg == "budget_from_default")
                assert isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                callers.add(path.name)
                assert "app.settings" not in path.read_text(encoding="utf-8")
    assert callers == {"drawdown_rule_diff.py"}


def test_the_engine_does_not_read_the_settings() -> None:
    """The flag arrives as an argument; the engine never judges a fallback itself."""
    source = Path(engine.__file__).read_text(encoding="utf-8")
    assert "app.settings" not in source
    assert "load_with_status" not in source


# --- through the advice endpoint ---------------------------------------------------------


@pytest.fixture
def add_signals(monkeypatch: pytest.MonkeyPatch, api_harness: ApiHarness) -> None:
    """A candidate whose rules say ``add``: a flat close with up-trend indicators."""
    api_harness.price_service.seed("2330", recent_bars([110.0] * 120, symbol="2330"))
    monkeypatch.setattr(
        advice_router, "compute_signals", lambda symbol, bars, **_: uptrend_signals()
    )


@pytest.mark.parametrize(
    ("broken", "downgraded"),
    [
        ((), False),
        (("risk_budget",), True),
        (("net_worth",), False),
        (("cost_model", "alerts"), False),
        (("risk_budget", "net_worth"), True),
    ],
    ids=["none", "risk_budget", "net_worth", "cost_model+alerts", "risk_budget+net_worth"],
)
def test_the_endpoint_downgrades_only_for_a_risk_budget_fallback(
    api_harness: ApiHarness, add_signals: None, broken: tuple[str, ...], downgraded: bool
) -> None:
    break_sections(api_harness.settings, broken)

    card = api_harness.client.get("/api/advice/2330").json()["advice"]

    assert card["aggregated_action"] == "add"
    if downgraded:
        assert card["action"] == "hold"
        assert card["downgrade_notices"] == [E2_SENTENCE]
        assert card["blocked_action"] is None
        assert card["quantity_range"] is None
    else:
        assert card["action"] == "add"
        assert E2_SENTENCE not in card["downgrade_notices"]


def test_the_endpoint_takes_the_flag_from_its_one_read(
    api_harness: ApiHarness, add_signals: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K-5: one ``load_with_status()``, and the flag is that read's ``risk_budget`` state."""
    store = SpySettingsStore(tmp_path / "spy.db")
    break_sections(store, ("risk_budget",))
    app.dependency_overrides[get_settings_store] = lambda: store
    seen: list[bool] = []
    real = build_advice

    def spy(**kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs["budget_from_default"])
        return real(**kwargs)

    monkeypatch.setattr(advice_router, "build_advice", spy)

    body = api_harness.client.get("/api/advice/2330").json()

    assert store.reads == ["load_with_status"]
    assert seen == [True]
    assert body["settings_fallback_notice"] is not None
