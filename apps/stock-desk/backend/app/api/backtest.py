"""Walk-forward backtest endpoint.

``report`` is the :func:`app.backtest.report.walk_forward_report` output
verbatim: in-sample and out-of-sample kept strictly separate, each paired with
its same-period Buy & Hold benchmark. Nothing is blended and nothing is ranked.

Three disclosures ride along with every run because they change how the numbers
should be read:

* ``cost_model.verified_on`` / ``rates_verified`` -- the fee, tax and
  regulatory rates are still unverified against a primary source (see the
  RATE-PROVENANCE NOTICE in ``app/backtest/costs.py``). A report built on them
  is "subject to rate verification".
* a ``notes`` line stating that Buy & Hold is a pure passive price path, gross
  of transaction cost, so it is never read as a costed strategy.
* ``dividend_adjustment`` -- whether the price series was back-adjusted for
  除權息 (see ``app/dividends/adjust.py``). Adjustment is **on by default**,
  because Taiwan's high payout culture makes an unadjusted series understate
  returns systematically; but the endpoint never claims an adjustment it did
  not make. Every run states, in one of a fixed set of sentences, either
  "已還原除權息" or exactly *why* it is "未還原". A symbol with no stored
  dividend data still backtests -- it just says so, never silently.

Too little history for even one walk-forward fold is a **200 with
``status="insufficient_data"``** and the arithmetic spelled out in ``reason``,
never a fabricated single-split "backtest".

The orchestration itself lives in :func:`execute_backtest`, a module-level
function the route is a one-line wrapper around (約束 32). The Kelly import path
(``POST /api/kelly-inputs/{symbol}/import-backtest``) re-runs a backtest
server-side and has to read the *objects* behind the response -- the
:class:`~app.backtest.engine.BacktestResult` and the fold geometry -- to extract
round trips from them. Giving it its own copy of this pipeline would let the two
drift, and the number stored as "what the backtest said" would stop being what
this endpoint says. So there is one pipeline, and it hands back
:class:`BacktestRun`: the response as served, plus the two objects the response
was built from. The import direction is one-way, ``api/kelly -> api/backtest``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.common import DataMeta, PayloadStatus, data_meta, now_iso
from app.api.deps import get_dividend_store, get_market_resolver, get_settings_store
from app.backtest.engine import BacktestResult, run_backtest
from app.backtest.report import TRADING_DAYS_PER_YEAR, walk_forward_report
from app.backtest.splits import WalkForwardFold, walk_forward_splits
from app.backtest.strategies import STRATEGY_IDS, STRATEGY_WARMUP_BARS, build_strategy
from app.data.interface import PriceBar
from app.dividends.adjust import back_adjust_bars
from app.dividends.store import DividendEventStore
from app.positions.models import InstrumentType, Market
from app.services.market import MarketDataResolver, load_bars
from app.settings.models import CostModelSettings
from app.settings.store import SettingsStore
from app.signals.frame import bars_to_frame

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]
DividendStoreDep = Annotated[DividendEventStore, Depends(get_dividend_store)]

#: Default walk-forward geometry: roughly one year in-sample, one quarter out.
DEFAULT_TRAIN_SIZE = 252
DEFAULT_TEST_SIZE = 63

BUY_AND_HOLD_NOTE = "Buy & Hold 為未計交易成本的被動價格基準，不是已計費的策略。"
UNVERIFIED_RATES_NOTE = (
    "費率（手續費、證交稅、規費）尚未經主要來源查證（verified_on 為 null），"
    "本報告的成本相關數字應視為待查證狀態。"
)

# --- 除權息還原揭露：一組固定句子，每次回測必出現其中之一 -------------------
# 這些字串是面向使用者的說明文案，任何修改都要重新過 risk-compliance-officer。
# Wording state, per work/reviews/波次1文案裁決.md (2026-08-10):
#   * DIVIDEND_METHOD_NOTE, both DIVIDEND_NO_EVENT_NOTE_* strings and
#     DIVIDEND_BIAS_SCOPE_NOTE are the risk-compliance approved sentences,
#     used verbatim.
#   * DIVIDEND_BIAS_SCOPE_NOTE is appended to every degraded ("未還原") branch,
#     including both no_events variants, so the scope qualifier is uniform.

DIVIDEND_ADJUSTED_NOTE = (
    "本回測已還原除權息：價格序列以官方除權息參考價／前一日收盤價為調整因子"
    "（交易所未公布參考價時，改以息值／權值回推同一數量）做還原（back-adjustment），"
    "報酬已含現金股利與配股，Buy & Hold 對照同步還原。"
)
#: 風控核可文案（2026-08-10）：逐字使用，未經 risk-compliance-officer 重新核可不得修改。
DIVIDEND_METHOD_NOTE = (
    "還原採比例法：等同假設股利在除權息參考價當天再投入。若改成假設在除息日收盤價"
    "再投入，數字會略有不同，這是模型選擇而非事實，本系統未計算兩者差距。還原價只"
    "用於回測報酬衡量；持倉市值與風險上限一律仍用原始收盤價。"
)
#: 風控核可文案（2026-08-10）：逐字使用。把「低估」的適用範圍限縮在 Buy & Hold
#: 與持有期間，且「若發生」保留低估未必成立的可能（例如該區間真的沒有配息），
#: 避免讀者把策略欄的偏誤幅度當成同一個數。附加在每一句「未還原」句尾，讓所有
#: 降級情境的限定語一致。
DIVIDEND_BIAS_SCOPE_NOTE = (
    "此低估（若發生）落在 Buy & Hold 與持有期間的報酬；策略欄因進出場時點不同，"
    "偏誤幅度不一定相同。"
)
DIVIDEND_NOT_SYNCED_NOTE = (
    "本回測未還原除權息：本機尚未同步過任何除權息資料"
    "（未執行 uv run python -m app.dividends.sync）。台股高配息情況下，未還原的"
    "報酬率會低估。" + DIVIDEND_BIAS_SCOPE_NOTE
)
#: 風控核可文案（2026-08-10）：逐字使用。「查無紀錄」與「沒有資料可查」是兩件不同
#: 的事，因此依 market 分兩支，非台股不得沿用「查無配息」的說法。
DIVIDEND_NO_EVENT_NOTE_TW = (
    "本回測未還原除權息：本機雖有除權息資料，但查無本商品在此區間的除權息紀錄。"
    "可能是該期間真的沒有配息，也可能是資料覆蓋不足（目前只涵蓋台股上市，不含上櫃），"
    "本系統無法分辨兩者；若實際有配息，此報酬率會低估。" + DIVIDEND_BIAS_SCOPE_NOTE
)
#: 風控核可文案（2026-08-10）：逐字使用。
DIVIDEND_NO_EVENT_NOTE_NON_TW = (
    "本回測未還原除權息：本系統的除權息資料目前只涵蓋台股上市，不涵蓋本市場，"
    "因此不是『查無配息』而是『沒有資料可查』。若本商品有配息，此報酬率會低估。"
    + DIVIDEND_BIAS_SCOPE_NOTE
)
DIVIDEND_UNUSABLE_NOTE = (
    "本回測未還原除權息：查到本商品在此區間的除權息紀錄，但欄位不足以推算調整因子，"
    "已整筆略過而非用推估值代替。此報酬率會低估。" + DIVIDEND_BIAS_SCOPE_NOTE + "請重跑同步，"
    "或回報此代號與區間供人工覆核來源欄位。"
)
DIVIDEND_DISABLED_NOTE = (
    "本次依請求關閉除權息還原（adjust_dividends=false），報酬率不含股利；"
    "台股高配息情況下會低估。" + DIVIDEND_BIAS_SCOPE_NOTE
)

def dividend_notes_by_code(market: Market) -> dict[str, str]:
    """reason_code -> the sentence shown for it in ``market``.

    The API returns both code and sentence so a client can branch on the code
    without pattern-matching Chinese prose. ``no_events`` is the one code whose
    *fact* differs by market: in TW the store does cover the market and found
    nothing, while in any other market there is no coverage to search at all.
    Collapsing the two would let a US run read as "this symbol paid no
    dividend", which is a claim this system cannot make.
    """
    return {
        "adjusted": DIVIDEND_ADJUSTED_NOTE,
        "disabled": DIVIDEND_DISABLED_NOTE,
        "never_synced": DIVIDEND_NOT_SYNCED_NOTE,
        "no_events": (
            DIVIDEND_NO_EVENT_NOTE_TW if market == "TW" else DIVIDEND_NO_EVENT_NOTE_NON_TW
        ),
        "unusable_events": DIVIDEND_UNUSABLE_NOTE,
    }


@dataclass(frozen=True)
class _DividendOutcome:
    """The bars to backtest, the disclosure block, and the notes to append."""

    bars: list[PriceBar]
    block: dict[str, Any]
    notes: list[str]


def _dividend_block(
    *,
    requested: bool,
    applied: bool,
    reason_code: str,
    market: Market,
    events_applied: int = 0,
    events_skipped: int = 0,
    first_ex_date: str | None = None,
    last_ex_date: str | None = None,
    understatement: float | None = None,
    last_synced_at: str | None = None,
) -> dict[str, Any]:
    return {
        "requested": requested,
        "applied": applied,
        "reason_code": reason_code,
        "note": dividend_notes_by_code(market).get(reason_code),
        "events_applied": events_applied,
        "events_skipped": events_skipped,
        "first_ex_date": first_ex_date,
        "last_ex_date": last_ex_date,
        #: How much the *raw* series understated the window's total return.
        "raw_return_understatement": understatement,
        "last_synced_at": last_synced_at,
    }


def resolve_dividend_adjustment(
    bars: list[PriceBar],
    *,
    requested: bool,
    symbol: str,
    market: Market,
    store: DividendEventStore,
) -> _DividendOutcome:
    """Back-adjust ``bars`` when possible, and always say which happened.

    Every branch returns usable bars, so a missing-dividend-data symbol still
    backtests; what changes is the disclosure. The one thing this function must
    never do is return raw bars while claiming they were adjusted.
    """
    last_synced = store.last_synced_at()
    last_synced_iso = last_synced.isoformat() if last_synced is not None else None

    if not requested:
        return _DividendOutcome(
            bars=bars,
            block=_dividend_block(
                requested=False,
                applied=False,
                reason_code="disabled",
                market=market,
                last_synced_at=last_synced_iso,
            ),
            notes=[DIVIDEND_DISABLED_NOTE],
        )
    if not store.is_synced():
        return _DividendOutcome(
            bars=bars,
            block=_dividend_block(
                requested=True, applied=False, reason_code="never_synced", market=market
            ),
            notes=[DIVIDEND_NOT_SYNCED_NOTE],
        )

    events = store.events_for(
        symbol, market, start=min(bar.date for bar in bars), end=max(bar.date for bar in bars)
    )
    adjustment = back_adjust_bars(bars, events)
    if not adjustment.applied:
        # "Found rows but could not use them" and "found nothing" are different
        # facts and get different sentences; collapsing them would hide a data
        # quality problem behind a benign-sounding message.
        code = "unusable_events" if adjustment.events_skipped else "no_events"
        return _DividendOutcome(
            bars=list(adjustment.bars),
            block=_dividend_block(
                requested=True,
                applied=False,
                reason_code=code,
                market=market,
                events_skipped=adjustment.events_skipped,
                last_synced_at=last_synced_iso,
            ),
            notes=[dividend_notes_by_code(market)[code]],
        )
    return _DividendOutcome(
        bars=list(adjustment.bars),
        block=_dividend_block(
            requested=True,
            applied=True,
            reason_code="adjusted",
            market=market,
            events_applied=adjustment.events_applied,
            events_skipped=adjustment.events_skipped,
            first_ex_date=(
                adjustment.first_ex_date.isoformat() if adjustment.first_ex_date else None
            ),
            last_ex_date=(
                adjustment.last_ex_date.isoformat() if adjustment.last_ex_date else None
            ),
            understatement=adjustment.understatement,
            last_synced_at=last_synced_iso,
        ),
        notes=[DIVIDEND_ADJUSTED_NOTE, DIVIDEND_METHOD_NOTE],
    )


class BacktestRequest(BaseModel):
    """``POST /api/backtest`` body."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    symbol: str = Field(min_length=1)
    market: Market = "TW"
    strategy: str = Field(default="ma_cross")
    start: date
    end: date
    instrument_type: InstrumentType = "stock"
    initial_cash: float = Field(default=1_000_000.0, gt=0.0)
    train_size: int = Field(default=DEFAULT_TRAIN_SIZE, ge=2, le=5000)
    test_size: int = Field(default=DEFAULT_TEST_SIZE, ge=1, le=5000)
    #: Per-run cost overrides. Omitted -> the stored settings are used.
    cost: CostModelSettings | None = None
    #: Back-adjust the price series for 除權息. **Default on**: an unadjusted
    #: Taiwanese series understates returns systematically. Turning it off is a
    #: deliberate "price-only return" run and is disclosed as such.
    adjust_dividends: bool = True

    @model_validator(mode="after")
    def _check_window_and_strategy(self) -> BacktestRequest:
        if self.end < self.start:
            raise ValueError("end 不可早於 start")
        if self.strategy not in STRATEGY_WARMUP_BARS:
            allowed = "、".join(STRATEGY_IDS)
            raise ValueError(f"未知的 strategy「{self.strategy}」，目前支援：{allowed}")
        return self


