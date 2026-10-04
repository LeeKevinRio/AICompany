"""Wording gate for every rule-set string that reaches the main view.

Risk-compliance review 2026-10-03, BLOCKING 6: the rule set's ``invalidation``
text (and its sibling text fields) is rendered on the front end as backend
data. The front-end scan (``componentWordingScan``) only reads front-end
constants and ``loader.BANNED_PHRASES`` only holds the ten guarantee phrases,
so neither one reached this text. This module closes that gap in the backend
CI run:

1. Every display string of every rule in ``rules/default.yaml`` is scanned
   against the *complete* ``FRONTEND_FORBIDDEN_TERMS`` list, plus the bare
   "即時" rule of the front end's ``findBareRealtimeClaims`` ("非即時" passes).
2. The 12 ``invalidation`` texts reviewed with rule set 1.0.2 (unchanged in
   1.0.3 and 1.1.0) are pinned verbatim.

Single-source decision (option (b), not a shared JSON): the backend test parses
the array literal out of ``adviceWording.ts`` itself, so the TS file stays the
only copy of the list and cannot drift from what is scanned here. Guard tests
below make a silently broken parse fail loudly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.advice.loader import BANNED_PHRASES, DEFAULT_RULES_PATH

_STOCK_DESK_ROOT = Path(__file__).resolve().parents[2]
_ADVICE_WORDING_TS = _STOCK_DESK_ROOT / "frontend" / "app" / "lib" / "adviceWording.ts"
_SHARED_FORBIDDEN_TERMS_JSON = _STOCK_DESK_ROOT / "shared" / "forbidden-terms.json"

_LIST_NAME = "FRONTEND_FORBIDDEN_TERMS"

#: Rule fields rendered on screen (``name`` / ``explanation`` / ``counterargument``
#: / ``invalidation``; ``rationale`` does not exist in this rule set's schema).
DISPLAY_FIELDS: tuple[str, ...] = ("name", "explanation", "counterargument", "invalidation")

#: Every key a rule may carry. A new key fails ``test_rule_keys_are_all_accounted_for``
#: so a new string field cannot reach the screen without being added to the scan.
_NON_DISPLAY_FIELDS: frozenset[str] = frozenset({"id", "action", "weight", "condition"})

#: The 11 real-time terms added to the front-end list on 2026-10-03
#: (ADR-0014 P13, risk-approved). Pinned so a parse that silently drops the tail
#: of the array cannot pass.
_REALTIME_TERMS_ADDED_2026_10_03: tuple[str, ...] = (
    "即時價",
    "即時行情",
    "即時股價",
    "即時更新",
    "即時顯示",
    "即時同步",
    "實時",
    "最新成交",
    "及時",
    "零延遲",
    "無延遲",
)

_REVIEW_MESSAGE = "改字需重送風控逐字審"

#: Reviewed with rule set 1.0.2, unchanged in 1.0.3 and 1.1.0, verbatim. 1.1.0
#: moved the two drawdown rules' *conditions* to ``drawdown.current`` (CEO D1,
#: 2026-10-04) precisely so that their pinned invalidations below, which already
#: speak of the drawdown in force now, describe what the program checks. Changing any
#: character must go back to risk-compliance-officer for a word-by-word review
#: (see ``_REVIEW_MESSAGE``).
EXPECTED_INVALIDATIONS: dict[str, str] = {
    "uptrend_ma_stack": "收盤價跌破 60 日均線，或 5 日均線下彎並跌破 20 日均線。",
    "macd_histogram_positive": "柱狀圖翻為負值，或收盤價跌破 20 日均線。",
    "rsi_oversold_with_trend": "收盤價跌破 60 日均線，或 RSI 續創新低並伴隨成交量放大的下跌。",
    "downtrend_ma_stack": "5 日均線向上穿越 20 日均線，且收盤價站回 60 日均線之上。",
    "price_below_ma60": "收盤價重新站上 60 日均線並延續三個交易日以上。",
    "rsi_overbought": "RSI 回落至 50 與 70 之間，且收盤價維持在 20 日均線之上。",
    "kd_high_level_weakening": "K 值重新向上穿越 D 值，或 K 值回落至 50 以下後止跌。",
    "bollinger_upper_breach": "布林 %B 回落至 0.8 以下，或通道寬度明顯收斂。",
    "drawdown_protection": "價格回到前波高點附近，或回撤幅度收斂至 -10% 以內。",
    "deep_drawdown_stop": "回撤幅度收斂至 -20% 以內，且收盤價站回 60 日均線之上。",
    "volume_spike_watch": "z 分數回到正負 2 以內，量能回到近月均量附近。",
    "concentration_watch": "佔比因組合調整或市值變化回落至 12% 以下。",
}


def _strip_ts_comments_and_collect_strings(source: str) -> list[str]:
    """Return the double-quoted string literals of ``source`` in order, ignoring
    ``//`` and ``/* */`` comments (the list's own comments contain quotes)."""
    strings: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if source.startswith("//", i):
            newline = source.find("\n", i)
            i = n if newline == -1 else newline
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif ch == '"':
            j = i + 1
            while j < n and source[j] != '"':
                j += 2 if source[j] == "\\" else 1
            if j >= n:
                raise AssertionError(f"unterminated string literal in {_LIST_NAME}")
            # A JSON string literal and a TS double-quoted literal share escapes
            # for everything this list uses.
            strings.append(json.loads(source[i : j + 1]))
            i = j + 1
        else:
            i += 1
    return strings


