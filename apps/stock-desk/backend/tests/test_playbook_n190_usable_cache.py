"""ADR-0040 附錄 B T1～T14: a cache the data layer judged current drives lines (Decision 1).

Every test runs the real cache_first ladders, the real scheduler and route
functions and a fixed clock (QB-7, :mod:`tests.n190_helpers`). Dates are
August 2026: Monday 10th, Tuesday 11th (排程日), Wednesday 12th, Thursday 13th.

QB-4(d): every module test runs under :func:`usable_calls`, a spy around
``is_usable`` in the engine and in the service; at the end of each test every
``cached_stale`` snapshot that reached it must have carried a non-``None``
``is_within_ttl`` (風控 C-4), and the spy must have seen at least one.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.alerts.store import AlertStore
from app.demo.seed import BLUE_CHIP_SYMBOL, seed_demo
from app.playbook import engine as engine_module
from app.playbook import service as service_module
from app.playbook import wording
from app.playbook.models import PlaybookEvaluation
from app.positions.store import PositionStore
from tests.n190_helpers import (
    FRI,
    MON,
    NEXT_MON,
    NEXT_TUE,
    NEXT_WED,
    QUIET_CLOSE,
    S1_CLOSE,
    THU,
    TUE,
    WED,
    WED_BEFORE,
    Rig,
    build,
    hold_shares,
    pending_sell,
    seed_pending,
    sells_of,
    settlement_of,
)

UsableCall = tuple[str, str, bool | None]


@pytest.fixture(autouse=True)
def usable_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[UsableCall]]:
    """QB-4(d): records every ``is_usable`` call; no product code is changed."""
    calls: list[UsableCall] = []
    real = engine_module.is_usable

    def spy(status: str, source: str, *, is_within_ttl: bool | None) -> bool:
        calls.append((status, source, is_within_ttl))
        return real(status, source, is_within_ttl=is_within_ttl)

    monkeypatch.setattr(engine_module, "is_usable", spy)
    monkeypatch.setattr(service_module, "is_usable", spy)
    yield calls
    assert calls, "is_usable was never reached"
    assert [call for call in calls if call[0] == "cached_stale" and call[2] is None] == []


# --- small readers ----------------------------------------------------------------------


def holding_gap(symbol: str, status: str, source: str = "twse") -> str:
    return wording.DATA_GAP_HOLDING_NOTE.format(symbol=symbol, status=status, source=source)


def index_gap(status: str, source: str = "yfinance") -> str:
    return wording.INDEX_DATA_GAP_NOTE.format(status=status, source=source)


def gaps_of(evaluation: PlaybookEvaluation, symbol: str) -> list[str]:
    return [
        warning
        for warning in evaluation.warnings
        if warning.startswith((f"【停損今日無法評估】{symbol} ", f"{symbol} 資料狀態為 "))
    ]


def b4(symbol: str, data_date: date, status: str = "cached_stale") -> str:
    return wording.SAME_DAY_EARLIER_SP_EVALUATED_NOTE.format(
        symbol=symbol, status=status, source="twse", data_date=data_date.isoformat()
    )


def b2(data_date: date) -> str:
    return wording.SAME_DAY_EARLIER_M1_EVALUATED_NOTE.format(
        status="cached_stale", source="yfinance", data_date=data_date.isoformat()
    )


def a_note(symbol: str, count: int, status: str = "cached_stale") -> str:
    return wording.SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE.format(
        symbol=symbol, status=status, line_count=count
    )


def defer_counts(rig: Rig) -> list[tuple[str, int, int]]:
    return [(b.symbol, b.batch_no, b.defer_count) for b in rig.store.list_batches()]


def m1_defers(evaluation: PlaybookEvaluation) -> list[tuple[str, int | None]]:
    return [
        (line.symbol, line.batch_no)
        for line in evaluation.directives
        if line.rule_id == "M1" and line.action == "defer"
    ]


def usable_load(rig: Rig, symbol: str) -> bool:
    load = rig.last_load(symbol)
    return load.status in ("fresh", "backup") or (
        load.status == "cached_stale" and load.is_within_ttl is True
    )


# --- T1 ～ T3: [qa-1104] ------------------------------------------------------------------


def test_t1_a_due_row_the_evaluation_reuses_the_settlement_and_batch_2_s1_runs(
    tmp_path: Path,
) -> None:
    rig = build(tmp_path, {"2330": S1_CLOSE, "2454": S1_CLOSE})
    hold_shares(rig, "2330", 1, 2)
    hold_shares(rig, "2454", 1)
    seed_pending(rig.store, pending_sell("2330", 1, data_date=TUE, execution_date=WED))
    rig.warm(["2330", "2454"], TUE)

    evaluation = rig.today(WED, 16)

    assert [line.directive.symbol for line in settlement_of(evaluation).settled] == ["2330"]
    assert sells_of(evaluation, "2330") == [(2, "S1")]
    assert sells_of(evaluation, "2454") == [(1, "S1")]
    assert gaps_of(evaluation, "2330") == gaps_of(evaluation, "2454") == []
    assert len(rig.loads_of("2330")) == 1  # QB-9


def test_t2_a_reload_the_same_day_is_usable_and_says_nothing_new(tmp_path: Path) -> None:
    rig = build(tmp_path, {"2454": S1_CLOSE})
    hold_shares(rig, "2454", 1)
    rig.warm(["2454"], TUE)
    first = rig.today(WED, 16)

    second = rig.today(WED, 16, 5)

    load = rig.last_load("2454")
    assert (load.status, load.is_within_ttl, load.live_calls) == ("cached_stale", True, 0)
    assert gaps_of(second, "2454") == []
    assert not any(w.startswith("2454 本次資料狀態為") for w in second.warnings)  # no A
    assert second.directives == first.directives
    assert sells_of(second, "2454") == [(1, "S1")]


def test_t3_a_holiday_and_the_four_days_after_are_all_evaluated(tmp_path: Path) -> None:
    """(c): Thursday is a holiday, batch 1's S1 for it is stuck; no rotation, N190-I."""
    rig = build(tmp_path, {"2330": S1_CLOSE, "2454": QUIET_CLOSE}, holidays=frozenset({THU}))
    hold_shares(rig, "2330", 1, 2)
    hold_shares(rig, "2454", 1)
    stuck = pending_sell("2330", 1, data_date=WED, execution_date=THU)
    seed_pending(rig.store, stuck)
    rig.warm(["2330", "2454"], WED)

    noted: list[date] = []
    for day in (THU, FRI, NEXT_MON, NEXT_TUE, NEXT_WED):
        rig.forget()
        evaluation = rig.today(day, 16)
        for symbol in ("2330", "2454"):
            assert usable_load(rig, symbol), (day, symbol)
            assert gaps_of(evaluation, symbol) == [], (day, symbol)
        (line,) = [i for i in settlement_of(evaluation).unsettled if i.directive == stuck]
        if wording.SETTLEMENT_EARLIER_SELL_NOT_DEDUCTED_NOTE.split("{")[0] in line.reason:
            noted.append(day)
    # Friday logs a later S1 for batch 1 (Monday's), so Thursday's line says so;
    # once that later line has settled the batch is closed and nothing is later.
    assert noted == [FRI]


