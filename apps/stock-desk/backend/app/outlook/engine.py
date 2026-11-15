"""Market outlook computation: features, rules, record content (ADR-0030 D-1 ``engine.py``).

Pure functions over one snapshot (``app.outlook.inputs.SnapshotBar``); no IO,
no clock, no registry. The dirdef object and the rule set are passed in by the
caller as keyword arguments without defaults.

**Features** (freeze pack G2, sections 2.1-2.5). Lag k is the k-th snapshot
bar back from T (k = 0 is T); only ``close`` is read. The fields are exactly
``OUTLOOK_RULE_FIELDS``:

======================  =====================================================  =====
field                   formula                                                N_req
======================  =====================================================  =====
``close``               c_0                                                    1
``ma20`` / ``ma60``     ``float(sum(Fraction(c)) / L)`` over lags 0..L-1        20/60
``z_past_L``            ``log_return(c_0, c_L) / (sigma_d * math.sqrt(L))``     W + 1
``vol_ratio_20_120``    ``stdev(r_0..r_19) / stdev(r_0..r_119)``, all returns   121
``logret_past_L``       ``log_return(c_0, c_L)`` (placeholder rule sets only)   L + 1
======================  =====================================================  =====

``L`` is 20, 3, 5 for ``z_past``; W is the dirdef ``SIGMA_WINDOW`` and sigma_d
is ``app.outlook.volatility.sigma_at(closes, 0)``. A field is evaluable when
the snapshot has its N_req bars, every close it reads is usable, sigma_d is
available for ``z_past_*``, and the result is finite; otherwise its value is
``None``. The window lengths above are the feature definitions; no rule
parameter (``theta``, ``min_completeness``, a threshold, a weight) is written
in this module -- they are read from the rule set.

**Record judgement** (freeze pack 2.5 / 2.6; ADR-0025 D-2.3 (a)-(c), literally):

* (0) sigma_d(T) unavailable, or ``E-PIT-UNVERIFIED`` -> ``insufficient``;
* (a) evaluable rules / all rules ``< min_completeness`` -> ``insufficient``,
  compared as ``Fraction``;
* (b) ``W`` = sum of the hit bullish weights minus the hit bearish weights, as
  ``Fraction``; ``|W| < Fraction(theta)`` -> ``range``, with ``range_basis``
  ``range_evidence`` when a range rule hit, else ``conflicting_evidence``;
* (c) otherwise ``bullish`` for W > 0, ``bearish`` for W < 0.

The missing list holds root causes only, in this order, each at most once:
``E-BARS-SHORT`` (``index_bars``), ``E-PRICE-UNUSABLE`` (``index_close``, the
unusable sessions in ``detail``), ``E-VOL-SHORT`` / ``E-VOL-DEGENERATE``
(``sigma_d``), ``E-PIT-UNVERIFIED``. "Missing is non-empty iff the label is
insufficient" is checked on every result and a violation raises.

``W`` and the per-rule hits are written to ``evidence`` only, as a Fraction
string and booleans; they are not a strength or a confidence (PA-3).

**Entry points.** :func:`compute_outlook` is the recorder's: it takes a
captured ``MarketSnapshot`` (T is the snapshot's own last session) and has no
T, ``as_of`` or clock parameter. :func:`evaluate_outlook` and
``baselines.compute_baselines`` take the decision session and refuse any bar
after it (LA-G2-3). :func:`_cut_and_compute` cuts a longer series at a chosen
session with the same cut the recorder's path uses; it exists for the
look-ahead tests and stays private to ``app/outlook`` (risk RC-130: it is not
a backfill path, and must not be run on real ``^TWII`` data to produce the
registered rules' labels).
"""

from __future__ import annotations

import math
import operator
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Final, Literal, get_args