def load_frontend_forbidden_terms() -> tuple[str, ...]:
    text = _ADVICE_WORDING_TS.read_text(encoding="utf-8")
    match = re.search(rf"export\s+const\s+{_LIST_NAME}\s*:\s*readonly\s+string\[\]\s*=\s*\[", text)
    assert match is not None, f"{_LIST_NAME} declaration not found in {_ADVICE_WORDING_TS}"
    start = match.end()
    # Find the closing bracket at nesting depth 0, skipping comments and strings.
    depth = 1
    i = start
    while i < len(text) and depth:
        if text.startswith("//", i):
            newline = text.find("\n", i)
            i = len(text) if newline == -1 else newline
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end == -1 else end + 2
        elif text[i] == '"':
            j = i + 1
            while j < len(text) and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            i = j + 1
        elif text[i] in ("'", "`", "."):
            # Only double-quoted literals are parsed; a single-quoted, template
            # or spread entry would be silently dropped, so fail loudly instead.
            raise AssertionError(
                f"{_LIST_NAME} contains a non-double-quoted entry near offset {i}; "
                "this parser only understands double-quoted string literals"
            )
        else:
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
            i += 1
    assert depth == 0, f"closing bracket of {_LIST_NAME} not found"
    return tuple(_strip_ts_comments_and_collect_strings(text[start : i - 1]))


FRONTEND_FORBIDDEN_TERMS: tuple[str, ...] = load_frontend_forbidden_terms()


def find_bare_realtime_claims(text: str) -> list[str]:
    """Port of the front end's ``findBareRealtimeClaims`` (wordingScanHelpers.ts):
    every "即時" not immediately preceded by "非" is a capability claim."""
    violations: list[str] = []
    for match in re.finditer("即時", text):
        preceding = text[max(0, match.start() - 1) : match.start()]
        if preceding != "非":
            violations.append(text[max(0, match.start() - 10) : match.start() + 12])
    return violations


