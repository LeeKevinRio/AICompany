"""Table-driven tests for every rejection code in ``app.data.quote_quality`` (W2).

Reference instant: Monday 2026-10-05 10:00:05 Asia/Taipei (02:00:05 UTC). The
thresholds exercised are the ADR-0014 pre-measurement defaults.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from app.data.interface import QuoteKey, QuoteRejectCode
from app.data.quote_quality import (
    DEFAULT_THRESHOLDS,
    QuoteQualityThresholds,
    RawQuoteResponse,
    RawQuoteRow,
    assess_quotes,
)

TAIPEI = timezone(timedelta(hours=8))
AS_OF = datetime(2026, 10, 5, 10, 0, 5, tzinfo=TAIPEI)
TODAY = date(2026, 10, 5)
SERVER_TIME = datetime(2026, 10, 5, 10, 0, 4, tzinfo=TAIPEI)

TSMC = QuoteKey(symbol="2330", board="tse")
TPEX = QuoteKey(symbol="5483", board="otc")


def _row(key: QuoteKey = TSMC, **overrides: Any) -> RawQuoteRow:
    fields: dict[str, Any] = {
        "requested": key,
        "symbol": key.symbol,
        "board": key.board,
        "last_price": Decimal("1050"),
        "prev_close": Decimal("1040"),
        "limit_up": None,
        "limit_down": None,
        "trade_date": TODAY,
        "quote_time": datetime(2026, 10, 5, 10, 0, 3, tzinfo=TAIPEI),
        "is_trial_match": None,
    }
    fields.update(overrides)
    return RawQuoteRow(**fields)


def _response(*rows: RawQuoteRow, **overrides: Any) -> RawQuoteResponse:
    fields: dict[str, Any] = {
        "transport": "ok",
        "as_of": AS_OF,
        "source": "twse_mis",
        "rtcode": "0000",
        "server_time": SERVER_TIME,
        "rows": rows,
    }
    fields.update(overrides)
    return RawQuoteResponse(**fields)


def _no_sentinel() -> QuoteQualityThresholds:
    return replace(DEFAULT_THRESHOLDS, sentinel=None)


# ---------------------------------------------------------------------------
# Happy path and batch status
# ---------------------------------------------------------------------------


def test_accepts_a_clean_row_and_carries_provenance() -> None:
    batch = assess_quotes([TSMC], _response(_row()))
    assert batch.status == "ok"
    assert batch.rejections == ()
    assert batch.reason is None
    assert batch.reject_code is None
    (quote,) = batch.quotes
    assert quote.symbol == "2330"
    assert quote.board == "tse"
    assert quote.price == Decimal("1050")
    assert quote.prev_close == Decimal("1040")
    assert quote.trade_date == TODAY
    assert quote.as_of == AS_OF
    assert quote.server_time == SERVER_TIME
    assert quote.source == "twse_mis"
    assert quote.currency == "TWD"
    assert batch.as_of == AS_OF
    assert batch.source == "twse_mis"


def test_empty_request_is_an_empty_ok_batch() -> None:
    batch = assess_quotes([], _response(transport="blocked"))
    assert batch.status == "ok"
    assert batch.quotes == ()
    assert batch.rejections == ()


def test_duplicate_requested_keys_are_collapsed() -> None:
    batch = assess_quotes([TSMC, TSMC], _response(_row()))
    assert batch.status == "ok"
    assert len(batch.quotes) == 1


def test_partial_when_some_channels_are_rejected() -> None:
    batch = assess_quotes(
        [TSMC, TPEX], _response(_row(), _row(TPEX, last_price=None)), _no_sentinel()
    )
    assert batch.status == "partial"
    assert [q.symbol for q in batch.quotes] == ["2330"]
    assert [(r.symbol, r.board, r.code) for r in batch.rejections] == [
        ("5483", "otc", QuoteRejectCode.NO_TRADE)
    ]
    assert batch.reason == "1 of 2 requested channels rejected"
    assert batch.reject_code is None


def test_failed_when_every_channel_is_rejected_per_symbol() -> None:
    batch = assess_quotes([TSMC], _response(_row(last_price=None)), _no_sentinel())
    assert batch.status == "failed"
    assert batch.quotes == ()
    assert batch.reject_code is None
    assert batch.reason is not None


def test_results_follow_request_order() -> None:
    batch = assess_quotes([TPEX, TSMC], _response(_row(), _row(TPEX)), _no_sentinel())
    assert [q.symbol for q in batch.quotes] == ["5483", "2330"]


# ---------------------------------------------------------------------------
# Batch-level codes
# ---------------------------------------------------------------------------


def _assert_whole_batch_rejected(
    batch: Any, code: QuoteRejectCode, status: str, keys: list[QuoteKey]
) -> None:
    assert batch.status == status
    assert batch.quotes == ()
    assert batch.reject_code == code
    assert batch.reason
    assert [(r.symbol, r.board, r.code) for r in batch.rejections] == [
        (k.symbol, k.board, code) for k in keys
    ]


def test_batch_blocked() -> None:
    response = _response(transport="blocked", rtcode=None, server_time=None, detail="HTTP 302")
    batch = assess_quotes([TSMC, TPEX], response)
    _assert_whole_batch_rejected(batch, QuoteRejectCode.BATCH_BLOCKED, "blocked", [TSMC, TPEX])
    assert batch.reason == "HTTP 302"


def test_batch_failed() -> None:
    response = _response(transport="failed", rtcode=None, server_time=None, detail="timeout")
    batch = assess_quotes([TSMC], response)
    _assert_whole_batch_rejected(batch, QuoteRejectCode.BATCH_FAILED, "failed", [TSMC])
    assert batch.reason == "timeout"


def test_batch_blocked_and_failed_have_default_details() -> None:
    blocked = assess_quotes([TSMC], _response(transport="blocked"))
    failed = assess_quotes([TSMC], _response(transport="failed"))
    assert blocked.reason == "source refused the request"
    assert failed.reason == "request failed"


@pytest.mark.parametrize("rtcode", ["9999", "", None])
def test_rtcode_not_ok(rtcode: str | None) -> None:
    batch = assess_quotes([TSMC], _response(_row(), rtcode=rtcode))
    _assert_whole_batch_rejected(batch, QuoteRejectCode.RTCODE_NOT_OK, "blocked", [TSMC])


def test_server_time_missing_is_fail_closed() -> None:
    batch = assess_quotes([TSMC], _response(_row(), server_time=None))
    _assert_whole_batch_rejected(batch, QuoteRejectCode.SERVER_TIME_MISSING, "failed", [TSMC])


@pytest.mark.parametrize("offset_s", [61, -61])
def test_clock_skew_in_either_direction(offset_s: int) -> None:
    server_time = AS_OF + timedelta(seconds=offset_s)
    batch = assess_quotes([TSMC], _response(_row(), server_time=server_time))
    _assert_whole_batch_rejected(batch, QuoteRejectCode.CLOCK_SKEW, "failed", [TSMC])


@pytest.mark.parametrize("offset_s", [60, -60])
def test_clock_skew_exactly_at_tolerance_is_accepted(offset_s: int) -> None:
    server_time = AS_OF + timedelta(seconds=offset_s)
    row = _row(quote_time=server_time - timedelta(seconds=1))
    batch = assess_quotes([TSMC], _response(row, server_time=server_time))
    assert batch.status == "ok"


def test_feed_lagging_from_the_sentinel() -> None:
    stale = _row(quote_time=AS_OF - timedelta(seconds=121))
    batch = assess_quotes([TSMC], _response(stale))
    _assert_whole_batch_rejected(batch, QuoteRejectCode.FEED_LAGGING, "failed", [TSMC])


def test_feed_lagging_rejects_other_channels_too() -> None:
    stale_sentinel = _row(TSMC, quote_time=AS_OF - timedelta(seconds=300))
    batch = assess_quotes([TPEX], _response(stale_sentinel, _row(TPEX)))
    _assert_whole_batch_rejected(batch, QuoteRejectCode.FEED_LAGGING, "failed", [TPEX])


def test_feed_lag_exactly_at_threshold_is_accepted() -> None:
    row = _row(quote_time=AS_OF - timedelta(seconds=120))
    assert assess_quotes([TSMC], _response(row)).status == "ok"


def test_sentinel_not_in_response_cannot_be_measured() -> None:
    batch = assess_quotes([TPEX], _response(_row(TPEX)))
    assert batch.status == "ok"


def test_sentinel_without_a_trade_cannot_be_measured() -> None:
    batch = assess_quotes([TSMC, TPEX], _response(_row(TSMC, last_price=None), _row(TPEX)))
    assert batch.reject_code is None
    assert [q.symbol for q in batch.quotes] == ["5483"]
    assert [r.code for r in batch.rejections] == [QuoteRejectCode.NO_TRADE]


def test_sentinel_from_another_day_is_not_feed_lag() -> None:
    """A holiday morning must surface as not_today, not as a stalled feed."""
    old = datetime(2026, 10, 2, 13, 30, tzinfo=TAIPEI)
    batch = assess_quotes([TSMC], _response(_row(trade_date=date(2026, 10, 2), quote_time=old)))
    assert batch.reject_code is None
    assert [r.code for r in batch.rejections] == [QuoteRejectCode.NOT_TODAY]


def test_sentinel_without_quote_time_cannot_be_measured() -> None:
    batch = assess_quotes([TSMC], _response(_row(quote_time=None)))
    assert [r.code for r in batch.rejections] == [QuoteRejectCode.QUOTE_TIME_MISSING]


def test_sentinel_can_be_disabled() -> None:
    stale = _row(quote_time=AS_OF - timedelta(seconds=900))
    batch = assess_quotes([TSMC], _response(stale), _no_sentinel())
    assert batch.status == "ok"


def test_last_trade_age_is_not_a_rejection_reason() -> None:
    """A thin stock that last traded an hour ago is still accepted (only disclosed)."""
    thin = _row(TPEX, quote_time=AS_OF - timedelta(hours=1))
    batch = assess_quotes([TPEX], _response(thin), _no_sentinel())
    assert batch.status == "ok"
    assert batch.quotes[0].quote_time == AS_OF - timedelta(hours=1)


def test_batch_checks_run_before_per_symbol_checks() -> None:
    batch = assess_quotes([TSMC], _response(_row(last_price=None), rtcode="1"))
    assert batch.reject_code == QuoteRejectCode.RTCODE_NOT_OK


def test_transport_failure_takes_precedence_over_rtcode() -> None:
    batch = assess_quotes([TSMC], _response(transport="blocked", rtcode="1"))
    assert batch.reject_code == QuoteRejectCode.BATCH_BLOCKED


# ---------------------------------------------------------------------------
# Per-symbol codes (table driven)
# ---------------------------------------------------------------------------

PER_SYMBOL_CASES: list[tuple[str, QuoteRejectCode, dict[str, Any]]] = [
    ("code_mismatch", QuoteRejectCode.CODE_MISMATCH, {"symbol": "2317"}),
    ("board_mismatch_otc", QuoteRejectCode.BOARD_MISMATCH, {"board": "otc"}),
    ("board_mismatch_unknown", QuoteRejectCode.BOARD_MISMATCH, {"board": None}),
    ("no_trade_none", QuoteRejectCode.NO_TRADE, {"last_price": None}),
    ("price_zero", QuoteRejectCode.PRICE_NON_POSITIVE, {"last_price": Decimal("0")}),
    ("price_negative", QuoteRejectCode.PRICE_NON_POSITIVE, {"last_price": Decimal("-3")}),
    ("quote_time_missing", QuoteRejectCode.QUOTE_TIME_MISSING, {"quote_time": None}),
    ("trade_date_missing", QuoteRejectCode.QUOTE_TIME_MISSING, {"trade_date": None}),
    ("trial_match", QuoteRejectCode.TRIAL_MATCH, {"is_trial_match": True}),
    ("not_today_trade_date", QuoteRejectCode.NOT_TODAY, {"trade_date": date(2026, 10, 2)}),
    (
        "not_today_quote_time",
        QuoteRejectCode.NOT_TODAY,
        {"quote_time": datetime(2026, 10, 2, 13, 30, tzinfo=TAIPEI)},
    ),
    (
        "future_quote_time",
        QuoteRejectCode.FUTURE_QUOTE_TIME,
        {"quote_time": SERVER_TIME + timedelta(seconds=6)},
    ),
    ("above_limit_up", QuoteRejectCode.OUTSIDE_PRICE_LIMITS, {"limit_up": Decimal("1049.5")}),
    ("below_limit_down", QuoteRejectCode.OUTSIDE_PRICE_LIMITS, {"limit_down": Decimal("1050.5")}),
    (
        "implausible_up",
        QuoteRejectCode.IMPLAUSIBLE_MOVE,
        {"last_price": Decimal("1561"), "prev_close": Decimal("1040")},
    ),
    (
        "implausible_down",
        QuoteRejectCode.IMPLAUSIBLE_MOVE,
        {"last_price": Decimal("519"), "prev_close": Decimal("1040")},
    ),
]


@pytest.mark.parametrize(
    ("code", "overrides"),
    [(c, o) for _, c, o in PER_SYMBOL_CASES],
    ids=[n for n, _, _ in PER_SYMBOL_CASES],
)
def test_per_symbol_rejection(code: QuoteRejectCode, overrides: dict[str, Any]) -> None:
    batch = assess_quotes([TSMC], _response(_row(**overrides)), _no_sentinel())
    assert batch.status == "failed"
    assert batch.quotes == ()
    assert batch.reject_code is None
    (rejection,) = batch.rejections
    assert rejection.code == code
    assert (rejection.symbol, rejection.board) == ("2330", "tse")
    assert rejection.detail


def test_symbol_missing() -> None:
    batch = assess_quotes([TSMC, TPEX], _response(_row()), _no_sentinel())
    assert batch.status == "partial"
    (rejection,) = batch.rejections
    assert (rejection.symbol, rejection.board, rejection.code) == (
        "5483",
        "otc",
        QuoteRejectCode.SYMBOL_MISSING,
    )


def test_symbol_missing_when_msg_array_is_empty() -> None:
    batch = assess_quotes([TSMC, TPEX], _response(), _no_sentinel())
    assert batch.status == "failed"
    assert {r.code for r in batch.rejections} == {QuoteRejectCode.SYMBOL_MISSING}
    assert len(batch.rejections) == 2


def test_duplicate_row_rejects_the_channel_rather_than_picking_one() -> None:
    batch = assess_quotes(
        [TSMC],
        _response(_row(), _row(last_price=Decimal("1060"))),
        _no_sentinel(),
    )
    assert batch.quotes == ()
    assert [r.code for r in batch.rejections] == [QuoteRejectCode.DUPLICATE_ROW]


def test_row_answering_an_unrequested_channel_is_reported_not_dropped() -> None:
    batch = assess_quotes([TSMC], _response(_row(), _row(TPEX)), _no_sentinel())
    assert len(batch.quotes) == 1
    assert batch.status == "partial"
    (rejection,) = batch.rejections
    assert rejection.code == QuoteRejectCode.CODE_MISMATCH
    assert (rejection.symbol, rejection.board) == ("5483", "otc")
    assert batch.reason is not None


def test_no_trade_never_falls_back_to_previous_close() -> None:
    """z='-' with a previous close present must yield no Quote at all."""
    row = _row(last_price=None, prev_close=Decimal("1040"))
    batch = assess_quotes([TSMC], _response(row), _no_sentinel())
    assert batch.quotes == ()
    assert [r.code for r in batch.rejections] == [QuoteRejectCode.NO_TRADE]


# Boundaries that must be accepted --------------------------------------------


def test_future_tolerance_boundary_is_accepted() -> None:
    row = _row(quote_time=SERVER_TIME + timedelta(seconds=5))
    assert assess_quotes([TSMC], _response(row), _no_sentinel()).status == "ok"


def test_price_exactly_on_a_limit_is_accepted() -> None:
    row = _row(limit_up=Decimal("1050"), limit_down=Decimal("1050"))
    assert assess_quotes([TSMC], _response(row), _no_sentinel()).status == "ok"


def test_only_one_limit_present_still_checks_that_side() -> None:
    ok = _row(limit_up=Decimal("1100"))
    bad = _row(limit_down=Decimal("1100"))
    assert assess_quotes([TSMC], _response(ok), _no_sentinel()).status == "ok"
    assert assess_quotes([TSMC], _response(bad), _no_sentinel()).status == "failed"


def test_limits_present_replace_the_loose_band() -> None:
    """With limits the band is not consulted: a 60% move inside the limits is accepted."""
    row = _row(
        last_price=Decimal("1664"),
        prev_close=Decimal("1040"),
        limit_up=Decimal("1700"),
        limit_down=Decimal("500"),
    )
    assert assess_quotes([TSMC], _response(row), _no_sentinel()).status == "ok"


def test_move_exactly_at_the_band_is_accepted() -> None:
    row = _row(last_price=Decimal("1560"), prev_close=Decimal("1040"))
    assert assess_quotes([TSMC], _response(row), _no_sentinel()).status == "ok"


@pytest.mark.parametrize("prev_close", [None, Decimal("0")])
def test_no_usable_previous_close_means_no_plausibility_verdict(prev_close: Decimal | None) -> None:
    row = _row(last_price=Decimal("99999"), prev_close=prev_close)
    assert assess_quotes([TSMC], _response(row), _no_sentinel()).status == "ok"


def test_trial_match_false_is_accepted() -> None:
    row = _row(is_trial_match=False)
    assert assess_quotes([TSMC], _response(row), _no_sentinel()).status == "ok"


def test_custom_thresholds_are_honoured() -> None:
    thresholds = QuoteQualityThresholds(implausible_move_band=Decimal("0.005"), sentinel=None)
    batch = assess_quotes([TSMC], _response(_row()), thresholds)
    assert [r.code for r in batch.rejections] == [QuoteRejectCode.IMPLAUSIBLE_MOVE]


# Order of checks ------------------------------------------------------------


def test_identity_is_judged_before_the_trade() -> None:
    row = _row(symbol="2317", last_price=None)
    batch = assess_quotes([TSMC], _response(row), _no_sentinel())
    assert batch.rejections[0].code == QuoteRejectCode.CODE_MISMATCH


def test_not_today_is_judged_before_future_and_limits() -> None:
    row = _row(
        trade_date=date(2026, 10, 2),
        quote_time=SERVER_TIME + timedelta(hours=1),
        limit_up=Decimal("1"),
    )
    batch = assess_quotes([TSMC], _response(row), _no_sentinel())
    assert batch.rejections[0].code == QuoteRejectCode.NOT_TODAY


# ---------------------------------------------------------------------------
# "Today" is the Taipei date, not the UTC date
# ---------------------------------------------------------------------------


def test_today_is_judged_on_the_taipei_calendar() -> None:
    """00:00:05 Taipei on 10/05 is still 10/04 in UTC; the Taipei date must win."""
    as_of = datetime(2026, 10, 4, 16, 0, 5, tzinfo=UTC)
    server_time = datetime(2026, 10, 5, 0, 0, 4, tzinfo=TAIPEI)
    trade = datetime(2026, 10, 5, 0, 0, 1, tzinfo=TAIPEI)
    good = _row(trade_date=date(2026, 10, 5), quote_time=trade)
    utc_dated = _row(trade_date=date(2026, 10, 4), quote_time=trade)
    ok = assess_quotes(
        [TSMC], _response(good, as_of=as_of, server_time=server_time), _no_sentinel()
    )
    bad = assess_quotes(
        [TSMC], _response(utc_dated, as_of=as_of, server_time=server_time), _no_sentinel()
    )
    assert ok.status == "ok"
    assert [r.code for r in bad.rejections] == [QuoteRejectCode.NOT_TODAY]


def test_quote_time_in_utc_is_converted_before_comparing_dates() -> None:
    """01:30 UTC on 10/05 is 09:30 Taipei on 10/05: same Taipei day."""
    quote_time = datetime(2026, 10, 5, 1, 30, tzinfo=UTC)
    row = _row(quote_time=quote_time)
    assert assess_quotes([TSMC], _response(row), _no_sentinel()).status == "ok"


# ---------------------------------------------------------------------------
# Raw input validation
# ---------------------------------------------------------------------------


def test_raw_inputs_reject_naive_datetimes() -> None:
    naive = datetime(2026, 10, 5, 10, 0, 0)
    with pytest.raises(ValueError, match="quote_time"):
        _row(quote_time=naive)
    with pytest.raises(ValueError, match="as_of"):
        _response(as_of=naive)
    with pytest.raises(ValueError, match="server_time"):
        _response(server_time=naive)
