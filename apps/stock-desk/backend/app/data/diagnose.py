"""CEO 本機體檢工具 -- 逐檔列出每一檔持倉的日線資料狀態。

    uv run python -m app.data.diagnose                 # 只看本機快取與冷卻狀態，不連線
    uv run python -m app.data.diagnose --probe         # 另外實際走一次資料梯子（會連線）
    uv run python -m app.data.diagnose --probe --clear-cooldown   # 先清掉冷卻再走梯子
    uv run python -m app.data.diagnose currency-inventory [--db PATH]

WHY
===
2026-09-19 the CEO found an 上櫃 holding (6147) showing 資料不足 and asked,
rightly, which *other* holdings are in the same state. The individual page
only ever shows one symbol, and the scheduler's refresh log is not something
the CEO reads. This module answers the question for the whole book in one
table: for every held ``(symbol, market)`` -- what the cache holds, whether
the ADR-0009 D-8 cooldown is currently blocking a live fetch, and (with
``--probe``) what the degradation ladder answers right now, with the data
layer's own reason sentence.

It never fabricates a verdict: a symbol with no bars is reported as ``無資料``
with the reason the ladder gave, not as "probably fine".

The ``currency-inventory`` subcommand (task F-9a) is a separate, strictly
read-only report: see :func:`currency_inventory`.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final

from app.data.admission import AdmissionReason, admit_symbol
from app.data.cache import PriceBarCache, resolve_db_path
from app.data.freshness import policy_for
from app.data.interface import DataStatus
from app.directory.store import SecurityDirectoryStore
from app.positions.models import MARKET_CURRENCY, Market
from app.positions.store import PositionStore
from app.services.market import MarketDataResolver, load_bars, trading_days_behind_market

#: Same window the scheduler warms (``app/scheduler.py``), so "what the cache
#: holds" is judged over the range the product actually reads. Equal to the
#: shared observation window (``app.signals.window``) but defined locally so
#: ``app.data`` does not import upward; a test pins the two together (ADR-0020 K-5).
DEFAULT_LOOKBACK_DAYS = 540

VERDICT_OK = "正常"
VERDICT_STALE = "資料過舊"
VERDICT_NONE = "無資料"
VERDICT_UNKNOWN = "無法判定"


@dataclass(frozen=True)
class SymbolDiagnosis:
    """One held series, as the cache and (optionally) the ladder see it."""

    symbol: str
    market: Market
    name: str | None
    cached_bars: int
    cached_last_date: date | None
    cached_sources: tuple[str, ...]
    last_attempt_at: datetime | None
    cooldown_active: bool
    cooldown_cleared: bool
    probe_status: str | None
    probe_source: str | None
    probe_bars: int | None
    probe_last_date: date | None
    probe_reason: str | None
    #: Market sessions observed in the cache after the series' last bar (C4,
    #: :func:`trading_days_behind_market`); ``None`` when the cache has seen no
    #: session in that window and cannot judge.
    sessions_behind: int | None

    @property
    def verdict(self) -> str:
        """``正常`` / ``資料過舊`` / ``無資料`` from the best evidence available.

        Staleness is judged in *observed* sessions, not calendar days, so a
        long exchange holiday (農曆春節) does not flag the whole book: no bar
        of any held series exists for those days, so no session is counted
        (qa-reviewer 2026-09-19). One session behind is the normal "not fetched
        yet today" state; two or more is an incident.

        ``sessions_behind`` is ``None`` only when the calendar window is empty,
        which cannot happen here: the window starts at the series' own last
        bar, which is itself an observed session (qa-reviewer 2026-09-19). It
        is kept as ``None``-tolerant so a caller wiring a different calendar
        source degrades to "cannot judge" rather than a false 正常.
        """
        bars = self.probe_bars if self.probe_bars is not None else self.cached_bars
        last = self.probe_last_date if self.probe_bars is not None else self.cached_last_date
        if bars == 0 or last is None:
            return VERDICT_NONE
        if self.sessions_behind is None:
            return VERDICT_UNKNOWN
        return VERDICT_STALE if self.sessions_behind >= 2 else VERDICT_OK


def diagnose_positions(
    *,
    positions: PositionStore,
    cache: PriceBarCache,
    resolver: MarketDataResolver | None = None,
    directory: SecurityDirectoryStore | None = None,
    today: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    probe: bool = False,
    clear_cooldown: bool = False,
) -> list[SymbolDiagnosis]:
    """Diagnose every distinct held ``(symbol, market)``; sorted by market then symbol.

    ``probe`` runs the real ladder through :func:`load_bars` (it may take a few
    seconds per symbol and respects the D-8 cooldown unless ``clear_cooldown``
    lifts it first). Without ``probe`` nothing leaves the machine.
    """
    end = today if today is not None else date.today()
    start = end - timedelta(days=lookback_days)
    now = datetime.now(UTC)
    held = sorted({(p.symbol, p.market) for p in positions.list_all()}, key=lambda x: (x[1], x[0]))
    out: list[SymbolDiagnosis] = []
    for symbol, market in held:
        name: str | None = None
        if directory is not None and directory.is_synced():
            entry = directory.resolve(symbol)
            name = entry.name if entry is not None else None

        cached = cache.get(symbol, market, start, end, now=now)
        cached_bars = len(cached.bars) if cached is not None else 0
        cached_last = max((b.date for b in cached.bars), default=None) if cached else None
        sources = tuple(sorted({b.source for b in cached.bars})) if cached else ()

        attempted = cache.last_attempt_at(symbol, market)
        cooldown_active = attempted is not None and policy_for(market).is_within_cooldown(
            now, attempted
        )
        cleared = False
        if clear_cooldown and cooldown_active:
            cleared = cache.clear_attempt(symbol, market)
            cooldown_active = False

        probe_status = probe_source = probe_reason = None
        probe_bars: int | None = None
        probe_last: date | None = None
        if probe and resolver is not None:
            loaded = load_bars(resolver, symbol=symbol, market=market, start=start, end=end)
            probe_status = loaded.status.value
            probe_source = loaded.source
            probe_bars = len(loaded.bars)
            probe_last = max((b.date for b in loaded.bars), default=None)
            probe_reason = loaded.reason
            if loaded.status is DataStatus.UNAVAILABLE and probe_reason is None:
                probe_reason = "來源未回報原因"

        effective_last = probe_last if probe_bars is not None else cached_last
        sessions_behind = trading_days_behind_market(
            cache, market=market, last_bar_date=effective_last, today=end
        )

        out.append(
            SymbolDiagnosis(
                symbol=symbol,
                market=market,
                name=name,
                cached_bars=cached_bars,
                cached_last_date=cached_last,
                cached_sources=sources,
                last_attempt_at=attempted,
                cooldown_active=cooldown_active,
                cooldown_cleared=cleared,
                probe_status=probe_status,
                probe_source=probe_source,
                probe_bars=probe_bars,
                probe_last_date=probe_last,
                probe_reason=probe_reason,
                sessions_behind=sessions_behind,
            )
        )
    return out


def render_report(rows: list[SymbolDiagnosis], *, probed: bool) -> str:
    """A Markdown table the CEO can paste back, one line per held series."""
    header = ["代號", "市場", "名稱", "判定", "快取根數", "快取最後日", "來源", "冷卻中"]
    if probed:
        header += ["梯子狀態", "梯子來源", "梯子根數", "原因"]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        cells = [
            r.symbol,
            r.market,
            r.name or "—",
            r.verdict,
            str(r.cached_bars),
            r.cached_last_date.isoformat() if r.cached_last_date else "—",
            "、".join(r.cached_sources) or "—",
            ("是（已清除）" if r.cooldown_cleared else "是")
            if r.cooldown_active or r.cooldown_cleared
            else "否",
        ]
        if probed:
            cells += [
                r.probe_status or "—",
                r.probe_source or "—",
                str(r.probe_bars) if r.probe_bars is not None else "—",
                (r.probe_reason or "—").replace("|", "／"),
            ]
        lines.append("| " + " | ".join(cells) + " |")
    problems = [r for r in rows if r.verdict != VERDICT_OK]
    summary = (
        f"共 {len(rows)} 檔持倉，{len(rows) - len(problems)} 檔正常，{len(problems)} 檔有問題"
        + ("：" + "、".join(f"{r.symbol}（{r.verdict}）" for r in problems) if problems else "。")
    )
    return "\n".join(lines) + "\n\n" + summary


#: Index series share the bars cache under a ``^`` key (ADR-0005 I-7). They are
#: outside symbol admission by design (ADR-0024 draft D-4), so the inventory
#: leaves them out of part (b); they still count as sessions in part (c).
_INDEX_PREFIX: Final = "^"
CURRENCY_INVENTORY_COMMAND: Final = "currency-inventory"


@dataclass(frozen=True)
class SuffixReviewHeuristic:
    """Which admitted US single-letter suffixes the inventory asks a person to look at.

    An inventory heuristic, **not** an admission rule (risk-compliance ruling
    F9W-15, adopted by the coordinator): admission lets every ``ROOT.X`` /
    ``ROOT-X`` through because a single-letter foreign exchange suffix
    (``VOD.L``) has the very shape of a share class (``BRK.B``). Rows written
    under such a symbol before F-9b are invisible to the currency gate (the
    adapters stamp USD on them) and out of reach of the F-9e clean-up, so the
    inventory lists every admitted US symbol whose suffix letter is *not* one
    of ``common_class_letters``, for the CEO to confirm one by one. It decides
    nothing and refuses nothing; the letter set is a judgement, unverified
    against any exchange list.
    """

    common_class_letters: frozenset[str]
    verified: bool
    verified_on: str | None
    note: str


#: Class letters common enough among US share classes (``BRK.A``/``BRK.B``,
#: ``BF.A``/``BF.B``, ``.C`` classes) not to need a second look. Heuristic only.
US_SUFFIX_REVIEW_HEURISTIC: Final = SuffixReviewHeuristic(
    common_class_letters=frozenset({"A", "B", "C"}),
    verified=False,
    verified_on=None,
    note="Inventory heuristic, not an admission rule: other single letters go to manual review.",
)

_US_SINGLE_LETTER_SUFFIX: Final = re.compile(r"[A-Z]{1,5}[.\-]([A-Z])")


def needs_suffix_review(symbol: str, market: str) -> bool:
    """An admitted US symbol whose single-letter suffix is outside the common class letters."""
    if market != "US" or not admit_symbol(symbol, market).admitted:
        return False
    match = _US_SINGLE_LETTER_SUFFIX.fullmatch(symbol)
    return (
        match is not None and match.group(1) not in US_SUFFIX_REVIEW_HEURISTIC.common_class_letters
    )


@dataclass(frozen=True)
class CurrencyMismatchSeries:
    """A cached series holding bars whose currency is not its market's."""

    symbol: str
    market: str
    #: The market's currency, or ``None`` for a market the table does not know.
    expected: str | None
    mismatched_rows: int
    #: Currencies of the mismatching rows, sorted.
    observed: tuple[str, ...]


