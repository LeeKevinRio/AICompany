"""N-182: W-B6b and the ENTRY／A exclusions (風控 2026-11-01 P2(d)／P4／P5).

A buy whose batch row exists and has left ``planned`` is refused by G1 at every
settlement, so the book never fills it. Before N-182 two live sentences still
told the reader it would be "judged as usual": SAME_DAY_EARLIER_ENTRY_NOTE and
A (SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE), e.g. for a same-day R1 whose batch
was filled meanwhile by an older line whose bar was back-filled (V4). Now:

* those buys are left out of ENTRY's lines and A's count (必改 5);
* ``/today`` names them in W-B6b ``PENDING_ENTRY_BLOCKED_NOTE`` -- every mode,
  K1-deduplicated, minus the lines G1 refused in this run's settlement, which
  ``unsettled`` names already (必改 5, 測試 7(e));
* the block after FROZEN_NOTE is ENTRY → W-B6b, first when FROZEN_NOTE is not
  there (P4; W-B6 and W-B1d are N-168's, not here; 測試 7(g));
* 「批次已非 planned」 is G1's own condition, one store constant, and a guard
  shows both places use it (必改 2, ADR-0035 補充一 S-1, ADR-0034 補充一 S-1 第 3 點);
  the buys are read inside the seam's one ``read_in_flight`` (補充四 S-5 第 4 點);
* the sentence is the ruling's, read from the ruling file (必改 1, 測試 7(h)).
"""

from __future__ import annotations

import ast
import inspect
import itertools
import sqlite3
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_cap1_reading, get_playbook_service
from app.api.playbook_cap1_wording import Cap1Reading
from app.main import app
from app.playbook import engine as engine_module
from app.playbook import service as service_module
from app.playbook import store as store_module
from app.playbook import wording
from app.playbook.models import BatchStatus, Directive, PlaybookEvaluation
from app.playbook.service import g1_blocked_entries, same_day_warnings
from app.playbook.store import (
    BATCH_LEFT_PLANNED_SQL,
    R_SERIES_RULE_IDS,
    EntryBeforeExitRead,
    EvaluationCommit,
    PendingDirective,
    PlaybookStore,
    decision_key,
)
from tests import playbook_helpers as helper
from tests.api_helpers import CLIENT_HEADERS
from tests.same_day_helpers import (
    MONDAY,
    ONE_BUY_SHARES,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Desk,
    bars,
    buy_line,
    evaluation_of,
    hold,
    log_like_before_n172a,
    open_desk,
)

RULING = "work/reviews/2026-11-01-N168字面裁示P2至P5-風控.md"
FRIDAY_BEFORE = date(2026, 8, 7)


def _ruling_sentence(identifier: str) -> str:
    """The 「…」 paragraph under the ruling's heading that names ``identifier``."""
    lines = (Path(__file__).resolve().parents[4] / RULING).read_text(encoding="utf-8").splitlines()
    (heading,) = [
        index
        for index, line in enumerate(lines)
        if line.startswith("####") and f"`{identifier}`" in line
    ]
    body = next(line for line in lines[heading + 1 :] if line.strip())
    assert body.startswith("「") and body.endswith("」")
    return body[1:-1]


def _item(line: Directive) -> str:
    return wording.SAME_DAY_EARLIER_ENTRY_ITEM.format(
        symbol=line.symbol,
        batch_no=line.batch_no,
        shares=line.shares,
        rule_id=line.rule_id,
        execution_date=line.execution_date.isoformat(),
    )


def _w_b6b(*lines: Directive) -> str:
    # 風控 2026-11-04 第 10 點: the sentence says 「R 系列買進指令」, so every
    # line it is expected to count is an R-series buy.
    assert all(line.action == "buy" and line.rule_id in R_SERIES_RULE_IDS for line in lines)
    return wording.PENDING_ENTRY_BLOCKED_NOTE.format(
        blocked_count=len(lines), entry_items="、".join(_item(line) for line in lines)
    )


def _entry(*lines: Directive) -> str:
    return wording.SAME_DAY_EARLIER_ENTRY_NOTE.format(
        entry_count=len(lines), entry_items="、".join(_item(line) for line in lines)
    )


def _blocked_notes(warnings: list[str]) -> list[str]:
    return [warning for warning in warnings if warning.startswith("尚有 ")]


def _entry_notes(warnings: list[str]) -> list[str]:
    return [warning for warning in warnings if warning.startswith("指令帳冊中有")]


def _set_status(store: PlaybookStore, symbol: str, batch_no: int, status: BatchStatus) -> None:
    batch = store.get_batch(symbol, batch_no)
    assert batch is not None
    store.save_batch(batch.model_copy(update={"status": status}))


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    return open_desk(tmp_path / "playbook.db")


