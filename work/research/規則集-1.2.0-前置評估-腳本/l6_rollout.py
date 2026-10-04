"""L-6: the 540-day window's peak rolling out, and the resulting one-day change.

A roll-out day t: the peak the window used on day t-1 is older than t's window
start. The counterfactual keeps that old peak (window extended by one day). The
jump is current_t - counterfactual_t (>= 0: the drawdown shrinks).
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad")
from common import WINDOW_BARS, demo_series, pit_drawdown  # noqa: E402

RULES = {"drawdown_protection": -0.20, "deep_drawdown_stop": -0.30}


def demo_part():
    print("## A. demo（完整區間日；區間不足日不可能發生滾出）")
    for sym, (dates, close) in demo_series().items():
        cur, peak, ws, partial = pit_drawdown(dates, close)
        events = []
        for t in range(1, len(dates)):
            if partial[t] or peak[t - 1] < 0:
                continue
            if peak[t - 1] < ws[t]:
                old = close[peak[t - 1]]
                cf = close[t] / max(old, close[ws[t] : t + 1].max()) - 1
                flips = [r for r, T in RULES.items() if cf < T <= cur[t]]
                events.append((dates[t], dates[peak[t - 1]], dates[peak[t]], cf, cur[t], cur[t] - cf, flips))
        full = int((~partial).sum())
        print(f"\n### {sym}：完整區間 {full} 日，滾出事件 {len(events)} 次")
        if events:
            print("| 日期 | 滾出的高點日 | 新高點日 | 保留舊高點的目前回撤 | 實際目前回撤 | 單日收斂（pp） | 因此不再命中 |")
            print("|---|---|---|---|---|---|---|")
            for d, op, np_, cf, c, j, fl in events:
                print(f"| {d} | {op} | {np_} | {cf:.2%} | {c:.2%} | {j*100:.2f} | {'、'.join(fl) or '—'} |")
        # how far is window peak below the all-available-history peak, on full-window days
        allmax = np.maximum.accumulate(close)
        cur_all = close / allmax - 1
        sel = ~partial
        diff = (cur - cur_all)[sel] * 100
        print(f"- 完整區間日中，窗內高點低於全部可得歷史高點的日數：{int(np.sum(diff > 1e-9))}／{full}；差距最大 {diff.max():.2f} pp")
        for r, T in RULES.items():
            silent = int(np.sum(((cur_all < T) & ~(cur < T))[sel]))
            print(f"  - {r}：以全部可得歷史高點計會命中、以 540 日窗計不命中的日數 {silent}")


def mc_part(n_paths=400, years=10, mu=0.06, seed=11):
    print(f"\n## B. GBM（模型），{n_paths} 條 × {years} 年；窗 {WINDOW_BARS} 根，對照窗 {2*WINDOW_BARS} 根")
    print("| σ | 滾出事件/年 | 單日收斂≥1pp/年 | ≥5pp/年 | ≥10pp/年 | 單日收斂 p50／p90／max（pp，事件中） | prot 因滾出單日翻為不命中/年 | deep 同/年 | prot 長窗命中但現窗不命中 日/年 | deep 同 日/年 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    rng = np.random.default_rng(seed)
    W = WINDOW_BARS
    extra_rows = []
    for sigma in (0.20, 0.35, 0.60):
        Tn = 2 * W + 252 * years
        lr = rng.normal((mu - sigma**2 / 2) / 252, sigma / np.sqrt(252), size=(Tn, n_paths))
        C = 100 * np.exp(np.cumsum(lr, axis=0))
        df = pd.DataFrame(C)
        m = df.rolling(W, min_periods=1).max().to_numpy()
        m_ext = df.rolling(W + 1, min_periods=1).max().to_numpy()  # yesterday's window + today
        m_long = df.rolling(2 * W, min_periods=1).max().to_numpy()
        ev = slice(2 * W, None)
        cur = C / m - 1
        cf = C / m_ext - 1
        jump = (cur - cf)[ev]
        is_ev = jump > 1e-12
        py = n_paths * years
        js = jump[is_ev] * 100
        fl = [int(np.sum(((cf < T) & (cur >= T))[ev])) / py for T in RULES.values()]
        cl = C / m_long - 1
        sil = [int(np.sum(((cl < T) & ~(cur < T))[ev])) / py for T in RULES.values()]
        cum20 = pd.DataFrame(np.where(jump > 0, jump, 0.0)).rolling(20, min_periods=1).sum().to_numpy() * 100
        extra_rows.append((sigma, (cum20 >= 5).any(axis=0).mean(), (cum20 >= 10).any(axis=0).mean(), np.percentile(cum20.max(axis=0), 90), cum20.max()))
        print(f"| {sigma} | {is_ev.sum()/py:.2f} | {(js>=1).sum()/py:.2f} | {(js>=5).sum()/py:.3f} | {(js>=10).sum()/py:.3f} "
              f"| {np.percentile(js,50):.2f}／{np.percentile(js,90):.2f}／{js.max():.1f} | {fl[0]:.3f} | {fl[1]:.3f} | {sil[0]:.1f} | {sil[1]:.1f} |")
    print("\n任一 20 交易日內『僅因滾出』累計收斂（pp）：")
    print("| σ | 10 年內至少一次 ≥5pp 的路徑比例 | ≥10pp 的路徑比例 | 每條路徑最大值 p90 | 全體最大 |")
    print("|---|---|---|---|---|")
    for r in extra_rows:
        print(f"| {r[0]} | {r[1]:.0%} | {r[2]:.0%} | {r[3]:.1f} | {r[4]:.1f} |")


if __name__ == "__main__":
    demo_part()
    mc_part()
