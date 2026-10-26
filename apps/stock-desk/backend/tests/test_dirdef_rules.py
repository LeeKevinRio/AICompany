"""Outlook rule set models and loader (ADR-0027 D-1 ``app/dirdef/`` (1)-(4); FL-78 (h)(j)(k)).

* validation context: ADR-0027 marks "does the pydantic validation context
  reach the after validator" as unverified; the first cells prove it on
  test-only models (outer and nested validators, ``model_validate`` and
  ``model_validate_json``) and on the real rule set model;
* FL-78 (h) banned phrases: every banned phrase (taken one by one from
  ``app.advice.loader.BANNED_PHRASES``, not listed here) x every string value
  position of a rule set. Each position is marked with what stops it:
  ``scan`` (the banned-phrase scan; the loader raises
  ``BannedPhraseRuleSetError``) or ``type`` (the model's own validation --
  pattern or closed list -- rejects the value before the scan runs; asserted as
  a construction failure, which still returns nothing);
* the position table is generated from the clean fixture's string values
  (tied to ``len(string_values(...))``; every level of the condition tree:
  ``field``, ``ref`` and ``op``; qa M-2, N137-4);
* fail-closed with a clean fixture: accepted with ``BANNED_PHRASES``, refused
  with ``()``, without context, with a context lacking phrases, and through the
  constructor; ``model_construct``, ``model_copy(update=...)`` and the
  deprecated ``copy(update/include/exclude=...)`` raise (qa M-1);
* FL-78 (j) evaluable subset through the ``OUTLOOK_RULE_FIELDS`` seam
  (``tests.dirdef_helpers.RULE_FIELDS_SEAM``);
* FL-78 (k) one changed byte with the old hash is refused;
* ``rules_logic_sha256``: text-only and version changes keep it (FL-33 pure
  part), logic changes move it.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from typing import Any, Self

import pytest
from pydantic import BaseModel, ValidationError, ValidationInfo, model_validator

from app.advice.loader import BANNED_PHRASES
from app.dirdef import rules
from app.dirdef.rules import (
    BANNED_PHRASES_CONTEXT_KEY,
    OUTLOOK_RULE_FIELDS,
    RULE_TEXT_FIELDS,
    BannedPhraseRuleSetError,
    OutlookAllOf,
    OutlookAnyOf,
    OutlookComparison,
    OutlookRule,
    OutlookRuleSet,
    RuleSetLoadError,
    condition_fields,
    load_ruleset,
    rules_logic_sha256,
)
from app.dirdef.strings import string_values
from tests.dirdef_helpers import (
    RULE_FIELDS_SEAM,
    SUBSTITUTE_FIELDS,
    rule_data,
    ruleset_bytes,
    ruleset_data,
    sha256_hex,
)

CONTEXT = {BANNED_PHRASES_CONTEXT_KEY: BANNED_PHRASES}


@pytest.fixture
def fields(monkeypatch: pytest.MonkeyPatch) -> Callable[[frozenset[str]], None]:
    """Replace the outlook rule field list (seam ``RULE_FIELDS_SEAM``)."""

    def install(value: frozenset[str]) -> None:
        monkeypatch.setattr(rules, RULE_FIELDS_SEAM, value)

    install(SUBSTITUTE_FIELDS)
    return install


def _load(data: dict[str, Any], phrases: tuple[str, ...] = BANNED_PHRASES) -> OutlookRuleSet:
    raw = ruleset_bytes(data)
    return load_ruleset(raw, rules_sha256=sha256_hex(raw), banned_phrases=phrases)


# --- Validation context reaches the after validator (ADR 〔未查證〕) -------------------

SEEN: list[tuple[str, object]] = []


class _Inner(BaseModel):
    x: int

    @model_validator(mode="after")
    def _record(self, info: ValidationInfo) -> Self:
        SEEN.append(("inner", info.context))
        return self


class _Outer(BaseModel):
    inner: tuple[_Inner, ...]

    @model_validator(mode="after")
    def _record(self, info: ValidationInfo) -> Self:
        SEEN.append(("outer", info.context))
        return self


@pytest.fixture
def seen() -> list[tuple[str, object]]:
    SEEN.clear()
    return SEEN


def test_the_context_reaches_outer_and_nested_after_validators(
    seen: list[tuple[str, object]],
) -> None:
    context = {"k": 1}
    _Outer.model_validate({"inner": [{"x": 1}, {"x": 2}]}, context=context)
    assert seen == [("inner", context), ("inner", context), ("outer", context)]
    assert all(entry[1] is context for entry in seen)


def test_the_context_reaches_the_validator_through_json_too(
    seen: list[tuple[str, object]],
) -> None:
    _Outer.model_validate_json('{"inner": [{"x": 1}]}', context={"k": 2})
    assert seen == [("inner", {"k": 2}), ("outer", {"k": 2})]


def test_without_a_context_the_validator_sees_none(seen: list[tuple[str, object]]) -> None:
    _Outer.model_validate({"inner": [{"x": 1}]})
    _Outer(inner=(_Inner(x=1),))
    assert {entry[1] for entry in seen} == {None}


def test_the_rule_set_validator_receives_the_loader_context(
    fields: Callable[[frozenset[str]], None],
) -> None:
    # Accepted with the context; refused, for want of phrases, without it.
    assert OutlookRuleSet.model_validate(ruleset_data(), context=CONTEXT).version == "1.0.0"
    with pytest.raises(ValidationError, match="without banned phrases"):
        OutlookRuleSet.model_validate(ruleset_data())


# --- FL-78 (h): banned phrase x string value position -----------------------------------
#
# Positions come from the clean fixture mechanically: the JSON dump of the
# validated rule set is walked in field order (the order ``string_values``
# uses -- asserted below), and cell i appends the phrase to the i-th string.
# Each position is classified by its key: ``scan`` keys are free text or field
# names, stopped by the banned-phrase scan; ``type`` keys are a pattern or a
# closed list, which the model itself refuses before the scan runs.

SCAN_KEYS = frozenset({"name", "explanation", "counterargument", "invalidation", "field", "ref"})
TYPE_KEYS = frozenset({"version", "id", "direction", "op"})


def _clean_dump() -> dict[str, Any]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(rules, RULE_FIELDS_SEAM, SUBSTITUTE_FIELDS)
        ruleset = OutlookRuleSet.model_validate(ruleset_data(), context=CONTEXT)
    dumped: dict[str, Any] = ruleset.model_dump(mode="json")
    assert [s for _, s in _walk(dumped)] == list(string_values(ruleset))
    return dumped


def _walk(value: object, path: str = "") -> list[tuple[str, str]]:
    """(path, string) pairs of a JSON dump, in field order."""
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        return [pair for key, item in value.items() for pair in _walk(item, f"{path}.{key}")]
    if isinstance(value, list):
        return [pair for i, item in enumerate(value) for pair in _walk(item, f"{path}[{i}]")]
    return []


CLEAN = _clean_dump()
POSITIONS = [path.lstrip(".") for path, _ in _walk(CLEAN)]


def _key(path: str) -> str:
    return path.rsplit(".", 1)[-1]


def _stopped_by(path: str) -> str:
    key = _key(path)
    if key in SCAN_KEYS:
        return "scan"
    if key in TYPE_KEYS:
        return "type"
    raise AssertionError(f"string position {path} is not classified as scan or type")


def _poisoned(index: int, phrase: str) -> dict[str, Any]:
    data = copy.deepcopy(CLEAN)
    counter = iter(range(len(POSITIONS)))

    def plant(value: object) -> object:
        if isinstance(value, str):
            return value + phrase if next(counter) == index else value
        if isinstance(value, dict):
            return {key: plant(item) for key, item in value.items()}
        if isinstance(value, list):
            return [plant(item) for item in value]
        return value

    planted = plant(data)
    assert isinstance(planted, dict)
    return planted


def test_the_position_table_is_every_string_value_of_the_fixture(
    fields: Callable[[frozenset[str]], None],
) -> None:
    # Tied to string_values: a string field added to the models grows the table.
    ruleset = OutlookRuleSet.model_validate(CLEAN, context=CONTEXT)
    assert len(POSITIONS) == len(string_values(ruleset))


def test_the_table_covers_every_level_of_the_condition_tree() -> None:
    expected = {
        "version",
        "rules[0].id",
        "rules[0].name",
        "rules[0].direction",
        "rules[0].condition.all[0].field",
        "rules[0].condition.all[0].op",
        "rules[0].condition.all[1].any[0].field",
        "rules[0].condition.all[1].any[0].op",
        "rules[0].condition.all[1].any[0].ref",
        "rules[0].explanation",
        "rules[0].counterargument",
        "rules[0].invalidation",
    }
    assert set(POSITIONS) == expected
    assert {path: _stopped_by(path) for path in POSITIONS}  # every position classified


def _with_poisoned_fields(install: Callable[[frozenset[str]], None], phrase: str) -> None:
    # Field / ref names with the phrase pass the evaluable check, so the scan stops them.
    install(SUBSTITUTE_FIELDS | {name + phrase for name in SUBSTITUTE_FIELDS})


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
@pytest.mark.parametrize("index", range(len(POSITIONS)), ids=POSITIONS)
def test_a_banned_phrase_in_any_position_is_refused_by_the_loader(
    fields: Callable[[frozenset[str]], None], phrase: str, index: int
) -> None:
    _with_poisoned_fields(fields, phrase)
    data = _poisoned(index, phrase)
    if _stopped_by(POSITIONS[index]) == "scan":
        with pytest.raises(BannedPhraseRuleSetError):
            _load(data)
    else:
        with pytest.raises(RuleSetLoadError) as caught:
            _load(data)
        assert not isinstance(caught.value, BannedPhraseRuleSetError)


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
@pytest.mark.parametrize("index", range(len(POSITIONS)), ids=POSITIONS)
def test_a_banned_phrase_in_any_position_is_refused_without_context(
    fields: Callable[[frozenset[str]], None], phrase: str, index: int
) -> None:
    _with_poisoned_fields(fields, phrase)
    with pytest.raises(ValidationError):
        OutlookRuleSet.model_validate(_poisoned(index, phrase))


def test_the_clean_dump_loads() -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(rules, RULE_FIELDS_SEAM, SUBSTITUTE_FIELDS)
        assert _load(CLEAN).version == "1.0.0"


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_a_banned_phrase_is_refused_with_context_too(
    fields: Callable[[frozenset[str]], None], phrase: str
) -> None:
    data = ruleset_data(rule_data(explanation=f"it {phrase}"))
    with pytest.raises(ValidationError, match="banned phrase"):
        OutlookRuleSet.model_validate(data, context=CONTEXT)


def test_a_second_rule_is_scanned(fields: Callable[[frozenset[str]], None]) -> None:
    data = ruleset_data(rule_data(), rule_data(id="second", name=f"x {BANNED_PHRASES[-1]}"))
    with pytest.raises(BannedPhraseRuleSetError):
        _load(data)


# --- Fail-closed with a clean fixture ---------------------------------------------------


def test_a_clean_rule_set_loads_with_the_banned_phrases(
    fields: Callable[[frozenset[str]], None],
) -> None:
    ruleset = _load(ruleset_data())
    assert ruleset.version == "1.0.0"
    assert isinstance(ruleset.rules, tuple)
    assert isinstance(ruleset.rules[0].condition, OutlookAllOf)


def test_an_empty_phrase_list_is_refused(fields: Callable[[frozenset[str]], None]) -> None:
    with pytest.raises(RuleSetLoadError, match="empty"):
        _load(ruleset_data(), phrases=())


@pytest.mark.parametrize(
    "context",
    [
        pytest.param(None, id="no-context"),
        pytest.param({}, id="no-key"),
        pytest.param({BANNED_PHRASES_CONTEXT_KEY: ()}, id="empty"),
        pytest.param({BANNED_PHRASES_CONTEXT_KEY: list(BANNED_PHRASES)}, id="list"),
        pytest.param({BANNED_PHRASES_CONTEXT_KEY: ("",)}, id="empty-phrase"),
        pytest.param({BANNED_PHRASES_CONTEXT_KEY: (1,)}, id="non-string"),
    ],
)
def test_model_validate_without_usable_phrases_is_refused(
    fields: Callable[[frozenset[str]], None], context: dict[str, Any] | None
) -> None:
    with pytest.raises(ValidationError):
        OutlookRuleSet.model_validate(ruleset_data(), context=context)


def test_the_constructor_is_refused(fields: Callable[[frozenset[str]], None]) -> None:
    rule = OutlookRule.model_validate(rule_data())
    with pytest.raises(ValidationError, match="without banned phrases"):
        OutlookRuleSet(version="1.0.0", rules=(rule,))


GUARDED: list[tuple[type[BaseModel], dict[str, Any]]] = [
    (OutlookRuleSet, ruleset_data()),
    (OutlookRule, rule_data()),
    (OutlookComparison, {"field": "index.ret_5d", "op": "gt", "value": 0.0}),
    (OutlookAllOf, {"all": [{"field": "index.ret_5d", "op": "gt", "value": 0.0}]}),
    (OutlookAnyOf, {"any": [{"field": "index.ret_5d", "op": "gt", "value": 0.0}]}),
]


@pytest.mark.parametrize(("model", "data"), GUARDED, ids=lambda v: getattr(v, "__name__", ""))
def test_model_construct_raises(model: type[BaseModel], data: dict[str, Any]) -> None:
    with pytest.raises(TypeError, match="model_construct"):
        model.model_construct(**data)


@pytest.mark.parametrize(("model", "data"), GUARDED, ids=lambda v: getattr(v, "__name__", ""))
def test_model_copy_with_update_raises_and_plain_copy_works(
    fields: Callable[[frozenset[str]], None], model: type[BaseModel], data: dict[str, Any]
) -> None:
    instance = model.model_validate(data, context=CONTEXT)
    with pytest.raises(TypeError, match="model_copy"):
        instance.model_copy(update={})
    assert instance.model_copy() == instance


@pytest.mark.parametrize(("model", "data"), GUARDED, ids=lambda v: getattr(v, "__name__", ""))
@pytest.mark.parametrize(
    "kwargs",
    [{"update": {}}, {"exclude": {"version"}}, {"include": {"version"}}],
    ids=["update", "exclude", "include"],
)
def test_the_deprecated_copy_with_arguments_raises(
    fields: Callable[[frozenset[str]], None],
    model: type[BaseModel],
    data: dict[str, Any],
    kwargs: dict[str, Any],
) -> None:
    # qa M-1: BaseModel.copy(update=...) would build a rule set the scan never saw.
    instance = model.model_validate(data, context=CONTEXT)
    with pytest.raises(TypeError, match="copy"):
        instance.copy(**kwargs)
    assert instance.copy() == instance


def test_the_deprecated_copy_cannot_swap_in_unscanned_rules(
    fields: Callable[[frozenset[str]], None],
) -> None:
    ruleset = OutlookRuleSet.model_validate(ruleset_data(), context=CONTEXT)
    poisoned = OutlookRule.model_validate(rule_data(explanation=f"x {BANNED_PHRASES[0]}"))
    with pytest.raises(TypeError):
        ruleset.copy(update={"rules": (poisoned,)})


# --- FL-78 (j): evaluable subset -------------------------------------------------------


def test_the_production_field_list_is_empty() -> None:
    assert OUTLOOK_RULE_FIELDS == frozenset()


def test_with_the_empty_field_list_every_rule_set_is_refused() -> None:
    with pytest.raises(RuleSetLoadError, match="OUTLOOK_RULE_FIELDS"):
        _load(ruleset_data())


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param("index.ret_5d", id="top-level-field"),
        pytest.param("index.ma20_gap", id="nested-any-field"),
        pytest.param("breadth.adv_ratio", id="nested-ref"),
    ],
)
def test_one_field_outside_the_list_is_refused(
    fields: Callable[[frozenset[str]], None], missing: str
) -> None:
    fields(SUBSTITUTE_FIELDS - {missing})
    with pytest.raises(RuleSetLoadError, match="OUTLOOK_RULE_FIELDS"):
        _load(ruleset_data())


def test_condition_fields_walks_nested_groups() -> None:
    rule = OutlookRule.model_validate(rule_data())
    assert condition_fields(rule.condition) == [
        "index.ret_5d",
        "index.ma20_gap",
        "breadth.adv_ratio",
    ]


# --- Schema ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(ruleset_data(version="1.0"), id="version-not-semver"),
        pytest.param({**ruleset_data(), "extra": 1}, id="extra-ruleset-key"),
        pytest.param(ruleset_data(rule_data(extra="x")), id="extra-rule-key"),
        pytest.param({"version": "1.0.0", "rules": []}, id="no-rules"),
        pytest.param(ruleset_data(rule_data(), rule_data()), id="duplicate-id"),
        pytest.param(ruleset_data(rule_data(weight=0.0)), id="weight-zero"),
        pytest.param(ruleset_data(rule_data(direction="up")), id="direction-unknown"),
        pytest.param(
            ruleset_data(
                rule_data(condition={"field": "index.ret_5d", "op": "gt", "value": 1.0, "ref": "x"})
            ),
            id="value-and-ref",
        ),
        pytest.param(
            ruleset_data(rule_data(condition={"field": "index.ret_5d", "op": "gt"})),
            id="no-operand",
        ),
        pytest.param(ruleset_data(rule_data(condition={"all": []})), id="empty-all"),
    ],
)
def test_malformed_rule_sets_are_refused(
    fields: Callable[[frozenset[str]], None], data: dict[str, Any]
) -> None:
    with pytest.raises(RuleSetLoadError):
        _load(data)


# --- Loader steps ----------------------------------------------------------------------


def test_one_changed_byte_with_the_old_hash_is_refused(
    fields: Callable[[frozenset[str]], None],
) -> None:
    raw = ruleset_bytes(ruleset_data())
    digest = sha256_hex(raw)
    changed = raw.replace(b"0.5", b"0.6", 1)
    assert changed != raw and len(changed) == len(raw)
    with pytest.raises(RuleSetLoadError, match="rules_sha256"):
        load_ruleset(changed, rules_sha256=digest, banned_phrases=BANNED_PHRASES)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"\xff\xfe", id="not-utf8"),
        pytest.param(b"version: [unclosed", id="bad-yaml"),
        pytest.param(b"- a\n- b\n", id="top-level-list"),
    ],
)
def test_unparseable_bytes_are_refused(raw: bytes) -> None:
    with pytest.raises(RuleSetLoadError):
        load_ruleset(raw, rules_sha256=sha256_hex(raw), banned_phrases=BANNED_PHRASES)


def test_the_hash_is_checked_before_parsing() -> None:
    with pytest.raises(RuleSetLoadError, match="rules_sha256"):
        load_ruleset(b"\xff", rules_sha256="0" * 64, banned_phrases=BANNED_PHRASES)


def test_a_single_string_for_the_phrases_is_a_type_error() -> None:
    raw = ruleset_bytes(ruleset_data())
    with pytest.raises(TypeError):
        load_ruleset(raw, rules_sha256=sha256_hex(raw), banned_phrases="x")


def test_text_instead_of_bytes_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        load_ruleset("version: 1", rules_sha256="0" * 64, banned_phrases=BANNED_PHRASES)  # type: ignore[arg-type]


# --- rules_logic_sha256 ----------------------------------------------------------------


def _ruleset(**rule_overrides: Any) -> OutlookRuleSet:
    return OutlookRuleSet.model_validate(ruleset_data(rule_data(**rule_overrides)), context=CONTEXT)


def test_the_rule_logic_hash_follows_the_canonical_form(
    fields: Callable[[frozenset[str]], None],
) -> None:
    ruleset = _ruleset()
    dumped = ruleset.model_dump(mode="json")
    payload = {
        "rules": [
            {k: v for k, v in rule.items() if k not in {"explanation", "counterargument"}}
            for rule in dumped["rules"]
        ]
    }
    text = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    assert rules_logic_sha256(ruleset) == hashlib.sha256(text.encode("utf-8")).hexdigest()


#: Rule text fields: a different value keeps the logic hash.
RULE_TEXT_CHANGES: dict[str, Any] = {"explanation": "reworded", "counterargument": "reworded"}
#: Every other rule field: a different value moves the logic hash.
RULE_LOGIC_CHANGES: dict[str, Any] = {
    "id": "renamed_rule",
    "name": "renamed",
    "direction": "bearish",
    "weight": 0.6,
    "condition": {"field": "index.ret_5d", "op": "lt", "value": 0.0},
    "invalidation": "another test",
}
#: Every field of a comparison leaf, changed in the fixture's first leaf.
COMPARISON_CHANGES: dict[str, Any] = {
    "field": "index.ma20_gap",
    "op": "gte",
    "value": 0.5,
    "ref": "breadth.adv_ratio",
}


def test_every_rule_and_condition_field_has_a_hash_cell() -> None:
    # qa F-5: a field added to the models must land in one of these tables.
    assert set(RULE_TEXT_CHANGES) == RULE_TEXT_FIELDS
    assert set(RULE_LOGIC_CHANGES) == set(OutlookRule.model_fields) - RULE_TEXT_FIELDS
    assert set(COMPARISON_CHANGES) == set(OutlookComparison.model_fields)
    # Rule set level: version (outside, see the bump cell) and rules (the cells below).
    assert set(OutlookRuleSet.model_fields) == {"version", "rules"}


@pytest.mark.parametrize("name", sorted(RULE_TEXT_CHANGES))
def test_a_text_only_change_keeps_the_rule_logic_hash(
    fields: Callable[[frozenset[str]], None], name: str
) -> None:
    changed = _ruleset(**{name: RULE_TEXT_CHANGES[name]})
    assert rules_logic_sha256(changed) == rules_logic_sha256(_ruleset())


@pytest.mark.parametrize("name", sorted(RULE_LOGIC_CHANGES))
def test_a_logic_change_moves_the_rule_logic_hash(
    fields: Callable[[frozenset[str]], None], name: str
) -> None:
    changed = _ruleset(**{name: RULE_LOGIC_CHANGES[name]})
    assert rules_logic_sha256(changed) != rules_logic_sha256(_ruleset())


@pytest.mark.parametrize("name", sorted(COMPARISON_CHANGES))
def test_a_condition_leaf_change_moves_the_rule_logic_hash(
    fields: Callable[[frozenset[str]], None], name: str
) -> None:
    leaf: dict[str, Any] = {"field": "index.ret_5d", "op": "gt", "value": 0.0}
    if name == "ref":
        leaf.pop("value")
    leaf[name] = COMPARISON_CHANGES[name]
    condition = copy.deepcopy(rule_data()["condition"])
    condition["all"][0] = leaf
    changed = _ruleset(condition=condition)
    assert rules_logic_sha256(changed) != rules_logic_sha256(_ruleset())


def test_a_version_bump_keeps_the_rule_logic_hash(
    fields: Callable[[frozenset[str]], None],
) -> None:
    bumped = OutlookRuleSet.model_validate(ruleset_data(version="1.0.1"), context=CONTEXT)
    assert rules_logic_sha256(bumped) == rules_logic_sha256(_ruleset())
