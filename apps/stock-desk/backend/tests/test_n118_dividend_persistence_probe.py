"""The N-118 offline probe: event classes, row_count accounting, and its read-only promise.

Runs are written into a market DB under ``tmp_path`` through the real
``MarketPanelStore``; the probe then reads that file. No network, no real DB.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import sqlite3
import sys
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.data.interface import DividendAnnounceSnapshotRow
from app.data.market_panel import MarketPanelStore
from app.data.providers.finmind import FINMIND_BASE_URL, FinMindAdapter
from app.data.providers.twse_snapshot import TwseSnapshotAdapter
from app.directory.providers import TWSE_OPENAPI_BASE_URL
from app.services.pit_snapshot import capture_once

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "n118_dividend_persistence_probe.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("n118_dividend_persistence_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load()

TODAY = date(2026, 10, 24)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class _Capture:
    """Writes ``dividend_announce`` runs for chosen sessions into a fake market DB."""

    def __init__(self, path: Path) -> None:
        self.clock = _Clock()
        self.path = path
        self.store = MarketPanelStore(path, clock=self.clock)
        self._tick = 0

    def run(
        self,
        session: date,
        rows: Sequence[tuple[str, date | None]],
        *,
        status: str = "ok",
        row_count: int | None = None,
    ) -> int:
        self._tick += 1
        self.clock.now = datetime(2026, 1, 1, tzinfo=UTC).replace(hour=self._tick % 24)
        announce = [
            DividendAnnounceSnapshotRow(
                symbol=symbol,
                ex_date=ex_date,
                raw={
                    "Code": symbol,
                    "Name": f"NAME-{symbol}",
                    "Date": ex_date.isoformat() if ex_date else "garbled",
                },
            )
            for symbol, ex_date in rows
        ]
        return self.store.record_run(
            kind="dividend_announce",
            session_date=session,
            source="twse_snapshot",
            status=status,  # type: ignore[arg-type]
            row_count=len(announce) if row_count is None else row_count,
            expected_count=None,
            dividend_announce_rows=announce if status == "ok" else [],
        )


def _d(month: int, day: int) -> date:
    return date(2026, month, day)


def _analyze(path: Path) -> Any:
    with closing(probe.open_read_only(path)) as conn:
        runs, contents = probe.load(conn)
    return probe.analyze(runs, contents)


def _count(report: Any, name: str, *, closed: bool = True) -> int:
    return int(report.class_counts.get((name, closed), 0))


def test_a_persistent_closed_event_is_the_baseline(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = _d(9, 10)
    for day in (1, 2, 3, 4):
        capture.run(_d(9, day), [("2330", e)])
    capture.run(_d(9, 10), [("1101", _d(10, 1))])  # last run is on the ex-date: closed
    report = _analyze(capture.path)
    assert _count(report, "persistent") == 1
    assert _count(report, "vanished_gone") == 0 and _count(report, "vanished_returned") == 0
    assert report.testable_closed == 1
    assert report.drop_episodes == 0


def test_disappearance_without_return_is_vanished_gone_symbol_gone(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = _d(9, 20)
    capture.run(_d(9, 1), [("2330", e), ("1101", _d(10, 1))])
    capture.run(_d(9, 2), [("2330", e), ("1101", _d(10, 1))])
    capture.run(_d(9, 3), [("1101", _d(10, 1))])  # 2330 gone entirely
    capture.run(_d(9, 4), [("1101", _d(10, 1))])
    capture.run(_d(9, 21), [("1101", _d(10, 1))])  # past the ex-date: closed
    report = _analyze(capture.path)
    assert _count(report, "vanished_gone") == 1
    assert report.split_counts[("symbol_gone", True)] == 1
    event = report.vanished[0]
    assert (event.symbol, event.ex_date, event.kind) == ("2330", e, "vanished_gone")
    assert (event.first_listed_run_id, event.first_missing_run_id) == (1, 3)
    assert event.last_listed_run_id == 2


def test_reappearance_is_vanished_returned_and_counts_the_gap(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = _d(9, 20)
    capture.run(_d(9, 1), [("2330", e)])
    capture.run(_d(9, 2), [("1101", _d(10, 1))])  # 2330 missing
    capture.run(_d(9, 3), [("2330", e), ("1101", _d(10, 1))])  # back
    capture.run(_d(9, 21), [("1101", _d(10, 1))])
    report = _analyze(capture.path)
    assert _count(report, "vanished_returned") == 1
    assert _count(report, "vanished_gone") == 0
    assert report.vanished[0].split is None
    # Run 2 lost 2330 (pending, 1 of 1 pending): one drop episode, share 1.0.
    assert report.drop_episodes >= 1 and report.largest_drop == 1


def test_reschedule_old_key_gone_new_key_added_is_candidate(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    capture.run(_d(9, 1), [("2330", _d(9, 20))])
    capture.run(_d(9, 2), [("2330", _d(9, 25))])  # old key gone, new key for the same symbol
    capture.run(_d(9, 3), [("2330", _d(9, 25))])
    capture.run(_d(9, 26), [("1101", _d(10, 1))])
    report = _analyze(capture.path)
    assert report.split_counts[("reschedule_candidate", True)] == 1
    assert report.split_counts.get(("symbol_gone", True), 0) == 0


def test_symbol_with_other_existing_event_is_not_called_a_reschedule(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    both = [("2330", _d(9, 20)), ("2330", _d(10, 5))]
    capture.run(_d(9, 1), both)
    capture.run(_d(9, 2), both)
    capture.run(_d(9, 3), [("2330", _d(10, 5))])  # 09-20 gone, 10-05 was already there
    capture.run(_d(9, 21), [("2330", _d(10, 5))])
    report = _analyze(capture.path)
    assert report.split_counts[("symbol_relisted_existing", True)] == 1
    assert report.split_counts.get(("reschedule_candidate", True), 0) == 0


def test_open_events_are_reported_separately_from_closed_ones(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = _d(12, 20)
    capture.run(_d(9, 1), [("2330", e)])
    capture.run(_d(9, 2), [("2330", e)])
    capture.run(_d(9, 3), [("1101", _d(12, 21))])  # 2330 gone, but the ex-date is far away
    report = _analyze(capture.path)
    assert _count(report, "vanished_gone", closed=False) == 1
    assert _count(report, "vanished_gone", closed=True) == 0
    assert report.events_closed == 0 and report.testable_closed == 0
    assert report.vanished[0].closed is False


def test_single_observation_and_first_seen_on_or_after_ex_are_not_tested(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    capture.run(_d(9, 1), [("2330", _d(9, 2))])  # listed once, then its ex-date passes
    capture.run(_d(9, 5), [("1101", _d(9, 5))])  # first seen on its ex-date
    capture.run(_d(9, 8), [("1101", _d(9, 5))])
    report = _analyze(capture.path)
    assert _count(report, "single_observation") == 1
    assert _count(report, "first_seen_on_or_after_ex") == 1
    assert report.testable_closed == 0
    assert not report.vanished


def test_a_failed_run_is_not_an_absence(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = _d(9, 20)
    capture.run(_d(9, 1), [("2330", e)])
    capture.run(_d(9, 2), [], status="failed", row_count=0)
    capture.run(_d(9, 3), [("2330", e)])
    capture.run(_d(9, 21), [("1101", _d(10, 1))])
    report = _analyze(capture.path)
    assert _count(report, "persistent") == 1
    assert report.usable_runs == 3
    assert dict(report.status_counts) == {"failed": 1}


def test_key_duplicate_in_one_batch_makes_stored_less_than_row_count(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = _d(10, 1)
    capture.run(_d(9, 1), [("2330", e), ("2330", e), ("1101", e)])  # row_count 3, 2 stored
    capture.run(_d(9, 2), [("2330", e), ("1101", e)])  # row_count 2, 2 stored
    report = _analyze(capture.path)
    assert (report.ok_runs, report.rc_equal, report.rc_less) == (2, 1, 1)
    assert report.deficit_sum == 1 and report.deficit_max == 1
    assert report.affected_hashes == 1
    assert report.mismatch_run_ids == (1,)
    assert report.anomaly_run_ids == ()


def test_row_count_deficit_equals_collapsed_rows_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real ``_fetch_dividend_announce`` + ``capture_once`` + store, fake HTTP, fake DB."""
    monkeypatch.setenv("FINMIND_API_TOKEN", "test-token-not-a-secret")
    candidate = date(2026, 9, 24)
    stock_day_all: list[dict[str, str]] = [
        {
            "Code": symbol,
            "Name": f"T{symbol}",
            "TradeVolume": "1000000",
            "TradeValue": "100000000",
            "OpeningPrice": "10.00",
            "HighestPrice": "10.50",
            "LowestPrice": "9.50",
            "ClosingPrice": "10.20",
            "Change": "0.20",
            "Transaction": "100",
        }
        for symbol in ("2330", "2317", "1101")
    ]
    sector_profile = json.loads(
        (Path(__file__).parent / "fixtures" / "twse_openapi_t187ap03_l.json").read_text("utf-8")
    )
    # 5 payload rows: one without Code (skipped), three that collapse to one key
    # (the symbol differs only by surrounding blanks), one distinct.
    dividends: list[dict[str, str]] = [
        {"Code": "2330", "Date": "1150930", "CashDividend": "1.0"},
        {"Code": " 2330", "Date": "1150930", "CashDividend": "2.0"},
        {"Code": "2330 ", "Date": "1150930", "CashDividend": "3.0"},
        {"Code": "", "Date": "1150930", "CashDividend": "4.0"},
        {"Code": "1101", "Date": "1150930", "CashDividend": "5.0"},
    ]

    def twse_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("STOCK_DAY_ALL"):
            return httpx.Response(200, json=stock_day_all)
        if path.endswith("t187ap03_L"):
            return httpx.Response(200, json=sector_profile)
        if path.endswith("TWT48U_ALL"):
            return httpx.Response(200, json=dividends)
        return httpx.Response(404, json={})

    by_code = {row["Code"]: row for row in stock_day_all}

    def finmind_handler(request: httpx.Request) -> httpx.Response:
        row = by_code[dict(request.url.params)["data_id"]]
        data = [
            {
                "date": candidate.isoformat(),
                "stock_id": row["Code"],
                "Trading_Volume": int(row["TradeVolume"]),
                "Trading_money": int(row["TradeValue"]),
                "open": row["OpeningPrice"],
                "max": row["HighestPrice"],
                "min": row["LowestPrice"],
                "close": row["ClosingPrice"],
                "spread": row["Change"],
                "Trading_turnover": int(row["Transaction"]),
            }
        ]
        return httpx.Response(200, json={"status": 200, "data": data})

    adapter = TwseSnapshotAdapter(
        client=RateLimitedClient(
            base_url=TWSE_OPENAPI_BASE_URL,
            min_interval_seconds=0.0,
            transport=httpx.MockTransport(twse_handler),
            sleep_fn=lambda _s: None,
        ),
        finmind=FinMindAdapter(
            client=RateLimitedClient(
                base_url=FINMIND_BASE_URL,
                min_interval_seconds=0.0,
                transport=httpx.MockTransport(finmind_handler),
                sleep_fn=lambda _s: None,
            )
        ),
        clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        candidate_session_date=lambda: candidate,
        sample_seed=42,
    )
    path = tmp_path / "market.db"
    store = MarketPanelStore(path, clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC))
    summary = capture_once(adapter, store)
    record = next(r for r in summary.records if r.kind == "dividend_announce")
    assert (record.status, record.row_count) == ("ok", 4)  # the blank-Code row is skipped
    report = _analyze(path)
    assert (report.ok_runs, report.rc_less, report.rc_equal) == (1, 1, 0)  # other kinds ignored
    assert report.deficit_sum == 2  # 4 parsed rows -> 2 distinct keys
    assert report.mismatch_run_ids == (record.run_id,)


