"""ADR-0030 failure condition F-2, first sentence: rolling 20-weekday windows (supplement 5).

Synthetic ledgers on ``tmp_path`` files, rows inserted as stored (the store's
reads are what is under test): a claim, runs with their end rows, snapshots
whose bars are final (fetched 20:00 Taipei on the session day) and
``late = 0`` / ``late = 1`` records. Each S-10a case of supplement 5 has a test
here; C5-3 (the counts only in ``store.py``, one weekday function with T2) is
checked by AST.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from app.forecast import report
from app.forecast.canonical import canonical_timestamp
from app.forecast.store import (
    F2_WINDOW_WEEKDAYS,
    ForecastStore,
    ForecastStoreError,
)
from app.outlook.inputs import late_cutoff_at
from tests import approved_copy
from tests.forecast_ledger_helpers import TAIPEI, file_ledger, insert, row, weekdays

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
CLAIM_H3 = "market|h3|r1|dirdef-v1.0|forward"
CLAIM_H5 = "market|h5|r1|dirdef-v1.0|forward"
LABEL_WORDS = ("bullish", "bearish", "range", "insufficient", "偏多", "偏空", "震盪", "模型=")

#: 2026-10-05 is a Monday; 20 weekdays from it end on Friday 2026-10-30.
MONDAY = date(2026, 10, 5)


def at(day: date, hour: int = 22, minute: int = 10) -> datetime:
    return datetime.combine(day, time(hour, minute), TAIPEI)


def after_cutoff(day: date) -> datetime:
    """The first instant ``day``'s ``late_cutoff_at`` has passed: next day 00:00 Taipei."""
    return datetime.combine(day + timedelta(days=1), time(0), TAIPEI)


@dataclass
class Ledger:
    """A synthetic ledger: one row writer per table, as stored."""

    path: Path
    runs: int = 0
    records: int = 0
    snapshots: int = 0
    claims: list[str] = field(default_factory=list)

    def execute(self, table: str, values: dict[str, object]) -> None:
        with closing(sqlite3.connect(self.path, isolation_level=None)) as conn:
            insert(conn, table, values)

    def claim(self, claim_id: str, *, horizon: int, registered: datetime) -> None:
        self.execute(
            "forecast_claim_registry",
            row(
                "forecast_claim_registry",
                claim_id=claim_id,
                horizon=horizon,
                registered_at=canonical_timestamp(registered),
            ),
        )
        self.claims.append(claim_id)

    def run(self, started: datetime, outcome: str = "ok") -> int:
        self.runs += 1
        stamp = canonical_timestamp(started)
        self.execute("forecast_run", row("forecast_run", started_at=stamp))
        self.execute(
            "forecast_run_end",
            row(
                "forecast_run_end",
                run_id=self.runs,
                outcome=outcome,
                candidate_t=None if outcome == "inputs_not_ready" else "2026-10-01",
                records_written=0,
                ended_at=stamp,
            ),
        )
        return self.runs

    def snapshot(self, sessions: Sequence[date]) -> None:
        bars = [
            {
                "session_date": day.isoformat(),
                "as_of": canonical_timestamp(at(day, 20, 0)),
                "fetched_at": canonical_timestamp(at(day, 20, 0)),
            }
            for day in sorted(sessions)
        ]
        text = json.dumps(bars)
        self.snapshots += 1
        self.execute(
            "forecast_input_series",
            row(
                "forecast_input_series",
                content_sha256=hashlib.sha256(f"{self.snapshots}{text}".encode()).hexdigest(),
                bars_json=text,
            ),
        )

    def record(self, claim_id: str, day: date, *, late: int = 0, horizon: int = 3) -> None:
        self.records += 1
        self.execute(
            "forecast_record",
            row(
                "forecast_record",
                forecast_id=f"01JCZ{self.records:021d}",
                claim_id=claim_id,
                horizon=horizon,
                data_as_of=day.isoformat(),
                late=late,
                valid_until_session_estimate=(day + timedelta(days=10)).isoformat(),
                late_cutoff_at=canonical_timestamp(late_cutoff_at(day)),
                inputs_max_fetched_at=canonical_timestamp(at(day, 20, 0)),
                created_at=canonical_timestamp(
                    late_cutoff_at(day) + timedelta(hours=1) if late else at(day)
                ),
            ),
        )


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    built = Ledger(path=file_ledger(tmp_path))
    built.claim(CLAIM_H3, horizon=3, registered=at(date(2026, 9, 1), 9, 0))
    built.claim(CLAIM_H5, horizon=5, registered=at(date(2026, 9, 1), 9, 1))
    return built


