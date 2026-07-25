"""Transaction-cost model for the backtester.

RATE-PROVENANCE NOTICE
======================
The default rates below (Taiwan broker commission, securities transaction tax,
US SEC/TAF-style fees) are values from the model's training knowledge of the
*then-current* regulations. This environment has **no external network access**,
so these figures could NOT be verified against a live regulatory source at
build time. They are therefore treated as **defaults on a settings object**, not
constants baked into any formula, so they can be overridden per backtest and
corrected centrally.

ACTION FOR data-engineer: once a networked environment is available, verify each
rate against the primary source (TWSE/FSC for TW fees and tax, SEC/FINRA fee
schedules for US), then update ``verified_on`` (currently ``None``) and the
values here. Until then every report built on these costs should be read as
"subject to rate verification".

Model (all rates are fractions of traded notional unless noted):

* TW broker commission: charged on both buy and sell.
* TW securities transaction tax: charged on **sell only**; 0.3% for ordinary
  stock, 0.1% for ETFs (day-trade discounts are out of scope here).
* US SEC/TAF-style fee: a small fee on **sell only** (proxy; exact schedule is
  per-fill and tiny -- flagged for verification).
* Slippage: symmetric, expressed in basis points of notional, applied on every
  trade to model execution away from the reference price.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.positions.models import InstrumentType, Market

Side = Literal["buy", "sell"]

# ETF-like instruments are taxed at the lower TW securities-transaction-tax rate.
_ETF_LIKE: frozenset[InstrumentType] = frozenset(
    {"etf", "leveraged_etf", "futures_etf"}
)


@dataclass(frozen=True)
class CostModel:
    """Configurable fee/tax/slippage rates. Defaults await verification (see module docstring)."""

    tw_broker_fee_rate: float = 0.001425
    tw_tax_rate_stock: float = 0.003
    tw_tax_rate_etf: float = 0.001
    us_broker_fee_rate: float = 0.0
    us_sell_regulatory_fee_rate: float = 0.0000278
    slippage_bps: float = 0.0
    #: ISO date the rates above were last verified against a primary source.
    #: ``None`` means UNVERIFIED -- data-engineer to set once online.
    verified_on: str | None = None

    def trade_cost(
        self,
        *,
        notional: float,
        side: Side,
        market: Market,
        instrument_type: InstrumentType,
    ) -> float:
        """Total cost (>= 0) of trading ``notional`` (absolute value) of an asset.

        Combines commission, any sell-side tax/regulatory fee, and symmetric
        slippage. ``notional`` is treated as an absolute traded value; a zero or
        negative notional costs zero.
        """
        gross = abs(notional)
        if gross == 0.0:
            return 0.0

        slippage = gross * self.slippage_bps / 10_000.0

        if market == "TW":
            commission = gross * self.tw_broker_fee_rate
            tax = 0.0
            if side == "sell":
                is_etf = instrument_type in _ETF_LIKE
                rate = self.tw_tax_rate_etf if is_etf else self.tw_tax_rate_stock
                tax = gross * rate
            return commission + tax + slippage

        # US
        commission = gross * self.us_broker_fee_rate
        regulatory = gross * self.us_sell_regulatory_fee_rate if side == "sell" else 0.0
        return commission + regulatory + slippage
