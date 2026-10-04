"""ADR-0016 D-5.2 / K-18 / K-19 / T-13: the main DB's sync record.

Every database lives under ``tmp_path``; the adapter is either a stub or the real
adapter over ``httpx.MockTransport``. Nothing touches the development DB or the
network.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.dividends.models import DividendEvent
from app.dividends.providers import TWSE_OPENAPI_BASE_URL, DividendFetchResult, TwseDividendAdapter
from app.dividends.store import DividendEventStore
from app.dividends.sync import sync_dividends

FIXTURES_DIR = Path(__file__).parent / "fixtures"
AS_OF = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
CLOCK_NOW = datetime(2026, 10, 1, 13, 30, 15, 123456, tzinfo=UTC)

_RUN_COLUMNS = (
    "run_id, recorded_at, trigger, source, status, event_count, unparsed_count, "
    "unattributed_count, reason"
)


def _event(symbol: str = "2330", ex_date: date = date(2026, 10, 20)) -> DividendEvent:
    return DividendEvent(
        symbol=symbol,
        market="TW",
        ex_date=ex_date,
        cash_dividend=Decimal("1.5"),
        source="stub",
        as_of=AS_OF,
    )


class _Stub:
    """An adapter that returns a canned result."""

    def __init__(self, result: DividendFetchResult) -> None:
        self.result = result

    def fetch(self) -> DividendFetchResult:
        return self.result


def _ok(
    events: list[DividendEvent],
    *,
    unparsed: tuple[str, ...] = (),
    unattributed: int = 0,
) -> _Stub:
    return _Stub(
        DividendFetchResult(
            events=tuple(events),
            ok=True,
            reason=None,
            source="stub",
            as_of=AS_OF,
            skipped_rows=len(unparsed) + unattributed,
            unparsed_symbols=unparsed,
            unattributed_rows=unattributed,
        )
    )


def _failed(reason: str = "連線失敗（ConnectError）：refused") -> _Stub:
    return _Stub(
        DividendFetchResult(events=(), ok=False, reason=reason, source="stub", as_of=AS_OF)
    )


def _store(tmp_path: Path) -> DividendEventStore:
    return DividendEventStore(tmp_path / "main.db", clock=lambda: CLOCK_NOW)


def _runs(path: Path) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(
            f"SELECT {_RUN_COLUMNS} FROM dividend_sync_runs ORDER BY run_id"
        ).fetchall()


def _unparsed(path: Path) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(
            "SELECT run_id, symbol FROM dividend_sync_unparsed ORDER BY run_id, symbol"
        ).fetchall()


def _add_trigger(path: Path, table: str, name: str) -> None:
    """Make every INSERT into ``table`` fail, to break a write half way through."""
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            f"CREATE TRIGGER {name} BEFORE INSERT ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )


# ---------------------------------------------------------------- schema (K-19)


def test_the_schema_matches_the_adr_and_avoids_the_pit_prefix(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with closing(sqlite3.connect(store.db_path)) as conn:
        runs_columns = [
            (name, ctype, notnull, pk)
            for _, name, ctype, notnull, _, pk in conn.execute(
                "PRAGMA table_info(dividend_sync_runs)"
            )
        ]
        unparsed_columns = [
            (name, ctype, notnull, pk)
            for _, name, ctype, notnull, _, pk in conn.execute(
                "PRAGMA table_info(dividend_sync_unparsed)"
            )
        ]
        indexes = {
            name: [col[2] for col in conn.execute(f"PRAGMA index_info({name})")]
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='dividend_sync_runs' AND name NOT LIKE 'sqlite_%'"
            )
        }
        unparsed_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='dividend_sync_unparsed'"
        ).fetchone()[0]
        runs_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='dividend_sync_runs'"
        ).fetchone()[0]
        tables = {
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert runs_columns == [
        ("run_id", "INTEGER", 0, 1),
        ("recorded_at", "TEXT", 1, 0),
        ("trigger", "TEXT", 1, 0),
        ("source", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0),
        ("event_count", "INTEGER", 1, 0),
        ("unparsed_count", "INTEGER", 1, 0),
        ("unattributed_count", "INTEGER", 1, 0),
        ("reason", "TEXT", 0, 0),
    ]
    assert unparsed_columns == [("run_id", "INTEGER", 1, 1), ("symbol", "TEXT", 1, 2)]
    assert indexes == {"idx_dividend_sync_runs_status_recorded": ["status", "recorded_at"]}
    assert "AUTOINCREMENT" in runs_sql
    assert "WITHOUT ROWID" in unparsed_sql
    assert not any(name.startswith("pit_") for name in tables)
    assert {"dividend_sync_runs", "dividend_sync_unparsed"} <= tables


def test_the_check_constraints_refuse_unknown_trigger_and_status(tmp_path: Path) -> None:
    store = _store(tmp_path)
    insert = (
        "INSERT INTO dividend_sync_runs (recorded_at, trigger, source, status, event_count, "
        "unparsed_count, unattributed_count) VALUES ('t', ?, 's', ?, 0, 0, 0)"
    )
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute(insert, ("cli", "ok"))
        for trigger, status in (("manual", "ok"), ("cli", "partial")):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(insert, (trigger, status))


def test_reopening_the_store_is_idempotent(tmp_path: Path) -> None:
    first = _store(tmp_path)
    sync_dividends(store=first, adapter=_ok([_event()]))
    second = DividendEventStore(first.db_path)
    assert len(_runs(second.db_path)) == 1


# --------------------------------------------------------------- writes (K-18)


def test_a_successful_sync_writes_one_ok_run_and_the_events(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sync_dividends(
        store=store,
        adapter=_ok(
            [_event("2330"), _event("2317")], unparsed=("9999", "9999", "00981a"), unattributed=2
        ),
        synced_at=AS_OF,
    )
    assert store.count() == 2
    assert _runs(store.db_path) == [
        (1, "2026-10-01T13:30:15.123456+00:00", "cli", "stub", "ok", 2, 3, 2, None)
    ]
    # One row per distinct normalized code; the count still counts rows.
    assert _unparsed(store.db_path) == [(1, "00981A"), (1, "9999")]


def test_the_scheduled_trigger_is_recorded(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sync_dividends(store=store, adapter=_ok([_event()]), trigger="scheduled")
    sync_dividends(store=store, adapter=_ok([_event()]))
    assert [row[2] for row in _runs(store.db_path)] == ["scheduled", "cli"]


def test_run_ids_increase_and_are_never_reused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for _ in range(3):
        sync_dividends(store=store, adapter=_ok([_event()]))
    assert [row[0] for row in _runs(store.db_path)] == [1, 2, 3]


def test_an_adapter_failure_is_a_failed_run_and_leaves_events_unchanged(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sync_dividends(store=store, adapter=_ok([_event("2330")]))
    assert store.count() == 1
    result = sync_dividends(store=store, adapter=_failed("boom"))
    assert result.ok is False
    assert store.count() == 1
    runs = _runs(store.db_path)
    assert runs[1][4:] == ("failed", 0, 0, 0, "boom")


def test_ok_without_events_is_failed_not_ok(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sync_dividends(store=store, adapter=_ok([], unparsed=("9999",)))
    ((_, _, _, _, status, event_count, unparsed_count, _, reason),) = _runs(store.db_path)
    assert (status, event_count, unparsed_count) == ("failed", 0, 1)
    assert reason is not None
    assert store.count() == 0


def test_a_failure_while_writing_the_run_rolls_the_events_back(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sync_dividends(store=store, adapter=_ok([_event("2330")]))
    _add_trigger(store.db_path, "dividend_sync_runs", "boom_runs")
    with pytest.raises(sqlite3.DatabaseError, match="injected failure"):
        sync_dividends(
            store=store, adapter=_ok([_event("2317"), _event("2454")], unparsed=("9999",))
        )
    assert store.count() == 1  # the second batch did not land
    assert store.events_for("2317", "TW") == []
    assert len(_runs(store.db_path)) == 1


def test_a_failure_while_writing_unparsed_symbols_rolls_everything_back(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _add_trigger(store.db_path, "dividend_sync_unparsed", "boom_unparsed")
    with pytest.raises(sqlite3.DatabaseError, match="injected failure"):
        sync_dividends(store=store, adapter=_ok([_event("2317")], unparsed=("9999",)))
    assert store.count() == 0
    assert _runs(store.db_path) == []
    assert _unparsed(store.db_path) == []


def test_a_failure_while_writing_events_leaves_no_run(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute(
            "CREATE TRIGGER boom_events BEFORE INSERT ON dividend_events "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
    with pytest.raises(sqlite3.DatabaseError, match="injected failure"):
        sync_dividends(store=store, adapter=_ok([_event()]))
    assert _runs(store.db_path) == []


def test_the_write_lock_is_taken_up_front(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # BEGIN IMMEDIATE: while another writer holds the lock, a sync is refused before
    # it changes anything -- neither the events nor the run row land.
    store = DividendEventStore(tmp_path / "main.db", clock=lambda: CLOCK_NOW)
    # A short busy timeout so the refused writer gives up quickly.
    monkeypatch.setattr("app.dividends.store.BUSY_TIMEOUT_MS", 50)
    blocker = sqlite3.connect(store.db_path, isolation_level=None)
    try:
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked|busy"):
            sync_dividends(store=store, adapter=_ok([_event()], unparsed=("9999",)))
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert store.count() == 0
    assert _runs(store.db_path) == []
    assert _unparsed(store.db_path) == []
    # Once the lock is released the same call goes through.
    sync_dividends(store=store, adapter=_ok([_event()]))
    assert len(_runs(store.db_path)) == 1


def test_the_clock_is_read_only_after_the_write_lock_is_held(tmp_path: Path) -> None:
    # A clock that cannot be read while another writer holds the lock proves the
    # order: the sync is refused (locked) without ever calling the clock.
    calls: list[int] = []

    def clock() -> datetime:
        calls.append(1)
        return CLOCK_NOW

    store = DividendEventStore(tmp_path / "main.db", clock=clock)
    blocker = sqlite3.connect(store.db_path, isolation_level=None)
    try:
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("app.dividends.store.BUSY_TIMEOUT_MS", 50)
            with pytest.raises(sqlite3.OperationalError):
                sync_dividends(store=store, adapter=_ok([_event()]))
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert calls == []
    sync_dividends(store=store, adapter=_ok([_event()]))
    assert calls == [1]


def test_recorded_at_comes_from_the_store_clock_only(tmp_path: Path) -> None:
    ticks = iter(
        [
            datetime(2026, 10, 1, 21, 30, tzinfo=UTC),
            datetime(2026, 10, 2, 7, 0, 0, 5, tzinfo=UTC),
        ]
    )
    store = DividendEventStore(tmp_path / "main.db", clock=lambda: next(ticks))
    # ``synced_at`` stamps the event rows, never the run.
    sync_dividends(store=store, adapter=_ok([_event()]), synced_at=datetime(2001, 1, 1, tzinfo=UTC))
    sync_dividends(store=store, adapter=_ok([_event()]))
    assert [row[1] for row in _runs(store.db_path)] == [
        "2026-10-01T21:30:00.000000+00:00",
        "2026-10-02T07:00:00.000005+00:00",
    ]


def test_no_write_path_accepts_a_recorded_at_from_the_caller(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(TypeError):
        sync_dividends(  # type: ignore[call-arg]
            store=store, adapter=_ok([_event()]), recorded_at=AS_OF
        )
    with pytest.raises(TypeError):
        store.record_sync(  # type: ignore[call-arg]
            trigger="cli",
            source="s",
            adapter_ok=True,
            reason=None,
            events=[_event()],
            recorded_at=AS_OF,
        )


def test_a_clock_in_another_zone_is_stored_as_utc(tmp_path: Path) -> None:
    from zoneinfo import ZoneInfo

    taipei = datetime(2026, 10, 2, 5, 30, tzinfo=ZoneInfo("Asia/Taipei"))
    store = DividendEventStore(tmp_path / "main.db", clock=lambda: taipei)
    sync_dividends(store=store, adapter=_ok([_event()]))
    assert _runs(store.db_path)[0][1] == "2026-10-01T21:30:00.000000+00:00"


def test_a_naive_clock_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    store = DividendEventStore(tmp_path / "main.db", clock=lambda: datetime(2026, 10, 1, 21, 30))
    with pytest.raises(ValueError, match="timezone-aware"):
        sync_dividends(store=store, adapter=_ok([_event()]))
    assert store.count() == 0
    assert _runs(store.db_path) == []


def test_the_upsert_method_does_not_write_a_run(tmp_path: Path) -> None:
    # Only the sync function records runs; a bare upsert is not a sync.
    store = _store(tmp_path)
    store.upsert([_event()], synced_at=AS_OF)
    assert _runs(store.db_path) == []


# ------------------------------------------------------ append-only (K-19)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE dividend_sync_runs SET status = 'failed'",
        "DELETE FROM dividend_sync_runs",
        "UPDATE dividend_sync_unparsed SET symbol = 'X'",
        "DELETE FROM dividend_sync_unparsed",
    ],
)
def test_both_sync_tables_are_append_only(tmp_path: Path, statement: str) -> None:
    store = _store(tmp_path)
    sync_dividends(store=store, adapter=_ok([_event()], unparsed=("9999",)))
    with closing(sqlite3.connect(store.db_path)) as conn:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute(statement)
        conn.rollback()
    assert [row[4] for row in _runs(store.db_path)] == ["ok"]
    assert _unparsed(store.db_path) == [(1, "9999")]


def test_the_triggers_survive_reopening_the_store(tmp_path: Path) -> None:
    first = _store(tmp_path)
    sync_dividends(store=first, adapter=_ok([_event()]))
    reopened = DividendEventStore(first.db_path)
    with closing(sqlite3.connect(reopened.db_path)) as conn:
        names = {
            name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
    assert names == {
        "dividend_sync_runs_no_update",
        "dividend_sync_runs_no_delete",
        "dividend_sync_unparsed_no_update",
        "dividend_sync_unparsed_no_delete",
    }


# ------------------------------------- the real adapter: unparsed vs unattributed


def _twse_client(payload: list[object]) -> RateLimitedClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return RateLimitedClient(
        base_url=TWSE_OPENAPI_BASE_URL,
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )


def _row(code: str | None, date_text: str, flag: str = "息") -> dict[str, str]:
    row = {"Date": date_text, "Exdividend": flag, "CashDividend": "1.0", "StockDividendRatio": ""}
    if code is not None:
        row["Code"] = code
    return row


def test_the_adapter_separates_unparsed_symbols_from_unattributed_rows(tmp_path: Path) -> None:
    payload: list[object] = [
        _row("2330", "1151020"),  # parses
        _row(" 00981a ", "garbled"),  # a Code, but the date does not parse
        _row("2317", "garbled"),
        _row("2317", "1151299"),  # same code again, impossible date
        _row("9999", "1151021", flag="?"),  # a Code, parseable date, refused flag
        _row(None, "1151020"),  # no Code
        _row("", "1151020"),  # blank Code
        "not an object",
    ]
    adapter = TwseDividendAdapter(client=_twse_client(payload))
    result = adapter.fetch()
    assert result.ok is True
    assert len(result.events) == 1
    assert sorted(result.unparsed_symbols) == ["00981A", "2317", "2317", "9999"]
    assert result.unattributed_rows == 3
    assert result.skipped_rows == 7

    store = _store(tmp_path)
    sync_dividends(store=store, adapter=adapter, trigger="scheduled")
    ((_, _, trigger, source, status, events, unparsed, unattributed, _),) = _runs(store.db_path)
    assert (trigger, source, status) == ("scheduled", "twse_openapi_dividend", "ok")
    assert (events, unparsed, unattributed) == (1, 4, 3)
    assert _unparsed(store.db_path) == [(1, "00981A"), (1, "2317"), (1, "9999")]


def test_the_repo_fixture_is_recorded_with_its_refused_rows(tmp_path: Path) -> None:
    payload = json.loads((FIXTURES_DIR / "twse_openapi_twt48u_all.json").read_text("utf-8"))
    store = _store(tmp_path)
    result = sync_dividends(store=store, adapter=TwseDividendAdapter(client=_twse_client(payload)))
    ((_, _, _, _, status, events, unparsed, unattributed, _),) = _runs(store.db_path)
    assert status == "ok"
    assert events == len(result.events) == store.count()
    assert unparsed + unattributed == result.skipped_rows
    assert unattributed >= 1  # the fixture carries a row without a Code


def test_an_unreachable_endpoint_is_a_failed_run_with_its_reason(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = RateLimitedClient(
        base_url=TWSE_OPENAPI_BASE_URL,
        min_interval_seconds=0.0,
        max_retries=0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )
    store = _store(tmp_path)
    sync_dividends(store=store, adapter=TwseDividendAdapter(client=client))
    ((_, _, _, _, status, events, _, _, reason),) = _runs(store.db_path)
    assert (status, events) == ("failed", 0)
    assert reason is not None and "ConnectError" in reason
    assert store.count() == 0


# --------------------------------------------------------------- the CLI path


def _patch_client(monkeypatch: pytest.MonkeyPatch, payload: list[object]) -> None:
    def build(*args: object, **kwargs: object) -> RateLimitedClient:
        return _twse_client(payload)

    monkeypatch.setattr("app.dividends.sync.RateLimitedClient", build)


def test_the_cli_records_a_cli_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.dividends.sync import main

    payload = json.loads((FIXTURES_DIR / "twse_openapi_twt48u_all.json").read_text("utf-8"))
    _patch_client(monkeypatch, payload)
    db_path = tmp_path / "cli.db"
    assert main(["--db-path", str(db_path)]) == 0
    runs = _runs(db_path)
    assert len(runs) == 1
    assert runs[0][2:5] == ("cli", "twse_openapi_dividend", "ok")


def test_the_cli_reports_a_failed_write_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.dividends.sync import main

    payload = json.loads((FIXTURES_DIR / "twse_openapi_twt48u_all.json").read_text("utf-8"))
    _patch_client(monkeypatch, payload)
    db_path = tmp_path / "cli.db"
    store = DividendEventStore(db_path)
    _add_trigger(store.db_path, "dividend_sync_runs", "boom_runs")
    assert main(["--db-path", str(db_path)]) == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err + captured.out
    assert "整筆回復" in captured.err
    assert store.count() == 0
    assert _runs(db_path) == []


# ------------------------------------------- the one-line rejected-rows WARNING

_REJECTED_LOGGER = "app.dividends.sync"
_REJECTED_PREFIX = "dividend sync rejected rows:"


def _rejected_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == _REJECTED_LOGGER and record.getMessage().startswith(_REJECTED_PREFIX)
    ]


def test_a_sync_logs_one_warning_with_the_rejection_counts_by_reason(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    payload: list[object] = [
        _row("2330", "1151020"),  # parses
        _row("9999", "1151021", flag="?"),  # flag unknown
        _row("9998", "1151021", flag="x"),  # flag unknown
        _row("9997", "1151021", flag=""),  # flag blank: also unknown
        _row("8888", "1151021", flag="權息"),  # stock component without a ratio
        _row("7777", "garbled"),  # date refused
        _row(None, "1151020"),  # no Code
        "not an object",
    ]
    store = _store(tmp_path)
    with caplog.at_level(logging.WARNING, logger=_REJECTED_LOGGER):
        sync_dividends(store=store, adapter=TwseDividendAdapter(client=_twse_client(payload)))
    lines = _rejected_lines(caplog)
    assert len(lines) == 1
    assert lines[0].levelno == logging.WARNING
    assert lines[0].getMessage() == (
        "dividend sync rejected rows: date_unparseable=1 flag_unknown=3 "
        "missing_stock_ratio=1 missing_symbol=1 not_an_object=1"
    )


def test_the_rejection_warning_carries_no_url_row_or_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TWSE_API_KEY", "super-secret-key")
    payload: list[object] = [_row("2330", "1151020"), _row("9999", "1151021", flag="?")]
    store = _store(tmp_path)
    with caplog.at_level(logging.DEBUG, logger=_REJECTED_LOGGER):
        sync_dividends(store=store, adapter=TwseDividendAdapter(client=_twse_client(payload)))
    (line,) = _rejected_lines(caplog)
    text = line.getMessage() + " " + " ".join(str(arg) for arg in line.args or ())
    for forbidden in ("http", "openapi.twse.com.tw", "TWT48U", "9999", "super-secret-key", "Code"):
        assert forbidden not in text
    assert line.getMessage() == "dividend sync rejected rows: flag_unknown=1"


def test_no_warning_is_logged_when_no_row_was_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = _store(tmp_path)
    with caplog.at_level(logging.DEBUG, logger=_REJECTED_LOGGER):
        sync_dividends(
            store=store,
            adapter=TwseDividendAdapter(client=_twse_client([_row("2330", "1151020")])),
        )
    assert _rejected_lines(caplog) == []


def test_an_all_refused_failed_run_still_logs_its_rejection_counts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = _store(tmp_path)
    payload: list[object] = [_row("9999", "1151021", flag="?")]
    with caplog.at_level(logging.WARNING, logger=_REJECTED_LOGGER):
        result = sync_dividends(
            store=store, adapter=TwseDividendAdapter(client=_twse_client(payload))
        )
    assert result.ok is False
    (line,) = _rejected_lines(caplog)
    assert line.getMessage() == "dividend sync rejected rows: flag_unknown=1"


def test_a_result_without_a_breakdown_is_counted_as_other(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = _store(tmp_path)
    with caplog.at_level(logging.WARNING, logger=_REJECTED_LOGGER):
        sync_dividends(
            store=store, adapter=_ok([_event()], unparsed=("9999", "9999"), unattributed=1)
        )
    (line,) = _rejected_lines(caplog)
    assert line.getMessage() == "dividend sync rejected rows: other=3"
