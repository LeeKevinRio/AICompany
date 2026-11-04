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
import random
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
from app.playbook import engine as engine_module
from app.playbook import service as service_module
from app.playbook import store as store_module
from app.playbook import wording
from app.playbook.models import (
    BatchSnapshot,
    BatchState,
    BatchStatus,
    Directive,
    EmergencyExitResult,
    LabeledBatch,
)
from app.playbook.store import (
    BATCH_LEFT_PLANNED_SQL,
    EntryBeforeExitRead,
    PendingDirective,
    PlaybookStore,
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
    hold,
    log_like_before_n172a,
    open_desk,
)
from tests.seam_helpers import SCENARIOS, FullyClockedService, clocked_desk

REPO = Path(__file__).resolve().parents[4]
PLAN = REPO / "work/reviews/2026-10-31-N168方案裁示-風控.md"
RULING = REPO / "work/reviews/2026-11-01-N168字面裁示P2至P5-風控.md"
#: 風控 2026-11-04 S3～S6: W-B2L and W-B3 revised, W-B2LS and W-B2LSr new.
REVISION = REPO / "work/reviews/2026-11-04-N168停止點S3至S6裁示-風控.md"
#: 風控 2026-11-04 E-30 裁示: W-B2LSf, (δ).
UNMATCHED_RULING = REPO / "work/reviews/2026-11-04-N168釐清七E30裁示-風控.md"
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
    return _paragraph_after(lines, heading)


def _paragraph_after(lines: list[str], heading: int) -> str:
    body = next(line for line in lines[heading + 1 :] if line.startswith("「"))
    assert body.endswith("」")
    return body[1:-1]


def _revised_sentence(marker: str, path: Path = REVISION) -> str:
    """The first 「…」 paragraph after the one bold line of ``path`` holding ``marker``."""
    lines = path.read_text(encoding="utf-8").splitlines()
    (heading,) = [index for index, line in enumerate(lines) if marker in line and "**" in line]
    return _paragraph_after(lines, heading)


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
    "PENDING_ENTRY_FROZEN_NOTE": PLAN,  # W-B6
    "EMERGENCY_EXIT_LABELED_BATCH_NOTE": PLAN,  # W-B7
    "EMERGENCY_EXIT_BLOCKED_ENTRY_NOTE": RULING,  # W-B1b
    "PENDING_ENTRY_SAME_BATCH_NOTE": RULING,  # W-B1d
}
#: 風控 2026-11-04: the revised and the new sentences, by the bold line naming each.
REVISED = {
    "ENTRY_BEFORE_EXIT_NOTE": "**W-B2L 修訂版",  # 第 6 點 (F-11)
    "SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE": "**W-B3 修訂版",  # 第 2 點 (D7)
    "ENTRY_BEFORE_EXIT_SYMBOL_NOTE": "`ENTRY_BEFORE_EXIT_SYMBOL_NOTE`",  # 第 5 點 W-B2LS
    "ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE": "`ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE`",  # W-B2LSr
}
ALL_SENTENCES = (*SENTENCES, *REVISED, "ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE")


@pytest.mark.parametrize("name", sorted(SENTENCES))
def test_every_sentence_is_the_ruling_verbatim(name: str) -> None:
    """必改 1: copied, not retyped (ADR-0034 Decision 8)."""
    assert getattr(wording, name) == _ruling_sentence(SENTENCES[name], name)


@pytest.mark.parametrize("name", sorted(REVISED))
def test_every_revised_sentence_is_the_2026_11_04_ruling_verbatim(name: str) -> None:
    """風控 2026-11-04 第 2、5、6 點: read from that file, never from the 10-31 one."""
    assert getattr(wording, name) == _revised_sentence(REVISED[name])


def test_w_b2lsf_is_the_e30_ruling_verbatim() -> None:
    """風控 2026-11-04 E-30 裁示第二節之 1: read from that file."""
    assert wording.ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE == _revised_sentence(
        "`ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE`", UNMATCHED_RULING
    )


def test_w_b2lsf_has_the_placeholders_of_w_b2ls() -> None:
    def fields(template: str) -> list[str]:
        return sorted(re.findall(r"{(\w+)}", template))

    assert fields(wording.ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE) == fields(
        wording.ENTRY_BEFORE_EXIT_SYMBOL_NOTE
    )


