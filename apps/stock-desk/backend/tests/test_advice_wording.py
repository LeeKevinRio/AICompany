"""Red-line scan: no guarantee-flavoured wording anywhere in the advice surface.

Same approach as ``test_signals_service.test_no_recommendation_fields_present``
in Phase 4: flatten the whole output and assert the banned terms are absent --
here applied to the rule file itself, to every rule's text, and to rendered
cards across the states the engine can reach.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.advice.engine import (
    CONFIDENCE_MEANING,
    DISCLAIMER,
    WEIGHT_MEANING,
    build_advice,
)
from app.advice.limits import PortfolioContext, RiskBudget
from app.advice.loader import DEFAULT_RULES_PATH, load_default_rules
from tests.advice_helpers import make_signals, uptrend_signals

#: The wording the brief bans outright.
FORBIDDEN_TERMS = ("保證", "必漲", "必賺", "穩賺")

#: Advice must not carry a price objective in any form.
FORBIDDEN_ADVICE_TERMS = ("目標價", "target_price", "price_target", "fair_value", "合理價")


def _cards() -> list[dict[str, Any]]:
    """One card per reachable action, so the scan covers all rendered text."""
    portfolio = PortfolioContext(
        symbol="2330",
        total_equity_twd=1_000_000.0,
        position_market_value_twd=50_000.0,
        position_cost_twd=45_000.0,
        gross_exposure_twd=500_000.0,
        quantity=500.0,
        close=110.0,
    )
    at_the_cap = portfolio.model_copy(
        update={"position_market_value_twd": 150_000.0, "quantity": 1_363.0}
    )
    return [
        build_advice(symbol="2330", signals=uptrend_signals(), portfolio=portfolio),
        build_advice(symbol="2330", signals=uptrend_signals(), portfolio=at_the_cap),
        build_advice(
            symbol="2330", signals=uptrend_signals(max_drawdown=-0.35), portfolio=portfolio
        ),
        build_advice(symbol="2330", signals=uptrend_signals(rsi=78.0), portfolio=portfolio),
        build_advice(symbol="2330", signals=make_signals(), portfolio=portfolio),
        build_advice(
            symbol="2330",
            signals=uptrend_signals(),
            portfolio=portfolio,
            budget=RiskBudget(max_position_weight=0.01),
        ),
    ]


@pytest.mark.parametrize("term", FORBIDDEN_TERMS)
def test_rule_file_text_is_free_of_banned_terms(term: str) -> None:
    assert term not in DEFAULT_RULES_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize("term", FORBIDDEN_TERMS)
def test_rule_objects_are_free_of_banned_terms(term: str) -> None:
    for rule in load_default_rules().rules:
        for text in (rule.name, rule.explanation, rule.counterargument, rule.invalidation):
            assert term not in text, f"{rule.id} 出現禁用字「{term}」"


@pytest.mark.parametrize("term", FORBIDDEN_TERMS)
def test_rendered_cards_are_free_of_banned_terms(term: str) -> None:
    for card in _cards():
        assert term not in str(card)


@pytest.mark.parametrize("term", FORBIDDEN_ADVICE_TERMS)
def test_cards_never_mention_a_price_objective(term: str) -> None:
    for card in _cards():
        assert term.lower() not in str(card).lower()


def test_every_card_carries_the_fixed_disclaimer() -> None:
    assert DISCLAIMER == "本工具為研究與教育用途，非投資建議"
    for card in _cards():
        assert card["disclaimer"] == DISCLAIMER


def test_every_card_states_its_rules_version_and_limit_verdicts() -> None:
    for card in _cards():
        assert card["rules_version"] == load_default_rules().version
        assert len(card["limits_check"]) == 5
        for check in card["limits_check"]:
            assert check["status"] in {"passed", "violated", "not_evaluable"}
            assert check["detail"]


def test_every_card_disclaims_that_confidence_and_weight_are_not_probabilities() -> None:
    # The qualifier has to travel with the payload: a consumer reading only the
    # dict must not be able to take these for odds.
    assert CONFIDENCE_MEANING == "信心等級反映規則一致性與資料完整度，非勝率或機率"
    assert WEIGHT_MEANING == "權重為規則優先序，非機率、勝率或預期報酬"
    for card in _cards():
        assert card["confidence_meaning"] == CONFIDENCE_MEANING
        for rule in card["matched_rules"]:
            assert rule["weight_meaning"] == WEIGHT_MEANING


def test_every_card_states_the_window_its_statistics_came_from() -> None:
    # Several rules say "觀察區間內"; the card has to say which interval.
    for card in _cards():
        window = card["observation_window"]
        assert set(window) == {"start", "end", "bars"}
        assert window["bars"] is not None


def test_drawdown_rules_describe_price_not_the_users_capital() -> None:
    # Drawdown is a statistic about the instrument's price path. It must not be
    # worded as a loss on the user's capital or on this position.
    forbidden = ("本金", "侵蝕", "可承受虧損")
    for rule in load_default_rules().rules:
        if "drawdown" not in rule.id:
            continue
        for term in forbidden:
            assert term not in rule.explanation, f"{rule.id}：{term}"
        assert "此標的" in rule.explanation


def test_no_card_recommends_adding_while_a_limit_is_violated() -> None:
    for card in _cards():
        violated = [c for c in card["limits_check"] if c["status"] == "violated"]
        if violated:
            assert card["action"] != "add", card["blocked_notices"]


def test_every_matched_rule_contributes_a_counterargument() -> None:
    # A card that states evidence must also state the opposing view.
    for card in _cards():
        if card["matched_rules"]:
            assert card["counterarguments"]
            assert card["invalidation_conditions"]
