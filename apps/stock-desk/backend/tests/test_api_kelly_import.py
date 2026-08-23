"""``POST /api/kelly-inputs/{symbol}/import-backtest``: the imported half (D-3).

End-to-end over the real pipeline: a fake price service supplies bars, the
endpoint re-runs the backtest itself, extracts round trips from the out-of-sample
window and stores what it computed. Nothing here hands the server a p, a b or an
f\\*, because nothing may.

What these tests hold down (約束 26 第 7 項, 27, 29, 31, 32, 34):

* a cleared import writes the pair **and** its whole provenance, and the pair is
  the round-trip estimate, never the fill-layer one;
* every attempt is logged, refused ones included, with the gate's verdict --
  and a ``DELETE`` of the input afterwards leaves ``K_observed`` alone;
* each of the six refusal codes returns a structured 422 naming the numbers
  measured, and writes nothing;
* a non-finite f\\* bound fails the import rather than being stored;
* exactly one backtest runs per request, so p and b cannot come from two runs.

The price paths are seeded random walks chosen for their *sample shape*, not for
a flattering result: one that clears the 20/5/5 gate, one that produces round
trips that almost all lose, one where they almost all win. A smooth analytic
series would make every round trip a winner and could never exercise the gates.
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.advice.limits import kelly_fraction
from app.api import kelly as kelly_api
from app.api import kelly_wording
from app.backtest.engine import run_backtest
from app.backtest.episodes import FractionInterval, attribute_round_trips
from app.kelly.sample_gate import (
    INSUFFICIENT_DATA_MESSAGE,
    MIN_OOS_LOSS_TRIPS,
    MIN_OOS_ROUND_TRIPS,
    MIN_OOS_WIN_TRIPS,
    PB_NONE_MESSAGE,
    SOFT_WARNING_ROUND_TRIPS,
    SYMBOL_MISMATCH_MESSAGE,
)
from tests.api_helpers import recent_bars
from tests.conftest import ApiHarness

_END = date(2026, 7, 20)
_BARS = 1100
_START = _END - timedelta(days=_BARS - 1)
_PATH = "/api/kelly-inputs/2330/import-backtest"

#: Walk parameters per sample shape. The gate is 20 round trips with at least 5
#: wins and 5 losses; a drifting walk under a breakout strategy lands on either
#: side of that on demand, and the exact counts are asserted below rather than
#: assumed, so a change in the engine shows up as a failing assertion instead of
#: a silently different sample.
_CLEARS_GATE = {"seed": 14, "drift": 0.0004, "vol": 0.03}
_ALMOST_ALL_LOSSES = {"seed": 2, "drift": -0.002, "vol": 0.02}
_ALMOST_ALL_WINS = {"seed": 17, "drift": 0.004, "vol": 0.02}


def _walk(*, seed: int, drift: float, vol: float, bars: int = _BARS) -> list[float]:
    """A deterministic lognormal-ish walk: wins and losses in the same run."""
    rnd = random.Random(seed)
    price = 100.0
    closes = [price]
    for _ in range(bars - 1):
        price = max(price * (1.0 + rnd.gauss(drift, vol)), 1.0)
        closes.append(round(price, 4))
    return closes


def _seed(harness: ApiHarness, shape: dict[str, float], *, bars: int = _BARS) -> None:
    closes = _walk(bars=bars, **shape)  # type: ignore[arg-type]  # shape is scalar kwargs
    harness.price_service.seed("2330", recent_bars(closes, symbol="2330", end=_END))


def _request(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "symbol": "2330",
        "market": "TW",
        "strategy": "breakout",
        "start": _START.isoformat(),
        "end": _END.isoformat(),
        "train_size": 120,
        "test_size": 60,
    }
    body.update(overrides)
    return body


_ATTEMPT_COLUMNS = (
    "symbol",
    "market",
    "strategy_id",
    "request_spec",
    "spec_hash",
    "outcome",
    "reason_code",
    "win_rate",
    "payoff_ratio",
    "kelly_fraction",
    "oos_round_trips",
    "oos_win_trips",
    "oos_loss_trips",
    "oos_excluded_boundary_trips",
    "oos_open_trip_at_end",
    "oos_start_date",
    "oos_end_date",
    "oos_observations",
    "f_star_ci_low",
    "f_star_ci_high",
)


def _attempts(harness: ApiHarness) -> list[dict[str, Any]]:
    """Every logged attempt, oldest first, read straight out of the table."""
    with closing(sqlite3.connect(harness.kelly_attempts.db_path)) as conn:
        rows = conn.execute(
            f"SELECT {', '.join(_ATTEMPT_COLUMNS)} FROM kelly_import_attempts ORDER BY id"
        ).fetchall()
    return [dict(zip(_ATTEMPT_COLUMNS, row, strict=True)) for row in rows]


def _import(harness: ApiHarness, **overrides: Any) -> Any:
    return harness.client.post(_PATH, json=_request(**overrides))


# --------------------------------------------------------------------------
# The cleared path
# --------------------------------------------------------------------------


def test_an_import_stores_the_pair_the_server_computed(api_harness: ApiHarness) -> None:
    _seed(api_harness, _CLEARS_GATE)

    response = _import(api_harness)

    assert response.status_code == 200, response.text
    item = response.json()["item"]
    assert item["source"] == "backtest"
    assert item["symbol"] == "2330"
    # The effective pair and the imported pair are the same at write time.
    assert item["win_rate"] == item["backtest_win_rate"]
    assert item["payoff_ratio"] == item["backtest_payoff_ratio"]
    assert 0.0 < item["win_rate"] < 1.0
    assert item["payoff_ratio"] > 0.0
    # p is the share of round trips that made money, by construction.
    assert item["win_rate"] == pytest.approx(
        item["oos_win_trips"] / item["oos_round_trips"]
    )


def test_the_sample_that_cleared_the_gate_is_the_one_that_was_stored(
    api_harness: ApiHarness,
) -> None:
    """The counts are pinned, so a changed sample shape cannot pass unnoticed."""
    _seed(api_harness, _CLEARS_GATE)

    item = _import(api_harness).json()["item"]

    assert (item["oos_round_trips"], item["oos_win_trips"], item["oos_loss_trips"]) == (
        27,
        15,
        12,
    )
    assert item["oos_round_trips"] >= MIN_OOS_ROUND_TRIPS
    assert item["oos_win_trips"] >= MIN_OOS_WIN_TRIPS
    assert item["oos_loss_trips"] >= MIN_OOS_LOSS_TRIPS


def test_the_row_carries_every_provenance_column_the_adr_lists(
    api_harness: ApiHarness,
) -> None:
    """D-2: with no ``backtest_id`` to quote, the columns are the whole trail."""
    _seed(api_harness, _CLEARS_GATE)

    item = _import(api_harness).json()["item"]

    required = (
        "strategy_id",
        "window_start",
        "window_end",
        "oos_start_date",
        "oos_end_date",
        "produced_at",
        "rates_verified",
        "dividend_reason_code",
        "adjust_dividends",
        "oos_round_trips",
        "oos_win_trips",
        "oos_loss_trips",
        "oos_excluded_boundary_trips",
        "oos_open_trip_at_end",
        "oos_observations",
        "p_ci_low",
        "p_ci_high",
        "f_star",
        "f_star_ci_low",
        "f_star_ci_high",
        "bootstrap_seed",
        "bootstrap_draws",
        "bootstrap_degenerate_no_loss_draws",
        "bootstrap_degenerate_no_win_draws",
        "spec_hash",
        "low_sample_warning",
        "k_observed_at_write",
    )
    missing = [name for name in required if item[name] is None]
    assert missing == []
    assert item["strategy_id"] == "breakout"
    assert item["adjust_dividends"] is True
    # The harness has never synced 除權息 data, and the row says so rather than
    # implying an adjustment that did not happen.
    assert item["dividend_reason_code"] == "never_synced"
    assert item["rates_verified"] is False


def test_the_window_columns_come_from_the_fold_geometry(api_harness: ApiHarness) -> None:
    """約束 23: the segment stored is the segment measured, by bar index."""
    _seed(api_harness, _CLEARS_GATE)

    item = _import(api_harness).json()["item"]
    folds = api_harness.client.post("/api/backtest", json=_request()).json()["folds"]

    # 1100 bars, train 120 / test 60: the out-of-sample stretch runs from the
    # first fold's test start to the last fold's test stop, and that span is
    # what ``oos_observations`` counts (bars, not round trips).
    assert item["oos_observations"] == folds[-1]["test_stop"] - folds[0]["test_start"]
    assert item["oos_observations"] > item["oos_round_trips"]
    assert item["window_start"] <= item["oos_start_date"] < item["oos_end_date"]
    assert item["oos_end_date"] <= item["window_end"]


def test_the_pair_is_the_round_trip_estimate_not_the_fill_layer_one(
    api_harness: ApiHarness,
) -> None:
    """約束 25: the stored pair is the round-trip estimate, never a fill count.

    The engine rebalances daily, so a single holding period emits a tail of tiny
    closing fills; the fill count still dwarfs the round-trip count. C8 note:
    the report's ``win_rate`` used to be the fill-layer rate and this test
    asserted the two numbers disagreed. Since the C8 fix the report's
    ``win_rate`` IS the round-trip rate over the same out-of-sample window, so
    the stored pair now agrees with it exactly -- one source, one number. What
    must never come back is a rate built from ``num_closing_trades``-style fill
    counting.
    """
    _seed(api_harness, _CLEARS_GATE)

    item = _import(api_harness).json()["item"]
    metrics = api_harness.client.post("/api/backtest", json=_request()).json()["report"][
        "out_of_sample"
    ]["strategy"]

    assert metrics["num_closing_trades"] > item["oos_round_trips"]
    assert metrics["win_rate"] == metrics["round_trip_win_rate"] == item["win_rate"]
    # The rate cannot be the fill-layer one: rating a sample this much larger
    # than the round-trip sample would not reproduce the round-trip fraction.
    assert item["win_rate"] == item["oos_win_trips"] / item["oos_round_trips"]


def test_an_imported_row_ages_from_its_out_of_sample_end(api_harness: ApiHarness) -> None:
    """D-4: the anchor is the segment end, never the run time.

    The segment ends where the last fold's test window does, which is before the
    last bar loaded -- so anchoring on the run (or on the requested ``end``)
    would report this row as younger than the evidence in it actually is.
    """
    _seed(api_harness, _CLEARS_GATE)

    body = _import(api_harness).json()

    oos_end = date.fromisoformat(body["item"]["oos_end_date"])
    assert body["anchored_at"].startswith(body["item"]["oos_end_date"])
    assert body["age_days"] == (date.today() - oos_end).days
    assert oos_end < _END


def test_a_sample_below_the_soft_band_carries_the_warning_flag(
    api_harness: ApiHarness,
) -> None:
    """D-3: 20 <= n < 50 is accepted **and** flagged, never quietly accepted."""
    _seed(api_harness, _CLEARS_GATE)

    item = _import(api_harness).json()["item"]

    assert item["oos_round_trips"] < SOFT_WARNING_ROUND_TRIPS
    assert item["low_sample_warning"] is True


def test_the_stored_fraction_is_the_one_the_injected_formula_produces(
    api_harness: ApiHarness,
) -> None:
    """約束 34: ``f_star`` is a record of the estimate, not a second policy.

    Recomputing it from the stored pair with ``app.advice.limits.kelly_fraction``
    -- exactly what cap 5 will do -- reproduces it, which is what makes the
    stored value safe to show and pointless to read back into the cap.
    """
    _seed(api_harness, _CLEARS_GATE)

    item = _import(api_harness).json()["item"]

    assert item["f_star"] == pytest.approx(
        kelly_fraction(item["win_rate"], item["payoff_ratio"])
    )
    assert item["f_star_ci_low"] <= item["f_star"] <= item["f_star_ci_high"]
    assert item["p_ci_low"] <= item["win_rate"] <= item["p_ci_high"]


def test_the_bootstrap_is_seeded_from_the_spec_hash_and_repeats(
    api_harness: ApiHarness,
) -> None:
    """約束 27: same spec, same bars -> the same interval, and it says so."""
    _seed(api_harness, _CLEARS_GATE)

    first = _import(api_harness).json()["item"]
    second = _import(api_harness).json()["item"]

    assert first["bootstrap_seed"] == int(first["spec_hash"][:8], 16)
    assert first["bootstrap_draws"] == kelly_api.BOOTSTRAP_DRAWS
    assert (first["f_star_ci_low"], first["f_star_ci_high"]) == (
        second["f_star_ci_low"],
        second["f_star_ci_high"],
    )


def test_an_import_replaces_a_hand_entered_row_with_the_measured_one(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, _CLEARS_GATE)
    api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 0.9, "payoff_ratio": 9.0}
    )

    item = _import(api_harness).json()["item"]

    assert item["source"] == "backtest"
    assert item["win_rate"] != 0.9
    assert item["strategy_id"] == "breakout"


# --------------------------------------------------------------------------
# The attempt log (約束 29 / 30 / 35)
# --------------------------------------------------------------------------


def test_a_cleared_import_logs_one_attempt_carrying_the_same_numbers(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, _CLEARS_GATE)

    item = _import(api_harness).json()["item"]

    (attempt,) = _attempts(api_harness)
    assert attempt["outcome"] == "ok"
    assert attempt["reason_code"] is None
    assert attempt["symbol"] == "2330"
    assert attempt["strategy_id"] == "breakout"
    assert attempt["win_rate"] == item["win_rate"]
    assert attempt["payoff_ratio"] == item["payoff_ratio"]
    assert attempt["kelly_fraction"] == item["f_star"]
    assert attempt["oos_round_trips"] == item["oos_round_trips"]
    assert attempt["oos_start_date"] == item["oos_start_date"]
    assert attempt["f_star_ci_low"] == item["f_star_ci_low"]
    assert attempt["spec_hash"] == item["spec_hash"]


def test_the_logged_spec_is_canonical_json_of_the_validated_request(
    api_harness: ApiHarness,
) -> None:
    """The spec is stored as it was validated, and holds no credential."""
    _seed(api_harness, _CLEARS_GATE)

    _import(api_harness)

    (attempt,) = _attempts(api_harness)
    spec = json.loads(attempt["request_spec"])
    assert spec["symbol"] == "2330"
    assert spec["strategy"] == "breakout"
    assert spec["start"] == _START.isoformat()
    # Field order cannot drift, or the hash (and the seed) would drift with it.
    assert list(spec) == sorted(spec)
    assert "win_rate" not in spec and "payoff_ratio" not in spec


def test_field_order_in_the_body_does_not_change_the_spec_hash(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, _CLEARS_GATE)
    shuffled = dict(reversed(list(_request().items())))

    first = _import(api_harness).json()["item"]
    second = api_harness.client.post(_PATH, json=shuffled).json()["item"]

    assert first["spec_hash"] == second["spec_hash"]


def test_k_observed_at_write_counts_the_attempt_that_wrote_the_row(
    api_harness: ApiHarness,
) -> None:
    """約束 30: including this one, including the refused ones."""
    _seed(api_harness, _CLEARS_GATE)

    first = _import(api_harness).json()["item"]
    api_harness.client.post(_PATH, json=_request(train_size=130))
    third = _import(api_harness).json()["item"]

    assert first["k_observed_at_write"] == 1
    assert third["k_observed_at_write"] == 3
    assert api_harness.kelly_attempts.k_observed("2330", "TW") == 3
    # Two of the three specs are identical, and the distinct count says so.
    assert api_harness.kelly_attempts.k_distinct_specs("2330", "TW") == 2


def test_clearing_the_input_after_an_import_leaves_the_log_intact(
    api_harness: ApiHarness,
) -> None:
    """約束 26 (7) / 35: a delete must not lower ``K_observed``."""
    _seed(api_harness, _CLEARS_GATE)
    _import(api_harness)

    assert api_harness.client.delete("/api/kelly-inputs/2330").status_code == 204

    assert api_harness.kelly_attempts.k_observed("2330", "TW") == 1
    assert len(_attempts(api_harness)) == 1
    assert api_harness.client.get("/api/kelly-inputs/2330").status_code == 404


def test_an_import_that_cannot_be_logged_fails_the_whole_request(
    api_harness: ApiHarness, tmp_path: Path
) -> None:
    """約束 29: no silent pass-through when the log is unwritable."""
    _seed(api_harness, _CLEARS_GATE)

    def unwritable(*_args: Any, **_kwargs: Any) -> int:
        raise sqlite3.OperationalError("disk I/O error")

    api_harness.kelly_attempts.append = unwritable  # type: ignore[method-assign]

    response = _import(api_harness)

    assert response.status_code == 500
    assert "嘗試紀錄" in response.json()["detail"]
    assert api_harness.kelly_inputs.get("2330", "TW") is None


# --------------------------------------------------------------------------
# Refusals: every gate, its code, its numbers, and its logged row (D-3)
# --------------------------------------------------------------------------


def _refusal(response: Any) -> dict[str, Any]:
    assert response.status_code == 422, response.text
    detail: dict[str, Any] = response.json()["detail"]
    return detail


def test_too_few_round_trips_is_refused_with_the_count_it_measured(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, _CLEARS_GATE, bars=400)

    detail = _refusal(_import(api_harness))

    assert detail["reason_code"] == "low_round_trips"
    assert f"門檻 {MIN_OOS_ROUND_TRIPS} 筆" in detail["message"]
    assert api_harness.kelly_inputs.get("2330", "TW") is None
    (attempt,) = _attempts(api_harness)
    assert (attempt["outcome"], attempt["reason_code"]) == ("rejected", "low_round_trips")
    assert attempt["oos_round_trips"] < MIN_OOS_ROUND_TRIPS
    # A refused attempt records what it measured but no interval: none was run.
    assert attempt["f_star_ci_low"] is None


def test_too_few_winning_round_trips_is_refused(api_harness: ApiHarness) -> None:
    _seed(api_harness, _ALMOST_ALL_LOSSES)

    detail = _refusal(_import(api_harness))

    assert detail["reason_code"] == "low_win_trips"
    assert f"門檻 {MIN_OOS_WIN_TRIPS} 筆" in detail["message"]
    (attempt,) = _attempts(api_harness)
    assert attempt["oos_round_trips"] >= MIN_OOS_ROUND_TRIPS
    assert attempt["oos_win_trips"] < MIN_OOS_WIN_TRIPS
    assert api_harness.kelly_inputs.get("2330", "TW") is None


def test_too_few_losing_round_trips_is_refused(api_harness: ApiHarness) -> None:
    _seed(api_harness, _ALMOST_ALL_WINS)

    detail = _refusal(_import(api_harness))

    assert detail["reason_code"] == "low_loss_trips"
    assert f"門檻 {MIN_OOS_LOSS_TRIPS} 筆" in detail["message"]
    (attempt,) = _attempts(api_harness)
    assert attempt["oos_round_trips"] >= MIN_OOS_ROUND_TRIPS
    assert attempt["oos_win_trips"] >= MIN_OOS_WIN_TRIPS
    assert attempt["oos_loss_trips"] < MIN_OOS_LOSS_TRIPS
    assert api_harness.kelly_inputs.get("2330", "TW") is None


def test_a_symbol_mismatch_is_refused_before_any_backtest_runs(
    api_harness: ApiHarness,
) -> None:
    """Filing one symbol's evidence under another's name is refused, not resolved."""
    _seed(api_harness, _CLEARS_GATE)

    detail = _refusal(_import(api_harness, symbol="2317"))

    assert detail["reason_code"] == "symbol_mismatch"
    # 風控 (5-2) 逐字定稿，第二輪. The message names the instrument the user was
    # working on and the one the request carried, not the URL and the body.
    assert detail["message"] == SYMBOL_MISMATCH_MESSAGE.format(
        path_symbol="2330", path_market="TW", body_symbol="2317", body_market="TW"
    )
    assert "2317" in detail["message"] and "2330" in detail["message"]
    assert api_harness.price_service.calls == []
    (attempt,) = _attempts(api_harness)
    # Logged under the key the write was addressed to: that is the instrument
    # whose search history this attempt belongs to.
    assert attempt["symbol"] == "2330"
    assert attempt["oos_round_trips"] is None


def test_a_market_mismatch_is_refused_too(api_harness: ApiHarness) -> None:
    """The same ticker in two markets is two instruments."""
    _seed(api_harness, _CLEARS_GATE)

    response = api_harness.client.post(
        "/api/kelly-inputs/2330/import-backtest?market=US", json=_request()
    )

    assert _refusal(response)["reason_code"] == "symbol_mismatch"


def test_a_run_that_could_not_report_is_refused_with_its_own_status(
    api_harness: ApiHarness,
) -> None:
    """``status != ok`` is the backtest's answer, and it is passed through."""
    _seed(api_harness, _CLEARS_GATE, bars=150)

    detail = _refusal(_import(api_harness))

    assert detail["reason_code"] == "insufficient_data"
    # 風控 (5-1) 逐字定稿，第二輪: the status travels as a bracketed code at the
    # end of the sentence, not as a clause inside it.
    assert detail["message"] == INSUFFICIENT_DATA_MESSAGE.format(status="insufficient_data")
    assert detail["message"].endswith("（狀態代碼：insufficient_data）。")
    (attempt,) = _attempts(api_harness)
    assert (attempt["outcome"], attempt["reason_code"]) == (
        "rejected",
        "insufficient_data",
    )


