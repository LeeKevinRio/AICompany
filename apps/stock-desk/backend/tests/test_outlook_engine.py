"""The market outlook engine against the freeze pack (sections 1.2, 2.5-2.7, 2.10, 3).

Synthetic data only (no real ``^TWII`` values anywhere; pre-registration §10, RC-130).

* golden values FX-A .. FX-E2: every feature within relative 1e-12 (absolute
  1e-15 where the expected value is 0), and votes, hits, W, label,
  ``range_basis`` and the band exactly / within the same tolerance -- for h3
  and h5 through the landed YAML files;
* missing fixtures FX-F1 .. FX-F5 (FX-F5 is RC-123: a PIT failure is
  insufficient even with every field evaluable);
* rule-level cases R1 .. R8 with injected field values; each of the 10 rules
  unevaluable in turn is insufficient; in normal volatility each vote has
  exactly one hit;
* the 54 vote combinations (27 x volatility state) against the freeze pack 1.2
  table, through the two YAML files;
* the grid property ``holds(invalidation) == not holds(condition)`` and the
  label / ``range_basis`` against the Appendix B reference on a boundary grid
  (TA Q1 test 2; freeze pack 2.7 test 2);
* N_SNAPSHOT is 315; the field table covers exactly ``OUTLOOK_RULE_FIELDS``;
* ``missing`` non-empty iff insufficient, checked on every result.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.advice.loader import BANNED_PHRASES
from app.dirdef import rules as rules_module
from app.dirdef.rules import BANNED_PHRASES_CONTEXT_KEY, OUTLOOK_RULE_FIELDS, OutlookRuleSet
from app.outlook.engine import (
    OutlookEvaluation,
    OutlookInvariantError,
    aggregate,
    evaluate_outlook,
    evaluate_rules,
    field_requirement,
    holds,
    mean_close,
    n_snapshot,
    required_bars,
)
from app.outlook.inputs import FutureBarError, SnapshotBar, late_cutoff_at
from tests.outlook_helpers import (
    bars_from_closes,
    definition,
    fixture_bars,
    ruleset,
    snapshot_bar,
    with_close,
)

REL = 1e-12
ABS_AT_ZERO = 1e-15


def _close_to(actual: float | None, expected: float) -> bool:
    if actual is None:
        return False
    if expected == 0:
        return abs(actual) <= ABS_AT_ZERO
    return abs(actual - expected) <= REL * abs(expected)


def _evaluate(bars: Sequence[SnapshotBar], horizon: int = 3) -> OutlookEvaluation:
    return evaluate_outlook(
        bars,
        data_as_of=bars[-1].session_date,
        ruleset=ruleset(horizon),
        definition=definition(),
        horizon=horizon,
    )


# --- Freeze pack 2.10: feature golden values (50-digit decimal, 15 decimals) ----------------

GOLDEN: dict[str, dict[str, float]] = {
    "close": {
        "FX-A": 10000,
        "FX-B": 10000,
        "FX-C": 10000,
        "FX-D": 10408.107741923882268,
        "FX-E1": 10000,
        "FX-E2": 10000,
    },
    "ma20": {
        "FX-A": 9950.249168745840268,
        "FX-B": 9763.677202287411144,
        "FX-C": 10243.763608700476025,
        "FX-D": 9970.654555842034381,
        "FX-E1": 9487.674847634721832,
        "FX-E2": 8974.924521826221792,
    },
    "ma60": {
        "FX-A": 9950.249168745840268,
        "FX-B": 9385.841723937167286,
        "FX-C": 10667.506594180140453,
        "FX-D": 9957.050964444571639,
        "FX-E1": 8832.666804460144304,
        "FX-E2": 7490.443411073297872,
    },
    "sigma_d": {
        "FX-A": 0.010084389681792,
        "FX-B": 0.010084389681792,
        "FX-C": 0.010084389681792,
        "FX-D": 0.011913056029198,
        "FX-E1": 0.019310136093052,
        "FX-E2": 0.019310136093052,
    },
    "z_past_20": {
        "FX-A": 0,
        "FX-B": 0.886942313043338,
        "FX-C": -0.886942313043338,
        "FX-D": 0.750795756192004,
        "FX-E1": 0.926381032935054,
        "FX-E2": 2.315952582337636,
    },
    "z_past_3": {
        "FX-A": 0.572518801243922,
        "FX-B": 0.916030081990276,
        "FX-C": -0.916030081990276,
        "FX-D": 2.423182883445697,
        "FX-E1": 1.255750409479961,
        "FX-E2": 1.793929156399945,
    },
    "z_past_5": {
        "FX-A": 0.443471156521669,
        "FX-B": 0.886942313043338,
        "FX-C": -0.886942313043338,
        "FX-D": 1.876989390480011,
        "FX-E1": 1.157976291168818,
        "FX-E2": 1.852762065870109,
    },
    "logret_past_3": {
        "FX-A": 0.01,
        "FX-B": 0.016,
        "FX-C": -0.016,
        "FX-D": 0.05,
        "FX-E1": 0.042,
        "FX-E2": 0.06,
    },
    "logret_past_5": {
        "FX-A": 0.01,
        "FX-B": 0.02,
        "FX-C": -0.02,
        "FX-D": 0.05,
        "FX-E1": 0.05,
        "FX-E2": 0.08,
    },
    "sigma_20": {
        "FX-A": 0.010259783520852,
        "FX-B": 0.010259783520852,
        "FX-C": 0.010259783520852,
        "FX-D": 0.015078740698501,
        "FX-E1": 0.030779350562555,
        "FX-E2": 0.030779350562555,
    },
    "sigma_120": {
        "FX-A": 0.010041928905069,
        "FX-B": 0.010041928905069,
        "FX-C": 0.010041928905069,
        "FX-D": 0.010995288015483,
        "FX-E1": 0.015339299776947,
        "FX-E2": 0.015339299776947,
    },
    "vol_ratio_20_120": {
        "FX-A": 1.021694498919715,
        "FX-B": 1.021694498919715,
        "FX-C": 1.021694498919715,
        "FX-D": 1.371382057229274,
        "FX-E1": 2.006568162179816,
        "FX-E2": 2.006568162179816,
    },
}

NAMES = ("FX-A", "FX-B", "FX-C", "FX-D", "FX-E1", "FX-E2")

#: Freeze pack 2.10 votes / labels table (same for h3 and h5).
LABELS: dict[str, tuple[set[str], str, str, str | None]] = {
    "FX-A": (
        {"trend_neutral", "momentum_neutral", "stretch_neutral"},
        "0",
        "range",
        "range_evidence",
    ),
    "FX-B": ({"trend_up", "momentum_up", "stretch_neutral"}, "2", "bullish", None),
    "FX-C": ({"trend_down", "momentum_down", "stretch_neutral"}, "-2", "bearish", None),
    "FX-D": (
        {"trend_up", "momentum_up", "stretch_up_reversal"},
        "1",
        "range",
        "conflicting_evidence",
    ),
    "FX-E1": ({"high_volatility_range", "stretch_neutral"}, "0", "range", "range_evidence"),
    "FX-E2": ({"high_volatility_range"}, "0", "range", "range_evidence"),
}

#: Freeze pack 2.10 threshold snapshot (K = 0.43): (up, down) per horizon.
BAND: dict[str, dict[int, tuple[float, float]]] = {
    "ABC": {3: (0.007538946206205, 0.007482535771537), 5: (0.009743394539880, 0.009649376854127)},
    "D": {3: (0.008912106311360, 0.008833382269486), 5: (0.011520367473484, 0.011389160163190)},
    "E": {3: (0.014485755045322, 0.014278914192023), 5: (0.018740310225185, 0.018395571508349)},
}
BAND_GROUP = {"FX-A": "ABC", "FX-B": "ABC", "FX-C": "ABC", "FX-D": "D", "FX-E1": "E", "FX-E2": "E"}


def _feature(evaluation: OutlookEvaluation, name: str) -> float | None:
    features = evaluation.features
    if name == "sigma_d":
        return features.sigma.value
    if name == "sigma_20":
        return features.sigma_20
    if name == "sigma_120":
        return features.sigma_120
    return features.values[name]


@pytest.mark.parametrize("horizon", [3, 5])
@pytest.mark.parametrize("fixture", NAMES)
@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_golden_feature_values(fixture: str, name: str, horizon: int) -> None:
    value = _feature(_evaluate(fixture_bars(fixture), horizon), name)
    assert _close_to(value, GOLDEN[name][fixture]), (fixture, name, value)


@pytest.mark.parametrize("fixture", NAMES)
def test_golden_valid_returns_are_60(fixture: str) -> None:
    assert _evaluate(fixture_bars(fixture)).features.sigma.valid_returns == 60


def test_fx_a_ma20_and_ma60_are_bit_equal() -> None:
    # Freeze pack 2.2: the Fraction mean makes the two theoretically equal means equal.
    values = _evaluate(fixture_bars("FX-A")).features.values
    assert values["ma20"] is not None and values["ma60"] is not None
    assert values["ma20"].hex() == values["ma60"].hex()


def test_a_running_float_sum_would_break_fx_a_bit_equality() -> None:
    # The reason 2.2 forbids a term-by-term float sum: on FX-A it leaves MA20 and
    # MA60 one ulp apart, while the Fraction mean gives the same double.
    closes = [float(b.close) for b in reversed(fixture_bars("FX-A"))]

    def running(length: int) -> float:
        total = 0.0
        for close in closes[:length]:
            total += close
        return total / length

    assert running(20) != running(60)
    assert math.ulp(running(20)) * 2 >= abs(running(20) - running(60))
    assert mean_close(closes, 20) == mean_close(closes, 60)


@pytest.mark.parametrize("horizon", [3, 5])
@pytest.mark.parametrize("fixture", NAMES)
def test_golden_votes_labels_and_bands(fixture: str, horizon: int) -> None:
    evaluation = _evaluate(fixture_bars(fixture), horizon)
    hits, w, label, basis = LABELS[fixture]
    assert {r.id for r in evaluation.rules if r.hit} == hits
    assert evaluation.evidence["aggregation"]["w"] == w  # type: ignore[index]
    assert evaluation.label == label
    assert evaluation.range_basis == basis
    assert evaluation.missing == ()
    up, down = BAND[BAND_GROUP[fixture]][horizon]
    assert _close_to(evaluation.band_def["up_pct"], up)  # type: ignore[arg-type]
    assert _close_to(evaluation.band_def["down_pct"], down)  # type: ignore[arg-type]
    assert evaluation.band_def["K_h"] == 0.43 and evaluation.band_def["EPS"] == 1e-12


def test_recomputing_the_same_snapshot_is_bit_identical() -> None:
    # Freeze pack 2.9: same snapshot, every field float.hex equal.
    first = _evaluate(fixture_bars("FX-D")).features.values
    second = _evaluate(fixture_bars("FX-D")).features.values
    assert {k: v.hex() for k, v in first.items() if v is not None} == {
        k: v.hex() for k, v in second.items() if v is not None
    }


# --- Freeze pack 2.10: missing fixtures ---------------------------------------------------------


def _codes(evaluation: OutlookEvaluation) -> list[tuple[str, str, str | None, str | None]]:
    return [(m.code, m.item, m.required, m.available) for m in evaluation.missing]


def _assert_insufficient(evaluation: OutlookEvaluation) -> None:
    assert evaluation.label == "insufficient"
    assert evaluation.range_basis is None
    assert evaluation.band_def["up_pct"] is None and evaluation.band_def["down_pct"] is None


def test_fx_f1_bars_short() -> None:
    bars = fixture_bars("FX-B")[-120:]
    evaluation = _evaluate(bars)
    _assert_insufficient(evaluation)
    assert _codes(evaluation) == [("E-BARS-SHORT", "index_bars", "121", "120")]
    assert _close_to(evaluation.band_def["sigma_d"], 0.010084389681792)  # type: ignore[arg-type]
    values = evaluation.features.values
    full = _evaluate(fixture_bars("FX-B")).features.values
    assert values["vol_ratio_20_120"] is None
    assert {k: v for k, v in values.items() if k != "vol_ratio_20_120"} == {
        k: v for k, v in full.items() if k != "vol_ratio_20_120"
    }


def test_fx_f2_degenerate_sigma() -> None:
    evaluation = _evaluate(bars_from_closes([10000.0] * 315))
    _assert_insufficient(evaluation)
    assert _codes(evaluation) == [("E-VOL-DEGENERATE", "sigma_d", "0.001", "0.0")]
    assert evaluation.band_def["sigma_d"] is None
    assert evaluation.band_def["valid_returns"] == 60
    values = evaluation.features.values
    assert values["ma20"] == values["ma60"] == values["close"] == 10000.0
    assert all(values[n] is None for n in ("z_past_20", "z_past_3", "z_past_5"))
    assert values["vol_ratio_20_120"] is None
    assert evaluation.features.sigma_120 == 0.0  # the 2.5 invariant's special case


def test_fx_f3_price_unusable_at_lag_30() -> None:
    bars = with_close(fixture_bars("FX-B"), 30, Decimal("0.0"))
    evaluation = _evaluate(bars)
    _assert_insufficient(evaluation)
    lag30 = bars[-31].session_date.isoformat()
    assert [(m.code, m.item, m.detail) for m in evaluation.missing] == [
        ("E-PRICE-UNUSABLE", "index_close", {"sessions": lag30})
    ]
    assert evaluation.features.sigma.valid_returns == 58
    assert _close_to(evaluation.band_def["sigma_d"], 0.010087337902782)  # type: ignore[arg-type]
    values = evaluation.features.values
    assert values["ma60"] is None and values["vol_ratio_20_120"] is None
    assert values["ma20"] is not None
    assert all(values[n] is not None for n in ("z_past_20", "z_past_3", "z_past_5"))
    assert _close_to(values["z_past_20"], 0.886683086875872)


def test_fx_f4_short_snapshot_with_a_sigma() -> None:
    evaluation = _evaluate(fixture_bars("FX-A")[-56:])
    _assert_insufficient(evaluation)
    assert _codes(evaluation) == [("E-BARS-SHORT", "index_bars", "121", "56")]
    assert evaluation.features.sigma.valid_returns == 55
    assert _close_to(evaluation.band_def["sigma_d"], 0.010090499582190)  # type: ignore[arg-type]


def test_fx_f5_a_bar_fetched_at_the_cutoff_is_pit_unverified() -> None:
    # RC-123: every field evaluable, PIT not proven -> insufficient under 2.5 (0).
    bars = fixture_bars("FX-B")
    last = bars[-1]
    cutoff = late_cutoff_at(last.session_date)
    bars[-1] = replace(last, fetched_at=cutoff)
    evaluation = _evaluate(bars)
    _assert_insufficient(evaluation)
    stamp = cutoff.isoformat(timespec="microseconds")
    assert _codes(evaluation) == [("E-PIT-UNVERIFIED", "inputs_max_fetched_at", stamp, stamp)]
    assert _close_to(evaluation.band_def["sigma_d"], 0.010084389681792)  # type: ignore[arg-type]
    full = _evaluate(fixture_bars("FX-B"))
    assert evaluation.features.values == full.features.values
    assert all(r.evaluable for r in evaluation.rules)


def test_one_microsecond_before_the_cutoff_is_verified() -> None:
    bars = fixture_bars("FX-B")
    last = bars[-1]
    early = late_cutoff_at(last.session_date) - timedelta(microseconds=1)
    bars[-1] = replace(last, fetched_at=early)
    assert _evaluate(bars).label == "bullish"


def test_an_older_bar_fetched_after_the_cutoff_is_pit_unverified_too() -> None:
    bars = fixture_bars("FX-B")
    old = bars[10]
    bars[10] = replace(old, fetched_at=late_cutoff_at(bars[-1].session_date))
    assert [m.code for m in _evaluate(bars).missing] == ["E-PIT-UNVERIFIED"]


def test_root_causes_are_listed_in_order_each_once() -> None:
    bars = fixture_bars("FX-A")[-56:]
    bars = with_close(bars, 1, Decimal("0"))
    bars = with_close(bars, 5, Decimal("0"))
    last = bars[-1]
    bars[-1] = replace(last, fetched_at=late_cutoff_at(last.session_date))
    codes = [m.code for m in _evaluate(bars).missing]
    assert codes == ["E-BARS-SHORT", "E-PRICE-UNUSABLE", "E-VOL-SHORT", "E-PIT-UNVERIFIED"]


def test_a_bar_after_the_decision_session_raises() -> None:
    bars = fixture_bars("FX-B")
    later = snapshot_bar(bars[-1].session_date + timedelta(days=1), Decimal("1"))
    with pytest.raises(FutureBarError):
        evaluate_outlook(
            [*bars, later],
            data_as_of=bars[-1].session_date,
            ruleset=ruleset(3),
            definition=definition(),
            horizon=3,
        )


# --- Freeze pack 2.10: rule-level cases -------------------------------------------------------

RULE_CASES: dict[str, tuple[tuple[float, float, float, float, float, float], set[str], str]] = {
    "R1": (
        (100, 100, 90, 0.5, 1.5, 1.5),
        {"trend_neutral", "momentum_neutral", "stretch_neutral"},
        "0",
    ),
    "R2": (
        (101, 100, 99, 0.5000000000000001, -1.5000000000000002, 1.5),
        {"trend_up", "momentum_up", "stretch_down_reversal"},
        "3",
    ),
    "R3": (
        (101, 100, 99, 0.5000000000000001, -1.5000000000000002, 1.5000000000000002),
        {"high_volatility_range"},
        "0",
    ),
    "R4": (
        (99, 100, 101, -0.6, 1.6, 1.0),
        {"trend_down", "momentum_down", "stretch_up_reversal"},
        "-3",
    ),
    "R5": (
        (101, 100, 101, -0.6, 1.6, 1.0),
        {"trend_neutral", "momentum_down", "stretch_up_reversal"},
        "-2",
    ),
    "R6": ((101, 100, 99, -0.6, 0.0, 1.0), {"trend_up", "momentum_down", "stretch_neutral"}, "0"),
    "R7": ((101, 100, 99, 0.6, 1.6, 1.0), {"trend_up", "momentum_up", "stretch_up_reversal"}, "1"),
    "R8": (
        (100, 100, 100, -0.5, -1.5, 3.0),
        {"trend_neutral", "momentum_neutral", "stretch_neutral", "high_volatility_range"},
        "0",
    ),
}
RULE_EXPECTED: dict[str, tuple[str, str | None]] = {
    "R1": ("range", "range_evidence"),
    "R2": ("bullish", None),
    "R3": ("range", "range_evidence"),
    "R4": ("bearish", None),
    "R5": ("bearish", None),
    "R6": ("range", "range_evidence"),
    "R7": ("range", "conflicting_evidence"),
    "R8": ("range", "range_evidence"),
}


def _values(
    horizon: int, close: float, ma20: float, ma60: float, z20: float, zh: float, vol: float
) -> dict[str, float | None]:
    return {
        "close": float(close),
        "ma20": float(ma20),
        "ma60": float(ma60),
        "z_past_20": z20,
        f"z_past_{horizon}": zh,
        "vol_ratio_20_120": vol,
    }


def _judge(horizon: int, values: Mapping[str, float | None]) -> tuple[str, str | None, Any]:
    results = evaluate_rules(ruleset(horizon), values)
    label, basis, w = aggregate(results, ruleset=ruleset(horizon), blocked=False)
    return label, basis, (results, w)


@pytest.mark.parametrize("horizon", [3, 5])
@pytest.mark.parametrize("case", sorted(RULE_CASES))
def test_rule_level_cases(case: str, horizon: int) -> None:
    row, hits, w = RULE_CASES[case]
    label, basis, (results, weight) = _judge(horizon, _values(horizon, *row))
    assert {r.id for r in results if r.hit} == hits
    assert str(weight) == w
    assert (label, basis) == RULE_EXPECTED[case]


@pytest.mark.parametrize("horizon", [3, 5])
@pytest.mark.parametrize("rule_index", range(10))
def test_each_rule_unevaluable_in_turn_is_insufficient(horizon: int, rule_index: int) -> None:
    rule = ruleset(horizon).rules[rule_index]
    field = sorted(set(rules_module.condition_fields(rule.condition)))[0]
    values = _values(horizon, *RULE_CASES["R6"][0])
    values[field] = None
    label, _, (results, _) = _judge(horizon, values)
    assert not results[rule_index].evaluable
    assert label == "insufficient"


# --- The boundary grid: TA Q1 test 2 and the Appendix B reference --------------------------------

_BELOW, _ABOVE = -math.inf, math.inf
_Z20 = sorted(
    {-0.6, math.nextafter(-0.5, _BELOW), -0.5, math.nextafter(-0.5, _ABOVE), 0.0}
    | {math.nextafter(0.5, _BELOW), 0.5, math.nextafter(0.5, _ABOVE), 0.6}
)
_ZH = sorted(
    {-1.6, math.nextafter(-1.5, _BELOW), -1.5, math.nextafter(-1.5, _ABOVE), 0.0}
    | {math.nextafter(1.5, _BELOW), 1.5, math.nextafter(1.5, _ABOVE), 1.6}
)
_VOL = [1.0, math.nextafter(1.5, _BELOW), 1.5, math.nextafter(1.5, _ABOVE), 3.0]
_LEVELS = [99.0, 100.0, 101.0]


def _grid(horizon: int) -> list[dict[str, float | None]]:
    return [
        _values(horizon, c, m20, m60, z20, zh, vol)
        for c, m20, m60 in itertools.product(_LEVELS, repeat=3)
        for z20 in _Z20
        for zh in _ZH
        for vol in _VOL
    ]


def _reference(values: Mapping[str, float | None], horizon: int) -> tuple[str, str | None]:
    """Appendix B with halving (theta 2), range_basis per the (i) edition (RC-118)."""
    close, ma20, ma60 = values["close"], values["ma20"], values["ma60"]
    z20, zh, vol = values["z_past_20"], values[f"z_past_{horizon}"], values["vol_ratio_20_120"]
    assert None not in (close, ma20, ma60, z20, zh, vol)
    assert close is not None and ma20 is not None and ma60 is not None
    assert z20 is not None and zh is not None and vol is not None
    trend = 1 if close > ma20 > ma60 else -1 if close < ma20 < ma60 else 0
    momentum = 1 if z20 > 0.5 else -1 if z20 < -0.5 else 0
    reversal = 1 if zh < -1.5 else -1 if zh > 1.5 else 0
    votes = (trend, momentum, reversal)
    total = sum(votes)
    high = vol > 1.5
    net = math.trunc(total / 2) if high else total
    if abs(net) >= 2:
        return ("bullish" if net > 0 else "bearish"), None
    if high or 0 in votes:
        return "range", "range_evidence"
    return "range", "conflicting_evidence"


@pytest.mark.parametrize("horizon", [3, 5])
def test_invalidation_is_the_negation_of_the_condition_on_the_grid(horizon: int) -> None:
    grid = _grid(horizon)
    assert len(grid) == 27 * 9 * 9 * 5
    violations = [
        (rule.id, point)
        for point in grid
        for rule in ruleset(horizon).rules
        if holds(rule.invalidation, point) == holds(rule.condition, point)  # type: ignore[arg-type]
    ]
    assert violations == []


@pytest.mark.parametrize("horizon", [3, 5])
def test_labels_match_the_appendix_b_reference_on_the_grid(horizon: int) -> None:
    mismatches = []
    for point in _grid(horizon):
        label, basis, (results, _) = _judge(horizon, point)
        if (label, basis) != _reference(point, horizon):
            mismatches.append(point)
        # ADR-0025 D-3: a non-insufficient result always has a rule hit (invalidations non-empty).
        assert any(r.hit for r in results)
    assert mismatches == []


@pytest.mark.parametrize("horizon", [3, 5])
def test_in_normal_volatility_each_vote_has_exactly_one_hit(horizon: int) -> None:
    votes = {
        "trend": ("trend_up", "trend_down", "trend_neutral"),
        "momentum": ("momentum_up", "momentum_down", "momentum_neutral"),
        "reversal": ("stretch_down_reversal", "stretch_up_reversal", "stretch_neutral"),
    }
    for point in _grid(horizon):
        vol = point["vol_ratio_20_120"]
        assert vol is not None
        if vol > 1.5:
            continue
        _, _, (results, _) = _judge(horizon, point)
        hit = {r.id for r in results if r.hit}
        for members in votes.values():
            assert len(hit & set(members)) == 1, point
        assert "high_volatility_range" not in hit


def test_a_ratio_of_exactly_1_5_is_not_high_volatility() -> None:
    _, _, (results, _) = _judge(3, _values(3, 101, 100, 99, 0.6, 0.0, 1.5))
    assert not next(r for r in results if r.id == "high_volatility_range").hit
    assert next(r for r in results if r.id == "trend_up").hit


# --- Freeze pack 1.2: the 54 cases ---------------------------------------------------------------

#: Representative field values per vote (+1, 0, -1).
_TREND = {1: (101.0, 100.0, 99.0), 0: (100.0, 100.0, 100.0), -1: (99.0, 100.0, 101.0)}
_MOMENTUM = {1: 0.6, 0: 0.0, -1: -0.6}
_REVERSAL = {1: -1.6, 0: 0.0, -1: 1.6}

#: Freeze pack 1.2 table, (i) columns: (S, has a zero vote) -> (normal, high-vol basis).
TABLE_1_2: dict[tuple[int, bool], tuple[tuple[str, str | None], tuple[str, str]]] = {
    (-3, False): (("bearish", None), ("range", "range_evidence")),
    (-2, True): (("bearish", None), ("range", "range_evidence")),
    (-1, False): (("range", "conflicting_evidence"), ("range", "range_evidence")),
    (-1, True): (("range", "range_evidence"), ("range", "range_evidence")),
    (0, True): (("range", "range_evidence"), ("range", "range_evidence")),
    (1, False): (("range", "conflicting_evidence"), ("range", "range_evidence")),
    (1, True): (("range", "range_evidence"), ("range", "range_evidence")),
    (2, True): (("bullish", None), ("range", "range_evidence")),
    (3, False): (("bullish", None), ("range", "range_evidence")),
}
TABLE_COUNTS = {(-3, False): 1, (-2, True): 3, (-1, False): 3, (-1, True): 3, (0, True): 7}
TABLE_COUNTS |= {(1, False): 3, (1, True): 3, (2, True): 3, (3, False): 1}


@pytest.mark.parametrize("horizon", [3, 5])
def test_the_54_cases_match_the_freeze_pack_table(horizon: int) -> None:
    seen: dict[tuple[int, bool], int] = {}
    normal: list[tuple[str, str | None]] = []
    high: list[tuple[str, str | None]] = []
    for trend, momentum, reversal in itertools.product((1, 0, -1), repeat=3):
        key = (trend + momentum + reversal, 0 in (trend, momentum, reversal))
        seen[key] = seen.get(key, 0) + 1
        for vol, bucket, column in ((1.0, normal, 0), (2.0, high, 1)):
            values = _values(horizon, *_TREND[trend], _MOMENTUM[momentum], _REVERSAL[reversal], vol)
            label, basis, _ = _judge(horizon, values)
            assert (label, basis) == TABLE_1_2[key][column], (key, vol)
            bucket.append((label, basis))
    assert seen == TABLE_COUNTS
    assert len(normal) + len(high) == 54
    assert sum(1 for x in normal if x[0] == "bullish") == 4
    assert sum(1 for x in normal if x[0] == "bearish") == 4
    assert sum(1 for x in normal if x == ("range", "range_evidence")) == 13
    assert sum(1 for x in normal if x == ("range", "conflicting_evidence")) == 6
    assert high == [("range", "range_evidence")] * 27


# --- Field table, N_SNAPSHOT, invariant ---------------------------------------------------------


def test_the_field_table_covers_exactly_the_rule_fields() -> None:
    for name in OUTLOOK_RULE_FIELDS:
        field_requirement(name, definition=definition())
    with pytest.raises(KeyError):
        field_requirement("unknown", definition=definition())


@pytest.mark.parametrize(
    ("name", "n_req"),
    [
        ("close", 1),
        ("ma20", 20),
        ("ma60", 60),
        ("z_past_20", 61),
        ("z_past_3", 61),
        ("z_past_5", 61),
        ("vol_ratio_20_120", 121),
        ("logret_past_3", 4),
        ("logret_past_5", 6),
    ],
)
def test_n_req_per_field(name: str, n_req: int) -> None:
    # Freeze pack 2.3 table.
    assert field_requirement(name, definition=definition()).n_req == n_req


def test_n_snapshot_is_315() -> None:
    assert n_snapshot(definition=definition(), rulesets=[ruleset(3), ruleset(5)]) == 315
    with pytest.raises(ValueError):
        n_snapshot(definition=definition(), rulesets=[])


@pytest.mark.parametrize("horizon", [3, 5])
def test_the_bars_short_threshold_is_121(horizon: int) -> None:
    assert required_bars(ruleset(horizon), definition=definition()) == 121


def _ruleset_with(**aggregation: float) -> OutlookRuleSet:
    data = ruleset(3).model_dump(mode="json")
    data["aggregation"] = {**data["aggregation"], **aggregation}
    return OutlookRuleSet.model_validate(data, context={BANNED_PHRASES_CONTEXT_KEY: BANNED_PHRASES})


def test_a_completeness_below_one_that_hides_a_root_cause_is_refused() -> None:
    # FX-F1 leaves 3 of 10 rules evaluable; min_completeness 0.3 lets that produce a
    # label while E-BARS-SHORT holds, so "missing iff insufficient" fails closed.
    bars = fixture_bars("FX-B")[-120:]
    with pytest.raises(OutlookInvariantError):
        evaluate_outlook(
            bars,
            data_as_of=bars[-1].session_date,
            ruleset=_ruleset_with(min_completeness=0.3),
            definition=definition(),
            horizon=3,
        )


def test_w_and_theta_are_compared_as_fractions() -> None:
    # theta = float(0.1 + 0.2): a float sum of the weights 0.1 and 0.2 equals it
    # (bullish under ``>=``), the exact sum of the two doubles is below it (range).
    theta = 0.1 + 0.2
    assert theta == 0.30000000000000004
    data = ruleset(3).model_dump(mode="json")
    data["aggregation"]["theta"] = theta
    weights = {"trend_up": 0.1, "momentum_up": 0.2}
    for rule in data["rules"]:
        if rule["id"] in weights:
            rule["weight"] = weights[rule["id"]]
    custom = OutlookRuleSet.model_validate(
        data, context={BANNED_PHRASES_CONTEXT_KEY: BANNED_PHRASES}
    )
    results = evaluate_rules(custom, _values(3, 101, 100, 99, 0.6, 0.0, 1.0))
    assert {r.id for r in results if r.hit} == {"trend_up", "momentum_up", "stretch_neutral"}
    assert 0.1 + 0.2 >= theta  # what a float comparison would conclude
    label, basis, w = aggregate(results, ruleset=custom, blocked=False)
    assert (label, basis) == ("range", "range_evidence")
    assert w is not None and w < theta


def test_every_result_keeps_missing_iff_insufficient() -> None:
    cases: list[list[SnapshotBar]] = [fixture_bars(name) for name in NAMES]
    cases += [fixture_bars("FX-B")[-n:] for n in (1, 2, 30, 61, 120, 121)]
    for bars in cases:
        for horizon in (3, 5):
            evaluation = _evaluate(bars, horizon)
            assert bool(evaluation.missing) == (evaluation.label == "insufficient")
