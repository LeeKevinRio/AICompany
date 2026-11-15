"""Outlook rule set models, rule logic hash and loader (ADR-0027 D-1 ``app/dirdef/``).

The load guards follow ADR-0025 D-2 point 3 ("schema as ``app/advice/loader.py``")
as ADR-0027 D-1 places them; a rule set object can only be built through the
loader or ``model_validate`` with a validation context:

1. every model is ``extra="forbid"``; the rule set ``version`` is semver; YAML is
   parsed with ``yaml.safe_load``;
2. evaluable subset: every ``field`` and ``ref`` of the condition tree and of
   the ``invalidation`` tree (nested ``all``/``any`` included) must be in
   :data:`OUTLOOK_RULE_FIELDS`, the one source of outlook rule fields (not the
   advice card's field list);
3. banned phrases: the loader takes them as the keyword ``banned_phrases`` (no
   default) and passes them through the validation context to the rule set's
   after validator, which rejects any string value containing one;
4. fail-closed: no phrases in the context, or an empty list, is a rejection, so
   an unscanned rule set cannot exist; ``model_construct``,
   ``model_copy(update=...)`` and the deprecated ``copy(update/include/exclude=...)``
   raise ``TypeError`` (:mod:`app.dirdef.guard`).

Two more guards (tech-architect type ruling 2026-11-14, Q1 and Q2):

* ``invalidation`` is a condition tree of the same type as ``condition`` -- no
  second expression grammar exists in ``app/`` -- and it reads exactly the set
  of fields its ``condition`` reads. That it is *the negation* of the condition
  is not judged at load time; tests prove it on a grid of boundary values;
* the rule set carries a required ``aggregation`` block (``theta``,
  ``min_completeness``; no default, no extra key). Both are floats (an int is
  taken as the same float, a bool or a string is refused), finite, ``theta > 0``
  and ``0 < min_completeness <= 1``. They are inside ``rules_logic_sha256``;
  ``theta: 2`` and ``theta: 2.0`` hash the same.

A rule's ``weight`` and a comparison's ``value`` use the same strict float type
(tech-architect 2026-11-15, question 4): ``true`` / ``false``, a string such as
``"1"`` and ``.inf`` / ``.nan`` are refused instead of being coerced. The landed
h3 / h5 files hold no such value, so their bytes and both ``rules_logic_sha256``
reference values are unchanged by this tightening (tests pin them).

:data:`OUTLOOK_RULE_FIELDS` is the field set of the frozen market h3 / h5
specification (freeze pack G3); the field formulas live in
``app/outlook/engine.py``.

Step 3 enumerates string values with :func:`app.dirdef.strings.string_values`,
the one enumeration in ``app/`` (shared with ``app/forecast/definitions.py``;
ADR-0027 N-128). A hit raises :class:`BannedPhraseError` inside validation; the
loader re-raises it as :class:`BannedPhraseRuleSetError`, so a banned-phrase
rejection is told apart from every other rejection by type.

``rules_logic_sha256`` hashes the validated rule set with the rule set
``version`` and the rules' :data:`RULE_TEXT_FIELDS` removed (D-10 point 1), so a
text-only PATCH bump keeps the hash and therefore the claim (D-10 point 2).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final, Literal, Self

import yaml
from pydantic import (
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    ValidationInfo,
    model_validator,
)

from app.dirdef.guard import GuardedModel
from app.dirdef.hashing import canonical_sha256
from app.dirdef.strings import string_values

#: Fields an outlook rule may read (freeze pack G3; formulas in ``app/outlook/engine.py``).
#: ``logret_past_3`` / ``logret_past_5`` are read only by the placeholder rule sets.
OUTLOOK_RULE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "close",
        "ma20",
        "ma60",
        "z_past_20",
        "z_past_3",
        "z_past_5",
        "vol_ratio_20_120",
        "logret_past_3",
        "logret_past_5",
    }
)

#: Rule fields outside ``rules_logic_sha256`` (D-10 point 1). quant may add
#: literal keys at the freeze; nothing is registered yet, so no stored hash moves.
RULE_TEXT_FIELDS: Final[frozenset[str]] = frozenset({"explanation", "counterargument"})

#: Validation context key the loader puts the banned phrases under.
BANNED_PHRASES_CONTEXT_KEY: Final = "banned_phrases"

ComparisonOp = Literal["gt", "gte", "lt", "lte", "eq", "ne", "abs_gt", "abs_lt"]
Direction = Literal["bullish", "bearish", "range"]


class RuleSetLoadError(ValueError):
    """A rule file failed the hash check, the YAML parse or validation."""


class BannedPhraseRuleSetError(RuleSetLoadError):
    """A rule file was rejected because a string value holds a banned phrase."""


class BannedPhraseError(ValueError):
    """Raised inside rule set validation when a string value holds a banned phrase."""


#: A finite float that is not a bool or a string; an int is taken as the same float.
#: The one strict float type of rule set numbers: the aggregation parameters and
#: each rule's ``weight`` and comparison ``value`` (tech-architect 2026-11-15 Q4).
AggregationNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class OutlookComparison(GuardedModel):
    """One leaf test: ``field <op> (value | ref)``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(min_length=1)
    op: ComparisonOp
    value: AggregationNumber | None = None
    ref: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _one_operand(self) -> Self:
        if (self.value is None) == (self.ref is None):
            raise ValueError("a condition needs exactly one of value or ref")
        return self


