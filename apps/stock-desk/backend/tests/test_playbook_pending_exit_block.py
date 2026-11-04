"""N-171 群組 A: ``/today``'s pending-exit block (ADR-0039 v2 ＋ 補充一).

Test map (ADR-0039 附錄 B ＋ 補充一 S-8; 風控 2026-11-03 第四節 (a)～(j), 2026-11-04 (k)～(m)):

* T1～T10 -- (a)～(j): ``test_a_*`` … ``test_j_*``.
* T11 refresh／second tab, T12 mode and freeze, T13 no buy, T14 zero writes and
  zero extra loads, T15 classification follows the settlement's own series,
  T19／T26 closed batches, T20 repeats, T21 warnings untouched, T25 A-15 on all
  three kinds, T17′ A-6 predicate (a)～(d).
* SEAM ``filled`` (補充四釐清二 E-9 第 2 點): ``test_seam_filled_*`` on the golden
  scenarios themselves, exact values.

Wording is asserted through the constants; their text is pinned verbatim in
``tests/test_playbook_pending_exit_wording.py``.
"""

from __future__ import annotations

import ast
import inspect
import itertools
import json
import random
import sqlite3
import tempfile
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import playbook as api_module
from app.api.deps import get_cap1_reading, get_playbook_service
from app.api.playbook_cap1_wording import Cap1Reading
from app.data.interface import Market, ProviderResult
from app.main import app
from app.playbook import service as service_module
from app.playbook import wording
from app.playbook.models import Directive, PendingExitBlock, PlaybookEvaluation
from app.playbook.service import (
    PlaybookService,
    exit_row_past_due,
    exit_row_shares_reduced,
)
from app.playbook.store import (
    STATE_EMERGENCY_UNTIL,
    EmergencyExitState,
    PendingExitRead,
)
from tests.api_helpers import CLIENT_HEADERS, FakePriceService, recent_bars
from tests.exit_idempotency_helpers import (
    FRIDAY,
    HISTORY,
    SERIES_END,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Book,
    already_pending_message,
    gapped_bars,
    hold,
    legacy_exit_line,
    log_like_before_n166,
    open_book,
    until_for,
)
from tests.playbook_helpers import confirm_rule_set
from tests.same_day_helpers import buy_line, log_like_before_n172a
from tests.same_day_helpers import hold as hold_open
from tests.seam_helpers import SCENARIOS, clocked_desk

APP_ROOT = Path(api_module.__file__).resolve().parents[1]
MONDAY_NEXT = date(2026, 8, 17)

COVERED_ONLY = {
    wording.PENDING_EXIT_STALE_LABEL,
    wording.PENDING_EXIT_STALE_LEAD,
    wording.PENDING_EXIT_COVERED_LABEL,
}


# --- builders -------------------------------------------------------------------------------


def _exit(symbol: str, batch_no: int, execution: date, shares: int = 300) -> Directive:
    return legacy_exit_line(symbol, shares, execution_date=execution).model_copy(
        update={"batch_no": batch_no}
    )


def _authored(db_path: Path, **kwargs: Any) -> Book:
    book = open_book(db_path, **kwargs)
    confirm_rule_set(book.store)
    return book


def _block(evaluation: PlaybookEvaluation) -> PendingExitBlock:
    assert evaluation.pending_exit_block is not None
    return evaluation.pending_exit_block


def _texts(block: PendingExitBlock) -> list[str]:
    """Every sentence of the block in the order the client renders it."""
    out = [block.title, block.lead_template]
    for section in block.sections:
        if section.label is not None:
            out.append(section.label)
        out.append(section.lead)
        for row in section.rows:
            out.extend([row.text, *row.notes])
    return [*out, *block.closing_notes]


def _rows(block: PendingExitBlock) -> list[tuple[str, str, int, int, list[str]]]:
    return [
        (
            section.kind,
            row.symbol,
            row.batch_no,
            row.shares,
            [d.isoformat() for d in row.execution_dates],
        )
        for section in block.sections
        for row in section.rows
    ]


def _today_body(book: Book, today: date) -> dict[str, Any]:
    """``GET /api/playbook/today`` on ``book``'s database, pinned to ``today``."""

    class _Clocked(PlaybookService):
        def evaluate_today(self, *, today: date | None = None) -> PlaybookEvaluation:
            return super().evaluate_today(today=today or day)

    day = today
    service = _Clocked(
        store=book.store,
        market_resolver={"TW": book.prices},
        index_resolver={"TW": book.index, "US": book.index},
    )
    app.dependency_overrides[get_playbook_service] = lambda: service
    app.dependency_overrides[get_cap1_reading] = lambda: Cap1Reading(
        weight=Decimal("0.10"), from_default=False
    )
    try:
        with TestClient(app, headers=CLIENT_HEADERS) as client:
            body: dict[str, Any] = client.get("/api/playbook/today").json()
    finally:
        app.dependency_overrides.clear()
    return body


