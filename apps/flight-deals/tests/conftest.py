"""Shared fixtures. All tests run offline: outbound sockets are blocked (C-5)."""

from __future__ import annotations

import socket
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from flight_deals.app import Assembly, create_app
from flight_deals.config import Config
from flight_deals.domain.currency import major_to_minor
from flight_deals.domain.models import FlightSearch, PriceKind, PriceQuote, QueryStatus
from flight_deals.ports import SendResult, SourceResult
from flight_deals.redact import clear_secrets

FIXTURES = Path(__file__).parent / "fixtures"
ROUNDTRIP_FIXTURE = FIXTURES / "fixture_roundtrip_TPE_NRT.json"
CLIENT_HEADERS = {"X-Flight-Deals-Client": "1"}
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class NetworkBlockedError(RuntimeError):
    pass


def _is_loopback(address: Any) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    return isinstance(host, str) and host in _LOOPBACK


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse any non-loopback connection unless the test is marked ``live``."""
    if request.node.get_closest_marker("live"):
        return
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self: socket.socket, address: Any) -> None:
        if not _is_loopback(address):
            raise NetworkBlockedError(f"network access blocked in tests: {address!r}")
        real_connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: Any) -> int:
        if not _is_loopback(address):
            raise NetworkBlockedError(f"network access blocked in tests: {address!r}")
        return real_connect_ex(self, address)

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in _LOOPBACK and host is not None:
            raise NetworkBlockedError(f"DNS lookup blocked in tests: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)


@pytest.fixture(autouse=True)
def _reset_secrets() -> Iterator[None]:
    clear_secrets()
    yield
    clear_secrets()


class FakeClock:
    """Mutable UTC clock. 2026-10-25 04:00Z is 12:00 in Asia/Taipei."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 10, 25, 4, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@dataclass
class FakeNotifier:
    configured: bool = True
    fail_with: str | None = None
    sent: list[str] = field(default_factory=list)
    attempts: int = 0

    @property
    def channel(self) -> str:
        return "telegram"

    def is_configured(self) -> bool:
        return self.configured

    def send(self, text: str) -> SendResult:
        self.attempts += 1
        if self.fail_with:
            return SendResult(ok=False, error=self.fail_with)
        self.sent.append(text)
        return SendResult(ok=True)


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


Handler = Callable[[FlightSearch], "SourceResult"]


class ScriptedSource:
    """Programmable source: ``prices`` maps (depart, return) ISO pairs to whole TWD."""

    def __init__(
        self,
        clock: Callable[[], datetime],
        *,
        name: str = "google_flights",
        price_kind: PriceKind = "live",
        default_price: int | None = 10_000,
        currency: str | None = None,
    ) -> None:
        self._clock = clock
        self._name = name
        self._kind = price_kind
        self.default_price = default_price
        self.prices: dict[tuple[str, str | None], int] = {}
        self.status_override: QueryStatus | None = None
        self.fail_for: set[tuple[str, str | None]] = set()
        self.currency = currency
        self.calls: list[FlightSearch] = []
        self.handler: Handler | None = None
        self.price_fn: Callable[[FlightSearch], int | None] | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def price_kind(self) -> PriceKind:
        return self._kind

    def search(self, query: FlightSearch) -> SourceResult:
        self.calls.append(query)
        if self.handler is not None:
            return self.handler(query)
        now = self._clock()
        key = (
            query.pair.depart.isoformat(),
            query.pair.return_date.isoformat() if query.pair.return_date else None,
        )
        if self.status_override is not None:
            return SourceResult(self._name, self.status_override, now, error="scripted failure")
        if key in self.fail_for:
            return SourceResult(self._name, "error", now, error="scripted error")
        if self.price_fn is not None:
            price = self.price_fn(query)
        else:
            price = self.prices.get(key, self.default_price)
        if price is None:
            return SourceResult(self._name, "no_data", now)
        currency = self.currency or query.currency
        quote = PriceQuote(
            source=self._name,
            price_kind=self._kind,
            depart_date=query.pair.depart,
            return_date=query.pair.return_date,
            amount_minor=major_to_minor(price, currency),
            currency=currency,
            as_of=now,
            as_of_basis="fetch_time",
            fetched_at=now,
            carrier="測試航空",
            stops=0,
            duration_minutes=180,
        )
        return SourceResult(self._name, "ok", now, quotes=(quote,))


@pytest.fixture
def source(clock: FakeClock) -> ScriptedSource:
    return ScriptedSource(clock)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(db_path=tmp_path / "test.db", sources=("google_flights",))


@dataclass
class Harness:
    assembly: Assembly
    client: TestClient
    clock: FakeClock
    source: ScriptedSource
    notifier: FakeNotifier

    @property
    def services(self) -> Any:
        return self.assembly.services

    @property
    def repo(self) -> Any:
        return self.assembly.services.watches._repo

    def create_watch(self, **overrides: Any) -> int:
        payload: dict[str, Any] = {
            "destination": "NRT",
            "trip_type": "round_trip",
            "date_mode": "fixed",
            "depart_date": "2026-12-10",
            "return_date": "2026-12-15",
            "budget": 12000,
        }
        payload.update(overrides)
        result = self.assembly.services.watches.create(payload)
        assert result.ok, result.errors
        assert result.watch_id is not None
        return result.watch_id

    def scan(self, watch_id: int, trigger: str = "scheduled") -> Any:
        return self.assembly.services.scan.scan_watch(watch_id, trigger)


@pytest.fixture
def harness(
    config: Config, clock: FakeClock, source: ScriptedSource, notifier: FakeNotifier
) -> Iterator[Harness]:
    app = create_app(
        config, sources=[source], notifier=notifier, clock=clock, start_scheduler=False
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield Harness(app.state.assembly, client, clock, source, notifier)
