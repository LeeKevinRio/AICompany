"""The two rule set type rulings (tech-architect 2026-11-14, Q1 and Q2): counter-examples.

Q1 -- ``invalidation`` is an ``OutlookCondition`` tree, not a string, and two load
guards hold: (a) its fields are in ``OUTLOOK_RULE_FIELDS``; (b) its field set
equals the condition's field set. Q2 -- ``aggregation`` is required, has exactly
``theta`` and ``min_completeness``, both floats (bool and strings refused),
finite, ``theta > 0`` and ``0 < min_completeness <= 1``; ``theta: 2`` and
``theta: 2.0`` give one ``rules_logic_sha256``.

Rule files are built as YAML text here, so the YAML scalars themselves
(``2``, ``2.0``, ``true``, ``.nan``, ``.inf``) are what the loader sees.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.advice.loader import BANNED_PHRASES
from app.dirdef import rules
from app.dirdef.rules import (
    OutlookAnyOf,
    OutlookRuleSet,
    RuleSetLoadError,
    load_ruleset,
    rules_logic_sha256,
)
from tests.dirdef_helpers import (
    RULE_FIELDS_SEAM,
    SUBSTITUTE_FIELDS,
    rule_data,
    ruleset_bytes,
    ruleset_data,
    sha256_hex,
)


@pytest.fixture
def fields(monkeypatch: pytest.MonkeyPatch) -> Callable[[frozenset[str]], None]:
    def install(value: frozenset[str]) -> None:
        monkeypatch.setattr(rules, RULE_FIELDS_SEAM, value)

    install(SUBSTITUTE_FIELDS)
    return install


def _load_bytes(raw: bytes) -> OutlookRuleSet:
    return load_ruleset(raw, rules_sha256=sha256_hex(raw), banned_phrases=BANNED_PHRASES)


def _load(data: dict[str, Any]) -> OutlookRuleSet:
    return _load_bytes(ruleset_bytes(data))


#: One rule in YAML; the aggregation block is spliced in front of it.
_RULE_YAML = """rules:
  - id: index_momentum
    name: index momentum
    direction: bullish
    weight: 1.0
    condition: {field: index.ret_5d, op: gt, value: 0.0}
    explanation: the index rose
    counterargument: rises fade
    invalidation: {field: index.ret_5d, op: lte, value: 0.0}
