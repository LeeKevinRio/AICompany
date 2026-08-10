"""Dividend / rights (除權息) events and back-adjusted prices for backtesting.

Scope boundary -- read this before using anything in this package:

* **Back-adjusted prices are for backtesting and return measurement only.**
  They are a synthetic total-return series, not prices anyone could have
  traded at.
* **Position valuation, portfolio totals and every risk cap keep using the raw
  close.** That is the real market value of what the user actually holds; an
  adjusted price would overstate a long-held position's worth and silently
  loosen the risk limits computed from it.

See ``app.dividends.adjust`` for the full rationale.
"""