def test_the_revisions_replaced_what_they_revise() -> None:
    assert wording.ENTRY_BEFORE_EXIT_NOTE != _ruling_sentence(PLAN, "ENTRY_BEFORE_EXIT_NOTE")
    assert wording.SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE != _ruling_sentence(
        PLAN, "SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE"
    )


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


#: 風控 2026-11-04 第 2 點: the only two exemptions, verbatim, each exactly once in
#: its own sentence; 「應」 must be gone once it is taken out. W-B3 and W-B2LS get none.
SENTENCE_EXEMPTIONS: dict[str, str] = {
    "ENTRY_BEFORE_EXIT_NOTE": "對應這批",
    "EMERGENCY_EXIT_LABELED_BATCH_NOTE": "對應這幾批",
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
        "ENTRY_BEFORE_EXIT_SYMBOL_NOTE",
        "ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE",
        "ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE",
    ],
)
def test_the_w_series_carries_no_forbidden_word(name: str) -> None:
    """風控 2026-10-31 逐條意見 (PRD AC 字串檢查), 2026-11-04 第 2 點 and 第 5 點 (iii)."""
    sentence = getattr(wording, name)
    exempt = SENTENCE_EXEMPTIONS.get(name)
    if exempt is not None:
        assert sentence.count(exempt) == 1
        sentence = sentence.replace(exempt, "", 1)
    assert sentence.count("應") == 0 and sentence.count("需") == 0, name
    for banned in FORBIDDEN:
        assert banned not in sentence, (name, banned)
    assert "需再次出清" not in sentence  # D7


def test_w_b3_w_b2ls_and_w_b2lsf_need_no_exemption() -> None:
    for name in (
        "SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE",
        "ENTRY_BEFORE_EXIT_SYMBOL_NOTE",
        "ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE",
    ):
        sentence = getattr(wording, name)
        assert name not in SENTENCE_EXEMPTIONS
        assert (sentence.count("需"), sentence.count("應"), sentence.count("對應")) == (0, 0, 0)
    assert wording.SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE.endswith(
        "可再次提交全部出清，替這些批次產生賣出指令。"
    )


@pytest.mark.parametrize(
    "name",
    [
        "EMERGENCY_EXIT_PENDING_ENTRY_NOTE",
        "PENDING_ENTRY_FROZEN_NOTE",
        "ENTRY_BEFORE_EXIT_NOTE",
        "SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE",
        "EMERGENCY_EXIT_LABELED_BATCH_NOTE",
        "ENTRY_BEFORE_EXIT_SYMBOL_NOTE",
        "ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE",
    ],
)
def test_the_disclosures_say_the_system_places_no_order(name: str) -> None:
    """風控 2026-11-04 第 3 點 (d): W-B1p, W-B2 and W-B2LSr are the exceptions, held
    by the combined-unit assertions (a)～(c) below instead."""
    assert "本系統不下單" in getattr(wording, name)


def test_the_sentences_live_in_wording_only() -> None:
    """ADR-0034 Decision 8: no other module under ``app/`` holds a piece of them."""
    app_root = Path(wording.__file__).resolve().parents[1]
    texts = [getattr(wording, name) for name in ALL_SENTENCES]
    for path in sorted(app_root.rglob("*.py")):
        if path.name == "wording.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                cjk = sum(1 for char in node.value if "\u4e00" <= char <= "\u9fff")
                for text in texts:
                    assert not (cjk >= 6 and node.value in text), (path, node.value)


# --- 風控 2026-11-04 第 3 點 (a)～(c): the combined units ------------------------------------

#: W-B1's last words (after its last placeholder) and W-B1p's first words.
_W_B1_TAIL = wording.EMERGENCY_EXIT_PENDING_ENTRY_NOTE.rsplit("}", 1)[1]
_W_B1P_HEAD = wording.EMERGENCY_EXIT_PENDING_ENTRY_PAST_DUE_NOTE.split("{", 1)[0]
_W_B2LS_HEAD = wording.ENTRY_BEFORE_EXIT_SYMBOL_NOTE.split("{", 1)[0]
_W_B2LS_TAIL = wording.ENTRY_BEFORE_EXIT_SYMBOL_NOTE.rsplit("}", 1)[1]
_REST = wording.ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE


def assert_w_b1p_follows_w_b1(message: str) -> None:
    """(a): wherever W-B1p is, W-B1 is right before it."""
    if _W_B1P_HEAD in message:
        assert message.count(_W_B1P_HEAD) == 1
        assert message[: message.index(_W_B1P_HEAD)].endswith(_W_B1_TAIL)


