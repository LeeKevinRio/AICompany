"""The source-gap disclosure line of ``report status`` (ADR-0030 supplement 8 point 6 (b)).

Supplement 8 (final draft 2, to be appended), S-18a point 6 (b), and the risk
review RC-230 (``work/reviews/2026-11-19-report-status缺日加註定稿RC229至RC232-風控.md``):
``render_execution_status`` ends with one fixed line -- the core does not
detect sessions the source left out, the F-2 and grid values may differ from
the validation layer's recomputation, the F-2 count may be low. The wording is
the approved text (the line "定稿全文：" of that report, extracted here and
compared verbatim); it is printed on every call, never branches on data and
changes no other line. Any change of it goes back to risk review.

Plus the S-18a point 3 (a)-(c) guards: the wiring PR changes no gap semantics
(``MISSING_CODES`` is pinned by ``tests/test_outlook_missing_codes.py``).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import get_args

import pytest

from app.forecast import report
from app.forecast.schema import EXPECTED_OBJECTS
from app.forecast.store import ForecastStore, ReviewTrigger, RunOutcome
from app.outlook.inputs import DropReason
from tests.forecast_ledger_helpers import file_ledger, weekdays
from tests.test_forecast_bootstrap import EXPECTED_OBJECTS_SHA256
from tests.test_forecast_f2_window import (
    CLAIM_H3,
    CLAIM_H5,
    MONDAY,
    Ledger,
    after_cutoff,
    at,
    recorded_window,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
REPO_ROOT = Path(__file__).resolve().parents[4]
#: The risk review that approved the wording (RC-230).
APPROVAL = (
    REPO_ROOT / "work" / "reviews" / "2026-11-19-report-status缺日加註定稿RC229至RC232-風控.md"
)
DAYS = weekdays(MONDAY, 25)
NOW = after_cutoff(DAYS[-1])


def approved_text() -> str:
    """The text between the backticks of the approval's "定稿全文：" line, exactly once."""
    found = re.findall(r"^定稿全文：`([^`]+)`$", APPROVAL.read_text(encoding="utf-8"), flags=re.M)
    assert len(found) == 1
    return found[0]


def test_the_line_is_the_risk_approved_text() -> None:
    assert report.GAP_DISCLOSURE == approved_text()


def _ledger(tmp_path: Path, *, case: str) -> Ledger:
    tmp_path.mkdir(parents=True, exist_ok=True)
    built = Ledger(path=file_ledger(tmp_path))
    if case == "no-claim":
        return built
    built.claim(CLAIM_H3, horizon=3, registered=at(date(2026, 9, 1), 9, 0))
    built.claim(CLAIM_H5, horizon=5, registered=at(date(2026, 9, 1), 9, 1))
    built.run(at(MONDAY))
    recorded_window(built, [d for d in DAYS if case != "gap" or d != DAYS[10]])
    return built


CASES = ("no-claim", "gap", "whole")


@pytest.mark.parametrize("case", CASES)
def test_1_the_line_is_the_last_element(tmp_path: Path, case: str) -> None:
    lines = report.render_execution_status(
        ForecastStore(_ledger(tmp_path, case=case).path), now=NOW
    )
    assert lines[-1] == report.GAP_DISCLOSURE
    assert lines.count(report.GAP_DISCLOSURE) == 1


def test_2_the_line_is_the_same_with_no_claim_a_gap_and_no_gap(tmp_path: Path) -> None:
    lasts = {
        report.render_execution_status(
            ForecastStore(_ledger(tmp_path / case, case=case).path), now=NOW
        )[-1]
        for case in CASES
    }
    assert lasts == {report.GAP_DISCLOSURE}


def _expected_before_the_line(*, gap: bool) -> list[str]:
    """The output as it was before the line was added (built here, not by the module)."""
    sessions = [d for d in DAYS if not gap or d != DAYS[10]]
    window = DAYS[5:]
    denominator = min(20, sum(1 for d in sessions if window[0] <= d <= window[-1]))
    f2 = [
        f"  {claim}：最近一個完整視窗 {window[0].isoformat()}～{window[-1].isoformat()}，"
        "沒有 late = 0 紀錄的定案 session 數 0，inputs_not_ready 日數 0，"
        f"分母 {denominator}，未成立；自起點以來曾否成立：否"
        for claim in (CLAIM_H3, CLAIM_H5)
    ]
    grid = [
        f"  {claim}：第 0 相位格點 {len(sessions[::h])} 個，其中沒有 late = 0 紀錄 0 個"
        for claim, h in ((CLAIM_H3, 3), (CLAIM_H5, 5))
    ]
    return [
        "執行狀態（只含執行狀態，不含任何標籤或對照）",
        "執行次數：ok=1，no_new_session=0，inputs_not_ready=0，gate_closed=0，error=0，"
        "沒有 end 列=0",
        "inputs_not_ready 日數（全部期間，台北日期）：0",
        report.F2_TITLE,
        *f2,
        *grid,
    ]


