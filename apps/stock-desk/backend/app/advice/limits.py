"""The risk budget and the caps every recommendation is measured against.

:class:`RiskBudget` holds the numbers (conservative defaults, meant to be
editable later from a settings page -- hence a plain pydantic model that
round-trips to JSON rather than an env-only settings object).
:class:`PortfolioContext` holds everything about *this* symbol and the book
around it that a cap needs.

Two conventions that make the output honest rather than merely reassuring:

* A cap whose inputs are missing reports ``not_evaluable`` with the reason. It
  is never silently reported as ``passed``. The sector cap is ``not_evaluable``
  in practice today because positions carry no sector field yet.
* A cap is ``violated`` when the observed value **reaches or exceeds** the
  threshold (``>=``), not only when it strictly exceeds it: at exactly the cap
  the budget is already spent, so there is no room left to add.

Currency: book-level amounts are TWD (the reporting currency, as in
``app/portfolio``); ``close`` and ``atr`` are in the instrument's own currency
and are converted with ``fx_to_twd`` at the single point where share sizing
happens. Values here are ``float`` (like the signal layer), not ``Decimal``:
these are indicative ranges derived from statistics, not accounting figures.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LimitStatus = Literal["passed", "violated", "not_evaluable"]

#: A cap's verdict as ``(status, detail, observed, threshold)``.
CheckResult = tuple[LimitStatus, str, float | None, float | None]

#: Fixed order of the caps; the 1-based index in this tuple is the "第 X 條上限"
#: quoted on the advice card when a cap blocks an ``add``.
LIMIT_IDS: tuple[str, ...] = (
    "single_position_weight",
    "sector_weight",
    "gross_exposure",
    "per_trade_loss",
    "kelly_fraction",
)

LIMIT_NAMES: dict[str, str] = {
    "single_position_weight": "單一標的佔比上限",
    "sector_weight": "單一產業佔比上限",
    "gross_exposure": "總曝險上限",
    "per_trade_loss": "單筆最大可承受虧損",
    "kelly_fraction": "分數 Kelly 部位上限",
}

#: Tolerance used when comparing an observed ratio against a cap, so that a
#: value that is mathematically equal to the cap is not missed by float noise.
EPSILON = 1e-9

#: The lower edge of a suggested quantity range is this fraction of the upper
#: edge -- a range, never a single "correct" number.
RANGE_LOWER_RATIO = 0.5

#: How many single-share steps a suggested quantity may be walked back (or up)
#: while verifying it against the binding cap. The arithmetic edge is already
#: within one share of the answer; the bound only stops a pathological budget
#: from spinning, and giving up yields "no suggestion" rather than a bad one.
MAX_SIZING_ADJUSTMENTS = 8


class RiskBudget(BaseModel):
    """The risk caps applied to every suggestion. Defaults are conservative."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_position_weight: float = Field(default=0.15, gt=0.0, le=1.0)
    max_sector_weight: float = Field(default=0.30, gt=0.0, le=1.0)
    max_gross_exposure: float = Field(default=1.00, gt=0.0, le=2.0)
    #: Largest acceptable loss on one position, as a fraction of total equity.
    max_loss_per_trade: float = Field(default=0.01, gt=0.0, le=0.1)
    #: Stop distance = this multiple of ATR(14).
    atr_stop_multiple: float = Field(default=2.0, gt=0.0, le=10.0)
    #: Only fractional Kelly is allowed, at most a quarter of full Kelly.
    kelly_fraction_cap: float = Field(default=0.25, gt=0.0, le=0.25)
    #: Hard ceiling on any Kelly-derived position, whatever the edge estimate.
    kelly_position_cap: float = Field(default=0.10, gt=0.0, le=0.10)


