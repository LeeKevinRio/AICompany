"""Walk-forward backtest endpoint.

``report`` is the :func:`app.backtest.report.walk_forward_report` output
verbatim: in-sample and out-of-sample kept strictly separate, each paired with
its same-period Buy & Hold benchmark. Nothing is blended and nothing is ranked.

Two disclosures ride along with every run because they change how the numbers
should be read:

* ``cost_model.verified_on`` / ``rates_verified`` -- the fee, tax and
  regulatory rates are still unverified against a primary source (see the
  RATE-PROVENANCE NOTICE in ``app/backtest/costs.py``). A report built on them
  is "subject to rate verification".
* a ``notes`` line stating that Buy & Hold is a pure passive price path, gross
  of transaction cost, so it is never read as a costed strategy.

Too little history for even one walk-forward fold is a **200 with
``status="insufficient_data"``** and the arithmetic spelled out in ``reason``,
never a fabricated single-split "backtest".
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.common import DataMeta, PayloadStatus, data_meta, now_iso
from app.api.deps import get_market_resolver, get_settings_store
from app.backtest.engine import run_backtest
from app.backtest.report import TRADING_DAYS_PER_YEAR, walk_forward_report
from app.backtest.splits import walk_forward_splits
from app.backtest.strategies import STRATEGY_IDS, STRATEGY_WARMUP_BARS, build_strategy
from app.positions.models import InstrumentType, Market
from app.services.market import MarketDataResolver, load_bars
from app.settings.models import CostModelSettings
from app.settings.store import SettingsStore
from app.signals.frame import bars_to_frame

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]

#: Default walk-forward geometry: roughly one year in-sample, one quarter out.
DEFAULT_TRAIN_SIZE = 252
DEFAULT_TEST_SIZE = 63

BUY_AND_HOLD_NOTE = "Buy & Hold 為未計交易成本的被動價格基準，不是已計費的策略。"
UNVERIFIED_RATES_NOTE = (
    "費率（手續費、證交稅、規費）尚未經主要來源查證（verified_on 為 null），"
    "本報告的成本相關數字應視為待查證狀態。"
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
    notes: list[str]
    data: DataMeta
    as_of: str


@router.post("", response_model=BacktestResponse)
def run_walk_forward_backtest(
    body: BacktestRequest,
    resolver: ResolverDep,
    settings_store: SettingsDep,
) -> BacktestResponse:
    costs = body.cost if body.cost is not None else settings_store.load().cost_model
    notes = [BUY_AND_HOLD_NOTE]
    if not costs.rates_verified:
        notes.append(UNVERIFIED_RATES_NOTE)

    loaded = load_bars(
        resolver, symbol=body.symbol, market=body.market, start=body.start, end=body.end
    )

    def unavailable(reason: str | None) -> BacktestResponse:
        return BacktestResponse(
            symbol=body.symbol,
            market=body.market,
            strategy=body.strategy,
            status="insufficient_data",
            reason=reason,
            report=None,
            folds=[],
            cost_model=costs.model_dump(),
            rates_verified=costs.rates_verified,
            notes=notes,
            data=data_meta(loaded.meta()),
            as_of=now_iso(),
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

    frame = bars_to_frame(loaded.bars)
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
    return BacktestResponse(
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
        notes=notes,
        data=data_meta(loaded.meta()),
        as_of=now_iso(),
    )
