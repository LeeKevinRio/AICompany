"""Load and validate a rule file into a typed, immutable :class:`RuleSet`.

The rule set is data, so the schema has to be strict enough that a malformed
file fails at load time instead of quietly producing a rule that never fires:

* ``extra="forbid"`` everywhere -- a misspelled key is an error, not a no-op.
* Every ``field``/``ref`` in a condition must be in
  :data:`app.advice.context.KNOWN_FIELDS`.
* A comparison carries exactly one right-hand side: a literal ``value`` or a
  ``ref`` to another field.
* Rule ids are unique and the file declares a semver ``version``.
* :data:`BANNED_PHRASES` are rejected in rule text. Guarantee-flavoured wording
  is a compliance red line, so the guard lives in the loader (every consumer
  gets it) rather than only in a test.

Validation errors are reported as ``<filename>：規則 <id> 的 <欄位> -- <原因>``
so a rule author can find the offending rule without decoding a pydantic dump.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    model_validator,
)

from app.advice.context import KNOWN_FIELDS

#: The rule file shipped with the product.
DEFAULT_RULES_PATH = Path(__file__).parent / "rules" / "default.yaml"

#: Wording that may never appear in a rule's text (compliance red line).
BANNED_PHRASES: tuple[str, ...] = (
    "保證",
    "必漲",
    "必賺",
    "必跌",
    "穩賺",
    "穩賠",
    "一定會",
    "包賺",
    "零風險",
    "無風險",
)

_TEXT_FIELDS = ("name", "explanation", "counterargument", "invalidation")

Action = Literal["add", "hold", "reduce", "stop_loss", "take_profit"]
ComparisonOp = Literal["gt", "gte", "lt", "lte", "eq", "ne", "abs_gt", "abs_lt"]


class RuleSetError(ValueError):
    """A rule file could not be read, parsed, or validated."""


class Comparison(BaseModel):
    """One leaf test: ``field <op> (value | ref)``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    op: ComparisonOp
    #: Literal right-hand side.
    value: float | None = None
    #: Right-hand side read from another context field (e.g. ``ma60.last``).
    ref: str | None = None

    @model_validator(mode="after")
    def _check_operands(self) -> Comparison:
        if (self.value is None) == (self.ref is None):
            raise ValueError("condition 需要 value 或 ref 其中一項，且只能擇一")
        for path in (self.field, self.ref):
            if path is not None and path not in KNOWN_FIELDS:
                raise ValueError(f"未知的欄位 {path!r}，可用欄位定義於 app/advice/context.py")
        return self


class AllOf(BaseModel):
    """Every child condition holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    all: list[ConditionNode] = Field(min_length=1)


class AnyOf(BaseModel):
    """At least one child condition holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    any: list[ConditionNode] = Field(min_length=1)


def _condition_kind(value: Any) -> str:
    """Pick the condition variant from the keys present.

    Without this the union would try all three variants and report three
    unrelated failures for one typo; tagging on ``all``/``any`` keeps the error
    pointing at the node the author actually wrote.
    """
    if isinstance(value, AllOf) or (isinstance(value, Mapping) and "all" in value):
        return "all"
    if isinstance(value, AnyOf) or (isinstance(value, Mapping) and "any" in value):
        return "any"
    return "comparison"


ConditionNode = Annotated[
    Annotated[AllOf, Tag("all")]
    | Annotated[AnyOf, Tag("any")]
    | Annotated[Comparison, Tag("comparison")],
    Discriminator(_condition_kind),
]

# The group nodes reference the union recursively; resolve the forward refs now
# so a malformed file fails inside ``load_rules`` rather than on first use.
AllOf.model_rebuild()
AnyOf.model_rebuild()


class Rule(BaseModel):
    """One rule: when ``condition`` holds, ``action`` is proposed with ``weight``.

    ``explanation`` / ``counterargument`` / ``invalidation`` are mandatory and
    non-empty: a rule that cannot state its evidence, the opposing view, and
    what would make it wrong does not belong in the set.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    condition: ConditionNode
    action: Action
    weight: float = Field(gt=0.0, le=1.0)
    explanation: str = Field(min_length=1)
    counterargument: str = Field(min_length=1)
    invalidation: str = Field(min_length=1)

    @model_validator(mode="after")
    def _reject_banned_phrases(self) -> Rule:
        for name in _TEXT_FIELDS:
            text = str(getattr(self, name))
            for phrase in BANNED_PHRASES:
                if phrase in text:
                    raise ValueError(f"{name} 出現不得使用的字眼「{phrase}」")
        return self


class RuleSet(BaseModel):
    """A versioned collection of rules."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    updated_at: date
    rules: list[Rule] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> RuleSet:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"規則 id 重複：{rule.id}")
            seen.add(rule.id)
        return self

    def rule_ids(self) -> list[str]:
        """Rule ids in file order."""
        return [rule.id for rule in self.rules]


def condition_fields(node: ConditionNode) -> list[str]:
    """Every context field a condition tree reads, in traversal order."""
    if isinstance(node, Comparison):
        return [node.field] + ([node.ref] if node.ref is not None else [])
    children = node.all if isinstance(node, AllOf) else node.any
    return [path for child in children for path in condition_fields(child)]


def load_rules(path: Path) -> RuleSet:
    """Read and validate a YAML rule file. Raises :class:`RuleSetError`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuleSetError(f"{path.name}：規則檔無法讀取（{exc}）") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RuleSetError(f"{path.name}：YAML 解析失敗（{exc}）") from exc
    if not isinstance(raw, dict):
        raise RuleSetError(
            f"{path.name}：規則檔最外層需要是 mapping，實際取得 {type(raw).__name__}"
        )
    try:
        return RuleSet.model_validate(raw)
    except ValidationError as exc:
        raise RuleSetError(_format_errors(path, raw, exc)) from exc


@lru_cache(maxsize=1)
def load_default_rules() -> RuleSet:
    """The shipped rule set, parsed once per process."""
    return load_rules(DEFAULT_RULES_PATH)


def _rule_id_at(raw: dict[str, Any], index: int) -> str:
    """Best-effort rule id for an error location, for a readable message."""
    rules = raw.get("rules")
    if isinstance(rules, Sequence) and not isinstance(rules, str) and index < len(rules):
        entry = rules[index]
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            return str(entry["id"])
    return f"第 {index + 1} 條（未提供 id）"


def _format_errors(path: Path, raw: dict[str, Any], exc: ValidationError) -> str:
    """Turn a pydantic error dump into per-rule Traditional Chinese messages."""
    lines: list[str] = []
    for error in exc.errors():
        loc = error["loc"]
        message = error["msg"]
        if len(loc) >= 2 and loc[0] == "rules" and isinstance(loc[1], int):
            rule_id = _rule_id_at(raw, loc[1])
            field_path = ".".join(str(part) for part in loc[2:]) or "整體"
            lines.append(f"{path.name}：規則 {rule_id} 的 {field_path} -- {message}")
        else:
            location = ".".join(str(part) for part in loc) or "整體"
            lines.append(f"{path.name}：{location} -- {message}")
    unique = list(dict.fromkeys(lines))
    return "\n".join(unique)
