"""``PriceInfo.is_within_ttl`` / ``PriceInfo.reason`` pass-through (CEO 2026-10-02 延遲標示修正).

The home-page holdings table must tell "the latest session, served from the
local cache" (``cached_stale`` + ``is_within_ttl=True``) apart from "really
behind" (``cached_stale`` + ``is_within_ttl`` not ``True``). Both fields are
copied verbatim from the data layer's ``ProviderResult``; no existing field
changes meaning.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_position_store, get_valuator
from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.data.providers.fx import FxRateProvider, FxRateResult
from app.main import app
from app.portfolio.valuation import PositionValuator, PriceInfo, PriceService
from app.positions.models import Position, PositionInput
from app.positions.store import PositionStore

NOW = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
BAR_DATE = date(2026, 9, 30)
STALE_REASON = "快取未含最近一個交易日。"

Wire = Callable[[PriceService], TestClient]


class _ResultPriceService(PriceService):
    """Answers every live read with one bar and a caller-chosen envelope."""

    def __init__(
        self,
        status: DataStatus,
        *,
        is_within_ttl: bool | None = None,
        reason: str | None = None,
    ) -> None:
        self._status = status
        self._is_within_ttl = is_within_ttl
        self._reason = reason

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        bar = PriceBar(
            symbol=symbol,
            market=market,
            date=BAR_DATE,
            open=Decimal("550"),
            high=Decimal("550"),
            low=Decimal("550"),
            close=Decimal("550"),
            volume=1,
            currency="TWD",
            as_of=NOW,
            source="fake",
        )
        return ProviderResult(
            bars=[bar],
            status=self._status,
            as_of=NOW,
            source="fake",
            is_within_ttl=self._is_within_ttl,
            reason=self._reason,
        )

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        raise NotImplementedError("this file exercises the live valuator only")


class _NoFxProvider(FxRateProvider):
    source_id = "fake_fx"

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        return FxRateResult(rates=[], status=DataStatus.UNAVAILABLE, as_of=NOW, source="fake_fx")


def _valuator(service: PriceService) -> PositionValuator:
    services: dict[Market, PriceService] = {"TW": service, "US": service}
    return PositionValuator(
        market_services=services, fx_provider=_NoFxProvider(), clock=lambda: NOW
    )


def _tw_position() -> Position:
    return Position(
        id=1,
        symbol="2330",
        market="TW",
        quantity=Decimal("100"),
        avg_cost=Decimal("500"),
        currency="TWD",
        opened_at=date(2026, 9, 1),
        instrument_type="stock",
        note=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _price(service: PriceService) -> PriceInfo:
    price = _valuator(service).value_position(_tw_position()).valuation.price
    assert price is not None
    return price


# --- unit: PriceInfo model and _resolve_price pass-through -------------------


def test_price_info_new_fields_default_to_none() -> None:
    info = PriceInfo(
        value=Decimal("1"), as_of="2026-09-30", source="fake", data_status=DataStatus.FRESH
    )
    assert info.is_within_ttl is None
    assert info.reason is None


def test_cached_stale_within_ttl_is_passed_through() -> None:
    price = _price(_ResultPriceService(DataStatus.CACHED_STALE, is_within_ttl=True))
    assert price.data_status is DataStatus.CACHED_STALE
    assert price.is_within_ttl is True
    assert price.reason is None


def test_cached_stale_outside_ttl_carries_reason() -> None:
    price = _price(
        _ResultPriceService(DataStatus.CACHED_STALE, is_within_ttl=False, reason=STALE_REASON)
    )
    assert price.is_within_ttl is False
    assert price.reason == STALE_REASON


def test_fresh_leaves_new_fields_none() -> None:
    price = _price(_ResultPriceService(DataStatus.FRESH))
    assert price.is_within_ttl is None
    assert price.reason is None


def test_existing_fields_keep_their_meaning() -> None:
    # ``as_of`` is still the bar's trading date (a plain ISO date, no time part).
    price = _price(_ResultPriceService(DataStatus.CACHED_STALE, is_within_ttl=True))
    assert price.as_of == "2026-09-30"
    assert price.value == Decimal("550")
    assert price.source == "fake"


# --- contract: GET /api/portfolio/summary --------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> PositionStore:
    store = PositionStore(db_path=tmp_path / "positions.db")
    store.create(
        PositionInput(
            symbol="2330",
            market="TW",
            quantity=Decimal("100"),
            avg_cost=Decimal("500"),
            currency="TWD",
            opened_at=date(2026, 9, 1),
            instrument_type="stock",
            note=None,
        ),
        now=NOW,
    )
    return store


@pytest.fixture
def wire(store: PositionStore) -> Iterator[Wire]:
    def _wire(service: PriceService) -> TestClient:
        app.dependency_overrides[get_position_store] = lambda: store
        app.dependency_overrides[get_valuator] = lambda: _valuator(service)
        return TestClient(app)

    yield _wire
    app.dependency_overrides.clear()


def _summary_price(client: TestClient) -> dict[str, object]:
    response = client.get("/api/portfolio/summary")
    assert response.status_code == 200
    price = response.json()["positions"][0]["valuation"]["price"]
    assert isinstance(price, dict)
    return price


def test_summary_price_contract_has_exact_key_set(wire: Wire) -> None:
    price = _summary_price(wire(_ResultPriceService(DataStatus.FRESH)))
    assert set(price) == {"value", "as_of", "source", "data_status", "is_within_ttl", "reason"}
    assert price["as_of"] == "2026-09-30"
    assert price["is_within_ttl"] is None
    assert price["reason"] is None


def test_summary_price_contract_cached_within_ttl(wire: Wire) -> None:
    price = _summary_price(wire(_ResultPriceService(DataStatus.CACHED_STALE, is_within_ttl=True)))
    assert price["data_status"] == "cached_stale"
    assert price["is_within_ttl"] is True
    assert price["reason"] is None


def test_summary_price_contract_cached_outside_ttl(wire: Wire) -> None:
    price = _summary_price(
        wire(_ResultPriceService(DataStatus.CACHED_STALE, is_within_ttl=False, reason=STALE_REASON))
    )
    assert price["data_status"] == "cached_stale"
    assert price["is_within_ttl"] is False
    assert price["reason"] == STALE_REASON
