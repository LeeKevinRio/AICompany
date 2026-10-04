"""ADR-0016 D-5 / T-14: the ex-date coverage rule over each run-log source.

Every scenario below runs against two ``AnnounceRunSource`` implementations:

* ``market`` -- the market DB's ``dividend_announce`` runs, written through the real
  ``MarketPanelStore`` and read through the read-only ``MarketPanelReader``. Test and
  V-1 offline use only (ADR-0012 C-7).
* ``main`` -- the main DB's sync record (ADR-0016 D-5.2), written through the real
  ``sync_dividends`` and read through ``DividendEventStore``. This is the runtime source.

Every database lives under ``tmp_path``; nothing touches the development DB and
nothing goes over the network. In both, ``recorded_at`` is the store's own clock.
A row ``(symbol, None)`` is an event whose date could not be parsed. A dated row is
an event: the market DB returns it as an observation, the main DB keeps it in
``dividend_events`` where F6 reads it (D-5.3), so the scenarios that depend on a
dated observation are split per source below.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection, Sequence
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.data.interface import DividendAnnounceObservation, DividendAnnounceSnapshotRow
from app.data.market_panel import MarketPanelReader, MarketPanelStore
from app.dividends.coverage import (
    LISTED_BAR_SOURCE,
    MIN_ANNOUNCE_LEAD_DAYS,
    AnnounceRunCoverageRule,
    AnnounceRunSource,
)
from app.dividends.models import DividendEvent
from app.dividends.providers import TWSE_OPENAPI_BASE_URL, DividendFetchResult, TwseDividendAdapter
from app.dividends.store import DividendEventStore
from app.dividends.sync import sync_dividends
from app.portfolio.price_change import (
    ChangeScreen,
    CoverageQuery,
    ExDateCoverageRule,
)
from app.positions.models import Market
from tests.import_graph import module_path, offenders, reachable_app_modules

THU = date(2026, 10, 1)
FRI = date(2026, 10, 2)
MON = date(2026, 10, 5)

#: 21:30 Taipei on the given day, i.e. 13:30 UTC -- the scheduler's last capture.
EVENING = {
    THU: datetime(2026, 10, 1, 13, 30, tzinfo=UTC),
    FRI: datetime(2026, 10, 2, 13, 30, tzinfo=UTC),
}


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class _Log(Protocol):
    """A tmp run log with a settable clock, in one of the two sources."""

    clock: _Clock

    def run(
        self, at: datetime, rows: Sequence[tuple[str, date | None]], *, status: str = "ok"
    ) -> int: ...

    def source(self) -> AnnounceRunSource: ...

    def rule(self) -> AnnounceRunCoverageRule: ...

    def traced(self) -> tuple[AnnounceRunSource, list[str]]:
        """A fresh source over the same file, and the SQL statements it runs."""
        ...

    def insert_ok_run(self, recorded_at: str) -> None:
        """Append one dirty ``ok`` run with a raw ``recorded_at`` (INSERT is not blocked)."""
        ...


class _MarketLog:
    """The market DB, writing ``dividend_announce`` runs."""

    def __init__(self, tmp_path: Path) -> None:
        self.clock = _Clock()
        self.path = tmp_path / "market.db"
        self.store = MarketPanelStore(self.path, clock=self.clock)

    def run(
        self,
        at: datetime,
        rows: Sequence[tuple[str, date | None]],
        *,
        status: str = "ok",
    ) -> int:
        self.clock.now = at
        announce = [
            DividendAnnounceSnapshotRow(
                symbol=symbol,
                ex_date=ex_date,
                raw={
                    "Code": symbol,
                    "Date": ex_date.isoformat() if ex_date is not None else "garbled",
                },
            )
            for symbol, ex_date in rows
        ]
        return self.store.record_run(
            kind="dividend_announce",
            session_date=at.date(),
            source="twse_snapshot",
            status=status,  # type: ignore[arg-type]
            row_count=len(announce),
            expected_count=None,
            dividend_announce_rows=announce if status == "ok" else [],
        )

    def source(self) -> AnnounceRunSource:
        return MarketPanelReader(self.path)

    def rule(self) -> AnnounceRunCoverageRule:
        return AnnounceRunCoverageRule(self.source())

    def traced(self) -> tuple[AnnounceRunSource, list[str]]:
        reader = _TracedReader(self.path)
        return reader, reader.statements

    def insert_ok_run(self, recorded_at: str) -> None:
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(
                "INSERT INTO pit_snapshot_runs (kind, session_date, recorded_at, source, status, "
                "row_count, expected_count, content_hash, reason) "
                "VALUES ('dividend_announce', '2026-10-01', ?, 'x', 'ok', 1, NULL, 'dirty', NULL)",
                (recorded_at,),
            )


class _MainLog:
    """The main DB, written by the real ``sync_dividends`` through a canned adapter."""

    def __init__(self, tmp_path: Path) -> None:
        self.clock = _Clock()
        self.path = tmp_path / "main.db"
        self.store = DividendEventStore(self.path, clock=self.clock)

    def run(
        self,
        at: datetime,
        rows: Sequence[tuple[str, date | None]],
        *,
        status: str = "ok",
    ) -> int:
        self.clock.now = at
        events = [
            DividendEvent(
                symbol=symbol,
                market="TW",
                ex_date=ex_date,
                cash_dividend=Decimal("1"),
                source="stub",
                as_of=at,
            )
            for symbol, ex_date in rows
            if ex_date is not None
        ]
        unparsed = tuple(symbol for symbol, ex_date in rows if ex_date is None)
        # The main DB records only ``ok`` and ``failed``; "partial" is a failed run here.
        ok = status == "ok"
        result = DividendFetchResult(
            events=tuple(events) if ok else (),
            ok=ok,
            reason=None if ok else "stub failure",
            source="stub",
            as_of=at,
            skipped_rows=len(unparsed),
            unparsed_symbols=unparsed if ok else (),
        )
        sync_dividends(store=self.store, adapter=_Canned(result), trigger="scheduled")
        with closing(sqlite3.connect(self.path)) as conn:
            (run_id,) = conn.execute("SELECT MAX(run_id) FROM dividend_sync_runs").fetchone()
        return int(run_id)

    def source(self) -> AnnounceRunSource:
        return DividendEventStore(self.path)

    def rule(self) -> AnnounceRunCoverageRule:
        return AnnounceRunCoverageRule(self.source())

    def traced(self) -> tuple[AnnounceRunSource, list[str]]:
        store = _TracedStore(self.path)
        return store, store.statements

    def insert_ok_run(self, recorded_at: str) -> None:
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(
                "INSERT INTO dividend_sync_runs (recorded_at, trigger, source, status, "
                "event_count, unparsed_count, unattributed_count, reason) "
                "VALUES (?, 'cli', 'x', 'ok', 1, 0, 0, NULL)",
                (recorded_at,),
            )


class _Canned:
    def __init__(self, result: DividendFetchResult) -> None:
        self.result = result

    def fetch(self) -> DividendFetchResult:
        return self.result


@pytest.fixture(params=["market", "main"])
def make_log(request: pytest.FixtureRequest) -> Callable[[Path], _Log]:
    """The run-log factory; every test using it runs once per source."""
    return _MarketLog if request.param == "market" else _MainLog


@pytest.fixture
def make_market_log() -> Callable[[Path], _MarketLog]:
    return _MarketLog


@pytest.fixture
def make_main_log() -> Callable[[Path], _MainLog]:
    return _MainLog


def _query(
    symbol: str = "2330",
    *,
    market: Market = "TW",
    source: str = LISTED_BAR_SOURCE,
    basis: date = THU,
    price: date = FRI,
) -> CoverageQuery:
    return CoverageQuery(
        symbol=symbol, market=market, latest_source=source, basis_date=basis, price_date=price
    )


# Another listed symbol's event keeps the table non-empty (an empty table is not an ok run).
OTHER = ("1101", date(2026, 11, 20))


def test_synced_before_the_window_and_no_event_is_known(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    log = make_log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


def test_a_far_off_event_outside_the_window_does_not_block_known(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    log = make_log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", date(2026, 10, 20))])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


def test_never_synced_is_unknown(tmp_path: Path, make_log: Callable[[Path], _Log]) -> None:
    # A database without any dividend run proves nothing.
    query = _query()
    log = make_log(tmp_path)
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_unfinished_runs_do_not_count(tmp_path: Path, make_log: Callable[[Path], _Log]) -> None:
    log = make_log(tmp_path)
    log.run(EVENING[THU], [], status="failed")
    log.run(EVENING[THU], [OTHER], status="partial")
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_a_sync_after_price_date_cannot_prove_the_window_was_future(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    # The table drops an ex-date once it has passed, so a run recorded after
    # the window cannot say whether an event was ever announced.
    log = make_log(tmp_path)
    log.run(datetime(2026, 10, 6, 13, 30, tzinfo=UTC), [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_a_sync_after_basis_date_cannot_anchor(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    # Recorded on price_date itself: an event dated price_date may already be gone from the table.
    log = make_log(tmp_path)
    log.run(EVENING[FRI], [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_an_earlier_anchor_still_counts_when_later_runs_exist(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    log = make_log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    log.run(EVENING[FRI], [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


def test_a_stale_anchor_is_unknown(tmp_path: Path, make_log: Callable[[Path], _Log]) -> None:
    # Synced a week before basis_date: events announced since are not excluded.
    log = make_log(tmp_path)
    log.run(datetime(2026, 9, 24, 13, 30, tzinfo=UTC), [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_monday_after_a_friday_anchor_is_unknown_under_the_default_lead(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    assert MIN_ANNOUNCE_LEAD_DAYS == 1
    log = make_log(tmp_path)
    log.run(EVENING[FRI], [OTHER])
    query = _query(basis=FRI, price=MON)
    assert log.rule().coverage([query]) == {query: "unknown"}
    # With a longer (evidenced) lead the same log proves it.
    wider = AnnounceRunCoverageRule(log.source(), min_announce_lead_days=3)
    assert wider.coverage([query]) == {query: "known"}


def test_run_date_is_the_taipei_date_not_the_utc_date(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    # 17:00 UTC on 10/01 is 01:00 on 10/02 in Taipei: after basis_date, so no anchor.
    log = make_log(tmp_path)
    log.run(datetime(2026, 10, 1, 17, 0, tzinfo=UTC), [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}
    # 15:59 UTC on 10/01 is 23:59 on 10/01 in Taipei: still on basis_date.
    other = make_log(tmp_path / "b")
    other.run(datetime(2026, 10, 1, 15, 59, tzinfo=UTC), [OTHER])
    assert other.rule().coverage([query]) == {query: "known"}


def test_market_db_an_event_in_the_window_is_not_known(
    tmp_path: Path, make_market_log: Callable[[Path], _MarketLog]
) -> None:
    log = make_market_log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", FRI)])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_main_db_leaves_a_dated_event_in_the_window_to_f6(
    tmp_path: Path, make_main_log: Callable[[Path], _MainLog]
) -> None:
    # The main DB source returns no dated observation: the event is in the same
    # transaction's ``dividend_events``, where F6 withholds the change before the
    # coverage rule is even asked (``ChangeScreen``: a known ex-date wins).
    log = make_main_log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", FRI)])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}
    assert log.store.ex_dates_between([("2330", "TW")], query.basis_date, query.price_date) == {
        ("2330", "TW"): frozenset({FRI})
    }


def test_an_event_dated_on_basis_date_is_outside_the_window(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    # Same boundary as F6: basis_date < ex_date <= price_date.
    log = make_log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", THU)])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


def test_an_event_with_an_unparseable_date_is_not_known(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    log = make_log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", None)])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_an_unparseable_row_from_before_the_anchor_is_ignored(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    # The anchor run supersedes older snapshots of the same table.
    log = make_log(tmp_path)
    log.run(datetime(2026, 9, 30, 13, 30, tzinfo=UTC), [OTHER, ("2330", None)])
    log.run(EVENING[THU], [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


@pytest.mark.parametrize(
    ("market", "source"),
    [
        ("TW", "tpex"),  # OTC: TWT48U_ALL lists TWSE stocks only
        ("TW", "twse+divadj"),
        ("TW", "finmind"),
        ("US", "yfinance"),
        ("US", "twse"),  # a US row is never covered, whatever its source says
    ],
)
def test_otc_us_and_other_sources_are_unknown_without_reading(
    tmp_path: Path, make_log: Callable[[Path], _Log], market: Market, source: str
) -> None:
    log = make_log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    spy = _Spy(log.source())
    query = _query(market=market, source=source)
    assert AnnounceRunCoverageRule(spy).coverage([query]) == {query: "unknown"}
    assert spy.calls == 0


def test_a_whole_book_is_one_call_and_one_statement(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    log = make_log(tmp_path)
    for day in (THU, FRI):
        log.run(EVENING[day], [OTHER])
    reader, statements = log.traced()
    rule = AnnounceRunCoverageRule(reader)
    queries = [
        _query("2330"),
        _query("2317"),
        _query("2454", basis=FRI, price=MON),
        _query("6488", source="tpex"),
        _query("AAPL", market="US", source="yfinance"),
    ]
    answers = rule.coverage(queries)
    assert answers[queries[0]] == "known"
    assert answers[queries[1]] == "known"
    assert answers[queries[3]] == "unknown"
    assert answers[queries[4]] == "unknown"
    assert len(statements) == 1


def test_every_query_gets_an_answer_even_when_the_log_is_empty(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    rule = make_log(tmp_path).rule()
    queries = [_query("2330"), _query("AAPL", market="US", source="yfinance")]
    assert rule.coverage(queries) == {query: "unknown" for query in queries}
    assert rule.coverage([]) == {}


def test_symbols_are_matched_case_insensitively(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    log = make_log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("00981A", None)])
    query = _query("00981a")
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_an_unreadable_run_log_is_unknown_not_an_exception() -> None:
    class Broken:
        def dividend_announce_observations(
            self, symbols: Collection[str], recorded_not_before: date
        ) -> Sequence[DividendAnnounceObservation]:
            raise sqlite3.OperationalError("database is locked")

    query = _query()
    assert AnnounceRunCoverageRule(Broken()).coverage([query]) == {query: "unknown"}


def test_a_naive_timestamp_proves_nothing() -> None:
    class Naive:
        def dividend_announce_observations(
            self, symbols: Collection[str], recorded_not_before: date
        ) -> Sequence[DividendAnnounceObservation]:
            return [
                DividendAnnounceObservation(
                    run_id=1, recorded_at=datetime(2026, 10, 1, 21, 30), symbol=None, ex_date=None
                )
            ]

    query = _query()
    assert AnnounceRunCoverageRule(Naive()).coverage([query]) == {query: "unknown"}


def test_the_lead_is_enforced_by_the_rule_not_only_by_the_read_bound() -> None:
    # A source that hands back runs older than asked for must not widen the proof.
    class Everything:
        def dividend_announce_observations(
            self, symbols: Collection[str], recorded_not_before: date
        ) -> Sequence[DividendAnnounceObservation]:
            return [
                DividendAnnounceObservation(
                    run_id=1, recorded_at=EVENING[THU], symbol=None, ex_date=None
                )
            ]

    stale = _query(basis=THU, price=date(2026, 10, 9))
    assert AnnounceRunCoverageRule(Everything()).coverage([stale]) == {stale: "unknown"}
    fresh = _query(basis=THU, price=FRI)
    assert AnnounceRunCoverageRule(Everything()).coverage([fresh]) == {fresh: "known"}


def test_a_naive_run_carrying_a_window_row_is_unknown() -> None:
    # The naive run cannot anchor, but its event row must not be skipped.
    class Mixed:
        def dividend_announce_observations(
            self, symbols: Collection[str], recorded_not_before: date
        ) -> Sequence[DividendAnnounceObservation]:
            return [
                DividendAnnounceObservation(
                    run_id=1, recorded_at=EVENING[THU], symbol=None, ex_date=None
                ),
                DividendAnnounceObservation(
                    run_id=2, recorded_at=datetime(2026, 10, 1, 21, 30), symbol="2330", ex_date=FRI
                ),
            ]

    query = _query()
    assert AnnounceRunCoverageRule(Mixed()).coverage([query]) == {query: "unknown"}


def test_a_naive_run_with_an_unparseable_date_row_is_unknown() -> None:
    class Mixed:
        def dividend_announce_observations(
            self, symbols: Collection[str], recorded_not_before: date
        ) -> Sequence[DividendAnnounceObservation]:
            return [
                DividendAnnounceObservation(
                    run_id=1, recorded_at=EVENING[THU], symbol=None, ex_date=None
                ),
                DividendAnnounceObservation(
                    run_id=2,
                    recorded_at=datetime(2026, 10, 1, 21, 30),
                    symbol="2330",
                    ex_date=None,
                ),
            ]

    query = _query()
    assert AnnounceRunCoverageRule(Mixed()).coverage([query]) == {query: "unknown"}


def test_a_corrupt_stored_timestamp_is_unknown_not_an_exception(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    log = make_log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    # Append-only triggers block UPDATE/DELETE, not INSERT: add one dirty ok run.
    log.insert_ok_run("not-a-timestamp")
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_main_db_a_stored_naive_run_never_anchors_and_its_unparsed_symbol_blocks(
    tmp_path: Path, make_main_log: Callable[[Path], _MainLog]
) -> None:
    log = make_main_log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}
    # A naive-time ok run cannot be placed on the calendar, so it cannot anchor ...
    log.insert_ok_run("2026-10-01T21:30:00.000000")
    assert log.rule().coverage([query]) == {query: "known"}
    # ... but an event it carries for the symbol still blocks (never skipped).
    with closing(sqlite3.connect(log.path)) as conn, conn:
        conn.execute("INSERT INTO dividend_sync_unparsed (run_id, symbol) VALUES (2, '2330')")
    assert log.rule().coverage([query]) == {query: "unknown"}
    # Another symbol's answer is unaffected.
    other = _query("2317")
    assert log.rule().coverage([other]) == {other: "known"}


def test_a_lead_below_one_day_is_refused(tmp_path: Path, make_log: Callable[[Path], _Log]) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        AnnounceRunCoverageRule(make_log(tmp_path).source(), min_announce_lead_days=0)


def test_market_db_a_missing_file_reads_as_unknown_and_is_not_created(tmp_path: Path) -> None:
    # ``MarketPanelReader`` opens read-only and never creates the file: a rule over a
    # market DB that does not exist answers ``unknown`` and leaves the directory empty.
    path = tmp_path / "absent-market.db"
    query = _query()
    assert AnnounceRunCoverageRule(MarketPanelReader(path)).coverage([query]) == {query: "unknown"}
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_the_coverage_module_cannot_reach_the_market_db_module() -> None:
    # ADR-0012 C-7: the positions data chain does not read the market DB, and the
    # coverage rule is what that chain will call. The reader only satisfies its
    # Protocol structurally (tests, V-1 offline checks).
    assert module_path("app.dividends.coverage") is not None
    reachable = reachable_app_modules(("app.dividends.coverage",))
    assert "app.data.market_panel" not in reachable
    assert offenders(reachable, "app.data.market_panel") == []


class _NoCalendar:
    def market_trading_days(self, market: Market, start: date, end: date) -> frozenset[date]:
        return frozenset()


def test_the_rule_plugs_into_the_change_screen(
    tmp_path: Path, make_log: Callable[[Path], _Log]
) -> None:
    rule: ExDateCoverageRule = make_log(tmp_path).rule()
    screen = ChangeScreen(
        ex_dates=DividendEventStore(tmp_path / "main.db"),
        calendar=_NoCalendar(),
        coverage_rule=rule,
    )
    assert screen.coverage_rule is rule
    assert screen.screen([]) == []


class _Spy:
    def __init__(self, inner: AnnounceRunSource) -> None:
        self.inner = inner
        self.calls = 0

    def dividend_announce_observations(
        self, symbols: Collection[str], recorded_not_before: date
    ) -> Sequence[DividendAnnounceObservation]:
        self.calls += 1
        return self.inner.dividend_announce_observations(symbols, recorded_not_before)


class _TracedStore(DividendEventStore):
    """A main DB store that records every SQL statement its read connections run."""

    def __init__(self, path: Path) -> None:
        self.statements: list[str] = []
        super().__init__(path)
        self.statements.clear()  # drop the schema statements of construction

    def _connect(self) -> sqlite3.Connection:
        conn = super()._connect()
        conn.set_trace_callback(self.statements.append)
        return conn


class _TracedReader(MarketPanelReader):
    """A reader that records every SQL statement its connections run."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.statements: list[str] = []

    def _connect(self) -> sqlite3.Connection | None:
        conn = super()._connect()
        if conn is not None:
            conn.set_trace_callback(self.statements.append)
        return conn


