"""N-168: pending R buys at an EMERGENCY_EXIT (ADR-0034 B-2a + L4; 補充一; 補充二).

An exit leaves an unsettled R1 buy where it is -- the book still judges it at
the 預定執行日 open (B-2a) -- and says so. Covered here:

* the L4 stamp: written in the exit's own ``BEGIN IMMEDIATE`` on every pending
  buy, both classes, once (C-B1, C-B3, 補充一 S-1 第 4 點; T-B1～T-B3, T-B7,
  T-B10～T-B12);
* the batch label: copied by ``settle`` on a fill only, kept until the batch
  closes, never from a G1 row (C-B6, C-B7, 必改 8; T-B4～T-B6, T-B8);
* the exit message: ［W-B7］＋［W-B1］＋［W-B1p］＋［W-B1d］＋［W-B1b］ appended
  before [S6] on all three branches, nothing else changed (C-B5, 必改 3, 4, 7(a)～(c),
  7(f));
* ``/today``: W-B6 and W-B1d in front of ENTRY and W-B6b, the two in-flight lists
  from the one in-flight read (C-B9, 必改 4, 5, 7(g)); W-B3 in the settlement;
* W-B2／W-B2L: the batch row and every sell line of a labeled batch, from one
  rule, through ``_lines`` (補充一 S-3 第 3、4 點, 釐清二 E-11 第 3 點);
* every sentence is 風控's, read back from the ruling files (必改 1, 7(h)).

T-B16 (only R1 writes a buy) is
``tests/test_playbook_pending_entry_blocked.py::test_every_buy_the_app_writes_is_an_r_series_line``.
"""

from __future__ import annotations

import ast
import inspect
import re
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import playbook as api_module
from app.api.deps import get_cap1_reading, get_playbook_service
from app.api.playbook_cap1_wording import Cap1Reading
from app.main import app
from app.playbook import service as service_module
from app.playbook import store as store_module
from app.playbook import wording
from app.playbook.models import BatchStatus, Directive, EmergencyExitResult, LabeledBatch
from app.playbook.store import (
    BATCH_LEFT_PLANNED_SQL,
    EntryBeforeExitRead,
    PendingDirective,
    PlaybookStore,
)
from tests.api_helpers import CLIENT_HEADERS
from tests.same_day_helpers import (
    MONDAY,
    ONE_BUY_SHARES,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Desk,
    buy_line,
    hold,
    log_like_before_n172a,
    open_desk,
)
from tests.seam_helpers import SCENARIOS, FullyClockedService, clocked_desk

REPO = Path(__file__).resolve().parents[4]
PLAN = REPO / "work/reviews/2026-10-31-N168方案裁示-風控.md"
RULING = REPO / "work/reviews/2026-11-01-N168字面裁示P2至P5-風控.md"
FRIDAY = date(2026, 8, 14)


# --- the 風控 files ---------------------------------------------------------------------


def _ruling_sentence(path: Path, identifier: str) -> str:
    """The first 「…」 paragraph under the heading (#### or **…**) naming ``identifier``."""
    lines = path.read_text(encoding="utf-8").splitlines()
    (heading,) = [
        index
        for index, line in enumerate(lines)
        if line.startswith(("####", "**")) and f"`{identifier}`" in line
    ]
    body = next(line for line in lines[heading + 1 :] if line.startswith("「"))
    assert body.endswith("」")
    return body[1:-1]


def _ruling_item(path: Path, marker: str) -> str:
    """The first 「…」 on the one line of ``path`` that contains ``marker``."""
    (line,) = [line for line in path.read_text(encoding="utf-8").splitlines() if marker in line]
    found = re.search(r"「([^」]*)」", line)
    assert found is not None
    return found.group(1)


SENTENCES = {
    "EMERGENCY_EXIT_PENDING_ENTRY_NOTE": PLAN,  # W-B1
    "EMERGENCY_EXIT_PENDING_ENTRY_PAST_DUE_NOTE": PLAN,  # W-B1p
    "ENTRY_BEFORE_EXIT_LABEL": PLAN,  # W-B2
    "ENTRY_BEFORE_EXIT_NOTE": PLAN,  # W-B2L
    "SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE": PLAN,  # W-B3
    "PENDING_ENTRY_FROZEN_NOTE": PLAN,  # W-B6
    "EMERGENCY_EXIT_LABELED_BATCH_NOTE": PLAN,  # W-B7
    "EMERGENCY_EXIT_BLOCKED_ENTRY_NOTE": RULING,  # W-B1b
    "PENDING_ENTRY_SAME_BATCH_NOTE": RULING,  # W-B1d
}


@pytest.mark.parametrize("name", sorted(SENTENCES))
def test_every_sentence_is_the_ruling_verbatim(name: str) -> None:
    """必改 1: copied, not retyped (ADR-0034 Decision 8)."""
    assert getattr(wording, name) == _ruling_sentence(SENTENCES[name], name)


def test_the_item_formats_are_the_rulings_verbatim() -> None:
    assert wording.EMERGENCY_EXIT_LABELED_ITEM == _ruling_item(
        PLAN, "`{labeled_items}` 的每項格式為"
    )
    assert wording.PENDING_ENTRY_SAME_BATCH_ITEM == _ruling_item(RULING, "`{dup_items}`")
    # ``{entry_items}`` is the one item N-172a／N-182 already use.
    assert wording.SAME_DAY_EARLIER_ENTRY_ITEM == _ruling_item(PLAN, "`{entry_items}` 的每項格式為")


#: 風控 2026-10-31 第二節之三 4. 的禁用詞, plus 「你已買進」 (條件 (a)).
FORBIDDEN = ("需", "應", "建議", "務必", "盡快", "否則", "安全", "已取消", "已撤單", "你已買進")
#: 風控 2026-11-04 第 9 點: the one exemption for W-B6b and W-B1b, verbatim.
EXEMPT_CORRESPONDING = "對應的批次"


@pytest.mark.parametrize(
    "name", ["EMERGENCY_EXIT_BLOCKED_ENTRY_NOTE", "PENDING_ENTRY_SAME_BATCH_NOTE"]
)
def test_the_new_sentences_pass_the_string_guards(name: str) -> None:
    """必改 7(h): W-B1b and W-B1d (W-B6b is N-182's own test)."""
    sentence = getattr(wording, name)
    exempt = EXEMPT_CORRESPONDING if name == "EMERGENCY_EXIT_BLOCKED_ENTRY_NOTE" else None
    if exempt is not None:
        assert sentence.count(exempt) == 1
        sentence = sentence.replace(exempt, "", 1)
    for banned in FORBIDDEN:
        assert banned not in sentence, banned
    assert "本系統不下單" in sentence
    assert "無法替你在券商撤單" in sentence
    assert "已成交" not in sentence


