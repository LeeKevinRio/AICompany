"""Off-ledger, read-only missing-day comparison of the ``^TWII`` cache (supplement 8 point 5).

Authority: ADR-0030 supplement 8 point 5, as read and tightened by supplement 10 point 7.

What it does (one run, started by ``gap-check.bat``): preflight, a SQLite backup-API copy of the
main database (the source is opened ``mode=ro&immutable=1``, and only when it has no ``-wal`` or
``-journal`` file and does not change while it is copied), ONE ``SELECT trade_date`` on the copy,
deletion of the copy, the official TWSE trading-day calendar month by month
(``MI_5MINS_HIST``, date column only), the comparison, and a whitelisted ``paste-back.txt`` plus
the same lines on screen.

Boundaries (point 5 (c), RC-220):

* standard library only: no ``app`` and no ``tests`` import (so neither ``app.forecast`` nor
  ``app.outlook``); the ``.env`` file is only searched for the key name, its values are never
  read; the main database and the cache are never written;
* the one SQL statement is :data:`SELECT_SQL`: no OHLCV column, no other table;
* the copy (with side files) is deleted before the first result line is printed; when it cannot
  be deleted the run stops and prints no result;
* the calendar source and URL are constants; a month that cannot be had is listed as unchecked
  (never estimated, never taken from another source); no user information, key or cookie is sent.

Screen guarantee (RC-158a, RC-158c, RC-162): the first statements of this file replace the three
exception hooks with one fixed sentence and silence warnings and logging; ``main`` catches
``BaseException``; every line shown or written fullmatches the whitelist or is a fixed STOP /
ERROR sentence. Console output is ASCII; the paste-back file is ``utf-8-sig``.
"""

# ruff: noqa: E402 -- the imports must follow the exception hooks (RC-162).

from __future__ import annotations

import logging
import sys
import threading
import warnings


def _fixed_hook(*_args: object) -> None:
    """RC-162: whatever escapes, the screen shows this one sentence (no text, no traceback)."""
    sys.stdout.write(
        "ERROR: unexpected failure; no paste-back file was made. Tell the coordinator.\n"
    )


sys.excepthook = _fixed_hook
threading.excepthook = _fixed_hook
sys.unraisablehook = _fixed_hook
warnings.simplefilter("ignore")
logging.disable(logging.CRITICAL)

import argparse
import gc
import hashlib
import http.client
import json
import os
import re
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import monotonic as _monotonic
from time import sleep as _sleep
from types import MappingProxyType
from typing import Any, Final, Literal, NoReturn

_BACKEND_DIR = Path(__file__).resolve().parents[1]

# === constants ====================================================================================

VERSION_LINE: Final = "gap_check version=1"
WORK_ROOT_NAME: Final = "stock-desk-gap-check"
DB_NAME: Final = "stock-desk.db"
#: The copy's files, in the order they are deleted (side files should never appear).
DB_FILES: Final = (DB_NAME, f"{DB_NAME}-wal", f"{DB_NAME}-shm")
COPY_EXTRA_FILES: Final = (f"{DB_NAME}-journal",)
COPY_DIR: Final = "copy"
RUN_FOLDER_PATTERN: Final = re.compile(r"[0-9]{8}-[0-9]{6}")
STAMP_FORMAT: Final = "%Y%m%d-%H%M%S"
PASTE_BACK_NAME: Final = "paste-back.txt"
PORT: Final = 8000
ENV_VAR: Final = "STOCK_DESK_DB_PATH"
ENV_KEY_PATTERN: Final = re.compile(r"^\s*STOCK_DESK_DB_PATH\s*=")
#: Folders and files of the backend folder that must be clean in git.
CLEAN_PATHS: Final = ("app", "tests", "scripts", "uv.lock")
PUBLISHED_REF: Final = "origin/product/stock-desk"
DELETE_ATTEMPTS: Final = 5
DELETE_PAUSE_SECONDS: Final = 0.5
PROMPT: Final = "Close the stock-desk backend, scheduler and frontend windows, then press Enter. "

#: The one statement run on the copy (point 5 (c)): one column, one table, one symbol.
SELECT_SQL: Final = "SELECT trade_date FROM price_bars_cache WHERE symbol = '^TWII'"