@pytest.fixture
def traced(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    statements: list[str] = []
    real_connect = sqlite3.connect

    def tracing(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracing)
    return statements


WRITES = ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER")


# --- SEAM filled (釐清二 E-9 第 2 點): exact values on the golden scenarios ---------------


@pytest.fixture(scope="module")
def golden_bodies() -> dict[str, dict[str, Any]]:
    work = Path(tempfile.mkdtemp())
    return {name: run(work / f"{name}.db") for name, run in SCENARIOS.items()}


def test_seam_filled_pending_exit_directives_on_the_golden_scenarios(
    golden_bodies: dict[str, dict[str, Any]],
) -> None:
    """``after_exit.today``: batches 2 and 3; ``unauthored.today_after_exit``: batch 1; else []."""
    after = golden_bodies["after_exit"]
    unauthored = golden_bodies["unauthored"]
    # Exactly the lines the first exit wrote, as DirectiveLines, null note.
    assert after["today"]["pending_exit_directives"] == after["exit"]["directives"]
    assert (
        unauthored["today_after_exit"]["pending_exit_directives"]
        == unauthored["exit"]["directives"]
    )
    picked = [
        (
            line["directive"]["symbol"],
            line["directive"]["batch_no"],
            line["directive"]["shares"],
            line["directive"]["execution_date"],
            line["directive"]["rule_id"],
            line["directive"]["action"],
            line["entry_before_exit_note"],
        )
        for line in after["today"]["pending_exit_directives"]
    ]
    assert picked == [
        ("2330", 2, 300, "2026-08-12", "EMERGENCY", "sell", None),
        ("2330", 3, 300, "2026-08-12", "EMERGENCY", "sell", None),
    ]
    unauthored_picked = [
        (line["directive"]["symbol"], line["directive"]["batch_no"], line["directive"]["shares"])
        for line in unauthored["today_after_exit"]["pending_exit_directives"]
    ]
    assert unauthored_picked == [("2330", 1, 300)]
    filled = {("after_exit", "today"), ("unauthored", "today_after_exit")}
    for scenario, bodies in golden_bodies.items():
        for name, body in bodies.items():
            if name.startswith("today") and (scenario, name) not in filled:
                assert body["pending_exit_directives"] == [], (scenario, name)
                assert body["pending_exit_block"] is None, (scenario, name)


def test_seam_filled_pending_exit_block_on_the_golden_scenarios(
    golden_bodies: dict[str, dict[str, Any]],
) -> None:
    after = golden_bodies["after_exit"]["today"]["pending_exit_block"]
    assert after["title"] == wording.PENDING_EXIT_BLOCK_TITLE
    assert after["lead_template"] == wording.PENDING_EXIT_BLOCK_LEAD
    assert after["closing_notes"] == [wording.PENDING_EXIT_RECEIPT_OVERLAP_NOTE]
    (section,) = after["sections"]
    assert (section["kind"], section["label"], section["lead"]) == (
        "covering",
        None,
        wording.PENDING_EXIT_COVERED_LEAD,
    )
    assert section["rows"] == [
        {
            "symbol": "2330",
            "batch_no": batch_no,
            "shares": 300,
            "coverage": "covering",
            "batch_has_covering": True,
            "execution_dates": ["2026-08-12"],
            "text": wording.PENDING_EXIT_ITEM.format(
                symbol="2330", batch_no=batch_no, shares=300, execution_dates="2026-08-12"
            ),
            "notes": [],
            "entry_before_exit_note": None,
        }
        for batch_no in (2, 3)
    ]
    unauthored = golden_bodies["unauthored"]["today_after_exit"]["pending_exit_block"]
    assert unauthored["closing_notes"] == [
        wording.PENDING_EXIT_UNAUTHORED_NOTE,
        wording.PENDING_EXIT_RECEIPT_OVERLAP_NOTE,
    ]
    (section,) = unauthored["sections"]
    assert (section["kind"], section["label"], section["lead"]) == (
        "unclassified",
        None,
        wording.PENDING_EXIT_UNCLASSIFIED_LEAD,
    )
    assert [(row["batch_no"], row["batch_has_covering"]) for row in section["rows"]] == [(1, None)]


def test_seam_filled_in_flight_exits_on_the_golden_scenario(tmp_path: Path) -> None:
    """``read_in_flight().exits`` after the ``after_exit`` scenario's exit, field by field."""
    desk = clocked_desk(tmp_path / "playbook.db")
    hold_open(desk.store, "2330", 2)
    hold_open(desk.store, "2330", 3)
    log_like_before_n172a(desk.store, [buy_line(execution_date=WEDNESDAY)])
    desk.service.emergency_exit(today=TUESDAY)

    read = desk.store.read_in_flight()

    assert isinstance(read.exits, PendingExitRead)
    state = read.exits.state
    assert isinstance(state, EmergencyExitState)
    assert state.open_batches == [desk.store.get_batch("2330", 2), desk.store.get_batch("2330", 3)]
    emergency = [
        item
        for item in desk.store.pending_directives()
        if item.directive.rule_id == "EMERGENCY" and item.directive.action == "sell"
    ]
    assert state.covering == emergency
    assert [(item.directive.batch_no, item.directive.execution_date) for item in emergency] == [
        (2, WEDNESDAY),
        (3, WEDNESDAY),
    ]
    assert (
        state.emergency_until == desk.store.portfolio_state().emergency_until == until_for(TUESDAY)
    )


# --- (a)～(c): the three shapes of the authored block -------------------------------------


def test_a_only_covering_rows(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    hold(book.store, "2454", 1, shares=200)
    book.service.emergency_exit(today=TUESDAY)

    block = _block(book.service.evaluate_today(today=TUESDAY))

    assert _rows(block) == [
        ("covering", "2330", 1, 300, ["2026-08-12"]),
        ("covering", "2454", 1, 200, ["2026-08-12"]),
    ]
    (section,) = block.sections
    assert section.label is None and section.lead == wording.PENDING_EXIT_COVERED_LEAD
    assert block.closing_notes == [wording.PENDING_EXIT_RECEIPT_OVERLAP_NOTE]
    assert not COVERED_ONLY & set(_texts(block))
    assert all(row.batch_has_covering is True and row.notes == [] for row in section.rows)


def _stale_book(db_path: Path) -> Book:
    """WEDNESDAY has no bar for 2330 while THURSDAY does: a WEDNESDAY exit line is stale."""
    prices = FakePriceService()
    prices.seed("2330", gapped_bars("2330", 100.0, missing={WEDNESDAY}))
    prices.seed("2454", recent_bars([50.0] * HISTORY, symbol="2454", end=SERIES_END))
    return _authored(db_path, prices=prices)


def test_b_a_batch_with_a_covering_and_a_stale_line_gets_a11(tmp_path: Path) -> None:
    book = _stale_book(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    log_like_before_n166(
        book.store, [_exit("2330", 1, WEDNESDAY), _exit("2330", 1, FRIDAY + timedelta(days=3))]
    )

    evaluation = book.service.evaluate_today(today=THURSDAY)
    block = _block(evaluation)

    covering, stale = block.sections
    assert (covering.kind, covering.label, covering.lead) == (
        "covering",
        wording.PENDING_EXIT_COVERED_LABEL,
        wording.PENDING_EXIT_COVERED_LEAD,
    )
    assert (stale.kind, stale.label, stale.lead) == (
        "stale",
        wording.PENDING_EXIT_STALE_LABEL,
        wording.PENDING_EXIT_STALE_LEAD,
    )
    (row,) = stale.rows
    assert row.text == wording.EMERGENCY_EXIT_STALE_ITEM.format(
        symbol="2330", batch_no=1, shares=300, stale_dates="2026-08-12"
    )
    assert row.notes == [wording.PENDING_EXIT_STALE_ALSO_COVERED_NOTE]
    assert row.batch_has_covering is True
    assert [d.isoformat() for d in covering.rows[0].execution_dates] == ["2026-08-17"]
    # The stale row is the very line the same response's settlement gives N1 (P-1).
    assert evaluation.settlement is not None
    (unsettled,) = evaluation.settlement.unsettled
    assert unsettled.directive.execution_date == WEDNESDAY
    assert wording.SETTLEMENT_EXIT_STALE_NOTE.split("{")[0] in unsettled.reason
    # Fixed order: A-1 → A-2 → A-7 → A-3 → rows → A-8 → A-9 → rows → A-14.
    texts = _texts(block)
    order = [
        wording.PENDING_EXIT_BLOCK_TITLE,
        wording.PENDING_EXIT_BLOCK_LEAD,
        wording.PENDING_EXIT_COVERED_LABEL,
        wording.PENDING_EXIT_COVERED_LEAD,
        wording.PENDING_EXIT_STALE_LABEL,
        wording.PENDING_EXIT_STALE_LEAD,
        wording.PENDING_EXIT_RECEIPT_OVERLAP_NOTE,
    ]
    assert [text for text in texts if text in order] == order
    assert texts[-1] == wording.PENDING_EXIT_RECEIPT_OVERLAP_NOTE


def test_c_only_stale_lines_get_a12_and_no_covering_section(tmp_path: Path) -> None:
    book = _stale_book(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY)])

    block = _block(book.service.evaluate_today(today=THURSDAY))

    (section,) = block.sections
    assert section.kind == "stale" and section.label == wording.PENDING_EXIT_STALE_LABEL
    (row,) = section.rows
    assert row.notes == [wording.PENDING_EXIT_STALE_UNCOVERED_NOTE]
    assert row.batch_has_covering is False
    texts = set(_texts(block))
    assert wording.PENDING_EXIT_COVERED_LEAD not in texts
    assert wording.PENDING_EXIT_COVERED_LABEL not in texts
    # A-6 is never on a stale row, past due or not.
    assert not any(note.startswith("預定執行日") for note in row.notes)


# --- (d)～(f): rows, dates, degradation -----------------------------------------------------


def test_d_two_lines_of_one_batch_are_one_row_with_both_dates(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    log_like_before_n166(book.store, [_exit("2330", 1, THURSDAY), _exit("2330", 1, WEDNESDAY)])

    evaluation = book.service.evaluate_today(today=TUESDAY)
    block = _block(evaluation)

    assert _rows(block) == [("covering", "2330", 1, 300, ["2026-08-12", "2026-08-13"])]
    (row,) = block.sections[0].rows
    assert row.text == wording.PENDING_EXIT_ITEM.format(
        symbol="2330", batch_no=1, shares=300, execution_dates="2026-08-12、2026-08-13"
    )
    # The raw data keeps both lines, by symbol, batch_no, date, id.
    assert [line.execution_date for line in evaluation.pending_exit_directives] == [
        WEDNESDAY,
        THURSDAY,
    ]


def _capped_book(db_path: Path, last: date) -> Book:
    prices = FakePriceService()
    prices.seed(
        "2330", [bar for bar in recent_bars([100.0] * HISTORY, end=SERIES_END) if bar.date <= last]
    )
    return _authored(db_path, prices=prices)


def test_e_only_the_past_due_date_is_named_in_a6(tmp_path: Path) -> None:
    """Data lags at TUESDAY: both lines still cover; only WEDNESDAY is before THURSDAY."""
    book = _capped_book(tmp_path / "playbook.db", TUESDAY)
    hold(book.store, "2330", 1, shares=300)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY), _exit("2330", 1, THURSDAY)])

    block = _block(book.service.evaluate_today(today=THURSDAY))

    (row,) = block.sections[0].rows
    assert row.coverage == "covering"
    assert row.notes == [wording.PENDING_EXIT_PAST_DUE_NOTE.format(past_due_dates="2026-08-12")]


