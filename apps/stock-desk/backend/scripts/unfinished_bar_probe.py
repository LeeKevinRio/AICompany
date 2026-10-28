"""N-152 offline probe: which ``price_bars_cache`` rows were fetched before their session closed?

Run from ``apps/stock-desk/backend`` on the machine that holds the price DB::

    uv run python scripts/unfinished_bar_probe.py --db-path ./data/stock-desk.db
    # or: STOCK_DESK_DB_PATH=./data/stock-desk.db uv run python scripts/unfinished_bar_probe.py

Background (risk control 2026-10-26, point 3 (c)): since 2026-09-15 the data service drops
bars dated after the latest closed session *before* writing the cache
(``DataService._without_unfinished_session``). A DB written before that date may still hold
a bar that was stored while its session was open.

The rule (deterministic, no heuristics)
---------------------------------------
Every ``price_bars_cache`` row carries ``fetched_at`` (UTC ISO-8601, refreshed on every
upsert). A row is listed when::

    fetched_at < close time of trade_date in the market's own time zone, converted to UTC

* ``TW``: 13:30 ``Asia/Taipei`` (no DST).
* ``US``: 16:00 ``America/New_York`` (DST-aware: 20:00 UTC in summer, 21:00 UTC in winter).

The close time is computed per row from ``zoneinfo`` for that row's own ``trade_date``; no
UTC offset is hard-coded. ``fetched_at == close`` is NOT listed (the service itself treats a
session as closed from ``local.time() >= session_close``, ``freshness.py``). The rule has no
trading calendar: a row is judged on its date alone.

Each listed row is also tagged with whether its ``trade_date`` equals the newest
``trade_date`` stored for the same ``(symbol, market)``. Rows that cannot be judged (unknown
market, unparseable date or timestamp, timezone-naive ``fetched_at``) are printed under their
own heading with the stored values; they are never skipped and never guessed at.

Output is facts only: counts, rows, and the rule. It states no conclusion and no advice.

Read-only by construction: the file is opened with SQLite's ``mode=ro`` URI plus
``PRAGMA query_only=ON``, it is never created, and nothing is written -- not to the DB and
not to disk (output goes to stdout only). One SELECT is issued, on ``price_bars_cache``
(symbol, market, trade_date, source, fetched_at); no price columns are read. One caveat that is
SQLite's, not the script's: when it reads a WAL-mode database, SQLite's own ``-wal`` /
``-shm`` sidecar files may appear next to it; the database file itself is byte-identical
afterwards.
Standard library only: no ``app`` import.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_DB_PATH = "./data/stock-desk.db"
DB_PATH_ENV_VAR = "STOCK_DESK_DB_PATH"

#: The only SQL this script sends besides ``PRAGMA query_only=ON``.
SCAN_SQL = "SELECT symbol, market, trade_date, source, fetched_at FROM price_bars_cache"


@dataclass(frozen=True)
class MarketRule:
    """Regular-session close of one market, in that market's own time zone."""

    timezone: str
    close: time


#: Mirrors ``session_close`` / ``timezone`` in ``app/data/freshness.py`` (a test pins them).
MARKET_RULES: dict[str, MarketRule] = {
    "TW": MarketRule("Asia/Taipei", time(13, 30)),
    "US": MarketRule("America/New_York", time(16, 0)),
}


def close_utc(market: str, trade_date: date) -> datetime:
    """The regular-session close of ``trade_date`` in ``market``, as an aware UTC datetime."""
    rule = MARKET_RULES[market]
    local = datetime.combine(trade_date, rule.close, tzinfo=ZoneInfo(rule.timezone))
    return local.astimezone(UTC)


@dataclass(frozen=True)
class Finding:
    """A row whose ``fetched_at`` is earlier than the close of its ``trade_date``."""

    symbol: str
    market: str
    trade_date: date
    fetched_at_text: str
    close_utc: datetime
    source: str
    symbol_latest_trade_date: date
    is_latest_bar: bool


