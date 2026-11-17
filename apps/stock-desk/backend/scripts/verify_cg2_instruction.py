"""Checks the CEO instruction of the CG-2 one-click files against its sources (RC-164 to RC-211).

Prints one ``OK ...`` or ``FAIL ...`` line per check and exits 0 only when every check is OK.

Every risk-final block is **extracted from the risk reports** by fixed rules and must occur in the
instruction byte for byte, exactly once:

* RC-182 and block five: block quotes in the instruction (extractors ``extract_rc182``,
  ``extract_block5``);
* RC-186b, RC-187, RC-195 (``RC185_REPORT``) and RC-202 to RC-211 (``RC199_REPORT``): the quote
  lines after the block's marker, with the quote marks removed (``block_after``);
* the four new STOP rows of RC-200 and RC-201: whole table lines;
* RC-186a (``PROMPT_SEEN``), RC-194 (``bad_answer``) and the four new sentences: equal to what
  ``scripts/cg2_register.py`` holds;
* the backup file names of RC-209: equal to what the script actually makes.

Also: every fixed sentence of the script is in the instruction, every table row says "do not fix it
yourself", no guarantee wording outside the quoted and verified blocks, no leftover "awaiting risk
final text" marker.

Usage (from the backend folder): ``python scripts/verify_cg2_instruction.py``.
"""

from __future__ import annotations

import runpy
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
DOC = REPO / "work" / "dispatch" / "2026-11-17-正式登記操作說明-CEO.md"
RC182_REPORT = REPO / "work" / "reviews" / "2026-11-16-補充七附記二三點判定RC179至RC184-風控.md"
BLOCK5_REPORT = REPO / "work" / "reviews" / "2026-11-15-真實資料一鍵檔Q1Q2確認-風控.md"
RC185_REPORT = (
    REPO / "work" / "reviews" / "2026-11-17-正式登記說明與畫面字句判定RC185至RC198-風控.md"
)
RC199_REPORT = REPO / "work" / "reviews" / "2026-11-17-附記三新增字面定稿RC199至RC212-風控.md"
SCRIPT = Path(__file__).resolve().with_name("cg2_register.py")

RC182_MARKER = "- **RC-182（required）：CEO 登記說明文件要逐字加入下面這段**"
BLOCK5_HEADING = "**區塊五：登記時「是否看過暫定對照」**"
#: Wording this instruction must not use in its own text (the quoted blocks are exempt).
GUARANTEE_WORDS = ("保證", "一定會", "絕對", "確保", "必然", "百分之百", "萬無一失", "不會出錯")
#: What every table row's last column must tell the CEO.
NO_SELF_FIX = "不要自己"
#: (marker, report) of every plain-text risk-final block of the instruction.
OLD_BLOCKS = ("【區塊 RC-186b", "【區塊 RC-187", "【區塊 RC-195")
NEW_BLOCKS = tuple(f"**RC-{n}" for n in range(202, 212))
#: Literal strings the risk reports prescribe (checked in the report and in the instruction).
OLD_LITERALS = (
    "## 六、登記被拒絕（結束碼 3 或 4）",
    "以下引文為風控定稿（RC-182）：",
    "## 七、登記開始之後無法確認結果（結束碼 5 等）（風控定稿 RC-191）",
    "登記程式回報已經寫入，但寫入之後的自我核對沒有通過（結束碼 5）。見本節下方說明。",
    "見本節下方引文。",
)
STATUS_LINE = "已套用風控 RC-185～RC-211"


def _unquote(line: str) -> str:
    text = line.lstrip()
    text = text[1:]
    return text[1:] if text.startswith(" ") else text


def block_after(report: str, marker: str) -> str:
    """The quote lines right after the one line that starts with ``marker`` (marks removed)."""
    lines = report.splitlines()
    starts = [i for i, line in enumerate(lines) if line.lstrip().startswith(marker)]
    if len(starts) != 1:
        raise ValueError(f"the marker {marker!r} occurs {len(starts)} times, not once")
    i = starts[0] + 1
    # Skip the lead-in lines (blank or prose) up to the first quote line of this block.
    while i < len(lines) and not lines[i].lstrip().startswith(">"):
        if lines[i].lstrip().startswith(("**RC-", "【區塊", "- **RC-")):
            raise ValueError(f"no quote after {marker!r}")
        i += 1
    block: list[str] = []
    while i < len(lines) and lines[i].lstrip().startswith(">"):
        block.append(_unquote(lines[i]))
        i += 1
    if not block:
        raise ValueError(f"no quote after {marker!r}")
    return "\n".join(block)


def _single_quote(lines: list[str], start: int, prefix: str) -> str:
    block: list[str] = []
    for line in lines[start:]:
        if not line.startswith(prefix):
            break
        block.append(line[len(prefix) :])
    if len(block) != 1:
        raise ValueError("the quote is not one paragraph")
    return block[0]


def extract_rc182(report: str) -> str:
    """The RC-182 paragraph: the ``  > `` lines right after the bullet (one blank line between)."""
    lines = report.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(RC182_MARKER)]
    if len(starts) != 1:
        raise ValueError(f"the RC-182 bullet occurs {len(starts)} times, not once")
    i = starts[0] + 1
    while lines[i].strip() == "":
        i += 1
    return _single_quote(lines, i, "  > ")


def extract_block5(report: str) -> str:
    """The block-five paragraph: the ``> `` lines right under its heading."""
    lines = report.splitlines()
    starts = [i for i, line in enumerate(lines) if line == BLOCK5_HEADING]
    if len(starts) != 1:
        raise ValueError(f"the block five heading occurs {len(starts)} times, not once")
    i = starts[0] + 1
    while lines[i].strip() == "":
        i += 1
    return _single_quote(lines, i, "> ")


