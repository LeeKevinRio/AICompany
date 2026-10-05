"""Verbatim pin of the two drawdown rules' wording in rule set 1.1.0 (R3).

Rule set 1.1.0 moved ``drawdown_protection`` and ``deep_drawdown_stop`` from
``drawdown.max_drawdown`` (the window's historical extreme) to
``drawdown.current`` (CEO D1, 2026-10-04). Their ``name`` / ``explanation`` /
``counterargument`` and the ``drawdown.current`` field label were rewritten and
approved word by word by risk-compliance-officer, see
``work/reviews/2026-10-04-回撤規則-1.1.0-字面-風控審查.md`` (核可字面總表).

Every character below -- full-width punctuation and half-width spaces
included -- is the approved text. Changing any of it must go back to
risk-compliance-officer for a word-by-word review. The two ``invalidation``
texts are pinned separately in ``test_rules_invalidation_wording.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from app.advice.context import FIELD_LABELS, describe_field
from app.advice.loader import DEFAULT_RULES_PATH, Comparison, load_default_rules

_REVIEW_MESSAGE = "改字需重送風控逐字審（work/reviews/2026-10-04-回撤規則-1.1.0-字面-風控審查.md）"

#: (rule id, field) -> approved text, verbatim from the review's 核可字面總表.
EXPECTED_DRAWDOWN_WORDING: dict[tuple[str, str], str] = {
    ("drawdown_protection", "name"): "目前回撤深於兩成",
    ("drawdown_protection", "explanation"): (
        "此標的最新收盤價，相對觀察區間內的最高收盤價，回撤幅度已深於 -20%。"
        "該數字描述價格自身的回落幅度，與此部位的未實現損益無關。"
    ),
    ("drawdown_protection", "counterargument"): (
        "目前回撤是截至最新收盤已發生的價格統計；"
        "若此部位帳面上有虧損，在低位降低部位會把帳面虧損轉為實現虧損。"
    ),
    ("deep_drawdown_stop", "name"): "目前回撤深於三成",
    ("deep_drawdown_stop", "explanation"): (
        "此標的最新收盤價，相對觀察區間內的最高收盤價，回撤幅度已深於本規則設定的 -30% 門檻。"
        "該數字僅描述價格自身的回落幅度，與此部位的未實現損益無關。"
    ),
    ("deep_drawdown_stop", "counterargument"): "若價格之後反彈，執行停損會放棄該段反彈的空間。",
}

#: Approved label for the field both rules now read.
EXPECTED_CURRENT_DRAWDOWN_LABEL = "最新收盤價相對區間最高收盤價的回撤"

DRAWDOWN_RULE_IDS: tuple[str, ...] = ("drawdown_protection", "deep_drawdown_stop")

#: Words the explanations must not carry any more: the rules no longer read the
#: window's historical extreme, and "已達" read as ">=" while the condition is a
#: strict "<" (approved wording uses "已深於").
FORBIDDEN_IN_EXPLANATION: tuple[str, ...] = ("歷史", "最大回撤", "已達")

_PIN_IDS = [f"{rule_id}.{field}" for rule_id, field in EXPECTED_DRAWDOWN_WORDING]


def _raw_rules_by_id() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
    return {rule["id"]: rule for rule in data["rules"]}


def test_rule_set_version_is_1_1_0() -> None:
    # The pins below belong to 1.1.0; a version bump must re-check them.
    assert load_default_rules().version == "1.1.0"


@pytest.mark.parametrize(
    ("rule_id", "field", "expected"),
    [(rule_id, field, text) for (rule_id, field), text in EXPECTED_DRAWDOWN_WORDING.items()],
    ids=_PIN_IDS,
)
def test_drawdown_rule_wording_is_pinned_in_yaml(rule_id: str, field: str, expected: str) -> None:
    rule = _raw_rules_by_id()[rule_id]
    assert rule[field] == expected, f"{rule_id}.{field}：{_REVIEW_MESSAGE}"


@pytest.mark.parametrize(
    ("rule_id", "field", "expected"),
    [(rule_id, field, text) for (rule_id, field), text in EXPECTED_DRAWDOWN_WORDING.items()],
    ids=_PIN_IDS,
)
def test_drawdown_rule_wording_is_pinned_in_loaded_rules(
    rule_id: str, field: str, expected: str
) -> None:
    # Same text after the loader's validation, i.e. what the engine renders.
    rules = {rule.id: rule for rule in load_default_rules().rules}
    assert getattr(rules[rule_id], field) == expected, f"{rule_id}.{field}：{_REVIEW_MESSAGE}"


def test_drawdown_rules_read_the_current_drawdown() -> None:
    # The wording above describes ``drawdown.current``; pin the pairing.
    rules = {rule.id: rule for rule in load_default_rules().rules}
    for rule_id in DRAWDOWN_RULE_IDS:
        condition = rules[rule_id].condition
        assert isinstance(condition, Comparison), rule_id
        assert condition.field == "drawdown.current", rule_id


def test_current_drawdown_field_label_is_pinned() -> None:
    assert FIELD_LABELS["drawdown.current"] == EXPECTED_CURRENT_DRAWDOWN_LABEL, _REVIEW_MESSAGE
    assert describe_field("drawdown.current") == (
        f"drawdown.current（{EXPECTED_CURRENT_DRAWDOWN_LABEL}）"
    )


@pytest.mark.parametrize("term", FORBIDDEN_IN_EXPLANATION)
@pytest.mark.parametrize("rule_id", DRAWDOWN_RULE_IDS)
def test_drawdown_explanation_avoids_historical_extreme_wording(rule_id: str, term: str) -> None:
    rules = {rule.id: rule for rule in load_default_rules().rules}
    assert term not in rules[rule_id].explanation, f"{rule_id}：{term}"