class BacktestResponse(BaseModel):
    """A walk-forward report plus everything needed to read it correctly."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    market: str
    strategy: str
    status: PayloadStatus
    reason: str | None
    #: Exactly ``app.backtest.report.walk_forward_report`` output, or ``None``.
    report: dict[str, Any] | None
    #: The fold geometry the report was built from.
    folds: list[dict[str, int]]
    #: The rates actually applied, with their verification flag.
    cost_model: dict[str, Any]
    rates_verified: bool
    #: Whether the price series was 除權息-adjusted, and if not, why not.
    dividend_adjustment: dict[str, Any]
    notes: list[str]
    data: DataMeta
    as_of: str


@dataclass(frozen=True)
class BacktestRun:
    """One executed run: the served response and the objects it was built from.

    ``result`` and ``folds`` are the run itself; they are ``None`` / empty
    exactly when ``response.status`` is ``insufficient_data``, because in that
    branch no backtest was executed at all. A caller that needs the objects must
    therefore check the status first rather than assume they are there -- the
    same check a reader of the response has to make.

    They are exposed for one caller (the Kelly import path) and one reason: the
    round-trip extraction behind an imported p/b pair reads fills and equity by
    **bar index**, which only the result carries, and it takes its out-of-sample
    bounds from the fold geometry rather than from the report's date strings
    (約束 23). Re-deriving either from the response would rebuild the geometry
    from its own description of itself.
    """

    response: BacktestResponse
    result: BacktestResult | None
    folds: tuple[WalkForwardFold, ...]


def execute_backtest(
    body: BacktestRequest,
    *,
    resolver: MarketDataResolver,
    settings_store: SettingsStore,
    dividend_store: DividendEventStore,
) -> BacktestRun:
    """Run one walk-forward backtest and assemble everything said about it.

    The single run pipeline of this backend (約束 32): load bars, decide and
    disclose the 除權息 adjustment, run the engine, split walk-forward folds and
    report on them. Both the route below and the Kelly import path go through
    here, so an imported Kelly pair is estimated from exactly the run a user
    would have seen on screen.

    Every "cannot answer" branch returns a ``200``-shaped response with
    ``status="insufficient_data"`` and no result object, never an exception:
    "there is not enough history" is an answer about the data, not a fault of
    the request.
    """
    costs = body.cost if body.cost is not None else settings_store.load().cost_model
    base_notes = [BUY_AND_HOLD_NOTE]
    if not costs.rates_verified:
        base_notes.append(UNVERIFIED_RATES_NOTE)

    loaded = load_bars(
        resolver, symbol=body.symbol, market=body.market, start=body.start, end=body.end
    )

    def unavailable(reason: str | None) -> BacktestRun:
        return BacktestRun(
            response=BacktestResponse(
                symbol=body.symbol,
                market=body.market,
                strategy=body.strategy,
                status="insufficient_data",
                reason=reason,
                report=None,
                folds=[],
                cost_model=costs.model_dump(),
                rates_verified=costs.rates_verified,
                # No report was produced, so there is nothing to claim adjusted
                # or not; the block records only what was asked for.
                dividend_adjustment=_dividend_block(
                    requested=body.adjust_dividends,
                    applied=False,
                    reason_code="not_run",
                    market=body.market,
                ),
                notes=base_notes,
                data=data_meta(loaded.meta()),
                as_of=now_iso(),
            ),
            # Nothing ran, so there is no result and no geometry to hand on.
            result=None,
            folds=(),
        )

    if not loaded.bars:
        return unavailable(loaded.reason)

    warmup = STRATEGY_WARMUP_BARS[body.strategy]
    needed = body.train_size + body.test_size
    if len(loaded.bars) < needed:
        return unavailable(
            f"區間內只有 {len(loaded.bars)} 根日線，walk-forward 至少需要 "
            f"train_size {body.train_size} + test_size {body.test_size} = {needed} 根，"
            "不以單一切分代替。"
        )
    if body.train_size < warmup:
        return unavailable(
            f"策略「{body.strategy}」需要 {warmup} 根日線暖身，"
            f"train_size {body.train_size} 不足，樣本內區段將完全沒有部位。"
        )

    dividends = resolve_dividend_adjustment(
        loaded.bars,
        requested=body.adjust_dividends,
        symbol=body.symbol,
        market=body.market,
        store=dividend_store,
    )
    notes = [*base_notes, *dividends.notes]

    frame = bars_to_frame(dividends.bars)
    result = run_backtest(
        frame,
        build_strategy(body.strategy),
        initial_cash=body.initial_cash,
        cost_model=costs.to_cost_model(),
        market=body.market,
        instrument_type=body.instrument_type,
    )
    folds = walk_forward_splits(
        len(frame), train_size=body.train_size, test_size=body.test_size
    )
    if not folds:  # pragma: no cover - the length check above already guarantees one
        return unavailable("資料長度不足以切出任何 walk-forward fold。")

    report = walk_forward_report(result, folds, periods_per_year=TRADING_DAYS_PER_YEAR)
    return BacktestRun(
        response=BacktestResponse(
            symbol=body.symbol,
            market=body.market,
            strategy=body.strategy,
            status="ok",
            reason=None,
            report=report.model_dump(),
            folds=[
                {
                    "fold": fold.fold,
                    "train_start": fold.train_start,
                    "train_stop": fold.train_stop,
                    "test_start": fold.test_start,
                    "test_stop": fold.test_stop,
                }
                for fold in folds
            ],
            cost_model=costs.model_dump(),
            rates_verified=costs.rates_verified,
            dividend_adjustment=dividends.block,
            notes=notes,
            data=data_meta(loaded.meta()),
            as_of=now_iso(),
        ),
        result=result,
        folds=tuple(folds),
    )


@router.post("", response_model=BacktestResponse)
def run_walk_forward_backtest(
    body: BacktestRequest,
    resolver: ResolverDep,
    settings_store: SettingsDep,
    dividend_store: DividendStoreDep,
) -> BacktestResponse:
    """Run a walk-forward backtest and report both segments separately.

    Wiring only: the pipeline is :func:`execute_backtest`, and this route serves
    the response half of what it produced.
    """
    return execute_backtest(
        body,
        resolver=resolver,
        settings_store=settings_store,
        dividend_store=dividend_store,
    ).response