def _backticked_after(report: str, marker: str) -> str:
    lines = report.splitlines()
    starts = [i for i, line in enumerate(lines) if marker in line]
    if len(starts) != 1:
        raise ValueError(f"the marker {marker!r} occurs {len(starts)} times, not once")
    i = starts[0] + 1
    while lines[i].strip() == "":
        i += 1
    text = lines[i].strip()
    if text.startswith("`") and text.endswith("`"):
        return text[1:-1]
    raise ValueError("not a backticked sentence")


def extract_prompt_seen(report: str) -> str:
    """RC-186a: the sentence (its trailing space is inside the backticks)."""
    return _backticked_after(report, "【區塊 RC-186a")


def extract_bad_answer(report: str) -> str:
    """RC-194: the new fixed sentence of the ``bad_answer`` stop."""
    return _backticked_after(report, "畫面固定句改為：")


def extract_new_stop_rows(report: str) -> list[tuple[str, str, str]]:
    """The four table rows of RC-200 / RC-201: (sentence, meaning, action)."""
    rows = []
    for line in report.splitlines():
        if line.startswith("| `STOP:"):
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if len(cells) == 3:
                rows.append((cells[0].strip("`"), cells[1], cells[2]))
    return rows


def new_stop_row_lines(report: str) -> list[str]:
    return [line for line in report.splitlines() if line.startswith("| `STOP:")]


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


def outside_quotes(doc: str, verified: Iterable[str] = ()) -> str:
    """The instruction's own text: without quote lines and without the verified blocks."""
    text = "\n".join(line for line in doc.splitlines() if not line.startswith("> "))
    for block in verified:
        text = text.replace(block, "")
    return text


def check(
    doc: str,
    *,
    rc182_report: str,
    block5_report: str,
    old_report: str,
    new_report: str,
    sentences: Iterable[str],
    script: Mapping[str, Any],
) -> list[tuple[bool, str]]:
    """The checks as ``(ok, text)`` pairs."""
    results: list[tuple[bool, str]] = []
    blocks = quote_blocks(doc)
    for name, expected in (
        ("rc182", extract_rc182(rc182_report)),
        ("block5", extract_block5(block5_report)),
    ):
        count = blocks.count(expected)
        results.append((count == 1, f"{name} verbatim, exactly once as a quote block ({count})"))
    verified: list[str] = []
    for report, markers in ((old_report, OLD_BLOCKS), (new_report, NEW_BLOCKS)):
        for marker in markers:
            expected = block_after(report, marker)
            verified.append(expected)
            count = doc.count(expected)
            label = marker.strip("*【")
            results.append((count == 1, f"{label} verbatim, exactly once ({count})"))
    row_lines = new_stop_row_lines(new_report)
    missing_rows = [r for r in row_lines if r not in doc.splitlines()]
    results.append(
        (
            len(row_lines) == 4 and not missing_rows,
            f"the four RC-200/201 rows are in ({len(row_lines)})",
        )
    )
    verified += row_lines
    for literal in OLD_LITERALS:
        ok = literal in old_report and literal in doc
        results.append((ok, f"literal {literal[:24]!r} is in the report and the instruction"))
    stops = script["STOPS"]
    new_sentences = [r[0] for r in extract_new_stop_rows(new_report)]
    script_new = [stops[k][1] for k in script["NEW_STOP_KEYS"]]
    results.append((script_new == new_sentences, "the four new script sentences equal RC-200/201"))
    results.append(
        (script["PROMPT_SEEN"] == extract_prompt_seen(old_report), "PROMPT_SEEN equals RC-186a")
    )
    results.append(
        (stops["bad_answer"][1] == extract_bad_answer(old_report), "bad_answer equals RC-194")
    )
    results.append(
        (
            stops["usage"][1].endswith(script["_TELL"]),
            "the usage sentence ends with the tell suffix",
        )
    )
    names = [script["backup_file_name"]("<時間戳>"), script["verify_file_name"]("<時間戳>")]
    results.append(
        (all(f"`{n}`" in doc for n in names), "the backup file names are the ones the script makes")
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
    own = outside_quotes(doc, verified)
    found = [word for word in GUARANTEE_WORDS if word in own]
    results.append((not found, f"no guarantee wording in the own text (found {found})"))
    results.append(("待風控定稿" not in doc, "no awaiting-risk marker is left"))
    results.append((STATUS_LINE in doc, "the status line names the applied risk conditions"))
    return results


def _script() -> dict[str, Any]:
    ns = runpy.run_path(str(SCRIPT), run_name="cg2_register_loaded")
    sys.excepthook = sys.__excepthook__  # the loaded script replaced it; this checker wants errors
    return ns


def script_sentences(ns: Mapping[str, Any]) -> list[str]:
    fixed = [
        ns["INTERRUPTED_SAFE"],
        ns["INTERRUPTED_LATE"],
        ns["UNEXPECTED_SAFE"],
        ns["UNEXPECTED_LATE"],
        ns["HOOK_SENTENCE"],
        ns["PROMPT_CLOSE"].strip(),
        ns["PROMPT_SEEN"].strip(),
    ]
    return [sentence for _code, sentence in ns["STOPS"].values()] + fixed


def main() -> int:
    ns = _script()
    results = check(
        DOC.read_text(encoding="utf-8"),
        rc182_report=RC182_REPORT.read_text(encoding="utf-8"),
        block5_report=BLOCK5_REPORT.read_text(encoding="utf-8"),
        old_report=RC185_REPORT.read_text(encoding="utf-8"),
        new_report=RC199_REPORT.read_text(encoding="utf-8"),
        sentences=script_sentences(ns),
        script=ns,
    )
    for ok, text in results:
        sys.stdout.write(("OK   " if ok else "FAIL ") + text + "\n")
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