def assert_labels_carry_their_note(snapshot: list[Any]) -> None:
    """(b): every labeled batch row has its W-B2L, which says 「本系統不下單」."""
    for row in snapshot:
        label = (
            row["entry_before_exit_label"] if isinstance(row, dict) else row.entry_before_exit_label
        )
        note = (
            row["entry_before_exit_note"] if isinstance(row, dict) else row.entry_before_exit_note
        )
        if label is not None:
            assert note is not None and "本系統不下單" in note


def assert_w_b2lsr_follows_w_b2ls(note: str | None) -> None:
    """(c): W-B2LSr only right after W-B2LS, in the same field, once."""
    if note is not None and _REST in note:
        assert note.count(_REST) == 1 and note.endswith(_REST)
        rest_free = note[: -len(_REST)]
        assert rest_free.startswith(_W_B2LS_HEAD) and rest_free.endswith(_W_B2LS_TAIL)


@pytest.mark.parametrize("labeled", [(), (("2330", 1, 300),)])
@pytest.mark.parametrize("entries", [0, 1, 2])
@pytest.mark.parametrize("past_due", [False, True])
@pytest.mark.parametrize("blocked", [False, True])
@pytest.mark.parametrize("describes_lines", [False, True])
def test_a_every_composition_keeps_w_b1p_right_after_w_b1(
    labeled: tuple[tuple[str, int, int], ...],
    entries: int,
    past_due: bool,
    blocked: bool,
    describes_lines: bool,
) -> None:
    lines = [buy_line(batch_no=index + 1) for index in range(entries)]
    notes = wording.exit_entry_notes(
        wording.ExitEntries(
            labeled=tuple(wording.ExitLabeled(*item) for item in labeled),
            entry_items=tuple(_item(line) for line in lines),
            past_due_dates=(MONDAY,) if past_due else (),
            blocked_items=(_item(buy_line(batch_no=9)),) if blocked else (),
        ),
        describes_lines=describes_lines,
    )
    assert_w_b1p_follows_w_b1(notes)
    assert (_W_B1P_HEAD in notes) is bool(entries and past_due)


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
                symbol=symbol, batch_no=batch_no, shares=shares
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
    assert_w_b1p_follows_w_b1(result.message)


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
    assert_w_b1p_follows_w_b1(result.message)
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
    assert_w_b1p_follows_w_b1(result.message)
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
    assert run.labeled_batches == (
        _label(1, WEDNESDAY, ONE_BUY_SHARES, open_shares=ONE_BUY_SHARES),
    )
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

    assert_labels_carry_their_note(run.snapshot)
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
    assert again.labeled_batches == (
        _label(1, WEDNESDAY, ONE_BUY_SHARES, open_shares=ONE_BUY_SHARES),
    )
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
    assert_labels_carry_their_note(body["snapshot"])


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


def _label(
    batch_no: int,
    entry_date: date,
    remaining_shares: int,
    *,
    open_shares: int,
    symbol: str = "2330",
) -> LabeledBatch:
    return LabeledBatch(
        symbol=symbol,
        batch_no=batch_no,
        entry_date=entry_date,
        remaining_shares=remaining_shares,
        symbol_open_shares=open_shares,
    )


def _w_b2ls(*batches: tuple[int, date, int], shares: int) -> str:
    """W-B2LS for 2330's ``(batch_no, entry_date, remaining_shares)``, ［＋W-B2LSr］."""
    ordered = sorted(batches)
    note = wording.ENTRY_BEFORE_EXIT_SYMBOL_NOTE.format(
        labeled_count=len(ordered),
        labeled_items="、".join(
            wording.EMERGENCY_EXIT_LABELED_ITEM.format(
                symbol="2330", batch_no=batch_no, shares=remaining
            )
            for batch_no, _, remaining in ordered
        ),
        entry_dates=wording.date_list(day for _, day, _ in ordered),
    )
    if shares > sum(remaining for _, _, remaining in ordered):
        note += wording.ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE
    return note


def _w_b2lsf(*batches: tuple[int, date, int]) -> str:
    """W-B2LSf for 2330's ``(batch_no, entry_date, remaining_shares)``; never W-B2LSr."""
    ordered = sorted(batches)
    return wording.ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE.format(
        labeled_count=len(ordered),
        labeled_items="、".join(
            wording.EMERGENCY_EXIT_LABELED_ITEM.format(
                symbol="2330", batch_no=batch_no, shares=remaining
            )
            for batch_no, _, remaining in ordered
        ),
        entry_dates=wording.date_list(day for _, day, _ in ordered),
    )


