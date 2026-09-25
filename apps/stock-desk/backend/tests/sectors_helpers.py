"""Synthetic point-in-time panels for the sector-core tests (offline, no I/O).

Two builders:

* :class:`PanelBuilder` -- raw rows, for tests that need exact control of runs,
  sources and ``recorded_at``;
* :func:`scenario` -- a ready-made market where every sector member is
  eligible and each member's fate in the lookback window is declared with a
  :class:`Member` (return, missing bar on t, ex-date in window, corporate
  action jump).

Every run is recorded at 18:00 Asia/Taipei on its own session unless a test
says otherwise, i.e. comfortably before ``cutoff(t)``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import pandas as pd

from app.data.panel import (
    BARS_COLUMNS,
    CLASSIFICATION_COLUMNS,
    EX_DIVIDEND_COLUMNS,
    LISTING_COLUMNS,
    RUNS_COLUMNS,
    TAIPEI,
    MarketPanel,
    PanelFrames,
)
from app.sectors.definition import COMMON_STOCK_SECURITY_TYPE

START = date(2026, 1, 5)  # a Monday


def weekdays(count: int, start: date = START) -> list[date]:
    days: list[date] = []
    cursor = start
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def taipei(day: date, hour: int = 18, minute: int = 0, second: int = 0) -> pd.Timestamp:
    local = datetime.combine(day, time(hour, minute, second), tzinfo=TAIPEI)
    return pd.Timestamp(local).tz_convert("UTC")


@dataclass
class PanelBuilder:
    bars: list[dict[str, object]] = field(default_factory=list)
    listing: list[dict[str, object]] = field(default_factory=list)
    classification: list[dict[str, object]] = field(default_factory=list)
    ex_dividend: list[dict[str, object]] = field(default_factory=list)
    runs: list[dict[str, object]] = field(default_factory=list)
    _next: int = 0

    def run(
        self,
        kind: str,
        session: date,
        *,
        recorded: pd.Timestamp | None = None,
        source: str = "twse_snapshot",
        status: str = "ok",
    ) -> tuple[str, pd.Timestamp]:
        self._next += 1
        run_id = f"r{self._next:06d}"
        at = recorded if recorded is not None else taipei(session)
        self.runs.append(
            {
                "run_id": run_id,
                "kind": kind,
                "session_date": session,
                "recorded_at": at,
                "source": source,
                "status": status,
                "row_count": 0,
                "expected_count": None,
            }
        )
        return run_id, at

    def bar(
        self,
        run: tuple[str, pd.Timestamp],
        session: date,
        symbol: str,
        close: float,
        *,
        source: str = "twse_snapshot",
        traded_value: float = 5e7,
        shares: int = 10_000,
        change: float = math.nan,
    ) -> None:
        self.bars.append(
            {
                "run_id": run[0],
                "session_date": session,
                "recorded_at": run[1],
                "source": source,
                "symbol": symbol,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "shares": shares,
                "traded_value": traded_value,
                "change": change,
            }
        )

    def listed(
        self,
        run: tuple[str, pd.Timestamp],
        session: date,
        symbol: str,
        security_type: str = COMMON_STOCK_SECURITY_TYPE,
    ) -> None:
        self.listing.append(
            {
                "run_id": run[0],
                "session_date": session,
                "recorded_at": run[1],
                "symbol": symbol,
                "security_type": security_type,
            }
        )

    def classified(
        self, run: tuple[str, pd.Timestamp], session: date, symbol: str, code: str, name: str
    ) -> None:
        self.classification.append(
            {
                "run_id": run[0],
                "session_date": session,
                "recorded_at": run[1],
                "symbol": symbol,
                "sector_code": code,
                "sector_name": name,
            }
        )

    def announced(
        self, run: tuple[str, pd.Timestamp], session: date, symbol: str, ex_date: date
    ) -> None:
        self.ex_dividend.append(
            {
                "run_id": run[0],
                "session_date": session,
                "recorded_at": run[1],
                "symbol": symbol,
                "ex_date": ex_date,
            }
        )

    def frames(self) -> PanelFrames:
        return PanelFrames(
            bars=pd.DataFrame(self.bars, columns=list(BARS_COLUMNS)),
            listing=pd.DataFrame(self.listing, columns=list(LISTING_COLUMNS)),
            classification=pd.DataFrame(self.classification, columns=list(CLASSIFICATION_COLUMNS)),
            ex_dividend=pd.DataFrame(self.ex_dividend, columns=list(EX_DIVIDEND_COLUMNS)),
            runs=pd.DataFrame(self.runs, columns=list(RUNS_COLUMNS)),
        )

    def panel(self) -> MarketPanel:
        return MarketPanel(self.frames())


@dataclass(frozen=True)
class Member:
    """One sector member and what happens to it inside the lookback window."""

    symbol: str
    ret: float = 0.01
    missing: bool = False
    ex_date: bool = False
    jump: bool = False
    traded_value: float = 5e7
    security_type: str = COMMON_STOCK_SECURITY_TYPE


#: Official-looking sector names used by the scenarios.
SECTOR_NAMES: Mapping[str, str] = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "12": "汽車工業",
    "14": "建材營造業",
    "15": "航運業",
    "17": "金融保險業",
    "20": "其他業",
    "24": "半導體業",
    "28": "電子零組件業",
    "91": "存託憑證",
}


@dataclass(frozen=True)
class Scenario:
    market: MarketPanel
    sessions: tuple[date, ...]
    lookback: int

    @property
    def t(self) -> date:
        return self.sessions[-1]

    @property
    def window(self) -> tuple[date, ...]:
        return self.sessions[-self.lookback - 1 :]


def _closes(member: Member, n_sessions: int, lookback: int) -> list[float]:
    closes = [100.0] * (n_sessions - lookback - 1)
    for k in range(lookback + 1):
        closes.append(100.0 * (1.0 + member.ret) ** (k / lookback))
    if member.jump:
        # +30% between the window's 2nd and 3rd session: category ③.
        for k in range(n_sessions - lookback + 1, n_sessions):
            closes[k] *= 1.3
    return closes


def scenario(
    sectors: Mapping[str, Sequence[Member]],
    *,
    n_sessions: int = 70,
    lookback: int = 5,
    dividend_run_missing_on: Iterable[date] = (),
    bars_source: str = "twse_snapshot",
) -> Scenario:
    """A market of fully eligible members; each Member declares its window fate."""
    days = weekdays(n_sessions)
    window = days[-lookback - 1 :]
    builder = PanelBuilder()
    skip_dividend = set(dividend_run_missing_on)
    members = [(code, member) for code, group in sectors.items() for member in group]
    closes = {member.symbol: _closes(member, n_sessions, lookback) for _, member in members}
    for index, day in enumerate(days):
        bars_run = builder.run("bars", day, source=bars_source)
        listing_run = builder.run("listing", day)
        class_run = builder.run("classification", day)
        for code, member in members:
            missing_today = member.missing and day == days[-1]
            if not missing_today:
                builder.bar(
                    bars_run,
                    day,
                    member.symbol,
                    closes[member.symbol][index],
                    source=bars_source,
                    traded_value=member.traded_value,
                )
            builder.listed(listing_run, day, member.symbol, member.security_type)
            builder.classified(class_run, day, member.symbol, code, SECTOR_NAMES.get(code, code))
        if day not in skip_dividend:
            dividend_run = builder.run("dividend_announce", day)
            for _, member in members:
                ex_day = window[2]
                if member.ex_date and day >= days[-15] and day <= ex_day:
                    builder.announced(dividend_run, day, member.symbol, ex_day)
    return Scenario(market=builder.panel(), sessions=tuple(days), lookback=lookback)


def members(prefix: str, count: int, *, ret: float = 0.0, **overrides: object) -> list[Member]:
    """``count`` plain members ``<prefix>00..`` returning ``ret`` plus a distinct small step."""
    return [
        Member(symbol=f"{prefix}{i:02d}", ret=ret + 0.001 * (i + 1), **overrides)  # type: ignore[arg-type]
        for i in range(count)
    ]


def canonical(value: object) -> object:
    """A bit-exact, order-independent rendering of core outputs (T-5)."""
    import dataclasses

    from pydantic import BaseModel

    if isinstance(value, float):
        return ("f", value.hex())
    if isinstance(value, BaseModel):
        return canonical(value.model_dump())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__name__,
            tuple((f.name, canonical(getattr(value, f.name))) for f in dataclasses.fields(value)),
        )
    if isinstance(value, Mapping):
        return tuple(sorted((str(k), canonical(v)) for k, v in value.items()))
    if isinstance(value, frozenset | set):
        return ("set", tuple(sorted(repr(canonical(v)) for v in value)))
    if isinstance(value, list | tuple):
        return tuple(canonical(v) for v in value)
    return value
