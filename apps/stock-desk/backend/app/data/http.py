"""Shared, hand-rolled HTTP client wrapper for all data-layer adapters.

Deliberately does not depend on ``tenacity`` or similar retry libraries per
the task's constraint -- rate limiting and exponential backoff are both
implemented directly on top of ``httpx``.

Every adapter should build one ``RateLimitedClient`` and reuse it for the
lifetime of the process so the rate limiter actually throttles traffic
across calls instead of resetting per request.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from types import TracebackType

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)


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
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
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
