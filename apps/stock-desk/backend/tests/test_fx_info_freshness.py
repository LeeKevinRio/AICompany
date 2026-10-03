"""``FxInfo.is_within_ttl`` / ``FxInfo.reason`` (CEO 2026-10-03 匯率標示修正).

Same fix as ``test_price_info_freshness.py`` for the FX badge. ``reason`` is
copied verbatim from the FX data layer's ``FxRateResult``. That layer has no
cache rung and no TTL concept (ADR-0011), so ``is_within_ttl`` follows
``PriceInfo``'s rule for a live source and stays ``None``. No existing field
changes meaning.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_dividend_store,
    get_position_store,
    get_price_bar_cache,
    get_valuator,
)
from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.dividends.store import DividendEventStore
from app.main import app
from app.portfolio.valuation import FxInfo, PositionValuator, PriceService
from app.positions.models import Position, PositionInput
from app.positions.store import PositionStore

NOW = datetime(2026, 10, 3, 6, 0, tzinfo=UTC)
RATE_DATE = date(2026, 10, 2)
BACKUP_REASON = "主來源（bank_of_taiwan）本次無法提供匯率。"
UNAVAILABLE_REASON = "兩個匯率來源本次皆無法提供資料。"

FX_KEYS = {
    "pair",
    "as_of",
    "source",
    "data_status",
    "source_note",
    "is_within_ttl",
    "reason",
}

Wire = Callable[[FxRateProvider], TestClient]


class _FixedPriceService(PriceService):
    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        bar = PriceBar(
            symbol=symbol,
            market=market,
            date=RATE_DATE,
            open=Decimal("150"),
            high=Decimal("150"),
            low=Decimal("150"),
            close=Decimal("150"),
            volume=1,
            currency="USD",
            as_of=NOW,
            source="fake",
        )
        return ProviderResult(bars=[bar], status=DataStatus.FRESH, as_of=NOW, source="fake")

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        raise NotImplementedError("this file exercises the live valuator only")


class _ResultFxProvider(FxRateProvider):
    """Answers every FX read with a caller-chosen envelope."""

    source_id = "fake_fx"

    def __init__(
        self, status: DataStatus, *, source: str = "fake_fx", reason: str | None = None
    ) -> None:
        self._status = status
        self._source = source
        self._reason = reason

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        rates = (
            []
            if self._status is DataStatus.UNAVAILABLE
            else [
                FxRate(
                    pair=pair, date=RATE_DATE, rate=Decimal("32.5"), as_of=NOW, source=self._source
                )
            ]
        )
        return FxRateResult(
            rates=rates,
            status=self._status,
            as_of=NOW,
            source=self._source,
            reason=self._reason,
        )


def _valuator(fx_provider: FxRateProvider) -> PositionValuator:
    shared = _FixedPriceService()
    services: dict[Market, PriceService] = {"TW": shared, "US": shared}
    return PositionValuator(market_services=services, fx_provider=fx_provider, clock=lambda: NOW)


def _us_position() -> Position:
    return Position(
        id=1,
        symbol="AAPL",
        market="US",
        quantity=Decimal("10"),
        avg_cost=Decimal("100"),
        currency="USD",
        opened_at=date(2026, 9, 1),
        instrument_type="stock",
        note=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _fx(fx_provider: FxRateProvider) -> FxInfo:
    fx = _valuator(fx_provider).value_position(_us_position()).valuation.fx
    assert fx is not None
    return fx


# --- unit: FxInfo model and _lookup_fx pass-through --------------------------


def test_fx_info_new_fields_default_to_none() -> None:
    info = FxInfo(
        pair="USDTWD",
        as_of="2026-10-02",
        source="fake_fx",
        data_status=DataStatus.FRESH,
        source_note="",
    )
    assert info.is_within_ttl is None
    assert info.reason is None


def test_fresh_leaves_new_fields_none() -> None:
    fx = _fx(_ResultFxProvider(DataStatus.FRESH))
    assert fx.data_status is DataStatus.FRESH
    assert fx.is_within_ttl is None
    assert fx.reason is None


def test_backup_reason_is_passed_through_verbatim() -> None:
    fx = _fx(_ResultFxProvider(DataStatus.BACKUP, source="yfinance_fx", reason=BACKUP_REASON))
    assert fx.data_status is DataStatus.BACKUP
    assert fx.reason == BACKUP_REASON
    # The FX data layer has no cache rung, so there is no TTL question to answer.
    assert fx.is_within_ttl is None


def test_unavailable_reason_is_passed_through_verbatim() -> None:
    fx = _fx(_ResultFxProvider(DataStatus.UNAVAILABLE, source="none", reason=UNAVAILABLE_REASON))
    assert fx.data_status is DataStatus.UNAVAILABLE
    assert fx.as_of is None
    assert fx.reason == UNAVAILABLE_REASON
    assert fx.is_within_ttl is None


def test_cached_stale_from_fx_layer_is_not_assumed_current() -> None:
    # The real FX layer never answers CACHED_STALE today; if a provider ever
    # does, the valuation must not invent a TTL verdict for it.
    fx = _fx(_ResultFxProvider(DataStatus.CACHED_STALE, reason="快取匯率。"))
    assert fx.data_status is DataStatus.CACHED_STALE
    assert fx.is_within_ttl is None
    assert fx.reason == "快取匯率。"


def test_existing_fields_keep_their_meaning() -> None:
    # ``as_of`` is still the rate's calendar date (a plain ISO date, no time part).
    fx = _fx(_ResultFxProvider(DataStatus.FRESH))
    assert fx.pair == "USDTWD"
    assert fx.as_of == "2026-10-02"
    assert fx.source == "fake_fx"


# --- contract: GET /api/portfolio/summary --------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> PositionStore:
    store = PositionStore(db_path=tmp_path / "positions.db")
    store.create(
        PositionInput(
            symbol="AAPL",
            market="US",
            quantity=Decimal("10"),
            avg_cost=Decimal("100"),
            currency="USD",
            opened_at=date(2026, 9, 1),
            instrument_type="stock",
            note=None,
        ),
        now=NOW,
    )
    return store


@pytest.fixture
def wire(store: PositionStore) -> Iterator[Wire]:
    def _wire(fx_provider: FxRateProvider) -> TestClient:
        app.dependency_overrides[get_position_store] = lambda: store
        app.dependency_overrides[get_valuator] = lambda: _valuator(fx_provider)
        # ADR-0016: the summary endpoint also reads the 除權息 store and the bar
        # cache (as a trading calendar); keep both off the developer's database.
        app.dependency_overrides[get_dividend_store] = lambda: DividendEventStore(
            db_path=store.db_path.parent / "dividends.db"
        )
        app.dependency_overrides[get_price_bar_cache] = lambda: PriceBarCache(
            db_path=store.db_path.parent / "bars.db"
        )
        return TestClient(app)

    yield _wire
    app.dependency_overrides.clear()


def _summary_fx(client: TestClient) -> dict[str, object]:
    response = client.get("/api/portfolio/summary")
    assert response.status_code == 200
    fx = response.json()["positions"][0]["valuation"]["fx"]
    assert isinstance(fx, dict)
    return fx


def test_summary_fx_contract_has_exact_key_set(wire: Wire) -> None:
    fx = _summary_fx(wire(_ResultFxProvider(DataStatus.FRESH)))
    assert set(fx) == FX_KEYS
    assert fx["as_of"] == "2026-10-02"
    assert fx["data_status"] == "fresh"
    assert fx["is_within_ttl"] is None
    assert fx["reason"] is None


def test_summary_fx_contract_backup_carries_reason(wire: Wire) -> None:
    fx = _summary_fx(
        wire(_ResultFxProvider(DataStatus.BACKUP, source="yfinance_fx", reason=BACKUP_REASON))
    )
    assert set(fx) == FX_KEYS
    assert fx["data_status"] == "backup"
    assert fx["is_within_ttl"] is None
    assert fx["reason"] == BACKUP_REASON


def test_summary_fx_contract_unavailable_carries_reason(wire: Wire) -> None:
    fx = _summary_fx(
        wire(_ResultFxProvider(DataStatus.UNAVAILABLE, source="none", reason=UNAVAILABLE_REASON))
    )
    assert set(fx) == FX_KEYS
    assert fx["data_status"] == "unavailable"
    assert fx["as_of"] is None
    assert fx["is_within_ttl"] is None
    assert fx["reason"] == UNAVAILABLE_REASON
