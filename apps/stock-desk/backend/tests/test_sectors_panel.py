"""``MarketPanel`` / ``PointInTimePanel`` visibility rules (ADR-0012 D-2, D-6, C-14).

The ``PanelFrames`` wire shape is frozen: this file pins its columns so a
change there is a visible ADR change, not a silent one.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pandas as pd
import pytest

from app.data.panel import (
    BARS_COLUMNS,
    CLASSIFICATION_COLUMNS,
    EX_DIVIDEND_COLUMNS,
    LISTING_COLUMNS,
    RUNS_COLUMNS,
    MarketPanel,
    PointInTimePanel,
    PointInTimeViolation,
    cutoff,
)
from tests.sectors_helpers import PanelBuilder, taipei, weekdays

DAY = date(2026, 3, 2)
NEXT = date(2026, 3, 3)


def test_panel_frames_columns_are_unchanged() -> None:
    assert BARS_COLUMNS == (
        "run_id",
        "session_date",
        "recorded_at",
        "source",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "shares",
        "traded_value",
        "change",
    )
    assert LISTING_COLUMNS == ("run_id", "session_date", "recorded_at", "symbol", "security_type")
    assert CLASSIFICATION_COLUMNS == (
        "run_id",
        "session_date",
        "recorded_at",
        "symbol",
        "sector_code",
        "sector_name",
    )
    assert EX_DIVIDEND_COLUMNS == ("run_id", "session_date", "recorded_at", "symbol", "ex_date")
    assert RUNS_COLUMNS == (
        "run_id",
        "kind",
        "session_date",
        "recorded_at",
        "source",
        "status",
        "row_count",
        "expected_count",
    )


def test_cutoff_is_2359_59_taipei_in_utc() -> None:
    assert cutoff(DAY) == pd.Timestamp("2026-03-02T15:59:59Z")


def test_rows_recorded_after_the_cutoff_are_invisible() -> None:
    builder = PanelBuilder()
    on_time = builder.run("bars", DAY, recorded=taipei(DAY, 23, 59, 59))
    builder.bar(on_time, DAY, "1101", 10.0)
    late = builder.run("bars", DAY, recorded=taipei(NEXT, 0, 0, 0), source="finmind")
    builder.bar(late, DAY, "1102", 20.0, source="finmind")
    market = builder.panel()
    view = market.as_of(DAY)
    assert list(view.bars(DAY, DAY)["symbol"]) == ["1101"]
    assert set(market.as_of(NEXT).bars(DAY, DAY)["symbol"]) == {"1101", "1102"}


def test_sessions_after_the_decision_date_are_invisible_and_refused() -> None:
    builder = PanelBuilder()
    for day in (DAY, NEXT):
        run = builder.run("bars", day)
        builder.bar(run, day, "1101", 10.0)
    view = builder.panel().as_of(DAY)
    assert view.sessions == (DAY,)
    with pytest.raises(PointInTimeViolation):
        view.bars(DAY, NEXT)
    with pytest.raises(PointInTimeViolation):
        view.field_matrix("close", [DAY, NEXT])
    with pytest.raises(PointInTimeViolation):
        view.sessions_before(NEXT, 3)
    with pytest.raises(PointInTimeViolation):
        view.bars_source_on(NEXT)


def test_non_ok_runs_never_feed_a_view() -> None:
    builder = PanelBuilder()
    for status in ("partial", "failed", "quality_failed"):
        run = builder.run("bars", DAY, status=status)
        builder.bar(run, DAY, f"1{status[:3]}", 10.0)
    ok = builder.run("bars", DAY)
    builder.bar(ok, DAY, "1101", 10.0)
    view = builder.panel().as_of(DAY)
    assert list(view.bars(DAY, DAY)["symbol"]) == ["1101"]
    assert len(view.visible_runs()) == 4  # diagnostics still see every run


def test_primary_source_wins_then_the_latest_correction() -> None:
    builder = PanelBuilder()
    finmind = builder.run("bars", DAY, source="finmind", recorded=taipei(DAY, 17))
    builder.bar(finmind, DAY, "1101", 11.0, source="finmind")
    builder.bar(finmind, DAY, "1102", 22.0, source="finmind")
    twse = builder.run("bars", DAY, recorded=taipei(DAY, 18))
    builder.bar(twse, DAY, "1101", 10.0)
    fix = builder.run("bars", DAY, recorded=taipei(DAY, 21))
    builder.bar(fix, DAY, "1101", 10.5)
    view = builder.panel().as_of(DAY)
    closes = view.field_matrix("close", [DAY], ["1101", "1102"])
    assert closes.at[DAY, "1101"] == 10.5
    assert closes.at[DAY, "1102"] == 22.0  # only finmind has it
    assert view.bars_source_on(DAY) == "twse_snapshot"


def test_snapshots_carry_forward_and_report_how_long() -> None:
    days = weekdays(4, DAY)
    builder = PanelBuilder()
    for day in days:
        run = builder.run("bars", day)
        builder.bar(run, day, "1101", 10.0)
    listing = builder.run("listing", days[0])
    builder.listed(listing, days[0], "1101")
    snap = builder.panel().as_of(days[-1]).snapshot("listing")
    assert snap is not None
    assert snap.session_date == days[0]
    assert snap.carried_sessions == 3 and snap.carried_forward
    assert builder.panel().as_of(days[0]).snapshot("classification") is None


def test_ex_dividend_announcements_are_the_union_of_visible_runs() -> None:
    days = weekdays(3, DAY)
    builder = PanelBuilder()
    first = builder.run("dividend_announce", days[0])
    builder.announced(first, days[0], "1101", days[1])
    builder.run("dividend_announce", days[1])  # the event has happened: no longer listed
    late = builder.run("dividend_announce", days[1], recorded=taipei(days[2], 9))
    builder.announced(late, days[1], "1102", days[1])
    view = builder.panel().as_of(days[1])
    assert list(view.ex_dividend_announcements()["symbol"]) == ["1101"]
    assert view.ok_run_sessions("dividend_announce") == {days[0], days[1]}


def test_point_in_time_panel_cannot_be_built_directly() -> None:
    with pytest.raises(TypeError, match="as_of"):
        PointInTimePanel(
            key=object(),
            decision_date=DAY,
            regime="pit",
            cutoff_at=None,
            frames=PanelBuilder().frames(),
        )


def test_as_of_only_ever_yields_the_pit_regime() -> None:
    view = PanelBuilder().panel().as_of(DAY)
    assert view.regime == "pit"
    assert view.cutoff == cutoff(DAY)


def test_naive_recorded_at_is_refused() -> None:
    builder = PanelBuilder()
    run = builder.run("bars", DAY)
    builder.bar(run, DAY, "1101", 10.0)
    frames = builder.frames()
    naive = frames.runs.assign(recorded_at=frames.runs["recorded_at"].dt.tz_localize(None))
    with pytest.raises(ValueError, match="timezone-aware"):
        MarketPanel(dataclasses.replace(frames, runs=naive))


def test_missing_columns_are_refused() -> None:
    frames = PanelBuilder().frames()
    with pytest.raises(ValueError, match="missing columns"):
        MarketPanel(dataclasses.replace(frames, bars=frames.bars.drop(columns=["change"])))


def test_accessors_hand_out_copies() -> None:
    builder = PanelBuilder()
    run = builder.run("bars", DAY)
    builder.bar(run, DAY, "1101", 10.0)
    view = builder.panel().as_of(DAY)
    rows = view.bars(DAY, DAY)
    rows.loc[:, "close"] = 999.0
    assert view.bars(DAY, DAY)["close"].tolist() == [10.0]