from app.dirdef.definition import DirectionDefinition, Horizon
from app.dirdef.rules import (
    OutlookAllOf,
    OutlookComparison,
    OutlookCondition,
    OutlookRuleSet,
    condition_fields,
)
from app.outlook.baselines import compute_baselines
from app.outlook.inputs import (
    MarketSnapshot,
    SnapshotBar,
    SnapshotView,
    _cut_snapshot,
    late_cutoff_at,
    snapshot_view,
)
from app.outlook.missing import MissingItem
from app.outlook.volatility import SigmaEstimate, log_return, sigma_at, usable, window_log_returns

Label = Literal["bullish", "range", "bearish", "insufficient"]
RangeBasis = Literal["range_evidence", "conflicting_evidence"]

E_BARS_SHORT: Final = "E-BARS-SHORT"
E_PRICE_UNUSABLE: Final = "E-PRICE-UNUSABLE"
E_PIT_UNVERIFIED: Final = "E-PIT-UNVERIFIED"
#: ``item`` of the ``E-PIT-UNVERIFIED`` missing entry. The freeze pack leaves
#: the name to tech-architect (FX-F5, "item 由 TA 定"); this is a provisional
#: name pending that ruling.
PIT_ITEM: Final = "inputs_max_fetched_at"

#: Feature window lengths (freeze pack 2.3), keyed by field.
_MEAN_WINDOWS: Final[Mapping[str, int]] = {"ma20": 20, "ma60": 60}
_Z_WINDOWS: Final[Mapping[str, int]] = {"z_past_20": 20, "z_past_3": 3, "z_past_5": 5}
_LOGRET_WINDOWS: Final[Mapping[str, int]] = {"logret_past_3": 3, "logret_past_5": 5}
_VOL_RATIO: Final = "vol_ratio_20_120"
_VOL_SHORT: Final = 20
_VOL_LONG: Final = 120

_OPS: Final[Mapping[str, Callable[[float, float], bool]]] = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "eq": operator.eq,
    "ne": operator.ne,
    "abs_gt": lambda left, right: abs(left) > right,
    "abs_lt": lambda left, right: abs(left) < right,
}


class OutlookInvariantError(ValueError):
    """A computed result broke "missing is non-empty iff insufficient" (a program defect)."""


# --- Field requirements ----------------------------------------------------------------


@dataclass(frozen=True)
class FieldRequirement:
    """What one field needs from the snapshot (freeze pack 2.3)."""

    n_req: int
    lags: frozenset[int]
    needs_sigma: bool
    window: str
    formula_ref: str


def field_requirement(name: str, *, definition: DirectionDefinition) -> FieldRequirement:
    """The requirement of field ``name``; an unknown field raises ``KeyError``."""
    ref = f"freeze-pack-2.3:{name}"
    if name == "close":
        return FieldRequirement(1, frozenset({0}), False, "lag 0", ref)
    if name in _MEAN_WINDOWS:
        length = _MEAN_WINDOWS[name]
        return FieldRequirement(
            length, frozenset(range(length)), False, f"lags 0-{length - 1}", ref
        )
    if name in _Z_WINDOWS:
        length = _Z_WINDOWS[name]
        n_req = max(length + 1, definition.SIGMA_WINDOW + 1)
        window = f"lags {length}->0; sigma_d over r_0-r_{definition.SIGMA_WINDOW - 1}"
        return FieldRequirement(n_req, frozenset({0, length}), True, window, ref)
    if name == _VOL_RATIO:
        return FieldRequirement(
            _VOL_LONG + 1,
            frozenset(range(_VOL_LONG + 1)),
            False,
            f"r_0-r_{_VOL_SHORT - 1} over r_0-r_{_VOL_LONG - 1}",
            ref,
        )
    if name in _LOGRET_WINDOWS:
        length = _LOGRET_WINDOWS[name]
        return FieldRequirement(length + 1, frozenset({0, length}), False, f"lags {length}->0", ref)
    raise KeyError(name)


