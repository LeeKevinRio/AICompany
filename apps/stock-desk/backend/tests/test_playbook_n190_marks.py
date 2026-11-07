"""(甲) narrowed: marks, their lock, and the B-4／B-2 sentences (ADR-0040 Decision 9).

* the store: one table, no UNIQUE, written and read inside ``commit_evaluation``'s
  ``BEGIN IMMEDIATE`` (QB-11);
* ``sp_evaluated`` and ``m1_evaluated`` against the engine itself (QB-12);
* ``same_day_warnings``: B-4 → A → B, C-1's 「HOLDING 不渲染」, B-2 on the status
  branch only, every condition structured (Decision 9 第 4～6 點);
* the real ladder on P-1 (QB-7).

Snapshots built by hand are ``cached_stale`` with no ``is_within_ttl``: unusable
both before and after (乙), so these pin (甲) on its own.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.playbook import engine as engine_module
from app.playbook import wording
from app.playbook.engine import evaluate
from app.playbook.models import (
    BatchState,
    Directive,
    IndexSnapshot,
    MarketSnapshot,
    PlaybookEvaluation,
    SymbolState,
)
from app.playbook.service import (
    M1_MARK_SUBJECT,
    evaluation_marks,
    m1_evaluated,
    same_day_warnings,
    sp_evaluated,
)
from app.playbook.store import (
    MARK_KIND_M1,
    MARK_KIND_SP,
    EvaluationCommit,
    EvaluationMark,
    PlaybookStore,
)
from tests import playbook_helpers as helper
from tests.n190_helpers import (
    MON,
    QUIET_CLOSE,
    TUE,
    build,
    hold_shares,
)
from tests.same_day_helpers import buy_line, evaluation_of

# --- the store ------------------------------------------------------------------------


def _mark(kind: str, subject: str, execution: date, data: date) -> EvaluationMark:
    return EvaluationMark(kind=kind, subject=subject, execution_date=execution, data_date=data)


def test_the_mark_table_has_no_unique_and_no_primary_key(tmp_path: Path) -> None:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    with closing(sqlite3.connect(store.db_path)) as conn:
        indexes = conn.execute("PRAGMA index_list(playbook_evaluation_marks)").fetchall()
        columns = conn.execute("PRAGMA table_info(playbook_evaluation_marks)").fetchall()
    assert indexes == []
    assert [str(row[1]) for row in columns] == [
        "kind",
        "subject",
        "execution_date",
        "data_date",
        "created_at",
    ]
    assert all(int(row[5]) == 0 for row in columns)  # no column is part of a primary key


def test_a_commit_returns_the_marks_that_existed_before_it_and_writes_its_own_once(
    tmp_path: Path,
) -> None:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    helper.confirm_rule_set(store)
    evaluation = evaluation_of(store, [])
    sp = _mark(MARK_KIND_SP, "2330", evaluation.execution_date, TUE)
    m1 = _mark(MARK_KIND_M1, "^TWII", evaluation.execution_date, TUE)
    other_day = _mark(MARK_KIND_SP, "2330", date(2026, 9, 1), TUE)

    first = store.commit_evaluation(evaluation, marks=[sp, sp, other_day])
    second = store.commit_evaluation(evaluation, marks=[sp, m1])
    third = store.commit_evaluation(evaluation)

    assert first.earlier_marks == frozenset()
    assert second.earlier_marks == {sp}  # another 預定執行日 is not read
    assert third.earlier_marks == {sp, m1}
    with closing(sqlite3.connect(store.db_path)) as conn:
        rows = conn.execute(
            "SELECT kind, subject, execution_date, data_date FROM playbook_evaluation_marks"
        ).fetchall()
    assert sorted(rows) == sorted(
        [
            (mark.kind, mark.subject, mark.execution_date.isoformat(), mark.data_date.isoformat())
            for mark in (sp, other_day, m1)
        ]
    )


def test_marks_are_read_and_written_inside_the_commits_write_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QB-11 / Decision 9 第 1 點: the read precedes the write, both under BEGIN IMMEDIATE."""
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    helper.confirm_rule_set(store)
    evaluation = evaluation_of(store, [])
    traced: list[str] = []
    real_connect = sqlite3.connect

    def tracing(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        conn.set_trace_callback(traced.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracing)
    store.commit_evaluation(
        evaluation, marks=[_mark(MARK_KIND_SP, "2330", evaluation.execution_date, TUE)]
    )

    begin, commit = traced.index("BEGIN IMMEDIATE"), traced.index("COMMIT")
    touching = [index for index, sql in enumerate(traced) if "playbook_evaluation_marks" in sql]
    assert touching and all(begin < index < commit for index in touching)
    assert traced[touching[0]].lstrip().startswith("SELECT")
    assert traced[touching[-1]].lstrip().startswith("INSERT")
    assert not any(sql.lstrip().upper().startswith("DELETE") for sql in traced)


# --- QB-12: the predicates against the engine -----------------------------------------


def _run(
    batches: Sequence[BatchState],
    snapshot: MarketSnapshot | None,
    *,
    symbol_state: SymbolState | None = None,
) -> PlaybookEvaluation:
    return evaluate(
        data_date=helper.TUESDAY,
        calendar=helper.calendar(),
        params=helper.params(),
        index=helper.index(),
        markets={} if snapshot is None else {"2330": snapshot},
        batches=list(batches),
        symbols={} if symbol_state is None else {"2330": symbol_state},
        portfolio=helper.portfolio(),
    )


_S1 = helper.market("2330", close="88")
_S2 = helper.market("2330", close="80")
_OPEN = helper.batch("2330", 1)
_PLANNED = helper.planned("2330", 1)

SP_TABLE: dict[str, tuple[list[BatchState], MarketSnapshot | None, SymbolState | None]] = {
    "eligible open batch": ([_OPEN], _S1, None),
    "only planned": ([_PLANNED, helper.planned("2330", 2)], _S1, None),
    "open, remaining_shares == 0": ([helper.batch("2330", 1, remaining=0)], _S1, None),
    "open, cost NULL": ([helper.batch("2330", 1, cost=None)], _S1, None),
    "eligible + paused": ([_OPEN], _S1, SymbolState(symbol="2330", paused=True)),
    "eligible + blacklisted": ([_OPEN], _S1, SymbolState(symbol="2330", blacklisted=True)),
    "S2 fires": ([_OPEN, helper.batch("2330", 2)], _S2, None),
    "unusable snapshot (cached_stale, no ttl)": (
        [_OPEN],
        helper.market("2330", close="88", status="cached_stale"),
        None,
    ),
    "unusable snapshot (demo)": (
        [_OPEN],
        helper.market("2330", close="88", source="demo_synthetic"),
        None,
    ),
    "snapshot is None": ([_OPEN], None, None),
}


@pytest.mark.parametrize("case", sorted(SP_TABLE))
def test_sp_evaluated_is_the_engines_own_s_p_gate(case: str) -> None:
    """At a close that meets S1, the engine sells for the symbol exactly when S/P ran."""
    batches, snapshot, symbol_state = SP_TABLE[case]
    evaluation = _run(batches, snapshot, symbol_state=symbol_state)
    engine_ran_s_p = any(
        line.symbol == "2330" and line.action == "sell" for line in evaluation.directives
    )
    assert sp_evaluated(batches, snapshot) is engine_ran_s_p
    expected = case in {"eligible open batch", "eligible + paused", "eligible + blacklisted"}
    assert engine_ran_s_p is (expected or case == "S2 fires")


M1_TABLE: dict[str, IndexSnapshot | None] = {
    "evaluated": helper.index(),
    "evaluated, fresh": helper.index(status="fresh", source="twse"),
    "index is None": None,
    "unusable (cached_stale, no ttl)": helper.index(status="cached_stale"),
    "unusable (unavailable)": helper.index(status="unavailable"),
    "unusable (demo)": helper.index(source="demo_synthetic"),
    "no monthly line (insufficient_data)": helper.index(monthly_line=None),
}


@pytest.mark.parametrize("case", sorted(M1_TABLE))
def test_m1_evaluated_is_the_third_branch_of_defense_transition(case: str) -> None:
    """Branches one and two warn and carry; branch three warns nothing."""
    index = M1_TABLE[case]
    _, _, warnings = engine_module._defense_transition(index, helper.portfolio(), helper.params())
    assert m1_evaluated(index) is (warnings == [])
    assert m1_evaluated(index) is case.startswith("evaluated")


def test_evaluation_marks_names_what_was_evaluated_on_what() -> None:
    held = helper.market("2330", close="100")
    planned = helper.market("2454", close="100")
    batches = [_OPEN, helper.planned("2454", 1)]
    evaluation = evaluate(
        data_date=helper.TUESDAY,
        calendar=helper.calendar(),
        params=helper.params(),
        index=helper.index(data_date=date(2026, 8, 10)),
        markets={"2330": held, "2454": planned},
        batches=batches,
        symbols={},
        portfolio=helper.portfolio(),
    )
    marks = evaluation_marks(
        evaluation,
        batches=batches,
        markets={"2330": held, "2454": planned},
        index=helper.index(data_date=date(2026, 8, 10)),
    )
    assert marks == [
        _mark(MARK_KIND_SP, "2330", evaluation.execution_date, held.data_date),
        _mark(MARK_KIND_M1, M1_MARK_SUBJECT, evaluation.execution_date, date(2026, 8, 10)),
    ]
    assert M1_MARK_SUBJECT == "^TWII"


# --- same_day_warnings ----------------------------------------------------------------

_STALE = helper.market("2330", close="88", status="cached_stale")
_STALE_INDEX = helper.index(status="cached_stale", source="yfinance")


def _evaluation(
    markets: dict[str, MarketSnapshot],
    batches: list[BatchState],
    *,
    index: IndexSnapshot | None = None,
) -> PlaybookEvaluation:
    return evaluate(
        data_date=helper.TUESDAY,
        calendar=helper.calendar(),
        params=helper.params(),
        index=index or helper.index(),
        markets=markets,
        batches=batches,
        symbols={},
        portfolio=helper.portfolio(),
        previous_fast_market=None,
    )


def _render(
    evaluation: PlaybookEvaluation,
    logged: list[Directive],
    marks: set[EvaluationMark],
    *,
    markets: dict[str, MarketSnapshot],
    batches: list[BatchState],
    index: IndexSnapshot | None = None,
) -> list[str]:
    return same_day_warnings(
        evaluation,
        EvaluationCommit(written=[], logged=logged, earlier_marks=frozenset(marks)),
        markets=markets,
        batches=batches,
        portfolio=helper.portfolio(),
        index=index,
    )


def _line(symbol: str, batch_no: int | None, rule_id: str, action: str) -> Directive:
    return buy_line(symbol=symbol, batch_no=batch_no).model_copy(
        update={"rule_id": rule_id, "action": action}
    )


def _holding_gap(snapshot: MarketSnapshot) -> str:
    return wording.DATA_GAP_HOLDING_NOTE.format(
        symbol=snapshot.symbol, status=snapshot.data_status, source=snapshot.source
    )


def _b4(snapshot: MarketSnapshot) -> str:
    return wording.SAME_DAY_EARLIER_SP_EVALUATED_NOTE.format(
        symbol=snapshot.symbol,
        status=snapshot.data_status,
        source=snapshot.source,
        data_date=snapshot.data_date.isoformat(),
    )


def _a(count: int) -> str:
    return wording.SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE.format(
        symbol="2330", status="cached_stale", line_count=count
    )


def _b(count: int) -> str:
    return wording.SAME_DAY_EARLIER_DECISIONS_DATA_GAP_NOTE.format(
        symbol="2330", decision_count=count
    )


def _sp_mark(evaluation: PlaybookEvaluation, data_date: date = helper.TUESDAY) -> EvaluationMark:
    return _mark(MARK_KIND_SP, "2330", evaluation.execution_date, data_date)


_BOOK = [_OPEN, helper.planned("2330", 2), helper.planned("2330", 3)]


def test_b4_takes_the_holding_sentences_place_even_with_nothing_logged() -> None:
    """Decision 9 第 5 點: `if not orders and not decisions: continue` does not skip (甲)."""
    markets = {"2330": _STALE}
    evaluation = _evaluation(markets, _BOOK)
    position = evaluation.warnings.index(_holding_gap(_STALE))

    warnings = _render(evaluation, [], {_sp_mark(evaluation)}, markets=markets, batches=_BOOK)

    assert warnings[position] == _b4(_STALE)
    assert _holding_gap(_STALE) not in warnings
    assert len(warnings) == len(evaluation.warnings)


def test_b4_then_a_then_b_when_the_log_has_no_s_p_sell() -> None:
    markets = {"2330": _STALE}
    evaluation = _evaluation(markets, _BOOK)
    logged = [_line("2330", 2, "R1", "buy"), _line("2330", 3, "R2", "defer")]
    plain = _render(evaluation, logged, set(), markets=markets, batches=_BOOK)
    position = plain.index(_holding_gap(_STALE))  # the ENTRY note went first

    warnings = _render(evaluation, logged, {_sp_mark(evaluation)}, markets=markets, batches=_BOOK)

    assert plain[position : position + 3] == [_holding_gap(_STALE), _a(1), _b(1)]
    assert warnings[position : position + 3] == [_b4(_STALE), _a(1), _b(1)]
    assert len(warnings) == len(plain)


def test_with_an_s_p_sell_the_holding_sentence_and_b4_go_and_a_then_b_take_the_place() -> None:
    """風控 C-1 / N190-C9: no HOLDING, no B-4, A as usual, B after A."""
    markets = {"2330": _STALE}
    evaluation = _evaluation(markets, _BOOK)
    position = evaluation.warnings.index(_holding_gap(_STALE))
    logged = [_line("2330", 1, "S1", "sell"), _line("2330", 3, "R2", "defer")]

    warnings = _render(evaluation, logged, {_sp_mark(evaluation)}, markets=markets, batches=_BOOK)

    assert warnings[position : position + 2] == [_a(1), _b(1)]
    assert _holding_gap(_STALE) not in warnings and _b4(_STALE) not in warnings


@pytest.mark.parametrize("rule_id", ["S1", "S2", "P1", "P2", "P3"])
def test_every_s_p_rule_id_counts_as_an_s_p_sell(rule_id: str) -> None:
    markets = {"2330": _STALE}
    evaluation = _evaluation(markets, _BOOK)
    logged = [_line("2330", None if rule_id == "S2" else 1, rule_id, "sell")]
    warnings = _render(evaluation, logged, {_sp_mark(evaluation)}, markets=markets, batches=_BOOK)
    assert _b4(_STALE) not in warnings and _a(1) in warnings


def _unchanged(
    evaluation: PlaybookEvaluation,
    marks: set[EvaluationMark],
    *,
    markets: dict[str, MarketSnapshot],
    batches: list[BatchState],
) -> None:
    logged = [_line(symbol, 2, "R1", "buy") for symbol in markets]
    without = _render(evaluation, logged, set(), markets=markets, batches=batches)
    assert _render(evaluation, logged, marks, markets=markets, batches=batches) == without


def test_no_mark_of_this_data_date_keeps_the_original_sentences() -> None:
    markets = {"2330": _STALE}
    evaluation = _evaluation(markets, _BOOK)
    other = {
        _sp_mark(evaluation, data_date=MON),  # another 依據資料日
        _mark(MARK_KIND_SP, "2330", date(2026, 9, 1), helper.TUESDAY),  # another 預定執行日
        _mark(MARK_KIND_M1, "2330", evaluation.execution_date, helper.TUESDAY),  # another kind
        _mark(MARK_KIND_SP, "2454", evaluation.execution_date, helper.TUESDAY),  # another symbol
    }
    _unchanged(evaluation, other, markets=markets, batches=_BOOK)


def test_a_symbol_that_holds_nothing_keeps_its_data_gap_note() -> None:
    """Decision 9 第 2 點: only planned batches -> DATA_GAP_NOTE stays (with A)."""
    planned = [helper.planned("2330", batch_no) for batch_no in (1, 2, 3)]
    markets = {"2330": _STALE}
    evaluation = _evaluation(markets, planned)
    _unchanged(evaluation, {_sp_mark(evaluation)}, markets=markets, batches=planned)


@pytest.mark.parametrize(
    "snapshot",
    [
        helper.market("2330", close="88", status="cached_stale", source="demo_synthetic"),
        helper.market("2330", close="88", status="unavailable"),
    ],
    ids=["demo", "unavailable"],
)
def test_demo_and_other_statuses_keep_the_original_sentences(snapshot: MarketSnapshot) -> None:
    markets = {"2330": snapshot}
    evaluation = _evaluation(markets, _BOOK)
    _unchanged(evaluation, {_sp_mark(evaluation)}, markets=markets, batches=_BOOK)


def test_no_snapshot_keeps_the_original_sentences() -> None:
    """P-4 (R-3): nothing to compare a data_date with."""
    evaluation = _evaluation({}, _BOOK)
    _unchanged(evaluation, {_sp_mark(evaluation)}, markets={}, batches=_BOOK)


def test_b2_takes_the_place_of_the_index_status_branch_only() -> None:
    evaluation = _evaluation({}, [], index=_STALE_INDEX)
    original = wording.INDEX_DATA_GAP_NOTE.format(status="cached_stale", source="yfinance")
    position = evaluation.warnings.index(original)
    mark = _mark(MARK_KIND_M1, M1_MARK_SUBJECT, evaluation.execution_date, _STALE_INDEX.data_date)

    warnings = _render(evaluation, [], {mark}, markets={}, batches=[], index=_STALE_INDEX)

    assert warnings[position] == wording.SAME_DAY_EARLIER_M1_EVALUATED_NOTE.format(
        status="cached_stale", source="yfinance", data_date=_STALE_INDEX.data_date.isoformat()
    )
    assert original not in warnings
    # FAST_MARKET_* stay as the engine wrote them (風控 B-2).
    assert [w for w in warnings if w.startswith("加權指數資料狀態為 cached_stale，")] == [
        w for w in evaluation.warnings if w.startswith("加權指數資料狀態為 cached_stale，")
    ]


def test_b2_does_not_replace_the_insufficient_data_branch_nor_render_without_a_mark() -> None:
    thin = helper.index(monthly_line=None)
    evaluation = _evaluation({}, [], index=thin)
    insufficient = wording.INDEX_DATA_GAP_NOTE.format(
        status="insufficient_data", source=thin.source
    )
    assert insufficient in evaluation.warnings
    mark = _mark(MARK_KIND_M1, M1_MARK_SUBJECT, evaluation.execution_date, thin.data_date)
    assert insufficient in _render(evaluation, [], {mark}, markets={}, batches=[], index=thin)

    stale = _evaluation({}, [], index=_STALE_INDEX)
    other_day = _mark(MARK_KIND_M1, M1_MARK_SUBJECT, stale.execution_date, MON)
    assert _render(stale, [], {other_day}, markets={}, batches=[], index=_STALE_INDEX) == (
        _render(stale, [], set(), markets={}, batches=[], index=_STALE_INDEX)
    )


# --- the real ladder: P-1 -------------------------------------------------------------


def test_p1_a_reload_inside_the_cooldown_gets_b4_and_b2(tmp_path: Path) -> None:
    """Decision 8 P-1 (QB-7): 15:05 is the first live answer after the cutoff, TWSE not
    out yet; 15:30 reads the cache inside the cooldown -- same 依據資料日, ttl False."""
    rig = build(tmp_path, {"2330": QUIET_CLOSE})
    hold_shares(rig, "2330", 1)
    rig.warm(["2330"], MON)

    first = rig.today(TUE, 15, 5, published=MON)
    assert rig.last_load("2330").status == "fresh"
    assert first.directives == []

    second = rig.today(TUE, 15, 30, published=MON)

    stock, index = rig.last_load("2330"), rig.last_load("^TWII")
    assert (stock.status, stock.is_within_ttl, stock.last_bar) == ("cached_stale", False, MON)
    assert (index.status, index.is_within_ttl, index.last_bar) == ("cached_stale", False, MON)
    b4 = wording.SAME_DAY_EARLIER_SP_EVALUATED_NOTE.format(
        symbol="2330", status="cached_stale", source="twse", data_date=MON.isoformat()
    )
    b2 = wording.SAME_DAY_EARLIER_M1_EVALUATED_NOTE.format(
        status="cached_stale", source="yfinance", data_date=MON.isoformat()
    )
    assert b4 in second.warnings and b2 in second.warnings
    assert not any(w.startswith("【停損今日無法評估】2330 ") for w in second.warnings)
    assert wording.INDEX_DATA_GAP_NOTE.format(status="cached_stale", source="yfinance") not in (
        second.warnings
    )
