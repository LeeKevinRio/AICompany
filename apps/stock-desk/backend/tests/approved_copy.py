"""Risk-approved fixed lines of ``report status``, read from the approval records themselves.

The tests compare the module constants with these, so the wording is never typed
twice. Each record holds exactly one ``<label>`全文`` line with the text between
backticks (ADR-0030 supplement 8 point 6 (b)).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
REVIEWS: Final = REPO_ROOT / "work" / "reviews"

#: RC-230: the line after the F-2 and grid counts.
F2_GAP_APPROVAL: Final = REVIEWS / "2026-11-19-report-status缺日加註定稿RC229至RC232-風控.md"
F2_GAP_LABEL: Final = "定稿全文："
#: RC-233 / RC-234: the line after the review trigger lines.
REVIEW_GAP_APPROVAL: Final = REVIEWS / "2026-11-19-重審觸發缺日加註定稿RC233至RC236-風控.md"
REVIEW_GAP_LABEL: Final = "第二行定稿全文："


def approved_text(record: Path, label: str) -> str:
    """The backticked text of the record's one line starting with ``label``."""
    pattern = rf"^{re.escape(label)}`([^`]+)`$"
    found = re.findall(pattern, record.read_text(encoding="utf-8"), flags=re.M)
    assert len(found) == 1, f"{record.name}: expected one {label!r} line, found {len(found)}"
    return str(found[0])


def f2_gap_line() -> str:
    return approved_text(F2_GAP_APPROVAL, F2_GAP_LABEL)


def review_gap_line() -> str:
    return approved_text(REVIEW_GAP_APPROVAL, REVIEW_GAP_LABEL)
