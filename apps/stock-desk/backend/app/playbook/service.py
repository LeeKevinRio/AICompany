"""Wiring: load bars, build snapshots, run the engine, persist what it decided.

The engine is pure and the store only writes; this module is the one place that
does both, so there is exactly one path from "the market closed" to "these are
today's lines and this is the new state".

Order of a run:

1. Load daily bars for every target symbol and for 加權指數 ``^TWII`` through the
   existing degradation ladder (nothing new is fetched directly).
2. Build the trading calendar from the dates the market actually produced bars
   on, and take 依據資料日 ``T`` as the latest bar date seen.
3. Read the parameter version already effective on ``T`` (鐵律④), the batches,
   the symbol flags and the portfolio state.
4. Evaluate, then persist: schedule-state effects, then -- under one write
   lock -- the new decisions' directive log rows (風控 R16), schedule rows and
   line-bound effects (ADR-0035).

The peak close (波段最高收盤) is rolled forward before evaluation, because the
trailing stop reads it on the same day's close.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

from app.data.calendar import TradingCalendar
from app.data.interface import PriceBar
from app.playbook import indicators, wording
from app.playbook.engine import (
    emergency_mode_reason,
    evaluate,
    is_usable,
    planned_batch_shares,
    settle_directive,
)
from app.playbook.models import (
    BatchState,
    BatchStatus,
    Directive,
    EmergencyExitResult,
    ExitConfirm,
    FastMarketState,
    IndexSnapshot,
    MarketSnapshot,
    PendingExitBlock,
    PendingExitCoverage,
    PendingExitRow,
    PendingExitSection,
    PlaybookEvaluation,
    PortfolioState,
    RebalanceResult,
    RuleChangeReceipt,
    RuleParams,
    RuleSetStatus,
    SettledLine,
    SettlementResult,
    UnsettledLine,
)
from app.playbook.store import (
    LINE_BOUND_EFFECTS,
    ORDER_ACTIONS,
    R_SERIES_RULE_IDS,
    EmergencyExitState,
    EntryBeforeExitRead,
    EvaluationCommit,
    PendingDirective,
    PendingExitRead,
    PlaybookStore,
    decision_key,
)
from app.positions.models import Market
from app.services.index import IndexServiceResolver, load_market_benchmark
from app.services.market import MarketDataResolver, load_bars

#: Calendar days of history requested per symbol. Enough for a 25-day MA, a
#: 20-day monthly line and the 20-day volatility with holidays in between.
LOOKBACK_DAYS = 180

#: The market this rule set trades. The 加權指數 benchmark is TW's ``^TWII``.
PLAYBOOK_MARKET: Market = "TW"

#: MA window for BIAS25 / S1 recovery -- the rule set's 25MA.
MA25_WINDOW = 25

#: ``total_deploy_source`` written by :meth:`PlaybookService.rebalance` (D-2).
REBALANCE_SOURCE = "quarterly_rebalance"

#: ``total_deploy_source`` written by :meth:`PlaybookService.confirm_rules` (D-2).
#: A capital figure that came from the user confirming a rule set is traceable to
#: that action and to nothing else, so it does not share ``REBALANCE_SOURCE``.
CONFIRMATION_SOURCE = "user_confirmation"


def build_calendar(*bar_groups: Sequence[PriceBar]) -> TradingCalendar:
    """A calendar of every date any loaded series produced a bar on."""
    days: set[date] = set()
    for bars in bar_groups:
        days.update(bar.date for bar in bars)
    return TradingCalendar(days)


def latest_bar_date(*bar_groups: Sequence[PriceBar]) -> date | None:
    """依據資料日 ``T``: the latest date any loaded series produced a bar on.

    ``None`` when nothing came back at all -- the caller decides what a day with
    no data is, rather than getting a date this function made up (鐵律⑤).
    """
    return max((bar.date for bars in bar_groups for bar in bars), default=None)


class LoadedSeries(NamedTuple):
    """One symbol's bars as the data ladder returned them, with its provenance."""

    bars: list[PriceBar]
    status: str
    source: str
    #: ``ProviderResult.reason`` -- carried into the snapshot and every
    #: directive issued from it (風控 2026-09-15 R3), never dropped here.
    reason: str | None = None


#: What a symbol the ladder never answered for looks like.
NOTHING_LOADED = LoadedSeries([], "unavailable", "none", None)


def build_market_snapshot(
    symbol: str,
    bars: Sequence[PriceBar],
    *,
    status: str,
    source: str,
    reason: str | None = None,
    high_volatility: bool = False,
) -> MarketSnapshot | None:
    """One symbol's snapshot, or ``None`` when no bar came back at all."""
    ordered = indicators.sorted_closes(bars)
    if not ordered:
        return None
    latest = ordered[-1]
    ma25 = indicators.moving_average(ordered, MA25_WINDOW)
    return MarketSnapshot(
        symbol=symbol,
        data_date=latest.date,
        close=latest.close,
        change_pct=indicators.change_pct(ordered),
        ma25=ma25,
        bias25=indicators.bias(latest.close, ma25),
        data_status=status,
        source=source,
        data_reason=reason,
        high_volatility=high_volatility,
    )


def build_index_snapshot(
    bars: Sequence[PriceBar],
    *,
    status: str,
    source: str,
    params: RuleParams,
    reason: str | None = None,
) -> IndexSnapshot | None:
    """加權指數 snapshot: 月線, its run of closes below it, and the fast-market pair."""
    ordered = indicators.sorted_closes(bars)
    if not ordered:
        return None
    latest = ordered[-1]
    monthly = indicators.moving_average(ordered, params.index_monthly_line_window)
    return IndexSnapshot(
        data_date=latest.date,
        close=latest.close,
        monthly_line=monthly,
        days_below_monthly_line=indicators.consecutive_days_below(
            ordered, params.index_monthly_line_window
        ),
        annualized_vol_20d=indicators.annualized_volatility(ordered),
        large_move_days=indicators.large_move_days(
            ordered,
            lookback=params.fast_market_lookback_days,
            threshold=params.fast_market_move_pct,
        ),
        data_status=status,
        source=source,
        data_reason=reason,
    )


def effective_freeze_until(*, stored: date | None, computed: date) -> date:
    """The 恢復日 an exit leaves in force: the later of the two (CEO #77, C-5).

    ``computed`` is ``emergency_freeze_trading_days`` shifted from the
    submission day; ``stored`` is the 恢復日 already on the book. Taking the
    later one means an exit can extend a freeze but never shorten it -- which
    also closes the 「縮短凍結」 path a later change of the parameter would
    otherwise open (附錄 D F3). One function, so the confirmation screen and
    the exit cannot apply two different rules.
    """
    return computed if stored is None else max(stored, computed)


def build_exit_confirm(
    *,
    params: RuleParams,
    calendar: TradingCalendar,
    as_of: date,
    stored_until: date | None,
) -> ExitConfirm:
    """The EMERGENCY_EXIT confirmation facts, counted for ``as_of``.

    Computed the same way :meth:`PlaybookService.emergency_exit` computes the
    freeze it will actually apply -- ``params.emergency_freeze_trading_days``
    shifted from the *submission* day on the trading calendar, kept at the
    stored 恢復日 when that one is later (:func:`effective_freeze_until`) -- so
    a screen that renders this block states the freeze the user is about to
    get, not a mirrored default (覆審: 天數與日期皆為參數與日曆的函數，不得寫死;
    ADR-0033 C-5). When the stored date is the one kept, check 2 is 風控 S9.

    The prediction walks days after ``as_of``, which are past the last observed
    bar, so it resolves through the calendar's documented weekday fallback in
    both cases; that is the same answer the exit itself reaches on that day.
    """
    freeze_days = params.emergency_freeze_trading_days
    computed = calendar.shift(as_of, freeze_days)
    freeze_until = effective_freeze_until(stored=stored_until, computed=computed)
    return ExitConfirm(
        freeze_days=freeze_days,
        freeze_until=freeze_until,
        checks=list(
            wording.exit_confirm_checks(
                freeze_days=freeze_days,
                freeze_until=freeze_until,
                freeze_kept=freeze_until != computed,
            )
        ),
    )


