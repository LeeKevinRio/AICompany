"""Cross-check of the 1.2.0 pre-assessment's drawdown recomputation.

Read-only, in-memory demo bars, no DB, no network.

Scope (what this check does and does not cover):

* Part A compares ``common.pit_drawdown`` with ``drawdown_rule_diff.replay``
  (compute_signals -> build_context -> rule eval). Both call the app's own
  ``current_drawdown``, so Part A verifies window slicing (540 calendar days,
  point-in-time), pipeline wiring and the threshold comparison of the 1.1.0
  rules. It is NOT an independent recomputation of the drawdown formula.
* Part B is that independent recomputation: pandas only (boolean date mask for
  the [t - 540d, t] window, ``expanding().max()`` for the peak), no app code,
  compared against both Part A paths and against the rule hit flags.
"""
from __future__ import annotations

import sys
from datetime import timedelta

import numpy as np
import pandas as pd
from common import BACKEND, DEMO_END, LOOKBACK, pit_drawdown  # noqa: E402

sys.path.insert(0, str(BACKEND / "scripts"))

from drawdown_rule_diff import legacy_ruleset, replay  # noqa: E402

from app.advice.loader import load_default_rules  # noqa: E402
from app.demo.seed import build_demo_bars  # noqa: E402

THRESH = {"drawdown_protection": -0.2, "deep_drawdown_stop": -0.3}
SENS_LOOKBACKS = (LOOKBACK - 1, LOOKBACK + 1, 400)  # 400 = alerts snapshot window


def pandas_drawdown(dates, closes, lookback: int = LOOKBACK) -> np.ndarray:
    """Independent recomputation: pandas window mask + expanding().max()."""
    s = pd.Series(closes, index=pd.DatetimeIndex(pd.to_datetime(dates)))
    out = np.full(len(s), np.nan)
    for i, t in enumerate(s.index):
        win = s[(s.index >= t - timedelta(days=lookback)) & (s.index <= t)]
        if len(win) < 2:  # same floor as the app (needs >= 2 prices)
            continue
        peak = win.expanding().max().iloc[-1]
        out[i] = win.iloc[-1] / peak - 1.0
    return out


def main() -> None:
    new_rules = load_default_rules()
    legacy = legacy_ruleset(new_rules)
    print(f"ruleset {new_rules.version}; demo end {DEMO_END}")
    print("\n## A. common.pit_drawdown vs drawdown_rule_diff.replay（同用 app 的 current_drawdown：驗切窗、管線接線、門檻比較）\n")
    print("| 標的 | 日數 | current 可比日數 | current 最大絕對差 | protection 旗標不一致 | deep 旗標不一致 |")
    print("|---|---:|---:|---:|---:|---:|")
    part_b = []
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

        # Part B: independent pandas recomputation.
        ind = pandas_drawdown(dates, closes)
        rep = np.array([np.nan if r.current is None else r.current for r in rows])
        nan_mismatch = int(np.sum(np.isnan(ind) != np.isnan(rep)) + np.sum(np.isnan(ind) != np.isnan(cur)))
        ok = ~np.isnan(ind) & ~np.isnan(rep) & ~np.isnan(cur)
        d_rep = float(np.max(np.abs(ind[ok] - rep[ok])))
        d_pit = float(np.max(np.abs(ind[ok] - cur[ok])))
        flag = {rid: 0 for rid in THRESH}
        for i, r in enumerate(rows):
            if not ok[i]:
                continue
            for rid, t in THRESH.items():
                if (rid in r.new_hits) != bool(ind[i] < t):
                    flag[rid] += 1
        # Sensitivity: an off-by-one window must be detectable by this check.
        sens = {}
        for lb in SENS_LOOKBACKS:
            alt = pandas_drawdown(dates, closes, lookback=lb)
            both = ~np.isnan(alt) & ~np.isnan(rep)
            sens[lb] = int(np.sum(np.abs(alt[both] - rep[both]) > 0))
        part_b.append((sym, int(ok.sum()), nan_mismatch, d_rep, d_pit, flag, sens))

    print("\n## B. 獨立重算（只用 pandas：日期遮罩切 [t−540 日, t] 窗、expanding().max() 取高點；不呼叫 app 回撤函式）\n")
    print("| 標的 | 可比日數 | 可計算與否不一致 | 與 replay 最大絕對差 | 與 pit_drawdown 最大絕對差 | protection 旗標不一致 | deep 旗標不一致 | 敏感度：窗改 539／541／400 日時與 replay 不同的日數 |")
    print("|---|---:|---:|---:|---:|---:|---:|---|")
    for sym, n, nm, d1, d2, flag, sens in part_b:
        print(f"| {sym} | {n} | {nm} | {d1:.3g} | {d2:.3g} | {flag['drawdown_protection']} | {flag['deep_drawdown_stop']} "
              "| " + "／".join(str(sens[lb]) for lb in SENS_LOOKBACKS) + " |")
    print()
    print("- 解讀：B 欄與 A 欄全為 0 表示獨立公式（pandas）與 app 公式、與規則命中旗標逐日一致。")
    print("- 限制：敏感度欄顯示窗長差 1 日在 demo 上**測不出來**（demo 高點從未落在窗邊界，L-6 滾出事件 0 次），")
    print("  窗長差到 400 日才在 2330 上出現差異；因此「540 日窗邊界恰好含／不含」未被 demo 驗到，只由程式碼閱讀與 replay 同源保證。")


if __name__ == "__main__":
    main()