def test_f_a_failed_load_keeps_every_row_covering(tmp_path: Path) -> None:
    prices = FakePriceService()  # nothing seeded: every load comes back empty
    book = _authored(tmp_path / "playbook.db", prices=prices)
    hold(book.store, "2330", 1, shares=300)
    hold(book.store, "2454", 1, shares=200)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY), _exit("2454", 1, THURSDAY)])

    block = _block(book.service.evaluate_today(today=THURSDAY))

    assert [(kind, symbol) for kind, symbol, *_ in _rows(block)] == [
        ("covering", "2330"),
        ("covering", "2454"),
    ]
    assert len(block.sections) == 1


# --- (g): unauthored ----------------------------------------------------------------------


def test_g_unauthored_lists_every_line_unclassified_with_a4_and_a13(tmp_path: Path) -> None:
    prices = FakePriceService()
    prices.seed("2330", gapped_bars("2330", 100.0, missing={WEDNESDAY}))
    book = open_book(tmp_path / "playbook.db", prices=prices)
    hold(book.store, "2330", 1, shares=300)
    hold(book.store, "2330", 2, shares=300)
    log_like_before_n166(
        book.store,
        [_exit("2330", 1, WEDNESDAY), _exit("2330", 1, FRIDAY), _exit("2330", 2, FRIDAY)],
    )

    evaluation = book.service.evaluate_today(today=THURSDAY)
    block = _block(evaluation)

    assert evaluation.mode == "unconfirmed" and evaluation.settlement is None
    assert _rows(block) == [
        ("unclassified", "2330", 1, 300, ["2026-08-12", "2026-08-14"]),
        ("unclassified", "2330", 2, 300, ["2026-08-14"]),
    ]
    (section,) = block.sections
    assert section.label is None and section.lead == wording.PENDING_EXIT_UNCLASSIFIED_LEAD
    assert all(row.batch_has_covering is None for row in section.rows)
    assert block.closing_notes == [
        wording.PENDING_EXIT_UNAUTHORED_NOTE,
        wording.PENDING_EXIT_RECEIPT_OVERLAP_NOTE,
    ]
    texts = set(_texts(block))
    for absent in (
        wording.PENDING_EXIT_COVERED_LEAD,
        *COVERED_ONLY,
        wording.PENDING_EXIT_STALE_ALSO_COVERED_NOTE,
        wording.PENDING_EXIT_STALE_UNCOVERED_NOTE,
    ):
        assert absent not in texts
    assert not any(text.startswith("{symbol}第 {batch_no} 批 {shares} 股（未能") for text in texts)
    assert book.prices.calls == [] and book.index.calls == []


