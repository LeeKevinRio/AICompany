"""v0.2 Wilson thresholds, normal-approx power, and calendar-time conversion (arithmetic only).

alpha* = 0.05 / (m * K_c). m planning values: 6 (forward claims only) and 8 (+ 2 index replay claims).
K_c: index/stock 6 checkpoints, sector 3 checkpoints.
Calendar: 245 trading days / year (assumption, same as sector methodology).
Lost-date rate g: fraction of phase-0 grid dates that yield no countable sample (gap, late, all-insufficient).
"""
import math
from statistics import NormalDist

ND = NormalDist()
DAYS = 245


def wilson_low(k, n, a):
    z = ND.inv_cdf(1 - a); p = k / n; d = 1 + z * z / n
    return (p + z * z / (2 * n)) / d - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d


def min_k(n, b, a):
    for k in range(n + 1):
        if wilson_low(k, n, a) > b:
            return k
    return None


A = {
    "0.05(ref)": 0.05,
    "m6 idx/stk 0.05/36": 0.05 / 36,
    "m8 idx/stk 0.05/48": 0.05 / 48,
    "m6 sector 0.05/18": 0.05 / 18,
    "m8 sector 0.05/24": 0.05 / 24,
}
print("== minimal k/n with one-sided Wilson lower bound > b ==")
for b in (0.35, 0.40):
    for n in (30, 60, 100, 150, 250, 500):
        cells = []
        for name, a in A.items():
            if "sector" in name and n not in (150, 250, 500):
                continue
            k = min_k(n, b, a)
            cells.append(f"{name}: {k}/{n}={k/n:.3f}")
        print(f"b={b} n={n}: " + " | ".join(cells))

print("== n for 80% power, normal approx, vs fixed b ==")
for b in (0.35, 0.40):
    for d in (0.03, 0.05, 0.10):
        p = b + d
        for name, a in A.items():
            za = ND.inv_cdf(1 - a); zb = ND.inv_cdf(0.8)
            n = math.ceil(((za * math.sqrt(b * (1 - b)) + zb * math.sqrt(p * (1 - p))) / d) ** 2)
            yrs = {h: [n * h / (DAYS * (1 - g)) for g in (0.0, 0.2)] for h in (3, 5)}
            print(f"b={b} p={p:.2f} {name:<20} n={n:>5}  3d yrs(g=0/0.2)={yrs[3][0]:5.1f}/{yrs[3][1]:5.1f}"
                  f"  5d yrs={yrs[5][0]:5.1f}/{yrs[5][1]:5.1f}")

print("== calendar years to reach n non-overlap samples: years = W/245 + n*h/(245*(1-g)) ==")
for n in (30, 60, 100, 150, 250):
    for h in (3, 5):
        row = []
        for W in (0, 121):
            for g in (0.0, 0.1, 0.2, 0.3):
                row.append(f"W{W},g{g}: {W/DAYS + n*h/(DAYS*(1-g)):.2f}")
        print(f"n={n} h={h}: " + " | ".join(row))
