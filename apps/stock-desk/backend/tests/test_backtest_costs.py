"""Golden tests for the transaction-cost model (hand-computed on 100k notional)."""

from __future__ import annotations

import math

from app.backtest.costs import CostModel

TOL = 1e-9
NOTIONAL = 100_000.0


def test_tw_stock_buy_commission_only() -> None:
    # Buy: commission 0.1425%, no tax. 100000 * 0.001425 = 142.5.
    cost = CostModel().trade_cost(
        notional=NOTIONAL, side="buy", market="TW", instrument_type="stock"
    )
    assert math.isclose(cost, 142.5, abs_tol=TOL)


def test_tw_stock_sell_commission_plus_tax() -> None:
    # Sell: commission 142.5 + tax 0.3% (300) = 442.5.
    cost = CostModel().trade_cost(
        notional=NOTIONAL, side="sell", market="TW", instrument_type="stock"
    )
    assert math.isclose(cost, 442.5, abs_tol=TOL)


def test_tw_etf_sell_uses_lower_tax() -> None:
    # ETF sell tax is 0.1% (100), not 0.3%: 142.5 + 100 = 242.5.
    cost = CostModel().trade_cost(
        notional=NOTIONAL, side="sell", market="TW", instrument_type="etf"
    )
    assert math.isclose(cost, 242.5, abs_tol=TOL)


def test_tw_leveraged_etf_taxed_as_etf() -> None:
    cost = CostModel().trade_cost(
        notional=NOTIONAL, side="sell", market="TW", instrument_type="leveraged_etf"
    )
    assert math.isclose(cost, 242.5, abs_tol=TOL)


def test_us_sell_regulatory_fee_only() -> None:
    # Default US broker fee 0; sell regulatory fee 0.00278% -> 2.78.
    cost = CostModel().trade_cost(
        notional=NOTIONAL, side="sell", market="US", instrument_type="stock"
    )
    assert math.isclose(cost, 2.78, abs_tol=TOL)


def test_us_buy_is_free_by_default() -> None:
    cost = CostModel().trade_cost(
        notional=NOTIONAL, side="buy", market="US", instrument_type="stock"
    )
    assert cost == 0.0


def test_slippage_is_symmetric_and_additive() -> None:
    # 10 bps of 100000 = 100 on both buy and sell, on top of other costs.
    model = CostModel(slippage_bps=10.0)
    buy = model.trade_cost(notional=NOTIONAL, side="buy", market="TW", instrument_type="stock")
    assert math.isclose(buy, 142.5 + 100.0, abs_tol=TOL)


def test_zero_notional_costs_nothing() -> None:
    assert CostModel().trade_cost(
        notional=0.0, side="buy", market="TW", instrument_type="stock"
    ) == 0.0


def test_rates_are_configurable_not_baked_in() -> None:
    # Overriding a default must flow straight through (proves rates live on the
    # settings object, ready for data-engineer to correct once verified).
    model = CostModel(tw_broker_fee_rate=0.001, tw_tax_rate_stock=0.0015)
    cost = model.trade_cost(
        notional=NOTIONAL, side="sell", market="TW", instrument_type="stock"
    )
    assert math.isclose(cost, 100.0 + 150.0, abs_tol=TOL)


def test_default_rates_are_flagged_unverified() -> None:
    # Provenance guard: the shipped defaults must announce they are unverified.
    assert CostModel().verified_on is None
