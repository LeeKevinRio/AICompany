"""RC-143: does a ``late = 1`` run that re-fetches bars after the cutoff come out insufficient?

Risk RC-143 asks dev-lead to confirm by test the sentence "a ``late = 1`` run that
re-fetches bars after the cutoff will usually be insufficient" before it is
written into V32-10. The whole chain runs on synthetic FX-B bars: the real
``app.services.index.load_market_benchmark`` with a fake price service, the
snapshot capture, ``compute_outlook`` and a write through ``ForecastStore`` on a
``tmp_path`` ledger with an injected clock (no network, no service database).

What a re-fetch looks like on this path: the index adapter stamps every bar it
returns with its retrieval time (``PriceBar.as_of``), and the snapshot's
``fetched_at`` is that stamp (``app/outlook/inputs.py``). So a re-fetch after the
cutoff puts at least one stamp at or after ``late_cutoff_at`` and
``E-PIT-UNVERIFIED`` holds.

Measured here:

* every re-fetch time from exactly the cutoff to the next evening -- all bars
  re-fetched, or only the latest one (the cached head kept) -- gives
  ``insufficient`` with ``missing = [E-PIT-UNVERIFIED]`` and is written with
  ``late = 1``: deterministic, not "usually";
* a ``late = 1`` run served from bars fetched before the cutoff (no re-fetch)
  keeps its label: lateness alone does not make a record insufficient;
* the on-time run (``late = 0``) with the same bars has the same label.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.dirdef.rules import rules_logic_sha256
from app.forecast.store import ForecastStore
from app.outlook.engine import compute_outlook
from app.outlook.inputs import capture_market_snapshot, late_cutoff_at
from app.services.index import load_market_benchmark
from tests.forecast_ledger_helpers import FakeClock, file_ledger, publish_definition
from tests.outlook_helpers import (
    FIXTURES,
    TAIPEI,
    FakeIndexService,
    closes_from_logs,
    definition,
    price_bar,
    rule_bytes,
    ruleset,
)

T = date(2026, 11, 13)  # a Friday
CUTOFF = late_cutoff_at(T)  # 2026-11-14 00:00 Asia/Taipei


def _sessions_ending(last: date, count: int) -> list[date]:
    days: list[date] = []
    day = last
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return list(reversed(days))


CLOSES = closes_from_logs(FIXTURES["FX-B"])
SESSIONS = _sessions_ending(T, len(CLOSES))


def _stamp(day: date, hour: int = 20) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=TAIPEI)


def _answer_bars(refetched_at: datetime | None, *, tail_only: bool = False) -> list[Any]:
    """FX-B bars as the index path returns them: fetched on their evening, or re-fetched."""
    out = []
    for index, (day, close) in enumerate(zip(SESSIONS, CLOSES, strict=True)):
        stamp = _stamp(day)
        if refetched_at is not None and (not tail_only or index == len(SESSIONS) - 1):
            stamp = refetched_at
        out.append(price_bar(day, Decimal(close), stamp))
    return out


def _record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bars: list[Any], created_at: datetime
) -> dict[str, Any]:
    """Capture, compute and write one h3 record; return the stored row."""
    defn = definition()
    publish_definition(monkeypatch, defn)
    path = file_ledger(tmp_path)
    clock = FakeClock(_stamp(T, 9) - timedelta(days=30))
    store = ForecastStore(path, clock=clock)
    claim = store.register_claim(
        horizon=3,
        rules_version="outlook-market-v1.0-h3",
        rules_bytes=rule_bytes(3),
        rules_logic_sha256=rules_logic_sha256(ruleset(3)),
        definition=defn,
        frozen_commit="abc123",
        prereg_doc_path="docs/prereg-v0.32.md",
        prereg_doc_blob=b"prereg",
        review_refs="work/reviews/x.md",
        replaces_claim_id=None,
        replace_reason=None,
        provisional_results_seen=False,
    )
    answer = load_market_benchmark(
        {"TW": FakeIndexService(bars)}, market="TW", start=SESSIONS[0], end=T + timedelta(days=1)
    )
    snapshot = capture_market_snapshot(answer, size=315)
    assert snapshot is not None and snapshot.data_as_of == T
    outcome = compute_outlook(snapshot, ruleset=ruleset(3), definition=defn, horizon=3)
    clock.now = created_at - timedelta(seconds=1)
    digest = store.put_input_series(
        bars=[bar.as_mapping() for bar in snapshot.bars],
        source=snapshot.source,
        source_status=snapshot.source_status,
        staleness_minutes=snapshot.staleness_minutes,
        reason=snapshot.reason,
        dropped_rows=[
            {"session_date": d.session_date.isoformat(), "reason": d.reason}
            for d in snapshot.dropped
        ],
        raw_timestamp_available=snapshot.raw_timestamp_available,
    )
    run = store.begin_run(code_commit="abc123", code_digest="2" * 64, runtime={"py": "3.13"})
    clock.now = created_at
    evaluation = outcome.evaluation
    store.write_record(
        run_id=run,
        claim_id=claim,
        data_as_of=T,
        label=evaluation.label,
        range_basis=evaluation.range_basis,
        missing=evaluation.missing,
        evidence=evaluation.evidence,
        band_def=evaluation.band_def,
        base_close=outcome.base_close,
        baseline_predictions=outcome.baseline_predictions,
        input_series_sha256=digest,
    )
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM forecast_record").fetchone()
    return dict(row)


REFETCH_TIMES = [
    pytest.param(CUTOFF, id="exactly-the-cutoff"),
    pytest.param(CUTOFF + timedelta(microseconds=1), id="cutoff+1us"),
    pytest.param(CUTOFF + timedelta(hours=1), id="01:00"),
    pytest.param(CUTOFF + timedelta(hours=9), id="09:00"),
    pytest.param(CUTOFF + timedelta(hours=22, minutes=10), id="22:10-next-day"),
]


@pytest.mark.parametrize("tail_only", [False, True], ids=["all-bars", "latest-bar-only"])
@pytest.mark.parametrize("refetched_at", REFETCH_TIMES)
def test_a_late_run_that_refetches_after_the_cutoff_is_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refetched_at: datetime, tail_only: bool
) -> None:
    row = _record(
        tmp_path,
        monkeypatch,
        _answer_bars(refetched_at, tail_only=tail_only),
        created_at=refetched_at + timedelta(seconds=5),
    )
    assert row["late"] == 1
    assert row["label"] == "insufficient"
    missing = json.loads(row["missing_json"])
    assert [m["code"] for m in missing] == ["E-PIT-UNVERIFIED"]
    assert missing[0]["required"] == CUTOFF.isoformat(timespec="microseconds")
    band = json.loads(row["band_def"])
    assert band["sigma_d"] is not None and band["up_pct"] is None


def test_a_late_run_without_a_refetch_keeps_its_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _record(tmp_path, monkeypatch, _answer_bars(None), created_at=CUTOFF + timedelta(hours=1))
    assert row["late"] == 1
    assert row["label"] == "bullish"
    assert json.loads(row["missing_json"]) == []


def test_the_on_time_run_has_the_same_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _record(
        tmp_path, monkeypatch, _answer_bars(None), created_at=_stamp(T, 22) + timedelta(minutes=10)
    )
    assert row["late"] == 0
    assert row["label"] == "bullish"


def test_a_refetch_before_the_cutoff_is_on_time_and_labelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    refetch = CUTOFF - timedelta(seconds=10)
    created = CUTOFF - timedelta(microseconds=1)
    row = _record(tmp_path, monkeypatch, _answer_bars(refetch), created_at=created)
    assert row["late"] == 0
    assert row["label"] == "bullish"
