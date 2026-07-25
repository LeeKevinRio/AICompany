"""Shared, machine-readable result models for the signal engine.

Every indicator and every risk metric answers the same provenance question the
data layer already answers for price bars: *which inputs produced this number,
over what window, as of when, from which source?* (see
``app/data/interface.py`` and ADR-0002). That is why every result here carries
an :class:`InputsUsed` block plus ``as_of`` / ``source`` passed straight through
from the originating bars.

Design rules honoured across the package:

* Values are plain ``float`` (indicators run on pandas/numpy); the Decimal
  ``PriceBar`` prices are converted to float at exactly one boundary
  (:func:`app.signals.frame.bars_to_frame`) and never silently round-tripped.
* Undefined points are ``None``, never ``NaN``. A window with too few bars
  reports ``status="insufficient_data"`` -- it never fabricates a value.
* Nothing here emits a target price, a rating, or a buy/sell instruction. These
  are numeric measurements and explicit states only; recommendation logic is a
  later, separately reviewed phase (M3).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Status = Literal["ok", "insufficient_data"]


class InputsUsed(BaseModel):
    """Explicit provenance for a single computed result.

    ``columns`` lists the price-bar fields the number was derived from,
    ``window`` maps each window parameter to its bar count, and ``description``
    is a short human-readable note (English) of the method and its minimum data
    requirement. Together they let any consumer answer "where did this come
    from?" without re-reading the implementation.
    """

    model_config = ConfigDict(frozen=True)

    columns: list[str]
    window: dict[str, int]
    description: str


class IndicatorResult(BaseModel):
    """One technical indicator over an aligned date index.

    ``series`` maps each output line (e.g. ``macd``/``signal``/``histogram``) to
    a list the same length as ``dates``, with ``None`` wherever the value is not
    yet defined. ``last`` is the most recent defined value per line (``None`` if
    none is defined). When ``status`` is ``insufficient_data`` the series are
    empty and ``last`` values are ``None``.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    status: Status
    params: dict[str, float]
    dates: list[str]
    series: dict[str, list[float | None]]
    last: dict[str, float | None]
    inputs_used: InputsUsed
    as_of: str | None
    source: str | None
