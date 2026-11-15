"""The four baselines published with every market record: B1, B2, B6, B8 (ADR-0030 D-4 point 1).

Computed from the same snapshot as the model, at publication, never recomputed
(pre-registration §3; freeze pack V32-06). Every closing price, return and
sigma goes through ``app.outlook.volatility`` (``log_return``, ``sigma_at``);
the constants (``K_h``, ``EPS``, ``SIGMA_WINDOW``, ``B2_WINDOW``,
``B2_MIN_REALIZED``, ``MAJORITY_TIE_ORDER``) come from the dirdef object the
caller passes in. Nothing here reads a registry, a clock or a database.

* :func:`threshold_label` -- the pre-registration §2.1 label rule
  (``z > K + EPS`` bullish, ``z < -K - EPS`` bearish, otherwise range), the
  single definition in ``app/``;
* B1 -- the label of the realised window (T-h, T]: ``z = ln(c_0 / c_h) /
  (sigma_d(T-h) * sqrt(h))``, sigma_d(T-h) over ``r_h .. r_{h+W-1}``.
  Unavailable reasons, first that holds: ``E-BARS-SHORT`` (fewer than
  ``h + W + 1`` bars), ``E-PRICE-UNUSABLE`` (lag 0 or lag h close),
  ``E-VOL-SHORT`` / ``E-VOL-DEGENERATE`` (sigma_d(T-h)); audit: sigma_d(T-h),
  its valid returns and z;
* B2 -- the majority of the realised labels at the snapshot positions
  T' = lag h .. lag h + B2_WINDOW - 1, each the B1 rule anchored at T'. A
  position that cannot be labelled does not vote and is not replaced; fewer
  than ``B2_MIN_REALIZED`` votes is ``unavailable`` (``b2_realized_short``);
  ties follow ``MAJORITY_TIE_ORDER``; audit: the counts and the voting positions;
* B6 -- always ``range``;
* B8 -- the sign of ``ln(c_0 / c_h)``: above 0 bullish, below 0 bearish, exactly
  0 range; no K. Unavailable: ``E-BARS-SHORT`` (fewer than h + 1 bars),
  ``E-PRICE-UNUSABLE`` (lag 0 or lag h close).

:func:`compute_baselines` takes the decision session and refuses any bar after
it (freeze pack LA-G2-3). It is not called from outside ``app/outlook``; the
recorder reaches it through ``app.outlook.engine.compute_outlook``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from typing import Final

from app.dirdef.definition import DirectionDefinition, DirectionLabel
from app.outlook.inputs import SnapshotBar, snapshot_view
from app.outlook.volatility import SigmaEstimate, log_return, sigma_at, usable

UNAVAILABLE: Final = "unavailable"
B2_REALIZED_SHORT: Final = "b2_realized_short"
E_BARS_SHORT: Final = "E-BARS-SHORT"
E_PRICE_UNUSABLE: Final = "E-PRICE-UNUSABLE"


def threshold_label(z: float, *, k: float, eps: float) -> DirectionLabel:
    """The §2.1 label of a z value: ties and near-ties within EPS of the band are range."""
    if z > k + eps:
        return "bullish"
    if z < -k - eps:
        return "bearish"
    return "range"


def _close(closes_by_lag: Sequence[float], lag: int) -> float | None:
    return closes_by_lag[lag] if lag < len(closes_by_lag) else None


def _realised(
    closes_by_lag: Sequence[float], anchor: int, *, horizon: int, definition: DirectionDefinition
) -> tuple[DirectionLabel | None, float | None, SigmaEstimate]:
    """The §2.1 label of the window (anchor, anchor - h], with sigma_d at ``anchor``."""
    sigma = sigma_at(closes_by_lag, anchor, definition=definition)
    later = _close(closes_by_lag, anchor - horizon)
    ret = log_return(later, _close(closes_by_lag, anchor))
    if ret is None or sigma.value is None:
        return None, None, sigma
    z = ret / (sigma.value * math.sqrt(horizon))
    return threshold_label(z, k=definition.k_for(horizon), eps=definition.EPS), z, sigma


def _b1(
    closes_by_lag: Sequence[float], *, horizon: int, definition: DirectionDefinition
) -> dict[str, object]:
    label, z, sigma = _realised(closes_by_lag, horizon, horizon=horizon, definition=definition)
    audit: dict[str, object] = {
        "sigma_d_t_minus_h": sigma.value,
        "valid_returns": sigma.valid_returns,
        "z": z,
    }
    if len(closes_by_lag) < horizon + definition.SIGMA_WINDOW + 1:
        return {"label": UNAVAILABLE, "reason": E_BARS_SHORT, **audit}
    if not (usable(closes_by_lag[0]) and usable(closes_by_lag[horizon])):
        return {"label": UNAVAILABLE, "reason": E_PRICE_UNUSABLE, **audit}
    if sigma.missing_code is not None:
        return {"label": UNAVAILABLE, "reason": sigma.missing_code, **audit}
    assert label is not None  # every reason it could be None for is handled above
    return {"label": label, **audit}


def _b2(
    closes_by_lag: Sequence[float], *, horizon: int, definition: DirectionDefinition
) -> dict[str, object]:
    counts: dict[DirectionLabel, int] = {"range": 0, "bullish": 0, "bearish": 0}
    for anchor in range(horizon, horizon + definition.B2_WINDOW):
        label, _, _ = _realised(closes_by_lag, anchor, horizon=horizon, definition=definition)
        if label is not None:
            counts[label] += 1
    voting = sum(counts.values())
    audit: dict[str, object] = {"counts": dict(counts), "voting_positions": voting}
    if voting < definition.B2_MIN_REALIZED:
        return {"label": UNAVAILABLE, "reason": B2_REALIZED_SHORT, **audit}
    top = max(counts.values())
    winner = next(label for label in definition.MAJORITY_TIE_ORDER if counts[label] == top)
    return {"label": winner, **audit}


def _b8(closes_by_lag: Sequence[float], *, horizon: int) -> dict[str, object]:
    if len(closes_by_lag) < horizon + 1:
        return {"label": UNAVAILABLE, "reason": E_BARS_SHORT, "logret_past_h": None}
    ret = log_return(closes_by_lag[0], closes_by_lag[horizon])
    if ret is None:
        return {"label": UNAVAILABLE, "reason": E_PRICE_UNUSABLE, "logret_past_h": None}
    label: DirectionLabel = "bullish" if ret > 0 else "bearish" if ret < 0 else "range"
    return {"label": label, "logret_past_h": ret}


def compute_baselines(
    bars: Sequence[SnapshotBar],
    *,
    data_as_of: date,
    horizon: int,
    definition: DirectionDefinition,
) -> dict[str, dict[str, object]]:
    """B1, B2, B6 and B8 of the snapshot ``bars`` for decision session ``data_as_of``."""
    definition.k_for(horizon)  # an unknown horizon raises here
    closes = snapshot_view(bars, data_as_of=data_as_of).closes_by_lag
    return {
        "B1": _b1(closes, horizon=horizon, definition=definition),
        "B2": _b2(closes, horizon=horizon, definition=definition),
        "B6": {"label": "range"},
        "B8": _b8(closes, horizon=horizon),
    }
