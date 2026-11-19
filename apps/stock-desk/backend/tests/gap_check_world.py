"""Synthetic worlds for the tests of ``scripts/gap_check.py`` (ADR-0030 supplement 8 point 5).

Everything is a ``tmp_path`` file or an in-memory fake: a synthetic "main" database (the real
``price_bars_cache`` columns, with OHLCV values and other tables that must never reach the
output), a fake backend folder, a fake home, a fake git, a recorded / synthetic TWSE calendar
and a fake clock. Nothing here opens the real ``<backend>/data/``, reads ``.env`` or touches the
network. This module imports only the standard library (it is also imported by a subprocess
driver that must not load ``app``).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sqlite3
import sys
import threading
import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND / "scripts" / "gap_check.py"
MODULE_NAME = "gap_check"
HEAD = "b" * 40
RUN_DATE = date(2026, 11, 19)
NOW = datetime(2026, 11, 19, 10, 0, 0)
WORK_NAME = "20261119-100000"

#: Values that must never appear in any output: prices, volumes, cash, holdings, labels.
POISON_OPEN = "31415.926"
POISON_VOLUME = "27182818"
POISON_CASH = "7777777.77"
POISON_HOLDING = "SECRETSYM"
POISON_INDEX = "99,999.99"
POISON = (POISON_OPEN, POISON_VOLUME, POISON_CASH, POISON_HOLDING, "99,999", "99999.99")

_cache: list[ModuleType] = []


def load_script() -> ModuleType:
    """The script as a module; the process's hooks and warnings filters are as they were."""
    if _cache:
        return _cache[0]
    saved = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    logging_disabled = logging.root.manager.disable
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        with warnings.catch_warnings():  # restores the filters on exit
            spec.loader.exec_module(module)
    finally:
        sys.excepthook, threading.excepthook, sys.unraisablehook = saved
        logging.disable(logging_disabled)
    _cache.append(module)
    return module


def weekdays(start: date, end: date, holidays: Iterable[date] = ()) -> list[date]:
    """Monday-Friday dates of ``[start, end]`` minus ``holidays`` (a synthetic official calendar)."""
    skip = set(holidays)
    days = []
    day = start
    while day <= end:
        if day.weekday() < 5 and day not in skip:
            days.append(day)
        day += timedelta(days=1)
    return days


def roc(day: date, *, blank: bool = True) -> str:
    year = day.year - 1911
    text = f"{year}/{day.month:02d}/{day.day:02d}"
    return f" {text}" if blank and year < 100 else text


