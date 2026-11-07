"""N-190 第一包 (i): ``/today`` evaluates on the settlement's own series (ADR-0040 Decision 7).

Real cache_first ladders and a fixed clock throughout (QB-7, :mod:`tests.n190_helpers`).
N190-C2 / QB-9: within one ``evaluate_today`` every symbol reaches the market
ladder at most once -- a symbol the settlement loaded is never loaded again,
whatever the status it came back with.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from app.playbook import wording
from tests.n190_helpers import (
    QUIET_CLOSE,
    S1_CLOSE,
    THU,
    TUE,
    WED,
    build,
    hold_shares,
    pending_sell,
    seed_pending,
    sells_of,
    settlement_of,
)


def _gap_sentences(warnings: list[str], symbol: str) -> list[str]:
    return [
        warning
        for warning in warnings
        if warning.startswith(f"【停損今日無法評估】{symbol} ")
        or warning.startswith(f"{symbol} 資料狀態為 ")
    ]


def test_a_due_symbol_is_evaluated_on_the_series_its_settlement_loaded(tmp_path: Path) -> None:
    """[qa-1104] (a): batch 1's S1 is due Wednesday; batch 2's S1 is evaluated as usual."""
    rig = build(tmp_path, {"2330": S1_CLOSE, "2454": S1_CLOSE})
    hold_shares(rig, "2330", 1, 2)
    hold_shares(rig, "2454", 1)
    seed_pending(rig.store, pending_sell("2330", 1, data_date=TUE, execution_date=WED))
    rig.warm(["2330", "2454"], TUE)

    evaluation = rig.today(WED, 16)

    assert [line.directive.symbol for line in settlement_of(evaluation).settled] == ["2330"]
    assert sells_of(evaluation, "2330") == [(2, "S1")]
    assert sells_of(evaluation, "2454") == [(1, "S1")]
    assert _gap_sentences(evaluation.warnings, "2330") == []
    # The S1 line states the status of the series it was decided on: the settlement's.
    (s1,) = [line for line in evaluation.directives if line.symbol == "2330"]
    assert (s1.data_status, s1.data_date) == ("fresh", WED)
    # N190-C2: one ladder answer per symbol for the whole request.
    assert [load.symbol for load in rig.loads_of("2330")] == ["2330"]
    assert [load.symbol for load in rig.loads_of("2454")] == ["2454"]


def test_every_symbol_reaches_the_ladder_at_most_once_per_request(tmp_path: Path) -> None:
    """QB-9: due and not-due symbols together, counted at the ladder and at the source."""
    rig = build(tmp_path, {"2330": S1_CLOSE, "2454": QUIET_CLOSE, "2317": QUIET_CLOSE})
    hold_shares(rig, "2330", 1, 2)
    hold_shares(rig, "2454", 1)
    rig.store.ensure_batches(["2317"], batches_per_target=3)
    seed_pending(rig.store, pending_sell("2330", 1, data_date=TUE, execution_date=WED))
    seed_pending(rig.store, pending_sell("2454", 1, data_date=TUE, execution_date=WED))
    rig.warm(["2330", "2454", "2317"], TUE)

    rig.today(WED, 16)

    assert sorted(load.symbol for load in rig.loads if load.symbol != "^TWII") == [
        "2317",
        "2330",
        "2454",
    ]
    assert [rig.live.calls_for(symbol) for symbol in ("2317", "2330", "2454")] == [1, 1, 1]


def test_the_series_is_reused_whatever_status_it_came_back_with(tmp_path: Path) -> None:
    """N190-C2 「不論狀態」: a failed settlement load is not retried inside the request."""
    rig = build(tmp_path, {"2330": S1_CLOSE})
    hold_shares(rig, "2330", 1, 2)
    seed_pending(rig.store, pending_sell("2330", 1, data_date=TUE, execution_date=WED))
    rig.warm(["2330"], TUE)
    rig.live.failing = True

    evaluation = rig.today(WED, 16)

    (load,) = rig.loads_of("2330")
    assert (load.status, load.is_within_ttl, load.last_bar) == ("cached_stale", False, TUE)
    assert rig.live.calls_for("2330") == 1
    assert [line.directive.symbol for line in settlement_of(evaluation).unsettled] == ["2330"]
    assert _gap_sentences(evaluation.warnings, "2330") == [
        wording.DATA_GAP_HOLDING_NOTE.format(symbol="2330", status="cached_stale", source="twse")
    ]


def test_path_a_prime_a_second_load_in_the_same_request_would_be_unusable(
    tmp_path: Path,
) -> None:
    """ADR-0040 Decision 7 (a′), measured: why (i) stays although (乙) is in.

    Wednesday 15:30, after the 15:00 cutoff but before TWSE published: the
    settlement's load is the first live answer of the cooldown -- ``fresh``,
    still ending Tuesday. A second load of the same request would land inside
    the cooldown as CHECKED_RECENTLY (``cached_stale``, ``is_within_ttl`` False)
    and be unusable even under Decision 1. With (i) the evaluation uses the
    fresh answer.
    """
    rig = build(tmp_path, {"2330": S1_CLOSE})
    hold_shares(rig, "2330", 1, 2)
    seed_pending(
        rig.store, pending_sell("2330", 1, data_date=TUE - timedelta(days=1), execution_date=TUE)
    )
    rig.warm(["2330"], TUE - timedelta(days=1))

    evaluation = rig.today(TUE, 15, 30, published=TUE - timedelta(days=1))

    (load,) = rig.loads_of("2330")
    assert (load.status, load.last_bar, load.live_calls) == ("fresh", TUE - timedelta(days=1), 1)
    assert (2, "S1") in sells_of(evaluation, "2330")
    assert _gap_sentences(evaluation.warnings, "2330") == []

    # What the evaluation would have seen had it loaded again (the pre-(i) code path).
    again = rig.desk._load_symbol_bars(["2330"], today=TUE)["2330"]
    assert again.status == "cached_stale"
    assert rig.last_load("2330").is_within_ttl is False


def test_a_holiday_execution_day_is_evaluated_on_its_first_request(tmp_path: Path) -> None:
    """[qa-1104] (c) on the holiday itself, 16:00: the first live answer has no new bar."""
    rig = build(tmp_path, {"2330": S1_CLOSE}, holidays=frozenset({THU}))
    hold_shares(rig, "2330", 1, 2)
    seed_pending(rig.store, pending_sell("2330", 1, data_date=WED, execution_date=THU))
    rig.warm(["2330"], WED)

    evaluation = rig.today(THU, 16)

    (load,) = rig.loads_of("2330")
    assert (load.status, load.last_bar) == ("fresh", WED)
    assert [line.directive.symbol for line in settlement_of(evaluation).unsettled] == ["2330"]
    assert _gap_sentences(evaluation.warnings, "2330") == []