@dataclass(frozen=True)
class RefusedSymbol:
    """A symbol admission refuses, with a count and nothing else.

    ``count`` is cached rows for a cached series, position rows for a holding.
    Quantities and costs are never read, so they cannot be reported.
    """

    symbol: str
    market: str
    reason: AdmissionReason
    count: int


@dataclass(frozen=True)
class ReviewSymbol:
    """An admitted symbol listed for manual review (:data:`US_SUFFIX_REVIEW_HEURISTIC`).

    ``count`` is cached rows for a cached series, position rows for a holding.
    """

    symbol: str
    market: str
    count: int


@dataclass(frozen=True)
class CalendarContribution:
    """How much of one market's observed calendar the flagged series supply (C4).

    ``market_trading_days`` treats a date as a session because *any* series of
    the market has a bar on it, so a foreign listing can add sessions the
    market never held. ``only_flagged_dates`` is that estimate: dates on which
    no unflagged series of the market has a bar.
    """

    market: str
    flagged_series: int
    flagged_dates: int
    only_flagged_dates: int


@dataclass(frozen=True)
class CurrencyInventory:
    """Everything :func:`currency_inventory` found; empty tuples mean clean."""

    mismatched: tuple[CurrencyMismatchSeries, ...]
    refused_cached: tuple[RefusedSymbol, ...]
    refused_held: tuple[RefusedSymbol, ...]
    calendar: tuple[CalendarContribution, ...]
    #: Tables the database does not have (nothing to inspect there).
    missing_tables: tuple[str, ...]
    #: (d) admitted, but with an uncommon single-letter suffix (manual review).
    review_cached: tuple[ReviewSymbol, ...] = ()
    review_held: tuple[ReviewSymbol, ...] = ()

    @property
    def has_findings(self) -> bool:
        return bool(
            self.mismatched
            or self.refused_cached
            or self.refused_held
            or self.review_cached
            or self.review_held
        )