_SELL = buy_line().model_copy(update={"action": "sell", "rule_id": "S1"})
_S2 = _SELL.model_copy(update={"batch_no": None, "rule_id": "S2"})


def _s2_note(shares: int, labeled: tuple[LabeledBatch, ...]) -> str | None:
    (line,) = api_module._lines(
        [_S2.model_copy(update={"shares": shares})], labeled_batches=labeled
    )
    return line.entry_before_exit_note


def test_the_w_b2l_rule_on_lines() -> None:
    """補充一 S-3 第 4 點; 風控 2026-11-04 第 5 點: W-B2L on a batch's sells, W-B2LS on S2."""
    labeled = (
        _label(3, MONDAY, 200, open_shares=866),
        _label(1, WEDNESDAY, 666, open_shares=866),
    )
    lines = [
        _SELL,
        buy_line(),  # a buy of the labeled batch
        _SELL.model_copy(update={"batch_no": 2}),  # an unlabeled batch
        _S2.model_copy(update={"shares": 866}),  # S2 of exactly the two labeled batches
        _SELL.model_copy(update={"symbol": "2454", "batch_no": None, "rule_id": "S2"}),
        _SELL.model_copy(update={"action": "defer", "rule_id": "R2"}),
    ]

    built = api_module._lines(lines, labeled_batches=labeled)
    notes = [line.entry_before_exit_note for line in built]

    assert notes == [
        _w_b2l(WEDNESDAY),
        None,
        None,
        _w_b2ls((1, WEDNESDAY, 666), (3, MONDAY, 200), shares=866),
        None,
        None,
    ]
    for note in notes:
        assert_w_b2lsr_follows_w_b2ls(note)
        if note is not None and note.startswith(_W_B2LS_HEAD):
            assert wording.ENTRY_BEFORE_EXIT_NOTE.split("{", 1)[0] not in note  # never W-B2L
    assert all(
        line.line == wording.directive_line(directive)
        for line, directive in zip(built, lines, strict=True)
    )


# --- 補充四釐清七 E-30 第 5 點 (a)～(d): premise P on an S2 line ------------------------


def test_e30a_p_holds_with_and_without_w_b2lsr() -> None:
    """P: ``shares`` == the symbol's open shares in the labels' book, items ≤ ``shares``."""
    exact = (_label(1, WEDNESDAY, 666, open_shares=666),)
    assert _s2_note(666, exact) == _w_b2ls((1, WEDNESDAY, 666), shares=666)
    assert wording.ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE not in str(_s2_note(666, exact))

    more = (_label(1, WEDNESDAY, 666, open_shares=966),)
    note = _s2_note(966, more)
    assert note == _w_b2ls((1, WEDNESDAY, 666), shares=966)
    assert note is not None and note.endswith(wording.ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE)
    assert_w_b2lsr_follows_w_b2ls(note)


@pytest.mark.parametrize(
    ("shares", "labeled", "expected"),
    [
        # shares ≠ the symbol's open shares: an S2 logged on another book (E-28).
        (
            300,
            (_label(1, WEDNESDAY, 666, open_shares=966),),
            ((1, WEDNESDAY, 666),),
        ),
        (
            966,
            (_label(1, WEDNESDAY, 666, open_shares=666),),
            ((1, WEDNESDAY, 666),),
        ),
        # the items add up to more than the line sells.
        (
            300,
            (_label(1, WEDNESDAY, 666, open_shares=300),),
            ((1, WEDNESDAY, 666),),
        ),
        # two items that disagree on the symbol's open shares.
        (
            966,
            (
                _label(1, WEDNESDAY, 666, open_shares=966),
                _label(3, MONDAY, 200, open_shares=866),
            ),
            ((1, WEDNESDAY, 666), (3, MONDAY, 200)),
        ),
        # a zero-share labeled batch is left out of W-B2LSf too.
        (
            300,
            (
                _label(1, WEDNESDAY, 666, open_shares=966),
                _label(2, MONDAY, 0, open_shares=966),
            ),
            ((1, WEDNESDAY, 666),),
        ),
    ],
    ids=[
        "shares-below-holding",
        "shares-above-holding",
        "items-above-shares",
        "split-holding",
        "zero-share-batch-left-out",
    ],
)
def test_e30a_p_fails_and_w_b2lsf_is_rendered(
    shares: int,
    labeled: tuple[LabeledBatch, ...],
    expected: tuple[tuple[int, date, int], ...],
) -> None:
    """風控 E-30 裁示 (δ), 條件 (b): exactly W-B2LSf, never W-B2LSr, never W-B2LS."""
    note = _s2_note(shares, labeled)
    assert note == _w_b2lsf(*expected)
    assert wording.ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE not in note
    assert not note.startswith(_W_B2LS_HEAD)


