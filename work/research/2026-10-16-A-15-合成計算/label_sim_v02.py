"""dirdef v0.2 synthetic check (synthetic data only; no DB, no network, no app.* import).

Same GARCH(1,1)+t(5) generator and seed as v0.1 label_sim.py so numbers are comparable.
K is FIXED at 0.43 (not searched). Boundary v0.2: strict '>' with eps, ties -> range.
Baselines:
  B1  persistence (3-class, same K, sigma at T-h)
  B2  rolling majority of last 250 realized labels (T'+h <= T), tie range>bull>bear, needs >=120
  B6  always range
  B7  climatology, oracle mode: constant = most frequent realized class in the evaluated sample
  B7r climatology, random draw by realized shares: expected hit = sum(p^2) (reference only)
  B8  sign persistence (ADR-0025 D-6.5 (c) literal): sign of past h-day log return
Reported on the phase-0 non-overlapping subsample and on the full daily sample.
"""
import numpy as np

EPS = 1e-12
K = 0.43
rng = np.random.default_rng(20261015)
N = 245 * 400
omega, alpha, beta = 1.2e-6, 0.08, 0.91
nu = 5.0
mu = 0.0003
r = np.empty(N); s2 = omega / (1 - alpha - beta)
for i in range(N):
    z = rng.standard_t(nu) / np.sqrt(nu / (nu - 2))
    r[i] = mu + np.sqrt(s2) * z
    s2 = omega + alpha * (r[i] - mu) ** 2 + beta * s2
logp = np.concatenate([[0.0], np.cumsum(r)])
W = 60
csum = np.cumsum(np.concatenate([[0.0], r])); csum2 = np.cumsum(np.concatenate([[0.0], r * r]))


def sigma_at(t):
    s = csum[t] - csum[t - W]; q = csum2[t] - csum2[t - W]
    return np.sqrt((q - s * s / W) / (W - 1))


def lab_of(z):
    return np.where(z > K + EPS, 1, np.where(z < -K - EPS, -1, 0))


def macro_recall(pred, truth):
    out = []
    for c in (1, 0, -1):
        m = truth == c
        out.append(np.mean(pred[m] == c) if m.any() else np.nan)
    return float(np.nanmean(out))


def run(h):
    T = np.arange(W + h, N - h)
    sig = sigma_at(T)
    truth = lab_of((logp[T + h] - logp[T]) / (sig * np.sqrt(h)))
    past = logp[T] - logp[T - h]
    b1 = lab_of(past / (sigma_at(T - h) * np.sqrt(h)))
    b8 = np.sign(past).astype(int)
    L = len(truth)
    cnt = {c: np.cumsum(np.concatenate([[0], (truth == c).astype(int)])) for c in (1, 0, -1)}
    b2 = np.zeros(L, int); ok = np.zeros(L, bool)
    for i in range(250 + h, L):
        hi = i - h + 1; lo = hi - 250
        cs = {c: cnt[c][hi] - cnt[c][lo] for c in (1, 0, -1)}
        best = max(cs.values())
        for c in (0, 1, -1):
            if cs[c] == best:
                b2[i] = c; break
        ok[i] = True
    res = {}
    for name, sel in (("phase0_nonoverlap", np.arange(L)[ok][::h]), ("daily_all", np.arange(L)[ok])):
        t = truth[sel]
        shares = [float(np.mean(t == c)) for c in (1, 0, -1)]
        mode_c = (1, 0, -1)[int(np.argmax(shares))]
        preds = {"B1": b1[sel], "B2": b2[sel], "B6": np.zeros_like(t),
                 "B7": np.full_like(t, mode_c), "B8": b8[sel]}
        hits = {k: float(np.mean(v == t)) for k, v in preds.items()}
        mrec = {k: macro_recall(v, t) for k, v in preds.items()}
        hits["B7r"] = float(sum(s * s for s in shares))
        res[name] = (len(sel), shares, hits, mrec)
    return res


for h in (3, 5):
    for name, (n, shares, hits, mrec) in run(h).items():
        print(f"h={h} {name} n={n} shares(bull/range/bear)={[round(x,3) for x in shares]}")
        print("   hit:", {k: round(v, 3) for k, v in hits.items()})
        print("   macro_recall:", {k: round(v, 3) for k, v in mrec.items()})
