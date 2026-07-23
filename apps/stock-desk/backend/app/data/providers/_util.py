"""Small parsing helpers shared by the TWSE and TPEx adapters.

Both exchanges' legacy JSON APIs report dates on the ROC (Minguo) calendar
and numbers with thousands separators and "--" placeholders for no-trade
rows, so the parsing quirks are centralized here instead of duplicated.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal, InvalidOperation

ROC_YEAR_OFFSET = 1911

#: Placeholder values the TWSE/TPEx APIs use for "no trade happened" cells.
_NO_TRADE_PLACEHOLDERS = {"--", "---", "----", "", "N/A"}


class UnparseableRowError(ValueError):
    """Raised when a data row cannot be parsed and must be skipped, not guessed."""


def parse_roc_date(value: str) -> date:
    """Parse a "113/01/02"-style ROC calendar date string into a Gregorian date."""
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise UnparseableRowError(f"unrecognized ROC date format: {value!r}")
    roc_year, month, day = parts
    try:
        year = int(roc_year) + ROC_YEAR_OFFSET
        return date(year, int(month), int(day))
    except ValueError as exc:
        raise UnparseableRowError(f"unrecognized ROC date format: {value!r}") from exc


def parse_decimal_cell(value: str) -> Decimal:
    """Parse a numeric cell that may contain thousands separators or a no-trade placeholder."""
    cleaned = value.strip().replace(",", "")
    if cleaned in _NO_TRADE_PLACEHOLDERS:
        raise UnparseableRowError(f"no-trade placeholder cell: {value!r}")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise UnparseableRowError(f"unparseable numeric cell: {value!r}") from exc


def parse_int_cell(value: str) -> int:
    """Parse an integer cell (e.g. volume) that may contain thousands separators."""
    cleaned = value.strip().replace(",", "")
    if cleaned in _NO_TRADE_PLACEHOLDERS:
        raise UnparseableRowError(f"no-trade placeholder cell: {value!r}")
    try:
        return int(cleaned)
    except ValueError as exc:
        raise UnparseableRowError(f"unparseable integer cell: {value!r}") from exc


def iter_month_starts(start: date, end: date) -> Iterator[date]:
    """Yield the first-of-month date for every calendar month in [start, end]."""
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield date(year, month, 1)
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
