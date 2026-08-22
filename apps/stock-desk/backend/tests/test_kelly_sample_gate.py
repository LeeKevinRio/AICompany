"""The four gates an imported Kelly pair has to clear, and the soft band."""

from __future__ import annotations

from typing import get_args

import pytest

from app.kelly.models import KellyGateReasonCode
from app.kelly.sample_gate import (
    MIN_OOS_LOSS_TRIPS,
    MIN_OOS_ROUND_TRIPS,
    MIN_OOS_WIN_TRIPS,
    SOFT_WARNING_ROUND_TRIPS,
    review_estimates,
    review_result_status,
    review_sample,
    review_symbol_match,
)


def test_the_thresholds_are_the_decided_ones() -> None:
    """CEO 2026-08-19 裁決 = 20; the win/loss floors are quant's 5 each (D-3).

    Pinned by test because these are risk-appetite numbers: changing one has to
    be a decision someone took, not a diff nobody noticed.
    """
    assert MIN_OOS_ROUND_TRIPS == 20
    assert MIN_OOS_WIN_TRIPS == 5
    assert MIN_OOS_LOSS_TRIPS == 5
    assert SOFT_WARNING_ROUND_TRIPS == 50


def test_too_few_round_trips_is_refused_and_names_the_numbers() -> None:
    review = review_sample(19, 12, 7)

    assert review.passed is False
    assert review.reason_code == "low_round_trips"
    assert review.rejection is not None
    assert "19" in review.rejection and "20" in review.rejection


def test_exactly_the_threshold_passes_with_the_soft_warning() -> None:
    review = review_sample(MIN_OOS_ROUND_TRIPS, 10, 10)

    assert review.passed is True
    assert review.reason_code is None
    assert review.low_sample_warning is True


@pytest.mark.parametrize(
    ("round_trips", "expected_warning"),
    [(20, True), (49, True), (50, False), (120, False)],
)
def test_the_soft_band_ends_where_the_alternative_threshold_began(
    round_trips: int, expected_warning: bool
) -> None:
    review = review_sample(round_trips, 10, 10)

    assert review.passed is True
    assert review.low_sample_warning is expected_warning


def test_too_few_winning_round_trips_is_refused() -> None:
    review = review_sample(30, 4, 26)

    assert review.reason_code == "low_win_trips"
    assert review.rejection is not None and "4" in review.rejection
    assert review.low_sample_warning is False


def test_too_few_losing_round_trips_is_refused() -> None:
    review = review_sample(30, 26, 4)

    assert review.reason_code == "low_loss_trips"
    assert review.rejection is not None and "4" in review.rejection


def test_the_total_gate_is_reported_before_the_one_sided_ones() -> None:
    """A sample failing two gates reports the first: raising n addresses both."""
    assert review_sample(3, 1, 2).reason_code == "low_round_trips"


@pytest.mark.parametrize(
    ("win_rate", "payoff_ratio"), [(None, 1.8), (0.55, None), (None, None)]
)
def test_a_missing_half_of_the_pair_is_refused(
    win_rate: float | None, payoff_ratio: float | None
) -> None:
    review = review_estimates(win_rate, payoff_ratio)

    assert review.reason_code == "pb_none"
    assert review.passed is False


def test_a_complete_pair_passes_the_estimate_gate() -> None:
    assert review_estimates(0.55, 1.8).passed is True


def test_a_result_that_is_not_ok_is_refused_and_states_the_status() -> None:
    review = review_result_status("insufficient_data")

    assert review.reason_code == "insufficient_data"
    assert review.rejection is not None and "insufficient_data" in review.rejection


def test_an_ok_result_passes_the_status_gate() -> None:
    assert review_result_status("ok").passed is True


def test_a_different_symbol_or_market_is_refused() -> None:
    on_symbol = review_symbol_match(
        path_symbol="2330", path_market="TW", body_symbol="2317", body_market="TW"
    )
    on_market = review_symbol_match(
        path_symbol="AAPL", path_market="US", body_symbol="AAPL", body_market="TW"
    )

    assert on_symbol.reason_code == "symbol_mismatch"
    assert on_market.reason_code == "symbol_mismatch"
    assert on_symbol.rejection is not None and "2317" in on_symbol.rejection


def test_the_symbol_match_ignores_case_and_padding() -> None:
    review = review_symbol_match(
        path_symbol="aapl", path_market="US", body_symbol=" AAPL ", body_market="US"
    )

    assert review.passed is True


def test_every_declared_reason_code_is_reachable() -> None:
    """A code no gate can produce would be a promise the API never keeps."""
    produced = {
        review_sample(1, 0, 0).reason_code,
        review_sample(30, 0, 30).reason_code,
        review_sample(30, 30, 0).reason_code,
        review_estimates(None, None).reason_code,
        review_symbol_match(
            path_symbol="A", path_market="US", body_symbol="B", body_market="US"
        ).reason_code,
        review_result_status("unavailable").reason_code,
    }

    assert produced == set(get_args(KellyGateReasonCode))


def test_a_passing_verdict_carries_no_reason_and_no_message() -> None:
    review = review_sample(80, 40, 40)

    assert (review.reason_code, review.rejection) == (None, None)
    assert review.low_sample_warning is False
