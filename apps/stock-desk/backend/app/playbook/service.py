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
from app.playbook.engine import evaluate, settle_directive
from app.playbook.models import (
    Directive,
    EmergencyExitResult,
    FastMarketState,
    IndexSnapshot,
    MarketSnapshot,
    PlaybookEvaluation,
    RuleChangeReceipt,
    RuleParams,
    StateEffect,
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


def build_calendar(*bar_groups: Sequence[PriceBar]) -> TradingCalendar:
    """A calendar of every date any loaded series produced a bar on."""
    days: set[date] = set()
    for bars in bar_groups:
        days.update(bar.date for bar in bars)
    return TradingCalendar(days)


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

    def evaluate_today(self, *, today: date | None = None) -> PlaybookEvaluation:
        """Run one evaluation off the latest closing data and persist the result."""
        as_of = today or datetime.now(UTC).date()
        batches = self._store.list_batches()
        symbols = sorted({batch.symbol for batch in batches})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        index_bars, index_status, index_source = self._load_index_bars(today=as_of)

        calendar = build_calendar(
            *(bars for bars, _, _ in loaded.values()),
            index_bars,
        )
        data_date = max(
            (
                bar.date
                for bars, _, _ in loaded.values()
                for bar in bars
            ),
            default=None,
        )
        if index_bars:
            index_latest = max(bar.date for bar in index_bars)
            data_date = index_latest if data_date is None else max(data_date, index_latest)
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
        )
        self._store.apply_effects(
            evaluation.effects, data_date=data_date, calendar=calendar
        )
        self._store.record_schedule(evaluation)
        self._store.record_directives(evaluation)
        return evaluation

    def emergency_exit(self, *, today: date | None = None) -> EmergencyExitResult:
        """Liquidate every batch and freeze the schedule for 20 trading days.

        Available in every mode and at any time (風控 R11): it is the user's own
        escape hatch, so it is never gated on a schedule day, a data status or a
        freeze. A symbol whose price could not be loaded is still liquidated --
        the line simply carries no reference price, because there is none to
        state (風控 R5: say what is missing, do not invent it).
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
                        f"{wording.RULE_TEXT['EMERGENCY']}｜出清 {batch.remaining_shares} 股"
                    ),
                    data_date=snapshot.data_date if snapshot else as_of,
                    execution_date=execution_date,
                    reference_price=snapshot.close if snapshot else None,
                    limit_low=None,
                    limit_high=None,
                    limit_note=wording.STOP_LOSS_NO_BAND_NOTE,
                    data_status=status,
                    source=source,
                )
            )
        message = (
            wording.EMERGENCY_EXIT_RESULT.format(
                batches=len(directives), shares=total, until=freeze_until.isoformat()
            )
            if directives
            else wording.EMERGENCY_EXIT_EMPTY.format(until=freeze_until.isoformat())
        )
        result = EmergencyExitResult(
            executed_at=as_of,
            execution_date=execution_date,
            directives=directives,
            total_shares=total,
            freeze_until=freeze_until,
            message=message,
            warnings=warnings,
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
                mode_reason=message,
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
        message += wording.FAST_MARKET_REFUSAL_SUFFIX.format(
            vol="—" if fast_market_vol is None else f"{fast_market_vol:.1f}",
            lookback=current.fast_market_lookback_days,
            moves=fast_market_moves,
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
