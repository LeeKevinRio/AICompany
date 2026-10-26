"""Shared adapter plumbing: TTL cache, client-side throttle, backoff and hard timeouts."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")
T = TypeVar("T")

log = logging.getLogger(__name__)


class TTLCache(Generic[K, V]):
    """Tiny in-memory cache with per-entry time-to-live."""

    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._data: dict[K, tuple[float, V]] = {}
        self._lock = threading.Lock()

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires, value = entry
            if self._clock() >= expires:
                del self._data[key]
                return None
            return value

    def put(self, key: K, value: V) -> None:
        if self._ttl <= 0:
            return
        with self._lock:
            self._data[key] = (self._clock() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class Throttle:
    """Enforce a minimum interval (plus random jitter) between outbound calls."""

    def __init__(
        self,
        min_interval_seconds: float,
        jitter_seconds: float = 0.0,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._min = min_interval_seconds
        self._jitter = jitter_seconds
        self._sleep = sleep
        self._clock = clock
        self._rng = rng
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> float:
        """Block until the next call is allowed; returns the seconds slept."""
        with self._lock:
            slept = 0.0
            if self._last is not None:
                gap = self._min + self._jitter * self._rng()
                remaining = self._last + gap - self._clock()
                if remaining > 0:
                    self._sleep(remaining)
                    slept = remaining
            self._last = self._clock()
            return slept


def backoff_delay(base_seconds: float, retry_index: int) -> float:
    """Exponential backoff: base, 2*base, 4*base, ... for retry 1, 2, 3, ..."""
    return float(base_seconds * (2 ** max(retry_index - 1, 0)))


DEFAULT_MAX_IN_FLIGHT = 4


class WorkersExhaustedError(RuntimeError):
    """Too many earlier calls are still running past their timeout."""


class TimeoutRunner:
    """Run blocking calls with a hard wall-clock timeout, one daemon thread per call.

    Some scraping libraries expose no timeout parameter, and a running thread
    cannot be cancelled: a call that overruns keeps its thread until it returns, and
    its result is discarded. Each call gets its own thread, so the timeout never
    includes queueing time; ``max_in_flight`` bounds how many such threads may pile up.
    """

    def __init__(self, max_in_flight: int = DEFAULT_MAX_IN_FLIGHT) -> None:
        self._max = max_in_flight
        self._in_flight = 0
        self._lock = threading.Lock()

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight

    def run(self, fn: Callable[[], T], timeout_seconds: float) -> T:
        with self._lock:
            if self._in_flight >= self._max:
                log.warning(
                    "source call refused: %d earlier calls still running after timeout",
                    self._in_flight,
                )
                raise WorkersExhaustedError(
                    f"workers exhausted: {self._in_flight} earlier calls still running"
                )
            self._in_flight += 1
        done = threading.Event()
        outcome: dict[str, object] = {}

        def target() -> None:
            try:
                outcome["value"] = fn()
            except BaseException as exc:  # handed back to the caller below
                outcome["error"] = exc
            finally:
                with self._lock:
                    self._in_flight -= 1
                done.set()

        threading.Thread(target=target, name="source-call", daemon=True).start()
        if not done.wait(timeout_seconds):
            raise TimeoutError(f"source call exceeded {timeout_seconds:g}s")
        error = outcome.get("error")
        if isinstance(error, BaseException):
            raise error
        return outcome["value"]  # type: ignore[return-value]


_default_runner = TimeoutRunner()


def call_with_timeout(
    fn: Callable[[], T], timeout_seconds: float, runner: TimeoutRunner | None = None
) -> T:
    """Run ``fn`` with a hard timeout on ``runner`` (process-wide default if omitted)."""
    return (runner or _default_runner).run(fn, timeout_seconds)
