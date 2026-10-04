"""Unit tests for the bar-provenance helpers in :mod:`app.signals.frame`."""

from __future__ import annotations

from app.signals.frame import latest_bar_date, provenance
from tests.signals_helpers import make_bar


def test_latest_bar_date_is_the_max_date_regardless_of_input_order() -> None:
    shuffled = [
        make_bar(day_offset=3, close=100.0),
        make_bar(day_offset=9, close=101.0),
        make_bar(day_offset=0, close=99.0),
    ]
    assert latest_bar_date(shuffled) == "2024-01-10"


def test_latest_bar_date_is_the_same_bar_provenance_reads() -> None:
    # Tag each bar with its own source so the bar provenance() picked is visible.
    unordered = [
        make_bar(day_offset=5, close=100.0, source="day-5"),
        make_bar(day_offset=12, close=100.0, source="day-12"),
        make_bar(day_offset=1, close=100.0, source="day-1"),
    ]
    _, source = provenance(unordered)
    assert source == "day-12"
    assert latest_bar_date(unordered) == "2024-01-13"


def test_latest_bar_date_is_an_iso_trading_date_not_a_timestamp() -> None:
    # make_bar stamps as_of 2024-03-01T14:00Z; the retrieval timestamp is a
    # different fact and must not leak into the trading date.
    assert latest_bar_date([make_bar(day_offset=0, close=100.0)]) == "2024-01-01"


def test_latest_bar_date_of_no_bars_is_none() -> None:
    assert latest_bar_date([]) is None
