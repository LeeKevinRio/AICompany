"""The source-gap disclosure line of ``report status`` (ADR-0030 supplement 8 point 6 (b)).

Supplement 8 (final draft 2, to be appended), S-18a point 6 (b), and the risk
review RC-230 (``work/reviews/2026-11-19-report-status缺日加註定稿RC229至RC232-風控.md``):
``render_execution_status`` ends with one fixed line -- the core does not
detect sessions the source left out, the F-2 and grid values may differ from
the validation layer's recomputation, the F-2 count may be low. The wording is
the approved text (the line "定稿全文：" of that report, extracted here and
compared verbatim); it is printed on every call, never branches on data and
changes no other line. Any change of it goes back to risk review.

The second line (RC-233 / RC-234,
``work/reviews/2026-11-19-重審觸發缺日加註定稿RC233至RC236-風控.md``, the line
"第二行定稿全文："): the last element of ``render_review_trigger`` and so of
``render_status``, once, with zero, one or two claims; it leaves every other
line, and n-hat, c_1, d_1, T1, T2 and D_v, unchanged, and never reaches the
execution status or the harness output. ``N_HAT_NOTE`` stays word for word
(supplement 8 point 3 (f)).

Plus the S-18a point 3 (a)-(c) guards: the wiring PR changes no gap semantics
(``MISSING_CODES`` is pinned by ``tests/test_outlook_missing_codes.py``).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import get_args

import pytest

from app.forecast import report
from app.forecast.schema import EXPECTED_OBJECTS
from app.forecast.store import ForecastStore, ReviewTrigger, RunOutcome
from app.outlook.inputs import DropReason
from tests import approved_copy
from tests.approved_copy import f2_gap_line, review_gap_line
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
from tests.test_forecast_report import d4_violations

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
REPO_ROOT = Path(__file__).resolve().parents[4]
#: The risk review that approved the wording (RC-230).
APPROVAL = (
    REPO_ROOT / "work" / "reviews" / "2026-11-19-report-status缺日加註定稿RC229至RC232-風控.md"
)
DAYS = weekdays(MONDAY, 25)
NOW = after_cutoff(DAYS[-1])


def test_the_line_is_the_risk_approved_text() -> None:
    assert report.GAP_DISCLOSURE == f2_gap_line()


def _ledger(tmp_path: Path, *, case: str) -> Ledger:
    tmp_path.mkdir(parents=True, exist_ok=True)
    built = Ledger(path=file_ledger(tmp_path))
    if case == "no-claim":
        return built
    built.claim(CLAIM_H3, horizon=3, registered=at(date(2026, 9, 1), 9, 0))
    if case != "one-claim":
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
    """The output without the last line, rendered here from the approval records' templates."""
    sessions = [d for d in DAYS if not gap or d != DAYS[10]]
    window = DAYS[5:]
    denominator = min(20, sum(1 for d in sessions if window[0] <= d <= window[-1]))
    wording, lines = approved_copy.f2_wording(), approved_copy.f2_lines()
    first = [
        approved_copy.fill(
            lines["full"],
            1,
            1,
            claim_id=claim,
            起=window[0],
            迄=window[-1],
            a=0,
            b=0,
            d=denominator,
        )
        for claim in (CLAIM_H3, CLAIM_H5)
    ]
    second = [
        approved_copy.fill(wording["second"], 1, 1, claim_id=claim, G=len(sessions[::h]), L=0)
        for claim, h in ((CLAIM_H3, 3), (CLAIM_H5, 5))
    ]
    return [
        "執行狀態（只含執行狀態，不含任何標籤或對照）",
        "執行次數：ok=1，no_new_session=0，inputs_not_ready=0，gate_closed=0，error=0，"
        "沒有 end 列=0",
        "inputs_not_ready 日數（全部期間，台北日期）：0",
        approved_copy.fill(
            approved_copy.latest_run_lines()["with_run"],
            **{"YYYY-MM-DD HH:MM": "2026-10-05 22:10", "outcome": "ok"},
        ),
        wording["title"],
        wording["first_heading"],
        *first,
        wording["second_heading"],
        *second,
        wording["action"],
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
        # The risk-approved F-2 heading "平日指週一至週五，不扣休市日" (RC-248): wording, not data.
        "forecast/report.py",
        # The fixed WARNING of supplement 10 point 2 ("... (an exchange holiday or a row
        # missing at the source) ..."): wording, not data; pinned to that one line below.
        "scheduler.py",
    }
)


