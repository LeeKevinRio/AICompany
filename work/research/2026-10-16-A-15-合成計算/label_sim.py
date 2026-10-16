"""Synthetic-only simulation: label class shares vs threshold k, baseline hit rates under a null.

No real market data is read. GARCH(1,1) with Student-t(5) innovations, daily vol ~1.1%,
small positive drift. Purpose: sanity-check pre-registration choices, not to fit anything.
"""
import numpy as np

rng = np.random.default_rng(20261015)
N = 245 * 400  # ~400 synthetic years
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
def sigma_at(t):  # std of the W returns ending at price index t (returns r[t-W..t-1])
    s = csum[t] - csum[t - W]; s2_ = csum2[t] - csum2[t - W]
    var = (s2_ - s * s / W) / (W - 1)
    return np.sqrt(var)

def labels(h, k):
    T = np.arange(W + h, N - h)  # need sigma at T-h too (for persistence)
    sig = sigma_at(T)
    fwd = (logp[T + h] - logp[T]) / (sig * np.sqrt(h))
    lab = np.where(fwd >= k, 1, np.where(fwd <= -k, -1, 0))
    sigp = sigma_at(T - h)
    past = (logp[T] - logp[T - h]) / (sigp * np.sqrt(h))
    plab = np.where(past >= k, 1, np.where(past <= -k, -1, 0))
    return T, lab, plab

print("== class shares (bull/range/bear) and null baseline hit rates ==")
for h in (3, 5):
    for k in (0.3, 0.43, 0.5, 0.6, 0.75, 1.0):
        T, lab, plab = labels(h, k)
        shares = [np.mean(lab == c) for c in (1, 0, -1)]
        persist = np.mean(lab == plab)
        # majority over trailing 250 realized labels (labels whose window ended by T)
        # approximate with rolling counts on label index; realized at T means T'+h<=T -> lag h
        L = len(lab); maj = np.zeros(L, dtype=int)
        cnt = {c: np.cumsum(np.concatenate([[0], (lab == c).astype(int)])) for c in (1, 0, -1)}
        ok = np.zeros(L, bool)
        for i in range(250 + h, L):
            hi = i - h + 1; lo = hi - 250
            cs = {c: cnt[c][hi] - cnt[c][lo] for c in (1, 0, -1)}
            best = max(cs.values())
            # tie-break: range > bull > bear
            for c in (0, 1, -1):
                if cs[c] == best:
                    maj[i] = c; break
            ok[i] = True
        majhit = np.mean(lab[ok] == maj[ok])
        majshare = [np.mean(maj[ok] == c) for c in (1, 0, -1)]
        print(f"h={h} k={k:<4} shares={[round(x,3) for x in shares]} persist_hit={persist:.3f} majority_hit={majhit:.3f} majority_pred_shares={[round(x,3) for x in majshare]}")
