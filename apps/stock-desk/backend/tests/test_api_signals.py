"""API tests for ``GET /api/signals/{symbol}`` (offline fakes only)."""

from __future__ import annotations

from app.data.interface import DataStatus
from app.services.index import MARKET_BENCHMARK
from tests.api_helpers import oscillating_closes, recent_bars, trending_closes
from tests.conftest import ApiHarness


def _seed(harness: ApiHarness, count: int = 200) -> None:
    harness.price_service.seed("2330", recent_bars(trending_closes(count)))


def _seed_benchmark(harness: ApiHarness, count: int = 200) -> None:
    """Seed the TW benchmark index (``^TWII``) on the index service only.

    Oscillating closes on purpose: a benchmark whose returns have zero variance
    makes beta undefined, which would test the wrong branch.
    """
    series = MARKET_BENCHMARK["TW"].series_symbol
    harness.index_service.seed(
        series, recent_bars(oscillating_closes(count), symbol=series)
    )


def test_signals_returns_the_compute_signals_shape(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    body = api_harness.client.get("/api/signals/2330").json()
    assert body["status"] == "ok"
    assert body["symbol"] == "2330"
    assert body["market"] == "TW"
    assert "as_of" in body
    signals = body["signals"]
    # The payload is the engine's own output: same keys, no repackaging.
    assert set(signals) >= {"symbol", "bar_count", "as_of", "source", "technical", "risk"}
    assert set(signals["technical"]) == {
        "moving_averages",
        "rsi",
        "macd",
        "bollinger",
        "atr",
        "kd",
        "volume_zscore",
    }
    assert signals["technical"]["rsi"]["status"] == "ok"


def test_signals_carries_the_data_provenance_block(api_harness: ApiHarness) -> None:
    _seed(api_harness, count=120)
    body = api_harness.client.get("/api/signals/2330").json()
    data = body["data"]
    assert data["status"] == DataStatus.FRESH.value
    assert data["source"] == "fake"
    assert data["bar_count"] == 120
    assert data["first_bar_date"] < data["last_bar_date"]
    assert data["reason"] is None


def test_signals_without_data_is_200_insufficient_not_500(api_harness: ApiHarness) -> None:
    response = api_harness.client.get("/api/signals/9999")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["signals"] is None
    assert "沒有可用的日線資料" in body["reason"]
    assert body["data"]["bar_count"] == 0


def test_signals_for_a_market_without_an_adapter_says_so(api_harness: ApiHarness) -> None:
    # US has no price adapter; that must be an explained state, not a crash.
    response = api_harness.client.get("/api/signals/AAPL", params={"market": "US"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert "沒有 US 市場的行情來源" in body["reason"]


def test_signals_rejects_an_unknown_market(api_harness: ApiHarness) -> None:
    assert api_harness.client.get("/api/signals/2330", params={"market": "JP"}).status_code == 422


def test_short_history_keeps_per_indicator_insufficient_data(api_harness: ApiHarness) -> None:
    # 30 bars: RSI(14) is computable, MA60 is not. The aggregate is still ``ok``
    # and each indicator reports its own state -- that is the honesty contract.
    _seed(api_harness, count=30)
    body = api_harness.client.get("/api/signals/2330").json()
    assert body["status"] == "ok"
    assert body["signals"]["technical"]["moving_averages"]["last"].get("ma_60") is None
    assert body["signals"]["technical"]["rsi"]["status"] == "ok"


def test_lookback_window_is_passed_to_the_provider(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    api_harness.client.get("/api/signals/2330", params={"lookback_days": 90})
    symbol, market, start, end = api_harness.price_service.calls[-1]
    assert (symbol, market) == ("2330", "TW")
    assert (end - start).days == 90


def test_beta_is_computed_against_the_market_benchmark_index(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    _seed_benchmark(api_harness)
    body = api_harness.client.get("/api/signals/2330").json()
    beta = body["signals"]["risk"]["beta"]
    assert beta["status"] == "ok"
    assert beta["beta"] is not None
    assert beta["observations"] > 0
    # The label names the index actually used, not a generic "大盤".
    assert beta["benchmark"] == MARKET_BENCHMARK["TW"].label
    benchmark = body["benchmark"]
    assert benchmark["series_symbol"] == "^TWII"
    assert benchmark["available"] is True
    assert benchmark["reason"] is None
    # A non-official source is never presented as the freshest rung (ADR-0005).
    assert benchmark["status"] == DataStatus.BACKUP.value
    assert benchmark["notes"]


def test_the_benchmark_is_requested_by_index_code_over_the_same_window(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness)
    _seed_benchmark(api_harness)
    api_harness.client.get("/api/signals/2330", params={"lookback_days": 90})
    series, market, start, end = api_harness.index_service.calls[-1]
    assert (series, market) == ("^TWII", "TW")
    assert (end - start).days == 90
    # The index series is asked of the index service, never of the equity one.
    assert all(call[0] != "^TWII" for call in api_harness.price_service.calls)


def test_an_unavailable_benchmark_costs_beta_and_nothing_else(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    # The index service has no ^TWII bars; the symbol's own bars are fine.
    body = api_harness.client.get("/api/signals/2330").json()
    assert body["status"] == "ok"
    beta = body["signals"]["risk"]["beta"]
    assert beta["status"] == "insufficient_data"
    # No label: "no benchmark at all" must not read as "benchmark, short overlap".
    assert beta["benchmark"] is None
    # Every other measure still comes from the symbol's own bars.
    assert body["signals"]["risk"]["volatility"]["status"] == "ok"
    assert body["signals"]["risk"]["drawdown"]["status"] == "ok"
    assert body["signals"]["technical"]["rsi"]["status"] == "ok"
    assert body["signals"]["technical"]["moving_averages"]["status"] == "ok"
    # And the missing benchmark is stated, with the series that was wanted.
    benchmark = body["benchmark"]
    assert benchmark["available"] is False
    assert benchmark["series_symbol"] == "^TWII"
    assert "^TWII" in benchmark["reason"]


def test_a_benchmark_too_short_to_use_is_still_named(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    # The series was obtained, it is simply too short to produce a beta; that is
    # a different state from having no benchmark, and the label keeps them apart.
    _seed_benchmark(api_harness, count=2)
    beta = api_harness.client.get("/api/signals/2330").json()["signals"]["risk"]["beta"]
    assert beta["status"] == "insufficient_data"
    assert beta["beta"] is None
    assert beta["benchmark"] == MARKET_BENCHMARK["TW"].label


def test_no_benchmark_is_fetched_when_there_are_no_bars_to_measure(
    api_harness: ApiHarness,
) -> None:
    body = api_harness.client.get("/api/signals/9999").json()
    assert body["status"] == "insufficient_data"
    assert body["benchmark"] is None
    assert api_harness.index_service.calls == []


def test_degraded_source_is_disclosed_not_hidden(api_harness: ApiHarness) -> None:
    _seed(api_harness, count=80)
    api_harness.price_service.status = DataStatus.CACHED_STALE
    api_harness.price_service.source = "cache"
    api_harness.price_service.staleness_minutes = 900
    body = api_harness.client.get("/api/signals/2330").json()
    assert body["status"] == "ok"
    assert body["data"]["status"] == "cached_stale"
    assert body["data"]["staleness_minutes"] == 900