def test_no_holiday_data_is_added_to_app() -> None:
    mentions = {
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*.py")
        if any(word in path.read_text(encoding="utf-8").lower() for word in ("holiday", "休市"))
    }
    assert mentions == HOLIDAY_MENTIONS
    scheduler_lines = [
        line.strip()
        for line in (APP_ROOT / "scheduler.py").read_text(encoding="utf-8").splitlines()
        if "holiday" in line.lower() or "休市" in line
    ]
    assert scheduler_lines == [
        '" (an exchange holiday or a row missing at the source); the run continues"'
    ]
    data_files = sorted(
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".csv", ".txt", ".ics", ".toml"}
    )
    assert data_files == []


def _mentions_holiday(line: str) -> bool:
    return "holiday" in line.lower() or "休市" in line


def _report_holiday_violations(source: str, approved: str) -> list[str]:
    """qa N-12: in ``report.py`` the only holiday mention is the RC-248 first heading.

    Every source line that mentions a holiday (code, comment or docstring) must
    sit inside the one ``F2_FIRST_HEADING`` assignment, be a string literal that
    is part of the approved heading, and there must be exactly one such line;
    the assigned value must equal the heading extracted from the risk record.
    """
    tree = ast.parse(source)
    headings = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and any(
            isinstance(target, ast.Name) and target.id == "F2_FIRST_HEADING"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    ]
    if len(headings) != 1:
        return ["F2_FIRST_HEADING is not assigned exactly once"]
    (heading,) = headings
    found: list[str] = []
    value = heading.value
    if not (isinstance(value, ast.Constant) and value.value == approved):
        found.append("F2_FIRST_HEADING is not the approved RC-248 first heading")
    last = heading.end_lineno or heading.lineno
    mentioned = [
        (number, line)
        for number, line in enumerate(source.splitlines(), start=1)
        if _mentions_holiday(line)
    ]
    if len(mentioned) != 1:
        found.append(f"{len(mentioned)} lines mention a holiday, not 1")
    for number, line in mentioned:
        if not heading.lineno <= number <= last:
            found.append(f"line {number} mentions a holiday outside the heading")
            continue
        try:
            piece = ast.literal_eval(line.strip())
        except (ValueError, SyntaxError):
            found.append(f"line {number} is not a string literal of the heading")
            continue
        if not isinstance(piece, str) or piece not in approved:
            found.append(f"line {number} is not part of the approved heading")
    return found


def test_n12_report_mentions_a_holiday_only_in_the_rc248_first_heading() -> None:
    approved = approved_copy.f2_wording()["first_heading"]
    assert "休市" in approved
    source = (APP_ROOT / "forecast" / "report.py").read_text(encoding="utf-8")
    assert _report_holiday_violations(source, approved) == []


def test_n12_the_report_holiday_scan_has_teeth() -> None:
    approved = approved_copy.f2_wording()["first_heading"]
    source = (APP_ROOT / "forecast" / "report.py").read_text(encoding="utf-8")
    assert _report_holiday_violations(source, approved) == []
    for extra in (
        "\n# TWSE 休市日 list follows\n",
        '\nHOLIDAYS = ("2026-01-01",)\n',
        '\ndef f() -> None:\n    """Skips holiday sessions."""\n',
    ):
        assert _report_holiday_violations(source + extra, approved) != []
    changed = source.replace("不扣休市日", "扣除休市日", 1)
    assert changed != source
    assert _report_holiday_violations(changed, approved) != []
    removed = source.replace("F2_FIRST_HEADING: Final =", "F2_HEADING_ONE: Final =", 1)
    assert _report_holiday_violations(removed, approved) != []


# --- the second line: after the review trigger lines (RC-233 / RC-234) --------------------------

#: The fixed n-hat note as it was before the wiring PR (9d5bbf48); it must not change.
N_HAT_NOTE_BEFORE = "重審觸發用計數（近似上界估計），不是驗證統計，不代表規則有效"


