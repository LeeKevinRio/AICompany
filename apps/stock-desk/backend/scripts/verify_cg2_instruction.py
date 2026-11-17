"""Checks the CEO instruction of the CG-2 one-click files against its sources (RC-164, RC-182).

Prints one ``OK ...`` or ``FAIL ...`` line per check and exits 0 only when every check is OK.

* The quoted risk text is **extracted from the risk reports** by fixed rules and compared with the
  instruction's quote blocks byte for byte (``extract_rc182``, ``extract_block5``):
  - RC-182: the block quote after the RC-182 bullet of the supplement 7 addendum 2 report;
  - block five: the block quote under the "block five" heading of the Q-1/Q-2 report.
* Every fixed sentence of ``scripts/cg2_register.py`` (the STOP table, the ERROR sentences and the
  prompts) appears in the instruction, and every row of the STOP table names "do not change any
  setting or file yourself" (in Chinese).
* No guarantee wording in the instruction outside the quoted blocks.

Usage (from the backend folder): ``python scripts/verify_cg2_instruction.py``.
"""

from __future__ import annotations

import runpy
import sys
from collections.abc import Iterable
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DOC = REPO / "work" / "dispatch" / "2026-11-17-正式登記操作說明-CEO.md"
RC182_REPORT = REPO / "work" / "reviews" / "2026-11-16-補充七附記二三點判定RC179至RC184-風控.md"
BLOCK5_REPORT = REPO / "work" / "reviews" / "2026-11-15-真實資料一鍵檔Q1Q2確認-風控.md"
SCRIPT = Path(__file__).resolve().with_name("cg2_register.py")

RC182_MARKER = "- **RC-182（required）：CEO 登記說明文件要逐字加入下面這段**"
BLOCK5_HEADING = "**區塊五：登記時「是否看過暫定對照」**"
#: Wording this instruction must not use in its own text (the quoted blocks are exempt).
GUARANTEE_WORDS = ("保證", "一定會", "絕對", "確保", "必然", "百分之百", "萬無一失", "不會出錯")
#: What every STOP row's last column must tell the CEO.
NO_SELF_FIX = "不要自己"


def _quote_after(lines: list[str], start: int, prefix: str) -> list[str]:
    """The consecutive lines from ``start`` that begin with ``prefix``, with it removed."""
    block: list[str] = []
    for line in lines[start:]:
        if not line.startswith(prefix):
            break
        block.append(line[len(prefix) :])
    return block


def extract_rc182(report: str) -> str:
    """The RC-182 paragraph: the ``  > `` lines right after the bullet (one blank line between)."""
    lines = report.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(RC182_MARKER)]
    if len(starts) != 1:
        raise ValueError(f"the RC-182 bullet occurs {len(starts)} times, not once")
    i = starts[0] + 1
    while lines[i].strip() == "":
        i += 1
    block = _quote_after(lines, i, "  > ")
    if len(block) != 1:
        raise ValueError("the RC-182 quote is not one paragraph")
    return block[0]


def extract_block5(report: str) -> str:
    """The block-five paragraph: the ``> `` lines right under its heading."""
    lines = report.splitlines()
    starts = [i for i, line in enumerate(lines) if line == BLOCK5_HEADING]
    if len(starts) != 1:
        raise ValueError(f"the block five heading occurs {len(starts)} times, not once")
    i = starts[0] + 1
    while lines[i].strip() == "":
        i += 1
    block = _quote_after(lines, i, "> ")
    if len(block) != 1:
        raise ValueError("the block five quote is not one paragraph")
    return block[0]


def quote_blocks(doc: str) -> list[str]:
    """Every block quote of the instruction as its lines joined by ``\\n`` (marker removed)."""
    blocks: list[str] = []
    current: list[str] = []
    for line in doc.splitlines():
        if line.startswith("> "):
            current.append(line[2:])
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def outside_quotes(doc: str) -> str:
    return "\n".join(line for line in doc.splitlines() if not line.startswith("> "))


def check(
    doc: str,
    *,
    rc182_report: str,
    block5_report: str,
    sentences: Iterable[str],
) -> list[tuple[bool, str]]:
    """The checks as ``(ok, text)`` pairs."""
    results: list[tuple[bool, str]] = []
    blocks = quote_blocks(doc)
    for name, expected in (
        ("rc182", extract_rc182(rc182_report)),
        ("block5", extract_block5(block5_report)),
    ):
        count = blocks.count(expected)
        results.append(
            (count == 1, f"{name} verbatim, exactly once as a quote block (found {count})")
        )
    missing = [s for s in sentences if f"`{s}`" not in doc]
    results.append(
        (not missing, f"every fixed sentence is in the instruction (missing {len(missing)})")
    )
    rows = [line for line in doc.splitlines() if line.startswith("| `")]
    bad_rows = [row for row in rows if NO_SELF_FIX not in row.rsplit("|", 2)[-2]]
    results.append(
        (not bad_rows, f"every table row says not to fix it yourself (bad {len(bad_rows)})")
    )
    own = outside_quotes(doc)
    found = [word for word in GUARANTEE_WORDS if word in own]
    results.append((not found, f"no guarantee wording outside the quotes (found {found})"))
    results.append(
        ("待風控定稿" in own, "the exit 5 text is marked as awaiting the risk final text")
    )
    return results


def _sentences() -> list[str]:
    ns = runpy.run_path(str(SCRIPT), run_name="cg2_register_loaded")
    sys.excepthook = sys.__excepthook__  # the loaded script replaced it; this checker wants errors
    stops = ns["STOPS"]
    fixed = [
        ns["INTERRUPTED_SAFE"],
        ns["INTERRUPTED_LATE"],
        ns["UNEXPECTED_SAFE"],
        ns["UNEXPECTED_LATE"],
        ns["HOOK_SENTENCE"],
        ns["PROMPT_CLOSE"].strip(),
        ns["PROMPT_SEEN"].strip(),
    ]
    return [sentence for _code, sentence in stops.values()] + fixed


def main() -> int:
    results = check(
        DOC.read_text(encoding="utf-8"),
        rc182_report=RC182_REPORT.read_text(encoding="utf-8"),
        block5_report=BLOCK5_REPORT.read_text(encoding="utf-8"),
        sentences=_sentences(),
    )
    for ok, text in results:
        sys.stdout.write(("OK   " if ok else "FAIL ") + text + "\n")
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
