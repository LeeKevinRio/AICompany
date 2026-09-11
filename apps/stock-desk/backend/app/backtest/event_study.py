"""Event study of the five price-only 觀察條件: what followed, historically.

CEO 2026-09-09 asked "歷史上這些條件同時成立之後怎麼走". This module answers it
in the only shape a研究 answer may take here: **a distribution with its sample
size and an interval**, next to the same distribution measured over every bar of
the same period. It never produces a price, a level, a rating or an instruction,
and it never says what to do next.

What is measured
================
An *event* is a bar on which all five conditions of
:func:`app.backtest.strategies.five_condition_series` hold at once. For each
event at bar ``t`` and each horizon ``h`` in :data:`HORIZONS` the forward return
``close[t + h] / close[t] - 1`` is collected. Reported per horizon: sample size,
median, first and third quartile, the share of positive returns and a Wilson 95%
interval for that share.

Point-in-time discipline (backtest-protocol rule 1)
===================================================
The *condition* side reads only bars ``<= t``: it is the very same function the
``five_conditions`` strategy calls on its point-in-time slice, and
``tests/test_backtest_strategies.py`` pins that the vectorised evaluation used
here agrees bar for bar with the sliced one. The *outcome* side is deliberately
in the future -- that is the object of study, not a leak -- and it never feeds
back into which bars count as events. Events whose horizon runs past the last
bar are dropped, not truncated, so the sample size shrinks with the horizon
instead of being padded with a shorter measurement.

Overlapping events
==================
Consecutive bars very often satisfy the conditions together, so their forward
windows overlap and the observations are **not** independent. Nothing is thrown
away because of it -- the full-sample distribution is what the conditions
actually produced -- but the Wilson interval on the full sample would understate
uncertainty, so every horizon additionally reports a **non-overlapping
subsample**: scanning forward, take an event and skip every later event within
``h`` bars (:func:`non_overlapping_indices`). That rule is deterministic and
biased towards earlier events inside a cluster; it is a disclosure device, not a
better estimator, and both numbers are always printed together.

Split
=====
The bar sequence is cut in half by date and each half reported separately
(plus the full period, for the reader who wants the pooled view). Calling the
halves 樣本內 / 樣本外 follows the protocol's vocabulary, with one honesty note
that belongs on every reading of them: **no parameter was fitted on either
half**. The thresholds are the panel's fixed constants, so the second half is a
stability check on numbers that were never estimated from the first, not an
out-of-sample test of a fitted model. A model that was never fitted cannot be
overfitted -- and cannot be credited for surviving a holdout either.

The sixth condition is not here
===============================
「建議引擎本次未命中任何防禦型方向規則」 depends on the holding state and the
advice rule engine and is not computable from a price series; it is excluded
from the strategy and from this study alike. Every number below therefore
describes **five** of the panel's six conditions.

CLI
===
    uv run python -m app.backtest.event_study 2330 --market TW

reads the local ``price_bars_cache`` (the same SQLite cache the API's data chain
falls back to; no network is touched) and prints the tables in Traditional
Chinese. The bar source is echoed on every run, so a ``demo_synthetic`` dataset
can never be mistaken for market data.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.backtest.episodes import ProportionInterval, wilson_interval
from app.backtest.strategies import five_condition_series
from app.data.interface import PriceBar
from app.positions.models import Market
from app.signals.frame import CLOSE, bars_to_frame

#: Forward horizons in trading bars, as asked for by the CEO's question.
HORIZONS: tuple[int, ...] = (5, 10, 20, 60)

#: Confidence level of every interval reported here.
ALPHA = 0.05

#: The forward path is traced bar by bar up to the longest horizon asked for.
PATH_MAX_HORIZON = max(HORIZONS)


@dataclass(frozen=True)
class HorizonStats:
    """The forward-return distribution of one cohort at one horizon.

    ``median`` / ``q1`` / ``q3`` are simple returns (0.012 = +1.2%). The
    ``independent_*`` fields repeat the positive-share measurement over the
    non-overlapping subsample; they are ``None`` exactly when the subsample is
    empty, never silently replaced by the overlapping figure.
    """

    horizon: int
    n: int
    median: float | None
    q1: float | None
    q3: float | None
    n_positive: int
    positive_rate: float | None
    positive_interval: ProportionInterval | None
    independent_n: int
    independent_n_positive: int
    independent_positive_rate: float | None
    independent_positive_interval: ProportionInterval | None


@dataclass(frozen=True)
class PathPoint:
    """The forward-return distribution of one cohort ``horizon`` bars out.

    One point of the bar-by-bar path (``horizon`` runs 1..``PATH_MAX_HORIZON``);
    the same measurement as :class:`HorizonStats` restricted to the three
    quantiles, over the **full** (overlapping) sample. ``n`` shrinks with the
    horizon for the same reason it does in :class:`HorizonStats`.
    """

    horizon: int
    n: int
    median: float | None
    q1: float | None
    q3: float | None


@dataclass(frozen=True)
class CohortReport:
    """One measured set of bars (the events, or the unconditional baseline)."""

    label: str
    #: Bars in the cohort before any horizon truncation.
    n_bars: int
    horizons: tuple[HorizonStats, ...]
    #: Bar-by-bar forward path, horizon 1..``PATH_MAX_HORIZON`` (CEO 2026-09-11
    #: 「CLI 圖形化」: the median line and Q1-Q3 band of the path chart).
    path: tuple[PathPoint, ...] = ()


@dataclass(frozen=True)
class PeriodReport:
    """Events and baseline over one contiguous stretch of the series."""

    label: str
    start_date: str | None
    end_date: str | None
    start_index: int
    stop_index: int
    n_bars: int
    n_events: int
    events: CohortReport
    baseline: CohortReport

    @property
    def event_rate(self) -> float | None:
        """Share of the period's bars on which all five conditions held."""
        return self.n_events / self.n_bars if self.n_bars else None


