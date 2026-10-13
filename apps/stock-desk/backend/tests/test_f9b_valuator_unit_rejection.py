"""F-9b commit 2: the valuator's token for a refused price answer (ADR-0024 D-7 (3)).

C-19 (valuator part), C-11 (valuation part), C-34 (b)(c)(d) (valuation part);
風控 F9W-18:

* ``rejection`` set -> ``missing == [SYMBOL_OR_UNIT_REJECTED]`` and nothing
  else, ``fx``/``fx_open`` ``None``, and the FX provider is never asked;
* ``rejection`` ``None`` with no bars -> the existing ``price`` /
  ``price_not_queried`` path, FX asked as before;
* bars -> valued normally, whatever reason rides along.

The valuator keys on ``rejection`` alone, never on "are the bars empty"
(D-7 (7)); refused answers are injected by a fake service built with the
``ProviderResult`` constructor.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.data.interface import DataStatus, Market, ProviderResult, Rejection
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.data.service import RECENT_ATTEMPT_FAILED_REASON, _combine_reasons
from app.portfolio.valuation import (
    CURRENCY_MARKET_MISMATCH,
    PRICE_NOT_QUERIED,
    SYMBOL_OR_UNIT_REJECTED,
    PositionValuator,
    PriceMode,
    PriceService,
    Valuation,
)
from app.positions.models import Currency, Position
from tests.api_helpers import recent_bars, trending_closes
from tests.f9b_helpers import (
    AV_QUOTA_REASON,
    T_15,
    W_A,
    W_C_PRIME_US,
    W_C_US,
    CannedPriceService,
    answered,
    failed,
    refused,
)

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
_TODAY = NOW.date()

#: Each category with a sentence its producer would attach.
REFUSALS: list[tuple[Rejection, str]] = [
    ("symbol_not_admitted", W_A),
    ("unit_mismatch", W_C_US.format(provider="yfinance")),
    ("unit_missing", W_C_PRIME_US.format(provider="yfinance")),
    ("cache_unit_rejected", T_15),
]


class _CountingFx(FxRateProvider):
    """A flat USD/TWD rate that counts every ask (C-19: zero asks on a refusal)."""

    source_id = "fake_fx"

    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date]] = []

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.calls.append((pair, start, end))
        rates = [
            FxRate(
                pair=pair,
                date=end - timedelta(days=offset),
                rate=Decimal("32"),
                as_of=NOW,
                source="fake_fx",
            )
            for offset in range(3)
        ]
        return FxRateResult(rates=rates, status=DataStatus.FRESH, as_of=NOW, source="fake_fx")


def _position(
    *,
    position_id: int = 1,
    symbol: str = "TSCO.LON",
    market: Market = "US",
    currency: Currency = "USD",
) -> Position:
    return Position(
        id=position_id,
        symbol=symbol,
        market=market,
        quantity=Decimal("10"),
        avg_cost=Decimal("100"),
        currency=currency,
        opened_at=date(2026, 1, 15),
        instrument_type="stock",
        note=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _valuator(
    service: PriceService, fx: FxRateProvider, *, mode: PriceMode = "live"
) -> PositionValuator:
    return PositionValuator(
        market_services={"TW": service, "US": service},
        fx_provider=fx,
        clock=lambda: NOW,
        price_mode=mode,
    )


def _assert_refused(valuation: Valuation) -> None:
    assert valuation.status == "insufficient_data"
    assert valuation.missing == [SYMBOL_OR_UNIT_REJECTED]
    for other in ("price", PRICE_NOT_QUERIED, "fx_now", "fx_open", CURRENCY_MARKET_MISMATCH):
        assert other not in valuation.missing
    assert valuation.price is None
    assert valuation.fx is None
    assert valuation.fx_open is None
    assert valuation.pnl_original is None
    assert valuation.pnl_twd is None
    assert valuation.asset_contribution_twd is None
    assert valuation.fx_contribution_twd is None


def test_the_token_is_new_and_distinct() -> None:
    assert SYMBOL_OR_UNIT_REJECTED == "symbol_or_unit_rejected"
    assert SYMBOL_OR_UNIT_REJECTED not in {
        "price",
        PRICE_NOT_QUERIED,
        "fx_now",
        "fx_open",
        CURRENCY_MARKET_MISMATCH,
    }


@pytest.mark.parametrize(("rejection", "reason"), REFUSALS)
def test_a_live_refusal_gets_the_one_token_and_asks_no_fx(
    rejection: Rejection, reason: str
) -> None:
    service = CannedPriceService(refused(rejection, reason))
    fx = _CountingFx()

    result = _valuator(service, fx).value_position(_position())

    _assert_refused(result.valuation)
    assert result.cost_twd is None
    assert result.market_value_twd is None
    assert result.change_basis is None
    assert fx.calls == []
    assert len(service.calls) == 1
    assert service.cached_calls == []


@pytest.mark.parametrize(("rejection", "reason"), REFUSALS)
def test_a_cache_only_refusal_gets_the_same_token(rejection: Rejection, reason: str) -> None:
    """D-7 (3): live and cache_only alike; the live path is never asked."""
    service = CannedPriceService(failed(None), cached=refused(rejection, reason))
    fx = _CountingFx()

    result = _valuator(service, fx, mode="cache_only").value_position(_position())

    _assert_refused(result.valuation)
    assert fx.calls == []
    assert service.calls == []
    assert len(service.cached_calls) == 1


@pytest.mark.parametrize(("rejection", "reason"), REFUSALS)
def test_a_twd_refusal_gets_the_same_token(rejection: Rejection, reason: str) -> None:
    service = CannedPriceService(refused(rejection, reason))
    fx = _CountingFx()

    result = _valuator(service, fx).value_position(
        _position(symbol="00679K", market="TW", currency="TWD")
    )

    _assert_refused(result.valuation)
    assert fx.calls == []


@pytest.mark.parametrize(("mode", "token"), [("live", "price"), ("cache_only", PRICE_NOT_QUERIED)])
def test_an_ordinary_empty_answer_keeps_the_existing_token(mode: PriceMode, token: str) -> None:
    """``rejection=None`` and no bars: the existing token, and FX is still asked (R-57)."""
    service = CannedPriceService(failed(AV_QUOTA_REASON))
    fx = _CountingFx()

    valuation = _valuator(service, fx, mode=mode).value_position(_position()).valuation

    assert valuation.status == "insufficient_data"
    assert valuation.missing == [token]
    assert SYMBOL_OR_UNIT_REJECTED not in valuation.missing
    assert valuation.fx is not None
    assert valuation.fx_open is not None
    assert len(fx.calls) == 2


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        pytest.param(
            DataStatus.CACHED_STALE,
            _combine_reasons([AV_QUOTA_REASON, W_C_PRIME_US.format(provider="yfinance")]),
            id="C-34(b)-W-c'+cache",
        ),
        pytest.param(DataStatus.BACKUP, None, id="C-34(c)-readback-blocked-then-whole-range"),
        pytest.param(DataStatus.CACHED_STALE, RECENT_ATTEMPT_FAILED_REASON, id="C-34(d)-T-17"),
    ],
)
@pytest.mark.parametrize("mode", ["live", "cache_only"])
def test_an_answer_with_bars_is_valued_normally(
    status: DataStatus, reason: str | None, mode: PriceMode
) -> None:
    """F9W-18: bars mean no new token, whatever reason rides along."""
    bars = recent_bars(trending_closes(5), symbol="AAPL", market="US", end=_TODAY)
    answer = answered(bars, status=status, reason=reason)
    service = CannedPriceService(answer, cached=answer)
    fx = _CountingFx()

    valuation = _valuator(service, fx, mode=mode).value_position(_position(symbol="AAPL")).valuation

    assert valuation.status == "ok"
    assert valuation.missing == []
    assert valuation.price is not None
    assert valuation.price.reason == reason
    assert valuation.fx is not None


def test_a_legacy_mismatch_row_is_still_judged_first() -> None:
    """X-3c precedes the price lookup: a refusing service is never asked about it."""
    service = CannedPriceService(refused("unit_mismatch", W_C_US.format(provider="yfinance")))
    fx = _CountingFx()

    valuation = (
        _valuator(service, fx).value_position(_position(market="US", currency="TWD")).valuation
    )

    assert valuation.missing == [CURRENCY_MARKET_MISMATCH]
    assert service.calls == []
    assert fx.calls == []


def test_a_refused_row_costs_the_book_no_fx_ask() -> None:
    """In one pass, only the valued row asks for its rates."""

    class _BySymbol:
        def __init__(self) -> None:
            self.ok = answered(
                recent_bars(trending_closes(5), symbol="AAPL", market="US", end=_TODAY),
                status=DataStatus.FRESH,
                reason=None,
            )

        def get_daily_bars(
            self, symbol: str, market: Market, start: date, end: date
        ) -> ProviderResult:
            return self.ok if symbol == "AAPL" else refused("symbol_not_admitted", W_A)

        def get_cached_bars(
            self, symbol: str, market: Market, start: date, end: date
        ) -> ProviderResult:
            raise AssertionError("live valuator")

    fx = _CountingFx()
    results = _valuator(_BySymbol(), fx).value_all(
        [_position(position_id=1, symbol="AAPL"), _position(position_id=2, symbol="TSCO.LON")]
    )

    assert [item.valuation.status for item in results] == ["ok", "insufficient_data"]
    assert results[1].valuation.missing == [SYMBOL_OR_UNIT_REJECTED]
    assert len(fx.calls) == 2
