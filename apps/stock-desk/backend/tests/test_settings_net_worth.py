"""Tests for the FR-9 (c) sanity bands on a reported account net worth.

The three bands are the only thing standing between a mistyped denominator and
a gross-exposure cap that looks like it is working. Each one is pinned here at
its edge, and every case asserts what was *not* done as well: nothing is ever
rewritten to a "nearest legal" value.
"""

from __future__ import annotations

from app.settings.net_worth import (
    NET_WORTH_MIN_RATIO,
    NET_WORTH_WARN_RATIO,
    NetWorthReview,
    review_net_worth,
)

_BOOK = 1_000_000.0


def _review(
    amount: float, *, valued: float = _BOOK, valued_count: int = 3, total: int = 3
) -> NetWorthReview:
    return review_net_worth(
        amount,
        valued_market_value_twd=valued,
        valued_count=valued_count,
        total_count=total,
    )


def test_a_plausible_net_worth_passes_without_comment() -> None:
    review = _review(_BOOK * 1.4)
    assert review.rejection is None
    assert review.warnings == []
    assert review.notes == []


def test_below_the_tolerance_is_rejected_with_the_named_reason() -> None:
    review = _review(_BOOK * 0.5)
    assert review.rejection is not None
    assert "自報淨值小於系統已估值的部位市值" in review.rejection
    assert "系統不會自行調整這個數字" in review.rejection


def test_the_rejection_edge_sits_exactly_on_the_tolerance() -> None:
    assert _review(_BOOK * NET_WORTH_MIN_RATIO).rejection is None
    assert _review(_BOOK * NET_WORTH_MIN_RATIO - 1.0).rejection is not None


def test_far_above_the_book_is_accepted_and_warned_about() -> None:
    review = _review(_BOOK * NET_WORTH_WARN_RATIO + 1.0)
    # Accepted: holding mostly cash is a legitimate position, not an error.
    assert review.rejection is None
    assert len(review.warnings) == 1
    assert "若此數字有誤，第 3 條上限將失去意義" in review.warnings[0]


def test_the_warning_edge_sits_exactly_on_the_multiple() -> None:
    assert _review(_BOOK * NET_WORTH_WARN_RATIO).warnings == []


def test_no_valued_book_means_the_relative_bands_are_skipped_and_said_to_be() -> None:
    # Applying them against a zero yardstick would reject or warn about
    # everything; claiming the figure was checked would be worse still.
    review = _review(5_000_000.0, valued=0.0, valued_count=0, total=2)
    assert review.rejection is None
    assert review.warnings == []
    assert any("無法用部位市值檢查" in note for note in review.notes)


def test_a_partial_book_is_compared_but_the_gap_is_disclosed() -> None:
    review = _review(_BOOK * 1.4, valued_count=2, total=5)
    assert review.rejection is None
    assert any("3 筆部位無法估值" in note for note in review.notes)