class OutlookAllOf(GuardedModel):
    """Every child condition holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    all: tuple[OutlookCondition, ...] = Field(min_length=1)


class OutlookAnyOf(GuardedModel):
    """At least one child condition holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    any: tuple[OutlookCondition, ...] = Field(min_length=1)


def _condition_kind(value: Any) -> str:
    """Pick the condition variant from the keys present (as the advice loader)."""
    if isinstance(value, OutlookAllOf) or (isinstance(value, Mapping) and "all" in value):
        return "all"
    if isinstance(value, OutlookAnyOf) or (isinstance(value, Mapping) and "any" in value):
        return "any"
    return "comparison"


OutlookCondition = Annotated[
    Annotated[OutlookAllOf, Tag("all")]
    | Annotated[OutlookAnyOf, Tag("any")]
    | Annotated[OutlookComparison, Tag("comparison")],
    Discriminator(_condition_kind),
]

OutlookAllOf.model_rebuild()
OutlookAnyOf.model_rebuild()


class OutlookRule(GuardedModel):
    """One outlook rule (ADR-0025 D-2 point 3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    direction: Direction
    weight: AggregationNumber = Field(gt=0.0, le=1.0)
    condition: OutlookCondition
    explanation: str = Field(min_length=1)
    counterargument: str = Field(min_length=1)
    #: The condition tree under which this rule's reason no longer holds (TA Q1).
    invalidation: OutlookCondition


class OutlookAggregation(GuardedModel):
    """ADR-0025 D-2.3 aggregation parameters of one rule set (TA G1 ruling, Q2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: theta_h: ``|W| < theta`` is ``range``.
    theta: AggregationNumber = Field(gt=0)
    #: Evaluable rules / all rules below this is ``insufficient``.
    min_completeness: AggregationNumber = Field(gt=0, le=1)


class OutlookRuleSet(GuardedModel):
    """A versioned outlook rule set for one horizon."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    aggregation: OutlookAggregation
    rules: tuple[OutlookRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _load_guards(self, info: ValidationInfo) -> Self:
        phrases = banned_phrases_from_context(info.context)
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"duplicate rule id {rule.id!r}")
            seen.add(rule.id)
        for rule in self.rules:
            for tree in (rule.condition, rule.invalidation):
                for path in condition_fields(tree):
                    if path not in OUTLOOK_RULE_FIELDS:
                        raise ValueError(
                            f"rule {rule.id!r} reads {path!r}, which is not in OUTLOOK_RULE_FIELDS"
                        )
        _scan_banned_phrases(self, phrases)
        for rule in self.rules:
            if set(condition_fields(rule.invalidation)) != set(condition_fields(rule.condition)):
                raise ValueError(
                    f"rule {rule.id!r}: the invalidation must read exactly the condition's fields"
                )
        return self


def banned_phrases_from_context(context: object) -> tuple[str, ...]:
    """The banned phrases carried by a validation context; anything else is rejected.

    The context must be a mapping whose :data:`BANNED_PHRASES_CONTEXT_KEY` holds a
    non-empty tuple of non-empty strings.
    """
    if not isinstance(context, Mapping):
        raise ValueError("validation context without banned phrases: rejected (fail-closed)")
    phrases = context.get(BANNED_PHRASES_CONTEXT_KEY)
    if not isinstance(phrases, tuple) or not phrases:
        raise ValueError("validation context without banned phrases: rejected (fail-closed)")
    if not all(isinstance(phrase, str) and phrase for phrase in phrases):
        raise ValueError("banned phrases must be non-empty strings")
    return phrases


def _scan_banned_phrases(ruleset: OutlookRuleSet, phrases: tuple[str, ...]) -> None:
    """Reject ``ruleset`` if any of its string values contains a phrase."""
    for text in string_values(ruleset):
        for phrase in phrases:
            if phrase in text:
                raise BannedPhraseError("a rule set string value holds a banned phrase")


def condition_fields(node: OutlookCondition) -> list[str]:
    """Every field a condition tree reads (``field`` and ``ref``), in traversal order."""
    if isinstance(node, OutlookComparison):
        return [node.field] + ([node.ref] if node.ref is not None else [])
    children = node.all if isinstance(node, OutlookAllOf) else node.any
    return [path for child in children for path in condition_fields(child)]


def rules_logic_sha256(ruleset: OutlookRuleSet) -> str:
    """The logic hash of ``ruleset`` (ADR-0027 D-10 point 1; single definition)."""
    payload = ruleset.model_dump(
        mode="json",
        exclude={"version": True, "rules": {"__all__": set(RULE_TEXT_FIELDS)}},
    )
    return canonical_sha256(payload)


def load_ruleset(
    data: bytes,
    *,
    rules_sha256: str,
    banned_phrases: Sequence[str],
) -> OutlookRuleSet:
    """Hash-check, parse and validate rule file bytes; raise on any failure.

    The steps run in order -- sha256 of the bytes against ``rules_sha256``, UTF-8
    decode and ``yaml.safe_load``, then ``model_validate`` with the banned
    phrases in the validation context -- and the first failure raises
    :class:`RuleSetLoadError`; nothing partial is returned.
    """
    if not isinstance(data, bytes):
        raise TypeError("rule file data must be bytes")
    if isinstance(banned_phrases, str):
        raise TypeError("banned_phrases must be a sequence of phrases, not one string")
    if hashlib.sha256(data).hexdigest() != rules_sha256:
        raise RuleSetLoadError("rule file bytes do not match the registered rules_sha256")
    phrases = tuple(banned_phrases)
    if not phrases:
        raise RuleSetLoadError("banned_phrases is empty: rejected (fail-closed)")
    try:
        raw = yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise RuleSetLoadError(f"rule file is not valid UTF-8 YAML ({type(exc).__name__})") from exc
    if not isinstance(raw, dict):
        raise RuleSetLoadError(f"rule file top level must be a mapping, got {type(raw).__name__}")
    try:
        return OutlookRuleSet.model_validate(raw, context={BANNED_PHRASES_CONTEXT_KEY: phrases})
    except ValidationError as exc:
        if any(
            isinstance(error.get("ctx", {}).get("error"), BannedPhraseError)
            for error in exc.errors()
        ):
            raise BannedPhraseRuleSetError(_format_errors(exc)) from exc
        raise RuleSetLoadError(_format_errors(exc)) from exc


def _format_errors(exc: ValidationError) -> str:
    lines = [
        f"{'.'.join(str(part) for part in error['loc']) or 'rule set'} -- {error['msg']}"
        for error in exc.errors()
    ]
    return "\n".join(dict.fromkeys(lines))