@pytest.mark.parametrize("shares", [300, 666, 966])
def test_e30_no_item_left_after_the_filter_is_none(shares: int) -> None:
    """風控 E-30 裁示 條件 (c) and 第二節之 2: P failing or holding, no item, no note."""
    zero = (
        _label(1, WEDNESDAY, 0, open_shares=966),
        _label(3, MONDAY, 0, open_shares=966),
    )
    assert _s2_note(shares, zero) is None
    # The batch rows keep their W-B2L: the filter is the S2 branch's only.
    (line,) = api_module._lines([_SELL], labeled_batches=zero)
    assert line.entry_before_exit_note == _w_b2l(WEDNESDAY)


def test_e30_a_zero_share_batch_is_not_counted_when_p_holds() -> None:
    labeled = (
        _label(1, WEDNESDAY, 666, open_shares=666),
        _label(2, MONDAY, 0, open_shares=666),
    )
    assert _s2_note(666, labeled) == _w_b2ls((1, WEDNESDAY, 666), shares=666)


def test_e30b_an_s2_logged_earlier_in_the_day_is_checked_against_this_book(
    tmp_path: Path,
) -> None:
    """E-28 第 2 點 / E-30 第 5 點 (b): run 1 logs S2 for batch 2 alone; a back-filled
    bar then fills batch 1's stamped buy; run 2 lists run 1's S2 line, whose shares
    no longer match the book the labels come from."""
    desk = _desk(tmp_path)
    log_like_before_n172a(desk.store, [buy_line(execution_date=WEDNESDAY)])
    desk.service.emergency_exit(today=TUESDAY)  # EMPTY: stamps the buy
    hold(desk.store, "2330", 2, shares=300)
    crashed = bars("2330", 100.0, {THURSDAY: 80.0})
    desk.prices.seed("2330", [bar for bar in crashed if bar.date != WEDNESDAY])

    first = desk.service.evaluate_today(today=THURSDAY)
    (s2,) = [line for line in first.directives if line.rule_id == "S2"]
    assert s2.shares == 300 and first.labeled_batches == ()

    desk.prices.seed("2330", crashed)  # Wednesday's bar is back
    second = desk.service.evaluate_today(today=THURSDAY)
    desk.service.pinned = THURSDAY
    with _client(desk) as client:
        body = client.get("/api/playbook/today").json()

    assert second.settlement is not None and second.settlement.executed == 1
    (labeled,) = second.labeled_batches
    assert (labeled.batch_no, labeled.remaining_shares, labeled.symbol_open_shares) == (
        1,
        ONE_BUY_SHARES,
        300 + ONE_BUY_SHARES,
    )
    (logged,) = [line for line in second.directives if line.rule_id == "S2"]
    assert logged == s2  # run 1's line, as logged (ADR-0035 Decision 4)
    (line,) = [line for line in body["directives"] if line["directive"]["rule_id"] == "S2"]
    note = line["entry_before_exit_note"]
    assert note == _w_b2lsf((1, WEDNESDAY, ONE_BUY_SHARES))  # 風控 E-30 裁示 條件 (b)
    assert wording.ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE not in note
    (row,) = [row for row in body["snapshot"] if row["batch_no"] == 1]
    assert row["entry_before_exit_note"] == _w_b2l(WEDNESDAY)  # the batch row still says it