# --- T4 ～ T8: the scheduler ([qa-1105] S1, S1-neg, S1′) ------------------------------------


def _scheduled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, close: str = S1_CLOSE) -> Rig:
    rig = build(tmp_path, {"2330": close, "2454": close})
    rig.patch_consumers(monkeypatch)
    rig.positions = ["2330"]
    hold_shares(rig, "2330", 1)
    rig.prime()
    return rig


def test_t4_the_1510_preload_no_longer_masks_s1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flips N190-C11's scheduler-preload test: 16:00 issues S1 on cached_stale (QB-6)."""
    rig = _scheduled(tmp_path, monkeypatch)
    rig.scheduler_refresh(TUE, 15, 10)

    evaluation = rig.today(TUE, 16)

    load = rig.last_load("2330")
    assert (load.status, load.is_within_ttl, load.live_calls) == ("cached_stale", True, 0)
    (line,) = [d for d in evaluation.directives if d.symbol == "2330"]
    assert (line.rule_id, line.data_status, line.source) == ("S1", "cached_stale", "twse")
    assert gaps_of(evaluation, "2330") == []


def test_t5_a_symbol_the_scheduler_does_not_warm_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _scheduled(tmp_path, monkeypatch)
    rig.positions = ["2454"]
    rig.scheduler_refresh(TUE, 15, 10)

    evaluation = rig.today(TUE, 16)

    assert rig.last_load("2330").status == "fresh"
    (line,) = [d for d in evaluation.directives if d.symbol == "2330"]
    assert (line.rule_id, line.data_status) == ("S1", "fresh")


