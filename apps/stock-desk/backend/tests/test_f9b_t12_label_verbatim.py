"""T-12, checked by machine: the ruling's line, the frontend label, its test.

The frontend label for ``symbol_or_unit_rejected`` is a literal in
``frontend/app/lib/valuationWording.ts`` and its vitest pins a written-out
copy, because the frontend tests do not read ``work/``. This test reads all
three -- the ruling's own line (裁定二 L29, T-12 主案; 風控 F9W-19), the label in
the frontend source and the string in the frontend test -- and asserts they
are the same text (qa-reviewer F-9b 第二段勾核, suggested on point 5).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
RULING = "work/reviews/2026-10-12-F-9-第二批字面逐字審-F9W-17至F9W-29-風控.md"
FRONTEND_LIB = REPO / "apps" / "stock-desk" / "frontend" / "app" / "lib"

_LABEL = re.compile(r'^\s*symbol_or_unit_rejected: "([^"]*)",$', re.MULTILINE)
_PINNED = re.compile(r'expect\(missingLabel\("symbol_or_unit_rejected"\)\)\.toBe\("([^"]*)"\);')


def _ruling_t12() -> str:
    lines = (REPO / RULING).read_text(encoding="utf-8").splitlines()
    assert lines[27] == "**T-12 庫存頁標籤（主案）**"  # the heading above L29
    return lines[28].removeprefix("> ")


def test_t12_is_the_same_text_in_the_ruling_the_frontend_label_and_its_test() -> None:
    t12 = _ruling_t12()
    assert t12  # not vacuous

    source = (FRONTEND_LIB / "valuationWording.ts").read_text(encoding="utf-8")
    [label] = _LABEL.findall(source)

    test = (FRONTEND_LIB / "__tests__" / "valuationWording.test.ts").read_text(encoding="utf-8")
    [pinned] = _PINNED.findall(test)

    assert label == t12
    assert pinned == t12
