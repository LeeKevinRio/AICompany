"""Cross-check: common.pit_drawdown vs drawdown_rule_diff.replay on demo bars.

Read-only, in-memory demo bars, no DB, no network. Confirms the 1.2.0
pre-assessment recomputes the same `drawdown.current` and the same 1.1.0 hit
flags as the CLI (which goes compute_signals -> build_context -> rule eval and
has its own future-peak test).
"""
from __future__ import annotations

import sys

import numpy as np

SCRATCH = "/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad"
sys.path.insert(0, SCRATCH)
sys.path.insert(0, "/home/user/AICompany/apps/stock-desk/backend/scripts")
from common import DEMO_END, pit_drawdown  # noqa: E402

from app.advice.loader import load_default_rules  # noqa: E402
from app.demo.seed import build_demo_bars  # noqa: E402
from drawdown_rule_diff import legacy_ruleset, replay  # noqa: E402

THRESH = {"drawdown_protection": -0.2, "deep_drawdown_stop": -0.3}


def main() -> None:
    new_rules = load_default_rules()
    legacy = legacy_ruleset(new_rules)
    print(f"ruleset {new_rules.version}; demo end {DEMO_END}")
    print("| 標的 | 日數 | current 可比日數 | current 最大絕對差 | protection 旗標不一致 | deep 旗標不一致 |")
    print("|---|---:|---:|---:|---:|---:|")
    for sym, bars in build_demo_bars(today=DEMO_END).items():
        bars = sorted(bars, key=lambda b: b.date)
        dates = [b.date for b in bars]
        closes = np.array([float(b.close) for b in bars])
        cur, _, _, _ = pit_drawdown(dates, closes)
        rows = replay(sym, bars, new_rules=new_rules, legacy_rules=legacy)
        assert [r.day for r in rows] == dates
        diffs, n_cmp = [], 0
        mism = {k: 0 for k in THRESH}
        for i, r in enumerate(rows):
            a, b = r.current, cur[i]
            if a is None or np.isnan(b):
                if not (a is None and np.isnan(b)):
                    diffs.append(float("inf"))
                continue
            n_cmp += 1
            diffs.append(abs(a - b))
            for rid, t in THRESH.items():
                if (rid in r.new_hits) != bool(b < t):
                    mism[rid] += 1
        print(f"| {sym} | {len(rows)} | {n_cmp} | {max(diffs):.3g} | {mism['drawdown_protection']} | {mism['deep_drawdown_stop']} |")


if __name__ == "__main__":
    main()