def _stub_triggers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixed trigger values: the synthetic registry rows carry no real definition JSON."""

    def review_trigger(self: ForecastStore, claim_id: str, *, today: date) -> ReviewTrigger:
        horizon = 3 if "|h3|" in claim_id else 5
        return ReviewTrigger(
            claim_id=claim_id,
            horizon=horizon,
            c1=30,
            d_v=MONDAY,
            n_hat=4 + horizon,
            d_1=date(2027, 3, 1),
            t1=False,
            t2=horizon == 3,
        )

    monkeypatch.setattr(ForecastStore, "review_trigger", review_trigger)


def test_r1_the_second_line_is_the_risk_approved_text() -> None:
    assert report.REVIEW_GAP_DISCLOSURE == review_gap_line()


def test_the_n_hat_note_is_unchanged() -> None:
    assert report.N_HAT_NOTE == N_HAT_NOTE_BEFORE


@pytest.mark.parametrize("case", ("no-claim", "one-claim", "whole", "gap"))
def test_r2_r3_the_second_line_is_last_and_printed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    _stub_triggers(monkeypatch)
    store = ForecastStore(_ledger(tmp_path, case=case).path)
    status = report.render_status(store, now=NOW)
    review = report.render_review_trigger(store, now=NOW)
    assert status[-1] == review[-1] == report.REVIEW_GAP_DISCLOSURE
    assert status.count(report.REVIEW_GAP_DISCLOSURE) == 1
    assert review.count(report.REVIEW_GAP_DISCLOSURE) == 1
    claims = {"no-claim": 0, "one-claim": 1}.get(case, 2)
    assert sum(line.startswith("重審觸發（") for line in review) == claims


def test_r4_the_second_line_is_the_same_with_and_without_a_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_triggers(monkeypatch)
    lasts = {
        report.render_status(ForecastStore(_ledger(tmp_path / c, case=c).path), now=NOW)[-1]
        for c in ("whole", "gap")
    }
    assert lasts == {report.REVIEW_GAP_DISCLOSURE}


def test_r5_no_other_line_or_value_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_triggers(monkeypatch)
    store = ForecastStore(_ledger(tmp_path, case="whole").path)
    review = report.render_review_trigger(store, now=NOW)
    assert review[:-1] == [
        f"重審觸發（{CLAIM_H3}）：D_v={MONDAY.isoformat()}，c₁=30，"
        f"n̂=7（{N_HAT_NOTE_BEFORE}），d₁=2027-03-01，T1=未成立，T2=成立",
        f"重審觸發（{CLAIM_H5}）：D_v={MONDAY.isoformat()}，c₁=30，"
        f"n̂=9（{N_HAT_NOTE_BEFORE}），d₁=2027-03-01，T1=未成立，T2=未成立",
    ]
    before = report.render_status(store, now=NOW)
    monkeypatch.setattr(report, "REVIEW_GAP_DISCLOSURE", "another text")
    after = report.render_status(store, now=NOW)
    assert before[:-1] == after[:-1] and after[-1] == "another text"


def test_r6_the_second_line_is_not_in_the_execution_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_triggers(monkeypatch)
    for case in ("no-claim", "whole"):
        store = ForecastStore(_ledger(tmp_path / case, case=case).path)
        assert report.REVIEW_GAP_DISCLOSURE not in report.render_execution_status(store, now=NOW)
    # The harness output (tests/test_forecast_pipeline_harness.py) is checked there.


def test_r7_the_first_line_precedes_every_review_trigger_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_triggers(monkeypatch)
    lines = report.render_status(ForecastStore(_ledger(tmp_path, case="whole").path), now=NOW)
    first = lines.index(report.GAP_DISCLOSURE)
    assert all(first < i for i, line in enumerate(lines) if line.startswith("重審觸發（"))
    assert first < lines.index(report.REVIEW_GAP_DISCLOSURE)


def test_the_second_line_is_a_module_constant_used_without_a_branch() -> None:
    tree = ast.parse((APP_ROOT / "forecast" / "report.py").read_text(encoding="utf-8"))
    assigned = [
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "REVIEW_GAP_DISCLOSURE"
    ]
    assert len(assigned) == 1 and isinstance(assigned[0].value, ast.Constant)
    for node in ast.walk(tree):
        if isinstance(node, ast.If | ast.IfExp | ast.comprehension):
            assert "REVIEW_GAP_DISCLOSURE" not in ast.unparse(node)


# --- RC-252: the F-2 section's fixed lines, order and wording ------------------------------------

FIXED_LINES = (
    "F2_TITLE",
    "F2_FIRST_HEADING",
    "F2_SECOND_HEADING",
    "F2_ACTION_LINE",
    "GAP_DISCLOSURE",
)
TEMPLATES = {
    "F2_FULL_LINE": ("lines", "full"),
    "F2_SHORT_LINE": ("lines", "short"),
    "F2_NO_WEEKDAY_LINE": ("lines", "no_weekday"),
    "F2_FULL_ZERO_LINE": ("wording", "full_zero"),
    "F2_SECOND_LINE": ("wording", "second"),
    "F2_SECOND_UNDECIDABLE_LINE": ("wording", "second_undecidable"),
}
FIXED_KEYS = {
    "F2_TITLE": "title",
    "F2_FIRST_HEADING": "first_heading",
    "F2_SECOND_HEADING": "second_heading",
    "F2_ACTION_LINE": "action",
    "GAP_DISCLOSURE": "gap",
}


def test_rc252_every_constant_is_the_approved_text() -> None:
    wording, lines = approved_copy.f2_wording(), approved_copy.f2_lines()
    for name, key in FIXED_KEYS.items():
        assert getattr(report, name) == wording[key], name
    for name, (record, key) in TEMPLATES.items():
        source = lines if record == "lines" else wording
        assert getattr(report, name) == source[key], name


def test_rc252_the_superseded_texts_are_not_used() -> None:
    # RC-237's title and RC-238's denominator-0 line (both superseded) appear nowhere.
    source = (APP_ROOT / "forecast" / "report.py").read_text(encoding="utf-8")
    values = {getattr(report, name) for name in (*FIXED_KEYS, *TEMPLATES)}
    for old in approved_copy.f2_superseded():
        assert old not in values
        assert old not in "".join(re.findall(r'"([^"\n]*)"', source))


@pytest.mark.parametrize("case", CASES)
def test_rc252_the_fixed_lines_are_printed_in_order_whatever_the_ledger(
    tmp_path: Path, case: str
) -> None:
    lines = report.render_execution_status(
        ForecastStore(_ledger(tmp_path, case=case).path), now=NOW
    )
    at_line = [lines.index(getattr(report, name)) for name in FIXED_LINES]
    assert at_line == sorted(at_line)
    assert all(lines.count(getattr(report, name)) == 1 for name in FIXED_LINES)
    assert lines[-2:] == [report.F2_ACTION_LINE, report.GAP_DISCLOSURE]
    assert lines[0].startswith("執行狀態（") and lines[4] == report.F2_TITLE
    assert lines[5] == report.F2_FIRST_HEADING


def test_rc252_the_whole_status_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_triggers(monkeypatch)
    lines = report.render_status(ForecastStore(_ledger(tmp_path, case="whole").path), now=NOW)
    first_heading = lines.index(report.F2_FIRST_HEADING)
    second_heading = lines.index(report.F2_SECOND_HEADING)
    first_sentence = lines[first_heading + 1 : second_heading]
    action = lines.index(report.F2_ACTION_LINE)
    second_sentence = lines[second_heading + 1 : action]
    triggers = [i for i, line in enumerate(lines) if line.startswith("重審觸發（")]
    assert lines.index(report.F2_TITLE) < first_heading
    assert len(first_sentence) == len(second_sentence) == 2
    assert lines.index(report.GAP_DISCLOSURE) == action + 1
    assert triggers == [action + 2, action + 3]
    assert lines[-1] == report.REVIEW_GAP_DISCLOSURE


@pytest.mark.parametrize("name", FIXED_LINES)
def test_rc252_the_fixed_lines_are_single_literals_never_in_a_branch(name: str) -> None:
    tree = ast.parse((APP_ROOT / "forecast" / "report.py").read_text(encoding="utf-8"))
    assigned = [
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == name
    ]
    assert len(assigned) == 1 and isinstance(assigned[0].value, ast.Constant)
    for node in ast.walk(tree):
        if isinstance(node, ast.If | ast.IfExp | ast.comprehension):
            assert name not in ast.unparse(node)


@pytest.mark.parametrize("case", CASES)
def test_rc252_no_new_line_trips_the_d4_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    _stub_triggers(monkeypatch)
    lines = report.render_status(ForecastStore(_ledger(tmp_path, case=case).path), now=NOW)
    assert d4_violations(lines, unpassed_hashes=set()) == []
    wording, templates = approved_copy.f2_wording(), approved_copy.f2_lines()
    every = [
        *wording.values(),
        *(approved_copy.fill(t, *([0] * t.count("／")), **_dummy(t)) for t in templates.values()),
        approved_copy.fill(wording["second"], 0, 0, **_dummy(wording["second"])),
    ]
    assert d4_violations(every, unpassed_hashes=set()) == []


def _dummy(template: str) -> dict[str, object]:
    return {
        name: "2026-10-05" if name in ("起", "迄", "S_c") else 1
        for name in approved_copy.placeholders(template)
        if "／" not in name
    }


# --- RC-259: the latest run that left a run row --------------------------------------------------


def _latest_line(lines: list[str]) -> str:
    at_line = lines.index(report.F2_TITLE) - 1
    assert lines[at_line - 1].startswith("inputs_not_ready 日數（全部期間，台北日期）：")
    return lines[at_line]


def test_rc259_the_constants_are_the_approved_text() -> None:
    texts = approved_copy.latest_run_lines()
    assert report.LATEST_RUN_LINE == texts["with_run"]
    assert report.LATEST_RUN_NONE_LINE == texts["no_run"]


def test_rc259_without_a_run_row_the_none_variant_is_printed(tmp_path: Path) -> None:
    lines = report.render_execution_status(
        ForecastStore(_ledger(tmp_path, case="no-claim").path), now=NOW
    )
    assert _latest_line(lines) == approved_copy.latest_run_lines()["no_run"]


@pytest.mark.parametrize(
    ("outcome", "shown"),
    [("ok", "ok"), ("inputs_not_ready", "inputs_not_ready"), (None, "沒有 end 列")],
)
def test_rc259_the_latest_run_is_the_highest_run_id_in_taipei_time(
    tmp_path: Path, outcome: str | None, shown: str
) -> None:
    ledger = _ledger(tmp_path, case="whole")  # run 1 at MONDAY 22:10 Taipei, ok
    if outcome is None:
        ledger.execute("forecast_run", {**_run_row_values(at(DAYS[-1], 23, 10))})
    else:
        ledger.run(at(DAYS[-1], 23, 10), outcome=outcome)
    lines = report.render_execution_status(ForecastStore(ledger.path), now=NOW)
    expected = approved_copy.fill(
        approved_copy.latest_run_lines()["with_run"],
        **{"YYYY-MM-DD HH:MM": f"{DAYS[-1].isoformat()} 23:10", "outcome": shown},
    )
    assert _latest_line(lines) == expected


def _run_row_values(started: datetime) -> dict[str, object]:
    from app.forecast.canonical import canonical_timestamp
    from tests.forecast_ledger_helpers import row

    return row("forecast_run", started_at=canonical_timestamp(started))


@pytest.mark.parametrize("case", CASES)
def test_rc259_both_variants_carry_the_note_and_pass_the_d4_checks(
    tmp_path: Path, case: str
) -> None:
    lines = report.render_execution_status(
        ForecastStore(_ledger(tmp_path, case=case).path), now=NOW
    )
    line = _latest_line(lines)
    note = approved_copy.latest_run_lines()["no_run"].split("；", 1)[1]
    assert line.endswith(note)
    assert d4_violations([line], unpassed_hashes=set()) == []
    for text in approved_copy.latest_run_lines().values():
        filled = approved_copy.fill(
            text, **{"YYYY-MM-DD HH:MM": "2026-10-05 22:10", "outcome": "ok"}
        )
        assert d4_violations([filled], unpassed_hashes=set()) == []