#: Official calendar: TWSE index history, one JSON per month; only the date column is read.
CALENDAR_SOURCE: Final = "twse_mi_5mins_hist"
CALENDAR_URL_TEMPLATE: Final = (
    "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?response=json&date={year:04d}{month:02d}01"
)
CALENDAR_DATE_FIELD: Final = "日期"
USER_AGENT: Final = "gap-check/1.0 (read-only, low rate)"
#: The check period: 500 calendar days before the run date through the day before it.
LOOKBACK_DAYS: Final = 500
#: Rate limit (the 2026-10-16 probe design: at least 6 s between requests, stop on 403/429/503,
#: no redirect followed; data-engineer 2026-11-19: 307 pages come with dense requests and
#: recover at 5-12 s). After a failed request the next gap is doubled.
REQUEST_INTERVAL_SECONDS: Final = 6.0
BACKOFF_INTERVAL_SECONDS: Final = 12.0
HARD_STOP_STATUSES: Final = (403, 429, 503)
MAX_CONSECUTIVE_FAILURES: Final = 3
REQUEST_TIMEOUT_SECONDS: Final = 30.0
MAX_BODY_BYTES: Final = 1 << 20
#: Taiwan has no daylight saving time; the run date is the Taipei date.
TAIPEI: Final = timezone(timedelta(hours=8))

# === fixed sentences ==============================================================================

RunStopKind = Literal[
    "env_db_path",
    "env_file_db_path",
    "no_db",
    "port_listening",
    "work_in_git",
    "git_unusable",
    "git_dirty",
    "head_unpublished",
    "db_in_use",
    "copy_failed",
    "copy_unreadable",
    "no_rows",
    "unparseable_row",
    "copy_not_deleted",
]

#: One fixed ASCII sentence per stop; none carries a value, a count or a path.
STOP_SENTENCES: Final[Mapping[RunStopKind, str]] = MappingProxyType(
    {
        # Verbatim from pipeline_acceptance_real.py (OUTER_STOP_SENTENCES):
        "env_db_path": "STOP: STOCK_DESK_DB_PATH is set in the environment.",
        "env_file_db_path": "STOP: STOCK_DESK_DB_PATH is set in the .env file of the app.",
        "no_db": "STOP: stock-desk.db was not found at the default location.",
        "port_listening": (
            "STOP: something is listening on port 8000; close the stock-desk windows and run again."
        ),
        "work_in_git": "STOP: the work folder would be inside a git work tree.",
        "git_unusable": "STOP: git could not be used on the code folder.",
        "git_dirty": "STOP: the code folder has uncommitted changes.",
        "head_unpublished": "STOP: this code version is not on origin/product/stock-desk.",
        "copy_not_deleted": (
            "STOP: the database copy could not be deleted, so the check did not continue."
            " Remove the whole work folder without opening it, do not send it to anyone,"
            " and tell the coordinator."
        ),
        # Verbatim from pipeline_acceptance_real.py (STOP_SENTENCES):
        "no_rows": "STOP: the cache copy holds no TWII rows.",
        "unparseable_row": "STOP: a TWII row of the cache copy cannot be read.",
        # Verbatim from the risk-control report (RC-271, S-1), extracted by script:
        "db_in_use": (
            "STOP: the database may be in use, or it changed while it was being "
            "copied, so the check did not continue. Close the stock-desk backend, "
            "scheduler and frontend windows, then run this again. Do not delete or "
            "change any file yourself; if this line appears again, tell the "
            "coordinator and do not run this again."
        ),
        # Verbatim from the risk-control report (RC-272, S-3; replaces the cg2_register.py line):
        "copy_failed": (
            "STOP: a copy of the database could not be made, so the check did not "
            "continue. Do not change any setting or file yourself; tell the "
            "coordinator."
        ),
        # Verbatim from the risk-control report (S-2), extracted by script:
        "copy_unreadable": (
            "STOP: the database copy could not be read. Do not change any setting or "
            "file yourself; tell the coordinator."
        ),
    }
)
#: Same text as the exception hooks at the top of this file.
UNEXPECTED: Final = "ERROR: unexpected failure; no paste-back file was made. Tell the coordinator."
INTERRUPTED: Final = "ERROR: interrupted; no paste-back file was made."
FIXED_SENTENCES: Final = frozenset({*STOP_SENTENCES.values(), UNEXPECTED, INTERRUPTED})


class RunStop(Exception):
    """A stop: a closed ``kind`` and its fixed sentence."""

    def __init__(self, kind: RunStopKind) -> None:
        if kind not in STOP_SENTENCES:
            raise ValueError("unknown stop kind")
        super().__init__(STOP_SENTENCES[kind])
        self.kind: RunStopKind = kind


