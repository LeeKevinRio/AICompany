"""L-7: threshold edge vs 2-decimal percent display, and exact ties in float64.

Display emulation: frontend formatPercent = (v*100).toLocaleString(2 decimals),
emulated as Decimal(repr(v*100)) rounded half away from zero. Alert message
_fmt = 4 decimals with trailing zeros stripped. Comparison: engine `lt` on the
float64 value from app.signals.risk._drawdown_path (values / running_peak - 1).
"""
from __future__ import annotations

import sys
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd

sys.path.insert(0, "/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad")
from common import WINDOW_BARS, demo_series, pit_drawdown  # noqa: E402
from app.signals.risk import current_drawdown  # noqa: E402

T_LIST = (-0.2, -0.3)


def disp(v):
    return Decimal(repr(v * 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stock_tick_cents(c):  # c in cents (int)
    p = c / 100
    return 1 if p < 10 else 5 if p < 50 else 10 if p < 100 else 50 if p < 500 else 100 if p < 1000 else 500


def etf_tick_cents(c):
    return 1 if c < 5000 else 5


def tie_part():
    print("## A. 收盤恰為高點的 80%／70%（數學上等於門檻）時，float64 比較結果")
    print("直接用 app 的 current_drawdown([P, C]) 計算，價格皆在台股升降單位格點上。\n")
    print("| 格點 | 比例 | 可成對的 (P, C) 組數 | current 的值（去重） | lt 門檻命中 | 不命中 | 前端顯示 |")
    print("|---|---|---|---|---|---|---|")
    for gname, tick in (("股票", stock_tick_cents), ("ETF", etf_tick_cents), ("demo 0.01", lambda c: 1)):
        for num, T in ((8, -0.2), (7, -0.3)):
            vals, hit, miss, n = set(), 0, 0, 0
            c = 100
            while c <= 200000:  # P from 1.00 to 2000.00
                if c % tick(c) == 0 and (c * num) % 10 == 0:
                    cc = c * num // 10
                    if cc % tick(cc) == 0:
                        v = current_drawdown([c / 100, cc / 100])[0]
                        vals.add(repr(v))
                        n += 1
                        if v < T:
                            hit += 1
                        else:
                            miss += 1
                c += 1
            dv = sorted({str(disp(float(x))) for x in vals})
            print(f"| {gname} | {num}/10 | {n} | {', '.join(sorted(vals))} | {hit} | {miss} | {', '.join(dv)}% |")
    print()
    for T in T_LIST:
        print(f"- 常數 {T!r} 的 float64 精確值：{Decimal(T)}")
    print(f"- 0.8 − 1 → {Decimal(0.8 - 1)}；0.7 − 1 → {Decimal(0.7 - 1)}")


def band_counts(cur):
    out = {}
    for T in T_LIST:
        v = cur[~np.isnan(cur)]
        tie = np.zeros(len(v), dtype=bool)
        dmiss = dhit = amiss = ahit = 0
        for x in v:
            if abs(x - T) > 1e-3:
                continue
            shows_T = disp(float(x)) == Decimal(repr(T * 100)).quantize(Decimal("0.01"))
            hit = x < T
            if shows_T and not hit:
                dmiss += 1
            if shows_T and hit:
                dhit += 1
            f = f"{x:,.4f}".rstrip("0").rstrip(".")
            if f == repr(T) and hit:
                ahit += 1
            if f == repr(T) and not hit:
                amiss += 1
        out[T] = (dmiss, dhit, amiss, ahit)
    return out


def density(cur, T, w=0.01):
    v = cur[~np.isnan(cur)]
    return np.sum(np.abs(v - T) < w / 2) / (len(v) * w)


def demo_part():
    print("\n## B. demo（全期可計算日，含區間不足日）")
    print("| 標的 | 日數 | 門檻 | 門檻 ±0.5pp 內日數 | 前端顯示恰為門檻且不命中 | 顯示恰為門檻且命中 | 期望值：每日落入 5e-5 不命中帶機率（密度估計） |")
    print("|---|---|---|---|---|---|---|")
    for sym, (dates, close) in demo_series().items():
        cur, *_ = pit_drawdown(dates, close)
        bc = band_counts(cur)
        n = int((~np.isnan(cur)).sum())
        for T in T_LIST:
            near = int(np.sum(np.abs(cur[~np.isnan(cur)] - T) < 0.005))
            print(f"| {sym} | {n} | {T:.0%} | {near} | {bc[T][0]} | {bc[T][1]} | {density(cur, T) * 5e-5:.2e} |")


def tick_round(p, etf=False):
    if etf:
        tick = np.where(p < 50, 0.01, 0.05)
    else:
        tick = np.select([p < 10, p < 50, p < 100, p < 500, p < 1000], [0.01, 0.05, 0.1, 0.5, 1.0], 5.0)
    return np.round(np.round(p / tick) * tick, 2)


def mc_part(n_paths=300, years=10, sigma=0.35, mu=0.06, seed=99):
    print(f"\n## C. GBM 收盤四捨五入到台股升降單位（模型），σ={sigma}，{n_paths} 條 × {years} 年，窗 {WINDOW_BARS} 根")
    print("| 起始價 | 格點 | 門檻 | 門檻 ±0.5pp 內 日/年 | 恰等於門檻（tie）日/年 | tie 中命中比例 | 顯示恰為門檻且不命中 日/年 | 顯示恰為門檻且命中 日/年 | 警示訊息顯示門檻值且命中 日/年 |")
    print("|---|---|---|---|---|---|---|---|---|")
    rng = np.random.default_rng(seed)
    for start, etf in ((15, False), (45, True), (80, False), (300, False), (700, False)):
        Tn = WINDOW_BARS + 252 * years
        lr = rng.normal((mu - sigma**2 / 2) / 252, sigma / np.sqrt(252), size=(Tn, n_paths))
        P = tick_round(start * np.exp(np.cumsum(lr, axis=0)), etf)
        P = np.maximum(P, 0.01)
        m = pd.DataFrame(P).rolling(WINDOW_BARS, min_periods=1).max().to_numpy()
        cur = (P / m - 1.0)[WINDOW_BARS:]
        cents_c = np.rint(P * 100).astype(np.int64)[WINDOW_BARS:]
        cents_m = np.rint(m * 100).astype(np.int64)[WINDOW_BARS:]
        py = n_paths * years
        for T, num in ((-0.2, 8), (-0.3, 7)):
            near = np.abs(cur - T) < 0.005
            tie = (cents_c * 10 == cents_m * num)
            tie_hit = (tie & (cur < T)).sum()
            flat = cur[near & ~tie]
            bc = band_counts(np.concatenate([flat, cur[tie]]))[T]
            print(f"| {start} | {'ETF' if etf else '股票'} | {T:.0%} | {near.sum()/py:.1f} | {tie.sum()/py:.3f} | {(tie_hit/tie.sum() if tie.sum() else float('nan')):.0%} "
                  f"| {bc[0]/py:.3f} | {bc[1]/py:.3f} | {bc[3]/py:.3f} |")


if __name__ == "__main__":
    tie_part()
    demo_part()
    mc_part()
