"""Decompose a leveraged ETF's realised holding-period gap versus the naive expectation.

The question this answers, neutrally and arithmetically: *a fund that targets
``beta`` times the underlying index's **single-day** return returned ``R_etf``
over the holding period, while ``beta * R_idx`` -- the number most people
extrapolate from the multiple -- was something else. Where did the difference
come from?*

Decomposition (all figures are simple returns over the same aligned window):

``actual``        ``R_etf   = etf_close_end / etf_close_start - 1``
``naive``         ``beta * R_idx``, with ``R_idx = idx_end / idx_start - 1``
``gap``           ``actual - naive``
``fee_effect``    ``-expense_ratio_annual * N / 252`` (linear approximation)
``reset_effect``  ``ideal_daily_reset_return - naive``, where the ideal path is
                  ``prod(1 + beta * r_idx_t) - 1``: a fund that tracked ``beta``
                  times the index *every single day*, with no fee and no
                  tracking error. This is the pure compounding / volatility drag
                  term and it is a mechanical consequence of daily resetting.
``residual``      ``gap - fee_effect - reset_effect``: everything else --
                  tracking error, roll/financing/borrow costs, dividends,
                  index-vs-fund price-source differences. Named, not hidden, and
                  never absorbed into the other two terms.

By construction the identity ``actual - naive == fee_effect + reset_effect +
residual`` holds exactly (to float precision); ``identity_abs_error`` is emitted
so a consumer can verify it rather than trust it.

A closed-form approximation ``drag ~= -0.5 * beta * (beta - 1) * sigma^2 * T``
is reported **alongside** the measured ``reset_effect``, with the difference
shown as-is. The two are not reconciled or forced to agree: the approximation
assumes i.i.d. small returns and continuous rebalancing, and where reality
disagrees with the textbook that disagreement is the information.

The attribution is only as meaningful as the index series it was computed
against, so ``index_basis`` / ``index_return_basis`` travel in and back out
with the result, and an oversized ``|residual|`` trips
:data:`RESIDUAL_ALERT_ABS` into ``notes`` -- a wrong index mapping does not
make this module fail, it quietly makes the three terms mean something else,
which is exactly the failure mode that flag exists to surface.

Nothing here is an instruction to do anything; it is an attribution of numbers
that already happened.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Final

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.data.interface import PriceBar
from app.leverage.index_mapping import IndexBasis, ReturnBasis
from app.signals.frame import CLOSE, bars_to_frame, provenance
from app.signals.models import InputsUsed, Status
from app.signals.risk import TRADING_DAYS_PER_YEAR, annualized_volatility

_ETF: Final = "etf"
_INDEX: Final = "index"

#: Minimum aligned bars for a decomposition (one holding-period return).
MIN_ALIGNED_BARS: Final = 2
#: Minimum index returns before the sigma-based approximation is attempted.
MIN_RETURNS_FOR_THEORY: Final = 2

THEORY_FORMULA: Final = "drag ~= -0.5 * beta * (beta - 1) * sigma^2 * T"

_ASSUMPTIONS: Final[list[str]] = [
    "持有期間以 ETF 與標的指數的共同交易日收盤價對齊計算；起點為建倉日（含）之後第一個"
    "共同交易日的收盤價，並非實際成交價，因此本章數字描述的是基金機制，不是個人損益。",
    "費用效應以「年費用率 × 交易日數 ÷ 252」線性近似，未逐日累計、未計複利，屬近似值。",
    "重置效應＝「每日精準追蹤 β 倍、零費用、零追蹤誤差」的理想路徑報酬減去 naive 期望，"
    "是日度重置機制的算術結果。",
    "殘差＝實際報酬與上述理想路徑及費用近似之間剩下的部分，可能來自追蹤誤差、期貨換倉與"
    "融資／放空成本、配息處理、以及指數與基金價格來源差異；本模組不再往下細拆。",
    f"理論近似式 {THEORY_FORMULA} 假設報酬獨立同分布、可連續重置、單日幅度小；"
    "其與實測重置效應的差異照實並列，不做調整使兩者相符。",
    "σ 以持有期間標的日報酬的樣本標準差（ddof=1）年化估得；觀測數少時此估計極不穩定，"
    "observations 欄位一併提供以供判讀。",
    "所有數字以收盤價計算，未含使用者端的交易稅費，也未含匯率影響。",
]

#: Appended when the series fed in is not the official index itself.
NON_OFFICIAL_BASIS_ASSUMPTION: Final = (
    "本次拆解所用的序列不是官方標的指數（basis={basis}），"
    "序列本身的費用與追蹤誤差會混進 residual，三項歸因的意義因此被稀釋。"
)

#: Appended when the index's dividend treatment has not been verified.
UNKNOWN_RETURN_BASIS_ASSUMPTION: Final = (
    "指數的含息口徑未查證（return_basis=unknown），配息差異會落在 residual。"
)

RESIDUAL_ALERT_ABS: Final = 0.10
"""Absolute ``|residual|`` above which the decomposition flags itself.