def _load_rules() -> list[dict[str, Any]]:
    # Read the YAML directly rather than through the loader, so a loader change
    # (or its own phrase list) cannot mask what the file actually contains.
    payload = yaml.safe_load(DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
    rules = payload["rules"]
    assert isinstance(rules, list) and rules
    return rules


def _display_texts() -> list[tuple[str, str, str]]:
    """(rule id, field, text) for every display string of every rule."""
    return [
        (rule["id"], field, str(rule[field])) for rule in _load_rules() for field in DISPLAY_FIELDS
    ]


# ---------------------------------------------------------------------------
# Guards on the scan itself.
# ---------------------------------------------------------------------------


def test_parsed_forbidden_term_list_is_complete() -> None:
    terms = FRONTEND_FORBIDDEN_TERMS
    # The list held 81 entries when this gate was written; a collapse means
    # the parser broke, not that the list was legitimately pruned.
    assert len(terms) >= 81, f"parsed only {len(terms)} terms from {_ADVICE_WORDING_TS}"
    assert len(set(terms)) == len(terms), "duplicate entries in the parsed term list"
    assert all(term for term in terms)
    # First and last entries of the array pin both ends of the parse.
    assert terms[0] == "保證"
    assert terms[-1] == "可留意"


@pytest.mark.parametrize("term", _REALTIME_TERMS_ADDED_2026_10_03)
def test_frontend_list_contains_realtime_terms_added_on_2026_10_03(term: str) -> None:
    assert term in FRONTEND_FORBIDDEN_TERMS, (
        f"「{term}」不在 {_LIST_NAME}：前端清單被縮減或解析失敗，須與風控確認"
    )


def test_shared_json_terms_are_subset_of_frontend_list() -> None:
    payload = json.loads(_SHARED_FORBIDDEN_TERMS_JSON.read_text(encoding="utf-8"))
    shared = [*payload["guarantee"], *payload["price_target"]]
    missing = [term for term in shared if term not in FRONTEND_FORBIDDEN_TERMS]
    assert not missing, f"shared/forbidden-terms.json 有而前端清單缺少：{missing}"


def test_loader_banned_phrases_are_subset_of_frontend_list() -> None:
    missing = [term for term in BANNED_PHRASES if term not in FRONTEND_FORBIDDEN_TERMS]
    assert not missing, f"loader.BANNED_PHRASES 有而前端清單缺少：{missing}"


def test_bare_realtime_matcher_mirrors_the_frontend_rule() -> None:
    assert find_bare_realtime_claims("本產品非即時報價") == []
    assert len(find_bare_realtime_claims("提供即時資訊")) == 1
    assert len(find_bare_realtime_claims("非即時，但即時")) == 1
    assert len(find_bare_realtime_claims("即時即時")) == 2
    assert find_bare_realtime_claims("") == []


def test_rule_keys_are_all_accounted_for() -> None:
    known = set(DISPLAY_FIELDS) | _NON_DISPLAY_FIELDS
    for rule in _load_rules():
        unknown = set(rule) - known
        assert not unknown, (
            f"{rule['id']} 出現未納入掃描的新欄位 {sorted(unknown)}：若會進畫面，"
            "請加入 DISPLAY_FIELDS，否則加入 _NON_DISPLAY_FIELDS 並說明"
        )
        for field in DISPLAY_FIELDS:
            assert isinstance(rule.get(field), str) and rule[field], f"{rule['id']}.{field}"


# ---------------------------------------------------------------------------
# The scans.
# ---------------------------------------------------------------------------


def test_scan_covers_all_display_fields_of_all_rules() -> None:
    assert len(_load_rules()) == 12
    assert len(_display_texts()) == 12 * len(DISPLAY_FIELDS)


def test_display_texts_have_no_forbidden_terms() -> None:
    hits = [
        f"{rule_id}.{field} 含禁用詞「{term}」"
        for rule_id, field, text in _display_texts()
        for term in FRONTEND_FORBIDDEN_TERMS
        if term.casefold() in text.casefold()
    ]
    assert not hits, "規則集顯示文字命中前端禁用詞清單：\n" + "\n".join(hits)


def test_display_texts_have_no_bare_realtime_claims() -> None:
    hits = [
        f"{rule_id}.{field} 出現裸「即時」：{context!r}"
        for rule_id, field, text in _display_texts()
        for context in find_bare_realtime_claims(text)
    ]
    assert not hits, "「即時」只能以「非即時」否定形式出現：\n" + "\n".join(hits)


def test_invalidations_have_no_forbidden_terms_or_bare_realtime() -> None:
    """Redundant with the all-fields scans on purpose: the invalidation text is
    the one the main view renders verbatim, so it keeps its own named gate."""
    for rule in _load_rules():
        text = str(rule["invalidation"])
        for term in FRONTEND_FORBIDDEN_TERMS:
            assert term.casefold() not in text.casefold(), (
                f"{rule['id']}.invalidation 含禁用詞「{term}」"
            )
        assert find_bare_realtime_claims(text) == [], f"{rule['id']}.invalidation 含裸「即時」"


# ---------------------------------------------------------------------------
# Verbatim pin of the invalidation text reviewed with rule set 1.0.2 (unchanged in
# 1.0.3 and 1.1.0).
# ---------------------------------------------------------------------------


def test_invalidation_rule_ids_match_the_reviewed_set() -> None:
    actual_ids = [rule["id"] for rule in _load_rules()]
    assert actual_ids == list(EXPECTED_INVALIDATIONS), (
        f"規則 id 清單與風控審過的 1.0.2（1.0.3、1.1.0 未變動）不同（新增、刪除或改序）。"
        f"{_REVIEW_MESSAGE}"
    )


@pytest.mark.parametrize("rule_id", list(EXPECTED_INVALIDATIONS))
def test_invalidation_text_is_verbatim_as_reviewed(rule_id: str) -> None:
    actual = {rule["id"]: rule["invalidation"] for rule in _load_rules()}
    assert actual.get(rule_id) == EXPECTED_INVALIDATIONS[rule_id], (
        f"{rule_id}.invalidation 與風控審過的 1.0.2（1.0.3、1.1.0 未變動）原文不同。"
        f"{_REVIEW_MESSAGE}。\n"
        f"expected: {EXPECTED_INVALIDATIONS[rule_id]!r}\n"
        f"actual:   {actual.get(rule_id)!r}"
    )
