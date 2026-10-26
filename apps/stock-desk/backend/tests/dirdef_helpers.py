"""Fixtures for the ``app.dirdef`` tests (ADR-0027 B2).

The numbers below are test fixtures, not dirdef values: nothing is registered
and quant freezes the real constants at G-3.

Seams (FL-78 (j)(k)(l)): the outlook rule field list is replaced through
:data:`RULE_FIELDS_SEAM` (``app.dirdef.rules.OUTLOOK_RULE_FIELDS``, read when
the validator runs); ``app/forecast/definitions.py`` is driven through the
names in :data:`DEFINITIONS_SEAMS`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, Final

import yaml

from app.dirdef.definition import DirectionDefinition

#: ``app.dirdef.rules`` attribute replaced by the substitute field list.
RULE_FIELDS_SEAM: Final = "OUTLOOK_RULE_FIELDS"

#: ``app.forecast.definitions`` attributes replaced in the tests.
DEFINITIONS_SEAMS: Final = (
    "PUBLISHED_DIRECTION_DEFINITIONS",
    "PUBLISHED_RULESETS",
    "_read_rules_bytes",
    "_DEFINITION_CACHE",
    "_RULESET_CACHE",
)

#: Substitute outlook rule fields for the positive fixtures.
SUBSTITUTE_FIELDS: Final = frozenset({"index.ret_5d", "index.ma20_gap", "breadth.adv_ratio"})

_DEFINITION: Final[Mapping[str, Any]] = {
    "definition_version": "dirdef-v1.0",
    "description": "fixture definition for tests",
    "K3": 0.43,
    "K5": 0.43,
    "EPS": 1e-12,
    "SIGMA_MIN_VALID": 55,
    "SIGMA_FLOOR": 0.001,
    "BASKET_EXCLUSION_REASON_ORDER": (
        "dividend_factor_unusable",
        "split_or_reduction_suspected",
        "t_plus_h_bar_unavailable",
    ),
    "SPLIT_SUSPECT_ABS_RETURN": 0.11,
    "BASKET_MIN_MEMBER_WEIGHT": 0.9,
    "f2_variant": "F2-B",
    "c8_decision_ref": "work/decisions/c8.md",
    "c8_decision_sha256": "0" * 64,
    "EXIT_DEADLINE_N_MARKET_SYMBOL": 150,
    "EXIT_DEADLINE_N_SECTOR": 250,
    "CHECKPOINTS_MARKET_SYMBOL": (30, 60, 100, 150, 250, 500),
    "CHECKPOINTS_SECTOR": (150, 250, 500),
    "REPLAY_CHECKPOINT_COUNT": 1,
    "ALPHA_FAMILY": 0.05,
    "M_EFF_FLOOR": 8,
    "MIN_MEAN_RECALL": 1 / 3,
    "MIN_COVERAGE": 0.8,
    "VOID_RATE_W_THRESHOLD": 0.05,
    "BOOTSTRAP_RESAMPLES": 10_000,
    "BOOTSTRAP_BLOCK_LEN": 4,
    "BOOTSTRAP_BLOCK_LEN_ALTERNATIVES": (2, 8),
}


def definition_data(**overrides: Any) -> dict[str, Any]:
    """A valid ``DirectionDefinition`` input, with ``overrides`` applied."""
    data = dict(_DEFINITION)
    data.update(overrides)
    return data


def make_definition(**overrides: Any) -> DirectionDefinition:
    return DirectionDefinition.model_validate(definition_data(**overrides))


def rule_data(**overrides: Any) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "id": "index_momentum",
        "name": "index momentum",
        "direction": "bullish",
        "weight": 0.5,
        "condition": {
            "all": [
                {"field": "index.ret_5d", "op": "gt", "value": 0.0},
                {"any": [{"field": "index.ma20_gap", "op": "gt", "ref": "breadth.adv_ratio"}]},
            ]
        },
        "explanation": "the index rose over five sessions",
        "counterargument": "short rises often fade",
        "invalidation": "index.ret_5d below zero",
    }
    rule.update(overrides)
    return rule


def ruleset_data(*rules: dict[str, Any], version: str = "1.0.0") -> dict[str, Any]:
    return {"version": version, "rules": list(rules) or [rule_data()]}


def ruleset_bytes(data: Mapping[str, Any]) -> bytes:
    return yaml.safe_dump(dict(data), allow_unicode=True, sort_keys=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