def store(ledger: Ledger) -> ForecastStore:
    return ForecastStore(ledger.path)


def recorded_window(ledger: Ledger, days: Sequence[date], *, skip: Sequence[date] = ()) -> None:
    """One snapshot over ``days`` and a ``late = 0`` record of both claims on each but ``skip``."""
    ledger.snapshot(days)
    for day in days:
        if day not in skip:
            ledger.record(CLAIM_H3, day)
            ledger.record(CLAIM_H5, day, horizon=5)


# --- (b) the start ------------------------------------------------------------------------------


def test_no_run_means_no_start_and_no_window(ledger: Ledger) -> None:
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(date(2026, 11, 18)))
    assert status.start is None and status.window is None
    assert status.weekdays == 0 and not status.full and not status.ever_held


def test_the_period_before_the_first_run_is_not_counted(ledger: Ledger) -> None:
    # Registered 2026-09-01, first run 2026-10-05: the September sessions, all without a
    # record, are outside every window.
    september = weekdays(date(2026, 9, 1), 24)
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY))
    recorded_window(ledger, [*september, *window], skip=september)
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.start == MONDAY
    assert status.full and status.window is not None
    assert (status.window.first, status.window.last) == (MONDAY, window[-1])
    assert status.window.missed_sessions == 0
    assert status.window.denominator == F2_WINDOW_WEEKDAYS
    assert not status.window.holds and not status.ever_held


def test_the_start_is_the_registration_when_it_is_later(tmp_path: Path) -> None:
    ledger = Ledger(path=file_ledger(tmp_path))
    ledger.run(at(date(2026, 9, 28)))  # a run before this claim existed
    ledger.claim(CLAIM_H3, horizon=3, registered=at(date(2026, 10, 3), 9, 0))  # a Saturday
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(date(2026, 10, 6)))
    assert status.start == date(2026, 10, 3)
    assert status.window is not None and status.window.first == MONDAY
    assert status.weekdays == 2


def test_the_start_counts_when_it_is_a_weekday(ledger: Ledger) -> None:
    ledger.run(at(MONDAY))
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(MONDAY))
    assert status.weekdays == 1 and status.window is not None
    assert status.window.first == status.window.last == MONDAY


# --- (a) the current day ------------------------------------------------------------------------


def test_the_current_day_is_not_counted(ledger: Ledger) -> None:
    ledger.run(at(MONDAY), outcome="inputs_not_ready")
    before = datetime.combine(MONDAY, time(23, 59, 59, 999999), TAIPEI)
    early = store(ledger).f2_status(CLAIM_H3, now=before)
    assert early.weekdays == 0 and early.window is None
    late = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(MONDAY))
    assert late.weekdays == 1
    assert late.window is not None and late.window.not_ready_days == 1


# --- (d) the numerator --------------------------------------------------------------------------


def test_two_not_ready_runs_on_one_day_count_once_even_with_an_ok_run(ledger: Ledger) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY, 22, 10), outcome="inputs_not_ready")
    ledger.run(at(MONDAY, 23, 10), outcome="inputs_not_ready")
    ledger.run(at(MONDAY, 23, 40), outcome="ok")
    recorded_window(ledger, window)
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.window is not None
    assert status.window.not_ready_days == 1 and status.window.missed_sessions == 0


def test_a_weekend_not_ready_run_inside_the_range_counts(ledger: Ledger) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY))
    ledger.run(at(date(2026, 10, 10)), outcome="inputs_not_ready")  # Saturday
    recorded_window(ledger, window)
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.window is not None and status.window.not_ready_days == 1