# --- 必改 1 / 測試 7(h): the sentence and its string guards ------------------------------


def test_w_b6b_is_the_ruling_sentence_verbatim() -> None:
    assert wording.PENDING_ENTRY_BLOCKED_NOTE == _ruling_sentence("PENDING_ENTRY_BLOCKED_NOTE")


#: N-168 方案裁示 第 3 點's 禁用詞, plus 「你已買進」 (FR 字串檢查).
FORBIDDEN = ("需", "應", "建議", "務必", "盡快", "否則", "安全", "已取消", "已撤單", "你已買進")


#: 風控 2026-11-04 第 9 點: the one exemption from 「應」, verbatim -- not every 「對應」.
EXEMPT_CORRESPONDING = "對應的批次"


def test_w_b6b_passes_the_string_guards() -> None:
    sentence = wording.PENDING_ENTRY_BLOCKED_NOTE
    # The ruling's own 「對應的批次」 is not the modal "should"; exactly that phrase,
    # exactly once, is exempt, and no other 「應」 may remain (e.g. 「對應該」).
    assert sentence.count(EXEMPT_CORRESPONDING) == 1
    modal = sentence.replace(EXEMPT_CORRESPONDING, "", 1)
    assert modal.count("應") == 0
    for banned in FORBIDDEN:
        assert banned not in modal, banned
    assert "本系統不下單" in sentence
    assert "無法替你在券商撤單" in sentence
    # 條件 (a)(c): no unqualified 「已成交」; both outcomes are stated.
    assert "已成交" not in sentence
    assert "若你在券商的買進實際成交" in sentence and "若未下單或未成交" in sentence


