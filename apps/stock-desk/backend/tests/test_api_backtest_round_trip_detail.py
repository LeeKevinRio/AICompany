"""``POST /api/backtest``: F-11's ``round_trip_detail`` on the wire.

What the API layer adds to the report-layer guarantees: exactly one new
response field, ``None`` exactly where ``report`` is (F11-A-16); its top-level
keys and every nested key set pinned so a rename on either side of the wire
turns red (F11-A-25, A-36, A-38); the run's last-bar date equal to the page's
``data.last_bar_date`` on all four 除權息 branches (F11-A-37); the copy riding
on ``labels`` only, never on ``notes`` or ``data_warning`` (F11-A-45); and the
Kelly import surface carrying none of it (F11-A-22, A-28).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.api.backtest import BacktestRequest, BacktestResponse, execute_backtest
from app.api.backtest_wording import F11_APPROVED_WORDING
from app.backtest.episodes import attribute_round_trips, oos_window
from app.backtest.strategies import STRATEGY_IDS
from app.dividends.models import DividendEvent
from tests.api_helpers import oscillating_closes, recent_bars
from tests.conftest import ApiHarness

_END = date(2026, 7, 20)
_START = _END - timedelta(days=600)
_AS_OF = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
#: train 200 / test 60: 400 bars leave a 20-bar tail, 380 bars leave none.
_BARS_WITH_TAIL = 400
_BARS_WITHOUT_TAIL = 380

#: ``BacktestResponse`` before F-11, in declaration order.
_PRE_F11_RESPONSE_FIELDS = (
    "symbol",
    "market",
    "strategy",
    "status",
    "reason",
    "report",
    "curves",
    "folds",
    "cost_model",
    "rates_verified",
    "dividend_adjustment",
    "notes",
    "data_warning",
    "data",
    "as_of",
    "metric_labels",
)

_DETAIL_KEYS = {"in_sample", "out_of_sample", "coverage", "labels"}
_SEGMENT_KEYS = {
    "num_round_trips",
    "num_winning_round_trips",
    "num_losing_round_trips",
    "round_trips",
    "lowest_return_round_trips",
    "mean_winning_return",
    "mean_losing_return",
    "longest_losing_streak",
    "excluded_boundary_trips",
    "open_trip_at_end",
    "in_market_ratio",
    "buy_and_hold_in_market_ratio",
    "warmup_flat_intervals",
    "below_display_minimum",
    "empty_state",
}
_ROW_KEYS = {"entry_date", "exit_date", "holding_bars", "return_on_entry_equity", "realized_pnl"}
_STREAK_KEYS = {"length", "start_date", "end_date"}
_COVERAGE_KEYS = {"last_bar_date", "unattributed_tail_bars", "unattributed_tail_start_date"}
_SEGMENT_LABEL_KEYS = {
    "detail_title",
    "lowest_returns_heading",
    "longest_losing_streak_value",
    "mean_winning_return_suffix",
    "mean_losing_return_suffix",
    "payoff_ratio_pointer",
    "in_market_ratio_definition",
    "expand_control",
    "collapse_control",
    "expand_control_aria",
    "collapse_control_aria",
}
_LABEL_KEYS = {
    "entry_date",
    "exit_date",
    "holding_bars",
    "return_on_entry_equity",
    "realized_pnl",
    "columns_note",
    "longest_losing_streak",
    "longest_losing_streak_definition",
    "mean_winning_return",
    "mean_losing_return",
    "payoff_ratio",
    "payoff_ratio_definition",
    "profit_factor_definition",
    "in_market_ratio",
    "sample_below_minimum",
    "sample_count_reminder",
    "excluded_heading",
    "excluded_closed_trips",
    "excluded_open_trips",
    "excluded_note",
    "cost_and_settings_note",
    "detail_opening",
    "empty_state_no_position",
    "empty_state_excluded_only",
    "unattributed_tail",
    "in_sample",
    "out_of_sample",
}


def _seed(harness: ApiHarness, count: int = _BARS_WITH_TAIL, symbol: str = "2330") -> None:
    harness.price_service.seed(
        symbol, recent_bars(oscillating_closes(count), symbol=symbol, end=_END)
    )


def _request(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "symbol": "2330",
        "market": "TW",
        "strategy": "ma_cross",
        "start": _START.isoformat(),
        "end": _END.isoformat(),
        "train_size": 200,
        "test_size": 60,
    }
    body.update(overrides)
    return body


def _post(harness: ApiHarness, **overrides: Any) -> dict[str, Any]:
    response = harness.client.post("/api/backtest", json=_request(**overrides))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --------------------------------------------------------------------------
# Shape (F11-A-16, A-21, A-25, A-36, A-38)
# --------------------------------------------------------------------------


def test_the_response_gains_exactly_one_field() -> None:
    fields = tuple(BacktestResponse.model_fields)
    assert set(fields) - set(_PRE_F11_RESPONSE_FIELDS) == {"round_trip_detail"}
    assert tuple(name for name in fields if name != "round_trip_detail") == (
        _PRE_F11_RESPONSE_FIELDS
    )


def test_no_detail_where_no_report(api_harness: ApiHarness) -> None:
    _seed(api_harness, count=100)
    body = _post(api_harness)
    assert body["status"] == "insufficient_data"
    assert body["report"] is None and body["round_trip_detail"] is None
    _seed(api_harness)
    refused = _post(api_harness, train_size=30, test_size=30)  # below the warm-up
    assert refused["report"] is None and refused["round_trip_detail"] is None


def test_every_key_on_the_wire_is_pinned(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    detail = _post(api_harness)["round_trip_detail"]
    assert set(detail) == _DETAIL_KEYS
    assert set(detail["coverage"]) == _COVERAGE_KEYS
    assert set(detail["labels"]) == _LABEL_KEYS
    for segment in ("in_sample", "out_of_sample"):
        assert set(detail[segment]) == _SEGMENT_KEYS
        assert set(detail["labels"][segment]) == _SEGMENT_LABEL_KEYS
        for row in (*detail[segment]["round_trips"], *detail[segment]["lowest_return_round_trips"]):
            assert set(row) == _ROW_KEYS
        streak = detail[segment]["longest_losing_streak"]
        assert streak is None or set(streak) == _STREAK_KEYS
    assert any(detail[segment]["round_trips"] for segment in ("in_sample", "out_of_sample"))


def test_the_metric_labels_and_report_are_untouched(api_harness: ApiHarness) -> None:
    """F11-A-31 / A-38: F-11 copy lives in ``round_trip_detail.labels`` only."""
    _seed(api_harness)
    body = _post(api_harness)
    assert set(body["metric_labels"]) == {"win_rate", "round_trips"}
    assert set(body["report"]) == {"in_sample", "out_of_sample"}
    for text in F11_APPROVED_WORDING.values():
        if "{" in text or len(text) < 4:
            continue
        assert text not in body["metric_labels"].values()


# --------------------------------------------------------------------------
# Same run, same segments, same counts (F11-A-18, A-20(f), A-42, AC-11)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bars", [_BARS_WITH_TAIL, _BARS_WITHOUT_TAIL])
@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
def test_the_detail_counts_the_table_s_round_trips(
    api_harness: ApiHarness, strategy_id: str, bars: int
) -> None:
    _seed(api_harness, count=bars)
    body = _post(api_harness, strategy=strategy_id)
    detail = body["round_trip_detail"]
    for segment in ("in_sample", "out_of_sample"):
        part = detail[segment]
        metrics = body["report"][segment]["strategy"]
        assert part["num_round_trips"] == metrics["num_round_trips"] == len(part["round_trips"])
        # F11-W-25: plain non-negative integers on every run.
        for key in ("excluded_boundary_trips", "open_trip_at_end"):
            assert type(part[key]) is int and part[key] >= 0
        win, loss = part["mean_winning_return"], part["mean_losing_return"]
        if win is None or loss is None:
            assert metrics["round_trip_payoff_ratio"] is None
        else:
            assert win / -loss == metrics["round_trip_payoff_ratio"]
        assert part["below_display_minimum"] == (part["num_round_trips"] < 30)
        if metrics["observations"] >= 2:
            assert part["buy_and_hold_in_market_ratio"] == 1.0
        # The Buy & Hold column has no round trip attribution at all.
        assert body["report"][segment]["buy_and_hold"]["num_round_trips"] is None


def test_the_out_of_sample_list_is_the_set_the_kelly_import_reads(api_harness: ApiHarness) -> None:
    """AC-11: one attribution, so the import cannot be reading another sample."""
    _seed(api_harness)
    run = execute_backtest(
        BacktestRequest.model_validate(_request(strategy="breakout")),
        resolver={"TW": api_harness.price_service},
        settings_store=api_harness.settings,
        dividend_store=api_harness.dividends,
    )
    assert run.result is not None and run.response.round_trip_detail is not None
    start, stop = oos_window(run.folds)
    attribution = attribute_round_trips(run.result, start=start, stop=stop)
    detail = run.response.round_trip_detail
    assert [(row.entry_date, row.exit_date) for row in detail.out_of_sample.round_trips] == [
        (run.result.dates[e.entry_idx], run.result.dates[e.exit_idx]) for e in attribution.episodes
    ]
    assert detail.out_of_sample.excluded_boundary_trips == attribution.excluded_boundary_trips
    assert detail.out_of_sample.open_trip_at_end == attribution.open_trip_at_end
    in_rows = {(row.entry_date, row.exit_date) for row in detail.in_sample.round_trips}
    out_rows = {(row.entry_date, row.exit_date) for row in detail.out_of_sample.round_trips}
    assert in_rows.isdisjoint(out_rows)


# --------------------------------------------------------------------------
# Tail and anchor date (F11-A-36, A-37, A-40(g), A-45)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("bars", "tail"), [(_BARS_WITH_TAIL, 20), (_BARS_WITHOUT_TAIL, 0)])
def test_the_tail_geometry_matches_the_curves_and_the_report(
    api_harness: ApiHarness, bars: int, tail: int
) -> None:
    _seed(api_harness, count=bars)
    body = _post(api_harness)
    coverage = body["round_trip_detail"]["coverage"]
    labels = body["round_trip_detail"]["labels"]
    oos_end = body["report"]["out_of_sample"]["strategy"]["end_date"]
    assert coverage["unattributed_tail_bars"] == tail
    assert body["curves"]["out_of_sample"]["dates"][-1] == oos_end
    assert body["folds"][0]["train_start"] == 0
    assert body["folds"][0]["test_start"] == body["folds"][0]["train_stop"]
    if tail:
        start = coverage["unattributed_tail_start_date"]
        assert start is not None and start > oos_end
        assert labels["unattributed_tail"] == F11_APPROVED_WORDING["L-18a"].format(
            tail_bars=tail, tail_start_date=start, tail_end_date=coverage["last_bar_date"]
        )
    else:
        assert coverage["unattributed_tail_start_date"] is None
        assert coverage["last_bar_date"] == oos_end
        assert labels["unattributed_tail"] == F11_APPROVED_WORDING["L-18b"]
    assert labels["excluded_open_trips"] == F11_APPROVED_WORDING["L-11b"].format(
        last_bar_date=coverage["last_bar_date"]
    )
    # A-45: the tail sentence is not a note and not the data warning.
    for sentence in (F11_APPROVED_WORDING["L-18b"], labels["unattributed_tail"]):
        assert sentence not in body["notes"]
        assert body["data_warning"] != sentence


def _seed_dividend(harness: ApiHarness, symbol: str) -> None:
    first = _END - timedelta(days=_BARS_WITH_TAIL - 1)
    harness.dividends.upsert(
        [
            DividendEvent(
                symbol=symbol,
                market="TW",
                ex_date=first + timedelta(days=100),
                previous_close=Decimal("105.00"),
                reference_price=Decimal("101.00"),
                cash_dividend=Decimal("4.00"),
                source="test",
                as_of=_AS_OF,
            )
        ]
    )


@pytest.mark.parametrize("branch", ["disabled", "never_synced", "no_events", "adjusted"])
def test_the_anchor_date_is_the_page_s_data_date_on_every_dividend_branch(
    api_harness: ApiHarness, branch: str
) -> None:
    """F11-A-37: if this turns red, go back to tech-architect -- do not edit the test."""
    _seed(api_harness)
    if branch == "no_events":
        _seed_dividend(api_harness, "2317")
    elif branch == "adjusted":
        _seed_dividend(api_harness, "2330")
    body = _post(api_harness, adjust_dividends=branch != "disabled")
    assert body["dividend_adjustment"]["reason_code"] == branch
    coverage = body["round_trip_detail"]["coverage"]
    assert coverage["last_bar_date"] == body["data"]["last_bar_date"]
    run = execute_backtest(
        BacktestRequest.model_validate(_request(adjust_dividends=branch != "disabled")),
        resolver={"TW": api_harness.price_service},
        settings_store=api_harness.settings,
        dividend_store=api_harness.dividends,
    )
    assert run.result is not None
    assert coverage["last_bar_date"] == run.result.dates[-1]


# --------------------------------------------------------------------------
# The Kelly import shares the pipeline and reads none of it (F11-A-22, A-28)
# --------------------------------------------------------------------------


def test_the_kelly_import_surface_carries_no_round_trip_detail(api_harness: ApiHarness) -> None:
    _seed(api_harness)
    response = api_harness.client.post(
        "/api/kelly-inputs/2330/import-backtest", json=_request(strategy="breakout")
    )
    assert response.status_code in (200, 422)
    text = response.text
    assert "round_trip_detail" not in text
    assert "below_display_minimum" not in text
    for item in ("L-11n", "L-13", "L-10", "L-06d"):
        assert F11_APPROVED_WORDING[item] not in text
