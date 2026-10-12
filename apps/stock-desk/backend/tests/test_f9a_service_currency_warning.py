"""F-9a: the service logs a WARNING for off-market bar currencies and changes nothing else.

Each scenario drives ``MarketDataService`` down one path that obtains bars
(a live provider, the incremental read-back, layer 0, the degrade-to-cache
rung, the cache-only read) and runs it twice on identical fresh databases --
once with the market currency injected, once without. The returned result and
every cache table must come out identical; only the log differs (F-9a: the
fail-closed refusal is F-9b).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.api import deps
from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult
from app.data.service import CURRENCY_DIFFERS_LOG_PREFIX, MarketDataService
from app.positions.models import MARKET_CURRENCY

SERVICE_LOGGER = "app.data.service"


def _bar(
    day: date, currency: str, source: str, *, symbol: str = "2330", market: Market = "TW"
) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market=market,
        date=day,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        volume=1,
        currency=currency,
        as_of=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
        source=source,
    )


class _Provider(MarketDataProvider):
    source_id = "stub"

    def __init__(self, label: str, bars: list[PriceBar]) -> None:
        self._label = label
        self._bars = bars
        self.asked: list[tuple[str, date, date]] = []

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.asked.append((symbol, start, end))
        return ProviderResult(
            bars=self._bars,
            status=DataStatus.FRESH if self._bars else DataStatus.UNAVAILABLE,
            as_of=datetime(2024, 1, 3, 8, 0, tzinfo=UTC),
            source=self._label,
            staleness_minutes=0 if self._bars else None,
        )


@dataclass(frozen=True)
class Scenario:
    name: str
    #: Seeds the cache; receives the off-market currency under test.
    seed: Callable[[PriceBarCache, str], None]
    #: What the primary returns, given that currency.
    primary_bars: Callable[[str], list[PriceBar]]
    cache_first: bool
    clock: datetime
    call: Callable[[MarketDataService], ProviderResult]
    #: Layers whose WARNING is expected when the currency is off-market.
    layers: tuple[str, ...]


def _no_seed(_cache: PriceBarCache, _currency: str) -> None:
    return None


def _seed_one(cache: PriceBarCache, currency: str) -> None:
    cache.put(
        [_bar(date(2024, 1, 2), currency, "twse")],
        source="twse",
        fetched_at=datetime(2024, 1, 2, 7, 0, tzinfo=UTC),
    )


def _seed_layer_zero(cache: PriceBarCache, currency: str) -> None:
    _seed_one(cache, currency)
    cache.record_fetch(
        "2330",
        "TW",
        start=date(2024, 1, 1),
        end=date(2024, 1, 2),
        fetched_at=datetime(2024, 1, 2, 7, 40, tzinfo=UTC),
    )


def _seed_incremental(cache: PriceBarCache, currency: str) -> None:
    # A TWD head in November, the off-market bar at the end of December.
    cache.put(
        [_bar(date(2023, 11, 30), "TWD", "twse"), _bar(date(2023, 12, 29), currency, "twse")],
        source="twse",
        fetched_at=datetime(2023, 12, 29, 8, 0, tzinfo=UTC),
    )
    cache.record_fetch(
        "2330",
        "TW",
        start=date(2023, 11, 1),
        end=date(2023, 12, 29),
        fetched_at=datetime(2023, 12, 29, 8, 0, tzinfo=UTC),
    )


SCENARIOS = [
    Scenario(
        name="provider",
        seed=_no_seed,
        primary_bars=lambda c: [_bar(date(2024, 1, 2), c, "twse")],
        cache_first=False,
        clock=datetime(2024, 1, 2, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_daily_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
        layers=("provider",),
    ),
    Scenario(
        name="incremental",
        seed=_seed_incremental,
        primary_bars=lambda c: [_bar(date(2024, 1, 3), c, "twse")],
        cache_first=True,
        clock=datetime(2024, 1, 3, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_daily_bars("2330", "TW", date(2023, 11, 1), date(2024, 1, 31)),
        layers=("provider", "incremental_readback"),
    ),
    Scenario(
        name="layer0",
        seed=_seed_layer_zero,
        primary_bars=lambda c: [],
        cache_first=True,
        clock=datetime(2024, 1, 2, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_daily_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
        layers=("layer0_cache",),
    ),
    Scenario(
        name="fallback",
        seed=_seed_one,
        primary_bars=lambda c: [],
        cache_first=False,
        clock=datetime(2024, 1, 2, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_daily_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
        layers=("fallback_cache",),
    ),
    Scenario(
        name="cache_only",
        seed=_seed_one,
        primary_bars=lambda c: [],
        cache_first=False,
        clock=datetime(2024, 1, 2, 8, 0, tzinfo=UTC),
        call=lambda s: s.get_cached_bars("2330", "TW", date(2024, 1, 1), date(2024, 1, 31)),
        layers=("cache_only",),
    ),
]


def _dump(db: Path) -> dict[str, list[tuple[Any, ...]]]:
    with closing(sqlite3.connect(db)) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall()
            for table in ("price_bars_cache", "price_bars_fetch_log", "price_bars_attempt_log")
        }


@dataclass(frozen=True)
class Run:
    result: ProviderResult
    tables: dict[str, list[tuple[Any, ...]]]
    warnings: list[str]
    primary_asked: list[tuple[str, date, date]]


def _run(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    scenario: Scenario,
    *,
    currency: str,
    expected: str | None,
) -> Run:
    db = tmp_path / f"{scenario.name}-{currency}-{expected}.db"
    cache = PriceBarCache(db_path=db)
    scenario.seed(cache, currency)
    primary = _Provider("twse", scenario.primary_bars(currency))
    service = MarketDataService(
        primary=primary,
        cache=cache,
        clock=lambda: scenario.clock,
        cache_first=scenario.cache_first,
        expected_currency=expected,
    )
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=SERVICE_LOGGER):
        result = scenario.call(service)
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == SERVICE_LOGGER
        and record.levelno == logging.WARNING
        and record.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)
    ]
    return Run(result, _dump(db), warnings, primary.asked)


def _layer(message: str) -> str:
    return message.split(" layer=")[1].split(" ")[0]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_off_market_currency_warns_on_each_path_and_changes_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, scenario: Scenario
) -> None:
    checked = _run(tmp_path, caplog, scenario, currency="USD", expected="TWD")
    unchecked = _run(tmp_path, caplog, scenario, currency="USD", expected=None)

    assert [_layer(message) for message in checked.warnings] == list(scenario.layers)
    assert unchecked.warnings == []
    # Behaviour unchanged: same answer, same rows, same logs, same live calls.
    assert checked.result == unchecked.result
    assert checked.tables == unchecked.tables
    assert checked.primary_asked == unchecked.primary_asked
    # The off-market bar is still served (F-9b, not F-9a, refuses it).
    assert "USD" in {bar.currency for bar in checked.result.bars}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_market_currency_bars_log_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, scenario: Scenario
) -> None:
    clean = _run(tmp_path, caplog, scenario, currency="TWD", expected="TWD")
    assert clean.warnings == []
    assert clean.result.bars


def test_warning_text_is_fixed(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    provider = _run(tmp_path, caplog, SCENARIOS[0], currency="USD", expected="TWD")
    assert provider.warnings == [
        "price bars currency differs from market: symbol=2330 market=TW expected=TWD "
        "observed=USD mismatched=1/1 layer=provider source=twse"
    ]
    incremental = _run(tmp_path, caplog, SCENARIOS[1], currency="USD", expected="TWD")
    assert incremental.warnings[1] == (
        "price bars currency differs from market: symbol=2330 market=TW expected=TWD "
        "observed=TWD,USD mismatched=2/3 layer=incremental_readback source=twse"
    )


def test_warning_is_one_record_at_warning_level(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _run(tmp_path, caplog, SCENARIOS[0], currency="USD", expected="TWD")
    records = [r for r in caplog.records if r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].name == SERVICE_LOGGER
    assert records[0].exc_info is None


# --- assembly layer (deps.py) --------------------------------------------------


class _IndexSource:
    """Stands in for the yfinance adapter in both of its roles."""

    source_id = "yfinance"

    def __init__(self, currency: str) -> None:
        self._currency = currency

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        return ProviderResult(
            bars=[],
            status=DataStatus.UNAVAILABLE,
            as_of=datetime(2024, 1, 2, tzinfo=UTC),
            source="yfinance",
            staleness_minutes=None,
        )

    def get_index_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        bar = _bar(date(2024, 1, 2), self._currency, "yfinance", symbol=symbol, market="US")
        return ProviderResult(
            bars=[bar],
            status=DataStatus.BACKUP,
            as_of=datetime(2024, 1, 2, tzinfo=UTC),
            source="yfinance",
            staleness_minutes=0,
        )


@pytest.fixture
def stub_wiring(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "wiring.db")
    source = _IndexSource("GBP")
    monkeypatch.setattr(deps, "_default_cache", lambda: cache)
    monkeypatch.setattr(deps, "_default_yfinance", lambda: source)
    for name, market in (
        ("TwseAdapter", "TW"),
        ("TpexAdapter", "TW"),
        ("FinMindAdapter", "TW"),
        ("AlphaVantageAdapter", "US"),
    ):
        bars = [_bar(date(2024, 1, 2), "GBP", "stub", market=market)]  # type: ignore[arg-type]
        monkeypatch.setattr(deps, name, lambda bars=bars: _Provider("stub", bars))


@pytest.mark.usefixtures("stub_wiring")
@pytest.mark.parametrize("market", ["TW", "US"])
def test_equity_ladders_are_told_their_market_currency(
    caplog: pytest.LogCaptureFixture, market: Market
) -> None:
    resolver = deps._default_resolver.__wrapped__()  # bypass lru_cache
    with caplog.at_level(logging.WARNING, logger=SERVICE_LOGGER):
        resolver[market].get_daily_bars("2330", market, date(2024, 1, 1), date(2024, 1, 2))
    messages = [r.getMessage() for r in caplog.records if r.name == SERVICE_LOGGER]
    assert any(
        message.startswith(CURRENCY_DIFFERS_LOG_PREFIX)
        and f" expected={MARKET_CURRENCY[market]} " in message
        for message in messages
    )


@pytest.mark.usefixtures("stub_wiring")
def test_index_ladder_is_explicitly_not_checked(caplog: pytest.LogCaptureFixture) -> None:
    resolver = deps._default_index_resolver.__wrapped__()  # bypass lru_cache
    with caplog.at_level(logging.WARNING, logger=SERVICE_LOGGER):
        result = resolver["US"].get_daily_bars("^GSPC", "US", date(2024, 1, 1), date(2024, 1, 2))
    assert [bar.currency for bar in result.bars] == ["GBP"]
    assert not [r for r in caplog.records if r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)]