@dataclass(frozen=True)
class NotJudged:
    """A row the rule cannot be applied to, with the values exactly as stored."""

    symbol: str
    market: str
    trade_date_text: str
    fetched_at_text: str
    source: str
    reason: str


@dataclass(frozen=True)
class Report:
    rows_total: int
    rows_by_market: dict[str, int]
    findings: list[Finding]
    not_judged: list[NotJudged]


# ---------------------------------------------------------------- reading


def open_read_only(path: Path) -> sqlite3.Connection:
    """Open ``path`` read-only; refuses a missing file instead of creating one."""
    if not path.is_file():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
    except BaseException:
        conn.close()
        raise
    return conn


def _parse_day(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_instant(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class _Candidate:
    symbol: str
    market: str
    trade_date: date
    fetched_at_text: str
    close_utc: datetime
    source: str


def _unjudgeable_reason(
    market: str, trade_date: date | None, fetched: datetime | None
) -> str | None:
    """Why the rule cannot be applied to a row, or ``None`` when it can."""
    if market not in MARKET_RULES:
        return "unknown_market"
    if trade_date is None:
        return "unparseable_trade_date"
    if fetched is None:
        return "unparseable_fetched_at"
    if fetched.tzinfo is None:
        return "timezone_naive_fetched_at"
    return None


def scan(rows: Iterable[tuple[object, ...]]) -> Report:
    """Apply the rule to ``(symbol, market, trade_date, source, fetched_at)`` rows."""
    total = 0
    by_market: Counter[str] = Counter()
    newest: dict[tuple[str, str], date] = {}
    candidates: list[_Candidate] = []
    not_judged: list[NotJudged] = []

    for raw_symbol, raw_market, raw_date, raw_source, raw_fetched in rows:
        total += 1
        symbol, market, source = str(raw_symbol), str(raw_market), str(raw_source)
        date_text, fetched_text = str(raw_date), str(raw_fetched)
        by_market[market] += 1

        trade_date = _parse_day(date_text)
        if trade_date is not None:
            key = (symbol, market)
            if key not in newest or trade_date > newest[key]:
                newest[key] = trade_date
        fetched = _parse_instant(fetched_text)
        reason = _unjudgeable_reason(market, trade_date, fetched)
        if reason is not None or trade_date is None or fetched is None:
            not_judged.append(
                NotJudged(symbol, market, date_text, fetched_text, source, reason or "unknown")
            )
            continue
        closing_instant = close_utc(market, trade_date)
        if fetched < closing_instant:
            candidates.append(
                _Candidate(symbol, market, trade_date, fetched_text, closing_instant, source)
            )

    findings = [
        Finding(
            symbol=c.symbol,
            market=c.market,
            trade_date=c.trade_date,
            fetched_at_text=c.fetched_at_text,
            close_utc=c.close_utc,
            source=c.source,
            symbol_latest_trade_date=newest[(c.symbol, c.market)],
            is_latest_bar=c.trade_date == newest[(c.symbol, c.market)],
        )
        for c in candidates
    ]
    findings.sort(key=lambda f: (f.market, f.symbol, f.trade_date))
    not_judged.sort(key=lambda n: (n.reason, n.market, n.symbol, n.trade_date_text))
    return Report(total, dict(by_market), findings, not_judged)


def load(conn: sqlite3.Connection) -> Report:
    """Scan every ``price_bars_cache`` row (a single read-only SELECT)."""
    return scan(conn.execute(SCAN_SQL))


# ---------------------------------------------------------------- output


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def render(report: Report, *, db_path: Path, now_utc: datetime) -> str:
    lines: list[str] = []
    out = lines.append
    out("N-152 unfinished-bar probe (read-only: SQLite mode=ro + PRAGMA query_only=ON)")
    out(f"db_path: {db_path}")
    out(f"run_at_utc: {_iso_utc(now_utc)}")
    out("")
    out("== Rule ==")
    out("listed when: fetched_at < close of trade_date in the market time zone, converted to UTC")
    for market, rule in MARKET_RULES.items():
        out(f"{market}: {rule.close.strftime('%H:%M')} {rule.timezone}")
    out("fetched_at equal to the close instant is not listed")
    out("is_latest_bar: trade_date equals the newest trade_date of the same (symbol, market)")
    out("")
    out("== Counts ==")
    out(f"price_bars_cache rows scanned: {report.rows_total}")
    for market in MARKET_RULES:
        listed = [f for f in report.findings if f.market == market]
        latest = sum(1 for f in listed if f.is_latest_bar)
        out(
            f"{market}: rows={report.rows_by_market.get(market, 0)} "
            f"fetched_before_close={len(listed)} "
            f"is_latest_bar={latest} not_latest_bar={len(listed) - latest}"
        )
    other_markets = {m: n for m, n in report.rows_by_market.items() if m not in MARKET_RULES}
    for market in sorted(other_markets):
        out(f"{market!r} (market value without a close rule): rows={other_markets[market]}")
    out(f"rows that could not be judged: {len(report.not_judged)}")
    reasons = Counter(n.reason for n in report.not_judged)
    for reason in sorted(reasons):
        out(f"  {reason}: {reasons[reason]}")
    out("")
    out("== Rows with fetched_at before close ==")
    out(f"count: {len(report.findings)}")
    if report.findings:
        out(
            "market | symbol | trade_date | fetched_at | close_utc | is_latest_bar | "
            "symbol_latest_trade_date | source"
        )
    for f in report.findings:
        out(
            f"{f.market} | {f.symbol} | {f.trade_date.isoformat()} | {f.fetched_at_text} | "
            f"{_iso_utc(f.close_utc)} | {'yes' if f.is_latest_bar else 'no'} | "
            f"{f.symbol_latest_trade_date.isoformat()} | {f.source}"
        )
    out("")
    out("== Rows that could not be judged (values as stored) ==")
    out(f"count: {len(report.not_judged)}")
    if report.not_judged:
        out("reason | market | symbol | trade_date | fetched_at | source")
    for n in report.not_judged:
        out(
            f"{n.reason} | {n.market} | {n.symbol} | {n.trade_date_text} | "
            f"{n.fetched_at_text} | {n.source}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI


def missing_timezone() -> str | None:
    """The first rule time zone the IANA database cannot supply, or ``None`` when all load.

    ``ZoneInfoNotFoundError`` is a ``KeyError``, so it must be checked up front: raised in the
    middle of a scan it would end as a traceback with exit status 1.
    """
    for rule in MARKET_RULES.values():
        try:
            ZoneInfo(rule.timezone)
        except ZoneInfoNotFoundError:
            return rule.timezone
    return None


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    now_utc: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="unfinished_bar_probe.py",
        description="Read-only N-152 probe: price_bars_cache rows fetched before their close.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=f"price DB file; default ${DB_PATH_ENV_VAR} or {DEFAULT_DB_PATH}",
    )
    args = parser.parse_args(argv)
    absent = missing_timezone()
    if absent is not None:
        print(
            f"cannot load time zone {absent!r}: the IANA time zone database is missing. "
            "On Windows run inside the project environment (uv run --frozen), which installs "
            "the 'tzdata' package; do not use the system Python or --no-project.",
            file=sys.stderr,
        )
        return 2
    environment = os.environ if env is None else env
    path = Path(args.db_path or environment.get(DB_PATH_ENV_VAR, DEFAULT_DB_PATH))
    try:
        with closing(open_read_only(path)) as conn:
            report = load(conn)
    except (FileNotFoundError, sqlite3.Error) as error:
        print(f"cannot read the DB: {error}", file=sys.stderr)
        return 2
    moment = now_utc if now_utc is not None else datetime.now(UTC)
    print(render(report, db_path=path.resolve(), now_utc=moment))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