@dataclass(frozen=True)
class EventStudyReport:
    """The whole study for one symbol: full period plus the two halves."""

    symbol: str
    market: Market
    source: str | None
    n_bars: int
    first_date: str | None
    last_date: str | None
    horizons: tuple[int, ...]
    split_index: int
    split_date: str | None
    periods: tuple[PeriodReport, ...]


def forward_returns(close: np.ndarray, horizon: int) -> np.ndarray:
    """``close[t + horizon] / close[t] - 1`` per bar, ``NaN`` past the end.

    The tail is ``NaN`` rather than measured against the last available bar: a
    20-bar horizon evaluated over 3 bars is not a 20-bar outcome, and padding it
    would quietly mix horizons inside one column.
    """
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    out = np.full(close.shape, np.nan, dtype="float64")
    if close.size > horizon:
        base = close[:-horizon]
        with np.errstate(divide="ignore", invalid="ignore"):
            out[:-horizon] = np.where(base > 0.0, close[horizon:] / base - 1.0, np.nan)
    return out


def non_overlapping_indices(indices: Sequence[int], horizon: int) -> list[int]:
    """A subsample whose ``horizon``-bar forward windows do not overlap.

    Greedy from the earliest bar: keep an index, then skip every index closer
    than ``horizon`` bars to the one kept. Deterministic, and biased towards the
    first event of a cluster -- which is why it is reported *beside* the full
    sample rather than replacing it.
    """
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    kept: list[int] = []
    last = None
    for index in sorted(indices):
        if last is None or index - last >= horizon:
            kept.append(index)
            last = index
    return kept


def _quantiles(values: np.ndarray) -> tuple[float | None, float | None, float | None]:
    if values.size == 0:
        return None, None, None
    q1, median, q3 = (float(v) for v in np.percentile(values, [25.0, 50.0, 75.0]))
    return median, q1, q3


