"""T1: flip-flop frequency of the two 1.1.0 drawdown rules, and 5 hysteresis designs.

Inputs: (1) demo synthetic bars (point-in-time, 540-day window, app's own
current_drawdown); (2) hand-built paths; (3) GBM Monte Carlo (model, not data).
Nothing here changes rules; designs are simulated on the current-drawdown path.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from common import WINDOW_BARS, demo_series, pit_drawdown, sma  # noqa: E402

RULES = {"drawdown_protection": -0.20, "deep_drawdown_stop": -0.30}
K_CONFIRM = 3
M_HOLD = 10
FLIP_WINDOW = 20
QUICK = 5


def invalidation_met(rule, cur, close, ma60):
    with np.errstate(invalid="ignore"):
        if rule == "drawdown_protection":
            return cur >= -0.10  # "收斂至 -10% 以內"; "回到前波高點附近" implies cur >= -0.10 too
        return (cur >= -0.20) & (close > ma60)


def simulate(design, rule, cur, close, ma60):
    """cur/close/ma60: (T, P) arrays. Returns on (T, P) bool."""
    T_ = RULES[rule]
    Tn, P = cur.shape
    valid = ~np.isnan(cur)
    with np.errstate(invalid="ignore"):
        below = (cur < T_) & valid
    if design == "base":
        return below
    if design == "B1_confirm3_exit0":
        out = np.zeros_like(below)
        for i in range(Tn):
            lo = max(0, i - K_CONFIRM + 1)
            out[i] = below[lo : i + 1].all(axis=0) if i - lo + 1 == K_CONFIRM else False
        return out
    if design == "C_any_below_last10":
        out = np.zeros_like(below)
        for i in range(Tn):
            lo = max(0, i - M_HOLD + 1)
            out[i] = below[lo : i + 1].any(axis=0)
        return out
    state = np.zeros(P, dtype=bool)
    out = np.zeros_like(below)
    cnt_in = np.zeros(P, dtype=int)
    cnt_out = np.zeros(P, dtype=int)
    inval = invalidation_met(rule, cur, close, ma60)
    for i in range(Tn):
        v = valid[i]
        if design == "A1_band_exit+5pp":
            with np.errstate(invalid="ignore"):
                exit_ = cur[i] >= T_ + 0.05
            state = np.where(state, ~exit_, below[i])
        elif design == "A2_exit_at_invalidation":
            state = np.where(state, ~inval[i], below[i])
        elif design == "B2_confirm3_both":
            cnt_in = np.where(below[i], cnt_in + 1, 0)
            cnt_out = np.where(~below[i] & v, cnt_out + 1, 0)
            state = np.where(state, cnt_out < K_CONFIRM, cnt_in >= K_CONFIRM)
        state = state & v
        out[i] = state
    return out


DESIGNS = ["base", "A1_band_exit+5pp", "A2_exit_at_invalidation", "B1_confirm3_exit0", "B2_confirm3_both", "C_any_below_last10"]


def metrics(on, base, cur, inval, i0):
    """Per single path (1-D arrays); stats over indices >= i0."""
    on_r, base_r = on[i0:], base[i0:]
    n = len(on_r)
    trans_idx = np.nonzero(on_r[1:] != on_r[:-1])[0] + 1
    trans = len(trans_idx)
    quick = int(np.sum(np.diff(trans_idx) <= QUICK)) if trans > 1 else 0
    maxw = 0
    if trans:
        for t in trans_idx:
            maxw = max(maxw, int(np.sum((trans_idx >= t) & (trans_idx < t + FLIP_WINDOW))))
    # runs
    edges = np.flatnonzero(np.diff(np.concatenate([[0], on_r.astype(int), [0]])))
    starts, ends = edges[0::2], edges[1::2] - 1
    eps = len(starts)
    short_eps = int(np.sum(ends - starts + 1 <= 3))
    gaps = starts[1:] - ends[:-1] - 1
    short_gaps = int(np.sum(gaps <= 3)) if eps > 1 else 0
    # vs base
    missed = int(np.sum(base_r & ~on_r))
    extra = int(np.sum(on_r & ~base_r))
    # entry delay per base episode
    be = np.flatnonzero(np.diff(np.concatenate([[0], base_r.astype(int), [0]])))
    bs, bend = be[0::2], be[1::2] - 1
    delays, missed_eps = [], 0
    for s, e in zip(bs, bend):
        hit = np.flatnonzero(on_r[s : e + 1])
        if len(hit):
            delays.append(int(hit[0]))
        else:
            missed_eps += 1
    # clusters: base episodes merged across off-gaps <= 10 days
    clusters = []
    for s_, e_ in zip(bs, bend):
        if clusters and s_ - clusters[-1][1] - 1 <= 10:
            clusters[-1][1] = e_
        else:
            clusters.append([s_, e_])
    missed_cl = sum(1 for s_, e_ in clusters if not on_r[s_ : e_ + 1].any())
    cl_delay = [int(np.flatnonzero(on_r[s_ : e_ + 1])[0]) for s_, e_ in clusters if on_r[s_ : e_ + 1].any()]
    # gap: design off, invalidation not met since last design-on
    gap = 0
    open_ = False
    inv_r = inval[i0:]
    for k in range(n):
        if on_r[k]:
            open_ = True
            continue
        if open_ and inv_r[k]:
            open_ = False
        if open_:
            gap += 1
    return dict(n=n, on=int(on_r.sum()), trans=trans, quick=quick, max20=maxw, eps=eps, short_eps=short_eps,
                short_gaps=short_gaps, missed=missed, extra=extra, base_eps=len(bs), missed_eps=missed_eps,
                delay_mean=(float(np.mean(delays)) if delays else float("nan")), gap=gap,
                clusters=len(clusters), missed_cl=missed_cl, cl_delay=(float(np.mean(cl_delay)) if cl_delay else float("nan")))


def fmt_table(rows, cols):
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    return "\n".join([head, sep] + ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows])


COLS = ["design", "on", "trans", "quick", "max20", "eps", "short_eps", "short_gaps", "missed", "missed_eps", "clusters", "missed_cl", "extra", "delay_mean", "gap"]


def run_single(label, close, cur, i0_list):
    close2, cur2 = close[:, None], cur[:, None]
    ma60 = sma(close, 60)[:, None]
    for rule in RULES:
        inval = invalidation_met(rule, cur2, close2, ma60)[:, 0]
        base = simulate("base", rule, cur2, close2, ma60)[:, 0]
        for tag, i0 in i0_list:
            rows = []
            for d in DESIGNS:
                on = simulate(d, rule, cur2, close2, ma60)[:, 0]
                m = metrics(on, base, cur, inval, i0)
                m["design"] = d
                if m["delay_mean"] == m["delay_mean"]:
                    m["delay_mean"] = f"{m['delay_mean']:.2f}"
                rows.append(m)
            print(f"\n#### {label} / {rule} / {tag}（評估 {rows[0]['n']} 日）\n")
            print(fmt_table(rows, COLS))


def demo_part():
    print("## A. demo 合成日線（point-in-time，540 日窗）")
    for sym, (dates, close) in demo_series().items():
        cur, peak, ws, partial = pit_drawdown(dates, close)
        first_full = int(np.argmax(~partial))
        first_valid = int(np.argmax(~np.isnan(cur)))
        run_single(sym, close, cur, [("全期（含區間不足日，口徑與線上不同）", first_valid), (f"完整區間（自 {dates[first_full]}）", first_full)])


def hand_paths():
    print("\n## B. 手工路徑（前置 60 日平盤 100，供 MA60）")
    pre = [100.0] * 60
    rng = np.random.default_rng(7)
    p1 = pre + list(np.linspace(100, 80, 16)[1:]) + list(80 * (1 + 0.012 * rng.choice([-1, 1], 40))) + list(np.linspace(80, 95, 21)[1:]) + [95.0] * 10
    p2 = pre + list(np.linspace(100, 81, 16)[1:]) + [81.0] * 10 + [79.5] + [81.0] * 10 + list(np.linspace(81, 95, 15)[1:]) + [95.0] * 10
    p3 = pre + list(np.linspace(100, 65, 21)[1:]) + list(np.linspace(65, 85, 21)[1:]) + list(85 * (1 + 0.015 * rng.choice([-1, 1], 30))) + list(np.linspace(85, 91, 11)[1:]) + [91.0] * 20
    for name, p in [("H1 −20% 附近 ±1.2% 震盪 40 日後回升到 −5%", p1), ("H2 停在 −19%，單日刺穿 −20.5%", p2), ("H3 跌到 −35% 後反彈至 −15% 附近 ±1.5% 震盪 30 日，再到 −9%", p3)]:
        close = np.array(p)
        cur = close / np.maximum.accumulate(close) - 1
        run_single(name, close, cur, [("全路徑", 0)])


def mc_part(n_paths=400, years=10, mu=0.06, seed=20261004):
    print(f"\n## C. GBM 蒙地卡羅（模型，不是資料）：每組 {n_paths} 條、每條 {years} 年（252 日/年）評估、窗 {WINDOW_BARS} 根")
    rng = np.random.default_rng(seed)
    out_rows = []
    for sigma in (0.20, 0.35, 0.60):
        Tn = WINDOW_BARS + 252 * years
        lr = rng.normal((mu - sigma**2 / 2) / 252, sigma / np.sqrt(252), size=(Tn, n_paths))
        close = 100 * np.exp(np.cumsum(lr, axis=0))
        df = pd.DataFrame(close)
        rmax = df.rolling(WINDOW_BARS, min_periods=1).max().to_numpy()
        cur = close / rmax - 1
        ma60 = df.rolling(60).mean().to_numpy()
        for rule in RULES:
            base = simulate("base", rule, cur, close, ma60)
            inval = invalidation_met(rule, cur, close, ma60)
            for d in DESIGNS:
                on = simulate(d, rule, cur, close, ma60)
                agg = {}
                for p in range(n_paths):
                    m = metrics(on[:, p], base[:, p], cur[:, p], inval[:, p], WINDOW_BARS)
                    for k, v in m.items():
                        agg.setdefault(k, []).append(v)
                py = n_paths * years
                row = dict(sigma=sigma, rule=rule, design=d,
                           on_per_yr=f"{sum(agg['on'])/py:.1f}",
                           trans_per_yr=f"{sum(agg['trans'])/py:.2f}",
                           quick_share=f"{sum(agg['quick'])/max(1,sum(agg['trans'])):.0%}",
                           eps_per_yr=f"{sum(agg['eps'])/py:.2f}",
                           short_eps_share=f"{sum(agg['short_eps'])/max(1,sum(agg['eps'])):.0%}",
                           p95_max20=int(np.percentile(agg['max20'], 95)),
                           missed_per_yr=f"{sum(agg['missed'])/py:.1f}",
                           missed_eps_share=f"{sum(agg['missed_eps'])/max(1,sum(agg['base_eps'])):.0%}",
                           extra_per_yr=f"{sum(agg['extra'])/py:.1f}",
                           delay_mean=f"{np.nanmean(agg['delay_mean']):.2f}",
                           clusters_per_yr=f"{sum(agg['clusters'])/py:.2f}",
                           missed_cl_share=f"{sum(agg['missed_cl'])/max(1,sum(agg['clusters'])):.1%}",
                           cl_delay=f"{np.nanmean(agg['cl_delay']):.2f}",
                           gap_per_yr=f"{sum(agg['gap'])/py:.1f}")
                out_rows.append(row)
    print(fmt_table(out_rows, list(out_rows[0].keys())))


if __name__ == "__main__":
    print("欄位：on=命中日數；trans=命中狀態翻轉次數；quick=距上次翻轉≤5日的翻轉數；max20=任一20交易日內最多翻轉數；"
          "eps=命中段數；short_eps=≤3日的命中段；short_gaps=命中段之間≤3日的空檔數；missed=基準命中而此設計未命中日數；"
          "missed_eps=整段基準命中被完全略過的段數；extra=此設計命中但目前回撤未深於門檻的日數（explanation『已深於』字面不成立）；"
          "delay_mean=基準命中段起點到此設計首次命中的平均延遲（交易日）；gap=規則已不命中但失效條件尚未達成的日數；clusters=基準命中段以≤10日空檔合併後的『事件』數；missed_cl=此設計整個事件都未命中的事件數；cl_delay=事件起點到此設計首次命中的平均延遲。")
    demo_part()
    hand_paths()
    mc_part()