def test_a_session_never_final_on_its_day_and_never_recorded_counts_two(ledger: Ledger) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    missing = window[4]
    ledger.run(at(MONDAY))
    ledger.run(at(missing), outcome="inputs_not_ready")
    recorded_window(ledger, window, skip=[missing])  # the later snapshot holds it, final
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.window is not None
    assert (status.window.missed_sessions, status.window.not_ready_days) == (1, 1)
    assert status.window.numerator == 2


def test_late_records_do_not_count_as_recorded(ledger: Ledger) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY))
    recorded_window(ledger, window, skip=window[:3])
    for day in window[:3]:
        ledger.record(CLAIM_H3, day, late=1)
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.window is not None and status.window.missed_sessions == 3


def test_each_claim_counts_its_own_records(ledger: Ledger) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY))
    ledger.snapshot(window)
    for day in window:
        ledger.record(CLAIM_H3, day)
    h3 = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    h5 = store(ledger).f2_status(CLAIM_H5, now=after_cutoff(window[-1]))
    assert h3.window is not None and h3.window.missed_sessions == 0
    assert h5.window is not None and h5.window.missed_sessions == F2_WINDOW_WEEKDAYS


def test_the_union_of_every_snapshot_is_counted_not_only_the_latest(ledger: Ledger) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY))
    ledger.snapshot(window[:10])  # an older snapshot holds the first ten sessions
    ledger.snapshot(window[10:])  # the latest one only the last ten
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.window is not None and status.window.missed_sessions == F2_WINDOW_WEEKDAYS


# --- (e) the denominator and the threshold ------------------------------------------------------


def test_a_holiday_heavy_window_uses_min_20_s_as_its_denominator(ledger: Ledger) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    sessions = window[:12]  # eight weekdays closed: s = 12
    ledger.run(at(MONDAY))
    recorded_window(ledger, sessions, skip=sessions[:4])
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.window is not None
    assert status.window.denominator == 12 and status.window.numerator == 4
    # 4 > 30 % of 12, though 4 would not exceed 30 % of a fixed 20.
    assert status.window.holds and status.ever_held


@pytest.mark.parametrize(("missed", "holds"), [(6, False), (7, True)])
def test_the_threshold_is_strictly_more_than_30_percent(
    ledger: Ledger, missed: int, holds: bool
) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY))
    recorded_window(ledger, window, skip=window[:missed])
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.window is not None and status.window.denominator == F2_WINDOW_WEEKDAYS
    assert status.window.holds is holds


def test_a_window_with_no_final_session_holds_on_any_not_ready_day(ledger: Ledger) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY), outcome="inputs_not_ready")
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.window is not None
    assert status.window.denominator == 0 and status.window.holds


def test_s19a_a_full_window_with_no_final_session_and_nothing_counted_holds(
    ledger: Ledger,
) -> None:
    # Supplement 9 point 4: denominator 0, numerator 0 -- held, and ever held.
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY))
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(window[-1]))
    assert status.full and status.window is not None
    assert (status.window.denominator, status.window.numerator) == (0, 0)
    assert status.window.holds and status.ever_held


def test_s19a_a_short_range_with_nothing_counted_is_still_not_held(ledger: Ledger) -> None:
    # Supplement 9 point 4 applies to full windows only: (f) is unchanged.
    ledger.run(at(MONDAY))
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(weekdays(MONDAY, 5)[-1]))
    assert not status.full and status.window is not None
    assert status.window.numerator == 0 and not status.window.holds


# --- (c) rolling and "ever held" ----------------------------------------------------------------


def test_only_an_earlier_window_held_and_ever_held_stays(ledger: Ledger) -> None:
    days = weekdays(MONDAY, F2_WINDOW_WEEKDAYS + 5)
    ledger.run(at(MONDAY))
    recorded_window(ledger, days, skip=days[:7])  # 7 of the first window's 20
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(days[-1]))
    assert status.full and status.window is not None
    assert (status.window.first, status.window.last) == (days[5], days[-1])
    assert status.window.missed_sessions == 2 and not status.window.holds
    assert status.ever_held