def summarise_horizon(returns: np.ndarray, indices: Sequence[int], horizon: int) -> HorizonStats:
    """Summarise ``returns`` at ``indices`` for one horizon.

    ``indices`` may include bars whose forward return is undefined (too close to
    the end); those are dropped here, which is why ``n`` shrinks as the horizon
    grows.
    """
    usable = [i for i in indices if not np.isnan(returns[i])]
    values = np.asarray([returns[i] for i in usable], dtype="float64")
    median, q1, q3 = _quantiles(values)
    n = int(values.size)
    n_positive = int(np.count_nonzero(values > 0.0))

    independent = non_overlapping_indices(usable, horizon)
    independent_values = np.asarray([returns[i] for i in independent], dtype="float64")
    independent_n = int(independent_values.size)
    independent_positive = int(np.count_nonzero(independent_values > 0.0))

    return HorizonStats(
        horizon=horizon,
        n=n,
        median=median,
        q1=q1,
        q3=q3,
        n_positive=n_positive,
        positive_rate=n_positive / n if n else None,
        positive_interval=wilson_interval(n_positive, n, alpha=ALPHA),
        independent_n=independent_n,
        independent_n_positive=independent_positive,
        independent_positive_rate=(independent_positive / independent_n if independent_n else None),
        independent_positive_interval=wilson_interval(
            independent_positive, independent_n, alpha=ALPHA
        ),
    )


def summarise_path_point(returns: np.ndarray, indices: Sequence[int], horizon: int) -> PathPoint:
    """The three quantiles of ``returns`` at ``indices`` for one path step."""
    values = np.asarray([returns[i] for i in indices if not np.isnan(returns[i])], dtype="float64")
    median, q1, q3 = _quantiles(values)
    return PathPoint(horizon=horizon, n=int(values.size), median=median, q1=q1, q3=q3)


def _cohort(
    label: str,
    *,
    returns_by_horizon: dict[int, np.ndarray],
    indices: Sequence[int],
    horizons: tuple[int, ...],
    path_horizons: tuple[int, ...] = (),
) -> CohortReport:
    return CohortReport(
        label=label,
        n_bars=len(indices),
        horizons=tuple(summarise_horizon(returns_by_horizon[h], indices, h) for h in horizons),
        path=tuple(summarise_path_point(returns_by_horizon[h], indices, h) for h in path_horizons),
    )


def _period(
    label: str,
    *,
    dates: list[str],
    event_flags: np.ndarray,
    returns_by_horizon: dict[int, np.ndarray],
    start: int,
    stop: int,
    horizons: tuple[int, ...],
    path_horizons: tuple[int, ...] = (),
) -> PeriodReport:
    """Build one period report over the half-open bar range ``[start, stop)``.

    A bar belongs to a period by the date **the conditions were observed on**.
    Its forward window may well run past the period's end -- for an event near
    the split that means the outcome is partly measured on bars the next period
    owns. Cutting the outcome at the boundary instead would replace a 20-bar
    return with a shorter one under a 20-bar label, which is the worse
    distortion; the overlap is disclosed rather than removed.
    """
    all_indices = list(range(start, stop))
    event_indices = [i for i in all_indices if bool(event_flags[i])]
    return PeriodReport(
        label=label,
        start_date=dates[start] if all_indices else None,
        end_date=dates[stop - 1] if all_indices else None,
        start_index=start,
        stop_index=stop,
        n_bars=len(all_indices),
        n_events=len(event_indices),
        events=_cohort(
            "五條同時成立",
            returns_by_horizon=returns_by_horizon,
            indices=event_indices,
            horizons=horizons,
            path_horizons=path_horizons,
        ),
        baseline=_cohort(
            "同期所有 bar（無條件基準）",
            returns_by_horizon=returns_by_horizon,
            indices=all_indices,
            horizons=horizons,
            path_horizons=path_horizons,
        ),
    )