# === the output whitelist (point 5 (e)) and the result codes (point 5 (f)) ========================

ResultCode = Literal[
    "calendar_unavailable", "gaps_found", "no_gaps_found", "no_gaps_in_checked_months"
]
RESULT_CODES: Final[tuple[ResultCode, ...]] = (
    "calendar_unavailable",
    "gaps_found",
    "no_gaps_found",
    "no_gaps_in_checked_months",
)

_HEX64 = r"[0-9a-f]{64}"
_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
_MONTH = r"[0-9]{4}-[0-9]{2}"
_DATES = rf"(none|{_DATE}(,{_DATE})*)"
_MONTHS = rf"(none|{_MONTH}(,{_MONTH})*)"
#: One entry per allowed shape; a line is shown or written only when it fullmatches one of them.
WHITELIST: Final[tuple[tuple[str, re.Pattern[str]], ...]] = tuple(
    (name, re.compile(pattern))
    for name, pattern in (
        ("version", re.escape(VERSION_LINE)),
        ("git_head", r"git_head=[0-9a-f]{40}"),
        ("script_sha256_lf", rf"script_sha256_lf={_HEX64}"),
        ("calendar_source", re.escape(f"calendar_source={CALENDAR_SOURCE}")),
        ("period_start", rf"period_start={_DATE}"),
        ("period_end", rf"period_end={_DATE}"),
        ("months_checked", rf"months_checked={_MONTHS}"),
        ("months_unchecked", rf"months_unchecked={_MONTHS}"),
        ("cache_range_start", rf"cache_range_start=(none|{_DATE})"),
        ("cache_range_end", rf"cache_range_end=(none|{_DATE})"),
        ("cache_not_covered_count", r"cache_not_covered_count=[0-9]+"),
        ("cache_not_covered_dates", rf"cache_not_covered_dates={_DATES}"),
        ("official_not_in_cache_count", r"official_not_in_cache_count=[0-9]+"),
        ("official_not_in_cache_dates", rf"official_not_in_cache_dates={_DATES}"),
        ("cache_not_in_official_count", r"cache_not_in_official_count=[0-9]+"),
        ("cache_not_in_official_dates", rf"cache_not_in_official_dates={_DATES}"),
        ("result", rf"result=({'|'.join(RESULT_CODES)})"),
    )
)


def on_whitelist(line: str) -> bool:
    """True when ``line`` fullmatches one whitelist shape (an ASCII line without a newline).

    Every digit class is spelled ``[0-9]``: the shorthand class also accepts the digits of other
    scripts (qa N-6).
    """
    return any(pattern.fullmatch(line) for _name, pattern in WHITELIST)


def is_screen_line(line: str) -> bool:
    """RC-220: every screen / file line is a whitelist shape or a fixed STOP / ERROR sentence."""
    return on_whitelist(line) or line in FIXED_SENTENCES


def say(text: str) -> None:
    """Console output, ASCII only; a line that is neither whitelisted nor fixed is never shown."""
    if not is_screen_line(text) or not text.isascii():
        raise RuntimeError("a line outside the whitelist")
    print(text)


# === the calendar =================================================================================

HttpGet = Callable[[str], tuple[int, bytes]]
_ROC_DATE = re.compile(r"([0-9]{2,3})/([0-9]{2})/([0-9]{2})")


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def roc_to_date(cell: object) -> date | None:
    """``115/11/02`` (ROC year, leading blanks allowed) to ``2026-11-02``; None when unreadable."""
    if not isinstance(cell, str):
        return None
    found = _ROC_DATE.fullmatch(cell.strip())
    if found is None:
        return None
    try:
        return date(int(found.group(1)) + 1911, int(found.group(2)), int(found.group(3)))
    except ValueError:
        return None


def parse_month(body: bytes, year: int, month: int) -> frozenset[date] | None:
    """The dates of one month's response, or None when anything is not as expected.

    Only the first cell of every row (the date) is read. The response must be a JSON object with
    ``stat`` equal to ``OK``, a first field named the date field, and a non-empty ``data`` whose
    every date is a valid ROC date inside the requested month.
    """
    if len(body) > MAX_BODY_BYTES:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        return None
    fields = payload.get("fields")
    if not isinstance(fields, list) or not fields or fields[0] != CALENDAR_DATE_FIELD:
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    days: set[date] = set()
    for row in data:
        if not isinstance(row, list) or not row:
            return None
        day = roc_to_date(row[0])
        if day is None or (day.year, day.month) != (year, month):
            return None
        days.add(day)
    return frozenset(days)


