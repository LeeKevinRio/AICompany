"""The single Decimal->float boundary for the signal engine.

Price bars cross the data layer as :class:`~app.data.interface.PriceBar` with
``Decimal`` OHLC prices (exactness preserved end to end for money). Technical
and statistical indicators, however, are naturally float math and run on
pandas/numpy. This module is the *one explicit place* that converts bars into a
float ``DataFrame`` -- callers upstream keep Decimal, callers downstream get
float, and the conversion is never hidden inside an indicator.

The frame is sorted ascending by date, indexed by a ``DatetimeIndex``, and
rejects duplicate dates (data-quality is the data layer's job; a duplicate here
means a broken input, not something to silently paper over).
"""

from __future__ import annotations

from typing import Final

import pandas as pd

from app.data.interface import PriceBar

OPEN: Final = "open"
HIGH: Final = "high"
LOW: Final = "low"
CLOSE: Final = "close"
VOLUME: Final = "volume"

_COLUMNS: Final = [OPEN, HIGH, LOW, CLOSE, VOLUME]


def bars_to_frame(bars: list[PriceBar]) -> pd.DataFrame:
    """Convert bars into a float OHLCV frame indexed by date (ascending).

    Raises ``ValueError`` on duplicate dates. An empty list yields an empty
    frame with the expected columns so downstream code can branch on length
    rather than on a missing schema.
    """
    if not bars:
        empty = pd.DataFrame({c: pd.Series(dtype="float64") for c in _COLUMNS})
        empty.index = pd.DatetimeIndex([], name="date")
        return empty

    ordered = sorted(bars, key=lambda bar: bar.date)
    index = pd.DatetimeIndex([pd.Timestamp(bar.date) for bar in ordered], name="date")
    if index.has_duplicates:
        raise ValueError("bars contain duplicate dates; expected point-in-time-unique input")

    frame = pd.DataFrame(
        {
            OPEN: [float(bar.open) for bar in ordered],
            HIGH: [float(bar.high) for bar in ordered],
            LOW: [float(bar.low) for bar in ordered],
            CLOSE: [float(bar.close) for bar in ordered],
            VOLUME: [float(bar.volume) for bar in ordered],
        },
        index=index,
    )
    return frame


def provenance(bars: list[PriceBar]) -> tuple[str | None, str | None]:
    """Return ``(as_of, source)`` carried through from the most recent bar.

    ``as_of`` is the latest bar's retrieval timestamp (ISO 8601) and ``source``
    its producing adapter, so every derived number inherits the freshness and
    origin of the data it was computed from. Returns ``(None, None)`` for an
    empty input.
    """
    if not bars:
        return None, None
    latest = max(bars, key=lambda bar: bar.date)
    return latest.as_of.isoformat(), latest.source


def clean_series(series: pd.Series) -> list[float | None]:
    """Render a float Series as a JSON-safe list with ``NaN`` mapped to ``None``.

    Undefined points must be an explicit ``None`` (no value), never a ``NaN``
    masquerading as one.
    """
    return [None if pd.isna(value) else float(value) for value in series]


def last_defined(series: pd.Series) -> float | None:
    """Return the most recent non-``NaN`` value of ``series``, or ``None``."""
    valid = series.dropna()
    if valid.empty:
        return None
    return float(valid.iloc[-1])


def date_index(frame: pd.DataFrame) -> list[str]:
    """Return the frame's dates as ISO ``YYYY-MM-DD`` strings."""
    return [ts.date().isoformat() for ts in frame.index]