def test_e30c_an_s2_line_and_the_labels_of_its_own_book_always_satisfy_p() -> None:
    """E-30 第 5 點 (c), property: random books, the engine's own S2, the same book's labels."""
    rng = random.Random(168)
    checked = 0
    for _ in range(400):
        book: list[BatchState] = []
        for batch_no in (1, 2, 3):
            status = rng.choice(["open", "open", "planned", "closed", "skipped"])
            if status == "open":
                shares = rng.randint(1, 900)
                state = helper.batch(
                    batch_no=batch_no,
                    cost=str(rng.randint(50, 200)),
                    shares=shares,
                    remaining=rng.choice([0, rng.randint(1, shares)]),
                )
                if rng.random() < 0.6:
                    state = state.model_copy(update={"entry_before_exit_on": TUESDAY})
            else:
                state = helper.batch(batch_no=batch_no, status=status, cost=None, shares=0)
            book.append(state)
        evaluation = engine_module.evaluate(
            data_date=TUESDAY,
            calendar=helper.calendar(),
            params=helper.params(),
            index=helper.index(),
            markets={"2330": helper.market(close="10")},
            batches=book,
            symbols={},
            portfolio=helper.portfolio(),
        )
        lines = [line for line in evaluation.directives if line.rule_id == "S2"]
        labeled = service_module.labeled_batches_of(book)
        listed = [batch for batch in labeled if batch.remaining_shares > 0]
        if not lines or not listed:
            continue
        (s2,) = lines
        note = service_module.entry_before_exit_note(
            s2.symbol, None, labeled_batches=labeled, shares=s2.shares
        )
        assert note is not None and note.startswith(_W_B2LS_HEAD), book
        assert_w_b2lsr_follows_w_b2ls(note)
        checked += 1
    assert checked > 50


def test_e30d_the_batch_rows_never_reach_the_s2_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """E-30 第 1 點 / E-31 第 2 點: ``_labeled_snapshot`` always passes an int batch_no."""
    seen: list[int | None] = []
    real = service_module.entry_before_exit_note

    def spy(symbol: str, batch_no: int | None, **kwargs: Any) -> str | None:
        seen.append(batch_no)
        return real(symbol, batch_no, **kwargs)

    monkeypatch.setattr(service_module, "entry_before_exit_note", spy)
    labeled = (_label(1, WEDNESDAY, 666, open_shares=966),)
    rows = engine_module._snapshot_rows(
        [
            helper.batch(batch_no=1, shares=666).model_copy(
                update={"entry_before_exit_on": TUESDAY}
            ),
            helper.batch(batch_no=2, shares=300),
        ],
        {},
    )

    service_module._labeled_snapshot(rows, labeled)

    assert seen == [1]
    assert BatchSnapshot.model_fields["batch_no"].annotation is int
    tree = ast.parse(inspect.cleandoc("\n" + inspect.getsource(service_module._labeled_snapshot)))
    (call,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "entry_before_exit_note"
    ]
    assert isinstance(call.args[1], ast.Attribute) and call.args[1].attr == "batch_no"


def test_e30_the_s2_branch_never_raises_or_asserts() -> None:
    """E-30 第 4 點 / 風控 E-30 裁示 條件 (d): no ``raise`` and no ``assert`` in the rule."""
    for function in (service_module.entry_before_exit_note, service_module._listed_on_an_s2_line):
        tree = ast.parse(inspect.cleandoc("\n" + inspect.getsource(function)))
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Raise | ast.Assert)]


def test_e30_6_an_exact_offset_is_the_accepted_residue(tmp_path: Path) -> None:
    """風控 E-30 裁示第二節之 3 (b): a known residue, not a bug, pinned.

    Run 1 logs S2 over batches 2 and 3 (300 + 666). Between the two runs of the
    day the back-filled Wednesday bar fills labeled batch 1 (666) and an S1 sells
    batch 3 (666) out: the book's open shares are 966 again, so P holds and
    run 1's line gets W-B2LS -- although it was computed without batch 1.
    """
    desk = _desk(tmp_path)
    log_like_before_n172a(desk.store, [buy_line(execution_date=WEDNESDAY)])
    desk.service.emergency_exit(today=TUESDAY)  # EMPTY: stamps batch 1's buy
    hold(desk.store, "2330", 2, shares=300)
    hold(desk.store, "2330", 3, shares=ONE_BUY_SHARES)
    stop = buy_line(batch_no=3, execution_date=WEDNESDAY).model_copy(
        update={"action": "sell", "rule_id": "S1", "limit_low": None, "limit_high": None}
    )
    log_like_before_n172a(desk.store, [stop])
    crashed = bars("2330", 100.0, {THURSDAY: 80.0})
    desk.prices.seed("2330", [bar for bar in crashed if bar.date != WEDNESDAY])

    first = desk.service.evaluate_today(today=THURSDAY)
    (s2,) = [line for line in first.directives if line.rule_id == "S2"]
    assert s2.shares == 300 + ONE_BUY_SHARES

    desk.prices.seed("2330", crashed)
    desk.service.pinned = THURSDAY
    with _client(desk) as client:
        body = client.get("/api/playbook/today").json()

    batch_3 = desk.store.get_batch("2330", 3)
    assert batch_3 is not None and batch_3.status == "closed"
    (line,) = [line for line in body["directives"] if line["directive"]["rule_id"] == "S2"]
    assert line["directive"]["shares"] == s2.shares
    assert line["entry_before_exit_note"] == _w_b2ls(
        (1, WEDNESDAY, ONE_BUY_SHARES), shares=300 + ONE_BUY_SHARES
    )