This is a **manually chosen reminder threshold, not a statistical test**. It is
not a confidence interval, not a hypothesis test, and it carries no notion of
how likely a residual of this size is; it is one hand-picked number that says
"a gap this large is more often a mapping or dividend-basis problem than a real
tracking cost, so read the attribution with that in mind". Crossing it proves
nothing on its own, and staying under it certifies nothing either.
"""

#: Emitted verbatim into ``notes`` when the threshold above is crossed.
RESIDUAL_ALERT_NOTE: Final = (
    "殘差 {residual:+.2%} 的絕對值超過提醒門檻 {threshold:.0%}："
    "殘差異常大，標的指數對應可能有誤或含息口徑不一致，請勿將本次歸因視為定論。"
)


def _assumptions_for(index_basis: IndexBasis, index_return_basis: ReturnBasis) -> list[str]:
    """The base assumptions plus whatever the index's provenance adds (I-4)."""
    assumptions = list(_ASSUMPTIONS)
    if index_basis != "official_index":
        assumptions.append(NON_OFFICIAL_BASIS_ASSUMPTION.format(basis=index_basis))
    if index_return_basis == "unknown":
        assumptions.append(UNKNOWN_RETURN_BASIS_ASSUMPTION)
    return assumptions


class TheoreticalDrag(BaseModel):
    """Closed-form drag approximation, placed next to the measured effect."""

    model_config = ConfigDict(frozen=True)

    status: Status
    formula: str
    annualized_volatility: float | None
    daily_volatility: float | None
    horizon_years: float | None
    observations: int
    theoretical_drag: float | None
    measured_reset_effect: float | None
    #: ``theoretical_drag - measured_reset_effect``; the honest disagreement.
    difference: float | None
    reason: str | None


class HoldingWindow(BaseModel):
    """The exact window the decomposition was computed over."""

    model_config = ConfigDict(frozen=True)

    start_date: str | None
    end_date: str | None
    aligned_bars: int
    trading_days: int
    calendar_days: int | None
    opened_at: str | None
    days_since_opened_at: int | None


class DragDecomposition(BaseModel):
    """Full attribution of ``actual - naive`` for one holding period."""

    model_config = ConfigDict(frozen=True)

    status: Status
    leverage_factor: float
    expense_ratio_annual: float
    window: HoldingWindow
    index_return: float | None
    actual_return: float | None
    naive_expected_return: float | None
    ideal_daily_reset_return: float | None
    gap: float | None
    fee_effect: float | None
    reset_effect: float | None
    residual: float | None
    identity_abs_error: float | None
    ideal_path_wiped_out: bool
    theoretical: TheoreticalDrag
    assumptions: list[str]
    inputs_used: InputsUsed
    as_of: str | None = None
    source: str | None = None
    index_as_of: str | None = None
    index_source: str | None = None
    #: How the series used relates to the fund's stated benchmark, echoed back
    #: so a reader never has to assume it was the official index (I-4).
    index_basis: IndexBasis = "official_index"
    #: Dividend treatment of that series; ``unknown`` until verified.
    index_return_basis: ReturnBasis = "unknown"
    #: ``True`` when ``|residual|`` crossed :data:`RESIDUAL_ALERT_ABS`.
    residual_alert: bool = False
    residual_alert_threshold: float = RESIDUAL_ALERT_ABS
    #: Qualifiers about *this* result (the residual trip lands here).
    notes: list[str] = Field(default_factory=list)
    reason: str | None = None


def align_closes(
    etf_bars: list[PriceBar],
    index_bars: list[PriceBar],
    *,
    opened_at: date_type | None = None,
) -> pd.DataFrame:
    """Inner-join ETF and index closes on common dates, from ``opened_at`` on.

    Point-in-time discipline: bars dated before ``opened_at`` are dropped, so a
    holding-period figure can never quietly include days the user did not hold.
    """
    etf_close = bars_to_frame(etf_bars)[CLOSE]
    index_close = bars_to_frame(index_bars)[CLOSE]
    joined = pd.concat(
        {_ETF: etf_close, _INDEX: index_close}, axis=1, join="inner"
    ).sort_index()
    joined = joined.dropna()
    if opened_at is not None:
        joined = joined[joined.index >= pd.Timestamp(opened_at)]
    return joined


