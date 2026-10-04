"""Rule set 1.0.3 vs 1.1.0: day-by-day hits of the two drawdown rules.

Rule set 1.1.0 (CEO ruling D1, 2026-10-04) moved ``drawdown_protection`` and
``deep_drawdown_stop`` from ``drawdown.max_drawdown`` (the worst drawdown
anywhere in the observation window) to ``drawdown.current`` (latest close
against the highest close up to that day). Thresholds did not change. This
script replays both conditions over a daily close series and prints, per
trading day, which drawdown rules each version would have matched and which
card action each version would have produced.

Point-in-time replay
--------------------
For every evaluation day ``t`` the signal layer is run on exactly the bars
dated ``t - lookback_days .. t`` -- the same window ``GET /api/advice`` uses
(``DEFAULT_LOOKBACK_DAYS``) -- so no bar after ``t`` can influence day ``t``.
``tests/test_drawdown_rule_diff.py`` appends a future high and checks that no
earlier day changes. Days whose window starts before the first available bar
are flagged ``partial_window``: their ``max_drawdown`` is measured on a shorter
history than the live endpoint would see, so they are reported but kept apart
in the summary.

The 1.0.3 conditions are rebuilt from the shipped 1.1.0 file by swapping the
two conditions' field back to ``drawdown.max_drawdown`` (nothing else differs
between the two versions' conditions); the swap refuses to run if the shipped
file no longer has the shape it expects.

Card actions are computed for a *candidate* (not-held) context: rules reading
``position.*`` are skipped, exactly as the advice endpoint does for a symbol
that is not held. A held position can therefore see a different action; the
drawdown rule hits themselves do not depend on the holding.

Read-only by construction: ``--db-path`` is opened with SQLite ``mode=ro``
(the file is never created, migrated or written), ``--demo`` builds the
synthetic demo series in memory, and nothing touches the network.

Run from ``apps/stock-desk/backend``::

    uv run python scripts/drawdown_rule_diff.py --symbol 3037 --market TW --days 120
    uv run python scripts/drawdown_rule_diff.py --demo --demo-end 2026-10-02
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, cast

from app.advice.context import build_context
from app.advice.engine import build_advice, evaluate_rule
from app.advice.limits import PortfolioContext
from app.advice.loader import Comparison, Rule, RuleSet, load_default_rules
from app.api.signals import DEFAULT_LOOKBACK_DAYS
from app.data.cache import resolve_db_path
from app.data.interface import Market, PriceBar
from app.signals.service import compute_signals

#: The two rules whose condition field changed in 1.1.0, in rule-file order.
DRAWDOWN_RULE_IDS: Final[tuple[str, ...]] = ("drawdown_protection", "deep_drawdown_stop")
NEW_FIELD: Final = "drawdown.current"
OLD_FIELD: Final = "drawdown.max_drawdown"
LEGACY_VERSION: Final = "1.0.3"

#: Same SELECT as ``PriceBarCache.get``, issued on a read-only connection.
_SELECT_BARS: Final = """
SELECT symbol, market, trade_date, open, high, low, close,
       volume, currency, source, as_of
