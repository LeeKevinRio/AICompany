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
    "SIGMA_WINDOW": 60,
    "SIGMA_MIN_VALID": 55,
    "SIGMA_FLOOR": 0.001,
    "B2_WINDOW": 250,
    "B2_MIN_REALIZED": 120,
    "MAJORITY_TIE_ORDER": ("range", "bullish", "bearish"),
    "NEFF_BLOCK_LEN3": 3,
    "NEFF_BLOCK_LEN5": 5,
    "SEASON_MONTHS": (6, 7, 8, 9),
    "MARKET_PRICE_INDEX_DEVIATION": "fixture deviation text",
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

#: ``c8_decision_ref`` / ``c8_decision_sha256`` stand-ins for tests only. The real
#: values come with the C-8 decision record, which the CG-2 registration batch lands
#: (freeze pack G7 / G8); no ``dirdef-v1.0`` object exists in ``app/`` before that.
C8_TEST_PLACEHOLDERS: Final[Mapping[str, Any]] = {
    "c8_decision_ref": "work/decisions/c8-pending-cg2.md",
    "c8_decision_sha256": "0" * 64,
}

#: ``dirdef-v1.0`` as tabled by freeze pack G7 (round 2; RC-133, RC-134, RC-142
#: wording), word for word, with the two C-8 provenance fields replaced by the
#: test stand-ins above. Values only; it is not registered anywhere.
DIRDEF_V1_0_G7: Final[Mapping[str, Any]] = {
    "definition_version": "dirdef-v1.0",
    "description": (
        "方向判斷定義 dirdef-v1.0：只供大盤 h3、h5 前瞻 claim 使用"
        "（ADR-0030 D-1、D-6 CG-2）；常數依事先宣告 v0.32。"
    ),
    "K3": 0.43,
    "K5": 0.43,
    "EPS": 1e-12,
    "SIGMA_WINDOW": 60,
    "SIGMA_MIN_VALID": 55,
    "SIGMA_FLOOR": 0.001,
    "B2_WINDOW": 250,
    "B2_MIN_REALIZED": 120,
    "MAJORITY_TIE_ORDER": ("range", "bullish", "bearish"),
    "NEFF_BLOCK_LEN3": 3,
    "NEFF_BLOCK_LEN5": 5,
    "SEASON_MONTHS": (6, 7, 8, 9),
    "MARKET_PRICE_INDEX_DEVIATION": (
        "大盤（臺灣加權股價指數）的標籤與特徵以價格指數點數計算，不含股利，不是還原價；"
        "此項偏離 PV-7「價格基準：還原價」，經風控 R-1（2026-10-16）附條件核可，只限大盤。"
        "除息旺季（6～9 月）標籤與特徵都會偏空，見事先宣告 §1.1 偏誤揭露。"
    ),
    "f2_variant": "F2-B",
    **C8_TEST_PLACEHOLDERS,
    "EXIT_DEADLINE_N_MARKET_SYMBOL": 150,
    "EXIT_DEADLINE_N_SECTOR": 250,
    "CHECKPOINTS_MARKET_SYMBOL": (30, 60, 100, 150, 250, 500),
    "CHECKPOINTS_SECTOR": (150, 250, 500),
    "REPLAY_CHECKPOINT_COUNT": 1,
    "ALPHA_FAMILY": 0.05,
    "M_EFF_FLOOR": 8,
    "MIN_MEAN_RECALL": 1 / 3,
    "MIN_COVERAGE": 0.80,
    "VOID_RATE_W_THRESHOLD": 0.05,
    "BOOTSTRAP_RESAMPLES": 10000,
    "BOOTSTRAP_BLOCK_LEN": 4,
    "BOOTSTRAP_BLOCK_LEN_ALTERNATIVES": (2, 8),
    "BASKET_EXCLUSION_REASON_ORDER": (
        "dividend_factor_unusable",
        "split_or_reduction_suspected",
        "t_plus_h_bar_unavailable",
    ),
    "SPLIT_SUSPECT_ABS_RETURN": 0.11,
    "BASKET_MIN_MEMBER_WEIGHT": 0.90,
}

#: The G7 "位置" column: D-NL rows (every other row is D, a logic field).
G7_NON_LOGIC_ROWS: Final = frozenset(
    {
        "definition_version",
        "description",
        "MARKET_PRICE_INDEX_DEVIATION",
        "c8_decision_ref",
        "c8_decision_sha256",
    }
)


def dirdef_v1_0() -> DirectionDefinition:
    """The G7 ``dirdef-v1.0`` values as a definition object (test stand-in; not registered)."""
    return DirectionDefinition.model_validate(dict(DIRDEF_V1_0_G7))


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
        # The negation of the condition, as a tree over the same fields (TA Q1).
        "invalidation": {
            "any": [
                {"field": "index.ret_5d", "op": "lte", "value": 0.0},
                {"field": "index.ma20_gap", "op": "lte", "ref": "breadth.adv_ratio"},
            ]
        },
    }
    rule.update(overrides)
    return rule


#: A valid ``aggregation`` block (fixture values, not the frozen theta).
AGGREGATION: Final[Mapping[str, Any]] = {"theta": 1.0, "min_completeness": 1.0}


def ruleset_data(
    *rules: dict[str, Any],
    version: str = "1.0.0",
    aggregation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "version": version,
        "aggregation": dict(AGGREGATION if aggregation is None else aggregation),
        "rules": list(rules) or [rule_data()],
    }


def ruleset_bytes(data: Mapping[str, Any]) -> bytes:
    return yaml.safe_dump(dict(data), allow_unicode=True, sort_keys=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
