"""Risk-approved fixed lines and templates of ``report status``, read from the approval records.

The tests compare the module constants with these, and render expected output
lines from these templates, so the wording is never typed twice (ADR-0030
supplement 8 point 6 (b), supplement 9 points 4-5).

Two shapes of record:

* ``approved_text``: exactly one ``<label>`text``` line (RC-230, RC-233);
* ``labelled_texts``: every ``定稿全文：`text``` line keyed by the line just
  before it -- in the RC-244～254 record that line is ``項目：<label>``; in the
  RC-237～243 record it is ``<label>：``. Each label occurs exactly once.

Templates hold placeholders: ``{name}`` is a value; ``{A／B}`` is a choice of
one alternative, braces and slash not printed (:func:`fill`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
REVIEWS: Final = REPO_ROOT / "work" / "reviews"

#: RC-230: the first line's original wording (superseded by RC-251, kept for the record).
F2_GAP_APPROVAL: Final = REVIEWS / "2026-11-19-report-status缺日加註定稿RC229至RC232-風控.md"
#: RC-233 / RC-234: the line after the review trigger lines.
REVIEW_GAP_APPROVAL: Final = REVIEWS / "2026-11-19-重審觸發缺日加註定稿RC233至RC236-風控.md"
REVIEW_GAP_LABEL: Final = "第二行定稿全文："
#: RC-237～RC-243: the F-2 first sentence lines (some of them superseded).
F2_LINES_APPROVAL: Final = REVIEWS / "2026-11-19-接線PR-F2視窗字面判定RC237至RC243-風控.md"
#: RC-244～RC-254: supplement 9 and the final F-2 wording.
F2_WORDING_APPROVAL: Final = REVIEWS / "2026-11-19-補充九判定與F2字面定稿RC244至RC254-風控.md"

#: The labels of F2_LINES_APPROVAL still in force, and the two that are not.
F2_LINES_IN_FORCE: Final = {
    "full": "RC-238 完整視窗（分母大於 0）",
    "short": "RC-239 視窗未滿",
    "no_weekday": "RC-242（suggested，之後辦；若要改「視窗未滿」那一行，用這個字面）",
}
F2_LINES_SUPERSEDED: Final = ("RC-237 段標題", "RC-238 完整視窗（分母為 0）")
#: The ``項目：`` labels of F2_WORDING_APPROVAL.
F2_WORDING_ITEMS: Final = {
    "title": "RC-248 段標題（取代 RC-237）",
    "first_heading": "RC-248 第一句小標題",
    "full_zero": "RC-247 第一句完整視窗分母為 0（取代 RC-238 分母為 0 那一行）",
    "second_heading": "RC-248 第二句小標題",
    "second": "RC-249 第二句有判定（G 大於 0）",
    "second_undecidable": "RC-249 第二句無從判定（G 為 0）",
    "action": "RC-250 行動句",
    "gap": "RC-251 第一行加註（修訂 RC-230）",
}

_FINAL_LINE: Final = re.compile(r"^定稿全文：`([^`]+)`$")
_PLACEHOLDER: Final = re.compile(r"\{([^{}]*)\}")


def approved_text(record: Path, label: str) -> str:
    """The backticked text of the record's one line starting with ``label``."""
    pattern = rf"^{re.escape(label)}`([^`]+)`$"
    found = re.findall(pattern, record.read_text(encoding="utf-8"), flags=re.M)
    assert len(found) == 1, f"{record.name}: expected one {label!r} line, found {len(found)}"
    return str(found[0])


def labelled_texts(record: Path, *, item_prefix: str | None) -> dict[str, str]:
    """Every ``定稿全文：`` text keyed by its label line (the line just before it)."""
    lines = record.read_text(encoding="utf-8").splitlines()
    found: dict[str, str] = {}
    for index, line in enumerate(lines):
        match = _FINAL_LINE.match(line)
        if match is None:
            continue
        assert index > 0, f"{record.name}: a final text without a label line"
        label = lines[index - 1].strip()
        if item_prefix is not None:
            assert label.startswith(item_prefix), f"{record.name}: unlabelled {line[:30]!r}"
            label = label.removeprefix(item_prefix)
        else:
            assert label.endswith("："), f"{record.name}: unlabelled {line[:30]!r}"
            label = label.removesuffix("：")
        assert label not in found, f"{record.name}: label {label!r} twice"
        found[label] = match.group(1)
    return found


def f2_wording() -> dict[str, str]:
    """The RC-244～254 texts by :data:`F2_WORDING_ITEMS` key; the record holds exactly those."""
    texts = labelled_texts(F2_WORDING_APPROVAL, item_prefix="項目：")
    assert set(texts) == set(F2_WORDING_ITEMS.values())
    return {key: texts[label] for key, label in F2_WORDING_ITEMS.items()}


def f2_lines() -> dict[str, str]:
    """The RC-237～243 texts still in force by :data:`F2_LINES_IN_FORCE` key."""
    texts = labelled_texts(F2_LINES_APPROVAL, item_prefix=None)
    assert set(texts) == {*F2_LINES_IN_FORCE.values(), *F2_LINES_SUPERSEDED}
    return {key: texts[label] for key, label in F2_LINES_IN_FORCE.items()}


def f2_superseded() -> list[str]:
    """The RC-237～243 texts that must not be used (the old title, the old denominator-0 line)."""
    texts = labelled_texts(F2_LINES_APPROVAL, item_prefix=None)
    return [texts[label] for label in F2_LINES_SUPERSEDED]


def f2_gap_line() -> str:
    """The first gap line in force: RC-251 (it revised RC-230)."""
    return f2_wording()["gap"]


def review_gap_line() -> str:
    return approved_text(REVIEW_GAP_APPROVAL, REVIEW_GAP_LABEL)


def fill(template: str, *choices: int, **values: object) -> str:
    """A template rendered: ``{A／B}`` takes the next choice (0 or 1), ``{name}`` its value."""
    picks = iter(choices)

    def one(match: re.Match[str]) -> str:
        name = match.group(1)
        if "／" in name:
            return name.split("／")[next(picks)]
        return str(values[name])

    text = _PLACEHOLDER.sub(one, template)
    assert next(picks, None) is None, "more choices than alternatives"
    return text


def placeholders(template: str) -> list[str]:
    return _PLACEHOLDER.findall(template)