# --- (h): settled in the same call ----------------------------------------------------------


def test_h_a_line_settled_by_this_call_is_in_settlement_not_in_the_block(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    hold(book.store, "2454", 1, shares=200)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY), _exit("2454", 1, FRIDAY)])

    evaluation = book.service.evaluate_today(today=WEDNESDAY)

    assert evaluation.settlement is not None
    assert [
        (line.directive.symbol, line.directive.status) for line in evaluation.settlement.settled
    ] == [("2330", "executed")]
    assert _rows(_block(evaluation)) == [("covering", "2454", 1, 200, ["2026-08-14"])]
    assert [line.symbol for line in evaluation.pending_exit_directives] == ["2454"]


def test_c14_no_row_no_block(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)

    evaluation = book.service.evaluate_today(today=TUESDAY)

    assert evaluation.pending_exit_block is None and evaluation.pending_exit_directives == []
    body = _today_body(book, TUESDAY)
    assert body["pending_exit_block"] is None
    dumped = json.dumps(body, ensure_ascii=False)
    assert wording.PENDING_EXIT_BLOCK_TITLE not in dumped


# --- (j): the block's shares are S1's {pending_shares} ------------------------------------


def test_j_block_shares_equal_s1_pending_shares_on_an_immediate_repeat(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    hold(book.store, "2454", 1, shares=200)
    book.service.emergency_exit(today=TUESDAY)
    block = _block(book.service.evaluate_today(today=TUESDAY))

    repeat = book.service.emergency_exit(today=TUESDAY)

    rows = [row for section in block.sections for row in section.rows]
    assert repeat.message == already_pending_message(
        batches=len(rows),
        shares=sum(row.shares for row in rows),
        execution_dates="2026-08-12",
        executed_at=TUESDAY,
        until=until_for(TUESDAY),
    )


# --- T11, T12, T13 ------------------------------------------------------------------------


def test_t11_the_same_database_reads_the_same_block_from_a_fresh_service(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    book.service.emergency_exit(today=TUESDAY)

    first = book.service.evaluate_today(today=TUESDAY)
    other = open_book(tmp_path / "playbook.db")  # a second tab / a reload: new objects
    second = other.service.evaluate_today(today=TUESDAY)

    assert first.pending_exit_block == second.pending_exit_block is not None
    assert first.pending_exit_directives == second.pending_exit_directives


def test_t12_mode_and_freeze_date_do_not_change_the_block(tmp_path: Path) -> None:
    book = _capped_book(tmp_path / "playbook.db", TUESDAY)
    hold(book.store, "2330", 1, shares=300)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY)])

    blocks = []
    modes = []
    for until in (None, date(2026, 8, 1), date(2026, 9, 30)):
        book.store._set_state({STATE_EMERGENCY_UNTIL: None if until is None else until.isoformat()})
        evaluation = book.service.evaluate_today(today=THURSDAY)
        blocks.append(evaluation.pending_exit_block)
        modes.append(evaluation.mode)
    assert "emergency_frozen" in modes and "normal" in modes
    assert blocks[0] is not None and blocks[0] == blocks[1] == blocks[2]


