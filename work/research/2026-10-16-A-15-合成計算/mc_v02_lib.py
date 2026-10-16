"""v0.2 Monte Carlo (synthetic only).

Part 1: power of the joint v0.2 criterion (b)+(c)+(d) for a SINGLE object (index-like), against
        required baselines B1, B2, B6, B7, B8, on phase-0 non-overlapping samples of the GARCH series.
        Synthetic 'model': predicts the truth with prob w, otherwise an independent draw from the
        full-sample class shares. This is a toy skill model, not a rule.
        (b) one-sided Wilson lower bound at alpha* > each baseline's hit rate on the same sample
        (c) exact one-sided McNemar (binomial on discordant pairs) p < alpha* vs each baseline
        (d) model macro recall > 1/3 and > each baseline's macro recall
        (e) coverage assumed 100% here.
Part 2: calendar time to reach n countable phase-0 samples with iid or clustered lost dates.
"""
import math
import numpy as np
from statistics import NormalDist

ND = NormalDist()
rng = np.random.default_rng(20261016)
EPS = 1e-12; K = 0.43

# ---- same synthetic generator as v0.1 / label_sim_v02 ----
g = np.random.default_rng(20261015)
N = 245 * 400
omega, alpha, beta, nu, mu = 1.2e-6, 0.08, 0.91, 5.0, 0.0003
r = np.empty(N); s2 = omega / (1 - alpha - beta)
for i in range(N):
    z = g.standard_t(nu) / np.sqrt(nu / (nu - 2))
    r[i] = mu + np.sqrt(s2) * z
    s2 = omega + alpha * (r[i] - mu) ** 2 + beta * s2
logp = np.concatenate([[0.0], np.cumsum(r)])
W = 60
cs = np.cumsum(np.concatenate([[0.0], r])); cs2 = np.cumsum(np.concatenate([[0.0], r * r]))
def sig(t):
    s = cs[t] - cs[t - W]; q = cs2[t] - cs2[t - W]
    return np.sqrt((q - s * s / W) / (W - 1))
def lab(z):
    return np.where(z > K + EPS, 1, np.where(z < -K - EPS, -1, 0))


def binom_sf_ge(k, n):  # P(X >= k), X~Bin(n, 0.5)
    if n == 0:
        return 1.0
    tot = 0.0
    for j in range(k, n + 1):
        tot += math.comb(n, j)
    return tot / 2 ** n


def wilson_low(k, n, a):
    z = ND.inv_cdf(1 - a); p = k / n; d = 1 + z * z / n
    return (p + z * z / (2 * n)) / d - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d


def macro(pred, t):
    vals = [np.mean(pred[t == c] == c) for c in (1, 0, -1) if np.any(t == c)]
    return float(np.mean(vals))


def build(h):
    T = np.arange(W + h, N - h)
    truth = lab((logp[T + h] - logp[T]) / (sig(T) * np.sqrt(h)))
    past = logp[T] - logp[T - h]
    b1 = lab(past / (sig(T - h) * np.sqrt(h)))
    b8 = np.sign(past).astype(int)
    L = len(truth)
    cnt = {c: np.cumsum(np.concatenate([[0], (truth == c).astype(int)])) for c in (1, 0, -1)}
    b2 = np.zeros(L, int)
    for i in range(250 + h, L):
        hi = i - h + 1; lo = hi - 250
        c_ = {c: cnt[c][hi] - cnt[c][lo] for c in (1, 0, -1)}
        best = max(c_.values())
        for c in (0, 1, -1):
            if c_[c] == best:
                b2[i] = c; break
    start = 250 + h
    idx = np.arange(start, L, h)  # phase-0 grid of the long series
    return truth[idx], {"B1": b1[idx], "B2": b2[idx], "B8": b8[idx]}


def evaluate(t, model, base, a):
    n = len(t)
    mh = model == t
    k = int(mh.sum())
    shares = [np.mean(t == c) for c in (1, 0, -1)]
    mode_c = (1, 0, -1)[int(np.argmax(shares))]
    bases = dict(base)
    bases["B6"] = np.zeros_like(t)
    bases["B7"] = np.full_like(t, mode_c)
    lw = wilson_low(k, n, a)
    m_macro = macro(model, t)
    if m_macro <= 1 / 3:
        return False
    for name, bp in bases.items():
        bh = bp == t
        if not lw > bh.mean():
            return False
        n10 = int(np.sum(mh & ~bh)); n01 = int(np.sum(~mh & bh))
        if binom_sf_ge(n10, n10 + n01) >= a:
            return False
        if not m_macro > macro(bp, t):
            return False
    return True


