"""The one definition of a usable latest close (task F-1, constraint 1).

A data source can hand back a bar whose close is zero, negative or not a finite
number: ``PriceBar.close`` rejects none of those, and neither does the cache. A
consumer that prices anything from that close -- a market value, a risk cap, a
signal -- must treat it as *no price*, never as a price of 0 or -1. Every such
consumer asks this module, so the portfolio valuator, the advice card and the
alert engine can never disagree about which closes count.

This is a leaf: it imports nothing from ``app`` so any layer may depend on it
without creating a cycle (``app.portfolio`` in particular must not reach
``app.alerts`` or ``app.advice``, where the guard used to live).

It only *judges* a value. Dropping or repairing bars is a data-layer policy
that belongs to F-2, not here.
"""

from __future__ import annotations

import math
from decimal import Decimal


def usable_price(value: float | Decimal | None) -> bool:
    """Whether ``value`` may be used as a latest close.

    ``None``, zero, negative and non-finite values (NaN, +/-Infinity, and the
    ``Decimal`` equivalents including signalling NaN) are all "no price".
    """
    if value is None:
        return False
    if isinstance(value, Decimal):
        # ``Decimal.is_finite`` is checked first: comparing a signalling NaN
        # raises, and a quiet NaN compares unordered.
        return value.is_finite() and value > 0
    return math.isfinite(value) and value > 0