def month_body(days: Iterable[date]) -> bytes:
    """A TWSE ``MI_5MINS_HIST`` response for the given days (index values are poison)."""
    rows = [
        [roc(d)] + [POISON_INDEX, POISON_INDEX, POISON_INDEX, POISON_INDEX] for d in sorted(days)
    ]
    payload = {
        "stat": "OK",
        "title": "synthetic",
        "fields": ["日期", "開盤指數", "最高指數", "最低指數", "收盤指數"],
        "data": rows,
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


SECURITY_PAGE = b"<html><body>security page (synthetic)</body></html>"


class FakeCalendar:
    """A fake ``get``: answers per month; records every URL asked, in order."""

    def __init__(
        self,
        official: Sequence[date],
        *,
        bad: Iterable[str] = (),
        statuses: dict[str, int] | None = None,
        bodies: dict[str, bytes] | None = None,
    ) -> None:
        self.official = sorted(official)
        self.bad = set(bad)  # "YYYY-MM" answered with a 307 security page
        self.statuses = statuses or {}
        self.bodies = bodies or {}
        self.urls: list[str] = []

    def __call__(self, url: str) -> tuple[int, bytes]:
        self.urls.append(url)
        stamp = url.rsplit("date=", 1)[1]
        key = f"{stamp[:4]}-{stamp[4:6]}"
        if key in self.bodies:
            return self.statuses.get(key, 200), self.bodies[key]
        if key in self.statuses:
            return self.statuses[key], SECURITY_PAGE
        if key in self.bad:
            return 307, SECURITY_PAGE
        days = [d for d in self.official if f"{d.year:04d}-{d.month:02d}" == key]
        return 200, month_body(days)


class FakeClock:
    """A fake time: ``sleep`` advances it; nothing really sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        self.now += 0.25  # every request / clock read takes a little time
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeGit:
    """A canned ``git``: the answers of a clean, published checkout (or a chosen failure)."""

    def __init__(
        self,
        *,
        dirty: bool = False,
        published: bool = True,
        unusable: bool = False,
        head: str = HEAD,
    ) -> None:
        self.dirty, self.published, self.unusable, self.head = dirty, published, unusable, head
        self.calls: list[list[str]] = []

    def __call__(self, cwd: Path, args: Sequence[str]) -> tuple[int, bytes]:
        self.calls.append(list(args))
        if self.unusable:
            return 127, b""
        if args[:1] == ["rev-parse"] and "--show-toplevel" in args:
            return 0, str(cwd.parent).encode()
        if args[:1] == ["status"]:
            return 0, b" M scripts/x.py\n" if self.dirty else b""
        if args[:2] == ["rev-parse", "HEAD"]:
            return 0, self.head.encode() + b"\n"
        if args[:1] == ["merge-base"]:
            return (0 if self.published else 1), b""
        return 1, b""


MAIN_DDL = """
CREATE TABLE price_bars_cache (
    symbol TEXT NOT NULL, market TEXT NOT NULL, trade_date TEXT NOT NULL,
    open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,
    volume INTEGER NOT NULL, currency TEXT NOT NULL, source TEXT NOT NULL,
    as_of TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market, trade_date)
)
"""


def write_main_db(
    db: Path,
    twii_dates: Iterable[str],
    *,
    wal: bool = False,
    keep_open: bool = False,
    extra_symbol_dates: Iterable[str] = ("2026-11-02", "2026-11-03"),
    with_table: bool = True,
) -> sqlite3.Connection | None:
    """A synthetic main database: ``^TWII`` rows with poison OHLCV, other symbols, other tables.

    ``keep_open`` returns the writer connection (its WAL / shm files stay), with the last row
    committed but not checkpointed; the caller closes it.
    """
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
    if with_table:
        conn.execute(MAIN_DDL)
        insert = "INSERT INTO price_bars_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
        for symbol, dates in (("^TWII", list(twii_dates)), ("2330", list(extra_symbol_dates))):
            for d in dates:
                conn.execute(
                    insert,
                    (
                        symbol, "TW", d, POISON_OPEN, "40000.1", "39000.2", "39500.3",
                        int(POISON_VOLUME), "TWD", "yfinance", d + "T20:00:00+08:00",
                        d + "T20:05:00+08:00",
                    ),
                )  # fmt: skip
    conn.execute("CREATE TABLE portfolio (symbol TEXT, qty INTEGER, cash TEXT)")
    conn.execute("INSERT INTO portfolio VALUES (?, 1000, ?)", (POISON_HOLDING, POISON_CASH))
    conn.execute("CREATE TABLE forecast_claim (claim_id TEXT, label TEXT)")
    conn.execute("INSERT INTO forecast_claim VALUES ('claim-0001', 'bullish')")
    conn.commit()
    if keep_open:
        return conn
    conn.close()
    return None


@dataclass
class World:
    """A fake backend folder, a fake home and the fakes a run needs."""

    root: Path
    backend: Path
    home: Path
    db: Path
    run_date: date
    official: list[date]
    twii: list[date]
    calendar: FakeCalendar
    clock: FakeClock = field(default_factory=FakeClock)
    git: FakeGit = field(default_factory=FakeGit)
    events: list[str] = field(default_factory=list)
    opened: list[Path] = field(default_factory=list)

    @property
    def work_root(self) -> Path:
        return self.home / "stock-desk-gap-check"

    @property
    def work(self) -> Path:
        return self.work_root / WORK_NAME

    @property
    def main_files(self) -> list[Path]:
        return [Path(f"{self.db}{s}") for s in ("", "-wal", "-shm", "-journal")]

    def args(self) -> list[str]:
        return ["--backend-dir", str(self.backend), "--home", str(self.home)]

    def seams(self, **override: Any) -> dict[str, Any]:
        seams: dict[str, Any] = {
            "env": {},
            "port_check": lambda: False,
            "git": self.git,
            "wait": lambda _prompt: None,
            "opener": self.opened.append,
            "now": lambda: NOW,
            "today": lambda: self.run_date,
            "get": self.calendar,
            "clock": self.clock,
            "sleep": self.clock.sleep,
            "pause": lambda _s: None,
        }
        seams.update(override)
        return seams


def period_of(run_date: date) -> tuple[date, date]:
    return run_date - timedelta(days=500), run_date - timedelta(days=1)


def make_world(
    root: Path,
    *,
    run_date: date = RUN_DATE,
    holidays: Iterable[date] = (),
    missing_in_cache: Iterable[date] = (),
    extra_in_cache: Iterable[str] = (),
    cache_from: date | None = None,
    cache_to: date | None = None,
    bad_months: Iterable[str] = (),
    wal: bool = False,
    write_db: bool = True,
) -> World:
    """A world whose cache holds every official day of the period except ``missing_in_cache``."""
    start, end = period_of(run_date)
    official = weekdays(start - timedelta(days=40), end, holidays)
    in_period = [d for d in official if start <= d <= end]
    lo = cache_from or in_period[0]
    hi = cache_to or in_period[-1]
    skip = set(missing_in_cache)
    twii = [d for d in in_period if lo <= d <= hi and d not in skip]
    backend = root / "backend"
    home = root / "home"
    home.mkdir(parents=True, exist_ok=True)
    (backend / "data").mkdir(parents=True, exist_ok=True)
    db = backend / "data" / "stock-desk.db"
    if write_db:
        write_main_db(db, [d.isoformat() for d in twii] + list(extra_in_cache), wal=wal)
    return World(
        root=root,
        backend=backend,
        home=home,
        db=db,
        run_date=run_date,
        official=official,
        twii=twii,
        calendar=FakeCalendar(official, bad=bad_months),
    )


def main_db_state(world: World) -> dict[str, tuple[bytes, int]]:
    """The bytes and mtime (ns) of every main database file that exists (never the real one)."""
    out: dict[str, tuple[bytes, int]] = {}
    for path in world.main_files:
        if path.exists():
            out[path.name] = (path.read_bytes(), path.stat().st_mtime_ns)
    return out