def open_read_only(db_path: Path) -> sqlite3.Connection:
    """Open ``db_path`` with SQLite's ``mode=ro``: every write is refused by SQLite.

    A missing file is an error, never created. No pragma that writes (WAL
    switch, schema creation) is issued -- unlike the stores, which all
    initialise their schema on construction and are therefore not used here.
    """
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(name) for (name,) in rows}


def currency_inventory(db_path: Path, *, market_currency: Mapping[str, str]) -> CurrencyInventory:
    """Inventory the bars cache and the book for F-9's three questions, read-only.

    (a) cached series with bars whose ``currency`` differs from
    ``market_currency[market]``; (b) cached series and held symbols that
    :func:`app.data.admission.admit_symbol` refuses (held symbols are checked
    as stored, not canonicalised); (c) per market, how many observed sessions
    the series from (a) and (b) supply, and how many only they supply;
    (d) cached series and held symbols that admission lets through with a
    single-letter suffix outside :data:`US_SUFFIX_REVIEW_HEURISTIC`'s common
    class letters, listed for manual review (not counted in (c)).

    ``market_currency`` is injected (the CLI passes ``MARKET_CURRENCY``) so the
    comparison has one source. The database is opened with ``mode=ro`` and
    only ``SELECT`` is issued; the positions query names ``symbol`` and
    ``market`` alone, so no quantity or cost is ever read.
    """
    with closing(open_read_only(db_path)) as conn:
        tables = _existing_tables(conn)
        missing = tuple(name for name in ("price_bars_cache", "positions") if name not in tables)

        mismatch_rows: dict[tuple[str, str], list[tuple[str, int]]] = {}
        refused_cached: list[RefusedSymbol] = []
        review_cached: list[ReviewSymbol] = []
        dates_by_series: dict[tuple[str, str], set[str]] = {}
        if "price_bars_cache" in tables:
            per_currency = conn.execute(
                """
                SELECT symbol, market, currency, COUNT(*)
                FROM price_bars_cache
                GROUP BY symbol, market, currency
                ORDER BY market, symbol, currency
                """
            ).fetchall()
            rows_by_series: dict[tuple[str, str], int] = {}
            for symbol, market, currency, count in per_currency:
                key = (str(symbol), str(market))
                rows_by_series[key] = rows_by_series.get(key, 0) + int(count)
                if market_currency.get(key[1]) != currency:
                    mismatch_rows.setdefault(key, []).append((str(currency), int(count)))
            for (symbol, market), count in rows_by_series.items():
                if symbol.startswith(_INDEX_PREFIX):
                    continue
                verdict = admit_symbol(symbol, market)
                if not verdict.admitted:
                    refused_cached.append(RefusedSymbol(symbol, market, verdict.reason, count))
                elif needs_suffix_review(symbol, market):
                    review_cached.append(ReviewSymbol(symbol, market, count))
            for symbol, market, trade_date in conn.execute(
                "SELECT symbol, market, trade_date FROM price_bars_cache"
            ):
                dates_by_series.setdefault((str(symbol), str(market)), set()).add(str(trade_date))

        refused_held: list[RefusedSymbol] = []
        review_held: list[ReviewSymbol] = []
        if "positions" in tables:
            held = conn.execute(
                """
                SELECT symbol, market, COUNT(*)
                FROM positions
                GROUP BY symbol, market
                ORDER BY market, symbol
                """
            ).fetchall()
            for symbol, market, count in held:
                verdict = admit_symbol(str(symbol), str(market))
                if not verdict.admitted:
                    refused_held.append(
                        RefusedSymbol(str(symbol), str(market), verdict.reason, int(count))
                    )
                elif needs_suffix_review(str(symbol), str(market)):
                    review_held.append(ReviewSymbol(str(symbol), str(market), int(count)))

    mismatched = tuple(
        CurrencyMismatchSeries(
            symbol=symbol,
            market=market,
            expected=market_currency.get(market),
            mismatched_rows=sum(count for _, count in found),
            observed=tuple(sorted(currency for currency, _ in found)),
        )
        for (symbol, market), found in sorted(
            mismatch_rows.items(), key=lambda item: (item[0][1], item[0][0])
        )
    )
    flagged = set(mismatch_rows) | {(r.symbol, r.market) for r in refused_cached}
    calendar: list[CalendarContribution] = []
    for market in sorted({market for _, market in flagged}):
        flagged_dates: set[str] = set()
        other_dates: set[str] = set()
        for (symbol, series_market), dates in dates_by_series.items():
            if series_market != market:
                continue
            (flagged_dates if (symbol, market) in flagged else other_dates).update(dates)
        calendar.append(
            CalendarContribution(
                market=market,
                flagged_series=sum(1 for _, flagged_market in flagged if flagged_market == market),
                flagged_dates=len(flagged_dates),
                only_flagged_dates=len(flagged_dates - other_dates),
            )
        )
    return CurrencyInventory(
        mismatched=mismatched,
        refused_cached=tuple(sorted(refused_cached, key=lambda r: (r.market, r.symbol))),
        refused_held=tuple(refused_held),
        calendar=tuple(calendar),
        missing_tables=missing,
        review_cached=tuple(sorted(review_cached, key=lambda r: (r.market, r.symbol))),
        review_held=tuple(review_held),
    )


