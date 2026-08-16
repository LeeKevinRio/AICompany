"""Shared, hand-rolled HTTP client wrapper for all data-layer adapters.

Deliberately does not depend on ``tenacity`` or similar retry libraries per
the task's constraint -- rate limiting and exponential backoff are both
implemented directly on top of ``httpx``.

Every adapter should build one ``RateLimitedClient`` and reuse it for the
lifetime of the process so the rate limiter actually throttles traffic
across calls instead of resetting per request.

Fast-fail tuning (穩定與速度衝刺 dispatch, 2026-08-13, Lane 1)
----------------------------------------------------------------
Every constant below is the single place the whole data layer's "how long
can one unreachable source hold up a request" budget is set -- no adapter
overrides ``timeout``/``max_retries``/``backoff_seconds`` (see
``app/data/providers/*.py``), so changing these numbers here changes the
budget everywhere at once.

Before this change the defaults were ``timeout=10.0`` (applied uniformly to
connect *and* read) with ``max_retries=3`` and ``backoff_seconds=(1, 2, 4)``,
which gives a worst case of ``4 attempts * 10s + (1+2+4)s = 47s`` for a
*single* HTTP call when a host is completely unreachable. Chained across the
TW ladder's three providers (twse -> tpex -> finmind, see
``app/api/deps.py``) that is up to ~141s, and up to ~94s for the US ladder's
two providers (alpha_vantage -> yfinance) -- both far above the "約 58s"
figure on record, and both squarely responsible for a page load that looks
hung. (twse/tpex fetch one calendar month per HTTP call for a multi-month
range, but a ``TransportError`` aborts their whole per-month loop on the
first failure -- see ``TwseAdapter``/``TpexAdapter`` -- so a longer lookback
window does not multiply this further.)

The fix splits the single ``timeout`` into a short **connect** timeout and a
more generous **read** timeout, and shrinks the retry budget:

- ``DEFAULT_CONNECT_TIMEOUT_SECONDS`` is kept short: a host that is truly
  unreachable (down, firewalled, DNS black hole) fails the TCP/TLS handshake
  itself -- waiting many seconds at THAT stage buys nothing, because a host
  that cannot be connected to within a couple of seconds will not become
  reachable later in the same request. This is what makes "unreachable"
  fail fast.
- ``DEFAULT_READ_TIMEOUT_SECONDS`` stays comparatively generous: a host that
  IS reachable but merely slow to answer (e.g. TWSE/TPEx under load) is a
  *different* failure mode this task must not touch -- the success path (and
  the "reachable but slow" path) must keep behaving as before, only the
  "cannot even connect" path gets shorter.
- ``DEFAULT_MAX_RETRIES`` drops from 3 to 1 (2 attempts total): a host that
  fails to connect once is very unlikely to start accepting connections
  again a few seconds later within the same request, so extra retries above
  the first mostly add wait time rather than a real chance of success. One
  retry is kept (not zero) so a single transient blip is still absorbed, per
  the data-source-integration skill's "retry has bounded exponential
  backoff" requirement.
- ``DEFAULT_BACKOFF_SECONDS`` shrinks to match (one interval instead of
  three), for the same reason.

New worst case for one unreachable-host HTTP call:
``2 attempts * 2.0s connect + 1.0s backoff = 5.0s``. Chained: TW ladder
(3 providers) ~15s, US ladder (2 providers) ~10s -- see
:func:`estimate_unreachable_chain_worst_case_seconds`, which is the single
function both production code and tests can call to keep this number
honest as the constants evolve, instead of restating the arithmetic in
multiple places.

This is a request-scoped change only: nothing here is cached or shared
across requests (no circuit breaker, no persisted "this host is down"
state), so every new request gets its own full, deterministic attempt
budget and stays reproducible in tests.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from types import TracebackType

import httpx

logger = logging.getLogger(__name__)

#: Short on purpose -- see module docstring "Fast-fail tuning" above. Governs
#: only the TCP/TLS connect phase, i.e. how long we wait to find out a host
#: cannot be reached at all.
DEFAULT_CONNECT_TIMEOUT_SECONDS = 2.0
#: More generous than the connect timeout on purpose -- a reachable-but-slow
#: host must keep succeeding like it did before this change; only the
#: "cannot connect at all" path was shortened.
#:
#: Why 8.0 (品質債清償批 dispatch, 2026-08-16, D5①): the pre-split default
#: was a uniform 10s covering connect *and* read, and slow-but-successful
#: sources (TWSE/TPEx under load) spend that budget in the read phase, after
#: the handshake. 8s keeps most of that former allowance for exactly that
#: phase, while the per-attempt ceiling (2s connect + 8s read) stays at the
#: old 10s -- so relative to the pre-split behaviour this change can only
#: shorten a request, never lengthen it, and a source that used to answer
#: in time still does.
#:
#: The reachable-but-slow boundary itself ("a response arriving just under
#: 8s still succeeds") is deliberately NOT unit-tested: httpx enforces read
#: timeouts inside the transport layer (httpcore) against the real socket
#: clock, and ``httpx.MockTransport`` -- this suite's only transport --
#: bypasses that layer entirely and never applies the ``timeout`` config, so
#: a mock-based boundary test would pass no matter what value this constant
#: held and would therefore assert nothing. The injectable ``sleep_fn`` fake
#: clock (see ``tests/test_fast_fail.py``) reaches only this wrapper's own
#: waits (throttle and backoff), not httpx's internal deadline. Exercising
#: the boundary for real would require a live socket server stalling ~8s of
#: wall clock per case -- a slow test of httpx itself rather than of this
#: module -- so the trade-off is recorded here instead of as a test.
DEFAULT_READ_TIMEOUT_SECONDS = 8.0
#: ``httpx.Client(timeout=...)`` accepts either a single float (applied to
#: every phase) or an ``httpx.Timeout`` with per-phase values; write/pool are
#: set to match connect/read respectively since neither adapter in this data
#: layer streams a request body or shares a connection pool across hosts.
DEFAULT_TIMEOUT = httpx.Timeout(
    connect=DEFAULT_CONNECT_TIMEOUT_SECONDS,
    read=DEFAULT_READ_TIMEOUT_SECONDS,
    write=DEFAULT_READ_TIMEOUT_SECONDS,
    pool=DEFAULT_CONNECT_TIMEOUT_SECONDS,
)
DEFAULT_MAX_RETRIES = 1
DEFAULT_BACKOFF_SECONDS: tuple[float, ...] = (1.0,)


def estimate_unreachable_chain_worst_case_seconds(
    provider_count: int,
    *,
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_seconds: Sequence[float] = DEFAULT_BACKOFF_SECONDS,
) -> float:
    """Upper bound, in seconds, on how long a ``provider_count``-deep ladder
    can take when every source is completely unreachable.

    A host that never completes the TCP/TLS handshake never reaches the read
    phase, so only ``connect_timeout_seconds`` (not the read timeout) bounds
    each attempt here -- this deliberately models the "unreachable" scenario
    this task targets, not the separate "reachable but slow to answer" one.
    Each provider gets ``max_retries + 1`` attempts plus every backoff sleep
    between them; the ladder's total is simply that summed once per provider,
    since :class:`MarketDataService` tries each rung strictly in sequence
    (see ``app/data/service.py``).
    """
    per_provider = (max_retries + 1) * connect_timeout_seconds + sum(
        backoff_seconds[:max_retries]
    )
    return provider_count * per_provider


class RateLimitedClient:
    """``httpx.Client`` wrapper adding client-side rate limiting and retry.

    - Rate limit: a minimum interval is enforced between consecutive
      requests issued through this client (a minimal "token bucket of one").
    - Retry: only 5xx responses and transport-level errors (connection
      refused, timeout, DNS failure, ...) are retried, never 4xx responses
      (those are the caller's problem, e.g. bad params or bad credentials).
    - Retries are capped and use exponential backoff with a fixed schedule
      so behaviour is deterministic and easy to unit test.
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
        min_interval_seconds: float = 0.0,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: Sequence[float] = DEFAULT_BACKOFF_SECONDS,
        transport: httpx.BaseTransport | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._min_interval_seconds = min_interval_seconds
        self._max_retries = max_retries
        self._backoff_seconds = tuple(backoff_seconds)
        self._sleep_fn = sleep_fn
        self._last_request_monotonic: float | None = None
        self._lock = threading.Lock()

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Issue a GET request, throttled and retried per this client's policy."""
        return self._request_with_retry("GET", url, params=params, headers=headers)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RateLimitedClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _throttle(self) -> None:
        """Block until at least ``min_interval_seconds`` has passed since the last request."""
        with self._lock:
            now = time.monotonic()
            if self._last_request_monotonic is not None:
                elapsed = now - self._last_request_monotonic
                remaining = self._min_interval_seconds - elapsed
                if remaining > 0:
                    self._sleep_fn(remaining)
            self._last_request_monotonic = time.monotonic()

    def _backoff_for_attempt(self, attempt: int) -> float:
        index = min(attempt, len(self._backoff_seconds) - 1)
        return self._backoff_seconds[index]

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
    ) -> httpx.Response:
        last_transport_error: httpx.TransportError | None = None
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                response = self._client.request(method, url, params=params, headers=headers)
            except httpx.TransportError as exc:
                last_transport_error = exc
                if attempt < self._max_retries:
                    logger.warning(
                        "transport error on attempt %d/%d for %s: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        url,
                        exc,
                    )
                    self._sleep_fn(self._backoff_for_attempt(attempt))
                    continue
                raise
            if response.status_code >= 500 and attempt < self._max_retries:
                logger.warning(
                    "server error %d on attempt %d/%d for %s",
                    response.status_code,
                    attempt + 1,
                    self._max_retries + 1,
                    url,
                )
                self._sleep_fn(self._backoff_for_attempt(attempt))
                continue
            return response
        if last_transport_error is not None:  # pragma: no cover - defensive
            raise last_transport_error
        raise RuntimeError("unreachable: retry loop exited without returning or raising")
