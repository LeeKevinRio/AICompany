"""B1, B2, B6, B8 at publication (ADR-0030 D-4 point 1; pre-registration §3; freeze pack V32-06).

Synthetic bars only. Cells:

* ``threshold_label``: strict inequalities with EPS; ties and near-ties are range;
* B1 = the §2.1 label of (T-h, T] with sigma_d(T-h); its unavailable reasons in
  the 2.5 order (bars short, price unusable, sigma); its audit fields;
* B2 = the majority over positions T' = lag h .. lag h + 249; a position that
  cannot be labelled does not vote; exactly ``B2_MIN_REALIZED`` votes is enough,
  one fewer is ``b2_realized_short``; ties follow ``MAJORITY_TIE_ORDER``;
* B6 = range; B8 = the sign of ln(c_0 / c_h), exactly 0 is range;
* LA-G2-3: a bar after the decision session raises.
"""

from __future__ import annotations

import ast
import math
import statistics
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.dirdef.definition import DirectionDefinition
from app.outlook.baselines import compute_baselines, threshold_label, z_score
from app.outlook.inputs import FutureBarError, SnapshotBar
from tests.dirdef_helpers import DIRDEF_V1_0_G7
from tests.import_graph import APP_ROOT
from tests.outlook_helpers import (
    bars_from_closes,
    definition,
    fixture_bars,
    snapshot_bar,
    with_close,
)


def _baselines(
    bars: Sequence[SnapshotBar], horizon: int = 3, **overrides: object
) -> dict[str, dict[str, Any]]:
    defn = (
        DirectionDefinition.model_validate({**DIRDEF_V1_0_G7, **overrides})
        if overrides
        else definition()
    )
    return compute_baselines(
        bars, data_as_of=bars[-1].session_date, horizon=horizon, definition=defn
    )


# --- threshold_label -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("z", "label"),
    [
        (0.43 + 1e-12, "range"),
        (math.nextafter(0.43 + 1e-12, math.inf), "bullish"),
        (-0.43 - 1e-12, "range"),
        (math.nextafter(-0.43 - 1e-12, -math.inf), "bearish"),
        (0.0, "range"),
        (0.43, "range"),
        (5.0, "bullish"),
        (-5.0, "bearish"),
    ],
)
def test_threshold_label(z: float, label: str) -> None:
    assert threshold_label(z, k=0.43, eps=1e-12) == label


# --- z_score (qa batch 5 supplement: one z for B1, B2 and the provisional comparison) --------


@pytest.mark.parametrize("horizon", [3, 5])
@pytest.mark.parametrize("ret", [0.0, 0.0123, -0.0456, 1e-300, -7.5])
@pytest.mark.parametrize("sigma", [0.01, 0.0153, 3e-5])
def test_z_score_is_the_inline_formula_bit_for_bit(horizon: int, ret: float, sigma: float) -> None:
    # The expression B1, B2 and scoring each wrote inline before it was shared.
    assert z_score(ret, sigma_d=sigma, horizon=horizon) == ret / (sigma * math.sqrt(horizon))


