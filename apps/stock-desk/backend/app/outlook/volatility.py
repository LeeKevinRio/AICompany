"""The single sigma_d kernel (ADR-0027 D-1 ``volatility.py``; D-3 "scope and missing inputs", N-63).

``sigma_d(log_returns, *, definition)`` takes the window's daily log returns,
already chosen by the caller per V12-19 (each a finite float, or ``None`` for an
invalid day -- never filled in, never replaced by days outside the window), and
the registered dirdef object of the record's ``definition_version`` (keyword,
no default). Market, sector basket and symbol all use it. It returns a frozen
:class:`SigmaEstimate`, judged in this order:

1. ``valid_returns`` = the number of non-``None`` items;
2. ``valid_returns < SIGMA_MIN_VALID`` (0 included): ``value`` and ``raw_std``
   are ``None``, ``missing_code = E-VOL-SHORT``; no estimate is computed and
   degeneracy is not judged;
3. otherwise ``raw_std`` is the sample standard deviation (ddof=1) of the valid
   returns; ``raw_std < SIGMA_FLOOR`` (strict): ``value`` is ``None``,
   ``missing_code = E-VOL-DEGENERATE``;
4. otherwise ``value = raw_std`` and ``missing_code`` is ``None``.

None of these raises or yields NaN. NaN or +/-inf in the input is a program
defect and raises ``ValueError``; a non-float item raises ``TypeError``.

The estimator is :func:`statistics.stdev`, which sums in exact rational
arithmetic and rounds the square root once: a constant series gives exactly
``0.0`` and the same input always gives the same bits.

Imports: the standard library and the ``app.dirdef`` definition type only; no
registry read and no ``app.forecast.*`` import.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from app.dirdef.definition import DirectionDefinition

VolatilityMissingCode = Literal["E-VOL-SHORT", "E-VOL-DEGENERATE"]

E_VOL_SHORT: Final[VolatilityMissingCode] = "E-VOL-SHORT"
E_VOL_DEGENERATE: Final[VolatilityMissingCode] = "E-VOL-DEGENERATE"


@dataclass(frozen=True)
class SigmaEstimate:
    """The sigma_d(T) result (D-3 N-63 return contract)."""

    #: sigma_d to store in ``band_def``; ``None`` when either code applies.
    value: float | None
    valid_returns: int
    #: The computed sample std; only for the ``E-VOL-DEGENERATE`` item's ``available``.
    raw_std: float | None
    missing_code: VolatilityMissingCode | None

    def __post_init__(self) -> None:
        if isinstance(self.valid_returns, bool) or self.valid_returns < 0:
            raise ValueError("valid_returns must be a non-negative int")
        if self.missing_code == E_VOL_SHORT:
            consistent = self.value is None and self.raw_std is None
        elif self.missing_code == E_VOL_DEGENERATE:
            consistent = self.value is None and self.raw_std is not None
        else:
            consistent = (
                self.missing_code is None and self.value is not None and self.raw_std == self.value
            )
        if not consistent:
            raise ValueError("SigmaEstimate fields contradict its missing_code")


def sigma_d(
    log_returns: Sequence[float | None],
    *,
    definition: DirectionDefinition,
) -> SigmaEstimate:
    """sigma_d(T) of the window ``log_returns`` under ``definition``."""
    valid: list[float] = []
    for item in log_returns:
        if item is None:
            continue
        if not isinstance(item, float):
            raise TypeError(f"log returns must be floats or None, got {type(item).__name__}")
        if not math.isfinite(item):
            raise ValueError("log returns must be finite (NaN or infinity is a program defect)")
        valid.append(item)
    valid_returns = len(valid)
    if valid_returns < definition.SIGMA_MIN_VALID:
        return SigmaEstimate(
            value=None, valid_returns=valid_returns, raw_std=None, missing_code=E_VOL_SHORT
        )
    raw_std = statistics.stdev(valid)
    if raw_std < definition.SIGMA_FLOOR:
        return SigmaEstimate(
            value=None, valid_returns=valid_returns, raw_std=raw_std, missing_code=E_VOL_DEGENERATE
        )
    return SigmaEstimate(
        value=raw_std, valid_returns=valid_returns, raw_std=raw_std, missing_code=None
    )