"""


def _yaml(theta: str, min_completeness: str = "1.0") -> bytes:
    head = (
        f'version: "1.0.0"\naggregation:\n  theta: {theta}\n'
        f"  min_completeness: {min_completeness}\n"
    )
    return (head + _RULE_YAML).encode("utf-8")


# --- Q1: invalidation is a condition tree -----------------------------------------------


def test_the_fixture_invalidation_loads_as_a_tree(fields: Callable[[frozenset[str]], None]) -> None:
    ruleset = _load(ruleset_data())
    assert isinstance(ruleset.rules[0].invalidation, OutlookAnyOf)


@pytest.mark.parametrize(
    "invalidation",
    [
        pytest.param("index.ret_5d lte 0", id="string"),
        pytest.param("index.ret_5d lte 0 or index.ma20_gap lte breadth.adv_ratio", id="or-string"),
        pytest.param(None, id="null"),
        pytest.param({"or": []}, id="unknown-key"),
        pytest.param({"any": []}, id="empty-any"),
    ],
)
def test_an_invalidation_that_is_not_a_condition_tree_is_refused(
    fields: Callable[[frozenset[str]], None], invalidation: object
) -> None:
    with pytest.raises(RuleSetLoadError):
        _load(ruleset_data(rule_data(invalidation=invalidation)))


def test_a_missing_invalidation_is_refused(fields: Callable[[frozenset[str]], None]) -> None:
    rule = rule_data()
    del rule["invalidation"]
    with pytest.raises(RuleSetLoadError, match="invalidation"):
        _load(ruleset_data(rule))


def test_guard_a_an_invalidation_field_outside_the_list_is_refused(
    fields: Callable[[frozenset[str]], None],
) -> None:
    # The condition reads listed fields only; the invalidation names one more.
    invalidation = {
        "any": [
            {"field": "index.ret_5d", "op": "lte", "value": 0.0},
            {"field": "index.ma20_gap", "op": "lte", "ref": "breadth.adv_ratio"},
            {"field": "index.unlisted", "op": "gt", "value": 0.0},
        ]
    }
    with pytest.raises(RuleSetLoadError, match="OUTLOOK_RULE_FIELDS"):
        _load(ruleset_data(rule_data(invalidation=invalidation)))


def test_guard_a_an_invalidation_ref_outside_the_list_is_refused(
    fields: Callable[[frozenset[str]], None],
) -> None:
    invalidation = {
        "any": [
            {"field": "index.ret_5d", "op": "lte", "value": 0.0},
            {"field": "index.ma20_gap", "op": "lte", "ref": "index.unlisted"},
        ]
    }
    with pytest.raises(RuleSetLoadError, match="OUTLOOK_RULE_FIELDS"):
        _load(ruleset_data(rule_data(invalidation=invalidation)))


@pytest.mark.parametrize(
    "invalidation",
    [
        pytest.param({"field": "index.ret_5d", "op": "lte", "value": 0.0}, id="subset"),
        pytest.param(
            {
                "any": [
                    {"field": "index.ret_5d", "op": "lte", "value": 0.0},
                    {"field": "index.ma20_gap", "op": "lte", "value": 0.0},
                ]
            },
            id="ref-missing",
        ),
    ],
)
def test_guard_b_an_invalidation_reading_fewer_fields_is_refused(
    fields: Callable[[frozenset[str]], None], invalidation: dict[str, Any]
) -> None:
    with pytest.raises(RuleSetLoadError, match="condition's fields"):
        _load(ruleset_data(rule_data(invalidation=invalidation)))


def test_guard_b_an_invalidation_reading_more_fields_is_refused(
    fields: Callable[[frozenset[str]], None],
) -> None:
    # Every field is listed (guard (a) passes); the extra one breaks guard (b).
    fields(SUBSTITUTE_FIELDS | {"index.extra"})
    invalidation = {
        "any": [
            {"field": "index.ret_5d", "op": "lte", "value": 0.0},
            {"field": "index.ma20_gap", "op": "lte", "ref": "breadth.adv_ratio"},
            {"field": "index.extra", "op": "gt", "value": 0.0},
        ]
    }
    with pytest.raises(RuleSetLoadError, match="condition's fields"):
        _load(ruleset_data(rule_data(invalidation=invalidation)))


def test_guard_b_compares_sets_not_order_or_multiplicity(
    fields: Callable[[frozenset[str]], None],
) -> None:
    # Same set, another order and a repeated field: accepted.
    invalidation = {
        "any": [
            {"field": "index.ma20_gap", "op": "lte", "ref": "breadth.adv_ratio"},
            {"field": "index.ret_5d", "op": "lte", "value": 0.0},
            {"field": "index.ret_5d", "op": "eq", "value": 0.0},
        ]
    }
    assert _load(ruleset_data(rule_data(invalidation=invalidation))).version == "1.0.0"


# --- Q2: aggregation ---------------------------------------------------------------------


def test_aggregation_is_required(fields: Callable[[frozenset[str]], None]) -> None:
    data = ruleset_data()
    del data["aggregation"]
    with pytest.raises(RuleSetLoadError, match="aggregation"):
        _load(data)


@pytest.mark.parametrize(
    "aggregation",
    [
        pytest.param({"theta": 2.0}, id="no-min-completeness"),
        pytest.param({"min_completeness": 1.0}, id="no-theta"),
        pytest.param({"theta": 2.0, "min_completeness": 1.0, "damping": 1.5}, id="extra-key"),
        pytest.param({}, id="empty"),
    ],
)
def test_aggregation_has_exactly_its_two_keys(
    fields: Callable[[frozenset[str]], None], aggregation: dict[str, Any]
) -> None:
    with pytest.raises(RuleSetLoadError, match="aggregation"):
        _load(ruleset_data(aggregation=aggregation))


def test_theta_2_and_2_0_give_one_logic_hash_and_3_another(
    fields: Callable[[frozenset[str]], None],
) -> None:
    as_int = _load_bytes(_yaml("2"))
    as_float = _load_bytes(_yaml("2.0"))
    three = _load_bytes(_yaml("3"))
    assert as_int.aggregation.theta == 2.0 and isinstance(as_int.aggregation.theta, float)
    assert rules_logic_sha256(as_int) == rules_logic_sha256(as_float)
    assert rules_logic_sha256(three) != rules_logic_sha256(as_int)


@pytest.mark.parametrize(
    "scalar",
    [
        pytest.param("true", id="true"),
        pytest.param("false", id="false"),
        pytest.param("0", id="zero"),
        pytest.param("0.0", id="zero-float"),
        pytest.param("-2", id="negative"),
        pytest.param(".nan", id="nan"),
        pytest.param(".inf", id="inf"),
        pytest.param("-.inf", id="minus-inf"),
        pytest.param('"2"', id="string"),
        pytest.param("null", id="null"),
    ],
)
def test_a_bad_theta_is_refused(fields: Callable[[frozenset[str]], None], scalar: str) -> None:
    with pytest.raises(RuleSetLoadError, match="theta"):
        _load_bytes(_yaml(scalar))


@pytest.mark.parametrize(
    "scalar",
    [
        pytest.param("true", id="true"),
        pytest.param("0", id="zero"),
        pytest.param("-0.5", id="negative"),
        pytest.param(".nan", id="nan"),
        pytest.param(".inf", id="inf"),
        pytest.param("1.01", id="above-one"),
        pytest.param('"1.0"', id="string"),
    ],
)
def test_a_bad_min_completeness_is_refused(
    fields: Callable[[frozenset[str]], None], scalar: str
) -> None:
    with pytest.raises(RuleSetLoadError, match="min_completeness"):
        _load_bytes(_yaml("2", scalar))


@pytest.mark.parametrize("scalar", ["1", "1.0", "0.5", "0.001"])
def test_min_completeness_in_the_half_open_unit_interval_loads(
    fields: Callable[[frozenset[str]], None], scalar: str
) -> None:
    assert 0 < _load_bytes(_yaml("2", scalar)).aggregation.min_completeness <= 1