def test_t6_s1_prime_a_stale_cache_is_not_usable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QB-8 stale／CHECKED_RECENTLY, stock: 15:10 asked before TWSE published."""
    rig = _scheduled(tmp_path, monkeypatch)
    rig.scheduler_refresh(TUE, 15, 10, published=MON)

    evaluation = rig.today(TUE, 16)

    load = rig.last_load("2330")
    assert (load.status, load.is_within_ttl, load.last_bar) == ("cached_stale", False, MON)
    assert sells_of(evaluation, "2330") == []
    assert evaluation.rules_fully_evaluated is False
    assert gaps_of(evaluation, "2330") == [holding_gap("2330", "cached_stale")]


def test_t6_with_a_morning_evaluation_of_the_same_dates_b4_replaces_the_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T6, second half: 10:00 evaluated S/P on Monday's close (sp_evaluated), no sell.

    The index is asked at 15:15, before publication too, so at 16:00 both series
    still end Monday and the 預定執行日 is Tuesday's again: the SP mark matches.
    """
    rig = _scheduled(tmp_path, monkeypatch, close=QUIET_CLOSE)
    morning = rig.today(TUE, 10)
    assert (morning.data_date, morning.execution_date) == (MON, TUE)
    rig.scheduler_refresh(TUE, 15, 10, published=MON)
    rig.signals_page("2454", TUE, 15, 15, published=MON)

    evaluation = rig.today(TUE, 16)

    assert evaluation.execution_date == TUE
    assert gaps_of(evaluation, "2330") == []
    assert b4("2330", MON) in evaluation.warnings
    assert b2(MON) in evaluation.warnings


