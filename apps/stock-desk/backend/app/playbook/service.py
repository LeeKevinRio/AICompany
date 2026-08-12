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
4. Evaluate, then persist: schedule-state effects, the schedule rows and the
   directive log (風控 R16).

The peak close (波段最高收盤) is rolled forward before evaluation, because the
trailing stop reads it on the same day's close.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.data.interface import PriceBar
from app.playbook import indicators, wording
from app.playbook.calendar import TradingCalendar
from app.playbook.engine import (
    emergency_frozen_day,
    evaluate,
    is_usable,
    settle_directive,
)
from app.playbook.models import (
    Directive,
    EmergencyExitResult,
    ExitConfirm,
    FastMarketState,
    IndexSnapshot,
    MarketSnapshot,
    PlaybookEvaluation,
    RebalanceResult,
    RuleChangeReceipt,
    RuleParams,
    RuleSetStatus,
    SettledLine,
    SettlementResult,
    StateEffect,
    UnsettledLine,
)
from app.playbook.store import PlaybookStore
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


def build_market_snapshot(
    symbol: str,
    bars: Sequence[PriceBar],
    *,
    status: str,
    source: str,
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
        high_volatility=high_volatility,
    )


def build_index_snapshot(
    bars: Sequence[PriceBar], *, status: str, source: str, params: RuleParams
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
    )