# --- main DB adapter specifics (ADR-0016 D-5.2 read side, K-20) ---------------------


def test_main_db_an_unparsed_symbol_makes_only_that_symbol_unknown(
    tmp_path: Path, make_main_log: Callable[[Path], _MainLog]
) -> None:
    log = make_main_log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", None)])
    blocked, free = _query("2330"), _query("2317")
    assert log.rule().coverage([blocked, free]) == {blocked: "unknown", free: "known"}


def _real_adapter_log(tmp_path: Path, payload: list[object]) -> _MainLog:
    """A main DB synced by the real adapter (``httpx.MockTransport``) at 21:30 Taipei."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = RateLimitedClient(
        base_url=TWSE_OPENAPI_BASE_URL,
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )
    log = _MainLog(tmp_path)
    log.clock.now = EVENING[THU]
    sync_dividends(store=log.store, adapter=TwseDividendAdapter(client=client), trigger="scheduled")
    return log


@pytest.mark.parametrize(
    ("symbol", "row"),
    [
        # A legal date (2026-10-21), but the Exdividend flag is not one of the known three.
        ("9999", {"Date": "1151021", "Exdividend": "?", "CashDividend": "1.0"}),
        # A legal date, a stock component flagged, but no StockDividendRatio.
        ("8888", {"Date": "1151021", "Exdividend": "權息", "CashDividend": "1.0"}),
        # A legal date, but a negative amount.
        ("7777", {"Date": "1151021", "Exdividend": "息", "CashDividend": "-1.0"}),
    ],
    ids=["flag_unknown", "missing_stock_ratio", "negative_cash_dividend"],
)
def test_main_db_a_dated_row_refused_for_another_reason_makes_its_symbol_unknown(
    tmp_path: Path, symbol: str, row: dict[str, str]
) -> None:
    # The date parses, so this is not the "garbled date" case: the row is refused for
    # some other reason, lands in ``dividend_sync_unparsed`` and blocks the symbol.
    payload: list[object] = [
        {"Code": "1101", "Date": "1151120", "Exdividend": "息", "CashDividend": "2.0"},
        {"Code": symbol, **row},
    ]
    log = _real_adapter_log(tmp_path, payload)
    with closing(sqlite3.connect(log.path)) as conn:
        assert conn.execute("SELECT symbol FROM dividend_sync_unparsed").fetchall() == [(symbol,)]
        assert conn.execute("SELECT symbol FROM dividend_events").fetchall() == [("1101",)]
    refused, clean = _query(symbol), _query("2330")
    assert log.rule().coverage([refused, clean]) == {refused: "unknown", clean: "known"}


def test_main_db_unattributed_rows_make_every_queried_symbol_unknown(
    tmp_path: Path, make_main_log: Callable[[Path], _MainLog]
) -> None:
    log = make_main_log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    queries = [_query("2330"), _query("2317"), _query("2454")]
    assert set(log.rule().coverage(queries).values()) == {"known"}

    # A run whose capture held a row with no Code: it may hide an event of any symbol.
    other = make_main_log(tmp_path / "unattributed")
    other.clock.now = EVENING[THU]
    sync_dividends(
        store=other.store,
        adapter=_Canned(
            DividendFetchResult(
                events=(
                    DividendEvent(
                        symbol="1101",
                        market="TW",
                        ex_date=date(2026, 11, 20),
                        source="stub",
                        as_of=EVENING[THU],
                    ),
                ),
                ok=True,
                reason=None,
                source="stub",
                as_of=EVENING[THU],
                skipped_rows=1,
                unattributed_rows=1,
            )
        ),
    )
    assert other.rule().coverage(queries) == {query: "unknown" for query in queries}


def test_main_db_a_later_clean_run_supersedes_an_unattributed_one(
    tmp_path: Path, make_main_log: Callable[[Path], _MainLog]
) -> None:
    log = make_main_log(tmp_path)
    log.clock.now = datetime(2026, 9, 30, 13, 30, tzinfo=UTC)
    sync_dividends(
        store=log.store,
        adapter=_Canned(
            DividendFetchResult(
                events=(
                    DividendEvent(
                        symbol="1101",
                        market="TW",
                        ex_date=date(2026, 11, 20),
                        source="stub",
                        as_of=log.clock.now,
                    ),
                ),
                ok=True,
                reason=None,
                source="stub",
                as_of=log.clock.now,
                skipped_rows=1,
                unattributed_rows=1,
            )
        ),
    )
    log.run(EVENING[THU], [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


def test_main_db_observations_have_the_documented_shape(
    tmp_path: Path, make_main_log: Callable[[Path], _MainLog]
) -> None:
    log = make_main_log(tmp_path)
    clean = log.run(EVENING[THU], [OTHER])
    dirty = log.run(EVENING[FRI], [OTHER, ("2330", None), ("2317", None)])
    log.run(datetime(2026, 9, 1, tzinfo=UTC), [OTHER, ("2330", None)])  # before the bound
    observations = log.store.dividend_announce_observations({"2330", " 00981a "}, date(2026, 10, 1))
    assert [(o.run_id, o.symbol, o.ex_date) for o in observations] == [
        (clean, None, None),
        (dirty, "2330", None),
    ]
    assert all(o.recorded_at.tzinfo is not None for o in observations)
    assert log.store.dividend_announce_observations(set(), date(2026, 10, 1)) == []
    # The bound is a UTC date, inclusive.
    assert [
        o.run_id for o in log.store.dividend_announce_observations({"x"}, date(2026, 10, 2))
    ] == [dirty]
    assert log.store.dividend_announce_observations({"x"}, date(2026, 10, 3)) == []


def test_main_db_failed_runs_are_never_returned(
    tmp_path: Path, make_main_log: Callable[[Path], _MainLog]
) -> None:
    log = make_main_log(tmp_path)
    log.run(EVENING[THU], [OTHER], status="failed")
    assert log.store.dividend_announce_observations({"2330"}, date(2026, 9, 1)) == []
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_main_db_missing_sync_tables_read_as_no_run(
    tmp_path: Path, make_main_log: Callable[[Path], _MainLog]
) -> None:
    log = make_main_log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    with closing(sqlite3.connect(log.path)) as conn, conn:
        conn.execute("DROP TABLE dividend_sync_unparsed")
        conn.execute("DROP TABLE dividend_sync_runs")
    assert log.store.dividend_announce_observations({"2330"}, date(2026, 9, 1)) == []
    query = _query()
    assert AnnounceRunCoverageRule(log.store).coverage([query]) == {query: "unknown"}


def test_main_db_any_other_read_error_reaches_the_rule_and_reads_as_unknown(
    tmp_path: Path, make_main_log: Callable[[Path], _MainLog]
) -> None:
    log = make_main_log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    with closing(sqlite3.connect(log.path)) as conn, conn:
        conn.execute("DROP INDEX idx_dividend_sync_runs_status_recorded")
        conn.execute("ALTER TABLE dividend_sync_runs RENAME COLUMN status TO state")
    with pytest.raises(sqlite3.OperationalError):
        log.store.dividend_announce_observations({"2330"}, date(2026, 9, 1))
    query = _query()
    assert AnnounceRunCoverageRule(log.store).coverage([query]) == {query: "unknown"}


def test_main_db_store_satisfies_the_protocol_structurally(tmp_path: Path) -> None:
    source: AnnounceRunSource = DividendEventStore(tmp_path / "main.db")
    assert source.dividend_announce_observations(["2330"], date(2026, 9, 1)) == []