def run_event_study(
    frame: pd.DataFrame,
    *,
    symbol: str,
    market: Market = "TW",
    source: str | None = None,
    horizons: tuple[int, ...] = HORIZONS,
) -> EventStudyReport:
    """Study the five-condition events in ``frame`` (an OHLCV frame).

    Reports the full period first, then the two date-ordered halves. The split
    is by bar position (``n // 2``), so both halves hold the same number of bars
    regardless of how the events happen to cluster -- a split chosen from the
    event distribution would be a parameter fitted on the outcome.
    """
    dates = [ts.date().isoformat() for ts in frame.index]
    n = len(frame)
    close = frame[CLOSE].to_numpy(dtype="float64") if n else np.empty(0, dtype="float64")
    event_flags = five_condition_series(frame).all_met if n else np.empty(0, dtype=bool)
    # The path is traced at every bar up to the longest horizon; the summary
    # horizons are a subset of those steps, so one dict serves both.
    path_horizons = tuple(range(1, min(max(horizons), PATH_MAX_HORIZON) + 1)) if horizons else ()
    returns_by_horizon = {h: forward_returns(close, h) for h in set(horizons) | set(path_horizons)}
    split = n // 2

    periods = (
        _period(
            "全期",
            dates=dates,
            event_flags=event_flags,
            returns_by_horizon=returns_by_horizon,
            start=0,
            stop=n,
            horizons=horizons,
            path_horizons=path_horizons,
        ),
        _period(
            "前半（樣本內）",
            dates=dates,
            event_flags=event_flags,
            returns_by_horizon=returns_by_horizon,
            start=0,
            stop=split,
            horizons=horizons,
            path_horizons=path_horizons,
        ),
        _period(
            "後半（樣本外）",
            dates=dates,
            event_flags=event_flags,
            returns_by_horizon=returns_by_horizon,
            start=split,
            stop=n,
            horizons=horizons,
            path_horizons=path_horizons,
        ),
    )
    return EventStudyReport(
        symbol=symbol,
        market=market,
        source=source,
        n_bars=n,
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
        horizons=horizons,
        split_index=split,
        split_date=dates[split] if split < n else None,
        periods=periods,
    )


# --- Traditional-Chinese rendering -------------------------------------------

_RULE = "=" * 78
_THIN = "-" * 78

#: Sentences printed with every run. They are descriptive, never directive: the
#: study reports what a distribution looked like and how uncertain it is, and
#: says out loud what it did not measure.
#: 風控 2026-09-09 REQ-2: printed at the top of every report, right under the
#: data-source line, so a copy that drops the tail still says "five, not six".
SCOPE_NOTICE = (
    "本研究僅涵蓋面板六項觀察條件中的前五條；第 6 條（防禦型規則）未納入。"
    "以下數字皆為「五條」，非「面板」。"
)

#: 風控 2026-09-09 REQ-4: the first line of 「說明與限制」, never after the others.
RESEARCH_USE_NOTICE = (
    "本輸出為歷史分布的描述性統計，僅供研究與教育用途，不構成投資建議，也不是任何買賣指示；"
    "歷史分布不預測未來，任何一次結果都可能落在區間之外。"
)

#: Printed right under the split-point line (scope notice, split point, then
#: this) whenever the bars are the offline demo set.
DEMO_DATA_WARNING = (
    "警告：本次使用的是離線示範資料（demo_synthetic），不是市場資料。"
    "以下數字只能用來驗證計算管線，不能拿來描述任何真實標的。"
)

#: Every sentence below is risk-compliance reviewed and pinned verbatim in
#: ``tests/test_event_study_wording.py``; edits go back through
#: risk-compliance-officer before they land.
FOOTNOTES: tuple[str, ...] = (
    RESEARCH_USE_NOTICE,
    "本研究只涵蓋面板六條中的前五條；第 6 條（建議引擎防禦型規則）依賴持倉狀態與規則引擎，"
    "價格序列算不出來，未納入。所有數字都是「五條」，不是「面板」。",
    "前瞻報酬為收盤對收盤的價格變化，未計手續費、證交稅與滑價，因此不是任何策略的報酬；"
    "含成本的版本請看 walk-forward 回測報告（POST /api/backtest, strategy=five_conditions）。",
    "事件常連續出現，前瞻視窗互相重疊，樣本並不獨立；全樣本的 Wilson 區間會低估不確定性，"
    "故每個橫軸另附非重疊子樣本（同一群集只取最早一根）的比例與區間，兩者並列。",
    "前半／後半只是依日期對半切。本研究沒有擬合任何參數（門檻全部取自面板固定值），"
    "所以後半不是「模型的樣本外」，只是同一組固定門檻在另一段期間的穩定度檢查。",
    "中位數與四分位描述分布位置，不是預測；正報酬比例是歷史頻率，不是對未來的機率。"
    "區間為 Wilson 95%，區間之外的結果本來就可能發生。",
)