class PortfolioContext(BaseModel):
    """Everything the caps need about one symbol and the book around it.

    Every field except ``symbol`` is optional: a missing input turns the caps
    that need it into ``not_evaluable`` instead of producing a fabricated pass.
    A *candidate* (not yet held) is expressed as
    ``position_market_value_twd=0`` and ``quantity=0``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    total_equity_twd: float | None = Field(default=None, ge=0.0)
    position_market_value_twd: float | None = Field(default=None, ge=0.0)
    position_cost_twd: float | None = Field(default=None, ge=0.0)
    gross_exposure_twd: float | None = Field(default=None, ge=0.0)
    quantity: float | None = Field(default=None, ge=0.0)
    #: Latest close in the instrument's own currency (what the rules compare).
    close: float | None = Field(default=None, gt=0.0)
    #: Instrument currency -> TWD; 1.0 for a TWD instrument.
    fx_to_twd: float = Field(default=1.0, gt=0.0)
    #: ATR(14) in the instrument's own currency; drives the stop distance.
    atr: float | None = Field(default=None, ge=0.0)
    #: Sector label. Positions have no sector field yet, so this is normally
    #: ``None`` and the sector cap honestly reports ``not_evaluable``.
    sector: str | None = None
    sector_market_value_twd: float | None = Field(default=None, ge=0.0)
    #: Kelly inputs. No source produces them yet; absent -> ``not_evaluable``.
    win_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    payoff_ratio: float | None = Field(default=None, gt=0.0)

    def position_weight(self) -> float | None:
        """This symbol's share of total equity, or ``None`` if not computable."""
        if self.total_equity_twd is None or not self.total_equity_twd > 0.0:
            return None
        if self.position_market_value_twd is None:
            return None
        return self.position_market_value_twd / self.total_equity_twd

    def unrealized_pnl_pct(self) -> float | None:
        """Unrealized P&L as a fraction of cost, or ``None`` without a cost."""
        if self.position_cost_twd is None or not self.position_cost_twd > 0.0:
            return None
        if self.position_market_value_twd is None:
            return None
        return self.position_market_value_twd / self.position_cost_twd - 1.0

    def price_twd(self) -> float | None:
        """Latest close converted to TWD, used for share sizing."""
        if self.close is None:
            return None
        return self.close * self.fx_to_twd

    def held_shares(self) -> float | None:
        """Shares held: the explicit quantity, else derived from market value."""
        if self.quantity is not None:
            return self.quantity
        price = self.price_twd()
        if price is None or price <= 0.0 or self.position_market_value_twd is None:
            return None
        return self.position_market_value_twd / price


class LimitCheck(BaseModel):
    """One cap's verdict, with the numbers behind it."""

    model_config = ConfigDict(frozen=True)

    index: int
    id: str
    name: str
    status: LimitStatus
    detail: str
    observed: float | None
    threshold: float | None


class QuantityRange(BaseModel):
    """A share-count range implied by the binding cap, plus how it was derived."""

    model_config = ConfigDict(frozen=True)

    min_shares: int
    max_shares: int
    basis: str


def kelly_fraction(win_rate: float, payoff_ratio: float) -> float | None:
    """Full Kelly fraction ``w - (1 - w) / b``.

    ``w`` is the win rate, ``b`` the payoff ratio (average win / average loss).
    Returns ``None`` for inputs outside their domain; a negative edge yields a
    negative fraction, which the caller floors at zero.
    """
    if not 0.0 <= win_rate <= 1.0 or payoff_ratio <= 0.0:
        return None
    return win_rate - (1.0 - win_rate) / payoff_ratio


def kelly_allowed_weight(budget: RiskBudget, ctx: PortfolioContext) -> float | None:
    """Position weight allowed by fractional Kelly, or ``None`` without inputs."""
    if ctx.win_rate is None or ctx.payoff_ratio is None:
        return None
    full = kelly_fraction(ctx.win_rate, ctx.payoff_ratio)
    if full is None:  # pragma: no cover - the field validators already pin the domain
        return None
    fractional = max(full, 0.0) * budget.kelly_fraction_cap
    return min(fractional, budget.kelly_position_cap)


def atr_max_shares(budget: RiskBudget, ctx: PortfolioContext) -> float | None:
    """Largest share count whose stop-out loss stays inside the per-trade cap.

    Stop distance is ``atr_stop_multiple x ATR(14)`` converted to TWD; the
    acceptable loss is ``max_loss_per_trade x total equity``.
    """
    if ctx.total_equity_twd is None or not ctx.total_equity_twd > 0.0 or ctx.atr is None:
        return None
    stop_distance_twd = budget.atr_stop_multiple * ctx.atr * ctx.fx_to_twd
    if stop_distance_twd <= 0.0:
        return None
    return budget.max_loss_per_trade * ctx.total_equity_twd / stop_distance_twd


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _breaches(observed: float, threshold: float) -> bool:
    """True when ``observed`` has reached or passed ``threshold``."""
    return observed >= threshold - EPSILON