def exit_line_still_covers(directive: Directive, bars: Sequence[PriceBar]) -> bool:
    """判準 Z (CEO #87／#89, 風控 2026-10-31): does this unsettled EMERGENCY sell cover its batch?

    It stops covering only when **both** hold on the symbol's loaded daily
    series: (1) a bar dated after its 預定執行日 E exists, and (2) no bar dated E
    exists (a window that does not reach E counts as "no bar"). Then the
    settlement can never stamp it -- E had no opening price while the market
    moved on -- so the exit may write a new line for the batch.

    Every other case still covers, by design:

    * E has a bar but the line is unsettled -- the exit does not settle first,
      so a user who skipped ``/today`` for a day would otherwise be sent to sell
      a second time (R10). Condition (2) is what keeps this case covered.
    * Nothing after E yet, or the load failed / came back empty -- a duplicate
      sell does more harm than an exit held back for a day; S3 says so.

    ``bars`` must be the series :meth:`PlaybookService.settle_pending` would
    use: the same loader (``_load_symbol_bars``), the same window, closed
    sessions only (the data layer drops an unfinished one). Never the weekday
    calendar, the index or another symbol. Pure, so it runs under the lock (C-3).
    """
    days = {bar.date for bar in bars}
    execution = directive.execution_date
    return execution in days or not any(day > execution for day in days)


@dataclass(frozen=True)
class ExitPlan:
    """What one EMERGENCY_EXIT decided under the write lock (ADR-0033).

    Satisfies :class:`app.playbook.store.EmergencyExitWrite`: the store writes
    ``directives`` and ``emergency_until`` from it; the rest is what the
    response describes.
    """

    #: Lines for the held batches no unsettled EMERGENCY sell still covers.
    directives: list[Directive]
    #: DATA_GAP_NOTE for every new line whose symbol had no bar (風控 R5).
    warnings: list[str]
    #: The batches that were covered already, as read under the lock.
    covered: list[BatchState]
    #: **Every** line that still covers a covered batch under 判準 Z, oldest
    #: first (C-4). A database written before N-166 may hold two for one batch,
    #: possibly with different 預定執行日; both stay listed (風控 第二次裁示
    #: 第 2 項). Counts come from ``covered``, never from here, so they do not
    #: double. Lines that no longer cover are in ``stale`` instead.
    pending: list[PendingDirective]
    #: Held batches with unsettled EMERGENCY lines that no longer cover them
    #: (S10), whether or not another line still does (風控: 第三次出清仍列).
    stale: list[wording.ExitStale]
    rules_version: int
    #: :func:`effective_freeze_until` of the stored and the computed 恢復日.
    emergency_until: date


def _is_exit_sell(directive: Directive) -> bool:
    """An EMERGENCY_EXIT sell line -- the only kind 判準 Z, N1 and N2 speak about."""
    return directive.rule_id == "EMERGENCY" and directive.action == "sell"


class ExitBatchClass(NamedTuple):
    """One open batch and its unsettled EMERGENCY sells, split under 判準 Z.

    ``live`` still cover the batch, ``stale`` no longer do; both keep the
    order of :attr:`EmergencyExitState.covering` (oldest first). A batch with
    neither is still listed -- the exit writes it a new line.
    """

    batch: BatchState
    live: list[PendingDirective]
    stale: list[PendingDirective]


def classify_exit_batches(
    state: EmergencyExitState, series_for: Callable[[str], Sequence[PriceBar]]
) -> list[ExitBatchClass]:
    """判準 Z for every open batch of ``state``, one entry each, in batch order. Pure.

    The single place EMERGENCY sells are told apart (ADR-0039 Decision 3,
    N171-C2″): :func:`plan_emergency_exit` decides from it under the write
    lock, and ``/today``'s pending-exit block classifies with it after the
    settlement. Each line is judged by :func:`exit_line_still_covers` alone,
    on ``series_for(symbol)`` -- the exit's preloaded series, or on ``/today``
    the very series the settlement judged N1 on (``SettlementRun.loaded``), so
    the two pages of one response cannot disagree (風控 P-1). A line without a
    ``batch_no`` belongs to no batch and is in no entry.
    """
    lines: dict[tuple[str, int], list[PendingDirective]] = {}
    for item in state.covering:
        if item.directive.batch_no is not None:
            lines.setdefault((item.directive.symbol, item.directive.batch_no), []).append(item)

    classes: list[ExitBatchClass] = []
    for batch in state.open_batches:
        bars = series_for(batch.symbol)
        live: list[PendingDirective] = []
        stale: list[PendingDirective] = []
        for item in lines.get((batch.symbol, batch.batch_no), []):
            (live if exit_line_still_covers(item.directive, bars) else stale).append(item)
        classes.append(ExitBatchClass(batch=batch, live=live, stale=stale))
    return classes


def plan_emergency_exit(
    state: EmergencyExitState,
    *,
    loaded: Mapping[str, LoadedSeries],
    params: RuleParams,
    as_of: date,
    execution_date: date,
    computed_until: date,
) -> ExitPlan:
    """Decide an EMERGENCY_EXIT from the state read under the lock. Pure.

    Called by :meth:`PlaybookStore.commit_emergency_exit` with the write lock
    held, so it touches nothing but its arguments (C-3): prices, calendar and
    parameters were loaded before the lock was taken. A batch that only
    appeared under the lock -- its symbol never preloaded -- is liquidated all
    the same, through the :data:`NOTHING_LOADED` path with a
    :data:`wording.DATA_GAP_NOTE` (風控 R5), exactly like a symbol whose load
    came back empty.

    Only uncovered batches get a line (C-4 as narrowed by CEO #87／#89): a batch
    with an unsettled EMERGENCY sell that still covers it under
    :func:`exit_line_still_covers` keeps it, and it is reported instead -- with
    every such line. Lines that no longer cover are reported as ``stale``
    (S10) and are not cancelled. Which line is which is
    :func:`classify_exit_batches`'s call.
    """
    directives: list[Directive] = []
    warnings: list[str] = []
    covered: list[BatchState] = []
    stale: list[wording.ExitStale] = []
    live_ids: set[int] = set()
    for entry in classify_exit_batches(
        state, lambda symbol: loaded.get(symbol, NOTHING_LOADED).bars
    ):
        batch = entry.batch
        series = loaded.get(batch.symbol, NOTHING_LOADED)
        if entry.stale:
            stale.append(
                wording.ExitStale(
                    symbol=batch.symbol,
                    batch_no=batch.batch_no,
                    shares=batch.remaining_shares,
                    dates=tuple(item.directive.execution_date for item in entry.stale),
                )
            )
        if entry.live:
            covered.append(batch)
            live_ids.update(item.directive_id for item in entry.live)
            continue
        snapshot = build_market_snapshot(
            batch.symbol,
            series.bars,
            status=series.status,
            source=series.source,
            reason=series.reason,
        )
        if snapshot is None:
            warnings.append(
                wording.DATA_GAP_NOTE.format(
                    symbol=batch.symbol, status=series.status, source=series.source
                )
            )
        directives.append(
            Directive(
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                action="sell",
                shares=batch.remaining_shares,
                rule_id="EMERGENCY",
                rule_summary=(
                    f"{wording.rule_text('EMERGENCY', params)}｜出清 {batch.remaining_shares} 股"
                ),
                data_date=snapshot.data_date if snapshot else as_of,
                execution_date=execution_date,
                reference_price=snapshot.close if snapshot else None,
                limit_low=None,
                limit_high=None,
                limit_note=wording.EMERGENCY_EXIT_NO_BAND_NOTE,
                data_status=series.status,
                source=series.source,
                data_reason=series.reason,
            )
        )
    # A line of a batch that is no longer open (a pre-N-166 duplicate whose
    # twin already settled it) covers nothing held, so it is not reported.
    return ExitPlan(
        directives=directives,
        warnings=warnings,
        covered=covered,
        pending=[item for item in state.covering if item.directive_id in live_ids],
        stale=stale,
        rules_version=params.version,
        emergency_until=effective_freeze_until(
            stored=state.emergency_until, computed=computed_until
        ),
    )


#: 風控 2026-11-01 解讀點 (c): the logged actions SAME_DAY_EARLIER_DECISIONS_DATA_GAP_NOTE
#: counts -- decisions that place no order. 買賣 lines are ``ORDER_ACTIONS``; an
#: action in neither tuple is not counted by either sentence.
DECISION_RECORD_ACTIONS: tuple[str, ...] = ("defer", "skip")


def _is_r_series(directive: Directive) -> bool:
    return directive.rule_id in R_SERIES_RULE_IDS


def _insert_after(warnings: list[str], anchor: str, note: str) -> None:
    """Put ``note`` right after ``anchor``; at the end if ``anchor`` is not there."""
    position = warnings.index(anchor) + 1 if anchor in warnings else len(warnings)
    warnings.insert(position, note)


