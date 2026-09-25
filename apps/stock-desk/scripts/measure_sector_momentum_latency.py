"""Non-merge-gate P95 latency measurement for ``GET /api/sectors/momentum`` (ADR-0012 T-34, C-51).

## Why this script exists

ADR-0012 D-10 / PRD FR-8 requires the sector-momentum endpoint to answer
within P95 <= 2 seconds even as the market DB accumulates ~100,000 PIT
``pit_snapshot_runs`` rows (warm-up: ~1,100 symbols x 80 warm-up days, plus
the four forward-PIT capture kinds). T-34 deliberately keeps this out of CI
("CI 不做計時斷言") -- wall-clock latency depends on the disk, the machine
and how big the operator's actual market DB has grown, none of which CI's
sandbox represents honestly. This script is the *operator-run* replacement:
it is meant to be executed by hand on the real deployment host (see the
deployment manual, `apps/stock-desk/docs/族群動能-主機部署手冊.md`), not
wired into `pytest` or the CI workflow.

## What it does and does not do

Does:
- Sends repeated ``GET {base-url}/api/sectors/momentum?market={market}``
  requests to an already-running backend process (no token needed -- the
  endpoint is unauthenticated, ADR-0012 D-10) and records wall-clock
  round-trip time per request.
- Reports min / mean / P50 / P95 / P99 / max, the HTTP status code
  distribution, and how many requests exceeded the budget.
- Exits non-zero when the measured P95 exceeds ``--budget-seconds``
  (default 2.0, the PRD FR-8 figure), so it is usable as a manual gate even
  though it is not an automated one.

Does not:
- Does not start or stop the backend process, seed data, or run the
  attestation/warm-up CLI -- run those first (deployment manual).
- Does not assert anything about *correctness* of the response body, only
  latency; `tests/test_api_sectors.py` (CI) already covers correctness.
- Does not require network egress: it only talks to a local/LAN backend URL
  the operator supplies.

## Usage (see the deployment manual for the full walkthrough)

```powershell
# from apps/stock-desk/backend, with the backend already running
uv run python ..\\scripts\\measure_sector_momentum_latency.py
```

```bash
# Linux/macOS, non-default host/port, more samples
uv run python ../scripts/measure_sector_momentum_latency.py \
    --base-url http://127.0.0.1:8000 --requests 200 --warmup-requests 5
```
"""

from __future__ import annotations

import argparse
import statistics
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_PATH = "/api/sectors/momentum"
#: PRD FR-8 / ADR-0012 D-10.
DEFAULT_BUDGET_SECONDS = 2.0


@dataclass(frozen=True)
class Sample:
    """One request's outcome."""

    elapsed_seconds: float
    status_code: int | None
    error: str | None


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile (0 <= pct <= 100); ``sorted_values`` must be sorted ascending."""
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = pct / 100 * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def run_once(client: httpx.Client, url: str) -> Sample:
    start = time.perf_counter()
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        elapsed = time.perf_counter() - start
        return Sample(elapsed_seconds=elapsed, status_code=None, error=str(exc))
    elapsed = time.perf_counter() - start
    return Sample(elapsed_seconds=elapsed, status_code=response.status_code, error=None)


def measure(
    *,
    base_url: str,
    path: str,
    market: str,
    requests: int,
    warmup_requests: int,
    timeout_seconds: float,
) -> list[Sample]:
    url = f"{base_url.rstrip('/')}{path}?market={market}"
    samples: list[Sample] = []
    with httpx.Client(timeout=timeout_seconds) as client:
        for _ in range(warmup_requests):
            run_once(client, url)  # discarded: first hits may pay one-off costs (e.g. cold cache)
        for _ in range(requests):
            samples.append(run_once(client, url))
    return samples


def summarize(samples: Sequence[Sample], *, budget_seconds: float) -> tuple[str, bool]:
    if not samples:
        return "no samples collected", False
    elapsed = sorted(sample.elapsed_seconds for sample in samples)
    statuses = Counter(sample.status_code for sample in samples)
    errors = [sample.error for sample in samples if sample.error is not None]
    p95 = _percentile(elapsed, 95)
    within_budget = p95 <= budget_seconds and not errors

    lines = [
        f"samples: {len(samples)}",
        f"status codes: {dict(statuses)}",
        f"errors: {len(errors)}" + (f" (first: {errors[0]})" if errors else ""),
        f"min:    {min(elapsed) * 1000:.1f} ms",
        f"mean:   {statistics.fmean(elapsed) * 1000:.1f} ms",
        f"p50:    {_percentile(elapsed, 50) * 1000:.1f} ms",
        f"p95:    {p95 * 1000:.1f} ms  (budget: {budget_seconds * 1000:.0f} ms, "
        f"PRD FR-8 / ADR-0012 D-10)",
        f"p99:    {_percentile(elapsed, 99) * 1000:.1f} ms",
        f"max:    {max(elapsed) * 1000:.1f} ms",
        f"over budget: {sum(1 for value in elapsed if value > budget_seconds)} / {len(elapsed)}",
        "RESULT: " + ("PASS" if within_budget else "FAIL"),
    ]
    return "\n".join(lines), within_budget


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL")
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--market", default="TW")
    parser.add_argument("--requests", type=int, default=50, help="Timed request count")
    parser.add_argument(
        "--warmup-requests",
        type=int,
        default=3,
        help="Untimed requests sent first, to avoid measuring one-off cold-start cost",
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="Per-request timeout")
    parser.add_argument(
        "--budget-seconds",
        type=float,
        default=DEFAULT_BUDGET_SECONDS,
        help="P95 budget; exit code is non-zero when exceeded (PRD FR-8)",
    )
    args = parser.parse_args(argv)

    samples = measure(
        base_url=args.base_url,
        path=args.path,
        market=args.market,
        requests=args.requests,
        warmup_requests=args.warmup_requests,
        timeout_seconds=args.timeout_seconds,
    )
    report, within_budget = summarize(samples, budget_seconds=args.budget_seconds)
    print(report)
    return 0 if within_budget else 1


if __name__ == "__main__":
    raise SystemExit(main())