def test_t6_the_mark_does_not_match_once_the_index_moved_the_execution_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[qa-1105] S1′-a as measured: the index is live at 16:00 and has Tuesday's bar.

    The evaluation is then for Wednesday; the morning's mark is Tuesday's, so the
    original sentence stays -- true of Wednesday's evaluation (Decision 9 第 4 點).
    """
    rig = _scheduled(tmp_path, monkeypatch, close=QUIET_CLOSE)
    rig.today(TUE, 10)
    rig.scheduler_refresh(TUE, 15, 10, published=MON)

    evaluation = rig.today(TUE, 16)

    assert rig.last_load("^TWII").last_bar == TUE
    assert evaluation.execution_date == WED
    assert gaps_of(evaluation, "2330") == [holding_gap("2330", "cached_stale")]
    assert b4("2330", MON) not in evaluation.warnings


def test_t7_s1_prime_b_the_1630_run_makes_it_usable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _scheduled(tmp_path, monkeypatch)
    rig.scheduler_refresh(TUE, 15, 10, published=MON)
    rig.scheduler_refresh(TUE, 16, 30)

    evaluation = rig.today(TUE, 17)

    load = rig.last_load("2330")
    assert (load.status, load.is_within_ttl, load.last_bar) == ("cached_stale", True, TUE)
    assert sells_of(evaluation, "2330") == [(1, "S1")]
    assert gaps_of(evaluation, "2330") == []


def test_t8_s1_prime_c_a_locked_index_is_not_usable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QB-8 stale／CHECKED_RECENTLY, index: 15:30 pins the behaviour; 16:15 no M1."""
    rig = _scheduled(tmp_path, monkeypatch)
    rig.scheduler_refresh(TUE, 15, 10, published=MON)

    early = rig.today(TUE, 15, 30, published=MON)
    stock, index = rig.last_load("2330"), rig.last_load("^TWII")
    assert (stock.status, stock.is_within_ttl, stock.last_bar) == ("cached_stale", False, MON)
    assert (index.status, index.last_bar, index.live_calls) == ("backup", MON, 1)
    assert early.data_date == MON and not early.is_schedule_day
    assert gaps_of(early, "2330") == [holding_gap("2330", "cached_stale")]
    assert index_gap("cached_stale") not in early.warnings
    defense_before = rig.store.portfolio_state().defense_active

    late = rig.today(TUE, 16, 15)

    stock, index = rig.last_load("2330"), rig.last_load("^TWII")
    assert (stock.status, stock.last_bar) == ("fresh", TUE)
    assert (index.status, index.is_within_ttl, index.last_bar) == ("cached_stale", False, MON)
    assert sells_of(late, "2330") == [(1, "S1")]
    assert index_gap("cached_stale") in late.warnings  # M1 not evaluated
    assert rig.store.portfolio_state().defense_active is defense_before


# --- T9 ～ T12: other consumers first ([qa-1105] S2, S3) ------------------------------------


def test_t9_the_stock_page_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _scheduled(tmp_path, monkeypatch)
    rig.positions = []
    rig.bars_page("2330", TUE, 15, 30)

    evaluation = rig.today(TUE, 16)

    assert rig.last_load("2330").status == "cached_stale"
    assert sells_of(evaluation, "2330") == [(1, "S1")]
    assert index_gap("cached_stale") not in evaluation.warnings
    assert index_gap("backup") not in evaluation.warnings


def test_t9_the_signals_page_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _scheduled(tmp_path, monkeypatch)
    rig.positions = []
    rig.signals_page("2330", TUE, 16)

    evaluation = rig.today(TUE, 16, 1)

    for symbol in ("2330", "^TWII"):
        load = rig.last_load(symbol)
        assert (load.status, load.is_within_ttl, load.live_calls) == ("cached_stale", True, 0)
    assert sells_of(evaluation, "2330") == [(1, "S1")]
    assert index_gap("cached_stale") not in evaluation.warnings  # M1 evaluated


def _r_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, cash: bool = False) -> Rig:
    rig = build(tmp_path, {"2317": "100", "2330": "100"})
    rig.patch_consumers(monkeypatch)
    rig.store.ensure_batches(["2317"], batches_per_target=3)
    if cash:
        rig.store.set_capital(
            cash=Decimal("1000000"), total_deploy=Decimal("700000"), source="test"
        )
    rig.prime()
    return rig