def _pct(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value * 100.0:+.2f}%" if signed else f"{value * 100.0:.1f}%"


def _interval(interval: ProportionInterval | None) -> str:
    if interval is None:
        return "—"
    return f"({interval.low * 100.0:.1f}%, {interval.high * 100.0:.1f}%)"


def _cohort_lines(cohort: CohortReport) -> list[str]:
    """Two stacked tables for one cohort: the distribution, then the subsample."""
    lines = [
        f"  {cohort.label}｜起算 bar {cohort.n_bars} 根",
        "    前瞻  樣本     中位數         Q1         Q3   正報酬率  Wilson 95%",
    ]
    for stats in cohort.horizons:
        lines.append(
            f"    {stats.horizon:>4}  {stats.n:>4}  "
            f"{_pct(stats.median, signed=True):>9}  "
            f"{_pct(stats.q1, signed=True):>9}  "
            f"{_pct(stats.q3, signed=True):>9}  "
            f"{_pct(stats.positive_rate):>9}  {_interval(stats.positive_interval)}"
        )
    lines.append("    非重疊子樣本（同一群集只取最早一根）")
    lines.append("    前瞻  樣本   正報酬率  Wilson 95%")
    for stats in cohort.horizons:
        lines.append(
            f"    {stats.horizon:>4}  {stats.independent_n:>4}  "
            f"{_pct(stats.independent_positive_rate):>9}  "
            f"{_interval(stats.independent_positive_interval)}"
        )
    return lines


def format_report(report: EventStudyReport) -> str:
    """Render the study as a Traditional-Chinese plain-text report."""
    # Imported here: the charts module builds on this module's report types.
    from app.backtest.event_study_charts import TERMINAL_GROUP_LEGEND, positive_rate_lines

    lines = [
        _RULE,
        f"五項觀察條件 事件研究 — {report.symbol}（{report.market}）",
        _RULE,
        f"日線 {report.n_bars} 根｜{report.first_date} ～ {report.last_date}"
        f"｜資料來源：{report.source or '未知'}",
        SCOPE_NOTICE,
        f"前後對半切點：bar {report.split_index}（{report.split_date or '—'}）",
    ]
    if report.source == "demo_synthetic":
        lines.append(DEMO_DATA_WARNING)
    for period in report.periods:
        lines.extend(
            [
                _THIN,
                f"【{period.label}】{period.start_date} ～ {period.end_date}"
                f"｜{period.n_bars} 根，其中五條同時成立 {period.n_events} 根"
                f"（{_pct(period.event_rate)}）",
            ]
        )
        lines.extend(_cohort_lines(period.events))
        lines.extend(_cohort_lines(period.baseline))
        # CEO 2026-09-11 CLI 圖形化: one 0-100% ruler per horizon so the two
        # Wilson intervals can be compared without arithmetic (full sample only;
        # the subsample stays in the table above).
        # creative-lead (風控 S2): printed with every period so an excerpt of
        # one period still carries the group definitions.
        lines.append(f"  {TERMINAL_GROUP_LEGEND}")
        lines.extend(positive_rate_lines(period))
    lines.append(_THIN)
    lines.append("說明與限制：")
    lines.extend(f"  - {note}" for note in FOOTNOTES)
    lines.append(_RULE)
    return "\n".join(lines)


# --- CLI ----------------------------------------------------------------------
#
# The two helpers below import the storage layers **inside** the function on
# purpose: everything above this line is pure analysis over a frame, and keeping
# SQLite and the 除權息 store off the module's import surface means a caller (or
# a test) that only wants the statistics never drags a database along.


def _load_cached_bars(
    symbol: str, market: Market, *, start: date, end: date
) -> tuple[list[PriceBar], str | None]:
    """Read bars from the local cache only -- no provider, no network.

    The cache is the last rung of the API's own data chain
    (``app.data.service.MarketDataService``), so this reads the same rows the
    endpoint would fall back to. It deliberately does **not** run the live
    rungs: a research CLI must not spend a provider quota, and an environment
    with no egress would just wait for timeouts.
    """
    from app.data.cache import PriceBarCache

    result = PriceBarCache().get(symbol, market, start, end)
    if result is None:
        return [], None
    return list(result.bars), result.source