def _crash(desk: Desk, day: date, close: float) -> None:
    """2330 closes at ``close`` on ``day``: below 均成本 × 0.85 fires S2 (engine.py S2)."""
    desk.prices.seed("2330", bars("2330", 100.0, {day: close}))


def test_ii_an_s2_line_of_this_evaluation_covers_its_labeled_batches(tmp_path: Path) -> None:
    """風控 2026-11-04 第 5 點 (i)(ii): this run's S2 is computed on ``book``, the same
    book the labels come from, so their ``remaining_shares`` never exceed its shares."""
    desk, _ = _labeled_desk(tmp_path)
    desk.service.evaluate_today(today=WEDNESDAY)  # batch 1 open, labeled, 666 shares
    hold(desk.store, "2330", 3, shares=300)  # and an unlabeled one
    _crash(desk, THURSDAY, 80.0)

    run = desk.service.evaluate_today(today=THURSDAY)
    with _client(desk) as client:
        desk.service.pinned = THURSDAY
        body = client.get("/api/playbook/today").json()

    (s2,) = [line for line in run.directives if line.rule_id == "S2"]
    assert s2.batch_no is None and s2.shares == 966
    held = {(batch.symbol, batch.batch_no): batch for batch in desk.store.list_batches()}
    labeled = [batch for batch in run.labeled_batches if batch.symbol == s2.symbol]
    assert sum(held[(batch.symbol, batch.batch_no)].remaining_shares for batch in labeled) <= (
        s2.shares
    )
    (line,) = [line for line in body["directives"] if line["directive"]["rule_id"] == "S2"]
    assert line["entry_before_exit_note"] == _w_b2ls((1, WEDNESDAY, 666), shares=966)
    assert_w_b2lsr_follows_w_b2ls(line["entry_before_exit_note"])
    assert_labels_carry_their_note(body["snapshot"])


def test_ii_an_s2_line_of_only_labeled_batches_gets_no_rest_sentence(tmp_path: Path) -> None:
    desk, _ = _labeled_desk(tmp_path)
    desk.service.evaluate_today(today=WEDNESDAY)
    _crash(desk, THURSDAY, 80.0)

    with _client(desk) as client:
        desk.service.pinned = THURSDAY
        body = client.get("/api/playbook/today").json()

    (line,) = [line for line in body["directives"] if line["directive"]["rule_id"] == "S2"]
    assert line["directive"]["shares"] == ONE_BUY_SHARES
    assert line["entry_before_exit_note"] == _w_b2ls((1, WEDNESDAY, ONE_BUY_SHARES), shares=666)
    assert wording.ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE not in line["entry_before_exit_note"]