def test_t10_the_signals_page_first_no_longer_defers_r(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _r_book(tmp_path, monkeypatch)
    rig.signals_page("2330", TUE, 16)

    evaluation = rig.today(TUE, 16, 1)

    load = rig.last_load("^TWII")
    assert (load.status, load.is_within_ttl) == ("cached_stale", True)
    assert evaluation.is_schedule_day
    assert m1_defers(evaluation) == []
    assert [count for _, _, count in defer_counts(rig)] == [0, 0, 0]
    assert wording.INDEX_DATA_GAP_DEFER_NOTE not in evaluation.warnings


def test_t10_with_cash_r1_enters_on_the_cached_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _r_book(tmp_path, monkeypatch, cash=True)
    rig.signals_page("2330", TUE, 16)

    evaluation = rig.today(TUE, 16, 1)

    buys = [(d.symbol, d.batch_no, d.rule_id) for d in evaluation.directives if d.action == "buy"]
    assert buys == [("2317", 1, "R1")]
    assert m1_defers(evaluation) == []


def _index_decline(_symbol: str, day: date) -> Decimal:
    """Flat 20000, then a decline from Wed 5 Aug: Tuesday is 4 closes below the monthly line."""
    steps = {
        WED_BEFORE: 19900,
        date(2026, 8, 6): 19800,
        date(2026, 8, 7): 19700,
        MON: 19650,
        TUE: 19600,
        WED: 19550,
    }
    if day in steps:
        return Decimal(steps[day])
    return Decimal(20000 if day < WED_BEFORE else 19550)


def test_t11_the_signals_page_first_still_turns_defense_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = build(tmp_path, {"2330": "92", "2454": "50"}, index_price=_index_decline)
    rig.patch_consumers(monkeypatch)
    rig.positions = []
    hold_shares(rig, "2330", 1)
    rig.prime()
    rig.signals_page("2454", TUE, 16)

    evaluation = rig.today(TUE, 16, 1)

    load = rig.last_load("^TWII")
    assert (load.status, load.is_within_ttl) == ("cached_stale", True)
    assert evaluation.mode == "defense"
    assert rig.store.portfolio_state().defense_active is True
    assert sells_of(evaluation, "2330") == [(1, "S1")]  # 92 < 100 × 0.93
    assert m1_defers(evaluation) == []


@pytest.mark.parametrize(
    ("window_days", "warm_index", "status"),
    [(20, True, "cached_stale"), (540, True, "cached_stale"), (20, False, "backup")],
    ids=["short", "long", "cold"],
)
def test_t12_the_sector_board_reference_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    window_days: int,
    warm_index: bool,
    status: str,
) -> None:
    rig = build(tmp_path, {"2317": "100"})
    rig.patch_consumers(monkeypatch)
    rig.store.ensure_batches(["2317"], batches_per_target=3)
    rig.prime(index=warm_index)
    rig.sector_reference(TUE, 18, window_days)

    evaluation = rig.today(TUE, 18, 1)

    assert rig.last_load("^TWII").status == status
    assert m1_defers(evaluation) == []
    assert [count for _, _, count in defer_counts(rig)] == [0, 0, 0]


# --- T13, T14: P-1 and P-4 (Decision 8) ------------------------------------------------------


def _p1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, close: str) -> Rig:
    """10:00 usable on Monday's close; 15:10 and 15:15 ask before publication."""
    rig = build(tmp_path, {"2330": close, "2454": close, "2317": close})
    rig.patch_consumers(monkeypatch)
    rig.positions = ["2330", "2454", "2317"]
    rig.prime()
    return rig


def _afternoon(rig: Rig) -> PlaybookEvaluation:
    rig.scheduler_refresh(TUE, 15, 10, published=MON)
    rig.signals_page("2330", TUE, 15, 15, published=MON)
    evaluation = rig.today(TUE, 15, 30, published=MON)
    assert evaluation.execution_date == TUE
    for symbol in ("2330", "^TWII"):
        load = rig.last_load(symbol)
        assert (load.status, load.is_within_ttl, load.last_bar) == ("cached_stale", False, MON)
    return evaluation


def test_t13_without_an_s_p_sell_b4_and_b2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _p1(tmp_path, monkeypatch, QUIET_CLOSE)
    hold_shares(rig, "2330", 1)
    morning = rig.today(TUE, 10)
    assert usable_load(rig, "2330") and morning.directives == []

    evaluation = _afternoon(rig)

    assert gaps_of(evaluation, "2330") == []
    assert b4("2330", MON) in evaluation.warnings
    assert b2(MON) in evaluation.warnings and index_gap("cached_stale") not in evaluation.warnings


