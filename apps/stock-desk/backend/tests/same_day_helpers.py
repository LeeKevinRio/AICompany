"""Builders shared by the N-172a same-day idempotency tests (ADR-0035).

Offline and dated like ``tests/exit_idempotency_helpers.py``: both ladders are
:class:`tests.api_helpers.FakePriceService` instances, which filter by the
requested ``end`` (= ``today``), so "the bar for T has not arrived yet" is staged
by seeding a series capped before it. Every call passes ``today`` explicitly,
or goes through :class:`ClockedService` on the HTTP path. Everything here is
importable from a spawned process, so the process race test uses it too.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.data.interface import PriceBar
from app.playbook.models import BatchState, Directive, FastMarketState, PlaybookEvaluation
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import confirm_rule_set

#: The seeded series end on this Friday.
SERIES_END = date(2026, 8, 14)
HISTORY = 40
SUNDAY = date(2026, 8, 9)
MONDAY = date(2026, 8, 10)  # not a schedule day
TUESDAY = date(2026, 8, 11)  # 排程日 (T)
WEDNESDAY = date(2026, 8, 12)  # T+1, not a schedule day
THURSDAY = date(2026, 8, 13)  # 排程日

START_CASH = Decimal("1000000")
#: R1 shares of one batch at a close of 100: 1,000,000 / 5 / 3 / 100 (CEO 裁決二).
ONE_BUY_SHARES = 666
ONE_BUY_COST = Decimal("100") * ONE_BUY_SHARES


def closes(base: float, overrides: dict[date, float] | None = None) -> list[float]:
    """``HISTORY`` consecutive daily closes ending ``SERIES_END``, with overrides."""
    values = [base] * HISTORY
    for day, value in (overrides or {}).items():
        values[HISTORY - 1 - (SERIES_END - day).days] = value
    return values


def bars(symbol: str, base: float, overrides: dict[date, float] | None = None) -> list[PriceBar]:
    return recent_bars(closes(base, overrides), symbol=symbol, end=SERIES_END)


def capped(series: Iterable[PriceBar], last: date) -> list[PriceBar]:
    """``series`` as it looked before any bar after ``last`` existed."""
    return [bar for bar in series if bar.date <= last]


class ClockedService(PlaybookService):
    """Pins the clock for the HTTP path only.

    ``GET /today`` calls ``evaluate_today()`` with no argument, i.e. the real
    clock. This subclass supplies the default ``today`` and changes nothing
    else; the route, the response mapping and every store call are production
    code.
    """

    pinned: date = TUESDAY

    def evaluate_today(self, *, today: date | None = None) -> PlaybookEvaluation:
        return super().evaluate_today(today=today or self.pinned)


@dataclass
class Desk:
    service: ClockedService
    store: PlaybookStore
    prices: FakePriceService
    index: FakePriceService


def open_desk(
    db_path: Path,
    *,
    symbols: Iterable[str] = ("2330",),
    seed: bool = True,
    cash: Decimal = START_CASH,
) -> Desk:
    """A confirmed rule set, planned batches, funded cash and flat series (seed=True)."""
    store = PlaybookStore(db_path=db_path)
    prices = FakePriceService()
    index = FakePriceService()
    index.seed("^TWII", bars("^TWII", 20000.0))
    symbols = list(symbols)
    for symbol in symbols:
        prices.seed(symbol, bars(symbol, 100.0))
    if seed:
        confirm_rule_set(store)
        store.ensure_batches(symbols, batches_per_target=3)
        store.set_capital(cash=cash, total_deploy=START_CASH, source="initial")
    service = ClockedService(
        store=store, market_resolver={"TW": prices}, index_resolver={"TW": index, "US": index}
    )
    return Desk(service=service, store=store, prices=prices, index=index)


def seed_desk(db_path: Path) -> None:
    """The database every race test starts from: one symbol, three planned batches."""
    open_desk(db_path)


def hold(
    store: PlaybookStore,
    symbol: str,
    batch_no: int,
    *,
    shares: int = 300,
    cost: str = "100",
    **changes: Any,
) -> None:
    """Make ``(symbol, batch_no)`` an open batch holding ``shares`` at ``cost``."""
    store.save_batch(
        BatchState(
            symbol=symbol,
            batch_no=batch_no,
            status="open",
            entry_date=date(2026, 7, 1),
            cost=Decimal(cost),
            shares=shares,
            remaining_shares=shares,
            peak_close=Decimal(cost),
        ).model_copy(update=changes)
    )


def log_rows(db_path: Path) -> list[tuple[Any, ...]]:
    """``(symbol, batch_no, rule_id, action, execution_date, settled, status)`` of every line."""
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            "SELECT symbol, batch_no, rule_id, action, execution_date, settled, status "
            "FROM playbook_directives ORDER BY id"
        ).fetchall()


def schedule_rows(db_path: Path) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            "SELECT symbol, batch_no, scheduled_date, defer_count, rule_id "
            "FROM playbook_schedule ORDER BY id"
        ).fetchall()


def rule_rows(db_path: Path, rule_id: str, action: str) -> list[tuple[Any, ...]]:
    return [row for row in log_rows(db_path) if row[2] == rule_id and row[3] == action]


def buy_line(
    *,
    symbol: str = "2330",
    batch_no: int = 1,
    shares: int = ONE_BUY_SHARES,
    data_date: date = TUESDAY,
    execution_date: date = WEDNESDAY,
    reference: str = "100",
) -> Directive:
    """An R1 buy shaped like the engine's, band ±2% around ``reference``."""
    price = Decimal(reference)
    return Directive(
        symbol=symbol,
        batch_no=batch_no,
        action="buy",
        shares=shares,
        rule_id="R1",
        rule_summary="R1 排程日進場",
        data_date=data_date,
        execution_date=execution_date,
        reference_price=price,
        limit_low=price * Decimal("0.98"),
        limit_high=price * Decimal("1.02"),
        limit_note="限價帶",
        data_status="fresh",
        source="fake",
    )


def evaluation_of(
    store: PlaybookStore, lines: list[Directive], **changes: Any
) -> PlaybookEvaluation:
    """A bare evaluation carrying ``lines``, for the store-level tests."""
    return PlaybookEvaluation(
        data_date=TUESDAY,
        execution_date=WEDNESDAY,
        mode="normal",
        mode_reason="正常模式",
        is_schedule_day=True,
        fast_market=FastMarketState(
            active=False, annualized_vol_20d=None, large_move_days=0, reason=None
        ),
        rules_version=1,
        params=store.active_params(TUESDAY),
        directives=lines,
        effects=[],
        warnings=[],
        snapshot=[],
    ).model_copy(update=changes)


def log_like_before_n172a(store: PlaybookStore, lines: list[Directive]) -> None:
    """Write ``lines`` the way ``/today`` did before N-172a: a plain append, no check."""
    store.record_directives(evaluation_of(store, lines))
