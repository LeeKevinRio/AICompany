"""API tests for ``GET /api/bars/{symbol}``: the raw series behind the K-line chart."""

from __future__ import annotations

from datetime import date

from app.api.signals import DEFAULT_LOOKBACK_DAYS
from app.data.interface import DataStatus
from tests.api_helpers import recent_bars, trending_closes
from tests.conftest import ApiHarness


def _seed(harness: ApiHarness, count: int = 120) -> None:
    harness.price_service.seed("2330", recent_bars(trending_closes(count)))


def test_bars_are_returned_ascending_with_the_full_ohlcv_shape(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness)
    body = api_harness.client.get("/api/bars/2330").json()
    assert body["status"] == "ok"
    assert body["symbol"] == "2330"
    assert body["market"] == "TW"
    assert body["reason"] is None
    assert "as_of" in body

    bars = body["bars"]
    assert len(bars) == 120
    assert set(bars[0]) == {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "currency",
        "source",
    }
    dates = [bar["date"] for bar in bars]
    assert dates == sorted(dates)
    assert dates[-1] == date.today().isoformat()


def test_prices_are_decimal_strings_not_floats(api_harness: ApiHarness) -> None:
    # Money crosses the wire as strings project-wide; a float here would quietly
    # reintroduce the precision loss the Decimal convention exists to prevent.
    _seed(api_harness, count=3)
    bars = api_harness.client.get("/api/bars/2330").json()["bars"]
    first = bars[0]
    for field in ("open", "high", "low", "close"):
        assert isinstance(first[field], str)
    assert first["close"] == "100.0"
    assert first["currency"] == "TWD"
    assert first["source"] == "fake"
    # Volume is a count, not money: it stays an integer.
    assert isinstance(first["volume"], int)


def test_bars_carry_the_data_provenance_block(api_harness: ApiHarness) -> None:
    _seed(api_harness, count=60)
    data = api_harness.client.get("/api/bars/2330").json()["data"]
    assert data["status"] == DataStatus.FRESH.value
    assert data["source"] == "fake"
    assert data["bar_count"] == 60
    assert data["first_bar_date"] < data["last_bar_date"]


def test_no_data_is_200_insufficient_with_an_empty_series(
    api_harness: ApiHarness,
) -> None:
    response = api_harness.client.get("/api/bars/9999")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    # Empty, never interpolated or fabricated.
    assert body["bars"] == []
    assert "沒有可用的日線資料" in body["reason"]
    assert body["data"]["bar_count"] == 0


def test_a_market_without_an_adapter_is_insufficient_not_500(
    api_harness: ApiHarness,
) -> None:
    response = api_harness.client.get("/api/bars/AAPL", params={"market": "US"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["bars"] == []
    assert "沒有 US 市場的行情來源" in body["reason"]


def test_default_window_matches_the_signals_endpoint(api_harness: ApiHarness) -> None:
    # The chart and its indicator overlay must cover the same range, or the two
    # series drift apart on the x-axis.
    _seed(api_harness)
    api_harness.client.get("/api/bars/2330")
    bars_call = api_harness.price_service.calls[-1]
    api_harness.client.get("/api/signals/2330")
    signals_call = api_harness.price_service.calls[-1]
    assert bars_call[2:] == signals_call[2:]
    assert (bars_call[3] - bars_call[2]).days == DEFAULT_LOOKBACK_DAYS


def test_lookback_days_is_honoured_and_bounded(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    api_harness.client.get("/api/bars/2330", params={"lookback_days": 30})
    _, _, start, end = api_harness.price_service.calls[-1]
    assert (end - start).days == 30
    assert len(api_harness.client.get(
        "/api/bars/2330", params={"lookback_days": 30}
    ).json()["bars"]) == 31

    assert api_harness.client.get(
        "/api/bars/2330", params={"lookback_days": 0}
    ).status_code == 422
    assert api_harness.client.get(
        "/api/bars/2330", params={"lookback_days": 5000}
    ).status_code == 422


def test_unknown_market_is_422(api_harness: ApiHarness) -> None:
    assert api_harness.client.get("/api/bars/2330", params={"market": "JP"}).status_code == 422


def test_a_degraded_rung_is_disclosed(api_harness: ApiHarness) -> None:
    _seed(api_harness, count=40)
    api_harness.price_service.status = DataStatus.CACHED_STALE
    api_harness.price_service.source = "cache"
    api_harness.price_service.staleness_minutes = 720
    body = api_harness.client.get("/api/bars/2330").json()
    assert body["status"] == "ok"
    assert body["data"]["status"] == "cached_stale"
    assert body["data"]["staleness_minutes"] == 720


def test_the_data_layers_own_reason_reaches_the_response(
    api_harness: ApiHarness,
) -> None:
    """A spent quota and a missing API key must not both arrive as "no data"."""
    api_harness.price_service.reason = "Alpha Vantage 今日查詢額度已用罄，請由備援來源接手。"
    body = api_harness.client.get("/api/bars/9999").json()
    assert body["status"] == "insufficient_data"
    assert "額度已用罄" in body["reason"]
    assert "額度已用罄" in body["data"]["reason"]
    # And the endpoint's own sentence is still there, not replaced.
    assert "沒有可用的日線資料" in body["reason"]


def test_ttl_freshness_is_disclosed_beside_the_cached_status(
    api_harness: ApiHarness,
) -> None:
    """ADR-0005 D-2: ``cached_stale`` alone cannot say how stale it really is."""
    _seed(api_harness, count=40)
    api_harness.price_service.status = DataStatus.CACHED_STALE
    api_harness.price_service.staleness_minutes = 30
    api_harness.price_service.is_within_ttl = True
    body = api_harness.client.get("/api/bars/2330").json()
    assert body["data"]["status"] == "cached_stale"
    assert body["data"]["is_within_ttl"] is True