def build_exit_confirm(
    *, params: RuleParams, calendar: TradingCalendar, as_of: date
) -> ExitConfirm:
    """The EMERGENCY_EXIT confirmation facts, counted for ``as_of``.

    Computed the same way :meth:`PlaybookService.emergency_exit` computes the
    freeze it will actually apply -- ``params.emergency_freeze_trading_days``
    shifted from the *submission* day on the trading calendar -- so a screen
    that renders this block states the freeze the user is about to get, not a
    mirrored default (覆審: 天數與日期皆為參數與日曆的函數，不得寫死).

    The prediction walks days after ``as_of``, which are past the last observed
    bar, so it resolves through the calendar's documented weekday fallback in
    both cases; that is the same answer the exit itself reaches on that day.
    """
    freeze_days = params.emergency_freeze_trading_days
    freeze_until = calendar.shift(as_of, freeze_days)
    return ExitConfirm(
        freeze_days=freeze_days,
        freeze_until=freeze_until,
        checks=list(
            wording.exit_confirm_checks(
                freeze_days=freeze_days, freeze_until=freeze_until
            )
        ),
    )


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

    def _load_symbol_bars(
        self, symbols: Sequence[str], *, today: date
    ) -> dict[str, tuple[list[PriceBar], str, str]]:
        start = today - timedelta(days=LOOKBACK_DAYS)
        loaded: dict[str, tuple[list[PriceBar], str, str]] = {}
        for symbol in symbols:
            result = load_bars(
                self._markets, symbol=symbol, market=PLAYBOOK_MARKET, start=start, end=today
            )
            loaded[symbol] = (list(result.bars), result.status.value, result.source)
        return loaded

    def _load_index_bars(self, *, today: date) -> tuple[list[PriceBar], str, str]:
        start = today - timedelta(days=LOOKBACK_DAYS)
        benchmark = load_market_benchmark(
            self._indices, market=PLAYBOOK_MARKET, start=start, end=today
        )
        return list(benchmark.bars), benchmark.status.value, benchmark.source

    def settle_pending(self, *, today: date | None = None) -> SettlementResult:
        """Stamp every due T+1 line against its 預定執行日 opening price.

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
        """
        as_of = today or datetime.now(UTC).date()
        pending = self._store.pending_directives(on_or_before=as_of)
        if not pending:
            return SettlementResult(
                settled_on=as_of,
                settled=[],
                unsettled=[],
                warnings=[wording.SETTLEMENT_NOTHING_PENDING],
            )

        symbols = sorted({item.directive.symbol for item in pending})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        settled: list[SettledLine] = []
        unsettled: list[UnsettledLine] = []
        for item in pending:
            directive = item.directive
            bars, status, source = loaded.get(directive.symbol, ([], "unavailable", "none"))
            opening = next(
                (bar.open for bar in bars if bar.date == directive.execution_date), None
            )
            if opening is None:
                unsettled.append(
                    UnsettledLine(
                        directive_id=item.directive_id,
                        directive=directive,
                        reason=wording.SETTLEMENT_NO_OPEN_PRICE.format(
                            symbol=directive.symbol,
                            execution_date=directive.execution_date.isoformat(),
                            status=status,
                            source=source,
                        ),
                    )
                )
                continue
            outcome = settle_directive(directive, open_price=opening)
            if not self._store.claim_directive(
                item.directive_id, status=outcome.status, open_price=opening
            ):
                # Someone else settled this row between the read and the claim.
                continue
            self._store.settle(outcome, fill_price=opening)
            settled.append(
                SettledLine(
                    directive_id=item.directive_id, directive=outcome, open_price=opening
                )
            )

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
        return result.model_copy(update={"warnings": warnings})

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
            bars, status, source = loaded.get(batch.symbol, ([], "unavailable", "none"))
            snapshot = build_market_snapshot(batch.symbol, bars, status=status, source=source)
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
        index_bars, _, _ = self._load_index_bars(today=as_of)
        latest = latest_bar_date(*(bars for bars, _, _ in loaded.values()), index_bars)
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

    def confirm_rules(
        self, *, capital: Decimal, today: date | None = None
    ) -> RuleSetStatus:
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
        warnings = (
            [wording.UNAUTHORED_HOLDING_NOTE.format(symbols="、".join(held))]
            if held
            else []
        )
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
                params=self._store.active_params(as_of),
                calendar=TradingCalendar(()),
                as_of=as_of,
            ),
        )

    def evaluate_today(self, *, today: date | None = None) -> PlaybookEvaluation:
        """Run one evaluation off the latest closing data and persist the result.

        Settlement runs first: yesterday's lines have to reach the book before
        today's lines are decided, or the same batch would be re-issued every day
        (the T+1 half of CEO 裁決七). It is idempotent, so calling this endpoint
        repeatedly is safe.

        Gated on authorship (風控 R2 / 覆審 歸屬語情境 1): a rule-driven directive
        may only be produced from rules the user submitted, so a book with no
        submission record gets the blocking sentence and no lines. The gate reads
        the explicit record, never a date.
        """
        as_of = today or datetime.now(UTC).date()
        authorship = self._store.rule_set_authorship(as_of)
        if not authorship.user_authored:
            return self._unauthored_evaluation(as_of)
        settlement = self.settle_pending(today=as_of)
        batches = self._store.list_batches()
        symbols = sorted({batch.symbol for batch in batches})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        index_bars, index_status, index_source = self._load_index_bars(today=as_of)

        calendar = build_calendar(
            *(bars for bars, _, _ in loaded.values()),
            index_bars,
        )
        data_date = latest_bar_date(*(bars for bars, _, _ in loaded.values()), index_bars)
        if data_date is None:
            # Nothing came back at all: still a 200-shaped answer, with the
            # gap stated, never a fabricated evaluation (鐵律⑤).
            data_date = as_of

        params = self._store.active_params(data_date)
        index = build_index_snapshot(
            index_bars, status=index_status, source=index_source, params=params
        )
        markets: dict[str, MarketSnapshot] = {}
        for symbol, (bars, status, source) in loaded.items():
            snapshot = build_market_snapshot(symbol, bars, status=status, source=source)
            if snapshot is not None:
                markets[symbol] = snapshot

        self._store.roll_peak_closes(
            {symbol: snapshot.close for symbol, snapshot in markets.items()}
        )
        evaluation = evaluate(
            data_date=data_date,
            calendar=calendar,
            params=params,
            index=index,
            markets=markets,
            batches=self._store.list_batches(),
            symbols=self._store.symbol_states(data_date),
            portfolio=self._store.portfolio_state(),
            previous_fast_market=self._store.fast_market_state(),
        )
        self._store.apply_effects(
            evaluation.effects, data_date=data_date, calendar=calendar
        )
        self._store.save_fast_market(evaluation.fast_market, measured_on=data_date)
        self._store.record_schedule(evaluation)
        self._store.record_directives(evaluation)
        # §6 ②: the effective date of the row actually in force on the 依據資料日,
        # read from the store rather than from ``params`` -- a parameter set that
        # fell back to the system default carries a derived date, and the page
        # states this one as the rule set's own (裁決: 禁推斷頂替).
        rules_effective_date = self._store.in_force_effective_date(data_date)
        return evaluation.model_copy(
            update={
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
                ),
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
        題 7): the response carries :data:`wording.EXIT_ATTRIBUTION`, which
        attributes the lines to the submitted action, and never the blocking
        sentence -- printing 「在你確認規則集之前不會產生指令」 next to lines the
        exit just produced would contradict the lines themselves.
        """
        as_of = today or datetime.now(UTC).date()
        batches = self._store.list_batches()
        symbols = sorted({batch.symbol for batch in batches})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        index_bars, _, _ = self._load_index_bars(today=as_of)
        calendar = build_calendar(*(bars for bars, _, _ in loaded.values()), index_bars)
        params = self._store.active_params(as_of)

        execution_date = calendar.next_trading_day(as_of)
        freeze_until = calendar.shift(as_of, params.emergency_freeze_trading_days)
        directives: list[Directive] = []
        warnings: list[str] = []
        total = 0
        for batch in batches:
            if batch.status != "open" or batch.remaining_shares <= 0:
                continue
            bars, status, source = loaded.get(batch.symbol, ([], "unavailable", "none"))
            snapshot = build_market_snapshot(batch.symbol, bars, status=status, source=source)
            if snapshot is None:
                warnings.append(
                    wording.DATA_GAP_NOTE.format(
                        symbol=batch.symbol, status=status, source=source
                    )
                )
            total += batch.remaining_shares
            directives.append(
                Directive(
                    symbol=batch.symbol,
                    batch_no=batch.batch_no,
                    action="sell",
                    shares=batch.remaining_shares,
                    rule_id="EMERGENCY",
                    rule_summary=(
                        f"{wording.rule_text('EMERGENCY', params)}"
                        f"｜出清 {batch.remaining_shares} 股"
                    ),
                    data_date=snapshot.data_date if snapshot else as_of,
                    execution_date=execution_date,
                    reference_price=snapshot.close if snapshot else None,
                    limit_low=None,
                    limit_high=None,
                    limit_note=wording.EMERGENCY_EXIT_NO_BAND_NOTE,
                    data_status=status,
                    source=source,
                )
            )
        freeze_days = params.emergency_freeze_trading_days
        message = (
            wording.EMERGENCY_EXIT_RESULT.format(
                batches=len(directives),
                shares=total,
                execution_date=execution_date.isoformat(),
                executed_at=as_of.isoformat(),
                freeze_days=freeze_days,
                until=freeze_until.isoformat(),
            )
            if directives
            else wording.EMERGENCY_EXIT_EMPTY.format(
                executed_at=as_of.isoformat(),
                freeze_days=freeze_days,
                until=freeze_until.isoformat(),
            )
        )
        # The mode line is rendered for today, not lifted from ``message``: the
        # 「第 N/20 交易日」 counter is only true on the day it was computed, so
        # nothing may store it (覆審: mode_reason 禁存快照字串).
        mode_reason = wording.mode_reason_emergency(
            frozen_day=emergency_frozen_day(
                calendar=calendar,
                data_date=as_of,
                until=freeze_until,
                freeze_days=freeze_days,
            ),
            freeze_days=freeze_days,
            until=freeze_until,
        )
        result = EmergencyExitResult(
            executed_at=as_of,
            execution_date=execution_date,
            directives=directives,
            total_shares=total,
            freeze_until=freeze_until,
            message=message,
            warnings=warnings,
            # 題 7: the EMPTY branch produced no 指令, so there is nothing for the
            # sentence to attribute and it is not rendered at all.
            attribution=wording.EXIT_ATTRIBUTION if directives else None,
            mode_reason=mode_reason,
        )
        self._store.apply_effects(
            [
                StateEffect(
                    kind="emergency_exit",
                    value=params.emergency_freeze_trading_days,
                    note=message,
                )
            ],
            data_date=as_of,
            calendar=calendar,
        )
        self._store.record_directives(
            PlaybookEvaluation(
                data_date=as_of,
                execution_date=execution_date,
                mode="emergency_frozen",
                mode_reason=mode_reason,
                is_schedule_day=calendar.is_schedule_day(as_of),
                fast_market=FastMarketState(
                    active=False,
                    annualized_vol_20d=None,
                    large_move_days=0,
                    reason=None,
                ),
                rules_version=params.version,
                directives=directives,
                effects=[],
                warnings=warnings,
                snapshot=[],
            )
        )
        return result


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
