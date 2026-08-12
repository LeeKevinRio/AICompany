"""Data model for the playbook engine: inputs, state, parameters, directives.

Money and price ratios are ``Decimal`` end to end (the project data convention);
only the annualised volatility of the index is a float, because it comes out of
a log-return computation where exactness has no meaning.

Three families live here:

* **Snapshots** -- what the market said on the 依據資料日 ``T`` (per symbol and
  for the index). They carry their own ``data_status`` / ``source`` so 鐵律⑤ and
  風控 R5/R6 can be decided from the input itself, not from a side channel.
* **State** -- everything that has to survive between schedule days: batches,
  deferral counters, pauses, blacklist, freeze and defense flags. The engine
  reads it and returns :class:`StateEffect` records; only the store writes.
* **Parameters** -- :class:`RuleParams`, versioned and dated. 鐵律④ means a
  submitted change is never the version used today (see
  :mod:`app.playbook.store`), so the parameter set is an input like any other.

Every threshold in :class:`RuleParams` restates a number from the user's own
rule set; none of them is a default the engine invented.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: The five actions the user's rule set names (買進/賣出/順延/跳過/無動作).
#: 凍結 is a *mode*, not a per-line action, so it is not in this list: a frozen
#: schedule produces no R-series line at all rather than a "凍結" line.
Action = Literal["buy", "sell", "defer", "skip", "none"]

#: 正常／防守（M1）／全凍結（S3）／緊急出清後凍結（EMERGENCY_EXIT）.
Mode = Literal["normal", "defense", "frozen", "emergency_frozen"]

#: Lifecycle of one batch. ``planned`` has never been filled, ``open`` holds
#: shares, ``closed`` was sold out, ``skipped`` was abandoned by R3.
BatchStatus = Literal["planned", "open", "closed", "skipped"]

#: T+1 execution outcome of one directive (CEO 裁決七).
DirectiveStatus = Literal["pending", "executed", "missed"]

#: Rule ids exactly as the user wrote them, plus ``REBALANCE`` -- the quarterly
#: recomputation of TOTAL_DEPLOY (CEO 裁決一), which is a dated capital decision
#: rather than a market rule, and so has no R/S/P number of its own.
RuleId = Literal[
    "R1", "R2", "R3", "R4", "S1", "S2", "S3", "P1", "P2", "P3", "M1", "IRON1",
    "EMERGENCY", "REBALANCE",
]


class RuleParams(BaseModel):
    """One dated version of the rule parameters (鐵律④: 次日生效).

    ``version`` is monotonic and ``effective_date`` is the first day the version
    may be used. The engine is handed the version that is already effective for
    the 依據資料日; it has no way to reach a pending one.
    """

    model_config = ConfigDict(frozen=True)

    version: int = 1
    effective_date: date

    # --- capital allocation (CEO 裁決一/二) ---
    #: 現金 30% 鐵律 -- the floor cash may not go below.
    cash_floor_ratio: Decimal = Decimal("0.30")
    #: TOTAL_DEPLOY = 總資產 × 70%, locked at the start of the quarter.
    deploy_ratio: Decimal = Decimal("0.70")
    n_targets: int = 5
    batches_per_target: int = 3

    # --- entry (R) ---
    r2_change_pct_limit: Decimal = Decimal("3")
    r2_bias_limit: Decimal = Decimal("10")
    r3_max_defers: int = 3

    # --- stop loss (S) ---
    s1_ratio: Decimal = Decimal("0.90")
    s1_defense_ratio: Decimal = Decimal("0.93")
    s2_ratio: Decimal = Decimal("0.85")
    s2_blacklist_trading_days: int = 60
    s3_unrealized_pct: Decimal = Decimal("-8")
    s3_freeze_trading_days: int = 10

    # --- take profit (P) ---
    p1_ratio: Decimal = Decimal("1.20")
    p2_ratio: Decimal = Decimal("1.35")
    p2_trailing_peak_ratio: Decimal = Decimal("0.88")
    p3_bias_limit: Decimal = Decimal("15")
    p3_bias_limit_high_vol: Decimal = Decimal("20")
    p3_cooldown_trading_days: int = 10

    # --- market master switch (M1) ---
    m1_consecutive_days: int = 3
    #: 月線 window in trading days. The Taiwan convention on a daily chart is the
    #: 20 日均線; it is a parameter so a different reading can be dated in
    #: rather than patched into code.
    index_monthly_line_window: int = 20

    # --- fast market (CEO 裁決六) ---
    fast_market_vol_threshold: float = 30.0
    fast_market_move_pct: Decimal = Decimal("2")
    fast_market_move_count: int = 2
    fast_market_lookback_days: int = 5
    emergency_freeze_trading_days: int = 20

    # --- T+1 execution (CEO 裁決七) ---
    #: 限價帶 = T 收盤 ±2%. Stop-loss (S 系列) lines carry no band at all.
    slippage_band_pct: Decimal = Decimal("2")


class MarketSnapshot(BaseModel):
    """One symbol's 依據資料日 close and the indicators the rules read."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    data_date: date
    close: Decimal
    #: 漲跌幅 in percent (``+3.5`` means +3.5%). ``None`` when there is no
    #: previous close to compare against.
    change_pct: Decimal | None
    ma25: Decimal | None
    #: BIAS25 = (close - MA25) / MA25 in percent.
    bias25: Decimal | None
    #: Ladder rung that answered (``fresh`` / ``backup`` / ``cached_stale`` /
    #: ``unavailable``) -- 風控 R5.
    data_status: str
    source: str
    #: 高波動清單 membership only changes the P3 threshold (15% -> 20%).
    high_volatility: bool = False