@pytest.mark.parametrize("gap", [False, True], ids=["whole", "gap"])
def test_3_no_other_line_changes(tmp_path: Path, gap: bool) -> None:
    ledger = _ledger(tmp_path, case="gap" if gap else "whole")
    lines = report.render_execution_status(ForecastStore(ledger.path), now=NOW)
    assert lines[:-1] == _expected_before_the_line(gap=gap)


def test_3_the_counts_do_not_depend_on_the_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ForecastStore(_ledger(tmp_path, case="gap").path)
    before = report.render_execution_status(store, now=NOW)
    monkeypatch.setattr(report, "GAP_DISCLOSURE", "another text")
    after = report.render_execution_status(store, now=NOW)
    assert before[:-1] == after[:-1] and after[-1] == "another text"


def test_4_in_status_the_line_precedes_the_review_trigger_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The synthetic registry rows carry no real definition JSON, so the trigger values
    # are stubbed: only the order of the lines is under test here.
    def review_trigger(self: ForecastStore, claim_id: str, *, today: date) -> ReviewTrigger:
        return ReviewTrigger(
            claim_id=claim_id, horizon=3, c1=30, d_v=None, n_hat=0, d_1=None, t1=False, t2=False
        )

    monkeypatch.setattr(ForecastStore, "review_trigger", review_trigger)
    store = ForecastStore(_ledger(tmp_path, case="whole").path)
    lines = report.render_status(store, now=NOW)
    at_line = lines.index(report.GAP_DISCLOSURE)
    triggers = [i for i, line in enumerate(lines) if line.startswith("重審觸發（")]
    assert len(triggers) == 2 and all(at_line < i for i in triggers)
    assert lines[: at_line + 1] == report.render_execution_status(store, now=NOW)


def test_the_line_is_a_module_constant_used_without_a_branch() -> None:
    tree = ast.parse((APP_ROOT / "forecast" / "report.py").read_text(encoding="utf-8"))
    assigned = [
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "GAP_DISCLOSURE"
    ]
    assert len(assigned) == 1
    assert isinstance(assigned[0].value, ast.Constant)  # one literal, no data in it
    for node in ast.walk(tree):
        if isinstance(node, ast.If | ast.IfExp | ast.comprehension):
            assert "GAP_DISCLOSURE" not in ast.unparse(node)


# --- S-18a point 3 (a)-(c): no gap semantics change in the wiring PR ---------------------------


def test_drop_reason_is_still_only_not_final() -> None:
    assert get_args(DropReason) == ("not_final",)


def test_the_outcomes_and_the_ddl_are_unchanged() -> None:
    assert get_args(RunOutcome) == (
        "ok",
        "no_new_session",
        "inputs_not_ready",
        "gate_closed",
        "error",
    )
    payload = json.dumps([[list(key), sql] for key, sql in EXPECTED_OBJECTS.items()])
    assert hashlib.sha256(payload.encode()).hexdigest() == EXPECTED_OBJECTS_SHA256


def test_session_calendar_defines_only_is_final() -> None:
    tree = ast.parse((APP_ROOT / "data" / "session_calendar.py").read_text(encoding="utf-8"))
    defined = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ] + [
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    ]
    assert defined == ["is_final"]


#: The app/ sources that mention holidays or market closures, exactly as at the CG-2
#: registration head (9d5bbf48: docstrings and comments, and the existing
#: cache-derived ``data/calendar.py``); a new one, or any data file, would be new
#: holiday data.
HOLIDAY_MENTIONS = frozenset(
    {
        "api/deps.py",
        "data/cache.py",
        "data/calendar.py",
        "data/diagnose.py",
        "data/freshness.py",
        "data/intraday_session.py",
        "data/providers/fx.py",
        "data/quote_quality.py",
        "data/service.py",
        "demo/series.py",
        "forecast/recorder.py",
        "forecast/store.py",
        "playbook/service.py",
        "playbook/wording.py",
        "portfolio/valuation.py",
    }
)


def test_no_holiday_data_is_added_to_app() -> None:
    mentions = {
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*.py")
        if any(word in path.read_text(encoding="utf-8").lower() for word in ("holiday", "休市"))
    }
    assert mentions == HOLIDAY_MENTIONS
    data_files = sorted(
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".csv", ".txt", ".ics", ".toml"}
    )
    assert data_files == []