def same_day_warnings(
    evaluation: PlaybookEvaluation,
    commit: EvaluationCommit,
    *,
    markets: Mapping[str, MarketSnapshot],
    batches: Sequence[BatchState],
    portfolio: PortfolioState,
) -> list[str]:
    """The evaluation's warnings, reconciled with the logged list the page shows.

    ADR-0035 Decision 4 lists the 預定執行日's logged lines, which an earlier
    run of the same day may have decided (S-α), so the sentences this run's
    engine wrote are checked against them (風控 CEO #87 回審 二-1、二-3). Every
    condition is read from structured data -- the lines, the mode, the
    snapshots -- never from another sentence (題 12 allowlist). Sentences are
    only located, to drop or to anchor one, by the exact text their own
    template renders for the same values.

    * **Shrink notes of a K2-blocked R decision are dropped** (二-3 第 2 點).
      The symbol's R line on the page is the earlier run's, and its own
      ``rule_summary`` already carries the shrink that applied to it.
    * **INDEX_DATA_GAP_DEFER_NOTE needs an M1 deferral on the list** (二-3
      第 3 點): without one, 「計入順延次數（逐批列示）」 is not true.
    * **SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE** (A, 二-3 第 4 點) and
      **SAME_DAY_EARLIER_DECISIONS_DATA_GAP_NOTE** (B, 風控 2026-11-01 (c))
      follow, in that order, the DATA_GAP_NOTE／DATA_GAP_HOLDING_NOTE of a
      symbol whose data is unusable now: A counts its listed 買賣 lines
      (``ORDER_ACTIONS``), B its 順延／跳過 records
      (:data:`DECISION_RECORD_ACTIONS`); each only when its count is one or
      more. Missing anchors put them at the end of the list.
    * **SAME_DAY_EARLIER_ENTRY_NOTE** (二-1) when the list has an R-series buy
      this run produced no buy of the same K1 for: right after FROZEN_NOTE when
      the mode is not ``normal`` (the condition FROZEN_NOTE is written on),
      otherwise first.
    """
    warnings = list(evaluation.warnings)
    logged = commit.logged
    written_r = {directive.symbol for directive in commit.written if _is_r_series(directive)}
    blocked_r = {directive.symbol for directive in logged if _is_r_series(directive)} - written_r

    # The engine's two 鐵律① sentences, rendered for the blocked symbols. The
    # 「{symbol}：」 prefix is the engine's own (``_apply_cash_floor``).
    stale: set[str] = {
        wording.SHRINK_TO_ZERO_NOTE.format(symbol=batch.symbol, batch_no=batch.batch_no)
        for batch in batches
        if batch.symbol in blocked_r
    }
    for directive in evaluation.directives:
        if (
            directive.symbol not in blocked_r
            or directive.action != "buy"
            or directive.batch_no is None
            or directive.reference_price is None
        ):
            continue
        planned = planned_batch_shares(
            batch_no=directive.batch_no,
            close=directive.reference_price,
            symbol_batches=[batch for batch in batches if batch.symbol == directive.symbol],
            total_deploy=portfolio.total_deploy,
            params=evaluation.params,
        )
        shrink = wording.SHRINK_NOTE.format(planned=planned, actual=directive.shares)
        stale.add(f"{directive.symbol}：{shrink}")
    if not any(line.rule_id == "M1" and line.action == "defer" for line in logged):
        stale.add(wording.INDEX_DATA_GAP_DEFER_NOTE)
    warnings = [warning for warning in warnings if warning not in stale]

    by_symbol: dict[str, list[BatchState]] = {}
    for batch in batches:
        by_symbol.setdefault(batch.symbol, []).append(batch)
    for symbol in sorted(by_symbol):
        snapshot = markets.get(symbol)
        if snapshot is not None and is_usable(snapshot.data_status, snapshot.source):
            continue
        lines = [line for line in logged if line.symbol == symbol]
        orders = sum(1 for line in lines if line.action in ORDER_ACTIONS)
        decisions = sum(1 for line in lines if line.action in DECISION_RECORD_ACTIONS)
        if not orders and not decisions:
            continue
        status = "unavailable" if snapshot is None else snapshot.data_status
        source = "none" if snapshot is None else snapshot.source
        holds = any(
            batch.status == "open" and batch.remaining_shares > 0 for batch in by_symbol[symbol]
        )
        gap = wording.DATA_GAP_HOLDING_NOTE if holds else wording.DATA_GAP_NOTE
        # DATA_GAP(_HOLDING)_NOTE -> A -> B; each falls back to the end of the
        # list when the sentence before it is not there (風控 必改 7).
        anchor = gap.format(symbol=symbol, status=status, source=source)
        if orders:
            note = wording.SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE.format(
                symbol=symbol, status=status, line_count=orders
            )
            _insert_after(warnings, anchor, note)
            anchor = note
        if decisions:
            _insert_after(
                warnings,
                anchor,
                wording.SAME_DAY_EARLIER_DECISIONS_DATA_GAP_NOTE.format(
                    symbol=symbol, decision_count=decisions
                ),
            )

    produced = {decision_key(line) for line in evaluation.directives if line.action == "buy"}
    earlier = sorted(
        (
            line
            for line in logged
            if _is_r_series(line) and line.action == "buy" and decision_key(line) not in produced
        ),
        key=lambda line: (line.symbol, line.batch_no or 0, line.execution_date),
    )
    if earlier:
        note = wording.SAME_DAY_EARLIER_ENTRY_NOTE.format(
            entry_count=len(earlier),
            entry_items="、".join(
                wording.SAME_DAY_EARLIER_ENTRY_ITEM.format(
                    symbol=line.symbol,
                    batch_no=line.batch_no,
                    shares=line.shares,
                    rule_id=line.rule_id,
                    execution_date=line.execution_date.isoformat(),
                )
                for line in earlier
            ),
        )
        frozen = wording.FROZEN_NOTE.format(mode=wording.MODE_LABELS[evaluation.mode])
        if evaluation.mode != "normal" and frozen in warnings:
            _insert_after(warnings, frozen, note)
        else:
            warnings.insert(0, note)
    return warnings


class SettlementRun(NamedTuple):
    """One settlement and the series it loaded (ADR-0035 補充四 2.4).

    ``loaded`` is what the settlement itself judged opening prices and N1 on,
    so a later reader classifying exit lines under 判準 Z (ADR-0039 Decision 3)
    uses the very same series. Empty when nothing was due, because then nothing
    was loaded.
    """

    result: SettlementResult
    loaded: Mapping[str, LoadedSeries]


def exit_row_past_due(execution_dates: Sequence[date], *, as_of: date) -> bool:
    """A-6's predicate (ADR-0039 補充一 S-2, N171-C23): is any 預定執行日 before ``as_of``?

    A plain date comparison and nothing else -- 風控 2026-11-04 第 1 點 accepts
    A-6 as "not a classification" on exactly that condition. ``as_of`` is the
    UTC day :meth:`PlaybookService.evaluate_today` runs for (``today or
    datetime.now(UTC).date()``), the basis S3 uses too, never the 依據資料日.
    It takes no trading-day table and no bars, and reaches no data source, so
    it answers the same on the unauthored path, which loads nothing. Pure; the
    only place the pending-exit block decides whether a row carries A-6.
    """
    return any(day < as_of for day in execution_dates)


def exit_row_shares_reduced(line_shares: Sequence[int], *, remaining_shares: int) -> bool:
    """A-15's predicate (ADR-0039 補充一 S-1, N171-C22): does a line ask for more than is held?

    ``line_shares`` are the ``shares`` of the row's own EMERGENCY sells and
    ``remaining_shares`` the batch's, both from the same in-flight read. True
    when a later S/P settlement left the batch smaller than the exit line that
    still names its old size (風控 P-6). Reads the book only -- no
    classification, no bars -- so every kind of row, unauthored included, uses
    it. Pure.
    """
    return any(shares > remaining_shares for shares in line_shares)


class PendingExitView(NamedTuple):
    """What N-171 adds to ``/today`` from one in-flight read (ADR-0039 Decision 1)."""

    #: Every line of the block, all three kinds, by symbol, batch_no,
    #: 預定執行日 and log id: the raw data, never what the client renders.
    directives: list[Directive]
    #: ``None`` when the block has no row (C14).
    block: PendingExitBlock | None


