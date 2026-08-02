"""Unit tests for PositionValuator: missing-input handling and TWD short-circuit.

Uses in-memory fake price/FX providers so nothing touches the network.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.portfolio.valuation import PositionValuator, PriceService
from app.positions.models import Currency, InstrumentType, Position

NOW = datetime(2024, 3, 20, 12, 0, tzinfo=UTC)


def _clock() -> datetime:
    return NOW


def _position(
    *,
    market: Market = "US",
    currency: Currency = "USD",
    quantity: str = "10",
    avg_cost: str = "100",
    opened_at: date | None = date(2024, 1, 15),
    instrument_type: InstrumentType = "stock",
    symbol: str = "AAPL",
) -> Position:
    return Position(
        id=1,
        symbol=symbol,
        market=market,
        quantity=Decimal(quantity),
        avg_cost=Decimal(avg_cost),
        currency=currency,
        opened_at=opened_at,
        instrument_type=instrument_type,
        note=None,
        created_at=NOW,
        updated_at=NOW,
    )


class _FakePriceService(PriceService):
    def __init__(
        self, close: str | None, *, status: DataStatus = DataStatus.FRESH
    ) -> None:
        self._close = close
        self._status = status

    def get_daily_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        if self._close is None:
            return ProviderResult(
                bars=[], status=DataStatus.UNAVAILABLE, as_of=NOW, source="fake"
            )
        bar = PriceBar(
            symbol=symbol,
            market=market,
            date=end,
            open=Decimal(self._close),
            high=Decimal(self._close),
            low=Decimal(self._close),
            close=Decimal(self._close),
            volume=1,
            currency="USD" if market == "US" else "TWD",
            as_of=NOW,
            source="fake",
        )
        return ProviderResult(
            bars=[bar], status=self._status, as_of=NOW, source="fake"
        )


class _FakeFxProvider(FxRateProvider):
    source_id = "fake_fx"

    def __init__(self, rates_by_pair: dict[str, list[tuple[date, str]]]) -> None:
        self._rates_by_pair = rates_by_pair

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        raw = self._rates_by_pair.get(pair, [])
        rates = [
            FxRate(pair=pair, date=day, rate=Decimal(value), as_of=NOW, source="fake_fx")
            for day, value in raw
            if start <= day <= end
        ]
        if not rates:
            return FxRateResult(
                rates=[], status=DataStatus.UNAVAILABLE, as_of=NOW, source="fake_fx"
            )
        return FxRateResult(
            rates=rates, status=DataStatus.FRESH, as_of=NOW, source="fake_fx"
        )


def _valuator(
    *,
    services: dict[Market, PriceService],
    fx: dict[str, list[tuple[date, str]]],
) -> PositionValuator:
    return PositionValuator(
        market_services=services,
        fx_provider=_FakeFxProvider(fx),
        clock=_clock,
    )


def test_us_market_without_adapter_is_missing_price() -> None:
    # Both FX rates are available; only the price adapter is absent, so "price"
    # is the sole missing input.
    valuator = _valuator(
        services={},
        fx={"USDTWD": [(date(2024, 1, 15), "31.5"), (date(2024, 3, 20), "30.0")]},
    )
    result = valuator.value_position(_position())
    assert result.valuation.status == "insufficient_data"
    assert result.valuation.missing == ["price"]
    assert result.valuation.price is None
    assert result.cost_twd is None


def test_tw_position_has_zero_fx_contribution_and_is_ok() -> None:
    services: dict[Market, PriceService] = {"TW": _FakePriceService("550")}
    valuator = _valuator(services=services, fx={})
    position = _position(
        market="TW", currency="TWD", avg_cost="500", quantity="100", symbol="2330"
    )
    result = valuator.value_position(position)
    assert result.valuation.status == "ok"
    assert result.valuation.missing == []
    assert result.valuation.fx_contribution_twd == Decimal("0")
    assert result.valuation.pnl_twd == Decimal("5000")
    assert result.cost_twd == Decimal("50000")
    assert result.market_value_twd == Decimal("55000")


def test_us_position_ok_when_price_and_both_fx_available() -> None:
    services: dict[Market, PriceService] = {"US": _FakePriceService("110")}
    valuator = _valuator(
        services=services,
        fx={
            "USDTWD": [
                (date(2024, 1, 15), "31.5"),  # F0 (open date)
                (date(2024, 3, 20), "30.0"),  # F1 (today)
            ]
        },
    )
    result = valuator.value_position(_position())
    assert result.valuation.status == "ok"
    assert result.valuation.pnl_twd == Decimal("1500")
    assert result.valuation.asset_contribution_twd == Decimal("3000")
    assert result.valuation.fx_contribution_twd == Decimal("-1500")
    assert result.valuation.pnl_original is not None
    assert result.valuation.pnl_original.value == Decimal("100")
    assert result.valuation.pnl_original.currency == "USD"


def test_missing_fx_now_and_fx_open_are_flagged() -> None:
    services: dict[Market, PriceService] = {"US": _FakePriceService("110")}
    valuator = _valuator(services=services, fx={})  # no rates at all
    result = valuator.value_position(_position())
    assert result.valuation.status == "insufficient_data"
    assert result.valuation.missing == ["fx_now", "fx_open"]
    # Price was available, so the price sub-object and original-currency P&L
    # are still populated even though the TWD conversion cannot be done.
    assert result.valuation.price is not None
    assert result.valuation.pnl_original is not None
    assert result.valuation.pnl_twd is None


def test_fx_open_backtracks_within_seven_days() -> None:
    services: dict[Market, PriceService] = {"US": _FakePriceService("110")}
    # No rate exactly on the 2024-01-15 open date; nearest earlier is 2024-01-10
    # (5 days back, within the 7-day window).
    valuator = _valuator(
        services=services,
        fx={
            "USDTWD": [
                (date(2024, 1, 10), "31.5"),
                (date(2024, 3, 20), "30.0"),
            ]
        },
    )
    result = valuator.value_position(_position())
    assert result.valuation.status == "ok"
    assert result.valuation.fx_contribution_twd == Decimal("-1500")


def test_foreign_position_without_opened_at_is_missing_fx_open() -> None:
    # No open date means no date to price F0 at; no rate is substituted, so the
    # TWD conversion is refused while the original-currency P&L still stands.
    services: dict[Market, PriceService] = {"US": _FakePriceService("110")}
    valuator = _valuator(
        services=services,
        fx={"USDTWD": [(date(2024, 1, 15), "31.5"), (date(2024, 3, 20), "30.0")]},
    )
    result = valuator.value_position(_position(opened_at=None))
    assert result.valuation.status == "insufficient_data"
    assert result.valuation.missing == ["fx_open"]
    assert result.valuation.pnl_twd is None
    assert result.valuation.pnl_original is not None
    assert result.cost_twd is None


def test_twd_position_without_opened_at_is_still_ok() -> None:
    # A TWD position needs no FX rate at all, so a missing open date changes
    # nothing about its valuation.
    services: dict[Market, PriceService] = {"TW": _FakePriceService("550")}
    valuator = _valuator(services=services, fx={})
    position = _position(
        market="TW",
        currency="TWD",
        avg_cost="500",
        quantity="100",
        symbol="2330",
        opened_at=None,
    )
    result = valuator.value_position(position)
    assert result.valuation.status == "ok"
    assert result.valuation.pnl_twd == Decimal("5000")


def test_price_unavailable_status_is_missing_price() -> None:
    services: dict[Market, PriceService] = {
        "US": _FakePriceService(None, status=DataStatus.UNAVAILABLE)
    }
    valuator = _valuator(
        services=services,
        fx={"USDTWD": [(date(2024, 1, 15), "31.5"), (date(2024, 3, 20), "30.0")]},
    )
    result = valuator.value_position(_position())
    assert result.valuation.status == "insufficient_data"
    assert "price" in result.valuation.missing