def test_stored_greater_than_row_count_and_other_anomalies_are_reported(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = _d(10, 1)
    greater = capture.run(_d(9, 1), [("2330", e), ("1101", e)], row_count=1)
    no_hash = capture.run(_d(9, 2), [], row_count=3)  # ok but nothing stored: hash is NULL
    nonpositive = capture.run(_d(9, 3), [("2330", e)], row_count=0)
    with closing(sqlite3.connect(capture.path)) as conn, conn:  # ok + hash with no rows behind it
        conn.execute(
            "INSERT INTO pit_snapshot_runs (kind, session_date, recorded_at, source, status, "
            "row_count, expected_count, content_hash, reason) VALUES "
            "('dividend_announce', '2026-09-04', '2026-09-04T00:00:00+00:00', 's', 'ok', 2, "
            "NULL, 'deadbeef', NULL)"
        )
    report = _analyze(capture.path)
    assert report.rc_greater == 2  # run 1 (2 > 1) and run 3 (1 > 0)
    assert report.rc_no_hash == 1
    assert report.rc_nonpositive == 1
    assert report.rc_zero_stored == 1
    assert report.rc_less == 0 and report.deficit_sum == 0  # none of these is a collision
    assert set(report.anomaly_run_ids) == {greater, no_hash, nonpositive, 4}


def test_row_count_change_distribution_and_largest_drop() -> None:
    def usable(run_id: int, row_count: int) -> Any:
        return probe.RunRecord(run_id, "ok", _d(9, run_id), f"h{run_id}", row_count)

    runs = [usable(i + 1, rc) for i, rc in enumerate((100, 99, 98, 60, 61, 62))]
    contents: dict[str, dict[str, tuple[str, date | None]]] = {f"h{i}": {} for i in range(1, 7)}
    report = probe.analyze(runs, contents)
    assert sorted(report.row_count_deltas) == [-38, -1, -1, 1, 1]
    assert report.row_drop_largest == 38
    assert report.row_drop_largest_share == pytest.approx(38 / 98)
    assert report.row_drop_pairs_over_share == 1  # only 98 -> 60 is >= 0.10
    text = probe.render(report, today=TODAY)
    assert "delta min / p25 / median / p75 / max" in text
    assert "-38 / -1 / -1 / 1 / 1" in text
    assert probe.percentile([1, 2, 3, 4, 5], 25) == 2
    assert probe.percentile([1, 2, 3, 4, 5], 50) == 3
    assert probe.percentile([7], 75) == 7


def test_fewer_than_two_runs_gives_an_empty_change_section(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    capture.run(_d(9, 1), [("2330", _d(10, 1))])
    report = _analyze(capture.path)
    assert report.row_count_deltas == () and report.row_drop_largest_share is None
    text = probe.render(report, today=TODAY)
    assert "fewer than 2 usable ok runs" in text
    assert report.usable_runs == 1 and report.events == 1


def test_conclusion_fields_proposed_thresholds_and_the_fixed_sentence(tmp_path: Path) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = _d(9, 10)
    capture.run(_d(9, 1), [("2330", e)])
    capture.run(_d(9, 2), [("2330", e)])
    capture.run(_d(9, 2), [("2330", e)])  # second ok run in one session
    capture.run(_d(9, 10), [("1101", _d(10, 1))])
    text = probe.render(_analyze(capture.path), today=TODAY)
    assert "-- Conclusion-format fields" in text
    assert re.search(r"usable ok runs the reading rests on\s*: 4\b", text)
    assert re.search(r"distinct session_date among them\s*: 3\b", text)
    assert re.search(r"closed testable events \(>=2 runs\)\s*: 1\b", text)
    assert "2026-10-24" in text and "date.today()" in text
    assert "樣本不足或未完成一律視為不成立；成立與否須送風控確認。" in text
    assert (
        text.rstrip().splitlines()[-2] == "樣本不足或未完成一律視為不成立；成立與否須送風控確認。"
    )
    assert "PROPOSED, pending quant and risk-control confirmation" in text
    assert "This script does not judge" in text
    assert "testable closed events >= 30" in text and "usable ok runs >= 20" in text
    assert "largest drop in one pair >= 3 and share >= 0.10" in text
    lowered = text.lower()
    assert "verdict" not in lowered.replace("not a verdict", "") and "refuted" not in lowered
    assert "sessions holding more than one ok run" in text


def test_default_output_has_no_symbols_or_names_and_detail_adds_only_symbols(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capture = _Capture(tmp_path / "market.db")
    e = _d(9, 20)
    capture.run(_d(9, 1), [("2330", e), ("1101", _d(10, 1))])
    capture.run(_d(9, 2), [("1101", _d(10, 1))])
    capture.run(_d(9, 21), [("1101", _d(10, 1))])

    assert probe.main(["--db-path", str(capture.path)]) == 0
    plain = capsys.readouterr().out
    assert "2330" not in plain and "1101" not in plain and "NAME-" not in plain

    assert probe.main(["--db-path", str(capture.path), "--detail", "5"]) == 0
    detailed = capsys.readouterr().out
    assert "2330" in detailed and "E=2026-09-20" in detailed and "vanished_gone" in detailed
    assert "first_missing_run=2" in detailed
    assert "NAME-" not in detailed and "CashDividend" not in detailed
    assert "1101" not in detailed  # only vanished events are listed

    assert probe.main(["--db-path", str(capture.path), "--detail", "0"]) == 0
    assert "2330" not in capsys.readouterr().out


def test_the_probe_is_read_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capture = _Capture(tmp_path / "market.db")
    capture.run(_d(9, 1), [("2330", _d(10, 1))])
    capture.run(_d(9, 2), [("2330", _d(10, 1))])
    before = hashlib.sha256(capture.path.read_bytes()).hexdigest()

    assert probe.main(["--db-path", str(capture.path), "--detail", "3"]) == 0
    assert "N-118 probe" in capsys.readouterr().out

    # The connection itself refuses writes, whatever the script does.
    with closing(probe.open_read_only(capture.path)) as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM pit_snapshot_runs")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE x (y INTEGER)")
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
    capture.run(_d(9, 1), [("2330", _d(10, 1))])
    assert probe.main([], env={probe.DB_PATH_ENV_VAR: str(capture.path)}) == 0
    assert "N-118 probe" in capsys.readouterr().out


def test_only_two_select_statements_and_never_raw_json() -> None:
    statements = [probe._RUNS_SQL, probe._ROWS_SQL]
    for sql in statements:
        assert sql.strip().upper().startswith("SELECT")
        assert "raw_json" not in sql.lower() and "name" not in sql.lower()
    assert "pit_snapshot_runs" in statements[0] and "pit_dividend_announce_rows" in statements[1]
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert source.count(".execute(") == 3  # the two SELECTs and PRAGMA query_only
    assert "raw_json" not in re.sub(r'""".*?"""', "", source, count=1, flags=re.DOTALL)


def test_the_script_uses_only_the_standard_library() -> None:
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
