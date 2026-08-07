#!/usr/bin/env python3
"""CI gate: every PR must add or update a review record containing a PASS verdict.

A review record is a Markdown file under work/reviews/ with a line matching
"結論:PASS" (full-width or half-width colon). See docs/handoff-protocol.md,
section "審查紀錄與機械閘門".

Usage: python scripts/check_review_record.py --base origin/main
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# A verdict line is "結論:<verdict>" alone on its line (either colon width).
# The LAST verdict line in a file is authoritative, so multi-round records
# ("結論:NEEDS_CHANGES" then "結論:PASS") and quoted format reminders
# cannot produce false positives.
VERDICT_PATTERN = re.compile(r"^\s*結論[:：]\s*(\S+)\s*$", re.MULTILINE)
REVIEW_DIR = "work/reviews/"


def final_verdict(text: str) -> str | None:
    verdicts = VERDICT_PATTERN.findall(text)
    return verdicts[-1] if verdicts else None


def changed_files(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base ref of the PR, e.g. origin/main")
    args = parser.parse_args()

    try:
        files = changed_files(args.base)
    except subprocess.CalledProcessError as exc:
        print(f"❌ git diff 失敗:{exc.stderr.strip()}", file=sys.stderr)
        return 2

    review_files = [
        f for f in files if f.startswith(REVIEW_DIR) and f.endswith(".md") and Path(f).is_file()
    ]

    if not review_files:
        print("❌ 此 PR 未新增或更新任何審查紀錄檔(work/reviews/*.md)。")
        print("   依交接協定,qa-reviewer 審查通過後必須落檔,含一行「結論:PASS」。")
        return 1

    passed = [
        f for f in review_files if final_verdict(Path(f).read_text(encoding="utf-8")) == "PASS"
    ]

    if not passed:
        print("❌ 找到審查紀錄檔,但沒有任何一份的最終結論行是「結論:PASS」:")
        for f in review_files:
            verdict = final_verdict(Path(f).read_text(encoding="utf-8"))
            print(f"   - {f}(最終結論:{verdict or '無結論行'})")
        return 1

    print("✅ 審查紀錄閘門通過:")
    for f in passed:
        print(f"   - {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
