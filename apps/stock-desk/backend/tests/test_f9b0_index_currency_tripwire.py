"""F-9b0: the index path's currency tripwires (F9W-31 (a), F9W-36, TA5 R-61) and test 5.

The index currency gate looks up the expected currency by the *market the
caller names*, not by the adapter's metadata. So "the index gate cannot fire
under the shipped configuration" (ADR-0024 D-4) rests on three tables agreeing
row by row: ``INDEX_SYMBOL_METADATA`` with ``MARKET_CURRENCY``, and every
``(series_symbol, market)`` the product asks for -- each ``official_index`` row
of ``INDEX_MAPPING`` and each ``MARKET_BENCHMARK`` entry -- with both.

Every table is expanded row by row at collection time, never frozen into a
snapshot list, so a row added later is checked automatically (F9W-36 (b)).

**Tripwire (F9W-31 (a), F9W-36 (a)).** These tests are the premise of the
index residual risk-compliance accepted in ADR-0024 D-4 (TA4 R-49, F9W-31,
F9W-32). If any of them turns red -- a changed ``MARKET_CURRENCY`` (failure
condition 4), a remapped index row, a new benchmark -- the change must go back
to risk-compliance-officer **together with the R-49 residual**. Do not just
update the expected values to make them green.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.api import deps
from app.data.cache import PriceBarCache
from app.data.http import RateLimitedClient
from app.data.interface import Market
from app.data.providers.yfinance import INDEX_SYMBOL_METADATA, YFinanceAdapter
from app.data.service import CURRENCY_DIFFERS_LOG_PREFIX
from app.leverage.index_mapping import INDEX_MAPPING
from app.positions.models import MARKET_CURRENCY
from app.services.index import MARKET_BENCHMARK

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SERVICE_LOGGER = "app.data.service"


def _official_rows() -> list[tuple[str, str, Market]]:
    """``(etf, series_symbol, series_market)`` for every ``official_index`` row, read live."""
    rows: list[tuple[str, str, Market]] = []
    for etf, ref in INDEX_MAPPING.items():
        if ref.basis != "official_index":
            continue
        assert ref.series_symbol is not None, etf
        rows.append((etf, ref.series_symbol, ref.series_market))
    return rows


def _benchmark_rows() -> list[tuple[Market, str]]:
    return [(market, benchmark.series_symbol) for market, benchmark in MARKET_BENCHMARK.items()]


def _asked_pairs() -> list[tuple[str, Market]]:
    """Every ``(series_symbol, market)`` the product asks the index service for (R-61)."""
    pairs = {(symbol, market) for _etf, symbol, market in _official_rows()}
    pairs |= {(symbol, market) for market, symbol in _benchmark_rows()}
    return sorted(pairs)


def test_the_tables_are_not_empty() -> None:
    """Guards the parametrisations below against silently expanding to nothing."""
    assert INDEX_SYMBOL_METADATA
    assert _official_rows()
    assert _benchmark_rows()


@pytest.mark.parametrize("symbol", sorted(INDEX_SYMBOL_METADATA))
def test_index_symbol_metadata_row_carries_its_market_currency(symbol: str) -> None:
    """Tripwire F9W-31 (a) / F9W-36: red means back to risk-compliance with the R-49 residual."""
    market, currency = INDEX_SYMBOL_METADATA[symbol]
    assert market in MARKET_CURRENCY
    assert currency == MARKET_CURRENCY[market]


@pytest.mark.parametrize(
    ("etf", "series_symbol", "series_market"), _official_rows(), ids=lambda v: str(v)
)
def test_official_index_mapping_row_agrees_with_metadata_and_market_currency(
    etf: str, series_symbol: str, series_market: Market
) -> None:
    """Tripwire F9W-31 (a) / F9W-36 (TA5 R-61): red means back to risk-compliance with R-49.

    ``services/index.py`` asks the index service with ``ref.series_market``;
    the gate expects ``MARKET_CURRENCY`` of that market, so the row must name
    the same market the adapter tags the series with.
    """
    assert INDEX_SYMBOL_METADATA[series_symbol] == (
        series_market,
        MARKET_CURRENCY[series_market],
    ), etf


@pytest.mark.parametrize(("market", "series_symbol"), _benchmark_rows())
def test_market_benchmark_agrees_with_metadata_and_market_currency(
    market: Market, series_symbol: str
) -> None:
    """Tripwire F9W-31 (a) / F9W-36 (TA5 R-61): red means back to risk-compliance with R-49.

    ``load_benchmark`` asks the index service with the holding's market.
    """
    assert INDEX_SYMBOL_METADATA[series_symbol] == (market, MARKET_CURRENCY[market])


# --- TA5 section 2 test 5: the shipped index wiring logs nothing ---------------------


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _fixture_yfinance() -> YFinanceAdapter:
    """The real adapter on recorded chart fixtures; nothing leaves the process."""
    twii = _fixture("yfinance_chart_twii.json")
    ndx = _fixture("yfinance_chart_ndx.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=twii if "TWII" in request.url.path else ndx)

    client = RateLimitedClient(
        base_url="https://query1.finance.yahoo.com",
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _seconds: None,
    )
    return YFinanceAdapter(client=client)


@pytest.mark.parametrize(("symbol", "market"), _asked_pairs())
def test_the_shipped_index_service_logs_nothing_for_any_asked_index(
    symbol: str,
    market: Market,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """TA5 test 5 (replaces ``test_index_ladder_is_explicitly_not_checked``).

    The index service exactly as ``deps`` builds it (``scope="index"``, the
    ``MARKET_CURRENCY`` lookup), over the real yfinance adapter -- which tags
    each series per ``INDEX_SYMBOL_METADATA`` -- asked for every pair the
    product asks for: no record carries the prefix, on the live read, the
    layer 0 read and the cache-only read. Tripwire as above (F9W-31 (a)).
    """
    cache = PriceBarCache(db_path=tmp_path / "index.db")
    adapter = _fixture_yfinance()
    monkeypatch.setattr(deps, "_default_cache", lambda: cache)
    monkeypatch.setattr(deps, "_default_yfinance", lambda: adapter)
    resolver = deps._default_index_resolver.__wrapped__()  # bypass lru_cache
    start, end = date(2024, 1, 1), date(2024, 1, 31)

    with caplog.at_level(logging.DEBUG, logger=SERVICE_LOGGER):
        live = resolver[market].get_daily_bars(symbol, market, start, end)
        again = resolver[market].get_daily_bars(symbol, market, start, end)
        cached = resolver[market].get_cached_bars(symbol, market, start, end)

    for result in (live, again, cached):
        assert result.bars, "precondition: the pair was actually served"
        assert {bar.market for bar in result.bars} == {market}
    assert [
        r for r in caplog.records if r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)
    ] == []
