"""Builders shared by the playbook tests: calendar, snapshots, batches.

Everything is fixed and offline. The calendar covers the second half of 2026 as
plain weekdays, which is enough for every "N 交易日" the rule set counts and
keeps 排程日 (週二／四) unambiguous in the assertions.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.playbook.calendar import TradingCalendar
from app.playbook.models import (
    BatchState,
    IndexSnapshot,
    MarketSnapshot,
    PortfolioState,
    RuleParams,
)
from app.playbook.store import PlaybookStore

#: A Tuesday (排程日) used as the 依據資料日 in most cases.
TUESDAY = date(2026, 8, 11)
#: The Wednesday after it -- the 預定執行日 for TUESDAY.
WEDNESDAY = date(2026, 8, 12)
#: A Friday: a trading day that is not a 排程日.
FRIDAY = date(2026, 8, 14)
#: 規則版本生效日 of the rule set the service-level tests adopt as the user's own.
RULE_SET_DATE = date(2026, 1, 1)


def calendar(start: date = date(2026, 6, 1), days: int = 200) -> TradingCalendar:
    """Weekday-only trading calendar covering ``days`` calendar days from ``start``."""
    return TradingCalendar(
        start + timedelta(days=offset)
        for offset in range(days)
        if (start + timedelta(days=offset)).weekday() < 5
    )


def params(**overrides: object) -> RuleParams:
    return RuleParams(effective_date=RULE_SET_DATE).model_copy(update=dict(overrides))


def confirm_rule_set(store: PlaybookStore, **overrides: object) -> RuleParams:
    """Record the user's own rule set, which every rule-driven line needs.

    風控 R2 / 覆審 歸屬語情境 1: without this record the service produces no
    directive at all, so a service-level test that wants lines has to state that
    the user confirmed the rules -- the same thing the product asks of them.
    """
    confirmed = params(**overrides)
    store.confirm_rule_set(confirmed)
    return confirmed


def market(
    symbol: str = "2330",
    *,
    close: str,
    ma25: str | None = "100",
    bias25: str | None = "0",
    change_pct: str | None = "0",
    data_date: date = TUESDAY,
    status: str = "fresh",
    source: str = "twse",
    high_volatility: bool = False,
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        data_date=data_date,
        close=Decimal(close),
        change_pct=None if change_pct is None else Decimal(change_pct),
        ma25=None if ma25 is None else Decimal(ma25),
        bias25=None if bias25 is None else Decimal(bias25),
        data_status=status,
        source=source,
        high_volatility=high_volatility,
    )


def index(
    *,
    close: str = "20000",
    monthly_line: str | None = "19000",
    days_below: int = 0,
    vol: float | None = 12.0,
    large_moves: int = 0,
    data_date: date = TUESDAY,
    status: str = "backup",
    source: str = "yfinance",
) -> IndexSnapshot:
    return IndexSnapshot(
        data_date=data_date,
        close=Decimal(close),
        monthly_line=None if monthly_line is None else Decimal(monthly_line),
        days_below_monthly_line=days_below,
        annualized_vol_20d=vol,
        large_move_days=large_moves,
        data_status=status,
        source=source,
    )


def batch(
    symbol: str = "2330",
    batch_no: int = 1,
    *,
    status: str = "open",
    cost: str | None = "100",
    shares: int = 300,
    remaining: int | None = None,
    peak: str | None = None,
    p1_done: bool = False,
    p2_done: bool = False,
    p3_last: date | None = None,
    trailing: bool = False,
    defer_count: int = 0,
    entry_date: date | None = date(2026, 7, 1),
) -> BatchState:
    return BatchState(
        symbol=symbol,
        batch_no=batch_no,
        status=status,  # type: ignore[arg-type]
        entry_date=entry_date if status == "open" else None,
        cost=None if cost is None or status == "planned" else Decimal(cost),
        shares=shares if status == "open" else 0,
        remaining_shares=(shares if remaining is None else remaining) if status == "open" else 0,
        peak_close=None if peak is None else Decimal(peak),
        p1_done=p1_done,
        p2_done=p2_done,
        p3_last_date=p3_last,
        trailing_active=trailing,
        defer_count=defer_count,
    )


def planned(symbol: str = "2330", batch_no: int = 1, *, defer_count: int = 0) -> BatchState:
    return batch(symbol, batch_no, status="planned", cost=None, shares=0, defer_count=defer_count)


def portfolio(
    *,
    cash: str = "1000000",
    total_deploy: str = "1000000",
    freeze_until: date | None = None,
    freeze_reason: str | None = None,
    emergency_until: date | None = None,
    defense_active: bool = False,
) -> PortfolioState:
    return PortfolioState(
        cash=Decimal(cash),
        total_deploy=Decimal(total_deploy),
        freeze_until=freeze_until,
        freeze_reason=freeze_reason,
        emergency_until=emergency_until,
        defense_active=defense_active,
    )
