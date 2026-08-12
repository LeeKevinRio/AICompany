"""The rule evaluator: one pure function from state + market to directives.

``evaluate`` performs no I/O and holds no clock. Everything it needs is passed
in and everything it decides comes back out, so a schedule day can be replayed
byte-for-byte in a test -- which is the whole reason this rule set is code and
not a prompt.

Arbitration follows 鐵律③ ``M1 > S3 > S2 > S1 > P3 > P1 > P2 > R`` with the
correction CEO 裁決五 made to it:

* a freeze (M1 防守 / S3 / EMERGENCY) suppresses **only** the R series;
* S and P stay active in every mode, and a SELL line always outranks the freeze
  state itself -- 「凍結中不動作」 is never a valid answer for a batch that has
  met a stop-loss or take-profit condition;
* within one batch at most one rule fires per day, the highest-ranked one.

Two more rulings shape every line produced here. CEO 裁決七: the evaluation runs
on ``T`` closing data and every directive is stamped 依據資料日 ``T`` / 預定執行日
``T+1`` / 參考價 ``T 收盤`` with a ±2% limit band, except stop-loss lines, which
carry no band because leaving matters more than the price. 鐵律⑤ (and 風控 R6):
a symbol whose data is stale, unavailable or demo produces **no** line at all
that day, only a warning.

Assumptions that the rule set does not settle and CEO's seven rulings did not
cover are marked ``ASSUMPTION`` below and are restated in the hand-off notes
rather than being quietly buried.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from app.demo.series import DEMO_SOURCE
from app.playbook import wording
from app.playbook.calendar import TradingCalendar
from app.playbook.models import (
    Action,
    BatchSnapshot,
    BatchState,
    Directive,
    FastMarketState,
    IndexSnapshot,
    MarketSnapshot,
    Mode,
    PlaybookEvaluation,
    PortfolioState,
    RuleId,
    RuleParams,
    StateEffect,
    SymbolState,
)

#: Ladder rungs whose data may drive an executable directive (風控 R6). A
#: ``cached_stale`` rung is excluded even when it sits inside its TTL: the rung
#: itself means no live source answered.
USABLE_DATA_STATUSES: frozenset[str] = frozenset({"fresh", "backup"})

_HUNDRED = Decimal("100")


def is_usable(status: str, source: str) -> bool:
    """Whether a snapshot may produce an executable line (鐵律⑤ / 風控 R6)."""
    return status in USABLE_DATA_STATUSES and source != DEMO_SOURCE


def _limit_band(reference: Decimal, pct: Decimal) -> tuple[Decimal, Decimal]:
    span = reference * pct / _HUNDRED
    return reference - span, reference + span


def _make_directive(
    *,
    symbol: str,
    batch_no: int | None,
    action: Action,
    shares: int,
    rule_id: RuleId,
    rule_summary: str,
    snapshot: MarketSnapshot,
    execution_date: date,
    params: RuleParams,
    stop_loss: bool = False,
) -> Directive:
    """Build one line, attaching the band rule that applies to its kind."""
    reference = snapshot.close
    if stop_loss:
        low: Decimal | None = None
        high: Decimal | None = None
        limit_note = wording.STOP_LOSS_NO_BAND_NOTE
    else:
        low, high = _limit_band(reference, params.slippage_band_pct)
        limit_note = wording.limit_band_note(reference, low, high, params.slippage_band_pct)
    return Directive(
        symbol=symbol,
        batch_no=batch_no,
        action=action,
        shares=shares,
        rule_id=rule_id,
        rule_summary=rule_summary,
        data_date=snapshot.data_date,
        execution_date=execution_date,
        reference_price=reference,
        limit_low=low,
        limit_high=high,
        limit_note=limit_note,
        data_status=snapshot.data_status,
        source=snapshot.source,
    )


def _measured(rule_id: str, detail: str) -> str:
    """``rule text｜measurement`` -- the 最小事實陳述 shown on the line."""
    return f"{wording.RULE_TEXT[rule_id]}｜{detail}"


def _pct(value: Decimal) -> str:
    return f"{value:+.2f}%"


def _price(value: Decimal) -> str:
    return f"{value:.2f}"


def planned_batch_shares(
    *,
    batch_no: int,
    close: Decimal,
    symbol_batches: Sequence[BatchState],
    total_deploy: Decimal,
    params: RuleParams,
) -> int:
    """Shares for one batch under CEO 裁決二.

    ``BATCH_AMOUNT = TOTAL_DEPLOY / N_TARGETS / 3`` and
    ``SHARES = floor(BATCH_AMOUNT / close)``, floored at 1 share. The **last**
    batch absorbs the rounding remainder of the whole symbol: it gets
    ``floor(symbol_amount / close)`` minus whatever the earlier batches already
    hold (or would hold at today's close, if they have not been filled yet), so
    the three batches together spend the symbol's allocation instead of leaving
    up to three price-sized crumbs behind.
    """
    symbol_amount = total_deploy / Decimal(params.n_targets)
    per_batch = symbol_amount / Decimal(params.batches_per_target)
    if close <= 0:
        return 0
    if batch_no < params.batches_per_target:
        return max(1, int(per_batch // close))
    already = 0
    for batch in symbol_batches:
        if batch.batch_no >= batch_no:
            continue
        already += batch.shares if batch.status != "planned" else max(1, int(per_batch // close))
    return max(1, int(symbol_amount // close) - already)


def _symbol_average_cost(batches: Sequence[BatchState]) -> tuple[Decimal, int]:
    """Weighted average cost and total remaining shares of one symbol."""
    shares = 0
    total = Decimal("0")
    for batch in batches:
        if batch.status != "open" or batch.cost is None or batch.remaining_shares <= 0:
            continue
        shares += batch.remaining_shares
        total += batch.cost * Decimal(batch.remaining_shares)
    if shares == 0:
        return Decimal("0"), 0
    return total / Decimal(shares), shares


def _portfolio_unrealized_pct(
    batches: Sequence[BatchState], markets: Mapping[str, MarketSnapshot]
) -> Decimal | None:
    """Unrealised P/L of every open batch as a percentage of its cost basis.

    ASSUMPTION: 「組合新倉未實現」 is read as every batch this engine opened and
    still holds -- the engine never holds a position it did not open, so there
    is no older cohort to exclude. Batches whose symbol has no usable snapshot
    are left out rather than valued at cost (鐵律⑤: missing data is missing, not
    "unchanged"); ``None`` means nothing could be valued at all.
    """
    cost_basis = Decimal("0")
    market_value = Decimal("0")
    for batch in batches:
        snapshot = markets.get(batch.symbol)
        if batch.status != "open" or batch.cost is None or batch.remaining_shares <= 0:
            continue
        if snapshot is None or not is_usable(snapshot.data_status, snapshot.source):
            continue
        quantity = Decimal(batch.remaining_shares)
        cost_basis += batch.cost * quantity
        market_value += snapshot.close * quantity
    if cost_basis == 0:
        return None
    return (market_value - cost_basis) / cost_basis * _HUNDRED


def _defense_transition(
    index: IndexSnapshot | None,
    portfolio: PortfolioState,
    params: RuleParams,
) -> tuple[bool, list[StateEffect], list[str]]:
    """M1: turn defense on after N closes below the monthly line, off above it.

    When the index itself is missing or stale the previous state is carried
    forward untouched and a warning is emitted -- 企劃 §9.4's gap. Inventing
    "not below" from missing data would silently disarm the highest-priority
    switch in the rule set.
    """
    effects: list[StateEffect] = []
    warnings: list[str] = []
    if index is None or not is_usable(index.data_status, index.source):
        status = "unavailable" if index is None else index.data_status
        source = "none" if index is None else index.source
        warnings.append(wording.INDEX_DATA_GAP_NOTE.format(status=status, source=source))
        return portfolio.defense_active, effects, warnings
    if index.monthly_line is None:
        warnings.append(
            wording.INDEX_DATA_GAP_NOTE.format(status="insufficient_data", source=index.source)
        )
        return portfolio.defense_active, effects, warnings

    below = index.close < index.monthly_line
    if not portfolio.defense_active and below and index.days_below_monthly_line >= (
        params.m1_consecutive_days
    ):
        effects.append(
            StateEffect(
                kind="defense_on",
                value=index.days_below_monthly_line,
                note=_measured(
                    "M1",
                    f"指數收盤 {_price(index.close)} 低於月線 {_price(index.monthly_line)} "
                    f"連續 {index.days_below_monthly_line} 日",
                ),
            )
        )
        return True, effects, warnings
    if portfolio.defense_active and not below:
        effects.append(
            StateEffect(
                kind="defense_off",
                note=_measured(
                    "M1",
                    f"指數收盤 {_price(index.close)} 站回月線 {_price(index.monthly_line)}",
                ),
            )
        )
        return False, effects, warnings
    return portfolio.defense_active, effects, warnings


def _fast_market(index: IndexSnapshot | None, params: RuleParams) -> FastMarketState:
    """CEO 裁決六's two-condition test, evaluated on the index snapshot."""
    if index is None:
        return FastMarketState(
            active=False, annualized_vol_20d=None, large_move_days=0, reason=None
        )
    vol = index.annualized_vol_20d
    by_vol = vol is not None and vol > params.fast_market_vol_threshold
    by_moves = index.large_move_days >= params.fast_market_move_count
    active = by_vol or by_moves
    reason = (
        wording.FAST_MARKET_REASON.format(
            vol="—" if vol is None else f"{vol:.1f}",
            lookback=params.fast_market_lookback_days,
            moves=index.large_move_days,
        )
        if active
        else None
    )
    return FastMarketState(
        active=active,
        annualized_vol_20d=vol,
        large_move_days=index.large_move_days,
        reason=reason,
    )


def _resolve_mode(
    *,
    data_date: date,
    portfolio: PortfolioState,
    defense_active: bool,
    s3_freeze_until: date | None,
    s3_reason: str | None,
) -> tuple[Mode, str]:
    if portfolio.emergency_until is not None and data_date <= portfolio.emergency_until:
        return "emergency_frozen", wording.MODE_REASON_EMERGENCY.format(
            until=portfolio.emergency_until.isoformat()
        )
    freeze_until = s3_freeze_until or portfolio.freeze_until
    reason = s3_reason or portfolio.freeze_reason
    if freeze_until is not None and data_date <= freeze_until:
        return "frozen", wording.mode_reason_frozen(reason or wording.RULE_TEXT["S3"], freeze_until)
    if defense_active:
        return "defense", wording.MODE_REASON_DEFENSE.format(days=1)
    return "normal", wording.MODE_REASON_NORMAL


class _SellPass:
    """Accumulator for the S/P pass over one symbol's batches."""

    def __init__(self) -> None:
        self.directives: list[Directive] = []
        self.effects: list[StateEffect] = []
        #: Batches that produced a sell, so the R pass skips them today.
        self.touched: set[tuple[str, int]] = set()


def _evaluate_batch_exits(
    *,
    batch: BatchState,
    snapshot: MarketSnapshot,
    defense_active: bool,
    execution_date: date,
    calendar: TradingCalendar,
    params: RuleParams,
    out: _SellPass,
) -> None:
    """S1 -> P3 -> P1 -> P2 for one open batch; at most one line comes out."""
    if batch.status != "open" or batch.cost is None or batch.remaining_shares <= 0:
        return
    close = snapshot.close
    cost = batch.cost
    key = (batch.symbol, batch.batch_no)

    # --- S1 单批停損 (0.90, tightened to 0.93 in defense mode) ---------------
    # ASSUMPTION: the tightened threshold applies to every open batch the moment
    # defense starts, not only to batches opened afterwards (企劃問題 15, which
    # CEO's seven rulings did not cover).
    s1_ratio = params.s1_defense_ratio if defense_active else params.s1_ratio
    if close < cost * s1_ratio:
        out.directives.append(
            _make_directive(
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                action="sell",
                shares=batch.remaining_shares,
                rule_id="S1",
                rule_summary=_measured(
                    "S1",
                    f"收盤 {_price(close)} < 成本 {_price(cost)} ×{s1_ratio:g} "
                    f"= {_price(cost * s1_ratio)}",
                ),
                snapshot=snapshot,
                execution_date=execution_date,
                params=params,
                stop_loss=True,
            )
        )
        out.effects.append(
            StateEffect(
                kind="batch_closed",
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                value=batch.remaining_shares,
                note="S1 停損賣出該批",
            )
        )
        out.effects.append(
            StateEffect(
                kind="pause_symbol",
                symbol=batch.symbol,
                note="S1：該檔排程暫停，收盤站回 25MA 後恢復",
            )
        )
        out.touched.add(key)
        return

    # --- P3 過熱減碼 --------------------------------------------------------
    bias_limit = params.p3_bias_limit_high_vol if snapshot.high_volatility else params.p3_bias_limit
    cooled_down = batch.p3_last_date is None or (
        calendar.trading_days_between(batch.p3_last_date, snapshot.data_date)
        >= params.p3_cooldown_trading_days
    )
    if snapshot.bias25 is not None and snapshot.bias25 > bias_limit and cooled_down:
        shares = batch.remaining_shares // 3
        if shares > 0:
            out.directives.append(
                _make_directive(
                    symbol=batch.symbol,
                    batch_no=batch.batch_no,
                    action="sell",
                    shares=shares,
                    rule_id="P3",
                    rule_summary=_measured(
                        "P3",
                        f"BIAS25 {_pct(snapshot.bias25)} > {bias_limit:g}%"
                        f"{'（高波動清單）' if snapshot.high_volatility else ''}，"
                        f"減 1/3 = {shares} 股",
                    ),
                    snapshot=snapshot,
                    execution_date=execution_date,
                    params=params,
                )
            )
            out.effects.append(
                StateEffect(
                    kind="batch_reduced",
                    symbol=batch.symbol,
                    batch_no=batch.batch_no,
                    value=shares,
                    note="P3 過熱減碼 1/3",
                )
            )
            out.effects.append(
                StateEffect(
                    kind="p3_marked",
                    symbol=batch.symbol,
                    batch_no=batch.batch_no,
                    note=f"P3 冷卻起算日 {snapshot.data_date.isoformat()}",
                )
            )
            out.touched.add(key)
            return

    # --- P1 / P2 停利 -------------------------------------------------------
    # ASSUMPTION: 「賣 1/3」 is one third of *this batch's original* shares
    # (企劃問題 6/7, not covered by CEO's rulings), so P1 and P2 each cut the
    # same slice and P2's 「餘」 is what is left after both.
    third = batch.shares // 3
    if not batch.p1_done and close >= cost * params.p1_ratio:
        shares = min(max(third, 1), batch.remaining_shares)
        out.directives.append(
            _make_directive(
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                action="sell",
                shares=shares,
                rule_id="P1",
                rule_summary=_measured(
                    "P1",
                    f"收盤 {_price(close)} ≥ 成本 {_price(cost)} ×{params.p1_ratio:g} "
                    f"= {_price(cost * params.p1_ratio)}，賣 1/3 = {shares} 股",
                ),
                snapshot=snapshot,
                execution_date=execution_date,
                params=params,
            )
        )
        out.effects.append(
            StateEffect(
                kind="batch_reduced",
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                value=shares,
                note="P1 停利賣 1/3",
            )
        )
        out.effects.append(
            StateEffect(
                kind="p1_done", symbol=batch.symbol, batch_no=batch.batch_no, note="P1 已執行"
            )
        )
        out.touched.add(key)
        return

    if not batch.p2_done and close >= cost * params.p2_ratio:
        shares = min(max(third, 1), batch.remaining_shares)
        out.directives.append(
            _make_directive(
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                action="sell",
                shares=shares,
                rule_id="P2",
                rule_summary=_measured(
                    "P2",
                    f"收盤 {_price(close)} ≥ 成本 {_price(cost)} ×{params.p2_ratio:g} "
                    f"= {_price(cost * params.p2_ratio)}，再賣 1/3 = {shares} 股，餘轉移動停利",
                ),
                snapshot=snapshot,
                execution_date=execution_date,
                params=params,
            )
        )
        out.effects.append(
            StateEffect(
                kind="batch_reduced",
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                value=shares,
                note="P2 停利再賣 1/3",
            )
        )
        out.effects.append(
            StateEffect(
                kind="p2_done", symbol=batch.symbol, batch_no=batch.batch_no, note="P2 已執行"
            )
        )
        out.effects.append(
            StateEffect(
                kind="trailing_on",
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                note="P2：餘額轉移動停利",
            )
        )
        out.touched.add(key)
        return

    # --- 移動停利出清 (P2 餘額, or a profitable batch in defense mode) -------
    trailing = batch.trailing_active or (defense_active and close > cost)
    if trailing and not batch.trailing_active and defense_active:
        out.effects.append(
            StateEffect(
                kind="trailing_on",
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                note="M1 防守模式：獲利部位套移動停利",
            )
        )
    if not trailing:
        return
    peak = batch.peak_close
    below_ma = snapshot.ma25 is not None and close < snapshot.ma25
    below_peak = peak is not None and close < peak * params.p2_trailing_peak_ratio
    if not (below_ma or below_peak):
        return
    trigger = (
        f"收盤 {_price(close)} 跌破 25MA {_price(snapshot.ma25)}"
        if below_ma and snapshot.ma25 is not None
        else f"收盤 {_price(close)} < 波段最高收盤 {_price(peak or close)} "
        f"×{params.p2_trailing_peak_ratio:g}"
    )
    out.directives.append(
        _make_directive(
            symbol=batch.symbol,
            batch_no=batch.batch_no,
            action="sell",
            shares=batch.remaining_shares,
            rule_id="P2",
            rule_summary=_measured("P2", f"移動停利觸發：{trigger}，出清該批餘額"),
            snapshot=snapshot,
            execution_date=execution_date,
            params=params,
        )
    )
    out.effects.append(
        StateEffect(
            kind="batch_closed",
            symbol=batch.symbol,
            batch_no=batch.batch_no,
            value=batch.remaining_shares,
            note="P2 移動停利出清",
        )
    )
    out.touched.add(key)


def _evaluate_symbol_stop(
    *,
    symbol: str,
    symbol_batches: Sequence[BatchState],
    snapshot: MarketSnapshot,
    execution_date: date,
    calendar: TradingCalendar,
    params: RuleParams,
    out: _SellPass,
) -> bool:
    """S2: whole-symbol liquidation plus a 60-trading-day blacklist.

    Returns ``True`` when it fired, in which case the per-batch pass is skipped
    for this symbol -- S2 outranks S1/P per 鐵律③ and there is nothing left to
    sell afterwards.
    """
    average_cost, shares = _symbol_average_cost(symbol_batches)
    if shares == 0 or average_cost == 0:
        return False
    if snapshot.close >= average_cost * params.s2_ratio:
        return False
    until = calendar.shift(snapshot.data_date, params.s2_blacklist_trading_days)
    out.directives.append(
        _make_directive(
            symbol=symbol,
            batch_no=None,
            action="sell",
            shares=shares,
            rule_id="S2",
            rule_summary=_measured(
                "S2",
                f"收盤 {_price(snapshot.close)} < 均成本 {_price(average_cost)} "
                f"×{params.s2_ratio:g} = {_price(average_cost * params.s2_ratio)}，"
                f"出清 {shares} 股",
            ),
            snapshot=snapshot,
            execution_date=execution_date,
            params=params,
            stop_loss=True,
        )
    )
    for batch in symbol_batches:
        if batch.status == "open" and batch.remaining_shares > 0:
            out.effects.append(
                StateEffect(
                    kind="batch_closed",
                    symbol=symbol,
                    batch_no=batch.batch_no,
                    value=batch.remaining_shares,
                    note="S2 出清整檔",
                )
            )
            out.touched.add((symbol, batch.batch_no))
    out.effects.append(
        StateEffect(
            kind="blacklist",
            symbol=symbol,
            value=params.s2_blacklist_trading_days,
            note=(
                f"S2：黑名單 {params.s2_blacklist_trading_days} 交易日，"
                f"至 {until.isoformat()}；名額不補"
            ),
        )
    )
    return True


def _evaluate_entries(
    *,
    symbol: str,
    symbol_batches: Sequence[BatchState],
    snapshot: MarketSnapshot,
    execution_date: date,
    total_deploy: Decimal,
    params: RuleParams,
    touched: set[tuple[str, int]],
) -> tuple[list[Directive], list[StateEffect]]:
    """R1/R2/R3 for the next unfilled batch of one symbol.

    Only one batch per symbol is queued per schedule day (the rule set buys "下
    一批", not all remaining batches at once).
    """
    directives: list[Directive] = []
    effects: list[StateEffect] = []
    pending = [
        batch
        for batch in sorted(symbol_batches, key=lambda item: item.batch_no)
        if batch.status == "planned" and (symbol, batch.batch_no) not in touched
    ]
    if not pending:
        return directives, effects
    batch = pending[0]

    # R3 first: a batch that already used up its three deferrals is skipped
    # rather than deferred a fourth time.
    if batch.defer_count >= params.r3_max_defers:
        directives.append(
            _make_directive(
                symbol=symbol,
                batch_no=batch.batch_no,
                action="skip",
                shares=0,
                rule_id="R3",
                rule_summary=_measured(
                    "R3", f"順延已達 {batch.defer_count} 次，跳過本批"
                ),
                snapshot=snapshot,
                execution_date=execution_date,
                params=params,
            )
        )
        effects.append(
            StateEffect(
                kind="batch_skipped",
                symbol=symbol,
                batch_no=batch.batch_no,
                value=batch.defer_count,
                note="R3：順延 3 次後跳過本批",
            )
        )
        return directives, effects

    change = snapshot.change_pct
    bias25 = snapshot.bias25
    chased = (change is not None and change > params.r2_change_pct_limit) or (
        bias25 is not None and bias25 > params.r2_bias_limit
    )
    if chased:
        new_count = batch.defer_count + 1
        detail = (
            f"漲幅 {_pct(change) if change is not None else '—'}、"
            f"BIAS25 {_pct(bias25) if bias25 is not None else '—'}；"
            f"順延第 {new_count} 次"
        )
        if new_count >= params.r3_max_defers:
            directives.append(
                _make_directive(
                    symbol=symbol,
                    batch_no=batch.batch_no,
                    action="skip",
                    shares=0,
                    rule_id="R3",
                    rule_summary=_measured(
                        "R3", f"{detail}，累計達 {params.r3_max_defers} 次，跳過本批"
                    ),
                    snapshot=snapshot,
                    execution_date=execution_date,
                    params=params,
                )
            )
            effects.append(
                StateEffect(
                    kind="defer_increment",
                    symbol=symbol,
                    batch_no=batch.batch_no,
                    value=new_count,
                    note="R2：不追價煞車順延",
                )
            )
            effects.append(
                StateEffect(
                    kind="batch_skipped",
                    symbol=symbol,
                    batch_no=batch.batch_no,
                    value=new_count,
                    note="R3：順延 3 次後跳過本批",
                )
            )
            return directives, effects
        directives.append(
            _make_directive(
                symbol=symbol,
                batch_no=batch.batch_no,
                action="defer",
                shares=0,
                rule_id="R2",
                rule_summary=_measured("R2", detail),
                snapshot=snapshot,
                execution_date=execution_date,
                params=params,
            )
        )
        effects.append(
            StateEffect(
                kind="defer_increment",
                symbol=symbol,
                batch_no=batch.batch_no,
                value=new_count,
                note="R2：不追價煞車順延",
            )
        )
        return directives, effects

    shares = planned_batch_shares(
        batch_no=batch.batch_no,
        close=snapshot.close,
        symbol_batches=symbol_batches,
        total_deploy=total_deploy,
        params=params,
    )
    if shares <= 0:
        return directives, effects
    directives.append(
        _make_directive(
            symbol=symbol,
            batch_no=batch.batch_no,
            action="buy",
            shares=shares,
            rule_id="R1",
            rule_summary=_measured(
                "R1",
                f"排程日進場第 {batch.batch_no} 批，參考價 {_price(snapshot.close)}，"
                f"股數 {shares}",
            ),
            snapshot=snapshot,
            execution_date=execution_date,
            params=params,
        )
    )
    effects.append(
        StateEffect(
            kind="batch_entered",
            symbol=symbol,
            batch_no=batch.batch_no,
            value=shares,
            note="R1：排程日進場",
        )
    )
    return directives, effects


def _apply_cash_floor(
    *,
    directives: Sequence[Directive],
    effects: Sequence[StateEffect],
    portfolio: PortfolioState,
    batches: Sequence[BatchState],
    markets: Mapping[str, MarketSnapshot],
    params: RuleParams,
) -> tuple[list[Directive], list[StateEffect], list[str]]:
    """鐵律①: shrink (or drop) buy lines so cash never falls below 30%.

    ``max_spend = cash - cash_floor_ratio × total_assets``. Buying does not move
    total assets (cash turns into stock of the same value), so the floor is a
    plain budget: each buy line is capped at what is left of it, in symbol order,
    and a line capped to zero shares is dropped with a warning rather than
    issued as a "0 股" instruction.
    """
    total_assets = portfolio.cash
    for batch in batches:
        snapshot = markets.get(batch.symbol)
        if batch.status != "open" or batch.remaining_shares <= 0 or snapshot is None:
            continue
        total_assets += snapshot.close * Decimal(batch.remaining_shares)
    budget = portfolio.cash - params.cash_floor_ratio * total_assets

    kept: list[Directive] = []
    warnings: list[str] = []
    dropped: set[tuple[str, int | None]] = set()
    for directive in directives:
        if directive.action != "buy" or directive.reference_price is None:
            kept.append(directive)
            continue
        price = directive.reference_price
        affordable = max(0, int(budget // price)) if budget > 0 else 0
        if affordable <= 0:
            warnings.append(
                wording.SHRINK_TO_ZERO_NOTE.format(
                    symbol=directive.symbol, batch_no=directive.batch_no
                )
            )
            dropped.add((directive.symbol, directive.batch_no))
            continue
        if affordable < directive.shares:
            note = wording.SHRINK_NOTE.format(planned=directive.shares, actual=affordable)
            warnings.append(f"{directive.symbol}：{note}")
            directive = directive.model_copy(
                update={
                    "shares": affordable,
                    "rule_summary": f"{directive.rule_summary}｜{note}",
                }
            )
        budget -= price * Decimal(directive.shares)
        kept.append(directive)

    kept_effects = [
        (
            effect.model_copy(update={"value": _shares_for(kept, effect)})
            if effect.kind == "batch_entered"
            else effect
        )
        for effect in effects
        if not (effect.kind == "batch_entered" and (effect.symbol, effect.batch_no) in dropped)
    ]
    return kept, kept_effects, warnings


def _shares_for(directives: Sequence[Directive], effect: StateEffect) -> int | None:
    for directive in directives:
        if directive.symbol == effect.symbol and directive.batch_no == effect.batch_no:
            return directive.shares
    return effect.value


def _snapshot_rows(
    batches: Sequence[BatchState], markets: Mapping[str, MarketSnapshot]
) -> list[BatchSnapshot]:
    rows: list[BatchSnapshot] = []
    for batch in sorted(batches, key=lambda item: (item.symbol, item.batch_no)):
        snapshot = markets.get(batch.symbol)
        close = snapshot.close if snapshot is not None else None
        unrealized = (
            (close - batch.cost) / batch.cost * _HUNDRED
            if close is not None and batch.cost is not None and batch.cost != 0
            else None
        )
        rows.append(
            BatchSnapshot(
                symbol=batch.symbol,
                batch_no=batch.batch_no,
                status=batch.status,
                entry_date=batch.entry_date,
                cost=batch.cost,
                close=close,
                remaining_shares=batch.remaining_shares,
                peak_close=batch.peak_close,
                unrealized_pct=unrealized,
            )
        )
    return rows


def evaluate(
    *,
    data_date: date,
    calendar: TradingCalendar,
    params: RuleParams,
    index: IndexSnapshot | None,
    markets: Mapping[str, MarketSnapshot],
    batches: Sequence[BatchState],
    symbols: Mapping[str, SymbolState],
    portfolio: PortfolioState,
) -> PlaybookEvaluation:
    """Evaluate one 依據資料日 and return the directives it produced."""
    execution_date = calendar.next_trading_day(data_date)
    is_schedule_day = calendar.is_schedule_day(data_date)

    defense_active, effects, warnings = _defense_transition(index, portfolio, params)
    fast_market = _fast_market(index, params)
    index_usable = index is not None and is_usable(index.data_status, index.source)

    # --- S3 組合熔斷 --------------------------------------------------------
    s3_until: date | None = None
    s3_reason: str | None = None
    unrealized = _portfolio_unrealized_pct(batches, markets)
    already_frozen = portfolio.freeze_until is not None and data_date <= portfolio.freeze_until
    if not already_frozen and unrealized is not None and unrealized < params.s3_unrealized_pct:
        s3_until = calendar.shift(data_date, params.s3_freeze_trading_days)
        s3_reason = _measured(
            "S3",
            f"組合新倉未實現 {_pct(unrealized)} < {params.s3_unrealized_pct:g}%，"
            f"凍結 {params.s3_freeze_trading_days} 交易日",
        )
        effects.append(
            StateEffect(
                kind="freeze_portfolio",
                value=params.s3_freeze_trading_days,
                note=f"{s3_reason}，至 {s3_until.isoformat()}",
            )
        )

    mode, mode_reason = _resolve_mode(
        data_date=data_date,
        portfolio=portfolio,
        defense_active=defense_active,
        s3_freeze_until=s3_until,
        s3_reason=s3_reason,
    )
    if mode == "defense" and index is not None:
        mode_reason = wording.MODE_REASON_DEFENSE.format(days=index.days_below_monthly_line)

    #: 凍結 suppresses only the R series (CEO 裁決五).
    entries_allowed = mode == "normal" and is_schedule_day and index_usable
    if mode != "normal":
        warnings.append(wording.FROZEN_NOTE.format(mode=wording.MODE_LABELS[mode]))
    elif not is_schedule_day:
        warnings.append(wording.NOT_SCHEDULE_DAY_NOTE.format(data_date=data_date.isoformat()))

    by_symbol: dict[str, list[BatchState]] = {}
    for batch in batches:
        by_symbol.setdefault(batch.symbol, []).append(batch)

    out = _SellPass()
    entry_directives: list[Directive] = []
    entry_effects: list[StateEffect] = []

    for symbol in sorted(by_symbol):
        symbol_batches = sorted(by_symbol[symbol], key=lambda item: item.batch_no)
        snapshot = markets.get(symbol)
        if snapshot is None or not is_usable(snapshot.data_status, snapshot.source):
            status = "unavailable" if snapshot is None else snapshot.data_status
            source = "none" if snapshot is None else snapshot.source
            warnings.append(
                wording.DATA_GAP_NOTE.format(symbol=symbol, status=status, source=source)
            )
            continue

        state = symbols.get(symbol, SymbolState(symbol=symbol))
        # S1 恢復: 站回 25MA clears the pause and zeroes the deferral counters
        # (CEO 裁決三). ASSUMPTION: a single close at or above MA25 is enough
        # (企劃問題 9 was not among the seven rulings).
        if state.paused and snapshot.ma25 is not None and snapshot.close >= snapshot.ma25:
            out.effects.append(
                StateEffect(
                    kind="resume_symbol",
                    symbol=symbol,
                    note=_measured(
                        "S1",
                        f"收盤 {_price(snapshot.close)} 站回 25MA {_price(snapshot.ma25)}，"
                        "排程恢復、順延計數歸零",
                    ),
                )
            )
            out.effects.append(
                StateEffect(kind="defer_reset", symbol=symbol, note="S1 恢復：順延計數歸零")
            )
            state = state.model_copy(update={"paused": False})

        if not _evaluate_symbol_stop(
            symbol=symbol,
            symbol_batches=symbol_batches,
            snapshot=snapshot,
            execution_date=execution_date,
            calendar=calendar,
            params=params,
            out=out,
        ):
            for batch in symbol_batches:
                _evaluate_batch_exits(
                    batch=batch,
                    snapshot=snapshot,
                    defense_active=defense_active,
                    execution_date=execution_date,
                    calendar=calendar,
                    params=params,
                    out=out,
                )

        if not entries_allowed or state.paused or state.blacklisted:
            continue
        symbol_entries, symbol_effects = _evaluate_entries(
            symbol=symbol,
            symbol_batches=symbol_batches,
            snapshot=snapshot,
            execution_date=execution_date,
            total_deploy=portfolio.total_deploy,
            params=params,
            touched=out.touched,
        )
        entry_directives.extend(symbol_entries)
        entry_effects.extend(symbol_effects)

    entry_directives, entry_effects, shrink_warnings = _apply_cash_floor(
        directives=entry_directives,
        effects=entry_effects,
        portfolio=portfolio,
        batches=batches,
        markets=markets,
        params=params,
    )
    warnings.extend(shrink_warnings)

    return PlaybookEvaluation(
        data_date=data_date,
        execution_date=execution_date,
        mode=mode,
        mode_reason=mode_reason,
        is_schedule_day=is_schedule_day,
        fast_market=fast_market,
        rules_version=params.version,
        directives=[*out.directives, *entry_directives],
        effects=[*effects, *out.effects, *entry_effects],
        warnings=warnings,
        snapshot=_snapshot_rows(batches, markets),
    )


def settle_directive(directive: Directive, *, open_price: Decimal) -> Directive:
    """T+1 outcome of one line against the opening price (CEO 裁決七).

    A stop-loss line has no band and is always executed -- 離場確定性優先於價格.
    Any other line whose open sits outside 參考價 ±2% is marked ``missed``: the
    engine does not chase, and the batch is re-evaluated on the next 依據資料日.
    """
    if directive.limit_low is None or directive.limit_high is None:
        return directive.model_copy(update={"status": "executed"})
    inside = directive.limit_low <= open_price <= directive.limit_high
    return directive.model_copy(update={"status": "executed" if inside else "missed"})