def test_t13_with_an_s_p_sell_no_holding_sentence_no_b4_and_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _p1(tmp_path, monkeypatch, S1_CLOSE)
    hold_shares(rig, "2330", 1)
    morning = rig.today(TUE, 10)
    assert sells_of(morning, "2330") == [(1, "S1")]

    evaluation = _afternoon(rig)

    assert sells_of(evaluation, "2330") == [(1, "S1")]  # the morning's line, listed
    assert gaps_of(evaluation, "2330") == []
    assert b4("2330", MON) not in evaluation.warnings
    assert a_note("2330", 1) in evaluation.warnings


def test_t13_planned_only_or_cost_null_writes_no_mark_and_keeps_the_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _p1(tmp_path, monkeypatch, QUIET_CLOSE)
    rig.store.ensure_batches(["2454", "2317"], batches_per_target=3)
    batch = rig.store.get_batch("2317", 1)
    assert batch is not None
    rig.store.save_batch(
        batch.model_copy(update={"status": "open", "shares": 100, "remaining_shares": 100})
    )  # open, cost NULL: the engine says it holds, S/P never runs on it
    rig.today(TUE, 10)

    evaluation = _afternoon(rig)

    assert gaps_of(evaluation, "2454") == [
        wording.DATA_GAP_NOTE.format(symbol="2454", status="cached_stale", source="twse")
    ]
    assert gaps_of(evaluation, "2317") == [holding_gap("2317", "cached_stale")]
    assert b4("2317", MON) not in evaluation.warnings


def test_t13_no_mark_keeps_the_original_sentences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _p1(tmp_path, monkeypatch, QUIET_CLOSE)
    hold_shares(rig, "2330", 1)  # no morning evaluation

    evaluation = _afternoon(rig)

    assert gaps_of(evaluation, "2330") == [holding_gap("2330", "cached_stale")]
    assert index_gap("cached_stale") in evaluation.warnings