def ideal_daily_reset_path(
    index_returns: list[float], leverage_factor: float
) -> tuple[float, bool]:
    """Return ``(cumulative_return, wiped_out)`` of a perfect daily-reset fund.

    ``wiped_out`` is ``True`` when a single day's ``1 + beta * r`` reaches zero
    or below: a daily-reset fund's NAV cannot go negative, so the path is
    floored at ``-100%`` and stops there rather than producing an impossible
    number.
    """
    level = 1.0
    for r in index_returns:
        factor = 1.0 + leverage_factor * r
        if factor <= 0.0:
            return -1.0, True
        level *= factor
    return level - 1.0, False


def theoretical_drag(
    *, leverage_factor: float, annualized_sigma: float, horizon_years: float
) -> float:
    """``-0.5 * beta * (beta - 1) * sigma^2 * T`` (log-return approximation)."""
    return -0.5 * leverage_factor * (leverage_factor - 1.0) * annualized_sigma**2 * horizon_years


def _empty_window(opened_at: date_type | None) -> HoldingWindow:
    return HoldingWindow(
        start_date=None,
        end_date=None,
        aligned_bars=0,
        trading_days=0,
        calendar_days=None,
        opened_at=opened_at.isoformat() if opened_at else None,
        days_since_opened_at=None,
    )


def _insufficient_theory(reason: str, observations: int) -> TheoreticalDrag:
    return TheoreticalDrag(
        status="insufficient_data",
        formula=THEORY_FORMULA,
        annualized_volatility=None,
        daily_volatility=None,
        horizon_years=None,
        observations=observations,
        theoretical_drag=None,
        measured_reset_effect=None,
        difference=None,
        reason=reason,
    )


def _inputs_used(
    *, etf_bars: int, index_bars: int, aligned: int, trading_days_per_year: int
) -> InputsUsed:
    return InputsUsed(
        columns=[CLOSE],
        window={
            "etf_bars": etf_bars,
            "index_bars": index_bars,
            "aligned_bars": aligned,
            "trading_days_per_year": trading_days_per_year,
        },
        description=(
            "Holding-period attribution from ETF and underlying-index closes on "
            "their common dates from opened_at onward: gap = actual - beta * "
            "index_return, split into a linear fee term, the compounding "
            "(daily-reset) term from a perfect beta-tracking path, and a named "
            f"residual. Needs at least {MIN_ALIGNED_BARS} aligned bars; the "
            f"sigma approximation needs {MIN_RETURNS_FOR_THEORY} index returns."
        ),
    )