def _exit_row(
    batch: BatchState,
    items: Sequence[PendingDirective],
    *,
    coverage: PendingExitCoverage,
    batch_has_covering: bool | None,
    as_of: date,
) -> PendingExitRow:
    """One row, its sentences in the fixed same-row order (補充一 S-1 第 4 點).

    covering／unclassified: A-5 →［A-6］→［A-15］; stale: STALE_ITEM → A-11 or
    A-12 →［A-15］. W-B2L is not here: the response derives it per row through
    ``_lines`` and never puts it in ``text`` or ``notes`` (Decision 9, C15).
    """
    dates = sorted({item.directive.execution_date for item in items})
    notes: list[str] = []
    if coverage == "stale":
        text = wording.EMERGENCY_EXIT_STALE_ITEM.format(
            symbol=batch.symbol,
            batch_no=batch.batch_no,
            shares=batch.remaining_shares,
            stale_dates=wording.date_list(dates),
        )
        notes.append(
            wording.PENDING_EXIT_STALE_ALSO_COVERED_NOTE
            if batch_has_covering
            else wording.PENDING_EXIT_STALE_UNCOVERED_NOTE
        )
    else:
        text = wording.PENDING_EXIT_ITEM.format(
            symbol=batch.symbol,
            batch_no=batch.batch_no,
            shares=batch.remaining_shares,
            execution_dates=wording.date_list(dates),
        )
        if exit_row_past_due(dates, as_of=as_of):
            # {past_due_dates}: the row's dates that are past, S3's definition.
            notes.append(
                wording.PENDING_EXIT_PAST_DUE_NOTE.format(
                    past_due_dates=wording.date_list(day for day in dates if day < as_of)
                )
            )
    if exit_row_shares_reduced(
        [item.directive.shares for item in items], remaining_shares=batch.remaining_shares
    ):
        notes.append(wording.PENDING_EXIT_SHARES_REDUCED_NOTE)
    return PendingExitRow(
        symbol=batch.symbol,
        batch_no=batch.batch_no,
        shares=batch.remaining_shares,
        coverage=coverage,
        batch_has_covering=batch_has_covering,
        execution_dates=dates,
        text=text,
        notes=notes,
        directives=[item.directive for item in items],
    )


def _by_batch(rows: list[PendingExitRow]) -> list[PendingExitRow]:
    return sorted(rows, key=lambda row: (row.symbol, row.batch_no))


def _pending_exit_lines(
    read: PendingExitRead, *, loaded: Mapping[str, LoadedSeries] | None, as_of: date
) -> PendingExitView:
    """``pending_exit_directives`` and ``pending_exit_block`` from the in-flight read.

    Owner N-171 (ADR-0039 Decision 1～8; 補充一 S-1, S-2). Candidates are
    exactly what ``_read_exit_state`` read: unsettled EMERGENCY sells of
    batches that are open with ``remaining_shares > 0`` -- 帳冊仍記為持有, the
    definition A-2 and NB-6 paragraph 2 share (補充一 S-4) -- and no buy line.
    Nothing here reads the store, loads bars or writes (C9).

    * ``loaded`` is the settlement's own series on the authored path
      (``SettlementRun.loaded``): rows are split by :func:`classify_exit_batches`
      on it, so a stale row here is a line the same response's settlement
      gives N1 (風控 P-1). A symbol the settlement did not load counts as
      nothing loaded, which keeps every line covering -- the exit's own
      degradation (AC-N171-9).
    * ``None`` on the unauthored path, which loads nothing: no classification
      at all, one unclassified row per batch with every line (P-3, C10).

    ``as_of`` is :meth:`PlaybookService.evaluate_today`'s, for A-6 only.
    """
    state = read.state
    sections: list[PendingExitSection] = []
    placed: list[PendingDirective] = []
    if loaded is None:
        lines: dict[tuple[str, int], list[PendingDirective]] = {}
        for item in state.covering:
            if item.directive.batch_no is not None:
                key = (item.directive.symbol, item.directive.batch_no)
                lines.setdefault(key, []).append(item)
        rows: list[PendingExitRow] = []
        for batch in state.open_batches:
            items = lines.get((batch.symbol, batch.batch_no), [])
            if items:
                placed.extend(items)
                rows.append(
                    _exit_row(
                        batch,
                        items,
                        coverage="unclassified",
                        batch_has_covering=None,
                        as_of=as_of,
                    )
                )
        if rows:
            sections.append(
                PendingExitSection(
                    kind="unclassified",
                    label=None,
                    lead=wording.PENDING_EXIT_UNCLASSIFIED_LEAD,
                    rows=_by_batch(rows),
                )
            )
        closing = [wording.PENDING_EXIT_UNAUTHORED_NOTE, wording.PENDING_EXIT_RECEIPT_OVERLAP_NOTE]
    else:
        series = loaded
        classes = classify_exit_batches(
            state, lambda symbol: series.get(symbol, NOTHING_LOADED).bars
        )
        covering: list[PendingExitRow] = []
        stale: list[PendingExitRow] = []
        for entry in classes:
            placed.extend((*entry.live, *entry.stale))
            if entry.live:
                covering.append(
                    _exit_row(
                        entry.batch,
                        entry.live,
                        coverage="covering",
                        batch_has_covering=True,
                        as_of=as_of,
                    )
                )
            if entry.stale:
                stale.append(
                    _exit_row(
                        entry.batch,
                        entry.stale,
                        coverage="stale",
                        batch_has_covering=bool(entry.live),
                        as_of=as_of,
                    )
                )
        if covering:
            sections.append(
                PendingExitSection(
                    kind="covering",
                    # A-7 only when the stale section is on the page too.
                    label=wording.PENDING_EXIT_COVERED_LABEL if stale else None,
                    lead=wording.PENDING_EXIT_COVERED_LEAD,
                    rows=_by_batch(covering),
                )
            )
        if stale:
            sections.append(
                PendingExitSection(
                    kind="stale",
                    label=wording.PENDING_EXIT_STALE_LABEL,
                    lead=wording.PENDING_EXIT_STALE_LEAD,
                    rows=_by_batch(stale),
                )
            )
        closing = [wording.PENDING_EXIT_RECEIPT_OVERLAP_NOTE]

    directives = [
        item.directive
        for item in sorted(
            placed,
            key=lambda item: (
                item.directive.symbol,
                item.directive.batch_no or 0,
                item.directive.execution_date,
                item.directive_id,
            ),
        )
    ]
    if not sections:
        return PendingExitView(directives=directives, block=None)
    return PendingExitView(
        directives=directives,
        block=PendingExitBlock(
            title=wording.PENDING_EXIT_BLOCK_TITLE,
            lead_template=wording.PENDING_EXIT_BLOCK_LEAD,
            sections=sections,
            closing_notes=closing,
        ),
    )


def _entry_before_exit_lines(
    read: EntryBeforeExitRead,
) -> tuple[list[Directive], list[Directive]]:
    """``(entry_before_exit_directives, entry_before_exit_blocked_directives)``.

    Owner N-168 (ADR-0034 補充一 S-3 第 6 點); ``([], [])`` in the seam.
    """
    del read
    return [], []


