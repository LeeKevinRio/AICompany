"""ADR-0025 F-2 reading check (synthetic only). Reuses mc_v02 generator/criteria by import-free copy.
Reading A (conservative): withdraw if NOT better_than_baseline at both n=30 and n=60.
Reading B: withdraw only if point estimate <= max required baseline at both n=30 and n=60.
alpha* = 0.05/48. Same toy skill model as mc_v02 (w = prob of copying truth).
"""
import runpy, numpy as np
ns = runpy.run_path("mc_v02_lib.py")
build, evaluate = ns["build"], ns["evaluate"]
rng = np.random.default_rng(20261017)
a = 0.05 / 48
for h in (3, 5):
    truth, base = build(h)
    shares = np.array([np.mean(truth == c) for c in (1, 0, -1)])
    for w in (0.0, 0.15, 0.25):
        A = B = 0; trials = 2000
        for _ in range(trials):
            s = rng.integers(0, len(truth) - 60)
            t = truth[s:s+60]; bb = {k: v[s:s+60] for k, v in base.items()}
            model = np.where(rng.random(60) < w, t, rng.choice([1, 0, -1], size=60, p=shares))
            def point_le(n):
                tt = t[:n]; m = model[:n]
                mode_c = (1, 0, -1)[int(np.argmax([np.mean(tt == c) for c in (1, 0, -1)]))]
                bs = [np.mean(v[:n] == tt) for v in bb.values()] + [np.mean(tt == 0), np.mean(tt == mode_c)]
                return np.mean(m == tt) <= max(bs)
            better30 = evaluate(t[:30], model[:30], {k: v[:30] for k, v in bb.items()}, a)
            better60 = evaluate(t, model, bb, a)
            A += (not better30) and (not better60)
            B += point_le(30) and point_le(60)
        print(f"h={h} w={w}: P(withdraw | reading A)={A/trials:.3f}  P(withdraw | reading B)={B/trials:.3f}")