def test_t13_a_pending_r1_buy_is_not_in_the_block(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 2, shares=300)
    log_like_before_n172a(book.store, [buy_line(execution_date=WEDNESDAY)])
    book.service.emergency_exit(today=TUESDAY)

    evaluation = book.service.evaluate_today(today=TUESDAY)

    assert [(line.rule_id, line.action) for line in evaluation.pending_exit_directives] == [
        ("EMERGENCY", "sell")
    ]
    assert [row.batch_no for section in _block(evaluation).sections for row in section.rows] == [2]
    assert any(line.action == "buy" for line in evaluation.directives)
    # Decision 14: the ledger never carries an EMERGENCY line.
    assert all(line.rule_id != "EMERGENCY" for line in evaluation.directives)


def test_decision_14_the_ledger_has_no_exit_line_end_to_end(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    book.service.emergency_exit(today=TUESDAY)

    body = _today_body(book, TUESDAY)

    assert body["pending_exit_directives"]
    assert all(line["directive"]["rule_id"] != "EMERGENCY" for line in body["directives"])
    for line in body["pending_exit_directives"]:
        assert line not in body["directives"]


# --- T14: zero writes and no extra load ---------------------------------------------------


def test_t14_the_n171_part_reads_nothing_more_loads_nothing_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, traced: list[str]
) -> None:
    book = _stale_book(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY), _exit("2330", 1, MONDAY_NEXT)])
    seen: list[tuple[int, int, int]] = []
    real = service_module._pending_exit_lines

    def spied(*args: Any, **kwargs: Any) -> service_module.PendingExitView:
        before = (len(traced), len(book.prices.calls), len(book.index.calls))
        view = real(*args, **kwargs)
        seen.append(
            (
                len(traced) - before[0],
                len(book.prices.calls) - before[1],
                len(book.index.calls) - before[2],
            )
        )
        return view

    monkeypatch.setattr(service_module, "_pending_exit_lines", spied)
    evaluation = book.service.evaluate_today(today=THURSDAY)

    assert evaluation.pending_exit_block is not None
    assert seen == [(0, 0, 0)]  # no statement, no load inside N-171's composition

    # And the whole /today loads exactly what it loaded with the block stubbed out.
    calls_with = list(book.prices.calls)
    twin = _stale_book(tmp_path / "twin.db")
    hold(twin.store, "2330", 1, shares=300)
    log_like_before_n166(twin.store, [_exit("2330", 1, WEDNESDAY), _exit("2330", 1, MONDAY_NEXT)])
    monkeypatch.setattr(
        service_module,
        "_pending_exit_lines",
        lambda *args, **kwargs: service_module.PendingExitView(directives=[], block=None),
    )
    twin.service.evaluate_today(today=THURSDAY)
    assert twin.prices.calls == calls_with


def test_c9_the_in_flight_read_is_select_only_with_rows_in_it(
    tmp_path: Path, traced: list[str]
) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    book.service.emergency_exit(today=TUESDAY)
    traced.clear()

    read = book.store.read_in_flight()

    assert read.exits.state.covering
    assert traced[0] == "BEGIN" and traced[-1] == "COMMIT"
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in traced[1:-1])


# --- T15: the settlement's series, not the second load ------------------------------------


class _ShiftingPrices(FakePriceService):
    """First answer per symbol: WEDNESDAY missing; every later answer: the full series."""

    def __init__(self) -> None:
        super().__init__()
        self.full = recent_bars([100.0] * HISTORY, symbol="2330", end=SERIES_END)
        self.seed("2330", gapped_bars("2330", 100.0, missing={WEDNESDAY}))
        self.answered: set[str] = set()

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        result = super().get_daily_bars(symbol, market, start, end)
        if symbol not in self.answered:
            self.answered.add(symbol)
            self.seed(symbol, self.full)
        return result


def test_t15_classification_follows_the_series_the_settlement_judged_n1_on(
    tmp_path: Path,
) -> None:
    prices = _ShiftingPrices()
    book = _authored(tmp_path / "playbook.db", prices=prices)
    hold(book.store, "2330", 1, shares=300)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY)])

    evaluation = book.service.evaluate_today(today=THURSDAY)

    # The evaluation's own load saw WEDNESDAY's bar; the settlement's did not.
    assert len(prices.calls) >= 2
    assert evaluation.settlement is not None
    (unsettled,) = evaluation.settlement.unsettled
    assert wording.SETTLEMENT_EXIT_STALE_REOPEN_NOTE in unsettled.reason  # N1b
    assert [section.kind for section in _block(evaluation).sections] == ["stale"]


# --- T19／T26 (風控 (l)): closed batches ---------------------------------------------------


