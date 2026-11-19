"""Characterisation: a session absent from the index answer stays absent (ADR-0030 D-8 point 3).

Known limitation, accepted by ADR-0030 (tech-architect ruling,
``work/reviews/2026-11-19-缺日靜默丟列與登記先後裁示-tech-architect.md`` point 5):
when the source has no row for a session -- e.g. the adapter dropped a row with
missing values -- the core does not detect the missing day. The snapshot keeps
the gap, nothing is filled in, ``dropped_rows_json`` does not name it, and the
outcome and ``missing_json`` follow the same rules as without the gap (no new
code). When the missing day is T itself, the run takes the latest final bar
before it: ``no_new_session``, or a ``late = 1`` record of T-1. This is the
known blind spot of ADR-0030 supplement 8 (final draft 2, to be appended) point
2 (a), (b); S-18a "point 3 (d)". The repair belongs to a later ADR (the
validation layer, D-8 point 3's frozen appendix); this test pins today's
behaviour so the wiring PR cannot change it silently.

``tmp_path`` ledgers and synthetic bars only.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from app.data.interface import PriceBar
from app.dirdef.registry import PublishedRuleset
from app.dirdef.rules import rules_logic_sha256
from app.forecast import definitions
from app.forecast.recorder import RunResult, record_forecasts
from app.forecast.store import ForecastStore
from app.outlook.engine import MISSING_CODES
from app.services.index import IndexServiceResolver, load_market_benchmark
from tests.forecast_ledger_helpers import FakeClock, file_ledger, publish_definition
from tests.outlook_helpers import (
    TAIPEI,
    FakeIndexService,
    definition,
    price_bar,
    rule_bytes,
    ruleset,
)

H3 = "outlook-market-v1.0-h3"
H5 = "outlook-market-v1.0-h5"
LAST = date(2026, 11, 13)  # a Friday


def _days(count: int) -> list[date]:
    days: list[date] = []
    day = LAST
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day = date.fromordinal(day.toordinal() - 1)
    return list(reversed(days))


def _bars(days: list[date]) -> list[PriceBar]:
    closes = [10000.0]
    for j in range(1, len(days)):
        step = 0.008 * math.sin(0.7 * j) + 0.003 * (((j * 7919) % 13) - 6) / 6
        closes.append(closes[-1] * math.exp(step))
    return [
        price_bar(day, Decimal(close), datetime.combine(day, time(20), TAIPEI))
        for day, close in zip(days, closes, strict=True)
    ]


DAYS = _days(331)
#: A session in the middle of the snapshot window (well inside N_SNAPSHOT = 315).
GAP = DAYS[-100]


def _run(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    bars: list[PriceBar],
    *,
    earlier: tuple[date, list[PriceBar]] | None = None,
) -> Path:
    """Register the two claims and run the recorder at LAST 22:10 on ``bars``.

    ``earlier``: one run before that, at the given day's 22:10 on its own bars.
    """
    root.mkdir(parents=True)
    publish_definition(monkeypatch, definition())
    entries = {
        H3: PublishedRuleset(horizon=3, rules_sha256=hashlib.sha256(rule_bytes(3)).hexdigest()),
        H5: PublishedRuleset(horizon=5, rules_sha256=hashlib.sha256(rule_bytes(5)).hexdigest()),
    }
    monkeypatch.setattr(definitions, "PUBLISHED_RULESETS", MappingProxyType(entries))
    monkeypatch.setattr(definitions, "_RULESET_CACHE", {})
    path = file_ledger(root)
    clock = FakeClock(datetime(2026, 10, 1, 9, tzinfo=TAIPEI))
    store = ForecastStore(path, clock=clock)
    for horizon in (3, 5):
        clock.advance(seconds=1)
        store.register_claim(
            horizon=3 if horizon == 3 else 5,
            rules_version=H3 if horizon == 3 else H5,
            rules_bytes=rule_bytes(horizon),
            rules_logic_sha256=rules_logic_sha256(ruleset(horizon)),
            definition=definition(),
            frozen_commit="abc123",
            prereg_doc_path="docs/prereg-v0.32.md",
            prereg_doc_blob=b"prereg",
            review_refs="work/reviews/x.md",
            replaces_claim_id=None,
            replace_reason=None,
            provisional_results_seen=False,
        )
    if earlier is not None:
        day, earlier_bars = earlier
        clock.now = datetime.combine(day, time(22, 10), TAIPEI)
        first: IndexServiceResolver = {"TW": FakeIndexService(earlier_bars)}
        assert (
            record_forecasts(store, load_benchmark=load_market_benchmark, resolver=first).outcome
            == "ok"
        )
    clock.now = datetime.combine(LAST, time(22, 10), TAIPEI)
    resolver: IndexServiceResolver = {"TW": FakeIndexService(bars)}
    result: RunResult = record_forecasts(
        store, load_benchmark=load_market_benchmark, resolver=resolver
    )
    assert result.outcome in ("ok", "no_new_session")
    return path


def _rows(path: Path, sql: str) -> list[sqlite3.Row]:
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        return list(conn.execute(sql))


def test_a_missing_session_is_kept_as_a_gap_and_judged_by_the_same_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    whole = _run(tmp_path / "whole", monkeypatch, _bars(DAYS))
    gapped_bars = [bar for bar in _bars(DAYS) if bar.date != GAP]
    gapped = _run(tmp_path / "gapped", monkeypatch, gapped_bars)

    (whole_series,) = _rows(whole, "SELECT bars_json, dropped_rows_json FROM forecast_input_series")
    (gap_series,) = _rows(gapped, "SELECT bars_json, dropped_rows_json FROM forecast_input_series")
    whole_days = [bar["session_date"] for bar in json.loads(whole_series["bars_json"])]
    gap_days = [bar["session_date"] for bar in json.loads(gap_series["bars_json"])]

    # (1) The snapshot keeps the gap as it is: the same last N sessions of the answer,
    # without the missing day and without any value put in its place.
    assert GAP.isoformat() in whole_days and GAP.isoformat() not in gap_days
    assert len(gap_days) == len(whole_days)
    expected = [d.isoformat() for d in DAYS if d != GAP][-len(gap_days) :]
    assert gap_days == expected
    by_day = {bar.date.isoformat(): bar for bar in gapped_bars}
    for stored in json.loads(gap_series["bars_json"]):
        assert Decimal(str(stored["close"])) == by_day[stored["session_date"]].close

    # (2) dropped_rows_json does not name the missing day (it was never a row).
    assert GAP.isoformat() not in gap_series["dropped_rows_json"]
    assert json.loads(gap_series["dropped_rows_json"]) == json.loads(
        whole_series["dropped_rows_json"]
    )

    # (3) Same outcome and the same missing-item rules: no new code for the gap.
    for path in (whole, gapped):
        assert [r["outcome"] for r in _rows(path, "SELECT outcome FROM forecast_run_end")] == ["ok"]
    for path in (whole, gapped):
        for record in _rows(path, "SELECT label, missing_json FROM forecast_record"):
            codes = {item["code"] for item in json.loads(record["missing_json"])}
            assert codes <= set(MISSING_CODES)
            assert bool(codes) == (record["label"] == "insufficient")
    whole_missing = [
        r["missing_json"]
        for r in _rows(whole, "SELECT missing_json FROM forecast_record ORDER BY horizon")
    ]
    gap_missing = [
        r["missing_json"]
        for r in _rows(gapped, "SELECT missing_json FROM forecast_record ORDER BY horizon")
    ]
    assert gap_missing == whole_missing


def test_a_missing_t_falls_back_to_the_previous_final_bar_late(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Supplement 8 point 2 (b): the source has no row for T (LAST) and T-1 was never
    # recorded. The run at LAST 22:10 takes T-1 as the latest final bar; T-1's cutoff has
    # passed, so this fixture's one outcome is ok with two late = 1 records of T-1.
    bars = [bar for bar in _bars(DAYS) if bar.date != LAST]
    path = _run(tmp_path / "no-t", monkeypatch, bars)
    (series,) = _rows(path, "SELECT bars_json, dropped_rows_json FROM forecast_input_series")
    days = [bar["session_date"] for bar in json.loads(series["bars_json"])]
    assert LAST.isoformat() not in days and days[-1] == DAYS[-2].isoformat()
    assert LAST.isoformat() not in series["dropped_rows_json"]
    (end,) = _rows(path, "SELECT outcome, candidate_t FROM forecast_run_end")
    assert (end["outcome"], end["candidate_t"]) == ("ok", DAYS[-2].isoformat())
    records = _rows(path, "SELECT data_as_of, late, label, missing_json FROM forecast_record")
    assert len(records) == 2
    for record in records:
        assert (record["data_as_of"], record["late"]) == (DAYS[-2].isoformat(), 1)
        codes = {item["code"] for item in json.loads(record["missing_json"])}
        assert codes <= set(MISSING_CODES)
        assert bool(codes) == (record["label"] == "insufficient")


def test_a_missing_t_after_t_minus_1_was_recorded_is_no_new_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Supplement 8 point 2 (b), the other outcome: T-1 was recorded on time the evening
    # before, so the run at LAST 22:10 finds no new session and writes nothing more.
    bars = [bar for bar in _bars(DAYS) if bar.date != LAST]
    path = _run(tmp_path / "no-t-seen", monkeypatch, bars, earlier=(DAYS[-2], bars))
    ends = _rows(path, "SELECT outcome, candidate_t FROM forecast_run_end ORDER BY run_id")
    assert [(e["outcome"], e["candidate_t"]) for e in ends] == [
        ("ok", DAYS[-2].isoformat()),
        ("no_new_session", DAYS[-2].isoformat()),
    ]
    records = _rows(path, "SELECT data_as_of, late FROM forecast_record")
    assert [(r["data_as_of"], r["late"]) for r in records] == [(DAYS[-2].isoformat(), 0)] * 2
    assert len(_rows(path, "SELECT 1 FROM forecast_input_series")) == 1
