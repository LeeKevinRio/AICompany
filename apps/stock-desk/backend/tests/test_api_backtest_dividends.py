"""``POST /api/backtest`` 除權息 disclosure wiring (offline fakes only).

The rule under test is not "the adjustment works" (that is
``test_dividends_adjust.py``) but **"the response never misstates whether it
happened"**: adjusted on by default, degraded runs still produce a report, and
each degradation reason gets its own sentence.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.api.backtest import (
    DIVIDEND_ADJUSTED_NOTE,
    DIVIDEND_DISABLED_NOTE,
    DIVIDEND_METHOD_NOTE,
    DIVIDEND_NO_EVENT_NOTE,
    DIVIDEND_NOT_SYNCED_NOTE,
    DIVIDEND_UNUSABLE_NOTE,
)
from app.dividends.models import DividendEvent
from tests.api_helpers import oscillating_closes, recent_bars
from tests.conftest import ApiHarness

_END = date(2026, 7, 20)
_START = _END - timedelta(days=600)
_BAR_COUNT = 400
#: The oldest bar the fake service serves, so seeded ex-dates land inside it.
_FIRST_BAR_DATE = _END - timedelta(days=_BAR_COUNT - 1)
AS_OF = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


def _seed_bars(harness: ApiHarness, symbol: str = "2330") -> None:
    harness.price_service.seed(
        symbol, recent_bars(oscillating_closes(_BAR_COUNT), symbol=symbol, end=_END)
    )


def _seed_event(
    harness: ApiHarness,
    *,
    days_after_first_bar: int = 100,
    symbol: str = "2330",
    previous_close: str = "105.00",
    reference_price: str | None = "101.00",
) -> None:
    harness.dividends.upsert(
        [
            DividendEvent(
                symbol=symbol,
                market="TW",
                ex_date=_FIRST_BAR_DATE + timedelta(days=days_after_first_bar),
                previous_close=Decimal(previous_close),
                reference_price=None if reference_price is None else Decimal(reference_price),
                cash_dividend=Decimal("4.00"),
                source="test",
                as_of=AS_OF,
            )
        ]
    )


def _request(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "symbol": "2330",
        "market": "TW",
        "strategy": "ma_cross",
        "start": _START.isoformat(),
        "end": _END.isoformat(),
        "train_size": 200,
        "test_size": 60,
    }
    body.update(overrides)
    return body


def _post(harness: ApiHarness, **overrides: Any) -> dict[str, Any]:
    response = harness.client.post("/api/backtest", json=_request(**overrides))
    assert response.status_code == 200
    return dict(response.json())


def test_adjustment_is_requested_by_default(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    _seed_event(api_harness)
    block = _post(api_harness)["dividend_adjustment"]
    assert block["requested"] is True
    assert block["applied"] is True
    assert block["reason_code"] == "adjusted"


def test_an_applied_adjustment_is_disclosed_with_its_event_count(
    api_harness: ApiHarness,
) -> None:
    _seed_bars(api_harness)
    _seed_event(api_harness)
    body = _post(api_harness)
    block = body["dividend_adjustment"]
    assert block["events_applied"] == 1
    assert block["first_ex_date"] == block["last_ex_date"]
    assert block["raw_return_understatement"] > 0
    assert DIVIDEND_ADJUSTED_NOTE in body["notes"]
    assert DIVIDEND_METHOD_NOTE in body["notes"]


def test_adjustment_raises_the_measured_return_of_the_segment_containing_it(
    api_harness: ApiHarness,
) -> None:
    """Without this, the disclosure could be true while the numbers were not.

    The seeded ex-date sits inside the in-sample window, so that is the segment
    whose Buy & Hold return must move. The out-of-sample window lies entirely
    after the event and correctly sees no change -- an adjustment that "fixed"
    a segment containing no ex-date would be the bug, not the fix.
    """
    _seed_bars(api_harness)
    _seed_event(api_harness)
    adjusted = _post(api_harness)
    raw = _post(api_harness, adjust_dividends=False)
    assert adjusted["dividend_adjustment"]["applied"] is True
    assert raw["dividend_adjustment"]["applied"] is False

    adjusted_in = adjusted["report"]["in_sample"]["buy_and_hold"]["total_return"]
    raw_in = raw["report"]["in_sample"]["buy_and_hold"]["total_return"]
    assert adjusted_in > raw_in  # the raw series understated it

    adjusted_out = adjusted["report"]["out_of_sample"]["buy_and_hold"]["total_return"]
    raw_out = raw["report"]["out_of_sample"]["buy_and_hold"]["total_return"]
    assert adjusted_out == raw_out


def test_never_synced_store_still_runs_the_backtest_and_says_so(
    api_harness: ApiHarness,
) -> None:
    _seed_bars(api_harness)  # no events seeded at all
    body = _post(api_harness)
    assert body["status"] == "ok"
    assert body["report"] is not None  # runs anyway -- never a silent refusal
    block = body["dividend_adjustment"]
    assert block["applied"] is False
    assert block["reason_code"] == "never_synced"
    assert DIVIDEND_NOT_SYNCED_NOTE in body["notes"]
    assert DIVIDEND_ADJUSTED_NOTE not in body["notes"]


def test_synced_store_without_an_event_for_this_symbol_gets_its_own_sentence(
    api_harness: ApiHarness,
) -> None:
    """"No data for this symbol" and "never synced" are different facts."""
    _seed_bars(api_harness)
    _seed_event(api_harness, symbol="2884")  # some other symbol was synced
    body = _post(api_harness)
    block = body["dividend_adjustment"]
    assert block["reason_code"] == "no_events"
    assert block["applied"] is False
    assert DIVIDEND_NO_EVENT_NOTE in body["notes"]
    assert block["last_synced_at"] is not None


def test_events_that_cannot_yield_a_factor_are_disclosed_as_unusable(
    api_harness: ApiHarness,
) -> None:
    _seed_bars(api_harness)
    # Reference price 0.50 against a 100.00 previous close: not a distribution,
    # a broken row. It must not quietly become "this symbol had no dividend".
    _seed_event(api_harness, previous_close="100.00", reference_price="0.50")
    body = _post(api_harness)
    block = body["dividend_adjustment"]
    assert block["reason_code"] == "unusable_events"
    assert block["events_skipped"] == 1
    assert DIVIDEND_UNUSABLE_NOTE in body["notes"]


def test_turning_adjustment_off_is_itself_disclosed(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    _seed_event(api_harness)
    body = _post(api_harness, adjust_dividends=False)
    block = body["dividend_adjustment"]
    assert block["requested"] is False
    assert block["applied"] is False
    assert block["reason_code"] == "disabled"
    assert DIVIDEND_DISABLED_NOTE in body["notes"]
    assert DIVIDEND_ADJUSTED_NOTE not in body["notes"]


def test_every_note_sentence_states_the_direction_of_the_bias(
    api_harness: ApiHarness,
) -> None:
    """Each "未還原" sentence must warn that the return is understated."""
    for note in (
        DIVIDEND_NOT_SYNCED_NOTE,
        DIVIDEND_NO_EVENT_NOTE,
        DIVIDEND_UNUSABLE_NOTE,
        DIVIDEND_DISABLED_NOTE,
    ):
        assert "未還原" in note or "關閉除權息還原" in note
        assert "低估" in note


def test_a_run_with_no_report_claims_nothing_about_adjustment(
    api_harness: ApiHarness,
) -> None:
    body = _post(api_harness)  # no bars seeded -> insufficient_data
    assert body["status"] == "insufficient_data"
    block = body["dividend_adjustment"]
    assert block["applied"] is False
    assert block["reason_code"] == "not_run"
    assert block["note"] is None
    assert DIVIDEND_ADJUSTED_NOTE not in body["notes"]


def test_provenance_still_describes_the_raw_source(api_harness: ApiHarness) -> None:
    """The ``data`` block reports the real feed, not the synthetic adjusted one."""
    _seed_bars(api_harness)
    _seed_event(api_harness)
    body = _post(api_harness)
    assert body["data"]["bar_count"] == _BAR_COUNT
    assert "divadj" not in body["data"]["source"]