class PlaybookService:
    """Loads data, runs one evaluation and persists its consequences."""

    def __init__(
        self,
        *,
        store: PlaybookStore,
        market_resolver: MarketDataResolver,
        index_resolver: IndexServiceResolver,
    ) -> None:
        self._store = store
        self._markets = market_resolver
        self._indices = index_resolver

    @property
    def store(self) -> PlaybookStore:
        return self._store

    def _load_symbol_bars(self, symbols: Sequence[str], *, today: date) -> dict[str, LoadedSeries]:
        start = today - timedelta(days=LOOKBACK_DAYS)
        loaded: dict[str, LoadedSeries] = {}
        for symbol in symbols:
            result = load_bars(
                self._markets, symbol=symbol, market=PLAYBOOK_MARKET, start=start, end=today
            )
            loaded[symbol] = LoadedSeries(
                list(result.bars), result.status.value, result.source, result.reason
            )
        return loaded

    def _load_index_bars(self, *, today: date) -> LoadedSeries:
        start = today - timedelta(days=LOOKBACK_DAYS)
        benchmark = load_market_benchmark(
            self._indices, market=PLAYBOOK_MARKET, start=start, end=today
        )
        return LoadedSeries(
            list(benchmark.bars), benchmark.status.value, benchmark.source, benchmark.reason
        )

    def settle_pending(self, *, today: date | None = None) -> SettlementResult:
        """Stamp every due T+1 line against its 預定執行日 opening price.

        See :meth:`_settle_pending`, which this returns the result of; the
        signature and the answer are unchanged (ADR-0035 補充四 2.4).
        """
        return self._settle_pending(today or datetime.now(UTC).date()).result

    def settle_on_request(self, *, today: date | None = None) -> SettlementResult:
        """``POST /api/playbook/settle``: :meth:`settle_pending`, gated on authorship.

        N171-C17′ (ADR-0039 補充一 S-3; 風控 2026-11-04 第 2 點). A-13 tells the
        user that, until they confirm a rule set, the book will not judge their
        exit lines against the opening price -- so no request path may settle
        while ``rule_set_authorship(as_of).user_authored`` is false (風控 P-4).
        The authorship read is the same one :meth:`evaluate_today` makes and the
        first thing done here: before any ``pending_directives``, any load and
        any claim. Unauthored, nothing is read beyond it, nothing is loaded and
        nothing is written; the answer is an empty settlement whose only warning
        is :data:`wording.SETTLEMENT_UNAUTHORED_NOTE` (``executed`` and
        ``missed`` are its properties, both 0).

        Authored, this is :meth:`settle_pending` unchanged. The gate lives here
        rather than in :meth:`settle_pending` or :meth:`_settle_pending` so
        neither moves (ADR-0035 補充四 2.4, SEAM-T6) and the authored ``/today``
        does not read authorship twice; :meth:`evaluate_today` never calls this.
        """
        as_of = today or datetime.now(UTC).date()
        if not self._store.rule_set_authorship(as_of).user_authored:
            return SettlementResult(
                settled_on=as_of,
                settled=[],
                unsettled=[],
                warnings=[wording.SETTLEMENT_UNAUTHORED_NOTE],
            )
        return self.settle_pending(today=as_of)

    def _settle_pending(self, as_of: date) -> SettlementRun:
        """Stamp every due T+1 line, and hand back the series it loaded.

        This is the other half of CEO 裁決七 and the reason the book moves at
        all. A line is due once its 預定執行日 has arrived; the outcome is decided
        by :func:`app.playbook.engine.settle_directive` against the *open* of
        that day's daily bar, which is the price the rule set names.

        Three properties this method has to keep:

        * **Idempotent.** The log row is claimed
          (:meth:`PlaybookStore.claim_directive`) before the book is touched, so
          calling this twice -- which ``GET /today`` does by design -- settles
          nothing the second time and deducts nothing twice.
        * **Honest about gaps.** A symbol with no bar on its 預定執行日 is listed
          in ``unsettled`` with the status and source that were seen. It is never
          settled at the reference price, and never quietly dropped (風控 R5).
        * **Silent about opinions.** Nothing here re-decides an outcome; the
          engine function does that from the band the line already carries.

        Two EMERGENCY disclosures (風控 CEO #87 回審, N-166): an unsettled exit
        line that meets 判準 Z gets N1 (or N1b) after its reason, and an exit
        line judged executed while its batch already held nothing gets N2 after
        the summary. Both are read around :meth:`PlaybookStore.settle`, which is
        left exactly as it was.

        G1 (ADR-0035 Decision 6′, CEO #88): a buy whose batch is no longer
        ``planned`` is refused by the claim itself, so it neither fills nor
        reaches the book; it stays pending and is listed in ``unsettled`` with
        :data:`wording.SETTLEMENT_BATCH_ALREADY_FILLED_NOTE` instead of being
        dropped like a row another run claimed (N172-T21). This is the one
        change N-172a makes here (N172-C8); ``settle`` is untouched. Moving the
        body under :meth:`settle_pending` into this method is a structural move
        with no difference in behaviour (ADR-0035 補充四 2.4).
        """
        pending = self._store.pending_directives(on_or_before=as_of)
        if not pending:
            return SettlementRun(
                result=SettlementResult(
                    settled_on=as_of,
                    settled=[],
                    unsettled=[],
                    warnings=[wording.SETTLEMENT_NOTHING_PENDING],
                ),
                loaded={},
            )

        symbols = sorted({item.directive.symbol for item in pending})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        settled: list[SettledLine] = []
        unsettled: list[UnsettledLine] = []
        moved_nothing: list[Directive] = []
        blocked: dict[int, BatchStatus] = {}
        for item in pending:
            directive = item.directive
            series = loaded.get(directive.symbol, NOTHING_LOADED)
            opening = next(
                (bar.open for bar in series.bars if bar.date == directive.execution_date), None
            )
            if opening is None:
                unsettled.append(
                    UnsettledLine(
                        directive_id=item.directive_id,
                        directive=directive,
                        reason=wording.SETTLEMENT_NO_OPEN_PRICE.format(
                            symbol=directive.symbol,
                            execution_date=directive.execution_date.isoformat(),
                            status=series.status,
                            source=series.source,
                        ),
                    )
                )
                continue
            outcome = settle_directive(directive, open_price=opening)
            if not self._store.claim_directive(
                item.directive_id, status=outcome.status, open_price=opening
            ):
                refused = self._store.batch_blocking_claim(item.directive_id)
                if refused is not None:
                    # G1: a buy for a batch that is no longer planned. Not
                    # claimed, nothing moved; listed with its own reason.
                    blocked[item.directive_id] = refused
                    unsettled.append(
                        UnsettledLine(
                            directive_id=item.directive_id, directive=directive, reason=""
                        )
                    )
                # Otherwise someone else settled this row between the read and the claim.
                continue
            if _is_exit_sell(outcome) and outcome.status == "executed":
                # N2: ``settle`` moves ``min(remaining, shares)``; with nothing
                # held that is zero shares and zero cash, read here beforehand.
                held = self._batch_of(outcome)
                if held is None or held.remaining_shares <= 0:
                    moved_nothing.append(outcome)
            self._store.settle(outcome, fill_price=opening)
            settled.append(
                SettledLine(directive_id=item.directive_id, directive=outcome, open_price=opening)
            )

        # N1／N1b and the G1 reason are decided after every line of the run has
        # reached the book, so the batch state they state is the one this
        # settlement leaves.
        unsettled = self._with_batch_filled_reasons(unsettled, blocked)
        unsettled = self._with_stale_exit_notes(unsettled, loaded)
        result = SettlementResult(
            settled_on=as_of, settled=settled, unsettled=unsettled, warnings=[]
        )
        warnings = [line.reason for line in unsettled]
        warnings.append(
            wording.SETTLEMENT_SUMMARY.format(
                settled_on=as_of.isoformat(),
                executed=result.executed,
                missed=result.missed,
                pending=len(unsettled),
            )
        )
        if moved_nothing:
            warnings.append(
                wording.SETTLEMENT_EXIT_NOTHING_MOVED_NOTE.format(
                    count=len(moved_nothing),
                    exit_items="、".join(
                        wording.SETTLEMENT_EXIT_ITEM.format(
                            symbol=line.symbol,
                            batch_no=line.batch_no,
                            execution_date=line.execution_date.isoformat(),
                        )
                        for line in moved_nothing
                    ),
                )
            )
        return SettlementRun(result=result.model_copy(update={"warnings": warnings}), loaded=loaded)

    def _batch_of(self, directive: Directive) -> BatchState | None:
        if directive.batch_no is None:
            return None
        return self._store.get_batch(directive.symbol, directive.batch_no)

    def _with_batch_filled_reasons(
        self, unsettled: list[UnsettledLine], blocked: Mapping[int, BatchStatus]
    ) -> list[UnsettledLine]:
        """Give each line G1 refused its :data:`wording.SETTLEMENT_BATCH_ALREADY_FILLED_NOTE`.

        ``{batch_state}`` is the batch as this settlement leaves it, which can
        only have moved on from the status the refusal saw (a batch never
        returns to ``planned``); that status stands in if the batch row is gone.
        """
        if not blocked:
            return unsettled
        noted: list[UnsettledLine] = []
        for line in unsettled:
            refused = blocked.get(line.directive_id)
            if refused is None:
                noted.append(line)
                continue
            directive = line.directive
            current = self._batch_of(directive)
            state = (
                current.status if current is not None and current.status != "planned" else refused
            )
            reason = wording.SETTLEMENT_BATCH_ALREADY_FILLED_NOTE.format(
                symbol=directive.symbol,
                batch_no=directive.batch_no,
                shares=directive.shares,
                rule_id=directive.rule_id,
                execution_date=directive.execution_date.isoformat(),
                batch_state=wording.SETTLEMENT_BATCH_STATES[state],
            )
            noted.append(line.model_copy(update={"reason": reason}))
        return noted

    def _with_stale_exit_notes(
        self, unsettled: list[UnsettledLine], loaded: Mapping[str, LoadedSeries]
    ) -> list[UnsettledLine]:
        """Append N1 or N1b to each unsettled EMERGENCY sell that meets 判準 Z.

        判準 Z is :func:`exit_line_still_covers` on the very series this
        settlement loaded, so "the exit no longer counts it" and "the
        settlement cannot stamp it" are judged from the same data. Then:

        * batch closed -> N1, 「已無持股」;
        * batch open with a later unsettled EMERGENCY sell -> N1, naming its
          預定執行日;
        * batch open, holding shares, no later one -> N1b: re-submitting the
          exit would write a new line for it (EX-3).

        Anything else (a planned or skipped batch, no batch) gets nothing added.
        """
        stale = [
            index
            for index, line in enumerate(unsettled)
            if _is_exit_sell(line.directive)
            and not exit_line_still_covers(
                line.directive, loaded.get(line.directive.symbol, NOTHING_LOADED).bars
            )
        ]
        if not stale:
            return unsettled
        outstanding = [
            item.directive
            for item in self._store.pending_directives()
            if _is_exit_sell(item.directive)
        ]
        noted = list(unsettled)
        for index in stale:
            line = unsettled[index]
            directive = line.directive
            batch = self._batch_of(directive)
            if batch is None:
                continue
            later = [
                other.execution_date
                for other in outstanding
                if (other.symbol, other.batch_no) == (directive.symbol, directive.batch_no)
                and other.execution_date > directive.execution_date
            ]
            if batch.status == "closed":
                note = wording.SETTLEMENT_EXIT_STALE_NOTE.format(
                    batch_clause=wording.SETTLEMENT_EXIT_STALE_CLOSED
                )
            elif batch.status == "open" and later:
                note = wording.SETTLEMENT_EXIT_STALE_NOTE.format(
                    batch_clause=wording.SETTLEMENT_EXIT_STALE_LATER.format(
                        later_dates=wording.date_list(later)
                    )
                )
            elif batch.status == "open" and batch.remaining_shares > 0:
                note = wording.SETTLEMENT_EXIT_STALE_REOPEN_NOTE
            else:
                continue
            noted[index] = line.model_copy(update={"reason": line.reason + note})
        return noted

    def rebalance(self, *, today: date | None = None) -> RebalanceResult:
        """季末 REBALANCE: recompute TOTAL_DEPLOY from the assets of the day.

        CEO 裁決一 locks TOTAL_DEPLOY for the quarter and recomputes it at the
        quarter end; 風控 D-1 adds that the recomputation is **two-way** -- a
        smaller book lowers it, not only a larger one raises it -- and that an
        overshoot may not be silent.

        Manual by design: the caller decides that today is the quarter end. The
        engine has no calendar of quarters and inventing one would make the
        locked value move on a day the user did not choose.

        Refuses rather than guesses (鐵律⑤): if any held symbol has no usable
        price, 總資產 cannot be stated, so nothing is written and the symbols are
        named. The overshoot case does not sell anything -- the rule set has no
        rule that trims one -- it states the number and logs a ``REBALANCE``
        line, which is what 「不得靜默」 asks for.
        """
        as_of = today or datetime.now(UTC).date()
        batches = self._store.list_batches()
        symbols = sorted({batch.symbol for batch in batches})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        portfolio = self._store.portfolio_state()
        params = self._store.active_params(as_of)

        deployed = Decimal("0")
        missing: list[str] = []
        for batch in batches:
            if batch.status != "open" or batch.remaining_shares <= 0:
                continue
            series = loaded.get(batch.symbol, NOTHING_LOADED)
            snapshot = build_market_snapshot(
                batch.symbol,
                series.bars,
                status=series.status,
                source=series.source,
                reason=series.reason,
            )
            if snapshot is None or not is_usable(snapshot.data_status, snapshot.source):
                missing.append(batch.symbol)
                continue
            deployed += snapshot.close * Decimal(batch.remaining_shares)

        if missing:
            message = wording.REBALANCE_BLOCKED.format(symbols="、".join(sorted(set(missing))))
            return RebalanceResult(
                executed_at=as_of,
                status="insufficient_data",
                total_assets=None,
                previous_total_deploy=portfolio.total_deploy,
                new_total_deploy=None,
                deployed_value=None,
                overshoot=None,
                directives=[],
                message=message,
                warnings=[message],
            )

        total_assets = portfolio.cash + deployed
        new_total_deploy = total_assets * params.deploy_ratio
        message = wording.REBALANCE_RESULT.format(
            assets=f"{total_assets:.2f}",
            previous=f"{portfolio.total_deploy:.2f}",
            new=f"{new_total_deploy:.2f}",
            ratio=wording.ratio_pct(params.deploy_ratio),
        )
        warnings: list[str] = []
        directives: list[Directive] = []
        overshoot: Decimal | None = None
        if deployed > new_total_deploy:
            overshoot = deployed - new_total_deploy
            warning = wording.REBALANCE_OVERSHOOT_WARNING.format(
                deployed=f"{deployed:.2f}",
                new=f"{new_total_deploy:.2f}",
                overshoot=f"{overshoot:.2f}",
            )
            warnings.append(warning)
            directives.append(
                Directive(
                    symbol="—",
                    batch_no=None,
                    action="none",
                    shares=0,
                    rule_id="REBALANCE",
                    rule_summary=f"{wording.rule_text('REBALANCE', params)}｜{warning}",
                    data_date=as_of,
                    execution_date=as_of,
                    reference_price=None,
                    limit_low=None,
                    limit_high=None,
                    limit_note=wording.REBALANCE_NO_ORDER_NOTE,
                    data_status="fresh",
                    source="playbook_rebalance",
                )
            )

        self._store.set_capital(
            cash=portfolio.cash,
            total_deploy=new_total_deploy,
            source=REBALANCE_SOURCE,
        )
        result = RebalanceResult(
            executed_at=as_of,
            status="ok",
            total_assets=total_assets,
            previous_total_deploy=portfolio.total_deploy,
            new_total_deploy=new_total_deploy,
            deployed_value=deployed,
            overshoot=overshoot,
            directives=directives,
            message=message,
            warnings=warnings,
        )
        if directives:
            self._store.record_directives(
                PlaybookEvaluation(
                    data_date=as_of,
                    execution_date=as_of,
                    mode="normal",
                    mode_reason=message,
                    is_schedule_day=False,
                    fast_market=FastMarketState(
                        active=False,
                        annualized_vol_20d=None,
                        large_move_days=0,
                        reason=None,
                    ),
                    rules_version=params.version,
                    params=params,
                    directives=directives,
                    effects=[],
                    warnings=warnings,
                    snapshot=[],
                )
            )
        return result

    def _evaluation_data_date(self, as_of: date) -> date:
        """The 依據資料日 an evaluation started now would run on.

        Read the same way :meth:`evaluate_today` reads it -- the latest bar date
        across the held symbols and the index -- and ``as_of`` when nothing came
        back at all, which is the fallback that method takes too. Never later
        than ``as_of``: a bar dated ahead of the day may not date a rule set into
        the future.

        This is the one place the confirmation flow touches market data, and it
        only reads: the date is needed because the row this dates has to be in
        force on the day the user confirmed it (see :meth:`confirm_rules`).
        """
        symbols = sorted({batch.symbol for batch in self._store.list_batches()})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        index_bars = self._load_index_bars(today=as_of).bars
        latest = latest_bar_date(*(series.bars for series in loaded.values()), index_bars)
        return as_of if latest is None else min(latest, as_of)

    def _rule_set_status(self, as_of: date) -> RuleSetStatus:
        return RuleSetStatus(
            params=self._store.active_params(as_of),
            authorship=self._store.rule_set_authorship(as_of),
            portfolio=self._store.portfolio_state(),
            rules_effective_date=self._store.in_force_effective_date(as_of),
        )

    def rule_set_status(self, *, today: date | None = None) -> RuleSetStatus:
        """The rule set in force and its authorship record. Writes nothing.

        The read half of the confirmation flow: the screen that asks the user to
        adopt a rule set has to show the thresholds it is asking about, and they
        are the ones :meth:`evaluate_today` would run -- not a copy the client
        keeps. Reading this never counts as adopting anything (風控 R2: only
        :meth:`confirm_rules` writes the record).
        """
        return self._rule_set_status(today or datetime.now(UTC).date())

    def confirm_rules(self, *, capital: Decimal, today: date | None = None) -> RuleSetStatus:
        """Adopt the rule set in force as the user's own and record the capital.

        This is the one action that lifts the 歸屬語情境 1 block: before it the
        module holds a system default and says so, and produces no rule-driven
        directive at all (:meth:`_unauthored_evaluation`).

        It takes **no thresholds**. The set adopted is the one already in force,
        so a confirmation can never smuggle a parameter change past 鐵律④ -- a
        later change goes through :func:`request_rule_change` and takes effect on
        the next trading day. A first adoption is dated at the 依據資料日 the
        evaluation runs on (:meth:`_evaluation_data_date`), not at ``as_of``:
        鐵律④ delays *changes* and there is nothing here to delay away from,
        while a row dated a day ahead of the data is a row
        :meth:`PlaybookStore.in_force_effective_date` cannot see on the very day
        it was written -- which left the confirmation day stating 「生效日期讀取
        失敗」 about the set the user had just confirmed (五輪定稿 生效日對齊
        路線 (a)). The thresholds are identical to the ones already in force, so
        dating the row at the data date changes no threshold retroactively.

        Idempotent. A second call finds an authorship record already there and
        writes no new version, so re-submitting cannot walk the rule set forward
        one version per click. The capital *is* written again -- this is also the
        capital entry point, and every write carries its timestamp and source
        (CEO 裁決 D-2), so the later figure is auditable rather than silent.

        TOTAL_DEPLOY is ``capital × deploy_ratio`` of the version in force
        (CEO 裁決一), computed from the submitted figure alone: this is the
        opening capital, and recomputing it from what the book holds is the
        季末 REBALANCE's job (:meth:`rebalance`), on the day the user names.
        """
        as_of = today or datetime.now(UTC).date()
        if not self._store.rule_set_authorship(as_of).user_authored:
            current = self._store.active_params(as_of)
            self._store.confirm_rule_set(
                current.model_copy(
                    update={
                        "version": self._store.next_version(),
                        "effective_date": self._evaluation_data_date(as_of),
                    }
                )
            )
        params = self._store.active_params(as_of)
        self._store.set_capital(
            cash=capital,
            total_deploy=capital * params.deploy_ratio,
            source=CONFIRMATION_SOURCE,
        )
        return self._rule_set_status(as_of)

    def _unauthored_evaluation(self, as_of: date) -> PlaybookEvaluation:
        """The answer when no user rule set exists (歸屬語情境 1).

        風控 覆審: with no submission record the module may not produce a
        rule-driven directive (進場／停損／停利), and the 歸屬語 is replaced by the
        blocking sentence rather than shortened. Nothing is loaded, evaluated or
        written -- an evaluation the user never authorised leaves no trace
        either. EMERGENCY_EXIT is outside this gate entirely and the blocking
        sentence says so itself (題 8, third clause).

        Held shares are the one thing that has to be said out loud (三輪定稿
        題 9): the block also stops the S/P series, so a position that is still
        open goes a day without its stop loss being evaluated. The disclosure is
        an **existence check on the batch book only** -- no bar is loaded, no
        indicator computed and nothing written -- because the day still has to
        leave no trace, and every held symbol is listed in full.

        The exit confirmation block is filled here too (EX-2 出口零摩擦): the
        exit is reachable on this path, so its confirmation screen may not be
        left without the freeze it is about to impose. It is counted on an empty
        calendar because this path loads no bars by design; that costs nothing,
        since every day the count walks is after the last bar either way and
        resolves through the calendar's weekday fallback (see
        :func:`build_exit_confirm`).
        """
        held = sorted(
            {
                batch.symbol
                for batch in self._store.list_batches()
                if batch.status == "open" and batch.remaining_shares > 0
            }
        )
        warnings = [wording.UNAUTHORED_HOLDING_NOTE.format(symbols="、".join(held))] if held else []
        # The one in-flight read of this path (ADR-0035 補充四 2.3(c)): SELECT
        # only, so the day still leaves no trace; nothing is loaded for it.
        in_flight = self._store.read_in_flight()
        entries, blocked_entries = _entry_before_exit_lines(in_flight.entries)
        # Unclassified: this path loads no bars to judge 判準 Z on (ADR-0039 Decision 7).
        exits = _pending_exit_lines(in_flight.exits, loaded=None, as_of=as_of)
        # The version in force -- what ``rule_set_status`` states and a
        # confirmation would adopt. Nothing is evaluated with it here; it is
        # carried for the figures a response restates (ADR-0031 C-5) and read
        # once for both that and the exit confirmation.
        params = self._store.active_params(as_of)
        return PlaybookEvaluation(
            data_date=as_of,
            execution_date=as_of,
            # 題 10: its own mode value, never 「正常」.
            mode="unconfirmed",
            mode_reason=wording.ATTRIBUTION_NO_USER_RULES,
            is_schedule_day=False,
            fast_market=FastMarketState(
                active=False, annualized_vol_20d=None, large_move_days=0, reason=None
            ),
            rules_version=0,
            params=params,
            directives=[],
            effects=[],
            warnings=warnings,
            snapshot=[],
            attribution=wording.ATTRIBUTION_NO_USER_RULES,
            # No rule set was evaluated at all today, so the ledger's 「無。」 may
            # not be explained away as 「無任何規則命中」 (題 12 fail-closed).
            rules_effective_date=None,
            rules_fully_evaluated=False,
            page_summary=wording.page_summary(
                data_date=as_of,
                rules_version=0,
                rules_effective_date=None,
                user_authored=False,
            ),
            exit_confirm=build_exit_confirm(
                params=params,
                calendar=TradingCalendar(()),
                as_of=as_of,
                stored_until=self._store.portfolio_state().emergency_until,
            ),
            pending_exit_directives=exits.directives,
            entry_before_exit_directives=entries,
            entry_before_exit_blocked_directives=blocked_entries,
            pending_exit_block=exits.block,
        )

    def evaluate_today(self, *, today: date | None = None) -> PlaybookEvaluation:
        """Run one evaluation off the latest closing data and persist the result.

        Settlement runs first: yesterday's lines have to reach the book before
        today's lines are decided, or the same batch would be re-issued every day
        (the T+1 half of CEO 裁決七). Settlement claims each row before the book
        moves, so running it again settles nothing twice.

        The evaluation itself writes, and before ADR-0035 every call wrote its
        lines again (N172-C10). It is now idempotent per 預定執行日 and decision
        (K1, K2), under one write lock (:meth:`PlaybookStore.commit_evaluation`):
        a repeated call logs only decisions no earlier call of the same
        預定執行日 made -- a new S1 once the data is back, say -- and applies a
        deferral or skip only with the line it belongs to. The effects left
        outside that transaction (pause, blacklist, freeze, defense, trailing,
        deferral reset) resolve to the same state for the same 依據資料日. The
        response lists the 預定執行日's **logged** lines (Decision 4), so every
        refresh shows the same table, and says so when an earlier R1 buy is on
        it that this run did not produce (Decision 5, S-α) -- see
        :func:`same_day_warnings`.

        Gated on authorship (風控 R2 / 覆審 歸屬語情境 1): a rule-driven directive
        may only be produced from rules the user submitted, so a book with no
        submission record gets the blocking sentence and no lines. The gate reads
        the explicit record, never a date.
        """
        as_of = today or datetime.now(UTC).date()
        authorship = self._store.rule_set_authorship(as_of)
        if not authorship.user_authored:
            return self._unauthored_evaluation(as_of)
        run = self._settle_pending(as_of)
        settlement = run.result
        # The one in-flight read after the settlement (ADR-0035 補充四 2.3(c)):
        # every in-flight list of this response derives from it.
        in_flight = self._store.read_in_flight()
        batches = self._store.list_batches()
        symbols = sorted({batch.symbol for batch in batches})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        index_series = self._load_index_bars(today=as_of)
        index_bars = index_series.bars

        calendar = build_calendar(
            *(series.bars for series in loaded.values()),
            index_bars,
        )
        data_date = latest_bar_date(*(series.bars for series in loaded.values()), index_bars)
        if data_date is None:
            # Nothing came back at all: still a 200-shaped answer, with the
            # gap stated, never a fabricated evaluation (鐵律⑤).
            data_date = as_of

        params = self._store.active_params(data_date)
        index = build_index_snapshot(
            index_bars,
            status=index_series.status,
            source=index_series.source,
            params=params,
            reason=index_series.reason,
        )
        markets: dict[str, MarketSnapshot] = {}
        for symbol, series in loaded.items():
            snapshot = build_market_snapshot(
                symbol,
                series.bars,
                status=series.status,
                source=series.source,
                reason=series.reason,
            )
            if snapshot is not None:
                markets[symbol] = snapshot

        self._store.roll_peak_closes(
            {symbol: snapshot.close for symbol, snapshot in markets.items()}
        )
        book = self._store.list_batches()
        portfolio = self._store.portfolio_state()
        evaluation = evaluate(
            data_date=data_date,
            calendar=calendar,
            params=params,
            index=index,
            markets=markets,
            batches=book,
            symbols=self._store.symbol_states(data_date),
            portfolio=portfolio,
            previous_fast_market=self._store.fast_market_state(),
        )
        # The line-bound effects go with their lines, under the lock (C5).
        self._store.apply_effects(
            [effect for effect in evaluation.effects if effect.kind not in LINE_BOUND_EFFECTS],
            data_date=data_date,
            calendar=calendar,
        )
        self._store.save_fast_market(evaluation.fast_market, measured_on=data_date)
        commit = self._store.commit_evaluation(evaluation)
        # §6 ②: the effective date of the row actually in force on the 依據資料日,
        # read from the store rather than from ``params`` -- a parameter set that
        # fell back to the system default carries a derived date, and the page
        # states this one as the rule set's own (裁決: 禁推斷頂替).
        rules_effective_date = self._store.in_force_effective_date(data_date)
        # 風控 2026-09-15 R1-b: what the data layer said about the index series
        # (cache, spliced sources) is shown with the evaluation it fed, verbatim.
        # Read from the loaded series, not the snapshot: when no bar came back
        # at all the snapshot is ``None`` and the loader's own sentence (which
        # source reported what) is exactly what the reader needs (風控 R4-a).
        warnings = same_day_warnings(
            evaluation, commit, markets=markets, batches=book, portfolio=portfolio
        )
        if index_series.reason:
            warnings.append(wording.index_data_reason_note(index_series.reason))
        entries, blocked_entries = _entry_before_exit_lines(in_flight.entries)
        # Classified on the settlement's own series (ADR-0039 Decision 3, 風控 P-1).
        exits = _pending_exit_lines(in_flight.exits, loaded=run.loaded, as_of=as_of)
        return evaluation.model_copy(
            update={
                # Decision 4: what the log holds for this 預定執行日, so 「無」
                # statements derived from it (``no_directive_note``) read the
                # same list the page shows (風控 二-3 第 1 點).
                "directives": commit.logged,
                "warnings": warnings,
                "settlement": settlement,
                "attribution": wording.attribution_note(authorship),
                "rules_effective_date": rules_effective_date,
                "page_summary": wording.page_summary(
                    data_date=evaluation.data_date,
                    rules_version=evaluation.rules_version,
                    rules_effective_date=rules_effective_date,
                    user_authored=authorship.user_authored,
                ),
                # Counted for today, not for 依據資料日: the confirmation screen
                # predicts what submitting *now* costs, which is what
                # :meth:`emergency_exit` reads (``active_params(as_of)``).
                "exit_confirm": build_exit_confirm(
                    params=self._store.active_params(as_of),
                    calendar=calendar,
                    as_of=as_of,
                    stored_until=self._store.portfolio_state().emergency_until,
                ),
                "pending_exit_directives": exits.directives,
                "entry_before_exit_directives": entries,
                "entry_before_exit_blocked_directives": blocked_entries,
                "pending_exit_block": exits.block,
            }
        )

    def emergency_exit(self, *, today: date | None = None) -> EmergencyExitResult:
        """Liquidate every batch and freeze the schedule for 20 trading days.

        Available in every mode and at any time (風控 R11): it is the user's own
        escape hatch, so it is never gated on a schedule day, a data status or a
        freeze. A symbol whose price could not be loaded is still liquidated --
        the line simply carries no reference price, because there is none to
        state (風控 R5: say what is missing, do not invent it).

        The 歸屬語情境 1 gate on :meth:`evaluate_today` deliberately does **not**
        apply here (CEO EX-2/EX-4, 出口零摩擦): these lines come from an action
        the user just submitted, not from rules the system holds on their behalf,
        and adding a precondition to the exit is the one thing the exit may not
        have. The authorship record is therefore not read at all here (三輪定稿
        題 7): the response carries an EXIT 歸屬語 (:data:`wording.EXIT_ATTRIBUTION`
        or, when earlier lines are described, 風控 N-166 S5／S4), which attributes
        the lines to the submitted action, and never the blocking sentence --
        printing 「在你確認規則集之前不會產生指令」 next to lines the exit just
        produced would contradict the lines themselves.

        **Repeat-safe (ADR-0033, CEO #76 方案 (d)).** A second submission -- a
        double click, a second tab, a retried request -- writes a line only for
        a held batch no unsettled EMERGENCY sell covers yet, and always answers
        200 with no new precondition (EX-2, EX-3, C-6). Everything that reaches
        a resolver happens first; the decision and both writes happen inside one
        write-locked transaction (:meth:`PlaybookStore.commit_emergency_exit`),
        so concurrent exits cannot both write and a failure leaves nothing
        half-written. The 恢復日 is the later of the stored one and this
        submission's own count (CEO #77): a repeat on a later day extends the
        freeze and the message says so (風控 S6); a stored later date is kept and
        stated as kept (風控 S7).
        """
        as_of = today or datetime.now(UTC).date()
        # Read outside the lock only to know which symbols to load; every
        # decision below is taken from what the lock re-reads (C-2).
        symbols = sorted({batch.symbol for batch in self._store.list_batches()})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        index_bars = self._load_index_bars(today=as_of).bars
        calendar = build_calendar(*(series.bars for series in loaded.values()), index_bars)
        params = self._store.active_params(as_of)
        freeze_days = params.emergency_freeze_trading_days
        execution_date = calendar.next_trading_day(as_of)
        computed_until = calendar.shift(as_of, freeze_days)

        state, plan = self._store.commit_emergency_exit(
            lambda locked: plan_emergency_exit(
                locked,
                loaded=loaded,
                params=params,
                as_of=as_of,
                execution_date=execution_date,
                computed_until=computed_until,
            )
        )

        until = plan.emergency_until
        previous = state.emergency_until
        pending_dates = tuple(item.directive.execution_date for item in plan.pending)
        pending = wording.ExitPending(
            batches=len(plan.covered),
            shares=sum(batch.remaining_shares for batch in plan.covered),
            execution_dates=pending_dates,
            past_due_dates=tuple(day for day in pending_dates if day < as_of),
            stale=tuple(plan.stale),
        )
        new_shares = sum(directive.shares for directive in plan.directives)
        # 風控 S6: only a freeze that was running and is now later was extended.
        extended = previous is not None and as_of <= previous and until > previous
        message = wording.emergency_exit_message(
            new_batches=len(plan.directives),
            new_shares=new_shares,
            execution_date=execution_date,
            executed_at=as_of,
            freeze_days=freeze_days,
            until=until,
            pending=pending,
            extended_from=previous if extended else None,
            freeze_kept=until != computed_until,
        )
        # The mode line is rendered for today, not lifted from ``message``: the
        # 「第 N/20 交易日」 counter is only true on the day it was computed, so
        # nothing may store it (覆審: mode_reason 禁存快照字串). It is counted
        # from the same 依據資料日 :meth:`evaluate_today` uses -- the latest bar
        # of the same loads, ``as_of`` when none came back -- through the same
        # function, so the exit's answer and the same day's ``/today`` state the
        # same line (風控 2026-10-31 第二次裁示 V-16, suggested).
        data_date = (
            latest_bar_date(*(series.bars for series in loaded.values()), index_bars) or as_of
        )
        mode_reason = emergency_mode_reason(
            calendar=calendar, data_date=data_date, until=until, freeze_days=freeze_days
        )
        return EmergencyExitResult(
            executed_at=as_of,
            execution_date=execution_date,
            directives=plan.directives,
            pending_directives=[item.directive for item in plan.pending],
            total_shares=new_shares,
            freeze_until=until,
            message=message,
            warnings=plan.warnings,
            attribution=wording.emergency_exit_attribution(
                new_batches=len(plan.directives),
                pending_batches=pending.batches,
                stale_batches=len(pending.stale),
            ),
            mode_reason=mode_reason,
        )


