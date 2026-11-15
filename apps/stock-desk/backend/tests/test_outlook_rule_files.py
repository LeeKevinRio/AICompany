"""The market h3 / h5 rule files as landed (freeze pack section 4; ADR-0025 D-2 point 3).

* the bytes are the freeze pack round 2 bytes: sha256 equal to the 4.3 values,
  8,290 bytes each, UTF-8, LF only, exactly one trailing newline;
* both load through ``app.dirdef.rules.load_ruleset`` with the one banned phrase
  list (``app.advice.loader.BANNED_PHRASES``): 10 rules, ``theta`` 2,
  ``min_completeness`` 1.0, every ``invalidation`` a condition tree over its
  condition's fields (TA Q1);
* the banned phrase check is rerun on the landed bytes the way 4.3 describes:
  every string value, NFKC-normalised and with whitespace removed, against all
  ten phrases -- 0 hits (CG-2 / RC-135 rerun on the landed bytes);
* h5 is h3 with only the horizon changed (first comment line, the reversal
  vote's field, the 3 / 5 in its explanation);
* neither file is registered: ``PUBLISHED_RULESETS`` stays empty until CG-2.
"""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.advice.loader import BANNED_PHRASES
from app.dirdef.registry import PUBLISHED_RULESETS
from app.dirdef.rules import (
    OutlookComparison,
    OutlookRuleSet,
    condition_fields,
    load_ruleset,
    rules_logic_sha256,
)
from app.dirdef.strings import string_values
from app.forecast.definitions import rules_path

#: Freeze pack 4.3, round 2 (check values for the transcription, not registered values).
FREEZE_PACK_SHA256 = {
    3: "f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443",
    5: "0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c",
}

#: ``rules_logic_sha256`` reference values (``name`` inside the hash; TA SP-A ruling
#: 2026-11-15). They must not move when the rule models are tightened (TA question 4).
LOGIC_SHA256 = {
    3: "ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484",
    5: "e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb",
}

RULE_IDS = (
    "trend_up",
    "trend_down",
    "trend_neutral",
    "momentum_up",
    "momentum_down",
    "momentum_neutral",
    "stretch_down_reversal",
    "stretch_up_reversal",
    "stretch_neutral",
    "high_volatility_range",
)


def _bytes(horizon: int) -> bytes:
    return rules_path(horizon).read_bytes()


def _load(horizon: int) -> OutlookRuleSet:
    data = _bytes(horizon)
    return load_ruleset(
        data, rules_sha256=hashlib.sha256(data).hexdigest(), banned_phrases=BANNED_PHRASES
    )


def _squeezed(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).split())


def _yaml_strings(value: Any) -> list[str]:
    """Every string scalar of the parsed YAML, keys excluded (as ``string_values``)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _yaml_strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _yaml_strings(item)]
    return []


@pytest.mark.parametrize("horizon", [3, 5])
def test_the_bytes_are_the_freeze_pack_bytes(horizon: int) -> None:
    data = _bytes(horizon)
    assert hashlib.sha256(data).hexdigest() == FREEZE_PACK_SHA256[horizon]
    assert len(data) == 8290
    data.decode("utf-8")
    assert b"\r" not in data
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")


def test_the_rules_directory_holds_the_two_files_only() -> None:
    directory = rules_path(3).parent
    assert directory == Path(rules_path(5)).parent
    assert sorted(p.name for p in directory.iterdir()) == ["h3.yaml", "h5.yaml"]


@pytest.mark.parametrize("horizon", [3, 5])
def test_the_file_loads_with_the_banned_phrases(horizon: int) -> None:
    ruleset = _load(horizon)
    assert ruleset.version == "1.0.0"
    assert tuple(rule.id for rule in ruleset.rules) == RULE_IDS
    assert ruleset.aggregation.theta == 2.0
    assert ruleset.aggregation.min_completeness == 1.0
    assert all(rule.weight == 1.0 for rule in ruleset.rules)
    for rule in ruleset.rules:
        assert set(condition_fields(rule.invalidation)) == set(condition_fields(rule.condition))


@pytest.mark.parametrize("horizon", [3, 5])
def test_the_directional_rules_are_gated_and_the_range_rule_is_its_complement(
    horizon: int,
) -> None:
    gate = OutlookComparison.model_validate(
        {"field": "vol_ratio_20_120", "op": "lte", "value": 1.5}
    )
    rules = {rule.id: rule for rule in _load(horizon).rules}
    for rule in rules.values():
        if rule.direction == "range":
            continue
        condition = rule.condition
        assert hasattr(condition, "all") and gate in condition.all
    assert rules["high_volatility_range"].condition == OutlookComparison.model_validate(
        {"field": "vol_ratio_20_120", "op": "gt", "value": 1.5}
    )


@pytest.mark.parametrize("horizon", [3, 5])
def test_banned_phrases_rerun_on_the_landed_bytes_find_nothing(horizon: int) -> None:
    data = _bytes(horizon)
    raw = yaml.safe_load(data.decode("utf-8"))
    from_yaml = _yaml_strings(raw)
    from_model = list(string_values(_load(horizon)))
    # 4.3: 159 string values per file, field names and operators included.
    assert len(from_yaml) == 159
    assert len(from_model) == 159
    assert len(BANNED_PHRASES) == 10
    phrases = [_squeezed(phrase) for phrase in BANNED_PHRASES]
    hits = [(text, p) for text in from_yaml + from_model for p in phrases if p in _squeezed(text)]
    assert hits == []


def test_h5_is_h3_with_only_the_horizon_changed() -> None:
    h3 = _bytes(3).decode("utf-8")
    expected = (
        h3.replace("outlook-market-v1.0-h3", "outlook-market-v1.0-h5", 1)
        .replace("z_past_3", "z_past_5")
        .replace("過去 3 個交易日", "過去 5 個交易日")
        .replace("換算到 3 日", "換算到 5 日")
    )
    assert _bytes(5).decode("utf-8") == expected


@pytest.mark.parametrize("horizon", [3, 5])
def test_the_logic_hash_is_the_reference_value(horizon: int) -> None:
    assert rules_logic_sha256(_load(horizon)) == LOGIC_SHA256[horizon]


def _leaves(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = node.get("all", node.get("any"))
    if children is None:
        return [node]
    return [leaf for child in children for leaf in _leaves(child)]


@pytest.mark.parametrize("horizon", [3, 5])
def test_the_files_hold_no_bool_int_or_string_number(horizon: int) -> None:
    # TA question 4: the strict float tightening only refuses what lax mode coerced,
    # and the landed files hold none of it, so their bytes and hashes cannot move.
    raw = yaml.safe_load(_bytes(horizon))
    numbers: list[object] = [rule["weight"] for rule in raw["rules"]]
    for rule in raw["rules"]:
        for tree in (rule["condition"], rule["invalidation"]):
            numbers += [leaf["value"] for leaf in _leaves(tree) if "value" in leaf]
    assert len(numbers) > 10
    assert all(type(number) is float for number in numbers)


def test_the_two_rule_sets_differ_in_logic() -> None:
    assert rules_logic_sha256(_load(3)) != rules_logic_sha256(_load(5))


def test_neither_file_is_registered() -> None:
    assert dict(PUBLISHED_RULESETS) == {}