@dataclass(frozen=True)
class Calendar:
    """What the official calendar gave: the dates, and which months were / were not had."""

    dates: frozenset[date]
    checked: tuple[str, ...]
    unchecked: tuple[str, ...]


def fetch_calendar(
    months: Sequence[tuple[int, int]],
    *,
    get: HttpGet,
    clock: Callable[[], float] = _monotonic,
    sleep: Callable[[float], None] = _sleep,
) -> Calendar:
    """One GET per month, newest first, rate limited; a month not had is listed as unchecked.

    No retry. At least :data:`REQUEST_INTERVAL_SECONDS` between requests (doubled after a failed
    one). A 403 / 429 / 503, or :data:`MAX_CONSECUTIVE_FAILURES` failures in a row, ends the
    fetching: every month not yet asked is unchecked. A 307 page, any other status, a network
    error, a bad body or an unexpected content makes that one month unchecked.
    """
    dates: set[date] = set()
    checked: list[str] = []
    unchecked: list[str] = []
    last_end: float | None = None
    interval = REQUEST_INTERVAL_SECONDS
    failures = 0
    stopped = False
    for year, month in sorted(months, reverse=True):
        key = f"{year:04d}-{month:02d}"
        if stopped:
            unchecked.append(key)
            continue
        if last_end is not None:
            wait = interval - (clock() - last_end)
            if wait > 0:
                sleep(wait)
        try:
            status, body = get(CALENDAR_URL_TEMPLATE.format(year=year, month=month))
        except (OSError, http.client.HTTPException):
            status, body = 0, b""
        last_end = clock()
        found = parse_month(body, year, month) if status == 200 else None
        if found is None:
            failures += 1
            interval = BACKOFF_INTERVAL_SECONDS
            unchecked.append(key)
            if status in HARD_STOP_STATUSES or failures >= MAX_CONSECUTIVE_FAILURES:
                stopped = True
        else:
            failures = 0
            interval = REQUEST_INTERVAL_SECONDS
            dates |= found
            checked.append(key)
    return Calendar(frozenset(dates), tuple(sorted(checked)), tuple(sorted(unchecked)))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is not followed: the 3xx answer surfaces as an ``HTTPError`` (the 307 page)."""

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def build_opener() -> urllib.request.OpenerDirector:
    """A plain opener: no redirect, and (by ``build_opener``'s defaults) no cookie handler."""
    return urllib.request.build_opener(_NoRedirect)


def http_get(url: str, *, opener: urllib.request.OpenerDirector | None = None) -> tuple[int, bytes]:
    """One GET: (status, body); network errors raise ``OSError``. The only header is User-Agent."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    director = opener if opener is not None else build_opener()
    try:
        with director.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return int(response.status), bytes(response.read(MAX_BODY_BYTES + 1))
    except urllib.error.HTTPError as error:
        try:
            return int(error.code), bytes(error.read(MAX_BODY_BYTES + 1))
        finally:
            error.close()


# === the period and the comparison ================================================================


def check_period(run_date: date) -> tuple[date, date]:
    """500 calendar days before the run date through the day before it."""
    return run_date - timedelta(days=LOOKBACK_DAYS), run_date - timedelta(days=1)


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    """Every (year, month) from ``start``'s month through ``end``'s month, ascending."""
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


@dataclass(frozen=True)
class Comparison:
    """The whole outcome: everything the whitelist lines show, nothing else."""

    period_start: date
    period_end: date
    checked: tuple[str, ...]
    unchecked: tuple[str, ...]
    cache_start: date | None
    cache_end: date | None
    not_covered: tuple[date, ...]
    official_not_in_cache: tuple[date, ...]
    cache_not_in_official: tuple[date, ...]
    result: ResultCode


def decide(
    *,
    checked: Sequence[str],
    unchecked: Sequence[str],
    not_covered: Sequence[date],
    official_not_in_cache: Sequence[date],
    cache_not_in_official: Sequence[date],
) -> ResultCode:
    """Point 5 (f): the first condition that holds, in this order."""
    if not checked:
        return "calendar_unavailable"
    if official_not_in_cache or cache_not_in_official:
        return "gaps_found"
    if not unchecked and not not_covered:
        return "no_gaps_found"
    return "no_gaps_in_checked_months"


def compare(
    cache_dates: Iterable[date], calendar: Calendar, *, start: date, end: date
) -> Comparison:
    """Point 5 (d): the cache's ``^TWII`` dates against the official dates, inside the period."""
    cache = {day for day in cache_dates if start <= day <= end}
    official = {day for day in calendar.dates if start <= day <= end}
    cache_start = min(cache) if cache else None
    cache_end = max(cache) if cache else None
    if cache_start is None or cache_end is None:
        not_covered = sorted(official)
        official_not_in_cache: list[date] = []
    else:
        not_covered = sorted(d for d in official if d < cache_start or d > cache_end)
        official_not_in_cache = sorted(
            d for d in official if cache_start <= d <= cache_end and d not in cache
        )
    checked_months = set(calendar.checked)
    cache_not_in_official = sorted(
        d for d in cache if month_key(d) in checked_months and d not in official
    )
    result = decide(
        checked=calendar.checked,
        unchecked=calendar.unchecked,
        not_covered=not_covered,
        official_not_in_cache=official_not_in_cache,
        cache_not_in_official=cache_not_in_official,
    )
    return Comparison(
        period_start=start,
        period_end=end,
        checked=calendar.checked,
        unchecked=calendar.unchecked,
        cache_start=cache_start,
        cache_end=cache_end,
        not_covered=tuple(not_covered),
        official_not_in_cache=tuple(official_not_in_cache),
        cache_not_in_official=tuple(cache_not_in_official),
        result=result,
    )


def _joined(items: Iterable[str]) -> str:
    text = ",".join(items)
    return text if text else "none"


def render(comparison: Comparison, *, git_head: str, script_sha256_lf: str) -> list[str]:
    """The result lines, in the order of point 5 (e); each one is checked against the whitelist."""
    c = comparison

    def day(value: date | None) -> str:
        return value.isoformat() if value is not None else "none"

    def days(values: Iterable[date]) -> str:
        return _joined(v.isoformat() for v in values)

    lines = [
        VERSION_LINE,
        f"git_head={git_head}",
        f"script_sha256_lf={script_sha256_lf}",
        f"calendar_source={CALENDAR_SOURCE}",
        f"period_start={c.period_start.isoformat()}",
        f"period_end={c.period_end.isoformat()}",
        f"months_checked={_joined(c.checked)}",
        f"months_unchecked={_joined(c.unchecked)}",
        f"cache_range_start={day(c.cache_start)}",
        f"cache_range_end={day(c.cache_end)}",
        f"cache_not_covered_count={len(c.not_covered)}",
        f"cache_not_covered_dates={days(c.not_covered)}",
        f"official_not_in_cache_count={len(c.official_not_in_cache)}",
        f"official_not_in_cache_dates={days(c.official_not_in_cache)}",
        f"cache_not_in_official_count={len(c.cache_not_in_official)}",
        f"cache_not_in_official_dates={days(c.cache_not_in_official)}",
        f"result={c.result}",
    ]
    if not all(on_whitelist(line) and line.isascii() for line in lines):
        raise RuntimeError("a rendered line is outside the whitelist")
    return lines


# === the database copy ============================================================================


def db_uri(db: Path) -> str:
    """The read-only, immutable URI: ``mode=ro&immutable=1``, always (supplement 10 point 7 (a)).

    A plain ``mode=ro`` connection to a WAL database creates or changes a ``-wal`` / ``-shm`` file
    beside it (measured, hand-over report). ``immutable=1`` reads the database file alone, with no
    lock and no side file; it is safe only while no writer is active, which is why
    :func:`make_copy` stops on a ``-wal`` / ``-journal`` file and on any change of the file. There
    is no plain ``mode=ro`` path for the main database any more.
    """
    return f"{Path(db).resolve().as_uri()}?mode=ro&immutable=1"


SIDE_FILE_SUFFIXES: Final = ("-wal", "-journal")
FileSignature = tuple[int, int]


def has_side_files(db: Path) -> bool:
    """True when a ``-wal`` or ``-journal`` file sits beside ``db`` (a ``stat``; no connection)."""
    path = Path(db).resolve()
    return any(path.with_name(f"{path.name}{suffix}").exists() for suffix in SIDE_FILE_SUFFIXES)


def file_signature(db: Path) -> FileSignature:
    """``(st_size, st_mtime_ns)`` of ``db``; a ``stat`` only, no connection is opened."""
    info = Path(db).stat()
    return info.st_size, info.st_mtime_ns


def make_copy(main_db: Path, copy_dir: Path) -> Path:
    """A consistent copy by the SQLite backup API; the source is opened ``mode=ro&immutable=1``.

    Supplement 10 point 7 (a): with a ``-wal`` or ``-journal`` beside the main database it stops
    before any connection is opened and before any copy exists. The main database's
    ``(st_size, st_mtime_ns)`` is taken before and after the backup (connections closed); a
    difference, or a side file that appeared, is the same stop (the caller deletes the copy before
    the stop is shown). A backup that fails with the file unchanged is ``copy_failed``; a failure
    with a changed file or a new side file is reported as the changed file (``db_in_use``).
    """
    if has_side_files(main_db):
        raise RunStop("db_in_use")
    try:
        before = file_signature(main_db)
    except OSError:
        raise RunStop("copy_failed") from None
    copy_dir.mkdir(parents=True)
    target = copy_dir / DB_NAME
    failed = False
    try:
        with closing(sqlite3.connect(db_uri(main_db), uri=True)) as source:
            with closing(sqlite3.connect(str(target))) as dest:
                source.backup(dest)
    except (sqlite3.Error, OSError):
        failed = True
    try:
        changed = has_side_files(main_db) or file_signature(main_db) != before
    except OSError:
        changed = True  # fail closed: a file that cannot be examined counts as changed
    if changed:
        raise RunStop("db_in_use")
    if failed:
        raise RunStop("copy_failed")
    return target


def read_trade_dates(copy_path: Path) -> list[date]:
    """The ``^TWII`` ``trade_date`` values of the copy (one SELECT, nothing else is read).

    Opens only the copy it is given, read-only (a missing file is never created). Stops when
    there is no row, or when any value is not a plain ``YYYY-MM-DD`` date.
    """
    try:
        with closing(sqlite3.connect(db_uri(copy_path), uri=True)) as conn:
            rows = conn.execute(SELECT_SQL).fetchall()
    except sqlite3.Error:
        raise RunStop("copy_unreadable") from None
    if not rows:
        raise RunStop("no_rows")
    days: list[date] = []
    for row in rows:
        value = row[0]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise RunStop("unparseable_row")
        try:
            days.append(date.fromisoformat(value))
        except ValueError:
            raise RunStop("unparseable_row") from None
    return days


# --- deleting ---------------------------------------------------------------------------------

Remover = Callable[[Path], None]


def remove_path(path: Path) -> None:
    """Delete a file or a folder tree; an absent path is fine."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def delete_with_retry(
    path: Path, remover: Remover = remove_path, pause: Callable[[float], None] = _sleep
) -> bool:
    """Delete ``path``: 5 tries, 0.5 s apart, ``gc.collect()`` first (Windows holds locks)."""
    for attempt in range(DELETE_ATTEMPTS):
        gc.collect()
        try:
            remover(path)
        except OSError:
            if attempt + 1 < DELETE_ATTEMPTS:
                pause(DELETE_PAUSE_SECONDS)
            continue
        return True
    return False


def delete_copy(
    copy_dir: Path, remover: Remover = remove_path, pause: Callable[[float], None] = _sleep
) -> None:
    """RC-158c: delete the copy's files incl. side files, then its folder; any left is a stop."""
    if not copy_dir.exists():
        return
    left = False
    for name in (*DB_FILES, *COPY_EXTRA_FILES):
        if (copy_dir / name).exists() and not delete_with_retry(copy_dir / name, remover, pause):
            left = True
    if not delete_with_retry(copy_dir, remover, pause):
        left = True
    if left or copy_dir.exists():
        raise RunStop("copy_not_deleted")


def sweep_residue(
    root: Path, remover: Remover = remove_path, pause: Callable[[float], None] = _sleep
) -> None:
    """Delete a ``copy`` left in an earlier run folder; one that cannot be deleted stops."""
    if not root.is_dir():
        return
    for folder in sorted(root.iterdir()):
        if folder.is_symlink() or not folder.is_dir():
            continue
        if RUN_FOLDER_PATTERN.fullmatch(folder.name) and (folder / COPY_DIR).exists():
            delete_copy(folder / COPY_DIR, remover, pause)


def copy_left_behind(root: Path | None) -> bool:
    """True when a run folder of ``root`` (this run or an earlier one) still has a ``copy``."""
    if root is None or not root.is_dir():
        return False
    return any(
        RUN_FOLDER_PATTERN.fullmatch(folder.name)
        and not folder.is_symlink()
        and (folder / COPY_DIR).exists()
        for folder in root.iterdir()
    )


# === git and checks ===============================================================================

GitRunner = Callable[[Path, Sequence[str]], tuple[int, bytes]]


def run_git(cwd: Path, args: Sequence[str]) -> tuple[int, bytes]:
    """``git -C cwd args``: (return code, stdout bytes); 127 when git cannot run. Never prints.

    Every ``GIT_*`` variable is removed from git's environment and replace refs are ignored.
    """
    clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    try:
        done = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-C",
                str(cwd),
                *args,
            ],
            capture_output=True,
            timeout=120,
            check=False,
            env=clean_env,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, b""
    return done.returncode, done.stdout


