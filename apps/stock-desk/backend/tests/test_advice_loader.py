"""Tests for the rule-file schema: what loads, and how failures are reported."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.advice.context import KNOWN_FIELDS
from app.advice.loader import (
    BANNED_PHRASES,
    DEFAULT_RULES_PATH,
    RuleSetError,
    condition_fields,
    load_default_rules,
    load_rules,
)
from tests.advice_helpers import minimal_rule, minimal_ruleset, write_rule_file

VALID_ACTIONS = {"add", "hold", "reduce", "stop_loss", "take_profit"}


# --- The shipped rule set ----------------------------------------------------


def test_default_rules_load_and_are_well_formed() -> None:
    ruleset = load_default_rules()
    assert ruleset.version == "1.0.2"
    assert ruleset.updated_at.isoformat() == "2026-07-26"
    assert 8 <= len(ruleset.rules) <= 12
    assert len(set(ruleset.rule_ids())) == len(ruleset.rules)
    for rule in ruleset.rules:
        assert rule.action in VALID_ACTIONS
        assert 0.0 < rule.weight <= 1.0
        assert rule.explanation and rule.counterargument and rule.invalidation


def test_default_rules_only_reference_known_fields() -> None:
    for rule in load_default_rules().rules:
        for path in condition_fields(rule.condition):
            assert path in KNOWN_FIELDS, f"{rule.id} 使用了未知欄位 {path}"


def test_default_rules_cover_the_required_themes() -> None:
    # Trend, overbought/oversold, drawdown protection and volume anomaly must
    # all be represented, per the M3 brief.
    ids = set(load_default_rules().rule_ids())
    assert {"uptrend_ma_stack", "downtrend_ma_stack"} <= ids
    assert {"rsi_overbought", "rsi_oversold_with_trend"} <= ids
    assert {"drawdown_protection", "deep_drawdown_stop"} <= ids
    assert "volume_spike_watch" in ids


def test_load_default_rules_is_cached() -> None:
    assert load_default_rules() is load_default_rules()


def test_condition_fields_walks_nested_groups(tmp_path: Path) -> None:
    condition = {
        "all": [
            {"any": [{"field": "kd.k", "op": "gt", "value": 80}]},
            {"field": "close", "op": "lt", "ref": "ma60.last"},
        ]
    }
    path = write_rule_file(tmp_path, minimal_ruleset(minimal_rule(condition=condition)))
    rule = load_rules(path).rules[0]
    assert condition_fields(rule.condition) == ["kd.k", "close", "ma60.last"]


# --- Valid custom files ------------------------------------------------------


def test_minimal_valid_file_loads(tmp_path: Path) -> None:
    path = write_rule_file(tmp_path, minimal_ruleset())
    ruleset = load_rules(path)
    assert ruleset.rule_ids() == ["sample_rule"]
    assert ruleset.rules[0].action == "hold"


# --- Invalid files -----------------------------------------------------------


def _error(tmp_path: Path, payload: object, *, name: str = "broken.yaml") -> str:
    path = write_rule_file(tmp_path, payload, name=name)
    with pytest.raises(RuleSetError) as excinfo:
        load_rules(path)
    return str(excinfo.value)


def test_missing_required_field_names_file_rule_and_field(tmp_path: Path) -> None:
    rule = {key: value for key, value in minimal_rule().items() if key != "explanation"}
    message = _error(tmp_path, minimal_ruleset(rule))
    assert "broken.yaml" in message
    assert "sample_rule" in message
    assert "explanation" in message


def test_missing_counterargument_is_rejected(tmp_path: Path) -> None:
    rule = {key: value for key, value in minimal_rule().items() if key != "counterargument"}
    assert "counterargument" in _error(tmp_path, minimal_ruleset(rule))


def test_unknown_condition_field_is_rejected(tmp_path: Path) -> None:
    condition = {"field": "rsi14.value", "op": "gt", "value": 70}
    message = _error(tmp_path, minimal_ruleset(minimal_rule(condition=condition)))
    assert "sample_rule" in message
    assert "rsi14.value" in message


def test_unknown_ref_field_is_rejected(tmp_path: Path) -> None:
    condition = {"field": "close", "op": "lt", "ref": "ma999.last"}
    assert "ma999.last" in _error(tmp_path, minimal_ruleset(minimal_rule(condition=condition)))


def test_nested_condition_error_points_at_the_rule(tmp_path: Path) -> None:
    condition = {"all": [{"field": "nope.last", "op": "gt", "value": 1}]}
    message = _error(tmp_path, minimal_ruleset(minimal_rule(condition=condition)))
    assert "sample_rule" in message
    assert "nope.last" in message


def test_condition_needs_exactly_one_right_hand_side(tmp_path: Path) -> None:
    both = {"field": "rsi14.last", "op": "gt", "value": 70, "ref": "ma20.last"}
    assert "value 或 ref" in _error(tmp_path, minimal_ruleset(minimal_rule(condition=both)))
    neither = {"field": "rsi14.last", "op": "gt"}
    assert "value 或 ref" in _error(tmp_path, minimal_ruleset(minimal_rule(condition=neither)))


def test_unknown_operator_is_rejected(tmp_path: Path) -> None:
    condition = {"field": "rsi14.last", "op": "much_greater", "value": 70}
    assert "op" in _error(tmp_path, minimal_ruleset(minimal_rule(condition=condition)))


def test_extra_condition_key_is_rejected(tmp_path: Path) -> None:
    condition = {"field": "rsi14.last", "op": "gt", "value": 70, "colour": "red"}
    assert "colour" in _error(tmp_path, minimal_ruleset(minimal_rule(condition=condition)))


def test_empty_condition_group_is_rejected(tmp_path: Path) -> None:
    assert "sample_rule" in _error(tmp_path, minimal_ruleset(minimal_rule(condition={"all": []})))


def test_weight_out_of_range_is_rejected(tmp_path: Path) -> None:
    assert "weight" in _error(tmp_path, minimal_ruleset(minimal_rule(weight=1.5)))
    assert "weight" in _error(tmp_path, minimal_ruleset(minimal_rule(weight=0.0)))


def test_unknown_action_is_rejected(tmp_path: Path) -> None:
    assert "action" in _error(tmp_path, minimal_ruleset(minimal_rule(action="short")))


def test_duplicate_rule_ids_are_rejected(tmp_path: Path) -> None:
    message = _error(tmp_path, minimal_ruleset(minimal_rule(), minimal_rule()))
    assert "重複" in message
    assert "sample_rule" in message


def test_bad_rule_id_format_is_rejected(tmp_path: Path) -> None:
    assert "id" in _error(tmp_path, minimal_ruleset(minimal_rule(id="Sample Rule")))


def test_version_must_be_semver(tmp_path: Path) -> None:
    payload = minimal_ruleset()
    payload["version"] = "v1"
    assert "version" in _error(tmp_path, payload)


def test_updated_at_must_be_a_date(tmp_path: Path) -> None:
    payload = minimal_ruleset()
    payload["updated_at"] = "not-a-date"
    assert "updated_at" in _error(tmp_path, payload)


def test_empty_rule_list_is_rejected(tmp_path: Path) -> None:
    payload = minimal_ruleset()
    payload["rules"] = []
    assert "rules" in _error(tmp_path, payload)


def test_unknown_top_level_key_is_rejected(tmp_path: Path) -> None:
    payload = minimal_ruleset()
    payload["author"] = "someone"
    assert "author" in _error(tmp_path, payload)


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_banned_phrases_are_rejected_in_rule_text(tmp_path: Path, phrase: str) -> None:
    rule = minimal_rule(explanation=f"這條規則{phrase}會出現。")
    message = _error(tmp_path, minimal_ruleset(rule))
    assert phrase in message
    assert "explanation" in message


def test_banned_phrase_in_name_is_rejected(tmp_path: Path) -> None:
    message = _error(tmp_path, minimal_ruleset(minimal_rule(name="保證命中的規則")))
    assert "name" in message


def test_broken_yaml_syntax_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "syntax.yaml"
    path.write_text("version: '1.0.0'\nrules:\n  - id: a\n   name: bad indent\n", encoding="utf-8")
    with pytest.raises(RuleSetError) as excinfo:
        load_rules(path)
    assert "YAML 解析失敗" in str(excinfo.value)
    assert "syntax.yaml" in str(excinfo.value)


def test_non_mapping_document_is_reported(tmp_path: Path) -> None:
    message = _error(tmp_path, ["not", "a", "mapping"], name="list.yaml")
    assert "mapping" in message
    assert "list.yaml" in message


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(RuleSetError) as excinfo:
        load_rules(tmp_path / "absent.yaml")
    assert "absent.yaml" in str(excinfo.value)
    assert "無法讀取" in str(excinfo.value)


def test_rule_without_id_still_produces_a_locatable_message(tmp_path: Path) -> None:
    rule = {key: value for key, value in minimal_rule().items() if key != "id"}
    message = _error(tmp_path, minimal_ruleset(rule))
    assert "第 1 條" in message


def test_default_rules_path_points_at_the_shipped_file() -> None:
    assert DEFAULT_RULES_PATH.name == "default.yaml"
    assert DEFAULT_RULES_PATH.is_file()
