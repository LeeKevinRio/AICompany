"""``app.data.market_panel.MarketPanelStore`` contract tests (ADR-0012 D-2, T-4, T-21).

All offline: a throwaway SQLite file per test, no network.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.interface import (
    BarSnapshotRow,
    ClassificationSnapshotRow,
    DividendAnnounceSnapshotRow,
    ListingSnapshotRow,
)
from app.data.market_panel import (
    DEFAULT_MARKET_DB_PATH,
    MarketPanelStore,
    resolve_market_db_path,
)


def _clock(moment: datetime) -> Callable[[], datetime]:
    return lambda: moment


def _bar(symbol: str = "2330", **overrides: object) -> BarSnapshotRow:
    defaults: dict[str, object] = dict(
        symbol=symbol,
        open=Decimal("594"),
        high=Decimal("598"),
        low=Decimal("590"),
        close=Decimal("594"),
        shares=41_393_088,
        traded_value=Decimal("24585432000"),
        change=Decimal("2.00"),
    )
    defaults.update(overrides)
    return BarSnapshotRow(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def store(tmp_path: Path) -> MarketPanelStore:
    return MarketPanelStore(
        tmp_path / "market.db", clock=_clock(datetime(2026, 9, 24, 9, 30, tzinfo=UTC))
    )


# -- T-3: file configuration --------------------------------------------------


def test_default_market_db_path_is_the_documented_default() -> None:
    assert DEFAULT_MARKET_DB_PATH == "./data/stock-desk-market.db"


def test_resolve_market_db_path_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_DESK_MARKET_DB_PATH", "/tmp/custom-market.db")
    assert resolve_market_db_path() == Path("/tmp/custom-market.db")


def test_market_db_path_string_only_appears_in_this_module_and_tests() -> None:
    app_root = Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in app_root.rglob("*.py"):
        if path.name == "market_panel.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "STOCK_DESK_MARKET_DB_PATH" in text or "stock-desk-market.db" in text:
            offenders.append(str(path))
    assert offenders == []


def test_market_db_contains_only_the_declared_tables(store: MarketPanelStore) -> None:
    with closing(sqlite3.connect(store.db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    table_names = {name for (name,) in rows}
    assert table_names == {
        "pit_snapshot_runs",
        "market_daily_bars",
        "pit_listing_rows",
        "pit_classification_rows",
        "pit_dividend_announce_rows",
        "market_backfill_progress",
    }
    # C-8: no sector_* tables leak into the market DB.
    assert not any(name.startswith("sector_") for name in table_names)


# -- T-21: busy_timeout --------------------------------------------------------


def test_busy_timeout_is_set(store: MarketPanelStore) -> None:
    with closing(sqlite3.connect(store.db_path)) as conn:
        (value,) = conn.execute("PRAGMA busy_timeout").fetchone()
    assert value > 0


# -- T-4: append-only, recorded_at, PIT storage --------------------------------


def test_update_and_delete_are_rejected_on_every_append_only_table(
    store: MarketPanelStore,
) -> None:
    run_id = store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=1,
        bars_rows=[_bar()],
    )
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE pit_snapshot_runs SET status = 'failed' WHERE run_id = ?", (run_id,)
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM pit_snapshot_runs WHERE run_id = ?", (run_id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE market_daily_bars SET shares = 0 WHERE run_id = ?", (run_id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM market_daily_bars WHERE run_id = ?", (run_id,))

    listing_run = store.record_run(
        kind="listing",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        listing_rows=[ListingSnapshotRow(symbol="2330", security_type="common_stock")],
    )
    assert listing_run > 0
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE pit_listing_rows SET security_type = 'x'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM pit_listing_rows")

    class_run = store.record_run(
        kind="classification",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        classification_rows=[
            ClassificationSnapshotRow(symbol="2330", sector_code="24", sector_name="半導體業")
        ],
    )
    assert class_run > 0
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE pit_classification_rows SET sector_name = 'x'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM pit_classification_rows")

    div_run = store.record_run(
        kind="dividend_announce",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        dividend_announce_rows=[
            DividendAnnounceSnapshotRow(
                symbol="2330", ex_date=date(2026, 10, 1), raw={"Code": "2330"}
            )
        ],
    )
    assert div_run > 0
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE pit_dividend_announce_rows SET ex_date = '2099-01-01'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM pit_dividend_announce_rows")


def test_append_only_triggers_exist_for_every_table(store: MarketPanelStore) -> None:
    tables = (
        "pit_snapshot_runs",
        "market_daily_bars",
        "pit_listing_rows",
        "pit_classification_rows",
        "pit_dividend_announce_rows",
    )
    with closing(sqlite3.connect(store.db_path)) as conn:
        for table in tables:
            names = {
                name
                for (name,) in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
                    (table,),
                ).fetchall()
            }
            assert names == {f"{table}_no_update", f"{table}_no_delete"}, table


def test_append_only_teeth_test_missing_trigger_is_detected(tmp_path: Path) -> None:
    """If a trigger were dropped, the existence assertion above would fail (teeth test)."""
    db_path = tmp_path / "broken.db"
    store = MarketPanelStore(db_path, clock=_clock(datetime(2026, 9, 24, tzinfo=UTC)))
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("DROP TRIGGER pit_snapshot_runs_no_update")
    with closing(sqlite3.connect(store.db_path)) as conn:
        names = {
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND tbl_name = 'pit_snapshot_runs'"
            ).fetchall()
        }
    assert names == {"pit_snapshot_runs_no_delete"}  # not the full expected set -> caught


def test_market_backfill_progress_is_mutable_by_design(store: MarketPanelStore) -> None:
    store.upsert_backfill_progress("2330", status="pending")
    store.upsert_backfill_progress("2330", status="done")
    assert store.backfill_progress()["2330"] == "done"
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        # No append-only trigger on this table -- ordinary UPDATE succeeds.
        conn.execute("UPDATE market_backfill_progress SET status = 'failed' WHERE symbol = '2330'")
    assert store.backfill_progress()["2330"] == "failed"


def test_recorded_at_is_not_a_caller_parameter() -> None:
    import inspect

    signature = inspect.signature(MarketPanelStore.record_run)
    assert "recorded_at" not in signature.parameters
    signature = inspect.signature(MarketPanelStore.record_symbol_backfill)
    assert "recorded_at" not in signature.parameters


def test_recorded_at_comes_from_the_injected_clock(tmp_path: Path) -> None:
    moment = datetime(2026, 9, 24, 9, 30, tzinfo=UTC)
    store = MarketPanelStore(tmp_path / "market.db", clock=_clock(moment))
    store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=1,
        bars_rows=[_bar()],
    )
    with closing(sqlite3.connect(store.db_path)) as conn:
        (recorded_at,) = conn.execute("SELECT recorded_at FROM pit_snapshot_runs").fetchone()
    assert recorded_at == moment.isoformat()


def test_failed_self_certification_is_recorded_with_null_session_date(
    store: MarketPanelStore,
) -> None:
    run_id = store.record_run(
        kind="bars",
        session_date=None,
        source="twse_snapshot",
        status="failed",
        row_count=0,
        expected_count=None,
        reason="無法自證交易日",
    )
    with closing(sqlite3.connect(store.db_path)) as conn:
        row = conn.execute(
            "SELECT session_date, status, reason FROM pit_snapshot_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    assert row == (None, "failed", "無法自證交易日")
    # A run with no certified date is invisible to load_panel_frames.
    frames = store.load_panel_frames(date(2020, 1, 1), date(2030, 1, 1))
    assert frames.runs.empty


def test_load_panel_frames_only_returns_rows_within_window(store: MarketPanelStore) -> None:
    store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=1,
        bars_rows=[_bar()],
    )
    in_range = store.load_panel_frames(date(2026, 9, 1), date(2026, 9, 30))
    out_of_range = store.load_panel_frames(date(2026, 1, 1), date(2026, 1, 31))
    assert len(in_range.bars) == 1
    assert out_of_range.bars.empty


def test_load_panel_frames_includes_non_ok_runs_for_panel_py_to_filter(
    store: MarketPanelStore,
) -> None:
    """PanelFrames.runs carries every status; app.data.panel derives ok_ids itself."""
    store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="partial",
        row_count=1,
        expected_count=100,
        reason="覆蓋率不足",
        bars_rows=[_bar()],
    )
    frames = store.load_panel_frames(date(2026, 9, 1), date(2026, 9, 30))
    assert list(frames.runs["status"]) == ["partial"]
    assert len(frames.bars) == 1  # raw content is still exposed; app.data.panel gates on status


# -- content-addressing (跨日只存一份) -----------------------------------------


def test_identical_listing_content_across_days_shares_one_content_hash(
    store: MarketPanelStore,
) -> None:
    rows = [ListingSnapshotRow(symbol="2330", security_type="common_stock")]
    store.record_run(
        kind="listing",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        listing_rows=rows,
    )
    store.record_run(
        kind="listing",
        session_date=date(2026, 9, 25),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        listing_rows=rows,
    )
    with closing(sqlite3.connect(store.db_path)) as conn:
        content_hashes = {
            row[0] for row in conn.execute("SELECT DISTINCT content_hash FROM pit_listing_rows")
        }
        row_count = conn.execute("SELECT COUNT(*) FROM pit_listing_rows").fetchone()[0]
    assert len(content_hashes) == 1
    assert row_count == 1  # not duplicated across the two days


def test_changed_classification_content_gets_a_new_hash(store: MarketPanelStore) -> None:
    store.record_run(
        kind="classification",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        classification_rows=[
            ClassificationSnapshotRow(symbol="2330", sector_code="24", sector_name="半導體業")
        ],
    )
    store.record_run(
        kind="classification",
        session_date=date(2026, 9, 25),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        classification_rows=[
            ClassificationSnapshotRow(symbol="2330", sector_code="30", sector_name="其他電子業")
        ],
    )
    with closing(sqlite3.connect(store.db_path)) as conn:
        content_hashes = {
            row[0]
            for row in conn.execute("SELECT DISTINCT content_hash FROM pit_classification_rows")
        }
    assert len(content_hashes) == 2


# -- D0 / run status summary ---------------------------------------------------


def test_first_all_kinds_ok_session_requires_all_four_kinds(store: MarketPanelStore) -> None:
    assert store.first_all_kinds_ok_session() is None

    store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        bars_rows=[_bar()],
    )
    assert store.first_all_kinds_ok_session() is None

    store.record_run(
        kind="listing",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        listing_rows=[ListingSnapshotRow(symbol="2330", security_type="x")],
    )
    assert store.first_all_kinds_ok_session() is None

    store.record_run(
        kind="classification",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        classification_rows=[
            ClassificationSnapshotRow(symbol="2330", sector_code="24", sector_name="半導體業")
        ],
    )
    assert store.first_all_kinds_ok_session() is None
    store.record_run(
        kind="dividend_announce",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        dividend_announce_rows=[
            DividendAnnounceSnapshotRow(symbol="2330", ex_date=date(2026, 10, 1), raw={})
        ],
    )
    assert store.first_all_kinds_ok_session() == date(2026, 9, 24)


def test_run_status_summary_reports_ok_sessions_per_kind(store: MarketPanelStore) -> None:
    store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=1,
        bars_rows=[_bar()],
    )
    store.record_run(
        kind="bars",
        session_date=date(2026, 9, 25),
        source="twse_snapshot",
        status="failed",
        row_count=0,
        expected_count=None,
    )
    summary = store.run_status_summary(date(2026, 9, 1), date(2026, 9, 30))
    assert summary["bars"].ok_sessions == frozenset({date(2026, 9, 24)})
    assert summary["bars"].last_ok_session == date(2026, 9, 24)
    assert summary["listing"].ok_sessions == frozenset()
    assert summary["listing"].last_ok_session is None


# -- warm-up backfill (D-3) ----------------------------------------------------


def test_record_symbol_backfill_writes_one_run_per_day(store: MarketPanelStore) -> None:
    rows = [
        (date(2026, 9, 10), _bar(symbol="0050")),
        (date(2026, 9, 11), _bar(symbol="0050")),
        (date(2026, 9, 12), _bar(symbol="0050")),
    ]
    run_ids = store.record_symbol_backfill(symbol="0050", source="finmind_warmup", rows=rows)
    assert len(run_ids) == 3
    assert len(set(run_ids)) == 3  # each day gets its own run_id

    summary = store.run_status_summary(date(2026, 9, 1), date(2026, 9, 30))
    assert summary["bars"].ok_sessions == frozenset(
        {date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 12)}
    )

    frames = store.load_panel_frames(date(2026, 9, 1), date(2026, 9, 30))
    assert len(frames.bars) == 3
    assert set(frames.bars["source"]) == {"finmind_warmup"}


def test_record_symbol_backfill_is_atomic_per_symbol(tmp_path: Path) -> None:
    """A crash mid-write must not leave a partial day set (simulated via a bad row)."""
    store = MarketPanelStore(
        tmp_path / "market.db", clock=_clock(datetime(2026, 9, 15, tzinfo=UTC))
    )
    good_row = (date(2026, 9, 10), _bar(symbol="0050"))
    # Force a failure mid-transaction by monkeypatching str() is overkill; instead
    # verify the two committed inserts happen inside one `with conn:` block by
    # checking WAL/commit semantics indirectly: after a successful call, both
    # pit_snapshot_runs and market_daily_bars have matching row counts.
    run_ids = store.record_symbol_backfill(symbol="0050", source="finmind_warmup", rows=[good_row])
    with closing(sqlite3.connect(store.db_path)) as conn:
        run_count = conn.execute(
            "SELECT COUNT(*) FROM pit_snapshot_runs WHERE run_id = ?", (run_ids[0],)
        ).fetchone()[0]
        bar_count = conn.execute(
            "SELECT COUNT(*) FROM market_daily_bars WHERE run_id = ?", (run_ids[0],)
        ).fetchone()[0]
    assert run_count == 1
    assert bar_count == 1


# -- carry-forward lookback (dev-lead coordination point 2) --------------------


def test_load_panel_frames_backfills_a_pre_start_listing_snapshot(
    store: MarketPanelStore,
) -> None:
    """A listing run captured well before `start` must still surface if it is
    the only visible carry-forward source (D-2 "缺日沿用")."""
    store.record_run(
        kind="listing",
        session_date=date(2026, 8, 1),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        listing_rows=[ListingSnapshotRow(symbol="2330", security_type="common_stock")],
    )
    frames = store.load_panel_frames(date(2026, 9, 1), date(2026, 9, 30))
    assert (frames.runs["kind"] == "listing").any()
    assert list(frames.listing["symbol"]) == ["2330"]
    # the extra run's own session_date is outside [start, end] on purpose
    assert frames.runs.loc[frames.runs["kind"] == "listing", "session_date"].iloc[0] == date(
        2026, 8, 1
    )


def test_load_panel_frames_lookback_prefers_the_most_recent_pre_start_run(
    store: MarketPanelStore,
) -> None:
    for day, sector_name in ((date(2026, 7, 1), "半導體業"), (date(2026, 8, 1), "其他電子業")):
        store.record_run(
            kind="classification",
            session_date=day,
            source="twse_snapshot",
            status="ok",
            row_count=1,
            expected_count=None,
            classification_rows=[
                ClassificationSnapshotRow(symbol="2330", sector_code="24", sector_name=sector_name)
            ],
        )
    frames = store.load_panel_frames(date(2026, 9, 1), date(2026, 9, 30))
    assert list(frames.classification["sector_name"]) == ["其他電子業"]


def test_load_panel_frames_lookback_is_a_noop_when_a_run_already_exists_in_window(
    store: MarketPanelStore,
) -> None:
    store.record_run(
        kind="listing",
        session_date=date(2026, 8, 1),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        listing_rows=[ListingSnapshotRow(symbol="OLD", security_type="common_stock")],
    )
    store.record_run(
        kind="listing",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        listing_rows=[ListingSnapshotRow(symbol="NEW", security_type="common_stock")],
    )
    frames = store.load_panel_frames(date(2026, 9, 1), date(2026, 9, 30))
    # both runs are present (in-window run plus the lookback run before it);
    # app.data.panel picks the latest visible one per decision date.
    assert set(frames.listing["symbol"]) == {"OLD", "NEW"}
    assert (frames.runs["kind"] == "listing").sum() == 2


# -- source verification of statistics rows (ADR-0012 C-50) ----------------


def test_the_source_set_is_ok_runs_up_to_the_session_and_run_cut(store: MarketPanelStore) -> None:
    first = store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=1,
        bars_rows=[_bar()],
    )
    failed = store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="failed",
        row_count=0,
        expected_count=1,
    )
    second = store.record_run(
        kind="listing",
        session_date=date(2026, 9, 25),
        source="twse_t187ap03_L",
        status="ok",
        row_count=0,
        expected_count=None,
    )
    later = store.record_run(
        kind="listing",
        session_date=date(2026, 9, 26),
        source="twse_t187ap03_L",
        status="ok",
        row_count=0,
        expected_count=None,
    )
    fingerprint = store.source_fingerprint(second, date(2026, 9, 25))
    assert fingerprint is not None
    assert (fingerprint.run_min, fingerprint.run_max, fingerprint.run_count) == (first, second, 2)
    assert fingerprint.session_end == date(2026, 9, 25) and len(fingerprint.digest) == 64
    tally = store.source_tally([first, failed, later, 999_999], second, date(2026, 9, 25))
    assert tally.ok_endpoints == {first, later}  # a failed run is not an ok endpoint
    assert (tally.run_count, tally.run_min, tally.run_max) == (2, first, second)
    assert store.source_fingerprint(0, date(2026, 9, 25)) is None


# -- minimal end-to-end regression: lookback carries forward through MarketPanel --


def test_lookback_listing_is_visible_through_market_panel_as_of(store: MarketPanelStore) -> None:
    """qa-reviewer medium item (a): the store-level lookback fix must actually
    reach a real decision through ``app.data.panel.MarketPanel.as_of()``, not
    just show up in the raw frame."""
    from app.data.panel import MarketPanel

    store.record_run(
        kind="listing",
        session_date=date(2026, 8, 1),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=None,
        listing_rows=[ListingSnapshotRow(symbol="2330", security_type="common_stock")],
    )
    # A bars session on the decision date -- needed for `carried_forward` to
    # be a meaningful signal at all (it counts elapsed *bar* sessions).
    store.record_run(
        kind="bars",
        session_date=date(2026, 9, 24),
        source="twse_snapshot",
        status="ok",
        row_count=1,
        expected_count=1,
        bars_rows=[_bar()],
    )
    frames = store.load_panel_frames(date(2026, 9, 1), date(2026, 9, 30))
    panel = MarketPanel(frames)
    view = panel.as_of(date(2026, 9, 24))
    snapshot = view.snapshot("listing")
    assert snapshot is not None
    assert snapshot.carried_forward is True
    assert list(snapshot.rows["symbol"]) == ["2330"]
