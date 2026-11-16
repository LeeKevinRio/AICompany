"""Fixtures for the market outlook tests (freeze pack 2.10 / 2.11): synthetic bars only.

Nothing here reads real ``^TWII`` data, a database or the network (pre-registration
§10, risk RC-130). Closes are built from log levels by lag exactly as freeze pack
2.10 writes them, ``c_k = 10000.0 * math.exp(L_k)``, ascending oldest first; the
session dates are consecutive weekdays (the features never read dates) and each
bar is stamped 20:00 Asia/Taipei on its own session, which is final.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from app.advice.loader import BANNED_PHRASES
from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.dirdef.definition import DirectionDefinition
from app.dirdef.rules import OutlookRuleSet, load_ruleset
from app.outlook.inputs import SnapshotBar
from tests.dirdef_helpers import dirdef_v1_0

TAIPEI: Final = ZoneInfo("Asia/Taipei")
RULES_DIR: Final = Path(__file__).resolve().parent.parent / "app" / "outlook" / "rules"
FIRST_SESSION: Final = date(2025, 1, 6)
N: Final = 315

# --- Freeze pack 2.10 fixtures (log level by lag k) ---------------------------------------
_A, _MU = 0.01, 0.002


def _hv(mu: float, b: float) -> list[float]:
    return [-(k * mu) - ((b if k <= 20 else _A) if k % 2 else 0.0) for k in range(N)]


FIXTURES: Final[dict[str, list[float]]] = {
    "FX-A": [-(_A if k % 2 else 0.0) for k in range(N)],
    "FX-B": [-(k * _MU) - (_A if k % 2 else 0.0) for k in range(N)],
    "FX-C": [(k * _MU) + (_A if k % 2 else 0.0) for k in range(N)],
    "FX-D": [0.04] + [-(_A if k % 2 else 0.0) for k in range(1, N)],
    "FX-E1": _hv(0.004, 0.03),
    "FX-E2": _hv(0.01, 0.03),
}


def weekdays(count: int, start: date = FIRST_SESSION) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def evening(day: date, hour: int = 20) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=TAIPEI)


def snapshot_bar(day: date, close: Decimal, *, fetched: datetime | None = None) -> SnapshotBar:
    stamp = fetched or evening(day)
    return SnapshotBar(
        session_date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0,
        source="yfinance",
        as_of=stamp,
        fetched_at=stamp,
    )


def closes_from_logs(logs_by_lag: Sequence[float]) -> list[float]:
    """Ascending closes (oldest first) of freeze pack 2.10's ``L_k``."""
    return [10000.0 * math.exp(logs_by_lag[k]) for k in reversed(range(len(logs_by_lag)))]


def bars_from_closes(closes: Sequence[float], start: date = FIRST_SESSION) -> list[SnapshotBar]:
    """One bar per close on consecutive weekdays; ``Decimal(float)`` is exact."""
    return [
        snapshot_bar(day, Decimal(close))
        for day, close in zip(weekdays(len(closes), start), closes, strict=True)
    ]


def fixture_bars(name: str) -> list[SnapshotBar]:
    return bars_from_closes(closes_from_logs(FIXTURES[name]))


def with_close(bars: Sequence[SnapshotBar], lag: int, close: Decimal) -> list[SnapshotBar]:
    """``bars`` with the close of lag ``lag`` replaced."""
    out = list(bars)
    index = len(out) - 1 - lag
    old = out[index]
    out[index] = snapshot_bar(old.session_date, close, fetched=old.fetched_at)
    return out


# --- Rule sets and definition -------------------------------------------------------------


def rule_bytes(horizon: int) -> bytes:
    return (RULES_DIR / f"h{horizon}.yaml").read_bytes()


@cache
def ruleset(horizon: int) -> OutlookRuleSet:
    """The landed h3 / h5 rule file, through the real loader and banned phrases."""
    data = rule_bytes(horizon)
    return load_ruleset(
        data, rules_sha256=hashlib.sha256(data).hexdigest(), banned_phrases=BANNED_PHRASES
    )


@cache
def definition() -> DirectionDefinition:
    """The G7 ``dirdef-v1.0`` values with test C-8 stand-ins (not registered)."""
    return dirdef_v1_0()


# --- LA-G2-1 series (freeze pack 2.11; deterministic, no random generator) ---------------


def la_return(j: int) -> float:
    base = 0.008 * math.sin(0.7 * j) + 0.003 * (((j * 7919) % 13) - 6) / 6
    return 3.0 * base if 450 <= j < 470 else base


def la_series(count: int = 600) -> list[SnapshotBar]:
    closes = [10000.0]
    for j in range(1, count):
        closes.append(closes[-1] * math.exp(la_return(j)))
    return bars_from_closes(closes)


# --- A fake price service for the real app.services.index path ---------------------------


class FakeIndexService:
    """A ``PriceService`` returning fixed ``^TWII`` bars; it never touches the network."""

    def __init__(self, bars: Sequence[PriceBar], status: DataStatus = DataStatus.BACKUP) -> None:
        self.bars = list(bars)
        self.status = status
        self.calls: list[tuple[str, Market, date, date]] = []

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        self.calls.append((symbol, market, start, end))
        return ProviderResult(
            bars=[b for b in self.bars if start <= b.date <= end],
            status=self.status,
            as_of=datetime(2026, 1, 1, tzinfo=UTC),
            source="yfinance",
        )

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        return self.get_daily_bars(symbol, market, start, end)


def price_bar(day: date, close: Decimal, as_of: datetime, symbol: str = "^TWII") -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market="TW",
        date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0,
        currency="TWD",
        as_of=as_of,
        source="yfinance",
    )


def price_bars(bars: Sequence[SnapshotBar]) -> list[PriceBar]:
    return [price_bar(b.session_date, b.close, b.as_of) for b in bars]