def _adjust_for_dividends(
    bars: list[PriceBar], symbol: str, market: Market, *, requested: bool
) -> tuple[list[PriceBar], str]:
    """Back-adjust for 除權息 when the local store can, and say which happened.

    Same store and same adjustment the backtest endpoint uses. The five
    conditions are invariant to the constant factor adjustment introduces
    (proven in ``tests/test_dividends_lookahead.py``), so this changes only the
    measured forward returns -- upwards, wherever a dividend fell inside a
    horizon.
    """
    from app.dividends.adjust import back_adjust_bars
    from app.dividends.store import DividendEventStore

    if not requested:
        return bars, (
            "未還原除權息（--no-adjust-dividends）：報酬不含股利；若該區間實際有配息，報酬會低估。"
        )
    store = DividendEventStore()
    if not store.is_synced():
        return bars, (
            "未還原除權息：本機尚未同步過任何除權息資料"
            "（未執行 uv run python -m app.dividends.sync）；報酬若實際有配息會低估。"
        )
    events = store.events_for(
        symbol, market, start=min(b.date for b in bars), end=max(b.date for b in bars)
    )
    adjustment = back_adjust_bars(bars, events)
    if not adjustment.applied:
        return list(adjustment.bars), (
            "未還原除權息：本機有除權息資料，但查無本商品在此區間可用的紀錄"
            f"（略過 {adjustment.events_skipped} 筆）；報酬若實際有配息會低估。"
        )
    return list(adjustment.bars), (
        f"已還原除權息：套用 {adjustment.events_applied} 筆事件（比例法 back-adjustment）。"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Print the event study for one symbol from the local bar cache."""
    parser = argparse.ArgumentParser(
        prog="python -m app.backtest.event_study",
        description=(
            "五項觀察條件事件研究：找出五條同時成立的日線，統計其後 5/10/20/60 根的"
            "前瞻報酬分布，並與同期無條件基準並列。只讀本機快取，不連外網。"
        ),
    )
    parser.add_argument("symbol", help="標的代號，例如 2330")
    parser.add_argument("--market", default="TW", choices=["TW", "US"], help="市場，預設 TW")
    parser.add_argument("--start", default="1900-01-01", help="起始日 YYYY-MM-DD")
    parser.add_argument("--end", default="2100-01-01", help="結束日 YYYY-MM-DD")
    parser.add_argument(
        "--no-adjust-dividends",
        action="store_true",
        help="不做除權息還原（預設會嘗試還原，並在輸出標明實際結果）",
    )
    parser.add_argument(
        "--html",
        metavar="PATH",
        default=None,
        help="另存自包含的 SVG 圖表頁（路徑圖、正報酬率區間、中位數與四分位）到此路徑",
    )
    args = parser.parse_args(argv)

    market: Market = "US" if args.market == "US" else "TW"
    bars, source = _load_cached_bars(
        args.symbol,
        market,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
    )
    if not bars:
        print(
            f"本機快取中沒有 {market} {args.symbol} 在此區間的日線資料，無法做事件研究。"
            "（離線環境可先執行 uv run python -m app.demo.seed 建立示範資料；"
            "示範資料只能用來驗證計算管線，不能描述任何真實標的。）"
        )
        return 1

    bars, dividend_note = _adjust_for_dividends(
        bars, args.symbol, market, requested=not args.no_adjust_dividends
    )
    report = run_event_study(bars_to_frame(bars), symbol=args.symbol, market=market, source=source)
    print(format_report(report))
    print(f"除權息：{dividend_note}")
    if args.html:
        from datetime import datetime
        from pathlib import Path
        from zoneinfo import ZoneInfo

        from app.backtest.event_study_charts import render_html

        generated_at = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M 台北時間")
        target = Path(args.html)
        target.write_text(
            render_html(report, dividend_note=dividend_note, generated_at=generated_at),
            encoding="utf-8",
        )
        print(f"圖表頁已寫入：{target}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
