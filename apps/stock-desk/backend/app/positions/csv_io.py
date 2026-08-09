"""CSV template generation and import parsing for positions.

The import validates every row independently: a bad row is skipped and its
reason recorded, while good rows in the same file are still imported (the
caller decides how to surface the errors). Row numbers are 1-based including
the header, so the first data row is row 2.

All error ``reason`` strings are Traditional Chinese (Taiwan) and safe to show
to the user verbatim.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from app.positions.models import (
    INDEX_SYMBOL_PREFIX,
    INDEX_SYMBOL_REJECTED_MESSAGE,
    Currency,
    InstrumentType,
    Market,
    PositionInput,
)
from app.positions.sectors import (
    SECTOR_REJECTED_MESSAGE,
    SECTOR_US_REJECTED_MESSAGE,
    is_valid_sector,
)

#: Column order shared by the downloadable template and the import parser.
COLUMNS: tuple[str, ...] = (
    "symbol",
    "market",
    "quantity",
    "avg_cost",
    "currency",
    "opened_at",
    "instrument_type",
    "sector",
    "note",
)

#: Columns the header may omit. ``sector`` arrived with FR-12, after users had
#: already built files against the older template; demanding it would turn a
#: previously valid file into a header error over a field that is optional even
#: when present. A file without the column imports with every sector unstated.
_OPTIONAL_COLUMNS: frozenset[str] = frozenset({"sector"})

_MARKETS: frozenset[str] = frozenset({"TW", "US"})
_CURRENCIES: frozenset[str] = frozenset({"TWD", "USD"})
_INSTRUMENT_TYPES: frozenset[str] = frozenset(
    {"stock", "etf", "leveraged_etf", "futures_etf"}
)

#: Two illustrative rows shipped with the template (one TW, one US).
#: The US row leaves ``sector`` empty on purpose: the TWSE categories do not
#: apply to US holdings (AC-12.6), so the template must not demonstrate filling
#: one in.
_TEMPLATE_EXAMPLES: tuple[tuple[str, ...], ...] = (
    ("2330", "TW", "1000", "600.5", "TWD", "2024-01-02", "stock", "半導體業", "台積電"),
    ("AAPL", "US", "10", "180.25", "USD", "2024-03-15", "stock", "", "Apple"),
)


class RowError(BaseModel):
    """One field-level problem found while importing a CSV row."""

    row: int
    field: str
    reason: str


class ImportResult(BaseModel):
    """Outcome of a CSV import: how many rows were stored plus any row errors."""

    imported: int
    errors: list[RowError]


def build_template_csv() -> str:
    """Return the CSV template text: a header row plus two example rows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for example in _TEMPLATE_EXAMPLES:
        writer.writerow(example)
    return buffer.getvalue()


def parse_import_csv(
    text: str, *, reference_date: date | None = None
) -> tuple[list[PositionInput], list[RowError]]:
    """Parse import CSV text into valid positions and per-row errors.

    Returns ``(inputs, errors)`` where ``inputs`` are the rows that passed
    every field check (ready to store) and ``errors`` lists every field-level
    failure. A row appears in at most one of the two outputs.
    """
    today = reference_date if reference_date is not None else datetime.now(UTC).date()
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], [RowError(row=1, field="header", reason="CSV 檔案是空的")]

    header = [cell.strip() for cell in rows[0]]
    missing = [
        column
        for column in COLUMNS
        if column not in header and column not in _OPTIONAL_COLUMNS
    ]
    if missing:
        return [], [
            RowError(
                row=1,
                field="header",
                reason=f"CSV 標題列缺少必要欄位：{'、'.join(missing)}",
            )
        ]
    index_of = {column: header.index(column) for column in COLUMNS if column in header}

    inputs: list[PositionInput] = []
    errors: list[RowError] = []
    for offset, raw_row in enumerate(rows[1:]):
        row_number = offset + 2  # header is row 1, first data row is row 2
        if not any(cell.strip() for cell in raw_row):
            continue  # skip fully blank lines silently
        parsed, row_errors = _parse_row(raw_row, index_of, row_number, today)
        if parsed is not None:
            inputs.append(parsed)
        errors.extend(row_errors)
    return inputs, errors


def _cell(raw_row: list[str], index_of: dict[str, int], column: str) -> str:
    """One cell, or ``""`` when the row is short or the column is absent."""
    idx = index_of.get(column)
    if idx is None:
        return ""
    return raw_row[idx].strip() if idx < len(raw_row) else ""


