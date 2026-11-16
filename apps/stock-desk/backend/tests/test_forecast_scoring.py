"""``app/forecast/scoring.py``: the provisional comparison (ADR-0030 D-5 point 5; K-7).

Synthetic bars only (consecutive weekdays, 20:00 Taipei stamps); no database.
Covered: the realised label and each party's match; every "no comparison"
reason; the isolation of the module (K-7: not reachable from the store, the
recorder or the schema; only ``report.py`` imports it in ``app/``).
"""

from __future__ import annotations

import ast
import json
import math
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.forecast import scoring
from app.forecast.scoring import (
    BaselinePrediction,
    ComparedRecord,
    RecordUnreadableError,
    provisional_comparison,
)
from app.outlook.inputs import MarketSnapshot, SnapshotBar
from tests.import_graph import APP_ROOT, offenders, reachable_app_modules
from tests.outlook_helpers import TAIPEI

T = date(2026, 11, 2)  # a Monday
SIGMA = 0.01
K = 0.43
EPS = 1e-12


def _sessions(start: date, count: int) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _bar(day: date, close: str, *, hour: int = 20) -> SnapshotBar:
    stamp = datetime(day.year, day.month, day.day, hour, tzinfo=TAIPEI)
    value = Decimal(close)
    return SnapshotBar(
        session_date=day,
        open=value,
        high=value,
        low=value,
        close=value,
        volume=0,
        source="synthetic",
        as_of=stamp,
        fetched_at=stamp,
    )


def _snapshot(closes: list[str], *, start: date = T, hours: dict[int, int] | None = None) -> Any:
    days = _sessions(start, len(closes))
    bars = tuple(
        _bar(day, close, hour=(hours or {}).get(i, 20))
        for i, (day, close) in enumerate(zip(days, closes, strict=True))
    )
    return MarketSnapshot(
        bars=bars,
        source="synthetic",
        source_status="backup",
        staleness_minutes=None,
        reason=None,
        dropped=(),
        raw_timestamp_available=False,
    )


def _record(**overrides: Any) -> ComparedRecord:
    values: dict[str, Any] = {
        "data_as_of": T,
        "horizon": 3,
        "label": "bullish",
        "band_def": {
            "K_h": K,
            "EPS": EPS,
            "sigma_d": SIGMA,
            "valid_returns": 60,
            "up_pct": 0.1,
            "down_pct": 0.1,
        },
        "base_close": "10000",
        "baseline_predictions": {
            "B1": BaselinePrediction(label="range", reason=None),
            "B2": BaselinePrediction(label="unavailable", reason="b2_realized_short"),
            "B6": BaselinePrediction(label="range", reason=None),
            "B8": BaselinePrediction(label="bullish", reason=None),
        },
        "valid_until_session_estimate": _sessions(T, 4)[-1],
    }
    values.update(overrides)
    return ComparedRecord(**values)


#: c_{T+3} so that z is far above K: ln(1.03) / (0.01 * sqrt(3)) ~ 1.7.
UP = ["10000", "10050", "10100", "10300", "10310"]
TODAY = date(2026, 11, 20)
KNOWN = _sessions(T, 5)


def test_a_comparison_gives_the_realised_label_and_each_partys_match() -> None:
    result = provisional_comparison(_record(), _snapshot(UP), known_sessions=KNOWN, today=TODAY)
    assert result.reason is None and result.realized == "bullish"
    assert result.matches == (
        ("B1", False),
        ("B2", None),  # unavailable: not compared
        ("B6", False),
        ("B8", True),
        ("model", True),
    )
    assert [party for party, _ in result.matches] == list(scoring.PARTIES)


def test_the_realised_label_follows_the_section_2_1_rule_with_the_records_band() -> None:
    # z = ln(c3 / c0) / (sigma * sqrt(3)); just inside K + EPS is range.
    inside = 10000 * math.exp(K * SIGMA * math.sqrt(3)) * 0.9999
    closes = ["10000", "10001", "10002", f"{inside:.6f}", "10000"]
    result = provisional_comparison(
        _record(label="range"), _snapshot(closes), known_sessions=KNOWN, today=TODAY
    )
    assert result.realized == "range" and dict(result.matches)["model"] is True
    down = ["10000", "9990", "9950", "9700", "9600"]
    result = provisional_comparison(_record(), _snapshot(down), known_sessions=KNOWN, today=TODAY)
    assert result.realized == "bearish" and dict(result.matches)["model"] is False


