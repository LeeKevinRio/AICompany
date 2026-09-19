"""CEO 本機體檢工具 -- 逐檔列出每一檔持倉的日線資料狀態。

    uv run python -m app.data.diagnose                 # 只看本機快取與冷卻狀態，不連線
    uv run python -m app.data.diagnose --probe         # 另外實際走一次資料梯子（會連線）
    uv run python -m app.data.diagnose --probe --clear-cooldown   # 先清掉冷卻再走梯子

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
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.data.cache import PriceBarCache
from app.data.freshness import policy_for
from app.data.interface import DataStatus
from app.directory.store import SecurityDirectoryStore
from app.positions.models import Market
from app.positions.store import PositionStore
from app.services.market import MarketDataResolver, load_bars, trading_days_behind_market

#: Same window the scheduler warms (``app/scheduler.py``), so "what the cache
#: holds" is judged over the range the product actually reads.
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
    args = parser.parse_args(argv)

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
