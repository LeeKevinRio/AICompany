"""Red-line scan: no guarantee-flavoured wording anywhere in the advice surface.

Same approach as ``test_signals_service.test_no_recommendation_fields_present``
in Phase 4: flatten the whole output and assert the banned terms are absent --
here applied to the rule file itself, to every rule's text, and to rendered
cards across the states the engine can reach.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.advice.engine import (
    CONFIDENCE_MEANING,
    DISCLAIMER,
    WEIGHT_MEANING,
    build_advice,
)
from app.advice.limits import PortfolioContext, RiskBudget
from app.advice.loader import BANNED_PHRASES, DEFAULT_RULES_PATH, Comparison, load_default_rules
from tests.advice_helpers import make_signals, reported_net_worth, uptrend_signals

#: S6 fix (work/reviews/risk-final-review.md 列管項:「禁用詞清單前後端鏡像漂
#: 移」): this file's own ``FORBIDDEN_TERMS``/``FORBIDDEN_ADVICE_TERMS`` used
#: to be a hand-typed subset of §1.3 (work/stock-desk-phase8-風控定調.md §1.3)
#: that had quietly fallen behind both `loader.BANNED_PHRASES` (missing 必跌/
#: 穩賠/一定會/包賺/零風險/無風險) and the frontend's
#: `adviceWording.ts::FRONTEND_FORBIDDEN_TERMS` (missing 上看). Both scan
#: lists now read the same `shared/forbidden-terms.json` — the frontend's
#: `sharedForbiddenTerms.test.ts` reads the identical file and asserts every
#: term is present in its own list, so the two can no longer drift apart
#: silently. Production `loader.py` deliberately stays self-contained (its
#: `BANNED_PHRASES` is not re-pointed at this file) so the backend Docker
#: image build does not need to reach outside `apps/stock-desk/backend`; a
#: same-content guard test below keeps it in sync instead.
_SHARED_FORBIDDEN_TERMS_PATH = (
    Path(__file__).resolve().parents[2] / "shared" / "forbidden-terms.json"
)


def _load_shared_forbidden_terms() -> dict[str, tuple[str, ...]]:
    payload = json.loads(_SHARED_FORBIDDEN_TERMS_PATH.read_text(encoding="utf-8"))
    return {
        "guarantee": tuple(payload["guarantee"]),
        "price_target": tuple(payload["price_target"]),
    }


_SHARED_FORBIDDEN_TERMS = _load_shared_forbidden_terms()

#: The wording the brief bans outright (§1.3 保證性).
FORBIDDEN_TERMS = _SHARED_FORBIDDEN_TERMS["guarantee"]

#: Advice must not carry a price objective in any form (§1.3 價格目標).
FORBIDDEN_ADVICE_TERMS = _SHARED_FORBIDDEN_TERMS["price_target"]


def test_shared_forbidden_terms_guarantee_category_matches_loader_banned_phrases() -> None:
    """S6 fix: guards production `loader.BANNED_PHRASES` — deliberately kept
    self-contained rather than reading `shared/forbidden-terms.json` at
    runtime — against silently drifting from the single source of truth this
    file's own scan list is now read from."""
    assert set(BANNED_PHRASES) == set(FORBIDDEN_TERMS)


def _cards() -> list[dict[str, Any]]:
    """One card per reachable action, so the scan covers all rendered text."""
    portfolio = PortfolioContext(
        symbol="2330",
        total_equity_twd=1_000_000.0,
        position_market_value_twd=50_000.0,
        position_cost_twd=45_000.0,
        gross_exposure_twd=500_000.0,
        # Reported net worth included so the FR-9 disclosure sentences on cap 3
        # are inside the scan below rather than outside it.
        net_worth=reported_net_worth(1_000_000.0, age_days=8),
        book_fully_valued=True,
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


def test_concentration_rule_speaks_only_of_its_own_fixed_threshold() -> None:
    # ``max_position_weight`` is editable from the settings page; this rule's
    # threshold is fixed. Wording that ties the two together would report an
    # *already violated* cap (user lowered it to 10%, holding sits at 11%) as
    # merely "approaching" one -- a mis-statement in the dangerous direction.
    # Both texts must therefore quote the rule's own number, and the same one.
    rule = next(r for r in load_default_rules().rules if r.id == "concentration_watch")
    condition = rule.condition
    assert isinstance(condition, Comparison)
    assert condition.field == "position.weight"
    assert condition.value is not None
    threshold = f"{condition.value * 100:.0f}%"
    assert threshold in rule.explanation
    assert threshold in rule.invalidation
    for term in ("接近", "已達上限", "超過上限"):
        assert term not in rule.explanation, f"concentration_watch：{term}"


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