def test_missing_estimates_are_refused_even_though_the_counts_passed(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``pb_none`` backstop, exercised by forcing the state it guards against.

    Today's gate makes it unreachable -- a missing p needs an empty sample, a
    missing b needs an empty side -- so the only way to prove the store is
    protected from a half-pair is to hand the handler one.
    """
    _seed(api_harness, _CLEARS_GATE)

    def half_a_pair(*args: Any, **kwargs: Any) -> Any:
        attribution = attribute_round_trips(*args, **kwargs)
        stats = attribution.stats
        return type(attribution)(
            window_start=attribution.window_start,
            window_stop=attribution.window_stop,
            episodes=attribution.episodes,
            excluded_boundary_trips=attribution.excluded_boundary_trips,
            open_trip_at_end=attribution.open_trip_at_end,
            stats=type(stats)(
                n=stats.n,
                n_win=stats.n_win,
                n_loss=stats.n_loss,
                round_trip_win_rate=stats.round_trip_win_rate,
                round_trip_payoff_ratio=None,
            ),
        )

    monkeypatch.setattr("app.api.kelly.attribute_round_trips", half_a_pair)

    detail = _refusal(_import(api_harness))

    assert detail["reason_code"] == "pb_none"
    # 風控 (5-3) 逐字定稿，第二輪, and 5-3A: the half that is missing is described,
    # never rendered. A "None" reaching this body is the fault the ruling named.
    assert detail["message"] == PB_NONE_MESSAGE
    assert "None" not in detail["message"] and "null" not in detail["message"]
    assert api_harness.kelly_inputs.get("2330", "TW") is None
    (attempt,) = _attempts(api_harness)
    assert attempt["reason_code"] == "pb_none"


@pytest.mark.parametrize(
    "extra",
    [
        {"win_rate": 0.6},
        {"payoff_ratio": 2.0},
        {"f_star": 0.3},
    ],
)
def test_a_body_carrying_a_number_of_its_own_is_refused(
    api_harness: ApiHarness, extra: dict[str, float]
) -> None:
    """約束 31: p, b and f\\* may only ever be produced here, never supplied.

    Refused by the request model before the handler runs, so no attempt is
    logged: nothing about a search for a favourable window happened here, and
    ``K_observed`` must not be inflated by malformed requests.
    """
    _seed(api_harness, _CLEARS_GATE)

    response = _import(api_harness, **extra)

    assert response.status_code == 422
    assert api_harness.kelly_inputs.get("2330", "TW") is None
    assert _attempts(api_harness) == []


# --------------------------------------------------------------------------
# Structural guards (約束 27 / 31)
# --------------------------------------------------------------------------


def test_a_non_finite_interval_fails_the_import_without_storing_it(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """約束 27: the defensive assertion, exercised by bypassing what it guards.

    Under the 20/5/5 gate a bound reaching an infinity is a should-not-happen,
    so it is injected. The import must fail rather than push an infinity into
    SQLite and into every response that would later read the row -- while still
    logging the attempt, which did happen.
    """
    _seed(api_harness, _CLEARS_GATE)

    def unbounded(*_args: Any, **_kwargs: Any) -> FractionInterval:
        return FractionInterval(
            point=0.2,
            low=-math.inf,
            high=0.5,
            seed=1,
            draws=kelly_api.BOOTSTRAP_DRAWS,
            degenerate_no_loss_draws=0,
            degenerate_no_win_draws=7,
        )

    monkeypatch.setattr("app.api.kelly.bootstrap_fraction_ci", unbounded)

    response = _import(api_harness)

    assert response.status_code == 500
    detail = response.json()["detail"]
    # The offending bounds stay in the log. This branch reaches here *because*
    # they are non-finite, so interpolating them put "-inf" in front of a user
    # (the front end renders ``detail`` verbatim for any non-422); the prose
    # itself is still awaiting a redraft from risk-compliance (風控第三輪 §3).
    assert detail == kelly_api.KELLY_NON_FINITE_INTERVAL_MESSAGE
    for bound in ("inf", "-inf", "nan"):
        assert bound not in detail
    # 落地條件 23 反向斷言: 元件 B is the *refusal* sentence and may not appear on a
    # path that refused nothing. 3-B is this path's approved sentence; wiring it
    # into the response waits on the redraft of the message above (風控第三輪 §3).
    assert kelly_wording.KELLY_REFUSAL_ATTEMPT_LOGGED not in detail
    assert "拒絕" not in detail
    assert api_harness.kelly_inputs.get("2330", "TW") is None
    (attempt,) = _attempts(api_harness)
    # 落地條件 23 口徑: every gate passed and the storage step is what failed, so
    # this row is not a refusal and must not be described as one.
    assert attempt["outcome"] == "ok"  # the gate verdict, not the storage result
    assert attempt["reason_code"] is None
    assert attempt["f_star_ci_low"] is None
    assert attempt["f_star_ci_high"] is None


def test_one_request_runs_exactly_one_backtest(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """約束 31: p and b are same-run by construction, not by inspection.

    Two runs inside one handler could pair a win rate from one price series with
    a payoff ratio from another -- same request, silently different samples. The
    guard is a count, because the property is "one", not "few".
    """
    _seed(api_harness, _CLEARS_GATE)
    runs: list[int] = []

    def counted(*args: Any, **kwargs: Any) -> Any:
        runs.append(1)
        return run_backtest(*args, **kwargs)

    monkeypatch.setattr("app.api.backtest.run_backtest", counted)

    assert _import(api_harness).status_code == 200

    assert sum(runs) == 1


# --------------------------------------------------------------------------
# (d-1) 元件 A/元件 B on the refusal body (落地條件 8/13, 3-A)
# --------------------------------------------------------------------------

#: The three sample-size codes 元件 A is bound to, and the three it is banned
#: from. Six scenarios, which is what 落地條件 8 asks for by name -- three that
#: trigger the frame and three that must not.
_SAMPLE_SIZE_CODES = ("low_round_trips", "low_win_trips", "low_loss_trips")
_OTHER_REFUSAL_CODES = ("symbol_mismatch", "insufficient_data", "pb_none")


def _refuse_with(
    code: str, api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Drive one of the six gates and hand back the 422 body it produced."""
    if code == "low_round_trips":
        _seed(api_harness, _CLEARS_GATE, bars=400)
        return _refusal(_import(api_harness))
    if code == "low_win_trips":
        _seed(api_harness, _ALMOST_ALL_LOSSES)
        return _refusal(_import(api_harness))
    if code == "low_loss_trips":
        _seed(api_harness, _ALMOST_ALL_WINS)
        return _refusal(_import(api_harness))
    if code == "symbol_mismatch":
        _seed(api_harness, _CLEARS_GATE)
        return _refusal(_import(api_harness, symbol="2317"))
    if code == "insufficient_data":
        _seed(api_harness, _CLEARS_GATE, bars=150)
        return _refusal(_import(api_harness))
    assert code == "pb_none"
    _seed(api_harness, _CLEARS_GATE)

    def half_a_pair(*args: Any, **kwargs: Any) -> Any:
        attribution = attribute_round_trips(*args, **kwargs)
        stats = attribution.stats
        return type(attribution)(
            window_start=attribution.window_start,
            window_stop=attribution.window_stop,
            episodes=attribution.episodes,
            excluded_boundary_trips=attribution.excluded_boundary_trips,
            open_trip_at_end=attribution.open_trip_at_end,
            stats=type(stats)(
                n=stats.n,
                n_win=stats.n_win,
                n_loss=stats.n_loss,
                round_trip_win_rate=stats.round_trip_win_rate,
                round_trip_payoff_ratio=None,
            ),
        )

    monkeypatch.setattr("app.api.kelly.attribute_round_trips", half_a_pair)
    return _refusal(_import(api_harness))


@pytest.mark.parametrize("code", _SAMPLE_SIZE_CODES)
def test_a_sample_size_refusal_carries_the_frame_verbatim(
    code: str, api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(d-1 元件 A) on the three codes it was approved for (落地條件 13)."""
    detail = _refuse_with(code, api_harness, monkeypatch)

    assert detail["reason_code"] == code
    assert detail["frame"] == kelly_wording.KELLY_REFUSAL_FRAME
    # The frame introduces the gate's own message: 「…如下：」 then the numbers.
    assert detail["frame"].endswith("：")


@pytest.mark.parametrize("code", _OTHER_REFUSAL_CODES)
def test_the_other_three_codes_get_no_reassurance_they_do_not_deserve(
    code: str, api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """落地條件 13:「其餘三碼不得顯示」.

    「這是常見情況」 is true of a window that produced too few round trips and
    false of a symbol mismatch, which is a front-end defect. Attaching comfort
    to a fault is the failure the NO_SECTOR_DETAILS ruling named.
    """
    detail = _refuse_with(code, api_harness, monkeypatch)

    assert detail["reason_code"] == code
    assert detail["frame"] is None
    assert kelly_wording.KELLY_REFUSAL_FRAME not in json.dumps(detail, ensure_ascii=False)


@pytest.mark.parametrize("code", (*_SAMPLE_SIZE_CODES, *_OTHER_REFUSAL_CODES))
def test_every_refusal_says_the_attempt_was_counted(
    code: str, api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(d-1 元件 B) on all six, with 3-A's (b) beside it and the counts to check.

    The two counts are the ones that already include this attempt: 元件 B says
    the attempt was counted, and a body quoting a K taken before the append
    would contradict itself.
    """
    detail = _refuse_with(code, api_harness, monkeypatch)

    assert detail["attempt_logged"] == kelly_wording.KELLY_REFUSAL_ATTEMPT_LOGGED
    # 3-A: (b) 同屏, not a link -- k_distinct_specs was pushed up by this attempt
    # too, and a link alone would suggest only K_observed moved.
    assert detail["selection_bias"] == kelly_wording.KELLY_SELECTION_BIAS_SINGLE
    assert (detail["k_observed"], detail["k_distinct_specs"]) == (1, 1)
    assert len(_attempts(api_harness)) == detail["k_observed"]


def test_a_second_refusal_switches_the_selection_bias_to_the_full_sentence(
    api_harness: ApiHarness,
) -> None:
    """落地條件 5 on the refusal body: K>=2 takes (b 完整), with both counts."""
    _seed(api_harness, _CLEARS_GATE, bars=400)
    _import(api_harness)

    detail = _refusal(_import(api_harness, train_size=121))

    assert detail["k_observed"] == 2
    # Two different specs, so the distinct count moved with it.
    assert detail["k_distinct_specs"] == 2
    assert detail["selection_bias"] == kelly_wording.KELLY_SELECTION_BIAS_FULL.format(
        k_observed=2, k_distinct_specs=2
    )


def test_the_non_finite_path_carries_no_refusal_sentence(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """落地條件 23: 元件 B's literal may not appear on the 500 path.

    That row's ``outcome`` is ``"ok"`` with no reason code -- the gates passed
    and the storage step failed -- so calling it a refusal would misstate the
    log. It has its own sentence (3-B), which this endpoint does not attach
    here; the 500 body is 落地條件 25's constant and nothing else.
    """
    _seed(api_harness, _CLEARS_GATE)
    monkeypatch.setattr(
        "app.api.kelly.bootstrap_fraction_ci",
        lambda *args, **kwargs: FractionInterval(
            point=0.1,
            low=-math.inf,
            high=0.2,
            seed=1,
            draws=1,
            degenerate_no_loss_draws=0,
            degenerate_no_win_draws=1,
        ),
    )

    response = _import(api_harness)

    assert response.status_code == 500
    body = response.text
    assert kelly_wording.KELLY_REFUSAL_ATTEMPT_LOGGED not in body
    assert kelly_wording.KELLY_REFUSAL_FRAME not in body
    assert "拒絕" not in response.json()["detail"]


@pytest.mark.parametrize("code", (*_SAMPLE_SIZE_CODES, *_OTHER_REFUSAL_CODES))
def test_no_refusal_claims_the_attempt_record_is_missing(
    code: str, api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """條件 101 (E-13): 條件 96's sentence may not share a screen with 元件 B.

    元件 B says this attempt was counted, which asserts K >= 1; the other says
    the record is absent. They cannot both be true, and on this path only the
    first one is: the attempt is appended before the counts are read.
    """
    detail = _refuse_with(code, api_harness, monkeypatch)

    assert kelly_wording.KELLY_SELECTION_BIAS_UNLOGGED not in json.dumps(
        detail, ensure_ascii=False
    )
    assert detail["k_observed"] >= 1
    assert detail["attempt_logged"] == kelly_wording.KELLY_REFUSAL_ATTEMPT_LOGGED


def test_the_counts_are_read_after_the_append_and_that_order_is_frozen() -> None:
    """條件 101: 「凍結 append 後才查計數」, asserted on the source order.

    A count cached before the append would be one lower than the row the log
    holds, and a K of zero rendered that way would put 條件 96's sentence on a
    screen that also says the attempt was counted -- the contradiction E-13 is
    about. Reading the counts *after* ``_append_attempt`` is what makes 元件 B's
    claim true of the numbers printed beside it.
    """
    source = (Path(__file__).resolve().parent.parent / "app" / "api" / "kelly.py").read_text(
        encoding="utf-8"
    )
    refuse = source.split("def refuse(", 1)[1].split("\n    matched =", 1)[0]

    assert refuse.index("_append_attempt(") < refuse.index("attempts.k_observed(")
    assert refuse.index("attempts.k_observed(") < refuse.index("KellyImportRefusal(")


def test_the_non_finite_path_makes_no_claim_about_the_attempt_record(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """條件 101 on the 500 path: it appends too, so K >= 1 there as well."""
    _seed(api_harness, _CLEARS_GATE)
    monkeypatch.setattr(
        "app.api.kelly.bootstrap_fraction_ci",
        lambda *args, **kwargs: FractionInterval(
            point=0.1,
            low=-math.inf,
            high=0.2,
            seed=1,
            draws=1,
            degenerate_no_loss_draws=0,
            degenerate_no_win_draws=1,
        ),
    )

    response = _import(api_harness)

    assert response.status_code == 500
    assert kelly_wording.KELLY_SELECTION_BIAS_UNLOGGED not in response.text
    assert len(_attempts(api_harness)) == 1


@pytest.mark.parametrize("code", (*_SAMPLE_SIZE_CODES, *_OTHER_REFUSAL_CODES))
def test_a_refused_import_claims_no_imported_source(
    code: str, api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """條件 105 (禁樂觀狀態): nothing was imported, so nothing may say it was.

    「來源：回測帶入」 is (fr6-backtest)'s label and the opening of the overridden
    one; either on a refusal would report a state the store does not hold -- the
    endpoint wrote no row at all.
    """
    detail = _refuse_with(code, api_harness, monkeypatch)

    assert "來源：回測帶入" not in json.dumps(detail, ensure_ascii=False)
    assert api_harness.kelly_inputs.get("2330", "TW") is None


def test_the_non_finite_path_claims_no_imported_source(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """條件 105 on the 500 path, where the row is likewise not written."""
    _seed(api_harness, _CLEARS_GATE)
    monkeypatch.setattr(
        "app.api.kelly.bootstrap_fraction_ci",
        lambda *args, **kwargs: FractionInterval(
            point=0.1,
            low=-math.inf,
            high=0.2,
            seed=1,
            draws=1,
            degenerate_no_loss_draws=0,
            degenerate_no_win_draws=1,
        ),
    )

    response = _import(api_harness)

    assert response.status_code == 500
    assert "來源：回測帶入" not in response.text
    assert api_harness.kelly_inputs.get("2330", "TW") is None


def test_a_cleared_import_is_what_makes_the_imported_source_true(
    api_harness: ApiHarness,
) -> None:
    """條件 105, positive side: after a successful import the claim is true.

    The disclosure endpoint is what a screen reads, so the transition is
    asserted where the user would see it: nothing before, the source stated
    after.
    """
    _seed(api_harness, _CLEARS_GATE)
    before = api_harness.client.get("/api/kelly-inputs/2330/disclosures").json()
    assert "來源：回測帶入" not in json.dumps(before, ensure_ascii=False)

    assert _import(api_harness).status_code == 200

    after = api_harness.client.get("/api/kelly-inputs/2330/disclosures").json()
    assert after["disclosures"]["source_label"] == kelly_wording.KELLY_SOURCE_BACKTEST_LABEL


def test_only_the_kelly_surface_mentions_the_stored_fraction() -> None:
    """約束 34: nothing outside the Kelly path can read ``f_star`` back.

    A source scan rather than prose: the moment the risk layer or the advice
    engine names this column, the stored audit number has become an input to a
    cap that is supposed to recompute it from the effective pair.
    """
    app_root = Path(__file__).resolve().parent.parent / "app"
    allowed = {
        app_root / "kelly" / "models.py",
        app_root / "kelly" / "store.py",
        app_root / "kelly" / "attempts.py",
        app_root / "api" / "kelly.py",
        # Text and nothing else: (a-1) names the two interval bounds as
        # ``{f_star_ci_*_pct}`` placeholders, and those names are inside a
        # sentence risk-compliance approved character for character, so they
        # cannot be spelled differently. The module imports nothing at all
        # (``tests/test_kelly_wording.py``), so naming the column here cannot
        # turn into reading it.
        app_root / "api" / "kelly_wording.py",
    }

    offenders = sorted(
        str(path.relative_to(app_root))
        for path in app_root.rglob("*.py")
        if path not in allowed and "f_star" in path.read_text(encoding="utf-8")
    )

    assert offenders == []


# --------------------------------------------------------------------------
# GET /api/kelly-inputs (D-8)
# --------------------------------------------------------------------------


def test_the_list_endpoint_is_empty_before_anything_is_entered(
    api_harness: ApiHarness,
) -> None:
    body = api_harness.client.get("/api/kelly-inputs").json()

    assert body["items"] == []
    assert body["as_of"]


def test_the_list_endpoint_returns_every_input_with_its_freshness(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, _CLEARS_GATE)
    _import(api_harness)
    api_harness.client.put(
        "/api/kelly-inputs/AAPL?market=US", json={"win_rate": 0.55, "payoff_ratio": 1.8}
    )

    items = api_harness.client.get("/api/kelly-inputs").json()["items"]

    assert [entry["item"]["symbol"] for entry in items] == ["2330", "AAPL"]
    sources = {entry["item"]["symbol"]: entry["item"]["source"] for entry in items}
    assert sources == {"2330": "backtest", "AAPL": "manual"}
    for entry in items:
        assert entry["freshness"] in {"fresh", "ageing", "expired"}
