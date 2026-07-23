"""Data quality checks for price bar series.

Per the skill and the project's red lines: this module only *detects* and
*reports* issues. It never silently drops, fixes, or interpolates data.
Callers decide what to do with the reported issues (e.g. surface them in
the API response, log them, refuse to render a chart).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from datetime import date as date_type
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.data.interface import PriceBar


class QualityIssueType(StrEnum):
    MISSING_TRADING_DAY = "missing_trading_day"
    DUPLICATE_ROW = "duplicate_row"
    CURRENCY_MISMATCH = "currency_mismatch"
    FUTURE_DATE = "future_date"
    OHLC_INVALID = "ohlc_invalid"


class QualityIssue(BaseModel):
    """One machine-readable data quality finding."""

    model_config = ConfigDict(frozen=True)

    issue_type: QualityIssueType
    symbol: str
    detail: str
    date: date_type | None = None


def check_price_bars(
    bars: Sequence[PriceBar],
    *,
    expected_currency: str | None = None,
    trading_calendar: Sequence[date_type] | None = None,
    reference_now: datetime | None = None,
) -> list[QualityIssue]:
    """Run every quality check against a series of bars and return all issues found.

    - ``expected_currency``: if given, flags any bar whose currency differs
      (catches e.g. a TWD bar accidentally tagged USD).
    - ``trading_calendar``: if given, the list of dates that were expected
      to have a bar; any date in it missing from ``bars`` is flagged.
    - ``reference_now``: "now" for the future-date check, defaults to
      ``datetime.now(UTC)``; tests should pass a fixed value.
    """
    issues: list[QualityIssue] = []
    issues.extend(_check_duplicates(bars))
    issues.extend(_check_future_dates(bars, reference_now))
    issues.extend(_check_currency(bars, expected_currency))
    issues.extend(_check_ohlc_consistency(bars))
    issues.extend(_check_missing_trading_days(bars, trading_calendar))
    return issues


def _check_duplicates(bars: Sequence[PriceBar]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    seen: set[tuple[str, date_type]] = set()
    for bar in bars:
        key = (bar.symbol, bar.date)
        if key in seen:
            issues.append(
                QualityIssue(
                    issue_type=QualityIssueType.DUPLICATE_ROW,
                    symbol=bar.symbol,
                    date=bar.date,
                    detail=f"duplicate bar for {bar.symbol} on {bar.date.isoformat()}",
                )
            )
        else:
            seen.add(key)
    return issues


def _check_future_dates(
    bars: Sequence[PriceBar], reference_now: datetime | None
) -> list[QualityIssue]:
    now = reference_now if reference_now is not None else datetime.now(UTC)
    today = now.date()
    issues: list[QualityIssue] = []
    for bar in bars:
        if bar.date > today:
            issues.append(
                QualityIssue(
                    issue_type=QualityIssueType.FUTURE_DATE,
                    symbol=bar.symbol,
                    date=bar.date,
                    detail=(
                        f"bar dated {bar.date.isoformat()} is after "
                        f"reference date {today.isoformat()}"
                    ),
                )
            )
    return issues


def _check_currency(
    bars: Sequence[PriceBar], expected_currency: str | None
) -> list[QualityIssue]:
    if expected_currency is None:
        return []
    issues: list[QualityIssue] = []
    for bar in bars:
        if bar.currency != expected_currency:
            issues.append(
                QualityIssue(
                    issue_type=QualityIssueType.CURRENCY_MISMATCH,
                    symbol=bar.symbol,
                    date=bar.date,
                    detail=(
                        f"bar currency {bar.currency!r} does not match "
                        f"expected {expected_currency!r}"
                    ),
                )
            )
    return issues


def _check_ohlc_consistency(bars: Sequence[PriceBar]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for bar in bars:
        invalid = (
            bar.high < bar.low
            or bar.high < bar.open
            or bar.high < bar.close
            or bar.low > bar.open
            or bar.low > bar.close
        )
        if invalid:
            issues.append(
                QualityIssue(
                    issue_type=QualityIssueType.OHLC_INVALID,
                    symbol=bar.symbol,
                    date=bar.date,
                    detail=(
                        f"OHLC out of order: open={bar.open} high={bar.high} "
                        f"low={bar.low} close={bar.close}"
                    ),
                )
            )
    return issues


def _check_missing_trading_days(
    bars: Sequence[PriceBar], trading_calendar: Sequence[date_type] | None
) -> list[QualityIssue]:
    if not trading_calendar:
        return []
    present = {bar.date for bar in bars}
    symbol = bars[0].symbol if bars else "unknown"
    issues: list[QualityIssue] = []
    for expected_date in trading_calendar:
        if expected_date not in present:
            issues.append(
                QualityIssue(
                    issue_type=QualityIssueType.MISSING_TRADING_DAY,
                    symbol=symbol,
                    date=expected_date,
                    detail=f"no bar found for expected trading day {expected_date.isoformat()}",
                )
            )
    return issues