FROM price_bars_cache
WHERE symbol = ? AND market = ? AND trade_date BETWEEN ? AND ?
ORDER BY trade_date ASC
"""


class RuleShapeError(RuntimeError):
    """The shipped rule file no longer has the shape the 1.0.3 rebuild expects."""


def legacy_ruleset(current: RuleSet) -> RuleSet:
    """Rebuild the 1.0.3 conditions from the shipped 1.1.0 rule set.

    Only the field of the two drawdown comparisons is swapped back; thresholds,
    weights, actions, texts and every other rule are taken as-is, which is
    exactly the 1.0.3 -> 1.1.0 difference.
    """
    rules: list[Rule] = []
    swapped: list[str] = []
    for rule in current.rules:
        if rule.id in DRAWDOWN_RULE_IDS:
            condition = rule.condition
            if not isinstance(condition, Comparison) or condition.field != NEW_FIELD:
                raise RuleShapeError(
                    f"{rule.id}: expected a single comparison on {NEW_FIELD}, got {condition!r}"
                )
            legacy = condition.model_copy(update={"field": OLD_FIELD})
            rules.append(rule.model_copy(update={"condition": legacy}))
            swapped.append(rule.id)
        else:
            rules.append(rule)
    if tuple(swapped) != DRAWDOWN_RULE_IDS:
        raise RuleShapeError(f"expected rules {DRAWDOWN_RULE_IDS}, found {tuple(swapped)}")
    return current.model_copy(update={"version": LEGACY_VERSION, "rules": rules})


@dataclass(frozen=True)
class DayRow:
    """One evaluation day under both rule versions."""

    day: date
    close: float
    window_bars: int
    partial_window: bool
    max_drawdown: float | None
    current: float | None
    current_peak_date: str | None
    legacy_hits: tuple[str, ...]
    new_hits: tuple[str, ...]
    legacy_action: str
    new_action: str

    @property
    def hits_changed(self) -> bool:
        return self.legacy_hits != self.new_hits

    @property
    def action_changed(self) -> bool:
        return self.legacy_action != self.new_action


def _drawdown_hits(ruleset: RuleSet, context: dict[str, float | None]) -> tuple[str, ...]:
    by_id = {rule.id: rule for rule in ruleset.rules}
    return tuple(
        rule_id for rule_id in DRAWDOWN_RULE_IDS if evaluate_rule(by_id[rule_id], context).matched
    )


def replay(
    symbol: str,
    bars: Sequence[PriceBar],
    *,
    new_rules: RuleSet,
    legacy_rules: RuleSet,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    last_n: int | None = None,
) -> list[DayRow]:
    """Evaluate both rule versions on every day (or the last ``last_n`` days).

    Day ``t`` sees only bars dated ``t - lookback_days .. t``.
    """
    ordered = sorted(bars, key=lambda bar: bar.date)
    if not ordered:
        return []
    first_day = ordered[0].date
    eval_days = [bar.date for bar in ordered]
    if last_n is not None:
        eval_days = eval_days[-last_n:]
    rows: list[DayRow] = []
    for day in eval_days:
        start = day - timedelta(days=lookback_days)
        window = [bar for bar in ordered if start <= bar.date <= day]
        close = float(window[-1].close)
        signals = compute_signals(symbol, window)
        portfolio = PortfolioContext(symbol=symbol, close=close)
        context = build_context(signals, portfolio)
        dd = signals["risk"]["drawdown"]
        legacy_card = build_advice(
            symbol=symbol, signals=signals, portfolio=portfolio, ruleset=legacy_rules
        )
        new_card = build_advice(
            symbol=symbol, signals=signals, portfolio=portfolio, ruleset=new_rules
        )
        rows.append(
            DayRow(
                day=day,
                close=close,
                window_bars=len(window),
                partial_window=start < first_day,
                max_drawdown=dd.get("max_drawdown"),
                current=dd.get("current"),
                current_peak_date=dd.get("current_peak_date"),
                legacy_hits=_drawdown_hits(legacy_rules, context),
                new_hits=_drawdown_hits(new_rules, context),
                legacy_action=str(legacy_card["action"]),
                new_action=str(new_card["action"]),
            )
        )
    return rows


def read_cached_bars(
    db_path: Path, symbol: str, market: Market, start: date, end: date
) -> list[PriceBar]:
    """Daily bars from the price cache, on a read-only connection.

    The database file is never created: a missing path is an error, and
    ``mode=ro`` makes SQLite refuse every write.
    """
    if not db_path.is_file():
        raise FileNotFoundError(f"cache database not found: {db_path}")
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        rows = conn.execute(
            _SELECT_BARS, (symbol, market, start.isoformat(), end.isoformat())
        ).fetchall()
    bars: list[PriceBar] = []
    for row in rows:
        (sym, mkt, trade_date, open_, high, low, close, volume, currency, source, as_of) = row
        try:
            bars.append(
                PriceBar(
                    symbol=sym,
                    market=mkt,
                    date=date.fromisoformat(trade_date),
                    open=Decimal(open_),
                    high=Decimal(high),
                    low=Decimal(low),
                    close=Decimal(close),
                    volume=volume,
                    currency=currency,
                    as_of=datetime.fromisoformat(as_of),
                    source=source,
                )
            )
        except (InvalidOperation, ValueError):
            continue  # corrupt row: skipped, as PriceBarCache.get does
    return bars


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.2f}%"


def _hits(hits: tuple[str, ...]) -> str:
    return "、".join(hits) if hits else "（無）"


def summarize(rows: Sequence[DayRow]) -> dict[str, int]:
    """Counts over full-window days only (partial-window days reported apart)."""
    full = [row for row in rows if not row.partial_window]
    counts: dict[str, int] = {
        "days": len(rows),
        "full_window_days": len(full),
        "partial_window_days": len(rows) - len(full),
        "hits_changed_days": sum(row.hits_changed for row in full),
        "action_changed_days": sum(row.action_changed for row in full),
    }
    for rule_id in DRAWDOWN_RULE_IDS:
        counts[f"legacy_{rule_id}"] = sum(rule_id in row.legacy_hits for row in full)
        counts[f"new_{rule_id}"] = sum(rule_id in row.new_hits for row in full)
        counts[f"only_legacy_{rule_id}"] = sum(
            rule_id in row.legacy_hits and rule_id not in row.new_hits for row in full
        )
        counts[f"only_new_{rule_id}"] = sum(
            rule_id in row.new_hits and rule_id not in row.legacy_hits for row in full
        )
    return counts


@dataclass(frozen=True)
class Segment:
    """A run of consecutive evaluation days with the same hits in both versions."""

    first: date
    last: date
    days: int
    partial_window: bool
    legacy_hits: tuple[str, ...]
    new_hits: tuple[str, ...]
    action_changes: dict[str, int]
    current_range: tuple[float, float] | None


def segments(rows: Sequence[DayRow]) -> list[Segment]:
    """Collapse the day rows into runs of identical (hits, window) state.

    Lossless for the hits: every day belongs to exactly one run. Action changes
    inside a run are counted per ``legacy->new`` pair.
    """
    runs: list[list[DayRow]] = []
    for row in rows:
        key = (row.legacy_hits, row.new_hits, row.partial_window)
        if (
            runs
            and (runs[-1][-1].legacy_hits, runs[-1][-1].new_hits, runs[-1][-1].partial_window)
            == key
        ):
            runs[-1].append(row)
        else:
            runs.append([row])
    result: list[Segment] = []
    for run in runs:
        changes: dict[str, int] = {}
        for row in run:
            if row.action_changed:
                pair = f"{row.legacy_action}→{row.new_action}"
                changes[pair] = changes.get(pair, 0) + 1
        currents = [row.current for row in run if row.current is not None]
        result.append(
            Segment(
                first=run[0].day,
                last=run[-1].day,
                days=len(run),
                partial_window=run[0].partial_window,
                legacy_hits=run[0].legacy_hits,
                new_hits=run[0].new_hits,
                action_changes=changes,
                current_range=(min(currents), max(currents)) if currents else None,
            )
        )
    return result


def _segment_table(rows: Sequence[DayRow]) -> list[str]:
    lines = [
        "| 起 | 迄 | 日數 | 區間 | 目前回撤範圍 | 1.0.3 命中 | 1.1.0 命中 "
        "| 動作改變（舊→新：日數） |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for seg in segments(rows):
        span = (
            "—"
            if seg.current_range is None
            else f"{_pct(seg.current_range[0])} ～ {_pct(seg.current_range[1])}"
        )
        changes = "、".join(f"{k}：{v}" for k, v in sorted(seg.action_changes.items())) or "—"
        lines.append(
            f"| {seg.first.isoformat()} | {seg.last.isoformat()} | {seg.days} "
            f"| {'不足' if seg.partial_window else '完整'} | {span} | {_hits(seg.legacy_hits)} "
            f"| {_hits(seg.new_hits)} | {changes} |"
        )
    return lines


def render_markdown(
    symbol: str, source: str, rows: Sequence[DayRow], *, all_days: bool = False
) -> str:
    """A Markdown section: summary counts, then the per-day table."""
    counts = summarize(rows)
    lines = [
        f"### {symbol}（來源：{source}）",
        "",
        f"- 評估日數 {counts['days']}（完整觀察區間 {counts['full_window_days']}、"
        f"區間不足 {counts['partial_window_days']}，後者不計入下列統計）",
        f"- 命中組合改變的日數 {counts['hits_changed_days']}；"
        f"卡片動作（未持有試算）改變的日數 {counts['action_changed_days']}",
    ]
    for rule_id in DRAWDOWN_RULE_IDS:
        lines.append(
            f"- {rule_id}：1.0.3 命中 {counts[f'legacy_{rule_id}']} 日 → "
            f"1.1.0 命中 {counts[f'new_{rule_id}']} 日"
            f"（僅舊版 {counts[f'only_legacy_{rule_id}']}、僅新版 {counts[f'only_new_{rule_id}']}）"
        )
    lines += ["", "命中區段（每一個評估日都落在其中一段）：", "", *_segment_table(rows)]
    shown = rows if all_days else [row for row in rows if row.hits_changed or row.action_changed]
    lines += [
        "",
        "逐日明細（預設只列命中或動作有差異的日子；--all-days 列全部）：",
        "",
        "| 日期 | 收盤 | 區間最大回撤 | 目前回撤 | 目前回撤基準高點日 | 1.0.3 命中 | 1.1.0 命中 "
        "| 1.0.3 動作 | 1.1.0 動作 | 區間 |",
        "|---|---:|---:|---:|---|---|---|---|---|---|",
    ]
    for row in shown:
        lines.append(
            f"| {row.day.isoformat()} | {row.close:,.2f} | {_pct(row.max_drawdown)} "
            f"| {_pct(row.current)} | {row.current_peak_date or '—'} | {_hits(row.legacy_hits)} "
            f"| {_hits(row.new_hits)} | {row.legacy_action} | {row.new_action} "
            f"| {'不足' if row.partial_window else f'{row.window_bars} 根'} |"
        )
    if not shown:
        lines.append("| （無差異日） | | | | | | | | | |")
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--symbol", action="append", default=[], help="repeatable")
    parser.add_argument("--market", default="TW", choices=("TW", "US"))
    parser.add_argument("--db-path", type=Path, default=None, help="default: STOCK_DESK_DB_PATH")
    parser.add_argument("--days", type=int, default=None, help="only the last N trading days")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument(
        "--history-days",
        type=int,
        default=None,
        help="calendar days of cache to read (default: lookback + 400)",
    )
    parser.add_argument("--all-days", action="store_true", help="table every day, not only diffs")
    parser.add_argument("--demo", action="store_true", help="use the in-memory demo series")
    parser.add_argument("--demo-end", type=date.fromisoformat, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    new_rules = load_default_rules()
    legacy_rules = legacy_ruleset(new_rules)
    print(f"# 規則集 {legacy_rules.version} vs {new_rules.version}：回撤規則逐日命中對照\n")
    sections: list[str] = []
    if args.demo:
        from app.demo.seed import build_demo_bars  # local: demo-only dependency

        for symbol, bars in build_demo_bars(today=args.demo_end).items():
            if args.symbol and symbol not in args.symbol:
                continue
            rows = replay(
                symbol,
                bars,
                new_rules=new_rules,
                legacy_rules=legacy_rules,
                lookback_days=args.lookback_days,
                last_n=args.days,
            )
            sections.append(
                render_markdown(symbol, "demo_synthetic（合成）", rows, all_days=args.all_days)
            )
    else:
        if not args.symbol:
            print("需要 --symbol（可重複）或 --demo", file=sys.stderr)
            return 2
        db_path = args.db_path if args.db_path is not None else resolve_db_path()
        end = date.today()
        history = args.history_days or args.lookback_days + 400
        for symbol in args.symbol:
            bars = read_cached_bars(
                db_path, symbol, cast(Market, args.market), end - timedelta(days=history), end
            )
            if not bars:
                sections.append(f"### {symbol}\n\n快取中沒有此標的的日線。")
                continue
            sources = "、".join(sorted({bar.source for bar in bars}))
            rows = replay(
                symbol,
                bars,
                new_rules=new_rules,
                legacy_rules=legacy_rules,
                lookback_days=args.lookback_days,
                last_n=args.days,
            )
            sections.append(render_markdown(symbol, sources, rows, all_days=args.all_days))
    print("\n\n".join(sections))
    return 0


if __name__ == "__main__":
    sys.exit(main())