def test_the_latest_full_window_is_the_last_20_weekdays(ledger: Ledger) -> None:
    days = weekdays(MONDAY, 33)
    ledger.run(at(MONDAY))
    recorded_window(ledger, days)
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(days[-1]) + timedelta(hours=5))
    assert status.window is not None
    assert (status.window.first, status.window.last) == (days[13], days[-1])
    assert status.weekdays == 33 and not status.ever_held


# --- (f) fewer than 20 weekdays -----------------------------------------------------------------


@pytest.mark.parametrize(("missed", "holds"), [(6, False), (7, True)])
def test_a_short_range_holds_only_above_six(ledger: Ledger, missed: int, holds: bool) -> None:
    days = weekdays(MONDAY, 10)
    ledger.run(at(MONDAY))
    recorded_window(ledger, days, skip=days[:missed])
    status = store(ledger).f2_status(CLAIM_H3, now=after_cutoff(days[-1]))
    assert not status.full and status.weekdays == 10
    assert status.window is not None and status.window.denominator is None
    assert (status.window.first, status.window.last) == (days[0], days[-1])
    assert status.window.holds is holds and status.ever_held is holds


def test_the_query_needs_an_aware_now_and_a_registered_claim(ledger: Ledger) -> None:
    with pytest.raises(ForecastStoreError):
        store(ledger).f2_status(CLAIM_H3, now=datetime(2026, 10, 6))  # naive
    with pytest.raises(ForecastStoreError):
        store(ledger).f2_status("market|h3|nope|dirdef-v1.0|forward", now=after_cutoff(MONDAY))


