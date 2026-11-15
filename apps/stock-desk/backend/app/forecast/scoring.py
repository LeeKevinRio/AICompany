"""The provisional comparison of one record (ADR-0030 D-5 point 5; ADR-0025 AV-18).

Pure functions: no IO, no clock, no registry. The caller passes a stored
record (:class:`ComparedRecord`), a later snapshot of the ledger that covers
the h final sessions after T, the union of final sessions over every stored
snapshot, and the date it reads as today.

* :func:`provisional_comparison` -- the realised label of (T, T+h] and, for
  the model and each of the four baselines B1, B2, B6, B8, whether its label
  equals it. ``None`` for a party is "not compared": an ``insufficient``
  model label or an ``unavailable`` baseline. When the input cannot support a
  comparison the result is "no comparison" with one reason, first that holds:

  - ``valid_until_not_passed`` -- ``today`` is not after
    ``valid_until_session_estimate`` (AV-18);
  - ``threshold_inputs_missing`` -- the record's ``band_def`` has no complete
    ``K_h`` / ``EPS`` / ``sigma_d`` (``app.forecast.band.threshold_inputs``,
    the one judgement of missing threshold inputs);
  - ``no_later_snapshot`` / ``t_not_in_snapshot`` /
    ``sessions_after_t_short`` -- the input is missing;
  - ``not_final`` -- a bar of [T, T+h] is not final
    (``app.data.session_calendar.is_final``);
  - ``session_gap`` -- the snapshot's sessions of [T, T+h] are not exactly
    the ledger's final sessions of that range (the dates are not contiguous);
  - ``base_close_differs`` -- the snapshot's close of T is not the record's
    ``base_close``;
  - ``price_unusable`` -- a close of T or T+h is not usable.

  The realised label is the pre-registration section 2.1 rule on
  ``z = ln(c_{T+h} / c_T) / (sigma_d * sqrt(h))`` with the record's own
  ``K_h``, ``EPS`` and ``sigma_d`` (``app.outlook.baselines.threshold_label``,
  the single definition of the label rule; ``app.outlook.volatility.log_return``).

Isolation (ADR-0030 D-5 point 5, K-7): nothing here is written to any table;
``store.py``, ``recorder.py`` and ``schema.py`` do not import this module, and
only ``app/forecast/report.py`` outputs its result, with
:data:`PROVISIONAL_BANNER` once at the start and once at the end of every
output. ADR-0012 C-15 (as revised by ADR-0025): forward return identifiers
are defined in this module only in ``app/forecast``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from app.data.session_calendar import is_final
from app.dirdef.definition import DirectionLabel
from app.forecast.band import threshold_inputs
from app.forecast.canonical import canonical_price
from app.outlook.baselines import UNAVAILABLE, threshold_label
from app.outlook.inputs import SNAPSHOT_MARKET, MarketSnapshot
from app.outlook.volatility import log_return

#: D-5 point 5: the fixed text at the start and at the end of every output.
PROVISIONAL_BANNER: Final = (
    "暫定對照：非正式結算，結果可能與日後正式結算不同；只對照發布當下可算的四個基準；"
    "不計入任何驗證統計，單筆符合與否不代表規則有效；規則未經驗證。"
)

#: The compared parties, in the one fixed order every output uses.
BASELINES: Final = ("B1", "B2", "B6", "B8")
MODEL: Final = "model"
PARTIES: Final = (*BASELINES, MODEL)

NoComparison = Literal[
    "valid_until_not_passed",
    "threshold_inputs_missing",
    "no_later_snapshot",
    "t_not_in_snapshot",
    "sessions_after_t_short",
    "not_final",
    "session_gap",
    "base_close_differs",
    "price_unusable",
]


class RecordUnreadableError(ValueError):
    """A stored record's columns cannot be read as a compared record."""


@dataclass(frozen=True)
class ComparedRecord:
    """The columns of one stored record the comparison reads."""

    data_as_of: date
    horizon: int
    label: str
    band_def: Mapping[str, object]
    base_close: str
    baseline_labels: Mapping[str, str]
    valid_until_session_estimate: date

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> ComparedRecord:
        """A ``forecast_record`` row as stored; ``RecordUnreadableError`` when it cannot be read."""
        try:
            band_def = json.loads(str(row["band_def"]))
            baselines = json.loads(str(row["baseline_predictions_json"]))
            labels = {key: str(baselines[key]["label"]) for key in BASELINES}
            if not isinstance(band_def, dict):
                raise TypeError("band_def is not an object")
            return cls(
                data_as_of=date.fromisoformat(str(row["data_as_of"])),
                horizon=int(str(row["horizon"])),
                label=str(row["label"]),
                band_def=band_def,
                base_close=str(row["base_close"]),
                baseline_labels=labels,
                valid_until_session_estimate=date.fromisoformat(
                    str(row["valid_until_session_estimate"])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RecordUnreadableError(
                f"stored record cannot be read ({type(exc).__name__})"
            ) from None


@dataclass(frozen=True)
class ProvisionalComparison:
    """One record's provisional comparison; ``reason`` is set exactly when there is none."""

    realized: DirectionLabel | None
    #: ``(party, matched)`` in :data:`PARTIES` order; ``None`` is "not compared".
    matches: tuple[tuple[str, bool | None], ...]
    reason: NoComparison | None


def _none(reason: NoComparison) -> ProvisionalComparison:
    return ProvisionalComparison(realized=None, matches=(), reason=reason)


def provisional_comparison(
    record: ComparedRecord,
    later: MarketSnapshot | None,
    *,
    known_sessions: Sequence[date],
    today: date,
) -> ProvisionalComparison:
    """The module docstring's comparison of ``record`` against the ``later`` snapshot."""
    if not today > record.valid_until_session_estimate:
        return _none("valid_until_not_passed")
    threshold = threshold_inputs(record.band_def)
    if threshold is None:
        return _none("threshold_inputs_missing")
    if later is None:
        return _none("no_later_snapshot")
    horizon = record.horizon
    sessions = [bar.session_date for bar in later.bars]
    if record.data_as_of not in sessions:
        return _none("t_not_in_snapshot")
    start = sessions.index(record.data_as_of)
    if len(sessions) - 1 - start < horizon:
        return _none("sessions_after_t_short")
    window = later.bars[start : start + horizon + 1]
    if not all(
        is_final(SNAPSHOT_MARKET, bar.session_date, bar.as_of, bar.fetched_at) for bar in window
    ):
        return _none("not_final")
    end = window[-1].session_date
    expected = [s for s in sorted(set(known_sessions)) if record.data_as_of <= s <= end]
    if [bar.session_date for bar in window] != expected:
        return _none("session_gap")
    if canonical_price(window[0].close) != record.base_close:
        return _none("base_close_differs")
    # Doubles as the computation reads closes (float(Decimal), correctly rounded).
    forward_return = log_return(float(window[-1].close), float(window[0].close))
    if forward_return is None:
        return _none("price_unusable")
    z = forward_return / (threshold.sigma_d * math.sqrt(horizon))
    realized = threshold_label(z, k=threshold.K_h, eps=threshold.EPS)
    matches: list[tuple[str, bool | None]] = [
        (key, None if label == UNAVAILABLE else label == realized)
        for key, label in ((key, record.baseline_labels[key]) for key in BASELINES)
    ]
    matches.append((MODEL, None if record.label == "insufficient" else record.label == realized))
    return ProvisionalComparison(realized=realized, matches=tuple(matches), reason=None)