def test_t14_unavailable_after_a_usable_morning_keeps_the_original_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P-4 (R-3): no snapshot, no data_date to compare -- the original sentence stays."""
    rig = _p1(tmp_path, monkeypatch, QUIET_CLOSE)
    hold_shares(rig, "2330", 1)
    rig.today(TUE, 10)
    with closing(sqlite3.connect(rig.cache.db_path)) as conn, conn:  # tmp_path only
        conn.execute("DELETE FROM price_bars_cache WHERE symbol = '2330'")
    rig.live.failing = True

    evaluation = rig.today(TUE, 15, 30)

    assert rig.last_load("2330").status == "unavailable"
    assert gaps_of(evaluation, "2330") == [holding_gap("2330", "unavailable", "none")]
    assert not any(w.startswith("2330 本次資料狀態為 unavailable（") for w in evaluation.warnings)


# --- QB-8: the remaining named negatives ------------------------------------------------------


def test_qb8_stale_r8_stock_a_failing_source_inside_the_cooldown(tmp_path: Path) -> None:
    rig = build(tmp_path, {"2330": S1_CLOSE})
    hold_shares(rig, "2330", 1)
    rig.warm(["2330"], MON)
    rig.live.failing = True
    rig.today(TUE, 16)  # the failed ask: R-8 now applies

    evaluation = rig.today(TUE, 16, 10)

    load = rig.last_load("2330")
    assert (load.status, load.is_within_ttl, load.live_calls) == ("cached_stale", False, 0)
    assert sells_of(evaluation, "2330") == []
    assert evaluation.rules_fully_evaluated is False
    assert gaps_of(evaluation, "2330") == [holding_gap("2330", "cached_stale")]


def test_qb8_stale_r8_index_carries_and_defers_on_a_schedule_day(tmp_path: Path) -> None:
    rig = build(tmp_path, {"2317": "100"})
    rig.store.ensure_batches(["2317"], batches_per_target=3)
    rig.warm(["2317"], MON)
    rig.index_live.failing = True
    rig.today(TUE, 16)

    evaluation = rig.today(TUE, 16, 10)

    load = rig.last_load("^TWII")
    assert (load.status, load.is_within_ttl) == ("cached_stale", False)
    assert index_gap("cached_stale") in evaluation.warnings
    assert m1_defers(evaluation) == [("2317", 1)]
    assert evaluation.rules_fully_evaluated is False


def test_qb8_unavailable_stock(tmp_path: Path) -> None:
    rig = build(tmp_path, {"2330": S1_CLOSE})
    hold_shares(rig, "2330", 1)
    rig.live.failing = True

    evaluation = rig.today(TUE, 16)

    assert rig.last_load("2330").status == "unavailable"
    assert sells_of(evaluation, "2330") == []
    assert evaluation.rules_fully_evaluated is False
    assert gaps_of(evaluation, "2330") == [holding_gap("2330", "unavailable", "none")]


def test_qb8_unavailable_index(tmp_path: Path) -> None:
    rig = build(tmp_path, {"2317": "100"})
    rig.store.ensure_batches(["2317"], batches_per_target=3)
    rig.index_live.failing = True

    evaluation = rig.today(TUE, 16)

    assert rig.last_load("^TWII").status == "unavailable"
    assert index_gap("unavailable", "none") in evaluation.warnings
    assert m1_defers(evaluation) == [("2317", 1)]
    assert evaluation.rules_fully_evaluated is False


def test_qb8_demo_seeded_cache(tmp_path: Path) -> None:
    """A cache written by ``app.demo`` is never usable, whatever its ttl."""
    rig = build(tmp_path, {BLUE_CHIP_SYMBOL: S1_CLOSE})
    seed_demo(
        cache=rig.cache,
        positions=PositionStore(tmp_path / "positions.db"),
        alerts=AlertStore(tmp_path / "alerts.db"),
        today=TUE,
    )
    hold_shares(rig, BLUE_CHIP_SYMBOL, 1)
    rig.live.failing = True

    evaluation = rig.today(TUE, 16)

    load = rig.last_load(BLUE_CHIP_SYMBOL)
    assert (load.status, load.source) == ("cached_stale", "demo_synthetic")
    assert [d for d in evaluation.directives if d.symbol == BLUE_CHIP_SYMBOL] == []
    assert evaluation.rules_fully_evaluated is False
    assert gaps_of(evaluation, BLUE_CHIP_SYMBOL) == [
        holding_gap(BLUE_CHIP_SYMBOL, "cached_stale", "demo_synthetic")
    ]


def test_qb6_the_line_states_cached_stale_and_its_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _scheduled(tmp_path, monkeypatch)
    rig.scheduler_refresh(TUE, 15, 10)
    evaluation = rig.today(TUE, 16)
    rows = rig.store.pending_directives()
    (line,) = [row.directive for row in rows if row.directive.symbol == "2330"]
    assert (line.data_status, line.source) == ("cached_stale", "twse")
    assert [d.data_status for d in evaluation.directives] == ["cached_stale"]


def test_qb19_rebalance_on_a_cache_within_ttl_and_outside_it(tmp_path: Path) -> None:
    """Decision 5 / QB-19: TOTAL_DEPLOY is recomputed on a current cache, refused otherwise."""
    rig = build(tmp_path, {"2330": "100"})
    hold_shares(rig, "2330", 1)
    rig.store.set_capital(cash=Decimal("500000"), total_deploy=Decimal("350000"), source="test")
    rig.warm(["2330"], MON)

    rig.at(TUE, 10)  # Monday is the latest session and the cache has it
    current = rig.desk.rebalance(today=TUE)
    assert (rig.last_load("2330").status, rig.last_load("2330").is_within_ttl) == (
        "cached_stale",
        True,
    )
    assert current.status == "ok"

    rig.at(TUE, 15, 10, published=MON)
    rig.desk._load_symbol_bars(["2330"], today=TUE)  # the 15:10 ask, nothing new
    rig.at(TUE, 15, 30, published=MON)
    stale = rig.desk.rebalance(today=TUE)
    assert rig.last_load("2330").is_within_ttl is False
    assert stale.status == "insufficient_data"
