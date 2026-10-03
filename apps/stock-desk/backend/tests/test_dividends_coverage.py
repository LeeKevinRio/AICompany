"""ADR-0016 D-5: the ex-date coverage rule over the market DB's dividend-announce run log.

Every database here lives under ``tmp_path``; nothing touches the development
DB and nothing goes over the network. Runs are written through the real
``MarketPanelStore`` (so ``recorded_at`` is the store's own clock) and read back
through the real read-only ``MarketPanelReader``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Collection, Sequence
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.data.interface import DividendAnnounceObservation, DividendAnnounceSnapshotRow
from app.data.market_panel import MarketPanelReader, MarketPanelStore
from app.dividends.coverage import (
    LISTED_BAR_SOURCE,
    MIN_ANNOUNCE_LEAD_DAYS,
    AnnounceRunCoverageRule,
)
from app.dividends.store import DividendEventStore
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


class _Log:
    """A tmp market DB with a settable clock, writing ``dividend_announce`` runs."""

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

    def rule(self) -> AnnounceRunCoverageRule:
        return AnnounceRunCoverageRule(MarketPanelReader(self.path))


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


def test_synced_before_the_window_and_no_event_is_known(tmp_path: Path) -> None:
    log = _Log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


def test_a_far_off_event_outside_the_window_does_not_block_known(tmp_path: Path) -> None:
    log = _Log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", date(2026, 10, 20))])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


def test_never_synced_is_unknown(tmp_path: Path) -> None:
    # Neither a missing market DB file nor a DB without any dividend run proves coverage.
    missing = AnnounceRunCoverageRule(MarketPanelReader(tmp_path / "absent.db"))
    query = _query()
    assert missing.coverage([query]) == {query: "unknown"}
    assert not (tmp_path / "absent.db").exists()  # the reader never creates the file

    log = _Log(tmp_path)
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_unfinished_runs_do_not_count(tmp_path: Path) -> None:
    log = _Log(tmp_path)
    log.run(EVENING[THU], [], status="failed")
    log.run(EVENING[THU], [OTHER], status="partial")
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_a_sync_after_price_date_cannot_prove_the_window_was_future(tmp_path: Path) -> None:
    # The table drops an ex-date once it has passed, so a run recorded after
    # the window cannot say whether an event was ever announced.
    log = _Log(tmp_path)
    log.run(datetime(2026, 10, 6, 13, 30, tzinfo=UTC), [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_a_sync_after_basis_date_cannot_anchor(tmp_path: Path) -> None:
    # Recorded on price_date itself: an event dated price_date may already be gone from the table.
    log = _Log(tmp_path)
    log.run(EVENING[FRI], [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_an_earlier_anchor_still_counts_when_later_runs_exist(tmp_path: Path) -> None:
    log = _Log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    log.run(EVENING[FRI], [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


def test_a_stale_anchor_is_unknown(tmp_path: Path) -> None:
    # Synced a week before basis_date: events announced since are not excluded.
    log = _Log(tmp_path)
    log.run(datetime(2026, 9, 24, 13, 30, tzinfo=UTC), [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_monday_after_a_friday_anchor_is_unknown_under_the_default_lead(tmp_path: Path) -> None:
    assert MIN_ANNOUNCE_LEAD_DAYS == 1
    log = _Log(tmp_path)
    log.run(EVENING[FRI], [OTHER])
    query = _query(basis=FRI, price=MON)
    assert log.rule().coverage([query]) == {query: "unknown"}
    # With a longer (evidenced) lead the same log proves it.
    wider = AnnounceRunCoverageRule(MarketPanelReader(log.path), min_announce_lead_days=3)
    assert wider.coverage([query]) == {query: "known"}


def test_run_date_is_the_taipei_date_not_the_utc_date(tmp_path: Path) -> None:
    # 17:00 UTC on 10/01 is 01:00 on 10/02 in Taipei: after basis_date, so no anchor.
    log = _Log(tmp_path)
    log.run(datetime(2026, 10, 1, 17, 0, tzinfo=UTC), [OTHER])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}
    # 15:59 UTC on 10/01 is 23:59 on 10/01 in Taipei: still on basis_date.
    other = _Log(tmp_path / "b")
    other.run(datetime(2026, 10, 1, 15, 59, tzinfo=UTC), [OTHER])
    assert other.rule().coverage([query]) == {query: "known"}


def test_an_event_in_the_window_is_not_known(tmp_path: Path) -> None:
    log = _Log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", FRI)])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_an_event_dated_on_basis_date_is_outside_the_window(tmp_path: Path) -> None:
    # Same boundary as F6: basis_date < ex_date <= price_date.
    log = _Log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", THU)])
    query = _query()
    assert log.rule().coverage([query]) == {query: "known"}


def test_an_event_with_an_unparseable_date_is_not_known(tmp_path: Path) -> None:
    log = _Log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("2330", None)])
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_an_unparseable_row_from_before_the_anchor_is_ignored(tmp_path: Path) -> None:
    # The anchor run supersedes older snapshots of the same table.
    log = _Log(tmp_path)
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
    tmp_path: Path, market: Market, source: str
) -> None:
    log = _Log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    spy = _Spy(MarketPanelReader(log.path))
    query = _query(market=market, source=source)
    assert AnnounceRunCoverageRule(spy).coverage([query]) == {query: "unknown"}
    assert spy.calls == 0


def test_a_whole_book_is_one_call_and_one_statement(tmp_path: Path) -> None:
    log = _Log(tmp_path)
    for day in (THU, FRI):
        log.run(EVENING[day], [OTHER])
    reader = _TracedReader(log.path)
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
    assert len(reader.statements) == 1


def test_every_query_gets_an_answer_even_when_the_log_is_empty(tmp_path: Path) -> None:
    rule = AnnounceRunCoverageRule(MarketPanelReader(tmp_path / "absent.db"))
    queries = [_query("2330"), _query("AAPL", market="US", source="yfinance")]
    assert rule.coverage(queries) == {query: "unknown" for query in queries}
    assert rule.coverage([]) == {}


def test_symbols_are_matched_case_insensitively(tmp_path: Path) -> None:
    log = _Log(tmp_path)
    log.run(EVENING[THU], [OTHER, ("00981A", FRI)])
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


def test_a_corrupt_stored_timestamp_is_unknown_not_an_exception(tmp_path: Path) -> None:
    log = _Log(tmp_path)
    log.run(EVENING[THU], [OTHER])
    # Append-only triggers block UPDATE/DELETE, not INSERT: add one dirty ok run.
    with closing(sqlite3.connect(log.path)) as conn, conn:
        conn.execute(
            "INSERT INTO pit_snapshot_runs (kind, session_date, recorded_at, source, status, "
            "row_count, expected_count, content_hash, reason) "
            "VALUES ('dividend_announce', '2026-10-01', 'not-a-timestamp', 'x', 'ok', 1, NULL, "
            "'dirty', NULL)"
        )
    query = _query()
    assert log.rule().coverage([query]) == {query: "unknown"}


def test_a_lead_below_one_day_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        AnnounceRunCoverageRule(MarketPanelReader(tmp_path / "x.db"), min_announce_lead_days=0)


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


def test_the_rule_plugs_into_the_change_screen(tmp_path: Path) -> None:
    rule: ExDateCoverageRule = _Log(tmp_path).rule()
    screen = ChangeScreen(
        ex_dates=DividendEventStore(tmp_path / "main.db"),
        calendar=_NoCalendar(),
        coverage_rule=rule,
    )
    assert screen.coverage_rule is rule
    assert screen.screen([]) == []


class _Spy:
    def __init__(self, inner: MarketPanelReader) -> None:
        self.inner = inner
        self.calls = 0

    def dividend_announce_observations(
        self, symbols: Collection[str], recorded_not_before: date
    ) -> Sequence[DividendAnnounceObservation]:
        self.calls += 1
        return self.inner.dividend_announce_observations(symbols, recorded_not_before)


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
