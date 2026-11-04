"""N171-C17′ and C21: ``POST /settle`` is gated on authorship, and authorship only rises.

ADR-0039 補充一 S-3 (C17′, T18′) and S-6 (C21, T28); 風控 2026-11-04 第 2 點.

* T18′ -- with no user rule set, ``POST /api/playbook/settle`` answers 200 with an
  empty settlement whose only warning is ``SETTLEMENT_UNAUTHORED_NOTE``; it
  claims, loads and writes nothing; the authorship read comes first. ``/today``
  never carries the sentence and never calls ``settle_on_request``. Authored,
  the endpoint is ``settle_pending`` unchanged.
* T28 -- the premise A-13, P-5(b) and C17′ rest on: ``user_authored`` only goes
  from false to true and does not depend on the date asked about.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.api import playbook as api_module
from app.playbook import service as service_module
from app.playbook import store as store_module
from app.playbook import wording
from app.playbook.models import SettlementResult
from app.playbook.service import PlaybookService
from app.playbook.store import (
    STATE_RULE_SET_CONFIRMED_AT,
    STATE_RULE_SET_VERSION,
    PlaybookStore,
)
from tests.exit_idempotency_helpers import legacy_exit_line, log_like_before_n166
from tests.playbook_helpers import confirm_rule_set, params
from tests.same_day_helpers import (
    TUESDAY,
    WEDNESDAY,
    Desk,
    hold,
    log_rows,
)
from tests.seam_helpers import clocked_desk, serving

APP_ROOT = Path(api_module.__file__).resolve().parents[1]
WRITES = ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER")


def _pinned(desk: Desk, day: date) -> None:
    """Pin ``settle_on_request``'s clock too, for the HTTP path."""
    real = desk.service.settle_on_request

    def settle_on_request(*, today: date | None = None) -> SettlementResult:
        return real(today=today or day)

    desk.service.settle_on_request = settle_on_request  # type: ignore[method-assign]


def _unauthored_with_a_due_exit(db_path: Path) -> Desk:
    """No rule set; a held batch with an EMERGENCY sell due (and priced) on Wednesday."""
    desk = clocked_desk(db_path, seed=False)
    desk.store.ensure_batches(["2330"], batches_per_target=3)
    hold(desk.store, "2330", 1)
    log_like_before_n166(desk.store, [legacy_exit_line("2330", 300, execution_date=WEDNESDAY)])
    return desk


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


def _writes(statements: list[str]) -> list[str]:
    return [sql for sql in statements if sql.lstrip().upper().startswith(WRITES)]


# --- T18′: the unauthored answer ----------------------------------------------------------


def test_unauthored_settle_answers_200_with_the_note_alone(
    tmp_path: Path, traced: list[str]
) -> None:
    desk = _unauthored_with_a_due_exit(tmp_path / "playbook.db")
    _pinned(desk, WEDNESDAY)
    before = log_rows(tmp_path / "playbook.db")
    traced.clear()

    with serving(desk) as client:
        response = client.post("/api/playbook/settle")

    assert response.status_code == 200
    body = response.json()
    assert body["settled_on"] == WEDNESDAY.isoformat()
    assert (body["executed"], body["missed"]) == (0, 0)
    assert body["settled"] == [] and body["unsettled"] == []
    assert body["warnings"] == [wording.SETTLEMENT_UNAUTHORED_NOTE]
    for other in (wording.SETTLEMENT_NOTHING_PENDING, wording.SETTLEMENT_SUMMARY[:6]):
        assert other not in body["warnings"]
    assert not any(text.startswith("T+1 結算：依") for text in body["warnings"])
    # Zero writes, zero loads, nothing claimed: the exit line is still pending.
    assert _writes(traced) == []
    assert all(
        sql.lstrip().upper().startswith(("SELECT", "PRAGMA", "BEGIN", "COMMIT")) for sql in traced
    )
    assert desk.prices.calls == [] and desk.index.calls == []
    assert log_rows(tmp_path / "playbook.db") == before
    assert len(desk.store.pending_directives()) == 1


def test_unauthored_settle_reads_authorship_before_anything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = _unauthored_with_a_due_exit(tmp_path / "playbook.db")
    calls: list[str] = []
    store = desk.store
    for name in (
        "rule_set_authorship",
        "pending_directives",
        "claim_directive",
        "settle",
        "get_batch",
    ):
        real = getattr(store, name)

        def spy(*args: Any, _real: Any = real, _name: str = name, **kwargs: Any) -> Any:
            calls.append(_name)
            return _real(*args, **kwargs)

        monkeypatch.setattr(store, name, spy)
    monkeypatch.setattr(
        desk.service, "_settle_pending", lambda as_of: pytest.fail("settled while unauthored")
    )

    result = desk.service.settle_on_request(today=WEDNESDAY)

    assert calls == ["rule_set_authorship"]
    assert result.warnings == [wording.SETTLEMENT_UNAUTHORED_NOTE]
    assert (result.executed, result.missed, result.settled, result.unsettled) == (0, 0, [], [])


