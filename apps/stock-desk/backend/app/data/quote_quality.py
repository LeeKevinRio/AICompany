"""Pure quality gate for intraday quotes (ADR-0014 D-10).

An adapter parses one MIS response into a :class:`RawQuoteResponse` (values
exactly as received, nothing judged); :func:`assess_quotes` turns it into a
``QuoteBatch`` of accepted ``Quote`` objects plus a ``QuoteRejection`` for every
requested channel that did not make it. Nothing here reads a clock, does I/O or
logs: ``as_of`` arrives with the response and every threshold is an argument,
so each rule is testable with a literal timestamp.

Red lines this module enforces:

* **Never substitute a price.** A row without a trade (``z`` of ``"-"``), with a
  non-positive price or failing any check is rejected; the previous close,
  open, bid/ask are never promoted to a trade price, nothing is interpolated.
* **Never drop silently.** Every requested channel ends up either as a
  ``Quote`` or as a ``QuoteRejection``; a response row that answers no
  requested channel is itself reported.
* **"Last trade is old" is not a rejection.** A thinly traded stock may
  legitimately not have traded for an hour. Only a stalled *feed* (judged from
  the sentinel channel, P-13) rejects.

Rejection order, per requested channel, is fixed so that the reported code is
the most fundamental problem: identity (``symbol_missing``, ``duplicate_row``,
``code_mismatch``, ``board_mismatch``), then the trade itself (``no_trade``,
``price_non_positive``, ``quote_time_missing``, ``trial_match``), then time
(``not_today``, ``future_quote_time``), then price plausibility
(``outside_price_limits`` or, when the source reports no limits,
``implausible_move``). The service-layer codes (``board_unknown``,
``board_ambiguous``, ``demo_series``, ``source_cooldown``,
``throttled_no_cache``) are not produced here.

All thresholds default to the pre-measurement values in
``app.data.quote_params`` (pending 10/05 field verification).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Final, Literal
from zoneinfo import ZoneInfo

from app.data.interface import (
    Board,
    Quote,
    QuoteBatch,
    QuoteKey,
    QuoteRejectCode,
    QuoteRejection,
)
from app.data.quote_params import (
    CLOCK_SKEW_TOLERANCE,
    FEED_LAG_THRESHOLD,
    FUTURE_QUOTE_TOLERANCE,
    IMPLAUSIBLE_MOVE_BAND,
    SENTINEL_KEY,
)

TAIPEI: Final = ZoneInfo("Asia/Taipei")

#: The only ``rtcode`` MIS uses for a successful answer (per the verification
#: script's contract); anything else is a refusal.
RTCODE_OK: Final = "0000"

Transport = Literal["ok", "blocked", "failed"]


@dataclass(frozen=True)
class QuoteQualityThresholds:
    """Every tunable the gate uses; defaults are the ADR-0014 P-table values."""

    #: P-4 (pending 10/05 field verification).
    clock_skew_tolerance: timedelta = CLOCK_SKEW_TOLERANCE
    #: P-5 (pending 10/05 field verification).
    future_tolerance: timedelta = FUTURE_QUOTE_TOLERANCE
    #: P-3 (pending 10/05 field verification).
    feed_lag_threshold: timedelta = FEED_LAG_THRESHOLD
    #: P-12 (pending 10/05 field verification).
    implausible_move_band: Decimal = IMPLAUSIBLE_MOVE_BAND
    #: P-13 (pending 10/05 field verification). ``None`` disables the
    #: stalled-feed check.
    sentinel: QuoteKey | None = SENTINEL_KEY


DEFAULT_THRESHOLDS: Final = QuoteQualityThresholds()


@dataclass(frozen=True)
class RawQuoteRow:
    """One response row as parsed, before any judgement.

    ``requested`` is the channel this row answers (the adapter attributes it);
    ``symbol`` and ``board`` are what the row itself claims to be (MIS ``c`` and
    ``ex``), so a mismatch between the two is detectable. ``last_price`` is
    ``None`` when the source reported no trade (``z`` of ``"-"`` or empty).
    """

    requested: QuoteKey
    symbol: str
    board: Board | None
    last_price: Decimal | None
    prev_close: Decimal | None = None
    limit_up: Decimal | None = None
    limit_down: Decimal | None = None
    #: Exchange-local trade date (MIS ``d``), ``None`` when absent.
    trade_date: date | None = None
    #: Last-trade time (MIS ``tlong``), timezone-aware, ``None`` when absent.
    quote_time: datetime | None = None
    #: ``True``/``False`` once a trial-match flag is known to exist in the
    #: feed (unverified: pending 10/05 field verification); ``None`` = the feed
    #: has no such flag, so nothing can be concluded.
    is_trial_match: bool | None = None

    def __post_init__(self) -> None:
        if self.quote_time is not None and self.quote_time.tzinfo is None:
            raise ValueError("quote_time must be timezone-aware")


@dataclass(frozen=True)
class RawQuoteResponse:
    """One whole response, as received.

    ``transport`` is the adapter's HTTP-level verdict: ``blocked`` for a refusal
    (non-200, redirect, non-JSON), ``failed`` for a network error or timeout.
    ``as_of`` is when the adapter retrieved the response (from its injected
    clock).
    """

    transport: Transport
    as_of: datetime
    source: str
    rtcode: str | None = None
    server_time: datetime | None = None
    rows: tuple[RawQuoteRow, ...] = ()
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        if self.server_time is not None and self.server_time.tzinfo is None:
            raise ValueError("server_time must be timezone-aware")


def assess_quotes(
    keys: Sequence[QuoteKey],
    response: RawQuoteResponse,
    thresholds: QuoteQualityThresholds = DEFAULT_THRESHOLDS,
) -> QuoteBatch:
    """Judge ``response`` against the requested ``keys``.

    Duplicate requested keys are collapsed (first occurrence wins). An empty
    request is an ``ok`` batch with nothing in it.
    """
    requested = tuple(dict.fromkeys(keys))
    if not requested:
        return QuoteBatch(
            quotes=(),
            rejections=(),
            status="ok",
            as_of=response.as_of,
            source=response.source,
        )

    batch_code, batch_detail = _batch_rejection(response, thresholds)
    if batch_code is not None:
        return _reject_whole_batch(requested, response, batch_code, batch_detail)

    # ``_batch_rejection`` guarantees a server time past this point.
    server_time = response.server_time
    assert server_time is not None
    today = response.as_of.astimezone(TAIPEI).date()
    quotes: list[Quote] = []
    rejections: list[QuoteRejection] = []

    rows_by_key: dict[QuoteKey, list[RawQuoteRow]] = {key: [] for key in requested}
    for row in response.rows:
        bucket = rows_by_key.get(row.requested)
        if bucket is None:
            # A row that answers nothing we asked for is an adapter or source
            # fault; surface it instead of dropping it.
            rejections.append(
                QuoteRejection(
                    symbol=row.symbol,
                    board=row.board,
                    code=QuoteRejectCode.CODE_MISMATCH,
                    detail=(
                        f"row for {row.requested.board}_{row.requested.symbol} "
                        "answers no requested channel"
                    ),
                )
            )
        else:
            bucket.append(row)

    for key in requested:
        outcome = _assess_key(key, rows_by_key[key], response, server_time, today, thresholds)
        if isinstance(outcome, Quote):
            quotes.append(outcome)
        else:
            rejections.append(outcome)

    accepted = len(quotes)
    status: Literal["ok", "partial", "failed"]
    reason: str | None
    if accepted == len(requested) and not rejections:
        status, reason = "ok", None
    elif accepted == 0:
        status, reason = "failed", "no requested channel passed the quality checks"
    elif accepted == len(requested):
        status, reason = "partial", "response also held rows for channels that were not requested"
    else:
        status = "partial"
        reason = f"{len(requested) - accepted} of {len(requested)} requested channels rejected"
    return QuoteBatch(
        quotes=tuple(quotes),
        rejections=tuple(rejections),
        status=status,
        as_of=response.as_of,
        source=response.source,
        reason=reason,
    )


def _batch_rejection(
    response: RawQuoteResponse, thresholds: QuoteQualityThresholds
) -> tuple[QuoteRejectCode | None, str]:
    """The first batch-level problem, or ``(None, "")``."""
    if response.transport == "blocked":
        return QuoteRejectCode.BATCH_BLOCKED, response.detail or "source refused the request"
    if response.transport == "failed":
        return QuoteRejectCode.BATCH_FAILED, response.detail or "request failed"
    if response.rtcode != RTCODE_OK:
        return QuoteRejectCode.RTCODE_NOT_OK, f"rtcode={response.rtcode!r}, expected {RTCODE_OK!r}"
    # Fail closed until the field verification shows ``queryTime`` is reliably
    # present: without the source's own clock neither skew nor future-dated
    # trades can be judged.
    if response.server_time is None:
        return QuoteRejectCode.SERVER_TIME_MISSING, "response carries no server time"
    skew = abs(response.as_of - response.server_time)
    if skew > thresholds.clock_skew_tolerance:
        return (
            QuoteRejectCode.CLOCK_SKEW,
            f"|as_of - server_time| = {skew.total_seconds():.0f}s exceeds "
            f"{thresholds.clock_skew_tolerance.total_seconds():.0f}s",
        )
    lag = _sentinel_lag(response, thresholds)
    if lag is not None and lag > thresholds.feed_lag_threshold:
        return (
            QuoteRejectCode.FEED_LAGGING,
            f"sentinel last trade is {lag.total_seconds():.0f}s old, limit "
            f"{thresholds.feed_lag_threshold.total_seconds():.0f}s",
        )
    return None, ""


def _sentinel_lag(
    response: RawQuoteResponse, thresholds: QuoteQualityThresholds
) -> timedelta | None:
    """Age of the sentinel's last trade, or ``None`` when it cannot be measured.

    Not measurable (so never a rejection) when the sentinel is disabled, absent
    from the response, shows no trade, or last traded on another day: the last
    case is a holiday or a pre-open morning, which the per-symbol ``not_today``
    check reports honestly, not a stalled feed.
    """
    sentinel = thresholds.sentinel
    if sentinel is None:
        return None
    today = response.as_of.astimezone(TAIPEI).date()
    for row in response.rows:
        if row.requested != sentinel:
            continue
        if row.last_price is None or row.quote_time is None or row.trade_date != today:
            return None
        return response.as_of - row.quote_time
    return None


def _reject_whole_batch(
    requested: tuple[QuoteKey, ...],
    response: RawQuoteResponse,
    code: QuoteRejectCode,
    detail: str,
) -> QuoteBatch:
    blocking = code in (QuoteRejectCode.BATCH_BLOCKED, QuoteRejectCode.RTCODE_NOT_OK)
    return QuoteBatch(
        quotes=(),
        rejections=tuple(
            QuoteRejection(symbol=key.symbol, board=key.board, code=code, detail=detail)
            for key in requested
        ),
        status="blocked" if blocking else "failed",
        as_of=response.as_of,
        source=response.source,
        reason=detail,
        reject_code=code,
    )


def _assess_key(
    key: QuoteKey,
    rows: list[RawQuoteRow],
    response: RawQuoteResponse,
    server_time: datetime,
    today: date,
    thresholds: QuoteQualityThresholds,
) -> Quote | QuoteRejection:
    def reject(code: QuoteRejectCode, detail: str) -> QuoteRejection:
        return QuoteRejection(symbol=key.symbol, board=key.board, code=code, detail=detail)

    if not rows:
        return reject(QuoteRejectCode.SYMBOL_MISSING, "no row in the response for this channel")
    if len(rows) > 1:
        return reject(
            QuoteRejectCode.DUPLICATE_ROW, f"{len(rows)} rows answer this channel; ambiguous"
        )
    row = rows[0]
    if row.symbol != key.symbol:
        return reject(
            QuoteRejectCode.CODE_MISMATCH,
            f"requested {key.symbol!r}, row says {row.symbol!r}",
        )
    if row.board != key.board:
        return reject(
            QuoteRejectCode.BOARD_MISMATCH,
            f"requested board {key.board!r}, row says {row.board!r}",
        )
    price = row.last_price
    if price is None:
        return reject(QuoteRejectCode.NO_TRADE, "no last trade price (dash or empty)")
    if not price > 0:
        return reject(QuoteRejectCode.PRICE_NON_POSITIVE, f"last trade price is {price}")
    if row.trade_date is None or row.quote_time is None:
        return reject(
            QuoteRejectCode.QUOTE_TIME_MISSING, "row lacks its trade date or last-trade time"
        )
    if row.is_trial_match is True:
        return reject(QuoteRejectCode.TRIAL_MATCH, "row is flagged as a simulated match")
    quote_day = row.quote_time.astimezone(TAIPEI).date()
    if row.trade_date != today or quote_day != today:
        return reject(
            QuoteRejectCode.NOT_TODAY,
            f"trade_date={row.trade_date}, quote_time date={quote_day}, today={today}",
        )
    if row.quote_time > server_time + thresholds.future_tolerance:
        return reject(
            QuoteRejectCode.FUTURE_QUOTE_TIME,
            f"quote_time {row.quote_time.isoformat()} is ahead of server_time "
            f"{server_time.isoformat()}",
        )
    limit_problem = _price_limit_problem(price, row, thresholds)
    if limit_problem is not None:
        return reject(*limit_problem)
    return Quote(
        symbol=key.symbol,
        board=key.board,
        currency="TWD",
        price=price,
        prev_close=row.prev_close,
        limit_up=row.limit_up,
        limit_down=row.limit_down,
        trade_date=row.trade_date,
        quote_time=row.quote_time,
        server_time=server_time,
        as_of=response.as_of,
        source=response.source,
    )


def _price_limit_problem(
    price: Decimal, row: RawQuoteRow, thresholds: QuoteQualityThresholds
) -> tuple[QuoteRejectCode, str] | None:
    """Reject a price outside the reported limits, else (no limits) outside the wide band."""
    if row.limit_up is not None or row.limit_down is not None:
        if row.limit_up is not None and price > row.limit_up:
            return QuoteRejectCode.OUTSIDE_PRICE_LIMITS, f"{price} above limit up {row.limit_up}"
        if row.limit_down is not None and price < row.limit_down:
            return (
                QuoteRejectCode.OUTSIDE_PRICE_LIMITS,
                f"{price} below limit down {row.limit_down}",
            )
        return None
    # No limit fields: fall back to the loose band against the previous close.
    # Without a usable previous close nothing can be concluded, so accept.
    if row.prev_close is not None and row.prev_close > 0:
        move = abs(price / row.prev_close - 1)
        if move > thresholds.implausible_move_band:
            return (
                QuoteRejectCode.IMPLAUSIBLE_MOVE,
                f"{price} is {move:.1%} from previous close {row.prev_close}, "
                f"band {thresholds.implausible_move_band:.0%}",
            )
    return None