def render_currency_inventory(inventory: CurrencyInventory, *, db_path: Path) -> str:
    """Plain Markdown, symbols and counts only (no quantity, no cost)."""

    def table(header: list[str], rows: list[list[str]]) -> list[str]:
        if not rows:
            return ["(none)"]
        out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        out += ["| " + " | ".join(cells) + " |" for cells in rows]
        return out

    lines = [f"currency inventory (read-only): {db_path}"]
    if inventory.missing_tables:
        lines.append("tables absent: " + ", ".join(inventory.missing_tables))
    lines += ["", "(a) cached series whose bar currency differs from the market currency"]
    lines += table(
        ["symbol", "market", "expected", "observed", "rows"],
        [
            [s.symbol, s.market, s.expected or "-", ",".join(s.observed), str(s.mismatched_rows)]
            for s in inventory.mismatched
        ],
    )
    lines += ["", "(b) cached series refused by symbol admission"]
    lines += table(
        ["symbol", "market", "reason", "rows"],
        [[r.symbol, r.market, r.reason.value, str(r.count)] for r in inventory.refused_cached],
    )
    lines += ["", "(b) held symbols refused by symbol admission"]
    lines += table(
        ["symbol", "market", "reason", "positions"],
        [[r.symbol, r.market, r.reason.value, str(r.count)] for r in inventory.refused_held],
    )
    lines += ["", "(c) observed sessions supplied by the series flagged in (a) and (b)"]
    lines += table(
        ["market", "flagged_series", "dates", "only_from_flagged"],
        [
            [c.market, str(c.flagged_series), str(c.flagged_dates), str(c.only_flagged_dates)]
            for c in inventory.calendar
        ],
    )
    letters = ",".join(sorted(US_SUFFIX_REVIEW_HEURISTIC.common_class_letters))
    for kind, rows, unit in (
        ("cached series", inventory.review_cached, "rows"),
        ("held symbols", inventory.review_held, "positions"),
    ):
        lines += [
            "",
            f"(d) {kind} admitted with a single-letter suffix other than {letters} (manual review)",
        ]
        lines += table(
            ["symbol", "market", unit], [[r.symbol, r.market, str(r.count)] for r in rows]
        )
    return "\n".join(lines)