def test_t26_a_closed_batchs_unsettled_line_is_not_in_the_block(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    hold(book.store, "2454", 1, shares=200)
    log_like_before_n166(book.store, [_exit("2330", 1, FRIDAY), _exit("2454", 1, FRIDAY)])
    closed = book.store.get_batch("2330", 1)
    assert closed is not None
    book.store.save_batch(closed.model_copy(update={"status": "closed", "remaining_shares": 0}))

    evaluation = book.service.evaluate_today(today=TUESDAY)
    block = _block(evaluation)

    assert _rows(block) == [("covering", "2454", 1, 200, ["2026-08-14"])]
    assert [line.symbol for line in evaluation.pending_exit_directives] == ["2454"]
    assert block.lead_template == wording.PENDING_EXIT_BLOCK_LEAD


def test_t19_an_open_batch_with_nothing_held_is_not_in_the_block(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300, remaining=0)
    log_like_before_n166(book.store, [_exit("2330", 1, FRIDAY)])

    evaluation = book.service.evaluate_today(today=TUESDAY)

    assert evaluation.pending_exit_block is None and evaluation.pending_exit_directives == []


def test_unauthored_closed_batch_is_not_in_the_block_either(tmp_path: Path) -> None:
    book = open_book(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300, remaining=0)
    hold(book.store, "2454", 1, shares=200)
    log_like_before_n166(book.store, [_exit("2330", 1, FRIDAY), _exit("2454", 1, FRIDAY)])

    block = _block(book.service.evaluate_today(today=TUESDAY))

    assert [symbol for _, symbol, *_ in _rows(block)] == ["2454"]


# --- T20: repeats ---------------------------------------------------------------------------


def test_t20_already_pending_and_next_day_repeats_leave_the_block_unchanged(
    tmp_path: Path,
) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    hold(book.store, "2454", 1, shares=200)
    book.service.emergency_exit(today=TUESDAY)
    before = _block(book.service.evaluate_today(today=TUESDAY))

    book.service.emergency_exit(today=TUESDAY)  # ALREADY_PENDING
    same_day = _block(book.service.evaluate_today(today=TUESDAY))

    assert same_day == before
    assert _rows(before) == [
        ("covering", "2330", 1, 300, ["2026-08-12"]),
        ("covering", "2454", 1, 200, ["2026-08-12"]),
    ]


def test_t20_a_new_batch_after_an_exit_is_a_second_row(tmp_path: Path) -> None:
    book = _capped_book(tmp_path / "playbook.db", TUESDAY)
    hold(book.store, "2330", 1, shares=300)
    book.service.emergency_exit(today=TUESDAY)
    hold(book.store, "2330", 2, shares=300)
    book.service.emergency_exit(today=WEDNESDAY)  # covers only the new batch

    block = _block(book.service.evaluate_today(today=WEDNESDAY))

    assert [(batch_no, dates) for _, _, batch_no, _, dates in _rows(block)] == [
        (1, ["2026-08-12"]),
        (2, ["2026-08-13"]),
    ]


def test_t20_ex3_a_stale_batch_gets_a_new_covering_row_and_keeps_its_stale_row(
    tmp_path: Path,
) -> None:
    book = _stale_book(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY)])
    book.service.emergency_exit(today=THURSDAY)  # 判準 Z: writes a FRIDAY line

    block = _block(book.service.evaluate_today(today=THURSDAY))

    assert _rows(block) == [
        ("covering", "2330", 1, 300, ["2026-08-14"]),
        ("stale", "2330", 1, 300, ["2026-08-12"]),
    ]
    assert block.sections[1].rows[0].notes == [wording.PENDING_EXIT_STALE_ALSO_COVERED_NOTE]


# --- T21: warnings untouched ----------------------------------------------------------------


def test_t21_warnings_are_the_same_with_the_block_stubbed_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    books = []
    for name in ("real", "stub"):
        book = _stale_book(tmp_path / f"{name}.db")
        hold(book.store, "2330", 1, shares=300)
        log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY)])
        books.append(book)
    real = books[0].service.evaluate_today(today=THURSDAY)
    monkeypatch.setattr(
        service_module,
        "_pending_exit_lines",
        lambda *args, **kwargs: service_module.PendingExitView(directives=[], block=None),
    )
    stub = books[1].service.evaluate_today(today=THURSDAY)

    assert real.pending_exit_block is not None and stub.pending_exit_block is None
    assert real.warnings == stub.warnings
    assert real.model_dump(
        exclude={"pending_exit_block", "pending_exit_directives"}
    ) == stub.model_dump(exclude={"pending_exit_block", "pending_exit_directives"})
    for text in _texts(real.pending_exit_block):
        assert text not in real.warnings


# --- T25 (風控 (k)): A-15 on all three kinds ------------------------------------------------


def test_t25_a15_on_a_covering_row_and_not_when_shares_are_equal(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300, remaining=200)  # P1 sold 100 after the exit
    hold(book.store, "2454", 1, shares=200)
    log_like_before_n166(book.store, [_exit("2330", 1, FRIDAY, 300), _exit("2454", 1, FRIDAY, 200)])

    block = _block(book.service.evaluate_today(today=TUESDAY))

    reduced, equal = block.sections[0].rows
    assert (reduced.shares, reduced.notes) == (200, [wording.PENDING_EXIT_SHARES_REDUCED_NOTE])
    assert reduced.text == wording.PENDING_EXIT_ITEM.format(
        symbol="2330", batch_no=1, shares=200, execution_dates="2026-08-14"
    )
    assert (equal.shares, equal.notes) == (200, [])


def test_t25_a15_after_a6_on_a_covering_row(tmp_path: Path) -> None:
    book = _capped_book(tmp_path / "playbook.db", TUESDAY)
    hold(book.store, "2330", 1, shares=300, remaining=100)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY, 300)])

    (row,) = _block(book.service.evaluate_today(today=THURSDAY)).sections[0].rows

    assert row.notes == [
        wording.PENDING_EXIT_PAST_DUE_NOTE.format(past_due_dates="2026-08-12"),
        wording.PENDING_EXIT_SHARES_REDUCED_NOTE,
    ]


def test_t25_a15_after_a11_or_a12_on_a_stale_row(tmp_path: Path) -> None:
    book = _stale_book(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300, remaining=200)
    hold(book.store, "2454", 1, shares=200)
    log_like_before_n166(
        book.store,
        [_exit("2330", 1, WEDNESDAY, 300), _exit("2454", 1, FRIDAY + timedelta(days=3), 200)],
    )

    block = _block(book.service.evaluate_today(today=THURSDAY))

    stale = next(section for section in block.sections if section.kind == "stale")
    (row,) = stale.rows
    assert row.notes == [
        wording.PENDING_EXIT_STALE_UNCOVERED_NOTE,
        wording.PENDING_EXIT_SHARES_REDUCED_NOTE,
    ]
    covering = next(section for section in block.sections if section.kind == "covering")
    assert covering.rows[0].notes == []  # equal shares: no A-15


