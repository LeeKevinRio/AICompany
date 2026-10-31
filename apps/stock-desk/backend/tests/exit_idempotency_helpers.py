"""Builders shared by the N-166 EMERGENCY_EXIT repeat tests (ADR-0033).

Offline and dated: both ladders are :class:`tests.api_helpers.FakePriceService`
instances seeded with flat series that end after every day the tests submit on,
and every call passes ``today`` explicitly. Everything here is importable from a
spawned process, so the process race test builds its books with it too.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.playbook import wording
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService, recent_bars

#: The seeded series end on this Friday; every submission day is before it.
SERIES_END = date(2026, 8, 14)
HISTORY = 40
TUESDAY = date(2026, 8, 11)
WEDNESDAY = date(2026, 8, 12)
THURSDAY = date(2026, 8, 13)
FREEZE_DAYS = 20

#: The two held batches most tests start from: (symbol, batch_no, shares, close).
HELD: tuple[tuple[str, int, int, float], ...] = (("2330", 1, 300, 100.0), ("2454", 1, 200, 50.0))


@dataclass
class Book:
    service: PlaybookService
    store: PlaybookStore
    prices: FakePriceService
    index: FakePriceService


def fakes() -> tuple[FakePriceService, FakePriceService]:
    prices = FakePriceService()
    for symbol, _, _, close in HELD:
        prices.seed(symbol, recent_bars([close] * HISTORY, symbol=symbol, end=SERIES_END))
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    return prices, index


def open_book(
    db_path: Path,
    *,
    prices: FakePriceService | None = None,
    index: FakePriceService | None = None,
) -> Book:
    """A store and a service on ``db_path``; seeds nothing."""
    default_prices, default_index = fakes()
    prices = prices or default_prices
    index = index or default_index
    store = PlaybookStore(db_path=db_path)
    return Book(
        service=PlaybookService(
            store=store,
            market_resolver={"TW": prices},
            index_resolver={"TW": index, "US": index},
        ),
        store=store,
        prices=prices,
        index=index,
    )


def hold(
    store: PlaybookStore,
    symbol: str,
    batch_no: int,
    *,
    shares: int,
    remaining: int | None = None,
) -> None:
    """Make ``(symbol, batch_no)`` an open batch holding ``remaining`` shares."""
    store.ensure_batches([symbol], batches_per_target=3)
    batch = store.get_batch(symbol, batch_no)
    assert batch is not None
    store.save_batch(
        batch.model_copy(
            update={
                "status": "open",
                "entry_date": date(2026, 7, 1),
                "cost": Decimal("100"),
                "shares": shares,
                "remaining_shares": shares if remaining is None else remaining,
                "peak_close": Decimal("100"),
            }
        )
    )


def hold_both(store: PlaybookStore) -> None:
    for symbol, batch_no, shares, _ in HELD:
        hold(store, symbol, batch_no, shares=shares)


def seed_held_book(db_path: Path) -> None:
    """The database every race test starts from: both batches held, no exit yet."""
    hold_both(PlaybookStore(db_path=db_path))


def weekdays_after(day: date, count: int) -> date:
    """``count`` weekdays after ``day`` -- the calendar's forward fallback.

    Every day a freeze count walks is after the last loaded bar, so the calendar
    answers from its documented weekday rule. Restated here so the expectation
    is an independent count, not the production calendar checking itself.
    """
    cursor = day
    remaining = count
    while remaining:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            remaining -= 1
    return cursor


def until_for(day: date) -> date:
    return weekdays_after(day, FREEZE_DAYS)


def emergency_rows(db_path: Path) -> list[tuple[str, int, int, str, int]]:
    """``(symbol, batch_no, shares, execution_date, settled)`` of every EMERGENCY line."""
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT symbol, batch_no, shares, execution_date, settled FROM playbook_directives "
            "WHERE rule_id = 'EMERGENCY' ORDER BY id"
        ).fetchall()
    return [(str(a), int(b), int(c), str(d), int(e)) for a, b, c, d, e in rows]


def unsettled_per_batch(db_path: Path) -> dict[tuple[str, int], int]:
    counts: dict[tuple[str, int], int] = {}
    for symbol, batch_no, _, _, settled in emergency_rows(db_path):
        if not settled:
            counts[(symbol, batch_no)] = counts.get((symbol, batch_no), 0) + 1
    return counts


def state_map(db_path: Path) -> dict[str, str]:
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("SELECT key, value FROM playbook_state").fetchall()
    return {str(key): str(value) for key, value in rows}


def already_pending_message(
    *,
    batches: int,
    shares: int,
    execution_dates: str,
    executed_at: date,
    until: date,
) -> str:
    """S1 formatted by hand from the constant, for exact-equality assertions."""
    return wording.EMERGENCY_EXIT_ALREADY_PENDING.format(
        pending_batches=batches,
        pending_shares=shares,
        pending_execution_dates=execution_dates,
        executed_at=executed_at.isoformat(),
        freeze_days=FREEZE_DAYS,
        until=until.isoformat(),
    )


def extended_note(*, previous: date, until: date, executed_at: date) -> str:
    return wording.EMERGENCY_EXIT_FREEZE_EXTENDED_NOTE.format(
        previous_until=previous.isoformat(),
        until=until.isoformat(),
        executed_at=executed_at.isoformat(),
    )
