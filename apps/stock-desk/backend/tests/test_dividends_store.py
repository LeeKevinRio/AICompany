"""SQLite store tests for 除權息 events: idempotence, Decimal fidelity, ranges."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from app.dividends.models import DividendEvent
from app.dividends.store import DividendEventStore

AS_OF = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
SYNCED_AT = datetime(2026, 8, 10, 13, 0, tzinfo=UTC)


def _event(
    symbol: str,
    day: date,
    *,
    previous_close: str | None = "102.00",
    reference_price: str | None = "99.00",
    cash: str = "3.00",
    rights: str = "0",
    stock_dividend_ratio: str | None = None,
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
        source="twse_openapi_dividend",
        as_of=AS_OF,
    )


def test_empty_store_reports_never_synced(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    assert store.count() == 0
    assert store.is_synced() is False
    assert store.last_synced_at() is None
    assert store.events_for("2330", "TW") == []


def test_upsert_is_idempotent_on_symbol_market_ex_date(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    events = [_event("2330", date(2024, 6, 17)), _event("2884", date(2024, 8, 1))]
    for _ in range(3):
        store.upsert(events, synced_at=SYNCED_AT)
    assert store.count() == 2


def test_reupsert_refreshes_the_row_in_place(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    store.upsert([_event("2330", date(2024, 6, 17), cash="3.00")], synced_at=SYNCED_AT)
    store.upsert(
        [_event("2330", date(2024, 6, 17), reference_price="98.00", cash="4.00")],
        synced_at=SYNCED_AT,
    )
    stored = store.events_for("2330", "TW")
    assert len(stored) == 1
    assert stored[0].cash_dividend == Decimal("4.00")
    assert stored[0].reference_price == Decimal("98.00")


def test_decimals_round_trip_exactly(tmp_path: Path) -> None:
    """Prices are stored as TEXT precisely so the factor is not rounded away."""
    store = DividendEventStore(db_path=tmp_path / "d.db")
    store.upsert(
        [_event("2884", date(2024, 8, 1), previous_close="26.55", reference_price="25.46")],
        synced_at=SYNCED_AT,
    )
    stored = store.events_for("2884", "TW")[0]
    assert stored.previous_close == Decimal("26.55")
    assert stored.reference_price == Decimal("25.46")
    assert stored.adjustment_factor == Decimal("25.46") / Decimal("26.55")


def test_null_reference_price_round_trips_as_none(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    store.upsert([_event("2330", date(2024, 6, 17), reference_price=None)], synced_at=SYNCED_AT)
    stored = store.events_for("2330", "TW")[0]
    assert stored.reference_price is None
    # Falls back to the component route rather than becoming unusable.
    assert stored.adjustment_factor == Decimal("99.00") / Decimal("102.00")


def test_events_are_returned_ascending_and_bounded_inclusively(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    days = [date(2024, 3, 1), date(2024, 6, 17), date(2024, 9, 1)]
    store.upsert([_event("2330", day) for day in reversed(days)], synced_at=SYNCED_AT)

    assert [event.ex_date for event in store.events_for("2330", "TW")] == days
    windowed = store.events_for(
        "2330", "TW", start=date(2024, 3, 1), end=date(2024, 6, 17)
    )
    assert [event.ex_date for event in windowed] == days[:2]


def test_events_are_scoped_by_symbol_and_market(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    store.upsert([_event("2330", date(2024, 6, 17))], synced_at=SYNCED_AT)
    assert store.events_for("2454", "TW") == []
    assert store.events_for("2330", "US") == []


def test_last_synced_at_reports_the_most_recent_run(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    store.upsert([_event("2330", date(2024, 6, 17))], synced_at=SYNCED_AT)
    later = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
    store.upsert([_event("2884", date(2024, 8, 1))], synced_at=later)
    assert store.last_synced_at() == later
    assert store.is_synced() is True


def test_upserting_nothing_writes_nothing(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    assert store.upsert([]) == 0
    assert store.count() == 0


def test_previous_close_round_trips_as_none_for_the_forecast_table_source(
    tmp_path: Path,
) -> None:
    """TWT48U_ALL rows never carry a previous_close at sync time -- confirm
    the column tolerates and round-trips that, not just reference_price."""
    store = DividendEventStore(db_path=tmp_path / "d.db")
    store.upsert(
        [_event("2330", date(2026, 8, 14), previous_close=None, reference_price=None)],
        synced_at=SYNCED_AT,
    )
    stored = store.events_for("2330", "TW")[0]
    assert stored.previous_close is None
    assert stored.adjustment_factor is None


def test_stock_dividend_ratio_round_trips_and_keeps_the_event_unusable(
    tmp_path: Path,
) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    store.upsert(
        [
            _event(
                "2884",
                date(2026, 8, 20),
                cash="0.61",
                stock_dividend_ratio="12.500000",
            )
        ],
        synced_at=SYNCED_AT,
    )
    stored = store.events_for("2884", "TW")[0]
    assert stored.stock_dividend_ratio == Decimal("12.500000")
    assert stored.adjustment_factor is None  # recorded, not computed -- see app.dividends.models


def test_a_preexisting_database_without_the_new_column_migrates_in_place(
    tmp_path: Path,
) -> None:
    """A local SQLite file synced before ``stock_dividend_ratio`` existed
    must gain the column on open, not error or silently drop the table."""
    db_path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            """
            CREATE TABLE dividend_events (
                symbol TEXT NOT NULL,
                market TEXT NOT NULL,
                ex_date TEXT NOT NULL,
                previous_close TEXT,
                reference_price TEXT,
                cash_dividend TEXT NOT NULL,
                rights_value TEXT NOT NULL,
                source TEXT NOT NULL,
                as_of TEXT NOT NULL,
                synced_at TEXT NOT NULL,
                PRIMARY KEY (symbol, market, ex_date)
            )
            """
        )
        conn.execute(
            "INSERT INTO dividend_events VALUES "
            "('2330', 'TW', '2026-08-14', '102.00', '99.00', '3.00', '0', "
            "'twse_openapi_dividend', ?, ?)",
            (AS_OF.isoformat(), SYNCED_AT.isoformat()),
        )

    store = DividendEventStore(db_path=db_path)
    stored = store.events_for("2330", "TW")[0]
    assert stored.stock_dividend_ratio is None
    assert stored.cash_dividend == Decimal("3.00")
    store.upsert(
        [_event("2884", date(2026, 8, 20), stock_dividend_ratio="12.50")], synced_at=SYNCED_AT
    )
    assert store.events_for("2884", "TW")[0].stock_dividend_ratio == Decimal("12.50")