def test_the_query_only_reads(ledger: Ledger, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger.run(at(MONDAY))
    before = hashlib.sha256(ledger.path.read_bytes()).hexdigest()

    def no_write(self: ForecastStore) -> sqlite3.Connection:
        raise AssertionError("f2_status opened a write connection")

    monkeypatch.setattr(ForecastStore, "_connect", no_write)
    store(ledger).f2_status(CLAIM_H3, now=after_cutoff(MONDAY))
    assert hashlib.sha256(ledger.path.read_bytes()).hexdigest() == before


# --- (g) the report -----------------------------------------------------------------------------


def f2_lines(lines: Sequence[str]) -> list[str]:
    """The first sentence's claim lines: between its heading and the second's."""
    return list(
        lines[lines.index(report.F2_FIRST_HEADING) + 1 : lines.index(report.F2_SECOND_HEADING)]
    )


def grid_lines(lines: Sequence[str]) -> list[str]:
    """The second sentence's claim lines: between its heading and the action line."""
    return list(
        lines[lines.index(report.F2_SECOND_HEADING) + 1 : lines.index(report.F2_ACTION_LINE)]
    )


def test_the_report_prints_the_full_window_per_claim(ledger: Ledger) -> None:
    days = weekdays(MONDAY, F2_WINDOW_WEEKDAYS + 5)
    ledger.run(at(MONDAY))
    recorded_window(ledger, days, skip=days[:7])
    lines = report.render_execution_status(store(ledger), now=after_cutoff(days[-1]))
    template = approved_copy.f2_lines()["full"]
    assert f2_lines(lines) == [
        approved_copy.fill(template, 1, 0, claim_id=claim, 起=days[5], 迄=days[-1], a=2, b=0, d=20)
        for claim in (CLAIM_H3, CLAIM_H5)
    ]
    assert not any(word in line for line in lines for word in LABEL_WORDS)


def test_the_report_prints_a_full_window_without_a_final_session(ledger: Ledger) -> None:
    window = weekdays(MONDAY, F2_WINDOW_WEEKDAYS)
    ledger.run(at(MONDAY), outcome="inputs_not_ready")
    lines = report.render_execution_status(store(ledger), now=after_cutoff(window[-1]))
    template = approved_copy.f2_wording()["full_zero"]
    assert f2_lines(lines) == [
        approved_copy.fill(template, claim_id=claim, 起=window[0], 迄=window[-1], a=0, b=1)
        for claim in (CLAIM_H3, CLAIM_H5)
    ]


@pytest.mark.parametrize(("missed", "choice"), [(0, 1), (7, 0)], ids=["open", "held"])
def test_the_report_prints_the_short_range(ledger: Ledger, missed: int, choice: int) -> None:
    days = weekdays(MONDAY, 10)
    ledger.run(at(MONDAY))
    recorded_window(ledger, days, skip=days[:missed])
    lines = report.render_execution_status(store(ledger), now=after_cutoff(days[-1]))
    template = approved_copy.f2_lines()["short"]
    assert f2_lines(lines) == [
        approved_copy.fill(
            template, choice, claim_id=claim, k=10, 起=days[0], 迄=days[-1], a=missed, b=0
        )
        for claim in (CLAIM_H3, CLAIM_H5)
    ]


def test_the_report_prints_no_run_and_no_weekday_yet(ledger: Ledger) -> None:
    lines = report.render_execution_status(store(ledger), now=at(MONDAY))
    # "視窗未滿（尚無執行）" keeps its earlier wording (RC-239's note): the module's own.
    assert f2_lines(lines) == [
        approved_copy.fill(report.F2_NO_RUN_LINE, claim_id=c) for c in (CLAIM_H3, CLAIM_H5)
    ]
    assert report.F2_NO_RUN_LINE == "  {claim_id}：視窗未滿（尚無執行）"
    ledger.run(at(MONDAY))
    lines = report.render_execution_status(store(ledger), now=at(MONDAY, 23, 0))
    template = approved_copy.f2_lines()["no_weekday"]
    assert f2_lines(lines) == [
        approved_copy.fill(template, claim_id=c, S_c=MONDAY) for c in (CLAIM_H3, CLAIM_H5)
    ]


def test_the_report_prints_the_second_sentence_per_claim(ledger: Ledger) -> None:
    days = _grid_ledger(ledger, 25, [4, 8])
    lines = report.render_execution_status(store(ledger), now=after_cutoff(days[-1]))
    template = approved_copy.f2_wording()["second"]
    # h5: points 0,5,...,20 (5 of them), the two lost h3 points are recorded for h5.
    assert grid_lines(lines) == [
        approved_copy.fill(template, 0, 0, claim_id=CLAIM_H3, G=9, L=2),
        approved_copy.fill(template, 1, 1, claim_id=CLAIM_H5, G=5, L=0),
    ]


def test_the_undecidable_second_sentence_has_no_ever_held(ledger: Ledger) -> None:
    lines = report.render_execution_status(store(ledger), now=at(MONDAY))
    template = approved_copy.f2_wording()["second_undecidable"]
    assert grid_lines(lines) == [
        approved_copy.fill(template, claim_id=c) for c in (CLAIM_H3, CLAIM_H5)
    ]
    assert not any("曾否成立" in line for line in grid_lines(lines))


# --- C5-3: only store.py derives F-2; one weekday function with T2 ------------------------------


def _function(source: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def _called_names(node: ast.AST) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def test_f2_and_t2_use_the_one_weekday_function() -> None:
    source = (APP_ROOT / "forecast" / "store.py").read_text(encoding="utf-8")
    assert "_weekdays_after" in _called_names(_function(source, "f2_status"))
    assert "_weekdays_after" in _called_names(_function(source, "review_trigger"))
    assert "weekday()" not in ast.unparse(_function(source, "f2_status"))


def test_f2_is_derived_in_store_py_only() -> None:
    defined = {
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef)
        and "f2" in node.name.lower()
        and node.name != "_f2_line"
    }
    assert defined == {"forecast/store.py"}
    text = (APP_ROOT / "forecast" / "report.py").read_text(encoding="utf-8")
    for counted in ("weekday(", "next_weekday", "_weekdays_after", "bisect", "on_time_sessions"):
        assert counted not in text


# --- F-2 second sentence: the phase-0 grid point loss (supplement 9 point 5, S-19a) -------------


def _grid_ledger(ledger: Ledger, sessions: int, lost_points: Sequence[int]) -> list[date]:
    """h3 records on every session but the given phase-0 grid points (by point index)."""
    days = weekdays(MONDAY, sessions)
    points = days[::3]
    ledger.run(at(MONDAY))
    recorded_window(ledger, days, skip=[points[i] for i in lost_points])
    return days


def test_s19a_no_d_v_is_undecidable(ledger: Ledger) -> None:
    ledger.run(at(MONDAY))
    ledger.snapshot(weekdays(MONDAY, 10))
    status = store(ledger).grid_loss_status(CLAIM_H3, now=after_cutoff(date(2026, 10, 30)))
    assert (status.counted, status.lost, status.verdict, status.ever_held) == (
        0,
        0,
        "undecidable",
        False,
    )


def test_s19a_d_v_whose_cutoff_has_not_passed_is_undecidable(ledger: Ledger) -> None:
    _grid_ledger(ledger, 1, [])
    status = store(ledger).grid_loss_status(CLAIM_H3, now=at(MONDAY, 23, 59))
    assert (status.counted, status.verdict) == (0, "undecidable")
    later = store(ledger).grid_loss_status(CLAIM_H3, now=after_cutoff(MONDAY))
    assert (later.counted, later.lost, later.verdict) == (1, 0, "not_held")


def test_s19a_one_of_five_is_not_held(ledger: Ledger) -> None:
    days = _grid_ledger(ledger, 13, [4])  # points 0,3,...,12: the last one lost
    status = store(ledger).grid_loss_status(CLAIM_H3, now=after_cutoff(days[-1]))
    assert (status.counted, status.lost, status.verdict) == (5, 1, "not_held")
    assert not status.ever_held  # prefix 5: 1 x 5 = 5, not more than 5


def test_s19a_two_of_nine_holds(ledger: Ledger) -> None:
    days = _grid_ledger(ledger, 25, [4, 8])
    status = store(ledger).grid_loss_status(CLAIM_H3, now=after_cutoff(days[-1]))
    assert (status.counted, status.lost, status.verdict) == (9, 2, "holds")
    assert status.ever_held


def test_s19a_an_earlier_prefix_held_and_ever_held_stays(ledger: Ledger) -> None:
    days = _grid_ledger(ledger, 13, [1])  # the second point lost: prefix 2 has 1 x 5 > 2
    status = store(ledger).grid_loss_status(CLAIM_H3, now=after_cutoff(days[-1]))
    assert (status.counted, status.lost, status.verdict) == (5, 1, "not_held")
    assert status.ever_held


def test_the_grid_points_are_counted_only_once_their_cutoff_passed(ledger: Ledger) -> None:
    days = _grid_ledger(ledger, 13, [])
    status = store(ledger).grid_loss_status(CLAIM_H3, now=at(days[-1], 23, 0))
    assert status.counted == 4  # the point on days[-1] is not counted yet


def test_the_grid_loss_query_needs_an_aware_now_and_only_reads(
    ledger: Ledger, monkeypatch: pytest.MonkeyPatch
) -> None:
    _grid_ledger(ledger, 4, [])
    with pytest.raises(ForecastStoreError):
        store(ledger).grid_loss_status(CLAIM_H3, now=datetime(2026, 10, 9))
    with pytest.raises(ForecastStoreError):
        store(ledger).grid_loss_status("market|h3|x|dirdef-v1.0|forward", now=after_cutoff(MONDAY))

    def no_write(self: ForecastStore) -> sqlite3.Connection:
        raise AssertionError("grid_loss_status opened a write connection")

    monkeypatch.setattr(ForecastStore, "_connect", no_write)
    store(ledger).grid_loss_status(CLAIM_H3, now=after_cutoff(MONDAY))


def test_the_grid_loss_verdict_is_derived_in_store_py_only() -> None:
    source = (APP_ROOT / "forecast" / "report.py").read_text(encoding="utf-8")
    for computed in ("GRID_LOSS_FACTOR", "* 5", "*5", "late_cutoff_at", ".points", "on_time"):
        assert computed not in source
