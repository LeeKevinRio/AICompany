"""Contract tests for the core data-layer schema (PriceBar / ProviderResult)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.data.interface import DataStatus, PriceBar, ProviderResult


def _make_bar(**overrides: object) -> PriceBar:
    defaults: dict[str, object] = {
        "symbol": "2330",
        "market": "TW",
        "date": date(2024, 1, 2),
        "open": Decimal("594.00"),
        "high": Decimal("598.00"),
        "low": Decimal("590.00"),
        "close": Decimal("594.00"),
        "volume": 41_393_088,
        "currency": "TWD",
        "as_of": datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
        "source": "twse",
    }
    defaults.update(overrides)
    return PriceBar.model_validate(defaults)


def test_price_bar_round_trip_has_all_required_fields() -> None:
    bar = _make_bar()
    dumped = bar.model_dump()
    assert set(dumped.keys()) == {
        "symbol",
        "market",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "currency",
        "as_of",
        "source",
    }
    assert dumped["as_of"] == datetime(2024, 1, 2, 14, 0, tzinfo=UTC)
    assert dumped["source"] == "twse"


def test_price_bar_rejects_naive_as_of() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _make_bar(as_of=datetime(2024, 1, 2, 14, 0))


def test_price_bar_rejects_negative_volume() -> None:
    with pytest.raises(ValidationError, match="non-negative"):
        _make_bar(volume=-1)


def test_price_bar_rejects_blank_source() -> None:
    with pytest.raises(ValidationError):
        _make_bar(source="")


def test_price_bar_is_frozen() -> None:
    bar = _make_bar()
    with pytest.raises(ValidationError):
        bar.symbol = "2454"


def test_price_bar_only_accepts_tw_or_us_market() -> None:
    with pytest.raises(ValidationError):
        _make_bar(market="JP")


def test_provider_result_carries_status_as_of_source() -> None:
    result = ProviderResult(
        bars=[_make_bar()],
        status=DataStatus.FRESH,
        as_of=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
        source="twse",
        staleness_minutes=0,
    )
    assert result.status is DataStatus.FRESH
    assert result.source == "twse"
    assert result.staleness_minutes == 0


def test_provider_result_rejects_negative_staleness() -> None:
    with pytest.raises(ValidationError):
        ProviderResult(
            bars=[],
            status=DataStatus.CACHED_STALE,
            as_of=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
            source="cache",
            staleness_minutes=-5,
        )


def test_data_status_has_all_four_degradation_layers() -> None:
    assert {status.value for status in DataStatus} == {
        "fresh",
        "backup",
        "cached_stale",
        "unavailable",
    }
