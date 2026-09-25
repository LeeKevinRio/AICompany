"""The hindsight view factory and the bias label (ADR-0012 D-14).

A hindsight view ignores ``recorded_at``: it shows every row describing a
session up to ``t``, including rows written long afterwards (back-filled
history, today's classification applied to the past). That is exactly the
look-ahead the point-in-time views forbid, which is why this factory exists
only here and every output built on it is labelled.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Final

from app.data.panel import MarketPanel, PointInTimePanel, _hindsight_view

#: Carried by every row, report and chart of this package (ADR-0012 D-14).
BIAS_LABEL: Final = "含已知偏誤，不得上畫面"

#: The three known biases and the direction each one pushes the results
#: (methodology §5.4). Machine codes; the research report renders them.
BIAS_DIRECTIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        # Only names still listed today are in the history: overstates upwards.
        "survivorship": "overstates_upwards",
        # Today's classification applied to the past: leans towards momentum.
        "classification_lookahead": "leans_towards_momentum",
        # No historical ex-dividend restoration: high-yield sectors understated.
        "unrestored_dividends": "understates_high_yield_sectors",
    }
)


def hindsight_view(panel: MarketPanel, t: date) -> PointInTimePanel:
    """A ``regime="hindsight"`` view of decision date ``t`` (research only)."""
    return _hindsight_view(panel, t)
