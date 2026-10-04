"""T4: how much un-adjusted dividends deepen the current drawdown, and false triggers.

Construction for (B)/(C): the demo (or GBM) close is taken as the *total-return*
path A; hypothetical cash dividends d = yield/freq of the previous raw close are
removed on ex-dates to form the raw path R. Current drawdown on R is what the app
computes (raw close); on A it equals the back-adjusted (anchored at t) value,
because back-adjustment anchored at t is A times a constant (scale invariant).
Hypothetical yields only; no dividend_events are read.
"""
from __future__ import annotations

import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, "/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad")
from common import WINDOW_BARS, demo_series, pit_drawdown  # noqa: E402

FREQS = {"年配": [(7, 15)], "半年配": [(1, 15), (7, 15)], "季配": [(1, 15), (4, 15), (7, 15), (10, 15)]}
YIELDS = (0.03, 0.045, 0.06)


def analytic():
    print("## A. 解析：高點日之後累計配息比例 D 與顯示回撤的關係（假設總報酬口徑高點與原始收盤高點同日）")
    print("顯示回撤（原始收盤）= (1 + 總報酬口徑回撤) × (1 − D) − 1；D = 1 − Π(1 − d_i)\n")
    Ds = (0.03, 0.045, 0.06, 0.09, 0.116)
    print("| 總報酬口徑回撤 | " + " | ".join(f"D={d:.1%}" for d in Ds) + " |")
    print("|---|" + "---|" * len(Ds))
    for a in (-0.15, -0.17, -0.18, -0.20, -0.25, -0.27, -0.28, -0.30):
        print(f"| {a:.0%} | " + " | ".join(f"{((1 + a) * (1 - d) - 1):.2%}" for d in Ds) + " |")
    print("\n誤觸帶（原始收盤已深於門檻、總報酬口徑未深於門檻）：")
    print("| D | −20% 規則誤觸帶（顯示值） | −30% 規則誤觸帶（顯示值） |")
    print("|---|---|---|")
    for d in Ds:
        print(f"| {d:.1%} | [{0.8 * (1 - d) - 1:.2%}, −20%) | [{0.7 * (1 - d) - 1:.2%}, −30%) |")
    print("\n540 日窗內高點日之後最多可能經過的除息次數與累計 D（以每次 d = 殖利率/頻率、窗長 540 日曆日）：")
    print("| 頻率 | 最多次數 | 3% | 4.5% | 6% |")
    print("|---|---|---|---|---|")
    for name, n, f in (("年配", 2, 1), ("半年配", 3, 2), ("季配", 6, 4)):
        print(f"| {name} | {n} | " + " | ".join(f"{1 - (1 - y / f) ** n:.1%}" for y in YIELDS) + " |")


def ex_mask(dates, md_list):
    mask = np.zeros(len(dates), dtype=bool)
    years = sorted({d.year for d in dates})
    for y in years:
        for m, dd in md_list:
            target = date(y, m, dd)
            idx = next((i for i, d in enumerate(dates) if d >= target), None)
            if idx is not None and idx > 0 and dates[idx].year == y:
                mask[idx] = True
    return mask


def raw_from_tr(A, mask, d):
    R = np.empty_like(A)
    R[0] = A[0]
    for i in range(1, len(A)):
        R[i] = R[i - 1] * (A[i] / A[i - 1]) * ((1 - d) if mask[i] else 1.0)
    return R


def flips(on):
    return int(np.sum(on[1:] != on[:-1]))


