"""Threshold snapshot judgement (ADR-0027 D-1 ``band.py``; D-3 "scope and missing inputs").

Pure functions, and the single definition of both:

* ``threshold_inputs(band_def)`` -- "missing" versus "complete" for a stored
  ``band_def``: ``K_h``, ``EPS`` and ``sigma_d`` must all be present numbers and
  ``sigma_d`` a positive finite one (the one implementation of pre-registration
  V22-07);
* ``labeled_snapshot_violations(band_def, *, horizon, definition)`` -- the
  closed violation list a labelled forecast must not have.

The store write validation, scoring, settlement, correction and the replay
pre-validation judge missing inputs only through these two functions. This
module reads no DB and imports neither ``scoring.py`` nor
``app/outlook/volatility.py``; the dirdef is described by the local
``BandDefinition`` Protocol and passed in by the caller.

Imports: the standard library, plus exactly one exception --
``ThresholdViolation`` and ``THRESHOLD_VIOLATION_ORDER`` from
``app.forecast.errors``, the single definition of the violation list in
``app/`` (not re-exported here). Per ADR-0027 D-1 ``band.py`` row, N-115
sentence (N115-10, landed 94fa2f9).

Numeric judgement, per ADR-0027 D-3 "scope and missing inputs", N-115
sentences (N115-6 landed 38572c1, N115-10 landed 94fa2f9):

* a value counts as a number only when
  ``isinstance(v, (int, float)) and not isinstance(v, bool)``; anything else
  (``bool``, strings, lists, dicts) is treated like null, never raised on;
* an ``int`` outside the IEEE 754 double range (``float()`` raises
  ``OverflowError``) is taken as +inf or -inf by its sign, by both functions;
* each violation is judged on its own condition, so one row can record several:
  ``sigma_d`` of 0, a negative value or -inf records both
  ``sigma_d_not_positive_finite`` and ``sigma_d_below_floor``; NaN and +inf only
  the former; a missing, null or non-numeric ``sigma_d`` records only
  ``sigma_d_missing``;
* ``valid_returns`` that is ``bool`` or not an ``int`` (``60.0`` included) is
  treated like null and records ``valid_returns_below_min``;
* ``K_h`` and ``EPS`` are compared with the definition bit for bit (IEEE 754
  representation): ``0.0`` and ``-0.0`` differ, and NaN never matches.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from app.forecast.errors import THRESHOLD_VIOLATION_ORDER, ThresholdViolation


class BandDefinition(Protocol):
    """The dirdef constants this module needs, for one ``definition_version``."""

    @property
    def EPS(self) -> float: ...

    @property
    def SIGMA_FLOOR(self) -> float: ...

    @property
    def SIGMA_MIN_VALID(self) -> int: ...

    def k_for(self, horizon: int) -> float:
        """The K of ``horizon`` in this definition."""
        ...


@dataclass(frozen=True)
class ThresholdInputs:
    """A complete threshold snapshot, as doubles."""

    K_h: float
    EPS: float
    sigma_d: float


def _number(value: object) -> float | None:
    """``value`` as a double, or ``None`` when it is not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, int):
        try:
            return float(value)
        except OverflowError:
            return math.inf if value > 0 else -math.inf
    return float(value)


def _bit_equal(value: float, expected: float | None) -> bool:
    if expected is None or math.isnan(value):
        return False
    return struct.pack("<d", value) == struct.pack("<d", expected)


def threshold_inputs(band_def: Mapping[str, object]) -> ThresholdInputs | None:
    """The complete threshold inputs of ``band_def``, or ``None`` when missing.

    Missing: ``K_h``, ``EPS`` or ``sigma_d`` absent, null or not a number, or
    ``sigma_d`` not a positive finite number. Never raises on a value.
    """
    k_h = _number(band_def.get("K_h"))
    eps = _number(band_def.get("EPS"))
    sigma_d = _number(band_def.get("sigma_d"))
    if k_h is None or eps is None or sigma_d is None:
        return None
    if not (math.isfinite(sigma_d) and sigma_d > 0):
        return None
    return ThresholdInputs(K_h=k_h, EPS=eps, sigma_d=sigma_d)


def labeled_snapshot_violations(
    band_def: Mapping[str, object],
    *,
    horizon: int,
    definition: BandDefinition,
) -> tuple[ThresholdViolation, ...]:
    """The violations of a labelled forecast's ``band_def``, in the closed order.

    ``definition`` is the dirdef registered for the row's ``definition_version``;
    an empty tuple means the snapshot is usable for a labelled forecast.
    """
    found: set[ThresholdViolation] = set()

    k_h = _number(band_def.get("K_h"))
    if k_h is None:
        found.add("k_h_missing")
    elif not _bit_equal(k_h, _number(definition.k_for(horizon))):
        found.add("k_h_mismatch")

    eps = _number(band_def.get("EPS"))
    if eps is None:
        found.add("eps_missing")
    elif not _bit_equal(eps, _number(definition.EPS)):
        found.add("eps_mismatch")

    sigma_d = _number(band_def.get("sigma_d"))
    if sigma_d is None:
        found.add("sigma_d_missing")
    else:
        if not (math.isfinite(sigma_d) and sigma_d > 0):
            found.add("sigma_d_not_positive_finite")
        if sigma_d < definition.SIGMA_FLOOR:
            found.add("sigma_d_below_floor")

    valid_returns = band_def.get("valid_returns")
    if (
        isinstance(valid_returns, bool)
        or not isinstance(valid_returns, int)
        or valid_returns < definition.SIGMA_MIN_VALID
    ):
        found.add("valid_returns_below_min")

    return tuple(violation for violation in THRESHOLD_VIOLATION_ORDER if violation in found)