class IndexSnapshot(BaseModel):
    """加權指數 for M1 and the fast-market test."""

    model_config = ConfigDict(frozen=True)

    data_date: date
    close: Decimal
    monthly_line: Decimal | None
    #: Consecutive trading days whose close sat below the monthly line, counted
    #: up to and including ``data_date``.
    days_below_monthly_line: int
    #: 20 日年化波動率 in percent; ``None`` when there is not enough history.
    annualized_vol_20d: float | None
    #: How many of the last N trading days moved |漲跌幅| ≥ 2%.
    large_move_days: int
    data_status: str
    source: str


class BatchState(BaseModel):
    """One of the three batches of one symbol, plus its schedule counters."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    batch_no: int = Field(ge=1)
    status: BatchStatus = "planned"
    entry_date: date | None = None
    #: Per-share cost of this batch (never an average across batches).
    cost: Decimal | None = None
    #: Shares originally filled -- the denominator P1/P2 read (賣 1/3 of 本批).
    shares: int = 0
    remaining_shares: int = 0
    #: 波段最高收盤 since entry, rolled forward every trading day.
    peak_close: Decimal | None = None
    p1_done: bool = False
    p2_done: bool = False
    p3_last_date: date | None = None
    #: Set by P2 (餘轉移動停利) and by M1 defense on a profitable batch.
    trailing_active: bool = False
    #: R2 deferrals accumulated for this batch; R3 skips it at 3.
    defer_count: int = 0
    #: T+1 lines of this batch that came back MISSED. CEO 裁決 E-2 aligns the
    #: retry ceiling with R3, so this counter is read against ``r3_max_defers``.
    missed_count: int = 0
    #: The schedule day this batch is queued for, if any.
    scheduled_date: date | None = None


class SymbolState(BaseModel):
    """Per-symbol flags that outlive a single batch."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    #: S1 排程暫停 -- lifted when the close stands back above MA25.
    paused: bool = False
    paused_since: date | None = None
    #: S2 黑名單, 60 交易日 (CEO 裁決四). 名額不補.
    blacklisted: bool = False
    blacklist_until: date | None = None