def port_is_listening(port: int = PORT) -> bool:
    """One connect to 127.0.0.1 (the only socket use besides the calendar GETs)."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def inside_git_work_tree(path: Path) -> bool:
    resolved = path.resolve()
    return any((folder / ".git").exists() for folder in (resolved, *resolved.parents))


def env_file_sets_db_path(env_file: Path) -> bool:
    """True when a line of the file starts with the key. Only the key is looked for."""
    if not env_file.is_file():
        return False
    with open(env_file, encoding="utf-8-sig", errors="ignore") as handle:
        return any(ENV_KEY_PATTERN.match(line) for line in handle)


def preflight(
    *,
    backend_dir: Path,
    work: Path,
    env: Mapping[str, str],
    port_check: Callable[[], bool],
    git: GitRunner,
) -> str:
    """The checks that must hold before anything is copied; returns ``git rev-parse HEAD``."""
    if ENV_VAR in env:
        raise RunStop("env_db_path")
    if env_file_sets_db_path(backend_dir.parent / ".env"):
        raise RunStop("env_file_db_path")
    if not (backend_dir / "data" / DB_NAME).is_file():
        raise RunStop("no_db")
    if port_check():
        raise RunStop("port_listening")
    if inside_git_work_tree(work):
        raise RunStop("work_in_git")
    code, _top = git(backend_dir, ["rev-parse", "--show-toplevel"])
    if code != 0:
        raise RunStop("git_unusable")
    code, dirty = git(
        backend_dir, ["status", "--porcelain", "--untracked-files=all", "--", *CLEAN_PATHS]
    )
    if code != 0:
        raise RunStop("git_unusable")
    if dirty.strip():
        raise RunStop("git_dirty")
    code, head = git(backend_dir, ["rev-parse", "HEAD"])
    commit = head.decode("ascii", "ignore").strip()
    if code != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RunStop("git_unusable")
    code, _ = git(backend_dir, ["merge-base", "--is-ancestor", "HEAD", PUBLISHED_REF])
    if code != 0:
        raise RunStop("head_unpublished")
    return commit


def normalised_source(data: bytes) -> bytes:
    """Source bytes with every line ending (CRLF, CR) written as LF; nothing else changes."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


