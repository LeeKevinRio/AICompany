"""F2-B cumulative withdrawal simulation (synthetic only; v0.5, risk v0.4 check item 4).

Single object (index-like), phase-0 non-overlapping samples of the same GARCH synthetic series,
same toy skill model and same joint criterion as mc_v02.py / mc_f2.py (imported from mc_v02_lib.py).
alpha* = 0.05/48 (m_eff = 8, K = 6). Checkpoints 30, 60, 100, 150, 250, 500.
F2-B as frozen in prereg v0.4 section 4.5:
  cond 1: from N_MIN=30, two ADJACENT checkpoints (rolling) both with point estimate <= any required
          baseline -> withdraw at the later checkpoint;
  cond 2: at n=150, status != better_than_baseline -> withdraw.
No voids, coverage 100% (so condition (f) and W never bind). Re-listing after withdrawal is not simulated.
Display assumed to start at the first record; years = n * h / 245 (no lost dates).
These results must not be used to change the frozen option set (F2-A / F2-B, checkpoints, 150/250, 5%).
"""
import runpy
import numpy as np

ns = runpy.run_path("mc_v02_lib.py")
build, evaluate = ns["build"], ns["evaluate"]
rng = np.random.default_rng(20261018)
A = 0.05 / 48
CPS = (30, 60, 100, 150, 250, 500)
TRIALS = 2000


def point_le(t, model, base):
    mode_c = (1, 0, -1)[int(np.argmax([np.mean(t == c) for c in (1, 0, -1)]))]
    bs = [np.mean(v == t) for v in base.values()] + [np.mean(t == 0), np.mean(t == mode_c)]
    return np.mean(model == t) <= max(bs)


for h in (3, 5):
    truth, base = build(h)
    shares = np.array([np.mean(truth == c) for c in (1, 0, -1)])
    for w in (0.0, 0.15, 0.25):
        out = {"c1@60": 0, "c1@100": 0, "c1@150": 0, "c2@150": 0, "survive150": 0,
               "c1@250": 0, "c1@500": 0, "survive500": 0}
        shown_n = []
        for _ in range(TRIALS):
            s = rng.integers(0, len(truth) - CPS[-1])
            t = truth[s:s + CPS[-1]]
            bb = {k: v[s:s + CPS[-1]] for k, v in base.items()}
            model = np.where(rng.random(CPS[-1]) < w, t, rng.choice([1, 0, -1], size=CPS[-1], p=shares))
            le = {n: point_le(t[:n], model[:n], {k: v[:n] for k, v in bb.items()}) for n in CPS}
            withdrawn_at = None
            for a, b in zip(CPS[:-1], CPS[1:]):
                if le[a] and le[b]:
                    withdrawn_at = (b, "c1"); break
                if b == 150:
                    better = evaluate(t[:150], model[:150], {k: v[:150] for k, v in bb.items()}, A)
                    if not better:
                        withdrawn_at = (150, "c2"); break
            if withdrawn_at is None:
                out["survive500"] += 1; out["survive150"] += 1; shown_n.append(500)
                continue
            n_w, why = withdrawn_at
            key = f"{why}@{n_w}"
            out[key] += 1
            if n_w > 150:
                out["survive150"] += 1
            shown_n.append(n_w)
        shown_n = np.array(shown_n)
        cum60 = out["c1@60"] / TRIALS
        cum100 = cum60 + out["c1@100"] / TRIALS
        cum150 = cum100 + (out["c1@150"] + out["c2@150"]) / TRIALS
        yrs = shown_n * h / 245
        print(f"h={h} w={w}: cum_withdraw by60={cum60:.3f} by100={cum100:.3f} by150={cum150:.3f} "
              f"[c1@150={out['c1@150']/TRIALS:.3f} c2@150={out['c2@150']/TRIALS:.3f}] "
              f"survive_past150={out['survive150']/TRIALS:.4f} "
              f"(later: c1@250={out['c1@250']/TRIALS:.4f} c1@500={out['c1@500']/TRIALS:.4f} still_shown@500={out['survive500']/TRIALS:.4f}) "
              f"display_n median={np.median(shown_n):.0f} max={shown_n.max():.0f} "
              f"display_years median={np.median(yrs):.2f} mean={yrs.mean():.2f} max={yrs.max():.2f}")
