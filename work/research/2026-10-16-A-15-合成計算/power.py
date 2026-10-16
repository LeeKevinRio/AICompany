"""Wilson lower-bound thresholds and approximate power, pure arithmetic."""
import math
from statistics import NormalDist

def wilson_low(k, n, alpha_one_sided):
    z = NormalDist().inv_cdf(1 - alpha_one_sided)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - s

def min_k(n, b, a):
    for k in range(n + 1):
        if wilson_low(k, n, a) > b:
            return k
    return None

alphas = {"0.05": 0.05, "0.01": 0.01, "0.05/30": 0.05 / 30}
for b in (0.35, 0.40):
    print(f"--- baseline b={b} : minimal observed hit rate k/n so that Wilson lower bound > b ---")
    for n in (30, 60, 100, 150, 250, 500):
        row = []
        for name, a in alphas.items():
            k = min_k(n, b, a)
            row.append(f"a={name}: {k}/{n}={k/n:.3f}" if k is not None else f"a={name}: none")
        print(f"n={n:<4} " + " | ".join(row))

print("--- n needed for 80% power (normal approx), one-sample vs fixed baseline ---")
for b in (0.35, 0.40):
    for d in (0.03, 0.05, 0.10):
        p = b + d
        for name, a in alphas.items():
            za = NormalDist().inv_cdf(1 - a); zb = NormalDist().inv_cdf(0.8)
            n = ((za * math.sqrt(b * (1 - b)) + zb * math.sqrt(p * (1 - p))) / d) ** 2
            print(f"b={b} true={p:.2f} a={name:<7} n={math.ceil(n):>5}  years(3d,81.7/yr)={n/81.7:5.1f}  years(5d,49/yr)={n/49:5.1f}")
