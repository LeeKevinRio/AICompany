"""The ADR-0016 V-1 offline probe: arithmetic, anomalies, and its read-only promise.

Runs are written into a market DB under ``tmp_path`` through the real
``MarketPanelStore``; the probe then reads that file. No network, no real DB.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import sys
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.data.interface import DividendAnnounceSnapshotRow
from app.data.market_panel import MarketPanelStore

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "v1_announce_lead_probe.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("v1_announce_lead_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load()


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class _Capture:
    """Writes ``dividend_announce`` runs at chosen UTC instants."""

    def __init__(self, path: Path) -> None:
        self.clock = _Clock()
        self.path = path
        self.store = MarketPanelStore(path, clock=self.clock)

    def run(
        self,
        at: datetime,
        rows: Sequence[tuple[str, date | None]],
        *,
        status: str = "ok",
    ) -> None:
        self.clock.now = at
        announce = [
            DividendAnnounceSnapshotRow(
                symbol=symbol,
                ex_date=ex_date,
                raw={"Code": symbol, "Date": ex_date.isoformat() if ex_date else "garbled"},
            )
            for symbol, ex_date in rows
        ]
        self.store.record_run(
            kind="dividend_announce",
            session_date=at.date(),
            source="twse_snapshot",
            status=status,  # type: ignore[arg-type]
            row_count=len(announce),
            expected_count=None,
            dividend_announce_rows=announce if status == "ok" else [],
        )


def _utc(month: int, day: int, hour: int = 13, minute: int = 30) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)  # 21:30 Taipei by default


def _analyze(path: Path) -> Any:
    with closing(probe.open_read_only(path)) as conn:
        runs, unparsed = probe.load_runs(conn)
    return probe.analyze(runs, unparsed)


def test_lead_is_floor_of_days_from_first_listing_to_taipei_midnight_of_e() -> None:
    # Listed 2026-09-05 21:30 Taipei; E 10-10 00:00 Taipei is 34 days 2.5 h later.
    first = datetime(2026, 9, 5, 13, 30, tzinfo=UTC)
    assert probe.lead_days(first, date(2026, 10, 10)) == 34
    # Listed 1h before E begins (23:00 Taipei): 0 days. After E began: negative.
    assert probe.lead_days(datetime(2026, 10, 9, 15, 0, tzinfo=UTC), date(2026, 10, 10)) == 0
    assert probe.lead_days(datetime(2026, 10, 10, 2, 0, tzinfo=UTC), date(2026, 10, 10)) == -1


def test_leads_censoring_and_the_minimum(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e1, e2, e3 = date(2026, 9, 20), date(2026, 10, 10), date(2026, 9, 25)
    capture.run(_utc(9, 1), [("1101", e1)])  # first run: 1101 is left-censored
    capture.run(_utc(9, 5), [("1101", e1), ("2330", e2)])  # 2330 appears: l = 34
    capture.run(_utc(9, 22), [("2330", e2), ("2317", e3)])  # 2317 appears 2d 2.5h ahead: l = 2
    report = _analyze(capture.path)
    leads = {event.symbol: event for event in report.events}
    assert leads["1101"].censored is True
    assert leads["2330"].lead_days == 34 and leads["2330"].censored is False
    assert leads["2317"].lead_days == 2
    assert probe.min_lead(report.events) == 2
    assert probe.min_lead(report.events, uncensored_only=True) == 2
    assert report.anomalies == ()


def test_an_event_that_disappears_before_e_is_reported_per_run(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = date(2026, 9, 30)
    capture.run(_utc(9, 1), [("1101", date(2026, 9, 2))])
    capture.run(_utc(9, 5), [("2330", e)])
    capture.run(_utc(9, 6), [("1101", date(2026, 9, 2))])  # 2330 gone entirely
    capture.run(_utc(9, 7), [("2330", date(2026, 10, 3))])  # listed under another date
    capture.run(_utc(9, 8), [("2330", e)])  # back
    report = _analyze(capture.path)
    pairs = [
        (a.symbol, a.ex_date, a.recorded_at.date(), a.other_dates)
        for a in report.anomalies
        if a.symbol == "2330"
    ]
    assert pairs == [
        ("2330", e, date(2026, 9, 6), ()),
        ("2330", e, date(2026, 9, 7), (date(2026, 10, 3),)),
        # The 10-03 date seen on 09-07 is an event of its own and is gone again on 09-08.
        ("2330", date(2026, 10, 3), date(2026, 9, 8), (e,)),
    ]
    # 1101's own date passed on 09-02 00:00 Taipei: later runs owe it nothing.
    assert not [a for a in report.anomalies if a.symbol == "1101"]


def test_runs_that_are_not_ok_are_ignored_and_empty_ok_runs_count_as_listing_nothing(
    tmp_path: Path,
) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = date(2026, 9, 30)
    capture.run(_utc(9, 1), [("2330", e)])
    capture.run(_utc(9, 2), [], status="failed")
    capture.run(_utc(9, 3), [])  # ok but no rows
    report = _analyze(capture.path)
    assert report.runs == 2
    assert report.empty_runs == 1
    assert [a.run_id for a in report.anomalies] == [3]  # run 2 was failed


def test_sample_coverage_weekdays_and_seasons(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    capture.run(datetime(2026, 5, 29, 13, 30, tzinfo=UTC), [("1101", date(2026, 7, 1))])
    capture.run(datetime(2026, 6, 2, 13, 30, tzinfo=UTC), [("1101", date(2026, 7, 1))])
    capture.run(datetime(2026, 10, 1, 13, 30, tzinfo=UTC), [("1101", date(2026, 11, 1))])
    report = _analyze(capture.path)
    assert report.complete_seasons == (2026,)
    missing = report.weekdays_without_run
    assert date(2026, 5, 29) not in missing and date(2026, 6, 1) in missing
    assert all(day.weekday() < 5 for day in missing)

    short = _Capture(tmp_path / "short.db")
    short.run(_utc(9, 1), [("1101", date(2026, 9, 20))])
    assert _analyze(short.path).complete_seasons == ()


def test_unparsed_rows_are_counted_not_turned_into_events(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    capture.run(_utc(9, 1), [("1101", date(2026, 9, 20)), ("2330", None)])
    report = _analyze(capture.path)
    assert [e.symbol for e in report.events] == ["1101"]
    assert report.unparsed_rows == 1


def test_the_probe_is_read_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capture = _Capture(tmp_path / "market.db")
    capture.run(_utc(9, 1), [("1101", date(2026, 9, 20))])
    capture.run(_utc(9, 5), [("2330", date(2026, 10, 10))])
    before = hashlib.sha256(capture.path.read_bytes()).hexdigest()

    assert probe.main(["--db-path", str(capture.path)]) == 0
    out = capsys.readouterr().out
    assert "min(l), all events" in out
    assert "Do not edit MIN_ANNOUNCE_LEAD_DAYS" in out

    # The connection itself refuses writes, whatever the script does.
    with closing(probe.open_read_only(capture.path)) as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM pit_snapshot_runs")
    assert hashlib.sha256(capture.path.read_bytes()).hexdigest() == before
    # Reading a WAL database may leave SQLite's own -wal/-shm sidecars; nothing else appears.
    assert {p.name for p in tmp_path.iterdir()} <= {"market.db", "market.db-wal", "market.db-shm"}


def test_a_missing_file_is_refused_and_not_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    absent = tmp_path / "absent.db"
    assert probe.main(["--db-path", str(absent)]) == 2
    assert not absent.exists()
    assert "not found" in capsys.readouterr().err


def test_a_db_without_runs_or_tables_exits_2_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = _Capture(tmp_path / "empty.db")
    assert probe.main(["--db-path", str(empty.path)]) == 2
    assert "nothing to analyze" in capsys.readouterr().err

    bare = tmp_path / "bare.db"
    with closing(sqlite3.connect(bare)) as conn, conn:
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
    assert probe.main(["--db-path", str(bare)]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_the_db_path_falls_back_to_the_environment_variable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capture = _Capture(tmp_path / "market.db")
    capture.run(_utc(9, 1), [("1101", date(2026, 9, 20))])
    assert probe.main([], env={probe.DB_PATH_ENV_VAR: str(capture.path)}) == 0
    assert "V-1 probe" in capsys.readouterr().out


def test_the_script_uses_only_the_standard_library() -> None:
    import ast

    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "app" not in imported
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}