def _sqrt_owners(path: Path) -> list[str]:
    """The functions of ``path`` that reference ``sqrt`` (``"<module>"`` outside any)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))

    def is_sqrt(node: ast.AST) -> bool:
        return (isinstance(node, ast.Attribute) and node.attr == "sqrt") or (
            isinstance(node, ast.Name) and node.id == "sqrt"
        )

    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    owners = [f.name for f in functions if any(is_sqrt(n) for n in ast.walk(f))]
    inside = {id(n) for f in functions for n in ast.walk(f)}
    if any(is_sqrt(n) and id(n) not in inside for n in ast.walk(tree)):
        owners.append("<module>")
    return owners


def _calls(path: Path, name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name
        for n in ast.walk(tree)
    )


def test_the_z_of_baselines_and_scoring_is_computed_by_z_score_only() -> None:
    baselines = APP_ROOT / "outlook" / "baselines.py"
    scoring = APP_ROOT / "forecast" / "scoring.py"
    assert _sqrt_owners(baselines) == ["z_score"]
    assert _sqrt_owners(scoring) == []
    assert _calls(baselines, "z_score") and _calls(scoring, "z_score")


def test_the_sqrt_scan_has_teeth(tmp_path: Path) -> None:
    source = tmp_path / "m.py"
    source.write_text("import math\ndef f(r, s, h):\n    return r / (s * math.sqrt(h))\n")
    assert _sqrt_owners(source) == ["f"]
    source.write_text("from math import sqrt\nX = 1 / sqrt(2)\n")
    assert _sqrt_owners(source) == ["<module>"]


# --- B1 ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("horizon", [3, 5])
def test_b1_is_the_label_of_the_realised_window(horizon: int) -> None:
    bars = fixture_bars("FX-B")
    closes = [float(b.close) for b in reversed(bars)]  # by lag
    returns = [math.log(closes[k] / closes[k + 1]) for k in range(horizon, horizon + 60)]
    sigma = statistics.stdev(returns)
    z = math.log(closes[0] / closes[horizon]) / (sigma * math.sqrt(horizon))
    b1 = _baselines(bars, horizon)["B1"]
    assert b1["sigma_d_t_minus_h"] == sigma
    assert b1["valid_returns"] == 60
    assert b1["z"] == z
    assert b1["label"] == threshold_label(z, k=0.43, eps=1e-12) == "bullish"


@pytest.mark.parametrize("horizon", [3, 5])
def test_b1_needs_h_plus_61_bars(horizon: int) -> None:
    bars = fixture_bars("FX-B")
    assert _baselines(bars[-(horizon + 61) :], horizon)["B1"]["label"] == "bullish"
    short = _baselines(bars[-(horizon + 60) :], horizon)["B1"]
    assert short["label"] == "unavailable" and short["reason"] == "E-BARS-SHORT"


@pytest.mark.parametrize("lag", [0, 3])
def test_b1_lag_0_or_lag_h_unusable_is_price_unusable(lag: int) -> None:
    b1 = _baselines(with_close(fixture_bars("FX-B"), lag, Decimal("0")))["B1"]
    assert (b1["label"], b1["reason"]) == ("unavailable", "E-PRICE-UNUSABLE")


def test_b1_sigma_reasons() -> None:
    flat = bars_from_closes([10000.0] * 315)
    b1 = _baselines(flat)["B1"]
    assert (b1["label"], b1["reason"], b1["sigma_d_t_minus_h"]) == (
        "unavailable",
        "E-VOL-DEGENERATE",
        None,
    )
    bars = fixture_bars("FX-B")
    for lag in range(10, 30, 3):  # 7 unusable closes in sigma_d(T-3)'s window: 46 valid
        bars = with_close(bars, lag, Decimal("0"))
    b1 = _baselines(bars)["B1"]
    assert (b1["label"], b1["reason"]) == ("unavailable", "E-VOL-SHORT")
    assert b1["valid_returns"] < 55


# --- B2 ----------------------------------------------------------------------------------------


def test_b2_votes_over_250_positions_with_the_tie_order() -> None:
    # FX-A, h = 3: odd positions realise +a (bullish), even ones -a (bearish): 125 / 125.
    b2 = _baselines(fixture_bars("FX-A"))["B2"]
    assert b2["counts"] == {"range": 0, "bullish": 125, "bearish": 125}
    assert b2["voting_positions"] == 250
    assert b2["label"] == "bullish"  # range > bullish > bearish
    flipped = _baselines(fixture_bars("FX-A"), MAJORITY_TIE_ORDER=("range", "bearish", "bullish"))
    assert flipped["B2"]["label"] == "bearish"


def test_b2_majority_without_a_tie() -> None:
    b2 = _baselines(fixture_bars("FX-B"))["B2"]
    counts = b2["counts"]
    assert sum(counts.values()) == b2["voting_positions"] == 250
    assert b2["label"] == max(counts, key=lambda k: counts[k])


@pytest.mark.parametrize(("horizon", "bars", "available"), [(3, 178, True), (3, 177, False)])
def test_b2_needs_120_voting_positions(horizon: int, bars: int, available: bool) -> None:
    # A position p votes when sigma_d(T') has 55 valid returns: p <= n - 56.
    result = _baselines(fixture_bars("FX-A")[-bars:], horizon)["B2"]
    assert result["voting_positions"] == bars - 56 - horizon + 1
    if available:
        assert result["label"] != "unavailable"
    else:
        assert (result["label"], result["reason"]) == ("unavailable", "b2_realized_short")


def test_b2_positions_that_cannot_be_labelled_do_not_vote() -> None:
    full = _baselines(fixture_bars("FX-A"))["B2"]["voting_positions"]
    holed = _baselines(with_close(fixture_bars("FX-A"), 100, Decimal("0")))["B2"]
    # Lag 100 is the label end of T'=100+h and the start of T'=100: both drop, nothing
    # is borrowed from an earlier position.
    assert holed["voting_positions"] < full


# --- B6, B8 ------------------------------------------------------------------------------------


def test_b6_is_always_range() -> None:
    for name in ("FX-A", "FX-B", "FX-C"):
        assert _baselines(fixture_bars(name))["B6"] == {"label": "range"}


@pytest.mark.parametrize(
    ("closes", "label"),
    [
        ([100.0, 100.0, 100.0, 101.0], "bullish"),
        ([100.0, 100.0, 100.0, 99.0], "bearish"),
        ([100.0, 120.0, 80.0, 100.0], "range"),
    ],
)
def test_b8_is_the_sign_of_the_past_h_return(closes: list[float], label: str) -> None:
    b8 = _baselines(bars_from_closes(closes))["B8"]
    assert b8["label"] == label
    assert b8["logret_past_h"] == math.log(closes[-1] / closes[0])


def test_b8_reasons() -> None:
    short = _baselines(bars_from_closes([100.0, 100.0, 101.0]))["B8"]
    assert (short["label"], short["reason"]) == ("unavailable", "E-BARS-SHORT")
    bad = _baselines(bars_from_closes([0.0, 100.0, 100.0, 101.0]))["B8"]
    assert (bad["label"], bad["reason"]) == ("unavailable", "E-PRICE-UNUSABLE")


def test_all_four_baselines_are_always_present() -> None:
    for bars in (fixture_bars("FX-B"), bars_from_closes([100.0])):
        assert set(_baselines(bars)) == {"B1", "B2", "B6", "B8"}


# --- LA-G2-3 -----------------------------------------------------------------------------------


def test_a_bar_after_the_decision_session_raises() -> None:
    bars = fixture_bars("FX-B")
    future = snapshot_bar(bars[-1].session_date + timedelta(days=1), Decimal("1"))
    with pytest.raises(FutureBarError):
        compute_baselines(
            [*bars, future],
            data_as_of=bars[-1].session_date,
            horizon=3,
            definition=definition(),
        )


@pytest.mark.parametrize("horizon", [1, 4, True])
def test_an_unknown_horizon_raises(horizon: int) -> None:
    with pytest.raises(ValueError):
        _baselines(fixture_bars("FX-A"), horizon)
