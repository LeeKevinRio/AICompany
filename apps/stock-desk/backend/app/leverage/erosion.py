"""Flat-index scenario: how fast the mechanics erode value if the index goes nowhere.

This is a **scenario projection built from realised historical volatility, not a
forecast**. It answers one narrow, conditional question:

    *If* the underlying index ends a horizon exactly where it started, and *if*
    its daily volatility over that horizon equals the volatility realised in the
    trailing window, *then* the daily-reset mechanism plus the expense ratio
    would mechanically leave the fund this far below its starting value.

Nothing about that sentence claims the index will be flat, that volatility will
persist, or that any number here will occur. Volatility is the least-unstable
thing to extrapolate in finance and it is still unstable; the ``assumptions``
list ships with every result so the conditionals are never dropped in
transmission.

Model (log space, so the terms compound rather than merely add):

    drag_log = -0.5 * beta * (beta - 1) * sigma^2 * T
    fee_log  = -expense_ratio_annual * T
    erosion  = exp(drag_log + fee_log) - 1

with ``T = horizon_trading_days / 252`` and ``sigma`` the annualised sample std
(``ddof=1``) of the trailing window's index returns -- the same estimator the
risk layer uses, imported rather than re-implemented.
"""

from __future__ import annotations

import math
from typing import Final

from pydantic import BaseModel, ConfigDict

from app.data.interface import PriceBar
from app.signals.frame import CLOSE, bars_to_frame, provenance
from app.signals.models import InputsUsed, Status
from app.signals.risk import TRADING_DAYS_PER_YEAR, annualized_volatility

#: Trailing index returns used to estimate sigma.
DEFAULT_WINDOW: Final = 60
#: Below this many returns the volatility estimate is too noisy to report.
DEFAULT_MIN_OBSERVATIONS: Final = 20

#: label -> horizon in trading days.
DEFAULT_HORIZONS: Final[tuple[tuple[str, int], ...]] = (
    ("1_month", 21),
    ("1_year", TRADING_DAYS_PER_YEAR),
)

_ASSUMPTIONS: Final[list[str]] = [
    "這是「基於歷史已實現波動的情境推估」，不是預測；標的未來波動與走勢皆未知。",
    "情境的前提是標的指數在該期間期末回到期初水準（期望報酬 0，純橫盤）；"
    "指數若有明確方向，實際結果會與此情境明顯不同。",
    "σ 取自最近 window 個交易日的標的日報酬樣本標準差（ddof=1）年化，"
    "並假設在整段推估期間維持不變。",
    "侵蝕以對數空間相加後轉回百分比：exp(drag_log + fee_log) − 1，"
    "因此波動效應與費用效應兩項不會線性相加成總數。",
    "費用率取自未經查證的 metadata 註冊表（verified=false），數值屬待查證狀態。",
    "未計入追蹤誤差、期貨換倉與融資／放空成本、配息、以及使用者端交易稅費與匯率影響。",
    "推估以交易日換算（1 個月＝21 個交易日、1 年＝252 個交易日）。",
]


class ErosionScenario(BaseModel):
    """One horizon's mechanical erosion under the flat-index assumption."""

    model_config = ConfigDict(frozen=True)

    label: str
    horizon_trading_days: int
    horizon_years: float
    #: exp(drag_log) - 1: the daily-reset compounding term alone.
    volatility_drag_pct: float
    #: exp(fee_log) - 1: the expense-ratio term alone.
    expense_pct: float
    #: exp(drag_log + fee_log) - 1: the two together (not their sum).
    total_expected_erosion_pct: float


class ErosionEstimate(BaseModel):
    """Flat-index erosion scenarios for one leveraged fund.

    ``status="insufficient_data"`` when the trailing window holds fewer than
    ``min_observations`` returns -- a noisy sigma is not quietly reported as a
    confident one.
    """

    model_config = ConfigDict(frozen=True)

    status: Status
    nature: str
    leverage_factor: float
    expense_ratio_annual: float
    window: int
    observations: int
    min_observations: int
    annualized_volatility: float | None
    daily_volatility: float | None
    scenarios: list[ErosionScenario]
    assumptions: list[str]
    inputs_used: InputsUsed
    as_of: str | None = None
    source: str | None = None
    reason: str | None = None


NATURE: Final = (
    "情境推估（conditional scenario），非預測；所有數字以「指數橫盤且波動維持」為前提。"
)