def test_t25_a15_on_an_unclassified_row(tmp_path: Path) -> None:
    book = open_book(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300, remaining=200)
    hold(book.store, "2454", 1, shares=200)
    log_like_before_n166(book.store, [_exit("2330", 1, FRIDAY, 300), _exit("2454", 1, FRIDAY, 200)])

    block = _block(book.service.evaluate_today(today=TUESDAY))

    reduced, equal = block.sections[0].rows
    assert reduced.coverage == "unclassified"
    assert reduced.notes == [wording.PENDING_EXIT_SHARES_REDUCED_NOTE] and equal.notes == []
    assert book.prices.calls == [] and book.index.calls == []


def test_exit_row_shares_reduced_is_any_line_above_the_batch() -> None:
    rng = random.Random(15)
    for _ in range(500):
        lines = [rng.randint(0, 5) for _ in range(rng.randint(0, 4))]
        remaining = rng.randint(0, 5)
        assert exit_row_shares_reduced(lines, remaining_shares=remaining) is any(
            shares > remaining for shares in lines
        )


# --- T17′ (風控 (m), 補充一 S-2 第 5 點 (a)～(d)) ------------------------------------------


FORBIDDEN_IN_A6 = ("TradingCalendar", "calendar", "load_", "resolver")


def test_t17_a_the_a6_predicate_takes_no_calendar_and_no_bars_and_reaches_none() -> None:
    signature = inspect.signature(exit_row_past_due)
    assert list(signature.parameters) == ["execution_dates", "as_of"]
    assert signature.parameters["as_of"].kind is inspect.Parameter.KEYWORD_ONLY
    for parameter in signature.parameters.values():
        annotation = str(parameter.annotation)
        assert "Calendar" not in annotation and "PriceBar" not in annotation
    source = inspect.getsource(exit_row_past_due)
    tree = ast.parse(source)
    (function,) = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    body = function.body[1:]  # after the docstring
    names = {
        node.id for statement in body for node in ast.walk(statement) if isinstance(node, ast.Name)
    } | {
        node.attr
        for statement in body
        for node in ast.walk(statement)
        if isinstance(node, ast.Attribute)
    }
    for name in names:
        for forbidden in FORBIDDEN_IN_A6:
            assert forbidden.lower() not in name.lower(), name
    for forbidden in FORBIDDEN_IN_A6:
        assert forbidden not in source, forbidden
    # The only call in the body is the builtin ``any``: nothing is loaded or looked up.
    calls = [
        node for statement in body for node in ast.walk(statement) if isinstance(node, ast.Call)
    ]
    assert [getattr(call.func, "id", None) for call in calls] == ["any"]


def test_t17_b_unauthored_a6_with_zero_resolver_calls(tmp_path: Path) -> None:
    book = open_book(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY), _exit("2330", 1, FRIDAY)])

    block = _block(book.service.evaluate_today(today=THURSDAY))

    (row,) = block.sections[0].rows
    assert row.coverage == "unclassified"
    assert row.notes == [wording.PENDING_EXIT_PAST_DUE_NOTE.format(past_due_dates="2026-08-12")]
    assert book.prices.calls == [] and book.index.calls == []
    assert book.prices.cached_calls == [] and book.index.cached_calls == []


def test_t17_c_the_predicate_is_any_date_before_as_of() -> None:
    days = [date(2026, 8, 10) + timedelta(days=offset) for offset in range(5)]
    for size in range(0, 4):
        for chosen in itertools.product(days, repeat=size):
            for as_of in days:
                assert exit_row_past_due(chosen, as_of=as_of) is any(d < as_of for d in chosen)
    rng = random.Random(6)
    for _ in range(500):
        drawn = [
            date(2026, 1, 1) + timedelta(days=rng.randint(0, 400)) for _ in range(rng.randint(0, 6))
        ]
        as_of = date(2026, 1, 1) + timedelta(days=rng.randint(0, 400))
        assert exit_row_past_due(drawn, as_of=as_of) is any(d < as_of for d in drawn)


def _app_trees() -> Iterator[tuple[Path, ast.AST]]:
    for path in sorted(APP_ROOT.rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_t17_d_a6_is_attached_only_under_the_one_call_of_the_predicate() -> None:
    calls: list[tuple[str, ast.Call]] = []
    uses: list[tuple[str, ast.AST]] = []
    guarded: list[ast.AST] = []
    for path, tree in _app_trees():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name | ast.Attribute)
                and getattr(node.func, "id", getattr(node.func, "attr", None))
                == "exit_row_past_due"
            ):
                calls.append((path.name, node))
            if (
                isinstance(node, ast.Attribute | ast.Name)
                and isinstance(node.ctx, ast.Load)
                and getattr(node, "attr", getattr(node, "id", None)) == "PENDING_EXIT_PAST_DUE_NOTE"
            ):
                uses.append((path.name, node))
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Call)
                and getattr(node.test.func, "id", None) == "exit_row_past_due"
            ):
                guarded.extend(inner for statement in node.body for inner in ast.walk(statement))
    assert [name for name, _ in calls] == ["service.py"]
    assert [name for name, _ in uses] == ["service.py"]
    assert uses[0][1] in guarded


# --- (i), C6: wording discipline --------------------------------------------------------------


