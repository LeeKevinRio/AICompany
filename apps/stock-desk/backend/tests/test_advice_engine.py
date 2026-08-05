"""Tests for the advice engine: matching, skipping, conflicts and blocked adds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.advice.context import FIELD_LABELS, KNOWN_FIELDS, build_context, describe_field
from app.advice.engine import (
    ACTION_PRECEDENCE,
    CONFIDENCE_MEANING,
    DISCLAIMER,
    WEIGHT_MEANING,
    build_advice,
    evaluate_rule,
)
from app.advice.limits import PortfolioContext, RiskBudget
from app.advice.loader import load_default_rules, load_rules
from app.signals.service import compute_signals
from tests.advice_helpers import (
    make_signals,
    minimal_rule,
    minimal_ruleset,
    reported_net_worth,
    uptrend_signals,
    write_rule_file,
)
from tests.signals_helpers import bars_from_closes

#: Every key an advice card must carry.
REQUIRED_CARD_FIELDS = {
    "action",
    "quantity_range",
    "matched_rules",
    "counterarguments",
    "invalidation_conditions",
    "confidence",
    "confidence_meaning",
    "rules_version",
    "as_of",
    "observation_window",
    "disclaimer",
    "limits_check",
}

BUDGET = RiskBudget()


def _portfolio(**overrides: Any) -> PortfolioContext:
    base: dict[str, Any] = {
        "symbol": "2330",
        "total_equity_twd": 1_000_000.0,
        "position_market_value_twd": 50_000.0,
        "position_cost_twd": 45_000.0,
        "gross_exposure_twd": 500_000.0,
        # Cap 3 divides by the reported net worth, not by the valued book
        # (FR-9 option B); the same 1,000,000 keeps these cards' numbers
        # comparable to the pre-FR-9 ones.
        "net_worth": reported_net_worth(1_000_000.0),
        "book_fully_valued": True,
        "quantity": 500.0,
        "close": 110.0,
    }
    base.update(overrides)
    return PortfolioContext(**base)


def _card(signals: dict[str, Any], portfolio: PortfolioContext, **kwargs: Any) -> dict[str, Any]:
    return build_advice(symbol="2330", signals=signals, portfolio=portfolio, **kwargs)


# --- Card shape --------------------------------------------------------------


def test_card_carries_every_required_field() -> None:
    card = _card(uptrend_signals(), _portfolio())
    assert REQUIRED_CARD_FIELDS <= set(card)
    assert card["disclaimer"] == DISCLAIMER
    assert card["rules_version"] == load_default_rules().version
    assert card["as_of"] == "2026-07-24T13:30:00+00:00"
    assert card["confidence"] in {"low", "medium", "high"}
    assert len(card["limits_check"]) == 5


def test_card_fields_are_present_even_with_no_inputs_at_all() -> None:
    card = _card(make_signals(), PortfolioContext(symbol="2330"))
    assert REQUIRED_CARD_FIELDS <= set(card)
    assert card["action"] == "insufficient_data"
    assert card["quantity_range"] is None
    assert card["matched_rules"] == []
    assert card["counterarguments"] == []
    assert card["invalidation_conditions"] == []
    assert card["confidence"] == "low"
    assert all(check["status"] == "not_evaluable" for check in card["limits_check"])


def test_card_never_emits_a_target_price() -> None:
    flat = str(_card(uptrend_signals(), _portfolio())).lower()
    for banned in ("target_price", "目標價", "fair_value", "price_target"):
        assert banned not in flat


def test_as_of_is_null_when_the_signals_carry_none() -> None:
    assert _card(uptrend_signals(as_of=None), _portfolio())["as_of"] is None


def test_card_states_the_observation_window_behind_the_rules() -> None:
    # Rules speak of "觀察區間內"; the window makes that statement checkable.
    window = _card(uptrend_signals(), _portfolio())["observation_window"]
    assert set(window) == {"start", "end", "bars"}
    assert window["start"] == "2026-03-27"
    assert window["end"] == "2026-07-24"
    assert window["bars"] == 120
    assert window["start"] < window["end"]


def test_observation_window_is_null_dated_when_no_indicator_has_a_date_index() -> None:
    window = _card(make_signals(), _portfolio())["observation_window"]
    assert set(window) == {"start", "end", "bars"}
    assert window["start"] is None
    assert window["end"] is None
    assert window["bars"] == 120


def test_observation_window_survives_a_malformed_indicator_block() -> None:
    signals = uptrend_signals()
    signals["technical"] = {"broken": "not-a-mapping", **signals["technical"]}
    window = _card(signals, _portfolio())["observation_window"]
    assert window["start"] == "2026-03-27"
    assert window["bars"] == 120


def test_observation_window_follows_real_bars() -> None:
    bars = bars_from_closes([100.0 + i * 0.5 for i in range(90)])
    card = build_advice(
        symbol="2330", signals=compute_signals("2330", bars), portfolio=_portfolio(close=144.5)
    )
    window = card["observation_window"]
    assert window["bars"] == 90
    assert window["start"] == bars[0].date.isoformat()
    assert window["end"] == bars[-1].date.isoformat()


def test_confidence_and_weight_carry_their_non_probability_meaning() -> None:
    card = _card(uptrend_signals(), _portfolio())
    assert card["confidence_meaning"] == CONFIDENCE_MEANING
    assert "非勝率或機率" in card["confidence_meaning"]
    assert card["matched_rules"]
    for rule in card["matched_rules"]:
        assert rule["weight_meaning"] == WEIGHT_MEANING
        assert "非機率、勝率或預期報酬" in rule["weight_meaning"]


# --- Rule matching -----------------------------------------------------------


def test_matched_rules_expose_their_evidence_and_both_sides() -> None:
    card = _card(uptrend_signals(), _portfolio())
    assert card["action"] == "add"
    ids = [rule["id"] for rule in card["matched_rules"]]
    assert ids == ["uptrend_ma_stack", "macd_histogram_positive"]
    for rule in card["matched_rules"]:
        assert set(rule) == {
            "id",
            "name",
            "action",
            "weight",
            "weight_meaning",
            "explanation",
        }
        assert rule["explanation"]
    assert len(card["counterarguments"]) == 2
    assert len(card["invalidation_conditions"]) == 2
    assert card["evaluation"]["matched_rules"] == 2


def test_no_rule_matches_yields_hold_with_no_evidence_listed() -> None:
    # A flat book right on its averages: nothing extreme in either direction.
    signals = uptrend_signals(
        ma={"ma_5": 100.0, "ma_20": 100.0, "ma_60": 100.0},
        macd={"macd": 0.0, "signal": 0.0, "histogram": 0.0},
    )
    card = _card(signals, _portfolio(close=100.0))
    assert card["action"] == "hold"
    assert card["matched_rules"] == []
    assert card["counterarguments"] == []
    assert card["evaluation"]["evaluated_rules"] == card["evaluation"]["total_rules"]
    assert card["confidence"] == "medium"


def test_drawdown_rules_fire_together_and_the_heaviest_action_wins() -> None:
    # Below the 60-day average with a -35% drawdown: three defensive rules fire.
    # ``reduce`` carries 0.6 + 0.5 against ``stop_loss``'s 0.8, so ``reduce``
    # wins -- and the stop-loss rule stays visible on the card either way.
    card = _card(uptrend_signals(max_drawdown=-0.35), _portfolio(close=90.0))
    ids = [rule["id"] for rule in card["matched_rules"]]
    assert {"drawdown_protection", "deep_drawdown_stop", "price_below_ma60"} <= set(ids)
    assert card["action"] == "reduce"
    actions = {entry["action"]: entry["weight"] for entry in card["action_weights"]}
    assert actions["reduce"] == pytest.approx(1.1)
    assert actions["stop_loss"] == pytest.approx(0.8)
    assert card["direction_weights"][0]["direction"] == "defensive"


def test_a_lone_deep_drawdown_produces_a_stop_loss() -> None:
    signals = uptrend_signals(
        max_drawdown=-0.35,
        ma={"ma_5": 100.0, "ma_20": 100.0, "ma_60": 100.0},
        macd={"macd": 0.0, "signal": 0.0, "histogram": 0.0},
    )
    # Drawdown deep enough for both drawdown rules; ``stop_loss`` (0.8) beats
    # the single ``reduce`` (0.6).
    card = _card(signals, _portfolio(close=100.0))
    assert card["action"] == "stop_loss"


def test_overbought_and_upper_band_downgrade_a_bullish_add_to_hold() -> None:
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
    card = _card(signals, _portfolio())
    ids = [rule["id"] for rule in card["matched_rules"]]
    assert "rsi_overbought" in ids
    assert "bollinger_upper_breach" in ids
    # The constructive side is heavier (0.85 vs 0.8) but never wins outright
    # while defensive rules are firing.
    assert card["aggregated_action"] == "add"
    assert card["action"] == "hold"
    assert len(card["downgrade_notices"]) == 1
    assert "防禦型規則" in card["downgrade_notices"][0]
    assert "RSI 高檔超買" in card["downgrade_notices"][0]
    assert card["blocked_action"] is None


def test_volume_anomaly_is_flagged() -> None:
    card = _card(uptrend_signals(volume_z=-3.1), _portfolio())
    assert "volume_spike_watch" in [rule["id"] for rule in card["matched_rules"]]


# --- Conflicting actions -----------------------------------------------------


def test_conflicting_actions_are_both_listed_and_the_heavier_one_wins() -> None:
    # Bullish MA stack (add 0.5 + 0.35) against a deep drawdown (stop_loss 0.8
    # + reduce 0.6): the defensive side is heavier and wins, but the bullish
    # side stays on the card.
    card = _card(uptrend_signals(max_drawdown=-0.35), _portfolio())
    actions = {entry["action"]: entry["weight"] for entry in card["action_weights"]}
    assert card["has_conflict"] is True
    assert actions["add"] == pytest.approx(0.85)
    assert actions["reduce"] == pytest.approx(0.6)
    assert actions["stop_loss"] == pytest.approx(0.8)
    # Defensive weight (1.4) beats constructive weight (0.85), then the
    # heaviest defensive action wins inside that direction.
    directions = {entry["direction"]: entry["weight"] for entry in card["direction_weights"]}
    assert directions["defensive"] == pytest.approx(1.4)
    assert directions["constructive"] == pytest.approx(0.85)
    assert card["action"] == "stop_loss"
    # Both sides' counter-arguments survive into the card.
    assert len(card["counterarguments"]) == len(card["matched_rules"])


def test_a_weight_tie_breaks_towards_the_defensive_action(tmp_path: Path) -> None:
    payload = minimal_ruleset(
        minimal_rule(
            id="bullish",
            action="add",
            weight=0.5,
            condition={"field": "rsi14.last", "op": "lt", "value": 90},
        ),
        minimal_rule(
            id="bearish",
            action="reduce",
            weight=0.5,
            condition={"field": "rsi14.last", "op": "gt", "value": 10},
        ),
    )
    ruleset = load_rules(write_rule_file(tmp_path, payload))
    card = _card(uptrend_signals(), _portfolio(), ruleset=ruleset)
    assert card["has_conflict"] is True
    assert card["action"] == "reduce"
    assert ACTION_PRECEDENCE.index("reduce") < ACTION_PRECEDENCE.index("add")


# --- Missing data ------------------------------------------------------------


def test_rules_with_missing_inputs_are_skipped_with_a_reason() -> None:
    # No moving averages at all: every MA-dependent rule must be skipped, not
    # silently reported as "did not match".
    card = _card(uptrend_signals(ma=None), _portfolio())
    skipped = {entry["id"]: entry for entry in card["evaluation"]["skipped_rules"]}
    assert "uptrend_ma_stack" in skipped
    assert "ma5.last" in skipped["uptrend_ma_stack"]["missing_fields"]
    assert "缺少輸入欄位" in skipped["uptrend_ma_stack"]["reason"]
    assert describe_field("ma5.last") in skipped["uptrend_ma_stack"]["reason"]
    assert card["evaluation"]["evaluated_rules"] < card["evaluation"]["total_rules"]
    assert card["evaluation"]["data_completeness"] < 1.0


def test_missing_close_price_skips_the_price_rules() -> None:
    card = _card(uptrend_signals(), _portfolio(close=None))
    skipped_ids = {entry["id"] for entry in card["evaluation"]["skipped_rules"]}
    assert {"uptrend_ma_stack", "price_below_ma60"} <= skipped_ids


def test_all_inputs_missing_yields_insufficient_data() -> None:
    card = _card(make_signals(), PortfolioContext(symbol="2330"))
    assert card["action"] == "insufficient_data"
    assert card["confidence"] == "low"
    assert card["evaluation"]["evaluated_rules"] == 0
    assert len(card["evaluation"]["skipped_rules"]) == card["evaluation"]["total_rules"]


def test_thin_data_never_produces_an_add(tmp_path: Path) -> None:
    # Only 1 of 4 rules is evaluable, and it says "add": too thin to endorse.
    payload = minimal_ruleset(
        minimal_rule(
            id="cheap_add",
            action="add",
            weight=0.5,
            condition={"field": "rsi14.last", "op": "lt", "value": 90},
        ),
        minimal_rule(id="needs_beta", condition={"field": "beta.value", "op": "gt", "value": 1}),
        minimal_rule(id="needs_kd", condition={"field": "kd.k", "op": "gt", "value": 50}),
        minimal_rule(id="needs_ma", condition={"field": "ma60.last", "op": "gt", "value": 1}),
    )
    ruleset = load_rules(write_rule_file(tmp_path, payload))
    card = _card(make_signals(rsi=55.0), _portfolio(), ruleset=ruleset)
    assert card["evaluation"]["data_completeness"] == 0.25
    assert card["aggregated_action"] == "add"
    assert card["action"] == "insufficient_data"
    assert card["confidence"] == "low"
    # The evidence is still shown -- the card refuses to advise, it does not
    # pretend the rule never fired.
    assert [rule["id"] for rule in card["matched_rules"]] == ["cheap_add"]


def test_thin_data_keeps_a_defensive_action(tmp_path: Path) -> None:
    payload = minimal_ruleset(
        minimal_rule(
            id="cheap_reduce",
            action="reduce",
            weight=0.5,
            condition={"field": "rsi14.last", "op": "gt", "value": 50},
        ),
        minimal_rule(id="needs_beta", condition={"field": "beta.value", "op": "gt", "value": 1}),
        minimal_rule(id="needs_kd", condition={"field": "kd.k", "op": "gt", "value": 50}),
        minimal_rule(id="needs_ma", condition={"field": "ma60.last", "op": "gt", "value": 1}),
    )
    ruleset = load_rules(write_rule_file(tmp_path, payload))
    card = _card(make_signals(rsi=55.0), _portfolio(), ruleset=ruleset)
    assert card["action"] == "reduce"
    assert card["confidence"] == "low"


def test_evaluate_rule_reports_every_missing_field_not_just_the_first() -> None:
    rule = load_default_rules().rules[0]  # uptrend_ma_stack
    outcome = evaluate_rule(rule, dict.fromkeys(KNOWN_FIELDS, None))
    assert outcome.skipped is True
    assert outcome.matched is False
    assert set(outcome.missing_fields) == {"ma5.last", "ma20.last", "ma60.last", "close"}


def test_a_partially_decidable_any_group_is_still_skipped(tmp_path: Path) -> None:
    condition = {
        "any": [
            {"field": "rsi14.last", "op": "gt", "value": 10},
            {"field": "beta.value", "op": "gt", "value": 10},
        ]
    }
    payload = minimal_ruleset(minimal_rule(condition=condition))
    ruleset = load_rules(write_rule_file(tmp_path, payload))
    card = _card(uptrend_signals(beta=None), _portfolio(), ruleset=ruleset)
    assert card["matched_rules"] == []
    assert card["evaluation"]["skipped_rules"][0]["missing_fields"] == ["beta.value"]


def test_any_group_matches_when_all_inputs_are_present(tmp_path: Path) -> None:
    condition = {
        "any": [
            {"field": "rsi14.last", "op": "gt", "value": 90},
            {"field": "beta.value", "op": "gt", "value": 1.0},
        ]
    }
    payload = minimal_ruleset(minimal_rule(condition=condition))
    ruleset = load_rules(write_rule_file(tmp_path, payload))
    card = _card(uptrend_signals(), _portfolio(), ruleset=ruleset)
    assert [rule["id"] for rule in card["matched_rules"]] == ["sample_rule"]


# --- Risk limits gating the action ------------------------------------------


def test_add_is_blocked_when_a_limit_is_violated_and_the_cap_is_named() -> None:
    # Golden case: the holding is already at the 15% single-name cap.
    card = _card(uptrend_signals(), _portfolio(position_market_value_twd=150_000.0,
                                               quantity=1_363.0))
    assert card["action"] == "hold"
    assert card["blocked_action"] == "add"
    assert card["blocked_notices"] == ["加碼建議被第 1 條上限（單一標的佔比上限）擋下。"]
    assert card["quantity_range"] is None
    breached = [check for check in card["limits_check"] if check["status"] == "violated"]
    assert [check["id"] for check in breached] == ["single_position_weight"]
    # The bullish rules stay visible; only the action is downgraded.
    assert [rule["id"] for rule in card["matched_rules"]] == [
        "uptrend_ma_stack",
        "macd_histogram_positive",
        "concentration_watch",
    ]


def test_every_violated_cap_is_quoted_when_several_block_the_add() -> None:
    card = _card(
        uptrend_signals(),
        _portfolio(
            position_market_value_twd=150_000.0,
            quantity=1_363.0,
            gross_exposure_twd=1_200_000.0,
        ),
    )
    assert card["blocked_action"] == "add"
    assert len(card["blocked_notices"]) == 2
    assert "第 1 條上限（單一標的佔比上限）" in card["blocked_notices"][0]
    assert "第 3 條上限（總曝險上限）" in card["blocked_notices"][1]


def test_a_violated_cap_does_not_rewrite_a_defensive_action() -> None:
    card = _card(
        uptrend_signals(max_drawdown=-0.35),
        _portfolio(position_market_value_twd=200_000.0, quantity=1_818.0),
    )
    assert card["action"] in {"reduce", "stop_loss"}
    assert card["blocked_action"] is None
    assert card["blocked_notices"] == []


def test_add_keeps_its_quantity_range_when_every_cap_passes() -> None:
    card = _card(uptrend_signals(), _portfolio())
    assert card["action"] == "add"
    quantity = card["quantity_range"]
    assert quantity is not None
    assert quantity["min_shares"] <= quantity["max_shares"]
    assert quantity["basis"]


def test_atr_from_the_signal_layer_makes_the_per_trade_cap_evaluable() -> None:
    with_atr = _card(uptrend_signals(atr=2.0), _portfolio())
    without_atr = _card(uptrend_signals(atr=None), _portfolio())
    assert with_atr["limits_check"][3]["status"] == "passed"
    assert without_atr["limits_check"][3]["status"] == "not_evaluable"


def test_an_explicit_atr_on_the_context_wins_over_the_signal_layer() -> None:
    card = _card(uptrend_signals(atr=2.0), _portfolio(atr=40.0, quantity=200.0))
    # 200 shares x 2 x 40 = 16,000 TWD = 1.6% of equity, over the 1% cap.
    assert card["limits_check"][3]["status"] == "violated"


def test_a_custom_budget_changes_the_verdict() -> None:
    portfolio = _portfolio(position_market_value_twd=60_000.0)
    strict = RiskBudget(max_position_weight=0.05)
    assert _card(uptrend_signals(), portfolio, budget=strict)["blocked_action"] == "add"
    assert _card(uptrend_signals(), portfolio, budget=BUDGET)["blocked_action"] is None


# --- Confidence --------------------------------------------------------------


def test_confidence_is_high_when_data_is_complete_and_rules_agree() -> None:
    assert _card(uptrend_signals(), _portfolio())["confidence"] == "high"


def test_agreement_is_measured_on_the_winning_direction(tmp_path: Path) -> None:
    # Defensive weight (0.5 + 0.45 = 0.95) narrowly beats a single add (0.9).
    # Agreement must be read off the *winning* side: 0.95 / 1.85 = 0.51, which
    # is a "medium". Reading the heaviest single action instead would score the
    # losing add (0.9 / 1.85 = 0.49) and understate it as "low".
    payload = minimal_ruleset(
        minimal_rule(
            id="bullish",
            action="add",
            weight=0.9,
            condition={"field": "rsi14.last", "op": "lt", "value": 90},
        ),
        minimal_rule(
            id="bearish_trim",
            action="reduce",
            weight=0.5,
            condition={"field": "rsi14.last", "op": "gt", "value": 10},
        ),
        minimal_rule(
            id="bearish_stop",
            action="stop_loss",
            weight=0.45,
            condition={"field": "rsi14.last", "op": "gt", "value": 20},
        ),
    )
    ruleset = load_rules(write_rule_file(tmp_path, payload))
    card = _card(uptrend_signals(), _portfolio(), ruleset=ruleset)
    directions = {entry["direction"]: entry["weight"] for entry in card["direction_weights"]}
    assert directions["defensive"] == pytest.approx(0.95)
    assert directions["constructive"] == pytest.approx(0.9)
    assert card["aggregated_action"] == "reduce"
    assert card["action"] == "reduce"
    assert card["confidence"] == "medium"


def test_confidence_drops_when_rules_disagree() -> None:
    card = _card(uptrend_signals(max_drawdown=-0.35), _portfolio())
    assert card["has_conflict"] is True
    assert card["confidence"] in {"low", "medium"}


def test_confidence_drops_when_data_is_sparse() -> None:
    card = _card(uptrend_signals(ma=None, macd=None, kd=None, bollinger=None), _portfolio())
    assert card["evaluation"]["data_completeness"] < 0.8
    assert card["confidence"] in {"low", "medium"}


# --- Context construction ----------------------------------------------------


def test_build_context_always_produces_the_full_vocabulary() -> None:
    context = build_context(make_signals(), PortfolioContext(symbol="2330"))
    assert set(context) == KNOWN_FIELDS == set(FIELD_LABELS)
    assert all(value is None for value in context.values())


def test_build_context_reads_the_real_signal_output() -> None:
    # Guards the fake in ``advice_helpers`` against drifting from the real
    # ``compute_signals`` shape.
    bars = bars_from_closes([100.0 + i * 0.5 for i in range(90)])
    signals = compute_signals("2330", bars)
    portfolio = _portfolio(close=144.5)
    context = build_context(signals, portfolio)
    assert context["close"] == pytest.approx(144.5)
    assert context["ma60.last"] is not None
    assert context["rsi14.last"] is not None
    assert context["atr14.last"] is not None
    assert context["drawdown.max_drawdown"] is not None
    assert context["position.weight"] == pytest.approx(0.05)


def test_end_to_end_over_real_bars_produces_a_complete_card() -> None:
    bars = bars_from_closes([100.0 + i * 0.5 for i in range(90)])
    signals = compute_signals("2330", bars)
    card = build_advice(symbol="2330", signals=signals, portfolio=_portfolio(close=144.5))
    assert REQUIRED_CARD_FIELDS <= set(card)
    assert card["action"] in {
        "add",
        "hold",
        "reduce",
        "stop_loss",
        "take_profit",
        "insufficient_data",
    }
    assert card["as_of"] is not None


def test_non_numeric_signal_values_are_treated_as_missing() -> None:
    signals = uptrend_signals()
    signals["technical"]["rsi"]["last"] = {"rsi": "n/a"}
    context = build_context(signals, _portfolio())
    assert context["rsi14.last"] is None


def test_describe_field_falls_back_to_the_raw_path() -> None:
    assert describe_field("rsi14.last") == "rsi14.last（14 日 RSI 最新值）"
    assert describe_field("unknown.path") == "unknown.path"