def ruleset_fields(ruleset: OutlookRuleSet) -> frozenset[str]:
    """Every field (``field`` and ``ref``) the rule set's conditions read."""
    return frozenset(path for rule in ruleset.rules for path in condition_fields(rule.condition))


def required_bars(ruleset: OutlookRuleSet, *, definition: DirectionDefinition) -> int:
    """R of ``E-BARS-SHORT``: max(W + 1, the largest N_req the rule set reads)."""
    reads = [
        field_requirement(name, definition=definition).n_req for name in ruleset_fields(ruleset)
    ]
    return max([definition.SIGMA_WINDOW + 1, *reads])


def n_snapshot(*, definition: DirectionDefinition, rulesets: Sequence[OutlookRuleSet]) -> int:
    """N_SNAPSHOT (freeze pack V32-07; ADR-0030 D-5 point 1), the single derivation.

    max(the rule sets' largest N_req, max(H) + ``B2_WINDOW`` + ``SIGMA_WINDOW``);
    one snapshot serves both claims.
    """
    if not rulesets:
        raise ValueError("N_SNAPSHOT needs the rule sets it serves")
    longest = max(
        field_requirement(name, definition=definition).n_req
        for ruleset in rulesets
        for name in ruleset_fields(ruleset)
    )
    horizons: tuple[int, ...] = get_args(Horizon)
    return max(longest, max(horizons) + definition.B2_WINDOW + definition.SIGMA_WINDOW)


# --- Features ----------------------------------------------------------------------------


def mean_close(closes_by_lag: Sequence[float], length: int) -> float | None:
    """The mean of lags ``0..length-1`` in exact rational arithmetic, rounded once (2.2)."""
    if len(closes_by_lag) < length:
        return None
    window = closes_by_lag[:length]
    if not all(usable(close) for close in window):
        return None
    return float(sum((Fraction(close) for close in window), Fraction(0)) / length)


