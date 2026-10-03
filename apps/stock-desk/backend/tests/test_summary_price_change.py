"""ADR-0016 (close-only D1): the change column on the summary payload.

T-2 (risk 2c(ii) invariants per row), T-3 (I-33; every non-summary caller gets
``change: null``), T-4 (no extra price-service calls), plus the end-to-end
wiring of ``GET /api/portfolio/summary`` to the real 除權息 store and bar cache.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_dividend_store,
    get_position_store,
    get_price_bar_cache,
    get_valuator,
)
from app.data.cache import PriceBarCache
from app.data.interface import Market, PriceBar
from app.dividends.models import DividendEvent
from app.dividends.store import DividendEventStore
from app.main import app
from app.portfolio.price_change import ChangeScreen, change_pct
from app.portfolio.summary import PortfolioSummary, build_summary
from app.portfolio.valuation import PositionValuator, PriceMode
from app.positions.models import Currency, PositionInput
from app.positions.store import PositionStore
from tests.api_helpers import FakePriceService, UnavailableFxProvider
from tests.conftest import ApiHarness

NOW = datetime(2026, 10, 5, 7, 0, tzinfo=UTC)  # Monday
THU = date(2026, 10, 1)
FRI = date(2026, 10, 2)
MON = date(2026, 10, 5)


def _bars(symbol: str, closes: list[tuple[date, str]], *, market: Market = "TW") -> list[PriceBar]:
    return [
        PriceBar(
            symbol=symbol,
            market=market,
            date=day,
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=1,
            currency="TWD" if market == "TW" else "USD",
            as_of=NOW,
            source="twse" if market == "TW" else "yfinance",
        )
        for day, close in closes
    ]


@dataclass
class Book:
    store: PositionStore
    prices: FakePriceService
    dividends: DividendEventStore
    bar_cache: PriceBarCache

    def valuator(self, price_mode: PriceMode = "live") -> PositionValuator:
        return PositionValuator(
            market_services={"TW": self.prices, "US": self.prices},
            fx_provider=UnavailableFxProvider(),
            clock=lambda: NOW,
            price_mode=price_mode,
        )

    def screen(self) -> ChangeScreen:
        return ChangeScreen(ex_dates=self.dividends, calendar=self.bar_cache)

    def hold(self, symbol: str, market: Market = "TW") -> None:
        currency: Currency = "TWD" if market == "TW" else "USD"
        self.store.create(
            PositionInput(
                symbol=symbol,
                market=market,
                quantity=Decimal("1000"),
                avg_cost=Decimal("500"),
                currency=currency,
                opened_at=date(2026, 1, 5),
                instrument_type="stock",
                note=None,
            ),
            now=NOW,
        )


@pytest.fixture
def book(tmp_path: Path) -> Book:
    prices = FakePriceService(source="twse")
    prices.seed("2330", _bars("2330", [(THU, "1060.00"), (FRI, "1072.00"), (MON, "1085.25")]))
    prices.seed("2317", _bars("2317", [(FRI, "200.0"), (MON, "190.0")]))
    prices.seed("2454", _bars("2454", [(MON, "1500")]))
    prices.seed("AAPL", _bars("AAPL", [(FRI, "250.00"), (MON, "245.00")], market="US"))
    bar_cache = PriceBarCache(db_path=tmp_path / "bars.db")
    # The market calendar the cache has observed: Thu, Fri, Mon.
    bar_cache.put(_bars("2330", [(THU, "1"), (FRI, "1"), (MON, "1")]), source="twse")
    dividends = DividendEventStore(db_path=tmp_path / "dividends.db")
    dividends.upsert(
        [
            DividendEvent(
                symbol="2317",
                market="TW",
                ex_date=MON,
                cash_dividend=Decimal("5.2"),
                source="twse_twt48u",
                as_of=NOW,
            )
        ]
    )
    store = PositionStore(db_path=tmp_path / "positions.db")
    result = Book(store=store, prices=prices, dividends=dividends, bar_cache=bar_cache)
    for symbol in ("2330", "2317", "2454"):
        result.hold(symbol)
    result.hold("AAPL", market="US")
    return result


@pytest.fixture
def client(book: Book) -> Iterator[TestClient]:
    app.dependency_overrides[get_position_store] = lambda: book.store
    app.dependency_overrides[get_valuator] = lambda: book.valuator()
    app.dependency_overrides[get_dividend_store] = lambda: book.dividends
    app.dependency_overrides[get_price_bar_cache] = lambda: book.bar_cache
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _changes(body: dict[str, Any]) -> dict[str, Any]:
    return {row["symbol"]: row["change"] for row in body["positions"]}


# --- the endpoint ------------------------------------------------------------


def test_summary_endpoint_screens_each_row(client: TestClient) -> None:
    body = client.get("/api/portfolio/summary").json()
    assert body["change_mode"] == "close_only"
    assert _changes(body) == {
        "2330": {
            "pct": "1.2360",
            "basis_kind": "close",
            "basis_date": "2026-10-02",
            "basis_price": "1072.00",
        },
        "2317": None,  # F6: ex-date on the price date
        "2454": None,  # F2: one bar
        "AAPL": {
            "pct": "-2.0000",
            "basis_kind": "close",
            "basis_date": "2026-10-02",
            "basis_price": "250.00",
        },
    }


def test_null_change_carries_no_reason(client: TestClient) -> None:
    body = client.get("/api/portfolio/summary").json()
    for row in body["positions"]:
        assert "change" in row
        assert not any(key.startswith("change_") for key in row)
        if row["change"] is not None:
            assert set(row["change"]) == {"pct", "basis_kind", "basis_date", "basis_price"}


def test_risk_2c_ii_invariants_hold_on_every_row(client: TestClient) -> None:
    """T-2: kind matches, basis precedes the price, pct recomputes exactly."""
    body = client.get("/api/portfolio/summary").json()
    shown = 0
    for row in body["positions"]:
        change = row["change"]
        if change is None:
            continue
        shown += 1
        price = row["valuation"]["price"]
        kinds = {"close": "daily_close", "intraday": "intraday_quote"}
        assert kinds[change["basis_kind"]] == price["price_kind"]
        assert date.fromisoformat(change["basis_date"]) < date.fromisoformat(price["as_of"])
        recomputed = change_pct(Decimal(price["value"]), Decimal(change["basis_price"]))
        assert str(recomputed) == change["pct"]
    assert shown == 2


def test_close_only_payload_has_no_intraday_kind(client: TestClient) -> None:
    """I-33: ``close_only`` -> no ``intraday_quote`` price, no ``intraday`` basis."""
    body = client.get("/api/portfolio/summary").json()
    assert body["change_mode"] == "close_only"
    for row in body["positions"]:
        price = row["valuation"]["price"]
        if price is not None:
            assert price["price_kind"] == "daily_close"
        if row["change"] is not None:
            assert row["change"]["basis_kind"] == "close"


def test_missing_session_withholds_through_the_real_calendar(book: Book) -> None:
    # Thu -> Fri: adjacent observed sessions, shown.
    book.prices.seed("2330", _bars("2330", [(THU, "1060.00"), (FRI, "1072.00")]))
    summary = build_summary(book.store, book.valuator(), change_screen=book.screen())
    assert {row.symbol: row.change for row in summary.positions}["2330"] is not None
    # Wed -> Fri: the market traded Thursday and this series does not have it.
    book.prices.seed("2330", _bars("2330", [(date(2026, 9, 30), "1060.00"), (FRI, "1072.00")]))
    summary = build_summary(book.store, book.valuator(), change_screen=book.screen())
    assert {row.symbol: row.change for row in summary.positions}["2330"] is None


# --- F8 and the other four callers (T-3) ----------------------------------------


def test_build_summary_without_a_screen_has_no_change(book: Book) -> None:
    summary = build_summary(book.store, book.valuator())
    assert [row.change for row in summary.positions] == [None, None, None, None]
    assert summary.change_mode == "close_only"


def test_cache_only_summary_without_a_screen_has_no_change(book: Book) -> None:
    summary = build_summary(book.store, book.valuator("cache_only"))
    assert all(row.change is None for row in summary.positions)


def test_non_summary_endpoints_do_not_screen(api_harness: ApiHarness) -> None:
    """The limits endpoint builds a summary too; it must not return or use a change.

    Runs on the fully isolated harness: this endpoint also reaches the settings
    and Kelly stores and the market resolver, none of which may be real here.
    """
    api_harness.price_service.seed(
        "2330", _bars("2330", [(THU, "1060.00"), (FRI, "1072.00"), (MON, "1085.25")])
    )
    api_harness.positions.create(
        PositionInput(
            symbol="2330",
            market="TW",
            quantity=Decimal("1000"),
            avg_cost=Decimal("500"),
            currency="TWD",
            opened_at=date(2026, 1, 5),
            instrument_type="stock",
            note=None,
        ),
        now=NOW,
    )
    response = api_harness.client.get("/api/portfolio/limits")
    assert response.status_code == 200
    assert '"change"' not in response.text


# --- T-4: the price service is asked exactly as often as before -------------------


@pytest.mark.parametrize("price_mode", ["live", "cache_only"])
def test_screen_adds_no_price_service_call(book: Book, price_mode: PriceMode) -> None:
    build_summary(book.store, book.valuator(price_mode))
    before = (len(book.prices.calls), len(book.prices.cached_calls))
    book.prices.calls.clear()
    book.prices.cached_calls.clear()

    build_summary(book.store, book.valuator(price_mode), change_screen=book.screen())
    after = (len(book.prices.calls), len(book.prices.cached_calls))

    assert after == before
    holdings = 4
    assert after == ((holdings, 0) if price_mode == "live" else (0, holdings))


def test_screen_reads_the_lookups_once_per_book(book: Book) -> None:
    """K-7: one ex-date read for the book, one calendar read per market."""

    class _CountingDividends:
        def __init__(self, inner: DividendEventStore) -> None:
            self.inner = inner
            self.calls = 0

        def ex_dates_between(
            self, keys: Collection[tuple[str, Market]], start: date, end: date
        ) -> Mapping[tuple[str, Market], frozenset[date]]:
            self.calls += 1
            return self.inner.ex_dates_between(keys, start, end)

    class _CountingCalendar:
        def __init__(self, inner: PriceBarCache) -> None:
            self.inner = inner
            self.markets: list[Market] = []

        def market_trading_days(self, market: Market, start: date, end: date) -> frozenset[date]:
            self.markets.append(market)
            return self.inner.market_trading_days(market, start, end)

    for symbol in ("2412", "2603", "3008"):
        book.prices.seed(symbol, _bars(symbol, [(FRI, "100"), (MON, "101")]))
        book.hold(symbol)
    dividends = _CountingDividends(book.dividends)
    calendar = _CountingCalendar(book.bar_cache)
    summary = build_summary(
        book.store,
        book.valuator(),
        change_screen=ChangeScreen(ex_dates=dividends, calendar=calendar),
    )
    assert sum(row.change is not None for row in summary.positions) == 5
    assert dividends.calls == 1
    assert sorted(calendar.markets) == ["TW", "US"]


# --- the ExDateLookup implementation -------------------------------------------


def test_dividend_store_batch_lookup(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "dividends.db")
    store.upsert(
        [
            DividendEvent(symbol=symbol, market="TW", ex_date=day, source="t", as_of=NOW)
            for symbol, day in [
                ("2330", THU),
                ("2330", MON),
                ("2317", FRI),
                ("1101", MON),
                ("2330", date(2026, 10, 20)),
            ]
        ]
    )
    found = store.ex_dates_between([("2330", "TW"), ("2317", "TW"), ("2330", "US")], FRI, MON)
    assert found == {("2330", "TW"): frozenset({MON}), ("2317", "TW"): frozenset({FRI})}
    assert store.ex_dates_between([], FRI, MON) == {}


def test_dividend_store_batch_lookup_across_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The >500-symbol path answers exactly what one query per key would."""
    from app.dividends import store as store_module

    store = DividendEventStore(db_path=tmp_path / "dividends.db")
    symbols = [f"S{number:04d}" for number in range(1200)]
    # Sorted positions 0..1199 split into chunks [0, 500), [500, 1000), [1000, 1200).
    hit = {symbols[0]: FRI, symbols[499]: MON, symbols[500]: FRI, symbols[1000]: MON}
    hit[symbols[1199]] = FRI
    events = [
        DividendEvent(symbol=symbol, market="TW", ex_date=day, source="t", as_of=NOW)
        for symbol, day in hit.items()
    ]
    events += [
        # Outside the window: must not appear.
        DividendEvent(symbol=symbols[750], market="TW", ex_date=THU, source="t", as_of=NOW),
        # Same symbol, two markets: only the requested market may match.
        DividendEvent(symbol="2330", market="TW", ex_date=MON, source="t", as_of=NOW),
        DividendEvent(symbol="2330", market="US", ex_date=FRI, source="t", as_of=NOW),
        # Stored under US, requested under TW: no match.
        DividendEvent(symbol=symbols[800], market="US", ex_date=MON, source="t", as_of=NOW),
    ]
    store.upsert(events)
    keys: list[tuple[str, Market]] = [(symbol, "TW") for symbol in symbols]
    keys.append(("2330", "TW"))
    assert len({symbol for symbol, _ in keys}) > store_module._MAX_SYMBOLS_PER_QUERY * 2

    statements: list[str] = []
    connect = store._connect

    def traced() -> sqlite3.Connection:
        conn = connect()
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(store, "_connect", traced)
    found = store.ex_dates_between(keys, FRI, MON)
    monkeypatch.undo()

    selects = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 3
    expected = {
        key: frozenset(event.ex_date for event in store.events_for(*key, start=FRI, end=MON))
        for key in keys
    }
    assert found == {key: days for key, days in expected.items() if days}
    assert found[("2330", "TW")] == frozenset({MON})
    assert ("2330", "US") not in found
    assert (symbols[800], "TW") not in found
    assert (symbols[750], "TW") not in found
    assert len(found) == 6


def test_screen_failure_on_an_extreme_price_keeps_the_summary(
    book: Book, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A per-row computation that raises withholds the whole book, not the response."""
    # 1E+999990 values fine (the market value stays inside Decimal's exponent
    # range) but cannot be quantized to 0.0001 -> InvalidOperation in change_pct.
    book.prices.seed("2330", _bars("2330", [(FRI, "1072.00"), (MON, "1E+999990")]))
    with caplog.at_level(logging.ERROR, logger="app.portfolio.price_change"):
        response = client.get("/api/portfolio/summary")
    assert response.status_code == 200
    body = response.json()
    assert [row["change"] for row in body["positions"]] == [None, None, None, None]
    failures = [record for record in caplog.records if "screen failed" in record.getMessage()]
    assert len(failures) == 1
    assert failures[0].exc_info is not None
    assert failures[0].exc_info[0] is InvalidOperation
    assert body["change_mode"] == "close_only"


def test_summary_model_defaults_keep_old_constructors_valid() -> None:
    assert PortfolioSummary.model_fields["change_mode"].default == "close_only"