def request_rule_change(
    *,
    store: PlaybookStore,
    calendar: TradingCalendar,
    changes: Mapping[str, object],
    submitted_at: date,
    fast_market_vol: float | None = None,
    fast_market_moves: int = 0,
) -> RuleChangeReceipt:
    """鐵律④: record a rule change for the next trading day, never for today.

    There is no argument that makes this take effect immediately, which is the
    entire point of the rule: the request is accepted, dated and stored. 風控 R14
    is satisfied because nothing is refused outright -- only delayed -- and
    CEO 裁決六 is satisfied because a fast market appends the current volatility
    to the sentence instead of relaxing the cooling period.
    """
    current = store.active_params(submitted_at)
    effective = calendar.next_trading_day(submitted_at)
    version = store.next_version()
    updated = current.model_copy(
        update={**dict(changes), "version": version, "effective_date": effective}
    )
    store.submit_rule_change(updated)
    message = wording.RULE_CHANGE_PENDING.format(
        effective_date=effective.isoformat(), version=version
    )
    fast = (
        fast_market_vol is not None and fast_market_vol > current.fast_market_vol_threshold
    ) or fast_market_moves >= current.fast_market_move_count
    if fast:
        # 覆審: an absent volatility is stated as absent, never rendered as 「—%」.
        message += wording.fast_market_note(
            vol=fast_market_vol,
            lookback=current.fast_market_lookback_days,
            moves=fast_market_moves,
            move_pct=current.fast_market_move_pct,
        )
    return RuleChangeReceipt(
        version=version,
        submitted_at=submitted_at,
        effective_date=effective,
        message=message,
    )


def settle_open_price(directive: Directive, open_price: Decimal) -> Directive:
    """Stamp a line's T+1 outcome; re-exported for service-layer callers."""
    return settle_directive(directive, open_price=open_price)