def _finite(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None


@dataclass(frozen=True)
class Features:
    """Every ``OUTLOOK_RULE_FIELDS`` value of one snapshot, plus the sigmas behind them."""

    values: Mapping[str, float | None]
    sigma: SigmaEstimate
    sigma_20: float | None
    sigma_120: float | None


def _stdev_of(returns: Sequence[float | None]) -> float | None:
    if any(item is None for item in returns):
        return None
    return statistics.stdev([item for item in returns if item is not None])


def compute_features(view: SnapshotView, *, definition: DirectionDefinition) -> Features:
    """The features of ``view`` (freeze pack 2.3, 2.5 point 1)."""
    closes = view.closes_by_lag
    count = len(closes)
    sigma = sigma_at(closes, 0, definition=definition)
    values: dict[str, float | None] = {"close": closes[0] if usable(closes[0]) else None}
    for name, length in _MEAN_WINDOWS.items():
        values[name] = mean_close(closes, length)
    for name, length in _Z_WINDOWS.items():
        z: float | None = None
        if count >= field_requirement(name, definition=definition).n_req:
            ret = log_return(closes[0], closes[length])
            if ret is not None and sigma.value is not None:
                z = ret / (sigma.value * math.sqrt(length))
        values[name] = _finite(z)
    sigma_20 = _stdev_of(window_log_returns(closes, 0, _VOL_SHORT)) if count > _VOL_SHORT else None
    sigma_120 = _stdev_of(window_log_returns(closes, 0, _VOL_LONG)) if count > _VOL_LONG else None
    ratio: float | None = None
    if sigma_20 is not None and sigma_120 is not None and sigma_120 > 0:
        ratio = sigma_20 / sigma_120
    values[_VOL_RATIO] = _finite(ratio)
    for name, length in _LOGRET_WINDOWS.items():
        values[name] = log_return(closes[0], closes[length]) if length < count else None
    return Features(values=values, sigma=sigma, sigma_20=sigma_20, sigma_120=sigma_120)


# --- Rules ---------------------------------------------------------------------------------


def holds(node: OutlookCondition, values: Mapping[str, float]) -> bool:
    """Whether the condition tree holds on ``values`` (every field it reads must be present).

    The one evaluator of outlook condition trees in ``app/``; ``condition`` and
    ``invalidation`` share it. Comparisons are IEEE 754 doubles.
    """
    if isinstance(node, OutlookComparison):
        left = values[node.field]
        right = values[node.ref] if node.ref is not None else node.value
        assert right is not None  # the model guarantees exactly one operand
        return _OPS[node.op](left, right)
    if isinstance(node, OutlookAllOf):
        return all(holds(child, values) for child in node.all)
    return any(holds(child, values) for child in node.any)


@dataclass(frozen=True)
class RuleResult:
    """One rule on one snapshot: evaluable (every field it reads is), and hit if so."""

    id: str
    direction: str
    weight: float
    evaluable: bool
    hit: bool | None


def evaluate_rules(ruleset: OutlookRuleSet, values: Mapping[str, float | None]) -> list[RuleResult]:
    """Every rule of ``ruleset`` on ``values`` (freeze pack 2.5 point 2)."""
    results: list[RuleResult] = []
    for rule in ruleset.rules:
        reads = condition_fields(rule.condition)
        known = {name: values[name] for name in reads}
        present = {name: value for name, value in known.items() if value is not None}
        evaluable = len(present) == len(known)
        hit = holds(rule.condition, present) if evaluable else None
        results.append(RuleResult(rule.id, rule.direction, rule.weight, evaluable, hit))
    return results


# --- Missing items -------------------------------------------------------------------------


def _stamp_text(stamp: datetime) -> str:
    return stamp.astimezone(UTC).isoformat(timespec="microseconds")


def _item(
    code: str,
    item: str,
    *,
    as_of: date,
    required: str | None = None,
    available: str | None = None,
    detail: Mapping[str, str] | None = None,
) -> MissingItem:
    return MissingItem(
        code=code,
        item=item,
        required=required,
        available=available,
        source=None,
        source_status=None,
        attempted_at=None,
        latest_available=None,
        as_of=as_of,
        detail=dict(detail or {}),
    )


def _pit_item(view: SnapshotView) -> MissingItem | None:
    """``E-PIT-UNVERIFIED`` when a bar's ``fetched_at`` is unusable or not before the cutoff."""
    cutoff = late_cutoff_at(view.data_as_of)
    aware = [
        stamp
        for stamp in view.fetched_by_lag
        if isinstance(stamp, datetime) and stamp.utcoffset() is not None
    ]
    unverified = len(aware) != len(view.fetched_by_lag) or any(s >= cutoff for s in aware)
    if not unverified:
        return None
    return _item(
        E_PIT_UNVERIFIED,
        PIT_ITEM,
        as_of=view.data_as_of,
        required=_stamp_text(cutoff),
        available=_stamp_text(max(aware)) if aware else None,
    )


def missing_items(
    view: SnapshotView,
    features: Features,
    *,
    ruleset: OutlookRuleSet,
    definition: DirectionDefinition,
) -> tuple[MissingItem, ...]:
    """The root-cause missing list of freeze pack 2.5 point 4, in its order."""
    found: list[MissingItem] = []
    count = len(view.closes_by_lag)
    as_of = view.data_as_of
    needed = required_bars(ruleset, definition=definition)
    if count < needed:
        found.append(
            _item(
                E_BARS_SHORT, "index_bars", as_of=as_of, required=str(needed), available=str(count)
            )
        )
    lags: set[int] = set()
    for name in ruleset_fields(ruleset):
        lags |= field_requirement(name, definition=definition).lags
    unusable = sorted(
        view.sessions_by_lag[lag]
        for lag in lags
        if lag < count and not usable(view.closes_by_lag[lag])
    )
    if unusable:
        sessions = ",".join(day.isoformat() for day in unusable)
        found.append(
            _item(E_PRICE_UNUSABLE, "index_close", as_of=as_of, detail={"sessions": sessions})
        )
    sigma = features.sigma
    if sigma.missing_code == "E-VOL-SHORT":
        found.append(
            _item(
                sigma.missing_code,
                "sigma_d",
                as_of=as_of,
                required=str(definition.SIGMA_MIN_VALID),
                available=str(sigma.valid_returns),
            )
        )
    elif sigma.missing_code == "E-VOL-DEGENERATE":
        found.append(
            _item(
                sigma.missing_code,
                "sigma_d",
                as_of=as_of,
                required=repr(definition.SIGMA_FLOOR),
                available=repr(sigma.raw_std),
            )
        )
    pit = _pit_item(view)
    if pit is not None:
        found.append(pit)
    return tuple(found)


# --- Judgement --------------------------------------------------------------------------------


@dataclass(frozen=True)
class OutlookEvaluation:
    """The model's part of one record."""

    label: Label
    range_basis: RangeBasis | None
    missing: tuple[MissingItem, ...]
    evidence: dict[str, object]
    band_def: dict[str, object]
    features: Features
    rules: tuple[RuleResult, ...]


def _sum_weights(results: Iterable[RuleResult], direction: str) -> Fraction:
    return sum(
        (Fraction(r.weight) for r in results if r.hit and r.direction == direction), Fraction(0)
    )


def aggregate(
    results: Sequence[RuleResult], *, ruleset: OutlookRuleSet, blocked: bool
) -> tuple[Label, RangeBasis | None, Fraction | None]:
    """(0), (a), (b), (c) of freeze pack 2.5 / ADR-0025 D-2.3, in that order."""
    if blocked:
        return "insufficient", None, None
    evaluable = sum(1 for r in results if r.evaluable)
    if Fraction(evaluable, len(results)) < Fraction(ruleset.aggregation.min_completeness):
        return "insufficient", None, None
    w = _sum_weights(results, "bullish") - _sum_weights(results, "bearish")
    if abs(w) < Fraction(ruleset.aggregation.theta):
        range_hit = any(r.hit and r.direction == "range" for r in results)
        return "range", "range_evidence" if range_hit else "conflicting_evidence", w
    return ("bullish" if w > 0 else "bearish"), None, w


def _band_def(
    label: Label, sigma: SigmaEstimate, *, horizon: int, definition: DirectionDefinition
) -> dict[str, object]:
    k = definition.k_for(horizon)
    up: float | None = None
    down: float | None = None
    if label != "insufficient" and sigma.value is not None:
        width = k * sigma.value * math.sqrt(horizon)
        up = math.exp(width) - 1
        down = 1 - math.exp(-width)
    return {
        "K_h": k,
        "EPS": definition.EPS,
        "sigma_d": sigma.value,
        "valid_returns": sigma.valid_returns,
        "up_pct": up,
        "down_pct": down,
    }


def _evidence(
    bars: Sequence[SnapshotBar],
    view: SnapshotView,
    features: Features,
    results: Sequence[RuleResult],
    w: Fraction | None,
    *,
    ruleset: OutlookRuleSet,
    definition: DirectionDefinition,
) -> dict[str, object]:
    as_of = view.data_as_of.isoformat()
    fields = []
    for name in sorted(ruleset_fields(ruleset)):
        requirement = field_requirement(name, definition=definition)
        fields.append(
            {
                "name": name,
                "value": features.values[name],
                "n_req": requirement.n_req,
                "window": f"{requirement.window} to {as_of}",
                "formula_ref": requirement.formula_ref,
                "as_of": as_of,
            }
        )
    return {
        "data_as_of": as_of,
        "series": "^TWII",
        "sources": sorted({bar.source for bar in bars}),
        "fields": fields,
        "sigma": {
            "sigma_d": features.sigma.value,
            "valid_returns": features.sigma.valid_returns,
            "sigma_20": features.sigma_20,
            "sigma_120": features.sigma_120,
        },
        "rules": [{"id": r.id, "evaluable": r.evaluable, "hit": r.hit} for r in results],
        "aggregation": {
            "w": None if w is None else str(w),
            "theta": ruleset.aggregation.theta,
            "min_completeness": ruleset.aggregation.min_completeness,
            "evaluable_rules": sum(1 for r in results if r.evaluable),
            "total_rules": len(results),
        },
        "counter_evidence": [r.id for r in results if r.hit],
    }


def evaluate_outlook(
    bars: Sequence[SnapshotBar],
    *,
    data_as_of: date,
    ruleset: OutlookRuleSet,
    definition: DirectionDefinition,
    horizon: int,
) -> OutlookEvaluation:
    """The model's judgement of the snapshot ``bars`` for ``data_as_of``; later bars raise."""
    definition.k_for(horizon)  # an unknown horizon raises here
    view = snapshot_view(bars, data_as_of=data_as_of)
    features = compute_features(view, definition=definition)
    missing = missing_items(view, features, ruleset=ruleset, definition=definition)
    results = evaluate_rules(ruleset, features.values)
    blocked = features.sigma.value is None or any(m.code == E_PIT_UNVERIFIED for m in missing)
    label, range_basis, w = aggregate(results, ruleset=ruleset, blocked=blocked)
    if bool(missing) != (label == "insufficient"):
        raise OutlookInvariantError(
            "missing must be non-empty exactly when the label is insufficient"
        )
    return OutlookEvaluation(
        label=label,
        range_basis=range_basis,
        missing=missing,
        evidence=_evidence(
            bars, view, features, results, w, ruleset=ruleset, definition=definition
        ),
        band_def=_band_def(label, features.sigma, horizon=horizon, definition=definition),
        features=features,
        rules=tuple(results),
    )


# --- Record content ------------------------------------------------------------------------


@dataclass(frozen=True)
class OutlookOutcome:
    """Everything one record needs from the computation (ADR-0030 D-2 point 4)."""

    data_as_of: date
    evaluation: OutlookEvaluation
    base_close: Decimal
    baseline_predictions: dict[str, dict[str, object]]


def _compute(
    bars: Sequence[SnapshotBar],
    *,
    ruleset: OutlookRuleSet,
    definition: DirectionDefinition,
    horizon: int,
) -> OutlookOutcome:
    data_as_of = bars[-1].session_date
    evaluation = evaluate_outlook(
        bars, data_as_of=data_as_of, ruleset=ruleset, definition=definition, horizon=horizon
    )
    baselines = compute_baselines(
        bars, data_as_of=data_as_of, horizon=horizon, definition=definition
    )
    return OutlookOutcome(
        data_as_of=data_as_of,
        evaluation=evaluation,
        base_close=bars[-1].close,
        baseline_predictions=baselines,
    )


def compute_outlook(
    snapshot: MarketSnapshot,
    *,
    ruleset: OutlookRuleSet,
    definition: DirectionDefinition,
    horizon: int,
) -> OutlookOutcome:
    """The record content of a captured snapshot; T is the snapshot's last session."""
    return _compute(snapshot.bars, ruleset=ruleset, definition=definition, horizon=horizon)


def _cut_and_compute(
    series: Sequence[SnapshotBar],
    decision_date: date,
    *,
    size: int,
    ruleset: OutlookRuleSet,
    definition: DirectionDefinition,
    horizon: int,
) -> OutlookOutcome:
    """Cut ``series`` at ``decision_date`` (the recorder's cut) and compute (LA-G2 tests).

    Private to ``app/outlook``; not a backfill path (risk RC-130).
    """
    return _compute(
        _cut_snapshot(series, decision_date, size),
        ruleset=ruleset,
        definition=definition,
        horizon=horizon,
    )