#: Phrases of 風控's own 2026-10-31 sentences that hold a forbidden character
#: without being the forbidden word (「對應」 is not the modal 「應」, 「如需」 is
#: not the urging 「需」 of D7). Listed verbatim, each exactly once, for 風控 to
#: confirm like 2026-11-04 第 9 點; nothing else is exempt.
SENTENCE_EXEMPTIONS: dict[str, str] = {
    "ENTRY_BEFORE_EXIT_NOTE": "對應這批",
    "EMERGENCY_EXIT_LABELED_BATCH_NOTE": "對應這幾批",
    "SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE": "如需",
}


@pytest.mark.parametrize(
    "name",
    [
        "EMERGENCY_EXIT_PENDING_ENTRY_NOTE",
        "EMERGENCY_EXIT_PENDING_ENTRY_PAST_DUE_NOTE",
        "ENTRY_BEFORE_EXIT_LABEL",
        "ENTRY_BEFORE_EXIT_NOTE",
        "SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE",
        "PENDING_ENTRY_FROZEN_NOTE",
        "EMERGENCY_EXIT_LABELED_BATCH_NOTE",
    ],
)
def test_the_w_series_carries_no_forbidden_word(name: str) -> None:
    """風控 2026-10-31 逐條意見 (PRD AC 字串檢查), with the exemptions above."""
    sentence = getattr(wording, name)
    exempt = SENTENCE_EXEMPTIONS.get(name)
    if exempt is not None:
        assert sentence.count(exempt) == 1
        sentence = sentence.replace(exempt, "", 1)
    for banned in FORBIDDEN:
        assert banned not in sentence, (name, banned)
    assert "需再次出清" not in sentence  # D7


@pytest.mark.parametrize(
    "name",
    [
        "EMERGENCY_EXIT_PENDING_ENTRY_NOTE",
        "PENDING_ENTRY_FROZEN_NOTE",
        "ENTRY_BEFORE_EXIT_NOTE",
        "SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE",
        "EMERGENCY_EXIT_LABELED_BATCH_NOTE",
    ],
)
def test_the_disclosures_say_the_system_places_no_order(name: str) -> None:
    assert "本系統不下單" in getattr(wording, name)


def test_the_sentences_live_in_wording_only() -> None:
    """ADR-0034 Decision 8: no other module under ``app/`` holds a piece of them."""
    app_root = Path(wording.__file__).resolve().parents[1]
    texts = [getattr(wording, name) for name in SENTENCES]
    for path in sorted(app_root.rglob("*.py")):
        if path.name == "wording.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                cjk = sum(1 for char in node.value if "一" <= char <= "鿿")
                for text in texts:
                    assert not (cjk >= 6 and node.value in text), (path, node.value)


# --- shared helpers ------------------------------------------------------------------------


def _item(line: Directive) -> str:
    return wording.SAME_DAY_EARLIER_ENTRY_ITEM.format(
        symbol=line.symbol,
        batch_no=line.batch_no,
        shares=line.shares,
        rule_id=line.rule_id,
        execution_date=line.execution_date.isoformat(),
    )


def _w_b1(*lines: Directive) -> str:
    return wording.EMERGENCY_EXIT_PENDING_ENTRY_NOTE.format(
        entry_count=len(lines), entry_items="、".join(_item(line) for line in lines)
    )


def _w_b1b(*lines: Directive) -> str:
    return wording.EMERGENCY_EXIT_BLOCKED_ENTRY_NOTE.format(
        blocked_count=len(lines), entry_items="、".join(_item(line) for line in lines)
    )


def _w_b1p(*days: date) -> str:
    return wording.EMERGENCY_EXIT_PENDING_ENTRY_PAST_DUE_NOTE.format(
        entry_past_due_dates=wording.date_list(days)
    )


def _w_b1d(*batches: tuple[str, int, tuple[date, ...]]) -> str:
    return wording.PENDING_ENTRY_SAME_BATCH_NOTE.format(
        dup_batches=len(batches),
        dup_items="、".join(
            wording.PENDING_ENTRY_SAME_BATCH_ITEM.format(
                symbol=symbol, batch_no=batch_no, dup_dates=wording.date_list(days)
            )
            for symbol, batch_no, days in batches
        ),
    )


def _w_b6(*lines: Directive) -> str:
    return wording.PENDING_ENTRY_FROZEN_NOTE.format(
        entry_count=len(lines), entry_items="、".join(_item(line) for line in lines)
    )


def _w_b2l(entry_date: date) -> str:
    return wording.ENTRY_BEFORE_EXIT_NOTE.format(entry_date=entry_date.isoformat())


def _w_b7(*batches: tuple[str, int, int]) -> str:
    return wording.EMERGENCY_EXIT_LABELED_BATCH_NOTE.format(
        labeled_count=len(batches),
        labeled_items="、".join(
            wording.EMERGENCY_EXIT_LABELED_ITEM.format(
                symbol=symbol, batch_no=batch_no, shares=f"{shares:,}"
            )
            for symbol, batch_no, shares in batches
        ),
    )


def _stamps(db_path: Path) -> list[tuple[int, str | None]]:
    with closing(sqlite3.connect(db_path)) as conn:
        return [
            (int(row[0]), row[1])
            for row in conn.execute(
                "SELECT id, exit_stamped_on FROM playbook_directives WHERE action = 'buy' "
                "ORDER BY id"
            )
        ]


def _set_status(store: PlaybookStore, symbol: str, batch_no: int, status: BatchStatus) -> None:
    batch = store.get_batch(symbol, batch_no)
    assert batch is not None
    store.save_batch(batch.model_copy(update={"status": status}))


