"""ADR-0010 D-1 / D-2: the cache-only book valuation behind the advice card.

The card's risk caps need book-level denominators, for which a session of
staleness is a rounding error while re-running one ladder per holding is
minutes of blank screen (CEO 2026-09-17, 12 holdings). So the advice endpoint
values the *book* from the local cache only and keeps the symbol itself live.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.api.advice import (
    CACHE_ONLY_BOOK_NOTE,
    CACHE_ONLY_BOOK_NOTE_EMPTY,
    CACHE_ONLY_BOOK_NOTE_SINGLE_DAY,
)
from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.portfolio.valuation import PRICE_NOT_QUERIED, PositionValuator
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from tests.api_helpers import FakePriceService, recent_bars
from tests.conftest import ApiHarness

NOW = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


class _CountingFxProvider(FxRateProvider):
    """One flat USDTWD rate for every day asked, counting the asks."""

    source_id = "fake_fx"

    def __init__(self) -> None:
        self.calls = 0

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.calls += 1
        rates = [
            FxRate(pair=pair, date=end, rate=Decimal("31.5"), as_of=NOW, source=self.source_id)
        ]
        return FxRateResult(rates=rates, status=DataStatus.FRESH, as_of=NOW, source=self.source_id)


def _position(symbol: str, *, market: str = "TW", currency: str = "TWD") -> PositionInput:
    return PositionInput(
        symbol=symbol,
        market=market,  # type: ignore[arg-type]
        quantity=Decimal("100"),
        avg_cost=Decimal("100"),
        currency=currency,  # type: ignore[arg-type]
        opened_at=date(2026, 7, 1),
        instrument_type="stock",
        note=None,
    )


def _stored(store: PositionStore, *inputs: PositionInput):  # type: ignore[no-untyped-def]
    for item in inputs:
        store.create(item, now=NOW)
    return store.list_all()


def test_cache_only_mode_reads_the_cache_and_never_the_ladder(tmp_path) -> None:  # type: ignore[no-untyped-def]
    prices = FakePriceService()
    prices.seed("2330", recent_bars([100.0] * 5, symbol="2330", end=NOW.date()))
    valuator = PositionValuator(
        market_services={"TW": prices},
        fx_provider=_CountingFxProvider(),
        clock=lambda: NOW,
        price_mode="cache_only",
    )
    store = PositionStore(db_path=tmp_path / "positions.db")
    held, unknown = _stored(store, _position("2330"), _position("2317"))

    valued = valuator.value_all([held, unknown])
    assert prices.calls == []  # R-1: no live ask at all
    assert [call[0] for call in prices.cached_calls] == ["2330", "2317"]
    assert valued[0].valuation.status == "ok"
    assert valued[0].valuation.price is not None
    assert valued[0].valuation.price.data_status is DataStatus.CACHED_STALE
    # R-5: "not asked this time" is a different fact from "the source had nothing".
    assert valued[1].valuation.status == "insufficient_data"
    assert valued[1].valuation.missing == [PRICE_NOT_QUERIED]


def test_live_mode_is_unchanged_and_names_a_missing_price_as_before(tmp_path) -> None:  # type: ignore[no-untyped-def]
    prices = FakePriceService()
    valuator = PositionValuator(
        market_services={"TW": prices}, fx_provider=_CountingFxProvider(), clock=lambda: NOW
    )
    store = PositionStore(db_path=tmp_path / "positions.db")
    (only,) = _stored(store, _position("2317"))
    valued = valuator.value_position(only)
    assert prices.calls and prices.cached_calls == []
    assert valued.valuation.missing == ["price"]


def test_one_pass_asks_the_fx_source_once_per_pair_and_date(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """ADR-0010 D-2: three USD holdings, one book, one lookup per (pair, date)."""
    prices = FakePriceService()
    for symbol in ("AAPL", "MSFT", "NVDA"):
        prices.seed(symbol, recent_bars([100.0] * 5, symbol=symbol, market="US", end=NOW.date()))
    fx = _CountingFxProvider()
    valuator = PositionValuator(market_services={"US": prices}, fx_provider=fx, clock=lambda: NOW)
    store = PositionStore(db_path=tmp_path / "positions.db")
    positions = _stored(
        store,
        _position("AAPL", market="US", currency="USD"),
        _position("MSFT", market="US", currency="USD"),
        _position("NVDA", market="US", currency="USD"),
    )
    valued = valuator.value_all(positions)
    assert all(item.valuation.status == "ok" for item in valued)
    # fx_now (today) and fx_open (the shared open date): two asks, not six.
    assert fx.calls == 2
    # Per-position calls (no memo) still ask every time, as before.
    fx.calls = 0
    valuator.value_position(positions[0])
    assert fx.calls == 2


def test_the_advice_card_values_the_book_from_the_cache_and_says_so(
    api_harness: ApiHarness,
) -> None:
    """R-6: the symbol itself is loaded live first; the rest of the book is a cache read."""
    prices = api_harness.price_service
    prices.seed("2330", recent_bars([100.0] * 80, symbol="2330"))
    prices.seed("2317", recent_bars([50.0] * 80, symbol="2317"))
    api_harness.positions.create(_position("2330"), now=NOW)
    api_harness.positions.create(_position("2317"), now=NOW)

    response = api_harness.client.get("/api/advice/2330", params={"market": "TW"})
    assert response.status_code == 200
    body = response.json()
    live = [call[0] for call in prices.calls]
    assert live == ["2330"]  # the card's own symbol, once, live
    assert [call[0] for call in prices.cached_calls] == ["2330", "2317"]
    # First in the list (風控 A-6): it qualifies every figure the notes after it are about.
    note = body["context_notes"][0]
    last_bar = prices.bars["2330"][-1].date.isoformat()
    # Both holdings' cached closes are from the same day: the single-day wording (A-7).
    assert note == CACHE_ONLY_BOOK_NOTE_SINGLE_DAY.format(date=last_bar)
    assert "{" not in CACHE_ONLY_BOOK_NOTE_EMPTY and "～" in CACHE_ONLY_BOOK_NOTE


def test_a_book_with_no_cached_price_at_all_still_says_so(api_harness: ApiHarness) -> None:
    """風控 A-1: the disclosure changes, it never disappears."""
    prices = api_harness.price_service
    prices.seed("2330", recent_bars([100.0] * 80, symbol="2330"))
    api_harness.positions.create(_position("2317"), now=NOW)  # held, but nothing cached
    body = api_harness.client.get("/api/advice/2330", params={"market": "TW"}).json()
    assert body["context_notes"][0] == CACHE_ONLY_BOOK_NOTE_EMPTY


def test_an_empty_book_gets_no_cache_note_at_all(api_harness: ApiHarness) -> None:
    """風控 複審 A-1: with nothing held there is nothing for the sentence to qualify."""
    api_harness.price_service.seed("2330", recent_bars([100.0] * 80, symbol="2330"))
    body = api_harness.client.get("/api/advice/2330", params={"market": "TW"}).json()
    assert not any("整體持倉估值" in note for note in body["context_notes"])