def decompose_drag(
    *,
    etf_bars: list[PriceBar],
    index_bars: list[PriceBar],
    leverage_factor: float,
    expense_ratio_annual: float,
    opened_at: date_type | None = None,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
    index_basis: IndexBasis = "official_index",
    index_return_basis: ReturnBasis = "unknown",
) -> DragDecomposition:
    """Attribute ``R_etf - beta * R_idx`` to fee, daily reset, and residual.

    Returns ``status="insufficient_data"`` (never a partial or fabricated
    number) when fewer than :data:`MIN_ALIGNED_BARS` common-dated bars survive
    the ``opened_at`` cut.

    ``index_basis`` / ``index_return_basis`` describe where ``index_bars`` came
    from (see ``app/leverage/index_mapping.py``). They are echoed in the output
    and add an assumption sentence when the series is not the official index or
    its dividend treatment is unverified: the three attribution terms are only
    as meaningful as the series they were computed against, and this module
    will not let that qualifier be lost in transmission.
    """
    as_of, source = provenance(etf_bars)
    index_as_of, index_source = provenance(index_bars)
    assumptions = _assumptions_for(index_basis, index_return_basis)
    inputs_used = _inputs_used(
        etf_bars=len(etf_bars),
        index_bars=len(index_bars),
        aligned=0,
        trading_days_per_year=trading_days_per_year,
    )

    def _insufficient(reason: str, aligned: int, window: HoldingWindow) -> DragDecomposition:
        return DragDecomposition(
            status="insufficient_data",
            leverage_factor=leverage_factor,
            expense_ratio_annual=expense_ratio_annual,
            window=window,
            index_return=None,
            actual_return=None,
            naive_expected_return=None,
            ideal_daily_reset_return=None,
            gap=None,
            fee_effect=None,
            reset_effect=None,
            residual=None,
            identity_abs_error=None,
            ideal_path_wiped_out=False,
            theoretical=_insufficient_theory(reason, max(aligned - 1, 0)),
            assumptions=list(assumptions),
            inputs_used=_inputs_used(
                etf_bars=len(etf_bars),
                index_bars=len(index_bars),
                aligned=aligned,
                trading_days_per_year=trading_days_per_year,
            ),
            as_of=as_of,
            source=source,
            index_as_of=index_as_of,
            index_source=index_source,
            index_basis=index_basis,
            index_return_basis=index_return_basis,
            residual_alert=False,
            notes=[],
            reason=reason,
        )

    if not etf_bars or not index_bars:
        return _insufficient(
            "缺少 ETF 或標的指數的日線資料，無法拆解，因此不計算任何數字。",
            0,
            _empty_window(opened_at),
        )

    joined = align_closes(etf_bars, index_bars, opened_at=opened_at)
    aligned_bars = int(len(joined))
    if aligned_bars < MIN_ALIGNED_BARS:
        return _insufficient(
            (
                f"建倉日之後 ETF 與標的指數的共同交易日僅 {aligned_bars} 天，"
                f"少於拆解所需的 {MIN_ALIGNED_BARS} 天，因此不計算任何數字。"
            ),
            aligned_bars,
            _empty_window(opened_at),
        )

    dates = [ts.date() for ts in joined.index]
    start_date, end_date = dates[0], dates[-1]
    etf_close = [float(v) for v in joined[_ETF]]
    index_close = [float(v) for v in joined[_INDEX]]
    if etf_close[0] <= 0.0 or index_close[0] <= 0.0:
        return _insufficient(
            "起點收盤價非正值，報酬無法定義，因此不計算任何數字。",
            aligned_bars,
            _empty_window(opened_at),
        )

    trading_days = aligned_bars - 1
    window = HoldingWindow(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        aligned_bars=aligned_bars,
        trading_days=trading_days,
        calendar_days=(end_date - start_date).days,
        opened_at=opened_at.isoformat() if opened_at else None,
        days_since_opened_at=(end_date - opened_at).days if opened_at else None,
    )

    index_returns = [
        index_close[i] / index_close[i - 1] - 1.0 for i in range(1, len(index_close))
    ]
    index_return = index_close[-1] / index_close[0] - 1.0
    actual_return = etf_close[-1] / etf_close[0] - 1.0
    naive = leverage_factor * index_return
    ideal, wiped_out = ideal_daily_reset_path(index_returns, leverage_factor)

    horizon_years = trading_days / trading_days_per_year
    gap = actual_return - naive
    fee_effect = -expense_ratio_annual * horizon_years
    reset_effect = ideal - naive
    residual = gap - fee_effect - reset_effect
    identity_abs_error = abs(gap - (fee_effect + reset_effect + residual))

    notes: list[str] = []
    residual_alert = abs(residual) > RESIDUAL_ALERT_ABS
    if residual_alert:
        notes.append(
            RESIDUAL_ALERT_NOTE.format(residual=residual, threshold=RESIDUAL_ALERT_ABS)
        )

    volatility = annualized_volatility(index_returns, periods_per_year=trading_days_per_year)
    if volatility is None or len(index_returns) < MIN_RETURNS_FOR_THEORY:
        theory = _insufficient_theory(
            (
                f"標的指數僅 {len(index_returns)} 個日報酬，少於估計波動度所需的 "
                f"{MIN_RETURNS_FOR_THEORY} 個，理論近似值不估算。"
            ),
            len(index_returns),
        )
    else:
        daily_sigma, annual_sigma = volatility
        approx = theoretical_drag(
            leverage_factor=leverage_factor,
            annualized_sigma=annual_sigma,
            horizon_years=horizon_years,
        )
        theory = TheoreticalDrag(
            status="ok",
            formula=THEORY_FORMULA,
            annualized_volatility=annual_sigma,
            daily_volatility=daily_sigma,
            horizon_years=horizon_years,
            observations=len(index_returns),
            theoretical_drag=approx,
            measured_reset_effect=reset_effect,
            difference=approx - reset_effect,
            reason=None,
        )

    return DragDecomposition(
        status="ok",
        leverage_factor=leverage_factor,
        expense_ratio_annual=expense_ratio_annual,
        window=window,
        index_return=index_return,
        actual_return=actual_return,
        naive_expected_return=naive,
        ideal_daily_reset_return=ideal,
        gap=gap,
        fee_effect=fee_effect,
        reset_effect=reset_effect,
        residual=residual,
        identity_abs_error=identity_abs_error,
        ideal_path_wiped_out=wiped_out,
        theoretical=theory,
        assumptions=list(assumptions),
        inputs_used=inputs_used.model_copy(
            update={
                "window": {
                    "etf_bars": len(etf_bars),
                    "index_bars": len(index_bars),
                    "aligned_bars": aligned_bars,
                    "trading_days_per_year": trading_days_per_year,
                }
            }
        ),
        as_of=as_of,
        source=source,
        index_as_of=index_as_of,
        index_source=index_source,
        index_basis=index_basis,
        index_return_basis=index_return_basis,
        residual_alert=residual_alert,
        notes=notes,
        reason=None,
    )