def _run_currency_inventory(db: str | None) -> int:
    """Exit status: 0 clean, 1 findings, 2 the file could not be read read-only."""
    db_path = Path(db) if db is not None else resolve_db_path()
    try:
        inventory = currency_inventory(db_path, market_currency=MARKET_CURRENCY)
    except sqlite3.Error as error:
        print(f"cannot read {db_path} read-only: {error}", file=sys.stderr)
        return 2
    print(render_currency_inventory(inventory, db_path=db_path))
    return 1 if inventory.has_findings else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.data.diagnose",
        description="逐檔列出每一檔持倉的日線資料狀態（快取、冷卻、可選實際走梯子）。",
    )
    parser.add_argument("--probe", action="store_true", help="實際走一次資料梯子（會連線）")
    parser.add_argument(
        "--clear-cooldown",
        action="store_true",
        help=(
            "對仍在冷卻期內的代號先清除冷卻紀錄（ADR-0009 D-8）。有副作用：不搭配 --probe 時，"
            "下一次正式流量（網頁或排程）會提早向來源重新取得，繞過一次冷卻節流。"
        ),
    )
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    commands = parser.add_subparsers(dest="command")
    inventory_parser = commands.add_parser(
        CURRENCY_INVENTORY_COMMAND,
        help=(
            "read-only: cached series whose currency differs from the market, symbols "
            "refused by admission, and the sessions they supply (task F-9a)"
        ),
    )
    inventory_parser.add_argument(
        "--db",
        default=None,
        help="SQLite file to inspect (default: STOCK_DESK_DB_PATH, else ./data/stock-desk.db)",
    )
    args = parser.parse_args(argv)
    if args.command == CURRENCY_INVENTORY_COMMAND:
        if args.probe or args.clear_cooldown:
            parser.error(
                f"{CURRENCY_INVENTORY_COMMAND} is read-only; drop --probe/--clear-cooldown"
            )
        return _run_currency_inventory(args.db)

    # Imported here so the CLI never builds live adapters unless asked to probe.
    from app.api.deps import (
        get_directory_store,
        get_market_resolver,
        get_position_store,
        get_price_bar_cache,
    )

    rows = diagnose_positions(
        positions=get_position_store(),
        cache=get_price_bar_cache(),
        resolver=get_market_resolver() if args.probe else None,
        directory=get_directory_store(),
        lookback_days=args.lookback_days,
        probe=args.probe,
        clear_cooldown=args.clear_cooldown,
    )
    print(render_report(rows, probed=args.probe))
    return 0 if all(r.verdict == VERDICT_OK for r in rows) else 1


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    sys.exit(main())