def test_e11_w_b2l_is_rendered_by_one_rule_only() -> None:
    """QB-13 as 補充四釐清六 E-26 第 4 點 words it: AST only, docstrings and comments
    aside. The W-B2L family is read in ``entry_before_exit_note`` alone, which is
    called exactly twice in ``app/`` -- ``_lines`` and ``_labeled_snapshot`` -- and
    never from N-171's code (第 3 點)."""
    app_root = Path(wording.__file__).resolve().parents[1]
    family = {
        "ENTRY_BEFORE_EXIT_NOTE",
        "ENTRY_BEFORE_EXIT_SYMBOL_NOTE",
        "ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE",
        "ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE",
    }
    readers: list[tuple[str, str, str]] = []
    calls: list[tuple[str, str]] = []
    for path in sorted(app_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

        def owner_of(node: ast.AST, parents: dict[ast.AST, ast.AST] = parents) -> str:
            while node in parents and not isinstance(node, ast.FunctionDef):
                node = parents[node]
            return node.name if isinstance(node, ast.FunctionDef) else ""

        where = path.relative_to(app_root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in family:
                readers.append((where, owner_of(node), node.attr))
            if isinstance(node, ast.Call) and (
                getattr(node.func, "id", None) == "entry_before_exit_note"
                or getattr(node.func, "attr", None) == "entry_before_exit_note"
            ):
                calls.append((where, owner_of(node)))
    assert sorted(readers) == sorted(
        ("playbook/service.py", "entry_before_exit_note", name) for name in family
    )
    assert sorted(calls) == [
        ("api/playbook.py", "_lines"),
        ("playbook/service.py", "_labeled_snapshot"),
    ]


def test_e26_both_callers_get_the_one_labeled_tuple_of_the_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E-26 第 2 點: on ``/today`` the batch row and the sell lines use the very tuple
    written into ``evaluation.labeled_batches``."""
    desk, _ = _labeled_desk(tmp_path)
    desk.service.evaluate_today(today=WEDNESDAY)
    desk.service.emergency_exit(today=THURSDAY)  # a pending sell on labeled batch 1
    real = service_module.entry_before_exit_note
    seen: list[tuple[int | None, int]] = []

    def spy(symbol: str, batch_no: int | None, **kwargs: Any) -> str | None:
        seen.append((batch_no, id(kwargs["labeled_batches"])))
        return real(symbol, batch_no, **kwargs)

    monkeypatch.setattr(service_module, "entry_before_exit_note", spy)
    monkeypatch.setattr(api_module, "entry_before_exit_note", spy)
    desk.service.pinned = THURSDAY
    with _client(desk) as client:
        body = client.get("/api/playbook/today").json()

    assert [line["directive"]["batch_no"] for line in body["pending_exit_directives"]] == [1]
    assert len(seen) >= 2 and len({identity for _, identity in seen}) == 1


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


_LABEL_KEYS = ("entry_before_exit_on", "entry_before_exit_label", "entry_before_exit_note")
_LINE_LISTS = (
    "directives",
    "pending_directives",
    "pending_exit_directives",
    "entry_before_exit_directives",
    "entry_before_exit_blocked_directives",
)


def test_e24_the_label_keys_on_the_golden_scenarios(
    golden_bodies: dict[str, dict[str, Any]],
) -> None:
    """補充四釐清六 E-24 第 3 點 (BLOCKING; not a ``filled`` entry): T2 drops these keys,
    so they are pinned here, on all nine responses, by exact value.

    (a) Only ``after_exit.today_next_day``'s batch 1 -- whose stamped R1 buy the
        2026-08-12 settlement filled -- carries the label, stamped with the
        exit's as_of (2026-08-11), W-B2, and W-B2L for its entry_date.
    (b) No ``DirectiveLine`` of any response carries a note: the golden has no
        sell line of a labeled batch (E-8 as E-24 第 4 點 rereads it).
    """
    responses = [
        (scenario, name, body)
        for scenario, bodies in golden_bodies.items()
        for name, body in bodies.items()
    ]
    assert len(responses) == 9
    labeled_rows = []
    for scenario, name, body in responses:
        for row in body.get("snapshot", []):
            values = tuple(row[key] for key in _LABEL_KEYS)
            if (scenario, name, row["symbol"], row["batch_no"]) == (
                "after_exit",
                "today_next_day",
                "2330",
                1,
            ):
                labeled_rows.append(row)
                assert row["status"] == "open" and row["entry_date"] == WEDNESDAY.isoformat()
                assert values == (
                    TUESDAY.isoformat(),
                    wording.ENTRY_BEFORE_EXIT_LABEL,
                    wording.ENTRY_BEFORE_EXIT_NOTE.format(entry_date=WEDNESDAY.isoformat()),
                )
            else:
                assert values == (None, None, None), (scenario, name, row["batch_no"])
        assert_labels_carry_their_note(body.get("snapshot", []))
        for key in _LINE_LISTS:
            for line in body.get(key, []):
                assert line["entry_before_exit_note"] is None, (scenario, name, key)
        block = body.get("pending_exit_block")
        for section in [] if block is None else block["sections"]:
            for row in section["rows"]:
                assert row["entry_before_exit_note"] is None, (scenario, name)
        if "message" in body:
            assert_w_b1p_follows_w_b1(body["message"])
    assert len(labeled_rows) == 1


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