def demo_part():
    print("\n## B. demo 注入假設配息（2330、0050；00631L 不注入）")
    print("欄位：raw/tr 命中=原始收盤口徑／總報酬口徑命中日數；誤觸=原始命中而總報酬未命中日數；gap=原始回撤減總報酬回撤（百分點，負值=原始較深）")
    ds = demo_series()
    for sym in ("2330", "0050"):
        dates, A = ds[sym]
        curA, _, _, partial = pit_drawdown(dates, A)
        i_full = int(np.argmax(~partial))
        print(f"\n### {sym}（完整區間 {dates[i_full]}～{dates[-1]}，{len(dates) - i_full} 日；括號內為全期 {int((~np.isnan(curA)).sum())} 日）\n")
        print("| 殖利率 | 頻率 | 除息日 | prot raw/tr 命中 | prot 誤觸 | deep raw/tr 命中 | deep 誤觸 | gap 最大 | gap 中位（完整區間） | 翻轉 raw/tr（prot，全期） |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for y in YIELDS:
            for fname, md in FREQS.items():
                mask = ex_mask(dates, md)
                d = y / len(md)
                R = raw_from_tr(A, mask, d)
                curR, *_ = pit_drawdown(dates, R)
                gap = (curR - curA) * 100
                v = ~np.isnan(curA)
                full = ~partial
                def cnt(c, T, sel):
                    with np.errstate(invalid="ignore"):
                        return int(np.sum((c < T) & sel))
                def fp(T, sel):
                    with np.errstate(invalid="ignore"):
                        return int(np.sum((curR < T) & ~(curA < T) & sel))
                with np.errstate(invalid="ignore"):
                    onR, onA = (curR < -0.2) & v, (curA < -0.2) & v
                print(f"| {y:.1%} | {fname} | {int(mask.sum())} | {cnt(curR,-0.2,full)}/{cnt(curA,-0.2,full)}（{cnt(curR,-0.2,v)}/{cnt(curA,-0.2,v)}） "
                      f"| {fp(-0.2,full)}（{fp(-0.2,v)}） | {cnt(curR,-0.3,full)}/{cnt(curA,-0.3,full)}（{cnt(curR,-0.3,v)}/{cnt(curA,-0.3,v)}） "
                      f"| {fp(-0.3,full)}（{fp(-0.3,v)}） | {np.nanmin(gap):.2f} | {np.nanmedian(gap[full]):.2f} | {flips(onR)}/{flips(onA)} |")


def mc_part(n_paths=400, years=10, mu=0.08, seed=4):
    print(f"\n## C. GBM（總報酬路徑 μ={mu:.0%}，模型非資料），{n_paths} 條 × {years} 年，窗 {WINDOW_BARS} 根")
    print("| σ | 殖利率 | 頻率 | prot 原始命中日/年 | 其中誤觸佔比 | deep 原始命中日/年 | 其中誤觸佔比 | 原始命中日的平均 gap（pp） |")
    print("|---|---|---|---|---|---|---|---|")
    rng = np.random.default_rng(seed)
    for sigma in (0.20, 0.35):
        Tn = WINDOW_BARS + 252 * years
        lr = rng.normal((mu - sigma**2 / 2) / 252, sigma / np.sqrt(252), size=(Tn, n_paths))
        A = 100 * np.exp(np.cumsum(lr, axis=0))
        curA = A / pd.DataFrame(A).rolling(WINDOW_BARS, min_periods=1).max().to_numpy() - 1
        for y in (0.03, 0.06):
            for fname, f in (("年配", 1), ("季配", 4)):
                step = 252 // f
                mask = np.zeros(Tn, dtype=bool)
                mask[step // 2 :: step] = True
                factor = np.cumprod(np.where(mask, 1 - y / f, 1.0))[:, None]
                R = A * factor
                curR = R / pd.DataFrame(R).rolling(WINDOW_BARS, min_periods=1).max().to_numpy() - 1
                ev = slice(WINDOW_BARS, None)
                py = n_paths * years
                res = []
                for T in (-0.2, -0.3):
                    hitR = curR[ev] < T
                    fp = hitR & ~(curA[ev] < T)
                    res.append((hitR.sum() / py, fp.sum() / max(1, hitR.sum())))
                g = (curR[ev] - curA[ev])[curR[ev] < -0.2] * 100
                print(f"| {sigma} | {y:.0%} | {fname} | {res[0][0]:.1f} | {res[0][1]:.0%} | {res[1][0]:.1f} | {res[1][1]:.0%} | {g.mean():.2f} |")


if __name__ == "__main__":
    analytic()
    demo_part()
    mc_part()
