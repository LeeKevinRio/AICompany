"""L-12 corporate-action scan over the local daily-bar cache (read-only).

Why this exists
---------------
Rule set 1.1.0 reads ``drawdown.current`` = latest close / highest close in the
540-calendar-day window - 1, computed from the locally cached daily closes. If
the cached closes are *unadjusted*, a split (e.g. 1-for-4) makes the series drop
~75% overnight and the card shows a false deep drawdown; a capital reduction or
reverse split makes the series jump up and the drawdown looks shallower than it
is (a rule can be missed). Risk control item L-12 (required, blocks R2) asks:
does any held symbol have such an event inside the 540-day window, on the CEO's
real cache?

What it does
------------
For every held ``(symbol, market)`` (``positions`` table) it reads that
symbol's cached bars (``price_bars_cache``), keeps the window
``[last_bar_date - 540 days, last_bar_date]`` (same 540-day length as the live
window, but anchored on each symbol's own last cached bar; when the cache lags,
this differs from the live window ``[today - 540, today]`` - use ``--as-of`` with
today's date to align), and lists every day whose close moved more than ``--threshold``
(default 30%, adjustable) against the previous cached bar. Each is labelled with a *suspected*
type, never a verdict:

* change <= -45%  -> suspected split
* change >= +45%  -> suspected reverse split / capital reduction
* anything else over the threshold -> needs a human look

Same-day volume ratio (today / previous bar) is shown as corroboration; a ratio
>= 3 or <= 1/3 on the same day as the price jump is listed separately.

The script reads ``price_bars_cache`` only. The live endpoint goes through the
resolver and may fetch newer bars, so the live series can differ from the cache.

Output encoding: the report is written as UTF-8. Use ``--out FILE`` (the script
opens the file itself) rather than shell redirection, which on Windows may
re-encode to cp950 or UTF-16.

Hard guarantees
---------------
* Read-only: the database is opened with SQLite ``mode=ro``; the file is never
  created, migrated or written. Nothing is read from ``.env``. No network.
* No fixing: no value is adjusted, interpolated or filled. A held symbol with no
  cached bars is reported as "no data", not skipped.
* ``--db`` has no default on purpose: it must point at a database explicitly.

Stdlib only (sqlite3, argparse, datetime). Run::

    python corporate_action_scan.py --db <path-to-stock-desk.db> --out L-12_out.md
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

LOOKBACK_DAYS = 540  # mirrors app.signals.window / DEFAULT_LOOKBACK_DAYS
DEFAULT_THRESHOLD = 0.30
SPLIT_CUT = -0.45  # at or below: suspected split
UP_CUT = 0.45  # at or above: suspected reverse split / capital reduction
VOLUME_RATIO = 3.0  # volume up >= 3x or down to <= 1/3 counts as corroboration
GAP_WARN_DAYS = 7  # calendar days between consecutive cached bars worth a note

LABEL_SPLIT = "疑似分割"
LABEL_UP = "疑似反分割／減資"
LABEL_MANUAL = "待人工判斷"


@dataclass(frozen=True)
class Bar:
    day: date
    close: float
    volume: int
    source: str


@dataclass(frozen=True)
class Event:
    day: date
    prev_day: date
    prev_close: float
    close: float
    change: float
    gap_days: int
    label: str
    volume_ratio: float | None  # None when previous volume is 0
    prev_volume: int
    volume: int
    volume_corroborates: bool
    after_peak: bool  # event is after the window's highest close (distorts current drawdown)
    prev_source: str
    source: str


@dataclass
class SymbolScan:
    symbol: str
    market: str
    bars_total: int = 0
    bars_in_window: int = 0
    window_start: date | None = None
    window_end: date | None = None
    sources: tuple[str, ...] = ()
    peak_day: date | None = None
    peak_close: float | None = None
    last_close: float | None = None
    raw_current_drawdown: float | None = None
    min_daily: float | None = None
    max_daily: float | None = None
    events: list[Event] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """Open ``db_path`` strictly read-only; a missing file is an error."""
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def read_scope(conn: sqlite3.Connection, scope: str) -> list[tuple[str, str]]:
    """Distinct ``(symbol, market)`` pairs to scan, sorted by market then symbol."""
    if scope == "holdings":
        if not _has_table(conn, "positions"):
            raise RuntimeError("table 'positions' not found: is this the stock-desk database?")
        rows = conn.execute("SELECT DISTINCT symbol, market FROM positions").fetchall()
    else:
        if not _has_table(conn, "price_bars_cache"):
            raise RuntimeError("table 'price_bars_cache' not found")
        rows = conn.execute("SELECT DISTINCT symbol, market FROM price_bars_cache").fetchall()
    return sorted(((str(s), str(m)) for s, m in rows), key=lambda x: (x[1], x[0]))


def read_bars(conn: sqlite3.Connection, symbol: str, market: str) -> list[Bar]:
    """All cached bars of one series, oldest first. Unparseable rows are an error."""
    rows = conn.execute(
        "SELECT trade_date, close, volume, source FROM price_bars_cache "
        "WHERE symbol = ? AND market = ? ORDER BY trade_date ASC",
        (symbol, market),
    ).fetchall()
    out: list[Bar] = []
    for trade_date, close, volume, source in rows:
        try:
            out.append(
                Bar(
                    day=date.fromisoformat(str(trade_date)),
                    close=float(close),
                    volume=int(volume),
                    source=str(source),
                )
            )
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"cannot parse cached row of {symbol} ({market}) "
                f"trade_date={trade_date!r} close={close!r} volume={volume!r}: {exc}"
            ) from exc
    return out


# --------------------------------------------------------------------------
# Scanning (pure functions; unit-testable without a DB)
# --------------------------------------------------------------------------


def classify(change: float) -> str:
    if change <= SPLIT_CUT:
        return LABEL_SPLIT
    if change >= UP_CUT:
        return LABEL_UP
    return LABEL_MANUAL


def scan_series(
    symbol: str,
    market: str,
    bars: list[Bar],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    as_of: date | None = None,
) -> SymbolScan:
    """Scan one series over ``[end - 540d, end]`` where ``end`` is its last bar
    (or ``as_of`` when given and not later than the last bar)."""
    scan = SymbolScan(symbol=symbol, market=market, bars_total=len(bars))
    if not bars:
        scan.notes.append(
            "快取內沒有任何日線；無法查證（不是「沒有事件」）。"
            "代號大小寫或前後空白與快取內不一致，也會顯示成無資料"
        )
        return scan
    end = bars[-1].day
    if as_of is not None:
        eligible = [b for b in bars if b.day <= as_of]
        if not eligible:
            scan.notes.append(f"快取沒有 {as_of.isoformat()} 以前的日線；無法查證")
            return scan
        bars = eligible
        end = bars[-1].day
    start = end - timedelta(days=LOOKBACK_DAYS)
    window = [b for b in bars if start <= b.day <= end]
    scan.bars_in_window = len(window)
    scan.window_start = window[0].day
    scan.window_end = window[-1].day
    scan.sources = tuple(sorted({b.source for b in window}))
    if len(scan.sources) > 1:
        scan.notes.append("窗內混用多個資料來源：" + "、".join(scan.sources))
    if window[0].day > start + timedelta(days=GAP_WARN_DAYS):
        scan.notes.append(
            f"快取最早日 {window[0].day.isoformat()} 晚於窗起點 {start.isoformat()}："
            "窗前段沒有資料，窗內事件可能被漏掉"
        )

    # Same tie-break as app.signals.risk.current_drawdown: the LAST bar whose
    # close equals the window maximum.
    max_close = max(b.close for b in window)
    peak_bar = [b for b in window if b.close == max_close][-1]
    scan.peak_day, scan.peak_close = peak_bar.day, peak_bar.close
    scan.last_close = window[-1].close
    if len(window) < 2:
        scan.notes.append("窗內不足 2 根日線，線上目前回撤也要求至少 2 根；不計算原始目前回撤")
    elif peak_bar.close > 0:
        scan.raw_current_drawdown = window[-1].close / peak_bar.close - 1.0

    for prev, cur in zip(window, window[1:], strict=False):
        if prev.close <= 0:
            scan.notes.append(f"{prev.day.isoformat()} 收盤價 <= 0，該日起算的變動略過")
            continue
        change = cur.close / prev.close - 1.0
        scan.min_daily = change if scan.min_daily is None else min(scan.min_daily, change)
        scan.max_daily = change if scan.max_daily is None else max(scan.max_daily, change)
        if abs(change) <= threshold:
            continue
        ratio: float | None = None
        corroborates = False
        if prev.volume > 0:
            ratio = cur.volume / prev.volume
            corroborates = ratio >= VOLUME_RATIO or ratio <= 1.0 / VOLUME_RATIO
        scan.events.append(
            Event(
                day=cur.day,
                prev_day=prev.day,
                prev_close=prev.close,
                close=cur.close,
                change=change,
                gap_days=(cur.day - prev.day).days,
                label=classify(change),
                volume_ratio=ratio,
                prev_volume=prev.volume,
                volume=cur.volume,
                volume_corroborates=corroborates,
                after_peak=cur.day > peak_bar.day,
                prev_source=prev.source,
                source=cur.source,
            )
        )
    return scan


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:+.2f}%"


def _num(x: float | None) -> str:
    return "—" if x is None else f"{x:,.2f}"


def _verdict(scan: SymbolScan) -> str:
    if scan.bars_in_window == 0:
        return "無資料"
    if not scan.events:
        return "窗內未見超過門檻的單日變動"
    return f"窗內 {len(scan.events)} 筆超過門檻，需處理"


def render_report(
    scans: list[SymbolScan],
    *,
    db_name: str,
    scope: str,
    threshold: float,
    as_of: date | None,
    generated_at: datetime,
) -> str:
    out: list[str] = []
    out.append("# L-12 公司行動查證輸出")
    out.append("")
    out.append(f"- 產生時間（UTC）：{generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    out.append(f"- 資料庫檔名：`{db_name}`（唯讀開啟，未寫入）")
    out.append(f"- 範圍：{'持股（positions）' if scope == 'holdings' else '快取內全部商品（含非持股）'}；共 {len(scans)} 檔")
    out.append(
        f"- 窗：每檔以自己的最後一根日線為終點往前 {LOOKBACK_DAYS} 日曆日"
        + (f"（限 {as_of.isoformat()} 以前）" if as_of else "")
    )
    out.append(
        f"- 門檻：單日收盤變動幅度絕對值 > {threshold * 100:g}%；"
        f"量能佐證：當日量 / 前一根量 >= {VOLUME_RATIO:g} 或 <= 1/{VOLUME_RATIO:g}"
    )
    out.append(
        "- 變動以「快取內前一根日線」為基準，沒有補值、沒有還原；"
        "「疑似類型」只依幅度分類，不是結論。"
    )
    out.append("")

    out.append("## A. 逐檔總表")
    out.append("")
    out.append(
        "| 代號 | 市場 | 窗內根數 | 窗起 | 窗迄 | 來源 | 窗內最高收盤（日） | 最新收盤 | "
        "原始目前回撤 | 單日最大跌／漲 | 超過門檻筆數 | 判定 |"
    )
    out.append("|" + "---|" * 12)
    for s in scans:
        peak = (
            f"{_num(s.peak_close)}（{s.peak_day.isoformat()}）"
            if s.peak_day and s.peak_close is not None
            else "—"
        )
        out.append(
            "| "
            + " | ".join(
                [
                    s.symbol,
                    s.market,
                    str(s.bars_in_window),
                    s.window_start.isoformat() if s.window_start else "—",
                    s.window_end.isoformat() if s.window_end else "—",
                    "、".join(s.sources) or "—",
                    peak,
                    _num(s.last_close),
                    _pct(s.raw_current_drawdown),
                    f"{_pct(s.min_daily)}／{_pct(s.max_daily)}",
                    str(len(s.events)),
                    _verdict(s),
                ]
            )
            + " |"
        )
    flagged = [s for s in scans if s.events]
    nodata = [s for s in scans if s.bars_in_window == 0]
    out.append("")
    out.append(
        f"共 {len(scans)} 檔：{len(flagged)} 檔窗內有超過門檻的單日變動"
        + ("（" + "、".join(f"{s.symbol}" for s in flagged) + "）" if flagged else "")
        + f"；{len(nodata)} 檔無快取資料"
        + ("（" + "、".join(f"{s.symbol}" for s in nodata) + "）" if nodata else "")
        + "。"
    )
    out.append("")
    out.append(
        "「原始目前回撤」＝最新收盤 ÷ 窗內最高收盤 - 1，直接用快取收盤算，公式與規則集 1.1.0 "
        "`drawdown.current` 相同；窗長同為 540 日，但本腳本以各檔最後一根日線為終點，"
        "快取落後時與線上窗 [今天-540, 今天] 不同（需對齊時用 `--as-of` 帶今天日期）；"
        "且本腳本只讀 `price_bars_cache`，線上經 resolver 可能補抓到較新的日線。"
        "僅供對照事件是否已進入該數值，不是還原後的值。"
    )

    out.append("")
    out.append("## B. 超過門檻的單日變動（事件明細）")
    out.append("")
    events = [(s, e) for s in scans for e in s.events]
    if not events:
        out.append("窗內沒有任何持股出現超過門檻的單日收盤變動。")
        out.append("")
        out.append(
            "（這只代表**快取內相鄰兩根**沒有超過門檻；若快取有缺漏、或「無資料」檔數 > 0，"
            "見 §D，不能直接當作「沒有公司行動」。）"
        )
    else:
        out.append(
            "| 代號 | 日期 | 前一根日期 | 前收 | 當日收 | 幅度 | 間隔（日曆日） | 疑似類型 | "
            "量（前→當日） | 量比 | 量能佐證 | 事件在窗內高點之後 | 來源（前→當日） |"
        )
        out.append("|" + "---|" * 13)
        for s, e in events:
            ratio = "前量為 0" if e.volume_ratio is None else f"{e.volume_ratio:.2f}x"
            vol_note = (
                f"有（同日量能放大／縮小逾 {VOLUME_RATIO:g} 倍）" if e.volume_corroborates else "無"
            )
            src = e.prev_source if e.prev_source == e.source else f"{e.prev_source}→{e.source}"
            out.append(
                "| "
                + " | ".join(
                    [
                        s.symbol,
                        e.day.isoformat(),
                        e.prev_day.isoformat(),
                        _num(e.prev_close),
                        _num(e.close),
                        _pct(e.change),
                        str(e.gap_days),
                        e.label,
                        f"{e.prev_volume:,}→{e.volume:,}",
                        ratio,
                        vol_note,
                        "是" if e.after_peak else "否",
                        src,
                    ]
                )
                + " |"
            )
        out.append("")
        out.append(
            "「事件在窗內高點之後」＝是：該跳動已落在最高收盤日之後，會直接進入 `drawdown.current`；"
            "否：事件在高點之前，高點本身已是事件後的價位，對目前回撤的影響較小，但仍需看 §A 的最高收盤是否合理。"
        )

    out.append("")
    out.append("## C. 價量同日佐證")
    out.append("")
    corr = [(s, e) for s, e in events if e.volume_corroborates]
    if not corr:
        out.append(f"沒有任何事件同日出現量能放大／縮小逾 {VOLUME_RATIO:g} 倍。")
    else:
        out.append("| 代號 | 日期 | 價格幅度 | 量比 | 疑似類型 |")
        out.append("|---|---|---|---|---|")
        for s, e in corr:
            assert e.volume_ratio is not None
            out.append(
                f"| {s.symbol} | {e.day.isoformat()} | {_pct(e.change)} | "
                f"{e.volume_ratio:.2f}x | {e.label} |"
            )
    out.append("")
    out.append(
        "量比無佐證不代表不是公司行動（分割後量能常是漸進放大），有佐證也不代表一定是；"
        "判定仍須對照交易所公告（見 README）。"
    )

    out.append("")
    out.append("## D. 資料缺口與品質備註")
    out.append("")
    any_note = False
    for s in scans:
        gap_events = [e for e in s.events if e.gap_days > GAP_WARN_DAYS]
        notes = list(s.notes)
        for e in gap_events:
            notes.append(
                f"{e.day.isoformat()} 事件與前一根相隔 {e.gap_days} 日曆日：中間可能缺資料，"
                "幅度可能是多日累計而非單日"
            )
        for e in s.events:
            if e.prev_source != e.source:
                notes.append(
                    f"{e.day.isoformat()} 事件前後來源不同（{e.prev_source}→{e.source}）："
                    "先排除是來源口徑差異（還原／未還原）造成的假跳動"
                )
        for n in notes:
            any_note = True
            out.append(f"- `{s.symbol}`（{s.market}）：{n}")
    if not any_note:
        out.append("無額外備註。")

    out.append("")
    out.append("## E. 本輸出的限制")
    out.append("")
    out.append("- 只讀 `price_bars_cache` 的收盤與成交量；不讀除權息表、不連網、不查交易所公告。")
    out.append(
        f"- 台股一般股票漲跌幅限制為 ±10%，超過 {threshold * 100:g}% 的單日變動幾乎必為公司行動或資料錯誤；"
        "ETF 與美股不適用此推論。"
    )
    out.append(
        "- 窗以各檔最後一根快取日線為終點；快取落後時與線上窗 [今天-540, 今天] 不同，"
        "需對齊線上窗請加 `--as-of` 帶今天日期。本腳本只讀 `price_bars_cache`，"
        "線上經 resolver 可能補抓到較新的日線。"
    )
    out.append("- 門檻以下的小幅公司行動（例如 1 拆 1.2、小額減資）不會被列出。")
    out.append("- 資料來源（TWSE／TPEx／FinMind）是否回還原價，見 README 的「依程式碼判讀」，上游實際行為**未查證**。")
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="corporate_action_scan.py",
        description="L-12: list large single-day close moves in the 540-day window "
        "of held symbols (read-only).",
    )
    p.add_argument("--db", required=True, help="path to the stock-desk SQLite database (opened read-only)")
    p.add_argument(
        "--out",
        default=None,
        help="write the report to this file as UTF-8 (recommended on Windows instead of '>')",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="absolute single-day close change to list, as a fraction (default 0.30)",
    )
    p.add_argument(
        "--scope",
        choices=("holdings", "all"),
        default="holdings",
        help="holdings (default): positions table; all: every cached series",
    )
    p.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="optional YYYY-MM-DD; use only bars on or before this date",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp950; keep stdout/stderr UTF-8 for cmd.exe redirection.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = _parse_args(argv)
    if args.threshold <= 0:
        print("error: --threshold must be > 0", file=sys.stderr)
        return 2
    db_path = Path(args.db)
    try:
        with closing(open_readonly(db_path)) as conn:
            if not _has_table(conn, "price_bars_cache"):
                print("error: table 'price_bars_cache' not found", file=sys.stderr)
                return 2
            pairs = read_scope(conn, args.scope)
            scans = [
                scan_series(sym, mkt, read_bars(conn, sym, mkt), threshold=args.threshold, as_of=args.as_of)
                for sym, mkt in pairs
            ]
    except (FileNotFoundError, RuntimeError, sqlite3.Error, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = render_report(
        scans,
        db_name=db_path.name,
        scope=args.scope,
        threshold=args.threshold,
        as_of=args.as_of,
        generated_at=datetime.now(UTC),
    )
    if args.out:
        # Refuse to write the report over the database itself.
        if Path(args.out).resolve() == db_path.resolve():
            print("error: --out must not point at the --db file", file=sys.stderr)
            return 2
        try:
            with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(report + "\n")
        except OSError as exc:
            print(f"error: cannot write --out file: {exc}", file=sys.stderr)
            return 2
        print(f"report written to {args.out}", file=sys.stderr)
    else:
        print(report)
    if not scans:
        print("\n（範圍內沒有任何商品；若預期有持股，請確認 --db 指到正確的檔案。）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