def _check_single_position_weight(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    threshold = budget.max_position_weight
    weight = ctx.position_weight()
    if weight is None:
        return ("not_evaluable", "缺少總資產或部位市值，無法計算單一標的佔比。", None, threshold)
    if _breaches(weight, threshold):
        return (
            "violated",
            f"{ctx.symbol} 佔總資產 {_pct(weight)}，已達或超過上限 {_pct(threshold)}。",
            weight,
            threshold,
        )
    return (
        "passed",
        f"{ctx.symbol} 佔總資產 {_pct(weight)}，低於上限 {_pct(threshold)}。",
        weight,
        threshold,
    )


def _check_sector_weight(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    threshold = budget.max_sector_weight
    if ctx.sector is None or ctx.sector_market_value_twd is None:
        return (
            "not_evaluable",
            "持倉資料目前沒有產業別欄位，這條上限未實際檢查。",
            None,
            threshold,
        )
    if ctx.total_equity_twd is None or not ctx.total_equity_twd > 0.0:
        return ("not_evaluable", "缺少總資產，無法計算產業佔比。", None, threshold)
    weight = ctx.sector_market_value_twd / ctx.total_equity_twd
    if _breaches(weight, threshold):
        return (
            "violated",
            f"{ctx.sector} 產業佔總資產 {_pct(weight)}，已達或超過上限 {_pct(threshold)}。",
            weight,
            threshold,
        )
    return (
        "passed",
        f"{ctx.sector} 產業佔總資產 {_pct(weight)}，低於上限 {_pct(threshold)}。",
        weight,
        threshold,
    )


def _check_gross_exposure(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    threshold = budget.max_gross_exposure
    if ctx.total_equity_twd is None or not ctx.total_equity_twd > 0.0:
        return ("not_evaluable", "缺少總資產，無法計算總曝險。", None, threshold)
    if ctx.gross_exposure_twd is None:
        return ("not_evaluable", "缺少組合總市值，無法計算總曝險。", None, threshold)
    exposure = ctx.gross_exposure_twd / ctx.total_equity_twd
    if _breaches(exposure, threshold):
        return (
            "violated",
            f"組合總曝險 {_pct(exposure)}，已達或超過上限 {_pct(threshold)}。",
            exposure,
            threshold,
        )
    return (
        "passed",
        f"組合總曝險 {_pct(exposure)}，低於上限 {_pct(threshold)}。",
        exposure,
        threshold,
    )


def _check_per_trade_loss(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    threshold = budget.max_loss_per_trade
    if ctx.atr is None:
        return ("not_evaluable", "缺少 ATR(14)，無法推導停損距離與部位上限。", None, threshold)
    if ctx.total_equity_twd is None or not ctx.total_equity_twd > 0.0:
        return ("not_evaluable", "缺少總資產，無法換算單筆可承受虧損。", None, threshold)
    shares = ctx.held_shares()
    if shares is None:
        return ("not_evaluable", "缺少持股數或部位市值，無法估算停損時的損失。", None, threshold)
    stop_distance_twd = budget.atr_stop_multiple * ctx.atr * ctx.fx_to_twd
    if stop_distance_twd <= 0.0:
        return ("not_evaluable", "ATR(14) 為 0，停損距離無法定義。", None, threshold)
    loss_ratio = shares * stop_distance_twd / ctx.total_equity_twd
    basis = f"以 {budget.atr_stop_multiple:g}×ATR(14) 為停損距離"
    if _breaches(loss_ratio, threshold):
        return (
            "violated",
            f"{basis}，觸及停損時的損失約佔總資產 {_pct(loss_ratio)}，"
            f"已達或超過上限 {_pct(threshold)}。",
            loss_ratio,
            threshold,
        )
    return (
        "passed",
        f"{basis}，觸及停損時的損失約佔總資產 {_pct(loss_ratio)}，低於上限 {_pct(threshold)}。",
        loss_ratio,
        threshold,
    )


def _check_kelly_fraction(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    allowed = kelly_allowed_weight(budget, ctx)
    if allowed is None or ctx.win_rate is None or ctx.payoff_ratio is None:
        return (
            "not_evaluable",
            "缺少勝率或盈虧比，無法計算 Kelly 部位上限（目前沒有資料來源提供這兩項輸入）。",
            None,
            None,
        )
    weight = ctx.position_weight()
    if weight is None:
        return ("not_evaluable", "缺少總資產或部位市值，無法比較 Kelly 部位上限。", None, allowed)
    detail_head = (
        f"以勝率 {_pct(ctx.win_rate)}、盈虧比 {ctx.payoff_ratio:g} 計算，"
        f"{budget.kelly_fraction_cap:g} 分數 Kelly 與 {_pct(budget.kelly_position_cap)} "
        f"硬上限取小後為 {_pct(allowed)}"
    )
    if _breaches(weight, allowed):
        return (
            "violated",
            f"{detail_head}，目前佔比 {_pct(weight)} 已達或超過該上限。",
            weight,
            allowed,
        )
    return ("passed", f"{detail_head}，目前佔比 {_pct(weight)} 低於該上限。", weight, allowed)


_CHECKS: dict[str, Callable[[RiskBudget, PortfolioContext], CheckResult]] = {
    "single_position_weight": _check_single_position_weight,
    "sector_weight": _check_sector_weight,
    "gross_exposure": _check_gross_exposure,
    "per_trade_loss": _check_per_trade_loss,
    "kelly_fraction": _check_kelly_fraction,
}


def evaluate_limits(budget: RiskBudget, ctx: PortfolioContext) -> list[LimitCheck]:
    """Run every cap in :data:`LIMIT_IDS` order, numbered from 1."""
    checks: list[LimitCheck] = []
    for index, limit_id in enumerate(LIMIT_IDS, start=1):
        status, detail, observed, threshold = _CHECKS[limit_id](budget, ctx)
        checks.append(
            LimitCheck(
                index=index,
                id=limit_id,
                name=LIMIT_NAMES[limit_id],
                status=status,
                detail=detail,
                observed=observed,
                threshold=threshold,
            )
        )
    return checks


def notional_caps(budget: RiskBudget, ctx: PortfolioContext) -> dict[str, float]:
    """Per-cap TWD ceilings on *this symbol's* market value.

    Only the caps whose inputs are present appear in the result; the caller
    takes the minimum of what is there and reports what was left out.
    """
    caps: dict[str, float] = {}
    equity = ctx.total_equity_twd
    if equity is None or not equity > 0.0:
        return caps
    current = ctx.position_market_value_twd

    caps["single_position_weight"] = budget.max_position_weight * equity

    if ctx.sector is not None and ctx.sector_market_value_twd is not None and current is not None:
        others = max(ctx.sector_market_value_twd - current, 0.0)
        caps["sector_weight"] = max(budget.max_sector_weight * equity - others, 0.0)

    if ctx.gross_exposure_twd is not None and current is not None:
        others = max(ctx.gross_exposure_twd - current, 0.0)
        caps["gross_exposure"] = max(budget.max_gross_exposure * equity - others, 0.0)

    max_shares = atr_max_shares(budget, ctx)
    price = ctx.price_twd()
    if max_shares is not None and price is not None:
        caps["per_trade_loss"] = max_shares * price

    allowed = kelly_allowed_weight(budget, ctx)
    if allowed is not None:
        caps["kelly_fraction"] = allowed * equity

    return caps


def project_position(ctx: PortfolioContext, *, share_delta: float) -> PortfolioContext:
    """The same book after buying (``+``) or selling (``-``) ``share_delta`` shares.

    Used to *verify* a suggested quantity against the caps instead of trusting
    the arithmetic that produced it. Only the amounts a trade in this symbol
    actually moves are adjusted: the position, the gross exposure and the
    symbol's sector bucket. Equity is untouched -- a trade at market price
    swaps cash for shares and does not change the book's value.
    """
    price = ctx.price_twd()
    if price is None:  # pragma: no cover - callers check the price first
        return ctx
    delta_value = share_delta * price
    updates: dict[str, float] = {
        "position_market_value_twd": max((ctx.position_market_value_twd or 0.0) + delta_value, 0.0)
    }
    held = ctx.held_shares()
    if held is not None:
        updates["quantity"] = max(held + share_delta, 0.0)
    if ctx.gross_exposure_twd is not None:
        updates["gross_exposure_twd"] = max(ctx.gross_exposure_twd + delta_value, 0.0)
    if ctx.sector_market_value_twd is not None:
        updates["sector_market_value_twd"] = max(ctx.sector_market_value_twd + delta_value, 0.0)
    return ctx.model_copy(update=updates)


def limit_status_after(
    budget: RiskBudget, ctx: PortfolioContext, *, limit_id: str, share_delta: float
) -> LimitStatus:
    """Status of one cap after a hypothetical trade of ``share_delta`` shares."""
    status, _, _, _ = _CHECKS[limit_id](budget, project_position(ctx, share_delta=share_delta))
    return status


def suggest_quantity_range(
    budget: RiskBudget, ctx: PortfolioContext, *, action: str
) -> QuantityRange | None:
    """Share range implied by the binding cap, or ``None`` when undefined.

    * ``add`` -- how many more shares fit under the tightest cap. ``None`` when
      there is no headroom.
    * ``reduce`` / ``stop_loss`` / ``take_profit`` -- how many shares must go to
      get back under the tightest cap, up to the whole holding. ``None`` when
      nothing is above a cap, because trimming a compliant position is not
      something the risk budget can size.
    * anything else -- ``None``.

    Both edges are **verified against the cap they came from**: a cap counts as
    breached at equality (see :func:`_breaches`), so a quantity that lands
    exactly on the threshold would be flagged ``violated`` the moment it was
    acted on. The arithmetic edge is therefore re-checked through
    :func:`limit_status_after` and walked one share at a time until the
    resulting position sits strictly inside the cap.
    """
    price = ctx.price_twd()
    if price is None or price <= 0.0:
        return None
    caps = notional_caps(budget, ctx)
    if not caps:
        return None
    binding_id, binding_value = min(caps.items(), key=lambda item: item[1])
    skipped = [LIMIT_NAMES[i] for i in LIMIT_IDS if i not in caps]
    skipped_note = f"；未納入計算的上限：{'、'.join(skipped)}" if skipped else ""
    current = ctx.position_market_value_twd or 0.0

    if action == "add":
        upper = _largest_compliant_buy(
            budget, ctx, binding_id=binding_id, start=math.floor((binding_value - current) / price)
        )
        if upper is None:
            return None
        lower = max(1, math.floor(upper * RANGE_LOWER_RATIO))
        return QuantityRange(
            min_shares=lower,
            max_shares=upper,
            basis=(
                f"以「{LIMIT_NAMES[binding_id]}」為最小可用額度換算，"
                f"最多可再買進 {upper} 股（買進後該上限仍為通過），"
                f"區間下緣取上緣的一半{skipped_note}。"
            ),
        )

    if action in {"reduce", "stop_loss", "take_profit"}:
        if current - binding_value <= 0.0:
            return None
        held = ctx.held_shares()
        sellable = math.floor(held) if held is not None else None
        lower = _smallest_compliant_sell(
            budget,
            ctx,
            binding_id=binding_id,
            start=max(1, math.ceil((current - binding_value) / price)),
            sellable=sellable,
        )
        upper = max(lower, sellable) if sellable is not None else lower
        return QuantityRange(
            min_shares=lower,
            max_shares=upper,
            basis=(
                f"目前部位超出「{LIMIT_NAMES[binding_id]}」，"
                f"減去 {lower} 股可回到該上限之內，上緣為目前持股全數{skipped_note}。"
            ),
        )

    return None


def _largest_compliant_buy(
    budget: RiskBudget, ctx: PortfolioContext, *, binding_id: str, start: int
) -> int | None:
    """Largest buy at or below ``start`` that leaves the binding cap passing."""
    shares = start
    for _ in range(MAX_SIZING_ADJUSTMENTS):
        if shares < 1:
            return None
        if limit_status_after(budget, ctx, limit_id=binding_id, share_delta=shares) != "violated":
            return shares
        shares -= 1
    # The arithmetic edge is already within one share of the answer, so the
    # bound is only a safety valve against an inconsistent budget.
    return None  # pragma: no cover


def _smallest_compliant_sell(
    budget: RiskBudget, ctx: PortfolioContext, *, binding_id: str, start: int, sellable: int | None
) -> int:
    """Smallest sale from ``start`` up that leaves the binding cap passing.

    Capped at the whole holding: when even selling everything leaves the cap
    breached (something other than this position is driving it), the honest
    answer is still "sell the lot", not a quantity the user does not own.
    """
    shares = start
    for _ in range(MAX_SIZING_ADJUSTMENTS):
        if sellable is not None and shares >= sellable:
            return max(1, sellable)
        if limit_status_after(budget, ctx, limit_id=binding_id, share_delta=-shares) != "violated":
            return shares
        shares += 1
    return shares  # pragma: no cover - same safety valve as on the buy side