class PortfolioState(BaseModel):
    """Portfolio-level money and the three freeze/defense flags."""

    model_config = ConfigDict(frozen=True)

    cash: Decimal
    #: 期初鎖定的 TOTAL_DEPLOY (CEO 裁決一). Realised gains do not raise it.
    total_deploy: Decimal
    #: When the locked value was written, and by which path (CEO 裁決 D-2:
    #: 鎖定值落檔含時間戳與輸入來源). ``None`` until capital is set once.
    total_deploy_set_at: datetime | None = None
    #: ``initial`` / ``rebalance`` / whatever the caller named as its input.
    total_deploy_source: str | None = None
    #: S3 全凍結 end date, inclusive. ``None`` when not frozen.
    freeze_until: date | None = None
    freeze_reason: str | None = None
    #: EMERGENCY_EXIT 凍結 end date, inclusive (20 交易日).
    emergency_until: date | None = None
    defense_active: bool = False
    defense_since: date | None = None


class StateEffect(BaseModel):
    """A state change the engine decided on and the store must persist.

    The engine stays pure: it never writes. Each effect names what changed, for
    whom, and carries the sentence that explains it, so the directive log
    (風控 R16) can be reconstructed from effects alone.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal[
        "pause_symbol",
        "resume_symbol",
        "blacklist",
        "freeze_portfolio",
        "defense_on",
        "defense_off",
        "defer_increment",
        "defer_reset",
        "batch_entered",
        "batch_reduced",
        "batch_closed",
        "batch_skipped",
        "p1_done",
        "p2_done",
        "p3_marked",
        "trailing_on",
        "emergency_exit",
    ]
    symbol: str | None = None
    batch_no: int | None = None
    #: Shares moved, or trading days of a freeze -- whichever the kind implies.
    value: int | None = None
    note: str


class Directive(BaseModel):
    """One line of the 今日指令表.

    Carries the full T/T+1 provenance CEO 裁決七 requires on *every* line:
    依據資料日 (``data_date``), 預定執行日 (``execution_date``) and 參考價
    (``reference_price``), plus the slippage band. Stop-loss lines carry no band
    (``limit_low``/``limit_high`` are ``None``): leaving is more important than
    the price it leaves at.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    batch_no: int | None
    action: Action
    shares: int
    rule_id: RuleId
    #: 最小事實陳述 of what the rule says and what was measured (風控 R1).
    rule_summary: str
    data_date: date
    execution_date: date
    reference_price: Decimal | None
    limit_low: Decimal | None
    limit_high: Decimal | None
    #: Why the band is what it is, including "停損無滑價帶" when it is absent.
    limit_note: str
    data_status: str
    source: str
    status: DirectiveStatus = "pending"