BLOCK_CONSTANTS = (
    "PENDING_EXIT_BLOCK_TITLE",
    "PENDING_EXIT_BLOCK_LEAD",
    "PENDING_EXIT_COVERED_LEAD",
    "PENDING_EXIT_UNCLASSIFIED_LEAD",
    "PENDING_EXIT_ITEM",
    "PENDING_EXIT_PAST_DUE_NOTE",
    "PENDING_EXIT_COVERED_LABEL",
    "PENDING_EXIT_STALE_LABEL",
    "PENDING_EXIT_STALE_LEAD",
    "PENDING_EXIT_STALE_ALSO_COVERED_NOTE",
    "PENDING_EXIT_STALE_UNCOVERED_NOTE",
    "PENDING_EXIT_UNAUTHORED_NOTE",
    "PENDING_EXIT_RECEIPT_OVERLAP_NOTE",
    "PENDING_EXIT_SHARES_REDUCED_NOTE",
)


def test_c6_the_block_wording_lives_in_wording_py_only() -> None:
    """No literal outside ``wording.py`` holds a block sentence or a CJK piece of one."""
    texts = [getattr(wording, name) for name in BLOCK_CONSTANTS]
    for path, tree in _app_trees():
        if path.name == "wording.py":
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            value = node.value
            cjk = sum(1 for char in value if "\u4e00" <= char <= "\u9fff")
            for text in texts:
                assert text not in value, path
                assert not (cjk >= 6 and value in text), (path, value)
    store = Path(service_module.__file__).with_name("store.py").read_text(encoding="utf-8")
    assert "wording" not in {
        alias.name.split(".")[-1]
        for node in ast.walk(ast.parse(store))
        if isinstance(node, ast.ImportFrom | ast.Import)
        for alias in node.names
    }


# --- C15 ／ 釐清二 E-11 第 3 點: W-B2L comes from _lines only --------------------------------


def test_e11_row_notes_are_copied_from_lines_and_labels_are_never_read_here() -> None:
    tree = ast.parse(Path(service_module.__file__).read_text(encoding="utf-8"))
    for function in ast.walk(tree):
        if isinstance(function, ast.FunctionDef) and function.name in {
            "_pending_exit_lines",
            "_exit_row",
            "classify_exit_batches",
            "exit_row_past_due",
            "exit_row_shares_reduced",
        }:
            names = {getattr(node, "id", getattr(node, "attr", "")) for node in ast.walk(function)}
            assert "labeled_batches" not in names and "entry_before_exit_note" not in names
    source = inspect.getsource(api_module._pending_exit_block)
    tree = ast.parse(source)
    reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "labeled_batches"
    ]
    lines_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_lines"
    ]
    assert len(lines_calls) == 1
    (call,) = lines_calls
    assert [keyword.arg for keyword in call.keywords] == ["labeled_batches"]
    assert {id(node) for node in reads} == {id(call.keywords[0].value)}


def test_c15_the_note_is_its_own_field_and_null_until_n168(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    book.service.emergency_exit(today=TUESDAY)

    body = _today_body(book, TUESDAY)

    rows = [row for section in body["pending_exit_block"]["sections"] for row in section["rows"]]
    assert rows and all(row["entry_before_exit_note"] is None for row in rows)
    assert all(line["entry_before_exit_note"] is None for line in body["pending_exit_directives"])
    # Row and its raw lines agree on the note (the E-11 第 3 點 pair, null for now).
    assert {row["entry_before_exit_note"] for row in rows} == {
        line["entry_before_exit_note"] for line in body["pending_exit_directives"]
    }


# --- (i): forbidden words, 「本系統不下單」 --------------------------------------------------


BANNED = (
    "安全",
    "放心",
    "已執行",
    "已出清",
    "已成交",
    "出清完成",
    "需",
    "應",
    "務必",
    "盡快",
    "否則",
    "已取消",
    "已撤單",
    "保證",
    "你已買進",
)
SUGGESTION_ALLOWLIST = "非本系統的判斷或建議"


def test_i_no_forbidden_word_and_suggestion_only_in_the_attribution_negation() -> None:
    for name in BLOCK_CONSTANTS:
        text = getattr(wording, name)
        for banned in BANNED:
            assert banned not in text, (name, banned)
        stripped = text.replace(SUGGESTION_ALLOWLIST, "")
        assert "建議" not in stripped, name
    assert wording.PENDING_EXIT_BLOCK_LEAD.count(SUGGESTION_ALLOWLIST) == 1
    for name in (
        "PENDING_EXIT_BLOCK_LEAD",
        "PENDING_EXIT_PAST_DUE_NOTE",
        "PENDING_EXIT_STALE_LEAD",
    ):
        assert "本系統不下單" in getattr(wording, name), name


def test_i_the_composed_block_carries_no_forbidden_word(tmp_path: Path) -> None:
    book = _stale_book(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300, remaining=200)
    log_like_before_n166(book.store, [_exit("2330", 1, WEDNESDAY), _exit("2330", 1, MONDAY_NEXT)])

    block = _block(book.service.evaluate_today(today=THURSDAY))

    for text in _texts(block):
        for banned in BANNED:
            assert banned not in text, banned
        assert "建議" not in text.replace(SUGGESTION_ALLOWLIST, "")
    assert "{read_at}" in block.lead_template and block.lead_template.count("{read_at}") == 1


# --- P-8 / C19: the backend never fills {read_at} --------------------------------------------


def test_c19_the_lead_template_keeps_read_at_for_the_client(tmp_path: Path) -> None:
    book = _authored(tmp_path / "playbook.db")
    hold(book.store, "2330", 1, shares=300)
    book.service.emergency_exit(today=TUESDAY)

    body = _today_body(book, TUESDAY)

    assert body["pending_exit_block"]["lead_template"] == wording.PENDING_EXIT_BLOCK_LEAD
    assert "{read_at}" in body["pending_exit_block"]["lead_template"]
    assert body["as_of"]  # the value the client substitutes
