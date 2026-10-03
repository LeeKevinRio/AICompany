"""Tests for per-rule invalidation text and the option-C rule selection.

Covers the backend half of the 2026-10-03 risk-compliance review (BLOCKING 1):
every ``matched_rules`` entry carries its own rule's invalidation text, and
:func:`pick_rule_for_action` picks the rule that argues *for* the card's action
rather than the heaviest rule overall.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.advice.engine import MatchedRule, build_advice
from app.advice.limits import PortfolioContext
from app.advice.loader import load_default_rules, load_rules
from app.advice.selection import pick_rule_for_action
from tests.advice_helpers import (
    minimal_rule,
    minimal_ruleset,
    reported_net_worth,
    uptrend_signals,
    write_rule_file,
)


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


def _entry(rule_id: str, action: str, weight: float) -> MatchedRule:
    return {
        "id": rule_id,
        "name": rule_id,
        "action": action,
        "weight": weight,
        "weight_meaning": "",
        "explanation": "",
        "invalidation": f"{rule_id} 的失效條件。",
    }


def _overbought_uptrend_signals() -> dict[str, Any]:
    """MA stack bullish, RSI overbought, KD rolling over at a high level.

    The review's counter-example: ``uptrend_ma_stack`` (add 0.5),
    ``rsi_overbought`` (reduce 0.4) and ``kd_high_level_weakening``
    (reduce 0.35) match together, and nothing else does.
    """
    return uptrend_signals(
        rsi=75.0,
        kd={"k": 85.0, "d": 88.0, "rsv": 80.0},
        macd={"macd": 0.8, "signal": 1.0, "histogram": -0.2},
    )


# --- matched_rules[].invalidation --------------------------------------------


def test_every_matched_rule_carries_its_own_invalidation_text() -> None:
    texts = {rule.id: rule.invalidation for rule in load_default_rules().rules}
    card = build_advice(
        symbol="2330", signals=_overbought_uptrend_signals(), portfolio=_portfolio()
    )
    assert card["matched_rules"]
    for rule in card["matched_rules"]:
        assert rule["invalidation"] == texts[rule["id"]]


def test_per_rule_invalidation_survives_the_card_level_de_duplication(tmp_path: Path) -> None:
    # Two rules sharing one invalidation text: the card-level list collapses
    # them into one entry, so pairing it with matched_rules by index would
    # attach the wrong text (or none) to the second and third rule.
    shared = "共用的失效條件。"
    payload = minimal_ruleset(
        minimal_rule(id="first", action="reduce", weight=0.3, invalidation=shared),
        minimal_rule(id="second", action="reduce", weight=0.5, invalidation=shared),
        minimal_rule(id="third", action="reduce", weight=0.2, invalidation="第三條的失效條件。"),
    )
    ruleset = load_rules(write_rule_file(tmp_path, payload))
    card = build_advice(
        symbol="2330",
        signals=uptrend_signals(rsi=75.0),
        portfolio=_portfolio(),
        ruleset=ruleset,
    )
    assert card["invalidation_conditions"] == [shared, "第三條的失效條件。"]
    assert [rule["invalidation"] for rule in card["matched_rules"]] == [
        shared,
        shared,
        "第三條的失效條件。",
    ]
    picked = pick_rule_for_action(card["matched_rules"], card["action"])
    assert picked is not None
    assert picked["id"] == "second"


# --- pick_rule_for_action: the review's counter-example -----------------------


def test_review_counter_example_picks_the_heaviest_rule_of_the_aggregated_action() -> None:
    card = build_advice(
        symbol="2330", signals=_overbought_uptrend_signals(), portfolio=_portfolio()
    )
    assert [rule["id"] for rule in card["matched_rules"]] == [
        "uptrend_ma_stack",
        "rsi_overbought",
        "kd_high_level_weakening",
    ]
    assert card["aggregated_action"] == "reduce"
    assert card["action"] == card["aggregated_action"]
    # The heaviest rule overall is the constructive one -- the trap option B
    # fell into.
    heaviest = max(card["matched_rules"], key=lambda rule: rule["weight"])
    assert heaviest["id"] == "uptrend_ma_stack"

    picked = pick_rule_for_action(card["matched_rules"], card["action"])
    assert picked is not None
    assert picked["id"] == "rsi_overbought"
    assert picked["action"] == "reduce"
    assert picked["invalidation"] == "RSI 回落至 50 與 70 之間，且收盤價維持在 20 日均線之上。"


def test_review_counter_example_on_hand_built_entries() -> None:
    rules = [
        _entry("uptrend_ma_stack", "add", 0.5),
        _entry("rsi_overbought", "reduce", 0.4),
        _entry("kd_high_level_weakening", "reduce", 0.35),
    ]
    picked = pick_rule_for_action(rules, "reduce")
    assert picked is rules[1]


# --- pick_rule_for_action: the selection rule itself ---------------------------


def test_only_rules_proposing_the_action_are_eligible() -> None:
    rules = [_entry("heavy_add", "add", 0.9), _entry("light_reduce", "reduce", 0.1)]
    picked = pick_rule_for_action(rules, "reduce")
    assert picked is not None
    assert picked["id"] == "light_reduce"


def test_heaviest_wins_regardless_of_position() -> None:
    rules = [_entry("light", "reduce", 0.35), _entry("heavy", "reduce", 0.6)]
    picked = pick_rule_for_action(rules, "reduce")
    assert picked is not None
    assert picked["id"] == "heavy"


def test_equal_weights_resolve_to_rule_file_order() -> None:
    rules = [
        _entry("earlier", "reduce", 0.6),
        _entry("later", "reduce", 0.6),
        _entry("lighter", "reduce", 0.5),
    ]
    picked = pick_rule_for_action(rules, "reduce")
    assert picked is not None
    assert picked["id"] == "earlier"
    # And the tie-break is positional, not alphabetical.
    picked_reversed = pick_rule_for_action(list(reversed(rules[:2])), "reduce")
    assert picked_reversed is not None
    assert picked_reversed["id"] == "later"


def test_no_rule_for_the_action_returns_none() -> None:
    assert pick_rule_for_action([], "reduce") is None
    assert pick_rule_for_action([_entry("only_add", "add", 0.5)], "reduce") is None
    # A card action no rule can carry finds nothing.
    assert pick_rule_for_action([_entry("only_add", "add", 0.5)], "insufficient_data") is None


def test_the_input_is_not_mutated() -> None:
    rules = [_entry("a", "reduce", 0.4), _entry("b", "add", 0.5)]
    snapshot = [dict(rule) for rule in rules]
    pick_rule_for_action(rules, "reduce")
    assert [dict(rule) for rule in rules] == snapshot


def test_aggregated_action_always_has_a_rule_on_real_cards() -> None:
    # Option C needs no direction fallback: whenever the engine aggregated an
    # action, at least one matched rule proposes exactly that action.
    for signals in (
        uptrend_signals(),
        _overbought_uptrend_signals(),
        uptrend_signals(
            ma={"ma_5": 90.0, "ma_20": 95.0, "ma_60": 100.0}, max_drawdown=-0.35, volume_z=3.0
        ),
    ):
        card = build_advice(symbol="2330", signals=signals, portfolio=_portfolio())
        aggregated = card["aggregated_action"]
        if aggregated is None:
            continue
        picked = pick_rule_for_action(card["matched_rules"], aggregated)
        assert picked is not None
        assert picked["action"] == aggregated
