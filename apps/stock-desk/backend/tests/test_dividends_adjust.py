"""Back-adjustment tests, anchored on a hand-computed golden case.

The golden numbers here were worked out by hand (and are reproduced in the
``app.dividends.adjust`` module docstring) so the arithmetic is auditable
without running the code -- per the backtest-protocol's "every conclusion must
expand into its calculation".
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.data.interface import PriceBar
from app.dividends.adjust import ADJUSTED_SOURCE_SUFFIX, back_adjust_bars, relevant_events
from app.dividends.models import DividendEvent

AS_OF = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _bar(day: date, close: str, symbol: str = "2330") -> PriceBar:
    price = Decimal(close)
    return PriceBar(
        symbol=symbol,
        market="TW",
        date=day,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1_000,
        currency="TWD",
        as_of=AS_OF,
        source="twse",
    )


def _event(
    day: date,
    *,
    previous_close: str | None = None,
    reference_price: str | None = None,
    cash: str = "0",
    rights: str = "0",
    stock_dividend_ratio: str | None = None,
    symbol: str = "2330",
) -> DividendEvent:
    return DividendEvent(
        symbol=symbol,
        market="TW",
        ex_date=day,
        previous_close=None if previous_close is None else Decimal(previous_close),
        reference_price=None if reference_price is None else Decimal(reference_price),
        cash_dividend=Decimal(cash),
        rights_value=Decimal(rights),
        stock_dividend_ratio=(
            None if stock_dividend_ratio is None else Decimal(stock_dividend_ratio)
        ),
        source="test",
        as_of=AS_OF,
    )


# --- The golden case ---------------------------------------------------------
#
# 前收 102.00 -> 參考價 99.00 (現金股利 3.00) on ex-date 2024-06-17.
# factor = 99/102 = 0.9705882352941176...
#
#   2024-06-14  100.00 * 99/102 = 97.058824  (rounded to the 1e-6 quantum)
#   2024-06-15  102.00 * 99/102 = 99.000000
#   2024-06-17   99.00           (ex-date itself: unchanged)
#   2024-06-18  101.00           (after: unchanged)

GOLDEN_BARS = [
    _bar(date(2024, 6, 14), "100.00"),
    _bar(date(2024, 6, 15), "102.00"),
    _bar(date(2024, 6, 17), "99.00"),
    _bar(date(2024, 6, 18), "101.00"),
]
GOLDEN_EVENT = _event(date(2024, 6, 17), previous_close="102.00", reference_price="99.00", cash="3")


def test_golden_factor_is_the_official_reference_over_previous_close() -> None:
    assert GOLDEN_EVENT.adjustment_factor == Decimal("99.00") / Decimal("102.00")


def test_golden_case_adjusted_closes_match_the_hand_computation() -> None:
    adjustment = back_adjust_bars(GOLDEN_BARS, [GOLDEN_EVENT])

    assert adjustment.applied is True
    assert adjustment.events_applied == 1
    assert adjustment.first_ex_date == date(2024, 6, 17)
    closes = [bar.close for bar in adjustment.bars]
    assert closes[0] == Decimal("97.058824")  # 100 * 99/102, quantized
    assert closes[1] == Decimal("99.000000")  # 102 * 99/102, exact
    assert closes[2] == Decimal("99.00")  # ex-date bar untouched
    assert closes[3] == Decimal("101.00")  # anchored at the present


def test_golden_case_removes_the_ex_date_return_gap() -> None:
    """The whole point: the raw series calls the dividend a 2.94% loss."""
    raw_return = float(Decimal("99.00") / Decimal("102.00") - 1)
    assert raw_return == pytest.approx(-0.0294117, abs=1e-6)

    adjusted = back_adjust_bars(GOLDEN_BARS, [GOLDEN_EVENT]).bars
    adjusted_return = float(adjusted[2].close / adjusted[1].close - 1)
    assert adjusted_return == pytest.approx(0.0, abs=1e-9)


def test_all_ohlc_columns_are_scaled_and_volume_is_left_raw() -> None:
    adjustment = back_adjust_bars(GOLDEN_BARS, [GOLDEN_EVENT])
    first = adjustment.bars[0]
    assert first.open == first.high == first.low == first.close == Decimal("97.058824")
    assert first.volume == 1_000  # documented: volume stays raw


def test_adjusted_bars_are_labelled_so_a_leak_is_visible() -> None:
    adjustment = back_adjust_bars(GOLDEN_BARS, [GOLDEN_EVENT])
    assert adjustment.bars[0].source.endswith(ADJUSTED_SOURCE_SUFFIX)
    # The untouched (post-event) bars keep their raw label -- they *are* raw.
    assert adjustment.bars[-1].source == "twse"


def test_understatement_quantifies_what_the_raw_series_lost() -> None:
    adjustment = back_adjust_bars(GOLDEN_BARS, [GOLDEN_EVENT])
    expected = float(Decimal("102.00") / Decimal("99.00") - 1)
    assert adjustment.understatement == pytest.approx(expected, abs=1e-9)


# --- Multiple events ---------------------------------------------------------


def test_factors_compound_across_two_events() -> None:
    bars = [
        _bar(date(2024, 6, 14), "100.00"),
        _bar(date(2024, 6, 20), "104.00"),
        _bar(date(2024, 7, 20), "110.00"),
    ]
    second = _event(
        date(2024, 7, 15), previous_close="110.00", reference_price="107.80", cash="2.2"
    )
    adjustment = back_adjust_bars(bars, [GOLDEN_EVENT, second])

    f1 = Decimal("99.00") / Decimal("102.00")
    f2 = Decimal("107.80") / Decimal("110.00")
    assert adjustment.events_applied == 2
    # Oldest bar sits before both events -> both factors apply.
    assert float(adjustment.bars[0].close) == pytest.approx(
        float(Decimal("100.00") * f1 * f2), abs=1e-6
    )
    # Middle bar sits after the first event, before the second -> only f2.
    assert float(adjustment.bars[1].close) == pytest.approx(
        float(Decimal("104.00") * f2), abs=1e-6
    )
    assert adjustment.bars[2].close == Decimal("110.00")


# --- Boundaries and refusals -------------------------------------------------


def test_event_on_or_before_the_first_bar_is_not_applicable() -> None:
    bars = [_bar(date(2024, 6, 17), "99.00"), _bar(date(2024, 6, 18), "101.00")]
    adjustment = back_adjust_bars(bars, [GOLDEN_EVENT])
    assert adjustment.applied is False
    assert adjustment.events_skipped == 0  # not applicable != unusable
    assert [bar.close for bar in adjustment.bars] == [Decimal("99.00"), Decimal("101.00")]


def test_event_after_the_last_bar_is_excluded_as_future_information() -> None:
    bars = [_bar(date(2024, 6, 14), "100.00"), _bar(date(2024, 6, 15), "102.00")]
    adjustment = back_adjust_bars(bars, [GOLDEN_EVENT])  # ex-date 06-17 > last bar 06-15
    assert adjustment.applied is False
    assert [bar.close for bar in adjustment.bars] == [Decimal("100.00"), Decimal("102.00")]


def test_unusable_event_is_counted_not_guessed() -> None:
    broken = _event(date(2024, 6, 17), previous_close="100.00", reference_price="0.50")
    assert broken.adjustment_factor is None  # implausible 99.5% drop
    adjustment = back_adjust_bars(GOLDEN_BARS, [broken])
    assert adjustment.applied is False
    assert adjustment.events_skipped == 1
    assert adjustment.understatement is None


def test_missing_previous_close_makes_the_event_unusable() -> None:
    no_prev = _event(date(2024, 6, 17), cash="3.00")
    assert no_prev.adjustment_factor is None
    assert no_prev.is_usable is False


def test_component_fallback_is_used_when_no_reference_price_is_published() -> None:
    fallback = _event(date(2024, 6, 17), previous_close="102.00", cash="3.00")
    assert fallback.adjustment_factor == Decimal("99.00") / Decimal("102.00")


def test_rights_component_is_included_in_the_fallback() -> None:
    fallback = _event(date(2024, 8, 1), previous_close="26.50", cash="0.61", rights="0.44")
    expected = (Decimal("26.50") - Decimal("1.05")) / Decimal("26.50")
    assert fallback.adjustment_factor == expected


def test_empty_bars_yields_an_honest_not_applied_result() -> None:
    adjustment = back_adjust_bars([], [GOLDEN_EVENT])
    assert adjustment.bars == []
    assert adjustment.applied is False
    assert adjustment.understatement is None


def test_relevant_events_window_is_exclusive_at_the_start_inclusive_at_the_end() -> None:
    events = [
        _event(date(2024, 6, 14), previous_close="100", reference_price="99"),  # == first bar
        _event(date(2024, 6, 15), previous_close="100", reference_price="99"),  # inside
        _event(date(2024, 6, 18), previous_close="100", reference_price="99"),  # == last bar
        _event(date(2024, 6, 19), previous_close="100", reference_price="99"),  # after
    ]
    kept, skipped = relevant_events(
        events, first_bar_date=date(2024, 6, 14), last_bar_date=date(2024, 6, 18)
    )
    assert [event.ex_date for event in kept] == [date(2024, 6, 15), date(2024, 6, 18)]
    assert skipped == 0


# --- Forecast-table (TWT48U_ALL) events without a published previous_close --


def test_missing_previous_close_is_filled_from_the_bar_before_the_ex_date() -> None:
    """TWT48U_ALL never publishes 前一日收盤價; back_adjust_bars must resolve
    it from the bar series itself, reproducing the golden case's numbers."""
    no_previous_close = _event(date(2024, 6, 17), cash="3.00")
    assert no_previous_close.previous_close is None
    assert no_previous_close.adjustment_factor is None  # unusable before resolution

    adjustment = back_adjust_bars(GOLDEN_BARS, [no_previous_close])
    assert adjustment.applied is True
    assert adjustment.events_applied == 1
    closes = [bar.close for bar in adjustment.bars]
    # Same arithmetic as the golden case: 06-15 close (102.00) minus cash 3.00.
    assert closes[0] == Decimal("97.058824")
    assert closes[1] == Decimal("99.000000")