def _trace(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    statements: list[str] = []
    real_connect = sqlite3.connect

    def tracing(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracing)
    return statements


def _writes(statements: list[str]) -> list[str]:
    return [
        sql
        for sql in statements
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
    ]


def _frozen_index(warnings: list[str]) -> int:
    return warnings.index(wording.FROZEN_NOTE.format(mode=wording.MODE_LABELS["emergency_frozen"]))


def _desk(tmp_path: Path, name: str = "playbook.db", **kwargs: Any) -> Desk:
    """:func:`open_desk` with every clock pinned (the HTTP exit included)."""
    desk = open_desk(tmp_path / name, **kwargs)
    service = FullyClockedService(
        store=desk.store,
        market_resolver={"TW": desk.prices},
        index_resolver={"TW": desk.index, "US": desk.index},
    )
    return Desk(service=service, store=desk.store, prices=desk.prices, index=desk.index)


# --- T-B1, T-B2: the stamp and the list on EMPTY and RESULT ---------------------------------


def test_t_b1_empty_stamps_the_buy_lists_it_and_writes_no_sell(tmp_path: Path) -> None:
    twin = _desk(tmp_path, "twin.db")
    desk = _desk(tmp_path)
    buy = buy_line()
    log_like_before_n172a(desk.store, [buy])

    base = twin.service.emergency_exit(today=TUESDAY)
    result = desk.service.emergency_exit(today=TUESDAY)

    assert result.directives == [] and result.pending_directives == []
    assert result.entry_before_exit_directives == [buy]
    assert result.entry_before_exit_blocked_directives == []
    assert result.message == base.message + _w_b1(buy)
    assert result.attribution is None  # W-B1 never picks a 歸屬語
    assert _stamps(desk.store.db_path) == [(1, TUESDAY.isoformat())]


def test_t_b2_result_sells_the_held_batch_only_and_lists_the_buy(tmp_path: Path) -> None:
    twin = _desk(tmp_path, "twin.db")
    desk = _desk(tmp_path)
    for book in (twin, desk):
        hold(book.store, "2330", 2)
    buy = buy_line()
    log_like_before_n172a(desk.store, [buy])

    base = twin.service.emergency_exit(today=TUESDAY)
    result = desk.service.emergency_exit(today=TUESDAY)

    assert [(line.batch_no, line.action) for line in result.directives] == [(2, "sell")]
    assert result.pending_directives == []  # the buy is in no covering set (VETO-2)
    assert result.entry_before_exit_directives == [buy]
    assert result.message == base.message + _w_b1(buy)
    assert result.attribution == base.attribution == wording.EXIT_ATTRIBUTION


def test_t_b3_a_repeat_writes_nothing_and_lists_the_buy_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = _desk(tmp_path)
    hold(desk.store, "2330", 2)
    buy = buy_line()
    log_like_before_n172a(desk.store, [buy])
    desk.service.emergency_exit(today=TUESDAY)
    stamped = _stamps(desk.store.db_path)
    statements = _trace(monkeypatch)

    repeat = desk.service.emergency_exit(today=TUESDAY)

    assert "BEGIN IMMEDIATE" in statements and "COMMIT" in statements
    assert _writes(statements) == []  # no INSERT and no UPDATE (ADR-0034 Q5, 0033 T-3)
    assert repeat.directives == []
    assert repeat.message.startswith("EMERGENCY_EXIT 已受理：本次未產生新的賣出指令。")
    assert repeat.message.endswith(_w_b1(buy))
    assert repeat.entry_before_exit_directives == [buy]
    assert _stamps(desk.store.db_path) == stamped


def test_the_stamp_is_written_in_the_exits_own_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-B1, C-B3, VETO-5: one BEGIN IMMEDIATE, the read and the UPDATE inside it."""
    desk = _desk(tmp_path)
    log_like_before_n172a(desk.store, [buy_line()])
    statements = _trace(monkeypatch)

    desk.service.emergency_exit(today=TUESDAY)

    begin = statements.index("BEGIN IMMEDIATE")
    commit = statements.index("COMMIT", begin)
    stamp = [
        index
        for index, sql in enumerate(statements)
        if sql.startswith("UPDATE playbook_directives SET exit_stamped_on")
    ]
    assert len(stamp) == 1 and begin < stamp[0] < commit
    (read,) = [
        sql
        for sql in statements[begin:commit]
        if sql.startswith("SELECT") and "exit_stamped_on IS NULL" in sql
    ]
    assert BATCH_LEFT_PLANNED_SQL in read  # 補充一 S-1 第 3 點: G1's own condition
    assert "action = 'buy' AND settled = 0 AND status = 'pending'" in read
    assert "execution_date" not in read.rsplit("WHERE", 1)[1]  # Decision 1: no date bound
    assert statements.count("BEGIN IMMEDIATE") == 1


def test_t_b7_a_past_due_buy_is_stamped_and_gets_w_b1p(tmp_path: Path) -> None:
    desk = _desk(tmp_path)
    late = buy_line(data_date=date(2026, 8, 7), execution_date=MONDAY)
    log_like_before_n172a(desk.store, [late])

    result = desk.service.emergency_exit(today=TUESDAY)

    assert _stamps(desk.store.db_path) == [(1, TUESDAY.isoformat())]
    assert result.message.endswith(_w_b1(late) + _w_b1p(MONDAY))


def test_t_b10_a_row_is_stamped_once_by_the_first_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = _desk(tmp_path)
    log_like_before_n172a(desk.store, [buy_line(execution_date=THURSDAY)])
    desk.service.emergency_exit(today=TUESDAY)
    statements = _trace(monkeypatch)

    desk.service.emergency_exit(today=WEDNESDAY)  # a later exit, the buy still pending

    assert _stamps(desk.store.db_path) == [(1, TUESDAY.isoformat())]
    assert not [sql for sql in _writes(statements) if "exit_stamped_on" in sql]


def test_t_b11_a_failure_rolls_the_stamp_back_with_the_lines_and_the_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = _desk(tmp_path)
    hold(desk.store, "2330", 2)
    log_like_before_n172a(desk.store, [buy_line()])
    real = store_module._read_and_stamp_exit_entries

    def broken(conn: sqlite3.Connection, *, stamped_on: date) -> Any:
        real(conn, stamped_on=stamped_on)
        raise sqlite3.OperationalError("boom")

    monkeypatch.setattr(store_module, "_read_and_stamp_exit_entries", broken)

    with pytest.raises(sqlite3.OperationalError, match="boom"):
        desk.service.emergency_exit(today=TUESDAY)

    assert _stamps(desk.store.db_path) == [(1, None)]
    assert [item.directive.rule_id for item in desk.store.pending_directives()] == ["R1"]
    assert desk.store.portfolio_state().emergency_until is None


# --- 補充一 S-1: the two classes, both stamped ------------------------------------------------


def test_s1_a_g1_row_is_stamped_its_claim_refused_and_no_label_follows(tmp_path: Path) -> None:
    """S-1 7(a), 必改 8: batch 1 filled already, unlabeled; its second buy is G1's."""
    desk = _desk(tmp_path)
    hold(desk.store, "2330", 1)
    blocked = buy_line()
    log_like_before_n172a(desk.store, [blocked])

    result = desk.service.emergency_exit(today=TUESDAY)

    assert result.entry_before_exit_directives == []
    assert result.entry_before_exit_blocked_directives == [blocked]
    assert _w_b1b(blocked) in result.message and "另有 1 筆在本次提交前已產生" in result.message
    assert _w_b1(blocked) not in result.message
    assert _stamps(desk.store.db_path) == [(1, TUESDAY.isoformat())]

    today = desk.service.evaluate_today(today=WEDNESDAY)

    assert today.settlement is not None
    (refused,) = [line for line in today.settlement.unsettled if line.refused_by_g1]
    assert refused.directive == blocked
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.entry_before_exit_on is None
    assert today.labeled_batches == ()
    assert not [warning for warning in today.settlement.warnings if "本次結算中" in warning]
    assert today.entry_before_exit_blocked_directives == [blocked]


def test_s1_a_row_turns_g1_once_another_line_filled_its_batch(tmp_path: Path) -> None:
    """S-1 7(b), 必改 7(f): two K1-distinct buys for one planned batch."""
    desk = _desk(tmp_path)
    first = buy_line(execution_date=WEDNESDAY)
    second = buy_line(execution_date=THURSDAY)
    duplicate = buy_line(execution_date=WEDNESDAY)  # same K1 as ``first``: counted once
    log_like_before_n172a(desk.store, [second, first, duplicate])

    result = desk.service.emergency_exit(today=TUESDAY)

    assert result.entry_before_exit_directives == [first, second]
    assert result.message.endswith(
        _w_b1(first, second) + _w_b1d(("2330", 1, (WEDNESDAY, THURSDAY)))
    )
    assert [stamp for _, stamp in _stamps(desk.store.db_path)] == [TUESDAY.isoformat()] * 3

    frozen = desk.service.evaluate_today(today=TUESDAY)
    position = _frozen_index(frozen.warnings)
    assert frozen.warnings[position + 1 : position + 3] == [
        _w_b6(first, second),
        _w_b1d(("2330", 1, (WEDNESDAY, THURSDAY))),
    ]

    after = desk.service.evaluate_today(today=WEDNESDAY)  # ``first`` fills batch 1

    # Both lines left are G1's now: ``duplicate`` (``first``'s K1, refused in this
    # settlement) and ``second``; one per K1, in item order.
    assert after.entry_before_exit_directives == []
    assert after.entry_before_exit_blocked_directives == [duplicate, second]
    assert after.settlement is not None
    assert [line.directive for line in after.settlement.unsettled if line.refused_by_g1] == [
        duplicate
    ]
    assert _w_b6(second) not in after.warnings
    w_b6b = [warning for warning in after.warnings if warning.startswith("尚有 1 筆已產生")]
    assert w_b6b and _item(second) in w_b6b[0]


def test_s1_the_exit_and_the_lists_split_by_g1s_own_condition() -> None:
    """S-1 7(c), 釐清一 E-1 第 3 點: one constant, and the service never decides it."""
    source = inspect.getsource(store_module._read_and_stamp_exit_entries)
    assert "BATCH_LEFT_PLANNED_SQL" in source and "planned" not in source.split('"""')[2]
    for function in (service_module._entry_before_exit_lines, service_module._exit_entries):
        (definition,) = ast.parse(inspect.cleandoc("\n" + inspect.getsource(function))).body
        assert isinstance(definition, ast.FunctionDef)
        nodes = [node for statement in definition.body[1:] for node in ast.walk(statement)]
        assert not [n for n in nodes if isinstance(n, ast.Constant) and "planned" in str(n.value)]
        assert not [n for n in nodes if isinstance(n, ast.Attribute) and n.attr == "status"]


# --- 必改 3, 4, 7(a)～(c): the three branches ----------------------------------------------


def _branch_desk(
    tmp_path: Path, name: str, *, branch: str, kinds: tuple[str, ...], with_buys: bool
) -> tuple[Desk, list[Directive], list[Directive]]:
    desk = _desk(tmp_path, name)
    if branch != "empty":
        hold(desk.store, "2330", 3)
    _set_status(desk.store, "2330", 2, "closed")
    entries = [buy_line(batch_no=1)] if "w_b1" in kinds else []
    blocked = [buy_line(batch_no=2)] if "w_b1b" in kinds else []
    if with_buys:
        log_like_before_n172a(desk.store, [*entries, *blocked])
    return desk, entries, blocked


def _exit(desk: Desk, branch: str) -> EmergencyExitResult:
    result = desk.service.emergency_exit(today=TUESDAY)
    if branch == "already_pending":
        result = desk.service.emergency_exit(today=TUESDAY)
    return result


@pytest.mark.parametrize("branch", ["result", "already_pending", "empty"])
@pytest.mark.parametrize("kinds", [("w_b1",), ("w_b1b",), ("w_b1", "w_b1b")])
def test_7a_each_branch_appends_w_b1_then_w_b1b_and_changes_nothing_else(
    tmp_path: Path, branch: str, kinds: tuple[str, ...]
) -> None:
    twin, _, _ = _branch_desk(tmp_path, "twin.db", branch=branch, kinds=kinds, with_buys=False)
    desk, entries, blocked = _branch_desk(
        tmp_path, "playbook.db", branch=branch, kinds=kinds, with_buys=True
    )

    base = _exit(twin, branch)
    result = _exit(desk, branch)

    expected = base.message
    if entries:
        expected += _w_b1(*entries)
    if blocked:
        expected += _w_b1b(*blocked)
    assert result.message == expected
    assert result.attribution == base.attribution
    assert result.directives == base.directives
    assert result.pending_directives == base.pending_directives
    assert result.entry_before_exit_directives == entries
    assert result.entry_before_exit_blocked_directives == blocked


@pytest.mark.parametrize("status", ["closed", "skipped"])
def test_7b_empty_names_a_buy_of_a_closed_or_skipped_batch_in_w_b1b(
    tmp_path: Path, status: BatchStatus
) -> None:
    desk = _desk(tmp_path)
    _set_status(desk.store, "2330", 1, status)
    blocked = buy_line()
    log_like_before_n172a(desk.store, [blocked])

    result = desk.service.emergency_exit(today=TUESDAY)

    assert result.message.startswith("EMERGENCY_EXIT 已受理：目前無持有批次")
    assert result.message.endswith(_w_b1b(blocked))
    assert result.attribution is None


def test_7c_w_b1p_counts_only_w_b1s_lines(tmp_path: Path) -> None:
    desk = _desk(tmp_path)
    hold(desk.store, "2330", 2)
    blocked_late = buy_line(batch_no=2, data_date=date(2026, 8, 7), execution_date=MONDAY)
    entry = buy_line(batch_no=1, execution_date=WEDNESDAY)
    log_like_before_n172a(desk.store, [blocked_late, entry])

    result = desk.service.emergency_exit(today=TUESDAY)

    assert result.message.endswith(_w_b1(entry) + _w_b1b(blocked_late))
    assert "已過、仍未結算；本系統無法得知你在券商是否已買進" not in result.message


def test_the_items_follow_date_symbol_batch_and_shares_stay_per_line(tmp_path: Path) -> None:
    desk = _desk(tmp_path, symbols=("2330", "2454"))
    lines = [
        buy_line(symbol="2454", batch_no=1, execution_date=THURSDAY, shares=100),
        buy_line(symbol="2330", batch_no=2, execution_date=THURSDAY, shares=200),
        buy_line(symbol="2454", batch_no=2, execution_date=WEDNESDAY, shares=300),
    ]
    log_like_before_n172a(desk.store, lines)

    result = desk.service.emergency_exit(today=TUESDAY)

    ordered = [lines[2], lines[1], lines[0]]
    assert result.entry_before_exit_directives == ordered
    assert result.message.endswith(_w_b1(*ordered))


# --- T-B4～T-B6, T-B8: the label --------------------------------------------------------------


def _labeled_desk(tmp_path: Path, name: str = "playbook.db") -> tuple[Desk, Directive]:
    """Batch 2 held and exited on Tuesday; batch 1's R1 buy fills on Wednesday."""
    desk = _desk(tmp_path, name)
    hold(desk.store, "2330", 2)
    buy = buy_line()
    log_like_before_n172a(desk.store, [buy])
    desk.service.emergency_exit(today=TUESDAY)
    return desk, buy


def test_t_b4_the_fill_labels_the_batch_and_the_label_survives(tmp_path: Path) -> None:
    desk, buy = _labeled_desk(tmp_path)

    run = desk.service.evaluate_today(today=WEDNESDAY)

    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.status == "open"
    assert batch.entry_before_exit_on == TUESDAY  # the exit's as_of (C-B3)
    assert run.labeled_batches == (LabeledBatch(symbol="2330", batch_no=1, entry_date=WEDNESDAY),)
    # W-B3, right after SETTLEMENT_SUMMARY (D5).
    assert run.settlement is not None
    summary = next(w for w in run.settlement.warnings if w.startswith("T+1 結算：依"))
    position = run.settlement.warnings.index(summary)
    assert run.settlement.warnings[position + 1] == (
        wording.SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE.format(count=1, entry_items=_item(buy))
    )

    desk.store.roll_peak_closes({"2330": Decimal("150")})
    desk.service.evaluate_today(today=WEDNESDAY)
    reopened = PlaybookStore(db_path=desk.store.db_path).get_batch("2330", 1)

    assert reopened is not None and reopened.peak_close == Decimal("150")
    assert reopened.entry_before_exit_on == TUESDAY


def test_the_batch_row_carries_w_b2_then_w_b2l_while_open(tmp_path: Path) -> None:
    desk, _ = _labeled_desk(tmp_path)
    run = desk.service.evaluate_today(today=WEDNESDAY)

    rows = {(row.batch_no, row.status): row for row in run.snapshot}
    labeled = rows[(1, "open")]
    assert labeled.entry_before_exit_on == TUESDAY
    assert labeled.entry_before_exit_label == wording.ENTRY_BEFORE_EXIT_LABEL
    assert labeled.entry_before_exit_note == _w_b2l(WEDNESDAY)
    for key, row in rows.items():
        if key != (1, "open"):
            assert (row.entry_before_exit_label, row.entry_before_exit_note) == (None, None)

    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    desk.store.save_batch(batch.model_copy(update={"status": "closed", "remaining_shares": 0}))
    closed = desk.service.evaluate_today(today=WEDNESDAY)

    (row,) = [row for row in closed.snapshot if row.batch_no == 1]
    assert row.entry_before_exit_on == TUESDAY  # the stored fact stays
    assert (row.entry_before_exit_label, row.entry_before_exit_note) == (None, None)
    assert closed.labeled_batches == ()


def test_t_b5_a_missed_buy_labels_nothing(tmp_path: Path) -> None:
    desk = _desk(tmp_path)
    log_like_before_n172a(desk.store, [buy_line(reference="120")])  # open 100 is off the band
    desk.service.emergency_exit(today=TUESDAY)

    run = desk.service.evaluate_today(today=WEDNESDAY)

    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    assert (batch.status, batch.missed_count, batch.entry_before_exit_on) == ("planned", 1, None)
    assert run.settlement is not None and run.settlement.missed == 1
    assert not [warning for warning in run.settlement.warnings if "本次結算中" in warning]


def test_t_b6_a_fill_after_the_freeze_is_still_labeled(tmp_path: Path) -> None:
    """L2's gap (VETO-1): the first ``/today`` comes after 預計恢復日."""
    desk, _ = _labeled_desk(tmp_path)
    until = desk.store.portfolio_state().emergency_until
    assert until is not None
    late = date(2026, 9, 16)
    assert late > until

    run = desk.service.evaluate_today(today=late)

    assert run.settlement is not None and run.settlement.settled_on == late
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.entry_before_exit_on == TUESDAY


def test_t_b8_a_buy_settled_before_the_exit_or_written_after_it_is_never_labeled(
    tmp_path: Path,
) -> None:
    desk = _desk(tmp_path)
    log_like_before_n172a(desk.store, [buy_line(batch_no=1)])
    desk.service.evaluate_today(today=WEDNESDAY)  # fills batch 1 before any exit
    desk.service.emergency_exit(today=WEDNESDAY)
    log_like_before_n172a(desk.store, [buy_line(batch_no=2, execution_date=THURSDAY)])

    desk.service.settle_pending(today=THURSDAY)  # batch 2's buy, written after the exit

    assert _stamps(desk.store.db_path) == [(1, None), (3, None)]
    for batch_no in (1, 2):
        batch = desk.store.get_batch("2330", batch_no)
        assert batch is not None and batch.entry_before_exit_on is None
    filled = desk.store.get_batch("2330", 2)
    assert filled is not None and filled.status == "open"


def test_settle_without_a_log_row_id_copies_nothing(tmp_path: Path) -> None:
    """C-B6: a line replayed by hand carries no stamp to copy."""
    desk = _desk(tmp_path)
    log_like_before_n172a(desk.store, [buy_line()])
    desk.service.emergency_exit(today=TUESDAY)

    desk.store.settle(buy_line().model_copy(update={"status": "executed"}))

    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.status == "open" and batch.entry_before_exit_on is None


# --- T-B9, W-B7, W-B2L on the lines ---------------------------------------------------------


def test_t_b9_a_later_exit_sells_the_labeled_batch_once_with_w_b7_and_w_b2l(
    tmp_path: Path,
) -> None:
    desk, _ = _labeled_desk(tmp_path)
    desk.service.evaluate_today(today=WEDNESDAY)  # batch 1 open, labeled; batch 2 sold

    again = desk.service.emergency_exit(today=THURSDAY)

    (line,) = again.directives
    assert (line.batch_no, line.action, line.rule_id) == (1, "sell", "EMERGENCY")
    assert again.labeled_batches == (LabeledBatch(symbol="2330", batch_no=1, entry_date=WEDNESDAY),)
    assert _w_b7(("2330", 1, ONE_BUY_SHARES)) in again.message
    assert again.attribution == wording.EXIT_ATTRIBUTION

    repeat = desk.service.emergency_exit(today=THURSDAY)
    assert repeat.directives == []
    assert _w_b7(("2330", 1, ONE_BUY_SHARES)) in repeat.message  # ALREADY_PENDING too
    assert [item.batch_no for item in repeat.pending_directives] == [1]

    with _client(desk) as client:
        body = client.post("/api/playbook/emergency-exit").json()
    (pending,) = body["pending_directives"]
    assert pending["entry_before_exit_note"] == _w_b2l(WEDNESDAY)
    assert pending["line"] == wording.directive_line(repeat.pending_directives[0])


def test_the_message_order_puts_w_b7_after_s10_and_before_w_b1(tmp_path: Path) -> None:
    """RESULT 支: … ＋［W-B7］＋［W-B1］＋［S6］ (補充二 P2(c))."""
    desk, _ = _labeled_desk(tmp_path)
    desk.service.evaluate_today(today=WEDNESDAY)
    pending = buy_line(batch_no=3, data_date=WEDNESDAY, execution_date=THURSDAY)
    log_like_before_n172a(desk.store, [pending])

    result = desk.service.emergency_exit(today=THURSDAY)

    w_b7 = _w_b7(("2330", 1, ONE_BUY_SHARES))
    w_b1 = _w_b1(pending)
    assert w_b7 in result.message and w_b1 in result.message
    assert result.message.index(w_b7) < result.message.index(w_b1)
    s6 = wording.EMERGENCY_EXIT_FREEZE_EXTENDED_NOTE.split("{", 1)[0]
    assert s6 in result.message and result.message.index(w_b1) < result.message.index(s6)


def _client(desk: Desk) -> Any:
    app.dependency_overrides[get_playbook_service] = lambda: desk.service
    app.dependency_overrides[get_cap1_reading] = lambda: Cap1Reading(
        weight=Decimal("0.10"), from_default=False
    )

    class _Serving:
        def __enter__(self) -> TestClient:
            self.client = TestClient(app, headers=CLIENT_HEADERS)
            return self.client.__enter__()

        def __exit__(self, *exc: object) -> None:
            self.client.__exit__(*exc)
            app.dependency_overrides.clear()

    return _Serving()


def test_e11_the_pending_exit_row_and_its_line_carry_the_same_w_b2l(tmp_path: Path) -> None:
    """釐清二 E-11 第 3 點 / ADR-0039 Decision 9: copied from ``_lines``, never derived."""
    desk, _ = _labeled_desk(tmp_path)
    desk.service.evaluate_today(today=WEDNESDAY)
    desk.service.emergency_exit(today=THURSDAY)
    desk.service.pinned = THURSDAY

    with _client(desk) as client:
        body = client.get("/api/playbook/today").json()

    (line,) = body["pending_exit_directives"]
    assert line["directive"]["batch_no"] == 1
    assert line["entry_before_exit_note"] == _w_b2l(WEDNESDAY)
    rows = [row for section in body["pending_exit_block"]["sections"] for row in section["rows"]]
    (row,) = rows
    assert (row["batch_no"], row["entry_before_exit_note"]) == (1, line["entry_before_exit_note"])
    (snapshot,) = [item for item in body["snapshot"] if item["batch_no"] == 1]
    assert snapshot["entry_before_exit_label"] == wording.ENTRY_BEFORE_EXIT_LABEL
    assert snapshot["entry_before_exit_note"] == line["entry_before_exit_note"]
    assert snapshot["entry_before_exit_on"] == TUESDAY.isoformat()


def test_the_unauthored_rows_carry_w_b2l_too(tmp_path: Path) -> None:
    """ADR-0039 Decision 9: the unclassified rows of a labeled batch, nothing loaded."""
    desk = clocked_desk(tmp_path / "playbook.db", seed=False)
    desk.store.ensure_batches(["2330"], batches_per_target=3)
    hold(desk.store, "2330", 1, entry_date=WEDNESDAY, entry_before_exit_on=TUESDAY)

    with _client(desk) as client:
        exit_body = client.post("/api/playbook/emergency-exit").json()
        desk.prices.calls.clear()  # the exit loads; the unauthored page may not
        body = client.get("/api/playbook/today").json()

    assert body["mode"] == "unconfirmed"
    (sell,) = exit_body["directives"]
    assert sell["entry_before_exit_note"] == _w_b2l(WEDNESDAY)
    (line,) = body["pending_exit_directives"]
    (section,) = body["pending_exit_block"]["sections"]
    (row,) = section["rows"]
    assert row["entry_before_exit_note"] == line["entry_before_exit_note"] == _w_b2l(WEDNESDAY)
    assert desk.prices.calls == []


def test_the_w_b2l_rule_on_lines() -> None:
    """補充一 S-3 第 4 點: sells of a labeled batch; S2 by symbol; nothing else."""
    labeled = (
        LabeledBatch(symbol="2330", batch_no=1, entry_date=WEDNESDAY),
        LabeledBatch(symbol="2330", batch_no=3, entry_date=MONDAY),
    )
    sell = buy_line().model_copy(update={"action": "sell", "rule_id": "S1"})
    lines = [
        sell,
        buy_line(),  # a buy of the labeled batch
        sell.model_copy(update={"batch_no": 2}),  # an unlabeled batch
        sell.model_copy(update={"batch_no": None, "rule_id": "S2"}),  # S2: whole symbol
        sell.model_copy(update={"symbol": "2454", "batch_no": None, "rule_id": "S2"}),
        sell.model_copy(update={"action": "defer", "rule_id": "R2"}),
    ]

    notes = [
        line.entry_before_exit_note for line in api_module._lines(lines, labeled_batches=labeled)
    ]

    assert notes == [
        _w_b2l(WEDNESDAY),
        None,
        None,
        wording.ENTRY_BEFORE_EXIT_NOTE.format(entry_date=f"{MONDAY}、{WEDNESDAY}"),
        None,
        None,
    ]
    assert all(
        line.line == wording.directive_line(directive)
        for line, directive in zip(
            api_module._lines(lines, labeled_batches=labeled), lines, strict=True
        )
    )


def test_e11_w_b2l_is_rendered_by_one_rule_only() -> None:
    """QB-13: ``ENTRY_BEFORE_EXIT_NOTE`` is read in ``entry_before_exit_note`` and nowhere else."""
    app_root = Path(wording.__file__).resolve().parents[1]
    readers: list[tuple[str, str]] = []
    for path in sorted(app_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "ENTRY_BEFORE_EXIT_NOTE":
                owner: ast.AST = node
                while owner in parents and not isinstance(owner, ast.FunctionDef):
                    owner = parents[owner]
                name = owner.name if isinstance(owner, ast.FunctionDef) else ""
                readers.append((path.relative_to(app_root).as_posix(), name))
    assert readers == [("playbook/service.py", "entry_before_exit_note")]
    callers = {
        function.name
        for module in (api_module, service_module)
        for function in ast.walk(ast.parse(Path(inspect.getfile(module)).read_text("utf-8")))
        if isinstance(function, ast.FunctionDef)
        and any(
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "entry_before_exit_note"
            for node in ast.walk(function)
        )
    }
    assert callers == {"_lines", "_labeled_snapshot"}


def test_e11_the_exit_read_and_the_exit_plan_never_see_a_buy() -> None:
    """QB-13: ``_read_exit_state`` reads no buy; the plan and the classifier get none."""
    assert "'buy'" not in inspect.getsource(store_module.PlaybookStore._read_exit_state)
    assert "ExitEntryRead" not in str(inspect.signature(service_module.plan_emergency_exit))
    for function in (service_module.plan_emergency_exit, service_module.classify_exit_batches):
        source = inspect.getsource(function)
        assert "entries" not in source and "buy" not in source


def test_t_b13_a_labeled_batch_gets_no_exit_line_nobody_submitted(tmp_path: Path) -> None:
    """CEO #80 (B-2b, permanent red line): only a submitted exit writes EMERGENCY."""
    desk, _ = _labeled_desk(tmp_path)
    exits_before = _emergency_rows(desk.store.db_path)

    for day in (WEDNESDAY, THURSDAY, FRIDAY):
        run = desk.service.evaluate_today(today=day)
        assert run.labeled_batches  # still labeled, still open
        assert not [line for line in run.directives if line.rule_id == "EMERGENCY"]

    assert _emergency_rows(desk.store.db_path) == exits_before


def _emergency_rows(db_path: Path) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            "SELECT id, batch_no FROM playbook_directives WHERE rule_id = 'EMERGENCY' ORDER BY id"
        ).fetchall()


def test_t_b15_after_the_freeze_r1_moves_on_to_the_next_batch(tmp_path: Path) -> None:
    desk, _ = _labeled_desk(tmp_path)
    desk.service.evaluate_today(today=WEDNESDAY)  # batch 1 fills, labeled
    desk.store.freeze_emergency(until=WEDNESDAY)  # the freeze is over by Thursday

    run = desk.service.evaluate_today(today=THURSDAY)

    assert run.mode == "normal" and run.is_schedule_day
    buys = [line for line in run.directives if line.action == "buy"]
    assert [(line.rule_id, line.batch_no) for line in buys] == [("R1", 3)]


# --- /today: C-B9, W-B6, W-B1d, the block order ---------------------------------------------


def test_t_b14_today_lists_the_stamped_buy_until_it_settles(tmp_path: Path) -> None:
    desk, buy = _labeled_desk(tmp_path)

    frozen = desk.service.evaluate_today(today=TUESDAY)
    assert frozen.entry_before_exit_directives == [buy]
    assert frozen.entry_before_exit_blocked_directives == []
    position = _frozen_index(frozen.warnings)
    assert frozen.warnings[position + 1] == _w_b6(buy)
    entry = [warning for warning in frozen.warnings if warning.startswith("指令帳冊中有")]
    assert entry == []  # ENTRY leaves out what W-B6 lists (P4)

    settled = desk.service.evaluate_today(today=WEDNESDAY)
    assert settled.entry_before_exit_directives == []
    assert _w_b6(buy) not in settled.warnings


def test_w_b6_is_rendered_in_the_exit_freeze_only(tmp_path: Path) -> None:
    desk, buy = _labeled_desk(tmp_path)
    desk.store.freeze_emergency(until=MONDAY)  # over: the page is not emergency_frozen

    run = desk.service.evaluate_today(today=TUESDAY)

    assert run.mode != "emergency_frozen"
    assert run.entry_before_exit_directives == [buy]  # the list is raw data, every mode
    assert _w_b6(buy) not in run.warnings


def test_7g_the_four_sentences_in_an_exit_freeze(tmp_path: Path) -> None:
    """FROZEN → W-B6 → W-B1d → ENTRY → W-B6b (補充二 P4)."""
    desk = _desk(tmp_path, symbols=("2330", "2454"))
    hold(desk.store, "2330", 2)
    first = buy_line(batch_no=1, execution_date=WEDNESDAY)
    second = buy_line(batch_no=1, execution_date=THURSDAY)
    blocked = buy_line(batch_no=2, execution_date=THURSDAY)
    log_like_before_n172a(desk.store, [first, second, blocked])
    desk.service.emergency_exit(today=TUESDAY)
    later = buy_line(symbol="2454")  # logged after the exit: unstamped, ENTRY's
    log_like_before_n172a(desk.store, [later])

    run = desk.service.evaluate_today(today=TUESDAY)

    position = _frozen_index(run.warnings)
    w_b6b = wording.PENDING_ENTRY_BLOCKED_NOTE.format(blocked_count=1, entry_items=_item(blocked))
    entry = wording.SAME_DAY_EARLIER_ENTRY_NOTE.format(entry_count=1, entry_items=_item(later))
    assert run.warnings[position + 1 : position + 5] == [
        _w_b6(first, second),
        _w_b1d(("2330", 1, (WEDNESDAY, THURSDAY))),
        entry,
        w_b6b,
    ]
    assert run.entry_before_exit_directives == [first, second]
    assert run.entry_before_exit_blocked_directives == [blocked]


def test_w_b6_and_its_lists_come_from_the_one_in_flight_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QB-7: the stamp is read inside ``read_in_flight`` only, once per ``/today``."""
    desk, _ = _labeled_desk(tmp_path)
    statements = _trace(monkeypatch)

    desk.service.evaluate_today(today=TUESDAY)

    stamped = [sql for sql in statements if "exit_stamped_on IS NOT NULL" in sql]
    assert len(stamped) == 1
    begin = max(
        index
        for index, sql in enumerate(statements[: statements.index(stamped[0])])
        if sql == "BEGIN"
    )
    window = statements[begin : statements.index("COMMIT", begin) + 1]
    assert stamped[0] in window
    assert all(sql.startswith(("BEGIN", "SELECT", "COMMIT")) for sql in window)
    assert not [sql for sql in statements if "exit_stamped_on IS NULL" in sql]


def test_the_seam_lists_never_mix(tmp_path: Path) -> None:
    """VETO-2: the buys are in their own lists, never in directives or pending lists."""
    desk, buy = _labeled_desk(tmp_path)
    run = desk.service.evaluate_today(today=TUESDAY)

    assert buy not in run.pending_exit_directives
    assert all(line.action == "sell" for line in run.pending_exit_directives)
    assert run.entry_before_exit_directives == [buy]


# --- W-B3 and N2 in one settlement -----------------------------------------------------------


def test_w_b3_comes_right_after_the_summary_and_before_n2(tmp_path: Path) -> None:
    """ADR-0034 W-B3 「緊接 SETTLEMENT_SUMMARY」 and N-166 N2 on one run (解讀點)."""
    desk = _desk(tmp_path)
    hold(desk.store, "2330", 2)
    stop = buy_line(batch_no=2, shares=300).model_copy(
        update={"action": "sell", "rule_id": "S1", "limit_low": None, "limit_high": None}
    )
    buy = buy_line(batch_no=1)
    log_like_before_n172a(desk.store, [stop, buy])
    desk.service.emergency_exit(today=TUESDAY)

    run = desk.service.evaluate_today(today=WEDNESDAY)

    assert run.settlement is not None
    warnings = run.settlement.warnings
    summary = next(index for index, w in enumerate(warnings) if w.startswith("T+1 結算：依"))
    assert warnings[summary + 1] == wording.SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE.format(
        count=1, entry_items=_item(buy)
    )
    assert warnings[summary + 2].startswith("本次判定成交的出清賣出指令中")


# --- C-B7, T-B12: the migration ----------------------------------------------------------------

_LEGACY_DIRECTIVES = """
    CREATE TABLE playbook_directives (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
        rules_version INTEGER NOT NULL, symbol TEXT NOT NULL, batch_no INTEGER,
        action TEXT NOT NULL, shares INTEGER NOT NULL, rule_id TEXT NOT NULL,
        rule_summary TEXT NOT NULL, data_date TEXT NOT NULL, execution_date TEXT NOT NULL,
        reference_price TEXT, limit_low TEXT, limit_high TEXT, limit_note TEXT NOT NULL DEFAULT '',
        data_status TEXT NOT NULL, source TEXT NOT NULL, data_reason TEXT, status TEXT NOT NULL,
        settled INTEGER NOT NULL DEFAULT 0, settled_at TEXT, settled_open_price TEXT
    )
"""
_LEGACY_BATCHES = """
    CREATE TABLE playbook_batches (
        symbol TEXT NOT NULL, batch_no INTEGER NOT NULL, status TEXT NOT NULL,
        entry_date TEXT, cost TEXT, shares INTEGER NOT NULL DEFAULT 0,
        remaining_shares INTEGER NOT NULL DEFAULT 0, peak_close TEXT,
        p1_done INTEGER NOT NULL DEFAULT 0, p2_done INTEGER NOT NULL DEFAULT 0,
        p3_last_date TEXT, trailing_active INTEGER NOT NULL DEFAULT 0,
        defer_count INTEGER NOT NULL DEFAULT 0, missed_count INTEGER NOT NULL DEFAULT 0,
        scheduled_date TEXT, updated_at TEXT NOT NULL, PRIMARY KEY (symbol, batch_no)
    )
"""


def _columns(db_path: Path, table: str) -> list[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]


def test_t_b12_a_legacy_database_gains_the_two_columns_once_and_nothing_is_back_filled(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(_LEGACY_DIRECTIVES)
        conn.execute(_LEGACY_BATCHES)
        conn.execute(
            "INSERT INTO playbook_batches (symbol, batch_no, status, entry_date, cost, shares, "
            "remaining_shares, updated_at) VALUES ('2330', 1, 'open', '2026-07-01', '100', 300, "
            "300, 'x')"
        )
        conn.execute(
            "INSERT INTO playbook_directives (created_at, rules_version, symbol, batch_no, "
            "action, shares, rule_id, rule_summary, data_date, execution_date, data_status, "
            "source, status) VALUES ('x', 1, '2330', 2, 'buy', 300, 'R1', 'legacy', "
            "'2026-08-11', '2026-08-12', 'fresh', 'fake', 'pending')"
        )
    errors: list[BaseException] = []

    def build() -> None:
        try:
            PlaybookStore(db_path=db_path)
        except BaseException as error:  # pragma: no cover - reported below
            errors.append(error)

    threads = [threading.Thread(target=build) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert _columns(db_path, "playbook_directives").count("exit_stamped_on") == 1
    assert _columns(db_path, "playbook_batches").count("entry_before_exit_on") == 1
    store = PlaybookStore(db_path=db_path)
    batch = store.get_batch("2330", 1)
    assert batch is not None and batch.entry_before_exit_on is None
    assert _stamps(db_path) == [(1, None)]


def test_c_b7_every_batch_write_keeps_the_label(tmp_path: Path) -> None:
    """The wholesale INSERT OR REPLACE carries the column (C-B7's 「最大的陷阱」)."""
    desk = _desk(tmp_path)
    hold(desk.store, "2330", 1, entry_before_exit_on=TUESDAY)

    desk.store.roll_peak_closes({"2330": Decimal("120")})
    desk.store._update_batch("2330", 1, {"trailing_active": True})

    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.trailing_active and batch.peak_close == Decimal("120")
    assert batch.entry_before_exit_on == TUESDAY
    assert [b.entry_before_exit_on for b in desk.store.list_batches() if b.batch_no == 1] == [
        TUESDAY
    ]


# --- SEAM (釐清二 E-6, E-8): the filled entries, on the golden scenarios ---------------------


@pytest.fixture(scope="module")
def golden_bodies(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    work = tmp_path_factory.mktemp("n168-golden")
    return {name: run(work / f"{name}.db") for name, run in SCENARIOS.items()}


def test_seam_filled_entry_before_exit_directives_on_the_golden_scenarios(
    golden_bodies: dict[str, dict[str, Any]],
) -> None:
    """``after_exit.today``: batch 1's one R1 buy; every other ``/today``: []; G1 lists: []."""
    after = golden_bodies["after_exit"]
    buy = buy_line(execution_date=WEDNESDAY)
    expected = [
        {
            "line": wording.directive_line(buy),
            "directive": buy.model_dump(mode="json"),
            "entry_before_exit_note": None,
        }
    ]
    assert after["today"]["entry_before_exit_directives"] == expected
    assert after["exit"]["entry_before_exit_directives"] == expected
    assert after["exit_repeat"]["entry_before_exit_directives"] == expected
    for scenario, bodies in golden_bodies.items():
        for name, body in bodies.items():
            if "entry_before_exit_blocked_directives" in body:
                assert body["entry_before_exit_blocked_directives"] == [], (scenario, name)
            if name.startswith("today") and (scenario, name) != ("after_exit", "today"):
                assert body["entry_before_exit_directives"] == [], (scenario, name)
    assert golden_bodies["unauthored"]["exit"]["entry_before_exit_directives"] == []


def test_seam_filled_in_flight_entries_on_the_golden_scenario(tmp_path: Path) -> None:
    """``read_in_flight().entries`` after the ``after_exit`` scenario's exit, exactly."""
    desk = clocked_desk(tmp_path / "playbook.db")
    hold(desk.store, "2330", 2)
    hold(desk.store, "2330", 3)
    log_like_before_n172a(desk.store, [buy_line(execution_date=WEDNESDAY)])
    desk.service.emergency_exit(today=TUESDAY)
    (pending,) = [
        item for item in desk.store.pending_directives() if item.directive.action == "buy"
    ]

    read = desk.store.read_in_flight()

    assert read.entries == EntryBeforeExitRead(blocked=(), stamped=(pending,))
    assert pending == PendingDirective(1, buy_line(execution_date=WEDNESDAY))


def test_entry_before_exit_lines_keep_one_per_k1_in_item_order() -> None:
    line = buy_line(execution_date=THURSDAY)
    other = buy_line(symbol="2454", execution_date=WEDNESDAY)
    read = EntryBeforeExitRead(
        blocked=(PendingDirective(9, buy_line(batch_no=2)),),
        stamped=(
            PendingDirective(3, line),
            PendingDirective(5, line),  # same K1: the smallest id stays
            PendingDirective(7, other),
            PendingDirective(9, buy_line(batch_no=2)),
        ),
    )

    entries, blocked = service_module._entry_before_exit_lines(read)

    assert entries == [other, line]
    assert blocked == [buy_line(batch_no=2)]


def _calls(function: Callable[..., Any]) -> list[str]:
    tree = ast.parse(inspect.cleandoc("\n" + inspect.getsource(function)))
    return [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]


def test_the_unauthored_path_classifies_without_g1_blocked_entries() -> None:
    """N-182's guard (``g1_blocked_entries`` is never called while unauthored) still holds."""
    assert "g1_blocked_entries" not in _calls(service_module._entry_before_exit_lines)
    assert "g1_blocked_entries" not in _calls(service_module._exit_entries)
