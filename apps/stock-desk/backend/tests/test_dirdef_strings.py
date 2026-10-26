"""``app.dirdef.strings.string_values`` on test-only types (ADR-0027 FL-78 (l1), N-128).

One cell per shape: a top-level string, strings inside a nested model and a
nested dataclass, and strings inside list, tuple and dict values. The
disclosed gaps (dict keys, set and frozenset members) are pinned as gaps, and
an unreadable type raises instead of being skipped. A tripwire (TA ruling 7c)
fails when a definition or rule model gains a field whose strings the
enumeration would not see, pointing at N-136.
"""

from __future__ import annotations

import collections.abc
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import get_args, get_origin

import pytest
from pydantic import BaseModel

from app.dirdef.definition import DirectionDefinition
from app.dirdef.rules import (
    OutlookAllOf,
    OutlookAnyOf,
    OutlookComparison,
    OutlookRule,
    OutlookRuleSet,
)
from app.dirdef.strings import string_values


class Leaf(BaseModel):
    text: str
    number: float


@dataclass(frozen=True)
class Note:
    body: str
    count: int


class Holder(BaseModel):
    title: str
    leaf: Leaf
    note: Note
    items: list[str]
    pair: tuple[str, int]
    table: dict[str, str]
    nested: tuple[Leaf, ...]
    missing: str | None
    flag: bool
    when: date


def _holder() -> Holder:
    return Holder(
        title="top",
        leaf=Leaf(text="in-model", number=1.0),
        note=Note(body="in-dataclass", count=2),
        items=["in-list-1", "in-list-2"],
        pair=("in-tuple", 3),
        table={"key-not-listed": "in-dict"},
        nested=(Leaf(text="in-tuple-model", number=2.0),),
        missing=None,
        flag=True,
        when=date(2026, 10, 25),
    )


def test_a_top_level_string_is_listed() -> None:
    assert string_values("alone") == ("alone",)


@pytest.mark.parametrize(
    "expected",
    [
        pytest.param("top", id="model-field"),
        pytest.param("in-model", id="nested-model"),
        pytest.param("in-dataclass", id="nested-dataclass"),
        pytest.param("in-list-1", id="list-value"),
        pytest.param("in-tuple", id="tuple-value"),
        pytest.param("in-dict", id="dict-value"),
        pytest.param("in-tuple-model", id="model-in-tuple"),
    ],
)
def test_each_shape_is_listed(expected: str) -> None:
    assert expected in string_values(_holder())


def test_values_come_in_field_order_depth_first() -> None:
    assert string_values(_holder()) == (
        "top",
        "in-model",
        "in-dataclass",
        "in-list-1",
        "in-list-2",
        "in-tuple",
        "in-dict",
        "in-tuple-model",
    )


def test_a_field_added_to_the_type_is_listed_without_naming_it() -> None:
    class Wider(Leaf):
        extra: str

    assert string_values(Wider(text="a", number=0.0, extra="b")) == ("a", "b")


def test_dict_keys_and_set_members_are_the_disclosed_gaps() -> None:
    assert string_values({"key": 1}) == ()
    assert string_values({"only-member"}) == ()
    assert string_values(frozenset({"only-member"})) == ()


@pytest.mark.parametrize("value", [b"bytes", object(), 1j])
def test_an_unreadable_value_raises(value: object) -> None:
    with pytest.raises(TypeError):
        string_values(value)


def test_a_dataclass_type_itself_is_not_walked() -> None:
    with pytest.raises(TypeError):
        string_values(Note)


# --- C-8 tripwire (TA B2 ruling point 7c; N-136) ---------------------------------------

#: Annotation origins whose strings ``string_values`` would not see.
UNENUMERATED_ORIGINS = (set, frozenset, dict, collections.abc.Mapping, collections.abc.Set)


def _unenumerated_fields(model: type[BaseModel], seen: set[type] | None = None) -> list[str]:
    """Fields of ``model`` (recursively) annotated with a set, frozenset, dict or Mapping."""
    seen = set() if seen is None else seen
    if model in seen:
        return []
    seen.add(model)
    found: list[str] = []
    for name, info in model.model_fields.items():
        stack: list[object] = [info.annotation]
        while stack:
            annotation = stack.pop()
            origin = get_origin(annotation) or annotation
            if isinstance(origin, type) and issubclass(origin, UNENUMERATED_ORIGINS):
                found.append(f"{model.__name__}.{name}")
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                found += _unenumerated_fields(annotation, seen)
            stack.extend(get_args(annotation))
    return found


@pytest.mark.parametrize(
    "model",
    [
        DirectionDefinition,
        OutlookRuleSet,
        OutlookRule,
        OutlookComparison,
        OutlookAllOf,
        OutlookAnyOf,
    ],
    ids=lambda m: m.__name__,
)
def test_no_definition_or_rule_field_hides_strings_from_the_scan(model: type[BaseModel]) -> None:
    found = _unenumerated_fields(model)
    assert found == [], (
        f"{found} would hold strings string_values does not list (set, frozenset, dict keys); "
        "resolve tracking item N-136 (fail-closed enumeration) before adding such a field"
    )


def test_the_tripwire_has_teeth() -> None:
    class Inner(BaseModel):
        tags: frozenset[str]

    class Outer(BaseModel):
        table: dict[str, int]
        inner: tuple[Inner, ...]
        maybe: Mapping[str, str] | None

    assert sorted(_unenumerated_fields(Outer)) == ["Inner.tags", "Outer.maybe", "Outer.table"]
