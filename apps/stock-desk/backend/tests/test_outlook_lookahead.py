"""Look-ahead tests LA-G2-1 .. LA-G2-7 (freeze pack 2.11; risk RC-130).

The comparison is freeze pack 2.11's: the canonical JSON bytes of ``label``,
``range_basis``, ``band_def``, ``missing``, ``evidence`` and
``baseline_predictions`` (B1, B2, B6, B8 with their audit details, LA-G2-6), plus
``float.hex`` of every field value -- all must be identical.

The "cut + compute" entry with a chosen decision session is
``app.outlook.engine._cut_and_compute``: the recorder's own cut
(``inputs._cut_snapshot``) followed by the recorder's own computation
(``engine._compute``, which ``compute_outlook`` calls). It is private to
``app/outlook`` and only ever fed the synthetic LA-G2-1 series here.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from functools import cache
from typing import Any

import pytest

from app.dirdef.hashing import canonical_json
from app.dirdef.rules import OUTLOOK_RULE_FIELDS
from app.outlook.baselines import compute_baselines
from app.outlook.engine import OutlookOutcome, _cut_and_compute, compute_outlook, evaluate_outlook
from app.outlook.inputs import FutureBarError, SnapshotBar, capture_market_snapshot
from app.services.index import load_market_benchmark
from tests.import_graph import APP_ROOT
from tests.outlook_helpers import (
    FakeIndexService,
    definition,
    evening,
    fixture_bars,
    la_series,
    price_bar,
    price_bars,
    ruleset,
    snapshot_bar,
    with_close,
)
from tests.test_c15_identifiers import defined_names

SIZE = 315
SERIES = la_series(600)

#: Forward-looking identifiers (ADR-0012 C-15 forms plus fwd / forward / ahead / future_x).
FORWARD_IDENTIFIER = re.compile(
    r"forward_return|label_return|excess_gross|excess_net|round_trip_cost"
    r"|(^|_)(forward|fwd)(_|$)|_ahead(_|$)|^future_"
)


def fingerprint(outcome: OutlookOutcome) -> tuple[str, tuple[str, ...]]:
    evaluation = outcome.evaluation
    payload = {
        "label": evaluation.label,
        "range_basis": evaluation.range_basis,
        "band_def": evaluation.band_def,
        "missing": [m.model_dump(mode="json") for m in evaluation.missing],
        "evidence": evaluation.evidence,
        "baseline_predictions": outcome.baseline_predictions,
    }
    hexes = tuple(
        f"{name}={'None' if value is None else value.hex()}"
        for name, value in sorted(evaluation.features.values.items())
    )
    return canonical_json(payload), hexes


def _at(series: Sequence[SnapshotBar], t: int, horizon: int) -> OutlookOutcome:
    return _cut_and_compute(
        series,
        SERIES[t].session_date,
        size=SIZE,
        ruleset=ruleset(horizon),
        definition=definition(),
        horizon=horizon,
    )


@cache
def truncated(t: int, horizon: int) -> tuple[str, tuple[str, ...]]:
    """The reference: the series cut at bar t by slicing, X[:t+1]."""
    return fingerprint(_at(SERIES[: t + 1], t, horizon))


def _decoded(t: int, horizon: int) -> dict[str, Any]:
    decoded: dict[str, Any] = json.loads(truncated(t, horizon)[0])
    return decoded


def test_the_series_exercises_the_volatility_gate_and_short_snapshots() -> None:
    def gate_open(t: int) -> bool:
        rules = _decoded(t, 3)["evidence"]["rules"]
        return any(r["id"] == "high_volatility_range" and r["hit"] for r in rules)

    assert any(gate_open(t) for t in range(450, 500)), "the burst must open the gate"
    assert not gate_open(400)
    assert _decoded(10, 3)["label"] == "insufficient"
    assert len({_decoded(t, 3)["label"] for t in range(315, 600, 5)}) >= 2


# --- LA-G2-1 / LA-G2-6 -----------------------------------------------------------------------


@pytest.mark.parametrize("horizon", [3, 5])
def test_la_g2_1_truncation_does_not_change_any_result(horizon: int) -> None:
    differing = [
        t
        for t in range(len(SERIES))
        if fingerprint(_at(SERIES, t, horizon)) != truncated(t, horizon)
    ]
    assert differing == []


# --- LA-G2-2 / LA-G2-6 -----------------------------------------------------------------------

TAMPER_POINTS = (0, 59, 60, 120, 121, 250, 314, 315, 316, 449, 455, 470, 500, 597)


def _tampered(t: int, kind: str) -> list[SnapshotBar]:
    head, tail = SERIES[: t + 1], list(SERIES[t + 1 :])
    if kind == "times-10":
        tail = [replace(b, close=b.close * 10) for b in tail]
    elif kind == "zero":
        tail = [replace(b, close=Decimal("0.0")) for b in tail]
    elif kind == "nan":
        tail = [replace(b, close=Decimal("NaN")) for b in tail]
    elif kind == "repeated-session" and len(tail) >= 2:
        tail = [tail[0], replace(tail[1], session_date=tail[0].session_date), *tail[2:]]
    elif kind == "deleted" and tail:
        tail = tail[::2]
    elif kind == "inserted":
        # A bar on the first Saturday after t: a session that does not exist.
        day = SERIES[t].session_date
        saturday = day + timedelta(days=(5 - day.weekday()) % 7 or 7)
        extra = snapshot_bar(saturday, Decimal("1"))
        tail = sorted([*tail, extra], key=lambda b: b.session_date)
    return [*head, *tail]


@pytest.mark.parametrize("horizon", [3, 5])
@pytest.mark.parametrize(
    "kind", ["times-10", "zero", "nan", "repeated-session", "deleted", "inserted"]
)
def test_la_g2_2_tampering_after_t_does_not_change_any_result(horizon: int, kind: str) -> None:
    differing = [
        t
        for t in TAMPER_POINTS
        if fingerprint(_at(_tampered(t, kind), t, horizon)) != truncated(t, horizon)
    ]
    assert differing == []


def test_la_g2_2_the_tampering_is_real() -> None:
    t = 400
    assert _tampered(t, "times-10")[t + 1].close == SERIES[t + 1].close * 10
    assert _tampered(t, "nan")[t + 1].close.is_nan()
    repeated = _tampered(t, "repeated-session")
    assert repeated[t + 2].session_date == repeated[t + 1].session_date
    assert len(_tampered(t, "deleted")) < len(SERIES)
    inserted = _tampered(t, "inserted")
    assert len(inserted) == len(SERIES) + 1
    assert {b.session_date.weekday() for b in inserted[t + 1 :]} & {5}


# --- LA-G2-3 -----------------------------------------------------------------------------------


def test_la_g2_3_engine_and_baselines_refuse_a_future_bar() -> None:
    bars = fixture_bars("FX-B")
    t = bars[-1].session_date
    future = [*bars, snapshot_bar(t + timedelta(days=3), Decimal("12000"))]
    with pytest.raises(FutureBarError):
        evaluate_outlook(
            future, data_as_of=t, ruleset=ruleset(3), definition=definition(), horizon=3
        )
    with pytest.raises(FutureBarError):
        compute_baselines(future, data_as_of=t, horizon=3, definition=definition())


def test_la_g2_3_the_snapshot_is_cut_in_one_function_only() -> None:
    # K-6: _cut_snapshot is defined once and the only slicing by decision session.
    holders = {
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*.py")
        if re.search(r"^def _cut_snapshot\(", path.read_text(encoding="utf-8"), re.M)
    }
    assert holders == {"outlook/inputs.py"}


# --- LA-G2-4 -----------------------------------------------------------------------------------

READ_LAGS = (0, 3, 5, 19, 20, 59, 60, 119, 120)


def _feature_hex(bars: Sequence[SnapshotBar]) -> dict[str, str | None]:
    evaluation = evaluate_outlook(
        bars,
        data_as_of=bars[-1].session_date,
        ruleset=ruleset(3),
        definition=definition(),
        horizon=3,
    )
    return {k: None if v is None else v.hex() for k, v in evaluation.features.values.items()}


@pytest.mark.parametrize("lag", READ_LAGS)
def test_la_g2_4_a_read_lag_changes_a_feature(lag: int) -> None:
    bars = fixture_bars("FX-B")
    changed = with_close(bars, lag, bars[-1 - lag].close * Decimal("1.01"))
    assert _feature_hex(changed) != _feature_hex(bars)


def test_la_g2_4_lags_beyond_120_change_no_feature() -> None:
    bars = fixture_bars("FX-B")
    base = _feature_hex(bars)
    moved = [
        lag
        for lag in range(121, 315)
        if _feature_hex(with_close(bars, lag, bars[-1 - lag].close * Decimal("1.01"))) != base
    ]
    assert moved == []


def test_la_g2_4_only_b2_may_move_beyond_lag_120() -> None:
    bars = fixture_bars("FX-B")
    changed = with_close(bars, 200, bars[-201].close * Decimal("1.01"))
    before = compute_baselines(
        bars, data_as_of=bars[-1].session_date, horizon=3, definition=definition()
    )
    after = compute_baselines(
        changed, data_as_of=bars[-1].session_date, horizon=3, definition=definition()
    )
    assert {k: before[k] for k in ("B1", "B6", "B8")} == {k: after[k] for k in ("B1", "B6", "B8")}


# --- LA-G2-5 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("horizon", [3, 5])
def test_la_g2_5_a_non_final_bar_after_t_leaves_the_record_unchanged(horizon: int) -> None:
    # Computation level. The recorder level, with the TA SP-C clock premise (the
    # injected clock before the next day's 15:00) and the stored content_hash, is
    # tests/test_forecast_recorder.py::test_la_g2_5_*.
    bars = fixture_bars("FX-D")
    t = bars[-1].session_date
    following = t + timedelta(days=3 if t.weekday() == 4 else 1)
    early = price_bar(following, Decimal("99999"), evening(following, hour=14))
    outcomes = []
    for extra in ([], [early]):
        answer = load_market_benchmark(
            {"TW": FakeIndexService([*price_bars(bars), *extra])},
            market="TW",
            start=bars[0].session_date,
            end=following,
        )
        snapshot = capture_market_snapshot(answer, size=SIZE)
        assert snapshot is not None and snapshot.data_as_of == t
        outcomes.append(
            fingerprint(
                compute_outlook(
                    snapshot, ruleset=ruleset(horizon), definition=definition(), horizon=horizon
                )
            )
        )
    assert outcomes[0] == outcomes[1]


def test_the_recorder_path_equals_the_cut_and_compute_entry() -> None:
    # The LA-G2 entry is the recorder's path: capture + compute_outlook give the same bytes.
    bars = SERIES[:500]
    answer = load_market_benchmark(
        {"TW": FakeIndexService(price_bars(bars))},
        market="TW",
        start=bars[0].session_date,
        end=bars[-1].session_date,
    )
    snapshot = capture_market_snapshot(answer, size=SIZE)
    assert snapshot is not None
    for horizon in (3, 5):
        recorded = compute_outlook(
            snapshot, ruleset=ruleset(horizon), definition=definition(), horizon=horizon
        )
        assert fingerprint(recorded) == truncated(499, horizon)


# --- LA-G2-7 -----------------------------------------------------------------------------------


def test_la_g2_7_no_forward_identifier_in_the_outlook_package() -> None:
    found = {
        path.relative_to(APP_ROOT).as_posix(): hits
        for path in sorted((APP_ROOT / "outlook").rglob("*.py"))
        if (hits := sorted(n for n in defined_names(path) if FORWARD_IDENTIFIER.search(n)))
    }
    assert found == {}


def test_la_g2_7_the_forward_pattern_has_teeth() -> None:
    for name in ("forward_return_h", "fwd_z", "future_close", "label_return_3", "z_ahead"):
        assert FORWARD_IDENTIFIER.search(name)
    for name in ("z_past_3", "logret_past_5", "ma20", "sigma_at", "FutureBarError"):
        assert not FORWARD_IDENTIFIER.search(name)


def test_la_g2_7_every_feature_name_in_the_engine_is_a_rule_field() -> None:
    source = (APP_ROOT / "outlook" / "engine.py").read_text(encoding="utf-8")
    names = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.fullmatch(r"(z_past|logret_past|ma|vol_ratio|close)\w*", node.value)
    }
    assert names == set(OUTLOOK_RULE_FIELDS)
    assert all("past" in n or n in {"close", "ma20", "ma60", "vol_ratio_20_120"} for n in names)