# === the outer flow ===============================================================================


@dataclass
class State:
    """What the cleanup of an abnormal end needs to know."""

    work: Path | None = None
    root: Path | None = None
    completed: bool = False


def cleanup(state: State, remover: Remover, pause: Callable[[float], None]) -> None:
    """The safety net: remove the copy, a paste-back that was not completed, an empty folder."""
    work = state.work
    if work is None or not work.exists():
        return
    try:
        delete_copy(work / COPY_DIR, remover, pause)
    except RunStop:
        pass  # the stop (if it matters) was raised where the copy was first deleted
    if not state.completed:
        try:
            (work / PASTE_BACK_NAME).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        work.rmdir()  # fails (and is ignored) unless the folder is empty
    except OSError:
        pass


def flow(
    state: State,
    *,
    backend_dir: Path,
    home: Path,
    env: Mapping[str, str],
    port_check: Callable[[], bool],
    git: GitRunner,
    wait: Callable[[str], object],
    opener: Callable[[Path], object] | None,
    now: Callable[[], datetime],
    today: Callable[[], date],
    get: HttpGet,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    remover: Remover,
    pause: Callable[[float], None],
) -> int:
    """The whole run; returns the exit code. Result output comes only at the very end."""
    root = home / WORK_ROOT_NAME
    work = root / now().strftime(STAMP_FORMAT)
    state.root = root
    wait(PROMPT)

    head = preflight(backend_dir=backend_dir, work=work, env=env, port_check=port_check, git=git)
    sweep_residue(root, remover, pause)
    state.work = work
    work.mkdir(parents=True)
    copy_dir = work / COPY_DIR
    try:
        cache_dates = read_trade_dates(make_copy(backend_dir / "data" / DB_NAME, copy_dir))
    finally:
        delete_copy(copy_dir, remover, pause)  # RC-220: before any result is printed

    start, end = check_period(today())
    calendar = fetch_calendar(months_between(start, end), get=get, clock=clock, sleep=sleep)
    comparison = compare(cache_dates, calendar, start=start, end=end)
    script_sha = hashlib.sha256(normalised_source(Path(__file__).read_bytes())).hexdigest()
    lines = render(comparison, git_head=head, script_sha256_lf=script_sha)

    with open(work / PASTE_BACK_NAME, "w", encoding="utf-8-sig") as handle:
        handle.write("\n".join(lines) + "\n")
    for line in lines:
        say(line)
    state.completed = True
    if opener is None and sys.platform == "win32":
        opener = getattr(os, "startfile", None)
    if opener is not None:
        try:
            opener(work / PASTE_BACK_NAME)
        except OSError:
            pass  # the paste-back file is in the work folder; the instruction says where
    return 0