def test_w_b6b_lives_in_wording_only_and_the_store_never_imports_it() -> None:
    app_root = Path(wording.__file__).resolve().parents[1]
    fragment = "帳冊不會依這幾筆判定成交"
    holders = [
        path.relative_to(app_root).as_posix()
        for path in sorted(app_root.rglob("*.py"))
        if fragment in path.read_text(encoding="utf-8")
    ]
    assert holders == ["playbook/wording.py"]
    imported = {
        alias.name
        for node in ast.walk(ast.parse(Path(store_module.__file__).read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "wording" not in imported


# --- 必改 2: one source for 「批次已非 planned」 ------------------------------------------


def _names_used(function: Any) -> set[str]:
    tree = ast.parse(inspect.cleandoc("\n" + inspect.getsource(function)))
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def test_the_condition_is_written_once_and_both_places_splice_it() -> None:
    """Static half: one literal in the store, and G1's claim, its reason pick and
    the in-flight classification all name the same constant."""
    source = Path(store_module.__file__).read_text(encoding="utf-8")
    assert source.count("<> 'planned'") == 1
    assert "<> 'planned'" in BATCH_LEFT_PLANNED_SQL
    for function in (
        store_module.PlaybookStore.claim_directive,
        store_module.PlaybookStore.batch_blocking_claim,
        store_module._read_entry_before_exit,
    ):
        assert "BATCH_LEFT_PLANNED_SQL" in _names_used(function), function.__name__
    # The service never decides it on its own: the function's code (its
    # docstring aside) reads no status and compares with no 'planned'.
    (definition,) = ast.parse(inspect.getsource(g1_blocked_entries)).body
    assert isinstance(definition, ast.FunctionDef)
    code = definition.body[1:] if ast.get_docstring(definition) else definition.body
    nodes = [node for statement in code for node in ast.walk(statement)]
    assert not [n for n in nodes if isinstance(n, ast.Constant) and "planned" in str(n.value)]
    assert not [n for n in nodes if isinstance(n, ast.Attribute) and n.attr == "status"]
    assert "blocked" in {n.attr for n in nodes if isinstance(n, ast.Attribute)}


def _trace(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    statements: list[str] = []
    real_connect = sqlite3.connect

    def tracing(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracing)
    return statements


def test_the_claim_and_the_in_flight_read_run_the_same_condition(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runtime half: the SQL actually executed carries the constant verbatim."""
    log_like_before_n172a(desk.store, [buy_line()])
    _set_status(desk.store, "2330", 1, "open")
    (pending,) = desk.store.pending_directives()
    statements = _trace(monkeypatch)

    assert not desk.store.claim_directive(
        pending.directive_id, status="executed", open_price=Decimal(100)
    )
    assert desk.store.batch_blocking_claim(pending.directive_id) == "open"
    read = desk.store.read_in_flight()

    claim = [sql for sql in statements if sql.lstrip().startswith("UPDATE playbook_directives")]
    reads = [
        sql
        for sql in statements
        if sql.lstrip().startswith("SELECT") and "FROM playbook_directives" in sql
    ]
    assert len(claim) == 1 and BATCH_LEFT_PLANNED_SQL in claim[0]
    using = [sql for sql in reads if BATCH_LEFT_PLANNED_SQL in sql]
    assert len(using) == 2  # batch_blocking_claim, then the in-flight read
    assert "settled = 0 AND status = 'pending'" in using[1]
    assert read.entries.blocked == (pending,)


@pytest.mark.parametrize(
    ("batch_no", "status"),
    [
        (1, "planned"),
        (1, "open"),
        (1, "closed"),
        (1, "skipped"),
        (9, None),  # no batch row
        (None, None),  # batch_no NULL
    ],
    ids=["planned", "open", "closed", "skipped", "no-batch-row", "batch-no-null"],
)
def test_the_in_flight_classification_is_exactly_what_g1_refuses(
    desk: Desk, batch_no: int | None, status: BatchStatus | None
) -> None:
    """Agreement on every batch state: blocked in flight ⇔ the claim is refused.
    A missing batch row and a NULL ``batch_no`` are neither (共用定義)."""
    if status is not None and batch_no is not None:
        _set_status(desk.store, "2330", batch_no, status)
    log_like_before_n172a(desk.store, [buy_line(batch_no=batch_no)])
    sell = buy_line(batch_no=batch_no).model_copy(update={"action": "sell", "rule_id": "S1"})
    log_like_before_n172a(desk.store, [sell])
    buy, sold = desk.store.pending_directives()

    blocked = {item.directive_id for item in desk.store.read_in_flight().entries.blocked}
    refused = not desk.store.claim_directive(
        buy.directive_id, status="executed", open_price=Decimal(100)
    )

    assert (buy.directive_id in blocked) is refused
    assert refused is (status in {"open", "closed", "skipped"})
    assert sold.directive_id not in blocked  # sells are never G1's


# --- 測試 7(d): V4 + a back-filled bar -------------------------------------------------


def test_a_same_day_buy_whose_batch_was_filled_meanwhile_leaves_entry_and_a_for_w_b6b(
    tmp_path: Path,
) -> None:
    """Monday's R1 (logged Friday) has no bar yet; Tuesday's run logs R1 for the same
    still-planned batch for Wednesday. Monday's bar is back-filled, the next run
    fills the batch with Monday's line, and Wednesday's R1 can no longer fill."""
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2454"))
    full = bars("2330", 100.0)
    desk.prices.seed("2330", [bar for bar in full if bar.date != MONDAY])
    monday = buy_line(data_date=FRIDAY_BEFORE, execution_date=MONDAY)
    log_like_before_n172a(desk.store, [monday])

    first = desk.service.evaluate_today(today=TUESDAY)
    wednesday = next(
        line for line in first.directives if (line.symbol, line.rule_id) == ("2330", "R1")
    )
    assert (wednesday.batch_no, wednesday.execution_date) == (1, WEDNESDAY)
    assert _blocked_notes(first.warnings) == []  # batch 1 is still planned

    desk.prices.seed("2330", full)  # the provider back-fills Monday
    second = desk.service.evaluate_today(today=TUESDAY)

    assert second.settlement is not None and second.settlement.executed == 1
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.status == "open"
    assert wednesday in second.directives  # the logged list is unchanged (Decision 4)
    assert _entry_notes(second.warnings) == []  # not "judged as usual" any more
    assert _blocked_notes(second.warnings) == [_w_b6b(wednesday)]
    assert second.warnings[0] == _w_b6b(wednesday)  # normal mode: the block comes first

    desk.prices.seed("2330", [])  # 2330 unusable on the next run: A would follow its gap
    third = desk.service.evaluate_today(today=TUESDAY)

    gap = wording.DATA_GAP_HOLDING_NOTE.format(symbol="2330", status="unavailable", source="none")
    assert gap in third.warnings
    assert not [w for w in third.warnings if w.startswith("2330 本次資料狀態為")]  # A: count 0
    assert _entry_notes(third.warnings) == []
    assert _blocked_notes(third.warnings) == [_w_b6b(wednesday)]


def test_a_counts_only_the_lines_left_after_the_exclusion(tmp_path: Path) -> None:
    """A planned-batch buy and a blocked one of the same symbol: A says 1, ENTRY
    lists the planned one, W-B6b the blocked one -- disjoint, together all."""
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2454"))
    desk.service.evaluate_today(today=TUESDAY)  # logs R1 2330 #1 and 2454 #1 for Wednesday
    _set_status(desk.store, "2454", 1, "skipped")
    desk.prices.seed("2330", [])
    desk.prices.seed("2454", [])
    desk.index.seed("^TWII", bars("^TWII", 20000.0))

    run = desk.service.evaluate_today(today=TUESDAY)

    logged = {line.symbol: line for line in run.directives if line.rule_id == "R1"}
    assert set(logged) == {"2330", "2454"}
    for symbol, count in (("2330", 1), ("2454", 0)):
        a = wording.SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE.format(
            symbol=symbol, status="unavailable", line_count=1
        )
        assert (a in run.warnings) is bool(count)
    assert _entry_notes(run.warnings) == [_entry(logged["2330"])]
    assert _blocked_notes(run.warnings) == [_w_b6b(logged["2454"])]


# --- 測試 7(e): a line G1 refused in this run is not listed twice -------------------------


def test_a_line_g1_refused_in_this_settlement_is_not_repeated_in_w_b6b(desk: Desk) -> None:
    due = buy_line(data_date=MONDAY, execution_date=TUESDAY)  # opens Tuesday at 100
    later = buy_line(batch_no=2, data_date=MONDAY, execution_date=THURSDAY)
    log_like_before_n172a(desk.store, [due, later])
    hold(desk.store, "2330", 1)
    hold(desk.store, "2330", 2)

    run = desk.service.evaluate_today(today=TUESDAY)

    assert run.settlement is not None
    (refused,) = run.settlement.unsettled
    assert refused.refused_by_g1 and refused.directive.batch_no == 1
    assert refused.reason.startswith("2330第 1 批買進")  # SETTLEMENT_BATCH_ALREADY_FILLED_NOTE
    assert _blocked_notes(run.warnings) == [_w_b6b(later)]  # batch 2 only, count 1


def test_nothing_is_rendered_when_every_blocked_line_was_refused_now(desk: Desk) -> None:
    log_like_before_n172a(desk.store, [buy_line(data_date=MONDAY, execution_date=TUESDAY)])
    hold(desk.store, "2330", 1)

    run = desk.service.evaluate_today(today=TUESDAY)

    assert run.settlement is not None and [
        line.refused_by_g1 for line in run.settlement.unsettled
    ] == [True]
    assert _blocked_notes(run.warnings) == []


def test_a_blocked_line_without_an_opening_price_is_listed(desk: Desk) -> None:
    """Not refused -- its 預定執行日 has no bar, so no claim was tried -- so W-B6b
    lists it next to the neutral SETTLEMENT_NO_OPEN_PRICE."""
    saturday = date(2026, 8, 8)
    gap_bars = [bar for bar in bars("2330", 100.0) if bar.date != saturday]
    desk.prices.seed("2330", gap_bars)
    stuck = buy_line(data_date=FRIDAY_BEFORE, execution_date=saturday)
    log_like_before_n172a(desk.store, [stuck])
    hold(desk.store, "2330", 1)

    run = desk.service.evaluate_today(today=TUESDAY)

    assert run.settlement is not None
    (unsettled,) = run.settlement.unsettled
    assert not unsettled.refused_by_g1
    assert _blocked_notes(run.warnings) == [_w_b6b(stuck)]


# --- the population: K1, NULL batch_no, missing batch rows, ordering ----------------------


def test_duplicates_count_once_and_items_follow_date_symbol_batch(tmp_path: Path) -> None:
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2454"))
    lines = [
        buy_line(symbol="2454", batch_no=1, execution_date=THURSDAY),
        buy_line(symbol="2330", batch_no=2, execution_date=THURSDAY),
        buy_line(symbol="2454", batch_no=1, execution_date=WEDNESDAY),
        buy_line(symbol="2330", batch_no=2, execution_date=THURSDAY),  # pre-N-172a twin
    ]
    log_like_before_n172a(desk.store, lines)
    hold(desk.store, "2330", 2)
    hold(desk.store, "2454", 1)

    run = desk.service.evaluate_today(today=TUESDAY)

    assert _blocked_notes(run.warnings) == [_w_b6b(lines[2], lines[1], lines[0])]


@pytest.mark.parametrize("batch_no", [9, None], ids=["no-batch-row", "batch-no-null"])
def test_a_buy_with_no_batch_row_stays_out_of_w_b6b(desk: Desk, batch_no: int | None) -> None:
    for number in (1, 2, 3):
        hold(desk.store, "2330", number)
    log_like_before_n172a(desk.store, [buy_line(batch_no=batch_no, execution_date=THURSDAY)])

    run = desk.service.evaluate_today(today=TUESDAY)

    assert _blocked_notes(run.warnings) == []


def test_blocked_entries_keep_the_smallest_id_per_k1() -> None:
    line = buy_line()
    other = buy_line(batch_no=2)
    read = EntryBeforeExitRead(
        blocked=(
            PendingDirective(3, line),
            PendingDirective(5, line),
            PendingDirective(7, other),
        )
    )

    assert g1_blocked_entries(read) == [PendingDirective(3, line), PendingDirective(7, other)]


def test_w_b6b_does_not_fill_the_seam_lists(desk: Desk) -> None:
    """W-B6b is a sentence; ``entry_before_exit_blocked_directives`` is N-168's."""
    log_like_before_n172a(desk.store, [buy_line(execution_date=THURSDAY)])
    hold(desk.store, "2330", 1)

    run = desk.service.evaluate_today(today=TUESDAY)

    assert _blocked_notes(run.warnings)
    assert run.entry_before_exit_blocked_directives == []
    assert run.entry_before_exit_directives == []


# --- 測試 7(g) / P4: FROZEN_NOTE → ENTRY → W-B6b, every mode -------------------------------


def test_the_block_order_in_an_emergency_freeze(tmp_path: Path) -> None:
    """In the exit freeze, 2330's earlier R1 carries the exit's stamp and its batch
    is still planned, so it is W-B6's and not ENTRY's; 2454's (batch open) is
    W-B6b's. N-168 adjusted this per ADR-0035 補充四釐清六 E-23."""
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2454"))
    blocked = buy_line(symbol="2454")
    log_like_before_n172a(desk.store, [blocked])
    hold(desk.store, "2454", 1)

    first = desk.service.evaluate_today(today=TUESDAY)
    assert first.mode == "normal"
    assert first.warnings[0] == _w_b6b(blocked)  # 不限模式; no anchor → first
    assert _entry_notes(first.warnings) == []
    entry = next(line for line in first.directives if line.symbol == "2330")

    desk.service.emergency_exit(today=TUESDAY)
    second = desk.service.evaluate_today(today=TUESDAY)

    assert second.mode == "emergency_frozen"
    frozen = wording.FROZEN_NOTE.format(mode=wording.MODE_LABELS["emergency_frozen"])
    position = second.warnings.index(frozen)
    w_b6 = wording.PENDING_ENTRY_FROZEN_NOTE.format(entry_count=1, entry_items=_item(entry))
    assert second.warnings[position + 1 : position + 3] == [w_b6, _w_b6b(blocked)]
    assert _blocked_notes(second.warnings) == [w_b6, _w_b6b(blocked)]
    assert _entry_notes(second.warnings) == []


def _reconcile(
    evaluation: PlaybookEvaluation, logged: list[Directive], blocked: Directive
) -> list[str]:
    return same_day_warnings(
        evaluation,
        EvaluationCommit(written=[], logged=logged),
        markets={},
        batches=[],
        portfolio=helper.portfolio(),
        blocked=[PendingDirective(41, blocked)],
    )


@pytest.mark.parametrize(
    ("mode", "warnings", "at"),
    [
        ("emergency_frozen", ["x", "FROZEN", "y"], 2),
        ("emergency_frozen", ["x", "y"], 0),  # anchor missing: the block still comes first
        ("normal", ["x", "y"], 0),
    ],
    ids=["after-frozen", "anchor-missing", "normal"],
)
def test_the_block_is_placed_after_frozen_note_or_first(
    desk: Desk, mode: str, warnings: list[str], at: int
) -> None:
    frozen = wording.FROZEN_NOTE.format(mode=wording.MODE_LABELS["emergency_frozen"])
    rendered = [frozen if warning == "FROZEN" else warning for warning in warnings]
    evaluation = evaluation_of(desk.store, [], mode=mode, warnings=rendered)
    earlier = buy_line()
    blocked = buy_line(symbol="2454")

    result = _reconcile(evaluation, [earlier, blocked], blocked)

    assert result[at : at + 2] == [_entry(earlier), _w_b6b(blocked)]
    assert len(result) == len(rendered) + 2
    assert [warning for warning in result if warning in rendered] == rendered


def test_the_shares_are_listed_per_line(desk: Desk) -> None:
    """Shares are shown per line, never summed (風控 共用定義)."""
    first = buy_line(shares=100, execution_date=THURSDAY)
    second = buy_line(batch_no=2, shares=ONE_BUY_SHARES, execution_date=THURSDAY)
    log_like_before_n172a(desk.store, [first, second])
    hold(desk.store, "2330", 1)
    hold(desk.store, "2330", 2)

    run = desk.service.evaluate_today(today=TUESDAY)

    (note,) = _blocked_notes(run.warnings)
    assert note == _w_b6b(first, second)
    assert "買進 100 股" in note and f"買進 {ONE_BUY_SHARES} 股" in note


# --- 釐清一 E-2 第 5 點 (b): within one request K2 keeps the two snapshots equal --------


def _batch_statuses(store: PlaybookStore, symbol: str) -> dict[int, BatchStatus]:
    return {
        batch.batch_no: batch.status for batch in store.list_batches() if batch.symbol == symbol
    }


def _classified_from_the_database(
    store: PlaybookStore, execution_date: date
) -> tuple[list[Directive], list[Directive]]:
    """ENTRY's and W-B6b's lines, recomputed from the rows and batches alone.

    The 待成交買單 (``settled = 0 AND status = 'pending'``) whose batch row has
    left ``planned`` are W-B6b's, every 預定執行日, K1-deduplicated; the
    R-series ones of ``execution_date`` whose batch is still ``planned`` are
    ENTRY's. Read straight from the database, not through the service.
    """
    seen: set[tuple[str, int | None, str, str, str]] = set()
    entry: list[Directive] = []
    blocked: list[Directive] = []
    for item in store.pending_directives():
        line = item.directive
        if line.action != "buy" or decision_key(line) in seen:
            continue
        seen.add(decision_key(line))
        batch = None if line.batch_no is None else store.get_batch(line.symbol, line.batch_no)
        if batch is not None and batch.status != "planned":
            blocked.append(line)
        elif line.execution_date == execution_date and line.rule_id in R_SERIES_RULE_IDS:
            entry.append(line)
    entry.sort(key=lambda line: (line.symbol, line.batch_no or 0, line.execution_date))
    blocked.sort(key=lambda line: (line.execution_date, line.symbol, line.batch_no or 0))
    return entry, blocked


def test_an_r3_skip_behind_a_logged_r1_moves_no_batch_and_no_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The premise of the accepted two-snapshot limit (釐清一 E-2 第 2、5 點, 風控
    2026-11-04 第 11 點 (b)): only a concurrent settlement can move a batch
    between the in-flight read and the commit. Here 2330's batch 1 already has
    a logged R1 buy for Wednesday and has used up its deferrals, so the engine
    decides R3 skip (with ``batch_skipped``) for it; K2 writes no line for 2330,
    so the skip is not applied. 2454 has a blocked R1 buy, so both ENTRY and
    W-B6b are in play."""
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2454"))
    desk.service.evaluate_today(today=TUESDAY)  # logs R1 2330 #1 and 2454 #1 for Wednesday
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    limit = desk.store.active_params(TUESDAY).r3_max_defers
    desk.store.save_batch(batch.model_copy(update={"defer_count": limit}))
    hold(desk.store, "2454", 1)
    before = {symbol: _batch_statuses(desk.store, symbol) for symbol in ("2330", "2454")}
    engine_runs: list[PlaybookEvaluation] = []
    real_evaluate = engine_module.evaluate

    def spying(**kwargs: Any) -> PlaybookEvaluation:
        result = real_evaluate(**kwargs)
        engine_runs.append(result)
        return result

    monkeypatch.setattr(service_module, "evaluate", spying)

    run = desk.service.evaluate_today(today=TUESDAY)

    # The engine did decide the skip this time...
    (engine,) = engine_runs
    (skip,) = [line for line in engine.directives if line.symbol == "2330"]
    assert (skip.rule_id, skip.action, skip.batch_no) == ("R3", "skip", 1)
    assert ("batch_skipped", "2330", 1) in {
        (effect.kind, effect.symbol, effect.batch_no) for effect in engine.effects
    }
    assert not [
        line for line in engine.directives if line.action == "buy" and line.symbol == "2330"
    ]
    # ...and neither symbol's batches moved.
    after = {symbol: _batch_statuses(desk.store, symbol) for symbol in ("2330", "2454")}
    assert after == before
    assert before["2330"][1] == "planned"
    # The response classified exactly what the database classifies afterwards.
    entry, blocked = _classified_from_the_database(desk.store, run.execution_date)
    assert [(line.symbol, line.batch_no) for line in entry] == [("2330", 1)]
    assert [(line.symbol, line.batch_no) for line in blocked] == [("2454", 1)]
    assert _entry_notes(run.warnings) == [_entry(*entry)]
    assert _blocked_notes(run.warnings) == [_w_b6b(*blocked)]


# --- qa-reviewer 2026-11-04 跟進: A drops to zero while B does not ---------------------


def test_a_is_not_rendered_but_b_is_when_only_decisions_are_left(desk: Desk) -> None:
    """2330 is unusable now and its Wednesday list holds one blocked R1 buy and
    one R2 deferral (two R lines of one 預定執行日: a pre-N-172a log). Once the
    buy is excluded A counts 0 and is not rendered (風控 2026-11-01 P5); B still
    counts the deferral and follows the DATA_GAP sentence directly, the
    「只有 defer 或 skip 列」 case of 風控 2026-11-01 解讀點 (c). W-B6b names the buy."""
    blocked = buy_line()
    deferral = buy_line(batch_no=2).model_copy(
        update={"action": "defer", "shares": 0, "rule_id": "R2", "rule_summary": "R2 順延"}
    )
    log_like_before_n172a(desk.store, [blocked, deferral])
    hold(desk.store, "2330", 1)
    desk.prices.seed("2330", [])

    run = desk.service.evaluate_today(today=TUESDAY)

    assert run.execution_date == WEDNESDAY
    gap = wording.DATA_GAP_HOLDING_NOTE.format(symbol="2330", status="unavailable", source="none")
    b = wording.SAME_DAY_EARLIER_DECISIONS_DATA_GAP_NOTE.format(symbol="2330", decision_count=1)
    position = run.warnings.index(gap)
    assert run.warnings[position + 1] == b
    assert not [warning for warning in run.warnings if warning.startswith("2330 本次資料狀態為")]
    assert not [warning for warning in run.warnings if "筆買賣指令" in warning]
    assert _entry_notes(run.warnings) == []
    assert _blocked_notes(run.warnings) == [_w_b6b(blocked)]


# --- 風控 2026-11-04 第 8 點 (b)(c): authored modes only ---------------------------------


@pytest.fixture
def unauthored(tmp_path: Path) -> Desk:
    """No submitted rule set, but a held batch and a blocked buy in the log."""
    desk = open_desk(tmp_path / "playbook.db", seed=False)
    desk.store.ensure_batches(["2330"], batches_per_target=3)
    hold(desk.store, "2330", 1)
    log_like_before_n172a(desk.store, [buy_line(execution_date=THURSDAY)])
    assert not desk.store.rule_set_authorship(TUESDAY).user_authored
    assert desk.store.read_in_flight().entries.blocked  # W-B6b would have a line
    return desk


@pytest.fixture
def unauthored_client(unauthored: Desk) -> Iterator[TestClient]:
    app.dependency_overrides[get_playbook_service] = lambda: unauthored.service
    app.dependency_overrides[get_cap1_reading] = lambda: Cap1Reading(
        weight=Decimal("0.10"), from_default=False
    )
    with TestClient(app, headers=CLIENT_HEADERS) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_the_unauthored_path_neither_computes_nor_renders_w_b6b(
    unauthored: Desk, unauthored_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``mode="unconfirmed"`` is outside 「不限模式」 (風控 2026-11-04 第 8 點): no
    settlement, no G1 refusal, no ENTRY／A to correct."""
    calls: list[str] = []

    def refuse(name: str) -> Any:
        def called(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            raise AssertionError(name)

        return called

    monkeypatch.setattr(service_module, "g1_blocked_entries", refuse("g1_blocked_entries"))
    monkeypatch.setattr(service_module, "same_day_warnings", refuse("same_day_warnings"))

    run = unauthored.service.evaluate_today(today=TUESDAY)
    response = unauthored_client.get("/api/playbook/today")

    assert run.mode == "unconfirmed"
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "unconfirmed"
    fragment = "帳冊不會依這幾筆判定成交"
    for warnings in (run.warnings, body["warnings"]):
        assert _blocked_notes(warnings) == []
        assert not [warning for warning in warnings if fragment in warning]
    assert fragment not in response.text
    assert calls == []


@pytest.mark.parametrize("today", [TUESDAY, WEDNESDAY], ids=["schedule-day", "not-schedule-day"])
def test_w_b6b_is_rendered_in_normal_mode(desk: Desk, today: date) -> None:
    """Authored and not frozen: W-B6b is rendered, first (no FROZEN_NOTE)."""
    stuck = buy_line(execution_date=THURSDAY)
    log_like_before_n172a(desk.store, [stuck])
    hold(desk.store, "2330", 1)

    run = desk.service.evaluate_today(today=today)

    assert run.mode == "normal"
    assert desk.store.rule_set_authorship(today).user_authored
    frozen = wording.FROZEN_NOTE.format(mode=wording.MODE_LABELS["normal"])
    assert frozen not in run.warnings
    assert _blocked_notes(run.warnings) == [_w_b6b(stuck)]
    assert run.warnings[0] == _w_b6b(stuck)


# --- 風控 2026-11-04 第 10 點: R-series only, the item order, one item template ----------


def test_every_buy_the_app_writes_is_an_r_series_line(tmp_path: Path) -> None:
    """W-B6b says 「R 系列買進指令」 without filtering on ``rule_id`` (解讀點 9).
    That holds only while every buy the app constructs is an R-series one: no
    call in ``app/`` passes ``action="buy"`` without an R-series ``rule_id``,
    and no update dict sets ``"action": "buy"``. A new buy source turns this
    red, and W-B6b and ENTRY go back to 風控."""
    app_root = Path(wording.__file__).resolve().parents[1]
    sites: list[str] = []
    for path in sorted(app_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                pairs = zip(node.keys, node.values, strict=True)
                assert not [
                    key
                    for key, value in pairs
                    if isinstance(key, ast.Constant)
                    and key.value == "action"
                    and isinstance(value, ast.Constant)
                    and value.value == "buy"
                ], path
            if not isinstance(node, ast.Call):
                continue
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            action = keywords.get("action")
            if not (isinstance(action, ast.Constant) and action.value == "buy"):
                continue
            rule_id = keywords.get("rule_id")
            assert isinstance(rule_id, ast.Constant), f"{path}:{node.lineno}"
            assert rule_id.value in R_SERIES_RULE_IDS, f"{path}:{node.lineno}"
            sites.append(f"{path.relative_to(app_root).as_posix()}:{rule_id.value}")
    assert sites == ["playbook/engine.py:R1"]

    # And at run time: the engine's own buy, blocked, is what W-B6b counts.
    desk = open_desk(tmp_path / "playbook.db")
    desk.service.evaluate_today(today=TUESDAY)
    hold(desk.store, "2330", 1)
    run = desk.service.evaluate_today(today=TUESDAY)
    lines = [item.directive for item in g1_blocked_entries(desk.store.read_in_flight().entries)]
    assert lines and all(line.rule_id in R_SERIES_RULE_IDS for line in lines)
    assert _blocked_notes(run.warnings) == [_w_b6b(*lines)]


def test_the_items_are_ordered_by_date_then_symbol_then_batch(desk: Desk) -> None:
    """``{entry_items}`` ascends by (預定執行日, symbol, batch_no) whatever the read
    order (風控 2026-11-01 共用定義, 2026-11-04 第 10 點). The lines are chosen
    so each key decides over the next one: an earlier date wins over a larger
    symbol, a smaller symbol over a smaller batch_no, and batch 2 sorts before
    batch 10 (a number, not a string)."""
    lines = [
        buy_line(symbol="2454", batch_no=1, execution_date=WEDNESDAY),
        buy_line(symbol="2330", batch_no=2, execution_date=THURSDAY),
        buy_line(symbol="2330", batch_no=10, execution_date=THURSDAY),
        buy_line(symbol="2454", batch_no=1, execution_date=THURSDAY),
    ]
    expected = sorted(lines, key=lambda line: (line.execution_date, line.symbol, line.batch_no))
    assert expected == lines
    evaluation = evaluation_of(desk.store, [])
    for order in itertools.permutations(range(len(lines))):
        warnings = same_day_warnings(
            evaluation,
            EvaluationCommit(written=[], logged=[]),
            markets={},
            batches=[],
            portfolio=helper.portfolio(),
            blocked=[PendingDirective(index + 1, lines[index]) for index in order],
        )
        assert _blocked_notes(warnings) == [_w_b6b(*expected)], order


def test_the_item_template_exists_once(desk: Desk) -> None:
    """ENTRY and W-B6b share :data:`wording.SAME_DAY_EARLIER_ENTRY_ITEM` (解讀點 10):
    no second constant holds it, no other module spells it, and the service
    formats it in one place that both sentences go through."""
    item = wording.SAME_DAY_EARLIER_ENTRY_ITEM
    assert [name for name, value in vars(wording).items() if value == item] == [
        "SAME_DAY_EARLIER_ENTRY_ITEM"
    ]
    app_root = Path(wording.__file__).resolve().parents[1]
    spelled = [
        path.relative_to(app_root).as_posix()
        for path in sorted(app_root.rglob("*.py"))
        if path.name != "wording.py" and "批買進 {shares} 股" in path.read_text(encoding="utf-8")
    ]
    assert spelled == []
    tree = ast.parse(Path(service_module.__file__).read_text(encoding="utf-8"))
    users = [
        function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        and any(
            isinstance(node, ast.Attribute) and node.attr == "SAME_DAY_EARLIER_ENTRY_ITEM"
            for node in ast.walk(function)
        )
    ]
    assert users == ["_entry_item"]
    (reconcile,) = [
        function
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef) and function.name == "same_day_warnings"
    ]
    called = [
        node.func.id
        for node in ast.walk(reconcile)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert called.count("_entry_item") == 2  # ENTRY, W-B6b
    # Rendered, the two sentences carry the same item text for the same line.
    line = buy_line()
    rendered = _item(line)
    assert rendered in _entry(line) and rendered in _w_b6b(line)