class BatchSnapshot(BaseModel):
    """One open batch as shown in the 部位快照."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    batch_no: int
    status: BatchStatus
    entry_date: date | None
    cost: Decimal | None
    close: Decimal | None
    remaining_shares: int
    peak_close: Decimal | None
    #: (close - cost) / cost in percent; ``None`` when either side is unknown.
    unrealized_pct: Decimal | None


class FastMarketState(BaseModel):
    """Whether the fast-market test fired, and on which measurement.

    CEO 裁決六: a fast market *raises* the refusal strength, never lowers it, so
    this state is reported alongside every refusal rather than being used to
    relax a rule.

    The state is persisted between days (風控 FM-1). When the index snapshot is
    missing or stale the previous verdict is carried forward untouched --
    ``carried_forward`` says so on the response -- and the test can never fire
    for the *first* time on data that is not usable: entering 快市 is a judgement
    about the market, and unusable data is not a measurement of the market.
    """

    model_config = ConfigDict(frozen=True)

    active: bool
    annualized_vol_20d: float | None
    large_move_days: int
    reason: str | None
    #: ``True`` when this verdict was carried over from an earlier day because
    #: today's index data was not usable.
    carried_forward: bool = False
    #: 依據資料日 the verdict was actually measured on.
    measured_on: date | None = None


class SettledLine(BaseModel):
    """One directive whose T+1 outcome has been stamped onto the book."""

    model_config = ConfigDict(frozen=True)

    directive_id: int
    directive: Directive
    #: The 開盤價 the outcome was decided against.
    open_price: Decimal


class UnsettledLine(BaseModel):
    """One directive that could **not** be settled, and why (風控 R5).

    A line with no opening price is reported as unsettled rather than being
    guessed at, closed at the reference price, or silently dropped.
    """

    model_config = ConfigDict(frozen=True)

    directive_id: int
    directive: Directive
    reason: str


class SettlementResult(BaseModel):
    """What one settlement run did (CEO 裁決七 T+1 結算).

    Replay-safe: a line is claimed in the log before the book is touched, so
    running this twice over the same day settles nothing the second time and
    ``settled`` comes back empty rather than deducting the same shares again.
    """

    model_config = ConfigDict(frozen=True)

    settled_on: date
    settled: list[SettledLine]
    unsettled: list[UnsettledLine]
    warnings: list[str]

    @property
    def executed(self) -> int:
        return sum(1 for line in self.settled if line.directive.status == "executed")

    @property
    def missed(self) -> int:
        return sum(1 for line in self.settled if line.directive.status == "missed")


class RebalanceResult(BaseModel):
    """季末 REBALANCE: TOTAL_DEPLOY recomputed from the assets of the day.

    Two-way by construction (CEO 裁決 D-1): the new value is 總資產 × 70%
    whether that is above or below the locked one. When the book already holds
    more than the new TOTAL_DEPLOY the overshoot is stated in ``warnings`` *and*
    written to the directive log as a ``REBALANCE`` line -- 超額不得靜默. The
    rule set has no rule that trims an overshoot, so the line carries 無動作 and
    says what was measured rather than inventing a sell instruction.
    """

    model_config = ConfigDict(frozen=True)

    executed_at: date
    status: Literal["ok", "insufficient_data"]
    total_assets: Decimal | None
    previous_total_deploy: Decimal
    new_total_deploy: Decimal | None
    deployed_value: Decimal | None
    #: ``deployed_value - new_total_deploy`` when positive, else ``None``.
    overshoot: Decimal | None
    directives: list[Directive]
    message: str
    warnings: list[str]


class PlaybookEvaluation(BaseModel):
    """Everything one schedule-day evaluation produced."""

    model_config = ConfigDict(frozen=True)

    data_date: date
    execution_date: date
    mode: Mode
    mode_reason: str
    is_schedule_day: bool
    fast_market: FastMarketState
    rules_version: int
    directives: list[Directive]
    effects: list[StateEffect]
    #: 資料缺漏 and 凍結 notices, already written as user-facing sentences.
    warnings: list[str]
    snapshot: list[BatchSnapshot]
    #: The T+1 settlement run that preceded this evaluation, when one ran.
    settlement: SettlementResult | None = None


class EmergencyExitResult(BaseModel):
    """What EMERGENCY_EXIT did (CEO 裁決六).

    All-or-nothing by construction: the caller cannot name a symbol, so
    ``directives`` covers every batch that still holds shares. The freeze that
    follows is the price of the escape hatch -- 逃生門不是後悔藥.
    """

    model_config = ConfigDict(frozen=True)

    executed_at: date
    execution_date: date
    directives: list[Directive]
    total_shares: int
    freeze_until: date
    message: str
    warnings: list[str]


class RuleChangeReceipt(BaseModel):
    """The answer to a request to change the rules (鐵律④ / T5).

    There is no branch in which ``accepted_immediately`` is ``True``: the
    request is always recorded as pending with an effective date of the next
    trading day. 風控 R14 keeps the door open (a change is never refused
    outright, only delayed), and CEO 裁決六 attaches the current volatility to
    the sentence when the market is fast.
    """

    model_config = ConfigDict(frozen=True)

    accepted_immediately: bool = False
    status: Literal["pending"] = "pending"
    version: int
    submitted_at: date
    effective_date: date
    message: str