def erosion_at_horizon(
    *,
    leverage_factor: float,
    expense_ratio_annual: float,
    annualized_sigma: float,
    horizon_years: float,
) -> tuple[float, float, float]:
    """Return ``(drag_pct, expense_pct, total_pct)`` for one horizon.

    Each is a simple return (negative = erosion), obtained by exponentiating the
    corresponding log-space term, so the total is the compounded combination of
    the two rather than their arithmetic sum.
    """
    drag_log = (
        -0.5 * leverage_factor * (leverage_factor - 1.0) * annualized_sigma**2 * horizon_years
    )
    fee_log = -expense_ratio_annual * horizon_years
    return (
        math.expm1(drag_log),
        math.expm1(fee_log),
        math.expm1(drag_log + fee_log),
    )


def estimate_erosion(
    *,
    index_bars: list[PriceBar],
    leverage_factor: float,
    expense_ratio_annual: float,
    window: int = DEFAULT_WINDOW,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    horizons: tuple[tuple[str, int], ...] = DEFAULT_HORIZONS,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> ErosionEstimate:
    """Estimate flat-index erosion per horizon from the trailing realised sigma."""
    inputs_used = InputsUsed(
        columns=[CLOSE],
        window={
            "index_bars": len(index_bars),
            "lookback_returns": window,
            "min_observations": min_observations,
            "trading_days_per_year": trading_days_per_year,
        },
        description=(
            "Annualized sample std (ddof=1) of the trailing window of underlying-"
            "index daily close returns, fed into "
            "exp(-0.5*beta*(beta-1)*sigma^2*T - expense_ratio*T) - 1 under a "
            "flat-index assumption. Conditional scenario, not a forecast."
        ),
    )
    as_of, source = provenance(index_bars)

    def _insufficient(reason: str, observations: int) -> ErosionEstimate:
        return ErosionEstimate(
            status="insufficient_data",
            nature=NATURE,
            leverage_factor=leverage_factor,
            expense_ratio_annual=expense_ratio_annual,
            window=window,
            observations=observations,
            min_observations=min_observations,
            annualized_volatility=None,
            daily_volatility=None,
            scenarios=[],
            assumptions=list(_ASSUMPTIONS),
            inputs_used=inputs_used,
            as_of=as_of,
            source=source,
            reason=reason,
        )

    if window < 2:
        return _insufficient("波動視窗長度小於 2，無法估計波動度，因此不計算任何數字。", 0)
    if len(index_bars) < 2:
        return _insufficient(
            f"標的指數日線僅 {len(index_bars)} 根，不足以計算任何日報酬，因此不計算任何數字。",
            0,
        )

    close = bars_to_frame(index_bars)[CLOSE]
    returns = [float(v) for v in close.pct_change().dropna()]
    trailing = returns[-window:]
    observations = len(trailing)
    if observations < min_observations:
        return _insufficient(
            (
                f"視窗內僅 {observations} 個標的日報酬，少於估計所需的 "
                f"{min_observations} 個；波動度估計過於不穩定，因此不輸出情境數字。"
            ),
            observations,
        )

    volatility = annualized_volatility(trailing, periods_per_year=trading_days_per_year)
    if volatility is None:
        return _insufficient("波動度無法估計，因此不輸出情境數字。", observations)
    daily_sigma, annual_sigma = volatility

    scenarios: list[ErosionScenario] = []
    for label, horizon_days in horizons:
        horizon_years = horizon_days / trading_days_per_year
        drag_pct, expense_pct, total_pct = erosion_at_horizon(
            leverage_factor=leverage_factor,
            expense_ratio_annual=expense_ratio_annual,
            annualized_sigma=annual_sigma,
            horizon_years=horizon_years,
        )
        scenarios.append(
            ErosionScenario(
                label=label,
                horizon_trading_days=horizon_days,
                horizon_years=horizon_years,
                volatility_drag_pct=drag_pct,
                expense_pct=expense_pct,
                total_expected_erosion_pct=total_pct,
            )
        )

    return ErosionEstimate(
        status="ok",
        nature=NATURE,
        leverage_factor=leverage_factor,
        expense_ratio_annual=expense_ratio_annual,
        window=window,
        observations=observations,
        min_observations=min_observations,
        annualized_volatility=annual_sigma,
        daily_volatility=daily_sigma,
        scenarios=scenarios,
        assumptions=list(_ASSUMPTIONS),
        inputs_used=inputs_used,
        as_of=as_of,
        source=source,
        reason=None,
    )