def test_the_authorship_read_is_evaluate_todays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same store call, same ``as_of``, on both entry points."""
    desk = _unauthored_with_a_due_exit(tmp_path / "playbook.db")
    asked: list[date] = []
    real = desk.store.rule_set_authorship

    def spy(on_date: date) -> Any:
        asked.append(on_date)
        return real(on_date)

    monkeypatch.setattr(desk.store, "rule_set_authorship", spy)
    desk.service.settle_on_request(today=WEDNESDAY)
    desk.service.evaluate_today(today=WEDNESDAY)
    assert asked == [WEDNESDAY, WEDNESDAY]


# --- T18′: authored, unchanged ------------------------------------------------------------


def test_authored_settle_on_request_is_settle_pending(tmp_path: Path) -> None:
    """Two identical authored books: the gated method on one, the public one on the other."""
    results: list[SettlementResult] = []
    rows: list[list[tuple[Any, ...]]] = []
    for name in ("gated", "plain"):
        desk = clocked_desk(tmp_path / f"{name}.db")
        hold(desk.store, "2330", 1)
        log_like_before_n166(
            desk.store,
            [
                legacy_exit_line("2330", 300, execution_date=WEDNESDAY),
                legacy_exit_line("2330", 300, execution_date=date(2026, 8, 20)),  # not due
            ],
        )
        if name == "gated":
            results.append(desk.service.settle_on_request(today=WEDNESDAY))
        else:
            results.append(desk.service.settle_pending(today=WEDNESDAY))
        rows.append(log_rows(tmp_path / f"{name}.db"))
    gated, plain = results
    gated_rows, plain_rows = rows
    assert gated == plain
    assert [row[5] for row in gated_rows] == [row[5] for row in plain_rows]
    assert isinstance(gated, SettlementResult) and gated.executed == 1
    assert wording.SETTLEMENT_UNAUTHORED_NOTE not in gated.warnings


def test_authored_post_settle_is_unchanged(tmp_path: Path) -> None:
    desk = clocked_desk(tmp_path / "playbook.db")
    hold(desk.store, "2330", 1)
    log_like_before_n166(desk.store, [legacy_exit_line("2330", 300, execution_date=WEDNESDAY)])
    _pinned(desk, WEDNESDAY)

    with serving(desk) as client:
        body = client.post("/api/playbook/settle").json()
        again = client.post("/api/playbook/settle").json()

    assert body["executed"] == 1 and body["settled"][0]["directive"]["rule_id"] == "EMERGENCY"
    assert again["warnings"] == [wording.SETTLEMENT_NOTHING_PENDING]
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.status == "closed"


# --- T18′: /today never carries it ---------------------------------------------------------


def test_today_never_carries_the_note_and_never_calls_settle_on_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = _unauthored_with_a_due_exit(tmp_path / "playbook.db")
    monkeypatch.setattr(
        PlaybookService,
        "settle_on_request",
        lambda self, **kwargs: pytest.fail("evaluate_today called settle_on_request"),
    )
    desk.service.pinned = WEDNESDAY

    with serving(desk) as client:
        unauthored = client.get("/api/playbook/today").json()
        confirm_rule_set(desk.store)
        authored = client.get("/api/playbook/today").json()

    assert unauthored["mode"] == "unconfirmed" and unauthored["settlement"] is None
    assert authored["settlement"] is not None
    for body in (unauthored, authored):
        assert json.dumps(body, ensure_ascii=False).count(wording.SETTLEMENT_UNAUTHORED_NOTE) == 0


def test_evaluate_today_does_not_reference_settle_on_request() -> None:
    tree = ast.parse(Path(service_module.__file__).read_text(encoding="utf-8"))
    (evaluate,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"evaluate_today"}
    ]
    names = {node.attr for node in ast.walk(evaluate) if isinstance(node, ast.Attribute)} | {
        node.id for node in ast.walk(evaluate) if isinstance(node, ast.Name)
    }
    assert "settle_on_request" not in names


def test_nothing_under_app_api_calls_settle_pending_directly() -> None:
    offenders: list[str] = []
    for path in sorted((APP_ROOT / "api").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "settle_pending(" in source:
            offenders.append(path.name)
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"settle_pending", "_settle_pending"}
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
    assert "service.settle_on_request()" in inspect.getsource(api_module.settle)


# --- T28 / C21: authorship is monotone and date-free ---------------------------------------


def _app_sources() -> Iterator[tuple[Path, str]]:
    for path in sorted(APP_ROOT.rglob("*.py")):
        yield path, path.read_text(encoding="utf-8")


def _string_literals(source: str) -> Iterator[str]:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def test_c21_rule_params_rows_are_never_deleted_and_no_playbook_table_is_dropped() -> None:
    for path, source in _app_sources():
        for text in _string_literals(source):
            normalized = " ".join(text.upper().split())
            assert "DELETE FROM PLAYBOOK_RULE_PARAMS" not in normalized, path
            if "DROP" in normalized.split():
                assert "PLAYBOOK" not in normalized, path
    for path in (APP_ROOT / "playbook").rglob("*.py"):
        for text in _string_literals(path.read_text(encoding="utf-8")):
            assert not re.search(r"\bDROP\s+(TABLE|INDEX|VIEW)\b", text.upper()), path
    # The one DELETE the playbook store runs is _write_state's, on playbook_state.
    store_source = Path(store_module.__file__).read_text(encoding="utf-8")
    deletes = [
        text
        for text in _string_literals(store_source)
        if text.lstrip().upper().startswith("DELETE")
    ]
    assert deletes == ["DELETE FROM playbook_state WHERE key = ?"]


def test_c21_the_confirmation_keys_are_written_in_confirm_rule_set_only_and_never_as_none() -> None:
    keys = {"STATE_RULE_SET_CONFIRMED_AT", "STATE_RULE_SET_VERSION"}
    literal_values = {STATE_RULE_SET_CONFIRMED_AT, STATE_RULE_SET_VERSION}
    writers: list[str] = []
    for path, source in _app_sources():
        # The raw key strings appear only where the constants are defined.
        for text in _string_literals(source):
            if text in literal_values:
                assert path.name == "store.py", path
        tree = ast.parse(source)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Name) and node.id in keys):
                continue
            owner: ast.AST = node
            while owner in parents and not isinstance(owner, ast.FunctionDef):
                owner = parents[owner]
            function = owner.name if isinstance(owner, ast.FunctionDef) else "<module>"
            parent = parents.get(node)
            if isinstance(parent, ast.Dict) and node in parent.keys:
                value = parent.values[parent.keys.index(node)]
                assert not (isinstance(value, ast.Constant) and value.value is None), path
                writers.append(f"{path.name}:{function}")
            elif function == "<module>":
                assert isinstance(parent, ast.Assign), path  # the definitions
            else:
                # Reads only: ``state.get(KEY)`` or ``KEY in state``.
                assert function == "rule_set_authorship", (path, function)
                assert isinstance(parent, ast.Call | ast.Compare), (path, function)
    assert sorted(writers) == ["store.py:confirm_rule_set", "store.py:confirm_rule_set"]


def _authorship_over(store: PlaybookStore, days: list[date]) -> set[bool]:
    return {store.rule_set_authorship(day).user_authored for day in days}


def test_c21_user_authored_is_the_same_for_any_two_dates_and_only_rises(tmp_path: Path) -> None:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    days = [date(2000, 1, 1), TUESDAY - timedelta(days=400), TUESDAY, WEDNESDAY]
    days += [TUESDAY + timedelta(days=step * 37) for step in range(1, 12)]
    seen: list[bool] = []

    assert _authorship_over(store, days) == {False}  # fresh book
    seen.append(False)

    # A rule change dated in the future is an authorship record from day one.
    store.submit_rule_change(params(version=2, effective_date=date(2030, 1, 1)))
    assert _authorship_over(store, days) == {True}
    seen.append(True)

    other = PlaybookStore(db_path=tmp_path / "confirmed.db")
    assert _authorship_over(other, days) == {False}
    confirm_rule_set(other)
    assert _authorship_over(other, days) == {True}
    # Every later write the playbook makes leaves it true.
    hold(other, "2330", 1)
    log_like_before_n166(other, [legacy_exit_line("2330", 300, execution_date=WEDNESDAY)])
    cash = other.portfolio_state().cash
    other.set_capital(cash=cash, total_deploy=cash, source="test")
    confirm_rule_set(other)
    assert _authorship_over(other, days) == {True}
    seen.append(True)
    assert seen == sorted(seen)  # false -> true, never back


# --- the sentence itself -------------------------------------------------------------------


def test_the_settlement_unauthored_note_is_the_signed_off_text_verbatim() -> None:
    """風控 2026-11-04 第 2 點，逐字定稿；無佔位符、不含禁用詞、有「本系統不下單」."""
    assert wording.SETTLEMENT_UNAUTHORED_NOTE == (
        "T+1 結算：目前尚無你本人的規則集設定或修改紀錄，本次未執行結算，"
        "也未載入日線資料；本回應的成交筆數與未成交（MISSED）筆數為 0、"
        "已結算與未結算清單皆為空，是因為未執行結算，不代表目前沒有待結算指令。"
        "若你先前提交全部出清時已產生賣出指令，在你確認規則集之前，"
        "帳冊不會依預定執行日開盤價判定它們，它們維持待結算狀態。本系統不下單，"
        "無法得知你是否已在券商下單或成交，實際持股以你的券商回報為準。"
    )
    note = wording.SETTLEMENT_UNAUTHORED_NOTE
    assert "{" not in note and "本系統不下單" in note
    # 「本回應」 is the noun 回應 (the response), not the modal 應; exempted
    # verbatim and exactly once, the way 風控 2026-11-04 第 9 點 narrows an
    # exemption, and 應 must not appear anywhere else.
    assert note.count("本回應") == 1
    stripped = note.replace("本回應", "")
    for banned in BANNED:
        assert banned not in stripped, banned


#: 風控 2026-11-03 第二節之 2 禁用詞（2026-11-04 新字面同一份清單）.
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
    "建議",
)
