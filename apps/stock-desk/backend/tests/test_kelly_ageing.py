"""Which moment a Kelly input ages from, and what happens when it has none.

D-4 anchors the two sources on different facts, and the difference is the whole
point: an imported pair that aged from its *run* time would let re-running an
old out-of-sample window reset the clock on stale evidence. The unanchorable
case is fail-safe by decision (qa-reviewer 退修 2026-08-19) -- no anchor is
treated as expired, never as recent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.kelly.models import (
    KELLY_SOFT_NOTICE_DAYS,
    KELLY_STALE_AFTER_DAYS,
    KellyInputRow,
    KellySource,
    ageing_of,
    anchor_moment,
)

_NOW = datetime(2026, 8, 19, 3, 0, tzinfo=UTC)


def _row(
    *,
    source: KellySource = "manual",
    oos_end_date: str | None = None,
    updated_at: datetime = _NOW,
) -> KellyInputRow:
    return KellyInputRow(
        symbol="2330",
        market="TW",
        win_rate=0.55,
        payoff_ratio=1.8,
        source=source,
        strategy_id=None if source == "manual" else "ma_cross",
        oos_end_date=oos_end_date,
        updated_at=updated_at,
    )


def test_a_manual_input_anchors_on_its_write_stamp() -> None:
    row = _row(updated_at=_NOW - timedelta(days=3))

    assert anchor_moment(row) == _NOW - timedelta(days=3)
    assert ageing_of(row, now=_NOW).age_days == 3


def test_an_imported_input_anchors_on_the_end_of_its_segment() -> None:
    """Not on the run time: a re-run of an old window must not look fresh."""
    row = _row(
        source="backtest", oos_end_date="2026-06-30", updated_at=_NOW - timedelta(hours=1)
    )

    ageing = ageing_of(row, now=_NOW)

    assert anchor_moment(row) == datetime(2026, 6, 30, tzinfo=UTC)
    assert ageing.age_days == 50
    assert ageing.freshness == "expired"


def test_an_edited_import_still_anchors_on_the_segment() -> None:
    """``backtest_overridden`` is a backtest source; editing p/b measures nothing new."""
    row = _row(source="backtest_overridden", oos_end_date="2026-08-17", updated_at=_NOW)

    assert anchor_moment(row) == datetime(2026, 8, 17, tzinfo=UTC)
    assert ageing_of(row, now=_NOW).age_days == 2


@pytest.mark.parametrize("source", ["backtest", "backtest_overridden"])
def test_an_import_without_a_segment_end_has_no_anchor(source: KellySource) -> None:
    """The write stamp must not stand in for a missing anchor.

    ``updated_at`` is always at or after the segment it summarises, so
    substituting it moves the anchor towards now and makes the row read
    *younger* -- the exact direction D-4 forbids.
    """
    row = _row(source=source, oos_end_date=None, updated_at=_NOW)

    assert anchor_moment(row) is None


@pytest.mark.parametrize("source", ["backtest", "backtest_overridden"])
def test_an_input_that_cannot_be_aged_is_treated_as_expired(source: KellySource) -> None:
    ageing = ageing_of(_row(source=source, oos_end_date=None), now=_NOW)

    assert ageing.freshness == "expired"
    assert ageing.anchored_at is None
    assert ageing.age_days is None


def test_a_freshly_written_import_with_no_segment_end_is_still_expired() -> None:
    """Written a second ago and still expired: the age is unknown, not zero."""
    ageing = ageing_of(_row(source="backtest", updated_at=_NOW), now=_NOW)

    assert (ageing.age_days, ageing.freshness) == (None, "expired")


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [
        (0, "fresh"),
        (KELLY_SOFT_NOTICE_DAYS - 1, "fresh"),
        (KELLY_SOFT_NOTICE_DAYS, "ageing"),
        (KELLY_STALE_AFTER_DAYS - 1, "ageing"),
        (KELLY_STALE_AFTER_DAYS, "expired"),
    ],
)
def test_the_bands_are_the_declared_ones(age_days: int, expected: str) -> None:
    row = _row(updated_at=_NOW - timedelta(days=age_days))

    assert ageing_of(row, now=_NOW).freshness == expected


def test_an_anchor_in_the_future_reads_as_just_now() -> None:
    """Clock skew must not produce a negative age."""
    row = _row(updated_at=_NOW + timedelta(days=5))

    assert ageing_of(row, now=_NOW).age_days == 0