def _parse_row(
    raw_row: list[str],
    index_of: dict[str, int],
    row_number: int,
    today: date,
) -> tuple[PositionInput | None, list[RowError]]:
    errors: list[RowError] = []

    def fail(field: str, reason: str) -> None:
        errors.append(RowError(row=row_number, field=field, reason=reason))

    symbol = _cell(raw_row, index_of, "symbol")
    if not symbol:
        fail("symbol", "股票代號不可空白")
    elif symbol.startswith(INDEX_SYMBOL_PREFIX):
        # Restated here rather than left to ``PositionInput``: this parser only
        # constructs the model once every field has passed, so a check missing
        # here would surface as an uncaught ValidationError (a 500 on
        # ``POST /api/positions/import``) instead of a per-row error the user
        # can act on.
        fail("symbol", INDEX_SYMBOL_REJECTED_MESSAGE)

    market = _cell(raw_row, index_of, "market")
    if market not in _MARKETS:
        fail("market", f"市場必須是 TW 或 US，收到「{market}」")

    quantity = _parse_positive_decimal(
        _cell(raw_row, index_of, "quantity"), "quantity", "數量", fail
    )

    avg_cost = _parse_positive_decimal(
        _cell(raw_row, index_of, "avg_cost"), "avg_cost", "平均成本", fail
    )

    currency = _cell(raw_row, index_of, "currency")
    if currency not in _CURRENCIES:
        fail("currency", f"幣別必須是 TWD 或 USD，收到「{currency}」")

    opened_at = _parse_opened_at(_cell(raw_row, index_of, "opened_at"), today, fail)

    instrument_type = _cell(raw_row, index_of, "instrument_type")
    if instrument_type not in _INSTRUMENT_TYPES:
        fail(
            "instrument_type",
            "商品類型必須是 stock、etf、leveraged_etf 或 futures_etf，"
            f"收到「{instrument_type}」",
        )

    sector = _parse_sector(_cell(raw_row, index_of, "sector"), market, fail)

    note_raw = _cell(raw_row, index_of, "note")
    note = note_raw or None

    if errors:
        return None, errors

    # Every field checked out; the enums are narrowed by the guards above.
    return (
        PositionInput(
            symbol=symbol,
            market=_as_market(market),
            quantity=quantity,  # type: ignore[arg-type]
            avg_cost=avg_cost,  # type: ignore[arg-type]
            currency=_as_currency(currency),
            opened_at=opened_at,
            instrument_type=_as_instrument_type(instrument_type),
            sector=sector,
            note=note,
        ),
        [],
    )


def _parse_positive_decimal(
    raw: str,
    field: str,
    label: str,
    fail: Callable[[str, str], None],
) -> Decimal | None:
    if not raw:
        fail(field, f"{label}不可空白")
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        fail(field, f"{label}必須是數字，收到「{raw}」")
        return None
    if value <= 0:
        fail(field, f"{label}必須大於 0")
        return None
    return value


def _parse_sector(
    raw: str, market: str, fail: Callable[[str, str], None]
) -> str | None:
    """Parse the optional industry category (FR-12).

    A blank cell means "not stated" and imports fine; anything outside the TWSE
    enumeration fails the row with the same sentence the API uses, and a US row
    carrying any category fails too (the taxonomy does not apply there).
    Returns ``None`` both for a blank cell and for a rejected value, which the
    caller tells apart by whether ``fail`` recorded an error for the row.
    """
    if not raw:
        return None
    if market == "US":
        fail("sector", SECTOR_US_REJECTED_MESSAGE)
        return None
    if not is_valid_sector(raw):
        fail("sector", f"{SECTOR_REJECTED_MESSAGE}收到「{raw}」。")
        return None
    return raw


def _parse_opened_at(
    raw: str, today: date, fail: Callable[[str, str], None]
) -> date | None:
    """Parse the optional open date; a blank cell means "not stated".

    Returns ``None`` both for a blank cell and for a rejected value, which the
    caller tells apart by whether ``fail`` recorded an error for the row.
    """
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        fail("opened_at", f"建倉日期格式必須是 YYYY-MM-DD，收到「{raw}」")
        return None
    if parsed > today:
        fail("opened_at", "建倉日期不可晚於今天")
        return None
    return parsed


def _as_market(value: str) -> Market:
    assert value in _MARKETS
    return value  # type: ignore[return-value]


def _as_currency(value: str) -> Currency:
    assert value in _CURRENCIES
    return value  # type: ignore[return-value]


def _as_instrument_type(value: str) -> InstrumentType:
    assert value in _INSTRUMENT_TYPES
    return value  # type: ignore[return-value]