def test_a_previous_close_already_on_the_event_is_never_overwritten() -> None:
    """A future non-forecast source that does publish previous_close must not
    have it silently replaced by the bar-derived value."""
    published = _event(date(2024, 6, 17), previous_close="102.00", cash="3.00")
    adjustment = back_adjust_bars(GOLDEN_BARS, [published])
    assert adjustment.bars[0].close == Decimal("97.058824")


def test_an_event_with_no_earlier_bar_stays_unfilled_and_inapplicable() -> None:
    bars = [_bar(date(2024, 6, 17), "99.00"), _bar(date(2024, 6, 18), "101.00")]
    no_previous_close = _event(date(2024, 6, 17), cash="3.00")  # == first bar's date
    adjustment = back_adjust_bars(bars, [no_previous_close])
    assert adjustment.applied is False
    assert adjustment.events_skipped == 0  # not applicable, not unusable


def test_stock_dividend_ratio_stays_unusable_even_after_previous_close_is_filled() -> None:
    """The bar-derived previous_close would make the cash portion computable,
    but a stock component present and uncomputed must still refuse the whole
    event rather than silently apply a cash-only, incomplete factor."""
    mixed = _event(date(2024, 6, 17), cash="3.00", stock_dividend_ratio="12.5")
    adjustment = back_adjust_bars(GOLDEN_BARS, [mixed])
    assert adjustment.applied is False
    assert adjustment.events_skipped == 1


def test_events_are_applied_in_date_order_regardless_of_input_order() -> None:
    second = _event(date(2024, 7, 15), previous_close="110.00", reference_price="107.80")
    bars = [_bar(date(2024, 6, 14), "100.00"), _bar(date(2024, 7, 20), "110.00")]
    forwards = back_adjust_bars(bars, [GOLDEN_EVENT, second])
    backwards = back_adjust_bars(bars, [second, GOLDEN_EVENT])
    assert [bar.close for bar in forwards.bars] == [bar.close for bar in backwards.bars]
    assert forwards.first_ex_date == backwards.first_ex_date == date(2024, 6, 17)