def test_an_insufficient_model_is_not_compared() -> None:
    result = provisional_comparison(
        _record(label="insufficient"), _snapshot(UP), known_sessions=KNOWN, today=TODAY
    )
    assert result.reason is None and dict(result.matches)["model"] is None


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("not-passed", "valid_until_not_passed"),
        ("passed-today", "valid_until_not_passed"),
        ("no-sigma", "threshold_inputs_missing"),
        ("no-snapshot", "no_later_snapshot"),
        ("t-absent", "t_not_in_snapshot"),
        ("short", "sessions_after_t_short"),
        ("not-final", "not_final"),
        ("gap", "session_gap"),
        ("base-close", "base_close_differs"),
        ("unusable", "price_unusable"),
    ],
)
def test_each_no_comparison_reason(case: str, reason: str) -> None:
    record = _record()
    later = _snapshot(UP)
    today = TODAY
    known = KNOWN
    if case == "not-passed":
        today = record.valid_until_session_estimate - timedelta(days=1)
    elif case == "passed-today":
        today = record.valid_until_session_estimate  # the same day has not passed
    elif case == "no-sigma":
        record = replace(record, band_def={**record.band_def, "sigma_d": None})
    elif case == "no-snapshot":
        later = None
    elif case == "t-absent":
        later = _snapshot(UP, start=T + timedelta(days=1))
    elif case == "short":
        later = _snapshot(UP[:3])
    elif case == "not-final":
        later = _snapshot(UP, hours={2: 14})  # T+2 stamped before its 15:00 cutoff
    elif case == "gap":
        # Another snapshot has 2026-11-04; this one skips it inside [T, T+3].
        gap = date(2026, 11, 4)
        known = _sessions(T, 6)
        later = MarketSnapshot(
            bars=tuple(b for b in _snapshot([*UP, "10320"]).bars if b.session_date != gap),
            source="synthetic",
            source_status="backup",
            staleness_minutes=None,
            reason=None,
            dropped=(),
            raw_timestamp_available=False,
        )
    elif case == "base-close":
        record = replace(record, base_close="10000.5")
    else:
        later = _snapshot(["10000", "10050", "10100", "0", "10310"])
    result = provisional_comparison(record, later, known_sessions=known, today=today)
    assert (result.reason, result.realized, result.matches) == (reason, None, ())


def test_a_stored_row_reads_as_a_compared_record() -> None:
    row = {
        "data_as_of": "2026-11-02",
        "horizon": 3,
        "label": "range",
        "band_def": json.dumps(dict(_record().band_def)),
        "base_close": "10000",
        "baseline_predictions_json": json.dumps(
            {
                "B1": {"label": "range"},
                "B2": {"label": "unavailable", "reason": "b2_realized_short"},
                "B6": {"label": "range"},
                "B8": {"label": "bearish"},
            }
        ),
        "valid_until_session_estimate": "2026-11-05",
    }
    record = ComparedRecord.from_row(row)
    # The baselines are kept whole: an unavailable one keeps its reason (D-4 point 3).
    assert record.baseline_predictions == {
        "B1": BaselinePrediction(label="range", reason=None),
        "B2": BaselinePrediction(label="unavailable", reason="b2_realized_short"),
        "B6": BaselinePrediction(label="range", reason=None),
        "B8": BaselinePrediction(label="bearish", reason=None),
    }
    assert record.valid_until_session_estimate == date(2026, 11, 5)
    for broken in ({"band_def": "[]"}, {"baseline_predictions_json": "{}"}, {"horizon": "x"}):
        with pytest.raises(RecordUnreadableError):
            ComparedRecord.from_row({**row, **broken})


@pytest.mark.parametrize(
    "b2",
    [
        pytest.param({"label": "unavailable"}, id="unavailable-without-reason"),
        pytest.param({"label": "unavailable", "reason": None}, id="null-reason"),
        pytest.param({"label": "unavailable", "reason": ""}, id="empty-reason"),
        pytest.param({"label": "unavailable", "reason": 3}, id="reason-not-text"),
        pytest.param({"label": "range", "reason": "b2_realized_short"}, id="reason-on-a-label"),
        pytest.param({"label": None}, id="label-not-text"),
        pytest.param("unavailable", id="not-an-object"),
    ],
)
def test_a_malformed_baseline_makes_the_record_unreadable(b2: object) -> None:
    # Negative cases: a baseline the outputs could not list as D-4 point 3 requires.
    baselines = {
        "B1": {"label": "range"},
        "B2": b2,
        "B6": {"label": "range"},
        "B8": {"label": "bearish"},
    }
    row = {
        "data_as_of": "2026-11-02",
        "horizon": 3,
        "label": "range",
        "band_def": json.dumps(dict(_record().band_def)),
        "base_close": "10000",
        "baseline_predictions_json": json.dumps(baselines),
        "valid_until_session_estimate": "2026-11-05",
    }
    with pytest.raises(RecordUnreadableError):
        ComparedRecord.from_row(row)
    with pytest.raises((TypeError, KeyError, ValueError)):
        BaselinePrediction.from_stored(b2)


# --- K-7 isolation, C-15 ------------------------------------------------------------------


@pytest.mark.parametrize(
    "module", ["app.forecast.store", "app.forecast.recorder", "app.forecast.schema"]
)
def test_k7_scoring_is_not_reachable_from_the_ledger_modules(module: str) -> None:
    assert offenders(reachable_app_modules((module,)), "app.forecast.scoring") == []


def test_k7_only_the_report_imports_scoring_in_app() -> None:
    importers = set()
    for path in sorted(APP_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (
                node.module == "app.forecast.scoring"
                or (node.module == "app.forecast" and any(a.name == "scoring" for a in node.names))
            ):
                importers.add(path.relative_to(APP_ROOT).as_posix())
            elif isinstance(node, ast.Import) and any(
                a.name == "app.forecast.scoring" for a in node.names
            ):
                importers.add(path.relative_to(APP_ROOT).as_posix())
    assert importers == {"forecast/report.py"}


def test_scoring_writes_nothing_and_reads_no_clock() -> None:
    # D-5 point 5: a pure function -- no database, no file, no clock read.
    tree = ast.parse((APP_ROOT / "forecast" / "scoring.py").read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"sqlite3", "open", "print"}
    assert not attributes & {"connect", "execute", "now", "today", "utcnow", "write_text"}
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    forecast = {m for m in imported if m.startswith("app.forecast")}
    assert forecast == {"app.forecast.band", "app.forecast.canonical"}