class _QuietParser(argparse.ArgumentParser):
    """No usage text on stderr: a bad argument is an unexpected failure (one fixed sentence)."""

    def error(self, message: str) -> NoReturn:
        raise RuntimeError("bad arguments")


def main(argv: Sequence[str] | None = None, **injected: Any) -> int:
    """Run the check; the screen shows whitelisted lines or one fixed sentence (RC-162).

    ``injected`` are the test seams (``env``, ``port_check``, ``git``, ``wait``, ``opener``,
    ``now``, ``today``, ``get``, ``clock``, ``sleep``, ``remover``, ``pause``); the batch file
    passes none of them.
    """
    state = State()
    code = 1
    copy_stop_shown = False
    remover: Remover = injected.get("remover", remove_path)
    pause: Callable[[float], None] = injected.get("pause", _sleep)
    try:
        parser = _QuietParser(prog="gap_check.py", add_help=False)
        # Test-only overrides; the batch file never passes them.
        parser.add_argument("--backend-dir", default=None)
        parser.add_argument("--home", default=None)
        args = parser.parse_args(argv)
        backend = Path(args.backend_dir) if args.backend_dir else _BACKEND_DIR
        home = Path(args.home) if args.home else Path.home()
        try:
            code = flow(
                state,
                backend_dir=backend,
                home=home,
                env=injected.get("env", os.environ),
                port_check=injected.get("port_check", port_is_listening),
                git=injected.get("git", run_git),
                wait=injected.get("wait", input),
                opener=injected.get("opener"),
                now=injected.get("now", datetime.now),
                today=injected.get("today", lambda: datetime.now(TAIPEI).date()),
                get=injected.get("get", http_get),
                clock=injected.get("clock", _monotonic),
                sleep=injected.get("sleep", _sleep),
                remover=remover,
                pause=pause,
            )
        finally:
            cleanup(state, remover, pause)
    except RunStop as stop:
        say(str(stop))
        copy_stop_shown = str(stop) == STOP_SENTENCES["copy_not_deleted"]
        code = 3
    except KeyboardInterrupt:
        say(INTERRUPTED)
        code = 2
    except BaseException:  # noqa: BLE001 - a fixed sentence only, never the exception or a path
        say(UNEXPECTED)
        code = 1
    try:
        cleanup(state, remover, pause)
    except BaseException:  # noqa: BLE001 - best effort; the next start sweeps what is left
        pass
    # RC-158c: a copy that is still there after the last cleanup is never silent, whichever
    # path led here. The sentence is shown once, after the sentence the run ended with.
    try:
        left = copy_left_behind(state.root)
    except OSError:
        left = True  # fail closed: a copy that cannot be ruled out is treated as left behind
    if left:
        if code != 3 or not copy_stop_shown:
            say(STOP_SENTENCES["copy_not_deleted"])
        code = 3
    return code


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI tests
    raise SystemExit(main())
